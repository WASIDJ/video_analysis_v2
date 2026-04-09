"""模板生成器.

基于探索结果自动生成动作配置文件。
"""
from typing import Dict, List, Optional, Any
from datetime import datetime
import json

from src.core.config.models import (
    ActionConfig,
    MetricConfig,
    MetricThreshold,
    ErrorCondition,
    PhaseDefinition,
)
from .exploration import ExplorationResult


class TemplateGenerator:
    """动作配置模板生成器."""

    # 默认权重配置
    DEFAULT_WEIGHTS = {
        "knee_flexion": 1.5,
        "hip_flexion": 1.2,
        "trunk_lean": 1.0,
        "knee_valgus": 1.0,
        "ankle_dorsiflexion": 0.8,
        "lumbar_curvature": 1.2,
        "default": 1.0,
    }

    # 阶段检测参数模板
    PHASE_DETECTION_TEMPLATES = {
        "descent": {
            "phase_id": "descent",
            "phase_name": "下降阶段",
            "description": "动作向下运动阶段",
            "detection_params": {
                "driver_signal": "knee_flexion",
                "velocity_threshold": -2.0,
            },
        },
        "bottom": {
            "phase_id": "bottom",
            "phase_name": "最低点",
            "description": "动作最低点/发力点",
            "detection_params": {
                "extremum_type": "valley",
            },
        },
        "ascent": {
            "phase_id": "ascent",
            "phase_name": "上升阶段",
            "description": "动作向上运动阶段",
            "detection_params": {
                "driver_signal": "knee_flexion",
                "velocity_threshold": 2.0,
            },
        },
    }

    def __init__(self, version: str = "1.0.0"):
        """
        Args:
            version: 生成的配置版本号
        """
        self.version = version

    def generate_from_exploration(
        self,
        exploration_result: ExplorationResult,
        action_id: Optional[str] = None,
        action_name_zh: Optional[str] = None,
    ) -> ActionConfig:
        """基于探索结果生成动作配置.

        Args:
            exploration_result: 探索结果
            action_id: 动作ID（如未提供则使用探索结果中的名称）
            action_name_zh: 中文名称

        Returns:
            生成的动作配置
        """
        action_id = action_id or exploration_result.action_name.lower().replace(" ", "_")

        # 1. 生成阶段定义
        phases = self._generate_phases(exploration_result)

        # 2. 生成检测项配置
        metrics = self._generate_metrics(exploration_result)

        # 3. 生成全局参数
        global_params = self._generate_global_params(exploration_result)

        return ActionConfig(
            action_id=action_id,
            action_name=exploration_result.action_name,
            action_name_zh=action_name_zh or exploration_result.action_name,
            description=exploration_result.description,
            version=self.version,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            phases=phases,
            metrics=metrics,
            global_params=global_params,
            metadata={
                "auto_generated": True,
                "generation_confidence": exploration_result.confidence,
                "exploration_tags": ["new_action"],
            },
        )

    def _generate_phases(self, exploration_result: ExplorationResult) -> List[PhaseDefinition]:
        """生成阶段定义."""
        phases = []

        # 始终添加起始阶段
        phases.append(PhaseDefinition(
            phase_id="start",
            phase_name="起始",
            description="动作开始前的准备姿态",
            detection_params={},
        ))

        # 基于探索结果的阶段候选生成阶段
        for i, phase_candidate in enumerate(exploration_result.phase_candidates):
            phase_id = phase_candidate.get("phase_id", f"phase_{i}")
            phase_name = phase_candidate.get("phase_name", f"阶段{i+1}")

            # 构建检测参数
            detection_params = {
                "primary_metric": phase_candidate.get("primary_metric"),
                "velocity": phase_candidate.get("velocity"),
            }

            # 添加阈值信息
            metric_range = phase_candidate.get("metric_range")
            if metric_range:
                detection_params["metric_range"] = metric_range

            phases.append(PhaseDefinition(
                phase_id=phase_id,
                phase_name=phase_name,
                description=f"自动检测到的阶段: {phase_name}",
                detection_params=detection_params,
            ))

        # 如果没有检测到足够的阶段，使用默认模板
        if len(phases) < 3:
            phases = self._get_default_phases()

        return phases

    def _get_default_phases(self) -> List[PhaseDefinition]:
        """获取默认阶段模板."""
        return [
            PhaseDefinition(
                phase_id="start",
                phase_name="起始",
                description="动作开始",
                detection_params={},
            ),
            PhaseDefinition(
                phase_id="execution",
                phase_name="执行",
                description="主要动作执行阶段",
                detection_params={},
            ),
            PhaseDefinition(
                phase_id="end",
                phase_name="结束",
                description="动作完成",
                detection_params={},
            ),
        ]

    def _generate_metrics(self, exploration_result: ExplorationResult) -> List[MetricConfig]:
        """生成检测项配置."""
        metrics = []

        suggested_thresholds = exploration_result.suggested_thresholds

        for metric_id in exploration_result.suggested_metrics:
            threshold_data = suggested_thresholds.get(metric_id, {})

            # 构建阈值配置
            thresholds = MetricThreshold()
            if "target_value" in threshold_data:
                thresholds.target_value = threshold_data["target_value"]
            if "normal_range" in threshold_data:
                thresholds.normal_range = threshold_data["normal_range"]
            if "excellent_range" in threshold_data:
                thresholds.excellent_range = threshold_data["excellent_range"]
            if "pass_range" in threshold_data:
                thresholds.pass_range = threshold_data["pass_range"]

            # 确定评估阶段
            evaluation_phase = self._determine_evaluation_phase(
                metric_id, exploration_result
            )

            # 获取权重
            weight = self.DEFAULT_WEIGHTS.get(metric_id, self.DEFAULT_WEIGHTS["default"])

            metrics.append(MetricConfig(
                metric_id=metric_id,
                enabled=True,
                evaluation_phase=evaluation_phase,
                thresholds=thresholds,
                error_conditions=[],  # 新生成的配置不包含错误条件（需要通过训练数据学习）
                custom_params={
                    "auto_generated": True,
                    "confidence": threshold_data.get("confidence", "low"),
                },
                weight=weight,
            ))

        return metrics

    def _determine_evaluation_phase(
        self,
        metric_id: str,
        exploration_result: ExplorationResult,
    ) -> str:
        """确定检测项的评估阶段."""
        # 如果阶段候选中有明确信息，使用它
        for phase in exploration_result.phase_candidates:
            if phase.get("primary_metric") == metric_id:
                return phase.get("phase_id", "execution")

        # 默认规则
        if "knee" in metric_id or "hip" in metric_id:
            return "bottom" if any(p.get("phase_id") == "bottom" for p in exploration_result.phase_candidates) else "execution"

        return "execution"

    def _generate_global_params(self, exploration_result: ExplorationResult) -> Dict[str, Any]:
        """生成全局参数."""
        return {
            "min_phase_duration": 0.2,
            "enable_phase_detection": True,
            "use_viewpoint_analysis": True,
            "auto_select_side": True,
            "exploration_mode": False,  # 生成的是正式配置，不是探索模式
            "auto_generated": True,
            "generation_confidence": exploration_result.confidence,
            "viewpoint_constraints": {
                "sagittal": {
                    "supported_metrics": exploration_result.suggested_metrics[:5],
                    "unsupported_metrics": [],
                },
                "frontal": {
                    "supported_metrics": [],
                    "unsupported_metrics": exploration_result.suggested_metrics[:3],
                },
            },
        }

    def generate_with_error_conditions(
        self,
        action_id: str,
        standard_fingerprints: List[Any],  # ActionFingerprint list
        error_fingerprints: Dict[str, List[Any]],  # error_type -> fingerprints
    ) -> ActionConfig:
        """基于标准动作和错误动作样本生成配置（含错误条件）.

        这是参数迭代的核心方法，通过对比正确和错误样本学习错误判断条件。

        Args:
            action_id: 动作ID
            standard_fingerprints: 标准动作指纹列表
            error_fingerprints: 按错误类型分类的错误动作指纹

        Returns:
            包含错误条件的完整配置
        """
        # TODO: 实现基于对比学习的错误条件生成
        # 1. 聚合标准指纹得到"金标准"范围
        # 2. 分析错误指纹与标准的差异模式
        # 3. 为每种错误类型生成判断条件

        raise NotImplementedError("错误条件生成功能待实现")

    def save_config(
        self,
        config: ActionConfig,
        output_path: str,
        indent: int = 2,
    ) -> bool:
        """保存配置到文件.

        Args:
            config: 动作配置
            output_path: 输出路径
            indent: JSON缩进

        Returns:
            是否保存成功
        """
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(config.to_dict(), f, indent=indent, ensure_ascii=False)
            return True
        except Exception as e:
            print(f"保存配置失败: {e}")
            return False


def create_exploration_template(
    exploration_result: ExplorationResult,
    output_dir: str = "config/action_configs",
) -> Optional[str]:
    """便捷函数：从探索结果创建配置模板文件.

    Args:
        exploration_result: 探索结果
        output_dir: 输出目录

    Returns:
        生成的文件路径，失败返回None
    """
    import os

    generator = TemplateGenerator()
    config = generator.generate_from_exploration(exploration_result)

    # 确保目录存在
    os.makedirs(output_dir, exist_ok=True)

    # 生成文件名
    filename = f"{config.action_id}_generated.json"
    filepath = os.path.join(output_dir, filename)

    # 检查文件是否已存在，避免覆盖
    counter = 1
    while os.path.exists(filepath):
        filename = f"{config.action_id}_generated_v{counter}.json"
        filepath = os.path.join(output_dir, filename)
        counter += 1

    if generator.save_config(config, filepath):
        return filepath
    return None
