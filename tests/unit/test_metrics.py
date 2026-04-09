"""检测项单元测试."""
import numpy as np
import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from src.core.metrics.definitions import (
    MetricCategory,
    MovementPlane,
    MetricDefinition,
    METRIC_TEMPLATES,
    get_metric_definition,
    get_metrics_by_category,
)
from src.core.config.models import (
    MetricConfig,
    MetricThreshold,
    ErrorCondition,
)


class TestMetricDefinition:
    """测试检测项定义（重构后版本）."""

    def test_basic_definition(self):
        """测试基本检测项定义创建."""
        metric = MetricDefinition(
            id="test",
            name="Test",
            name_zh="测试",
            description="测试检测项",
            category=MetricCategory.JOINT_ANGLE,
            plane=MovementPlane.SAGITTAL,
            primary_joints=["knee"],
            measurement_type="angle",
            required_keypoints=["hip", "knee", "ankle"],
            calculator="joint_angle",
        )

        assert metric.id == "test"
        assert metric.name == "Test"
        assert metric.category == MetricCategory.JOINT_ANGLE
        assert metric.calculator == "joint_angle"

    def test_to_dict_serialization(self):
        """测试检测项定义序列化."""
        metric = MetricDefinition(
            id="test",
            name="Test",
            name_zh="测试",
            description="测试检测项",
            category=MetricCategory.JOINT_ANGLE,
            plane=MovementPlane.SAGITTAL,
            primary_joints=["knee"],
            measurement_type="angle",
            required_keypoints=["hip", "knee", "ankle"],
            calculator="joint_angle",
            tags=["squat", "lower_body"],
        )

        data = metric.to_dict()
        assert data["id"] == "test"
        assert data["name"] == "Test"
        assert data["category"] == "joint_angle"
        assert data["plane"] == "sagittal"
        assert data["tags"] == ["squat", "lower_body"]


class TestMetricConfig:
    """测试检测项配置（配置系统）."""

    def test_metric_config_with_thresholds(self):
        """测试带阈值的检测项配置."""
        config = MetricConfig(
            metric_id="knee_flexion",
            enabled=True,
            evaluation_phase="bottom",
            thresholds=MetricThreshold(
                target_value=110.0,
                normal_range=(90.0, 120.0),
                excellent_range=(100.0, 120.0),
                good_range=(90.0, 130.0),
                pass_range=(70.0, 140.0),
            ),
            weight=1.5,
        )

        assert config.metric_id == "knee_flexion"
        assert config.enabled is True
        assert config.evaluation_phase == "bottom"
        assert config.thresholds.target_value == 110.0
        assert config.weight == 1.5

    def test_metric_config_with_error_conditions(self):
        """测试带错误条件的检测项配置."""
        config = MetricConfig(
            metric_id="knee_flexion",
            enabled=True,
            evaluation_phase="bottom",
            thresholds=MetricThreshold(
                target_value=110.0,
                normal_range=(90.0, 120.0),
            ),
            error_conditions=[
                ErrorCondition(
                    error_id="insufficient_depth",
                    error_name="深蹲深度不足",
                    description="膝关节屈曲角度不足",
                    severity="medium",
                    condition={"operator": "gt", "value": 90},
                ),
            ],
            weight=1.0,
        )

        assert len(config.error_conditions) == 1
        assert config.error_conditions[0].error_id == "insufficient_depth"
        assert config.error_conditions[0].condition["operator"] == "gt"

    def test_metric_config_serialization(self):
        """测试检测项配置序列化."""
        config = MetricConfig(
            metric_id="knee_flexion",
            enabled=True,
            evaluation_phase="bottom",
            thresholds=MetricThreshold(
                target_value=110.0,
                normal_range=(90.0, 120.0),
            ),
            weight=1.5,
        )

        data = config.to_dict()
        assert data["metric_id"] == "knee_flexion"
        assert data["enabled"] is True
        assert data["thresholds"]["target_value"] == 110.0
        assert data["thresholds"]["normal_range"] == [90.0, 120.0]


