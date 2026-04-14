"""iteration runtime 单例."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from .job_store import IterationJobStore
from .models import RetryPolicy
from .queue import IterationQueue
from .service import IterationService
from .versioning import VersionStore
from .worker import IterationWorker
from ..dataset.feedback_loop import FeedbackLoop
from ..dataset.repository import DatasetRepository


@dataclass
class IterationRuntime:
    """执行面依赖集合."""

    job_store: IterationJobStore
    queue: IterationQueue
    repository: DatasetRepository
    version_store: VersionStore
    worker: IterationWorker
    service: IterationService


_runtime: IterationRuntime | None = None


def get_iteration_runtime(base_dir: str | Path = "data") -> IterationRuntime:
    """获取 runtime 单例."""
    global _runtime
    if _runtime is None:
        base_path = Path(os.getenv("ITERATION_RUNTIME_DIR", str(base_dir)))
        repository = DatasetRepository(storage_path=base_path / "dataset_repository.json")
        queue = IterationQueue()
        version_store = VersionStore(base_path / "version_store.json")
        job_store = IterationJobStore(base_path / "iteration_jobs.json")
        worker = IterationWorker(
            queue=queue,
            job_store=job_store,
            version_store=version_store,
            feedback_loop=FeedbackLoop(repository),
            retry_policy=RetryPolicy(max_retries=1),
        )
        service = IterationService(job_store=job_store, queue=queue, worker=worker)
        _runtime = IterationRuntime(job_store, queue, repository, version_store, worker, service)
    return _runtime


def reset_iteration_runtime() -> None:
    """重置 runtime 单例，主要用于测试."""
    global _runtime
    _runtime = None
