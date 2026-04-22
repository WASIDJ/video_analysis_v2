"""从训练后的动作配置构建 iOS detectItemParameters。"""

from __future__ import annotations

from typing import Any


def build_parameter_row(
    builder_name: str,
    metric: dict[str, Any],
    action_config: dict[str, Any],
) -> list[float]:
    """为一个指标构建一个 iOS 参数行。"""
    if builder_name == "range8_v1":
        return _range8(metric)
    if builder_name == "item7_static_v1":
        return _item7_static(metric)
    if builder_name == "item8_dynamic_v1":
        return _item8_dynamic(metric, action_config)
    raise ValueError(f"Unsupported iOS parameter builder: {builder_name}")


def _thresholds(metric: dict[str, Any]) -> dict[str, Any]:
    return metric.get("thresholds", {})


def _range8(metric: dict[str, Any]) -> list[float]:
    thresholds = _thresholds(metric)
    normal_min, normal_max = thresholds["normal_range"]
    excellent_min, excellent_max = thresholds["excellent_range"]
    return [
        normal_min,
        excellent_min,
        excellent_max,
        normal_max,
        normal_min,
        excellent_min,
        excellent_max,
        normal_max,
    ]


def _item7_static(metric: dict[str, Any]) -> list[float]:
    thresholds = _thresholds(metric)
    normal_min, normal_max = thresholds["normal_range"]
    excellent_min, excellent_max = thresholds["excellent_range"]
    target = thresholds["target_value"]
    return [
        normal_min,
        normal_max,
        excellent_min,
        excellent_max,
        normal_min,
        target,
        target,
        normal_max,
    ]


def _item8_dynamic(metric: dict[str, Any], action_config: dict[str, Any]) -> list[float]:
    thresholds = _thresholds(metric)
    count_thresholds = action_config["count_layer"]["thresholds"]
    hold_exit = _find_hold_exit_threshold(action_config, metric["metric_id"])
    return [
        count_thresholds["exit_p2"],
        count_thresholds["enter_p2"],
        count_thresholds["enter_p2"],
        count_thresholds["exit_p1"],
        thresholds["normal_range"][0],
        thresholds["excellent_range"][0],
        hold_exit,
        thresholds["excellent_range"][1],
    ]


def _find_hold_exit_threshold(action_config: dict[str, Any], metric_id: str) -> float:
    semantic_layer = action_config.get("semantic_layer", {})
    for phase in semantic_layer.get("phases", []):
        if phase.get("phase_id") != "hold":
            continue
        for condition in phase.get("exit_conditions", []):
            if condition.get("metric") == metric_id and "value" in condition:
                return condition["value"]
    raise ValueError(f"Missing hold exit threshold for metric: {metric_id}")
