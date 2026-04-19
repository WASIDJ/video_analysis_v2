"""配置数据模型."""
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union
import json


class ComparisonOperator(Enum):
    """比较操作符."""
    LT = "lt"      # 小于
    LTE = "lte"    # 小于等于
    GT = "gt"      # 大于
    GTE = "gte"    # 大于等于
    EQ = "eq"      # 等于
    NEQ = "neq"    # 不等于
    BETWEEN = "between"  # 在范围内


class CycleDefinitionSource(str, Enum):
    """周期定义来源（用于追溯和审计）."""
    EXPLICIT = "explicit"           # 用户显式配置（最高优先级）
    DATA_INFERRED = "data_inferred" # 基于训练数据推断
    TEMPLATE_FALLBACK = "template"  # 模板回退（最低优先级）
    MISSING = "missing"             # 未配置（计数功能不可用）


@dataclass
class CycleDefinition:
    """动作周期定义."""
    # 完整周期所需的阶段序列（有序）
    phase_sequence: List[str]
    # 起始阶段（可从中间开始，默认第一个）
    start_phase: Optional[str] = None
    # 结束阶段（回到起始或特定阶段，默认第一个形成闭环）
    end_phase: Optional[str] = None
    # 关键阶段（必须存在才能算一个有效周期）
    required_phases: List[str] = field(default_factory=list)
    # 循环模式
    cycle_mode: str = "closed"  # closed: 闭环, open: 开环
    # 时长限制
    min_cycle_duration: float = 1.0   # 秒，过滤抖动
    max_cycle_duration: float = 30.0  # 秒，过滤异常

    def __post_init__(self):
        # 默认值处理
        if self.start_phase is None and self.phase_sequence:
            self.start_phase = self.phase_sequence[0]
        if self.end_phase is None and self.phase_sequence:
            self.end_phase = self.phase_sequence[0]

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "CycleDefinition":
        return cls(
            phase_sequence=data.get("phase_sequence", []),
            start_phase=data.get("start_phase"),
            end_phase=data.get("end_phase"),
            required_phases=data.get("required_phases", []),
            cycle_mode=data.get("cycle_mode", "closed"),
            min_cycle_duration=data.get("min_cycle_duration", 1.0),
            max_cycle_duration=data.get("max_cycle_duration", 30.0),
        )


