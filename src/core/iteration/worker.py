"""异步 iteration worker."""

from __future__ import annotations

from collections.abc import Callable
import inspect

from .evaluator import UnifiedEvaluator
from .job_store import IterationJobStore
from .models import IterationJob, RetryPolicy
from .orchestrator import IterationOrchestrator
from .queue import IterationQueue
from .state_machine import IterationStateMachine
from .versioning import VersionStore
from ..dataset.feedback_loop import FeedbackLoop


class IterationWorker:
    """消费 queue 中的迭代任务."""

    def __init__(
        self,
        queue: IterationQueue,
        job_store: IterationJobStore,
        version_store: VersionStore,
        feedback_loop: FeedbackLoop,
        retry_policy: RetryPolicy,
        execution_handler: Callable[[IterationJob], object] | None = None,
    ) -> None:
        self.queue = queue
        self.job_store = job_store
        self.version_store = version_store
        self.feedback_loop = feedback_loop
        self.state_machine = IterationStateMachine(retry_policy=retry_policy)
        self.execution_handler = execution_handler
        self.orchestrator = IterationOrchestrator(
            evaluator=UnifiedEvaluator(low_confidence_threshold=feedback_loop.low_confidence_threshold),
            version_store=version_store,
            feedback_loop=feedback_loop,
        )

    async def run_once(self) -> IterationJob | None:
        """处理一个任务."""
        job_id = self.queue.dequeue_nowait()
        if job_id is None:
            return None

        job = self.job_store.require_job(job_id)
        self.state_machine.start(job)
        self.job_store.update_job(job)

        try:
            await self._execute(job)
            self.state_machine.succeed(job)
        except Exception as error:
            self.state_machine.fail(job, str(error), retryable=True)
            if job.status.value == "pending":
                await self.queue.enqueue(job.job_id)

        self.job_store.update_job(job)
        return job

    async def run_until_empty(self) -> None:
        """处理直到队列为空."""
        while self.queue.size() > 0:
            await self.run_once()

    async def _execute(self, job: IterationJob) -> object:
        self._ensure_versions(job)

        if self.execution_handler is not None:
            result = self.execution_handler(job)
            if inspect.isawaitable(result):
                return await result
            return result

        return self.orchestrator.process_candidate(
            action_id=job.action_id,
            baseline=job.baseline,
            candidate=job.candidate,
        )

    def _ensure_versions(self, job: IterationJob) -> None:
        if job.baseline and self.version_store.get_version(job.action_id, job.baseline.version_id) is None:
            self.version_store.register_version(
                action_id=job.action_id,
                version_id=job.baseline.version_id,
                dataset_version=job.baseline.dataset_version,
                config_version=job.baseline.config_version,
                metrics=job.baseline.metric_scores,
                status="baseline",
            )
        if job.candidate and self.version_store.get_version(job.action_id, job.candidate.version_id) is None:
            self.version_store.register_version(
                action_id=job.action_id,
                version_id=job.candidate.version_id,
                dataset_version=job.candidate.dataset_version,
                config_version=job.candidate.config_version,
                metrics=job.candidate.metric_scores,
                status="candidate",
                parent_version=job.baseline.version_id if job.baseline else None,
            )
