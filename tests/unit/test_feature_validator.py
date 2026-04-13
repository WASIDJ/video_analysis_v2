"""特征验证器单元测试."""

from src.core.analysis.fingerprint import ActionFingerprint, MetricFingerprint
from src.core.training.feature_validator import FeatureValidator, ValidationReport


def make_metric_fingerprint(
    metric_id: str = "knee_flexion",
    metric_name: str = "膝关节屈曲角度",
    *,
    mean: float = 100.0,
    std: float = 5.0,
    min_value: float = 90.0,
    max_value: float = 110.0,
    range_value: float = 20.0,
    variance_coefficient: float = 0.2,
    peak_count: int = 1,
    valley_count: int = 1,
    significance_score: float = 0.8,
) -> MetricFingerprint:
    """构造测试用检测项指纹."""
    return MetricFingerprint(
        metric_id=metric_id,
        metric_name=metric_name,
        category="joint_angle",
        mean=mean,
        std=std,
        min=min_value,
        max=max_value,
        range=range_value,
        total_variation=range_value,
        variance_coefficient=variance_coefficient,
        peak_count=peak_count,
        valley_count=valley_count,
        significance_score=significance_score,
    )


def make_action_fingerprint(
    dominant_metrics: list[MetricFingerprint],
    *,
    secondary_metrics: list[MetricFingerprint] | None = None,
    total_metrics_analyzed: int = 6,
    active_joints: list[str] | None = None,
    symmetry_score: float | None = 0.9,
    tags: list[str] | None = None,
) -> ActionFingerprint:
    """构造测试用动作指纹."""
    return ActionFingerprint(
        action_id="squat",
        action_name="Squat",
        created_at="2026-04-13T00:00:00",
        dominant_metrics=dominant_metrics,
        secondary_metrics=secondary_metrics or [],
        total_metrics_analyzed=total_metrics_analyzed,
        active_joints=active_joints or ["knee"],
        symmetry_score=symmetry_score,
        tags=tags or ["standard"],
    )


class TestFeatureValidator:
    """测试特征验证器."""

    def test_validate_marks_fingerprint_invalid_when_no_dominant_metrics(self):
        """没有主导指标时应直接判为无效."""
        validator = FeatureValidator()
        fingerprint = make_action_fingerprint(
            dominant_metrics=[],
            total_metrics_analyzed=0,
            active_joints=[],
            symmetry_score=None,
            tags=[],
        )

        report = validator.validate(fingerprint)

        assert report.is_valid is False
        assert "没有主导指标" in report.issues

    def test_validate_reports_physical_limit_violation(self):
        """超出生物力学极限时应报告 issue."""
        validator = FeatureValidator()
        fingerprint = make_action_fingerprint(
            dominant_metrics=[
                make_metric_fingerprint(
                    mean=120.0,
                    min_value=-20.0,
                    max_value=195.0,
                    range_value=215.0,
                )
            ],
        )

        report = validator.validate(fingerprint)

        assert report.is_valid is False
        assert any("超出物理极限" in issue for issue in report.issues)

    def test_batch_validate_returns_only_valid_fingerprints(self):
        """批量验证应只返回通过验证的指纹."""
        validator = FeatureValidator()
        valid_fp = make_action_fingerprint(
            dominant_metrics=[make_metric_fingerprint(metric_id="hip_flexion")],
            active_joints=["hip"],
        )
        invalid_fp = make_action_fingerprint(
            dominant_metrics=[],
            total_metrics_analyzed=0,
            active_joints=[],
            symmetry_score=None,
            tags=[],
        )

        valid_fps, reports = validator.batch_validate([valid_fp, invalid_fp])

        assert valid_fps == [valid_fp]
        assert len(reports) == 2
        assert reports[0].is_valid is True
        assert reports[1].is_valid is False

    def test_generate_validation_summary_aggregates_totals(self):
        """汇总报告应正确聚合通过率和问题总数."""
        validator = FeatureValidator()
        reports = [
            ValidationReport(is_valid=True, warnings=["变化幅度过小"]),
            ValidationReport(is_valid=False, issues=["没有主导指标"], warnings=["变化幅度过小"]),
        ]

        summary = validator.generate_validation_summary(reports)

        assert summary["total"] == 2
        assert summary["passed"] == 1
        assert summary["failed"] == 1
        assert summary["pass_rate"] == 0.5
        assert summary["total_issues"] == 1
        assert summary["total_warnings"] == 2
        assert summary["common_warnings"][0] == ("变化幅度过小", 2)

