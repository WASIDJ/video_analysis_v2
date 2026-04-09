"""视角约束定义.

定义检测项与视角的兼容性，以及可靠性评估.
"""
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from .analyzer import CameraViewpoint


@dataclass
class ViewpointConstraint:
    """视角约束定义."""

    # 支持的视角列表
    supported_viewpoints: List[CameraViewpoint]

    # 可靠性评分 (0-1)
    reliability_scores: Dict[CameraViewpoint, float]

    # 是否需要特定侧面
    requires_specific_side: bool = False

    # 描述
    description: str = ""


@dataclass
class DetectionItemConstraint:
    """检测项约束.

    为每个检测项定义其适用的视角约束.
    """
    metric_id: str
    metric_name: str

    # 需要的运动平面
    required_plane: str  # sagittal / frontal / transverse

    # 视角约束
    viewpoint_constraint: ViewpointConstraint

    # 当视角不匹配时的回退策略
    fallback_action: str  # "skip" / "warn" / "use_with_caution"


class ConstraintManager:
    """约束管理器.

    管理所有检测项的视角约束，提供查询接口.
    """

    # 预定义的约束表
    CONSTRAINTS: Dict[str, DetectionItemConstraint] = {}

    @classmethod
    def initialize(cls):
        """初始化约束表."""
        if cls.CONSTRAINTS:
            return

        # 矢状面检测项（深度相关）
        sagittal_metrics = [
            ("knee_flexion", "膝关节屈曲角度"),
            ("hip_flexion", "髋关节屈曲角度"),
            ("trunk_lean", "躯干前倾角度"),
            ("ankle_dorsiflexion", "踝关节背屈角度"),
            ("lumbar_curvature", "腰椎曲率"),
            ("thoracic_curvature", "胸椎曲率"),
            ("pelvic_tilt", "骨盆倾斜角度"),
        ]

        for metric_id, name in sagittal_metrics:
            cls.CONSTRAINTS[metric_id] = DetectionItemConstraint(
                metric_id=metric_id,
                metric_name=name,
                required_plane="sagittal",
                viewpoint_constraint=ViewpointConstraint(
                    supported_viewpoints=[
                        CameraViewpoint.SAGITTAL,
                        CameraViewpoint.NEAR_SAGITTAL,
                        CameraViewpoint.DIAGONAL,
                    ],
                    reliability_scores={
                        CameraViewpoint.SAGITTAL: 0.95,
                        CameraViewpoint.NEAR_SAGITTAL: 0.85,
                        CameraViewpoint.DIAGONAL: 0.60,
                        CameraViewpoint.NEAR_FRONTAL: 0.40,
                        CameraViewpoint.FRONTAL: 0.20,
                    },
                    description="侧面视角最佳，正面视角不可靠",
                ),
                fallback_action="warn",
            )

        # 冠状面检测项（外翻/内扣相关）
        frontal_metrics = [
            ("knee_valgus", "膝关节外翻角度"),
            ("knee_symmetry", "膝关节对称性"),
            ("shoulder_lift_ratio", "肩部上提比例"),
            ("hip_symmetry", "髋关节对称性"),
        ]

        for metric_id, name in frontal_metrics:
            cls.CONSTRAINTS[metric_id] = DetectionItemConstraint(
                metric_id=metric_id,
                metric_name=name,
                required_plane="frontal",
                viewpoint_constraint=ViewpointConstraint(
                    supported_viewpoints=[
                        CameraViewpoint.FRONTAL,
                        CameraViewpoint.NEAR_FRONTAL,
                        CameraViewpoint.DIAGONAL,
                    ],
                    reliability_scores={
                        CameraViewpoint.FRONTAL: 0.95,
                        CameraViewpoint.NEAR_FRONTAL: 0.85,
                        CameraViewpoint.DIAGONAL: 0.50,
                        CameraViewpoint.NEAR_SAGITTAL: 0.20,
                        CameraViewpoint.SAGITTAL: 0.05,  # 侧面几乎不可能可靠检测
                    },
                    description="正面视角最佳，侧面视角不可靠",
                ),
                fallback_action="skip",  # 侧面视角下跳过
            )

        # 水平面检测项（旋转相关）
        transverse_metrics = [
            ("trunk_rotation", "躯干旋转角度"),
        ]

        for metric_id, name in transverse_metrics:
            cls.CONSTRAINTS[metric_id] = DetectionItemConstraint(
                metric_id=metric_id,
                metric_name=name,
                required_plane="transverse",
                viewpoint_constraint=ViewpointConstraint(
                    supported_viewpoints=[
                        CameraViewpoint.FRONTAL,
                        CameraViewpoint.NEAR_FRONTAL,
                        CameraViewpoint.SAGITTAL,
                        CameraViewpoint.NEAR_SAGITTAL,
                    ],
                    reliability_scores={
                        CameraViewpoint.FRONTAL: 0.90,
                        CameraViewpoint.NEAR_FRONTAL: 0.80,
                        CameraViewpoint.SAGITTAL: 0.70,
                        CameraViewpoint.NEAR_SAGITTAL: 0.60,
                        CameraViewpoint.DIAGONAL: 0.40,
                    },
                    requires_specific_side=True,
                    description="需要明确的正面或侧面视角",
                ),
                fallback_action="use_with_caution",
            )

    @classmethod
    def get_constraint(cls, metric_id: str) -> Optional[DetectionItemConstraint]:
        """获取检测项的约束定义."""
        cls.initialize()
        return cls.CONSTRAINTS.get(metric_id)

    @classmethod
    def check_compatibility(
        cls,
        metric_id: str,
        viewpoint: CameraViewpoint,
    ) -> tuple[bool, float, str]:
        """检查检测项与视角的兼容性.

        Returns:
            (is_compatible, reliability_score, message)
        """
        cls.initialize()

        constraint = cls.CONSTRAINTS.get(metric_id)
        if not constraint:
            # 未定义约束，默认可用
            return True, 0.5, "未定义视角约束"

        if viewpoint in constraint.viewpoint_constraint.supported_viewpoints:
            reliability = constraint.viewpoint_constraint.reliability_scores.get(
                viewpoint, 0.5
            )
            if reliability < 0.3:
                return (
                    False,
                    reliability,
                    f"{constraint.metric_name}在{viewpoint.value}视角下可靠性过低({reliability:.1f})"
                )
            return True, reliability, ""
        else:
            return (
                False,
                0.0,
                f"{constraint.metric_name}不支持{viewpoint.value}视角"
            )

    @classmethod
    def filter_metrics_by_viewpoint(
        cls,
        metric_ids: List[str],
        viewpoint: CameraViewpoint,
        min_reliability: float = 0.3,
    ) -> tuple[List[str], List[dict]]:
        """根据视角筛选检测项.

        Returns:
            (valid_metrics, warnings)
        """
        cls.initialize()

        valid_metrics = []
        warnings = []

        for metric_id in metric_ids:
            is_compatible, reliability, message = cls.check_compatibility(
                metric_id, viewpoint
            )

            if is_compatible and reliability >= min_reliability:
                valid_metrics.append(metric_id)
            else:
                constraint = cls.CONSTRAINTS.get(metric_id)
                if constraint:
                    warnings.append({
                        "metric_id": metric_id,
                        "metric_name": constraint.metric_name,
                        "reason": message,
                        "reliability": reliability,
                        "fallback_action": constraint.fallback_action,
                    })

        return valid_metrics, warnings
