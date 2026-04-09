"""错误条件学习器.

从错误样本与标准样本的对比中自动学习错误判断条件.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, Tuple
import numpy as np
from collections import defaultdict

from src.core.analysis.fingerprint import ActionFingerprint, MetricFingerprint
from src.core.config.models import ErrorCondition


@dataclass
class ErrorPattern:
    """发现的错误模式."""
    metric_id: str
    metric_name: str
    error_type: str

    # 偏离特征
    deviation_direction: str  # "high" 或 "low"
    deviation_magnitude: float  # 偏离幅度

    # 建议阈值
    suggested_threshold: float
    operator: str  # "gt" 或 "lt"

    # 置信度
    confidence: float
    support: int  # 支持的样本数


class ErrorConditionLearner:
    """错误条件学习器.

    通过对比标准动作和错误动作的指纹，自动学习错误判断条件。

    学习策略:
    1. 范围对比: 错误样本的范围是否超出标准范围
    2. 极值对比: 错误样本的极值是否偏离标准极值
    3. 统计对比: 均值、方差的显著差异
    4. 模式发现: 特定指标的错误关联性
    """

    # 学习参数
    LEARNING_PARAMS = {
        "min_separation": 0.3,          # 标准与错误分布的最小分离度
        "confidence_threshold": 0.7,     # 最小置信度
        "min_support": 2,                # 最小支持样本数
        "outlier_percentile": 5,         # 异常值百分位
        "safety_margin": 1.1,            # 阈值安全边距
    }

    def __init__(self, params: Optional[Dict] = None):
        """
        Args:
            params: 自定义学习参数
        """
        self.params = {**self.LEARNING_PARAMS, **(params or {})}

    def learn_error_conditions(
        self,
        standard_fingerprints: List[ActionFingerprint],
        error_fingerprints: List[ActionFingerprint],
        error_type: str,
    ) -> List[ErrorCondition]:
        """学习错误判断条件.

        Args:
            standard_fingerprints: 标准动作指纹列表
            error_fingerprints: 错误动作指纹列表
            error_type: 错误类型标识

        Returns:
            学习到的错误条件列表
        """
        if len(standard_fingerprints) < 2 or len(error_fingerprints) < self.params["min_support"]:
            return []

        # 聚合标准动作的统计信息
        standard_stats = self._aggregate_fingerprints(standard_fingerprints)

        # 发现错误模式
        patterns = self._discover_error_patterns(
            standard_stats,
            error_fingerprints,
            error_type
        )

        # 转换为ErrorCondition
        conditions = []
        for pattern in patterns:
            if pattern.confidence >= self.params["confidence_threshold"]:
                condition = self._pattern_to_condition(pattern, error_type)
                if condition:
                    conditions.append(condition)

        return conditions

    def _aggregate_fingerprints(
        self,
        fingerprints: List[ActionFingerprint]
    ) -> Dict[str, Dict[str, Any]]:
        """聚合多个指纹的统计信息."""
        stats = defaultdict(lambda: {
            "ranges": [],
            "means": [],
            "mins": [],
            "maxs": [],
            "stds": [],
        })

        for fp in fingerprints:
            for metric in fp.dominant_metrics + fp.secondary_metrics:
                mstats = stats[metric.metric_id]
                mstats["ranges"].append(metric.range)
                mstats["means"].append(metric.mean)
                mstats["mins"].append(metric.min)
                mstats["maxs"].append(metric.max)
                mstats["stds"].append(metric.std)

        # 计算聚合统计
        aggregated = {}
        for metric_id, mstats in stats.items():
            if not mstats["ranges"]:
                continue

            aggregated[metric_id] = {
                "mean_range": np.mean(mstats["ranges"]),
                "std_range": np.std(mstats["ranges"]),
                "min_range": np.min(mstats["ranges"]),
                "max_range": np.max(mstats["ranges"]),
                "mean_of_means": np.mean(mstats["means"]),
                "std_of_means": np.std(mstats["means"]),
                "global_min": np.min(mstats["mins"]),
                "global_max": np.max(mstats["maxs"]),
                "mean_std": np.mean(mstats["stds"]),
                "sample_count": len(mstats["ranges"]),
                # 计算金标准范围 (mean ± 2*std)
                "gold_standard_low": np.mean(mstats["means"]) - 2 * np.std(mstats["means"]),
                "gold_standard_high": np.mean(mstats["means"]) + 2 * np.std(mstats["means"]),
            }

        return aggregated

    def _discover_error_patterns(
        self,
        standard_stats: Dict[str, Dict],
        error_fingerprints: List[ActionFingerprint],
        error_type: str
    ) -> List[ErrorPattern]:
        """发现错误模式."""
        patterns = []

        # 收集错误样本的指标
        error_metrics = defaultdict(list)
        for fp in error_fingerprints:
            for metric in fp.dominant_metrics + fp.secondary_metrics:
                error_metrics[metric.metric_id].append(metric)

        # 对比每个指标
        for metric_id, std_stat in standard_stats.items():
            if metric_id not in error_metrics:
                continue

            err_metrics = error_metrics[metric_id]
            if len(err_metrics) < self.params["min_support"]:
                continue

            # 分析偏离方向
            pattern = self._analyze_deviation(
                metric_id,
                std_stat,
                err_metrics,
                error_type
            )

            if pattern:
                patterns.append(pattern)

        return patterns

    def _analyze_deviation(
        self,
        metric_id: str,
        std_stat: Dict,
        err_metrics: List[MetricFingerprint],
        error_type: str
    ) -> Optional[ErrorPattern]:
        """分析偏离特征."""
        # 计算错误样本的统计
        err_means = [m.mean for m in err_metrics]
        err_mins = [m.min for m in err_metrics]
        err_maxs = [m.max for m in err_metrics]

        err_mean = np.mean(err_means)
        err_min = np.min(err_mins)
        err_max = np.max(err_maxs)

        std_mean = std_stat["mean_of_means"]
        std_low = std_stat["gold_standard_low"]
        std_high = std_stat["gold_standard_high"]

        # 判断偏离方向
        # 情况1: 错误样本均值高于标准上限
        if err_mean > std_high:
            deviation = err_mean - std_high
            separation = deviation / (std_stat["std_of_means"] + 1e-6)

            if separation >= self.params["min_separation"]:
                # 建议使用上限作为阈值
                threshold = std_high * self.params["safety_margin"]
                confidence = min(0.95, 0.5 + separation * 0.2)

                return ErrorPattern(
                    metric_id=metric_id,
                    metric_name=err_metrics[0].metric_name,
                    error_type=error_type,
                    deviation_direction="high",
                    deviation_magnitude=deviation,
                    suggested_threshold=threshold,
                    operator="gt",
                    confidence=confidence,
                    support=len(err_metrics),
                )

        # 情况2: 错误样本均值低于标准下限
        elif err_mean < std_low:
            deviation = std_low - err_mean
            separation = deviation / (std_stat["std_of_means"] + 1e-6)

            if separation >= self.params["min_separation"]:
                # 建议使用下限作为阈值
                threshold = std_low / self.params["safety_margin"]
                confidence = min(0.95, 0.5 + separation * 0.2)

                return ErrorPattern(
                    metric_id=metric_id,
                    metric_name=err_metrics[0].metric_name,
                    error_type=error_type,
                    deviation_direction="low",
                    deviation_magnitude=deviation,
                    suggested_threshold=threshold,
                    operator="lt",
                    confidence=confidence,
                    support=len(err_metrics),
                )

        # 情况3: 错误样本的范围超出标准范围
        err_range = err_max - err_min
        std_range = std_stat["mean_range"]

        if err_range > std_range * 1.5:  # 错误样本变化幅度大得多
            # 这可能表示动作不稳定
            pass

        return None

    def _pattern_to_condition(
        self,
        pattern: ErrorPattern,
        error_type: str
    ) -> Optional[ErrorCondition]:
        """将错误模式转换为ErrorCondition."""
        # 生成错误ID
        error_id = f"{error_type}_{pattern.deviation_direction}_{pattern.metric_id}"

        # 生成错误名称
        direction_name = "过大" if pattern.deviation_direction == "high" else "过小"
        error_name = f"{pattern.metric_name}{direction_name}"

        # 生成描述
        description = (
            f"检测到{error_type}: "
            f"{pattern.metric_name}数值{direction_name} "
            f"(阈值: {pattern.suggested_threshold:.1f}, "
            f"置信度: {pattern.confidence:.2f})"
        )

        # 确定严重程度
        if pattern.confidence > 0.9:
            severity = "high"
        elif pattern.confidence > 0.75:
            severity = "medium"
        else:
            severity = "low"

        return ErrorCondition(
            error_id=error_id,
            error_name=error_name,
            description=description,
            severity=severity,
            condition={
                "operator": pattern.operator,
                "value": round(pattern.suggested_threshold, 2),
                "metric_id": pattern.metric_id,
            },
            # 保留向后兼容的简单阈值
            threshold_high=pattern.suggested_threshold if pattern.operator == "gt" else None,
            threshold_low=pattern.suggested_threshold if pattern.operator == "lt" else None,
        )

    def learn_from_labeled_dataset(
        self,
        labeled_fingerprints: List[Tuple[ActionFingerprint, List[str]]]
    ) -> Dict[str, List[ErrorCondition]]:
        """从带标签的数据集中学习所有错误条件.

        Args:
            labeled_fingerprints: (指纹, 标签列表) 的列表

        Returns:
            错误类型到条件列表的映射
        """
        # 分离标准动作和错误动作
        standard_fps = []
        error_by_type = defaultdict(list)

        for fp, tags in labeled_fingerprints:
            if "standard" in tags:
                standard_fps.append(fp)
            else:
                for tag in tags:
                    if tag.startswith("error:"):
                        error_type = tag[6:]
                        error_by_type[error_type].append(fp)

        # 为每种错误类型学习条件
        all_conditions = {}
        for error_type, error_fps in error_by_type.items():
            conditions = self.learn_error_conditions(
                standard_fps, error_fps, error_type
            )
            if conditions:
                all_conditions[error_type] = conditions

        return all_conditions
