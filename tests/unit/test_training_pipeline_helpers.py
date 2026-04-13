"""训练管道辅助逻辑单元测试."""

import json
import sys
import types

import pytest

from src.core.analysis.fingerprint import ActionFingerprint, MetricFingerprint
from src.core.config.models import ActionConfig, ErrorCondition, MetricConfig

# 这些辅助逻辑测试不触发真实视频 I/O，这里只为通过模块导入注入最小桩对象。
sys.modules.setdefault("aiofiles", types.SimpleNamespace(open=None))

from src.core.training.batch_processor import create_batch_config_from_json
from src.core.training.pipeline import TrainingPipeline


def make_metric_fingerprint(
    metric_id: str,
    *,
    mean: float,
    std: float,
    min_value: float,
    max_value: float,
) -> MetricFingerprint:
    """构造测试用检测项指纹."""
    return MetricFingerprint(
        metric_id=metric_id,
        metric_name=metric_id,
        category="joint_angle",
        mean=mean,
        std=std,
        min=min_value,
        max=max_value,
        range=max_value - min_value,
        total_variation=max_value - min_value,
        variance_coefficient=std / mean,
        peak_count=1,
        valley_count=1,
        significance_score=0.8,
    )


def make_action_fingerprint(
    *,
    dominant_metrics: list[MetricFingerprint],
    secondary_metrics: list[MetricFingerprint] | None = None,
) -> ActionFingerprint:
    """构造测试用动作指纹."""
    total_metrics = len(dominant_metrics) + len(secondary_metrics or [])
    return ActionFingerprint(
        action_id="squat",
        action_name="Squat",
        created_at="2026-04-13T00:00:00",
        dominant_metrics=dominant_metrics,
        secondary_metrics=secondary_metrics or [],
        total_metrics_analyzed=total_metrics,
        active_joints=["knee"],
        symmetry_score=0.9,
        tags=["standard"],
    )


class TestTrainingPipelineHelpers:
    """测试训练管道辅助逻辑."""

    def test_determine_label_prioritizes_standard_tag(self):
        """存在 standard 标签时应优先返回 standard."""
        pipeline = TrainingPipeline.__new__(TrainingPipeline)

        label = pipeline._determine_label(["standard", "error:knee_valgus"])

        assert label == "standard"

    def test_aggregate_metric_stats_combines_dominant_and_secondary_metrics(self):
        """指标聚合应同时覆盖 dominant 和 secondary metrics."""
        pipeline = TrainingPipeline.__new__(TrainingPipeline)
        fp1 = make_action_fingerprint(
            dominant_metrics=[
                make_metric_fingerprint(
                    "knee_flexion",
                    mean=100.0,
                    std=5.0,
                    min_value=90.0,
                    max_value=110.0,
                )
            ],
            secondary_metrics=[
                make_metric_fingerprint(
                    "trunk_lean",
                    mean=20.0,
                    std=2.0,
                    min_value=15.0,
                    max_value=25.0,
                )
            ],
        )
        fp2 = make_action_fingerprint(
            dominant_metrics=[
                make_metric_fingerprint(
                    "knee_flexion",
                    mean=104.0,
                    std=6.0,
                    min_value=94.0,
                    max_value=114.0,
                )
            ]
        )

        stats = pipeline._aggregate_metric_stats([fp1, fp2])

        assert stats["knee_flexion"]["mean"] == pytest.approx(102.0)
        assert stats["knee_flexion"]["std"] == pytest.approx(5.5)
        assert stats["knee_flexion"]["min"] == 90.0
        assert stats["knee_flexion"]["max"] == 114.0
        assert stats["trunk_lean"]["mean"] == 20.0

    def test_calculate_config_confidence_caps_at_upper_bound(self):
        """配置置信度应随着覆盖提升，但上限为 0.95."""
        pipeline = TrainingPipeline.__new__(TrainingPipeline)

        confidence = pipeline._calculate_config_confidence(
            standard_sample_count=10,
            error_conditions={
                f"error_{idx}": [] for idx in range(10)
            },
        )

        assert confidence == pytest.approx(0.95)

    def test_add_error_condition_appends_only_to_matching_metric(self):
        """错误条件应只追加到匹配的检测项配置."""
        pipeline = TrainingPipeline.__new__(TrainingPipeline)
        config = ActionConfig(
            action_id="squat",
            action_name="Squat",
            action_name_zh="深蹲",
            metrics=[
                MetricConfig(metric_id="knee_flexion"),
                MetricConfig(metric_id="trunk_lean"),
            ],
        )
        condition = ErrorCondition(
            error_id="valgus_high_knee_flexion",
            error_name="膝屈过大",
            description="测试条件",
            condition={"metric_id": "knee_flexion", "operator": "gt", "value": 120},
            threshold_high=120.0,
        )

        pipeline._add_error_condition_to_config(config, "knee_flexion", condition)

        assert len(config.get_metric_config("knee_flexion").error_conditions) == 1
        assert len(config.get_metric_config("trunk_lean").error_conditions) == 0


class TestCreateBatchConfigFromJson:
    """测试批量配置解析."""

    def test_create_batch_config_from_json_parses_video_entries(self, tmp_path):
        """JSON 配置应正确解析为批处理配置对象."""
        json_path = tmp_path / "batch_config.json"
        json_path.write_text(
            json.dumps(
                {
                    "action_id": "side_lift",
                    "action_name_zh": "侧抬腿",
                    "videos": [
                        {"video_path": "std_01.mp4", "tags": ["standard"]},
                        {"video_path": "err_01.mp4", "tags": ["error:hip_drop"]},
                    ],
                    "auto_approve": True,
                }
            ),
            encoding="utf-8",
        )

        config = create_batch_config_from_json(str(json_path))

        assert config.action_id == "side_lift"
        assert config.action_name_zh == "侧抬腿"
        assert config.auto_approve is True
        assert len(config.videos) == 2
        assert config.videos[0].video_path == "std_01.mp4"
        assert config.videos[1].tags == ["error:hip_drop"]
