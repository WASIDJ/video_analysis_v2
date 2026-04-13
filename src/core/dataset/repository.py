"""数据集仓储."""

from __future__ import annotations

from .models import AnnotationTask, SampleRecord, VideoSample


class DatasetRepository:
    """管理训练样本及其反馈状态."""

    def __init__(self) -> None:
        self._records: dict[str, SampleRecord] = {}
        self._annotation_tasks: dict[str, AnnotationTask] = {}

    def add_sample(self, sample: VideoSample) -> SampleRecord:
        """添加样本到仓库."""
        record = SampleRecord(sample=sample)
        self._records[sample.sample_id] = record
        return record

    def get_record(self, sample_id: str) -> SampleRecord | None:
        """获取样本记录."""
        return self._records.get(sample_id)

    def require_record(self, sample_id: str) -> SampleRecord:
        """获取样本记录，不存在则抛错."""
        record = self.get_record(sample_id)
        if record is None:
            raise KeyError(f"sample_id not found: {sample_id}")
        return record

    def create_annotation_task(
        self,
        sample_id: str,
        reason: str,
        source_version: str | None = None,
    ) -> AnnotationTask:
        """创建待标注任务，按 sample_id 去重."""
        if sample_id in self._annotation_tasks:
            return self._annotation_tasks[sample_id]

        record = self.require_record(sample_id)
        task = AnnotationTask(
            sample_id=record.sample.sample_id,
            action_id=record.sample.action_id,
            label=record.sample.label,
            reason=reason,
            source_version=source_version,
        )
        self._annotation_tasks[sample_id] = task
        return task

    def list_annotation_tasks(self) -> list[AnnotationTask]:
        """列出待标注任务."""
        return list(self._annotation_tasks.values())
