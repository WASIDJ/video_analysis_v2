"""配置管理模块.

提供动作检测项参数的加载、验证和记录功能.
"""
from .manager import ConfigManager
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
from .transformer import ConfigTransformer, CycleDefinitionSuggester
from .validator import ParameterValidator
from .recorder import ParameterRecorder

__all__ = [
    "ConfigManager",
    "ActionConfig",
    "PhaseDefinition",
    "MetricConfig",
    "MetricThreshold",
    "ErrorCondition",
    "CycleDefinition",
    "CycleDefinitionSource",
    "CycleDefinitionWithMeta",
    "ConfigTransformer",
    "CycleDefinitionSuggester",
    "ParameterValidator",
    "ParameterRecorder",
]
