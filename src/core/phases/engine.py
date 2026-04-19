"""阶段引擎 V2 - 配置驱动的阶段检测.

基于 FSM (Finite State Machine) 实现，完全由配置驱动。
"""
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
from dataclasses import dataclass, field
import logging

from src.core.models.base import PoseSequence

logger = logging.getLogger(__name__)


class ConditionType(str, Enum):
    """条件类型."""
    THRESHOLD = "threshold"
    DERIVATIVE = "derivative"
    EXTREMUM = "extremum"
    DURATION = "duration"
    COMPOUND = "compound"
    STABILITY = "stability"


class Operator(str, Enum):
    """比较操作符."""
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    EQ = "eq"
    NEQ = "neq"


@dataclass
class Condition:
    """条件定义."""
    type: ConditionType
    metric: Optional[str] = None
    operator: Optional[Operator] = None
    value: Optional[float] = None
    order: Optional[int] = None  # 导数阶数
    duration_min: Optional[float] = None
    duration_max: Optional[float] = None
    persist_frames: int = 1
    logic: Optional[str] = None  # AND/OR for compound
    sub_conditions: List["Condition"] = field(default_factory=list)


@dataclass
class PhaseConfig:
    """阶段配置."""
    phase_id: str
    phase_name: str
    description: Optional[str] = None
    entry_conditions: List[Condition] = field(default_factory=list)
    exit_conditions: List[Condition] = field(default_factory=list)
    stability_checks: List[Condition] = field(default_factory=list)
    max_duration: Optional[float] = None
    min_duration: Optional[float] = None


@dataclass
class PhaseDetection:
    """阶段检测结果."""
    phase_id: str
    start_frame: int
    end_frame: int
    duration: float
    confidence: float = 1.0


@dataclass
class PhaseSequence:
    """阶段序列."""
    detections: List[PhaseDetection]

    def get_phase_at(self, frame_idx: int) -> Optional[str]:
        """获取指定帧所在的阶段."""
        for det in self.detections:
            if det.start_frame <= frame_idx <= det.end_frame:
                return det.phase_id
        return None

    def get_phase_range(self, phase_id: str) -> Optional[Tuple[int, int]]:
        """获取指定阶段的帧范围."""
        for det in self.detections:
            if det.phase_id == phase_id:
                return (det.start_frame, det.end_frame)
        return None


