"""异步迭代 worker 单元测试."""

from src.core.iteration.job_store import IterationJobStore
from src.core.iteration.models import ModelEvaluation, RetryPolicy
from src.core.iteration.queue import IterationQueue
from src.core.iteration.versioning import VersionStore
from src.core.iteration.worker import IterationWorker
from src.core.dataset.feedback_loop import FeedbackLoop
from src.core.dataset.models import VideoSample
from src.core.dataset.repository import DatasetRepository


def make_evaluation(version_id: str, overall_score: float) -> ModelEvaluation:
    """构造测试评估结果."""
    return ModelEvaluation(
        version_id=version_id,
        action_id="squat",
        overall_score=overall_score,
        metric_scores={"f1": overall_score},
        sample_results=[],
        dataset_version="dataset-v1",
        config_version=f"config-{version_id}",
    )


class TestIterationWorker:
    """测试异步 worker."""

    async def test_worker_processes_enqueued_job_to_success(self, tmp_path):
        """worker 应消费队列任务并将成功结果写回 store."""
        repository = DatasetRepository()
        repository.add_sample(VideoSample("sample-001", "squat", "standard", "/tmp/sample.mp4"))
        version_store = VersionStore(tmp_path / "versions.json")
        version_store.register_version("squat", "baseline-v1", "dataset-v1", "config-v1", {"f1": 0.80}, status="baseline")
        version_store.register_version("squat", "candidate-v2", "dataset-v1", "config-v2", {"f1": 0.88}, status="candidate")
        queue = IterationQueue()
        store = IterationJobStore()
        worker = IterationWorker(
            queue=queue,
            job_store=store,
            version_store=version_store,
            feedback_loop=FeedbackLoop(repository),
            retry_policy=RetryPolicy(max_retries=1),
        )

        job = store.create_job(
            action_id="squat",
            baseline=make_evaluation("baseline-v1", 0.80),
            candidate=make_evaluation("candidate-v2", 0.88),
            trigger_reason="manual",
        )
        await queue.enqueue(job.job_id)

        await worker.run_once()

        updated = store.require_job(job.job_id)
        assert updated.status.value == "succeeded"
        assert version_store.get_active_version("squat").version_id == "candidate-v2"

    async def test_worker_requeues_retryable_failure(self, tmp_path):
        """可重试失败应把任务放回 pending."""
        queue = IterationQueue()
        store = IterationJobStore()
        repository = DatasetRepository()
        version_store = VersionStore(tmp_path / "versions.json")
        version_store.register_version("squat", "baseline-v1", "dataset-v1", "config-v1", {"f1": 0.80}, status="baseline")

        worker = IterationWorker(
            queue=queue,
            job_store=store,
            version_store=version_store,
            feedback_loop=FeedbackLoop(repository),
            retry_policy=RetryPolicy(max_retries=1),
            execution_handler=lambda job: (_ for _ in ()).throw(RuntimeError("boom")),
        )

        job = store.create_job(
            action_id="squat",
            baseline=make_evaluation("baseline-v1", 0.80),
            candidate=make_evaluation("baseline-v1", 0.80),
            trigger_reason="manual",
        )
        await queue.enqueue(job.job_id)

        await worker.run_once()

        updated = store.require_job(job.job_id)
        assert updated.status.value == "pending"
        assert updated.retry_count == 1

