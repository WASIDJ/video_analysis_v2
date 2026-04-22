"""train_action iOS 代码生成集成测试。"""

from pathlib import Path
from types import SimpleNamespace


def test_parser_accepts_ios_codegen_flags():
    """train_action 应该公开可选的 iOS 代码生成预运行标志。"""
    parser = _load_train_action().create_parser()

    args = parser.parse_args(
        [
            "--config",
            "scripts/straight_leg_raise_training.json",
            "--ios-codegen",
            "--ios-codegen-output",
            "data/ios_codegen/straight_leg_raise",
            "--ios-project",
            "/tmp/ios",
        ]
    )

    assert args.ios_codegen is True
    assert args.ios_codegen_output == "data/ios_codegen/straight_leg_raise"
    assert args.ios_project == "/tmp/ios"
    assert args.ios_codegen_write is False


def test_print_result_includes_ios_codegen_summary(capsys, tmp_path):
    """train_action 结果输出应包括 iOS 代码生成干运行工件。"""
    train_action = _load_train_action()
    payload_path = tmp_path / "ios_payload.json"
    payload_path.write_text("{}", encoding="utf-8")

    codegen_result = SimpleNamespace(
        success=True,
        output_dir=Path(tmp_path),
        payload_path=payload_path,
        generated_strategies=["HipAbductionMP33Strategy", "KneeSymmetryMP33Strategy"],
        warnings=["knee_symmetry unit requires review"],
        errors=[],
    )

    train_action.print_result(
        {
            "success": True,
            "action_id": "straight_leg_raise",
            "generated_config_path": "config/action_configs/straight_leg_raise_trained.json",
            "fingerprint_db_path": "data/fingerprints",
            "videos_processed": 14,
            "quality_report": {"confidence": 0.91},
        },
        ios_codegen_result=codegen_result,
    )

    output = capsys.readouterr().out
    assert "iOS Codegen" in output
    assert "HipAbductionMP33Strategy" in output
    assert "knee_symmetry unit requires review" in output


def _load_train_action():
    """导入 train_action。"""
    import train_action

    return train_action
