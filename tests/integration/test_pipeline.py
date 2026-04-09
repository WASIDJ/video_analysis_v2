"""管道集成测试."""
import pytest
import numpy as np

from src.core.models.base import Keypoint, PoseFrame, PoseSequence
from src.core.features.skeleton_features import SkeletonFeatureExtractor
from src.core.metrics.calculator import MetricsCalculator


class TestSkeletonFeatureExtraction:
    """测试骨骼特征提取集成."""

    def create_squat_sequence(self):
        """创建模拟深蹲姿态序列."""
        sequence = PoseSequence()

        # 模拟10帧的深蹲动作
        for i in range(10):
            # 模拟下蹲过程：膝关节角度从170度减小到90度
            knee_angle = 170 - 8 * i

            # 计算关键点位置（简化）
            hip_y = 0.4 + 0.02 * i
            knee_y = 0.6 + 0.03 * i

            keypoints = [
                Keypoint(name="nose", x=0.5, y=0.2),
                Keypoint(name="left_shoulder", x=0.45, y=0.3),
                Keypoint(name="right_shoulder", x=0.55, y=0.3),
                Keypoint(name="left_elbow", x=0.35, y=0.45),
                Keypoint(name="right_elbow", x=0.65, y=0.45),
                Keypoint(name="left_wrist", x=0.3, y=0.55),
                Keypoint(name="right_wrist", x=0.7, y=0.55),
                Keypoint(name="left_hip", x=0.45, y=hip_y),
                Keypoint(name="right_hip", x=0.55, y=hip_y),
                Keypoint(name="left_knee", x=0.4, y=knee_y),
                Keypoint(name="right_knee", x=0.6, y=knee_y),
                Keypoint(name="left_ankle", x=0.4, y=0.9),
                Keypoint(name="right_ankle", x=0.6, y=0.9),
            ]

            frame = PoseFrame(frame_id=i, keypoints=keypoints)
            sequence.add_frame(frame)

        return sequence

    def test_extract_joint_angles(self):
        """测试关节角度提取."""
        sequence = self.create_squat_sequence()
        extractor = SkeletonFeatureExtractor(use_3d=False)

        features = extractor.extract(sequence)

        assert len(features) > 0

        # 检查是否包含膝关节角度
        angle_feature_names = [f.name for f in features]
        assert "knee_flexion_left" in angle_feature_names or "knee_flexion_right" in angle_feature_names

    def test_calculate_metrics(self):
        """测试检测项计算集成."""
        sequence = self.create_squat_sequence()
        calculator = MetricsCalculator()

        from src.core.metrics.definitions import METRIC_TEMPLATES

        # 计算膝关节屈曲角度
        metric_def = METRIC_TEMPLATES.get("knee_flexion")
        assert metric_def is not None

        result = calculator.calculate_metric(metric_def, sequence)

        assert "values" in result
        assert len(result["values"]) == 10
        assert "statistics" in result
        assert result["name"] == "膝关节屈曲角度"


class TestMetricsCalculator:
    """测试检测项计算器."""

    def test_calculate_trunk_lean(self):
        """测试躯干前倾角度计算."""
        sequence = PoseSequence()

        # 创建前倾姿态
        for i in range(5):
            keypoints = [
                Keypoint(name="left_shoulder", x=0.45, y=0.3),
                Keypoint(name="right_shoulder", x=0.55, y=0.3),
                Keypoint(name="left_hip", x=0.45, y=0.6),
                Keypoint(name="right_hip", x=0.55, y=0.6),
            ]
            frame = PoseFrame(frame_id=i, keypoints=keypoints)
            sequence.add_frame(frame)

        calculator = MetricsCalculator()

        from src.core.metrics.definitions import METRIC_TEMPLATES

        metric_def = METRIC_TEMPLATES.get("trunk_lean")
        result = calculator.calculate_metric(metric_def, sequence)

        assert result is not None
        assert len(result["values"]) == 5


class TestEndToEnd:
    """端到端测试."""

    def test_full_pipeline_mock(self):
        """测试完整流程（模拟数据）."""
        # 1. 创建姿态序列
        sequence = PoseSequence()

        for i in range(5):
            keypoints = [
                Keypoint(name="nose", x=0.5, y=0.2, confidence=0.95),
                Keypoint(name="left_shoulder", x=0.4, y=0.3, confidence=0.95),
                Keypoint(name="right_shoulder", x=0.6, y=0.3, confidence=0.95),
                Keypoint(name="left_hip", x=0.4, y=0.5, confidence=0.90),
                Keypoint(name="right_hip", x=0.6, y=0.5, confidence=0.90),
                Keypoint(name="left_knee", x=0.4, y=0.7, confidence=0.90),
                Keypoint(name="right_knee", x=0.6, y=0.7, confidence=0.90),
                Keypoint(name="left_ankle", x=0.4, y=0.9, confidence=0.85),
                Keypoint(name="right_ankle", x=0.6, y=0.9, confidence=0.85),
            ]
            sequence.add_frame(PoseFrame(frame_id=i, keypoints=keypoints))

        # 2. 特征提取
        extractor = SkeletonFeatureExtractor()
        features = extractor.extract(sequence)

        assert len(features) > 0

        # 3. 检测项计算
        calculator = MetricsCalculator()

        from src.core.metrics.templates import get_metrics_for_action

        metric_ids = get_metrics_for_action("squat")
        results = calculator.calculate_all_metrics(
            sequence,
            metric_ids=metric_ids,
        )

        assert len(results) > 0
        assert "knee_flexion" in results or "trunk_lean" in results
