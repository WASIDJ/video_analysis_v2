"""API端点定义."""
import time
from typing import Dict, List

from fastapi import APIRouter, BackgroundTasks, HTTPException

from config import get_settings
from ..core.iteration import EvaluationSampleResult, ModelEvaluation, get_iteration_runtime
from .schemas import (
    AnalysisParams,
    TaskRequest,
    TaskResponse,
    TaskStatusResponse,
    VideoResult,
    QuestionRequest,
    QuestionResponse,
    IterationJobRequest,
    IterationJobResponse,
)

router = APIRouter()

# 任务状态存储（内存中，生产环境应使用Redis）
task_storage: Dict[str, Dict] = {}


@router.post("/analyze/task", response_model=TaskResponse)
async def create_analysis_task(
    request: TaskRequest,
    background_tasks: BackgroundTasks,
) -> TaskResponse:
    """创建视频分析任务.

    接收任务信息，异步处理视频分析.
    """
    task_id = str(request.task_id)

    # 初始化任务状态
    task_storage[task_id] = {
        "task_id": task_id,
        "status": "accepted",
        "message": "任务已接受并开始处理",
        "results": [],
        "error_msg": "",
        "created_at": time.time(),
    }

    # 后台处理
    background_tasks.add_task(
        process_analysis_task,
        task_id,
        request.analysis_params,
    )

    return TaskResponse(
        task_id=request.task_id,
        status="accepted",
        message="任务已接受并开始处理",
    )


@router.get("/analyze/task/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    """获取任务状态."""
    task = task_storage.get(task_id)

    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return TaskStatusResponse(
        task_id=task_id,
        status=task.get("status", "unknown"),
        results=task.get("results", []),
        error_msg=task.get("error_msg", ""),
    )


@router.post("/generate/question", response_model=QuestionResponse)
async def generate_questions(request: QuestionRequest) -> QuestionResponse:
    """生成问卷问题."""
    questions = []

    # 基于检测项生成问题
    metric_to_questions = {
        "knee_valgus": {
            "question": "深蹲时是否出现膝关节内扣？",
            "options": ["无", "轻微", "明显"],
        },
        "trunk_lean": {
            "question": "深蹲时躯干前倾程度如何？",
            "options": ["直立", "适度前倾", "过度前倾"],
        },
        "lumbar_curvature": {
            "question": "动作过程中是否出现塌腰？",
            "options": ["无", "轻微", "明显"],
        },
        "shoulder_lift_ratio": {
            "question": "动作过程中是否耸肩？",
            "options": ["无", "轻微", "明显"],
        },
    }

    for metric_id in request.metrics:
        if metric_id in metric_to_questions:
            questions.append({
                "metric_id": metric_id,
                **metric_to_questions[metric_id],
            })

    return QuestionResponse(questions=questions)


@router.post("/iteration/jobs", response_model=IterationJobResponse, status_code=202)
async def create_iteration_job(
    request: IterationJobRequest,
) -> IterationJobResponse:
    """创建并入队一个 iteration 任务."""
    runtime = get_iteration_runtime()
    service = runtime.service

    baseline = _to_model_evaluation(request.baseline)
    candidate = _to_model_evaluation(request.candidate)
    job = await service.enqueue_job(
        action_id=request.action_id,
        baseline=baseline,
        candidate=candidate,
        trigger_reason=request.trigger_reason,
    )
    return _to_iteration_job_response(job)


@router.get("/iteration/jobs/{job_id}", response_model=IterationJobResponse)
async def get_iteration_job(job_id: str) -> IterationJobResponse:
    """查询 iteration 任务状态."""
    runtime = get_iteration_runtime()
    job = runtime.service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="迭代任务不存在")
    return _to_iteration_job_response(job)


async def process_analysis_task(
    task_id: str,
    analysis_params: AnalysisParams,
) -> None:
    """后台处理分析任务."""
    task = task_storage.get(task_id)
    if not task:
        return

    settings = get_settings()
    results = []

    try:
        task["status"] = "processing"

        # 创建处理器
        from ..core.pipeline.video_processor import VideoProcessor
        processor = VideoProcessor(settings)

        # 处理每个视频
        for video_info in analysis_params.video_infos:
            try:
                result = await processor.process_video(
                    video_url=video_info.video_url,
                    action_name=video_info.actionName,
                )

                # 转换为响应格式
                video_result = VideoResult(
                    video_path=video_info.video_url,
                    optimal_combination=[m.metric_id for m in result.metrics[:5]],
                    combination_score=0.85,  # 简化处理
                    metric_details={
                        "num_frames": result.num_frames,
                        "pose_model": result.pose_model,
                        "detected_errors": result.detected_errors,
                    },
                )
                results.append(video_result)

            except Exception as e:
                results.append(VideoResult(
                    video_path=video_info.video_url,
                    error_msg=str(e),
                ))

        task["status"] = "completed"
        task["results"] = results

    except Exception as e:
        task["status"] = "failed"
        task["error_msg"] = str(e)


@router.get("/health")
async def health_check() -> Dict[str, str]:
    """健康检查."""
    return {"status": "healthy", "version": "2.0.0"}


def _to_model_evaluation(payload) -> ModelEvaluation:
    """把 API payload 转成域模型."""
    return ModelEvaluation(
        version_id=payload.version_id,
        action_id=payload.action_id,
        overall_score=payload.overall_score,
        metric_scores=payload.metric_scores,
        sample_results=[
            EvaluationSampleResult(
                sample_id=item.sample_id,
                confidence=item.confidence,
                predicted_label=item.predicted_label,
                expected_label=item.expected_label,
                source_version=item.source_version,
                split=item.split,
            )
            for item in payload.sample_results
        ],
        dataset_version=payload.dataset_version,
        config_version=payload.config_version,
    )


def _to_iteration_job_response(job) -> IterationJobResponse:
    """把任务对象转换为 API 响应."""
    return IterationJobResponse(
        job_id=job.job_id,
        action_id=job.action_id,
        status=job.status.value,
        trigger_reason=job.trigger_reason or "",
        retry_count=job.retry_count,
        last_error=job.last_error,
        baseline_version=job.baseline_version,
        candidate_version=job.candidate_version,
    )
