"""测试集反馈回流逻辑."""

from __future__ import annotations

from .models import FeedbackRecord, SampleRecord
from .repository import DatasetRepository

class FeedbackLoop:
    """处理低置信和误判样本回流."""

    def __init__(
        self,
        repository: DatasetRepository,
        low_confidence_threshold: float = 0.5,
        annotation_threshold: int = 3,
    ) -> None:
        self.repository = repository
        self.low_confidence_threshold = low_confidence_threshold
        self.annotation_threshold = annotation_threshold

    def process_feedback(self, feedback: FeedbackRecord) -> SampleRecord:
        """处理一条反馈并更新样本状态."""
        record = self.repository.require_record(feedback.sample_id)

        if record.status == "pending_annotation":
            return record

        record.feedback_history.append(feedback)

        if feedback.confidence < self.low_confidence_threshold:
            self._add_tag(record, "confusing_sample")
            record.status = "queued_for_retraining"
            if feedback.source_version is not None:
                record.source_version = feedback.source_version

        misclassified = (
            feedback.predicted_label is not None
            and feedback.expected_label is not None
            and feedback.predicted_label != feedback.expected_label
        )
        if misclassified:
            record.misclassification_count += 1
            record.status = "queued_for_retraining"
            if feedback.source_version is not None:
                record.source_version = feedback.source_version

        if record.misclassification_count >= self.annotation_threshold:
            record.status = "pending_annotation"
            self._add_tag(record, "pending_annotation")
            self.repository.create_annotation_task(
                record.sample.sample_id,
                reason="repeated_misclassification",
                source_version=record.source_version,
            )

        return record

    @staticmethod
    def _add_tag(record: SampleRecord, tag: str) -> None:
        """添加标签并避免重复."""
        if tag not in record.tags:
            record.tags.append(tag)
