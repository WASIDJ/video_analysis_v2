"""ActionAnalyzer V2 单元测试."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

import numpy as np
import pytest
from src.core.config.models import (
    ActionConfig,
    PhaseDefinition,
    MetricConfig,
    MetricThreshold,
    CycleDefinition,
)
from src.core.phases.counter import RepCounter, CycleDefinition
from src.core.metrics.evaluator import ThresholdEvaluator, MetricThreshold
from src.core.analysis.analyzer import ActionAnalyzer


class TestCycleDefinition:
    """测试周期定义."""

    def test_cycle_definition_creation(self):
        """测试周期定义创建."""
        cycle = CycleDefinition(
            phase_sequence=["start", "descent", "bottom", "ascent", "end"],
            start_phase="start",
            end_phase="end",
            required_phases=["bottom"],
        )

        assert cycle.start_phase == "start"
        assert cycle.end_phase == "end"
        assert "bottom" in cycle.required_phases

    def test_cycle_definition_defaults(self):
        """测试周期定义默认值."""
        cycle = CycleDefinition(
            phase_sequence=["start", "end"],
        )

        # 自动设置 start_phase 和 end_phase
        assert cycle.start_phase == "start"
        assert cycle.end_phase == "start"  # 闭环默认


class TestRepCounter:
    """测试动作计数器."""

    def test_rep_counter_basic(self):
        """测试基本计数功能."""
        cycle_def = CycleDefinition(
            phase_sequence=["start", "descent", "bottom", "ascent", "end"],
            required_phases=["bottom"],
            start_phase="start",
            end_phase="end",
        )

        counter = RepCounter(cycle_def)

        # 创建模拟阶段序列
        from src.core.phases.engine import PhaseSequence, PhaseDetection

        phase_seq = PhaseSequence(
            detections=[
                PhaseDetection("start", 0, 10, 0.33),
                PhaseDetection("descent", 11, 20, 0.33),
                PhaseDetection("bottom", 21, 30, 0.33),
                PhaseDetection("ascent", 31, 40, 0.33),
                PhaseDetection("end", 41, 50, 0.33),
                # 第二个 rep
                PhaseDetection("start", 51, 60, 0.33),
                PhaseDetection("descent", 61, 70, 0.33),
                PhaseDetection("bottom", 71, 80, 0.33),
                PhaseDetection("ascent", 81, 90, 0.33),
                PhaseDetection("end", 91, 100, 0.33),
            ]
        )

        result = counter.count(phase_seq)

        assert result.count == 2
        assert len(result.rep_ranges) == 2
        assert result.confidence > 0

    def test_rep_counter_no_cycle_def(self):
        """测试无周期定义时不计数."""
        counter = RepCounter(None)

        from src.core.phases.engine import PhaseSequence
        phase_seq = PhaseSequence(detections=[])

        result = counter.count(phase_seq)

        assert result.count == 0
        assert result.confidence == 0.0


class TestThresholdEvaluator:
    """测试阈值评估引擎."""

    def test_evaluate_excellent(self):
        """测试优秀等级评估."""
        evaluator = ThresholdEvaluator()

        thresholds = MetricThreshold(
            target_value=100.0,
            excellent_range=(95.0, 105.0),
            good_range=(90.0, 110.0),
            pass_range=(80.0, 120.0),
        )

        result = evaluator.evaluate(100.0, thresholds)

        assert result.grade == "excellent"
        assert result.score >= 90

    def test_evaluate_good(self):
        """测试良好等级评估."""
        evaluator = ThresholdEvaluator()

        thresholds = MetricThreshold(
            target_value=100.0,
            excellent_range=(95.0, 105.0),
            good_range=(90.0, 110.0),
            pass_range=(80.0, 120.0),
        )

        result = evaluator.evaluate(92.0, thresholds)

        assert result.grade == "good"
        assert 80 <= result.score < 90

    def test_evaluate_fail(self):
        """测试不及格评估."""
        evaluator = ThresholdEvaluator()

        thresholds = MetricThreshold(
            target_value=100.0,
            pass_range=(80.0, 120.0),
        )

        result = evaluator.evaluate(50.0, thresholds)

        assert result.grade == "fail"
        assert result.score < 60

    def test_normal_range_warning(self):
        """测试正常范围告警."""
        evaluator = ThresholdEvaluator()

        thresholds = MetricThreshold(
            target_value=100.0,
            normal_range=(90.0, 110.0),
            pass_range=(80.0, 120.0),
        )

        # 在 pass_range 但不在 normal_range
        result = evaluator.evaluate(85.0, thresholds)

        assert result.grade == "pass"
        assert result.normal_warning is not None
        assert "偏离正常范围" in result.normal_warning


class TestActionConfigV2:
    """测试 ActionConfig V2 功能."""

    def test_v2_schema_version(self):
        """测试 V2 schema_version."""
        config = ActionConfig(
            schema_version="2.0.0",
            action_id="test",
            action_name="Test",
            action_name_zh="测试",
        )

        assert config.schema_version == "2.0.0"

    def test_cycle_definition_field(self):
        """测试 cycle_definition 字段."""
        cycle = CycleDefinition(
            phase_sequence=["start", "end"],
        )

        config = ActionConfig(
            action_id="test",
            cycle_definition=cycle,
        )

        assert config.cycle_definition is not None
        assert config.cycle_definition.start_phase == "start"

    def test_backward_compatibility(self):
        """测试向后兼容（V1配置加载）."""
        # 模拟 V1 配置（没有 schema_version）
        v1_data = {
            "action_id": "squat",
            "action_name": "Squat",
            "action_name_zh": "深蹲",
            "version": "1.0.0",
            "phases": [
                {"phase_id": "start", "phase_name": "起始"},
                {"phase_id": "bottom", "phase_name": "最低点"},
            ],
            "metrics": [],
        }

        config = ActionConfig.from_dict(v1_data)

        # 默认 schema_version 为 1.0.0
        assert config.schema_version == "1.0.0"
        assert config.action_id == "squat"
        assert len(config.phases) == 2


class TestIntegration:
    """集成测试."""

    def test_full_analysis_pipeline(self):
        """测试完整分析流程（简化）."""
        # 创建配置
        config = ActionConfig(
            action_id="test_squat",
            action_name="Test Squat",
            phases=[
                PhaseDefinition(phase_id="start", phase_name="起始"),
                PhaseDefinition(phase_id="bottom", phase_name="最低点"),
                PhaseDefinition(phase_id="end", phase_name="结束"),
            ],
            metrics=[
                MetricConfig(
                    metric_id="knee_flexion",
                    enabled=True,
                    evaluation_phase="bottom",
                    thresholds=MetricThreshold(
                        target_value=110.0,
                        pass_range=(90.0, 130.0),
                    ),
                ),
            ],
            cycle_definition=CycleDefinition(
                phase_sequence=["start", "bottom", "end"],
                required_phases=["bottom"],
            ),
        )

        # 创建分析器
        analyzer = ActionAnalyzer(config, fps=30.0)

        assert analyzer.config.action_id == "test_squat"
        assert analyzer.rep_counter is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
