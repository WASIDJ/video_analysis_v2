"""配置系统单元测试.

测试配置管理器、验证器和记录器的功能。
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from src.core.config.manager import ConfigManager
from src.core.config.models import (
    ActionConfig,
    MetricConfig,
    MetricThreshold,
    ErrorCondition,
    PhaseDefinition,
)
from src.core.config.validator import ParameterValidator
from src.core.config.recorder import ParameterRecorder


class TestConfigModels(unittest.TestCase):
    """测试配置数据模型."""

    def test_metric_threshold_serialization(self):
        """测试阈值配置的序列化和反序列化."""
        threshold = MetricThreshold(
            target_value=90.0,
            normal_range=(80.0, 100.0),
            excellent_range=(85.0, 95.0),
        )

        # 测试 to_dict
        data = threshold.to_dict()
        self.assertEqual(data["target_value"], 90.0)
        self.assertEqual(data["normal_range"], [80.0, 100.0])

        # 测试 from_dict
        restored = MetricThreshold.from_dict(data)
        self.assertEqual(restored.target_value, 90.0)
        self.assertEqual(restored.normal_range, (80.0, 100.0))

    def test_error_condition_serialization(self):
        """测试错误条件的序列化和反序列化."""
        condition = ErrorCondition(
            error_id="insufficient_depth",
            error_name="深蹲深度不足",
            description="膝关节屈曲角度不足",
            severity="medium",
            condition={"operator": "gt", "value": 90, "phase": "bottom"},
        )

        data = condition.to_dict()
        self.assertEqual(data["error_id"], "insufficient_depth")
        self.assertEqual(data["condition"]["operator"], "gt")

        restored = ErrorCondition.from_dict(data)
        self.assertEqual(restored.error_id, "insufficient_depth")
        self.assertEqual(restored.condition["value"], 90)

    def test_action_config_serialization(self):
        """测试动作配置的完整序列化."""
        config = ActionConfig(
            action_id="squat",
            action_name="Squat",
            action_name_zh="深蹲",
            version="1.0.0",
            phases=[
                PhaseDefinition(
                    phase_id="bottom",
                    phase_name="最低点",
                    description="深蹲最深处",
                )
            ],
            metrics=[
                MetricConfig(
                    metric_id="knee_flexion",
                    enabled=True,
                    evaluation_phase="bottom",
                    thresholds=MetricThreshold(
                        target_value=110.0,
                        normal_range=(90.0, 120.0),
                    ),
                    error_conditions=[
                        ErrorCondition(
                            error_id="insufficient_depth",
                            error_name="深蹲深度不足",
                            description="膝关节屈曲角度不足",
                            severity="medium",
                            condition={"operator": "gt", "value": 90},
                        )
                    ],
                    weight=1.5,
                )
            ],
            global_params={"min_phase_duration": 0.2},
        )

        # 测试完整序列化
        data = config.to_dict()
        self.assertEqual(data["action_id"], "squat")
        self.assertEqual(len(data["metrics"]), 1)
        self.assertEqual(data["metrics"][0]["metric_id"], "knee_flexion")

        # 测试反序列化
        restored = ActionConfig.from_dict(data)
        self.assertEqual(restored.action_id, "squat")
        self.assertEqual(len(restored.metrics), 1)
        self.assertEqual(restored.metrics[0].weight, 1.5)

    def test_get_metric_config(self):
        """测试获取检测项配置."""
        config = ActionConfig(
            action_id="squat",
            action_name="Squat",
            action_name_zh="深蹲",
            metrics=[
                MetricConfig(metric_id="knee_flexion", enabled=True),
                MetricConfig(metric_id="trunk_lean", enabled=False),
            ],
        )

        metric_config = config.get_metric_config("knee_flexion")
        self.assertIsNotNone(metric_config)
        self.assertEqual(metric_config.metric_id, "knee_flexion")
        self.assertTrue(metric_config.enabled)

        # 测试不存在的检测项
        self.assertIsNone(config.get_metric_config("nonexistent"))


class TestConfigManager(unittest.TestCase):
    """测试配置管理器."""

    def setUp(self):
        """创建临时配置目录."""
        self.temp_dir = tempfile.mkdtemp()
        self.config_manager = ConfigManager(config_dir=self.temp_dir, enable_caching=False)

    def tearDown(self):
        """清理临时目录."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_save_and_load_config(self):
        """测试保存和加载配置."""
        config = ActionConfig(
            action_id="test_action",
            action_name="Test Action",
            action_name_zh="测试动作",
            version="1.0.0",
            metrics=[
                MetricConfig(metric_id="knee_flexion", enabled=True),
            ],
        )

        # 保存配置
        result = self.config_manager.save_config(config)
        self.assertTrue(result)

        # 加载配置
        loaded = self.config_manager.load_config("test_action")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.action_id, "test_action")
        self.assertEqual(loaded.version, "1.0.0")

    def test_load_nonexistent_config(self):
        """测试加载不存在的配置."""
        config = self.config_manager.load_config("nonexistent_action")
        # 当配置不存在时，应返回 None（而不是创建默认配置，避免意外行为）
        # 默认配置只在明确的默认动作（squat, lunge 等）时创建
        self.assertIsNone(config)

    def test_list_configs(self):
        """测试列出所有配置."""
        # 创建两个配置
        config1 = ActionConfig(action_id="action1", action_name="Action 1", action_name_zh="动作1")
        config2 = ActionConfig(action_id="action2", action_name="Action 2", action_name_zh="动作2")

        self.config_manager.save_config(config1)
        self.config_manager.save_config(config2)

        configs = self.config_manager.list_configs()
        self.assertGreaterEqual(len(configs), 2)

        action_ids = [c["action_id"] for c in configs]
        self.assertIn("action1", action_ids)
        self.assertIn("action2", action_ids)


