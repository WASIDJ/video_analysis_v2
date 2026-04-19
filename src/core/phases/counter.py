"""动作计数器 - 基于阶段序列的动作重复计数.

基于阶段序列识别完整周期并计数。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
import logging

from .engine import PhaseSequence, PhaseDetection

logger = logging.getLogger(__name__)


@dataclass
class CycleDefinition:
    """动作周期定义."""
    phase_sequence: List[str]  # 完整周期所需的阶段序列（有序）
    start_phase: Optional[str] = None  # 起始阶段
    end_phase: Optional[str] = None  # 结束阶段
    required_phases: List[str] = field(default_factory=list)  # 关键阶段
    cycle_mode: str = "closed"  # closed: 闭环, open: 开环
    min_cycle_duration: float = 1.0  # 秒，过滤抖动
    max_cycle_duration: float = 30.0  # 秒，过滤异常

    def __post_init__(self):
        # 默认值处理
        if self.start_phase is None and self.phase_sequence:
            self.start_phase = self.phase_sequence[0]
        if self.end_phase is None and self.phase_sequence:
            self.end_phase = self.phase_sequence[0]


@dataclass
class RepDetail:
    """单次重复详细信息."""
    rep_index: int
    start_frame: int
    end_frame: int
    duration: float
    phases_completed: List[str]  # 实际完成的阶段
    phase_durations: Dict[str, float]  # 各阶段时长
    quality_score: float  # 质量评分（基于阶段完整性）


@dataclass
class RepCountResult:
    """动作计数结果."""
    count: int = 0  # 完成次数
    rep_ranges: List[Tuple[int, int]] = field(default_factory=list)  # 每个rep的帧范围
    partial_rep: Optional[Tuple[int, int]] = None  # 当前未完成的部分rep
    confidence: float = 0.0  # 计数置信度
    rep_details: List[RepDetail] = field(default_factory=list)  # 每个rep的详细信息


class RepCounter:
    """基于阶段序列的动作计数器."""

    def __init__(self, cycle_definition: Optional[CycleDefinition] = None):
        self.cycle_def = cycle_definition

    def count(self, phase_sequence: PhaseSequence) -> RepCountResult:
        """
        基于阶段序列识别完整周期.

        算法：
        1. 查找 start_phase 出现位置
        2. 从start开始跟踪阶段序列
        3. 检查 required_phases 是否都出现
        4. 到达 end_phase 时计数+1
        5. 应用时长过滤
        """
        if not self.cycle_def:
            logger.debug("未配置周期定义，跳过计数")
            return RepCountResult()

        reps: List[Tuple[int, int]] = []
        rep_details: List[RepDetail] = []
        current_rep_start: Optional[int] = None
        phases_in_current: Set[str] = set()
        phase_durations: Dict[str, float] = {}
        current_phase_start: int = 0

        for i, detection in enumerate(phase_sequence.detections):
            phase_id = detection.phase_id

            # 检测阶段变化
            if phase_id == self.cycle_def.start_phase:
                # 新的rep开始
                if current_rep_start is not None:
                    # 上一rep未正常结束，视为不完整，跳过
                    logger.debug(f"Rep 在 {detection.start_frame} 被中断")

                current_rep_start = detection.start_frame
                phases_in_current = {phase_id}
                phase_durations = {phase_id: detection.duration}
                current_phase_start = detection.start_frame

            elif current_rep_start is not None:
                # 记录阶段时长
                if phase_id not in phase_durations:
                    phase_durations[phase_id] = 0.0
                phase_durations[phase_id] += detection.duration

                phases_in_current.add(phase_id)

                # 检查是否到达结束阶段
                if phase_id == self.cycle_def.end_phase:
                    # 检查必需阶段
                    if self._check_required_phases(phases_in_current):
                        duration = detection.end_frame - current_rep_start
                        duration_sec = duration / 30.0  # 假设30fps

                        # 时长过滤
                        if self.cycle_def.min_cycle_duration <= duration_sec <= self.cycle_def.max_cycle_duration:
                            reps.append((current_rep_start, detection.end_frame))

                            # 计算质量评分
                            quality = self._calculate_quality(
                                phases_in_current, phase_durations
                            )

                            rep_details.append(RepDetail(
                                rep_index=len(reps) - 1,
                                start_frame=current_rep_start,
                                end_frame=detection.end_frame,
                                duration=duration_sec,
                                phases_completed=list(phases_in_current),
                                phase_durations=phase_durations.copy(),
                                quality_score=quality,
                            ))
                        else:
                            logger.debug(f"Rep 时长 {duration_sec:.2f}s 超出范围")

                    current_rep_start = None
                    phases_in_current = set()
                    phase_durations = {}

        # 处理未完成的rep
        partial = None
        if current_rep_start is not None and phase_sequence.detections:
            last_detection = phase_sequence.detections[-1]
            partial = (current_rep_start, last_detection.end_frame)

        # 计算置信度
        confidence = self._calculate_confidence(reps, rep_details)

        return RepCountResult(
            count=len(reps),
            rep_ranges=reps,
            partial_rep=partial,
            confidence=confidence,
            rep_details=rep_details,
        )

    def _check_required_phases(self, phases: Set[str]) -> bool:
        """检查必需阶段是否都出现."""
        if not self.cycle_def or not self.cycle_def.required_phases:
            return True
        return all(
            req in phases
            for req in self.cycle_def.required_phases
        )

    def _calculate_quality(
        self,
        phases_completed: Set[str],
        phase_durations: Dict[str, float]
    ) -> float:
        """计算单次重复的质量评分."""
        if not self.cycle_def:
            return 0.0

        # 基础分：阶段完整性
        expected_phases = set(self.cycle_def.phase_sequence)
        if expected_phases:
            completeness = len(phases_completed & expected_phases) / len(expected_phases)
        else:
            completeness = 1.0

        # 时长合理性（简化处理）
        duration_score = 1.0
        for phase_id, duration in phase_durations.items():
            if duration < 0.1:  # 阶段过短
                duration_score *= 0.8
            elif duration > 5.0:  # 阶段过长
                duration_score *= 0.9

        # 综合评分
        return min(1.0, completeness * duration_score)

    def _calculate_confidence(
        self,
        reps: List[Tuple[int, int]],
        rep_details: List[RepDetail]
    ) -> float:
        """计算计数置信度."""
        if not reps:
            return 0.0

        # 基于质量评分的加权平均
        if rep_details:
            avg_quality = sum(r.quality_score for r in rep_details) / len(rep_details)
        else:
            avg_quality = 0.5

        # 基于rep数量的置信度（越多越可信）
        count_confidence = min(1.0, len(reps) / 5.0)  # 5个以上达到最大置信度

        return (avg_quality * 0.7 + count_confidence * 0.3)
