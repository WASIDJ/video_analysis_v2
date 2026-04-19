"""通用动作训练执行脚本.

通过配置文件执行完整训练流程，并产出：
1) 训练配置产物（action_config）
2) 训练后自动拆分清单（dataset split manifest）
3) 测试评估结果（ModelEvaluation JSON）
4) 训练执行报告（Markdown）

示例:
    python scripts/train_action_generic.py \
      --config scripts/straight_leg_raise_training.json
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.training.batch_processor import BatchConfig, BatchProcessor  # noqa: E402
from src.core.training.pipeline import VideoTrainingConfig  # noqa: E402
from src.core.training.post_train_evaluator import PostTrainEvaluator, PostTrainArtifacts  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="通用动作训练执行脚本")
    parser.add_argument(
        "--config",
        required=True,
        help="训练配置 JSON 路径（如 scripts/straight_leg_raise_training.json）",
    )
    parser.add_argument(
        "--data-dir",
        default="data",
        help="训练后拆分与评估产物目录（默认：data）",
    )
    parser.add_argument(
        "--skip-auto-eval",
        action="store_true",
        help="跳过训练后自动拆分与评估",
    )
    parser.add_argument(
        "--report-dir",
        default="docs/reports",
        help="训练报告输出目录（默认：docs/reports）",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def ensure_video_exists(videos: list[dict[str, Any]]) -> None:
    missing = [v["video_path"] for v in videos if not Path(v["video_path"]).exists()]
    if missing:
        raise FileNotFoundError(
            "以下视频不存在:\n" + "\n".join(f"- {p}" for p in missing)
        )


def build_batch_config(raw: dict[str, Any]) -> BatchConfig:
    videos = [VideoTrainingConfig(**video) for video in raw.get("videos", [])]
    return BatchConfig(
        action_id=raw["action_id"],
        action_name_zh=raw.get("action_name_zh"),
        videos=videos,
        output_dir=raw.get("output_dir", "config/action_configs"),
        fingerprint_db_path=raw.get("fingerprint_db_path", "data/fingerprints"),
        min_standard_samples=raw.get("min_standard_samples", 3),
        min_error_samples_per_type=raw.get("min_error_samples_per_type", 2),
        min_confidence_threshold=raw.get("min_confidence_threshold", 0.7),
        max_false_positive_rate=raw.get("max_false_positive_rate", 0.1),
        enable_feature_validation=raw.get("enable_feature_validation", True),
        enable_error_learning=raw.get("enable_error_learning", True),
        auto_approve=raw.get("auto_approve", False),
    )


def summarize_tags(videos: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for video in videos:
        for tag in video.get("tags", []):
            counter[tag] += 1
    return dict(sorted(counter.items(), key=lambda x: x[0]))


def write_report(
    report_dir: Path,
    config_path: Path,
    config_data: dict[str, Any],
    batch_result: dict[str, Any],
    artifacts: PostTrainArtifacts | None,
) -> Path:
    report_dir.mkdir(parents=True, exist_ok=True)
    action_id = config_data["action_id"]
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = report_dir / f"{action_id}_{stamp}_training_report.md"

    tag_summary = summarize_tags(config_data.get("videos", []))
    quality = batch_result.get("quality_report", {})

    lines = [
        f"# {action_id} 训练执行报告",
        "",
        "## 1. 输入配置",
        f"- 配置文件: `{config_path}`",
        f"- 动作ID: `{config_data.get('action_id')}`",
        f"- 动作中文名: `{config_data.get('action_name_zh', config_data.get('action_id'))}`",
        f"- 视频数量: `{len(config_data.get('videos', []))}`",
        "",
        "### 标签分布",
    ]
    lines.extend([f"- `{tag}`: {count}" for tag, count in tag_summary.items()] or ["- 无"])

    lines.extend(
        [
            "",
            "## 2. 训练结果",
            f"- 训练成功: `{batch_result.get('success', False)}`",
            f"- 处理视频数: `{batch_result.get('videos_processed', 0)}`",
            f"- 生成配置: `{batch_result.get('generated_config_path')}`",
            f"- 指纹库路径: `{batch_result.get('fingerprint_db_path')}`",
            f"- 质量置信度: `{quality.get('confidence', 0.0):.4f}`",
            f"- 覆盖错误类型数: `{quality.get('error_types_covered', 0)}`",
        ]
    )

    warnings = batch_result.get("warnings", [])
    lines.append("")
    lines.append("### 警告")
    lines.extend([f"- {w}" for w in warnings] or ["- 无"])

    lines.extend(
        [
            "",
            "## 3. 自动拆分与评估",
        ]
    )
    if artifacts:
        lines.extend(
            [
                f"- 数据集版本: `{artifacts.dataset_version}`",
                f"- 候选版本: `{artifacts.candidate_version}`",
                f"- 拆分清单: `{artifacts.split_manifest_path}`",
                f"- 评估结果: `{artifacts.evaluation_path}`",
                f"- 评估总分: `{artifacts.evaluation.overall_score:.4f}`",
            ]
        )
    else:
        lines.append("- 已跳过自动拆分与评估（--skip-auto-eval）")

    lines.extend(
        [
            "",
            "## 4. 原始结果快照",
            "```json",
            json.dumps(batch_result, ensure_ascii=False, indent=2, default=str),
            "```",
        ]
    )

    with open(report_path, "w", encoding="utf-8") as file:
        file.write("\n".join(lines))
    return report_path


def main() -> int:
    args = parse_args()
    config_path = Path(args.config).expanduser().resolve()
    if not config_path.exists():
        print(f"错误：配置文件不存在: {config_path}")
        return 1

    config_data = load_json(config_path)
    videos = config_data.get("videos", [])
    if not videos:
        print("错误：配置中 videos 为空")
        return 1

    try:
        ensure_video_exists(videos)
    except FileNotFoundError as exc:
        print(str(exc))
        return 1

    batch_config = build_batch_config(config_data)

    print("=" * 60)
    print("通用动作训练执行")
    print("=" * 60)
    print(f"动作ID: {batch_config.action_id}")
    print(f"动作名称: {batch_config.action_name_zh or batch_config.action_id}")
    print(f"视频数量: {len(batch_config.videos)}")

    processor = BatchProcessor(batch_config)
    batch_result = processor.process()

    artifacts: PostTrainArtifacts | None = None
    if batch_result.get("success") and not args.skip_auto_eval:
        evaluator = PostTrainEvaluator(data_dir=args.data_dir)
        artifacts = evaluator.evaluate_from_batch_result(batch_config, batch_result)

    report_path = write_report(
        report_dir=(PROJECT_ROOT / args.report_dir),
        config_path=config_path,
        config_data=config_data,
        batch_result=batch_result,
        artifacts=artifacts,
    )

    print("\n训练完成")
    print(f"- 训练成功: {batch_result.get('success', False)}")
    print(f"- 训练报告: {report_path}")
    print(f"- 配置产物: {batch_result.get('generated_config_path')}")
    if artifacts:
        print(f"- 拆分清单: {artifacts.split_manifest_path}")
        print(f"- 评估结果: {artifacts.evaluation_path}")

    return 0 if batch_result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
