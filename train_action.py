#!/usr/bin/env python3
"""批量视频训练启动脚本.

使用示例:
    # 方式1: 使用JSON配置文件
    python train_action.py --config jumping_jack_config.json

    # 方式2: 命令行参数
    python train_action.py \
        --action-id jumping_jack \
        --action-name "开合跳" \
        --video std1.mp4 --tag standard \
        --video err1.mp4 --tag "error:knee_valgus"

JSON配置格式:
{
    "action_id": "jumping_jack",
    "action_name_zh": "开合跳",
    "videos": [
        {"video_path": "path/to/std1.mp4", "tags": ["standard"]},
        {"video_path": "path/to/std2.mp4", "tags": ["standard"]},
        {"video_path": "path/to/err1.mp4", "tags": ["error:knee_valgus"]},
        {"video_path": "path/to/err2.mp4", "tags": ["error:knee_valgus"]},
        {"video_path": "path/to/extreme1.mp4", "tags": ["extreme"]}
    ],
    "auto_approve": false,
    "output_dir": "config/action_configs"
}
"""
import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict

# 添加src到路径
sys.path.insert(0, str(Path(__file__).parent))

from src.core.training.batch_processor import BatchProcessor, BatchConfig, create_batch_config_from_json
from src.core.training.pipeline import VideoTrainingConfig


def create_parser() -> argparse.ArgumentParser:
    """创建命令行参数解析器."""
    parser = argparse.ArgumentParser(
        description="训练新动作配置",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用配置文件
  %(prog)s --config my_action.json

  # 命令行方式
  %(prog)s --action-id squat --action-name "深蹲" \\
    --video ./std1.mp4 --tag standard \\
    --video ./err1.mp4 --tag "error:insufficient_depth"
        """
    )

    parser.add_argument(
        "--config", "-c",
        help="JSON配置文件路径"
    )

    parser.add_argument(
        "--action-id", "-a",
        help="动作ID（如：jumping_jack）"
    )

    parser.add_argument(
        "--action-name",
        help="动作中文名称"
    )

    parser.add_argument(
        "--video", "-v",
        action="append",
        dest="videos",
        help="视频路径（可多次使用）"
    )

    parser.add_argument(
        "--tag", "-t",
        action="append",
        dest="tags",
        help="视频标签（与--video一一对应）"
    )

    parser.add_argument(
        "--output-dir", "-o",
        default="config/action_configs",
        help="输出目录（默认：config/action_configs）"
    )

    parser.add_argument(
        "--fingerprint-db",
        default="data/fingerprints",
        help="指纹数据库存储路径"
    )

    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="自动批准（跳过人工审核）"
    )

    parser.add_argument(
        "--min-standard",
        type=int,
        default=3,
        help="最少标准样本数（默认：3）"
    )

    return parser


def validate_args(args) -> bool:
    """验证参数."""
    if args.config:
        if not Path(args.config).exists():
            print(f"错误：配置文件不存在：{args.config}")
            return False
        return True

    if not args.action_id:
        print("错误：必须提供 --action-id 或 --config")
        return False

    if not args.videos:
        print("错误：必须提供至少一个 --video")
        return False

    if args.tags and len(args.tags) != len(args.videos):
        print("错误：--tag 数量必须与 --video 数量一致")
        return False

    # 检查视频文件
    for video_path in args.videos:
        if not Path(video_path).exists():
            print(f"错误：视频文件不存在：{video_path}")
            return False

    return True


def build_config_from_args(args) -> BatchConfig:
    """从命令行参数构建配置."""
    videos = []

    for i, video_path in enumerate(args.videos):
        tags = [args.tags[i]] if args.tags and i < len(args.tags) else ["standard"]
        videos.append(VideoTrainingConfig(
            video_path=video_path,
            tags=tags,
        ))

    return BatchConfig(
        action_id=args.action_id,
        action_name_zh=args.action_name or args.action_id,
        videos=videos,
        output_dir=args.output_dir,
        fingerprint_db_path=args.fingerprint_db,
        auto_approve=args.auto_approve,
        min_standard_samples=args.min_standard,
    )


def print_result(result: Dict) -> None:
    """打印处理结果."""
    print("\n" + "=" * 50)
    print("训练结果")
    print("=" * 50)

    if result["success"]:
        print(f"✓ 动作ID: {result['action_id']}")
        print(f"✓ 配置文件: {result['generated_config_path']}")
        print(f"✓ 指纹数据库: {result['fingerprint_db_path']}")
        print(f"✓ 处理视频数: {result['videos_processed']}")
        print(f"✓ 配置置信度: {result['quality_report']['confidence']:.2f}")

        if result['quality_report'].get('error_types_covered', 0) > 0:
            print(f"✓ 错误类型覆盖: {result['quality_report']['error_types_covered']}")
    else:
        print(f"✗ 训练失败")

    if result.get('warnings'):
        print("\n⚠ 警告:")
        for warning in result['warnings']:
            print(f"  - {warning}")

    if result.get('requires_manual_review'):
        print("\n⚠ 配置需要人工审核后才能投入使用")
        print(f"   审核命令: python approve_action.py --action-id {result['action_id']}")

    print("=" * 50)


def main():
    """主函数."""
    parser = create_parser()
    args = parser.parse_args()

    # 验证参数
    if not validate_args(args):
        sys.exit(1)

    # 构建配置
    if args.config:
        print(f"从配置文件加载: {args.config}")
        config = create_batch_config_from_json(args.config)
    else:
        print(f"从命令行参数构建配置")
        config = build_config_from_args(args)

    print(f"\n动作ID: {config.action_id}")
    print(f"中文名称: {config.action_name_zh}")
    print(f"视频数量: {len(config.videos)}")

    # 统计标签
    tag_counts = {}
    for v in config.videos:
        for tag in v.tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1

    print("标签分布:")
    for tag, count in sorted(tag_counts.items()):
        print(f"  - {tag}: {count}")

    # 确认
    if not config.auto_approve:
        response = "y" # auto accept for testing
        if response and response != 'y':
            print("取消训练")
            sys.exit(0)

    # 执行训练
    print("\n开始训练...")
    processor = BatchProcessor(config)
    result = processor.process()

    # 打印结果
    print_result(result)

    # 返回码
    sys.exit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
