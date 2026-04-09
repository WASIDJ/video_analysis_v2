#!/usr/bin/env python3
"""
本地视频测试脚本

使用方法:
1. 激活conda环境:
   conda activate py310

2. 运行测试:
   python test_video.py --video /path/to/video.mp4 --action squat

3. 批量测试文件夹内所有视频:
   python test_video.py --folder /path/to/videos/ --action squat

4. 使用YOLO模型（而非默认BlazePose）:
   python test_video.py --video video.mp4 --model yolo
"""

import argparse
import json
import sys
import time
from pathlib import Path
from typing import List, Dict, Any

# 确保可以导入src模块
sys.path.insert(0, str(Path(__file__).parent))

import numpy as np

from src.core.models.base import create_pose_estimator
from src.core.features.skeleton_features import SkeletonFeatureExtractor
from src.core.features.segment_features import SegmentFeatureExtractor
from src.core.metrics.calculator import MetricsCalculator
from src.core.metrics.templates import get_metrics_for_action, get_action_template
from src.core.metrics.definitions import METRIC_TEMPLATES
from src.utils.video import VideoFrameIterator


def analyze_video(
    video_path: str,
    action_name: str = "squat",
    model_type: str = "blazepose",
    enable_segment: bool = False,
    output_dir: str = "./output",
) -> Dict[str, Any]:
    """
    分析单个视频

    Args:
        video_path: 视频文件路径
        action_name: 动作名称 (squat/lunge/pushup/plank/deadlift/overhead_press)
        model_type: 姿态估计模型 (blazepose/yolo)
        enable_segment: 是否启用体块分割特征
        output_dir: 输出目录

    Returns:
        分析结果字典
    """
    print(f"\n{'='*60}")
    print(f"分析视频: {video_path}")
    print(f"动作类型: {action_name}")
    print(f"姿态模型: {model_type}")
    print(f"{'='*60}\n")

    start_time = time.time()

    # 1. 初始化姿态估计器
    print("[1/4] 初始化姿态估计模型...")
    pose_estimator = create_pose_estimator(model_type)
    print(f"      模型: {pose_estimator.model_name}")
    print(f"      关键点数: {pose_estimator.num_keypoints}")

    # 2. 姿态估计
    print("[2/4] 进行姿态估计...")
    pose_sequence = pose_estimator.process_video(video_path)
    print(f"      处理帧数: {len(pose_sequence)}")

    if len(pose_sequence) == 0:
        print("      ❌ 未检测到姿态")
        return {"error": "未检测到姿态", "video_path": video_path}

    # 3. 特征提取
    print("[3/4] 提取特征...")

    # 3.1 骨骼特征
    skeleton_extractor = SkeletonFeatureExtractor()
    skeleton_features = skeleton_extractor.extract(pose_sequence)
    print(f"      骨骼特征: {len(skeleton_features)} 个")

    # 3.2 体块特征（可选）
    segment_features_dict = {}
    if enable_segment:
        print("      提取体块特征...")
        segment_extractor = SegmentFeatureExtractor()

        # 读取视频帧
        video_frames = []
        with VideoFrameIterator(video_path) as iterator:
            for _, frame in iterator:
                video_frames.append(frame)

        segment_feature_sets = segment_extractor.extract(pose_sequence, video_frames)
        segment_features_dict = {fs.name: fs.values for fs in segment_feature_sets}
        print(f"      体块特征: {len(segment_features_dict)} 个")

    # 4. 检测项计算
    print("[4/4] 计算检测项...")
    print("      启用功能：")
    print("        - 动作阶段检测（在关键点评估）")
    print("        - 视角分析（自动检测拍摄角度）")
    print("        - 左右侧自动选择（基于置信度）")

    calculator = MetricsCalculator(
        action_id=action_name,
        use_phase_detection=True,
        use_viewpoint_analysis=True,
        auto_select_side=True,
    )

    config_summary = calculator.get_action_config_summary()
    if config_summary.get("loaded") and config_summary.get("enabled_metrics"):
        metric_ids = config_summary["enabled_metrics"]
    else:
        metric_ids = get_metrics_for_action(action_name)
        if not metric_ids:
            metric_ids = ["knee_flexion", "trunk_lean", "lumbar_curvature"]

    print(f"      计算检测项: {len(metric_ids)} 个")

    results = calculator.calculate_all_metrics(
        pose_sequence,
        metric_ids=metric_ids,
        segment_features=segment_features_dict,
        action_name=action_name,
    )

    # 5. 结果格式化
    processing_time = time.time() - start_time

    # 收集检测到的错误
    detected_errors = []
    skipped_metrics = []
    viewpoint_info = {}
    metrics_summary = []

    for metric_id, result in results.items():
        # 收集视角信息
        if "statistics" in result:
            stats = result["statistics"]
            if "viewpoint" in stats and not viewpoint_info:
                viewpoint_info = {
                    "viewpoint": stats.get("viewpoint"),
                    "confidence": stats.get("viewpoint_confidence"),
                    "used_side": stats.get("used_side"),
                }

        # 处理跳过的检测项
        if result.get("skipped"):
            skipped_metrics.append({
                "metric_id": metric_id,
                "metric_name": result.get("name", ""),
                "reason": result.get("error", ""),
                "reliability": result.get("reliability", 0),
            })
            continue

        if "error" in result:
            continue

        stats = result.get("statistics", {})
        metric_summary = {
            "id": metric_id,
            "name": result.get("name", ""),
            "mean": stats.get("mean"),
            "min": stats.get("min"),
            "max": stats.get("max"),
            "unit": result.get("unit", ""),
        }
        if "reliability" in stats:
            metric_summary["reliability"] = stats["reliability"]
        metrics_summary.append(metric_summary)

        # 收集错误
        for error in result.get("errors", []):
            detected_errors.append({
                "metric": result.get("name", ""),
                "error": error.get("name", ""),
                "severity": error.get("severity", "medium"),
                "description": error.get("description", ""),
            })

    # 构建完整结果
    analysis_result = {
        "video_path": video_path,
        "action_name": action_name,
        "pose_model": pose_estimator.model_name,
        "num_frames": len(pose_sequence),
        "processing_time": round(processing_time, 2),
        "viewpoint": viewpoint_info,
        "metrics_summary": metrics_summary,
        "detected_errors": detected_errors,
        "skipped_metrics": skipped_metrics,
        "detailed_results": results,
    }

    # 保存结果到文件
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    output_file = output_path / f"{Path(video_path).stem}_result.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(analysis_result, f, ensure_ascii=False, indent=2)

    # 打印结果摘要
    print(f"\n{'='*60}")
    print("分析完成!")
    print(f"{'='*60}")
    print(f"处理时间: {processing_time:.2f} 秒")

    # 显示视角分析结果
    if viewpoint_info:
        print(f"\n📹 视角分析:")
        print(f"  检测到的视角: {viewpoint_info.get('viewpoint', 'unknown')}")
        print(f"  视角置信度: {viewpoint_info.get('confidence', 0):.2f}")
        print(f"  使用侧面: {viewpoint_info.get('used_side', 'unknown')}")

    # 显示跳过的检测项
    if skipped_metrics:
        print(f"\n⏭️  因视角不可靠而跳过的检测项 ({len(skipped_metrics)}个):")
        for m in skipped_metrics[:3]:
            print(f"  • {m['metric_name']}: {m['reason'][:50]}...")

    print(f"\n检测项摘要:")
    for m in metrics_summary[:5]:  # 只显示前5个
        if m["mean"] is not None:
            rel_str = f" (可靠度:{m['reliability']:.1f})" if 'reliability' in m else ""
            print(f"  • {m['name']}: {m['mean']:.1f} {m['unit']}{rel_str}")

    if detected_errors:
        print(f"\n⚠️  检测到 {len(detected_errors)} 个问题:")
        for err in detected_errors[:3]:  # 只显示前3个
            severity_icon = "🔴" if err["severity"] == "high" else "🟡"
            print(f"  {severity_icon} {err['metric']} - {err['error']}")
    else:
        print("\n✅ 未检测到明显问题")

    print(f"\n结果已保存: {output_file}")
    print(f"{'='*60}\n")

    return analysis_result


