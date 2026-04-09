"""批量视频处理器.

提供便捷的批量视频训练启动接口。
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
from pathlib import Path
import json
from datetime import datetime
from collections import defaultdict

from src.core.training.pipeline import TrainingPipeline, VideoTrainingConfig
from src.core.training.feature_validator import FeatureValidator
from src.core.training.error_learner import ErrorConditionLearner
from src.core.config.manager import ConfigManager


@dataclass
class BatchConfig:
    """批量训练配置."""
    action_id: str                                    # 动作ID
    action_name_zh: Optional[str] = None             # 中文名称

    # 视频配置列表
    videos: List[VideoTrainingConfig] = field(default_factory=list)

    # 输出配置
    output_dir: str = "config/action_configs"
    fingerprint_db_path: str = "data/fingerprints"

    # 训练参数
    min_standard_samples: int = 3                     # 最少标准样本数
    min_error_samples_per_type: int = 2              # 每种错误最少样本数

    # 质量阈值
    min_confidence_threshold: float = 0.7            # 最小置信度
    max_false_positive_rate: float = 0.1             # 最大误报率

    # 机器审核开关
    enable_feature_validation: bool = True           # 启用特征验证
    enable_error_learning: bool = True               # 启用错误学习
    auto_approve: bool = False                        # 自动批准（跳过人工审核）


class BatchProcessor:
    """批量视频处理器.

    使用示例:
        config = BatchConfig(
            action_id="jumping_jack",
            action_name_zh="开合跳",
            videos=[
                VideoTrainingConfig(
                    video_path="/path/to/std1.mp4",
                    tags=["standard"]
                ),
                VideoTrainingConfig(
                    video_path="/path/to/err1.mp4",
                    tags=["error:knee_valgus"]
                ),
            ]
        )

        processor = BatchProcessor(config)
        result = processor.process()
    """

    def __init__(self, config: BatchConfig):
        self.config = config
        self.training_pipeline = TrainingPipeline(
            fingerprint_db_path=config.fingerprint_db_path
        )
        self.feature_validator = FeatureValidator()
        self.error_learner = ErrorConditionLearner()
        self.config_manager = ConfigManager(config_dir=config.output_dir)

        # 处理结果
        self._results: List[Dict[str, Any]] = []
        self._fingerprints: Dict[str, List[Any]] = {
            "standard": [],
            "error": defaultdict(list),
        }

    def process(self) -> Dict[str, Any]:
        """执行批量处理.

        Returns:
            处理结果报告
        """
        print(f"=== 开始批量训练: {self.config.action_id} ===")
        print(f"视频总数: {len(self.config.videos)}")

        # 阶段1: 处理所有视频
        phase1_results = self._phase1_process_videos()

        # 阶段2: 特征验证（机器审核）
        if self.config.enable_feature_validation:
            phase2_results = self._phase2_validate_features(phase1_results)
        else:
            phase2_results = phase1_results

        # 阶段3: 学习错误条件
        if self.config.enable_error_learning:
            error_conditions = self._phase3_learn_errors(phase2_results)
        else:
            error_conditions = {}

        # 阶段4: 生成配置
        config_result = self._phase4_generate_config(phase2_results, error_conditions)

        # 阶段5: 验证配置质量
        quality_report = self._phase5_validate_quality(config_result)

        return {
            "action_id": self.config.action_id,
            "success": quality_report["passed"],
            "videos_processed": len(self._results),
            "fingerprint_db_path": str(self.training_pipeline.db.db_path),
            "generated_config_path": config_result.get("config_path"),
            "quality_report": quality_report,
            "warnings": quality_report.get("warnings", []),
            "requires_manual_review": not self.config.auto_approve and not quality_report["passed"],
        }

    def _phase1_process_videos(self) -> Dict[str, List[Any]]:
        """阶段1: 处理所有视频，提取指纹."""
        print("\n[阶段1] 处理视频，提取指纹...")

        results = {"standard": [], "error": defaultdict(list)}

        for i, video_config in enumerate(self.config.videos, 1):
            print(f"  处理视频 {i}/{len(self.config.videos)}: {video_config.video_path}")

            try:
                # 执行训练流程
                result = self.training_pipeline.process_video(video_config)

                if result["success"]:
                    fingerprint = result["fingerprint"]

                    # 根据标签分类
                    if "standard" in video_config.tags:
                        results["standard"].append(fingerprint)
                        self._fingerprints["standard"].append(fingerprint)

                    # 提取错误标签
                    for tag in video_config.tags:
                        if tag.startswith("error:"):
                            error_type = tag[6:]  # 去掉 "error:" 前缀
                            results["error"][error_type].append(fingerprint)
                            self._fingerprints["error"][error_type].append(fingerprint)

                    self._results.append({
                        "video_path": video_config.video_path,
                        "status": "success",
                        "fingerprint_id": fingerprint.created_at,
                    })
                else:
                    error_msg = result.get("error", "Unknown error")
                    print(f"    处理失败: {error_msg}")
                    self._results.append({
                        "video_path": video_config.video_path,
                        "status": "failed",
                        "error": error_msg,
                    })

            except Exception as e:
                print(f"    错误: {e}")
                self._results.append({
                    "video_path": video_config.video_path,
                    "status": "failed",
                    "error": str(e),
                })

        print(f"  成功处理: {len([r for r in self._results if r['status'] == 'success'])}")
        return results

    def _phase2_validate_features(self, results: Dict[str, List[Any]]) -> Dict[str, List[Any]]:
        """阶段2: 特征验证（机器审核）."""
        print("\n[阶段2] 机器审核: 验证特征质量...")

        validated_results = {"standard": [], "error": defaultdict(list)}

        # 验证标准动作指纹
        for fp in results["standard"]:
            report = self.feature_validator.validate(fp)
            if report.is_valid:
                validated_results["standard"].append(fp)
            else:
                print(f"    剔除伪特征 (标准动作): {report.issues}")

        # 验证错误动作指纹
        for error_type, fps in results["error"].items():
            for fp in fps:
                report = self.feature_validator.validate(fp)
                if report.is_valid:
                    validated_results["error"][error_type].append(fp)
                else:
                    print(f"    剔除伪特征 (错误:{error_type}): {report.issues}")

        # 检查剔除后的样本数
        removed_std = len(results["standard"]) - len(validated_results["standard"])
        print(f"  标准动作: 剔除 {removed_std} 个伪特征, 保留 {len(validated_results['standard'])}")

        return validated_results

    def _phase3_learn_errors(self, results: Dict[str, List[Any]]) -> Dict[str, List[Any]]:
        """阶段3: 学习错误判断条件."""
        print("\n[阶段3] 学习错误判断条件...")

        if not results["standard"]:
            print("  警告: 没有标准动作样本，无法学习错误条件")
            return {}

        error_conditions = {}

        for error_type, error_fps in results["error"].items():
            print(f"  学习错误类型: {error_type} (样本数: {len(error_fps)})")

            if len(error_fps) < self.config.min_error_samples_per_type:
                print(f"    跳过: 样本数不足 ({len(error_fps)} < {self.config.min_error_samples_per_type})")
                continue

            # 学习错误条件
            conditions = self.error_learner.learn_error_conditions(
                standard_fingerprints=results["standard"],
                error_fingerprints=error_fps,
                error_type=error_type,
            )

            if conditions:
                error_conditions[error_type] = conditions
                print(f"    学习到 {len(conditions)} 个判断条件")
            else:
                print(f"    未能学习到有效条件")

        return error_conditions

    def _phase4_generate_config(
        self,
        results: Dict[str, List[Any]],
        error_conditions: Dict[str, List[Any]]
    ) -> Dict[str, Any]:
        """阶段4: 生成配置文件."""
        print("\n[阶段4] 生成配置文件...")

        # 使用训练管道生成配置
        config_result = self.training_pipeline.generate_production_config(
            action_id=self.config.action_id,
            action_name_zh=self.config.action_name_zh or self.config.action_id,
            standard_fingerprints=results["standard"],
            error_conditions=error_conditions,
            output_dir=self.config.output_dir,
        )

        return config_result

    def _phase5_validate_quality(self, config_result: Dict[str, Any]) -> Dict[str, Any]:
        """阶段5: 验证配置质量."""
        print("\n[阶段5] 验证配置质量...")

        warnings = []
        passed = True

        # 检查标准样本数
        std_count = len(self._fingerprints["standard"])
        if std_count < self.config.min_standard_samples:
            warnings.append(f"标准样本数不足: {std_count} < {self.config.min_standard_samples}")
            passed = False

        # 检查是否生成了配置
        if not config_result.get("config_path"):
            warnings.append("未能生成配置文件")
            passed = False

        # 检查错误条件覆盖率
        if self._fingerprints["error"]:
            covered_errors = set(config_result.get("error_conditions", {}).keys())
            all_errors = set(self._fingerprints["error"].keys())
            uncovered = all_errors - covered_errors
            if uncovered:
                warnings.append(f"以下错误类型未学习到条件: {uncovered}")

        # 检查置信度
        if config_result.get("confidence", 0) < self.config.min_confidence_threshold:
            warnings.append(f"配置置信度过低: {config_result.get('confidence', 0):.2f}")
            passed = False

        status = "通过" if passed else "需要人工审核"
        print(f"  质量检查: {status}")
        if warnings:
            for w in warnings:
                print(f"    - {w}")

        return {
            "passed": passed,
            "warnings": warnings,
            "standard_samples": std_count,
            "error_types_covered": len(config_result.get("error_conditions", {})),
            "confidence": config_result.get("confidence", 0.0),
        }


def create_batch_config_from_json(json_path: str) -> BatchConfig:
    """从JSON文件创建批量配置.

    JSON格式:
    {
        "action_id": "jumping_jack",
        "action_name_zh": "开合跳",
        "videos": [
            {"video_path": "/path/to/std1.mp4", "tags": ["standard"]},
            {"video_path": "/path/to/err1.mp4", "tags": ["error:knee_valgus"]}
        ],
        "auto_approve": false
    }
    """
    with open(json_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    videos = [VideoTrainingConfig(**v) for v in data.get("videos", [])]

    return BatchConfig(
        action_id=data["action_id"],
        action_name_zh=data.get("action_name_zh"),
        videos=videos,
        auto_approve=data.get("auto_approve", False),
    )
