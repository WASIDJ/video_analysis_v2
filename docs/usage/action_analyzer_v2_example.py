"""ActionAnalyzer V2 使用示例.

演示如何使用新的 V2 API 进行动作分析。
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from src.core.config.models import (
    ActionConfig,
    PhaseDefinition,
    MetricConfig,
    MetricThreshold,
    ErrorCondition,
    CycleDefinition,
)
from src.core.analysis.analyzer import ActionAnalyzer
from src.core.models.base import PoseSequence, PoseFrame, Keypoint
import numpy as np


def create_sample_config():
    """创建示例配置."""
    return ActionConfig(
        schema_version="2.0.0",
        action_id="squat",
        action_name="Squat",
        action_name_zh="深蹲",
        description="深蹲动作分析",
        version="2.0.0",
        phases=[
            PhaseDefinition(
                phase_id="start",
                phase_name="起始位置",
                description="站立起始",
            ),
            PhaseDefinition(
                phase_id="descent",
                phase_name="下蹲阶段",
                description="下蹲过程",
            ),
            PhaseDefinition(
                phase_id="bottom",
                phase_name="最低点",
                description="深蹲最深处",
            ),
            PhaseDefinition(
                phase_id="ascent",
                phase_name="上升阶段",
                description="站起过程",
            ),
            PhaseDefinition(
                phase_id="end",
                phase_name="结束",
                description="回到站立",
            ),
        ],
        metrics=[
            MetricConfig(
                metric_id="knee_flexion",
                enabled=True,
                evaluation_phase="bottom",
                thresholds=MetricThreshold(
                    target_value=110.0,
                    normal_range=(100.0, 120.0),
                    excellent_range=(105.0, 115.0),
                    good_range=(100.0, 120.0),
                    pass_range=(90.0, 130.0),
                ),
                error_conditions=[
                    ErrorCondition(
                        error_id="insufficient_depth",
                        error_name="深蹲深度不足",
                        description="膝关节屈曲角度不足，应≥90度",
                        severity="medium",
                        condition={"operator": "lt", "value": 90},
                    ),
                ],
                weight=1.5,
            ),
            MetricConfig(
                metric_id="trunk_lean",
                enabled=True,
                evaluation_phase="bottom",
                thresholds=MetricThreshold(
                    target_value=30.0,
                    pass_range=(0.0, 45.0),
                ),
                weight=1.0,
            ),
        ],
        global_params={
            "min_phase_duration": 0.2,
            "enable_phase_detection": True,
        },
        cycle_definition=CycleDefinition(
            phase_sequence=["start", "descent", "bottom", "ascent", "end"],
            start_phase="start",
            end_phase="end",
            required_phases=["bottom"],
            cycle_mode="closed",
            min_cycle_duration=1.0,
            max_cycle_duration=5.0,
        ),
        metadata={
            "author": "system",
            "tags": ["lower_body", "strength"],
        },
    )


def create_sample_pose_sequence():
    """创建示例姿态序列（简化）."""
    frames = []

    # 模拟 3 秒的 30fps 视频 = 90 帧
    for i in range(90):
        t = i / 30.0  # 时间（秒）

        # 模拟深蹲动作：
        # 0-1s: 下蹲 (knee_flexion 从 170 降到 90)
        # 1-2s: 最低点保持 (90)
        # 2-3s: 站起 (90 升到 170)
        if t < 1.0:
            knee_angle = 170 - 80 * t  # 线性下降
        elif t < 2.0:
            knee_angle = 90  # 保持
        else:
            knee_angle = 90 + 80 * (t - 2.0)  # 线性上升

        # 创建关键点（简化）
        keypoints = [
            Keypoint("left_hip", 0.5, 0.4, 0, 0.95),
            Keypoint("left_knee", 0.5, 0.6, 0, 0.95),
            Keypoint("left_ankle", 0.5, 0.8, 0, 0.95),
            Keypoint("left_shoulder", 0.5, 0.2, 0, 0.95),
        ]

        frame = PoseFrame(
            frame_id=i,
            keypoints=keypoints,
            timestamp=t,
        )
        frames.append(frame)

    return PoseSequence(frames=frames)


def main():
    """主函数."""
    print("=" * 60)
    print("ActionAnalyzer V2 使用示例")
    print("=" * 60)

    # 1. 创建配置
    print("\n1. 创建动作配置...")
    config = create_sample_config()
    print(f"   动作ID: {config.action_id}")
    print(f"   Schema版本: {config.schema_version}")
    print(f"   阶段数: {len(config.phases)}")
    print(f"   检测项数: {len(config.metrics)}")
    print(f"   周期定义: {config.cycle_definition.start_phase} -> {config.cycle_definition.end_phase}")

    # 2. 创建分析器
    print("\n2. 创建分析器...")
    analyzer = ActionAnalyzer(config, fps=30.0)
    print("   分析器创建成功")

    # 3. 创建示例数据
    print("\n3. 创建示例姿态序列...")
    pose_sequence = create_sample_pose_sequence()
    print(f"   帧数: {len(pose_sequence.frames)}")
    print(f"   时长: {pose_sequence.frames[-1].timestamp:.2f}秒")

    # 4. 执行分析
    print("\n4. 执行分析...")
    result = analyzer.analyze(pose_sequence)

    # 5. 输出结果
    print("\n5. 分析结果:")
    print(f"   API版本: {result.api_version}")
    print(f"   处理时间: {result.processing_info['duration_ms']:.2f}ms")

    print(f"\n   阶段检测:")
    for phase in result.phases:
        print(f"     - {phase['phase_id']}: 帧{phase['start_frame']}-{phase['end_frame']}, "
              f"持续{phase['duration']:.2f}s")

    print(f"\n   动作计数:")
    print(f"     - 完成次数: {result.rep_count['count']}")
    print(f"     - 置信度: {result.rep_count['confidence']:.2f}")

    print(f"\n   检测项评估:")
    for metric_id, metric_result in result.metrics.items():
        print(f"     - {metric_id}:")
        print(f"       名称: {metric_result['name']}")
        print(f"       等级: {metric_result['grade']}")
        score = metric_result['score']
        print(f"       评分: {score:.1f}" if score is not None else "       评分: N/A")
        key_value = metric_result['key_frame_value']
        print(f"       关键帧值: {key_value:.1f}" if key_value is not None else "       关键帧值: N/A")
        if metric_result['errors']:
            print(f"       错误: {[e.get('error_id') for e in metric_result['errors']]}")

    print(f"\n   整体评估:")
    print(f"     - 等级: {result.overall['grade']}")
    print(f"     - 评分: {result.overall['score']:.1f}")
    print(f"     - 错误数: {result.overall['error_count']}")
    print(f"     - 摘要: {result.overall['summary']}")

    print("\n" + "=" * 60)
    print("示例完成")
    print("=" * 60)

    return result


if __name__ == "__main__":
    main()