def batch_analyze(
    folder_path: str,
    action_name: str = "squat",
    model_type: str = "blazepose",
    enable_segment: bool = False,
) -> List[Dict[str, Any]]:
    """批量分析文件夹内所有视频"""
    folder = Path(folder_path)

    # 支持的视频格式
    video_extensions = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".wmv"}

    # 查找所有视频文件
    video_files = [
        f for f in folder.iterdir()
        if f.is_file() and f.suffix.lower() in video_extensions
    ]

    if not video_files:
        print(f"❌ 在 {folder_path} 中未找到视频文件")
        return []

    print(f"找到 {len(video_files)} 个视频文件")

    results = []
    for video_file in sorted(video_files):
        try:
            result = analyze_video(
                str(video_file),
                action_name=action_name,
                model_type=model_type,
                enable_segment=enable_segment,
            )
            results.append(result)
        except Exception as e:
            print(f"❌ 分析失败 {video_file}: {e}")
            results.append({
                "video_path": str(video_file),
                "error": str(e),
            })

    return results


def main():
    parser = argparse.ArgumentParser(
        description="视频姿态分析测试脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 分析单个视频
  python test_video.py --video squat_video.mp4 --action squat

  # 批量分析文件夹
  python test_video.py --folder ./videos/ --action squat

  # 使用YOLO模型
  python test_video.py --video video.mp4 --model yolo

  # 启用体块分割特征（用于识别耸肩、塌腰）
  python test_video.py --video video.mp4 --enable-segment

  # 指定输出目录
  python test_video.py --video video.mp4 --output ./my_results/
        """
    )

    parser.add_argument(
        "--video",
        type=str,
        help="单个视频文件路径",
    )
    parser.add_argument(
        "--folder",
        type=str,
        help="批量分析文件夹路径",
    )
    parser.add_argument(
        "--action",
        type=str,
        default="squat",
        help="动作类型 (默认: squat)",
    )
    parser.add_argument(
        "--model",
        type=str,
        default="blazepose",
        choices=["blazepose", "yolo"],
        help="姿态估计模型 (默认: blazepose)",
    )
    parser.add_argument(
        "--enable-segment",
        action="store_true",
        help="启用体块分割特征提取",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="./output",
        help="输出目录 (默认: ./output)",
    )
    parser.add_argument(
        "--list-metrics",
        action="store_true",
        help="列出所有可用检测项",
    )
    parser.add_argument(
        "--list-actions",
        action="store_true",
        help="列出所有可用动作模板",
    )

    args = parser.parse_args()

    # 列出检测项
    if args.list_metrics:
        print("\n可用检测项:")
        print("-" * 60)
        for metric_id, metric in METRIC_TEMPLATES.items():
            print(f"  {metric_id:30s} - {metric.name_zh}")
        print()
        return

    # 列出动作模板
    if args.list_actions:
        print("\n可用动作模板:")
        print("-" * 60)
        from src.core.metrics.templates import ACTION_TEMPLATES
        for action_id, template in ACTION_TEMPLATES.items():
            print(f"  {action_id:20s} - {template.name_zh}")
            print(f"    主要检测项: {', '.join(template.primary_metrics[:3])}")
        print()
        return

    # 验证参数
    if not args.video and not args.folder:
        parser.print_help()
        print("\n❌ 请指定 --video 或 --folder 参数")
        sys.exit(1)

    # 执行分析
    if args.video:
        # 单个视频
        if not Path(args.video).exists():
            print(f"❌ 视频文件不存在: {args.video}")
            sys.exit(1)

        analyze_video(
            video_path=args.video,
            action_name=args.action,
            model_type=args.model,
            enable_segment=args.enable_segment,
            output_dir=args.output,
        )

    elif args.folder:
        # 批量分析
        if not Path(args.folder).exists():
            print(f"❌ 文件夹不存在: {args.folder}")
            sys.exit(1)

        batch_analyze(
            folder_path=args.folder,
            action_name=args.action,
            model_type=args.model,
            enable_segment=args.enable_segment,
        )


if __name__ == "__main__":
    main()
