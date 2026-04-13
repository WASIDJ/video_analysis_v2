"""数据集领域模型."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import Counter


@dataclass(frozen=True)
class VideoSample:
    """单个视频样本."""

    sample_id: str
    action_id: str
    label: str
    video_path: str


@dataclass(frozen=True)
class FeedbackRecord:
    """单次反馈记录."""

    sample_id: str
    confidence: float
    predicted_label: str | None = None
    expected_label: str | None = None
    source_version: str | None = None
    reason: str | None = None


@dataclass
class SampleRecord:
    """仓库中的样本记录."""

    sample: VideoSample
    status: str = "ready"
    tags: list[str] = field(default_factory=list)
    source_version: str | None = None
    misclassification_count: int = 0
    feedback_history: list[FeedbackRecord] = field(default_factory=list)


@dataclass(frozen=True)
class AnnotationTask:
    """待标注任务."""

    sample_id: str
    action_id: str
    label: str
    reason: str
    source_version: str | None = None


@dataclass
class DatasetSplit:
    """训练/验证/测试拆分结果."""

    train: list[VideoSample] = field(default_factory=list)
    validation: list[VideoSample] = field(default_factory=list)
    test: list[VideoSample] = field(default_factory=list)

    @staticmethod
    def count_by_group(samples: list[VideoSample]) -> Counter[tuple[str, str]]:
        """按 action_id + label 统计样本数."""
        return Counter((sample.action_id, sample.label) for sample in samples)
