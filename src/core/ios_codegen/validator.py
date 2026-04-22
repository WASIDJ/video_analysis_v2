"用于 iOS 代码生成干运行产物的验证助手。"

from __future__ import annotations

from pathlib import Path


def validate_parameter_rows(rows: list[list[float]]) -> list[dict[str, str]]:
    """返回 iOS 参数行的验证错误。"""
    errors: list[dict[str, str]] = []
    for index, row in enumerate(rows):
        if len(row) != 8:
            errors.append(
                {
                    "code": "PARAMETER_LENGTH_MISMATCH",
                    "message": f"parameter row {index} has length {len(row)}, expected 8",
                }
            )
    return errors


def validate_generated_swift(generated_dir: Path) -> list[dict[str, str]]:
    """返回生成的Swift源代码的验证错误。"""
    errors: list[dict[str, str]] = []
    for path in generated_dir.glob("*.swift"):
        source = path.read_text(encoding="utf-8")
        has_explicit_update_parameters = "func updateParameters" in source
        inherits_base_with_update_parameters = "BaseStaticStrategy" in source or "BaseDetectionItemStrategy" in source
        if not has_explicit_update_parameters and not inherits_base_with_update_parameters:
            errors.append(
                {
                    "code": "MISSING_UPDATE_PARAMETERS",
                    "message": f"{path.name} does not define updateParameters and does not inherit a base class that provides it",
                }
            )
        for forbidden_literal in ("64.57", "90.17", "0.12", "0.22"):
            if forbidden_literal in source:
                errors.append(
                    {
                        "code": "HARDCODED_TRAINED_THRESHOLD",
                        "message": f"{path.name} embeds trained threshold {forbidden_literal}",
                    }
                )
    return errors
