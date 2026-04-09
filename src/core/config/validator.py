"""参数验证器.

提供配置参数的验证功能，确保参数值在合理范围内.
"""
from typing import Any, Dict, List, Optional, Tuple

from .models import ActionConfig, MetricConfig, MetricThreshold


class ValidationError(Exception):
    """验证错误."""
    pass


class ParameterValidator:
    """参数验证器.

    验证配置参数的合法性和合理性.
    """

    # 检测项的合法范围定义
    METRIC_RANGES = {
        "knee_flexion": {
            "min": 0,
            "max": 180,
            "unit": "degrees",
        },
        "hip_flexion": {
            "min": 0,
            "max": 180,
            "unit": "degrees",
        },
        "trunk_lean": {
            "min": 0,
            "max": 90,
            "unit": "degrees",
        },
        "ankle_dorsiflexion": {
            "min": 0,
            "max": 90,
            "unit": "degrees",
        },
        "knee_valgus": {
            "min": -90,
            "max": 90,
            "unit": "degrees",
        },
        "lumbar_curvature": {
            "min": 0,
            "max": 1,
            "unit": "ratio",
        },
        "thoracic_curvature": {
            "min": 0,
            "max": 1,
            "unit": "ratio",
        },
        "pelvic_tilt": {
            "min": -45,
            "max": 45,
            "unit": "degrees",
        },
    }

    # 权重范围
    WEIGHT_RANGE = (0.0, 10.0)

    @classmethod
    def validate_action_config(cls, config: ActionConfig) -> Tuple[bool, List[str]]:
        """验证动作配置.

        Args:
            config: 动作配置

        Returns:
            (是否通过, 错误信息列表)
        """
        errors = []

        # 验证基础信息
        if not config.action_id:
            errors.append("action_id不能为空")

        if not config.action_name:
            errors.append("action_name不能为空")

        # 验证版本号格式
        if not cls._is_valid_version(config.version):
            errors.append(f"版本号格式错误: {config.version}")

        # 验证检测项
        metric_ids = set()
        for metric in config.metrics:
            if metric.metric_id in metric_ids:
                errors.append(f"重复的检测项ID: {metric.metric_id}")
            metric_ids.add(metric.metric_id)

            valid, metric_errors = cls.validate_metric_config(metric)
            if not valid:
                errors.extend([f"{metric.metric_id}: {e}" for e in metric_errors])

        # 验证权重总和
        total_weight = sum(m.weight for m in config.metrics if m.enabled)
        if total_weight <= 0:
            errors.append("启用的检测项权重总和必须大于0")

        return len(errors) == 0, errors

    @classmethod
    def validate_metric_config(cls, config: MetricConfig) -> Tuple[bool, List[str]]:
        """验证检测项配置.

        Args:
            config: 检测项配置

        Returns:
            (是否通过, 错误信息列表)
        """
        errors = []

        # 验证检测项ID
        if not config.metric_id:
            errors.append("metric_id不能为空")

        # 验证阶段
        valid_phases = ["standing", "descent", "bottom", "ascent", "completion", "any"]
        if config.evaluation_phase not in valid_phases:
            errors.append(f"未知的评估阶段: {config.evaluation_phase}")

        # 验证阈值
        threshold_errors = cls.validate_thresholds(
            config.metric_id, config.thresholds
        )
        errors.extend(threshold_errors)

        # 验证权重
        if not (cls.WEIGHT_RANGE[0] <= config.weight <= cls.WEIGHT_RANGE[1]):
            errors.append(
                f"权重必须在{cls.WEIGHT_RANGE[0]}到{cls.WEIGHT_RANGE[1]}之间"
            )

        # 验证错误条件
        for condition in config.error_conditions:
            if not condition.error_id:
                errors.append("错误条件必须有error_id")
            if not condition.error_name:
                errors.append("错误条件必须有error_name")

        return len(errors) == 0, errors

    @classmethod
    def validate_thresholds(
        cls,
        metric_id: str,
        thresholds: MetricThreshold,
    ) -> List[str]:
        """验证阈值配置.

        Args:
            metric_id: 检测项ID
            thresholds: 阈值配置

        Returns:
            错误信息列表
        """
        errors = []

        # 获取合法范围
        valid_range = cls.METRIC_RANGES.get(metric_id)
        if not valid_range:
            # 未知检测项，跳过范围验证
            return errors

        min_val = valid_range["min"]
        max_val = valid_range["max"]

        # 验证目标值
        if thresholds.target_value is not None:
            if not (min_val <= thresholds.target_value <= max_val):
                errors.append(
                    f"目标值{thresholds.target_value}不在合法范围[{min_val}, {max_val}]内"
                )

        # 验证范围
        ranges_to_check = [
            ("normal_range", thresholds.normal_range),
            ("excellent_range", thresholds.excellent_range),
            ("good_range", thresholds.good_range),
            ("pass_range", thresholds.pass_range),
        ]

        for name, range_val in ranges_to_check:
            if range_val is not None:
                if len(range_val) != 2:
                    errors.append(f"{name}必须是长度为2的元组")
                    continue

                low, high = range_val
                if low >= high:
                    errors.append(f"{name}的最小值必须小于最大值")

                if not (min_val <= low <= max_val):
                    errors.append(
                        f"{name}的最小值{low}不在合法范围[{min_val}, {max_val}]内"
                    )

                if not (min_val <= high <= max_val):
                    errors.append(
                        f"{name}的最大值{high}不在合法范围[{min_val}, {max_val}]内"
                    )

        # 检查范围一致性
        if (thresholds.excellent_range and thresholds.good_range):
            if thresholds.excellent_range[1] > thresholds.good_range[1]:
                errors.append("优秀范围的最大值不应大于良好范围的最大值")

        if (thresholds.good_range and thresholds.pass_range):
            if thresholds.good_range[1] > thresholds.pass_range[1]:
                errors.append("良好范围的最大值不应大于及格范围的最大值")

        return errors

    @classmethod
    def sanitize_config(cls, config: ActionConfig) -> ActionConfig:
        """清理配置（自动修复小问题）.

        Args:
            config: 原始配置

        Returns:
            清理后的配置
        """
        from copy import deepcopy
        config = deepcopy(config)

        for metric in config.metrics:
            # 确保权重非负
            if metric.weight < 0:
                metric.weight = 0

            # 限制权重上限
            if metric.weight > cls.WEIGHT_RANGE[1]:
                metric.weight = cls.WEIGHT_RANGE[1]

            # 清理阈值的精度
            thresholds = metric.thresholds
            if thresholds.target_value is not None:
                thresholds.target_value = round(thresholds.target_value, 2)

            for attr_name in ["normal_range", "excellent_range", "good_range", "pass_range"]:
                range_val = getattr(thresholds, attr_name)
                if range_val is not None:
                    cleaned = tuple(round(v, 2) for v in range_val)
                    setattr(thresholds, attr_name, cleaned)

        return config

    @classmethod
    def _is_valid_version(cls, version: str) -> bool:
        """检查版本号格式是否合法.

        支持格式: x.y.z, x.y, x
        """
        parts = version.split(".")
        if len(parts) < 1 or len(parts) > 3:
            return False

        for part in parts:
            if not part.isdigit():
                return False

        return True

    @classmethod
    def get_valid_range(cls, metric_id: str) -> Optional[Dict[str, Any]]:
        """获取检测项的合法范围.

        Args:
            metric_id: 检测项ID

        Returns:
            范围定义或None
        """
        return cls.METRIC_RANGES.get(metric_id)
