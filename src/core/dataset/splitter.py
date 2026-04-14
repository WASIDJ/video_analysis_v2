"""按 action_id + label 分层拆分数据集."""

from __future__ import annotations

from collections import defaultdict
import math
import random

from .models import DatasetSplit, VideoSample


class DatasetSplitter:
    """训练集/验证集/测试集拆分器."""

    def __init__(
        self,
        train_ratio: float = 0.7,
        validation_ratio: float = 0.15,
        test_ratio: float = 0.15,
        random_seed: int = 42,
    ) -> None:
        total_ratio = train_ratio + validation_ratio + test_ratio
        if not math.isclose(total_ratio, 1.0, rel_tol=1e-6, abs_tol=1e-6):
            raise ValueError("train_ratio + validation_ratio + test_ratio 必须等于 1.0")

        self.train_ratio = train_ratio
        self.validation_ratio = validation_ratio
        self.test_ratio = test_ratio
        self.random_seed = random_seed

    def split(self, samples: list[VideoSample]) -> DatasetSplit:
        """按 action_id + label 分层拆分样本."""
        grouped_samples: dict[tuple[str, str], list[VideoSample]] = defaultdict(list)
        for sample in samples:
            grouped_samples[(sample.action_id, sample.label)].append(sample)

        result = DatasetSplit()
        for group_key in sorted(grouped_samples):
            group_samples = sorted(grouped_samples[group_key], key=lambda sample: sample.sample_id)
            randomizer = random.Random(f"{self.random_seed}:{group_key[0]}:{group_key[1]}")
            randomizer.shuffle(group_samples)

            train_count, validation_count, test_count = self._allocate_counts(len(group_samples))

            result.train.extend(group_samples[:train_count])
            result.validation.extend(group_samples[train_count:train_count + validation_count])
            result.test.extend(group_samples[train_count + validation_count:train_count + validation_count + test_count])

        return result

    def _allocate_counts(self, sample_count: int) -> tuple[int, int, int]:
        """根据比例分配组内样本数."""
        if sample_count <= 0:
            return 0, 0, 0

        split_order = ("train", "validation", "test")
        ratios = {
            "train": self.train_ratio,
            "validation": self.validation_ratio,
            "test": self.test_ratio,
        }
        raw_counts = {name: sample_count * ratio for name, ratio in ratios.items()}
        counts = {name: math.floor(raw_counts[name]) for name in split_order}

        assigned = sum(counts.values())
        remaining = sample_count - assigned

        priorities = sorted(
            split_order,
            key=lambda name: (raw_counts[name] - counts[name], ratios[name], name),
            reverse=True,
        )
        for index in range(remaining):
            counts[priorities[index % len(priorities)]] += 1

        if sample_count >= 1 and counts["train"] == 0:
            donor = "validation" if counts["validation"] >= counts["test"] else "test"
            if counts[donor] > 0:
                counts[donor] -= 1
                counts["train"] += 1

        return counts["train"], counts["validation"], counts["test"]
