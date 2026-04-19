"""配置转换器 - V1/V2 配置兼容层.

提供 V1 配置到 V2 的自动转换，确保向后兼容。
"""
from typing import Any, Dict, List, Optional, Tuple
import logging

from .models import (
    ActionConfig,
    PhaseDefinition,
    MetricConfig,
    MetricThreshold,
    ErrorCondition,
    CycleDefinition,
    CycleDefinitionSource,
    CycleDefinitionWithMeta,
)

logger = logging.getLogger(__name__)


class ConfigTransformer:
    """配置转换器 - V1 到 V2 转换."""

    @classmethod
    def v1_to_v2(cls, v1_config: Dict[str, Any]) -> ActionConfig:
        """将 V1 配置转换为 V2 ActionConfig.

        Args:
            v1_config: V1 格式的配置字典

        Returns:
            V2 ActionConfig 对象
        """
        # 基础信息
        action_id = v1_config.get("action_id", "")
        phases = cls._convert_phases(v1_config.get("phases", []))
        metrics = cls._convert_metrics(v1_config.get("metrics", []))

        # 尝试生成或转换 cycle_definition
        cycle_meta = cls._convert_cycle_definition(
            action_id, phases, v1_config.get("cycle_definition")
        )

        return ActionConfig(
            schema_version="2.0.0",
            action_id=action_id,
            action_name=v1_config.get("action_name", ""),
            action_name_zh=v1_config.get("action_name_zh", ""),
            description=v1_config.get("description", ""),
            version=v1_config.get("version", "1.0.0"),
            phases=phases,
            metrics=metrics,
            global_params=v1_config.get("global_params", {}),
            cycle_definition=cycle_meta.definition if cycle_meta else None,
            metadata={
                **v1_config.get("metadata", {}),
                "cycle_definition_source": cycle_meta.source.value if cycle_meta else CycleDefinitionSource.MISSING.value,
                "transformed_from_v1": True,
            },
        )

    @classmethod
    def _convert_phases(
        cls, v1_phases: List[Dict[str, Any]]
    ) -> List[PhaseDefinition]:
        """转换阶段定义."""
        phases = []
        for i, v1_phase in enumerate(v1_phases):
            phase = PhaseDefinition(
                phase_id=v1_phase.get("phase_id", f"phase_{i}"),
                phase_name=v1_phase.get("phase_name", ""),
                description=v1_phase.get("description"),
                # V1 的 detection_params 保持原样，PhaseEngine 会处理
                entry_conditions=[],
                exit_conditions=[],
            )
            phases.append(phase)
        return phases

    @classmethod
    def _convert_metrics(
        cls, v1_metrics: List[Dict[str, Any]]
    ) -> List[MetricConfig]:
        """转换检测项配置."""
        metrics = []
        for v1_metric in v1_metrics:
            # 转换阈值
            thresholds = None
            v1_thresholds = v1_metric.get("thresholds", {})
            if v1_thresholds:
                thresholds = MetricThreshold(
                    target_value=v1_thresholds.get("target_value"),
                    normal_range=tuple(v1_thresholds["normal_range"])
                    if "normal_range" in v1_thresholds
                    else None,
                    excellent_range=tuple(v1_thresholds["excellent_range"])
                    if "excellent_range" in v1_thresholds
                    else None,
                    good_range=tuple(v1_thresholds["good_range"])
                    if "good_range" in v1_thresholds
                    else None,
                    pass_range=tuple(v1_thresholds["pass_range"])
                    if "pass_range" in v1_thresholds
                    else None,
                )

            # 转换错误条件
            error_conditions = []
            for v1_error in v1_metric.get("error_conditions", []):
                error_conditions.append(
                    ErrorCondition(
                        error_id=v1_error.get("error_id", ""),
                        error_name=v1_error.get("error_name", ""),
                        description=v1_error.get("description", ""),
                        severity=v1_error.get("severity", "medium"),
                        condition=v1_error.get("condition", {}),
                    )
                )

            metric = MetricConfig(
                metric_id=v1_metric.get("metric_id", ""),
                enabled=v1_metric.get("enabled", True),
                evaluation_phase=v1_metric.get("evaluation_phase", ""),
                thresholds=thresholds,
                error_conditions=error_conditions,
                weight=v1_metric.get("weight", 1.0),
                custom_params=v1_metric.get("custom_params", {}),
            )
            metrics.append(metric)

        return metrics

    @classmethod
    def _convert_cycle_definition(
        cls,
        action_id: str,
        phases: List[PhaseDefinition],
        v1_cycle: Optional[Dict[str, Any]],
    ) -> Optional[CycleDefinitionWithMeta]:
        """转换周期定义."""
        if v1_cycle:
            # 用户显式配置了 cycle_definition
            return CycleDefinitionWithMeta(
                definition=CycleDefinition(
                    phase_sequence=v1_cycle.get("phase_sequence", []),
                    start_phase=v1_cycle.get("start_phase"),
                    end_phase=v1_cycle.get("end_phase"),
                    required_phases=v1_cycle.get("required_phases", []),
                    cycle_mode=v1_cycle.get("cycle_mode", "closed"),
                    min_cycle_duration=v1_cycle.get("min_cycle_duration", 1.0),
                    max_cycle_duration=v1_cycle.get("max_cycle_duration", 30.0),
                ),
                source=CycleDefinitionSource.EXPLICIT,
                confidence=1.0,
                generated_at="",
                generated_by="user_v1",
                validation_warnings=[],
            )

        # 尝试基于阶段名称推断
        return CycleDefinitionSuggester.suggest(phases)


