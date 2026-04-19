"""检测项选择器 - 筛选最优检测项组合.

限制 max_metrics_per_action=6，按区分度和稳定性排序.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import logging
from scipy.stats import pearsonr

logger = logging.getLogger(__name__)


@dataclass
class MetricScore:
    """检测项评分."""
    metric_id: str
    stability_score: float  # 稳定性 (0-1)
    discrimination_score: float  # 区分度 (0-1)
    interpretability_score: float  # 可解释性 (0-1)
    cycle_correlation: float  # 与周期信号的相关性
    error_separation: float  # 标准/错误分离度
    redundancy_score: float  # 冗余度 (与其他指标的相关性)
    overall_score: float  # 综合评分
    reason: str = ""  # 入选/剔除原因


@dataclass
class MetricSelectionResult:
    """检测项选择结果."""
    core_metrics: List[str]  # 核心指标（用于计数和错误识别）
    aux_metrics: List[str]  # 辅助指标（仅用于分析）
    rejected_metrics: List[Tuple[str, str]]  # 被剔除的指标及原因
    selection_info: Dict[str, Any]  # 选择过程信息


class MetricSelector:
    """
    检测项选择器.

    规则：
    1. max_metrics_per_action = 6
    2. 保留：稳定性高 + 区分度高 + 可解释性高
    3. 去冗余：高相关指标只留一个（相关阈值 > 0.9）
    """

    MAX_METRICS = 6
    CORRELATION_THRESHOLD = 0.9  # 冗余判定阈值
    MIN_STABILITY = 0.3  # 最低稳定性门槛
    MIN_DISCRIMINATION = 0.2  # 最低区分度门槛

    def __init__(
        self,
        max_metrics: int = 6,
        correlation_threshold: float = 0.9,
    ):
        self.max_metrics = max_metrics
        self.correlation_threshold = correlation_threshold

    def select_metrics(
        self,
        metric_values: Dict[str, np.ndarray],
        labels: Optional[List[str]] = None,
        cycle_signal: Optional[np.ndarray] = None,
    ) -> MetricSelectionResult:
        """
        选择最优检测项组合.

        Args:
            metric_values: 检测项时序值 {metric_id: values_array}
            labels: 样本标签列表（用于计算区分度）
            cycle_signal: 周期信号（用于计算相关性）

        Returns:
            MetricSelectionResult
        """
        if not metric_values:
            return MetricSelectionResult(
                core_metrics=[],
                aux_metrics=[],
                rejected_metrics=[],
                selection_info={"error": "No metrics provided"},
            )

        # 1. 计算每个检测项的评分
        scores = self._score_metrics(metric_values, labels, cycle_signal)

        # 2. 过滤不满足最低门槛的指标
        filtered_scores = self._filter_by_threshold(scores)

        # 3. 去冗余（高相关只保留一个）
        core_metrics, rejected = self._remove_redundancy(
            filtered_scores, metric_values
        )

        # 4. 限制数量
        core_metrics, aux_metrics, rejected = self._limit_count(
            core_metrics, rejected
        )

        # 5. 构建结果
        selection_info = {
            "total_candidates": len(metric_values),
            "scored_metrics": len(scores),
            "passed_threshold": len(filtered_scores),
            "final_core": len(core_metrics),
            "final_aux": len(aux_metrics),
            "scoring_details": [
                {
                    "metric_id": s.metric_id,
                    "stability": round(s.stability_score, 3),
                    "discrimination": round(s.discrimination_score, 3),
                    "overall": round(s.overall_score, 3),
                    "reason": s.reason,
                }
                for s in scores
            ],
        }

        return MetricSelectionResult(
            core_metrics=core_metrics,
            aux_metrics=aux_metrics,
            rejected_metrics=rejected,
            selection_info=selection_info,
        )

    def _score_metrics(
        self,
        metric_values: Dict[str, np.ndarray],
        labels: Optional[List[str]],
        cycle_signal: Optional[np.ndarray],
    ) -> List[MetricScore]:
        """计算每个检测项的评分."""
        scores = []

        for metric_id, values in metric_values.items():
            # 稳定性评分（基于变异系数）
            stability = self._calculate_stability(values)

            # 区分度评分（基于标准/错误分离）
            discrimination = self._calculate_discrimination(values, labels)

            # 可解释性评分（基于是否是标准生物力学指标）
            interpretability = self._calculate_interpretability(metric_id)

            # 与周期的相关性
            cycle_corr = 0.0
            if cycle_signal is not None and len(values) == len(cycle_signal):
                try:
                    cycle_corr, _ = pearsonr(values, cycle_signal)
                    cycle_corr = abs(cycle_corr)
                except Exception:
                    pass

            # 错误分离度
            error_sep = discrimination  # 简化为与区分度相同

            # 综合评分
            overall = (
                stability * 0.3
                + discrimination * 0.3
                + interpretability * 0.2
                + cycle_corr * 0.2
            )

            scores.append(
                MetricScore(
                    metric_id=metric_id,
                    stability_score=stability,
                    discrimination_score=discrimination,
                    interpretability_score=interpretability,
                    cycle_correlation=cycle_corr,
                    error_separation=error_sep,
                    redundancy_score=0.0,  # 稍后计算
                    overall_score=overall,
                )
            )

        # 按综合评分排序
        scores.sort(key=lambda x: x.overall_score, reverse=True)

        return scores

    def _calculate_stability(self, values: np.ndarray) -> float:
        """计算稳定性评分（基于变异系数）."""
        if len(values) == 0:
            return 0.0

        mean = np.mean(values)
        std = np.std(values)

        if mean == 0:
            return 0.0

        cv = std / abs(mean)  # 变异系数
        stability = max(0.0, 1.0 - cv)  # CV越小越稳定

        return stability

    def _calculate_discrimination(
        self, values: np.ndarray, labels: Optional[List[str]]
    ) -> float:
        """计算区分度评分."""
        if labels is None or len(set(labels)) < 2:
            # 没有标签，使用基于范围的区分度
            range_val = np.max(values) - np.min(values)
            mean_val = np.mean(np.abs(values))
            if mean_val == 0:
                return 0.0
            return min(1.0, range_val / mean_val)

        # 基于标签的区分度（标准 vs 错误）
        standard_values = [v for v, l in zip(values, labels) if l == "standard"]
        error_values = [v for v, l in zip(values, labels) if l != "standard"]

        if not standard_values or not error_values:
            return 0.5

        std_mean = np.mean(standard_values)
        err_mean = np.mean(error_values)
        std_std = np.std(standard_values) if len(standard_values) > 1 else 1.0
        err_std = np.std(error_values) if len(error_values) > 1 else 1.0

        # Cohen's d effect size
        pooled_std = np.sqrt((std_std**2 + err_std**2) / 2)
        if pooled_std == 0:
            return 0.0

        cohens_d = abs(std_mean - err_mean) / pooled_std
        # 归一化到 0-1
        discrimination = min(1.0, cohens_d / 2.0)

        return discrimination

    def _calculate_interpretability(self, metric_id: str) -> float:
        """计算可解释性评分."""
        # 优先保留生物力学意义明确的指标
        high_interpretability = [
            "knee_flexion",
            "hip_flexion",
            "trunk_lean",
            "hip_abduction",
            "leg_elevation_height",
            "ankle_dorsiflexion",
        ]

        medium_interpretability = [
            "knee_valgus",
            "pelvic_tilt",
            "trunk_lateral_flexion",
            "pelvic_obliquity",
        ]

        if any(m in metric_id for m in high_interpretability):
            return 1.0
        elif any(m in metric_id for m in medium_interpretability):
            return 0.7
        else:
            return 0.5

    def _filter_by_threshold(self, scores: List[MetricScore]) -> List[MetricScore]:
        """过滤不满足最低门槛的指标."""
        filtered = []

        for score in scores:
            if score.stability_score < self.MIN_STABILITY:
                score.reason = f"稳定性不足 ({score.stability_score:.2f} < {self.MIN_STABILITY})"
            elif score.discrimination_score < self.MIN_DISCRIMINATION:
                score.reason = f"区分度不足 ({score.discrimination_score:.2f} < {self.MIN_DISCRIMINATION})"
            else:
                filtered.append(score)

        return filtered

    def _remove_redundancy(
        self,
        scores: List[MetricScore],
        metric_values: Dict[str, np.ndarray],
    ) -> Tuple[List[str], List[Tuple[str, str]]]:
        """去除冗余指标（高相关只保留一个）."""
        core_metrics = []
        rejected = []

        selected_indices = set()

        for i, score in enumerate(scores):
            if i in selected_indices:
                continue

            metric_id = score.metric_id

            # 检查与已选指标的相关性
            is_redundant = False
            values_i = metric_values[metric_id]

            for j, selected_idx in enumerate(selected_indices):
                selected_metric = scores[selected_idx].metric_id
                values_j = metric_values[selected_metric]

                # 计算相关性
                if len(values_i) == len(values_j):
                    try:
                        corr, _ = pearsonr(values_i, values_j)
                        if abs(corr) > self.correlation_threshold:
                            is_redundant = True
                            rejected.append(
                                (metric_id, f"与 {selected_metric} 高相关 ({corr:.2f})")
                            )
                            break
                    except Exception:
                        pass

            if not is_redundant:
                core_metrics.append(metric_id)
                selected_indices.add(i)

        return core_metrics, rejected

    def _limit_count(
        self,
        core_metrics: List[str],
        rejected: List[Tuple[str, str]],
    ) -> Tuple[List[str], List[str], List[Tuple[str, str]]]:
        """限制指标数量."""
        if len(core_metrics) <= self.max_metrics:
            return core_metrics, [], rejected

        # 超出限制，将多余的移到 aux
        final_core = core_metrics[: self.max_metrics]
        aux_metrics = core_metrics[self.max_metrics :]

        # 记录被移入 aux 的原因
        for metric_id in aux_metrics:
            rejected.append((metric_id, "超出核心指标数量限制，降级为辅助指标"))

        return final_core, aux_metrics, rejected
