"""检测项计算器.

根据检测项定义计算实际数值，支持视角感知和自动左右侧选择.
集成配置系统，从JSON配置文件加载检测项参数和错误判断阈值。
"""
from typing import Any, Dict, List, Optional

import numpy as np

from src.core.models.base import Keypoint, PoseFrame, PoseSequence
from src.utils.geometry import calculate_angle_2d, calculate_distance
from src.core.phases.squat_phases import create_phase_detector
from src.core.viewpoint.analyzer import ViewpointAnalyzer, CameraViewpoint
from src.core.viewpoint.constraints import ConstraintManager
from src.core.metrics.definitions import MetricDefinition, METRIC_TEMPLATES
from src.core.config.manager import ConfigManager
from src.core.config.models import MetricConfig, ErrorCondition, ComparisonOperator


class MetricsCalculator:
    """检测项计算器.

    支持：
    1. 动作阶段检测 - 在关键点评估
    2. 视角分析 - 自动检测视频视角，过滤不可靠检测项
    3. 左右侧自动选择 - 基于置信度和可见性
    4. 配置驱动 - 从JSON配置文件加载检测项参数
    """

    def __init__(
        self,
        action_id: str = "squat",
        config_manager: Optional[ConfigManager] = None,
        min_confidence: float = 0.3,
        use_phase_detection: bool = True,
        use_viewpoint_analysis: bool = True,
        auto_select_side: bool = True,
    ):
        """
        Args:
            action_id: 动作ID（用于加载对应配置）
            config_manager: 配置管理器实例（None则使用默认）
            min_confidence: 最小关键点置信度
            use_phase_detection: 是否使用动作阶段检测
            use_viewpoint_analysis: 是否使用视角分析
            auto_select_side: 是否自动选择左右侧
        """
        self.action_id = action_id
        self.min_confidence = min_confidence
        self.use_phase_detection = use_phase_detection
        self.use_viewpoint_analysis = use_viewpoint_analysis
        self.auto_select_side = auto_select_side

        # 配置系统
        self._config_manager = config_manager or ConfigManager()
        self._action_config = self._config_manager.load_config(action_id)

        self._viewpoint_analyzer = ViewpointAnalyzer() if use_viewpoint_analysis else None
        self._selected_side: Optional[str] = None
        self._viewpoint_result: Optional[Any] = None
        self._metric_configs: Dict[str, MetricConfig] = {}

        # 加载检测项配置
        if self._action_config:
            for metric in self._action_config.metrics:
                self._metric_configs[metric.metric_id] = metric

    def calculate_metric(
        self,
        metric_def: MetricDefinition,
        pose_sequence: PoseSequence,
        segment_features: Optional[Dict[str, np.ndarray]] = None,
        action_name: str = "squat",
    ) -> Dict[str, Any]:
        """计算单个检测项."""
        # 初始化视角分析和左右侧选择（只执行一次）
        if self.use_viewpoint_analysis and self._viewpoint_result is None:
            self._viewpoint_result = self._viewpoint_analyzer.analyze(pose_sequence)

        if self.auto_select_side and self._selected_side is None:
            self._selected_side = self._auto_select_side(pose_sequence)

        calculator_name = metric_def.calculator if isinstance(metric_def.calculator, str) else ""

        # 检查视角兼容性
        viewpoint_warning = None
        reliability = 1.0
        if self.use_viewpoint_analysis and self._viewpoint_result:
            is_compatible, reliability, message = ConstraintManager.check_compatibility(
                metric_def.id, self._viewpoint_result.viewpoint
            )
            if not is_compatible:
                viewpoint_warning = {
                    "metric_id": metric_def.id,
                    "metric_name": metric_def.name_zh,
                    "viewpoint": self._viewpoint_result.viewpoint.value,
                    "warning": message,
                    "reliability": reliability,
                }

        # 根据计算器类型选择计算方式
        if calculator_name == "joint_angle":
            values = self._calculate_joint_angle(metric_def, pose_sequence)
        elif calculator_name == "knee_valgus_angle":
            values = self._calculate_knee_valgus(metric_def, pose_sequence)
        elif calculator_name == "trunk_lean_angle":
            values = self._calculate_trunk_lean(metric_def, pose_sequence)
        elif calculator_name == "trunk_rotation_angle":
            values = self._calculate_trunk_rotation(metric_def, pose_sequence)
        elif calculator_name == "trunk_lateral_flexion":
            values = self._calculate_trunk_lateral_flexion(metric_def, pose_sequence)
        elif calculator_name == "vertical_symmetry":
            values = self._calculate_vertical_symmetry(metric_def, pose_sequence)
        elif calculator_name == "joint_angle_range":
            values = self._calculate_angle_range(metric_def, pose_sequence)
        elif calculator_name == "hip_abduction_angle":
            values = self._calculate_hip_abduction(metric_def, pose_sequence)
        elif calculator_name == "hip_rotation_angle":
            values = self._calculate_hip_rotation(metric_def, pose_sequence)
        elif calculator_name == "pelvic_obliquity_angle":
            values = self._calculate_pelvic_obliquity(metric_def, pose_sequence)
        elif calculator_name == "vertical_elevation_ratio":
            values = self._calculate_vertical_elevation_ratio(metric_def, pose_sequence)
        elif calculator_name.startswith(("lumbar_curvature", "thoracic_curvature")):
            values = segment_features.get(metric_def.id, np.array([])) if segment_features else np.array([])
        elif calculator_name.startswith("shoulder_lift"):
            values = segment_features.get(metric_def.id, np.array([])) if segment_features else np.array([])
        elif calculator_name.startswith("pelvic_tilt"):
            values = self._calculate_pelvic_tilt(metric_def, pose_sequence)
        else:
            values = self._calculate_joint_angle(metric_def, pose_sequence)

        if len(values) == 0:
            return {
                "metric_id": metric_def.id,
                "name": metric_def.name_zh,
                "values": [],
                "statistics": {},
                "errors": [],
                "viewpoint_warning": viewpoint_warning,
            }

        # 计算统计信息
        valid_values = values[~np.isnan(values)]
        statistics = {
            "mean": float(np.mean(valid_values)) if len(valid_values) > 0 else None,
            "std": float(np.std(valid_values)) if len(valid_values) > 0 else None,
            "min": float(np.min(valid_values)) if len(valid_values) > 0 else None,
            "max": float(np.max(valid_values)) if len(valid_values) > 0 else None,
            "range": float(np.max(valid_values) - np.min(valid_values)) if len(valid_values) > 0 else None,
        }

        # 添加视角信息
        if self.use_viewpoint_analysis and self._viewpoint_result:
            statistics["viewpoint"] = self._viewpoint_result.viewpoint.value
            statistics["viewpoint_confidence"] = self._viewpoint_result.confidence
            statistics["used_side"] = self._selected_side
            statistics["reliability"] = reliability

        # 使用动作阶段检测获取关键帧进行错误评估
        errors = []
        if self.use_phase_detection:
            errors = self._detect_errors_with_phase(
                metric_def, values, pose_sequence, action_name
            )
            phase_detector = create_phase_detector(action_name)
            if phase_detector:
                # 从配置获取评估阶段
                evaluation_phase = self._get_evaluation_phase(metric_def.id)
                key_frame = phase_detector.get_key_frame_for_phase(
                    pose_sequence, evaluation_phase
                )
                if key_frame is not None and 0 <= key_frame < len(values):
                    statistics["key_frame_value"] = float(values[key_frame])
                    statistics["key_frame_index"] = key_frame
                    statistics["evaluation_phase"] = evaluation_phase

        return {
            "metric_id": metric_def.id,
            "name": metric_def.name_zh,
            "description": metric_def.description,
            "category": metric_def.category.value,
            "unit": metric_def.unit,
            "values": values.tolist(),
            "statistics": statistics,
            "errors": errors,
            "viewpoint_warning": viewpoint_warning,
        }

    def calculate_all_metrics(
        self,
        pose_sequence: PoseSequence,
        metric_ids: Optional[List[str]] = None,
        segment_features: Optional[Dict[str, np.ndarray]] = None,
        action_name: str = "squat",
    ) -> Dict[str, Dict[str, Any]]:
        """计算所有检测项."""
        results = {}

        ids_to_calculate = metric_ids if metric_ids else list(METRIC_TEMPLATES.keys())

        # 如果使用视角分析，先分析视角并过滤检测项
        if self.use_viewpoint_analysis and self._viewpoint_analyzer:
            viewpoint_result = self._viewpoint_analyzer.analyze(pose_sequence)
            valid_metrics, warnings = ConstraintManager.filter_metrics_by_viewpoint(
                ids_to_calculate, viewpoint_result.viewpoint, min_reliability=0.3
            )

            # 记录被跳过的检测项
            for warning in warnings:
                results[warning["metric_id"]] = {
                    "metric_id": warning["metric_id"],
                    "name": warning["metric_name"],
                    "error": warning["reason"],
                    "skipped": True,
                    "reliability": warning["reliability"],
                }

            ids_to_calculate = valid_metrics

        for metric_id in ids_to_calculate:
            metric_def = METRIC_TEMPLATES.get(metric_id)
            if not metric_def:
                continue

            try:
                result = self.calculate_metric(
                    metric_def, pose_sequence, segment_features, action_name
                )
                results[metric_id] = result
            except Exception as e:
                results[metric_id] = {
                    "metric_id": metric_id,
                    "error": str(e),
                    "values": [],
                    "statistics": {},
                }

        return results

    def _auto_select_side(self, pose_sequence: PoseSequence) -> str:
        """自动选择左右侧.

        基于以下标准：
        1. 关键点可见性（置信度）
        2. 运动范围（哪侧运动更明显）
        3. 朝向（哪侧更靠近镜头）
        """
        if len(pose_sequence) == 0:
            return "right"  # 默认右侧

        # 计算左右侧的可见性
        left_visible = []
        right_visible = []

        for frame in pose_sequence.frames:
            left_points = ["left_hip", "left_knee", "left_ankle"]
            right_points = ["right_hip", "right_knee", "right_ankle"]

            left_conf = [
                frame.get_keypoint(p).confidence
                for p in left_points
                if frame.get_keypoint(p)
            ]
            right_conf = [
                frame.get_keypoint(p).confidence
                for p in right_points
                if frame.get_keypoint(p)
            ]

            left_visible.append(np.mean(left_conf) if left_conf else 0)
            right_visible.append(np.mean(right_conf) if right_conf else 0)

        avg_left = np.mean(left_visible)
        avg_right = np.mean(right_visible)

        # 可见性差异较大时选择可见性高的一侧
        if abs(avg_left - avg_right) > 0.1:
            return "left" if avg_left > avg_right else "right"

        # 可见性相近，比较运动范围
        left_range = self._calculate_side_range(pose_sequence, "left")
        right_range = self._calculate_side_range(pose_sequence, "right")

        if abs(left_range - right_range) > 0.05:
            return "left" if left_range > right_range else "right"
            
        # [静态启发式规则] 当运动幅度都很小（比如纯静态动作），引入角度启发式
        # 兼容 "quadriceps_stretch" 和配置文件中可能带来的 action_id 
        # (比如由于 action_id 和 action_name 映射导致没有被设置对)
        if ("quadriceps" in str(self.action_id).lower() or "stretch" in str(self.action_id).lower()) and len(pose_sequence.frames) > 0:
            # 股四头肌拉伸：哪只脚弯曲得更厉害（角度更小），哪只脚就是拉伸脚
            first_frame = pose_sequence.frames[0]
            
            def get_knee_angle(side):
                hip = first_frame.get_keypoint(f"{side}_hip")
                knee = first_frame.get_keypoint(f"{side}_knee")
                ankle = first_frame.get_keypoint(f"{side}_ankle")
                # 必须确保关键点存在且置信度不为 None
                if hip and knee and ankle and hip.confidence is not None and knee.confidence is not None and ankle.confidence is not None:
                    v1 = np.array([hip.x - knee.x, hip.y - knee.y])
                    v2 = np.array([ankle.x - knee.x, ankle.y - knee.y])
                    norm1, norm2 = np.linalg.norm(v1), np.linalg.norm(v2)
                    if norm1 > 1e-6 and norm2 > 1e-6:
                        cos_theta = np.clip(np.dot(v1, v2) / (norm1 * norm2), -1.0, 1.0)
                        return np.degrees(np.arccos(cos_theta))
                return 180.0
                
            left_angle = get_knee_angle("left")
            right_angle = get_knee_angle("right")
            
            # 【基于阈值的锁定机制】: 差值大于 20 度才锁定，排除站立时的微小误差
            if abs(left_angle - right_angle) > 20.0:
                return "left" if left_angle < right_angle else "right"
            else:
                return None  # 角度差不够大，保持未锁定状态 (Unlocked)

        # 默认 fallback
        # 如果是单帧流式处理且未能通过前面任何规则锁定，保持未锁定
        if len(pose_sequence.frames) <= 1:
            return None
            
        return "right"

    def _calculate_side_range(self, pose_sequence: PoseSequence, side: str) -> float:
        """计算一侧关键点的运动范围."""
        knee_points = []
        for frame in pose_sequence.frames:
            knee = frame.get_keypoint(f"{side}_knee")
            if knee and knee.confidence > self.min_confidence:
                knee_points.append(knee.y)

        if len(knee_points) < 2:
            return 0.0

        return max(knee_points) - min(knee_points)

    def _detect_errors_with_phase(
        self,
        metric_def: MetricDefinition,
        values: np.ndarray,
        pose_sequence: PoseSequence,
        action_name: str,
    ) -> List[Dict[str, Any]]:
        """使用动作阶段检测来评估错误.

        从配置系统加载错误条件（ErrorCondition），支持灵活的条件表达式。
        """
        errors = []

        # 从配置获取该检测项的错误条件
        metric_config = self._metric_configs.get(metric_def.id)
        if not metric_config or not metric_config.error_conditions:
            return errors

        phase_detector = create_phase_detector(action_name)
        if not phase_detector:
            return errors

        key_frame = phase_detector.get_key_frame_for_metric(
            pose_sequence, metric_def.id
        )

        if key_frame is None or key_frame >= len(values):
            return errors

        key_value = values[key_frame]
        if np.isnan(key_value):
            return errors

        # 使用配置中的错误条件评估
        for condition in metric_config.error_conditions:
            is_error = self._evaluate_error_condition(condition, key_value)

            if is_error:
                errors.append({
                    "id": condition.error_id,
                    "name": condition.error_name,
                    "description": condition.description,
                    "severity": condition.severity,
                    "key_frame": key_frame,
                    "key_value": float(key_value),
                })

        return errors

    def _evaluate_error_condition(
        self,
        condition: ErrorCondition,
        value: float,
    ) -> bool:
        """评估错误条件.

        支持从配置读取的条件表达式（operator + value/phase）。
        """
        # 1. 优先使用 condition 字典（新配置格式）
        if condition.condition:
            op = condition.condition.get("operator", "gt")
            threshold = condition.condition.get("value")
            # phase 检查已在调用处处理（key_frame选择）

            if threshold is not None:
                return self._apply_operator(value, op, threshold)

        # 2. 向后兼容：使用简单阈值
        if condition.threshold_low is not None and value < condition.threshold_low:
            return True
        if condition.threshold_high is not None and value > condition.threshold_high:
            return True

        return False

    def _apply_operator(self, value: float, op: str, threshold: float) -> bool:
        """应用比较操作符."""
        operators = {
            "lt": lambda v, t: v < t,
            "lte": lambda v, t: v <= t,
            "gt": lambda v, t: v > t,
            "gte": lambda v, t: v >= t,
            "eq": lambda v, t: abs(v - t) < 1e-6,
            "neq": lambda v, t: abs(v - t) >= 1e-6,
        }
        func = operators.get(op, operators["gt"])
        return func(value, threshold)

    # ============== 计算方法（使用自动选择的侧面） ==============

    def _get_keypoint_with_side(self, frame: PoseFrame, base_name: str) -> Optional[Keypoint]:
        """获取关键点，使用自动选择的侧面."""
        # 如果已经选择了侧面，优先使用
        if self._selected_side:
            kp = frame.get_keypoint(f"{self._selected_side}_{base_name}")
            if kp and kp.confidence > self.min_confidence:
                return kp

        # 否则尝试左右两侧，选择置信度更高的
        left_kp = frame.get_keypoint(f"left_{base_name}")
        right_kp = frame.get_keypoint(f"right_{base_name}")

        if left_kp and right_kp:
            return left_kp if left_kp.confidence >= right_kp.confidence else right_kp
        elif left_kp:
            return left_kp
        elif right_kp:
            return right_kp

        return None

    def _calculate_joint_angle(
        self,
        metric_def: MetricDefinition,
        pose_sequence: PoseSequence,
    ) -> np.ndarray:
        """计算关节角度（使用自动选择的侧面）."""
        values = []

        required = metric_def.required_keypoints
        if len(required) < 3:
            return np.array([])

        # 映射关键点名称到实际使用的一侧
        point_names = required[:3]  # 只需要前3个点来计算角度

        for frame in pose_sequence.frames:
            # 获取三个关键点
            kp1 = self._get_keypoint_with_side(frame, point_names[0])
            kp2 = self._get_keypoint_with_side(frame, point_names[1])
            kp3 = self._get_keypoint_with_side(frame, point_names[2])

            if kp1 and kp2 and kp3:
                angle = calculate_angle_2d(
                    (kp1.x, kp1.y),
                    (kp2.x, kp2.y),
                    (kp3.x, kp3.y),
                    min_confidence=self.min_confidence,
                    confidences=(kp1.confidence, kp2.confidence, kp3.confidence),
                )
                values.append(angle)
            else:
                values.append(np.nan)

        return np.array(values)

    def _calculate_knee_valgus(
        self,
        metric_def: MetricDefinition,
        pose_sequence: PoseSequence,
    ) -> np.ndarray:
        """计算膝关节外翻角度."""
        values = []

        for frame in pose_sequence.frames:
            hip = self._get_keypoint_with_side(frame, "hip")
            knee = self._get_keypoint_with_side(frame, "knee")
            ankle = self._get_keypoint_with_side(frame, "ankle")

            if hip and knee and ankle:
                # 使用选定的侧面计算
                hip_to_ankle_x = ankle.x - hip.x
                hip_to_ankle_y = ankle.y - hip.y
                knee_to_ankle_x = ankle.x - knee.x
                knee_to_ankle_y = ankle.y - knee.y

                cross = hip_to_ankle_x * knee_to_ankle_y - hip_to_ankle_y * knee_to_ankle_x
                dot = hip_to_ankle_x * knee_to_ankle_x + hip_to_ankle_y * knee_to_ankle_y
                norm1 = np.sqrt(hip_to_ankle_x**2 + hip_to_ankle_y**2)
                norm2 = np.sqrt(knee_to_ankle_x**2 + knee_to_ankle_y**2)

                if norm1 > 0 and norm2 > 0:
                    cos_angle = np.clip(dot / (norm1 * norm2), -1.0, 1.0)
                    angle = np.degrees(np.arccos(cos_angle))
                    if cross < 0:
                        angle = -angle
                    values.append(angle)
                else:
                    values.append(np.nan)
            else:
                values.append(np.nan)

        return np.array(values)

    def _calculate_trunk_lean(
        self,
        metric_def: MetricDefinition,
        pose_sequence: PoseSequence,
    ) -> np.ndarray:
        """计算躯干前倾角度."""
        values = []

        for frame in pose_sequence.frames:
            # 获取肩中心和髋中心（使用选定侧的肩和髋计算中心）
            left_shoulder = frame.get_keypoint("left_shoulder")
            right_shoulder = frame.get_keypoint("right_shoulder")
            left_hip = frame.get_keypoint("left_hip")
            right_hip = frame.get_keypoint("right_hip")

            if all([left_shoulder, right_shoulder, left_hip, right_hip]):
                shoulder_x = (left_shoulder.x + right_shoulder.x) / 2
                shoulder_y = (left_shoulder.y + right_shoulder.y) / 2
                hip_x = (left_hip.x + right_hip.x) / 2
                hip_y = (left_hip.y + right_hip.y) / 2

                dx = shoulder_x - hip_x
                dy = shoulder_y - hip_y

                if abs(dy) > 1e-6:
                    angle = np.degrees(np.arctan(abs(dx) / abs(dy)))
                    values.append(angle)
                else:
                    values.append(90.0)
            else:
                values.append(np.nan)

        return np.array(values)

    def _calculate_trunk_rotation(
        self,
        metric_def: MetricDefinition,
        pose_sequence: PoseSequence,
    ) -> np.ndarray:
        """计算躯干旋转角度."""
        values = []

        for frame in pose_sequence.frames:
            left_shoulder = frame.get_keypoint("left_shoulder")
            right_shoulder = frame.get_keypoint("right_shoulder")
            left_hip = frame.get_keypoint("left_hip")
            right_hip = frame.get_keypoint("right_hip")

            if all([left_shoulder, right_shoulder, left_hip, right_hip]):
                shoulder_dx = right_shoulder.x - left_shoulder.x
                shoulder_dy = right_shoulder.y - left_shoulder.y
                shoulder_angle = np.degrees(np.arctan2(shoulder_dy, shoulder_dx))

                hip_dx = right_hip.x - left_hip.x
                hip_dy = right_hip.y - left_hip.y
                hip_angle = np.degrees(np.arctan2(hip_dy, hip_dx))

                rotation = shoulder_angle - hip_angle
                while rotation > 90:
                    rotation -= 180
                while rotation < -90:
                    rotation += 180

                values.append(rotation)
            else:
                values.append(np.nan)

        return np.array(values)

    def _calculate_vertical_symmetry(
        self,
        metric_def: MetricDefinition,
        pose_sequence: PoseSequence,
    ) -> np.ndarray:
        """计算垂直对称性."""
        values = []

        for frame in pose_sequence.frames:
            left_knee = frame.get_keypoint("left_knee")
            right_knee = frame.get_keypoint("right_knee")

            if left_knee and right_knee:
                diff = abs(left_knee.y - right_knee.y)
                values.append(diff)
            else:
                values.append(np.nan)

        return np.array(values)

    def _calculate_angle_range(
        self,
        metric_def: MetricDefinition,
        pose_sequence: PoseSequence,
    ) -> np.ndarray:
        """计算角度活动范围."""
        angle_values = self._calculate_joint_angle(metric_def, pose_sequence)

        if len(angle_values) == 0:
            return np.array([])

        valid_values = angle_values[~np.isnan(angle_values)]
        if len(valid_values) == 0:
            return np.array([])

        range_value = np.max(valid_values) - np.min(valid_values)
        return np.array([range_value] * len(angle_values))

    def _calculate_pelvic_tilt(
        self,
        metric_def: MetricDefinition,
        pose_sequence: PoseSequence,
    ) -> np.ndarray:
        """计算骨盆倾斜角度."""
        values = []

        for frame in pose_sequence.frames:
            left_hip = frame.get_keypoint("left_hip")
            right_hip = frame.get_keypoint("right_hip")
            left_shoulder = frame.get_keypoint("left_shoulder")
            right_shoulder = frame.get_keypoint("right_shoulder")

            if all([left_hip, right_hip, left_shoulder, right_shoulder]):
                hip_dx = right_hip.x - left_hip.x
                hip_dy = right_hip.y - left_hip.y
                hip_angle = np.degrees(np.arctan2(hip_dy, hip_dx))

                shoulder_dx = right_shoulder.x - left_shoulder.x
                shoulder_dy = right_shoulder.y - left_shoulder.y
                shoulder_angle = np.degrees(np.arctan2(shoulder_dy, shoulder_dx))

                tilt = hip_angle - shoulder_angle
                values.append(tilt)
            else:
                values.append(np.nan)

        return np.array(values)

    # ============== 配置系统集成方法 ==============

    def reset(self) -> None:
        """重置计算器状态（用于新视频）."""
        self._selected_side = None
        self._viewpoint_result = None

    def reload_config(self) -> bool:
        """重新加载动作配置.

        Returns:
            是否成功加载
        """
        self._action_config = self._config_manager.load_config(
            self.action_id, use_cache=False
        )
        if self._action_config:
            self._metric_configs = {
                m.metric_id: m for m in self._action_config.metrics
            }
            return True
        return False

    def _get_evaluation_phase(self, metric_id: str) -> str:
        """获取检测项的评估阶段.

        从配置中读取，如果不存在则返回默认值"bottom"。
        """
        metric_config = self._metric_configs.get(metric_id)
        if metric_config and metric_config.evaluation_phase:
            return metric_config.evaluation_phase
        return "bottom"  # 默认在最低点评估

    def get_metric_config(self, metric_id: str) -> Optional[MetricConfig]:
        """获取检测项配置.

        Args:
            metric_id: 检测项ID

        Returns:
            检测项配置或None
        """
        return self._metric_configs.get(metric_id)

    def get_action_config_summary(self) -> Dict[str, Any]:
        """获取动作配置摘要（用于记录和调试）."""
        if not self._action_config:
            return {"action_id": self.action_id, "loaded": False}

        return {
            "action_id": self._action_config.action_id,
            "action_name": self._action_config.action_name,
            "version": self._action_config.version,
            "loaded": True,
            "metrics_count": len(self._action_config.metrics),
            "enabled_metrics": [
                m.metric_id for m in self._action_config.metrics if m.enabled
            ],
            "phases": [p.phase_id for p in self._action_config.phases],
            "global_params": self._action_config.global_params,
        }

    # ============== 侧抬腿专用计算器 ==============

    def _calculate_hip_abduction(
        self,
        metric_def: MetricDefinition,
        pose_sequence: PoseSequence,
    ) -> np.ndarray:
        """计算髋关节外展角度（冠状面）.

        测量大腿与躯干垂线的夹角，用于侧抬腿动作评估。
        """
        values = []

        for frame in pose_sequence.frames:
            # 获取肩中心、髋和膝的关键点
            left_shoulder = frame.get_keypoint("left_shoulder")
            right_shoulder = frame.get_keypoint("right_shoulder")
            hip = self._get_keypoint_with_side(frame, "hip")
            knee = self._get_keypoint_with_side(frame, "knee")

            if hip and knee and (left_shoulder or right_shoulder):
                # 计算肩中心
                if left_shoulder and right_shoulder:
                    shoulder_x = (left_shoulder.x + right_shoulder.x) / 2
                    shoulder_y = (left_shoulder.y + right_shoulder.y) / 2
                elif left_shoulder:
                    shoulder_x, shoulder_y = left_shoulder.x, left_shoulder.y
                else:
                    shoulder_x, shoulder_y = right_shoulder.x, right_shoulder.y

                # 躯干垂线向量（从上向下）
                torso_dx = hip.x - shoulder_x
                torso_dy = hip.y - shoulder_y

                # 大腿向量（从髋到膝）
                thigh_dx = knee.x - hip.x
                thigh_dy = knee.y - hip.y

                # 计算两向量夹角
                dot = torso_dx * thigh_dx + torso_dy * thigh_dy
                norm_torso = np.sqrt(torso_dx**2 + torso_dy**2)
                norm_thigh = np.sqrt(thigh_dx**2 + thigh_dy**2)

                if norm_torso > 0 and norm_thigh > 0:
                    cos_angle = np.clip(dot / (norm_torso * norm_thigh), -1.0, 1.0)
                    angle = np.degrees(np.arccos(cos_angle))
                    values.append(angle)
                else:
                    values.append(np.nan)
            else:
                values.append(np.nan)

        return np.array(values)

    def _calculate_hip_rotation(
        self,
        metric_def: MetricDefinition,
        pose_sequence: PoseSequence,
    ) -> np.ndarray:
        """计算髋关节外旋角度（水平面投影）.

        基于髋-膝-踝在水平面的投影关系估算外旋角度。
        """
        values = []

        for frame in pose_sequence.frames:
            hip = self._get_keypoint_with_side(frame, "hip")
            knee = self._get_keypoint_with_side(frame, "knee")
            ankle = self._get_keypoint_with_side(frame, "ankle")

            if hip and knee and ankle:
                # 使用x坐标差异估算水平面旋转（简化计算）
                # 正常侧抬腿时，膝应该在髋的外侧（x方向偏离）
                hip_to_knee_x = knee.x - hip.x
                hip_to_knee_y = knee.y - hip.y
                knee_to_ankle_x = ankle.x - knee.x

                # 计算膝-踝连线与髋-膝连线的水平偏离
                if abs(hip_to_knee_y) > 1e-6:
                    # 估算旋转角度
                    rotation = np.degrees(np.arctan2(
                        knee_to_ankle_x,
                        abs(hip_to_knee_y)
                    ))
                    values.append(rotation)
                else:
                    values.append(0.0)
            else:
                values.append(np.nan)

        return np.array(values)

    def _calculate_trunk_lateral_flexion(
        self,
        metric_def: MetricDefinition,
        pose_sequence: PoseSequence,
    ) -> np.ndarray:
        """计算躯干侧倾角度（冠状面）.

        测量躯干相对于垂直方向的侧向倾斜，用于检测侧抬腿时的躯干代偿。
        """
        values = []

        for frame in pose_sequence.frames:
            left_shoulder = frame.get_keypoint("left_shoulder")
            right_shoulder = frame.get_keypoint("right_shoulder")
            left_hip = frame.get_keypoint("left_hip")
            right_hip = frame.get_keypoint("right_hip")

            if all([left_shoulder, right_shoulder, left_hip, right_hip]):
                # 计算肩中心和髋中心
                shoulder_x = (left_shoulder.x + right_shoulder.x) / 2
                shoulder_y = (left_shoulder.y + right_shoulder.y) / 2
                hip_x = (left_hip.x + right_hip.x) / 2
                hip_y = (left_hip.y + right_hip.y) / 2

                # 躯干向量
                dx = shoulder_x - hip_x
                dy = shoulder_y - hip_y

                # 计算与垂直方向的夹角（侧倾）
                if abs(dy) > 1e-6:
                    # 侧倾角度：躯干偏离垂直线的程度
                    lateral_angle = np.degrees(np.arctan(abs(dx) / abs(dy)))
                    # 根据dx符号确定方向（向抬腿侧倾斜为负，向对侧倾斜为正）
                    if self._selected_side == "left":
                        lateral_angle = -lateral_angle if dx > 0 else lateral_angle
                    else:
                        lateral_angle = lateral_angle if dx > 0 else -lateral_angle
                    values.append(lateral_angle)
                else:
                    values.append(0.0)
            else:
                values.append(np.nan)

        return np.array(values)

    def _calculate_pelvic_obliquity(
        self,
        metric_def: MetricDefinition,
        pose_sequence: PoseSequence,
    ) -> np.ndarray:
        """计算骨盆倾斜度（冠状面）.

        测量左右髂嵴的高度差，检测骨盆冠状面的倾斜。
        """
        values = []

        for frame in pose_sequence.frames:
            left_hip = frame.get_keypoint("left_hip")
            right_hip = frame.get_keypoint("right_hip")

            if left_hip and right_hip:
                # 计算骨盆倾斜角度
                # 正常情况下左右髋应该水平
                hip_dx = right_hip.x - left_hip.x
                hip_dy = right_hip.y - left_hip.y

                if abs(hip_dx) > 1e-6:
                    # 骨盆倾斜角度（正值表示右侧抬高，负值表示左侧抬高）
                    obliquity = np.degrees(np.arctan(hip_dy / hip_dx))
                    values.append(obliquity)
                else:
                    values.append(0.0)
            else:
                values.append(np.nan)

        return np.array(values)

    def _calculate_vertical_elevation_ratio(
        self,
        metric_def: MetricDefinition,
        pose_sequence: PoseSequence,
    ) -> np.ndarray:
        """计算腿部垂直抬升比例.

        测量抬腿高度相对于支撑腿或躯干的比例。
        """
        values = []

        for frame in pose_sequence.frames:
            # 获取两侧髋和踝的关键点
            left_hip = frame.get_keypoint("left_hip")
            right_hip = frame.get_keypoint("right_hip")
            left_ankle = frame.get_keypoint("left_ankle")
            right_ankle = frame.get_keypoint("right_ankle")

            if all([left_hip, right_hip, left_ankle, right_ankle]):
                # 确定支撑腿和抬腿
                if self._selected_side == "left":
                    lift_hip, lift_ankle = left_hip, left_ankle
                    support_hip, support_ankle = right_hip, right_ankle
                else:
                    lift_hip, lift_ankle = right_hip, right_ankle
                    support_hip, support_ankle = left_hip, left_ankle

                # 计算抬升高度（相对于支撑髋的垂直距离）
                hip_to_ankle_y = support_hip.y - support_ankle.y  # 支撑腿长度参考
                lift_height = support_hip.y - lift_ankle.y  # 抬腿踝的高度

                if abs(hip_to_ankle_y) > 1e-6:
                    # 计算抬升比例（相对于支撑腿长度的比例）
                    ratio = lift_height / hip_to_ankle_y
                    # 限制在合理范围内
                    ratio = np.clip(ratio, -0.5, 1.5)
                    values.append(ratio)
                else:
                    values.append(0.0)
            else:
                values.append(np.nan)

        return np.array(values)
