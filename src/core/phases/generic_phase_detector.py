"""通用相位检测引擎 (Generic Phase Engine).

数据驱动的有限状态机(FSM)执行器，通过JSON配置定义状态转移规则。
支持任何动作的阶段检测，无需编写特定动作的Python代码。
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any, Callable
import numpy as np
from collections import defaultdict

from src.core.models.base import PoseSequence, PoseFrame
from src.core.metrics.definitions import MetricDefinition, METRIC_TEMPLATES
from src.core.metrics.calculator import MetricsCalculator
from src.core.config.models import ActionConfig, PhaseDefinition as ConfigPhaseDefinition


class TransitionType(Enum):
    """状态转移条件类型."""
    THRESHOLD = "threshold"           # 阈值比较 (value >/< threshold)
    DERIVATIVE = "derivative"         # 导数判断 (上升/下降/平稳)
    EXTREMUM = "extremum"             # 极值点 (局部最小/最大)
    DURATION = "duration"             # 持续时间
    COMPOUND = "compound"             # 复合条件 (多个条件组合)


class DerivativeDirection(Enum):
    """导数方向."""
    INCREASING = "increasing"         # 增加 (导数 > 0)
    DECREASING = "decreasing"         # 减少 (导数 < 0)
    STABLE = "stable"                 # 平稳 (|导数| < epsilon)
    PEAK = "peak"                     # 峰值 (导数由正变负)
    VALLEY = "valley"                 # 谷值 (导数由负变正)


@dataclass
class StateTransitionRule:
    """状态转移规则.

    定义从当前状态转移到目标状态的条件。
    """
    from_state: str                   # 起始状态
    to_state: str                     # 目标状态
    driver_signal: str                # 驱动信号 (metric_id 如 "knee_flexion", "hip_center_y")
    transition_type: TransitionType   # 转移类型

    # 条件参数
    params: Dict[str, Any] = field(default_factory=dict)

    # 元数据
    description: str = ""
    priority: int = 0                 # 优先级，高优先级规则先检查


@dataclass
class PhaseState:
    """相位状态定义."""
    state_id: str                     # 状态ID
    state_name: str                   # 状态名称
    description: str = ""
    is_start: bool = False            # 是否是起始状态
    is_terminal: bool = False         # 是否是终止状态


@dataclass
class PhaseStateMachine:
    """相位状态机配置."""
    action_id: str
    states: Dict[str, PhaseState]     # 所有状态
    transitions: List[StateTransitionRule]  # 转移规则
    global_params: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PhaseInstance:
    """检测到的相位实例."""
    phase_id: str
    phase_name: str
    start_frame: int
    end_frame: int
    confidence: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class SignalExtractor:
    """信号提取器.

    从姿态序列中提取用于驱动状态机的信号。
    """

    def __init__(self, pose_sequence: PoseSequence):
        self.pose_sequence = pose_sequence
        self._signal_cache: Dict[str, np.ndarray] = {}
        self._derivative_cache: Dict[str, np.ndarray] = {}

    def extract_signal(self, signal_name: str) -> np.ndarray:
        """提取指定信号的时间序列.

        Args:
            signal_name: 信号名称
                - 可以是 MetricDefinition 的 ID (如 "knee_flexion")
                - 可以是关键点坐标 (如 "hip_center_y", "left_knee_x")

        Returns:
            信号时间序列数组
        """
        if signal_name in self._signal_cache:
            return self._signal_cache[signal_name]

        # 尝试作为 MetricDefinition 计算
        if signal_name in METRIC_TEMPLATES:
            signal = self._extract_metric_signal(signal_name)
        else:
            # 尝试作为关键点坐标
            signal = self._extract_keypoint_signal(signal_name)

        self._signal_cache[signal_name] = signal
        return signal

    def _extract_metric_signal(self, metric_id: str) -> np.ndarray:
        """计算检测项的时间序列."""
        metric_def = METRIC_TEMPLATES.get(metric_id)
        if not metric_def:
            return np.full(len(self.pose_sequence), np.nan)

        # 使用 MetricsCalculator 计算
        calculator = MetricsCalculator(
            action_id="generic",
            use_phase_detection=False,
            use_viewpoint_analysis=False,
        )

        result = calculator.calculate_metric(
            metric_def=metric_def,
            pose_sequence=self.pose_sequence,
            action_name="generic"
        )

        values = result.get("values", [])
        return np.array(values) if values else np.full(len(self.pose_sequence), np.nan)

    def _extract_keypoint_signal(self, signal_name: str) -> np.ndarray:
        """提取关键点坐标信号.

        格式: "{keypoint_name}_{axis}" 或 "{keypoint_name}"
        例如: "hip_center_y", "left_knee_x", "nose"
        """
        # 解析信号名
        parts = signal_name.rsplit('_', 1)
        if len(parts) == 2 and parts[1] in ['x', 'y', 'z']:
            kp_name, axis = parts
            axis_idx = {'x': 0, 'y': 1, 'z': 2}[axis]
        else:
            kp_name = signal_name
            axis_idx = 1  # 默认y轴

        # 提取坐标
        values = []
        for frame in self.pose_sequence.frames:
            kp = frame.get_keypoint(kp_name)
            if kp:
                coord = [kp.x, kp.y, kp.z][axis_idx]
                values.append(coord)
            else:
                # 尝试计算中心点
                if 'center' in kp_name:
                    coord = self._calculate_center(frame, kp_name, axis_idx)
                    values.append(coord if coord is not None else np.nan)
                else:
                    values.append(np.nan)

        return np.array(values)

    def _calculate_center(self, frame: PoseFrame, center_name: str, axis_idx: int) -> Optional[float]:
        """计算中心点坐标."""
        if center_name == "hip_center":
            left = frame.get_keypoint("left_hip")
            right = frame.get_keypoint("right_hip")
        elif center_name == "shoulder_center":
            left = frame.get_keypoint("left_shoulder")
            right = frame.get_keypoint("right_shoulder")
        else:
            return None

        if left and right:
            coords = [left.x, left.y, left.z]
            right_coords = [right.x, right.y, right.z]
            return (coords[axis_idx] + right_coords[axis_idx]) / 2
        return None

    def calculate_derivative(self, signal_name: str, window: int = 3) -> np.ndarray:
        """计算信号的导数（变化率）."""
        cache_key = f"{signal_name}_der_{window}"
        if cache_key in self._derivative_cache:
            return self._derivative_cache[cache_key]

        signal = self.extract_signal(signal_name)
        derivative = np.gradient(signal, edge_order=1)

        # 平滑导数
        if len(derivative) >= window:
            smoothed = np.convolve(derivative, np.ones(window)/window, mode='same')
        else:
            smoothed = derivative

        self._derivative_cache[cache_key] = smoothed
        return smoothed

    def detect_extrema(self, signal_name: str, mode: str = "min", window: int = 5) -> List[int]:
        """检测极值点.

        Args:
            mode: "min" 或 "max"
            window: 检测窗口大小
        """
        signal = self.extract_signal(signal_name)
        extrema = []

        for i in range(window, len(signal) - window):
            local_window = signal[i-window:i+window+1]
            if mode == "min" and signal[i] == np.nanmin(local_window):
                extrema.append(i)
            elif mode == "max" and signal[i] == np.nanmax(local_window):
                extrema.append(i)

        return extrema


class GenericPhaseDetector:
    """通用相位检测器.

    基于有限状态机(FSM)的通用阶段检测引擎，完全由JSON配置驱动。
    """

    def __init__(
        self,
        state_machine: Optional[PhaseStateMachine] = None,
        config: Optional[ActionConfig] = None,
        min_phase_duration: float = 0.2,
    ):
        """
        Args:
            state_machine: 预构建的状态机配置
            config: 动作配置（从中构建状态机）
            min_phase_duration: 最小阶段持续时间（秒）
        """
        self.min_phase_duration = min_phase_duration

        if state_machine:
            self.state_machine = state_machine
        elif config:
            self.state_machine = self._build_state_machine_from_config(config)
        else:
            raise ValueError("必须提供 state_machine 或 config")

    def _build_state_machine_from_config(self, config: ActionConfig) -> PhaseStateMachine:
        """从动作配置构建状态机."""
        states = {}
        transitions = []

        # 构建状态
        for phase_config in config.phases:
            state = PhaseState(
                state_id=phase_config.phase_id,
                state_name=phase_config.phase_name,
                description=phase_config.description,
                is_start=(phase_config.phase_id == config.phases[0].phase_id),
                is_terminal=(phase_config.phase_id == config.phases[-1].phase_id),
            )
            states[phase_config.phase_id] = state

            # 从 detection_params 构建转移规则
            params = phase_config.detection_params
            if "velocity_threshold" in params:
                # 基于速度的转移
                transitions.append(StateTransitionRule(
                    from_state=phase_config.phase_id,
                    to_state=self._get_next_phase(config, phase_config.phase_id),
                    driver_signal=params.get("driver_signal", "knee_flexion"),
                    transition_type=TransitionType.DERIVATIVE,
                    params={
                        "direction": "decreasing" if params["velocity_threshold"] < 0 else "increasing",
                        "threshold": abs(params["velocity_threshold"]),
                    },
                    description=f"基于速度阈值的状态转移",
                ))

        return PhaseStateMachine(
            action_id=config.action_id,
            states=states,
            transitions=transitions,
            global_params=config.global_params,
        )

    def _get_next_phase(self, config: ActionConfig, current_phase_id: str) -> str:
        """获取下一个阶段ID."""
        phase_ids = [p.phase_id for p in config.phases]
        try:
            idx = phase_ids.index(current_phase_id)
            if idx < len(phase_ids) - 1:
                return phase_ids[idx + 1]
        except ValueError:
            pass
        return current_phase_id

    def detect_phases(self, pose_sequence: PoseSequence) -> List[PhaseInstance]:
        """检测动作阶段.

        使用FSM根据配置的转移规则分析姿态序列。
        """
        if len(pose_sequence) == 0:
            return []

        # 初始化信号提取器
        signal_extractor = SignalExtractor(pose_sequence)

        # 获取起始状态
        current_state = self._get_start_state()
        state_start_frame = 0

        phases = []
        frame_rate = pose_sequence.fps if hasattr(pose_sequence, 'fps') else 30
        min_frames = int(self.min_phase_duration * frame_rate)

        # 逐帧遍历，执行状态机
        for frame_idx in range(len(pose_sequence)):
            # 检查是否需要状态转移
            transition = self._check_transitions(
                current_state, frame_idx, signal_extractor
            )

            if transition:
                # 记录当前阶段
                if frame_idx - state_start_frame >= min_frames:
                    phase = self._create_phase_instance(
                        current_state, state_start_frame, frame_idx, signal_extractor
                    )
                    phases.append(phase)

                # 转移状态
                current_state = transition.to_state
                state_start_frame = frame_idx

        # 记录最后一个阶段
        if len(pose_sequence) - state_start_frame >= min_frames:
            phase = self._create_phase_instance(
                current_state, state_start_frame, len(pose_sequence), signal_extractor
            )
            phases.append(phase)

        return phases

    def _get_start_state(self) -> str:
        """获取起始状态ID."""
        for state_id, state in self.state_machine.states.items():
            if state.is_start:
                return state_id
        # 默认返回第一个状态
        return list(self.state_machine.states.keys())[0]

    def _check_transitions(
        self,
        current_state: str,
        frame_idx: int,
        signal_extractor: SignalExtractor,
    ) -> Optional[StateTransitionRule]:
        """检查是否需要状态转移."""
        # 获取当前状态的所有转移规则，按优先级排序
        applicable_rules = [
            t for t in self.state_machine.transitions
            if t.from_state == current_state
        ]
        applicable_rules.sort(key=lambda x: x.priority, reverse=True)

        for rule in applicable_rules:
            if self._evaluate_transition(rule, frame_idx, signal_extractor):
                return rule

        return None

    def _evaluate_transition(
        self,
        rule: StateTransitionRule,
        frame_idx: int,
        signal_extractor: SignalExtractor,
    ) -> bool:
        """评估单个转移规则."""
        if rule.transition_type == TransitionType.THRESHOLD:
            return self._evaluate_threshold(rule, frame_idx, signal_extractor)
        elif rule.transition_type == TransitionType.DERIVATIVE:
            return self._evaluate_derivative(rule, frame_idx, signal_extractor)
        elif rule.transition_type == TransitionType.EXTREMUM:
            return self._evaluate_extremum(rule, frame_idx, signal_extractor)
        elif rule.transition_type == TransitionType.DURATION:
            return self._evaluate_duration(rule, frame_idx)
        return False

    def _evaluate_threshold(
        self,
        rule: StateTransitionRule,
        frame_idx: int,
        signal_extractor: SignalExtractor,
    ) -> bool:
        """评估阈值条件."""
        signal = signal_extractor.extract_signal(rule.driver_signal)
        if frame_idx >= len(signal) or np.isnan(signal[frame_idx]):
            return False

        value = signal[frame_idx]
        threshold = rule.params.get("threshold", 0)
        operator = rule.params.get("operator", "gt")

        operators = {
            "gt": lambda v, t: v > t,
            "gte": lambda v, t: v >= t,
            "lt": lambda v, t: v < t,
            "lte": lambda v, t: v <= t,
            "eq": lambda v, t: abs(v - t) < 1e-6,
        }

        op_func = operators.get(operator, operators["gt"])
        return op_func(value, threshold)

    def _evaluate_derivative(
        self,
        rule: StateTransitionRule,
        frame_idx: int,
        signal_extractor: SignalExtractor,
    ) -> bool:
        """评估导数条件."""
        derivative = signal_extractor.calculate_derivative(rule.driver_signal)
        if frame_idx >= len(derivative):
            return False

        der_value = derivative[frame_idx]
        direction = rule.params.get("direction", "decreasing")
        epsilon = rule.params.get("epsilon", 0.5)

        if direction == DerivativeDirection.INCREASING.value:
            return der_value > epsilon
        elif direction == DerivativeDirection.DECREASING.value:
            return der_value < -epsilon
        elif direction == DerivativeDirection.STABLE.value:
            return abs(der_value) < epsilon

        return False

    def _evaluate_extremum(
        self,
        rule: StateTransitionRule,
        frame_idx: int,
        signal_extractor: SignalExtractor,
    ) -> bool:
        """评估极值条件."""
        mode = rule.params.get("mode", "min")
        window = rule.params.get("window", 5)

        extrema = signal_extractor.detect_extrema(
            rule.driver_signal, mode=mode, window=window
        )

        # 检查当前帧是否是极值点
        return frame_idx in extrema

    def _evaluate_duration(self, rule: StateTransitionRule, frame_idx: int) -> bool:
        """评估持续时间条件."""
        # 需要跟踪状态进入时间
        # 简化处理：由外部控制器管理
        return False

    def _create_phase_instance(
        self,
        state_id: str,
        start_frame: int,
        end_frame: int,
        signal_extractor: SignalExtractor,
    ) -> PhaseInstance:
        """创建阶段实例."""
        state = self.state_machine.states.get(state_id)

        # 计算置信度（基于信号质量）
        confidence = 0.8  # 默认置信度

        # 收集元数据
        metadata = {
            "duration_frames": end_frame - start_frame,
        }

        return PhaseInstance(
            phase_id=state_id,
            phase_name=state.state_name if state else state_id,
            start_frame=start_frame,
            end_frame=end_frame,
            confidence=confidence,
            metadata=metadata,
        )

    def get_key_frame_for_metric(
        self,
        pose_sequence: PoseSequence,
        metric_id: str,
        evaluation_phase: str = "bottom",
    ) -> Optional[int]:
        """获取用于评估检测项的关键帧.

        Args:
            pose_sequence: 姿态序列
            metric_id: 检测项ID
            evaluation_phase: 评估阶段（默认"bottom"最低点）

        Returns:
            关键帧索引
        """
        phases = self.detect_phases(pose_sequence)

        # 查找指定阶段
        for phase in phases:
            if phase.phase_id == evaluation_phase:
                # 返回阶段中间帧
                return (phase.start_frame + phase.end_frame) // 2

        # 默认返回序列中间
        return len(pose_sequence) // 2

    def get_key_frame_for_phase(
        self,
        pose_sequence: PoseSequence,
        phase_id: str,
    ) -> Optional[int]:
        """获取指定阶段的关键帧."""
        phases = self.detect_phases(pose_sequence)

        for phase in phases:
            if phase.phase_id == phase_id:
                return (phase.start_frame + phase.end_frame) // 2

        return None


def create_phase_detector(action_config: ActionConfig) -> Optional[GenericPhaseDetector]:
    """创建相位检测器工厂函数.

    替代原有的 create_phase_detector 工厂函数。
    """
    if not action_config or not action_config.phases:
        return None

    return GenericPhaseDetector(config=action_config)
