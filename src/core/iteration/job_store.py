"""迭代任务仓储."""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from .models import IterationJob, ModelEvaluation


class IterationJobStore:
    """保存与查询迭代任务."""

    def __init__(self, storage_path: str | Path | None = None) -> None:
        self.storage_path = Path(storage_path) if storage_path else None
        self._jobs: dict[str, IterationJob] = {}
        if self.storage_path and self.storage_path.exists():
            self._load()

    def create_job(
        self,
        action_id: str,
        baseline: ModelEvaluation,
        candidate: ModelEvaluation,
        trigger_reason: str,
    ) -> IterationJob:
        """创建任务."""
        job_id = str(uuid.uuid4())[:8]
        job = IterationJob(
            job_id=job_id,
            action_id=action_id,
            trigger_reason=trigger_reason,
            dataset_version=candidate.dataset_version,
            baseline_version=baseline.version_id,
            candidate_version=candidate.version_id,
            baseline=baseline,
            candidate=candidate,
        )
        self._jobs[job_id] = job
        self._save()
        return job

    def require_job(self, job_id: str) -> IterationJob:
        """获取任务."""
        job = self._jobs.get(job_id)
        if job is None:
            raise KeyError(f"job_id not found: {job_id}")
        return job

    def get_job(self, job_id: str) -> IterationJob | None:
        """尝试获取任务."""
        return self._jobs.get(job_id)

    def update_job(self, job: IterationJob) -> None:
        """更新任务."""
        self._jobs[job.job_id] = job
        self._save()

    def list_jobs(self) -> list[IterationJob]:
        """列出所有任务."""
        return sorted(self._jobs.values(), key=lambda job: job.job_id)

    def _save(self) -> None:
        if self.storage_path is None:
            return
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"jobs": [job.to_dict() for job in self._jobs.values()]}
        with open(self.storage_path, "w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2, ensure_ascii=False)

    def _load(self) -> None:
        with open(self.storage_path, "r", encoding="utf-8") as file:
            payload = json.load(file)
        self._jobs = {
            job_data["job_id"]: IterationJob.from_dict(job_data)
            for job_data in payload.get("jobs", [])
        }
