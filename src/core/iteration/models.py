"""迭代系统数据模型."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class IterationStatus(str, Enum):
    """迭代任务状态."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class RetryPolicy:
    """重试策略."""

    max_retries: int = 0


@dataclass(frozen=True)
class EvaluationSampleResult:
    """单个样本的评估结果."""

    sample_id: str
    confidence: float
    predicted_label: str
    expected_label: str
    source_version: str
    split: str = "test"

    def to_dict(self) -> dict[str, object]:
        return {
            "sample_id": self.sample_id,
            "confidence": self.confidence,
            "predicted_label": self.predicted_label,
            "expected_label": self.expected_label,
            "source_version": self.source_version,
            "split": self.split,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "EvaluationSampleResult":
        return cls(**data)


@dataclass(frozen=True)
class ModelEvaluation:
    """模型版本评估结果."""

    version_id: str
    action_id: str
    overall_score: float
    metric_scores: dict[str, float]
    sample_results: list[EvaluationSampleResult]
    dataset_version: str
    config_version: str

    def to_dict(self) -> dict[str, object]:
        return {
            "version_id": self.version_id,
            "action_id": self.action_id,
            "overall_score": self.overall_score,
            "metric_scores": self.metric_scores,
            "sample_results": [sample.to_dict() for sample in self.sample_results],
            "dataset_version": self.dataset_version,
            "config_version": self.config_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "ModelEvaluation":
        return cls(
            version_id=data["version_id"],
            action_id=data["action_id"],
            overall_score=data["overall_score"],
            metric_scores=data["metric_scores"],
            sample_results=[
                EvaluationSampleResult.from_dict(sample)
                for sample in data.get("sample_results", [])
            ],
            dataset_version=data["dataset_version"],
            config_version=data["config_version"],
        )


@dataclass
class IterationJob:
    """单次参数迭代任务."""

    job_id: str
    action_id: str
    status: IterationStatus = IterationStatus.PENDING
    retry_count: int = 0
    last_error: str | None = None
    trigger_reason: str | None = None
    dataset_version: str | None = None
    baseline_version: str | None = None
    candidate_version: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    baseline: ModelEvaluation | None = None
    candidate: ModelEvaluation | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "job_id": self.job_id,
            "action_id": self.action_id,
            "status": self.status.value,
            "retry_count": self.retry_count,
            "last_error": self.last_error,
            "trigger_reason": self.trigger_reason,
            "dataset_version": self.dataset_version,
            "baseline_version": self.baseline_version,
            "candidate_version": self.candidate_version,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "baseline": self.baseline.to_dict() if self.baseline else None,
            "candidate": self.candidate.to_dict() if self.candidate else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "IterationJob":
        return cls(
            job_id=data["job_id"],
            action_id=data["action_id"],
            status=IterationStatus(data.get("status", IterationStatus.PENDING.value)),
            retry_count=data.get("retry_count", 0),
            last_error=data.get("last_error"),
            trigger_reason=data.get("trigger_reason"),
            dataset_version=data.get("dataset_version"),
            baseline_version=data.get("baseline_version"),
            candidate_version=data.get("candidate_version"),
            started_at=data.get("started_at"),
            finished_at=data.get("finished_at"),
            baseline=ModelEvaluation.from_dict(data["baseline"]) if data.get("baseline") else None,
            candidate=ModelEvaluation.from_dict(data["candidate"]) if data.get("candidate") else None,
        )


@dataclass(frozen=True)
class TriggerSnapshot:
    """触发器输入快照."""

    action_id: str
    new_samples: int
    low_confidence_samples: int
    last_training_at: datetime | None
    now: datetime
    snapshot_id: str | None = None


@dataclass(frozen=True)
class TriggerDecision:
    """触发判断结果."""

    triggered: bool
    reasons: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvaluationDecision:
    """baseline/candidate 对比结论."""

    should_promote: bool
    improvement: float
    regressions: list[str]
    dataset_version: str
    baseline_version: str
    candidate_version: str

    def to_dict(self) -> dict[str, object]:
        return {
            "should_promote": self.should_promote,
            "improvement": self.improvement,
            "regressions": self.regressions,
            "dataset_version": self.dataset_version,
            "baseline_version": self.baseline_version,
            "candidate_version": self.candidate_version,
        }


@dataclass
class VersionRecord:
    """版本库中的单条记录."""

    action_id: str
    version_id: str
    dataset_version: str
    config_version: str
    metrics: dict[str, float]
    status: str
    is_active: bool = False
    parent_version: str | None = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> dict[str, object]:
        return {
            "action_id": self.action_id,
            "version_id": self.version_id,
            "dataset_version": self.dataset_version,
            "config_version": self.config_version,
            "metrics": self.metrics,
            "status": self.status,
            "is_active": self.is_active,
            "parent_version": self.parent_version,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "VersionRecord":
        return cls(**data)
