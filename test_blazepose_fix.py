#!/usr/bin/env python3
"""
测试 BlazePose Tasks API 修复

使用方法:
    conda activate py310
    python test_blazepose_fix.py --video /path/to/video.mp4
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def test_import():
    """测试模块导入"""
    print("=" * 60)
    print("1. 测试模块导入")
    print("=" * 60)

    try:
        from src.core.models.base import create_pose_estimator
        print("✅ create_pose_estimator 导入成功")

        from src.core.models.blazepose import BlazePoseEstimator
        print("✅ BlazePoseEstimator 导入成功")

        return True
    except Exception as e:
        print(f"❌ 导入失败: {e}")
        return False


def test_initialization():
    """测试模型初始化"""
    print("\n" + "=" * 60)
    print("2. 测试模型初始化")
    print("=" * 60)

    try:
        from src.core.models.base import create_pose_estimator

        print("创建 BlazePoseEstimator...")
        estimator = create_pose_estimator("blazepose")

        print(f"✅ 模型创建成功")
        print(f"   模型名称: {estimator.model_name}")
        print(f"   关键点数: {estimator.num_keypoints}")
        print(f"   关键点名称: {estimator.keypoint_names[:5]}...")

        return True
    except Exception as e:
        print(f"❌ 初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_video_analysis(video_path: str):
    """测试视频分析"""
    print("\n" + "=" * 60)
    print("3. 测试视频分析")
    print("=" * 60)

    if not Path(video_path).exists():
        print(f"❌ 视频文件不存在: {video_path}")
        return False

    try:
        from src.core.models.base import create_pose_estimator
        from src.core.features.skeleton_features import SkeletonFeatureExtractor
        from src.core.metrics.calculator import MetricsCalculator
        from src.core.metrics.templates import get_metrics_for_action

        # 1. 创建估计器
        print(f"\n加载视频: {video_path}")
        estimator = create_pose_estimator("blazepose")
        print(f"✅ 模型创建成功: {estimator.model_name}")

        # 2. 姿态估计
        print("\n开始姿态估计...")
        sequence = estimator.process_video(video_path)
        print(f"✅ 姿态估计完成")
        print(f"   处理帧数: {len(sequence)}")

        if len(sequence) == 0:
            print("⚠️ 未检测到姿态")
            return False

        # 3. 特征提取
        print("\n提取骨骼特征...")
        extractor = SkeletonFeatureExtractor()
        features = extractor.extract(sequence)
        print(f"✅ 特征提取完成: {len(features)} 个特征")

        # 4. 检测项计算
        print("\n计算检测项...")
        calculator = MetricsCalculator()
        metric_ids = get_metrics_for_action("squat")[:3]

        results = calculator.calculate_all_metrics(sequence, metric_ids=metric_ids)
        print(f"✅ 检测项计算完成: {len(results)} 个")

        for metric_id, result in results.items():
            if "error" not in result:
                stats = result.get("statistics", {})
                print(f"   - {result['name']}: mean={stats.get('mean', 0):.1f}°")

        return True

    except Exception as e:
        print(f"❌ 分析失败: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    parser = argparse.ArgumentParser(description="测试 BlazePose Tasks API")
    parser.add_argument(
        "--video",
        type=str,
        help="测试用的视频文件路径",
    )
    parser.add_argument(
        "--skip-video",
        action="store_true",
        help="跳过视频测试",
    )

    args = parser.parse_args()

    print("\n" + "=" * 60)
    print("BlazePose Tasks API 修复测试")
    print("=" * 60)

    # 测试1: 导入
    if not test_import():
        print("\n❌ 导入测试失败，停止后续测试")
        return 1

    # 测试2: 初始化
    if not test_initialization():
        print("\n❌ 初始化测试失败，停止后续测试")
        return 1

    # 测试3: 视频分析
    if not args.skip_video:
        if args.video:
            if not test_video_analysis(args.video):
                return 1
        else:
            print("\n⚠️ 未提供视频文件，跳过视频分析测试")
            print("   使用 --video /path/to/video.mp4 指定视频")

    print("\n" + "=" * 60)
    print("✅ 所有测试通过!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
