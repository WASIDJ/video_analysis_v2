"""训练流程模块.

提供批量视频处理、特征学习、自动配置生成等功能。
"""

# 避免循环导入，延迟导入依赖较重的模块
from .feature_validator import FeatureValidator, ValidationReport
from .error_learner import ErrorConditionLearner

__all__ = [
    "TrainingPipeline",
    "VideoTrainingConfig",
    "FeatureValidator",
    "ValidationReport",
    "ErrorConditionLearner",
    "BatchProcessor",
    "BatchConfig",
]

# 延迟导入
def __getattr__(name):
    if name == "TrainingPipeline" or name == "VideoTrainingConfig":
        from .pipeline import TrainingPipeline, VideoTrainingConfig
        return locals()[name]
    if name == "BatchProcessor" or name == "BatchConfig":
        from .batch_processor import BatchProcessor, BatchConfig
        return locals()[name]
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
