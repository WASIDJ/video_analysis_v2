"""数据集仓储单元测试."""

from src.core.dataset.models import FeedbackRecord, VideoSample
from src.core.dataset.repository import DatasetRepository


class TestDatasetRepository:
    """测试数据集仓储."""

    def test_save_and_load_preserves_sample_state(self, tmp_path):
        """仓储序列化后应保留样本状态和反馈历史."""
        storage_path = tmp_path / "dataset_repository.json"
        repository = DatasetRepository(storage_path=storage_path)
        record = repository.add_sample(
            VideoSample(
                sample_id="sample-001",
                action_id="squat",
                label="standard",
                video_path="/tmp/sample-001.mp4",
            )
        )
        record.status = "queued_for_retraining"
        record.tags.append("confusing_sample")
        record.misclassification_count = 2
        record.feedback_history.append(
            FeedbackRecord(
                sample_id="sample-001",
                confidence=0.42,
                source_version="candidate-v1",
                reason="low_confidence",
            )
        )

        repository.save()
        restored = DatasetRepository.load(storage_path)
        restored_record = restored.require_record("sample-001")

        assert restored_record.status == "queued_for_retraining"
        assert restored_record.tags == ["confusing_sample"]
        assert restored_record.misclassification_count == 2
        assert restored_record.feedback_history[0].source_version == "candidate-v1"

    def test_list_samples_for_iteration_excludes_pending_annotation(self):
        """下一轮训练候选样本应排除 pending_annotation."""
        repository = DatasetRepository()
        repository.add_sample(
            VideoSample("ready-1", "squat", "standard", "/tmp/ready-1.mp4")
        )
        queued = repository.add_sample(
            VideoSample("queue-1", "squat", "standard", "/tmp/queue-1.mp4")
        )
        pending = repository.add_sample(
            VideoSample("pending-1", "squat", "standard", "/tmp/pending-1.mp4")
        )
        queued.status = "queued_for_retraining"
        pending.status = "pending_annotation"

        candidates = repository.list_samples_for_iteration(action_id="squat")

        assert [sample.sample_id for sample in candidates] == ["queue-1", "ready-1"]

