"""数据集拆分器单元测试."""

from src.core.dataset.models import VideoSample
from src.core.dataset.splitter import DatasetSplitter


def make_samples(action_id: str, label: str, count: int) -> list[VideoSample]:
    """构造一组测试视频样本."""
    return [
        VideoSample(
            sample_id=f"{action_id}-{label}-{index}",
            action_id=action_id,
            label=label,
            video_path=f"/tmp/{action_id}-{label}-{index}.mp4",
        )
        for index in range(count)
    ]


class TestDatasetSplitter:
    """测试数据集拆分器."""

    def test_split_stratifies_by_action_and_label(self):
        """拆分结果应按 action_id + label 分层保持比例."""
        splitter = DatasetSplitter(train_ratio=0.5, validation_ratio=0.25, test_ratio=0.25, random_seed=7)
        samples = []
        samples.extend(make_samples("squat", "standard", 8))
        samples.extend(make_samples("squat", "error:knee_valgus", 8))
        samples.extend(make_samples("lunge", "standard", 8))

        split = splitter.split(samples)

        assert len(split.train) == 12
        assert len(split.validation) == 6
        assert len(split.test) == 6
        assert split.count_by_group(split.train)[("squat", "standard")] == 4
        assert split.count_by_group(split.validation)[("squat", "standard")] == 2
        assert split.count_by_group(split.test)[("squat", "standard")] == 2
        assert split.count_by_group(split.train)[("squat", "error:knee_valgus")] == 4
        assert split.count_by_group(split.train)[("lunge", "standard")] == 4

    def test_split_is_deterministic_with_same_seed(self):
        """相同随机种子应产生稳定拆分结果."""
        samples = make_samples("squat", "standard", 8) + make_samples("squat", "error:knee_valgus", 8)

        first = DatasetSplitter(random_seed=11).split(samples)
        second = DatasetSplitter(random_seed=11).split(samples)

        assert [sample.sample_id for sample in first.train] == [sample.sample_id for sample in second.train]
        assert [sample.sample_id for sample in first.validation] == [sample.sample_id for sample in second.validation]
        assert [sample.sample_id for sample in first.test] == [sample.sample_id for sample in second.test]

    def test_split_keeps_samples_disjoint_across_partitions(self):
        """同一 sample_id 不应同时出现在多个分区."""
        splitter = DatasetSplitter(random_seed=5)
        samples = make_samples("squat", "standard", 12)

        split = splitter.split(samples)

        train_ids = {sample.sample_id for sample in split.train}
        validation_ids = {sample.sample_id for sample in split.validation}
        test_ids = {sample.sample_id for sample in split.test}

        assert train_ids.isdisjoint(validation_ids)
        assert train_ids.isdisjoint(test_ids)
        assert validation_ids.isdisjoint(test_ids)

    def test_split_preserves_small_group_coverage(self):
        """小样本分组也应尽量覆盖 train/validation/test."""
        splitter = DatasetSplitter(train_ratio=0.5, validation_ratio=0.25, test_ratio=0.25, random_seed=3)
        samples = make_samples("plank", "standard", 3)

        split = splitter.split(samples)

        assert len(split.train) == 1
        assert len(split.validation) == 1
        assert len(split.test) == 1
