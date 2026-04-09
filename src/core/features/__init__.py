"""特征提取模块."""
from .base import BaseFeatureExtractor
from .skeleton_features import SkeletonFeatureExtractor
from .segment_features import SegmentFeatureExtractor

__all__ = [
    "BaseFeatureExtractor",
    "SkeletonFeatureExtractor",
    "SegmentFeatureExtractor",
]