@dataclass
class CycleDefinitionWithMeta:
    """带元信息的周期定义."""
    definition: Optional[CycleDefinition]
    source: CycleDefinitionSource
    confidence: float              # 定义可信度（0-1）
    generated_at: str              # 生成时间
    generated_by: str              # 生成工具/算法
    validation_warnings: List[str] # 校验警告

    def to_dict(self) -> Dict:
        return {
            "definition": self.definition.to_dict() if self.definition else None,
            "source": self.source.value,
            "confidence": self.confidence,
            "generated_at": self.generated_at,
            "generated_by": self.generated_by,
            "validation_warnings": self.validation_warnings,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "CycleDefinitionWithMeta":
        def_data = data.get("definition")
        return cls(
            definition=CycleDefinition.from_dict(def_data) if def_data else None,
            source=CycleDefinitionSource(data.get("source", "missing")),
            confidence=data.get("confidence", 0.0),
            generated_at=data.get("generated_at", ""),
            generated_by=data.get("generated_by", ""),
            validation_warnings=data.get("validation_warnings", []),
        )
    """周期定义来源（用于追溯和审计）."""
    EXPLICIT = "explicit"           # 用户显式配置（最高优先级）
    DATA_INFERRED = "data_inferred" # 基于训练数据推断
    TEMPLATE_FALLBACK = "template"  # 模板回退（最低优先级）
    MISSING = "missing"             # 未配置（计数功能不可用）


@dataclass
class PhaseDefinition:
    """动作阶段定义."""
    phase_id: str
    phase_name: str
    description: str = ""
    # 阶段识别参数
    detection_params: Dict[str, Any] = field(default_factory=dict)
    # V2: 进入条件
    entry_conditions: List[Dict[str, Any]] = field(default_factory=list)
    # V2: 退出条件
    exit_conditions: List[Dict[str, Any]] = field(default_factory=list)
    # V2: 稳定性检查
    stability_checks: List[Dict[str, Any]] = field(default_factory=list)
    # V2: 最大持续时间（秒）
    max_duration: Optional[float] = None
    # V2: 最小持续时间（秒）
    min_duration: Optional[float] = None

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "PhaseDefinition":
        # 处理向后兼容
        kwargs = {
            "phase_id": data["phase_id"],
            "phase_name": data["phase_name"],
            "description": data.get("description", ""),
            "detection_params": data.get("detection_params", {}),
            "entry_conditions": data.get("entry_conditions", []),
            "exit_conditions": data.get("exit_conditions", []),
            "stability_checks": data.get("stability_checks", []),
            "max_duration": data.get("max_duration"),
            "min_duration": data.get("min_duration"),
        }
        return cls(**kwargs)


@dataclass
class MetricThreshold:
    """检测项阈值配置."""
    # 正常范围
    normal_range: Optional[tuple] = None
    # 目标值
    target_value: Optional[float] = None
    # 分级范围
    excellent_range: Optional[tuple] = None
    good_range: Optional[tuple] = None
    pass_range: Optional[tuple] = None

    def to_dict(self) -> Dict:
        result = {}
        for key in ['normal_range', 'excellent_range', 'good_range', 'pass_range']:
            value = getattr(self, key)
            if value is not None:
                result[key] = list(value) if isinstance(value, tuple) else value
        if self.target_value is not None:
            result['target_value'] = self.target_value
        return result

    @classmethod
    def from_dict(cls, data: Dict) -> "MetricThreshold":
        kwargs = {}
        for key in ['normal_range', 'excellent_range', 'good_range', 'pass_range']:
            if key in data and data[key] is not None:
                value = data[key]
                kwargs[key] = tuple(value) if isinstance(value, list) else value
        if 'target_value' in data:
            kwargs['target_value'] = data['target_value']
        return cls(**kwargs)


@dataclass
class ErrorCondition:
    """错误判断条件."""
    error_id: str
    error_name: str
    description: str
    severity: str = "medium"  # low/medium/high
    # 判断条件（支持复杂逻辑）
    condition: Dict[str, Any] = field(default_factory=dict)
    # 简单的阈值条件（向后兼容）
    threshold_low: Optional[float] = None
    threshold_high: Optional[float] = None

    def to_dict(self) -> Dict:
        result = {
            "error_id": self.error_id,
            "error_name": self.error_name,
            "description": self.description,
            "severity": self.severity,
            "condition": self.condition,
        }
        if self.threshold_low is not None:
            result["threshold_low"] = self.threshold_low
        if self.threshold_high is not None:
            result["threshold_high"] = self.threshold_high
        return result

    @classmethod
    def from_dict(cls, data: Dict) -> "ErrorCondition":
        return cls(
            error_id=data["error_id"],
            error_name=data["error_name"],
            description=data.get("description", ""),
            severity=data.get("severity", "medium"),
            condition=data.get("condition", {}),
            threshold_low=data.get("threshold_low"),
            threshold_high=data.get("threshold_high"),
        )


@dataclass
class MetricConfig:
    """单个检测项的配置."""
    metric_id: str
    # 是否启用
    enabled: bool = True
    # 阶段定义（在哪个阶段评估）
    evaluation_phase: str = "bottom"  # standing/descent/bottom/ascent/completion
    # 阈值配置
    thresholds: MetricThreshold = field(default_factory=MetricThreshold)
    # 错误条件列表
    error_conditions: List[ErrorCondition] = field(default_factory=list)
    # 自定义参数
    custom_params: Dict[str, Any] = field(default_factory=dict)
    # 权重（用于组合评分）
    weight: float = 1.0

    def to_dict(self) -> Dict:
        return {
            "metric_id": self.metric_id,
            "enabled": self.enabled,
            "evaluation_phase": self.evaluation_phase,
            "thresholds": self.thresholds.to_dict(),
            "error_conditions": [e.to_dict() for e in self.error_conditions],
            "custom_params": self.custom_params,
            "weight": self.weight,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "MetricConfig":
        return cls(
            metric_id=data["metric_id"],
            enabled=data.get("enabled", True),
            evaluation_phase=data.get("evaluation_phase", "bottom"),
            thresholds=MetricThreshold.from_dict(data.get("thresholds", {})),
            error_conditions=[ErrorCondition.from_dict(e) for e in data.get("error_conditions", [])],
            custom_params=data.get("custom_params", {}),
            weight=data.get("weight", 1.0),
        )


@dataclass
class ActionConfig:
    """动作配置 - V2版本（向后兼容V1）."""
    # Schema版本标识
    schema_version: str = "2.0.0"

    # 基础信息
    action_id: str = ""
    action_name: str = ""
    action_name_zh: str = ""
    description: str = ""
    version: str = "1.0.0"
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    # 阶段定义
    phases: List[PhaseDefinition] = field(default_factory=list)

    # 检测项配置
    metrics: List[MetricConfig] = field(default_factory=list)

    # 全局参数
    global_params: Dict[str, Any] = field(default_factory=dict)

    # V2: 周期定义（可选，用于动作计数）
    cycle_definition: Optional[CycleDefinition] = None

    # V3: 双层相位计数结构
    count_layer: Dict[str, Any] = field(default_factory=dict)
    semantic_layer: Dict[str, Any] = field(default_factory=dict)
    compatibility: Dict[str, Any] = field(default_factory=dict)

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "schema_version": self.schema_version,
            "action_id": self.action_id,
            "action_name": self.action_name,
            "action_name_zh": self.action_name_zh,
            "description": self.description,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "phases": [p.to_dict() for p in self.phases],
            "metrics": [m.to_dict() for m in self.metrics],
            "global_params": self.global_params,
            "cycle_definition": self.cycle_definition.to_dict() if self.cycle_definition else None,
            "count_layer": self.count_layer,
            "semantic_layer": self.semantic_layer,
            "compatibility": self.compatibility,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ActionConfig":
        # 处理向后兼容：V1 配置可能没有 schema_version
        schema_version = data.get("schema_version", "1.0.0")

        # 处理 cycle_definition（V1可能没有）
        cycle_def = None
        if "cycle_definition" in data and data["cycle_definition"]:
            cycle_def = CycleDefinition.from_dict(data["cycle_definition"])

        return cls(
            schema_version=schema_version,
            action_id=data.get("action_id", ""),
            action_name=data.get("action_name", ""),
            action_name_zh=data.get("action_name_zh", ""),
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            phases=[PhaseDefinition.from_dict(p) for p in data.get("phases", [])],
            metrics=[MetricConfig.from_dict(m) for m in data.get("metrics", [])],
            global_params=data.get("global_params", {}),
            cycle_definition=cycle_def,
            count_layer=data.get("count_layer", {}),
            semantic_layer=data.get("semantic_layer", {}),
            compatibility=data.get("compatibility", {}),
            metadata=data.get("metadata", {}),
        )

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "ActionConfig":
        return cls.from_dict(json.loads(json_str))

    def get_metric_config(self, metric_id: str) -> Optional[MetricConfig]:
        """获取指定检测项的配置."""
        for metric in self.metrics:
            if metric.metric_id == metric_id:
                return metric
        return None

    def update_metric_config(self, metric_id: str, config: MetricConfig) -> bool:
        """更新检测项配置."""
        for i, metric in enumerate(self.metrics):
            if metric.metric_id == metric_id:
                self.metrics[i] = config
                self.updated_at = datetime.now().isoformat()
                return True
        return False


@dataclass
class ExecutionRecord:
    """执行记录."""
    record_id: str
    timestamp: str
    action_id: str
    action_version: str
    algorithm_version: str
    video_path: str

    # 使用的参数
    params_used: Dict[str, Any]

    # 执行结果摘要
    results_summary: Dict[str, Any] = field(default_factory=dict)

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "ExecutionRecord":
        return cls(**data)
