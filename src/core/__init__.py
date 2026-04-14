"""核心模块.

避免在包导入阶段加载重量级模型依赖。
"""

__all__ = ["BasePoseEstimator", "Keypoint", "PoseFrame"]


def __getattr__(name: str):
    if name in {"BasePoseEstimator", "Keypoint", "PoseFrame"}:
        from .models.base import BasePoseEstimator, Keypoint, PoseFrame

        return {
            "BasePoseEstimator": BasePoseEstimator,
            "Keypoint": Keypoint,
            "PoseFrame": PoseFrame,
        }[name]
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