class TestParameterValidator(unittest.TestCase):
    """测试参数验证器."""

    def test_validate_metric_config(self):
        """测试检测项配置验证."""
        config = MetricConfig(
            metric_id="knee_flexion",
            enabled=True,
            evaluation_phase="bottom",
            thresholds=MetricThreshold(
                target_value=110.0,
                normal_range=(90.0, 120.0),
            ),
            weight=1.5,
        )

        valid, errors = ParameterValidator.validate_metric_config(config)
        self.assertTrue(valid)
        self.assertEqual(len(errors), 0)

    def test_validate_invalid_phase(self):
        """测试无效阶段的验证."""
        config = MetricConfig(
            metric_id="knee_flexion",
            evaluation_phase="invalid_phase",
        )

        valid, errors = ParameterValidator.validate_metric_config(config)
        self.assertFalse(valid)
        self.assertTrue(any("未知的评估阶段" in e for e in errors))

    def test_validate_threshold_range(self):
        """测试阈值范围验证."""
        config = MetricConfig(
            metric_id="knee_flexion",
            thresholds=MetricThreshold(
                target_value=200.0,  # 超出合法范围
                normal_range=(90.0, 120.0),
            ),
        )

        errors = ParameterValidator.validate_thresholds(
            config.metric_id, config.thresholds
        )
        self.assertTrue(any("目标值" in e and "不在合法范围" in e for e in errors))

    def test_validate_weight_range(self):
        """测试权重范围验证."""
        config = MetricConfig(
            metric_id="knee_flexion",
            weight=15.0,  # 超出范围
        )

        valid, errors = ParameterValidator.validate_metric_config(config)
        self.assertFalse(valid)
        self.assertTrue(any("权重必须" in e for e in errors))

    def test_get_valid_range(self):
        """测试获取合法范围."""
        range_info = ParameterValidator.get_valid_range("knee_flexion")
        self.assertIsNotNone(range_info)
        self.assertEqual(range_info["min"], 0)
        self.assertEqual(range_info["max"], 180)
        self.assertEqual(range_info["unit"], "degrees")


