"""数据集仓储."""

from __future__ import annotations

import json
from pathlib import Path

from .models import AnnotationTask, SampleRecord, VideoSample


class DatasetRepository:
    """管理训练样本及其反馈状态."""

    def __init__(self, storage_path: str | Path | None = None) -> None:
        self.storage_path = Path(storage_path) if storage_path else None
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

    def list_samples_for_iteration(self, action_id: str | None = None) -> list[VideoSample]:
        """列出下一轮训练应纳入的样本."""
        eligible_statuses = {"ready", "queued_for_retraining"}
        records = [
            record for record in self._records.values()
            if record.status in eligible_statuses
            and (action_id is None or record.sample.action_id == action_id)
        ]
        records.sort(key=lambda record: (record.status != "queued_for_retraining", record.sample.sample_id))
        return [record.sample for record in records]

    def save(self) -> None:
        """持久化仓储内容."""
        if self.storage_path is None:
            raise ValueError("storage_path is not configured")

        payload = {
            "records": [record.to_dict() for record in self._records.values()],
            "annotation_tasks": [task.to_dict() for task in self._annotation_tasks.values()],
        }
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, storage_path: str | Path) -> "DatasetRepository":
        """从磁盘恢复仓储."""
        path = Path(storage_path)
        repository = cls(storage_path=path)
        with open(path, "r", encoding="utf-8") as file:
            payload = json.load(file)

        for record_data in payload.get("records", []):
            record = SampleRecord.from_dict(record_data)
            repository._records[record.sample.sample_id] = record

        for task_data in payload.get("annotation_tasks", []):
            task = AnnotationTask.from_dict(task_data)
            repository._annotation_tasks[task.sample_id] = task

        return repository
