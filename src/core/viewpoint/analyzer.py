"""视角分析器.

自动检测视频拍摄视角（正面、侧面、斜角等），并评估检测项可靠性.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.core.models.base import PoseSequence


class CameraViewpoint(Enum):
    """相机视角分类."""
    FRONTAL = "frontal"           # 正面（0°）- 正对人物
    NEAR_FRONTAL = "near_frontal" # 近正面（0-30°）
    DIAGONAL = "diagonal"         # 斜角（30-60°）
    SAGITTAL = "sagittal"         # 纯侧面（90°）
    NEAR_SAGITTAL = "near_sagittal"  # 近侧面（60-90°）
    UNKNOWN = "unknown"           # 无法判断


@dataclass
class ViewpointAnalysisResult:
    """视角分析结果."""
    viewpoint: CameraViewpoint
    confidence: float                    # 视角判断置信度
    hip_width_px: float                  # 髋部宽度（像素）
    shoulder_width_px: float             # 肩宽（像素）
    hip_shoulder_ratio: float            # 髋肩比（用于判断视角）
    left_side_visible: bool              # 左侧是否可见
    right_side_visible: bool             # 右侧是否可见
    depth_reliability: float             # 深度估计可靠性
    recommended_side: Optional[str]      # 推荐使用的侧面


class ViewpointAnalyzer:
    """视角分析器.

    通过分析关键点几何特征自动判断相机视角.
    """

    def __init__(self, min_confidence: float = 0.5):
        self.min_confidence = min_confidence

    def analyze(self, pose_sequence: PoseSequence) -> ViewpointAnalysisResult:
        """分析视频视角.

        使用多种几何特征综合判断：
        1. 髋宽/肩宽比例 - 侧面时比例接近1（投影收缩）
        2. 左右关键点可见性 - 侧面时一侧被遮挡
        3. 深度变化一致性 - 侧面时深度变化与水平移动相关
        """
        if len(pose_sequence) == 0:
            return self._create_unknown_result()

        # 采样多帧进行稳定判断
        sample_frames = self._select_sample_frames(pose_sequence)

        # 计算几何特征
        hip_shoulder_ratios = []
        left_visible_ratios = []
        right_visible_ratios = []
        depth_variations = []

        for frame in sample_frames:
            # 1. 髋肩比分析
            ratio = self._calculate_hip_shoulder_ratio(frame)
            if ratio is not None:
                hip_shoulder_ratios.append(ratio)

            # 2. 左右可见性分析
            left_vis, right_vis = self._analyze_side_visibility(frame)
            left_visible_ratios.append(left_vis)
            right_visible_ratios.append(right_vis)

            # 3. 深度变化分析
            depth_var = self._analyze_depth_variation(frame)
            if depth_var is not None:
                depth_variations.append(depth_var)

        # 综合判断视角
        if len(hip_shoulder_ratios) == 0:
            return self._create_unknown_result()

        avg_ratio = np.mean(hip_shoulder_ratios)
        avg_left_vis = np.mean(left_visible_ratios)
        avg_right_vis = np.mean(right_visible_ratios)

        # 判断逻辑
        viewpoint, confidence = self._determine_viewpoint(
            avg_ratio, avg_left_vis, avg_right_vis, depth_variations
        )

        # 确定推荐侧面
        recommended_side = self._determine_recommended_side(
            avg_left_vis, avg_right_vis, sample_frames
        )

        return ViewpointAnalysisResult(
            viewpoint=viewpoint,
            confidence=confidence,
            hip_width_px=0.0,  # 简化处理
            shoulder_width_px=0.0,
            hip_shoulder_ratio=avg_ratio,
            left_side_visible=avg_left_vis > 0.5,
            right_side_visible=avg_right_vis > 0.5,
            depth_reliability=self._calculate_depth_reliability(
                viewpoint, depth_variations
            ),
            recommended_side=recommended_side,
        )

    def _select_sample_frames(
        self, pose_sequence: PoseSequence, num_samples: int = 10
    ) -> List:
        """选择代表性帧进行分析."""
        total = len(pose_sequence)
        if total <= num_samples:
            return pose_sequence.frames

        indices = np.linspace(0, total - 1, num_samples, dtype=int)
        return [pose_sequence.frames[i] for i in indices]

    def _calculate_hip_shoulder_ratio(self, frame) -> Optional[float]:
        """计算髋宽/肩宽比例.

        正面视角：肩宽 > 髋宽，比例约 0.7-0.8
        侧面视角：两者都收缩，比例接近 1.0
        """
        left_shoulder = frame.get_keypoint("left_shoulder")
        right_shoulder = frame.get_keypoint("right_shoulder")
        left_hip = frame.get_keypoint("left_hip")
        right_hip = frame.get_keypoint("right_hip")

        if not all([left_shoulder, right_shoulder, left_hip, right_hip]):
            return None

        # 计算宽度（归一化坐标下的距离）
        shoulder_width = abs(right_shoulder.x - left_shoulder.x)
        hip_width = abs(right_hip.x - left_hip.x)

        if shoulder_width < 0.01:  # 避免除零
            return None

        return hip_width / shoulder_width

    def _analyze_side_visibility(self, frame) -> Tuple[float, float]:
        """分析左右侧关键点的可见性.

        返回左右侧可见度（0-1）
        """
        # 定义左右侧关键点
        left_points = ["left_shoulder", "left_elbow", "left_wrist",
                      "left_hip", "left_knee", "left_ankle"]
        right_points = ["right_shoulder", "right_elbow", "right_wrist",
                       "right_hip", "right_knee", "right_ankle"]

        left_visible = sum(
            1 for p in left_points
            if frame.get_keypoint(p) and
            frame.get_keypoint(p).confidence > self.min_confidence
        ) / len(left_points)

        right_visible = sum(
            1 for p in right_points
            if frame.get_keypoint(p) and
            frame.get_keypoint(p).confidence > self.min_confidence
        ) / len(right_points)

        return left_visible, right_visible

    def _analyze_depth_variation(self, frame) -> Optional[float]:
        """分析深度估计的变异性.

        使用左右髋的z坐标差异估计深度可靠性.
        侧面视角时，左右髋应有明显深度差.
        """
        left_hip = frame.get_keypoint("left_hip")
        right_hip = frame.get_keypoint("right_hip")

        if not (left_hip and right_hip):
            return None

        # 检查是否有z坐标
        if left_hip.z == 0 and right_hip.z == 0:
            return None

        depth_diff = abs(left_hip.z - right_hip.z)
        return depth_diff

    def _determine_viewpoint(
        self,
        hip_shoulder_ratio: float,
        left_visible: float,
        right_visible: float,
        depth_variations: List[float],
    ) -> Tuple[CameraViewpoint, float]:
        """确定视角类型.

        判断逻辑：
        - 深度差大 + 双侧可见性高 → 侧面（左右有明显前后距离）
        - 髋肩比正常(0.7-0.8) + 双侧可见性高 → 正面
        - 髋肩比很小(<0.3) + 深度差明显 → 侧面（投影收缩）
        """
        # 基于可见性的判断
        visibility_diff = abs(left_visible - right_visible)
        min_visibility = min(left_visible, right_visible)

        # 计算平均深度差
        avg_depth_diff = np.mean(depth_variations) if depth_variations else 0

        # 侧面视角的显著特征：
        # 1. 深度差大（左右髋/肩有明显的前后距离）
        # 2. 髋肩比可能异常小（投影收缩）
        # 3. 或者髋肩比接近1（都收缩）

        is_likely_sagittal = False
        sagittal_confidence = 0.5

        # 特征1: 明显的深度差异（左右在z轴上分离）
        if avg_depth_diff > 0.15:
            is_likely_sagittal = True
            sagittal_confidence += 0.2

        # 特征2: 髋肩比异常小（投影严重收缩）
        if hip_shoulder_ratio < 0.3:
            is_likely_sagittal = True
            sagittal_confidence += 0.2

        # 特征3: 髋肩比接近1（肩和髋同等收缩）
        if 0.8 <= hip_shoulder_ratio <= 1.2:
            is_likely_sagittal = True
            sagittal_confidence += 0.15

        # 特征4: 单侧可见性差
        if visibility_diff > 0.2 or min_visibility < 0.4:
            is_likely_sagittal = True
            sagittal_confidence += 0.15

        if is_likely_sagittal:
            if sagittal_confidence > 0.8:
                return CameraViewpoint.SAGITTAL, min(sagittal_confidence, 0.95)
            else:
                return CameraViewpoint.NEAR_SAGITTAL, sagittal_confidence

        # 正面视角判断
        if 0.65 <= hip_shoulder_ratio <= 0.85 and avg_depth_diff < 0.1:
            return CameraViewpoint.FRONTAL, 0.85
        elif 0.55 <= hip_shoulder_ratio <= 0.9:
            return CameraViewpoint.NEAR_FRONTAL, 0.70
        else:
            return CameraViewpoint.DIAGONAL, 0.55

    def _determine_recommended_side(
        self,
        left_visible: float,
        right_visible: float,
        sample_frames: List,
    ) -> Optional[str]:
        """确定推荐使用的侧面.

        选择可见性更高、运动范围更大的一侧.
        """
        if left_visible > right_visible + 0.2:
            return "left"
        elif right_visible > left_visible + 0.2:
            return "right"

        # 可见性相近，比较运动范围
        left_range = self._calculate_side_motion_range(sample_frames, "left")
        right_range = self._calculate_side_motion_range(sample_frames, "right")

        if left_range > right_range:
            return "left"
        elif right_range > left_range:
            return "right"

        # 仍无法确定，默认右侧（大多数人的优势侧）
        return "right"

    def _calculate_side_motion_range(
        self, frames: List, side: str
    ) -> float:
        """计算一侧关键点的运动范围."""
        key_points = [f"{side}_hip", f"{side}_knee", f"{side}_ankle"]

        y_positions = []
        for frame in frames:
            knee = frame.get_keypoint(f"{side}_knee")
            if knee and knee.confidence > self.min_confidence:
                y_positions.append(knee.y)

        if len(y_positions) < 2:
            return 0.0

        return max(y_positions) - min(y_positions)

    def _calculate_depth_reliability(
        self,
        viewpoint: CameraViewpoint,
        depth_variations: List[float],
    ) -> float:
        """计算深度估计的可靠性.

        侧面视角下深度估计通常更可靠（左右有明显深度差）.
        正面视角下深度估计不可靠（左右深度相近，易产生噪点）.
        """
        if len(depth_variations) == 0:
            return 0.3

        avg_variation = np.mean(depth_variations)

        if viewpoint in [CameraViewpoint.SAGITTAL, CameraViewpoint.NEAR_SAGITTAL]:
            # 侧面视角，深度差异应明显
            if avg_variation > 0.1:
                return 0.8
            else:
                return 0.5
        elif viewpoint in [CameraViewpoint.FRONTAL, CameraViewpoint.NEAR_FRONTAL]:
            # 正面视角，深度估计不可靠
            return 0.3
        else:
            return 0.5

    def _create_unknown_result(self) -> ViewpointAnalysisResult:
        """创建未知视角的结果."""
        return ViewpointAnalysisResult(
            viewpoint=CameraViewpoint.UNKNOWN,
            confidence=0.0,
            hip_width_px=0.0,
            shoulder_width_px=0.0,
            hip_shoulder_ratio=1.0,
            left_side_visible=True,
            right_side_visible=True,
            depth_reliability=0.3,
            recommended_side="right",
        )
