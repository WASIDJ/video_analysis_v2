"""动作阶段检测基类."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any

import numpy as np

from src.core.models.base import PoseSequence


class ActionPhase(Enum):
    """动作阶段基类枚举."""
    pass


@dataclass
class PhaseDetectionResult:
    """阶段检测结果."""
    phase: ActionPhase
    start_frame: int
    end_frame: int
    confidence: float
    metadata: Dict[str, Any]


class BasePhaseDetector(ABC):
    """动作阶段检测器基类.

    用于检测动作的不同阶段（如深蹲的：站立-下蹲-最低点-站起）
    """

    def __init__(self, min_phase_duration: float = 0.1):
        """
        Args:
            min_phase_duration: 最小阶段持续时间（秒）
        """
        self.min_phase_duration = min_phase_duration

    @abstractmethod
    def detect_phases(self, pose_sequence: PoseSequence) -> List[PhaseDetectionResult]:
        """检测动作阶段.

        Args:
            pose_sequence: 姿态序列

        Returns:
            阶段检测结果列表
        """
        pass

    @abstractmethod
    def get_key_frame_for_metric(
        self,
        pose_sequence: PoseSequence,
        metric_id: str
    ) -> Optional[int]:
        """获取用于评估检测项的关键帧.

        Args:
            pose_sequence: 姿态序列
            metric_id: 检测项ID

        Returns:
            关键帧索引，None表示无法确定
        """
        pass

    def smooth_sequence(self, values: np.ndarray, window: int = 5) -> np.ndarray:
        """平滑序列数据."""
        if len(values) < window:
            return values

        smoothed = np.copy(values)
        for i in range(window, len(values) - window):
            smoothed[i] = np.mean(values[i-window:i+window+1])
        return smoothed

    def find_local_minima(self, values: np.ndarray, window: int = 5) -> List[int]:
        """寻找局部最小值位置."""
        minima = []
        for i in range(window, len(values) - window):
            if values[i] == np.min(values[i-window:i+window+1]):
                minima.append(i)
        return minima

    def find_local_maxima(self, values: np.ndarray, window: int = 5) -> List[int]:
        """寻找局部最大值位置."""
        maxima = []
        for i in range(window, len(values) - window):
            if values[i] == np.max(values[i-window:i+window+1]):
                maxima.append(i)
        return maxima