class TestMetricTemplates:
    """测试预定义检测项模板."""

    def test_all_metrics_have_required_fields(self):
        """测试所有检测项都有必需字段."""
        for metric_id, metric in METRIC_TEMPLATES.items():
            assert metric.id, f"{metric_id} 缺少 id"
            assert metric.name, f"{metric_id} 缺少 name"
            assert metric.name_zh, f"{metric_id} 缺少 name_zh"
            assert metric.description, f"{metric_id} 缺少 description"
            assert metric.category, f"{metric_id} 缺少 category"
            assert metric.plane, f"{metric_id} 缺少 plane"
            assert metric.measurement_type, f"{metric_id} 缺少 measurement_type"
            assert metric.required_keypoints, f"{metric_id} 缺少 required_keypoints"

    def test_knee_flexion_exists(self):
        """测试膝关节屈曲检测项存在."""
        metric = get_metric_definition("knee_flexion")
        assert metric is not None
        assert metric.name_zh == "膝关节屈曲角度"
        assert metric.category == MetricCategory.JOINT_ANGLE_SAGITTAL
        assert metric.calculator == "joint_angle"

    def test_segment_metrics_exist(self):
        """测试体块特征检测项存在."""
        segment_metrics = [
            "lumbar_curvature",
            "thoracic_curvature",
            "shoulder_lift_ratio",
            "pelvic_tilt",
        ]
        for metric_id in segment_metrics:
            metric = get_metric_definition(metric_id)
            assert metric is not None, f"检测项 {metric_id} 不存在"
            assert metric.category == MetricCategory.SEGMENT

    def test_get_by_category(self):
        """测试按分类获取."""
        sagittal_metrics = get_metrics_by_category(MetricCategory.JOINT_ANGLE_SAGITTAL)
        assert len(sagittal_metrics) > 0
        for m in sagittal_metrics:
            assert m.plane == MovementPlane.SAGITTAL

    def test_no_hardcoded_thresholds_in_templates(self):
        """测试模板中没有硬编码阈值（重构后的关键特性）."""
        for metric_id, metric in METRIC_TEMPLATES.items():
            # 验证模板中不包含特定阈值参数
            assert not hasattr(metric, 'normal_range') or getattr(metric, 'normal_range', None) is None, \
                f"{metric_id} 不应在模板中定义 normal_range"
            assert not hasattr(metric, 'error_patterns'), \
                f"{metric_id} 不应在模板中定义 error_patterns"


class TestSideLegRaiseMetrics:
    """测试侧抬腿专用检测项."""

    def test_hip_abduction_metric_exists(self):
        """测试髋关节外展检测项存在."""
        metric = get_metric_definition("hip_abduction")
        assert metric is not None
        assert metric.name_zh == "髋关节外展角度"
        assert metric.category == MetricCategory.JOINT_ANGLE_FRONTAL
        assert metric.plane == MovementPlane.FRONTAL
        assert metric.calculator == "hip_abduction_angle"
        assert "gluteus_medius" in metric.muscle_groups

    def test_hip_external_rotation_metric_exists(self):
        """测试髋关节外旋检测项存在."""
        metric = get_metric_definition("hip_external_rotation")
        assert metric is not None
        assert metric.name_zh == "髋关节外旋角度"
        assert metric.category == MetricCategory.JOINT_ANGLE_TRANSVERSE
        assert metric.plane == MovementPlane.TRANSVERSE
        assert metric.calculator == "hip_rotation_angle"

    def test_trunk_lateral_flexion_metric_exists(self):
        """测试躯干侧倾检测项存在."""
        metric = get_metric_definition("trunk_lateral_flexion")
        assert metric is not None
        assert metric.name_zh == "躯干侧倾角度"
        assert metric.category == MetricCategory.JOINT_ANGLE_FRONTAL
        assert metric.calculator == "trunk_lateral_flexion"

    def test_pelvic_obliquity_metric_exists(self):
        """测试骨盆倾斜检测项存在."""
        metric = get_metric_definition("pelvic_obliquity")
        assert metric is not None
        assert metric.name_zh == "骨盆倾斜度"
        assert metric.category == MetricCategory.POSITION_ALIGNMENT
        assert metric.calculator == "pelvic_obliquity_angle"

    def test_leg_elevation_height_metric_exists(self):
        """测试腿部抬升高度检测项存在."""
        metric = get_metric_definition("leg_elevation_height")
        assert metric is not None
        assert metric.name_zh == "腿部抬升高度"
        assert metric.category == MetricCategory.POSITION
        assert metric.calculator == "vertical_elevation_ratio"

    def test_knee_flexion_compensation_metric_exists(self):
        """测试膝关节屈曲代偿检测项存在."""
        metric = get_metric_definition("knee_flexion_compensation")
        assert metric is not None
        assert metric.name_zh == "膝关节屈曲代偿"
        assert metric.category == MetricCategory.JOINT_ANGLE_SAGITTAL
        assert metric.calculator == "joint_angle"

    def test_ankle_dorsiflexion_lateral_metric_exists(self):
        """测试外展时踝关节位置检测项存在."""
        metric = get_metric_definition("ankle_dorsiflexion_lateral")
        assert metric is not None
        assert metric.name_zh == "外展时踝关节位置"
        assert metric.calculator == "joint_angle"

    def test_all_side_leg_raise_metrics_have_required_keypoints(self):
        """测试所有侧抬腿检测项都有必需的关键点."""
        side_leg_raise_metrics = [
            "hip_abduction",
            "hip_external_rotation",
            "trunk_lateral_flexion",
            "pelvic_obliquity",
            "leg_elevation_height",
            "knee_flexion_compensation",
            "ankle_dorsiflexion_lateral",
        ]

        for metric_id in side_leg_raise_metrics:
            metric = get_metric_definition(metric_id)
            assert metric is not None, f"检测项 {metric_id} 不存在"
            assert len(metric.required_keypoints) >= 2, \
                f"{metric_id} 应有至少2个必需关键点"
            assert metric.calculator, f"{metric_id} 应有指定的计算器"
