"""模型版本库."""

from __future__ import annotations

import json
from pathlib import Path

from .models import VersionRecord


class VersionStore:
    """管理 baseline/candidate/promoted 版本及回滚记录."""

    def __init__(self, storage_path: str | Path) -> None:
        self.storage_path = Path(storage_path)
        self._versions: dict[str, list[VersionRecord]] = {}
        self._history: dict[str, list[dict[str, str]]] = {}

        if self.storage_path.exists():
            self._load()

    def register_version(
        self,
        action_id: str,
        version_id: str,
        dataset_version: str,
        config_version: str,
        metrics: dict[str, float],
        status: str,
        parent_version: str | None = None,
    ) -> VersionRecord:
        """注册新版本."""
        action_versions = self._versions.setdefault(action_id, [])
        is_first_version = len(action_versions) == 0
        record = VersionRecord(
            action_id=action_id,
            version_id=version_id,
            dataset_version=dataset_version,
            config_version=config_version,
            metrics=metrics,
            status=status,
            is_active=is_first_version and status == "baseline",
            parent_version=parent_version,
        )
        action_versions.append(record)
        self._append_history(action_id, "register", version_id)
        self._save()
        return record

    def promote_candidate(self, action_id: str, version_id: str) -> VersionRecord:
        """提升 candidate 为 active 版本."""
        target = self.get_version(action_id, version_id)
        if target is None:
            raise KeyError(f"version not found: {version_id}")

        for record in self._versions.get(action_id, []):
            record.is_active = False
            if record.version_id == version_id:
                record.status = "promoted"

        target.is_active = True
        self._append_history(action_id, "promote", version_id)
        self._save()
        return target

    def rollback_to(self, action_id: str, version_id: str) -> VersionRecord:
        """回滚到指定版本."""
        target = self.get_version(action_id, version_id)
        if target is None:
            raise KeyError(f"version not found: {version_id}")

        for record in self._versions.get(action_id, []):
            record.is_active = False
        target.is_active = True
        target.status = "baseline"
        self._append_history(action_id, "rollback", version_id)
        self._save()
        return target

    def get_active_version(self, action_id: str) -> VersionRecord | None:
        """获取当前激活版本."""
        for record in self._versions.get(action_id, []):
            if record.is_active:
                return record
        return None

    def get_version(self, action_id: str, version_id: str) -> VersionRecord | None:
        """获取指定版本."""
        for record in self._versions.get(action_id, []):
            if record.version_id == version_id:
                return record
        return None

    def list_history(self, action_id: str) -> list[dict[str, str]]:
        """获取操作历史."""
        return list(self._history.get(action_id, []))

    def _append_history(self, action_id: str, event: str, version_id: str) -> None:
        self._history.setdefault(action_id, []).append(
            {"event": event, "version_id": version_id}
        )

    def _save(self) -> None:
        payload = {
            "versions": {
                action_id: [record.to_dict() for record in records]
                for action_id, records in self._versions.items()
            },
            "history": self._history,
        }
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.storage_path, "w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2, ensure_ascii=False)

    def _load(self) -> None:
        with open(self.storage_path, "r", encoding="utf-8") as file:
            payload = json.load(file)

        self._versions = {
            action_id: [VersionRecord.from_dict(record) for record in records]
            for action_id, records in payload.get("versions", {}).items()
        }
        self._history = {
            action_id: list(history)
            for action_id, history in payload.get("history", {}).items()
        }
