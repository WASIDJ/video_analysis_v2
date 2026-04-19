"""阶段边界学习器单元测试."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import numpy as np
import pytest

from src.core.phases.boundary_learner import PhaseBoundaryLearner, PhaseLearningResult
from src.core.metrics.selector import MetricSelector, MetricSelectionResult


class TestPhaseBoundaryLearner:
    """测试阶段边界学习器."""

    def test_find_cycle_signal(self):
        """测试周期信号检测."""
        learner = PhaseBoundaryLearner(target_rep_count=5)

        # 创建周期性信号（5个周期）
        t = np.linspace(0, 10, 300)  # 300帧，10秒
        cycle_signal = np.sin(2 * np.pi * 0.5 * t) * 50 + 100  # 5个周期

        metric_values = {
            "hip_abduction": cycle_signal,
            "noise": np.random.randn(300) * 10,
        }

        result = learner.learn_from_metrics(metric_values)

        assert result.key_metric == "hip_abduction"
        assert result.cycle_count >= 3  # 至少检测到3个周期
        assert result.confidence > 0
        assert len(result.phases) > 0

    def test_no_periodic_signal(self):
        """测试无周期信号的情况."""
        learner = PhaseBoundaryLearner()

        # 纯噪声
        metric_values = {
            "noise1": np.random.randn(100) * 10,
            "noise2": np.random.randn(100) * 5,
        }

        result = learner.learn_from_metrics(metric_values)

        assert result.key_metric == ""
        assert result.cycle_count == 0
        assert result.confidence == 0.0

    def test_phase_boundary_creation(self):
        """测试阶段边界创建."""
        learner = PhaseBoundaryLearner()

        # 创建明确的周期性信号
        t = np.linspace(0, 6, 180)  # 180帧，6秒
        cycle_signal = np.sin(2 * np.pi * 0.5 * t) * 50 + 100  # 3个周期

        metric_values = {"hip_abduction": cycle_signal}
        result = learner.learn_from_metrics(metric_values)

        # 验证阶段定义
        phase_ids = [p.phase_id for p in result.phases]
        assert "start" in phase_ids or "execution" in phase_ids

        # 验证边界条件
        for phase in result.phases:
            assert phase.phase_id is not None
            assert phase.confidence > 0


class TestMetricSelector:
    """测试检测项选择器."""

    def test_select_metrics_basic(self):
        """测试基本检测项筛选."""
        selector = MetricSelector(max_metrics=3)

        # 创建测试数据（需要有足够的区分度和稳定性）
        np.random.seed(42)  # 可重复
        metric_values = {
            "stable_metric": np.array([50, 100, 50, 100, 50]),  # 稳定且变化大
            "variable_metric": np.array([0, 100, 0, 100, 0]),   # 变化大
            "noise_metric": np.random.randn(10) * 5 + 50,        # 噪声但稳定
        }

        result = selector.select_metrics(metric_values)

        # 验证数量限制
        assert len(result.core_metrics) <= 3

    def test_redundancy_removal(self):
        """测试冗余去除."""
        selector = MetricSelector(max_metrics=6, correlation_threshold=0.9)

        # 创建高度相关的指标
        base = np.array([100, 102, 98, 101, 99])
        metric_values = {
            "metric_a": base,
            "metric_b": base + 1,  # 高度相关
            "metric_c": base * 2,  # 高度相关
            "metric_d": np.array([0, 50, 100, 50, 0]),  # 不相关
        }

        result = selector.select_metrics(metric_values)

        # 高度相关的应该被剔除
        # metric_a 被选中后，metric_b 和 metric_c 应该被标记为冗余
        if "metric_a" in result.core_metrics:
            assert ("metric_b", "与 metric_a 高相关") in result.rejected_metrics or \
                   ("metric_c", "与 metric_a 高相关") in result.rejected_metrics

    def test_selection_info(self):
        """测试选择信息输出."""
        selector = MetricSelector(max_metrics=2)

        metric_values = {
            "m1": np.array([100, 101, 99, 100, 102]),
            "m2": np.array([0, 100, 0, 100, 0]),
            "m3": np.array([50, 50, 50, 50, 50]),  # 无变化，应该被剔除
        }

        result = selector.select_metrics(metric_values)

        # 验证选择信息
        assert "total_candidates" in result.selection_info
        assert result.selection_info["total_candidates"] == 3
        assert "final_core" in result.selection_info
        assert result.selection_info["final_core"] <= 2


class TestIntegration:
    """集成测试."""

    def test_end_to_end_phase_learning(self):
        """测试端到端阶段学习."""
        # 1. 生成模拟数据
        t = np.linspace(0, 10, 300)
        cycle_signal = np.sin(2 * np.pi * 0.5 * t) * 50 + 100  # 5个周期

        metric_values = {
            "hip_abduction": cycle_signal,
            "trunk_lean": cycle_signal * 0.5 + np.random.randn(300) * 5,
            "noise": np.random.randn(300) * 10,
        }

        # 2. 检测项筛选
        selector = MetricSelector(max_metrics=2)
        selection = selector.select_metrics(metric_values)

        # 3. 阶段边界学习
        learner = PhaseBoundaryLearner(target_rep_count=5)
        phase_result = learner.learn_from_metrics(
            metric_values,
            preferred_metrics=selection.core_metrics,
        )

        # 4. 验证
        assert phase_result.cycle_count >= 3
        assert phase_result.confidence > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
