"""探索模式分析器.

当遇到未定义的新动作时，进入探索模式，全面分析动作特征。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
import numpy as np
from collections import defaultdict

from src.core.models.base import PoseSequence
from src.core.metrics.definitions import MetricDefinition, METRIC_TEMPLATES, MetricCategory
from src.core.metrics.calculator import MetricsCalculator
from .fingerprint import FingerprintAnalyzer, ActionFingerprint


@dataclass
class ExplorationResult:
    """探索模式分析结果."""
    action_name: str
    description: str

    # 发现的特征
    dominant_metrics: List[Dict[str, Any]]
    phase_candidates: List[Dict[str, Any]]
    symmetry_analysis: Dict[str, Any]

    # 建议
    suggested_metrics: List[str]           # 建议纳入检测的指标
    suggested_phases: List[str]            # 建议的阶段划分
    suggested_thresholds: Dict[str, Any]   # 建议的阈值范围

    # 置信度
    confidence: float


def get_default_exploration_config() -> Dict[str, Any]:
    """获取默认探索模式配置.

    当找不到动作配置时，使用此配置进行全面分析。
    """
    return {
        "action_id": "exploration",
        "action_name": "Exploration Mode",
        "description": "新动作探索模式 - 启用所有指标进行全面分析",
        "phases": [
            {
                "phase_id": "analysis",
                "phase_name": "分析阶段",
                "description": "探索模式下的全量分析",
            }
        ],
        "metrics": [
            # 启用所有可用的检测项，但不设置具体的阈值
            # 这些将在探索过程中动态分析
        ],
        "global_params": {
            "exploration_mode": True,
            "enable_all_metrics": True,
            "record_raw_data": True,
            "min_significance_threshold": 0.05,
        },
    }


class ExplorationAnalyzer:
    """探索模式分析器.

    对未知动作进行全面分析，发现其关键特征和阶段模式。
    """

    # 阶段候选检测的配置
    PHASE_DETECTION_CONFIG = {
        "min_phase_duration": 0.3,      # 最小阶段持续时间（秒）
        "prominence_threshold": 0.3,     # 极值显著性阈值
        "smoothing_window": 5,           # 平滑窗口大小
    }

    def __init__(self, min_significance: float = 0.05):
        """
        Args:
            min_significance: 最小重要性阈值
        """
        self.min_significance = min_significance
        self.fingerprint_analyzer = FingerprintAnalyzer(min_significance)

    def explore(
        self,
        pose_sequence: PoseSequence,
        video_path: Optional[str] = None,
        suggested_name: Optional[str] = None,
    ) -> ExplorationResult:
        """探索新动作.

        Args:
            pose_sequence: 姿态序列
            video_path: 视频路径
            suggested_name: 建议的动作名称

        Returns:
            探索结果，包含发现的特征和建议配置
        """
        # 1. 生成完整指纹
        fingerprint = self.fingerprint_analyzer.analyze(
            pose_sequence=pose_sequence,
            action_name=suggested_name or "unknown_action",
            video_metadata={"video_path": video_path} if video_path else {},
            tags=["exploration"],
        )

        # 2. 分析阶段候选
        phase_candidates = self._detect_phase_candidates(
            pose_sequence, fingerprint
        )

        # 3. 生成建议的阈值
        suggested_thresholds = self._generate_threshold_suggestions(
            fingerprint
        )

        # 4. 对称性分析
        symmetry_analysis = self._analyze_symmetry(fingerprint)

        # 5. 选择建议的检测项
        suggested_metrics = [
            m.metric_id for m in fingerprint.dominant_metrics[:8]
        ]

        # 6. 计算置信度
        confidence = self._calculate_confidence(fingerprint, phase_candidates)

        return ExplorationResult(
            action_name=suggested_name or fingerprint.action_id,
            description=self._generate_description(fingerprint),
            dominant_metrics=[m.to_dict() for m in fingerprint.dominant_metrics],
            phase_candidates=phase_candidates,
            symmetry_analysis=symmetry_analysis,
            suggested_metrics=suggested_metrics,
            suggested_phases=[p["phase_name"] for p in phase_candidates],
            suggested_thresholds=suggested_thresholds,
            confidence=confidence,
        )

    def _detect_phase_candidates(
        self,
        pose_sequence: PoseSequence,
        fingerprint: ActionFingerprint,
    ) -> List[Dict[str, Any]]:
        """检测可能的阶段划分.

        基于主导指标的变化模式识别阶段边界。
        """
        if not fingerprint.dominant_metrics:
            return []

        # 选择最重要的指标作为阶段检测的基础
        primary_metric = fingerprint.dominant_metrics[0]

        calculator = MetricsCalculator(
            action_id="exploration",
            use_phase_detection=False,
            use_viewpoint_analysis=False,
        )

        metric_def = METRIC_TEMPLATES.get(primary_metric.metric_id)
        if not metric_def:
            return []

        result = calculator.calculate_metric(
            metric_def=metric_def,
            pose_sequence=pose_sequence,
            action_name="exploration",
        )

        values = result.get("values", [])
        if not values:
            return []

        arr = np.array(values)
        arr = arr[~np.isnan(arr)]

        # 平滑数据
        window = self.PHASE_DETECTION_CONFIG["smoothing_window"]
        if len(arr) > window:
            smoothed = np.convolve(arr, np.ones(window)/window, mode='same')
        else:
            smoothed = arr

        # 检测极值点
        peaks = self._find_prominent_peaks(smoothed)
        valleys = self._find_prominent_valleys(smoothed)

        # 构建阶段候选
        phase_candidates = []

        # 基于起始点、极值点构建阶段
        key_points = sorted([0, len(arr)-1] + peaks + valleys)

        phase_names = ["起始", "下降/蓄力", "最低点/发力", "上升/恢复", "结束"]

        for i in range(len(key_points) - 1):
            start_frame = key_points[i]
            end_frame = key_points[i + 1]

            # 计算阶段特征
            phase_values = smoothed[start_frame:end_frame]
            if len(phase_values) == 0:
                continue

            phase_name = phase_names[min(i, len(phase_names)-1)]

            phase_candidates.append({
                "phase_id": f"phase_{i}",
                "phase_name": phase_name,
                "start_frame": int(start_frame),
                "end_frame": int(end_frame),
                "duration_frames": int(end_frame - start_frame),
                "primary_metric": primary_metric.metric_id,
                "metric_range": (float(np.min(phase_values)), float(np.max(phase_values))),
                "velocity": float(np.mean(np.diff(phase_values))) if len(phase_values) > 1 else 0.0,
            })

        return phase_candidates

    def _find_prominent_peaks(self, arr: np.ndarray) -> List[int]:
        """查找显著的峰值."""
        threshold = self.PHASE_DETECTION_CONFIG["prominence_threshold"]
        window = 5

        peaks = []
        for i in range(window, len(arr) - window):
            local_window = arr[i-window:i+window+1]
            if (arr[i] == np.max(local_window) and
                arr[i] > np.mean(arr) + threshold * np.std(arr)):
                peaks.append(i)

        return peaks

    def _find_prominent_valleys(self, arr: np.ndarray) -> List[int]:
        """查找显著的谷值."""
        threshold = self.PHASE_DETECTION_CONFIG["prominence_threshold"]
        window = 5

        valleys = []
        for i in range(window, len(arr) - window):
            local_window = arr[i-window:i+window+1]
            if (arr[i] == np.min(local_window) and
                arr[i] < np.mean(arr) - threshold * np.std(arr)):
                valleys.append(i)

        return valleys

    def _generate_threshold_suggestions(
        self,
        fingerprint: ActionFingerprint,
    ) -> Dict[str, Any]:
        """生成阈值建议.

        基于统计分析生成合理的阈值范围。
        """
        suggestions = {}

        for metric in fingerprint.dominant_metrics[:5]:
            metric_id = metric.metric_id

            # 基于统计分布生成阈值
            mean = metric.mean
            std = metric.std
            min_val = metric.min
            max_val = metric.max

            # 使用百分位数概念生成分级范围
            suggestions[metric_id] = {
                "target_value": round(mean, 2),
                "normal_range": (
                    round(mean - std, 2),
                    round(mean + std, 2)
                ),
                "excellent_range": (
                    round(mean - 0.5 * std, 2),
                    round(mean + 0.5 * std, 2)
                ),
                "pass_range": (
                    round(min_val - 0.1 * (max_val - min_val), 2),
                    round(max_val + 0.1 * (max_val - min_val), 2)
                ),
                "auto_generated": True,
                "sample_count": 1,
                "confidence": "low",  # 基于单个样本的置信度低
            }

        return suggestions

    def _analyze_symmetry(self, fingerprint: ActionFingerprint) -> Dict[str, Any]:
        """分析动作对称性."""
        left_metrics = []
        right_metrics = []

        for metric in fingerprint.dominant_metrics:
            if metric.metric_id.startswith("left_"):
                left_metrics.append(metric)
            elif metric.metric_id.startswith("right_"):
                right_metrics.append(metric)

        return {
            "has_bilateral_metrics": len(left_metrics) > 0 and len(right_metrics) > 0,
            "left_dominant_count": len(left_metrics),
            "right_dominant_count": len(right_metrics),
            "symmetry_score": fingerprint.symmetry_score,
            "asymmetric_metrics": [
                {
                    "metric_id": m.metric_id,
                    "range": m.range,
                }
                for m in left_metrics + right_metrics
            ],
        }

    def _generate_description(self, fingerprint: ActionFingerprint) -> str:
        """生成动作描述."""
        parts = []

        # 描述主导特征
        if fingerprint.dominant_metrics:
            top_metric = fingerprint.dominant_metrics[0]
            parts.append(f"主要运动特征: {top_metric.metric_name}")
            parts.append(f"变化范围: {top_metric.min:.1f}° - {top_metric.max:.1f}°")

        # 描述活跃关节
        if fingerprint.active_joints:
            joints_str = ", ".join(fingerprint.active_joints[:3])
            parts.append(f"主要涉及关节: {joints_str}")

        # 描述对称性
        if fingerprint.symmetry_score is not None:
            if fingerprint.symmetry_score > 0.8:
                parts.append("动作对称性良好")
            elif fingerprint.symmetry_score < 0.5:
                parts.append("动作存在明显不对称")

        return "; ".join(parts)

    def _calculate_confidence(
        self,
        fingerprint: ActionFingerprint,
        phase_candidates: List[Dict],
    ) -> float:
        """计算探索结果的可信度."""
        confidence = 0.5  # 基础置信度

        # 基于样本量的调整
        if fingerprint.total_metrics_analyzed > 10:
            confidence += 0.1

        # 基于主导指标清晰度的调整
        if fingerprint.dominant_metrics:
            top_score = fingerprint.dominant_metrics[0].significance_score
            if top_score > 1.0:
                confidence += 0.1

        # 基于阶段检测的调整
        if len(phase_candidates) >= 3:
            confidence += 0.2
        elif len(phase_candidates) >= 2:
            confidence += 0.1

        # 基于对称性的调整
        if fingerprint.symmetry_score is not None:
            confidence += 0.1

        return min(confidence, 0.95)  # 最高0.95（因为是探索模式）
