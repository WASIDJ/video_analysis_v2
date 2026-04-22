"""iOS检测项代码生成测试。"""

import json
from pathlib import Path

from src.core.ios_codegen import run_ios_codegen


def test_generates_ios_payload_and_missing_swift_strategies(tmp_path):
    """直腿抬高代码生成应重用8/7并生成22/23。"""
    result = run_ios_codegen(
        action_id="straight_leg_raise",
        action_config_path="config/action_configs/straight_leg_raise_trained.json",
        output_dir=tmp_path,
    )

    assert result.success is True
    assert result.detect_item_ids == ["8", "7", "22", "23"]
    assert result.generated_strategies == [
        "HipAbductionMP33Strategy",
        "KneeSymmetryMP33Strategy",
    ]

    payload = json.loads((tmp_path / "ios_payload.json").read_text(encoding="utf-8"))
    assert payload["detectItemIDs"] == ["8", "7", "22", "23"]
    assert len(payload["detectItemParameters"][0]) == 4
    assert payload["detectItemParameters"][0][2] == [
        64.57,
        70.97,
        83.77,
        90.17,
        64.57,
        70.97,
        83.77,
        90.17,
    ]

    hip_strategy = tmp_path / "generated" / "HipAbductionMP33Strategy.swift"
    knee_strategy = tmp_path / "generated" / "KneeSymmetryMP33Strategy.swift"
    assert hip_strategy.exists()
    assert knee_strategy.exists()

    hip_source = hip_strategy.read_text(encoding="utf-8")
    knee_source = knee_strategy.read_text(encoding="utf-8")

    # 修正后继承 BaseStaticStrategy，不再继承 BaseDetectionItemStrategy
    assert "BaseStaticStrategy" in hip_source
    assert "BaseStaticStrategy" in knee_source
    assert "BaseDetectionItemStrategy" not in hip_source
    assert "BaseDetectionItemStrategy" not in knee_source

    # 修正后使用 evaluateStaticWithHold，不再有自定义 evaluateRange
    assert "evaluateStaticWithHold" in hip_source
    assert "evaluateStaticWithHold" in knee_source
    assert "evaluateRange" not in hip_source
    assert "evaluateRange" not in knee_source

    # 修正后使用 hold-duration 机制，不再有 isCompleted: score > 0.0
    assert "isCompleted: score > 0.0" not in hip_source
    assert "isCompleted: score > 0.0" not in knee_source
    assert "isCompleted: isCompleted" in hip_source
    assert "isCompleted: isCompleted" in knee_source

    # 修正后 raiseCount 固定为 0（静态项不计数）
    assert "raiseCount: 0" in hip_source
    assert "raiseCount: 0" in knee_source

    # 修正后不再有 parameters.count >= 8 的 guard（用安全访问 parameters.count > N）
    assert "parameters.count >= 8" not in hip_source
    assert "parameters.count >= 8" not in knee_source

    # init 签名应接受 itemID 参数（与真实 iOS 策略工厂一致）
    assert "itemID: String" in hip_source
    assert "itemID: String" in knee_source

    # 保持 Keypoints 类型
    assert "Keypoints" in hip_source
    assert "Keypoints" in knee_source

    # 不应有旧模板的残留
    assert "KeypointViews" not in hip_source
    assert "ScoreRange" not in hip_source
    assert "keypoints[" in hip_source

    factory_patch = (tmp_path / "patches" / "strategy_factory.patch.txt").read_text(
        encoding="utf-8"
    )
    assert 'case "22":' in factory_patch
    assert "return HipAbductionMP33Strategy(itemID: itemID, parameters: parameters)" in factory_patch

    # knee_symmetry 单位警告仍应存在
    assert "knee_symmetry unit requires review" in result.warnings[0] or any(
        "knee_symmetry" in w for w in result.warnings
    )


