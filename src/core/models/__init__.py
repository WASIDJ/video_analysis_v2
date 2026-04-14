"""姿态估计模型模块.

使用延迟导入避免在轻量入口中提前加载大模型依赖。
"""

__all__ = [
    "BasePoseEstimator",
    "Keypoint",
    "PoseFrame",
    "BlazePoseEstimator",
    "YOLOPoseAdapter",
]


def __getattr__(name: str):
    if name in {"BasePoseEstimator", "Keypoint", "PoseFrame"}:
        from .base import BasePoseEstimator, Keypoint, PoseFrame

        return {
            "BasePoseEstimator": BasePoseEstimator,
            "Keypoint": Keypoint,
            "PoseFrame": PoseFrame,
        }[name]

    if name == "BlazePoseEstimator":
        from .blazepose import BlazePoseEstimator

        return BlazePoseEstimator

    if name == "YOLOPoseAdapter":
        from .yolo_adapter import YOLOPoseAdapter

        return YOLOPoseAdapter

    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
