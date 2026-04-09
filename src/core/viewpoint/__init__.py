"""视角分析模块.

自动检测视频拍摄视角，并评估检测项的可靠性.
"""
from .analyzer import ViewpointAnalyzer, CameraViewpoint, ViewpointAnalysisResult
from .constraints import ViewpointConstraint, DetectionItemConstraint

__all__ = [
    "ViewpointAnalyzer",
    "CameraViewpoint",
    "ViewpointAnalysisResult",
    "ViewpointConstraint",
    "DetectionItemConstraint",
]
