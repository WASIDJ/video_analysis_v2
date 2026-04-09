"""检测项定义模块（重构版）.

剥离动作阶段/幅度规范参数和错误判断阈值，保持模板的通用性.

参数配置已迁移到独立的JSON配置文件系统.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union


class MetricCategory(Enum):
    """检测项分类（基于生物力学）."""
    JOINT_ANGLE = "joint_angle"
    JOINT_ANGLE_SAGITTAL = "joint_angle_sagittal"
    JOINT_ANGLE_FRONTAL = "joint_angle_frontal"
    JOINT_ANGLE_TRANSVERSE = "joint_angle_transverse"
    POSITION = "position"
    POSITION_ALIGNMENT = "position_alignment"
    POSITION_SYMMETRY = "position_symmetry"
    RANGE_OF_MOTION = "rom"
    TEMPORAL = "temporal"
    RHYTHM = "rhythm"
    SEGMENT = "segment"
    STABILITY = "stability"


class MovementPlane(Enum):
    """运动平面（解剖学定义）."""
    SAGITTAL = "sagittal"
    FRONTAL = "frontal"
    TRANSVERSE = "transverse"
    MULTI_PLANE = "multi_plane"


@dataclass
class MetricDefinition:
    """检测项定义模板（通用版本）.

    此类只定义检测项的基本属性和计算方法，不包含：
    - 具体阈值参数（迁移到配置文件）
    - 错误判断条件（迁移到配置文件）
    - 动作阶段定义（迁移到配置文件）

    这种设计使得检测项模板可以跨动作复用，具体的参数配置
    通过独立的JSON配置文件进行管理。
    """

    # ========== 基础信息 ==========
    id: str
    name: str
    name_zh: str
    description: str
    category: MetricCategory

    # ========== 生物力学属性 ==========
    plane: MovementPlane
    primary_joints: List[str]
    measurement_type: str
    required_keypoints: List[str]

    # ========== 可选属性（带默认值） ==========
    secondary_joints: List[str] = field(default_factory=list)
    muscle_groups: List[str] = field(default_factory=list)
    unit: str = ""
    is_bilateral: bool = False
    optional_keypoints: List[str] = field(default_factory=list)
    calculator: str = ""
    calculator_params: Dict[str, Any] = field(default_factory=dict)

    # ========== 元数据 ==========
    tags: List[str] = field(default_factory=list)
    related_sports: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于序列化）."""
        return {
            "id": self.id,
            "name": self.name,
            "name_zh": self.name_zh,
            "description": self.description,
            "category": self.category.value,
            "plane": self.plane.value,
            "primary_joints": self.primary_joints,
            "measurement_type": self.measurement_type,
            "required_keypoints": self.required_keypoints,
            "secondary_joints": self.secondary_joints,
            "muscle_groups": self.muscle_groups,
            "unit": self.unit,
            "is_bilateral": self.is_bilateral,
            "optional_keypoints": self.optional_keypoints,
            "calculator": self.calculator if isinstance(self.calculator, str) else "",
            "calculator_params": self.calculator_params,
            "tags": self.tags,
            "related_sports": self.related_sports,
        }


# ========== 通用检测项模板库 ==========
# 这些模板只定义检测项的基本属性，不包含具体参数
# 参数通过配置文件系统进行管理

