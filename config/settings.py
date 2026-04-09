"""Pydantic Settings 配置管理."""
import os
from pathlib import Path
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class PoseEstimationConfig(BaseSettings):
    """姿态估计模型配置."""

    model_config = SettingsConfigDict(env_prefix="POSE_")

    # 默认使用 BlazePose，可选 yolo
    model_type: str = Field(default="blazepose", description="姿态估计模型类型")

    # BlazePose 配置
    blazepose_complexity: int = Field(default=2, ge=0, le=2, description="BlazePose复杂度 (0/1/2)")
    blazepose_min_detection_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    blazepose_min_tracking_confidence: float = Field(default=0.5, ge=0.0, le=1.0)

    # YOLO 配置
    yolo_model_path: str = Field(default="yolov8m-pose.pt", description="YOLO模型路径")
    yolo_conf: float = Field(default=0.5, ge=0.0, le=1.0)
    yolo_iou: float = Field(default=0.5, ge=0.0, le=1.0)


class SegmentationConfig(BaseSettings):
    """人体分割配置."""

    model_config = SettingsConfigDict(env_prefix="SEGMENT_")

    enabled: bool = Field(default=True, description="是否启用体块分割")
    model_type: str = Field(default="selfie_segmentation", description="分割模型类型")
    model_complexity: int = Field(default=1, ge=0, le=1)


class VideoProcessingConfig(BaseSettings):
    """视频处理配置."""

    model_config = SettingsConfigDict(env_prefix="VIDEO_")

    # 输入输出
    temp_dir: Path = Field(default=Path("./temp_videos"))
    output_dir: Path = Field(default=Path("./output"))

    # 处理参数
    target_fps: Optional[float] = Field(default=None, description="目标帧率（None表示原始帧率）")
    max_resolution: Optional[int] = Field(default=1080, description="最大分辨率")

    # 鲁棒性处理
    outlier_method: str = Field(default="iqr", description="异常值处理方法: iqr/zscore/none")
    outlier_threshold: float = Field(default=1.5, description="IQR异常值阈值")
    smooth_window: int = Field(default=5, ge=1, description="平滑窗口大小")

    # 旋转检测
    auto_rotate: bool = Field(default=True, description="自动检测并校正视频旋转")

    @field_validator("temp_dir", "output_dir", mode="before")
    @classmethod
    def ensure_path(cls, v: str | Path) -> Path:
        """确保路径是Path对象并创建目录."""
        path = Path(v)
        path.mkdir(parents=True, exist_ok=True)
        return path


class MetricsConfig(BaseSettings):
    """检测项配置."""

    model_config = SettingsConfigDict(env_prefix="METRICS_")

    # 检测项筛选参数（保留与原系统兼容）
    min_metrics: int = Field(default=3, ge=1, description="最少选择检测项数")
    max_metrics: int = Field(default=7, ge=1, le=20, description="最多选择检测项数")
    gain_threshold: float = Field(default=0.05, description="信息增益阈值")

    # 置信度阈值
    min_keypoint_confidence: float = Field(default=0.3, ge=0.0, le=1.0)

    # 默认启用的检测项类别
    enabled_categories: List[str] = Field(
        default=["joint_angle", "position", "segment", "stability"],
        description="启用的检测项类别"
    )


class CloudConfig(BaseSettings):
    """云端配置."""

    model_config = SettingsConfigDict(env_prefix="CLOUD_")

    enabled: bool = Field(default=True, description="是否启用云端上传")
    base_url: str = Field(default="http://14.103.141.203:48080")
    api_path: str = Field(default="/app-api/infra/file/plus/presigned-url")
    file_type: int = Field(default=3, description="业务类型")
    timeout: int = Field(default=300, description="上传超时秒数")


class APIConfig(BaseSettings):
    """API服务配置."""

    model_config = SettingsConfigDict(env_prefix="API_")

    host: str = Field(default="0.0.0.0")
    port: int = Field(default=8000, ge=1, le=65535)
    workers: int = Field(default=1, ge=1)
    reload: bool = Field(default=False, description="开发模式热重载")

    # CORS
    cors_origins: List[str] = Field(default=["*"])
    cors_credentials: bool = Field(default=True)
    cors_methods: List[str] = Field(default=["*"])
    cors_headers: List[str] = Field(default=["*"])


class Settings(BaseSettings):
    """全局配置."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # 忽略未定义的环境变量
    )

    # 应用信息
    app_name: str = Field(default="Video Analysis V2")
    app_version: str = Field(default="0.1.0")
    debug: bool = Field(default=False)

    # 子配置
    pose: PoseEstimationConfig = Field(default_factory=PoseEstimationConfig)
    segment: SegmentationConfig = Field(default_factory=SegmentationConfig)
    video: VideoProcessingConfig = Field(default_factory=VideoProcessingConfig)
    metrics: MetricsConfig = Field(default_factory=MetricsConfig)
    cloud: CloudConfig = Field(default_factory=CloudConfig)
    api: APIConfig = Field(default_factory=APIConfig)


# 全局配置单例
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """获取全局配置单例."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings


def reload_settings() -> Settings:
    """重新加载配置."""
    global _settings
    _settings = Settings()
    return _settings
