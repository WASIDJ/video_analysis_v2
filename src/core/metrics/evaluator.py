"""阈值评估引擎 - 基于阈值的等级评估.

提供明确的评估优先级规范：excellent > good > pass > fail
"""
from dataclasses import dataclass
from typing import Dict, Optional, Tuple, Literal
import logging

logger = logging.getLogger(__name__)


@dataclass
class MetricThreshold:
    """检测项阈值配置."""
    target_value: Optional[float] = None
    normal_range: Optional[Tuple[float, float]] = None
    excellent_range: Optional[Tuple[float, float]] = None
    good_range: Optional[Tuple[float, float]] = None
    pass_range: Optional[Tuple[float, float]] = None


@dataclass
class ThresholdEvaluation:
    """阈值评估结果."""
    grade: Literal["excellent", "good", "pass", "fail"]
    score: float  # 0-100
    deviation: float  # 与 target 的偏差
    normalized_score: float  # 0-1
    description: str
    normal_warning: Optional[str] = None  # normal_range 告警（不参与评分）


class ThresholdEvaluator:
    """
    阈值评估引擎 - 明确优先级规范.

    判定优先级（从高到低）：
    1. excellent_range: 优秀区间（最高等级）
    2. good_range: 良好区间（次高等级）
    3. pass_range: 及格区间（最低通过等级）
    4. fail: 不及格（不在上述区间）

    normal_range 用途：
    - 仅用于告警/提示（如"偏离正常范围"）
    - 不参与评分等级计算
    - 可用于训练时的数据过滤

    区间包含规则：
    - excellent_range ⊆ good_range ⊆ pass_range
    - 若配置违反包含关系，自动修正并警告
    """

    GRADE_PRIORITY = ["excellent", "good", "pass", "fail"]

    def evaluate(
        self,
        value: float,
        thresholds: MetricThreshold
    ) -> ThresholdEvaluation:
        """评估数值所属的等级."""

        # 检查区间包含关系，修复不一致配置
        effective_ranges = self._normalize_ranges(thresholds)

        # 按优先级判定
        if effective_ranges["excellent"] and self._in_range(value, effective_ranges["excellent"]):
            grade = "excellent"
            score = self._calc_score_in_range(
                value,
                effective_ranges["excellent"],
                thresholds.target_value
            )
        elif effective_ranges["good"] and self._in_range(value, effective_ranges["good"]):
            grade = "good"
            base_score = 80
            range_score = self._calc_score_in_range(
                value,
                effective_ranges["good"],
                thresholds.target_value
            )
            score = base_score + range_score * 0.15
        elif effective_ranges["pass"] and self._in_range(value, effective_ranges["pass"]):
            grade = "pass"
            base_score = 60
            range_score = self._calc_score_in_range(
                value,
                effective_ranges["pass"],
                thresholds.target_value
            )
            score = base_score + range_score * 0.18
        else:
            grade = "fail"
            score = self._calc_fail_score(
                value,
                effective_ranges["pass"],
                thresholds.target_value
            )

        # normal_range 告警（不参与评分）
        normal_warning = None
        if thresholds.normal_range and not self._in_range(value, thresholds.normal_range):
            normal_warning = f"值 {value:.1f} 偏离正常范围 {thresholds.normal_range}"

        return ThresholdEvaluation(
            grade=grade,
            score=round(score, 1),
            deviation=self._calc_deviation(value, thresholds.target_value),
            normalized_score=round(score / 100, 2),
            description=self._generate_description(grade, value, thresholds),
            normal_warning=normal_warning
        )

    def _normalize_ranges(
        self,
        thresholds: MetricThreshold
    ) -> Dict[str, Optional[Tuple[float, float]]]:
        """
        规范化区间，确保包含关系.

        若 excellent 不完全包含于 good，扩展 good
        若 good 不完全包含于 pass，扩展 pass
        """
        ranges = {
            "excellent": thresholds.excellent_range,
            "good": thresholds.good_range,
            "pass": thresholds.pass_range
        }

        # 确保包含关系（从内到外）
        if ranges["excellent"] and ranges["good"]:
            if not self._range_contains(ranges["good"], ranges["excellent"]):
                logger.warning(
                    f"excellent_range {ranges['excellent']} 不完全包含于 "
                    f"good_range {ranges['good']}，自动扩展"
                )
                ranges["good"] = self._extend_to_contain(
                    ranges["good"], ranges["excellent"]
                )

        if ranges["good"] and ranges["pass"]:
            if not self._range_contains(ranges["pass"], ranges["good"]):
                logger.warning(
                    f"good_range {ranges['good']} 不完全包含于 "
                    f"pass_range {ranges['pass']}，自动扩展"
                )
                ranges["pass"] = self._extend_to_contain(
                    ranges["pass"], ranges["good"]
                )

        return ranges

    def _range_contains(
        self,
        outer: Tuple[float, float],
        inner: Tuple[float, float]
    ) -> bool:
        """检查 outer 是否包含 inner."""
        return outer[0] <= inner[0] and outer[1] >= inner[1]

    def _extend_to_contain(
        self,
        base: Tuple[float, float],
        to_contain: Tuple[float, float]
    ) -> Tuple[float, float]:
        """扩展 base 以包含 to_contain."""
        return (
            min(base[0], to_contain[0]),
            max(base[1], to_contain[1])
        )

    def _in_range(self, value: float, range_tuple: Tuple[float, float]) -> bool:
        """检查值是否在范围内."""
        return range_tuple[0] <= value <= range_tuple[1]

    def _calc_score_in_range(
        self,
        value: float,
        range_tuple: Tuple[float, float],
        target: Optional[float]
    ) -> float:
        """计算在范围内的分数（0-100）."""
        if target is None:
            # 无目标值，范围中心为最佳
            target = (range_tuple[0] + range_tuple[1]) / 2

        range_size = range_tuple[1] - range_tuple[0]
        if range_size == 0:
            return 100.0

        # 距离目标越近分数越高
        distance = abs(value - target)
        max_distance = max(
            abs(range_tuple[0] - target),
            abs(range_tuple[1] - target)
        )

        if max_distance == 0:
            return 100.0

        return 100 * (1 - distance / max_distance)

    def _calc_fail_score(
        self,
        value: float,
        pass_range: Optional[Tuple[float, float]],
        target: Optional[float]
    ) -> float:
        """计算不及格分数（0-60）."""
        if pass_range is None:
            return 0.0

        # 计算超出 pass_range 的程度
        if value < pass_range[0]:
            distance = pass_range[0] - value
        else:
            distance = value - pass_range[1]

        # 参考距离（用于归一化）
        range_size = pass_range[1] - pass_range[0]
        reference = range_size * 0.5 if range_size > 0 else 10.0

        # 距离越大分数越低
        penalty = min(60, 60 * distance / reference)
        return max(0, 60 - penalty)

    def _calc_deviation(
        self,
        value: float,
        target: Optional[float]
    ) -> float:
        """计算与目标值的偏差."""
        if target is None:
            return 0.0
        return value - target

    def _generate_description(
        self,
        grade: str,
        value: float,
        thresholds: MetricThreshold
    ) -> str:
        """生成评估描述."""
        grade_descriptions = {
            "excellent": "优秀",
            "good": "良好",
            "pass": "及格",
            "fail": "不及格"
        }

        desc = grade_descriptions.get(grade, "未知")

        if thresholds.target_value:
            deviation = value - thresholds.target_value
            if abs(deviation) < 1:
                desc += "，接近期望值"
            elif deviation > 0:
                desc += f"，高于期望值 {deviation:.1f}"
            else:
                desc += f"，低于期望值 {abs(deviation):.1f}"

        return desc