def test_blocks_unknown_metric_without_guessing_mapping(tmp_path):
    """未知的指标应阻止代码生成，而不是让生成器猜测。"""
    action_config = {
        "action_id": "unknown_action",
        "metrics": [
            {
                "metric_id": "unknown_metric",
                "enabled": True,
                "thresholds": {
                    "normal_range": [1.0, 2.0],
                    "excellent_range": [1.2, 1.8],
                    "target_value": 1.5,
                },
            }
        ],
    }
    config_path = tmp_path / "unknown_action_trained.json"
    config_path.write_text(json.dumps(action_config), encoding="utf-8")

    result = run_ios_codegen(
        action_id="unknown_action",
        action_config_path=config_path,
        output_dir=tmp_path / "out",
    )

    assert result.success is False
    validation = json.loads((tmp_path / "out" / "validation_result.json").read_text())
    assert validation["errors"][0]["code"] == "REGISTRY_MISSING_METRIC"


def test_generated_swift_does_not_embed_trained_threshold_literals(tmp_path):
    """生成的Swift代码应通过updateParameters接收阈值，而不是将其硬编码。"""
    run_ios_codegen(
        action_id="straight_leg_raise",
        action_config_path="config/action_configs/straight_leg_raise_trained.json",
        output_dir=tmp_path,
    )

    generated_source = (tmp_path / "generated" / "HipAbductionMP33Strategy.swift").read_text(
        encoding="utf-8"
    )

    assert "64.57" not in generated_source
    assert "90.17" not in generated_source
    # 修正后不再硬编码 updateParameters，因为 BaseStaticStrategy 已有默认实现
    # 但仍可通过 updateParameters 更新参数


def test_ios_project_scan_marks_existing_and_missing_items(tmp_path):
    """传入真实形态的iOS runtime时，应标记已注册和缺失检测项。"""
    ios_project = tmp_path / "Knieo"
    strategy_dir = ios_project / "Sources" / "Vision" / "PostureAnalysis" / "Domain" / "Strategy"
    strategy_dir.mkdir(parents=True)
    (strategy_dir / "DetectionItemStrategy.swift").write_text(
        """
        public protocol DetectionItemStrategy {}
        public class BaseDetectionItemStrategy: DetectionItemStrategy {}
        public class BaseStaticStrategy: BaseDetectionItemStrategy {}
        public typealias Keypoints = [String: [Float]]
        public struct DetectionResult {}
        """,
        encoding="utf-8",
    )
    (strategy_dir / "StrategyFactory.swift").write_text(
        """
        public final class StrategyFactory {
            public static func createStrategy(for itemID: String) -> DetectionItemStrategy? {
                switch itemID {
                case "7":
                    return nil
                case "8":
                    return nil
                default:
                    return nil
                }
            }
        }
        """,
        encoding="utf-8",
    )

    result = run_ios_codegen(
        action_id="straight_leg_raise",
        action_config_path="config/action_configs/straight_leg_raise_trained.json",
        output_dir=tmp_path / "out",
        ios_project=ios_project,
    )

    assert result.success is True
    assert result.ios_project_scan is not None
    assert result.ios_project_scan["status"] == "verified_runtime"
    assert result.ios_project_scan["target_items"] == {
        "8": "verified_present",
        "7": "verified_present",
        "22": "verified_missing",
        "23": "verified_missing",
    }

    plan = json.loads((tmp_path / "out" / "codegen_plan.json").read_text(encoding="utf-8"))
    statuses = {item["item_id"]: item["ios_project_status"] for item in plan["items"]}
    assert statuses["8"] == "verified_present"
    assert statuses["22"] == "verified_missing"


