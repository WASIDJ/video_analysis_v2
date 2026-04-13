"""反馈回流单元测试."""

from src.core.dataset.feedback_loop import FeedbackLoop
from src.core.dataset.models import FeedbackRecord, VideoSample
from src.core.dataset.repository import DatasetRepository


def build_repository() -> DatasetRepository:
    """构造包含单个样本的仓库."""
    repository = DatasetRepository()
    repository.add_sample(
        VideoSample(
            sample_id="sample-001",
            action_id="squat",
            label="standard",
            video_path="/tmp/sample-001.mp4",
        )
    )
    return repository


class TestFeedbackLoop:
    """测试反馈回流."""

    def test_low_confidence_sample_is_tagged_as_confusing(self):
        """低置信样本应被标记为 confusing_sample 并入回流队列."""
        repository = build_repository()
        feedback_loop = FeedbackLoop(repository, low_confidence_threshold=0.6)

        record = feedback_loop.process_feedback(
            FeedbackRecord(
                sample_id="sample-001",
                confidence=0.4,
                source_version="model-v1",
                reason="low_confidence",
            )
        )

        assert record.status == "queued_for_retraining"
        assert "confusing_sample" in record.tags
        assert record.source_version == "model-v1"

    def test_misclassified_sample_keeps_source_version_for_retraining(self):
        """误判样本应记录来源版本并进入回流队列."""
        repository = build_repository()
        feedback_loop = FeedbackLoop(repository)

        record = feedback_loop.process_feedback(
            FeedbackRecord(
                sample_id="sample-001",
                confidence=0.9,
                predicted_label="error:knee_valgus",
                expected_label="standard",
                source_version="candidate-v2",
                reason="misclassified",
            )
        )

        assert record.status == "queued_for_retraining"
        assert record.misclassification_count == 1
        assert record.source_version == "candidate-v2"

    def test_repeated_misclassification_moves_sample_to_pending_annotation(self):
        """多轮误判后样本应转入待标注池."""
        repository = build_repository()
        feedback_loop = FeedbackLoop(repository, annotation_threshold=3)

        for _ in range(3):
            record = feedback_loop.process_feedback(
                FeedbackRecord(
                    sample_id="sample-001",
                    confidence=0.95,
                    predicted_label="error:knee_valgus",
                    expected_label="standard",
                    source_version="baseline-v1",
                    reason="misclassified",
                )
            )

        annotation_tasks = repository.list_annotation_tasks()

        assert record.status == "pending_annotation"
        assert "pending_annotation" in record.tags
        assert len(annotation_tasks) == 1
        assert annotation_tasks[0].sample_id == "sample-001"
        assert annotation_tasks[0].source_version == "baseline-v1"

    def test_pending_annotation_sample_is_not_enqueued_twice(self):
        """已进入待标注池的样本不应重复创建标注任务."""
        repository = build_repository()
        feedback_loop = FeedbackLoop(repository, annotation_threshold=1)

        feedback = FeedbackRecord(
            sample_id="sample-001",
            confidence=0.95,
            predicted_label="error:knee_valgus",
            expected_label="standard",
            source_version="baseline-v1",
            reason="misclassified",
        )

        feedback_loop.process_feedback(feedback)
        record = feedback_loop.process_feedback(feedback)

        assert record.status == "pending_annotation"
        assert len(repository.list_annotation_tasks()) == 1