class PhaseEngine:
    """V2 阶段引擎（配置驱动）."""

    def __init__(
        self,
        phase_configs: List[PhaseConfig],
        metric_values: Dict[str, np.ndarray],
        fps: float = 30.0
    ):
        self.phase_configs = {p.phase_id: p for p in phase_configs}
        self.metric_values = metric_values
        self.fps = fps

        # 状态跟踪
        self.current_state: Optional[str] = None
        self.state_start_frame: int = 0
        self.state_frame_count: int = 0
        self.persist_counter: Dict[str, int] = {}

    def detect_phases(self) -> PhaseSequence:
        """检测阶段序列."""
        phase_detections = []
        frame_count = self._get_frame_count()

        for frame_idx in range(frame_count):
            new_state = self._transition(frame_idx)

            if new_state != self.current_state:
                # 状态变化，记录上一阶段
                if self.current_state:
                    phase_detections.append(
                        PhaseDetection(
                            phase_id=self.current_state,
                            start_frame=self.state_start_frame,
                            end_frame=frame_idx - 1,
                            duration=(frame_idx - self.state_start_frame) / self.fps,
                        )
                    )

                # 进入新状态
                self.current_state = new_state
                self.state_start_frame = frame_idx
                self.state_frame_count = 0
                self.persist_counter = {}
            else:
                self.state_frame_count += 1

        # 处理最后一个阶段
        if self.current_state:
            frame_idx = frame_count - 1
            phase_detections.append(
                PhaseDetection(
                    phase_id=self.current_state,
                    start_frame=self.state_start_frame,
                    end_frame=frame_idx,
                    duration=(frame_idx - self.state_start_frame + 1) / self.fps,
                )
            )

        return PhaseSequence(detections=phase_detections)

    def get_key_frame(self, phase_id: str, metric_id: Optional[str] = None) -> Optional[int]:
        """获取指定阶段的关键帧.

        关键帧选择策略:
        1. 如果指定了 metric_id，选择该 metric 在阶段内的极值点
        2. 否则选择阶段中间帧
        """
        phase_range = None
        for det in self.phase_detections:
            if det.phase_id == phase_id:
                phase_range = (det.start_frame, det.end_frame)
                break

        if not phase_range:
            return None

        start, end = phase_range

        if metric_id and metric_id in self.metric_values:
            # 选择 metric 极值点
            values = self.metric_values[metric_id][start:end+1]
            if len(values) > 0:
                # 根据 metric 类型选择 max 或 min
                # 这里简化处理，选择最大值
                relative_idx = np.argmax(values)
                return start + relative_idx

        # 默认返回中间帧
        return (start + end) // 2

    def _get_frame_count(self) -> int:
        """获取帧数."""
        if not self.metric_values:
            return 0
        return len(next(iter(self.metric_values.values())))

    def _transition(self, frame_idx: int) -> Optional[str]:
        """状态转换逻辑."""
        if self.current_state is None:
            # 初始状态：检查所有阶段的进入条件
            for phase_id, config in self.phase_configs.items():
                if self._check_entry_conditions(config, frame_idx):
                    return phase_id
            return None

        # 检查当前阶段的退出条件
        current_config = self.phase_configs[self.current_state]

        # 1. 检查最大持续时间
        if current_config.max_duration:
            duration = self.state_frame_count / self.fps
            if duration >= current_config.max_duration:
                return self._find_next_phase()

        # 2. 检查退出条件
        if self._check_exit_conditions(current_config, frame_idx):
            return self._find_next_phase()

        return self.current_state

    def _check_entry_conditions(self, config: PhaseConfig, frame_idx: int) -> bool:
        """检查进入条件（OR关系）."""
        if not config.entry_conditions:
            return True
        return any(
            self._evaluate_condition(c, frame_idx) for c in config.entry_conditions
        )

    def _check_exit_conditions(self, config: PhaseConfig, frame_idx: int) -> bool:
        """检查退出条件（OR关系）."""
        if not config.exit_conditions:
            return False
        return any(
            self._evaluate_condition(c, frame_idx) for c in config.exit_conditions
        )

    def _evaluate_condition(self, condition: Condition, frame_idx: int) -> bool:
        """评估单个条件."""
        if condition.type == ConditionType.THRESHOLD:
            result = self._eval_threshold(condition, frame_idx)
        elif condition.type == ConditionType.DERIVATIVE:
            result = self._eval_derivative(condition, frame_idx)
        elif condition.type == ConditionType.EXTREMUM:
            result = self._eval_extremum(condition, frame_idx)
        elif condition.type == ConditionType.DURATION:
            result = self._eval_duration(condition)
        elif condition.type == ConditionType.COMPOUND:
            result = self._eval_compound(condition, frame_idx)
        else:
            result = False

        # 处理持续帧数要求（防抖）
        if result:
            key = f"{condition.type}_{condition.metric}"
            self.persist_counter[key] = self.persist_counter.get(key, 0) + 1
            return self.persist_counter[key] >= condition.persist_frames
        else:
            self.persist_counter = {}  # 重置计数器
            return False

    def _eval_threshold(self, condition: Condition, frame_idx: int) -> bool:
        """评估阈值条件."""
        if not condition.metric or condition.metric not in self.metric_values:
            return False

        value = self.metric_values[condition.metric][frame_idx]
        if np.isnan(value):
            return False

        threshold = condition.value if condition.value is not None else 0
        op = condition.operator if condition.operator else Operator.GT

        operators = {
            Operator.GT: lambda v, t: v > t,
            Operator.GTE: lambda v, t: v >= t,
            Operator.LT: lambda v, t: v < t,
            Operator.LTE: lambda v, t: v <= t,
            Operator.EQ: lambda v, t: abs(v - t) < 1e-6,
            Operator.NEQ: lambda v, t: abs(v - t) >= 1e-6,
        }

        return operators.get(op, operators[Operator.GT])(value, threshold)

    def _eval_derivative(self, condition: Condition, frame_idx: int) -> bool:
        """评估导数条件."""
        if not condition.metric or condition.metric not in self.metric_values:
            return False

        values = self.metric_values[condition.metric]
        if frame_idx < 1:
            return False

        # 计算一阶导数（简化：用后向差分）
        derivative = values[frame_idx] - values[frame_idx - 1]

        # 归一化到每秒（考虑fps）
        derivative *= self.fps

        threshold = condition.value if condition.value is not None else 0
        op = condition.operator if condition.operator else Operator.GT

        operators = {
            Operator.GT: lambda v, t: v > t,
            Operator.GTE: lambda v, t: v >= t,
            Operator.LT: lambda v, t: v < t,
            Operator.LTE: lambda v, t: v <= t,
        }

        return operators.get(op, operators[Operator.GT])(derivative, threshold)

    def _eval_extremum(self, condition: Condition, frame_idx: int) -> bool:
        """评估极值条件."""
        if not condition.metric or condition.metric not in self.metric_values:
            return False

        values = self.metric_values[condition.metric]
        window = 5  # 默认窗口

        start = max(0, frame_idx - window)
        end = min(len(values), frame_idx + window + 1)
        window_values = values[start:end]

        if len(window_values) == 0:
            return False

        current_value = values[frame_idx]

        if condition.value == "max":
            return current_value == np.nanmax(window_values)
        elif condition.value == "min":
            return current_value == np.nanmin(window_values)

        return False

    def _eval_duration(self, condition: Condition) -> bool:
        """评估持续时间条件."""
        duration = self.state_frame_count / self.fps

        if condition.duration_min and duration < condition.duration_min:
            return False
        if condition.duration_max and duration > condition.duration_max:
            return True  # 超过最大持续时间，触发退出

        return True

    def _eval_compound(self, condition: Condition, frame_idx: int) -> bool:
        """评估复合条件."""
        if not condition.sub_conditions:
            return True

        results = [
            self._evaluate_condition(c, frame_idx) for c in condition.sub_conditions
        ]

        if condition.logic == "AND":
            return all(results)
        elif condition.logic == "OR":
            return any(results)

        return any(results)  # 默认 OR

    def _find_next_phase(self) -> Optional[str]:
        """查找下一个阶段（简化：按 phase_sequence 顺序）."""
        if not self.current_state:
            return None

        phase_ids = list(self.phase_configs.keys())
        if self.current_state in phase_ids:
            idx = phase_ids.index(self.current_state)
            if idx + 1 < len(phase_ids):
                return phase_ids[idx + 1]

        return None
