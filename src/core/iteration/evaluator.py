"""统一评估器."""

from __future__ import annotations

from .models import EvaluationDecision, EvaluationSampleResult, ModelEvaluation
from ..dataset.models import FeedbackRecord


class UnifiedEvaluator:
    """对比 baseline 与 candidate，并提取反馈样本."""

    def __init__(
        self,
        low_confidence_threshold: float = 0.5,
        required_metric_improvements: dict[str, float] | None = None,
    ) -> None:
        self.low_confidence_threshold = low_confidence_threshold
        self.required_metric_improvements = required_metric_improvements or {}

    def compare(self, baseline: ModelEvaluation, candidate: ModelEvaluation) -> EvaluationDecision:
        """对比两个版本的评估结果."""
        regressions: list[str] = []
        for metric_name, min_delta in self.required_metric_improvements.items():
            baseline_metric = baseline.metric_scores.get(metric_name)
            candidate_metric = candidate.metric_scores.get(metric_name)
            if baseline_metric is None or candidate_metric is None:
                continue
            if candidate_metric - baseline_metric < min_delta:
                regressions.append(metric_name)

        improvement = round(candidate.overall_score - baseline.overall_score, 10)
        should_promote = improvement > 0 and not regressions

        return EvaluationDecision(
            should_promote=should_promote,
            improvement=improvement,
            regressions=regressions,
            dataset_version=candidate.dataset_version,
            baseline_version=baseline.version_id,
            candidate_version=candidate.version_id,
        )

    def collect_feedback_records(self, evaluation: ModelEvaluation) -> list[FeedbackRecord]:
        """从评估结果中收集低置信和误判样本."""
        feedback_records: list[FeedbackRecord] = []
        for sample_result in evaluation.sample_results:
            reason = self._detect_feedback_reason(sample_result)
            if reason is None:
                continue

            feedback_records.append(
                FeedbackRecord(
                    sample_id=sample_result.sample_id,
                    confidence=sample_result.confidence,
                    predicted_label=sample_result.predicted_label,
                    expected_label=sample_result.expected_label,
                    source_version=sample_result.source_version,
                    reason=reason,
                )
            )

        return feedback_records

    def _detect_feedback_reason(self, sample_result: EvaluationSampleResult) -> str | None:
        """判断样本是否应被回流."""
        misclassified = sample_result.predicted_label != sample_result.expected_label
        if misclassified:
            return "misclassified"
        if sample_result.confidence < self.low_confidence_threshold:
            return "low_confidence"
        return None
