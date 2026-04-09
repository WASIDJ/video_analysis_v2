"""预定义动作模板.

为常见运动动作提供预配置的检测项组合.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ActionTemplate:
    """动作模板."""

    id: str                           # 模板ID
    name: str                         # 名称
    name_zh: str                      # 中文名称
    description: str                  # 描述

    # 推荐的检测项列表
    primary_metrics: List[str]        # 主要检测项
    secondary_metrics: List[str]      # 次要检测项

    # 参考标准
    difficulty_levels: Dict[str, Dict] = field(default_factory=dict)  # 难度等级定义


# 预定义动作模板
ACTION_TEMPLATES: Dict[str, ActionTemplate] = {
    "squat": ActionTemplate(
        id="squat",
        name="Squat",
        name_zh="深蹲",
        description="深蹲动作分析，评估深度、膝外翻、躯干前倾等指标。",
        primary_metrics=[
            "knee_flexion",      # 膝关节屈曲（深度）
            "knee_valgus",       # 膝外翻
            "trunk_lean",        # 躯干前倾
            "hip_flexion",       # 髋屈曲
            "ankle_dorsiflexion", # 踝背屈
        ],
        secondary_metrics=[
            "lumbar_curvature",  # 腰椎曲率（塌腰）
            "pelvic_tilt",       # 骨盆倾斜
            "knee_symmetry",     # 膝关节对称性
            "hip_range_of_motion", # 髋活动范围
        ],
        difficulty_levels={
            "beginner": {
                "knee_flexion": (60, 90),
                "trunk_lean": (0, 60),
            },
            "intermediate": {
                "knee_flexion": (90, 120),
                "trunk_lean": (0, 45),
            },
            "advanced": {
                "knee_flexion": (110, 140),
                "trunk_lean": (15, 45),
            },
        },
    ),

    "lunge": ActionTemplate(
        id="lunge",
        name="Lunge",
        name_zh="弓步蹲",
        description="弓步蹲动作分析，评估前腿深度、躯干稳定性等指标。",
        primary_metrics=[
            "knee_flexion",
            "knee_valgus",
            "trunk_lean",
            "trunk_rotation",    # 躯干旋转
        ],
        secondary_metrics=[
            "lumbar_curvature",
            "pelvic_tilt",
            "knee_symmetry",
            "hip_flexion",
        ],
    ),

    "pushup": ActionTemplate(
        id="pushup",
        name="Push-up",
        name_zh="俯卧撑",
        description="俯卧撑动作分析，评估躯干对齐、肩部稳定性等指标。",
        primary_metrics=[
            "elbow_flexion",     # 肘关节屈曲
            "trunk_lean",        # 躯干对齐
            "shoulder_lift_ratio", # 耸肩
        ],
        secondary_metrics=[
            "lumbar_curvature",
            "thoracic_curvature",
            "knee_symmetry",
        ],
    ),

    "plank": ActionTemplate(
        id="plank",
        name="Plank",
        name_zh="平板支撑",
        description="平板支撑动作分析，评估脊柱对齐、核心稳定性等指标。",
        primary_metrics=[
            "lumbar_curvature",
            "thoracic_curvature",
            "pelvic_tilt",
            "shoulder_lift_ratio",
        ],
        secondary_metrics=[
            "trunk_lean",
            "knee_symmetry",
        ],
    ),

    "deadlift": ActionTemplate(
        id="deadlift",
        name="Deadlift",
        name_zh="硬拉",
        description="硬拉动作分析，评估脊柱中立位、髋膝协调等指标。",
        primary_metrics=[
            "lumbar_curvature",
            "trunk_lean",
            "knee_flexion",
            "hip_flexion",
        ],
        secondary_metrics=[
            "thoracic_curvature",
            "pelvic_tilt",
            "shoulder_lift_ratio",
        ],
    ),

    "overhead_press": ActionTemplate(
        id="overhead_press",
        name="Overhead Press",
        name_zh="肩推",
        description="肩推动作分析，评估肩部活动度、脊柱对齐等指标。",
        primary_metrics=[
            "elbow_flexion",
            "shoulder_lift_ratio",
            "lumbar_curvature",
            "thoracic_curvature",
        ],
        secondary_metrics=[
            "trunk_lean",
            "pelvic_tilt",
        ],
    ),
}


def get_action_template(action_id: str) -> Optional[ActionTemplate]:
    """获取动作模板."""
    return ACTION_TEMPLATES.get(action_id)


def get_all_action_templates() -> List[ActionTemplate]:
    """获取所有动作模板."""
    return list(ACTION_TEMPLATES.values())


def get_metrics_for_action(action_id: str) -> List[str]:
    """获取动作推荐的检测项列表."""
    template = ACTION_TEMPLATES.get(action_id)
    if not template:
        return []

    metrics = list(template.primary_metrics)
    metrics.extend(template.secondary_metrics)
    return metrics
