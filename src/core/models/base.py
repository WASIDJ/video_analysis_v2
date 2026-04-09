"""姿态估计模型抽象基类."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union
from datetime import datetime

import numpy as np


@dataclass
class Keypoint:
    """关键点数据类.

    兼容多种姿态估计模型的输出格式:
    - BlazePose: 33个关键点 (x, y, z, visibility)
    - COCO/YOLO: 17个关键点 (x, y, confidence)
    """
    name: str
    x: float
    y: float
    z: float = 0.0
    visibility: float = 1.0
    confidence: float = 1.0

    @property
    def is_visible(self) -> bool:
        """判断关键点是否可见."""
        return self.visibility > 0.5 and self.confidence > 0.3

    def to_array(self, use_3d: bool = False) -> np.ndarray:
        """转换为numpy数组.

        Args:
            use_3d: 是否包含z坐标

        Returns:
            [x, y] 或 [x, y, z]
        """
        if use_3d:
            return np.array([self.x, self.y, self.z])
        return np.array([self.x, self.y])

    def to_tuple(self, use_3d: bool = False) -> Union[Tuple[float, float], Tuple[float, float, float]]:
        """转换为元组."""
        if use_3d:
            return (self.x, self.y, self.z)
        return (self.x, self.y)


@dataclass
class PoseFrame:
    """单帧姿态数据."""
    frame_id: int
    keypoints: List[Keypoint]
    timestamp: float = 0.0

    def get_keypoint(self, name: str) -> Optional[Keypoint]:
        """根据名称获取关键点."""
        for kp in self.keypoints:
            if kp.name == name:
                return kp
        return None

    def get_keypoint_index(self, index: int) -> Optional[Keypoint]:
        """根据索引获取关键点."""
        if 0 <= index < len(self.keypoints):
            return self.keypoints[index]
        return None

    def to_dict(self) -> Dict[str, Dict[str, float]]:
        """转换为字典格式."""
        return {
            kp.name: {
                "x": kp.x,
                "y": kp.y,
                "z": kp.z,
                "visibility": kp.visibility,
                "confidence": kp.confidence,
            }
            for kp in self.keypoints
        }


@dataclass
class PoseSequence:
    """姿态序列数据."""
    frames: List[PoseFrame] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.frames)

    def add_frame(self, frame: PoseFrame) -> None:
        """添加帧."""
        self.frames.append(frame)

    def get_keypoint_trajectory(self, name: str) -> np.ndarray:
        """获取指定关键点的轨迹."""
        trajectory = []
        for frame in self.frames:
            kp = frame.get_keypoint(name)
            if kp:
                trajectory.append([kp.x, kp.y, kp.z])
            else:
                trajectory.append([np.nan, np.nan, np.nan])
        return np.array(trajectory)

    def get_visible_keypoints(self, min_confidence: float = 0.3) -> List[str]:
        """获取置信度足够的关键点列表."""
        if not self.frames:
            return []

        visible = []
        for kp in self.frames[0].keypoints:
            # 检查所有帧中该点的置信度
            confidences = [
                frame.get_keypoint(kp.name).confidence
                for frame in self.frames
                if frame.get_keypoint(kp.name)
            ]
            if confidences and np.mean(confidences) >= min_confidence:
                visible.append(kp.name)
        return visible


class BasePoseEstimator(ABC):
    """姿态估计模型抽象基类.

    所有姿态估计模型必须继承此类并实现抽象方法.
    """

    def __init__(self, **kwargs):
        """初始化.

        Args:
            **kwargs: 模型特定参数
        """
        self._model = None
        self._config = kwargs
        self._is_initialized = False

    @property
    @abstractmethod
    def keypoint_names(self) -> List[str]:
        """返回关键点名称列表.

        Returns:
            关键点名称列表，顺序必须与模型输出一致
        """
        pass

    @property
    @abstractmethod
    def keypoint_connections(self) -> List[Tuple[int, int]]:
        """返回骨骼连接关系.

        Returns:
            连接关系列表，每个元组表示两个关键点的索引
        """
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        """返回模型名称."""
        pass

    @property
    def num_keypoints(self) -> int:
        """返回关键点数量."""
        return len(self.keypoint_names)

    @abstractmethod
    def initialize(self) -> None:
        """初始化模型.

        加载模型权重，准备推理环境.
        """
        pass

    @abstractmethod
    def process_frame(self, frame: np.ndarray) -> Optional[PoseFrame]:
        """处理单帧图像.

        Args:
            frame: BGR格式的numpy数组，shape为(H, W, 3)

        Returns:
            PoseFrame对象，如果未检测到人体返回None
        """
        pass

    @abstractmethod
    def process_video(self, video_path: str, **kwargs) -> PoseSequence:
        """处理整个视频.

        Args:
            video_path: 视频文件路径
            **kwargs: 额外参数（如progress_callback等）

        Returns:
            PoseSequence对象
        """
        pass

    def visualize_frame(
        self,
        frame: np.ndarray,
        pose_frame: PoseFrame,
        draw_connections: bool = True,
        draw_keypoints: bool = True,
        connection_color: Tuple[int, int, int] = (0, 255, 0),
        keypoint_color: Tuple[int, int, int] = (0, 0, 255),
        thickness: int = 2,
    ) -> np.ndarray:
        """可视化单帧姿态.

        Args:
            frame: 原始帧
            pose_frame: 姿态数据
            draw_connections: 是否绘制骨骼连接
            draw_keypoints: 是否绘制关键点
            connection_color: 连接线颜色
            keypoint_color: 关键点颜色
            thickness: 线宽

        Returns:
            标注后的帧
        """
        import cv2

        result = frame.copy()
        h, w = frame.shape[:2]

        if draw_connections:
            for start_idx, end_idx in self.keypoint_connections:
                start_kp = pose_frame.get_keypoint_index(start_idx)
                end_kp = pose_frame.get_keypoint_index(end_idx)

                if start_kp and end_kp and start_kp.is_visible and end_kp.is_visible:
                    start_pos = (int(start_kp.x * w), int(start_kp.y * h))
                    end_pos = (int(end_kp.x * w), int(end_kp.y * h))
                    cv2.line(result, start_pos, end_pos, connection_color, thickness)

        if draw_keypoints:
            for kp in pose_frame.keypoints:
                if kp.is_visible:
                    pos = (int(kp.x * w), int(kp.y * h))
                    cv2.circle(result, pos, thickness + 2, keypoint_color, -1)

        return result


def create_pose_estimator(model_type: str, **kwargs) -> BasePoseEstimator:
    """工厂函数：创建姿态估计器.

    Args:
        model_type: 模型类型，'blazepose' 或 'yolo'
        **kwargs: 模型参数

    Returns:
        BasePoseEstimator实例
    """
    if model_type.lower() == "blazepose":
        from .blazepose import BlazePoseEstimator
        return BlazePoseEstimator(**kwargs)
    elif model_type.lower() in ("yolo", "yolov8"):
        from .yolo_adapter import YOLOPoseAdapter
        return YOLOPoseAdapter(**kwargs)
    else:
        raise ValueError(f"不支持的模型类型: {model_type}")