class CycleDefinitionSuggester:
    """周期定义建议器（迁移期辅助工具，非主路径）."""

    # 阶段语义模式库（按语义分组，非动作ID）
    SEMANTIC_PATTERNS = {
        "closed_loop": {
            "description": "闭环动作（回到起点）",
            "phase_markers": {
                "start": ["start", "initial", "ready", "setup"],
                "execution": ["action", "movement", "dynamic"],
                "peak": ["peak", "top", "bottom", "max", "min"],
                "end": ["end", "finish", "complete", "return"],
            },
        },
        "open_sequence": {
            "description": "开环序列（单向执行）",
            "phase_markers": {
                "start": ["start"],
                "middle": ["process", "execution"],
                "end": ["end"],
            },
        },
        "hold_based": {
            "description": "保持型动作（hold为核心）",
            "phase_markers": {
                "entry": ["start", "enter"],
                "hold": ["hold", "static", "maintain"],
                "exit": ["release", "end", "exit"],
            },
        },
    }

    @classmethod
    def suggest(
        cls, phases: List[PhaseDefinition]
    ) -> Optional[CycleDefinitionWithMeta]:
        """建议周期定义（仅建议，不自动应用）.

        Returns:
            CycleDefinitionWithMeta 或 None
        """
        warnings = []
        phase_ids = [p.phase_id for p in phases]

        # 1. 基础校验
        if len(phases) < 2:
            warnings.append("阶段数量少于2，无法形成有效周期")
            return CycleDefinitionWithMeta(
                definition=None,
                source=CycleDefinitionSource.MISSING,
                confidence=0.0,
                generated_at="",
                generated_by="suggester",
                validation_warnings=warnings,
            )

        # 2. 基于阶段名称语义推断
        suggested = cls._infer_by_semantics(phases, warnings)

        if suggested:
            # 3. 完整可达性校验
            is_valid, validation_warnings = cls._validate_reachability(
                suggested, phases
            )
            warnings.extend(validation_warnings)

            if is_valid:
                return CycleDefinitionWithMeta(
                    definition=suggested,
                    source=CycleDefinitionSource.TEMPLATE_FALLBACK,
                    confidence=0.7,
                    generated_at="",
                    generated_by="suggester_semantic",
                    validation_warnings=warnings,
                )

        return CycleDefinitionWithMeta(
            definition=None,
            source=CycleDefinitionSource.MISSING,
            confidence=0.0,
            generated_at="",
            generated_by="suggester",
            validation_warnings=warnings,
        )

    @classmethod
    def _infer_by_semantics(
        cls,
        phases: List[PhaseDefinition],
        warnings: List[str],
    ) -> Optional[CycleDefinition]:
        """基于阶段名称语义推断周期定义."""
        phase_ids = [p.phase_id for p in phases]

        # 查找语义标记
        markers = cls._find_semantic_markers(phase_ids)

        if not markers.get("start"):
            warnings.append("未找到明确的起始阶段标记（如 start/initial/ready）")
            return None

        # 推断周期结构
        start_phase = markers["start"]
        end_phase = markers.get("end", start_phase)  # 默认闭环

        # 识别关键阶段（优先使用 peak/hold 类标记）
        required_phases = []
        if markers.get("peak"):
            required_phases.append(markers["peak"])
        elif markers.get("hold"):
            required_phases.append(markers["hold"])
        else:
            # 使用中间阶段作为关键阶段
            mid_idx = len(phase_ids) // 2
            required_phases.append(phase_ids[mid_idx])
            warnings.append(
                f"未识别关键阶段，使用中间阶段 {phase_ids[mid_idx]} 作为 required_phase"
            )

        return CycleDefinition(
            phase_sequence=phase_ids,
            start_phase=start_phase,
            end_phase=end_phase,
            required_phases=required_phases,
            cycle_mode="closed" if end_phase == start_phase else "open",
        )

    @classmethod
    def _find_semantic_markers(cls, phase_ids: List[str]) -> Dict[str, str]:
        """查找阶段语义标记."""
        markers = {}

        for pattern_name, pattern in cls.SEMANTIC_PATTERNS.items():
            for marker_type, candidates in pattern["phase_markers"].items():
                for phase_id in phase_ids:
                    if any(c in phase_id.lower() for c in candidates):
                        if marker_type not in markers:  # 保留第一个匹配
                            markers[marker_type] = phase_id

        return markers

    @classmethod
    def _validate_reachability(
        cls, cycle_def: CycleDefinition, phases: List[PhaseDefinition]
    ) -> Tuple[bool, List[str]]:
        """校验周期定义的完整可达性."""
        warnings = []
        phase_ids = {p.phase_id for p in phases}
        sequence_set = set(cycle_def.phase_sequence)

        # 1. 存在性校验
        for ref_phase in [
            cycle_def.start_phase,
            cycle_def.end_phase,
        ] + cycle_def.required_phases:
            if ref_phase not in phase_ids:
                warnings.append(f"引用的阶段 '{ref_phase}' 不在可用阶段列表中")
                return False, warnings

        # 2. sequence 一致性校验
        if cycle_def.start_phase not in sequence_set:
            warnings.append(
                f"start_phase '{cycle_def.start_phase}' 不在 phase_sequence 中"
            )
        if cycle_def.end_phase not in sequence_set:
            warnings.append(
                f"end_phase '{cycle_def.end_phase}' 不在 phase_sequence 中"
            )

        for req in cycle_def.required_phases:
            if req not in sequence_set:
                warnings.append(f"required_phase '{req}' 不在 phase_sequence 中")

        return len(warnings) == 0, warnings
