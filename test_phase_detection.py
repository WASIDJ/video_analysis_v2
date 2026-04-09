#!/usr/bin/env python3
"""
动作阶段检测演示

展示如何使用动作阶段检测来避免在动作起始位置触发错误判定
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import numpy as np
from src.core.models.base import Keypoint, PoseFrame, PoseSequence
from src.core.phases.squat_phases import SquatPhaseDetector, SquatPhase
from src.core.metrics.calculator import MetricsCalculator
from src.core.metrics.definitions import get_metric_definition


def create_simulated_squat():
    """创建一个模拟深蹲的姿态序列"""
    sequence = PoseSequence()

    # 模拟60帧的深蹲：站立(10帧) -> 下蹲(20帧) -> 最低点(5帧) -> 站起(20帧) -> 站立(5帧)
    frames_config = [
        # (phase, num_frames, start_angle, end_angle)
        ("standing", 10, 180, 180),      # 站立
        ("descent", 20, 180, 60),       # 下蹲到最低点
        ("bottom", 5, 60, 60),          # 最低点保持
        ("ascent", 20, 60, 180),        # 站起
        ("completion", 5, 180, 180),    # 完成站立
    ]

    frame_id = 0
    for phase, num_frames, start_angle, end_angle in frames_config:
        for i in range(num_frames):
            t = i / num_frames if num_frames > 1 else 0
            knee_angle = start_angle + (end_angle - start_angle) * t

            # 计算关键点位置（简化）
            knee_y = 0.6 + (knee_angle / 180) * 0.2
            hip_y = 0.4 + (knee_angle / 180) * 0.15

            keypoints = [
                Keypoint(name="left_hip", x=0.45, y=hip_y, confidence=0.95),
                Keypoint(name="right_hip", x=0.55, y=hip_y, confidence=0.95),
                Keypoint(name="left_knee", x=0.4, y=knee_y, confidence=0.95),
                Keypoint(name="right_knee", x=0.6, y=knee_y, confidence=0.95),
                Keypoint(name="left_ankle", x=0.4, y=0.9, confidence=0.90),
                Keypoint(name="right_ankle", x=0.6, y=0.9, confidence=0.90),
            ]

            frame = PoseFrame(frame_id=frame_id, keypoints=keypoints)
            sequence.add_frame(frame)
            frame_id += 1

    return sequence


def test_phase_detection():
    """测试阶段检测功能"""
    print("=" * 70)
    print("动作阶段检测演示")
    print("=" * 70)

    # 创建模拟深蹲序列
    sequence = create_simulated_squat()
    print(f"\n生成模拟深蹲序列: {len(sequence)} 帧")

    # 1. 测试阶段检测
    print("\n" + "-" * 70)
    print("1. 阶段检测结果")
    print("-" * 70)

    detector = SquatPhaseDetector()
    phases = detector.detect_phases(sequence)

    print(f"检测到 {len(phases)} 个阶段:\n")
    for phase in phases:
        print(f"  阶段: {phase.phase.value}")
        print(f"    帧范围: {phase.start_frame} - {phase.end_frame}")
        print(f"    置信度: {phase.confidence}")
        if phase.metadata:
            for key, value in phase.metadata.items():
                if isinstance(value, float):
                    print(f"    {key}: {value:.1f}")
                else:
                    print(f"    {key}: {value}")
        print()

    # 2. 测试关键帧选择
    print("-" * 70)
    print("2. 检测项关键帧选择")
    print("-" * 70)

    test_metrics = ["knee_flexion", "knee_valgus", "trunk_lean"]

    for metric_id in test_metrics:
        key_frame = detector.get_key_frame_for_metric(sequence, metric_id)
        print(f"  {metric_id:20s} -> 关键帧: {key_frame}")

    # 3. 对比：全局评估 vs 阶段感知评估
    print("\n" + "-" * 70)
    print("3. 评估方式对比")
    print("-" * 70)

    metric_def = get_metric_definition("knee_flexion")

    # 计算膝关节角度序列
    angles = []
    for frame in sequence.frames:
        hip = frame.get_keypoint("left_hip")
        knee = frame.get_keypoint("left_knee")
        ankle = frame.get_keypoint("left_ankle")

        if hip and knee and ankle:
            from src.utils.geometry import calculate_angle_2d
            angle = calculate_angle_2d(
                (hip.x, hip.y), (knee.x, knee.y), (ankle.x, ankle.y),
                min_confidence=0.3,
                confidences=(0.95, 0.95, 0.90)
            )
            angles.append(angle)
        else:
            angles.append(np.nan)

    angles = np.array(angles)
    valid_angles = angles[~np.isnan(angles)]

    print(f"\n  膝关节角度统计:")
    print(f"    最小值 (最低点): {np.min(valid_angles):.1f}°")
    print(f"    最大值 (站立):   {np.max(valid_angles):.1f}°")
    print(f"    平均值:          {np.mean(valid_angles):.1f}°")

    # 使用阶段检测获取关键帧
    key_frame = detector.get_key_frame_for_metric(sequence, "knee_flexion")
    key_value = angles[key_frame] if key_frame is not None else None

    print(f"\n  阶段感知评估:")
    print(f"    关键帧:     {key_frame}")
    print(f"    关键帧值:   {key_value:.1f}°" if key_value else "    关键帧值:   N/A")
    print(f"    深度不足?   {'是' if key_value and key_value > 90 else '否'}")

    print(f"\n  传统全局评估 (问题所在):")
    print(f"    使用全局最小值: {np.min(valid_angles):.1f}°")
    print(f"    使用全局最大值: {np.max(valid_angles):.1f}°")
    print(f"    错误: 会同时触发'深度不足'和'过度下蹲'")

    # 4. 完整检测项计算对比
    print("\n" + "-" * 70)
    print("4. 完整检测项计算对比")
    print("-" * 70)

    # 不使用阶段检测
    calc_no_phase = MetricsCalculator(use_phase_detection=False)
    result_no_phase = calc_no_phase.calculate_metric(
        metric_def, sequence, action_name="squat"
    )

    print("\n  不使用阶段检测 (全局极值):")
    print(f"    检测到的错误: {len(result_no_phase.get('errors', []))}")
    for err in result_no_phase.get('errors', []):
        print(f"      - {err['name']}")

    # 使用阶段检测
    calc_with_phase = MetricsCalculator(use_phase_detection=True)
    result_with_phase = calc_with_phase.calculate_metric(
        metric_def, sequence, action_name="squat"
    )

    print("\n  使用阶段检测 (关键点评估):")
    print(f"    检测到的错误: {len(result_with_phase.get('errors', []))}")
    for err in result_with_phase.get('errors', []):
        print(f"      - {err['name']}")
        if 'key_value' in err:
            print(f"        触发值: {err['key_value']:.1f}°")

    print("\n" + "=" * 70)
    print("结论:")
    print("=" * 70)
    print("  ✓ 阶段检测确保在动作关键点进行评估")
    print("  ✓ 避免在起始/结束位置触发误报")
    print("  ✓ 阈值逻辑修复：threshold_high 表示'值过高触发错误'")
    print("  ✓ threshold_low 表示'值过低触发错误'")
    print()


if __name__ == "__main__":
    test_phase_detection()
