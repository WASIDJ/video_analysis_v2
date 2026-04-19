"""特征验证器（机器审核）.

自动剔除伪特征，确保核心指标的质量。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
import numpy as np

from src.core.analysis.fingerprint import ActionFingerprint, MetricFingerprint


@dataclass
class ValidationReport:
    """验证报告."""
    is_valid: bool                      # 是否通过验证
    issues: List[str] = field(default_factory=list)  # 发现的问题
    warnings: List[str] = field(default_factory=list)  # 警告
    metrics: Dict[str, Any] = field(default_factory=dict)  # 详细指标

    def add_issue(self, issue: str) -> None:
        self.issues.append(issue)
        self.is_valid = False

    def add_warning(self, warning: str) -> None:
        self.warnings.append(warning)


class FeatureValidator:
    """特征验证器.

    通过多种规则自动识别和剔除伪特征：
    1. 信号质量检查（NaN比例、异常值）
    2. 物理合理性检查（超出人体极限）
    3. 稳定性检查（过度抖动）
    4. 一致性检查（左右对称性异常）
    5. 显著性检查（变化幅度是否足够）
    """

    # 物理极限值（生物力学约束）
    PHYSICAL_LIMITS = {
        "knee_flexion": {"min": 0, "max": 180},
        "hip_flexion": {"min": 0, "max": 140},
        # 2D投影下踝角容易映射到接近180度，训练阶段使用宽容范围避免误杀样本
        "ankle_dorsiflexion": {"min": -30, "max": 180},
        "trunk_lean": {"min": 0, "max": 90},
        # 2D场景下膝外翻符号和幅值受视角影响较大，训练阶段仅做弱约束
        "knee_valgus": {"min": -180, "max": 180},
        "shoulder_flexion": {"min": 0, "max": 180},
        "elbow_flexion": {"min": 0, "max": 160},
    }

    # 验证阈值
    VALIDATION_THRESHOLDS = {
        "max_nan_ratio": 0.3,              # 最大NaN比例
        "min_range_threshold": 5.0,        # 最小变化幅度（度）
        "max_variance_coefficient": 0.5,   # 最大变异系数
        "min_peak_count": 1,               # 最少极值点数量
        "max_outlier_ratio": 0.2,          # 最大异常值比例
        "min_symmetry_score": 0.3,         # 最小对称性得分
        "min_significance_score": 0.1,     # 最小重要性得分
    }

    def __init__(self, custom_limits: Optional[Dict] = None):
        """
        Args:
            custom_limits: 自定义物理极限值
        """
        self.limits = {**self.PHYSICAL_LIMITS, **(custom_limits or {})}

    def validate(self, fingerprint: ActionFingerprint) -> ValidationReport:
        """验证动作指纹.

        Args:
            fingerprint: 动作指纹

        Returns:
            验证报告
        """
        report = ValidationReport(is_valid=True)

        # 1. 基本完整性检查
        self._validate_completeness(fingerprint, report)

        # 2. 主导指标质量检查
        for metric in fingerprint.dominant_metrics:
            self._validate_metric_quality(metric, report)
            self._validate_physical_plausibility(metric, report)

        # 3. 对称性检查（如果适用）
        if fingerprint.symmetry_score is not None:
            self._validate_symmetry(fingerprint, report)

        # 4. 阶段特征检查
        self._validate_phase_characteristics(fingerprint, report)

        # 5. 统计显著性检查
        self._validate_statistical_significance(fingerprint, report)

        return report

    def _validate_completeness(
        self,
        fingerprint: ActionFingerprint,
        report: ValidationReport
    ) -> None:
        """验证基本完整性."""
        if not fingerprint.dominant_metrics:
            report.add_issue("没有主导指标")
            return

        if fingerprint.total_metrics_analyzed < 5:
            report.add_warning(f"分析的指标数量过少: {fingerprint.total_metrics_analyzed}")

        if not fingerprint.active_joints:
            report.add_issue("没有识别到活跃关节")

    def _validate_metric_quality(
        self,
        metric: MetricFingerprint,
        report: ValidationReport
    ) -> None:
        """验证单个指标的质量."""
        # 检查NaN比例（通过方差系数推断）
        if np.isnan(metric.mean) or np.isnan(metric.std):
            report.add_issue(f"{metric.metric_name}: 数据包含过多NaN")
            return

        # 检查变化幅度
        if metric.range < self.VALIDATION_THRESHOLDS["min_range_threshold"]:
            report.add_warning(
                f"{metric.metric_name}: 变化幅度过小 ({metric.range:.1f}°)"
            )

        # 检查变异系数
        if metric.variance_coefficient > self.VALIDATION_THRESHOLDS["max_variance_coefficient"]:
            report.add_warning(
                f"{metric.metric_name}: 变异系数过大 ({metric.variance_coefficient:.2f})，可能存在抖动"
            )

        # 检查极值点
        total_extrema = metric.peak_count + metric.valley_count
        if total_extrema < self.VALIDATION_THRESHOLDS["min_peak_count"]:
            report.add_warning(
                f"{metric.metric_name}: 极值点数量过少 ({total_extrema})"
            )

    def _validate_physical_plausibility(
        self,
        metric: MetricFingerprint,
        report: ValidationReport
    ) -> None:
        """验证物理合理性."""
        if metric.metric_id not in self.limits:
            return

        limits = self.limits[metric.metric_id]
        min_limit = limits["min"]
        max_limit = limits["max"]
        hard_margin = 60  # 极端越界仍判失败
        soft_margin = 10  # 轻度越界仅告警，避免误杀样本

        # 检查是否超出物理极限
        if metric.min < min_limit - hard_margin:
            report.add_issue(
                f"{metric.metric_name}: 最小值 {metric.min:.1f}° 严重超出物理极限 [{min_limit}, {max_limit}]"
            )
        elif metric.min < min_limit - soft_margin:
            report.add_warning(
                f"{metric.metric_name}: 最小值 {metric.min:.1f}° 超出物理极限 [{min_limit}, {max_limit}]"
            )

        if metric.max > max_limit + hard_margin:
            report.add_issue(
                f"{metric.metric_name}: 最大值 {metric.max:.1f}° 严重超出物理极限 [{min_limit}, {max_limit}]"
            )
        elif metric.max > max_limit + soft_margin:
            report.add_warning(
                f"{metric.metric_name}: 最大值 {metric.max:.1f}° 超出物理极限 [{min_limit}, {max_limit}]"
            )

        # 检查范围是否合理
        expected_range = max_limit - min_limit
        if metric.range > expected_range * 1.2:
            report.add_warning(
                f"{metric.metric_name}: 变化范围 {metric.range:.1f}° 超出预期 {expected_range}°"
            )

    def _validate_symmetry(
        self,
        fingerprint: ActionFingerprint,
        report: ValidationReport
    ) -> None:
        """验证对称性."""
        if fingerprint.symmetry_score is None:
            return

        # 检查对称性得分
        if fingerprint.symmetry_score < self.VALIDATION_THRESHOLDS["min_symmetry_score"]:
            # 对于标准动作，过低的对称性可能是问题
            if "standard" in fingerprint.tags:
                report.add_warning(
                    f"标准动作对称性过低: {fingerprint.symmetry_score:.2f}"
                )

        # 检查左右指标数量平衡
        left_count = sum(1 for m in fingerprint.dominant_metrics
                        if m.metric_id.startswith("left_"))
        right_count = sum(1 for m in fingerprint.dominant_metrics
                         if m.metric_id.startswith("right_"))

        if left_count > 0 or right_count > 0:
            imbalance = abs(left_count - right_count)
            if imbalance > 2:
                report.add_warning(f"左右指标数量不平衡: L{left_count} vs R{right_count}")

    def _validate_phase_characteristics(
        self,
        fingerprint: ActionFingerprint,
        report: ValidationReport
    ) -> None:
        """验证阶段特征."""
        # 检查峰值/谷值比例
        total_peaks = sum(m.peak_count for m in fingerprint.dominant_metrics)
        total_valleys = sum(m.valley_count for m in fingerprint.dominant_metrics)

        if total_peaks == 0 and total_valleys == 0:
            report.add_issue("没有检测到极值点，可能不是周期性动作")

        # 对于标准动作，应该有明确的阶段变化
        if "standard" in fingerprint.tags:
            if total_peaks < 1 or total_valleys < 1:
                report.add_warning("标准动作应该至少有一个峰值和一个谷值")

    def _validate_statistical_significance(
        self,
        fingerprint: ActionFingerprint,
        report: ValidationReport
    ) -> None:
        """验证统计显著性."""
        # 检查主导指标的重要性
        low_significance = [
            m for m in fingerprint.dominant_metrics
            if m.significance_score < self.VALIDATION_THRESHOLDS["min_significance_score"]
        ]

        if low_significance:
            names = ", ".join(m.metric_name for m in low_significance)
            report.add_warning(f"以下主导指标重要性偏低: {names}")

        # 检查是否有异常的主导指标
        if fingerprint.dominant_metrics:
            max_sig = max(m.significance_score for m in fingerprint.dominant_metrics)
            for m in fingerprint.dominant_metrics:
                if m.significance_score < max_sig * 0.1:
                    report.add_warning(
                        f"{m.metric_name} 重要性 ({m.significance_score:.2f}) "
                        f"远低于主要指标 ({max_sig:.2f})"
                    )

    def batch_validate(
        self,
        fingerprints: List[ActionFingerprint]
    ) -> Tuple[List[ActionFingerprint], List[ValidationReport]]:
        """批量验证.

        Returns:
            (有效指纹列表, 验证报告列表)
        """
        valid_fps = []
        reports = []

        for fp in fingerprints:
            report = self.validate(fp)
            reports.append(report)
            if report.is_valid:
                valid_fps.append(fp)

        return valid_fps, reports

    def generate_validation_summary(
        self,
        reports: List[ValidationReport]
    ) -> Dict[str, Any]:
        """生成验证汇总报告."""
        total = len(reports)
        passed = sum(1 for r in reports if r.is_valid)
        failed = total - passed

        all_issues = []
        all_warnings = []
        for r in reports:
            all_issues.extend(r.issues)
            all_warnings.extend(r.warnings)

        # 统计最常见的问题
        from collections import Counter
        issue_counts = Counter(all_issues)
        warning_counts = Counter(all_warnings)

        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "pass_rate": passed / total if total > 0 else 0,
            "common_issues": issue_counts.most_common(5),
            "common_warnings": warning_counts.most_common(5),
            "total_issues": len(all_issues),
            "total_warnings": len(all_warnings),
        }