METRIC_TEMPLATES: Dict[str, MetricDefinition] = {

    # ===== 关节角度类（矢状面）=====
    "knee_flexion": MetricDefinition(
        id="knee_flexion",
        name="Knee Flexion Angle",
        name_zh="膝关节屈曲角度",
        description="膝关节矢状面屈曲角度，测量大腿与小腿之间的夹角。",
        category=MetricCategory.JOINT_ANGLE_SAGITTAL,
        plane=MovementPlane.SAGITTAL,
        primary_joints=["knee"],
        secondary_joints=["hip", "ankle"],
        muscle_groups=["quadriceps", "hamstrings", "glutes"],
        measurement_type="angle",
        unit="degrees",
        is_bilateral=True,
        required_keypoints=["hip", "knee", "ankle"],
        calculator="joint_angle",
        calculator_params={"plane": "sagittal"},
        tags=["squat", "depth", "lower_body"],
        related_sports=["weightlifting", "crossfit", "bodybuilding"],
    ),

    "knee_valgus": MetricDefinition(
        id="knee_valgus",
        name="Knee Valgus Angle",
        name_zh="膝关节外翻角度",
        description="膝关节冠状面内扣角度（膝外翻）。",
        category=MetricCategory.JOINT_ANGLE_FRONTAL,
        plane=MovementPlane.FRONTAL,
        primary_joints=["knee"],
        muscle_groups=["vastus_medialis", "vastus_lateralis", "gluteus_medius"],
        measurement_type="angle",
        unit="degrees",
        is_bilateral=True,
        required_keypoints=["hip", "knee", "ankle"],
        calculator="knee_valgus_angle",
        tags=["squat", "knee_stability", "injury_risk"],
        related_sports=["weightlifting", "running", "basketball"],
    ),

    "hip_flexion": MetricDefinition(
        id="hip_flexion",
        name="Hip Flexion Angle",
        name_zh="髋关节屈曲角度",
        description="髋关节矢状面屈曲角度。",
        category=MetricCategory.JOINT_ANGLE_SAGITTAL,
        plane=MovementPlane.SAGITTAL,
        primary_joints=["hip"],
        secondary_joints=["spine", "knee"],
        muscle_groups=["hip_flexors", "glutes", "hamstrings"],
        measurement_type="angle",
        unit="degrees",
        is_bilateral=True,
        required_keypoints=["shoulder", "hip", "knee"],
        calculator="joint_angle",
        tags=["hip_mobility", "squat", "lower_body"],
    ),

    "trunk_lean": MetricDefinition(
        id="trunk_lean",
        name="Trunk Lean Angle",
        name_zh="躯干前倾角度",
        description="躯干相对于垂直方向的倾斜角度。",
        category=MetricCategory.JOINT_ANGLE_SAGITTAL,
        plane=MovementPlane.SAGITTAL,
        primary_joints=["spine", "hip"],
        muscle_groups=["erector_spinae", "core", "glutes"],
        measurement_type="angle",
        unit="degrees",
        required_keypoints=["shoulder_center", "hip_center"],
        calculator="trunk_lean_angle",
        tags=["squat", "spine", "core"],
    ),

    "ankle_dorsiflexion": MetricDefinition(
        id="ankle_dorsiflexion",
        name="Ankle Dorsiflexion",
        name_zh="踝关节背屈角度",
        description="踝关节背屈角度。",
        category=MetricCategory.JOINT_ANGLE_SAGITTAL,
        plane=MovementPlane.SAGITTAL,
        primary_joints=["ankle"],
        secondary_joints=["knee"],
        muscle_groups=["gastrocnemius", "soleus", "tibialis_anterior"],
        measurement_type="angle",
        unit="degrees",
        is_bilateral=True,
        required_keypoints=["knee", "ankle", "foot_index"],
        calculator="joint_angle",
        tags=["ankle_mobility", "squat", "lower_body"],
    ),

    # ===== 体块轮廓类 =====
    "lumbar_curvature": MetricDefinition(
        id="lumbar_curvature",
        name="Lumbar Curvature",
        name_zh="腰椎曲率",
        description="基于体块轮廓分析的腰椎曲率。",
        category=MetricCategory.SEGMENT,
        plane=MovementPlane.SAGITTAL,
        primary_joints=["spine", "hip"],
        muscle_groups=["erector_spinae", "core", "hip_flexors"],
        measurement_type="curvature",
        unit="ratio",
        required_keypoints=["shoulder_center", "hip_center"],
        optional_keypoints=["contour_points"],
        calculator="lumbar_curvature_from_segment",
        tags=["core", "lumbar", "spine", "segment"],
    ),

    "thoracic_curvature": MetricDefinition(
        id="thoracic_curvature",
        name="Thoracic Curvature",
        name_zh="胸椎曲率",
        description="基于体块轮廓分析的胸椎曲率。",
        category=MetricCategory.SEGMENT,
        plane=MovementPlane.SAGITTAL,
        primary_joints=["spine", "shoulder"],
        measurement_type="curvature",
        unit="ratio",
        required_keypoints=["nose", "shoulder_center"],
        optional_keypoints=["contour_points"],
        calculator="thoracic_curvature_from_segment",
        tags=["thoracic", "spine", "posture", "segment"],
    ),

    "shoulder_lift_ratio": MetricDefinition(
        id="shoulder_lift_ratio",
        name="Shoulder Lift Ratio",
        name_zh="肩部上提比例",
        description="基于轮廓分析的肩部上提比例。",
        category=MetricCategory.SEGMENT,
        plane=MovementPlane.FRONTAL,
        primary_joints=["shoulder"],
        muscle_groups=["trapezius", "deltoid"],
        measurement_type="ratio",
        unit="ratio",
        is_bilateral=True,
        required_keypoints=["shoulder", "ear", "hip"],
        optional_keypoints=["contour_points"],
        calculator="shoulder_lift_from_segment",
        tags=["shoulder", "upper_body", "segment"],
    ),

    "pelvic_tilt": MetricDefinition(
        id="pelvic_tilt",
        name="Pelvic Tilt",
        name_zh="骨盆倾斜角度",
        description="骨盆前后倾角度。",
        category=MetricCategory.SEGMENT,
        plane=MovementPlane.SAGITTAL,
        primary_joints=["hip"],
        muscle_groups=["hip_flexors", "glutes", "core"],
        measurement_type="angle",
        unit="degrees",
        required_keypoints=["left_hip", "right_hip", "left_shoulder", "right_shoulder"],
        optional_keypoints=["contour_points"],
        calculator="pelvic_tilt_angle",
        tags=["pelvis", "posture", "segment"],
    ),

    # ===== 对称性类 =====
    "knee_symmetry": MetricDefinition(
        id="knee_symmetry",
        name="Knee Height Symmetry",
        name_zh="膝关节高度对称性",
        description="左右膝关节高度的对称性。",
        category=MetricCategory.POSITION_SYMMETRY,
        plane=MovementPlane.FRONTAL,
        primary_joints=["knee"],
        measurement_type="distance",
        unit="normalized",
        required_keypoints=["left_knee", "right_knee"],
        calculator="vertical_symmetry",
        tags=["symmetry", "lower_body", "balance"],
    ),

    # ===== 活动范围类 =====
    "hip_range_of_motion": MetricDefinition(
        id="hip_range_of_motion",
        name="Hip Range of Motion",
        name_zh="髋关节活动范围",
        description="整个动作过程中髋关节的最大活动范围。",
        category=MetricCategory.RANGE_OF_MOTION,
        plane=MovementPlane.SAGITTAL,
        primary_joints=["hip"],
        measurement_type="range",
        unit="degrees",
        is_bilateral=True,
        required_keypoints=["shoulder", "hip", "knee"],
        calculator="joint_angle_range",
        tags=["hip_mobility", "rom", "lower_body"],
    ),

    # ===== 侧抬腿专用检测项（冠状面动作）=====
    "hip_abduction": MetricDefinition(
        id="hip_abduction",
        name="Hip Abduction Angle",
        name_zh="髋关节外展角度",
        description="髋关节冠状面外展角度，测量大腿与躯干垂线的夹角。",
        category=MetricCategory.JOINT_ANGLE_FRONTAL,
        plane=MovementPlane.FRONTAL,
        primary_joints=["hip"],
        secondary_joints=["knee", "ankle"],
        muscle_groups=["gluteus_medius", "gluteus_minimus", "tensor_fasciae_latae"],
        measurement_type="angle",
        unit="degrees",
        is_bilateral=True,
        required_keypoints=["hip", "knee", "shoulder"],
        calculator="hip_abduction_angle",
        calculator_params={"plane": "frontal"},
        tags=["hip_abduction", "side_leg_raise", "frontal_plane", "glute_strength"],
        related_sports=["physiotherapy", "pilates", "yoga", "rehabilitation"],
    ),

    "hip_external_rotation": MetricDefinition(
        id="hip_external_rotation",
        name="Hip External Rotation",
        name_zh="髋关节外旋角度",
        description="髋关节水平面外旋角度，检测抬腿时是否伴随外旋。",
        category=MetricCategory.JOINT_ANGLE_TRANSVERSE,
        plane=MovementPlane.TRANSVERSE,
        primary_joints=["hip"],
        muscle_groups=["piriformis", "gemelli", "obturator_internus"],
        measurement_type="angle",
        unit="degrees",
        is_bilateral=True,
        required_keypoints=["hip", "knee", "ankle"],
        calculator="hip_rotation_angle",
        calculator_params={"plane": "transverse"},
        tags=["hip_rotation", "side_leg_raise", "turnout", "hip_mobility"],
        related_sports=["ballet", "physiotherapy", "rehabilitation"],
    ),

    "trunk_lateral_flexion": MetricDefinition(
        id="trunk_lateral_flexion",
        name="Trunk Lateral Flexion",
        name_zh="躯干侧倾角度",
        description="躯干冠状面侧倾角度，检测侧抬腿时的躯干代偿。",
        category=MetricCategory.JOINT_ANGLE_FRONTAL,
        plane=MovementPlane.FRONTAL,
        primary_joints=["spine", "hip"],
        muscle_groups=["quadratus_lumborum", "obliques", "erector_spinae"],
        measurement_type="angle",
        unit="degrees",
        required_keypoints=["shoulder_center", "hip_center"],
        calculator="trunk_lateral_flexion",
        calculator_params={"reference": "vertical"},
        tags=["trunk_stability", "side_leg_raise", "compensation", "core"],
        related_sports=["physiotherapy", "pilates", "core_training"],
    ),

    "pelvic_obliquity": MetricDefinition(
        id="pelvic_obliquity",
        name="Pelvic Obliquity",
        name_zh="骨盆倾斜度",
        description="骨盆冠状面倾斜程度，左右髂嵴高度差。",
        category=MetricCategory.POSITION_ALIGNMENT,
        plane=MovementPlane.FRONTAL,
        primary_joints=["hip", "pelvis"],
        muscle_groups=["hip_abductors", "quadratus_lumborum", "obliques"],
        measurement_type="angle",
        unit="degrees",
        required_keypoints=["left_hip", "right_hip"],
        calculator="pelvic_obliquity_angle",
        tags=["pelvis", "side_leg_raise", "alignment", "hip_hiking"],
        related_sports=["physiotherapy", "posture_assessment"],
    ),

    "leg_elevation_height": MetricDefinition(
        id="leg_elevation_height",
        name="Leg Elevation Height",
        name_zh="腿部抬升高度",
        description="抬腿高度相对于支撑腿的比例，评估动作幅度。",
        category=MetricCategory.POSITION,
        plane=MovementPlane.FRONTAL,
        primary_joints=["hip", "ankle"],
        muscle_groups=["hip_abductors"],
        measurement_type="distance_ratio",
        unit="normalized",
        is_bilateral=True,
        required_keypoints=["ankle", "hip_center"],
        calculator="vertical_elevation_ratio",
        calculator_params={"reference": "contralateral"},
        tags=["elevation", "side_leg_raise", "amplitude", "range"],
        related_sports=["physiotherapy", "fitness_assessment"],
    ),

    "knee_flexion_compensation": MetricDefinition(
        id="knee_flexion_compensation",
        name="Knee Flexion Compensation",
        name_zh="膝关节屈曲代偿",
        description="侧抬腿时膝关节是否屈曲代偿（屈腿借力）。",
        category=MetricCategory.JOINT_ANGLE_SAGITTAL,
        plane=MovementPlane.SAGITTAL,
        primary_joints=["knee"],
        muscle_groups=["hamstrings", "quadriceps"],
        measurement_type="angle",
        unit="degrees",
        is_bilateral=True,
        required_keypoints=["hip", "knee", "ankle"],
        calculator="joint_angle",
        calculator_params={"plane": "sagittal"},
        tags=["knee_angle", "side_leg_raise", "compensation", "form_check"],
        related_sports=["physiotherapy", "form_correction"],
    ),

    "ankle_dorsiflexion_lateral": MetricDefinition(
        id="ankle_dorsiflexion_lateral",
        name="Ankle Position in Abduction",
        name_zh="外展时踝关节位置",
        description="侧抬腿时踝关节的背屈/跖屈角度。",
        category=MetricCategory.JOINT_ANGLE_SAGITTAL,
        plane=MovementPlane.SAGITTAL,
        primary_joints=["ankle"],
        muscle_groups=["tibialis_anterior", "gastrocnemius"],
        measurement_type="angle",
        unit="degrees",
        is_bilateral=True,
        required_keypoints=["knee", "ankle", "foot_index"],
        calculator="joint_angle",
        calculator_params={"plane": "sagittal"},
        tags=["ankle", "side_leg_raise", "foot_position"],
        related_sports=["physiotherapy", "foot_function"],
    ),
}


def get_metric_definition(metric_id: str) -> Optional[MetricDefinition]:
    """获取检测项定义."""
    return METRIC_TEMPLATES.get(metric_id)


def get_metrics_by_category(category: MetricCategory) -> List[MetricDefinition]:
    """按分类获取检测项."""
    return [m for m in METRIC_TEMPLATES.values() if m.category == category]


def list_all_metrics() -> List[Dict[str, str]]:
    """列出所有可用检测项."""
    return [
        {
            "id": m.id,
            "name": m.name,
            "name_zh": m.name_zh,
            "category": m.category.value,
            "plane": m.plane.value,
        }
        for m in METRIC_TEMPLATES.values()
    ]
