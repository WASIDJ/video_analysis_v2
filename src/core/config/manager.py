"""配置管理器.

提供配置文件的加载、保存和管理功能.
支持探索模式和参数迭代。
"""
import json
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Union, Any
import threading

from .models import ActionConfig, MetricConfig, MetricThreshold, ErrorCondition


class ConfigManager:
    """配置管理器.

    管理动作配置文件的加载、保存和版本控制.
    """

    # 默认配置目录
    DEFAULT_CONFIG_DIR = Path(__file__).parent.parent.parent.parent / "config" / "action_configs"

    # 算法版本
    ALGORITHM_VERSION = "2.1.0"

    def __init__(
        self,
        config_dir: Optional[Union[str, Path]] = None,
        enable_caching: bool = True,
    ):
        """
        Args:
            config_dir: 配置目录路径
            enable_caching: 是否启用配置缓存
        """
        self.config_dir = Path(config_dir) if config_dir else self.DEFAULT_CONFIG_DIR
        self.config_dir.mkdir(parents=True, exist_ok=True)

        self._cache: Dict[str, ActionConfig] = {}
        self._cache_lock = threading.RLock()
        self._enable_caching = enable_caching

        # 确保默认配置存在
        self._ensure_default_configs()

    def _ensure_default_configs(self) -> None:
        """确保默认配置文件存在."""
        default_configs = ["squat", "lunge", "pushup", "plank", "deadlift", "side_leg_raise"]
        for action_id in default_configs:
            config_path = self.config_dir / f"{action_id}.json"
            if not config_path.exists():
                default_config = self._create_default_config(action_id)
                self.save_config(default_config)

    def _create_default_config(self, action_id: str) -> ActionConfig:
        """创建默认配置."""
        from ..metrics.definitions import METRIC_TEMPLATES
        from .models import MetricConfig, MetricThreshold

        configs = {
            "squat": {
                "action_name": "Squat",
                "action_name_zh": "深蹲",
                "description": "深蹲动作分析配置",
                "metrics": ["knee_flexion", "trunk_lean", "hip_flexion"],
                "phase_name": "最低点",
            },
            "lunge": {
                "action_name": "Lunge",
                "action_name_zh": "弓步蹲",
                "description": "弓步蹲动作分析配置",
                "metrics": ["knee_flexion", "trunk_lean", "hip_flexion"],
                "phase_name": "最低点",
            },
            "pushup": {
                "action_name": "Push-up",
                "action_name_zh": "俯卧撑",
                "description": "俯卧撑动作分析配置",
                "metrics": ["elbow_flexion_left", "trunk_lean"],
                "phase_name": "最低点",
            },
            "plank": {
                "action_name": "Plank",
                "action_name_zh": "平板支撑",
                "description": "平板支撑动作分析配置",
                "metrics": ["trunk_lean", "lumbar_curvature"],
                "phase_name": "hold",
            },
            "deadlift": {
                "action_name": "Deadlift",
                "action_name_zh": "硬拉",
                "description": "硬拉动作分析配置",
                "metrics": ["knee_flexion", "trunk_lean", "hip_flexion"],
                "phase_name": "最低点",
            },
            "side_leg_raise": {
                "action_name": "Side Leg Raise",
                "action_name_zh": "侧抬腿",
                "description": "侧抬腿动作分析配置，主要训练臀中肌",
                "metrics": ["hip_abduction", "trunk_lateral_flexion", "pelvic_obliquity"],
                "phase_name": "顶点保持",
            },
        }

        base_info = configs.get(action_id, {
            "action_name": action_id.capitalize(),
            "action_name_zh": action_id,
            "description": f"{action_id}动作分析配置",
        })

        # 创建默认检测项配置（不依赖模板中的阈值，使用空默认值）
        metrics = []
        for metric_id in ["knee_flexion", "trunk_lean", "hip_flexion"]:
            if metric_id in METRIC_TEMPLATES:
                metrics.append(MetricConfig(
                    metric_id=metric_id,
                    enabled=True,
                    evaluation_phase="bottom",
                    thresholds=MetricThreshold(),  # 空阈值，需在配置文件中设置
                    error_conditions=[],  # 空错误条件，需在配置文件中设置
                    weight=1.0,
                ))

        return ActionConfig(
            action_id=action_id,
            action_name=base_info["action_name"],
            action_name_zh=base_info["action_name_zh"],
            description=base_info["description"],
            version="1.0.0",
            phases=[
                PhaseDefinition(
                    phase_id="bottom",
                    phase_name="最低点",
                    description="深蹲最深处",
                )
            ],
            metrics=metrics,
            global_params={
                "min_phase_duration": 0.2,
                "enable_phase_detection": True,
            },
        )

    def load_config(
        self,
        action_id: str,
        version: Optional[str] = None,
        use_cache: bool = True,
        enable_exploration: bool = False,
    ) -> Optional[ActionConfig]:
        """加载配置.

        Args:
            action_id: 动作ID
            version: 指定版本（None表示最新版本）
            use_cache: 是否使用缓存
            enable_exploration: 当配置不存在时是否返回探索模式配置

        Returns:
            ActionConfig或None（如果enable_exploration=True且配置不存在，返回探索模式配置）
        """
        cache_key = f"{action_id}:{version}"

        # 检查缓存
        if use_cache and self._enable_caching:
            with self._cache_lock:
                if cache_key in self._cache:
                    return self._cache[cache_key]

        # 构建文件路径
        if version:
            config_path = self.config_dir / f"{action_id}_v{version}.json"
        else:
            config_path = self.config_dir / f"{action_id}.json"

        # 加载配置
        if not config_path.exists():
            # 尝试加载默认配置
            if version:
                # 如果指定版本不存在，回退到最新版本
                return self.load_config(action_id, None, use_cache, enable_exploration)

            trained_config_path = self.config_dir / f"{action_id}_trained.json"
            if trained_config_path.exists():
                config_path = trained_config_path
            else:
                side_leg_raise_alias = self.config_dir / "side_leg_raise.json"
                if action_id == "side_lift" and side_leg_raise_alias.exists():
                    config_path = side_leg_raise_alias
                else:
                    if enable_exploration:
                        return self._create_exploration_config(action_id)
                    return None

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            config = ActionConfig.from_dict(data)

            # 更新缓存
            if self._enable_caching:
                with self._cache_lock:
                    self._cache[cache_key] = config

            return config

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            print(f"加载配置失败 {config_path}: {e}")
            if enable_exploration:
                return self._create_exploration_config(action_id)
            return None

    def _create_exploration_config(self, action_id: str) -> ActionConfig:
        """创建探索模式配置.

        当找不到动作配置时，返回探索模式配置以支持新动作分析。
        """
        from ..analysis.exploration import get_default_exploration_config
        from ..metrics.definitions import METRIC_TEMPLATES

        base_config = get_default_exploration_config()

        # 启用所有可用的检测项
        metrics = []
        for metric_id in METRIC_TEMPLATES.keys():
            metrics.append(MetricConfig(
                metric_id=metric_id,
                enabled=True,
                evaluation_phase="execution",
                thresholds=MetricThreshold(),  # 空阈值
                error_conditions=[],  # 无错误条件
                custom_params={"exploration_mode": True},
                weight=1.0,
            ))

        return ActionConfig(
            action_id=action_id,
            action_name=base_config["action_name"],
            action_name_zh=f"新动作探索: {action_id}",
            description=base_config["description"],
            version="0.1.0-exploration",
            phases=[PhaseDefinition.from_dict(p) for p in base_config["phases"]],
            metrics=metrics,
            global_params=base_config["global_params"],
            metadata={"exploration_mode": True, "auto_created": True},
        )

    def save_config(
        self,
        config: ActionConfig,
        backup: bool = True,
    ) -> bool:
        """保存配置.

        Args:
            config: 配置对象
            backup: 是否备份旧版本

        Returns:
            是否保存成功
        """
        config_path = self.config_dir / f"{config.action_id}.json"

        try:
            # 备份旧版本
            if backup and config_path.exists():
                backup_path = self.config_dir / f"{config.action_id}_backup_{config.version}.json"
                shutil.copy2(config_path, backup_path)

            # 更新版本号和时间戳
            import time
            config.updated_at = time.strftime("%Y-%m-%dT%H:%M:%S")

            # 保存配置
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)

            # 更新缓存
            if self._enable_caching:
                cache_key = f"{config.action_id}:{config.version}"
                with self._cache_lock:
                    self._cache[cache_key] = config

            return True

        except Exception as e:
            print(f"保存配置失败: {e}")
            return False

    def list_configs(self) -> List[Dict[str, str]]:
        """列出所有可用配置.

        Returns:
            配置信息列表
        """
        configs = []

        for config_file in self.config_dir.glob("*.json"):
            if "_backup_" in config_file.name or "_v" in config_file.name:
                continue

            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                configs.append({
                    "action_id": data.get("action_id", ""),
                    "action_name": data.get("action_name", ""),
                    "action_name_zh": data.get("action_name_zh", ""),
                    "version": data.get("version", ""),
                    "updated_at": data.get("updated_at", ""),
                })
            except Exception:
                continue

        return configs

    def get_versions(self, action_id: str) -> List[str]:
        """获取动作的所有版本号.

        Args:
            action_id: 动作ID

        Returns:
            版本号列表
        """
        versions = []

        # 主版本
        main_config = self.config_dir / f"{action_id}.json"
        if main_config.exists():
            try:
                with open(main_config, "r", encoding="utf-8") as f:
                    data = json.load(f)
                versions.append(data.get("version", "unknown"))
            except Exception:
                pass

        # 备份版本
        for backup_file in self.config_dir.glob(f"{action_id}_backup_*.json"):
            version = backup_file.stem.split("_backup_")[-1]
            versions.append(version)

        return sorted(set(versions), reverse=True)

    def clear_cache(self) -> None:
        """清除配置缓存."""
        with self._cache_lock:
            self._cache.clear()

    def reload_config(self, action_id: str) -> Optional[ActionConfig]:
        """重新加载配置（忽略缓存）.

        Args:
            action_id: 动作ID

        Returns:
            ActionConfig或None
        """
        # 清除相关缓存
        keys_to_remove = [k for k in self._cache.keys() if k.startswith(f"{action_id}:")]
        with self._cache_lock:
            for key in keys_to_remove:
                del self._cache[key]

        return self.load_config(action_id, use_cache=False)

    def update_metric_thresholds(
        self,
        action_id: str,
        metric_id: str,
        new_thresholds: Dict[str, Any],
        source: str = "manual",
        validate: bool = True,
    ) -> bool:
        """更新检测项阈值（参数迭代）.

        Args:
            action_id: 动作ID
            metric_id: 检测项ID
            new_thresholds: 新阈值配置
            source: 更新来源（manual/iteration/training）
            validate: 是否验证新阈值

        Returns:
            是否更新成功
        """
        config = self.load_config(action_id)
        if not config:
            return False

        metric_config = config.get_metric_config(metric_id)
        if not metric_config:
            return False

        # 验证新阈值
        if validate:
            from .validator import ParameterValidator
            temp_thresholds = MetricThreshold.from_dict(new_thresholds)
            errors = ParameterValidator.validate_thresholds(metric_id, temp_thresholds)
            if errors:
                print(f"阈值验证失败: {errors}")
                return False

        # 更新阈值
        if "target_value" in new_thresholds:
            metric_config.thresholds.target_value = new_thresholds["target_value"]
        if "normal_range" in new_thresholds:
            metric_config.thresholds.normal_range = tuple(new_thresholds["normal_range"])
        if "excellent_range" in new_thresholds:
            metric_config.thresholds.excellent_range = tuple(new_thresholds["excellent_range"])
        if "good_range" in new_thresholds:
            metric_config.thresholds.good_range = tuple(new_thresholds["good_range"])
        if "pass_range" in new_thresholds:
            metric_config.thresholds.pass_range = tuple(new_thresholds["pass_range"])

        # 记录更新历史
        if "threshold_history" not in config.metadata:
            config.metadata["threshold_history"] = []

        config.metadata["threshold_history"].append({
            "metric_id": metric_id,
            "timestamp": self._get_timestamp(),
            "source": source,
            "new_thresholds": new_thresholds,
        })

        # 更新版本号（迭代版本）
        self._increment_version(config)

        return self.save_config(config)

    def add_error_condition(
        self,
        action_id: str,
        metric_id: str,
        error_condition: ErrorCondition,
        source: str = "training",
    ) -> bool:
        """添加错误判断条件（从训练数据学习）.

        Args:
            action_id: 动作ID
            metric_id: 检测项ID
            error_condition: 错误条件
            source: 来源

        Returns:
            是否添加成功
        """
        config = self.load_config(action_id)
        if not config:
            return False

        metric_config = config.get_metric_config(metric_id)
        if not metric_config:
            return False

        # 检查是否已存在相同error_id的条件
        existing_ids = {ec.error_id for ec in metric_config.error_conditions}
        if error_condition.error_id in existing_ids:
            # 更新现有条件
            for i, ec in enumerate(metric_config.error_conditions):
                if ec.error_id == error_condition.error_id:
                    metric_config.error_conditions[i] = error_condition
                    break
        else:
            # 添加新条件
            metric_config.error_conditions.append(error_condition)

        # 记录更新
        if "error_condition_history" not in config.metadata:
            config.metadata["error_condition_history"] = []

        config.metadata["error_condition_history"].append({
            "metric_id": metric_id,
            "error_id": error_condition.error_id,
            "timestamp": self._get_timestamp(),
            "source": source,
        })

        self._increment_version(config)
        return self.save_config(config)

    def register_new_action(
        self,
        config: ActionConfig,
        auto_activate: bool = True,
    ) -> bool:
        """注册新动作配置.

        Args:
            config: 新动作配置
            auto_activate: 是否立即激活（保存到主配置目录）

        Returns:
            是否注册成功
        """
        if auto_activate:
            return self.save_config(config)
        else:
            # 保存到待审核目录
            pending_dir = self.config_dir / "pending"
            pending_dir.mkdir(exist_ok=True)

            config_path = pending_dir / f"{config.action_id}_pending.json"
            try:
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
                return True
            except Exception as e:
                print(f"保存待审核配置失败: {e}")
                return False

    def list_pending_actions(self) -> List[Dict[str, str]]:
        """列出待审核的新动作配置."""
        pending_dir = self.config_dir / "pending"
        if not pending_dir.exists():
            return []

        pending = []
        for config_file in pending_dir.glob("*_pending.json"):
            try:
                with open(config_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                pending.append({
                    "action_id": data.get("action_id", ""),
                    "action_name": data.get("action_name", ""),
                    "description": data.get("description", ""),
                    "confidence": data.get("metadata", {}).get("generation_confidence", 0),
                })
            except Exception:
                continue

        return pending

    def approve_pending_action(self, action_id: str) -> bool:
        """批准待审核的动作配置."""
        pending_dir = self.config_dir / "pending"
        pending_path = pending_dir / f"{action_id}_pending.json"

        if not pending_path.exists():
            return False

        try:
            with open(pending_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            config = ActionConfig.from_dict(data)
            config.metadata["approved"] = True
            config.metadata["approved_at"] = self._get_timestamp()

            # 移动到主配置目录
            if self.save_config(config):
                pending_path.unlink()  # 删除待审核文件
                return True
            return False
        except Exception as e:
            print(f"批准配置失败: {e}")
            return False

    def _increment_version(self, config: ActionConfig) -> None:
        """递增配置版本号."""
        try:
            parts = config.version.split(".")
            if len(parts) >= 2:
                minor = int(parts[1])
                parts[1] = str(minor + 1)
                config.version = ".".join(parts[:2])
            else:
                config.version = config.version + ".1"
        except (ValueError, IndexError):
            config.version = "1.1.0"

    def _get_timestamp(self) -> str:
        """获取当前时间戳."""
        import time
        return time.strftime("%Y-%m-%dT%H:%M:%S")


# 全局配置管理器实例
_config_manager: Optional[ConfigManager] = None


def get_config_manager(
    config_dir: Optional[Union[str, Path]] = None,
    enable_caching: bool = True,
) -> ConfigManager:
    """获取全局配置管理器实例.

    使用单例模式确保全局只有一个配置管理器.
    """
    global _config_manager

    if _config_manager is None:
        _config_manager = ConfigManager(config_dir, enable_caching)

    return _config_manager


def reset_config_manager() -> None:
    """重置全局配置管理器（主要用于测试）."""
    global _config_manager
    _config_manager = None


# 导入PhaseDefinition避免循环依赖
from .models import PhaseDefinition