def test_ios_project_scan_reports_unverifiable_runtime(tmp_path):
    """没有检测运行时的iOS项目不能被误判为未实现。"""
    ios_project = tmp_path / "Knieo"
    ios_project.mkdir()
    (ios_project / "SomeView.swift").write_text("struct SomeView {}", encoding="utf-8")

    result = run_ios_codegen(
        action_id="straight_leg_raise",
        action_config_path="config/action_configs/straight_leg_raise_trained.json",
        output_dir=tmp_path / "out",
        ios_project=ios_project,
    )

    assert result.success is True
    assert result.ios_project_scan is not None
    assert result.ios_project_scan["status"] == "not_verifiable"
    assert set(result.ios_project_scan["target_items"].values()) == {"not_verifiable"}
    assert result.warnings == [
        "iOS project scan could not verify posture runtime; review scan notes",
        "knee_symmetry unit requires review: Python unit is normalized but calculator uses y difference",
    ]


def test_ios_project_scan_missing_path_fails_codegen(tmp_path):
    """不存在的iOS项目路径应让codegen失败，而不是静默跳过。"""
    result = run_ios_codegen(
        action_id="straight_leg_raise",
        action_config_path="config/action_configs/straight_leg_raise_trained.json",
        output_dir=tmp_path,
        ios_project=tmp_path / "missing-ios-project",
    )

    assert result.success is False
    assert "iOS project path does not exist" in result.errors[0]


def test_generated_static_strategies_use_hold_duration_pattern(tmp_path):
    """生成的静态策略应使用 evaluateStaticWithHold（保持计时模式），而不是 isCompleted: score > 0.0。"""
    run_ios_codegen(
        action_id="straight_leg_raise",
        action_config_path="config/action_configs/straight_leg_raise_trained.json",
        output_dir=tmp_path,
    )

    for strategy_name in ("HipAbductionMP33Strategy", "KneeSymmetryMP33Strategy"):
        source = (tmp_path / "generated" / f"{strategy_name}.swift").read_text(
            encoding="utf-8"
        )

        # 继承 BaseStaticStrategy，而非 BaseDetectionItemStrategy
        assert "BaseStaticStrategy" in source, f"{strategy_name} should inherit BaseStaticStrategy"
        assert "BaseDetectionItemStrategy" not in source

        # 使用 evaluateStaticWithHold 而非自定义 evaluateRange
        assert "evaluateStaticWithHold" in source, f"{strategy_name} should use evaluateStaticWithHold"
        assert "evaluateRange" not in source, f"{strategy_name} should not have custom evaluateRange"

        # isCompleted 由 evaluateStaticWithHold 返回值决定，而非 score > 0.0
        assert "isCompleted: isCompleted" in source, f"{strategy_name} should use isCompleted from evaluateStaticWithHold"
        assert "isCompleted: score > 0.0" not in source, f"{strategy_name} should not use isCompleted: score > 0.0"

        # 静态项 raiseCount 固定为 0
        assert "raiseCount: 0" in source, f"{strategy_name} should have raiseCount: 0"

        # init 签名接受 itemID 参数（与真实 iOS 工厂模式一致）
        assert "itemID: String" in source, f"{strategy_name} init should accept itemID parameter"

        # score 是 1.0 或 0.0 二值（由 evaluateStaticWithHold 返回）
        # 不应有三档评分 0.5
        assert "0.5" not in source, f"{strategy_name} should not have 0.5 score tier"

        # timestamp 参数被正确传入 evaluateStaticWithHold
        assert "timestamp: timestamp" in source, f"{strategy_name} should pass timestamp to evaluateStaticWithHold"


def test_factory_patch_passes_item_id(tmp_path):
    """Strategy factory patch 应传入 itemID 参数（与真实 iOS 一致）。"""
    result = run_ios_codegen(
        action_id="straight_leg_raise",
        action_config_path="config/action_configs/straight_leg_raise_trained.json",
        output_dir=tmp_path,
    )

    factory_patch = (tmp_path / "patches" / "strategy_factory.patch.txt").read_text(
        encoding="utf-8"
    )

    # 修正后传入 itemID（与真实 iOS StrategyFactory 中的静态策略一致）
    assert "HipAbductionMP33Strategy(itemID: itemID, parameters: parameters)" in factory_patch
    assert "KneeSymmetryMP33Strategy(itemID: itemID, parameters: parameters)" in factory_patch