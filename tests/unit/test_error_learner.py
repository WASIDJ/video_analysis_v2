"""错误条件学习器单元测试."""

import pytest

from src.core.analysis.fingerprint import ActionFingerprint, MetricFingerprint
from src.core.training.error_learner import ErrorConditionLearner


def make_metric_fingerprint(
    *,
    metric_id: str = "knee_flexion",
    metric_name: str = "膝关节屈曲角度",
    mean: float,
    std: float = 2.0,
    min_value: float,
    max_value: float,
) -> MetricFingerprint:
    """构造测试用检测项指纹."""
    return MetricFingerprint(
        metric_id=metric_id,
        metric_name=metric_name,
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


def make_action_fingerprint(metric: MetricFingerprint, *, tags: list[str]) -> ActionFingerprint:
    """构造测试用动作指纹."""
    return ActionFingerprint(
        action_id="squat",
        action_name="Squat",
        created_at="2026-04-13T00:00:00",
        dominant_metrics=[metric],
        secondary_metrics=[],
        total_metrics_analyzed=1,
        active_joints=["knee"],
        symmetry_score=0.9,
        tags=tags,
    )


class TestErrorConditionLearner:
    """测试错误条件学习器."""

    def test_returns_empty_conditions_when_support_is_insufficient(self):
        """错误样本不足时不应学习出条件."""
        learner = ErrorConditionLearner()
        standard_fps = [
            make_action_fingerprint(
                make_metric_fingerprint(mean=100.0, min_value=90.0, max_value=110.0),
                tags=["standard"],
            ),
            make_action_fingerprint(
                make_metric_fingerprint(mean=102.0, min_value=92.0, max_value=112.0),
                tags=["standard"],
            ),
        ]
        error_fps = [
            make_action_fingerprint(
                make_metric_fingerprint(mean=130.0, min_value=120.0, max_value=140.0),
                tags=["error:knee_valgus"],
            )
        ]

        conditions = learner.learn_error_conditions(standard_fps, error_fps, "knee_valgus")

        assert conditions == []

    def test_learns_high_deviation_condition(self):
        """错误样本均值显著偏高时应学习 gt 条件."""
        learner = ErrorConditionLearner()
        standard_fps = [
            make_action_fingerprint(
                make_metric_fingerprint(mean=100.0, min_value=90.0, max_value=110.0),
                tags=["standard"],
            ),
            make_action_fingerprint(
                make_metric_fingerprint(mean=102.0, min_value=92.0, max_value=112.0),
                tags=["standard"],
            ),
        ]
        error_fps = [
            make_action_fingerprint(
                make_metric_fingerprint(mean=128.0, min_value=118.0, max_value=138.0),
                tags=["error:knee_valgus"],
            ),
            make_action_fingerprint(
                make_metric_fingerprint(mean=130.0, min_value=120.0, max_value=140.0),
                tags=["error:knee_valgus"],
            ),
        ]

        conditions = learner.learn_error_conditions(standard_fps, error_fps, "knee_valgus")

        assert len(conditions) == 1
        condition = conditions[0]
        assert condition.condition["operator"] == "gt"
        assert condition.condition["metric_id"] == "knee_flexion"
        assert condition.threshold_high == pytest.approx(113.3, rel=1e-3)
        assert condition.severity == "high"

    def test_learns_low_deviation_condition(self):
        """错误样本均值显著偏低时应学习 lt 条件."""
        learner = ErrorConditionLearner()
        standard_fps = [
            make_action_fingerprint(
                make_metric_fingerprint(mean=100.0, min_value=90.0, max_value=110.0),
                tags=["standard"],
            ),
            make_action_fingerprint(
                make_metric_fingerprint(mean=102.0, min_value=92.0, max_value=112.0),
                tags=["standard"],
            ),
        ]
        error_fps = [
            make_action_fingerprint(
                make_metric_fingerprint(mean=72.0, min_value=62.0, max_value=82.0),
                tags=["error:insufficient_depth"],
            ),
            make_action_fingerprint(
                make_metric_fingerprint(mean=70.0, min_value=60.0, max_value=80.0),
                tags=["error:insufficient_depth"],
            ),
        ]

        conditions = learner.learn_error_conditions(standard_fps, error_fps, "insufficient_depth")

        assert len(conditions) == 1
        condition = conditions[0]
        assert condition.condition["operator"] == "lt"
        assert condition.condition["metric_id"] == "knee_flexion"
        assert condition.threshold_low == pytest.approx(90.0, rel=1e-3)
        assert condition.severity == "high"

    def test_learn_from_labeled_dataset_groups_conditions_by_error_type(self):
        """带标签数据集学习应按错误类型分组输出条件."""
        learner = ErrorConditionLearner()
        labeled_fingerprints = [
            (
                make_action_fingerprint(
                    make_metric_fingerprint(mean=100.0, min_value=90.0, max_value=110.0),
                    tags=["standard"],
                ),
                ["standard"],
            ),
            (
                make_action_fingerprint(
                    make_metric_fingerprint(mean=102.0, min_value=92.0, max_value=112.0),
                    tags=["standard"],
                ),
                ["standard"],
            ),
            (
                make_action_fingerprint(
                    make_metric_fingerprint(mean=128.0, min_value=118.0, max_value=138.0),
                    tags=["error:knee_valgus"],
                ),
                ["error:knee_valgus"],
            ),
            (
                make_action_fingerprint(
                    make_metric_fingerprint(mean=130.0, min_value=120.0, max_value=140.0),
                    tags=["error:knee_valgus"],
                ),
                ["error:knee_valgus"],
            ),
        ]

        all_conditions = learner.learn_from_labeled_dataset(labeled_fingerprints)

        assert list(all_conditions.keys()) == ["knee_valgus"]
        assert len(all_conditions["knee_valgus"]) == 1

