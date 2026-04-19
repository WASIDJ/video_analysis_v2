"""阶段边界学习器 - 从视频学习阶段进入/退出条件.

通用阶段划分：不依赖动作特定模板，从时序信号自动学习阶段边界.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import logging
from scipy.signal import find_peaks, savgol_filter

logger = logging.getLogger(__name__)


@dataclass
class PhaseBoundary:
    """阶段边界定义."""
    phase_id: str
    phase_name: str
    entry_conditions: List[Dict[str, Any]] = field(default_factory=list)
    exit_conditions: List[Dict[str, Any]] = field(default_factory=list)
    detection_params: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0  # 边界学习置信度
    key_metric: Optional[str] = None  # 用于划分边界的关键指标


@dataclass
class PhaseLearningResult:
    """阶段学习结果."""
    phases: List[PhaseBoundary]
    cycle_count: int  # 检测到的周期数
    key_metric: str  # 用于划分的关键指标
    confidence: float  # 整体置信度
    method: str  # 学习方法（peak_detection/derivative/zero_crossing）


class PhaseBoundaryLearner:
    """
    阶段边界学习器.

    通用阶段划分策略：
    1. 从所有检测项中找出周期性最强的信号
    2. 基于极值点/导数零点划分阶段边界
    3. 推导入/出条件（阈值或导数方向）
    """

    # 优先用于阶段划分的检测项（按优先级排序）
    PREFERRED_METRICS = [
        "hip_abduction",
        "leg_elevation_height",
        "hip_flexion",
        "knee_flexion",
        "trunk_lean",
    ]

    def __init__(
        self,
        target_rep_count: Optional[int] = None,
        fps: float = 30.0,
        min_phase_duration: float = 0.2,  # 秒
        max_phase_duration: float = 5.0,  # 秒
    ):
        self.target_rep_count = target_rep_count
        self.fps = fps
        self.min_phase_frames = int(min_phase_duration * fps)
        self.max_phase_frames = int(max_phase_duration * fps)

    def learn_from_metrics(
        self,
        metric_values: Dict[str, np.ndarray],
        preferred_metrics: Optional[List[str]] = None,
    ) -> PhaseLearningResult:
        """
        从检测项数值学习阶段边界.

        Args:
            metric_values: 检测项时序值 {metric_id: values_array}
            preferred_metrics: 优先尝试的检测项列表

        Returns:
            PhaseLearningResult
        """
        if preferred_metrics is None:
            preferred_metrics = self.PREFERRED_METRICS

        # 1. 找出最佳周期信号
        best_metric, cycle_info = self._find_best_cycle_signal(
            metric_values, preferred_metrics
        )

        if best_metric is None:
            logger.warning("未能找到有效的周期信号")
            return PhaseLearningResult(
                phases=[],
                cycle_count=0,
                key_metric="",
                confidence=0.0,
                method="failed",
            )

        # 2. 基于周期信号划分阶段
        phases = self._segment_phases(
            metric_values[best_metric],
            best_metric,
            cycle_info,
        )

        # 3. 计算整体置信度
        confidence = self._calculate_confidence(
            phases, cycle_info, best_metric
        )

        return PhaseLearningResult(
            phases=phases,
            cycle_count=cycle_info.get("count", 0),
            key_metric=best_metric,
            confidence=confidence,
            method=cycle_info.get("method", "unknown"),
        )

    def _find_best_cycle_signal(
        self,
        metric_values: Dict[str, np.ndarray],
        preferred_metrics: List[str],
    ) -> Tuple[Optional[str], Dict[str, Any]]:
        """找出最佳的周期信号."""
        best_metric = None
        best_score = 0.0
        best_info = {}

        # 按优先级尝试检测项
        for metric_id in preferred_metrics:
            if metric_id not in metric_values:
                continue

            values = metric_values[metric_id]
            if len(values) < self.min_phase_frames * 3:
                continue

            # 检测周期性
            cycle_info = self._detect_periodicity(values)
            score = cycle_info.get("score", 0.0)

            # 如果有目标次数，匹配度高的优先
            if self.target_rep_count and cycle_info.get("count"):
                count_diff = abs(cycle_info["count"] - self.target_rep_count)
                score *= max(0.5, 1 - count_diff / max(self.target_rep_count, 1))

            if score > best_score:
                best_score = score
                best_metric = metric_id
                best_info = cycle_info

        return best_metric, best_info

    def _detect_periodicity(self, values: np.ndarray) -> Dict[str, Any]:
        """检测信号的周期性."""
        # 平滑处理
        if len(values) < 5:
            return {"score": 0.0}

        window = min(5, len(values) // 3 * 2 + 1)
        if window < 3:
            window = 3

        try:
            smoothed = savgol_filter(values, window, 2)
        except Exception:
            smoothed = values

        # 方法1：基于极值点检测
        peaks_info = self._detect_peaks(smoothed)

        # 方法2：基于过零点检测
        zero_cross_info = self._detect_zero_crossings(smoothed)

        # 选择更好的方法
        if peaks_info["score"] >= zero_cross_info["score"]:
            return peaks_info
        return zero_cross_info

    def _detect_peaks(self, values: np.ndarray) -> Dict[str, Any]:
        """基于极值点检测周期."""
        # 根据目标次数动态估计最小峰间距，抑制过检
        distance = self.min_phase_frames
        if self.target_rep_count and self.target_rep_count > 0:
            expected_cycle = len(values) / max(self.target_rep_count, 1)
            distance = max(self.min_phase_frames, int(expected_cycle * 0.6))

        signal_range = float(np.max(values) - np.min(values))
        signal_std = float(np.std(values))
        prominence = max(signal_std * 0.35, signal_range * 0.05, 1e-6)

        peaks, _ = find_peaks(values, distance=distance, prominence=prominence)
        valleys, _ = find_peaks(-values, distance=distance, prominence=prominence)

        if len(peaks) < 2 and len(valleys) < 2:
            return {"score": 0.0}

        # 计算周期稳定性
        peak_intervals = np.diff(peaks) if len(peaks) > 1 else []
        valley_intervals = np.diff(valleys) if len(valleys) > 1 else []

        all_intervals = list(peak_intervals) + list(valley_intervals)
        if not all_intervals:
            return {"score": 0.0}

        # 周期性评分（间隔一致性）
        mean_interval = np.mean(all_intervals)
        std_interval = np.std(all_intervals)
        stability_score = 1.0 - min(1.0, std_interval / max(mean_interval, 1))

        # 周期数：用峰谷的较小值，避免单侧噪声导致高估
        cycle_count = min(len(peaks), len(valleys)) if len(peaks) and len(valleys) else max(len(peaks), len(valleys))

        return {
            "method": "peak_detection",
            "peaks": peaks,
            "valleys": valleys,
            "count": cycle_count,
            "mean_interval": mean_interval,
            "stability_score": stability_score,
            "score": stability_score * min(1.0, cycle_count / 3),  # 至少3个周期才给满分
        }

    def _detect_zero_crossings(self, values: np.ndarray) -> Dict[str, Any]:
        """基于导数过零点检测周期."""
        # 计算导数
        derivative = np.gradient(values)

        # 寻找导数过零点（极值点）
        zero_crossings = []
        min_gap = self.min_phase_frames
        if self.target_rep_count and self.target_rep_count > 0:
            expected_cycle = len(values) / max(self.target_rep_count, 1)
            min_gap = max(self.min_phase_frames, int(expected_cycle * 0.4))

        last_idx = -10**9
        for i in range(1, len(derivative)):
            if derivative[i-1] * derivative[i] < 0:  # 符号变化
                if i - last_idx >= min_gap:
                    zero_crossings.append(i)
                    last_idx = i

        if len(zero_crossings) < 2:
            return {"score": 0.0}

        # 计算间隔稳定性
        intervals = np.diff(zero_crossings)
        mean_interval = np.mean(intervals)
        std_interval = np.std(intervals)
        stability_score = 1.0 - min(1.0, std_interval / max(mean_interval, 1))

        return {
            "method": "zero_crossing",
            "zero_crossings": zero_crossings,
            "count": len(zero_crossings) // 2,  # 近似周期数
            "mean_interval": mean_interval,
            "stability_score": stability_score,
            "score": stability_score * 0.8,  # 略低于峰值检测
        }

    def _segment_phases(
        self,
        values: np.ndarray,
        metric_id: str,
        cycle_info: Dict[str, Any],
    ) -> List[PhaseBoundary]:
        """基于周期信息划分阶段."""
        phases = []
        method = cycle_info.get("method")

        if method == "peak_detection":
            phases = self._segment_by_peaks(values, metric_id, cycle_info)
        elif method == "zero_crossing":
            phases = self._segment_by_zero_crossings(values, metric_id, cycle_info)

        return phases

    def _segment_by_peaks(
        self,
        values: np.ndarray,
        metric_id: str,
        cycle_info: Dict[str, Any],
    ) -> List[PhaseBoundary]:
        """基于峰值划分阶段."""
        peaks = cycle_info.get("peaks", [])
        valleys = cycle_info.get("valleys", [])

        phases = []

        # 识别完整的周期：谷 -> 峰 -> 谷
        if len(valleys) >= 2 and len(peaks) >= 1:
            # 阶段1：起始/准备（第一个谷前或谷到峰之间）
            phases.append(self._create_phase_boundary(
                "start", "起始位置",
                metric_id, values, "rising"
            ))

            # 阶段2：执行/上升（谷到峰）
            phases.append(self._create_phase_boundary(
                "execution", "执行阶段",
                metric_id, values, "rising_to_peak"
            ))

            # 阶段3：保持/峰值（峰附近）
            if len(peaks) > 0:
                peak_value = np.mean(values[peaks])
                phases.append(self._create_phase_boundary(
                    "hold", "保持阶段",
                    metric_id, values, "at_peak",
                    threshold=peak_value * 0.9
                ))

            # 阶段4：返回/下降（峰到谷）
            phases.append(self._create_phase_boundary(
                "return", "返回阶段",
                metric_id, values, "falling"
            ))

            # 阶段5：结束（谷）
            if len(valleys) > 0:
                valley_value = np.mean(values[valleys])
                phases.append(self._create_phase_boundary(
                    "end", "结束位置",
                    metric_id, values, "at_valley",
                    threshold=valley_value * 1.1
                ))

        return phases

    def _segment_by_zero_crossings(
        self,
        values: np.ndarray,
        metric_id: str,
        cycle_info: Dict[str, Any],
    ) -> List[PhaseBoundary]:
        """基于过零点划分阶段（简化版本）."""
        # 简化为三个阶段：start -> execution -> end
        phases = [
            self._create_phase_boundary("start", "起始位置", metric_id, values, "static"),
            self._create_phase_boundary("execution", "执行阶段", metric_id, values, "dynamic"),
            self._create_phase_boundary("end", "结束位置", metric_id, values, "static"),
        ]
        return phases

    def _create_phase_boundary(
        self,
        phase_id: str,
        phase_name: str,
        metric_id: str,
        values: np.ndarray,
        pattern: str,
        threshold: Optional[float] = None,
    ) -> PhaseBoundary:
        """创建阶段边界定义."""
        entry_conditions = []
        exit_conditions = []
        detection_params = {}

        # 根据模式设置条件
        if pattern == "rising":
            entry_conditions.append({
                "type": "derivative",
                "metric": metric_id,
                "operator": "gt",
                "value": 0,
            })
        elif pattern == "rising_to_peak":
            entry_conditions.append({
                "type": "derivative",
                "metric": metric_id,
                "operator": "gt",
                "value": 5.0,  # 显著上升
            })
            exit_conditions.append({
                "type": "derivative",
                "metric": metric_id,
                "operator": "lt",
                "value": 0,  # 开始下降
            })
        elif pattern == "at_peak" and threshold is not None:
            entry_conditions.append({
                "type": "threshold",
                "metric": metric_id,
                "operator": "gte",
                "value": threshold,
            })
            exit_conditions.append({
                "type": "threshold",
                "metric": metric_id,
                "operator": "lt",
                "value": threshold * 0.95,
            })
        elif pattern == "falling":
            entry_conditions.append({
                "type": "derivative",
                "metric": metric_id,
                "operator": "lt",
                "value": 0,
            })
        elif pattern == "at_valley" and threshold is not None:
            entry_conditions.append({
                "type": "threshold",
                "metric": metric_id,
                "operator": "lte",
                "value": threshold,
            })

        # 设置检测参数
        detection_params["key_metric"] = metric_id
        detection_params["pattern"] = pattern
        if threshold is not None:
            detection_params["threshold"] = threshold

        return PhaseBoundary(
            phase_id=phase_id,
            phase_name=phase_name,
            entry_conditions=entry_conditions,
            exit_conditions=exit_conditions,
            detection_params=detection_params,
            confidence=0.7,  # 默认置信度
            key_metric=metric_id,
        )

    def _calculate_confidence(
        self,
        phases: List[PhaseBoundary],
        cycle_info: Dict[str, Any],
        metric_id: str,
    ) -> float:
        """计算整体置信度."""
        if not phases:
            return 0.0

        # 基于周期稳定性的置信度
        stability = cycle_info.get("stability_score", 0.0)

        # 基于阶段数的置信度
        phase_score = min(1.0, len(phases) / 4)  # 期望至少4个阶段

        # 基于是否有目标的置信度
        target_score = 1.0
        if self.target_rep_count:
            detected_count = cycle_info.get("count", 0)
            if detected_count > 0:
                target_score = 1.0 - abs(detected_count - self.target_rep_count) / max(
                    self.target_rep_count, detected_count
                )
                # 检测次数明显偏多时追加惩罚，减少过检高置信
                if detected_count > self.target_rep_count * 2:
                    target_score *= 0.6

        return (stability * 0.4 + phase_score * 0.3 + target_score * 0.3)
