"""训练流程管道 V2.

连接所有训练步骤，提供完整的训练流程.
新增：阶段边界学习、检测项筛选、计数评估、规范产物输出.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path
import json
from datetime import datetime
import numpy as np

from src.core.models.base import PoseSequence
from src.core.pipeline.video_processor import VideoProcessor
from src.core.analysis.fingerprint import FingerprintAnalyzer, ActionFingerprint
from src.core.analysis.exploration import ExplorationAnalyzer
from src.core.analysis.template_generator import TemplateGenerator
from src.core.config.manager import ConfigManager
from src.core.config.models import (
    ActionConfig,
    ErrorCondition,
    PhaseDefinition,
    MetricConfig,
    CycleDefinition,
)
from src.core.phases.boundary_learner import PhaseBoundaryLearner, PhaseLearningResult
from src.core.phases.counter import RepCounter
from src.core.metrics.selector import MetricSelector
from src.core.metrics.calculator import MetricsCalculator


@dataclass
class VideoTrainingConfig:
    """单个视频的训练配置."""
    video_path: str
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    ground_truth_reps: Optional[int] = None  # 真实动作次数（用于评估）


from config.settings import Settings

class TrainingPipeline:
    """训练流程管道 V2.

    完整的训练流程:
    1. 视频处理 -> 姿态序列
    2. 指纹提取 -> ActionFingerprint
    3. 阶段边界学习 -> 从视频学习阶段条件
    4. 检测项筛选 -> 选择最优指标组合（max 6）
    5. 计数评估 -> 评估计数准确率
    6. 存储到数据库
    7. 聚合生成配置
    """

    def __init__(
        self,
        video_processor: Optional[VideoProcessor] = None,
        fingerprint_db_path: str = "data/fingerprints",
        max_metrics: int = 6,
    ):
        """
        Args:
            video_processor: 视频处理器
            fingerprint_db_path: 指纹数据库存储路径
            max_metrics: 最大检测项数量
        """
        from config.settings import Settings
        self.video_processor = video_processor or VideoProcessor(Settings())
        self.fingerprint_analyzer = FingerprintAnalyzer()
        self.exploration_analyzer = ExplorationAnalyzer()
        self.template_generator = TemplateGenerator()
        self.phase_learner = PhaseBoundaryLearner()
        self.metric_selector = MetricSelector(max_metrics=max_metrics)
        self.metrics_calculator = MetricsCalculator()

        # 初始化指纹数据库
        from src.core.analysis.fingerprint import FingerprintDatabase
        self.db = FingerprintDatabase(db_path=fingerprint_db_path)

        # 评估结果存储
        self.evaluation_results: List[Dict[str, Any]] = []

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

            # 2. 计算检测项（用于阶段边界学习）
            metric_results = self.metrics_calculator.calculate_all_metrics(
                pose_sequence,
                action_name=config.metadata.get("action_id", "unknown"),
            )
            metric_values = {
                mid: np.array(mr.get("values", []))
                for mid, mr in metric_results.items()
                if "values" in mr and mr["values"]
            }
            metric_summary = self._summarize_metric_results(metric_results)

            # 3. 阶段边界学习
            phase_learning_result = None
            if metric_values:
                # 通过实例属性传入目标计数，避免 learn_from_metrics 接口不匹配
                self.phase_learner.target_rep_count = config.ground_truth_reps
                phase_learning_result = self.phase_learner.learn_from_metrics(
                    metric_values,
                )

            # 4. 计数评估（如果有 ground_truth_reps）
            rep_count_eval = None
            if config.ground_truth_reps and phase_learning_result:
                rep_count_eval = self._evaluate_rep_count(
                    phase_learning_result,
                    config.ground_truth_reps,
                )

            # 5. 分析指纹
            fingerprint_action_name = (
                config.metadata.get("action_id")
                or config.metadata.get("action_name")
                or Path(config.video_path).stem
            )
            fingerprint = self.fingerprint_analyzer.analyze(
                pose_sequence=pose_sequence,
                action_name=fingerprint_action_name,
                video_metadata={
                    "video_path": config.video_path,
                    "metric_time_series": {
                        mid: vals.tolist() for mid, vals in metric_values.items()
                    },
                    "metric_summary": metric_summary,
                    **config.metadata,
                },
                tags=config.tags,
            )

            # 6. 确定标签
            label = self._determine_label(config.tags)

            # 7. 存储到数据库
            self.db.add_fingerprint(fingerprint, label=label)
            self.db.save_to_disk()

            # 8. 构建评估记录
            eval_record = {
                "video_path": config.video_path,
                "label": label,
                "ground_truth_reps": config.ground_truth_reps,
                "detected_reps": phase_learning_result.cycle_count if phase_learning_result else None,
                "rep_count_eval": rep_count_eval,
                "metric_time_series": {
                    mid: vals.tolist() for mid, vals in metric_values.items()
                },
                "metric_summary": metric_summary,
                "phase_learning": {
                    "key_metric": phase_learning_result.key_metric if phase_learning_result else None,
                    "confidence": phase_learning_result.confidence if phase_learning_result else 0.0,
                    "method": phase_learning_result.method if phase_learning_result else None,
                } if phase_learning_result else None,
            }
            self.evaluation_results.append(eval_record)

            return {
                "success": True,
                "fingerprint": fingerprint,
                "label": label,
                "metrics_analyzed": fingerprint.total_metrics_analyzed,
                "dominant_metrics": [m.metric_id for m in fingerprint.dominant_metrics],
                "phase_learning": phase_learning_result,
                "rep_count_eval": rep_count_eval,
            }

        except Exception as e:
            import traceback
            return {
                "success": False,
                "error": str(e),
                "traceback": traceback.format_exc(),
            }

    def _determine_label(self, tags: List[str]) -> str:
        """从标签列表确定主标签."""
        if "standard" in tags:
            return "standard"
        if "extreme" in tags:
            return "extreme"
        if "edge" in tags:
            return "edge"
        for tag in tags:
            if tag.startswith("error:"):
                return tag
        return "unknown"

    def _evaluate_rep_count(
        self,
        phase_learning_result: PhaseLearningResult,
        ground_truth_reps: int,
    ) -> Dict[str, float]:
        """评估计数准确性."""
        detected = phase_learning_result.cycle_count
        error = abs(detected - ground_truth_reps)

        return {
            "mae": float(error),  # Mean Absolute Error
            "acc_at_0": 1.0 if error == 0 else 0.0,  # 完全准确
            "acc_at_1": 1.0 if error <= 1 else 0.0,  # 误差<=1
            "detected": detected,
            "ground_truth": ground_truth_reps,
        }

    def _summarize_metric_results(
        self,
        metric_results: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, float]]:
        """将检测项时序压缩为可用于规则评估的摘要."""
        summary: Dict[str, Dict[str, float]] = {}
        for metric_id, result in metric_results.items():
            values = result.get("values")
            if not values:
                continue
            arr = np.array(values, dtype=float)
            arr = arr[~np.isnan(arr)]
            if arr.size == 0:
                continue
            summary[metric_id] = {
                "mean": float(np.mean(arr)),
                "min": float(np.min(arr)),
                "max": float(np.max(arr)),
                "last": float(arr[-1]),
            }
        return summary

    def generate_production_config(
        self,
        action_id: str,
        action_name_zh: str,
        standard_fingerprints: List[ActionFingerprint],
        error_conditions: Dict[str, List[ErrorCondition]],
        output_dir: str = "config/action_configs",
        dataset_version: str = "v1.0",
    ) -> Dict[str, Any]:
        """生成生产环境配置 V2.

        Args:
            action_id: 动作ID
            action_name_zh: 中文名称
            standard_fingerprints: 标准动作指纹列表
            error_conditions: 错误类型到条件列表的映射
            output_dir: 输出目录
            dataset_version: 数据集版本

        Returns:
            配置生成结果（包含规范产物信息）
        """
        if not standard_fingerprints:
            return {
                "success": False,
                "error": "没有标准动作指纹",
            }

        # 1. 聚合指标统计
        metric_stats = self._aggregate_metric_stats(standard_fingerprints)

        # 2. 检测项筛选（max 6）
        # 构建用于筛选的 metric_values
        metric_values = self._build_metric_values_for_selection(standard_fingerprints)
        selection_result = self.metric_selector.select_metrics(
            metric_values=metric_values,
            labels=["standard"] * len(standard_fingerprints),
        )

        # 3. 阶段边界学习（基于聚合数据）
        phase_learning_result = self._learn_phases_from_fingerprints(
            standard_fingerprints, selection_result.core_metrics
        )

        # 3.1 计数层参数学习（仅训练集标准样本）
        count_layer = self._learn_count_layer_from_training_set(
            action_id=action_id,
            core_metrics=selection_result.core_metrics,
            phase_learning_result=phase_learning_result,
        )

        # 4. 创建基础配置
        base_config = self._create_base_config_v2(
            action_id=action_id,
            action_name_zh=action_name_zh,
            metric_stats=metric_stats,
            selection_result=selection_result,
            phase_learning_result=phase_learning_result,
            count_layer=count_layer,
        )

        # 5. 添加错误条件（只添加到核心指标）
        for error_type, conditions in error_conditions.items():
            for condition in conditions:
                metric_id = condition.condition.get("metric_id")
                if metric_id and metric_id in selection_result.core_metrics:
                    self._add_error_condition_to_config(
                        base_config, metric_id, condition
                    )

        # 6. 计算计数评估指标
        rep_count_metrics = self._calculate_rep_count_metrics()
        error_recognition_metrics = self._calculate_error_recognition_metrics(error_conditions)

        # 7. 计算配置置信度
        confidence = self._calculate_config_confidence_v2(
            standard_sample_count=len(standard_fingerprints),
            error_conditions=error_conditions,
            selection_result=selection_result,
            phase_learning_result=phase_learning_result,
            rep_count_metrics=rep_count_metrics,
            error_recognition_metrics=error_recognition_metrics,
        )

        # 8. 添加元数据
        candidate_version = f"{datetime.now().strftime('%Y%m%d')}_{dataset_version}"
        base_config.metadata["training_info"] = {
            "schema_version": "v2.0",
            "action_id": action_id,
            "dataset_version": dataset_version,
            "candidate_version": candidate_version,
            "created_at": datetime.now().isoformat(),
            "standard_samples": len(standard_fingerprints),
            "error_types": list(error_conditions.keys()),
            "total_error_conditions": sum(len(c) for c in error_conditions.values()),
            "confidence": confidence,
        }

        # 9. 生成拆分清单产物
        split_result = self._generate_split_manifest(
            action_id=action_id,
            dataset_version=dataset_version,
            output_dir="data/datasets",
        )

        # 10. 生成评估产物
        evaluation_result = self._generate_evaluation_artifact(
            action_id=action_id,
            candidate_version=candidate_version,
            rep_count_metrics=rep_count_metrics,
            error_recognition_metrics=error_recognition_metrics,
            error_conditions=error_conditions,
            selection_result=selection_result,
            phase_learning_result=phase_learning_result,
            output_dir="data/evaluations",
        )

        # 11. 保存配置
        output_path = Path(output_dir) / f"{action_id}_trained.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(base_config.to_dict(), f, indent=2, ensure_ascii=False)

            return {
                "success": True,
                "config_path": str(output_path),
                "action_id": action_id,
                "candidate_version": candidate_version,
                "confidence": confidence,
                "metric_selection": selection_result.selection_info,
                "phase_learning": {
                    "key_metric": phase_learning_result.key_metric if phase_learning_result else None,
                    "cycle_count": phase_learning_result.cycle_count if phase_learning_result else 0,
                    "confidence": phase_learning_result.confidence if phase_learning_result else 0.0,
                },
                "rep_count_metrics": rep_count_metrics,
                "error_recognition_metrics": error_recognition_metrics,
                "artifacts": {
                    "config": str(output_path),
                    "split_manifest": split_result.get("path"),
                    "evaluation": evaluation_result.get("path"),
                },
            }
        except Exception as e:
            import traceback
            return {
                "success": False,
                "error": f"保存配置失败: {e}",
                "traceback": traceback.format_exc(),
            }

    def _create_base_config_v2(
        self,
        action_id: str,
        action_name_zh: str,
        metric_stats: Dict[str, Dict[str, float]],
        selection_result: Any,  # MetricSelectionResult
        phase_learning_result: Optional[PhaseLearningResult],
        count_layer: Dict[str, Any],
    ) -> ActionConfig:
        """从指纹创建基础配置 V2."""
        # 生成检测项配置（只保留核心指标）
        metrics = []
        for metric_id in selection_result.core_metrics:
            if metric_id not in metric_stats:
                continue

            stats = metric_stats[metric_id]
            from src.core.config.models import MetricThreshold

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
                evaluation_phase="hold" if "hold" in [p.phase_id for p in (phase_learning_result.phases if phase_learning_result else [])] else "execution",
                thresholds=thresholds,
                error_conditions=[],  # 稍后添加
                weight=1.0,
            ))

        # 生成阶段定义（从学习结果或默认）
        phases = self._build_phases_from_learning(phase_learning_result)

        # 构建周期定义
        cycle_def = None
        if phase_learning_result and phase_learning_result.phases:
            cycle_def = self._build_cycle_definition(phase_learning_result)

        semantic_layer = {
            "enabled": bool(phase_learning_result and phase_learning_result.phases),
            "phases": [p.to_dict() for p in phases],
        }
        compatibility = {
            "phase_alias_map": self._build_phase_alias_map(phases),
        }

        return ActionConfig(
            schema_version="3.0.0",
            action_id=action_id,
            action_name=action_name_zh,
            action_name_zh=action_name_zh,
            description=f"通过训练自动生成的{action_name_zh}配置",
            version="3.0.0-trained",
            phases=phases,
            metrics=metrics,
            cycle_definition=cycle_def,
            count_layer=count_layer,
            semantic_layer=semantic_layer,
            compatibility=compatibility,
            global_params={
                "min_phase_duration": 0.2,
                "enable_phase_detection": True,
                "use_viewpoint_analysis": True,
                "auto_select_side": True,
                "auto_generated": True,
            },
            metadata={
                "metric_selection_info": selection_result.selection_info,
            },
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

    def _build_metric_values_for_selection(
        self,
        fingerprints: List[ActionFingerprint],
    ) -> Dict[str, np.ndarray]:
        """构建用于检测项筛选的 metric_values."""
        metric_values = {}

        for fingerprint in fingerprints:
            for metric in fingerprint.dominant_metrics + fingerprint.secondary_metrics:
                if metric.metric_id not in metric_values:
                    metric_values[metric.metric_id] = []
                # 使用时间序列特征作为代表
                metric_values[metric.metric_id].extend([
                    metric.mean, metric.std, metric.min, metric.max
                ])

        # 转换为 numpy 数组
        return {
            k: np.array(v) for k, v in metric_values.items() if v
        }

    def _learn_phases_from_fingerprints(
        self,
        fingerprints: List[ActionFingerprint],
        core_metrics: List[str],
    ) -> Optional[PhaseLearningResult]:
        """从指纹学习阶段边界."""
        if not fingerprints or not core_metrics:
            return None

        # 从训练集标准样本聚合时序，降低单样本过拟合
        total = len(self.evaluation_results)
        train_records = [
            record
            for idx, record in enumerate(self.evaluation_results)
            if self._determine_split(idx, total) == "train" and record.get("label") == "standard"
        ]

        metric_values: Dict[str, np.ndarray] = {}
        for metric_id in core_metrics:
            series_list: List[np.ndarray] = []
            for record in train_records:
                metric_series = record.get("metric_time_series", {})
                series = metric_series.get(metric_id)
                if series and len(series) >= 3:
                    series_list.append(np.array(series, dtype=float))
            if not series_list:
                continue
            min_len = min(len(series) for series in series_list)
            aligned = np.stack([series[:min_len] for series in series_list], axis=0)
            metric_values[metric_id] = np.median(aligned, axis=0)

        if not metric_values:
            return None

        return self.phase_learner.learn_from_metrics(
            metric_values,
            preferred_metrics=core_metrics,
        )

    def _learn_count_layer_from_training_set(
        self,
        action_id: str,
        core_metrics: List[str],
        phase_learning_result: Optional[PhaseLearningResult],
    ) -> Dict[str, Any]:
        """基于训练集样本学习 p1/p2 计数层参数."""
        key_metric = (
            phase_learning_result.key_metric
            if phase_learning_result and phase_learning_result.key_metric
            else (core_metrics[0] if core_metrics else "")
        )
        if not key_metric:
            return {}

        total = len(self.evaluation_results)
        train_records = [
            record
            for idx, record in enumerate(self.evaluation_results)
            if self._determine_split(idx, total) == "train" and record.get("label") == "standard"
        ]
        if not train_records:
            return {}

        enter_p1_values = []
        exit_p1_values = []
        enter_p2_values = []
        exit_p2_values = []
        cycle_distance_values = []

        for record in train_records:
            series = record.get("metric_time_series", {}).get(key_metric)
            if not series or len(series) < 3:
                continue
            arr = np.array(series, dtype=float)
            min_v = float(np.min(arr))
            max_v = float(np.max(arr))
            amp = max_v - min_v
            if amp <= 1e-6:
                continue

            enter_p1_values.append(min_v + 0.35 * amp)
            exit_p1_values.append(min_v + 0.75 * amp)
            enter_p2_values.append(min_v + 0.65 * amp)
            exit_p2_values.append(min_v + 0.30 * amp)

            gt_reps = record.get("ground_truth_reps")
            if gt_reps and gt_reps > 0:
                cycle_distance_values.append(len(arr) / gt_reps)

        if not enter_p1_values:
            return {}

        def _median(values: List[float]) -> float:
            return float(np.median(np.array(values, dtype=float)))

        def _ci(values: List[float]) -> List[float]:
            arr = np.array(values, dtype=float)
            return [round(float(np.percentile(arr, 25)), 3), round(float(np.percentile(arr, 75)), 3)]

        min_cycle_distance = 3
        if cycle_distance_values:
            min_cycle_distance = max(3, int(_median(cycle_distance_values) * 0.4))

        return {
            "phase_mode": "p1p2",
            "control_metric": key_metric,
            "polarity": "valley_to_peak_to_valley",
            "thresholds": {
                "enter_p1": round(_median(enter_p1_values), 3),
                "exit_p1": round(_median(exit_p1_values), 3),
                "enter_p2": round(_median(enter_p2_values), 3),
                "exit_p2": round(_median(exit_p2_values), 3),
            },
            "timing": {
                "min_phase_duration_sec": 0.2,
                "max_phase_duration_sec": 5.0,
                "min_cycle_distance_frames": min_cycle_distance,
            },
            "aggregation": {
                "method": "median_iqr",
                "train_video_count": len(train_records),
                "param_ci": {
                    "enter_p1": _ci(enter_p1_values),
                    "exit_p1": _ci(exit_p1_values),
                    "enter_p2": _ci(enter_p2_values),
                    "exit_p2": _ci(exit_p2_values),
                },
            },
            "source": {
                "action_id": action_id,
                "dataset_split": "train",
            },
        }

    def _build_phase_alias_map(self, phases: List[PhaseDefinition]) -> Dict[str, str]:
        """构建语义 phase 到 p1/p2 的兼容映射."""
        alias_map: Dict[str, str] = {}
        for phase in phases:
            phase_id = phase.phase_id
            phase_name = (phase.phase_name or "").lower()
            token = f"{phase_id.lower()} {phase_name}"
            if any(key in token for key in ["execution", "ascent", "up", "rise", "lift", "hold"]):
                alias_map[phase_id] = "p1"
            elif any(key in token for key in ["return", "descent", "down", "fall"]):
                alias_map[phase_id] = "p2"
        if "execution" in [p.phase_id for p in phases]:
            alias_map.setdefault("execution", "p1")
        if "return" in [p.phase_id for p in phases]:
            alias_map.setdefault("return", "p2")
        return alias_map

    def _build_phases_from_learning(
        self,
        phase_learning_result: Optional[PhaseLearningResult],
    ) -> List[PhaseDefinition]:
        """从学习结果构建阶段定义."""
        if phase_learning_result and phase_learning_result.phases:
            return [
                PhaseDefinition(
                    phase_id=p.phase_id,
                    phase_name=p.phase_name,
                    entry_conditions=p.entry_conditions,
                    exit_conditions=p.exit_conditions,
                    detection_params=p.detection_params,
                )
                for p in phase_learning_result.phases
            ]

        # 默认阶段
        return [
            PhaseDefinition(phase_id="start", phase_name="起始位置"),
            PhaseDefinition(phase_id="execution", phase_name="执行阶段"),
            PhaseDefinition(phase_id="end", phase_name="结束位置"),
        ]

    def _build_cycle_definition(
        self,
        phase_learning_result: PhaseLearningResult,
    ) -> Optional[CycleDefinition]:
        """从学习结果构建周期定义."""
        if not phase_learning_result.phases:
            return None

        phase_ids = [p.phase_id for p in phase_learning_result.phases]

        # 识别关键阶段（包含 hold/peak/bottom 等）
        required = []
        for pid in phase_ids:
            if any(k in pid for k in ["hold", "peak", "bottom", "max", "min"]):
                required.append(pid)
                break

        if not required and len(phase_ids) >= 2:
            required = [phase_ids[len(phase_ids) // 2]]

        return CycleDefinition(
            phase_sequence=phase_ids,
            start_phase=phase_ids[0] if phase_ids else None,
            end_phase=phase_ids[0] if phase_ids else None,
            required_phases=required,
            cycle_mode="closed",
        )

    def _calculate_rep_count_metrics(self) -> Dict[str, float]:
        """计算计数评估指标."""
        if not self.evaluation_results:
            return {"mae": 0.0, "acc_at_0": 0.0, "acc_at_1": 0.0}

        evals = [r for r in self.evaluation_results if r.get("rep_count_eval")]
        if not evals:
            return {"mae": 0.0, "acc_at_0": 0.0, "acc_at_1": 0.0}

        mae_list = [r["rep_count_eval"]["mae"] for r in evals]
        acc_at_0_list = [r["rep_count_eval"]["acc_at_0"] for r in evals]
        acc_at_1_list = [r["rep_count_eval"]["acc_at_1"] for r in evals]

        return {
            "mae": round(sum(mae_list) / len(mae_list), 2),
            "acc_at_0": round(sum(acc_at_0_list) / len(acc_at_0_list), 2),
            "acc_at_1": round(sum(acc_at_1_list) / len(acc_at_1_list), 2),
        }

    def _calculate_config_confidence_v2(
        self,
        standard_sample_count: int,
        error_conditions: Dict[str, List[ErrorCondition]],
        selection_result: Any,
        phase_learning_result: Optional[PhaseLearningResult],
        rep_count_metrics: Dict[str, float],
        error_recognition_metrics: Dict[str, float],
    ) -> float:
        """计算配置置信度 V2."""
        # 基础置信度（样本数）
        sample_confidence = min(0.4 + standard_sample_count * 0.05, 0.6)

        # 检测项筛选置信度
        selection_confidence = 0.0
        if selection_result.selection_info:
            final_core = selection_result.selection_info.get("final_core", 0)
            scored = selection_result.selection_info.get("scored_metrics", 1)
            selection_confidence = min(0.2, final_core / max(scored, 1) * 0.2)

        # 阶段学习置信度
        phase_confidence = 0.0
        if phase_learning_result:
            phase_confidence = phase_learning_result.confidence * 0.15

        # 计数评估置信度
        count_confidence = 0.0
        if rep_count_metrics:
            acc = rep_count_metrics.get("acc_at_1", 0)
            count_confidence = acc * 0.15

        # 错误识别置信度
        error_confidence = 0.0
        evaluated_samples = error_recognition_metrics.get("evaluated_samples", 0)
        if evaluated_samples > 0:
            error_confidence = error_recognition_metrics.get("error_f1", 0.0) * 0.1

        total = sample_confidence + selection_confidence + phase_confidence + count_confidence + error_confidence
        return min(total, 0.95)

    def _calculate_error_recognition_metrics(
        self,
        error_conditions: Dict[str, List[ErrorCondition]],
    ) -> Dict[str, float]:
        """基于规则回放评估错误识别率（standard vs error:*）."""
        tp = fp = tn = fn = 0
        type_correct = 0
        type_total = 0

        for record in self.evaluation_results:
            label = record.get("label", "")
            if label == "standard":
                expected_is_error = False
                expected_error_type = None
            elif label.startswith("error:"):
                expected_is_error = True
                expected_error_type = label.split(":", 1)[1]
                type_total += 1
            else:
                # extreme/edge 不纳入错误识别率
                continue

            predicted_types = self._predict_error_types_for_record(record, error_conditions)
            predicted_is_error = len(predicted_types) > 0

            if expected_is_error and predicted_is_error:
                tp += 1
            elif (not expected_is_error) and predicted_is_error:
                fp += 1
            elif (not expected_is_error) and (not predicted_is_error):
                tn += 1
            else:
                fn += 1

            if expected_error_type and expected_error_type in predicted_types:
                type_correct += 1

        evaluated = tp + fp + tn + fn
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        accuracy = (tp + tn) / evaluated if evaluated else 0.0
        type_acc = type_correct / type_total if type_total else 0.0

        return {
            "evaluated_samples": float(evaluated),
            "error_precision": round(precision, 4),
            "error_recall": round(recall, 4),
            "error_f1": round(f1, 4),
            "error_accuracy": round(accuracy, 4),
            "error_type_accuracy": round(type_acc, 4),
        }

    def _predict_error_types_for_record(
        self,
        record: Dict[str, Any],
        error_conditions: Dict[str, List[ErrorCondition]],
    ) -> List[str]:
        """按错误条件规则预测样本错误类型."""
        metric_summary = record.get("metric_summary", {})
        predicted_types: List[str] = []

        for error_type, conditions in error_conditions.items():
            normalized_error_type = self._normalize_error_type(error_type)
            hit = False
            for condition in conditions:
                cond = condition.condition or {}
                metric_id = cond.get("metric_id")
                operator = cond.get("operator")
                threshold = cond.get("value")
                if not metric_id or threshold is None or operator is None:
                    continue
                metric_stats = metric_summary.get(metric_id)
                if not metric_stats:
                    continue
                metric_value = metric_stats.get("mean")
                if metric_value is None:
                    continue
                if self._evaluate_condition(metric_value, operator, threshold):
                    hit = True
                    break
            if hit:
                predicted_types.append(normalized_error_type)
        return predicted_types

    @staticmethod
    def _evaluate_condition(value: float, operator: str, threshold: float) -> bool:
        if operator == "lt":
            return value < threshold
        if operator == "lte":
            return value <= threshold
        if operator == "gt":
            return value > threshold
        if operator == "gte":
            return value >= threshold
        if operator == "eq":
            return value == threshold
        return False

    @staticmethod
    def _normalize_error_type(error_type: str) -> str:
        return error_type.split(":", 1)[1] if error_type.startswith("error:") else error_type

    def _generate_split_manifest(
        self,
        action_id: str,
        dataset_version: str,
        output_dir: str,
    ) -> Dict[str, Any]:
        """生成拆分清单产物."""
        # 统计各分区样本
        train_samples = []
        validation_samples = []
        test_samples = []

        for i, record in enumerate(self.evaluation_results):
            sample = {
                "sample_id": f"{action_id}_{i:04d}",
                "video_path": record["video_path"],
                "label": record["label"],
                "ground_truth_reps": record.get("ground_truth_reps"),
                "detected_reps": record.get("detected_reps"),
            }

            # 简单拆分策略：前 70% 训练，中间 15% 验证，后 15% 测试
            if i < len(self.evaluation_results) * 0.7:
                train_samples.append(sample)
            elif i < len(self.evaluation_results) * 0.85:
                validation_samples.append(sample)
            else:
                test_samples.append(sample)

        manifest = {
            "schema_version": "v2.0",
            "action_id": action_id,
            "dataset_version": dataset_version,
            "created_at": datetime.now().isoformat(),
            "counts": {
                "train": len(train_samples),
                "validation": len(validation_samples),
                "test": len(test_samples),
            },
            "train": train_samples,
            "validation": validation_samples,
            "test": test_samples,
            "distribution_by_label": self._calculate_label_distribution(
                train_samples, validation_samples, test_samples
            ),
        }

        # 保存
        output_path = Path(output_dir) / f"{action_id}_{dataset_version}_split.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(manifest, f, indent=2, ensure_ascii=False)

        return {"path": str(output_path), "manifest": manifest}

    def _calculate_label_distribution(
        self, train: List, validation: List, test: List
    ) -> Dict[str, Dict[str, int]]:
        """计算各分区标签分布."""
        from collections import Counter

        return {
            "train": dict(Counter(s["label"] for s in train)),
            "validation": dict(Counter(s["label"] for s in validation)),
            "test": dict(Counter(s["label"] for s in test)),
        }

    def _generate_evaluation_artifact(
        self,
        action_id: str,
        candidate_version: str,
        rep_count_metrics: Dict[str, float],
        error_recognition_metrics: Dict[str, float],
        error_conditions: Dict[str, List[ErrorCondition]],
        selection_result: Any,
        phase_learning_result: Optional[PhaseLearningResult],
        output_dir: str,
    ) -> Dict[str, Any]:
        """生成评估产物."""
        evaluation = {
            "schema_version": "v2.0",
            "action_id": action_id,
            "candidate_version": candidate_version,
            "created_at": datetime.now().isoformat(),
            "overall_score": 0.0,  # 稍后计算
            "metric_scores": {
                "rep_count_mae": rep_count_metrics.get("mae", 0),
                "rep_count_acc_at_0": rep_count_metrics.get("acc_at_0", 0),
                "rep_count_acc_at_1": rep_count_metrics.get("acc_at_1", 0),
                "error_precision": error_recognition_metrics.get("error_precision", 0),
                "error_recall": error_recognition_metrics.get("error_recall", 0),
                "error_f1": error_recognition_metrics.get("error_f1", 0),
                "error_accuracy": error_recognition_metrics.get("error_accuracy", 0),
                "error_type_accuracy": error_recognition_metrics.get("error_type_accuracy", 0),
            },
            "sample_results": [
                {
                    "sample_id": f"{action_id}_{i:04d}",
                    "video_path": r["video_path"],
                    "predicted_reps": r.get("detected_reps"),
                    "expected_reps": r.get("ground_truth_reps"),
                    "expected_label": r.get("label"),
                    "predicted_error_types": self._predict_error_types_for_record(r, error_conditions),
                    "split": self._determine_split(i, len(self.evaluation_results)),
                }
                for i, r in enumerate(self.evaluation_results)
            ],
            "phase_learning_info": {
                "key_metric": phase_learning_result.key_metric if phase_learning_result else None,
                "method": phase_learning_result.method if phase_learning_result else None,
                "cycle_count": phase_learning_result.cycle_count if phase_learning_result else 0,
                "confidence": phase_learning_result.confidence if phase_learning_result else 0.0,
            } if phase_learning_result else None,
            "metric_selection_info": selection_result.selection_info if selection_result else None,
        }

        # 计算整体评分
        evaluation["overall_score"] = self._calculate_overall_score(evaluation)

        # 保存
        output_path = Path(output_dir) / action_id / f"{candidate_version}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(evaluation, f, indent=2, ensure_ascii=False)

        return {"path": str(output_path), "evaluation": evaluation}

    def _determine_split(self, index: int, total: int) -> str:
        """确定样本所属分区."""
        if index < total * 0.7:
            return "train"
        elif index < total * 0.85:
            return "validation"
        return "test"

    def _calculate_overall_score(self, evaluation: Dict) -> float:
        """计算整体评分."""
        metric_scores = evaluation.get("metric_scores", {})

        # 计数分
        acc = metric_scores.get("rep_count_acc_at_1", 0)
        mae = metric_scores.get("rep_count_mae", 0)
        mae_score = max(0, 1 - mae / 5)
        count_score = acc * 0.7 + mae_score * 0.3

        # 错误识别分
        error_f1 = metric_scores.get("error_f1", 0)
        error_score = error_f1

        return round((count_score * 0.7 + error_score * 0.3) * 100, 1)

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
