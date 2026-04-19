"""侧抬腿动作训练脚本 V2.

使用 side_lift_training.json 进行训练，验证阶段边界学习和检测项筛选.
"""
import json
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.core.training.pipeline import (
    TrainingPipeline,
    VideoTrainingConfig,
)
from src.core.config.models import ErrorCondition
from src.core.phases.boundary_learner import PhaseBoundaryLearner
from src.core.metrics.selector import MetricSelector


def load_training_config(config_path: str) -> dict:
    """加载训练配置."""
    with open(config_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def main():
    """主函数."""
    print("=" * 60)
    print("侧抬腿动作训练 V2")
    print("=" * 60)

    # 加载训练配置
    config_path = Path(__file__).parent / "side_lift_training.json"
    training_config = load_training_config(str(config_path))

    action_id = training_config["action_id"]
    action_name_zh = training_config["action_name_zh"]
    videos = training_config["videos"]

    print(f"\n动作ID: {action_id}")
    print(f"动作名称: {action_name_zh}")
    print(f"训练视频数: {len(videos)}")

    # 初始化训练管道
    print("\n初始化训练管道...")
    pipeline = TrainingPipeline(
        fingerprint_db_path=f"data/fingerprints/{action_id}",
        max_metrics=6,  # 限制检测项数量
    )

    # 处理每个视频
    print("\n处理训练视频...")
    standard_fingerprints = []
    error_samples = {}

    for i, video_info in enumerate(videos):
        print(f"\n  [{i+1}/{len(videos)}] {video_info['video_path']}")
        print(f"      Tags: {video_info['tags']}")
        print(f"      Ground Truth Reps: {video_info.get('ground_truth_reps', 'N/A')}")

        config = VideoTrainingConfig(
            video_path=video_info["video_path"],
            tags=video_info["tags"],
            ground_truth_reps=video_info.get("ground_truth_reps"),
            metadata={"action_id": action_id},
        )

        result = pipeline.process_video(config)

        if result["success"]:
            print(f"      ✓ 处理成功")
            print(f"        检测项数: {result['metrics_analyzed']}")
            print(f"        主导指标: {result['dominant_metrics'][:3]}")

            if result.get("phase_learning"):
                pl = result["phase_learning"]
                print(f"        阶段学习: key_metric={pl.key_metric}, "
                      f"cycles={pl.cycle_count}, confidence={pl.confidence:.2f}")

            if result.get("rep_count_eval"):
                rce = result["rep_count_eval"]
                print(f"        计数评估: MAE={rce['mae']:.1f}, "
                      f"Acc@0={rce['acc_at_0']:.0%}, Acc@1={rce['acc_at_1']:.0%}")

            # 分类存储指纹
            if "standard" in video_info["tags"]:
                standard_fingerprints.append(result["fingerprint"])
            elif any(t.startswith("error:") for t in video_info["tags"]):
                for tag in video_info["tags"]:
                    if tag.startswith("error:"):
                        if tag not in error_samples:
                            error_samples[tag] = []
                        error_samples[tag].append(result["fingerprint"])
        else:
            print(f"      ✗ 处理失败: {result.get('error', 'Unknown error')}")

    print(f"\n{'=' * 60}")
    print("生成生产配置...")
    print(f"{'=' * 60}")

    # 生成错误条件（简化示例）
    error_conditions = {}
    for error_type, samples in error_samples.items():
        # 这里应该调用错误学习器
        # 简化处理：创建一个示例错误条件
        error_conditions[error_type] = [
            ErrorCondition(
                error_id=f"{error_type.replace(':', '_')}_detected",
                error_name=f"{error_type}检测",
                description=f"检测到{error_type}错误",
                severity="medium",
                condition={"metric_id": "hip_abduction", "operator": "lt", "value": 30},
            )
        ]

    # 生成生产配置
    result = pipeline.generate_production_config(
        action_id=action_id,
        action_name_zh=action_name_zh,
        standard_fingerprints=standard_fingerprints,
        error_conditions=error_conditions,
        output_dir="config/action_configs",
        dataset_version="v1.0",
    )

    if result["success"]:
        print("\n✓ 配置生成成功!")
        print(f"  配置路径: {result['config_path']}")
        print(f"  候选版本: {result['candidate_version']}")
        print(f"  置信度: {result['confidence']:.2%}")

        print("\n  检测项筛选结果:")
        selection_info = result.get("metric_selection", {})
        print(f"    候选指标数: {selection_info.get('total_candidates', 0)}")
        print(f"    核心指标数: {selection_info.get('final_core', 0)}")
        print(f"    辅助指标数: {selection_info.get('final_aux', 0)}")

        print("\n  阶段学习结果:")
        phase_info = result.get("phase_learning", {})
        print(f"    关键指标: {phase_info.get('key_metric', 'N/A')}")
        print(f"    检测周期数: {phase_info.get('cycle_count', 0)}")
        print(f"    置信度: {phase_info.get('confidence', 0):.2%}")

        print("\n  计数评估指标:")
        rc_metrics = result.get("rep_count_metrics", {})
        print(f"    MAE: {rc_metrics.get('mae', 0):.2f}")
        print(f"    Acc@0: {rc_metrics.get('acc_at_0', 0):.0%}")
        print(f"    Acc@1: {rc_metrics.get('acc_at_1', 0):.0%}")

        print("\n  产物文件:")
        artifacts = result.get("artifacts", {})
        for name, path in artifacts.items():
            print(f"    {name}: {path}")
    else:
        print(f"\n✗ 配置生成失败: {result.get('error', 'Unknown error')}")
        if "traceback" in result:
            print(f"\n详细错误:\n{result['traceback']}")

    print("\n" + "=" * 60)
    print("训练完成")
    print("=" * 60)

    return result


if __name__ == "__main__":
    main()
