"""迭代任务状态机."""

from __future__ import annotations

from datetime import datetime

from .models import IterationJob, IterationStatus, RetryPolicy


class IterationStateMachine:
    """管理迭代任务状态转换."""

    def __init__(self, retry_policy: RetryPolicy) -> None:
        self.retry_policy = retry_policy

    def start(self, job: IterationJob) -> IterationJob:
        """启动任务."""
        if job.status not in {IterationStatus.PENDING}:
            raise ValueError(f"cannot start job from status={job.status}")
        job.status = IterationStatus.RUNNING
        job.started_at = datetime.now().isoformat()
        job.finished_at = None
        job.last_error = None
        return job

    def succeed(self, job: IterationJob) -> IterationJob:
        """标记任务成功."""
        if job.status is not IterationStatus.RUNNING:
            raise ValueError(f"cannot succeed job from status={job.status}")
        job.status = IterationStatus.SUCCEEDED
        job.finished_at = datetime.now().isoformat()
        return job

    def fail(self, job: IterationJob, error: str, retryable: bool = True) -> IterationJob:
        """标记任务失败，并在允许时回到 pending."""
        if job.status is not IterationStatus.RUNNING:
            raise ValueError(f"cannot fail job from status={job.status}")

        if retryable and job.retry_count < self.retry_policy.max_retries:
            job.retry_count += 1
            job.status = IterationStatus.PENDING
            job.last_error = error
            job.finished_at = None
            return job

        job.status = IterationStatus.FAILED
        job.last_error = error
        job.finished_at = datetime.now().isoformat()
        return job

    def cancel(self, job: IterationJob) -> IterationJob:
        """取消任务."""
        if job.status not in {IterationStatus.PENDING, IterationStatus.RUNNING}:
            raise ValueError(f"cannot cancel job from status={job.status}")
        job.status = IterationStatus.CANCELLED
        job.finished_at = datetime.now().isoformat()
        return job
