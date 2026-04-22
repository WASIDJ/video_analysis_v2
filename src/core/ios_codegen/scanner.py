"""只读扫描 iOS 项目中检测项运行时和已注册 item。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


RUNTIME_SYMBOL_PATTERNS = {
    "detection_item_strategy": r"\bprotocol\s+DetectionItemStrategy\b",
    "base_detection_item_strategy": r"\bclass\s+BaseDetectionItemStrategy\b",
    "detection_result": r"\bstruct\s+DetectionResult\b",
    "keypoints": r"\btypealias\s+Keypoints\b",
    "strategy_factory": r"\bclass\s+StrategyFactory\b",
}


@dataclass(frozen=True)
class IosProjectScan:
    """iOS 项目只读扫描结果。"""

    project_path: str
    status: str
    runtime_symbols: dict[str, bool]
    factory_item_ids: list[str]
    target_items: dict[str, str]
    strategy_classes: list[str]
    notes: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "project_path": self.project_path,
            "status": self.status,
            "runtime_symbols": self.runtime_symbols,
            "factory_item_ids": self.factory_item_ids,
            "target_items": self.target_items,
            "strategy_classes": self.strategy_classes,
            "notes": self.notes,
        }


def scan_ios_project(
    ios_project: str | Path,
    target_item_ids: list[str],
    target_strategy_classes: list[str] | None = None,
) -> IosProjectScan:
    """扫描 iOS 项目目录，不修改任何文件。"""
    project_path = Path(ios_project)
    if not project_path.exists():
        raise FileNotFoundError(f"iOS project path does not exist: {project_path}")
    if not project_path.is_dir():
        raise NotADirectoryError(f"iOS project path is not a directory: {project_path}")

    swift_files = [path for path in project_path.rglob("*.swift") if path.is_file()]
    source_by_path = {
        str(path.relative_to(project_path)): path.read_text(encoding="utf-8", errors="ignore")
        for path in swift_files
    }
    combined_source = "\n".join(source_by_path.values())

    runtime_symbols = {
        name: re.search(pattern, combined_source) is not None
        for name, pattern in RUNTIME_SYMBOL_PATTERNS.items()
    }
    can_verify_items = (
        runtime_symbols["detection_item_strategy"]
        and runtime_symbols["detection_result"]
        and runtime_symbols["keypoints"]
        and runtime_symbols["strategy_factory"]
    )

    factory_item_ids = _extract_factory_item_ids(source_by_path)
    target_items = {
        item_id: _target_status(item_id, can_verify_items, factory_item_ids)
        for item_id in target_item_ids
    }
    strategy_classes = _find_strategy_classes(combined_source, target_strategy_classes or [])

    notes: list[str] = []
    if not swift_files:
        notes.append("No Swift files found under iOS project path")
    if can_verify_items:
        notes.append("Detected iOS posture runtime and StrategyFactory")
    else:
        missing = [name for name, present in runtime_symbols.items() if not present]
        notes.append(f"Cannot verify item registration; missing runtime symbols: {', '.join(missing)}")
    if factory_item_ids:
        notes.append(f"StrategyFactory registers item IDs: {', '.join(factory_item_ids)}")

    return IosProjectScan(
        project_path=str(project_path),
        status="verified_runtime" if can_verify_items else "not_verifiable",
        runtime_symbols=runtime_symbols,
        factory_item_ids=factory_item_ids,
        target_items=target_items,
        strategy_classes=strategy_classes,
        notes=notes,
    )


def _extract_factory_item_ids(source_by_path: dict[str, str]) -> list[str]:
    factory_sources = [
        source for path, source in source_by_path.items() if path.endswith("StrategyFactory.swift")
    ]
    if not factory_sources:
        return []

    item_ids: set[str] = set()
    for source in factory_sources:
        for match in re.finditer(r'case\s+"([^"]+)"\s*:', source):
            item_ids.add(match.group(1))
    return sorted(item_ids, key=_natural_item_sort_key)


def _target_status(item_id: str, can_verify_items: bool, factory_item_ids: list[str]) -> str:
    if not can_verify_items:
        return "not_verifiable"
    if item_id in factory_item_ids:
        return "verified_present"
    return "verified_missing"


def _find_strategy_classes(source: str, target_strategy_classes: list[str]) -> list[str]:
    found: list[str] = []
    for class_name in target_strategy_classes:
        if re.search(rf"\b(class|final\s+class|open\s+class)\s+{re.escape(class_name)}\b", source):
            found.append(class_name)
    return found


def _natural_item_sort_key(value: str) -> tuple[int, int | str]:
    if value.isdigit():
        return (0, int(value))
    return (1, value)
