"""参数记录器.

提供执行参数的记录、历史管理和回溯功能.
"""
import json
import os
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

from .models import ExecutionRecord, ActionConfig
from .manager import ConfigManager


class ParameterRecorder:
    """参数记录器.

    记录每次执行的参数配置，支持历史版本管理和对比.
    """

    # 默认记录目录
    DEFAULT_RECORDS_DIR = Path(__file__).parent / "records"

    def __init__(
        self,
        records_dir: Optional[Union[str, Path]] = None,
        max_records_per_action: int = 100,
    ):
        """
        Args:
            records_dir: 记录存储目录
            max_records_per_action: 每个动作保留的最大记录数
        """
        self.records_dir = Path(records_dir) if records_dir else self.DEFAULT_RECORDS_DIR
        self.records_dir.mkdir(parents=True, exist_ok=True)
        self.max_records_per_action = max_records_per_action

    def record_execution(
        self,
        action_id: str,
        action_version: str,
        algorithm_version: str,
        video_path: str,
        params_used: Dict[str, Any],
        results_summary: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """记录一次执行.

        Args:
            action_id: 动作ID
            action_version: 动作配置版本
            algorithm_version: 算法版本
            video_path: 视频路径
            params_used: 使用的参数
            results_summary: 结果摘要
            metadata: 元数据

        Returns:
            记录ID
        """
        record_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().isoformat()

        record = ExecutionRecord(
            record_id=record_id,
            timestamp=timestamp,
            action_id=action_id,
            action_version=action_version,
            algorithm_version=algorithm_version,
            video_path=video_path,
            params_used=params_used,
            results_summary=results_summary or {},
            metadata=metadata or {},
        )

        # 保存记录
        action_records_dir = self.records_dir / action_id
        action_records_dir.mkdir(exist_ok=True)

        record_file = action_records_dir / f"{record_id}_{timestamp[:10]}.json"

        with open(record_file, "w", encoding="utf-8") as f:
            json.dump(record.to_dict(), f, indent=2, ensure_ascii=False)

        # 清理旧记录
        self._cleanup_old_records(action_id)

        return record_id

    def get_records(
        self,
        action_id: str,
        limit: int = 10,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
    ) -> List[ExecutionRecord]:
        """获取执行记录.

        Args:
            action_id: 动作ID
            limit: 返回的最大记录数
            start_date: 开始日期（ISO格式）
            end_date: 结束日期（ISO格式）

        Returns:
            记录列表
        """
        action_records_dir = self.records_dir / action_id
        if not action_records_dir.exists():
            return []

        records = []

        for record_file in sorted(action_records_dir.glob("*.json"), reverse=True):
            try:
                with open(record_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                record = ExecutionRecord.from_dict(data)

                # 日期过滤
                if start_date and record.timestamp < start_date:
                    continue
                if end_date and record.timestamp > end_date:
                    continue

                records.append(record)

                if len(records) >= limit:
                    break

            except Exception:
                continue

        return records

    def get_record(self, action_id: str, record_id: str) -> Optional[ExecutionRecord]:
        """获取指定记录.

        Args:
            action_id: 动作ID
            record_id: 记录ID

        Returns:
            记录或None
        """
        action_records_dir = self.records_dir / action_id
        if not action_records_dir.exists():
            return None

        for record_file in action_records_dir.glob(f"{record_id}_*.json"):
            try:
                with open(record_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return ExecutionRecord.from_dict(data)
            except Exception:
                continue

        return None

    def compare_records(
        self,
        action_id: str,
        record_id1: str,
        record_id2: str,
    ) -> Optional[Dict[str, Any]]:
        """对比两个记录的参数差异.

        Args:
            action_id: 动作ID
            record_id1: 第一个记录ID
            record_id2: 第二个记录ID

        Returns:
            差异信息或None
        """
        record1 = self.get_record(action_id, record_id1)
        record2 = self.get_record(action_id, record_id2)

        if not record1 or not record2:
            return None

        diff = {
            "record1": {
                "id": record1.record_id,
                "timestamp": record1.timestamp,
                "version": record1.action_version,
            },
            "record2": {
                "id": record2.record_id,
                "timestamp": record2.timestamp,
                "version": record2.action_version,
            },
            "params_diff": self._compute_params_diff(
                record1.params_used, record2.params_used
            ),
        }

        return diff

    def export_config_from_record(
        self,
        action_id: str,
        record_id: str,
        config_manager: ConfigManager,
    ) -> bool:
        """从历史记录导出配置.

        Args:
            action_id: 动作ID
            record_id: 记录ID
            config_manager: 配置管理器

        Returns:
            是否成功
        """
        record = self.get_record(action_id, record_id)
        if not record:
            return False

        try:
            # 从params_used重建配置
            params = record.params_used

            # 加载当前配置作为基础
            current_config = config_manager.load_config(action_id)
            if not current_config:
                return False

            # 更新参数
            if "metrics" in params:
                for metric_config in current_config.metrics:
                    metric_id = metric_config.metric_id
                    if metric_id in params["metrics"]:
                        metric_data = params["metrics"][metric_id]
                        # 应用参数更新...

            # 更新版本号
            current_config.version = record.action_version

            # 保存为新的配置版本
            return config_manager.save_config(current_config)

        except Exception as e:
            print(f"导出配置失败: {e}")
            return False

    def get_statistics(self, action_id: str) -> Dict[str, Any]:
        """获取执行统计信息.

        Args:
            action_id: 动作ID

        Returns:
            统计信息
        """
        records = self.get_records(action_id, limit=1000)

        if not records:
            return {"total_executions": 0}

        versions = {}
        for record in records:
            version = record.action_version
            versions[version] = versions.get(version, 0) + 1

        return {
            "total_executions": len(records),
            "date_range": {
                "earliest": records[-1].timestamp if records else None,
                "latest": records[0].timestamp if records else None,
            },
            "version_distribution": versions,
        }

    def _cleanup_old_records(self, action_id: str) -> None:
        """清理旧的执行记录.

        Args:
            action_id: 动作ID
        """
        action_records_dir = self.records_dir / action_id
        if not action_records_dir.exists():
            return

        record_files = sorted(
            action_records_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )

        if len(record_files) > self.max_records_per_action:
            for old_file in record_files[self.max_records_per_action :]:
                try:
                    old_file.unlink()
                except Exception:
                    pass

    def _compute_params_diff(
        self,
        params1: Dict[str, Any],
        params2: Dict[str, Any],
    ) -> Dict[str, Any]:
        """计算参数差异.

        Args:
            params1: 第一组参数
            params2: 第二组参数

        Returns:
            差异信息
        """
        diff = {
            "added": {},
            "removed": {},
            "modified": {},
        }

        all_keys = set(params1.keys()) | set(params2.keys())

        for key in all_keys:
            if key not in params1:
                diff["added"][key] = params2[key]
            elif key not in params2:
                diff["removed"][key] = params1[key]
            elif params1[key] != params2[key]:
                diff["modified"][key] = {
                    "old": params1[key],
                    "new": params2[key],
                }

        return diff
