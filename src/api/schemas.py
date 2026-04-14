"""API数据模型.

保持与原系统兼容的Pydantic模型定义.
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ========== 请求模型 ==========

class VideoInfo(BaseModel):
    """视频信息."""
    video_url: str = Field(..., description="视频URL或本地路径")
    actionEvaluation: str = Field("correct", description="动作评估类型")
    actionName: str = Field("squat", description="动作名称")


class MetricDetails(BaseModel):
    """检测项详情."""
    taskStage: str = Field("analysis", description="任务阶段")
    stageCode: int = Field(1, description="阶段代码")
    description: Optional[str] = Field(None, description="描述")


class AnalysisParams(BaseModel):
    """分析参数."""
    video_infos: List[VideoInfo] = Field(..., description="视频列表")
    metric_details: MetricDetails = Field(default_factory=MetricDetails, description="任务详情")
    analysis_type: str = Field("videoAnalysis", description="分析类型")


class TaskRequest(BaseModel):
    """任务创建请求."""
    analysis_params: AnalysisParams
    task_id: int


# ========== 响应模型 ==========

class TaskResponse(BaseModel):
    """任务创建响应."""
    task_id: int
    status: str
    message: str


class VideoResult(BaseModel):
    """单视频分析结果."""
    video_path: str
    optimal_combination: List[str] = Field(default_factory=list)
    combination_score: float = 0.0
    metric_details: Dict[str, Any] = Field(default_factory=dict)
    results_path: Optional[str] = None
    visualization_path: Optional[str] = None


class TaskStatusResponse(BaseModel):
    """任务状态响应."""
    task_id: str
    status: str  # pending/processing/completed/failed
    results: List[VideoResult] = Field(default_factory=list)
    error_msg: str = ""


class MetricResult(BaseModel):
    """单个检测项结果."""
    metric_id: str
    name: str
    description: str
    category: str
    unit: str
    values: List[float]
    statistics: Dict[str, Any]
    errors: List[Dict[str, Any]]


class VideoAnalysisResult(BaseModel):
    """视频分析完整结果（内部使用）."""
    video_path: str
    action_name: str
    pose_model: str
    num_frames: int
    metrics: List[MetricResult]
    segment_metrics: List[MetricResult]
    detected_errors: List[Dict[str, Any]]
    processing_time: float


# ========== 问卷生成模型 ==========

class QuestionRequest(BaseModel):
    """问题生成请求."""
    metrics: List[str] = Field(default_factory=list)
    action_type: str = "general"


class QuestionResponse(BaseModel):
    """问题生成响应."""
    questions: List[Dict[str, Any]] = Field(default_factory=list)


class EvaluationSamplePayload(BaseModel):
    """单个样本评估负载."""
    sample_id: str
    confidence: float
    predicted_label: str
    expected_label: str
    source_version: str
    split: str = "test"


class ModelEvaluationPayload(BaseModel):
    """模型评估负载."""
    version_id: str
    action_id: str
    overall_score: float
    metric_scores: Dict[str, float]
    sample_results: List[EvaluationSamplePayload] = Field(default_factory=list)
    dataset_version: str
    config_version: str


class IterationJobRequest(BaseModel):
    """创建迭代任务请求."""
    action_id: str
    trigger_reason: str = "manual"
    baseline: ModelEvaluationPayload
    candidate: ModelEvaluationPayload


class IterationJobResponse(BaseModel):
    """迭代任务响应."""
    job_id: str
    action_id: str
    status: str
    trigger_reason: str
    retry_count: int = 0
    last_error: Optional[str] = None
    baseline_version: Optional[str] = None
    candidate_version: Optional[str] = None
