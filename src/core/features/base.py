"""特征提取抽象基类."""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from ...core.models.base import PoseFrame, PoseSequence


@dataclass
class FeatureSet:
    """特征集合."""

    name: str
    values: np.ndarray
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.values)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典."""
        return {
            "name": self.name,
            "values": self.values.tolist() if isinstance(self.values, np.ndarray) else self.values,
            "metadata": self.metadata,
        }


class BaseFeatureExtractor(ABC):
    """特征提取器抽象基类."""

    def __init__(self, name: str, config: Optional[Dict[str, Any]] = None):
        """
        Args:
            name: 提取器名称
            config: 配置参数
        """
        self.name = name
        self.config = config or {}

    @abstractmethod
    def extract(self, pose_sequence: PoseSequence, **kwargs) -> List[FeatureSet]:
        """从姿态序列中提取特征.

        Args:
            pose_sequence: 姿态序列
            **kwargs: 额外参数

        Returns:
            特征集合列表
        """
        pass

    @abstractmethod
    def get_supported_features(self) -> List[str]:
        """返回支持的特征名称列表."""
        pass

    def validate_sequence(self, pose_sequence: PoseSequence) -> bool:
        """验证姿态序列是否有效."""
        if not pose_sequence or len(pose_sequence) == 0:
            return False
        if not pose_sequence.frames or len(pose_sequence.frames[0].keypoints) == 0:
            return False
        return True
