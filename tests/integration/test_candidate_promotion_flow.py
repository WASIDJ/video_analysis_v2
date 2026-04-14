"""candidate 发布与回滚集成测试."""

from src.core.dataset.feedback_loop import FeedbackLoop
from src.core.dataset.models import VideoSample
from src.core.dataset.repository import DatasetRepository
from src.core.iteration.evaluator import UnifiedEvaluator
from src.core.iteration.models import EvaluationSampleResult, ModelEvaluation
from src.core.iteration.orchestrator import IterationOrchestrator
from src.core.iteration.versioning import VersionStore


def make_evaluation(version_id: str, overall_score: float) -> ModelEvaluation:
    """构造测试用评估结果."""
    return ModelEvaluation(
        version_id=version_id,
        action_id="squat",
        overall_score=overall_score,
        metric_scores={"f1": overall_score},
        dataset_version="dataset-v1",
        config_version=f"config-{version_id}",
        sample_results=[
            EvaluationSampleResult(
                sample_id="sample-feedback",
                confidence=0.45,
                predicted_label="standard",
                expected_label="standard",
                source_version=version_id,
            )
        ],
    )


class TestCandidatePromotionFlow:
    """测试 candidate 发布/回滚闭环."""

    def test_promotes_candidate_and_enqueues_feedback_samples(self, tmp_path):
        """candidate 提升时应被激活，并把反馈样本回流."""
        repository = DatasetRepository()
        repository.add_sample(
            VideoSample("sample-feedback", "squat", "standard", "/tmp/sample-feedback.mp4")
        )
        version_store = VersionStore(tmp_path / "versions.json")
        version_store.register_version("squat", "baseline-v1", "dataset-v1", "config-v1", {"f1": 0.80}, status="baseline")
        version_store.register_version("squat", "candidate-v2", "dataset-v1", "config-v2", {"f1": 0.88}, status="candidate")

        orchestrator = IterationOrchestrator(
            evaluator=UnifiedEvaluator(low_confidence_threshold=0.6),
            version_store=version_store,
            feedback_loop=FeedbackLoop(repository, low_confidence_threshold=0.6),
        )

        decision = orchestrator.process_candidate(
            action_id="squat",
            baseline=make_evaluation("baseline-v1", 0.80),
            candidate=make_evaluation("candidate-v2", 0.88),
        )

        assert decision.should_promote is True
        assert version_store.get_active_version("squat").version_id == "candidate-v2"
        assert repository.require_record("sample-feedback").status == "queued_for_retraining"

    def test_rejects_candidate_and_rolls_back_to_baseline(self, tmp_path):
        """candidate 退化时应保留 baseline 为激活版本."""
        repository = DatasetRepository()
        repository.add_sample(
            VideoSample("sample-feedback", "squat", "standard", "/tmp/sample-feedback.mp4")
        )
        version_store = VersionStore(tmp_path / "versions.json")
        version_store.register_version("squat", "baseline-v1", "dataset-v1", "config-v1", {"f1": 0.90}, status="baseline")
        version_store.register_version("squat", "candidate-v2", "dataset-v1", "config-v2", {"f1": 0.85}, status="candidate")

        orchestrator = IterationOrchestrator(
            evaluator=UnifiedEvaluator(low_confidence_threshold=0.6),
            version_store=version_store,
            feedback_loop=FeedbackLoop(repository, low_confidence_threshold=0.6),
        )

        decision = orchestrator.process_candidate(
            action_id="squat",
            baseline=make_evaluation("baseline-v1", 0.90),
            candidate=make_evaluation("candidate-v2", 0.85),
        )

        assert decision.should_promote is False
        assert version_store.get_active_version("squat").version_id == "baseline-v1"
