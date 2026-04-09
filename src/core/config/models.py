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


@dataclass
class PhaseDefinition:
    """动作阶段定义."""
    phase_id: str
    phase_name: str
    description: str = ""
    # 阶段识别参数
    detection_params: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "PhaseDefinition":
        return cls(**data)


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
    """动作配置."""
    # 基础信息
    action_id: str
    action_name: str
    action_name_zh: str
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

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
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
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "ActionConfig":
        return cls(
            action_id=data["action_id"],
            action_name=data["action_name"],
            action_name_zh=data["action_name_zh"],
            description=data.get("description", ""),
            version=data.get("version", "1.0.0"),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            phases=[PhaseDefinition.from_dict(p) for p in data.get("phases", [])],
            metrics=[MetricConfig.from_dict(m) for m in data.get("metrics", [])],
            global_params=data.get("global_params", {}),
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
