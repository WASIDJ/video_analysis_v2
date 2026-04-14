"""iteration 服务层."""

from __future__ import annotations

from .job_store import IterationJobStore
from .models import IterationJob, ModelEvaluation
from .queue import IterationQueue
from .worker import IterationWorker


class IterationService:
    """给 API/CLI 提供稳定入口."""

    def __init__(
        self,
        job_store: IterationJobStore,
        queue: IterationQueue,
        worker: IterationWorker,
    ) -> None:
        self.job_store = job_store
        self.queue = queue
        self.worker = worker

    async def enqueue_job(
        self,
        action_id: str,
        baseline: ModelEvaluation,
        candidate: ModelEvaluation,
        trigger_reason: str,
    ) -> IterationJob:
        """创建任务并入队."""
        job = self.job_store.create_job(
            action_id=action_id,
            baseline=baseline,
            candidate=candidate,
            trigger_reason=trigger_reason,
        )
        await self.queue.enqueue(job.job_id)
        return job

    def get_job(self, job_id: str) -> IterationJob | None:
        """查询任务."""
        return self.job_store.get_job(job_id)

    async def run_once(self) -> IterationJob | None:
        """执行一个队列任务."""
        return await self.worker.run_once()
