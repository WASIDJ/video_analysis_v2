"""iteration API 集成测试."""

import httpx
import pytest
from fastapi import HTTPException

from src.api.endpoints import create_iteration_job, get_iteration_job
from src.api.main import app
from src.api.schemas import IterationJobRequest, ModelEvaluationPayload
from src.core.iteration import reset_iteration_runtime


def build_request() -> IterationJobRequest:
    """构造测试请求."""
    return IterationJobRequest(
        action_id="squat",
        trigger_reason="manual",
        baseline=ModelEvaluationPayload(
            version_id="baseline-v1",
            action_id="squat",
            overall_score=0.8,
            metric_scores={"f1": 0.8},
            sample_results=[],
            dataset_version="dataset-v1",
            config_version="config-v1",
        ),
        candidate=ModelEvaluationPayload(
            version_id="candidate-v2",
            action_id="squat",
            overall_score=0.88,
            metric_scores={"f1": 0.88},
            sample_results=[],
            dataset_version="dataset-v1",
            config_version="config-v2",
        ),
    )


class TestIterationApi:
    """测试 iteration API handler."""

    @pytest.fixture(autouse=True)
    def isolate_runtime(self, monkeypatch, tmp_path):
        """隔离 runtime 持久化目录."""
        monkeypatch.setenv("ITERATION_RUNTIME_DIR", str(tmp_path / "runtime"))
        reset_iteration_runtime()
        yield
        reset_iteration_runtime()

    async def test_create_iteration_job_returns_pending_job_payload(self):
        """创建任务应返回 pending 状态的 payload."""
        response = await create_iteration_job(build_request())

        assert response.job_id
        assert response.action_id == "squat"
        assert response.status == "pending"
        assert response.trigger_reason == "manual"

    async def test_http_asgi_post_and_get_iteration_job(self):
        """应能通过 ASGI 发送真实 HTTP 请求创建并查询任务."""
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            created = await client.post("/api/v2/iteration/jobs", json=build_request().model_dump())

            assert created.status_code == 202
            created_payload = created.json()
            assert created_payload["status"] == "pending"

            fetched = await client.get(f"/api/v2/iteration/jobs/{created_payload['job_id']}")

            assert fetched.status_code == 200
            assert fetched.json()["job_id"] == created_payload["job_id"]

    async def test_get_iteration_job_returns_existing_job(self):
        """查询已创建任务应返回相同 job."""
        created = await create_iteration_job(build_request())

        response = await get_iteration_job(created.job_id)

        assert response.job_id == created.job_id
        assert response.status in {"pending", "running", "succeeded"}

    async def test_get_iteration_job_raises_404_for_unknown_job(self):
        """查询不存在任务应返回 404."""
        try:
            await get_iteration_job("missing-job")
        except HTTPException as error:
            assert error.status_code == 404
            assert error.detail == "迭代任务不存在"
        else:
            raise AssertionError("Expected HTTPException for missing iteration job")
