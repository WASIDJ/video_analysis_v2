"""训练流程管道.

连接所有训练步骤，提供完整的训练流程.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path
import json
from datetime import datetime

from src.core.models.base import PoseSequence
from src.core.pipeline.video_processor import VideoProcessor
from src.core.analysis.fingerprint import FingerprintAnalyzer, ActionFingerprint
from src.core.analysis.exploration import ExplorationAnalyzer
from src.core.analysis.template_generator import TemplateGenerator
from src.core.config.manager import ConfigManager
from src.core.config.models import ActionConfig, ErrorCondition


@dataclass
class VideoTrainingConfig:
    """单个视频的训练配置."""
    video_path: str
    tags: List[str] = field(default_factory=list)  # ["standard"], ["error:knee_valgus"], etc.
    metadata: Dict[str, Any] = field(default_factory=dict)


from config.settings import Settings

class TrainingPipeline:
    """训练流程管道.

    完整的训练流程:
    1. 视频处理 -> 姿态序列
    2. 指纹提取 -> ActionFingerprint
    3. 存储到数据库
    4. 聚合生成配置
    """

    def __init__(
        self,
        video_processor: Optional[VideoProcessor] = None,
        fingerprint_db_path: str = "data/fingerprints",
    ):
        """
        Args:
            video_processor: 视频处理器
            fingerprint_db_path: 指纹数据库存储路径
        """
        self.video_processor = video_processor or VideoProcessor(Settings())
        self.fingerprint_analyzer = FingerprintAnalyzer()
        self.exploration_analyzer = ExplorationAnalyzer()
        self.template_generator = TemplateGenerator()

        # 初始化指纹数据库
        from src.core.analysis.fingerprint import FingerprintDatabase
        self.db = FingerprintDatabase(db_path=fingerprint_db_path)

    def process_video(self, config: VideoTrainingConfig) -> Dict[str, Any]:
        """处理单个视频.

        Args:
            config: 视频训练配置

        Returns:
            处理结果
        """
        try:
            # 1. 处理视频获取姿态序列
            pose_sequence = self.video_processor.pose_estimator.process_video(config.video_path)

            if not pose_sequence or len(pose_sequence) == 0:
                return {
                    "success": False,
                    "error": "视频处理失败：未能提取姿态",
                }

            # 2. 分析指纹
            fingerprint = self.fingerprint_analyzer.analyze(
                pose_sequence=pose_sequence,
                action_name=Path(config.video_path).stem,
                video_metadata={
                    "video_path": config.video_path,
                    **config.metadata,
                },
                tags=config.tags,
            )

            # 3. 确定标签
            label = self._determine_label(config.tags)

            # 4. 存储到数据库
            self.db.add_fingerprint(fingerprint, label=label)
            self.db.save_to_disk()

            return {
                "success": True,
                "fingerprint": fingerprint,
                "label": label,
                "metrics_analyzed": fingerprint.total_metrics_analyzed,
                "dominant_metrics": [m.metric_id for m in fingerprint.dominant_metrics],
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }

    def _determine_label(self, tags: List[str]) -> str:
        """从标签列表确定主标签."""
        if "standard" in tags:
            return "standard"
        for tag in tags:
            if tag.startswith("error:"):
                return tag
        return "unknown"

    def generate_production_config(
        self,
        action_id: str,
        action_name_zh: str,
        standard_fingerprints: List[ActionFingerprint],
        error_conditions: Dict[str, List[ErrorCondition]],
        output_dir: str = "config/action_configs",
    ) -> Dict[str, Any]:
        """生成生产环境配置.

        Args:
            action_id: 动作ID
            action_name_zh: 中文名称
            standard_fingerprints: 标准动作指纹列表
            error_conditions: 错误类型到条件列表的映射
            output_dir: 输出目录

        Returns:
            配置生成结果
        """
        if not standard_fingerprints:
            return {
                "success": False,
                "error": "没有标准动作指纹",
            }

        # 1. 创建基础配置
        base_config = self._create_base_config(
            action_id, action_name_zh, standard_fingerprints
        )

        # 2. 添加错误条件
        for error_type, conditions in error_conditions.items():
            for condition in conditions:
                metric_id = condition.condition.get("metric_id")
                if metric_id:
                    self._add_error_condition_to_config(
                        base_config, metric_id, condition
                    )

        # 3. 计算配置置信度
        confidence = self._calculate_config_confidence(
            len(standard_fingerprints),
            error_conditions,
        )

        # 4. 添加元数据
        base_config.metadata["training_info"] = {
            "trained_at": datetime.now().isoformat(),
            "standard_samples": len(standard_fingerprints),
            "error_types": list(error_conditions.keys()),
            "total_error_conditions": sum(len(c) for c in error_conditions.values()),
            "confidence": confidence,
        }

        # 5. 保存配置
        output_path = Path(output_dir) / f"{action_id}_trained.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(base_config.to_dict(), f, indent=2, ensure_ascii=False)

            return {
                "success": True,
                "config_path": str(output_path),
                "action_id": action_id,
                "confidence": confidence,
                "error_conditions": {
                    et: len(ec) for et, ec in error_conditions.items()
                },
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"保存配置失败: {e}",
            }

    def _create_base_config(
        self,
        action_id: str,
        action_name_zh: str,
        fingerprints: List[ActionFingerprint],
    ) -> ActionConfig:
        """从指纹创建基础配置."""
        # 聚合所有指纹的指标
        metric_stats = self._aggregate_metric_stats(fingerprints)

        # 生成检测项配置
        metrics = []
        for metric_id, stats in metric_stats.items():
            from src.core.config.models import MetricConfig, MetricThreshold

            # 基于统计生成阈值
            thresholds = MetricThreshold(
                target_value=round(stats["mean"], 2),
                normal_range=(
                    round(stats["mean"] - stats["std"], 2),
                    round(stats["mean"] + stats["std"], 2)
                ),
                excellent_range=(
                    round(stats["mean"] - 0.5 * stats["std"], 2),
                    round(stats["mean"] + 0.5 * stats["std"], 2)
                ),
                pass_range=(
                    round(stats["min"], 2),
                    round(stats["max"], 2)
                ),
            )

            metrics.append(MetricConfig(
                metric_id=metric_id,
                enabled=True,
                evaluation_phase="execution",  # 默认在执行阶段评估
                thresholds=thresholds,
                error_conditions=[],  # 稍后添加
                weight=1.0,
            ))

        # 生成阶段定义
        phases = self._infer_phases_from_fingerprints(fingerprints)

        return ActionConfig(
            action_id=action_id,
            action_name=action_name_zh,
            action_name_zh=action_name_zh,
            description=f"通过训练自动生成的{action_name_zh}配置",
            version="1.0.0-trained",
            phases=phases,
            metrics=metrics,
            global_params={
                "min_phase_duration": 0.2,
                "enable_phase_detection": True,
                "use_viewpoint_analysis": True,
                "auto_select_side": True,
                "auto_generated": True,
            },
            metadata={},
        )

    def _aggregate_metric_stats(
        self,
        fingerprints: List[ActionFingerprint]
    ) -> Dict[str, Dict[str, float]]:
        """聚合指标统计信息."""
        from collections import defaultdict
        import numpy as np

        stats = defaultdict(lambda: {"means": [], "stds": [], "mins": [], "maxs": []})

        for fp in fingerprints:
            for metric in fp.dominant_metrics + fp.secondary_metrics:
                s = stats[metric.metric_id]
                s["means"].append(metric.mean)
                s["stds"].append(metric.std)
                s["mins"].append(metric.min)
                s["maxs"].append(metric.max)

        aggregated = {}
        for metric_id, s in stats.items():
            if s["means"]:
                aggregated[metric_id] = {
                    "mean": np.mean(s["means"]),
                    "std": np.mean(s["stds"]),
                    "min": np.min(s["mins"]),
                    "max": np.max(s["maxs"]),
                }

        return aggregated

    def _infer_phases_from_fingerprints(
        self,
        fingerprints: List[ActionFingerprint]
    ) -> List[Any]:
        """从指纹推断阶段定义."""
        from src.core.config.models import PhaseDefinition

        # 简化处理：使用通用阶段
        return [
            PhaseDefinition(
                phase_id="start",
                phase_name="起始",
                description="动作开始",
            ),
            PhaseDefinition(
                phase_id="execution",
                phase_name="执行",
                description="主要动作执行阶段",
            ),
            PhaseDefinition(
                phase_id="end",
                phase_name="结束",
                description="动作完成",
            ),
        ]

    def _add_error_condition_to_config(
        self,
        config: ActionConfig,
        metric_id: str,
        condition: ErrorCondition
    ) -> None:
        """添加错误条件到配置."""
        for metric in config.metrics:
            if metric.metric_id == metric_id:
                metric.error_conditions.append(condition)
                break

    def _calculate_config_confidence(
        self,
        standard_sample_count: int,
        error_conditions: Dict[str, List[ErrorCondition]],
    ) -> float:
        """计算配置置信度."""
        base_confidence = min(0.5 + standard_sample_count * 0.1, 0.8)

        # 有错误条件增加置信度
        if error_conditions:
            error_coverage = min(len(error_conditions) * 0.05, 0.15)
            base_confidence += error_coverage

        return min(base_confidence, 0.95)
