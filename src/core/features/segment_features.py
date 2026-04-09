"""体块特征提取模块.

基于人体分割（Mask）和轮廓分析，提取骨骼点无法描述的特征：
- 脊柱曲率（塌腰/驼背识别）
- 肩部上提比例（耸肩识别）
- 骨盆倾斜
- 身体轮廓不对称性
"""
from typing import Any, List, Optional, Tuple

import cv2
import numpy as np

from ...core.models.base import PoseFrame, PoseSequence
from .base import BaseFeatureExtractor, FeatureSet


class SegmentFeatureExtractor(BaseFeatureExtractor):
    """体块特征提取器.

    使用人体分割模型提取Mask和轮廓，结合关键点计算体块特征.

    主要功能:
    1. 脊柱曲率分析 - 识别塌腰、驼背
    2. 肩部轮廓分析 - 识别耸肩
    3. 骨盆轮廓分析 - 识别骨盆前倾/后倾
    4. 身体对称性分析 - 基于轮廓的左右对称性
    """

    def __init__(
        self,
        segmentation_model: Optional[Any] = None,
        model_type: str = "mediapipe",
        min_mask_area: float = 0.05,
    ):
        """
        Args:
            segmentation_model: 人体分割模型实例
            model_type: 模型类型 ('mediapipe' / 'opencv' / 'none')
            min_mask_area: 最小有效Mask面积占比
        """
        super().__init__("segment_features", {"model_type": model_type})
        self.model_type = model_type
        self.min_mask_area = min_mask_area
        self._segmentation_model = segmentation_model
        self._is_initialized = False

    def initialize(self) -> None:
        """初始化分割模型."""
        if self._is_initialized:
            return

        if self.model_type == "mediapipe":
            import mediapipe as mp
            self._mp_selfie_segmentation = mp.solutions.selfie_segmentation
            self._segmentation_model = self._mp_selfie_segmentation.SelfieSegmentation(
                model_selection=1
            )
        elif self.model_type == "opencv":
            # 使用OpenCV的DNN分割或背景减除
            self._segmentation_model = None  # 使用传统CV方法

        self._is_initialized = True

    def get_supported_features(self) -> List[str]:
        """返回支持的特征列表."""
        return [
            "lumbar_curvature",
            "thoracic_curvature",
            "shoulder_lift_ratio",
            "pelvis_tilt_from_contour",
            "body_contour_symmetry",
            "torso_area_ratio",
        ]

    def extract(
        self,
        pose_sequence: PoseSequence,
        video_frames: Optional[List[np.ndarray]] = None,
        **kwargs
    ) -> List[FeatureSet]:
        """提取体块特征.

        Args:
            pose_sequence: 姿态序列
            video_frames: 对应的视频帧列表（用于分割）
            **kwargs: 额外参数

        Returns:
            特征集合列表
        """
        if not self.validate_sequence(pose_sequence):
            return []

        if not self._is_initialized:
            self.initialize()

        if video_frames is None or len(video_frames) != len(pose_sequence):
            # 无法提取体块特征
            return []

        features = {
            "lumbar_curvature": [],
            "thoracic_curvature": [],
            "shoulder_lift_ratio": [],
            "pelvis_tilt_from_contour": [],
            "body_contour_symmetry": [],
            "torso_area_ratio": [],
        }

        for frame, video_frame in zip(pose_sequence.frames, video_frames):
            # 提取人体Mask
            mask = self._extract_mask(video_frame)

            if mask is None or np.sum(mask) < (mask.size * self.min_mask_area):
                # Mask无效，填充nan
                for key in features:
                    features[key].append(np.nan)
                continue

            # 提取轮廓
            contour = self._extract_contour(mask)

            if contour is None:
                for key in features:
                    features[key].append(np.nan)
                continue

            # 计算各特征
            features["lumbar_curvature"].append(
                self._calculate_lumbar_curvature(contour, frame, mask.shape)
            )
            features["thoracic_curvature"].append(
                self._calculate_thoracic_curvature(contour, frame, mask.shape)
            )
            features["shoulder_lift_ratio"].append(
                self._calculate_shoulder_lift_ratio(contour, frame, mask.shape)
            )
            features["pelvis_tilt_from_contour"].append(
                self._calculate_pelvis_tilt(contour, frame, mask.shape)
            )
            features["body_contour_symmetry"].append(
                self._calculate_contour_symmetry(contour, mask.shape)
            )
            features["torso_area_ratio"].append(
                self._calculate_torso_area_ratio(contour, mask)
            )

        # 转换为FeatureSet列表
        return [
            FeatureSet(name=name, values=np.array(values), metadata={"type": "segment"})
            for name, values in features.items()
        ]

    def _extract_mask(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """提取人体二值Mask."""
        if self.model_type == "mediapipe":
            return self._extract_mask_mediapipe(frame)
        elif self.model_type == "opencv":
            return self._extract_mask_opencv(frame)
        else:
            # 使用简单的肤色检测作为备选
            return self._extract_mask_simple(frame)

    def _extract_mask_mediapipe(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """使用MediaPipe Selfie Segmentation."""
        import mediapipe as mp

        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self._segmentation_model.process(rgb_frame)

        if results.segmentation_mask is not None:
            return (results.segmentation_mask > 0.5).astype(np.uint8)
        return None

    def _extract_mask_opencv(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """使用OpenCV进行简单的背景分离."""
        # 转换到HSV
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

        # 肤色范围
        lower_skin = np.array([0, 20, 70])
        upper_skin = np.array([20, 255, 255])

        # 创建肤色Mask
        mask = cv2.inRange(hsv, lower_skin, upper_skin)

        # 形态学操作
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

        return mask.astype(np.uint8)

    def _extract_mask_simple(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """简单的前景提取方法."""
        # 使用GrabCut
        h, w = frame.shape[:2]
        mask = np.zeros((h, w), np.uint8)
        bgd_model = np.zeros((1, 65), np.float64)
        fgd_model = np.zeros((1, 65), np.float64)

        # 以图像中心为初始矩形
        rect = (w // 4, h // 4, w // 2, h // 2)

        try:
            cv2.grabCut(frame, mask, rect, bgd_model, fgd_model, 5, cv2.GC_INIT_WITH_RECT)
            mask = np.where((mask == 2) | (mask == 0), 0, 1).astype(np.uint8)
            return mask
        except cv2.error:
            return None

    def _extract_contour(self, mask: np.ndarray) -> Optional[np.ndarray]:
        """从Mask提取轮廓."""
        contours, _ = cv2.findContours(
            mask.astype(np.uint8),
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )

        if not contours:
            return None

        # 返回最大轮廓
        return max(contours, key=cv2.contourArea)

    def _calculate_lumbar_curvature(
        self,
        contour: np.ndarray,
        pose_frame: PoseFrame,
        mask_shape: Tuple[int, int]
    ) -> float:
        """计算腰椎曲率（用于识别塌腰）.

        思路:
        1. 找到腰椎区域（hip_center到shoulder_center之间）
        2. 提取该区域的轮廓片段
        3. 拟合曲线计算曲率
        """
        h, w = mask_shape

        # 获取关键点
        left_hip = pose_frame.get_keypoint("left_hip")
        right_hip = pose_frame.get_keypoint("right_hip")
        left_shoulder = pose_frame.get_keypoint("left_shoulder")
        right_shoulder = pose_frame.get_keypoint("right_shoulder")

        if not all([left_hip, right_hip, left_shoulder, right_shoulder]):
            return np.nan

        # 计算中心点（像素坐标）
        hip_center_y = int((left_hip.y + right_hip.y) / 2 * h)
        shoulder_center_y = int((left_shoulder.y + right_shoulder.y) / 2 * h)

        # 腰椎区域（腰部到胸部之间）
        lumbar_top = int(shoulder_center_y + (hip_center_y - shoulder_center_y) * 0.6)
        lumbar_bottom = hip_center_y

        # 提取腰椎区域的轮廓点
        lumbar_points = []
        for point in contour:
            px, py = point[0]
            if lumbar_top <= py <= lumbar_bottom:
                lumbar_points.append([px, py])

        if len(lumbar_points) < 5:
            return np.nan

        lumbar_points = np.array(lumbar_points)

        # 计算脊柱曲线（取x坐标的中值）
        y_coords = np.linspace(lumbar_top, lumbar_bottom, 20)
        spine_x = []

        for y in y_coords:
            x_at_y = lumbar_points[np.abs(lumbar_points[:, 1] - y) < 3][:, 0]
            if len(x_at_y) >= 2:
                # 取中间位置（脊柱大致在中间）
                spine_x.append(np.mean(x_at_y))
            else:
                spine_x.append(np.nan)

        # 移除nan
        spine_x = np.array(spine_x)
        valid_mask = ~np.isnan(spine_x)

        if np.sum(valid_mask) < 5:
            return np.nan

        # 计算曲率（二阶导数的近似）
        try:
            spine_x_valid = spine_x[valid_mask]
            if len(spine_x_valid) < 3:
                return 0.0

            # 计算变化率
            first_deriv = np.gradient(spine_x_valid)
            curvature = np.std(first_deriv)  # 使用标准差作为曲率度量

            # 归一化
            torso_height = abs(hip_center_y - shoulder_center_y)
            if torso_height > 0:
                curvature = curvature / torso_height

            return float(curvature)
        except Exception:
            return np.nan

    def _calculate_thoracic_curvature(
        self,
        contour: np.ndarray,
        pose_frame: PoseFrame,
        mask_shape: Tuple[int, int]
    ) -> float:
        """计算胸椎曲率（用于识别驼背）."""
        h, w = mask_shape

        # 获取关键点
        left_shoulder = pose_frame.get_keypoint("left_shoulder")
        right_shoulder = pose_frame.get_keypoint("right_shoulder")
        nose = pose_frame.get_keypoint("nose")

        if not all([left_shoulder, right_shoulder, nose]):
            return np.nan

        shoulder_center_y = int((left_shoulder.y + right_shoulder.y) / 2 * h)
        nose_y = int(nose.y * h)

        # 胸椎区域
        thoracic_top = nose_y + (shoulder_center_y - nose_y) // 3
        thoracic_bottom = shoulder_center_y

        # 提取胸椎区域轮廓点
        thoracic_points = []
        for point in contour:
            px, py = point[0]
            if thoracic_top <= py <= thoracic_bottom:
                thoracic_points.append([px, py])

        if len(thoracic_points) < 5:
            return np.nan

        # 类似于腰椎曲率计算
        thoracic_points = np.array(thoracic_points)
        y_coords = np.linspace(thoracic_top, thoracic_bottom, 15)
        spine_x = []

        for y in y_coords:
            x_at_y = thoracic_points[np.abs(thoracic_points[:, 1] - y) < 3][:, 0]
            if len(x_at_y) >= 2:
                spine_x.append(np.mean(x_at_y))
            else:
                spine_x.append(np.nan)

        spine_x = np.array(spine_x)
        valid_mask = ~np.isnan(spine_x)

        if np.sum(valid_mask) < 3:
            return 0.0

        try:
            spine_x_valid = spine_x[valid_mask]
            first_deriv = np.gradient(spine_x_valid)
            curvature = np.std(first_deriv)

            thoracic_height = abs(shoulder_center_y - nose_y)
            if thoracic_height > 0:
                curvature = curvature / thoracic_height

            return float(curvature)
        except Exception:
            return np.nan

    def _calculate_shoulder_lift_ratio(
        self,
        contour: np.ndarray,
        pose_frame: PoseFrame,
        mask_shape: Tuple[int, int]
    ) -> float:
        """计算肩部上提比例（用于识别耸肩）.

        思路:
        1. 找到颈部和肩部的相对位置
        2. 测量肩带高度相对于正常位置的比例
        """
        h, w = mask_shape

        # 获取关键点
        left_shoulder = pose_frame.get_keypoint("left_shoulder")
        right_shoulder = pose_frame.get_keypoint("right_shoulder")
        nose = pose_frame.get_keypoint("nose")
        left_ear = pose_frame.get_keypoint("left_ear")
        right_ear = pose_frame.get_keypoint("right_ear")

        if not all([left_shoulder, right_shoulder, nose]):
            return np.nan

        # 计算颈部参考点
        ear_y = None
        if left_ear and right_ear:
            ear_y = (left_ear.y + right_ear.y) / 2 * h
        else:
            ear_y = nose.y * h  # 备选

        shoulder_center_y = (left_shoulder.y + right_shoulder.y) / 2 * h

        # 正常肩颈部距离（相对于身高）
        neck_shoulder_dist = abs(ear_y - shoulder_center_y)
        torso_height = abs(pose_frame.get_keypoint("left_hip").y * h - shoulder_center_y) if pose_frame.get_keypoint("left_hip") else h * 0.3

        if torso_height > 0:
            ratio = neck_shoulder_dist / torso_height
            return float(ratio)

        return np.nan

    def _calculate_pelvis_tilt(
        self,
        contour: np.ndarray,
        pose_frame: PoseFrame,
        mask_shape: Tuple[int, int]
    ) -> float:
        """基于轮廓计算骨盆倾斜角度."""
        h, w = mask_shape

        # 获取髋部关键点
        left_hip = pose_frame.get_keypoint("left_hip")
        right_hip = pose_frame.get_keypoint("right_hip")

        if not all([left_hip, right_hip]):
            return np.nan

        # 转换为像素坐标
        left_hip_px = (int(left_hip.x * w), int(left_hip.y * h))
        right_hip_px = (int(right_hip.x * w), int(right_hip.y * h))

        # 计算髋部连线角度
        dx = right_hip_px[0] - left_hip_px[0]
        dy = right_hip_px[1] - left_hip_px[1]

        if dx == 0:
            return 0.0

        angle = np.degrees(np.arctan2(dy, dx))

        # 归一化到-90到90度
        return float(angle)

    def _calculate_contour_symmetry(
        self,
        contour: np.ndarray,
        mask_shape: Tuple[int, int]
    ) -> float:
        """计算身体轮廓对称性."""
        h, w = mask_shape

        # 找到轮廓的垂直中心线
        moments = cv2.moments(contour)
        if moments["m00"] == 0:
            return np.nan

        cx = int(moments["m10"] / moments["m00"])

        # 计算左右不对称度
        left_area = 0
        right_area = 0

        for point in contour:
            px, py = point[0]
            if px < cx:
                left_area += 1
            else:
                right_area += 1

        total = left_area + right_area
        if total == 0:
            return 0.0

        # 对称性得分（1为完全对称，0为完全不对称）
        symmetry = 1.0 - abs(left_area - right_area) / total
        return float(symmetry)

    def _calculate_torso_area_ratio(
        self,
        contour: np.ndarray,
        mask: np.ndarray
    ) -> float:
        """计算躯干占整个身体的面积比例."""
        torso_area = cv2.contourArea(contour)
        total_area = np.sum(mask)

        if total_area > 0:
            return float(torso_area / total_area)
        return 0.0

    def __del__(self):
        """清理资源."""
        if self._segmentation_model and self.model_type == "mediapipe":
            self._segmentation_model.close()


# 导入Any用于类型提示
try:
    from typing import Any
except ImportError:
    Any = object
