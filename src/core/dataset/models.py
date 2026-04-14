"""数据集领域模型."""

from __future__ import annotations

from dataclasses import dataclass, field
from collections import Counter


@dataclass(frozen=True)
class VideoSample:
    """
    单个视频样本.

    TODO: video_path 之后要考虑改成更抽象的存储路径（比如 S3 URL）以支持云存储.
    TODO: 可以考虑增加 metadata 字段存储额外信息（拍摄设备、环境条件等）以便后续分析和拆分. 

    """

    sample_id: str
    action_id: str
    label: str
    video_path: str

    def to_dict(self) -> dict[str, str]:
        """序列化为字典."""
        return {
            "sample_id": self.sample_id,
            "action_id": self.action_id,
            "label": self.label,
            "video_path": self.video_path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str]) -> "VideoSample":
        """从字典反序列化."""
        return cls(**data)


@dataclass(frozen=True)
class FeedbackRecord:
    """单次反馈记录."""

    sample_id: str
    confidence: float
    predicted_label: str | None = None
    expected_label: str | None = None
    source_version: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, str | float | None]:
        """序列化为字典."""
        return {
            "sample_id": self.sample_id,
            "confidence": self.confidence,
            "predicted_label": self.predicted_label,
            "expected_label": self.expected_label,
            "source_version": self.source_version,
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str | float | None]) -> "FeedbackRecord":
        """从字典反序列化."""
        return cls(**data)


@dataclass
class SampleRecord:
    """仓库中的样本记录."""

    sample: VideoSample
    status: str = "ready"
    tags: list[str] = field(default_factory=list)
    source_version: str | None = None
    misclassification_count: int = 0
    feedback_history: list[FeedbackRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        """序列化为字典."""
        return {
            "sample": self.sample.to_dict(),
            "status": self.status,
            "tags": self.tags,
            "source_version": self.source_version,
            "misclassification_count": self.misclassification_count,
            "feedback_history": [record.to_dict() for record in self.feedback_history],
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "SampleRecord":
        """从字典反序列化."""
        return cls(
            sample=VideoSample.from_dict(data["sample"]),
            status=data.get("status", "ready"),
            tags=list(data.get("tags", [])),
            source_version=data.get("source_version"),
            misclassification_count=data.get("misclassification_count", 0),
            feedback_history=[
                FeedbackRecord.from_dict(record)
                for record in data.get("feedback_history", [])
            ],
        )


@dataclass(frozen=True)
class AnnotationTask:
    """待标注任务."""

    sample_id: str
    action_id: str
    label: str
    reason: str
    source_version: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        """序列化为字典."""
        return {
            "sample_id": self.sample_id,
            "action_id": self.action_id,
            "label": self.label,
            "reason": self.reason,
            "source_version": self.source_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, str | None]) -> "AnnotationTask":
        """从字典反序列化."""
        return cls(**data)


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
