"""训练后自动评估单元测试."""

from src.core.training.batch_processor import BatchConfig
from src.core.training.pipeline import VideoTrainingConfig
from src.core.training.post_train_evaluator import PostTrainEvaluator


class TestPostTrainEvaluator:
    """测试训练后自动拆分与评估."""

    def test_generates_split_manifest_and_model_evaluation(self, tmp_path):
        """应落盘拆分清单和 ModelEvaluation."""
        config = BatchConfig(
            action_id="side_lift",
            action_name_zh="侧抬腿",
            videos=[
                VideoTrainingConfig(video_path="/tmp/std-1.mp4", tags=["standard"]),
                VideoTrainingConfig(video_path="/tmp/std-2.mp4", tags=["standard"]),
                VideoTrainingConfig(video_path="/tmp/std-3.mp4", tags=["standard"]),
                VideoTrainingConfig(video_path="/tmp/err-1.mp4", tags=["error:leg_low"]),
                VideoTrainingConfig(video_path="/tmp/err-2.mp4", tags=["error:leg_low"]),
                VideoTrainingConfig(video_path="/tmp/edge-1.mp4", tags=["edge"]),
            ],
        )
        batch_result = {
            "success": True,
            "generated_config_path": "config/action_configs/side_lift_trained.json",
            "quality_report": {
                "confidence": 0.85,
                "covered_error_types": ["leg_low"],
            },
        }

        evaluator = PostTrainEvaluator(
            data_dir=tmp_path,
            train_ratio=0.5,
            validation_ratio=0.25,
            test_ratio=0.25,
            random_seed=7,
        )
        artifacts = evaluator.evaluate_from_batch_result(config=config, batch_result=batch_result)

        assert artifacts.dataset_version.startswith("side_lift-dataset-")
        assert artifacts.candidate_version.startswith("side_lift-candidate-")
        assert artifacts.evaluation.action_id == "side_lift"
        assert artifacts.evaluation.dataset_version == artifacts.dataset_version
        assert artifacts.evaluation.version_id == artifacts.candidate_version
        assert len(artifacts.evaluation.sample_results) >= 1
        assert artifacts.evaluation.metric_scores["test_sample_count"] == float(len(artifacts.evaluation.sample_results))
