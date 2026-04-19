"""动作阶段检测模块."""
from .squat_phases import SquatPhaseDetector, SquatPhase
from .engine import (
    PhaseEngine,
    PhaseConfig,
    PhaseSequence,
    PhaseDetection,
    Condition,
    ConditionType,
    Operator,
)
from .counter import (
    RepCounter,
    CycleDefinition,
    RepCountResult,
    RepDetail,
)
from .boundary_learner import (
    PhaseBoundaryLearner,
    PhaseBoundary,
    PhaseLearningResult,
)

__all__ = [
    # V1 兼容
    "SquatPhaseDetector",
    "SquatPhase",
    # V2 新增
    "PhaseEngine",
    "PhaseConfig",
    "PhaseSequence",
    "PhaseDetection",
    "Condition",
    "ConditionType",
    "Operator",
    "RepCounter",
    "CycleDefinition",
    "RepCountResult",
    "RepDetail",
    "PhaseBoundaryLearner",
    "PhaseBoundary",
    "PhaseLearningResult",
]
