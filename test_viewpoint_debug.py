#!/usr/bin/env python3
"""
视角分析调试脚本

分析视频的视角特征，帮助调试视角检测算法
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.core.models.base import create_pose_estimator
from src.core.viewpoint.analyzer import ViewpointAnalyzer
from src.utils.video import VideoFrameIterator
import numpy as np


def analyze_video_viewpoint(video_path: str):
    """分析视频视角特征"""
    print("=" * 70)
    print(f"视角分析调试: {video_path}")
    print("=" * 70)

    # 1. 姿态估计
    print("\n[1] 进行姿态估计...")
    estimator = create_pose_estimator("blazepose")
    pose_sequence = estimator.process_video(video_path)
    print(f"    处理帧数: {len(pose_sequence)}")

    if len(pose_sequence) == 0:
        print("❌ 未检测到姿态")
        return

    # 2. 详细视角分析
    print("\n[2] 详细视角特征分析...")
    analyzer = ViewpointAnalyzer()

    # 采样多帧进行分析
    sample_indices = np.linspace(0, len(pose_sequence)-1, 10, dtype=int)

    print("\n    各帧特征:")
    print(f"    {'帧号':>6} | {'髋肩比':>8} | {'左可见':>8} | {'右可见':>8} | {'深度差':>8}")
    print("    " + "-" * 60)

    ratios = []
    left_viss = []
    right_viss = []

    for idx in sample_indices:
        frame = pose_sequence.frames[idx]

        # 髋肩比
        ratio = analyzer._calculate_hip_shoulder_ratio(frame)
        if ratio:
            ratios.append(ratio)

        # 可见性
        left_vis, right_vis = analyzer._analyze_side_visibility(frame)
        left_viss.append(left_vis)
        right_viss.append(right_vis)

        # 深度变化
        depth_var = analyzer._analyze_depth_variation(frame)

        ratio_str = f"{ratio:.3f}" if ratio else "N/A"
        depth_str = f"{depth_var:.3f}" if depth_var else "N/A"

        print(f"    {idx:>6} | {ratio_str:>8} | {left_vis:>8.3f} | {right_vis:>8.3f} | {depth_str:>8}")

    # 3. 综合判断
    print("\n[3] 综合统计:")
    if ratios:
        print(f"    髋肩比统计:")
        print(f"      平均值: {np.mean(ratios):.3f}")
        print(f"      最小值: {np.min(ratios):.3f}")
        print(f"      最大值: {np.max(ratios):.3f}")

        # 判断逻辑
        avg_ratio = np.mean(ratios)
        avg_left = np.mean(left_viss)
        avg_right = np.mean(right_viss)

        print(f"\n    可见性统计:")
        print(f"      左侧平均可见度: {avg_left:.3f}")
        print(f"      右侧平均可见度: {avg_right:.3f}")
        print(f"      可见性差: {abs(avg_left - avg_right):.3f}")

        print(f"\n    视角判断:")
        if avg_ratio > 0.85:
            print(f"      → 侧面视角 (髋肩比 > 0.85)")
        elif avg_ratio < 0.75:
            print(f"      → 正面视角 (髋肩比 < 0.75)")
        else:
            print(f"      → 斜角视角 (0.75 <= 髋肩比 <= 0.85)")

        if abs(avg_left - avg_right) > 0.2:
            more_visible = "左侧" if avg_left > avg_right else "右侧"
            print(f"      → {more_visible}更可见 (差异 > 0.2)")

    # 4. 视角分析器结果
    print("\n[4] 视角分析器输出:")
    result = analyzer.analyze(pose_sequence)
    print(f"    检测到的视角: {result.viewpoint.value}")
    print(f"    置信度: {result.confidence:.2f}")
    print(f"    髋肩比: {result.hip_shoulder_ratio:.3f}")
    print(f"    左侧可见: {result.left_side_visible}")
    print(f"    右侧可见: {result.right_side_visible}")
    print(f"    深度可靠性: {result.depth_reliability:.2f}")
    print(f"    推荐侧面: {result.recommended_side}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="视角分析调试")
    parser.add_argument("--video", type=str, required=True, help="视频文件路径")
    args = parser.parse_args()

    if not Path(args.video).exists():
        print(f"❌ 视频文件不存在: {args.video}")
        sys.exit(1)

    analyze_video_viewpoint(args.video)
