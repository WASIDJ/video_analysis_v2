"""动作分析器 - 统一调度层.

整合阶段检测、动作计数、检测项计算、阈值评估、错误识别。
"""
from typing import Any, Dict, List, Optional
import logging
import time

from src.core.config.models import ActionConfig
from src.core.models.base import PoseSequence
from src.core.phases.engine import PhaseEngine, PhaseConfig
from src.core.phases.counter import RepCounter, CycleDefinition, RepCountResult
from src.core.metrics.evaluator import ThresholdEvaluator, ThresholdEvaluation
from src.core.metrics.calculator import MetricsCalculator

logger = logging.getLogger(__name__)


class AnalysisResult:
    """分析结果 - 统一输出格式."""

    def __init__(
        self,
        api_version: str = "2.0.0",
        action_id: str = "",
        action_config: Optional[Dict] = None,
        processing_info: Optional[Dict] = None,
        phases: Optional[List[Dict]] = None,
        rep_count: Optional[Dict] = None,
        metrics: Optional[Dict[str, Dict]] = None,
        overall: Optional[Dict] = None,
    ):
        self.api_version = api_version
        self.action_id = action_id
        self.action_config = action_config or {}
        self.processing_info = processing_info or {}
        self.phases = phases or []
        self.rep_count = rep_count or {"count": 0, "confidence": 0.0}
        self.metrics = metrics or {}
        self.overall = overall or {}

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典."""
        return {
            "api_version": self.api_version,
            "action_id": self.action_id,
            "action_config": self.action_config,
            "processing_info": self.processing_info,
            "phases": self.phases,
            "rep_count": self.rep_count,
            "metrics": self.metrics,
            "overall": self.overall,
        }


class ActionAnalyzer:
    """动作分析器 - 统一调度."""

    def __init__(
        self,
        action_config: ActionConfig,
        fps: float = 30.0,
    ):
        self.config = action_config
        self.fps = fps

        # 初始化子组件
        self.metrics_calculator = MetricsCalculator(
            action_id=action_config.action_id,
        )
        self.threshold_evaluator = ThresholdEvaluator()

        # 阶段引擎和计数器（延迟初始化，需要运行时数据）
        self.phase_engine: Optional[PhaseEngine] = None
        self.rep_counter: Optional[RepCounter] = None

        # 初始化计数器（如果有周期定义）
        if action_config.cycle_definition:
            self.rep_counter = RepCounter(action_config.cycle_definition)

    def analyze(
        self,
        pose_sequence: PoseSequence,
        metric_values: Optional[Dict[str, Any]] = None,
    ) -> AnalysisResult:
        """
        执行完整分析.

        流程：
        1. 计算检测项
        2. 阶段检测
        3. 动作计数
        4. 阈值评估
        5. 错误识别
        6. 整体评估
        """
        start_time = time.time()

        # 1. 计算检测项（如果没有预计算）
        if metric_values is None:
            metric_values = self._calculate_metrics(pose_sequence)

        # 2. 阶段检测
        phase_sequence = self._detect_phases(metric_values)

        # 3. 动作计数
        rep_result = self._count_reps(phase_sequence)

        # 4. 阈值评估和错误识别
        metrics_result = self._evaluate_metrics(metric_values, phase_sequence)

        # 5. 整体评估
        overall = self._calculate_overall(metrics_result)

        # 6. 构建结果
        processing_time = (time.time() - start_time) * 1000

        return AnalysisResult(
            api_version="2.0.0",
            action_id=self.config.action_id,
            action_config={
                "version": self.config.version,
                "schema_version": self.config.schema_version,
                "phases": [p.phase_id for p in self.config.phases],
                "metrics_count": len(self.config.metrics),
            },
            processing_info={
                "duration_ms": round(processing_time, 2),
                "frame_count": len(pose_sequence.frames) if pose_sequence else 0,
                "fps": self.fps,
            },
            phases=[
                {
                    "phase_id": det.phase_id,
                    "start_frame": det.start_frame,
                    "end_frame": det.end_frame,
                    "duration": round(det.duration, 2),
                    "confidence": round(det.confidence, 2),
                }
                for det in phase_sequence.detections
            ] if phase_sequence else [],
            rep_count={
                "count": rep_result.count if rep_result else 0,
                "confidence": round(rep_result.confidence, 2) if rep_result else 0.0,
                "rep_ranges": rep_result.rep_ranges if rep_result else [],
            },
            metrics=metrics_result,
            overall=overall,
        )

    def _calculate_metrics(
        self,
        pose_sequence: PoseSequence,
    ) -> Dict[str, Any]:
        """计算检测项."""
        # 使用现有的 MetricsCalculator
        results = self.metrics_calculator.calculate_all_metrics(
            pose_sequence,
            action_name=self.config.action_id,
        )
        return results

    def _detect_phases(
        self,
        metric_values: Dict[str, Any],
    ) -> Any:
        """检测阶段."""
        if not self.config.phases:
            logger.warning("未配置阶段定义")
            return None

        # 转换 PhaseDefinition 到 PhaseConfig
        phase_configs = []
        for phase_def in self.config.phases:
            config = PhaseConfig(
                phase_id=phase_def.phase_id,
                phase_name=phase_def.phase_name,
                description=phase_def.description,
                # 简化处理：使用空的条件列表
                # 实际应该从 detection_params 转换
                entry_conditions=[],
                exit_conditions=[],
            )
            phase_configs.append(config)

        # 提取数值数组
        numeric_values = {}
        for metric_id, result in metric_values.items():
            if isinstance(result, dict) and "values" in result:
                import numpy as np
                numeric_values[metric_id] = np.array(result["values"])

        # 初始化阶段引擎
        self.phase_engine = PhaseEngine(
            phase_configs=phase_configs,
            metric_values=numeric_values,
            fps=self.fps,
        )

        return self.phase_engine.detect_phases()

    def _count_reps(
        self,
        phase_sequence: Any,
    ) -> Optional[RepCountResult]:
        """动作计数."""
        if not self.rep_counter or not phase_sequence:
            return None

        return self.rep_counter.count(phase_sequence)

    def _evaluate_metrics(
        self,
        metric_values: Dict[str, Any],
        phase_sequence: Any,
    ) -> Dict[str, Dict]:
        """评估检测项."""
        results = {}

        for metric in self.config.metrics:
            if not metric.enabled:
                continue

            metric_id = metric.metric_id

            # 获取检测项计算结果
            calc_result = metric_values.get(metric_id, {})
            if not calc_result:
                continue

            # 获取关键帧数值
            key_value = calc_result.get("statistics", {}).get("key_frame_value")
            if key_value is None and "values" in calc_result:
                # 使用平均值
                import numpy as np
                values = calc_result["values"]
                key_value = float(np.mean([v for v in values if v is not None]))

            # 阈值评估
            evaluation = None
            if metric.thresholds and key_value is not None:
                from src.core.metrics.evaluator import MetricThreshold
                thresholds = MetricThreshold(
                    target_value=metric.thresholds.target_value,
                    normal_range=metric.thresholds.normal_range,
                    excellent_range=metric.thresholds.excellent_range,
                    good_range=metric.thresholds.good_range,
                    pass_range=metric.thresholds.pass_range,
                )
                evaluation = self.threshold_evaluator.evaluate(key_value, thresholds)

            # 构建结果
            result = {
                "metric_id": metric_id,
                "name": calc_result.get("name", ""),
                "category": calc_result.get("category", ""),
                "unit": calc_result.get("unit", ""),
                "evaluation_phase": metric.evaluation_phase,
                "values": calc_result.get("values", []),
                "statistics": calc_result.get("statistics", {}),
                "key_frame_value": key_value,
                "grade": evaluation.grade if evaluation else None,
                "score": evaluation.score if evaluation else None,
                "errors": calc_result.get("errors", []),
            }

            results[metric_id] = result

        return results

    def _calculate_overall(
        self,
        metrics_result: Dict[str, Dict],
    ) -> Dict:
        """计算整体评估."""
        if not metrics_result:
            return {"grade": "unknown", "score": 0.0}

        # 收集所有评分
        scores = []
        error_count = 0

        for metric_result in metrics_result.values():
            if metric_result.get("score") is not None:
                scores.append(metric_result["score"])
            error_count += len(metric_result.get("errors", []))

        # 计算平均分
        if scores:
            avg_score = sum(scores) / len(scores)
        else:
            avg_score = 0.0

        # 确定整体等级
        if avg_score >= 90:
            grade = "excellent"
        elif avg_score >= 80:
            grade = "good"
        elif avg_score >= 60:
            grade = "pass"
        else:
            grade = "fail"

        return {
            "grade": grade,
            "score": round(avg_score, 1),
            "error_count": error_count,
            "summary": self._generate_summary(grade, error_count),
        }

    def _generate_summary(self, grade: str, error_count: int) -> str:
        """生成评估摘要."""
        grade_desc = {
            "excellent": "动作完成优秀",
            "good": "动作完成良好",
            "pass": "动作基本合格",
            "fail": "动作需要改进",
        }

        summary = grade_desc.get(grade, "评估完成")

        if error_count > 0:
            summary += f"，发现 {error_count} 处问题"

        return summary
