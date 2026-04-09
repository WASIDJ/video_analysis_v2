"""骨骼特征提取模块.

基于关键点坐标的几何计算，提取关节角度、距离、对称性等特征.
"""
from typing import Dict, List, Optional, Tuple

import numpy as np

from ...core.models.base import Keypoint, PoseFrame, PoseSequence
from ...utils.geometry import (
    calculate_angle_2d,
    calculate_angle_3d,
    calculate_distance,
    calculate_vertical_angle,
)
from .base import BaseFeatureExtractor, FeatureSet


class SkeletonFeatureExtractor(BaseFeatureExtractor):
    """骨骼特征提取器.

    从姿态关键点提取几何特征:
    - 关节角度（2D/3D）
    - 肢体距离
    - 对齐度
    - 对称性
    - 速度/加速度
    """

    # 预定义的关节角度计算配置
    JOINT_ANGLES = {
        # 膝关节屈曲（矢状面）
        "knee_flexion_left": ("left_hip", "left_knee", "left_ankle"),
        "knee_flexion_right": ("right_hip", "right_knee", "right_ankle"),

        # 膝关节外翻（冠状面）
        "knee_valgus_left": ("left_hip", "left_knee", "left_ankle"),
        "knee_valgus_right": ("right_hip", "right_knee", "right_ankle"),

        # 髋关节角度
        "hip_flexion_left": ("left_shoulder", "left_hip", "left_knee"),
        "hip_flexion_right": ("right_shoulder", "right_hip", "right_knee"),

        # 肘关节角度
        "elbow_flexion_left": ("left_shoulder", "left_elbow", "left_wrist"),
        "elbow_flexion_right": ("right_shoulder", "right_elbow", "right_wrist"),

        # 躯干角度
        "trunk_lean": ("shoulder_center", "hip_center", "vertical"),  # 特殊处理
        "trunk_rotation": ("left_shoulder", "shoulder_center", "right_shoulder"),

        # 踝关节角度
        "ankle_dorsiflexion_left": ("left_knee", "left_ankle", "left_foot_index"),
        "ankle_dorsiflexion_right": ("right_knee", "right_ankle", "right_foot_index"),
    }

    # 预定义的距离计算
    DISTANCES = {
        "hip_width": ("left_hip", "right_hip"),
        "shoulder_width": ("left_shoulder", "right_shoulder"),
        "torso_length": ("shoulder_center", "hip_center"),
        "left_leg_length": ("left_hip", "left_ankle"),
        "right_leg_length": ("right_hip", "right_ankle"),
        "left_arm_length": ("left_shoulder", "left_wrist"),
        "right_arm_length": ("right_shoulder", "right_wrist"),
    }

    # 对称性计算
    SYMMETRY_PAIRS = {
        "knee_height": ("left_knee", "right_knee"),
        "hip_height": ("left_hip", "right_hip"),
        "shoulder_height": ("left_shoulder", "right_shoulder"),
        "wrist_height": ("left_wrist", "right_wrist"),
    }

    # 侧抬腿专用角度配置
    SIDE_LEG_RAISE_ANGLES = {
        # 髋关节外展角度（冠状面）
        "hip_abduction_left": ("shoulder_center", "left_hip", "left_knee"),
        "hip_abduction_right": ("shoulder_center", "right_hip", "right_knee"),
        # 躯干侧倾角度
        "trunk_lateral_flexion": ("hip_center", "shoulder_center", "vertical"),
        # 骨盆倾斜
        "pelvic_obliquity": ("left_hip", "hip_center", "right_hip"),
    }

    def __init__(self, use_3d: bool = False, min_confidence: float = 0.3):
        """
        Args:
            use_3d: 是否使用3D坐标计算角度
            min_confidence: 最小关键点置信度
        """
        super().__init__("skeleton_features")
        self.use_3d = use_3d
        self.min_confidence = min_confidence

    def get_supported_features(self) -> List[str]:
        """返回支持的特征列表."""
        features = list(self.JOINT_ANGLES.keys())
        features.extend(list(self.DISTANCES.keys()))
        features.extend(list(self.SIDE_LEG_RAISE_ANGLES.keys()))
        features.extend([f"{k}_symmetry" for k in self.SYMMETRY_PAIRS.keys()])
        features.extend(["center_of_mass_x", "center_of_mass_y"])
        features.extend(["leg_elevation_ratio_left", "leg_elevation_ratio_right"])
        return features

    def extract(self, pose_sequence: PoseSequence, **kwargs) -> List[FeatureSet]:
        """提取骨骼特征."""
        if not self.validate_sequence(pose_sequence):
            return []

        features = []

        # 提取关节角度
        angle_features = self._extract_joint_angles(pose_sequence)
        features.extend(angle_features)

        # 提取距离特征
        distance_features = self._extract_distances(pose_sequence)
        features.extend(distance_features)

        # 提取对称性特征
        symmetry_features = self._extract_symmetry(pose_sequence)
        features.extend(symmetry_features)

        # 提取质心特征
        com_features = self._extract_center_of_mass(pose_sequence)
        features.extend(com_features)

        # 提取速度特征
        velocity_features = self._extract_velocity(pose_sequence)
        features.extend(velocity_features)

        # 提取侧抬腿专用特征
        side_leg_features = self._extract_side_leg_raise_features(pose_sequence)
        features.extend(side_leg_features)

        return features

    def _extract_joint_angles(self, pose_sequence: PoseSequence) -> List[FeatureSet]:
        """提取关节角度特征."""
        features = []

        for angle_name, joint_names in self.JOINT_ANGLES.items():
            values = []

            for frame in pose_sequence.frames:
                # 获取关键点
                if "_center" in joint_names[0] or "_center" in joint_names[1]:
                    # 需要计算中心点
                    kp1 = self._get_virtual_keypoint(frame, joint_names[0])
                    kp2 = self._get_virtual_keypoint(frame, joint_names[1])
                    kp3 = self._get_virtual_keypoint(frame, joint_names[2])
                else:
                    kp1 = frame.get_keypoint(joint_names[0])
                    kp2 = frame.get_keypoint(joint_names[1])
                    kp3 = frame.get_keypoint(joint_names[2])

                # 计算角度
                if kp1 and kp2 and kp3:
                    if self.use_3d:
                        angle = calculate_angle_3d(
                            (kp1.x, kp1.y, kp1.z),
                            (kp2.x, kp2.y, kp2.z),
                            (kp3.x, kp3.y, kp3.z),
                            min_confidence=self.min_confidence,
                            confidences=(kp1.confidence, kp2.confidence, kp3.confidence),
                        )
                    else:
                        angle = calculate_angle_2d(
                            (kp1.x, kp1.y),
                            (kp2.x, kp2.y),
                            (kp3.x, kp3.y),
                            min_confidence=self.min_confidence,
                            confidences=(kp1.confidence, kp2.confidence, kp3.confidence),
                        )
                    values.append(angle)
                else:
                    values.append(np.nan)

            if values:
                features.append(FeatureSet(
                    name=angle_name,
                    values=np.array(values),
                    metadata={"type": "angle", "unit": "degrees"}
                ))

        return features

    def _extract_distances(self, pose_sequence: PoseSequence) -> List[FeatureSet]:
        """提取距离特征."""
        features = []

        for dist_name, joint_names in self.DISTANCES.items():
            values = []

            for frame in pose_sequence.frames:
                kp1 = self._get_virtual_keypoint(frame, joint_names[0])
                kp2 = self._get_virtual_keypoint(frame, joint_names[1])

                if kp1 and kp2:
                    dist = calculate_distance(
                        (kp1.x, kp1.y),
                        (kp2.x, kp2.y),
                        min_confidence=self.min_confidence,
                        confidences=(kp1.confidence, kp2.confidence),
                    )
                    values.append(dist)
                else:
                    values.append(np.nan)

            if values:
                features.append(FeatureSet(
                    name=dist_name,
                    values=np.array(values),
                    metadata={"type": "distance", "unit": "normalized"}
                ))

        return features

    def _extract_symmetry(self, pose_sequence: PoseSequence) -> List[FeatureSet]:
        """提取对称性特征（左右差异）."""
        features = []

        for sym_name, joint_pair in self.SYMMETRY_PAIRS.items():
            values = []

            for frame in pose_sequence.frames:
                kp_left = frame.get_keypoint(joint_pair[0])
                kp_right = frame.get_keypoint(joint_pair[1])

                if kp_left and kp_right:
                    # 计算高度差（归一化到图像高度）
                    height_diff = abs(kp_left.y - kp_right.y)
                    values.append(height_diff)
                else:
                    values.append(np.nan)

            if values:
                features.append(FeatureSet(
                    name=f"{sym_name}_symmetry",
                    values=np.array(values),
                    metadata={"type": "symmetry", "unit": "normalized"}
                ))

        return features

    def _extract_center_of_mass(self, pose_sequence: PoseSequence) -> List[FeatureSet]:
        """提取质心/重心特征."""
        x_values = []
        y_values = []

        for frame in pose_sequence.frames:
            # 基于髋部和肩部中心计算
            left_hip = frame.get_keypoint("left_hip")
            right_hip = frame.get_keypoint("right_hip")
            left_shoulder = frame.get_keypoint("left_shoulder")
            right_shoulder = frame.get_keypoint("right_shoulder")

            if all([left_hip, right_hip, left_shoulder, right_shoulder]):
                # 简化计算：髋部中点和肩部中点的加权平均
                hip_center_x = (left_hip.x + right_hip.x) / 2
                hip_center_y = (left_hip.y + right_hip.y) / 2
                shoulder_center_x = (left_shoulder.x + right_shoulder.x) / 2
                shoulder_center_y = (left_shoulder.y + right_shoulder.y) / 2

                # 质心更接近髋部（重心偏下）
                com_x = hip_center_x * 0.6 + shoulder_center_x * 0.4
                com_y = hip_center_y * 0.6 + shoulder_center_y * 0.4

                x_values.append(com_x)
                y_values.append(com_y)
            else:
                x_values.append(np.nan)
                y_values.append(np.nan)

        return [
            FeatureSet(name="center_of_mass_x", values=np.array(x_values), metadata={"type": "position"}),
            FeatureSet(name="center_of_mass_y", values=np.array(y_values), metadata={"type": "position"}),
        ]

    def _extract_side_leg_raise_features(self, pose_sequence: PoseSequence) -> List[FeatureSet]:
        """提取侧抬腿专用特征.

        侧抬腿动作的关键特征:
        - 髋关节外展角度
        - 躯干侧倾（代偿检测）
        - 骨盆倾斜
        - 抬腿高度比例
        """
        features = []

        # 1. 提取髋关节外展角度（冠状面）
        for angle_name, joint_names in self.SIDE_LEG_RAISE_ANGLES.items():
            values = []

            for frame in pose_sequence.frames:
                kp1 = self._get_virtual_keypoint(frame, joint_names[0])
                kp2 = self._get_virtual_keypoint(frame, joint_names[1])
                kp3 = self._get_virtual_keypoint(frame, joint_names[2])

                if kp1 and kp2 and kp3:
                    # 对于外展角度，需要计算相对于垂直面的角度
                    if "abduction" in angle_name:
                        angle = self._calculate_abduction_angle(kp1, kp2, kp3)
                    elif "lateral_flexion" in angle_name:
                        angle = self._calculate_lateral_flexion(kp1, kp2, kp3)
                    elif "obliquity" in angle_name:
                        angle = self._calculate_pelvic_obliquity(kp1, kp2, kp3)
                    else:
                        angle = calculate_angle_2d(
                            (kp1.x, kp1.y), (kp2.x, kp2.y), (kp3.x, kp3.y),
                            min_confidence=self.min_confidence,
                            confidences=(kp1.confidence, kp2.confidence, kp3.confidence),
                        )
                    values.append(angle)
                else:
                    values.append(np.nan)

            if values:
                features.append(FeatureSet(
                    name=angle_name,
                    values=np.array(values),
                    metadata={"type": "angle", "unit": "degrees", "category": "side_leg_raise"}
                ))

        # 2. 计算抬腿高度比例
        elevation_features = self._extract_leg_elevation_ratio(pose_sequence)
        features.extend(elevation_features)

        # 3. 计算左右腿外展对称性
        symmetry_features = self._extract_abduction_symmetry(pose_sequence)
        features.extend(symmetry_features)

        return features

    def _calculate_abduction_angle(self, hip: Keypoint, knee: Keypoint, shoulder: Keypoint) -> float:
        """计算髋关节外展角度.

        外展角度 = 大腿与垂直线的夹角（冠状面）
        0度 = 腿垂直向下（站立位）
        90度 = 腿水平外展
        """
        # 计算大腿向量（髋到膝）
        thigh_vector_x = knee.x - hip.x
        thigh_vector_y = knee.y - hip.y

        # 垂直向下的参考向量
        vertical_x = 0
        vertical_y = 1  # 图像坐标系中y向下为正

        # 计算夹角
        dot_product = thigh_vector_x * vertical_x + thigh_vector_y * vertical_y
        thigh_length = np.sqrt(thigh_vector_x**2 + thigh_vector_y**2)

        if thigh_length < 1e-6:
            return np.nan

        cos_angle = np.clip(dot_product / thigh_length, -1.0, 1.0)
        angle = np.degrees(np.arccos(cos_angle))

        return angle

    def _calculate_lateral_flexion(self, hip_center: Keypoint, shoulder_center: Keypoint, vertical: Keypoint) -> float:
        """计算躯干侧倾角度（冠状面）."""
        # 计算躯干向量
        trunk_x = shoulder_center.x - hip_center.x
        trunk_y = shoulder_center.y - hip_center.y

        # 垂直参考
        vertical_x = 0
        vertical_y = -1  # 向上

        # 计算夹角
        dot_product = trunk_x * vertical_x + trunk_y * vertical_y
        trunk_length = np.sqrt(trunk_x**2 + trunk_y**2)

        if trunk_length < 1e-6:
            return np.nan

        cos_angle = np.clip(dot_product / trunk_length, -1.0, 1.0)
        angle = np.degrees(np.arccos(cos_angle))

        return angle

    def _calculate_pelvic_obliquity(self, left_hip: Keypoint, hip_center: Keypoint, right_hip: Keypoint) -> float:
        """计算骨盆倾斜度（冠状面）."""
        # 计算左右髂嵴连线与水平面的夹角
        hip_line_x = right_hip.x - left_hip.x
        hip_line_y = right_hip.y - left_hip.y

        # 水平参考
        horizontal_x = 1
        horizontal_y = 0

        # 计算夹角
        dot_product = hip_line_x * horizontal_x + hip_line_y * horizontal_y
        hip_line_length = np.sqrt(hip_line_x**2 + hip_line_y**2)

        if hip_line_length < 1e-6:
            return np.nan

        cos_angle = np.clip(dot_product / hip_line_length, -1.0, 1.0)
        angle = np.degrees(np.arccos(cos_angle))

        return angle

    def _extract_leg_elevation_ratio(self, pose_sequence: PoseSequence) -> List[FeatureSet]:
        """提取腿部抬升高度比例.

        计算抬腿脚踝相对于髋部中心的高度比例。
        """
        left_ratios = []
        right_ratios = []

        for frame in pose_sequence.frames:
            hip_center = self._get_virtual_keypoint(frame, "hip_center")
            left_ankle = frame.get_keypoint("left_ankle")
            right_ankle = frame.get_keypoint("right_ankle")

            if hip_center and left_ankle and right_ankle:
                # 计算相对于髋部中心的高度差（y坐标差，图像坐标系y向下）
                left_height = hip_center.y - left_ankle.y  # 正值表示抬升
                right_height = hip_center.y - right_ankle.y

                # 归一化到腿部长度（简化：髋到踝的参考长度约0.4-0.5倍图像高度）
                reference_length = 0.45

                left_ratio = left_height / reference_length
                right_ratio = right_height / reference_length

                left_ratios.append(left_ratio)
                right_ratios.append(right_ratio)
            else:
                left_ratios.append(np.nan)
                right_ratios.append(np.nan)

        features = []
        if left_ratios:
            features.append(FeatureSet(
                name="leg_elevation_ratio_left",
                values=np.array(left_ratios),
                metadata={"type": "ratio", "unit": "normalized", "category": "side_leg_raise"}
            ))
        if right_ratios:
            features.append(FeatureSet(
                name="leg_elevation_ratio_right",
                values=np.array(right_ratios),
                metadata={"type": "ratio", "unit": "normalized", "category": "side_leg_raise"}
            ))

        return features

    def _extract_abduction_symmetry(self, pose_sequence: PoseSequence) -> List[FeatureSet]:
        """提取左右外展对称性.

        比较左右腿外展角度的差异。
        """
        symmetry_values = []

        for frame in pose_sequence.frames:
            # 获取左右髋和膝
            left_hip = frame.get_keypoint("left_hip")
            left_knee = frame.get_keypoint("left_knee")
            right_hip = frame.get_keypoint("right_hip")
            right_knee = frame.get_keypoint("right_knee")
            shoulder_center = self._get_virtual_keypoint(frame, "shoulder_center")

            if all([left_hip, left_knee, right_hip, right_knee, shoulder_center]):
                # 计算左右外展角度
                left_abduction = self._calculate_abduction_angle(left_hip, left_knee, shoulder_center)
                right_abduction = self._calculate_abduction_angle(right_hip, right_knee, shoulder_center)

                if not (np.isnan(left_abduction) or np.isnan(right_abduction)):
                    # 对称性得分 = 1 - |差值| / 最大值
                    max_angle = max(abs(left_abduction), abs(right_abduction))
                    if max_angle > 5:  # 避免除零
                        symmetry = 1.0 - abs(left_abduction - right_abduction) / max_angle
                        symmetry_values.append(max(0, symmetry))
                    else:
                        symmetry_values.append(1.0)  # 都接近0，认为对称
                else:
                    symmetry_values.append(np.nan)
            else:
                symmetry_values.append(np.nan)

        if symmetry_values:
            return [FeatureSet(
                name="hip_abduction_symmetry",
                values=np.array(symmetry_values),
                metadata={"type": "symmetry", "unit": "score", "category": "side_leg_raise"}
            )]
        return []

    def _extract_velocity(self, pose_sequence: PoseSequence) -> List[FeatureSet]:
        """提取速度特征（质心速度）."""
        com_x = []
        com_y = []

        for frame in pose_sequence.frames:
            left_hip = frame.get_keypoint("left_hip")
            right_hip = frame.get_keypoint("right_hip")
            left_shoulder = frame.get_keypoint("left_shoulder")
            right_shoulder = frame.get_keypoint("right_shoulder")

            if all([left_hip, right_hip, left_shoulder, right_shoulder]):
                hip_center_x = (left_hip.x + right_hip.x) / 2
                hip_center_y = (left_hip.y + right_hip.y) / 2
                shoulder_center_x = (left_shoulder.x + right_shoulder.x) / 2
                shoulder_center_y = (left_shoulder.y + right_shoulder.y) / 2

                com_x.append(hip_center_x * 0.6 + shoulder_center_x * 0.4)
                com_y.append(hip_center_y * 0.6 + shoulder_center_y * 0.4)
            else:
                com_x.append(np.nan)
                com_y.append(np.nan)

        # 计算速度
        vx = np.gradient(com_x) if len(com_x) > 1 else np.array([0.0])
        vy = np.gradient(com_y) if len(com_y) > 1 else np.array([0.0])
        v_magnitude = np.sqrt(vx**2 + vy**2)

        return [
            FeatureSet(name="com_velocity_x", values=vx, metadata={"type": "velocity"}),
            FeatureSet(name="com_velocity_y", values=vy, metadata={"type": "velocity"}),
            FeatureSet(name="com_velocity_magnitude", values=v_magnitude, metadata={"type": "velocity"}),
        ]

    def _get_virtual_keypoint(self, frame: PoseFrame, name: str) -> Optional[Keypoint]:
        """获取或计算虚拟关键点."""
        # 检查是否是直接存在的点
        kp = frame.get_keypoint(name)
        if kp:
            return kp

        # 计算中心点
        if name == "shoulder_center":
            left = frame.get_keypoint("left_shoulder")
            right = frame.get_keypoint("right_shoulder")
            if left and right:
                return Keypoint(
                    name="shoulder_center",
                    x=(left.x + right.x) / 2,
                    y=(left.y + right.y) / 2,
                    z=(left.z + right.z) / 2,
                    visibility=min(left.visibility, right.visibility),
                    confidence=min(left.confidence, right.confidence),
                )

        elif name == "hip_center":
            left = frame.get_keypoint("left_hip")
            right = frame.get_keypoint("right_hip")
            if left and right:
                return Keypoint(
                    name="hip_center",
                    x=(left.x + right.x) / 2,
                    y=(left.y + right.y) / 2,
                    z=(left.z + right.z) / 2,
                    visibility=min(left.visibility, right.visibility),
                    confidence=min(left.confidence, right.confidence),
                )

        elif name == "vertical":
            # 垂直参考点（用于计算躯干倾斜）
            shoulder_center = self._get_virtual_keypoint(frame, "shoulder_center")
            if shoulder_center:
                return Keypoint(
                    name="vertical",
                    x=shoulder_center.x,
                    y=shoulder_center.y - 0.1,  # 上方
                    z=shoulder_center.z,
                    visibility=1.0,
                    confidence=1.0,
                )

        return None
