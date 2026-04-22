"""Dry-run iOS 检测项代码生成服务。"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .parameter_builder import build_parameter_row
from .registry import DEFAULT_REGISTRY_PATH, MetricItemRegistration, load_registry
from .scanner import scan_ios_project
from .swift_templates import render_strategy
from .validator import validate_generated_swift, validate_parameter_rows


@dataclass(frozen=True)
class IosCodegenResult:
    """总结iOS 代码生成干运行结果的不可变数据类."""

    success: bool
    output_dir: Path
    payload_path: Path
    plan_path: Path
    validation_path: Path
    detect_item_ids: list[str]
    generated_strategies: list[str]
    warnings: list[str]
    errors: list[str]
    ios_project_scan: dict[str, Any] | None = None


def run_ios_codegen(
    action_id: str,
    action_config_path: str | Path,
    output_dir: str | Path,
    evaluation_path: str | Path | None = None,
    ios_project: str | Path | None = None,
    write: bool = False,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
) -> IosCodegenResult:
    """执行 iOS 检测项代码生成 dry-run，返回结果对象。"""
    del evaluation_path
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    generated_dir = output / "generated"
    patches_dir = output / "patches"
    generated_dir.mkdir(exist_ok=True)
    patches_dir.mkdir(exist_ok=True)

    if write:
        raise NotImplementedError("iOS project writes are intentionally disabled in first version")

    action_config = _load_action_config(action_config_path)
    registry = load_registry(registry_path)

    detect_item_ids: list[str] = []
    parameter_rows: list[list[float]] = []
    plan_items: list[dict[str, Any]] = []
    generated_strategies: list[str] = []
    warnings: list[str] = []
    errors: list[dict[str, str]] = []

    metrics = [metric for metric in action_config.get("metrics", []) if metric.get("enabled", True)]
    for metric in metrics:
        metric_id = metric["metric_id"]
        registration = registry.get(metric_id)
        if registration is None:
            errors.append(
                {
                    "code": "REGISTRY_MISSING_METRIC",
                    "message": f"Missing iOS registry mapping for metric: {metric_id}",
                }
            )
            continue

        parameter_row = build_parameter_row(registration.parameter_builder, metric, action_config)
        detect_item_ids.append(registration.item_id)
        parameter_rows.append(parameter_row)

        item = _plan_item(metric_id, registration, parameter_row)
        plan_items.append(item)

        if registration.ios_status == "generate":
            source = render_strategy(registration)
            (generated_dir / f"{registration.strategy}.swift").write_text(source, encoding="utf-8")
            generated_strategies.append(registration.strategy)

    ios_project_scan: dict[str, Any] | None = None
    if ios_project:
        try:
            scan = scan_ios_project(
                ios_project,
                target_item_ids=detect_item_ids,
                target_strategy_classes=[item["strategy"] for item in plan_items],
            )
            ios_project_scan = scan.to_dict()
            _attach_scan_status(plan_items, scan.target_items)
            if scan.status != "verified_runtime":
                warnings.append("iOS project scan could not verify posture runtime; review scan notes")
        except (FileNotFoundError, NotADirectoryError) as exc:
            errors.append(
                {
                    "code": "IOS_PROJECT_SCAN_FAILED",
                    "message": str(exc),
                }
            )

    _write_patches(patches_dir, [item for item in plan_items if item["ios_status"] == "generate"])

    parameter_errors = validate_parameter_rows(parameter_rows)
    swift_errors = validate_generated_swift(generated_dir)
    errors.extend(parameter_errors)
    errors.extend(swift_errors)

    if any(item["metric_id"] == "knee_symmetry" for item in plan_items):
        warnings.append("knee_symmetry unit requires review: Python unit is normalized but calculator uses y difference")

    payload_path = output / "ios_payload.json"
    plan_path = output / "codegen_plan.json"
    validation_path = output / "validation_result.json"

    _write_json(
        payload_path,
        {
            "action_id": action_id,
            "detectItemIDs": detect_item_ids,
            "detectItemParameters": [parameter_rows],
        },
    )
    _write_json(
        plan_path,
        {
            "action_id": action_id,
            "items": plan_items,
            "generated_strategies": generated_strategies,
            "ios_project_scan": ios_project_scan,
        },
    )
    _write_json(
        validation_path,
        {
            "action_id": action_id,
            "success": not errors,
            "warnings": warnings,
            "errors": errors,
            "ios_project_scan": ios_project_scan,
        },
    )
    _write_summary(
        output / "summary.md",
        action_id,
        plan_items,
        generated_strategies,
        warnings,
        errors,
        ios_project_scan,
    )

    return IosCodegenResult(
        success=not errors,
        output_dir=output,
        payload_path=payload_path,
        plan_path=plan_path,
        validation_path=validation_path,
        detect_item_ids=detect_item_ids,
        generated_strategies=generated_strategies,
        warnings=warnings,
        errors=[error["message"] for error in errors],
        ios_project_scan=ios_project_scan,
    )


def _load_action_config(path: str | Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def _plan_item(
    metric_id: str,
    registration: MetricItemRegistration,
    parameter_row: list[float],
) -> dict[str, Any]:
    return {
        "metric_id": metric_id,
        "item_id": registration.item_id,
        "ios_status": registration.ios_status,
        "profile": registration.profile,
        "strategy": registration.strategy,
        "schema": registration.schema,
        "parameter_builder": registration.parameter_builder,
        "generator": registration.generator,
        "parameters": parameter_row,
    }


def _attach_scan_status(plan_items: list[dict[str, Any]], target_items: dict[str, str]) -> None:
    for item in plan_items:
        item["ios_project_status"] = target_items.get(item["item_id"], "not_scanned")


def _write_patches(patches_dir: Path, generated_items: list[dict[str, Any]]) -> None:
    profile_lines = [f'{item["item_id"]} -> {item["profile"]}' for item in generated_items]
    strategy_lines: list[str] = []
    for item in generated_items:
        strategy_lines.extend(
            [
                f'case "{item["item_id"]}":',
                f'    return {item["strategy"]}(itemID: itemID, parameters: parameters)',
            ]
        )
    schema_lines = [f'{item["item_id"]} -> {item["schema"]}' for item in generated_items]

    (patches_dir / "profile_registry.patch.txt").write_text(
        "\n".join(profile_lines) + ("\n" if profile_lines else ""),
        encoding="utf-8",
    )
    (patches_dir / "strategy_factory.patch.txt").write_text(
        "\n".join(strategy_lines) + ("\n" if strategy_lines else ""),
        encoding="utf-8",
    )
    (patches_dir / "parameter_schema.patch.txt").write_text(
        "\n".join(schema_lines) + ("\n" if schema_lines else ""),
        encoding="utf-8",
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_summary(
    path: Path,
    action_id: str,
    plan_items: list[dict[str, Any]],
    generated_strategies: list[str],
    warnings: list[str],
    errors: list[dict[str, str]],
    ios_project_scan: dict[str, Any] | None = None,
) -> None:
    lines = [
        f"# {action_id} iOS codegen dry-run",
        "",
        "## Items",
    ]
    for item in plan_items:
        lines.append(
            f"- `{item['metric_id']}` -> item `{item['item_id']}` ({item['ios_status']})"
        )
    lines.extend(["", "## Generated Swift"])
    lines.extend([f"- `{strategy}.swift`" for strategy in generated_strategies] or ["- None"])
    lines.extend(["", "## iOS Project Scan"])
    if ios_project_scan:
        lines.append(f"- Status: `{ios_project_scan['status']}`")
        target_items = ios_project_scan.get("target_items", {})
        if isinstance(target_items, dict):
            for item_id, status in target_items.items():
                lines.append(f"- item `{item_id}`: `{status}`")
        notes = ios_project_scan.get("notes", [])
        if isinstance(notes, list):
            lines.extend([f"- {note}" for note in notes])
    else:
        lines.append("- Not requested")
    lines.extend(["", "## Warnings"])
    lines.extend([f"- {warning}" for warning in warnings] or ["- None"])
    lines.extend(["", "## Errors"])
    lines.extend([f"- {error['message']}" for error in errors] or ["- None"])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
