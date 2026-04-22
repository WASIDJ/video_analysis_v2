"""用于将 Python 指标映射到 iOS 检测项的注册表。"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path


DEFAULT_REGISTRY_PATH = Path("config/ios_codegen/metric_item_registry.json")


@dataclass(frozen=True)
class MetricItemRegistration:
    """针对一个 Python 指标的 iOS 注册元数据。"""

    metric_id: str
    item_id: str
    ios_status: str
    profile: str
    strategy: str
    schema: str
    parameter_builder: str
    generator: str | None = None


def load_registry(
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
) -> dict[str, MetricItemRegistration]:
    """Load metric-to-iOS item registry."""
    path = Path(registry_path)
    with open(path, "r", encoding="utf-8") as file:
        payload = json.load(file)

    registrations: dict[str, MetricItemRegistration] = {}
    for metric_id, item in payload.get("metrics", {}).items():
        registrations[metric_id] = MetricItemRegistration(
            metric_id=metric_id,
            item_id=str(item["item_id"]),
            ios_status=item["ios_status"],
            profile=item["profile"],
            strategy=item["strategy"],
            schema=item["schema"],
            parameter_builder=item["parameter_builder"],
            generator=item.get("generator"),
        )
    return registrations
