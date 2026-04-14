"""迭代状态机单元测试."""

from src.core.iteration.models import IterationJob, IterationStatus, RetryPolicy
from src.core.iteration.state_machine import IterationStateMachine


class TestIterationStateMachine:
    """测试迭代任务状态机."""

    def test_pending_job_can_transition_to_running(self):
        """pending 任务应能启动到 running."""
        job = IterationJob(job_id="job-001", action_id="squat")
        machine = IterationStateMachine(retry_policy=RetryPolicy(max_retries=2))

        machine.start(job)

        assert job.status is IterationStatus.RUNNING
        assert job.started_at is not None

    def test_running_job_retries_until_max_retries_then_fails(self):
        """running 任务在超过最大重试次数前应回到 pending，之后进入 failed."""
        job = IterationJob(job_id="job-001", action_id="squat", status=IterationStatus.RUNNING)
        machine = IterationStateMachine(retry_policy=RetryPolicy(max_retries=2))

        machine.fail(job, "temporary error", retryable=True)
        assert job.status is IterationStatus.PENDING
        assert job.retry_count == 1

        machine.start(job)
        machine.fail(job, "temporary error", retryable=True)
        assert job.status is IterationStatus.PENDING
        assert job.retry_count == 2

        machine.start(job)
        machine.fail(job, "permanent error", retryable=True)
        assert job.status is IterationStatus.FAILED
        assert job.last_error == "permanent error"
        assert job.finished_at is not None

    def test_running_job_can_be_cancelled(self):
        """running 任务应能转为 cancelled."""
        job = IterationJob(job_id="job-001", action_id="squat", status=IterationStatus.RUNNING)
        machine = IterationStateMachine(retry_policy=RetryPolicy(max_retries=1))

        machine.cancel(job)

        assert job.status is IterationStatus.CANCELLED
        assert job.finished_at is not None