class TestParameterRecorder(unittest.TestCase):
    """测试参数记录器."""

    def setUp(self):
        """创建临时记录目录."""
        self.temp_dir = tempfile.mkdtemp()
        self.recorder = ParameterRecorder(records_dir=self.temp_dir)

    def tearDown(self):
        """清理临时目录."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_record_execution(self):
        """测试记录执行."""
        record_id = self.recorder.record_execution(
            action_id="squat",
            action_version="1.0.0",
            algorithm_version="2.1.0",
            video_path="/path/to/video.mp4",
            params_used={
                "metrics": {
                    "knee_flexion": {"threshold": 90.0},
                }
            },
            results_summary={"score": 85.0},
        )

        self.assertIsNotNone(record_id)
        self.assertEqual(len(record_id), 8)  # UUID前8位

    def test_get_records(self):
        """测试获取记录."""
        # 记录几次执行
        for i in range(3):
            self.recorder.record_execution(
                action_id="squat",
                action_version="1.0.0",
                algorithm_version="2.1.0",
                video_path=f"/path/to/video{i}.mp4",
                params_used={"iteration": i},
            )

        records = self.recorder.get_records("squat", limit=10)
        self.assertEqual(len(records), 3)

    def test_compare_records(self):
        """测试对比记录."""
        record_id1 = self.recorder.record_execution(
            action_id="squat",
            action_version="1.0.0",
            algorithm_version="2.1.0",
            video_path="/path/to/video1.mp4",
            params_used={"threshold": 90.0},
        )

        record_id2 = self.recorder.record_execution(
            action_id="squat",
            action_version="1.1.0",
            algorithm_version="2.1.0",
            video_path="/path/to/video2.mp4",
            params_used={"threshold": 100.0},
        )

        diff = self.recorder.compare_records("squat", record_id1, record_id2)
        self.assertIsNotNone(diff)
        self.assertIn("params_diff", diff)
        self.assertIn("modified", diff["params_diff"])


class TestIntegration(unittest.TestCase):
    """集成测试."""

    def test_end_to_end_workflow(self):
        """测试端到端工作流."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # 1. 创建配置管理器
            config_manager = ConfigManager(config_dir=temp_dir, enable_caching=False)

            # 2. 创建动作配置
            config = ActionConfig(
                action_id="squat",
                action_name="Squat",
                action_name_zh="深蹲",
                version="1.0.0",
                phases=[
                    PhaseDefinition(
                        phase_id="bottom",
                        phase_name="最低点",
                        description="深蹲最深处",
                    )
                ],
                metrics=[
                    MetricConfig(
                        metric_id="knee_flexion",
                        enabled=True,
                        evaluation_phase="bottom",
                        thresholds=MetricThreshold(
                            target_value=110.0,
                            normal_range=(90.0, 120.0),
                            excellent_range=(100.0, 120.0),
                            good_range=(90.0, 130.0),
                            pass_range=(70.0, 140.0),
                        ),
                        error_conditions=[
                            ErrorCondition(
                                error_id="insufficient_depth",
                                error_name="深蹲深度不足",
                                description="膝关节屈曲角度不足",
                                severity="medium",
                                condition={"operator": "gt", "value": 90},
                            )
                        ],
                        weight=1.5,
                    ),
                ],
                global_params={
                    "min_phase_duration": 0.2,
                    "enable_phase_detection": True,
                },
            )

            # 3. 保存配置
            self.assertTrue(config_manager.save_config(config))

            # 4. 验证配置
            valid, errors = ParameterValidator.validate_action_config(config)
            self.assertTrue(valid, f"验证失败: {errors}")

            # 5. 加载配置
            loaded_config = config_manager.load_config("squat")
            self.assertIsNotNone(loaded_config)
            self.assertEqual(loaded_config.action_id, "squat")

            # 6. 验证检测项配置
            metric_config = loaded_config.get_metric_config("knee_flexion")
            self.assertIsNotNone(metric_config)
            self.assertEqual(metric_config.thresholds.target_value, 110.0)
            self.assertEqual(len(metric_config.error_conditions), 1)

            # 7. 记录执行
            records_dir = os.path.join(temp_dir, "records")
            recorder = ParameterRecorder(records_dir=records_dir)
            record_id = recorder.record_execution(
                action_id="squat",
                action_version="1.0.0",
                algorithm_version="2.1.0",
                video_path="/path/to/test_video.mp4",
                params_used=config.to_dict(),
                results_summary={"overall_score": 85.5},
            )
            self.assertIsNotNone(record_id)

            # 8. 获取记录
            records = recorder.get_records("squat")
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0].action_id, "squat")


if __name__ == "__main__":
    unittest.main()
