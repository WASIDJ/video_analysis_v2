"""反馈回流集成测试."""

from src.core.dataset.feedback_loop import FeedbackLoop
from src.core.dataset.models import VideoSample
from src.core.dataset.repository import DatasetRepository
from src.core.iteration.evaluator import UnifiedEvaluator
from src.core.iteration.models import EvaluationSampleResult, ModelEvaluation


class TestFeedbackFlow:
    """测试 evaluator -> feedback loop -> repository 的集成流."""

    def test_evaluation_feedback_is_enqueued_and_available_for_next_iteration(self):
        """低置信和误判样本应被回流并进入下一轮训练候选."""
        repository = DatasetRepository()
        repository.add_sample(VideoSample("sample-low", "squat", "standard", "/tmp/sample-low.mp4"))
        repository.add_sample(VideoSample("sample-mis", "squat", "standard", "/tmp/sample-mis.mp4"))

        evaluator = UnifiedEvaluator(low_confidence_threshold=0.6)
        feedback_loop = FeedbackLoop(repository, low_confidence_threshold=0.6, annotation_threshold=2)

        evaluation = ModelEvaluation(
            version_id="candidate-v2",
            action_id="squat",
            overall_score=0.87,
            metric_scores={"f1": 0.87},
            dataset_version="dataset-v2",
            config_version="config-v2",
            sample_results=[
                EvaluationSampleResult(
                    sample_id="sample-low",
                    confidence=0.41,
                    predicted_label="standard",
                    expected_label="standard",
                    source_version="candidate-v2",
                ),
                EvaluationSampleResult(
                    sample_id="sample-mis",
                    confidence=0.91,
                    predicted_label="error:knee_valgus",
                    expected_label="standard",
                    source_version="candidate-v2",
                ),
            ],
        )

        for feedback in evaluator.collect_feedback_records(evaluation):
            feedback_loop.process_feedback(feedback)

        iteration_samples = repository.list_samples_for_iteration("squat")

        assert {sample.sample_id for sample in iteration_samples} == {"sample-low", "sample-mis"}
        assert repository.require_record("sample-low").status == "queued_for_retraining"
        assert repository.require_record("sample-mis").status == "queued_for_retraining"
