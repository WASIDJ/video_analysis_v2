"""统一评估器单元测试."""

from src.core.iteration.evaluator import UnifiedEvaluator
from src.core.iteration.models import EvaluationSampleResult, ModelEvaluation


def build_evaluation(
    version_id: str,
    overall_score: float,
    *,
    dataset_version: str = "dataset-v1",
    config_version: str = "config-v1",
    metric_scores: dict[str, float] | None = None,
    sample_results: list[EvaluationSampleResult] | None = None,
) -> ModelEvaluation:
    """构造测试用评估结果."""
    return ModelEvaluation(
        version_id=version_id,
        action_id="squat",
        overall_score=overall_score,
        metric_scores=metric_scores or {"f1": overall_score},
        sample_results=sample_results or [],
        dataset_version=dataset_version,
        config_version=config_version,
    )


class TestUnifiedEvaluator:
    """测试统一评估器."""

    def test_promotes_candidate_when_score_improves(self):
        """candidate 分数提升时应允许发布."""
        evaluator = UnifiedEvaluator(low_confidence_threshold=0.6)
        baseline = build_evaluation("baseline-v1", 0.80)
        candidate = build_evaluation("candidate-v2", 0.88)

        decision = evaluator.compare(baseline, candidate)

        assert decision.should_promote is True
        assert decision.improvement == 0.08
        assert decision.dataset_version == "dataset-v1"
        assert decision.baseline_version == "baseline-v1"
        assert decision.candidate_version == "candidate-v2"

    def test_rejects_candidate_when_metric_regresses(self):
        """关键指标退化时应拒绝发布."""
        evaluator = UnifiedEvaluator(required_metric_improvements={"f1": 0.0, "precision": 0.0})
        baseline = build_evaluation("baseline-v1", 0.90, metric_scores={"f1": 0.90, "precision": 0.92})
        candidate = build_evaluation("candidate-v2", 0.91, metric_scores={"f1": 0.91, "precision": 0.88})

        decision = evaluator.compare(baseline, candidate)

        assert decision.should_promote is False
        assert decision.regressions == ["precision"]

    def test_collects_feedback_records_from_low_confidence_and_misclassified_samples(self):
        """评估器应提取低置信和误判样本用于回流."""
        evaluator = UnifiedEvaluator(low_confidence_threshold=0.6)
        candidate = build_evaluation(
            "candidate-v2",
            0.85,
            sample_results=[
                EvaluationSampleResult(
                    sample_id="sample-low",
                    confidence=0.4,
                    predicted_label="standard",
                    expected_label="standard",
                    source_version="candidate-v2",
                ),
                EvaluationSampleResult(
                    sample_id="sample-mis",
                    confidence=0.9,
                    predicted_label="error:knee_valgus",
                    expected_label="standard",
                    source_version="candidate-v2",
                ),
            ],
        )

        records = evaluator.collect_feedback_records(candidate)

        assert {record.sample_id for record in records} == {"sample-low", "sample-mis"}
        assert {record.reason for record in records} == {"low_confidence", "misclassified"}

