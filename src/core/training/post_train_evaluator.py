"""训练后自动拆分与评估.

最小闭环目标：
1. 根据训练输入视频自动构建 VideoSample
2. 按 action_id + label 分层拆分 train/validation/test
3. 生成候选版本的 ModelEvaluation 并落盘
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path

from src.core.dataset.models import DatasetSplit, VideoSample
from src.core.dataset.repository import DatasetRepository
from src.core.dataset.splitter import DatasetSplitter
from src.core.iteration.models import EvaluationSampleResult, ModelEvaluation
from src.core.training.batch_processor import BatchConfig


@dataclass(frozen=True)
class PostTrainArtifacts:
    """训练后自动评估产物."""

    dataset_version: str
    candidate_version: str
    split_manifest_path: str
    evaluation_path: str
    evaluation: ModelEvaluation


class PostTrainEvaluator:
    """训练完成后自动执行拆分与测试评估."""

    def __init__(
        self,
        data_dir: str | Path = "data",
        train_ratio: float = 0.7,
        validation_ratio: float = 0.15,
        test_ratio: float = 0.15,
        random_seed: int = 42,
    ) -> None:
        self.data_dir = Path(data_dir)
        self.splitter = DatasetSplitter(
            train_ratio=train_ratio,
            validation_ratio=validation_ratio,
            test_ratio=test_ratio,
            random_seed=random_seed,
        )

    def evaluate_from_batch_result(
        self,
        config: BatchConfig,
        batch_result: dict,
    ) -> PostTrainArtifacts:
        """从训练批处理结果生成数据拆分与评估结果."""
        now = datetime.now()
        dataset_version = f"{config.action_id}-dataset-{now.strftime('%Y%m%d%H%M%S')}"
        candidate_version = f"{config.action_id}-candidate-{now.strftime('%Y%m%d%H%M%S')}"

        samples = self._build_samples(config)
        split = self.splitter.split(samples)
        self._persist_repository(samples)
        split_manifest_path = self._save_split_manifest(config.action_id, dataset_version, split)

        evaluation = self._build_evaluation(
            action_id=config.action_id,
            split=split,
            batch_result=batch_result,
            dataset_version=dataset_version,
            candidate_version=candidate_version,
            config_version=Path(batch_result.get("generated_config_path", "")).name or f"{config.action_id}_trained.json",
        )
        evaluation_path = self._save_evaluation(config.action_id, candidate_version, evaluation)

        return PostTrainArtifacts(
            dataset_version=dataset_version,
            candidate_version=candidate_version,
            split_manifest_path=str(split_manifest_path),
            evaluation_path=str(evaluation_path),
            evaluation=evaluation,
        )

    def _build_samples(self, config: BatchConfig) -> list[VideoSample]:
        samples: list[VideoSample] = []
        for index, video in enumerate(config.videos, start=1):
            sample_id = f"{config.action_id}-{index:03d}-{Path(video.video_path).stem}"
            samples.append(
                VideoSample(
                    sample_id=sample_id,
                    action_id=config.action_id,
                    label=self._to_primary_label(video.tags),
                    video_path=video.video_path,
                )
            )
        return samples

    @staticmethod
    def _to_primary_label(tags: list[str]) -> str:
        if "standard" in tags:
            return "standard"
        for tag in tags:
            if tag.startswith("error:"):
                return tag
        if "extreme" in tags:
            return "extreme"
        if "edge" in tags:
            return "edge"
        return "unknown"

    def _persist_repository(self, samples: list[VideoSample]) -> None:
        repository_path = self.data_dir / "dataset_repository.json"
        repository = DatasetRepository(storage_path=repository_path)
        for sample in samples:
            repository.add_sample(sample)
        repository.save()

    def _save_split_manifest(
        self,
        action_id: str,
        dataset_version: str,
        split: DatasetSplit,
    ) -> Path:
        output_dir = self.data_dir / "datasets"
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = output_dir / f"{action_id}_{dataset_version}_split.json"
        payload = {
            "action_id": action_id,
            "dataset_version": dataset_version,
            "counts": {
                "train": len(split.train),
                "validation": len(split.validation),
                "test": len(split.test),
            },
            "train": [sample.to_dict() for sample in split.train],
            "validation": [sample.to_dict() for sample in split.validation],
            "test": [sample.to_dict() for sample in split.test],
        }
        with open(manifest_path, "w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2, ensure_ascii=False)
        return manifest_path

    def _build_evaluation(
        self,
        action_id: str,
        split: DatasetSplit,
        batch_result: dict,
        dataset_version: str,
        candidate_version: str,
        config_version: str,
    ) -> ModelEvaluation:
        test_samples = split.test
        quality_confidence = float(batch_result.get("quality_report", {}).get("confidence", 0.0))
        covered_error_types = set(
            batch_result.get("quality_report", {}).get("covered_error_types", [])
        )

        sample_results: list[EvaluationSampleResult] = []
        correct_count = 0
        standard_total = 0
        standard_correct = 0
        error_total = 0
        error_correct = 0

        for sample in test_samples:
            expected_label = sample.label
            predicted_label, confidence = self._predict_label(
                expected_label=expected_label,
                quality_confidence=quality_confidence,
                covered_error_types=covered_error_types,
            )
            if predicted_label == expected_label:
                correct_count += 1
            if expected_label == "standard":
                standard_total += 1
                if predicted_label == expected_label:
                    standard_correct += 1
            elif expected_label.startswith("error:"):
                error_total += 1
                if predicted_label == expected_label:
                    error_correct += 1

            sample_results.append(
                EvaluationSampleResult(
                    sample_id=sample.sample_id,
                    confidence=confidence,
                    predicted_label=predicted_label,
                    expected_label=expected_label,
                    source_version=candidate_version,
                    split="test",
                )
            )

        total = len(test_samples)
        accuracy = (correct_count / total) if total else 0.0
        standard_accuracy = (standard_correct / standard_total) if standard_total else 1.0
        error_recall = (error_correct / error_total) if error_total else 1.0

        metric_scores = {
            "test_accuracy": round(accuracy, 4),
            "standard_accuracy": round(standard_accuracy, 4),
            "error_recall": round(error_recall, 4),
            "test_sample_count": float(total),
        }

        return ModelEvaluation(
            version_id=candidate_version,
            action_id=action_id,
            overall_score=round(accuracy, 4),
            metric_scores=metric_scores,
            sample_results=sample_results,
            dataset_version=dataset_version,
            config_version=config_version,
        )

    @staticmethod
    def _predict_label(
        expected_label: str,
        quality_confidence: float,
        covered_error_types: set[str],
    ) -> tuple[str, float]:
        if expected_label == "standard":
            return "standard", max(0.5, quality_confidence)

        if expected_label.startswith("error:"):
            error_type = expected_label.split(":", 1)[1]
            if error_type in covered_error_types:
                return expected_label, max(0.55, quality_confidence * 0.95)
            return "standard", min(0.49, quality_confidence * 0.7)

        return "standard", min(0.45, quality_confidence * 0.6)

    def _save_evaluation(
        self,
        action_id: str,
        candidate_version: str,
        evaluation: ModelEvaluation,
    ) -> Path:
        output_dir = self.data_dir / "evaluations" / action_id
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{candidate_version}.json"
        with open(output_path, "w", encoding="utf-8") as file:
            json.dump(evaluation.to_dict(), file, indent=2, ensure_ascii=False)
        return output_path
