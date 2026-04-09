"""视频处理管道.

整合姿态估计、特征提取、检测项计算的完整流程.
"""
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

import numpy as np
import aiohttp
import aiofiles

from config.settings import Settings
from src.core.models.base import BasePoseEstimator, PoseSequence, create_pose_estimator
from src.core.features.skeleton_features import SkeletonFeatureExtractor
from src.core.features.segment_features import SegmentFeatureExtractor
from src.core.metrics.calculator import MetricsCalculator
from src.core.metrics.templates import get_metrics_for_action
from src.core.metrics.definitions import METRIC_TEMPLATES
from src.utils.video import VideoFrameIterator


class VideoProcessor:
    """视频处理器.

    完整的视频分析流程：
    1. 视频下载/加载
    2. 姿态估计
    3. 特征提取（骨骼+体块）
    4. 检测项计算
    5. 结果格式化
    """

    def __init__(self, settings: Settings):
        """
        Args:
            settings: 应用配置
        """
        self.settings = settings

        # 初始化姿态估计器
        self.pose_estimator = create_pose_estimator(
            settings.pose.model_type,
            min_pose_detection_confidence=settings.pose.blazepose_min_detection_confidence,
            min_tracking_confidence=settings.pose.blazepose_min_tracking_confidence,
        )

        # 初始化特征提取器
        self.skeleton_extractor = SkeletonFeatureExtractor(
            use_3d=False,
            min_confidence=settings.metrics.min_keypoint_confidence,
        )

        self.segment_extractor = None
        if settings.segment.enabled:
            self.segment_extractor = SegmentFeatureExtractor(
                model_type=settings.segment.model_type,
            )

        # 初始化检测项计算器
        self.metrics_calculator = MetricsCalculator(
            min_confidence=settings.metrics.min_keypoint_confidence,
        )

    async def process_video(
        self,
        video_url: str,
        action_name: str = "squat",
    ) -> "VideoAnalysisResult":
        """处理单个视频.

        Args:
            video_url: 视频URL或本地路径
            action_name: 动作名称（用于选择检测项模板）

        Returns:
            分析结果
        """
        start_time = time.time()

        # 1. 下载/获取视频
        video_path = await self._get_video(video_url)

        try:
            # 2. 姿态估计
            pose_sequence = self._estimate_pose(video_path)

            if len(pose_sequence) == 0:
                raise ValueError("未检测到姿态")

            # 3. 特征提取
            # 3.1 骨骼特征
            skeleton_features = self.skeleton_extractor.extract(pose_sequence)

            # 3.2 体块特征（如果需要）
            segment_features_dict = {}
            if self.segment_extractor and self.settings.segment.enabled:
                # 读取视频帧用于分割
                video_frames = self._extract_video_frames(video_path)
                segment_feature_sets = self.segment_extractor.extract(
                    pose_sequence, video_frames
                )
                segment_features_dict = {
                    fs.name: fs.values for fs in segment_feature_sets
                }

            # 4. 检测项计算（使用动作阶段检测）
            metric_ids = get_metrics_for_action(action_name)
            if not metric_ids:
                # 使用默认检测项
                metric_ids = list(METRIC_TEMPLATES.keys())[:7]

            metrics_results = self.metrics_calculator.calculate_all_metrics(
                pose_sequence,
                metric_ids=metric_ids,
                segment_features=segment_features_dict,
                action_name=action_name,  # 传入动作名称以启用阶段检测
            )

            # 5. 格式化结果
            from ...api.schemas import MetricResult, VideoAnalysisResult

            metrics_list = []
            for metric_id, result in metrics_results.items():
                if "error" not in result:
                    metrics_list.append(MetricResult(**result))

            # 收集所有检测到的错误
            detected_errors = []
            for metric in metrics_list:
                for error in metric.errors:
                    detected_errors.append({
                        "metric_id": metric.metric_id,
                        "metric_name": metric.name,
                        **error,
                    })

            processing_time = time.time() - start_time

            return VideoAnalysisResult(
                video_path=video_url,
                action_name=action_name,
                pose_model=self.pose_estimator.model_name,
                num_frames=len(pose_sequence),
                metrics=metrics_list,
                segment_metrics=[],  # 简化处理
                detected_errors=detected_errors,
                processing_time=processing_time,
            )

        finally:
            # 清理临时文件
            if video_url.startswith(("http://", "https://")):
                # 删除下载的临时文件
                temp_path = Path(video_path)
                if temp_path.exists():
                    temp_path.unlink()

    async def _get_video(self, video_url: str) -> str:
        """获取视频文件.

        如果是URL则下载，如果是本地路径则直接返回.
        """
        if video_url.startswith(("http://", "https://")):
            # 下载视频
            return await self._download_video(video_url)
        elif Path(video_url).exists():
            return video_url
        else:
            raise FileNotFoundError(f"视频不存在: {video_url}")

    async def _download_video(self, url: str) -> str:
        """下载视频到临时目录."""
        import tempfile
        import uuid

        temp_dir = Path(self.settings.video.temp_dir)
        temp_dir.mkdir(parents=True, exist_ok=True)

        filename = f"temp_{uuid.uuid4().hex[:8]}.mp4"
        temp_path = temp_dir / filename

        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status != 200:
                    raise ValueError(f"下载失败: {response.status}")

                async with aiofiles.open(temp_path, "wb") as f:
                    async for chunk in response.content.iter_chunked(8192):
                        await f.write(chunk)

        return str(temp_path)

    def _estimate_pose(self, video_path: str) -> PoseSequence:
        """执行姿态估计."""
        return self.pose_estimator.process_video(
            video_path,
            target_fps=self.settings.video.target_fps,
        )

    def _extract_video_frames(self, video_path: str) -> List[np.ndarray]:
        """提取视频帧列表."""
        frames = []
        with VideoFrameIterator(
            video_path,
            target_fps=self.settings.video.target_fps,
            auto_rotate=self.settings.video.auto_rotate,
        ) as iterator:
            for _, frame in iterator:
                frames.append(frame)
        return frames
