"""动作特征指纹系统.

分析动作的关键特征，生成可存储、可比较的动作"指纹"。
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict
import numpy as np
import json
from datetime import datetime

from src.core.models.base import PoseSequence
from src.core.metrics.definitions import MetricDefinition, METRIC_TEMPLATES, MetricCategory
from src.core.metrics.calculator import MetricsCalculator


@dataclass
class MetricFingerprint:
    """单个检测项的特征指纹."""
    metric_id: str
    metric_name: str
    category: str

    # 统计特征
    mean: float
    std: float
    min: float
    max: float
    range: float

    # 动态特征
    total_variation: float          # 总变差（变化幅度）
    variance_coefficient: float     # 变异系数（std/mean）
    peak_count: int                 # 峰值数量
    valley_count: int               # 谷值数量

    # 时序特征
    dominant_frequency: Optional[float] = None  # 主导频率
    periodicity: Optional[float] = None          # 周期性得分

    # 重要性评分（基于变化幅度）
    significance_score: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "metric_name": self.metric_name,
            "category": self.category,
            "statistics": {
                "mean": self.mean,
                "std": self.std,
                "min": self.min,
                "max": self.max,
                "range": self.range,
            },
            "dynamics": {
                "total_variation": self.total_variation,
                "variance_coefficient": self.variance_coefficient,
                "peak_count": self.peak_count,
                "valley_count": self.valley_count,
            },
            "significance_score": self.significance_score,
        }


@dataclass
class ActionFingerprint:
    """动作的完整特征指纹."""
    action_id: str
    action_name: str
    created_at: str

    # 主导指标（变化最大的前N个）
    dominant_metrics: List[MetricFingerprint]

    # 次要指标
    secondary_metrics: List[MetricFingerprint]

    # 全局统计
    total_metrics_analyzed: int
    active_joints: List[str]          # 活跃关节列表
    symmetry_score: Optional[float] = None  # 对称性评分

    # 元数据
    video_metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)  # 标签：standard, error, extreme, edge

    def get_top_metrics(self, n: int = 5) -> List[MetricFingerprint]:
        """获取最重要的N个指标."""
        all_metrics = self.dominant_metrics + self.secondary_metrics
        return sorted(all_metrics, key=lambda x: x.significance_score, reverse=True)[:n]

    def compare_with(self, other: "ActionFingerprint") -> Dict[str, Any]:
        """与另一个指纹对比."""
        common_metrics = set()
        differences = []

        self_metrics = {m.metric_id: m for m in self.dominant_metrics + self.secondary_metrics}
        other_metrics = {m.metric_id: m for m in other.dominant_metrics + other.secondary_metrics}

        for metric_id in set(self_metrics.keys()) & set(other_metrics.keys()):
            common_metrics.add(metric_id)
            m1 = self_metrics[metric_id]
            m2 = other_metrics[metric_id]

            # 计算范围重叠度
            overlap = self._calculate_range_overlap(
                (m1.min, m1.max), (m2.min, m2.max)
            )

            if overlap < 0.5:  # 重叠度低于50%视为显著差异
                differences.append({
                    "metric_id": metric_id,
                    "range1": (m1.min, m1.max),
                    "range2": (m2.min, m2.max),
                    "overlap": overlap,
                })

        return {
            "common_metrics": list(common_metrics),
            "unique_to_first": list(set(self_metrics.keys()) - set(other_metrics.keys())),
            "unique_to_second": list(set(other_metrics.keys()) - set(self_metrics.keys())),
            "significant_differences": differences,
            "similarity_score": 1.0 - len(differences) / max(len(common_metrics), 1),
        }

    def _calculate_range_overlap(self, range1: Tuple[float, float], range2: Tuple[float, float]) -> float:
        """计算两个范围的重叠度."""
        min1, max1 = range1
        min2, max2 = range2

        overlap_start = max(min1, min2)
        overlap_end = min(max1, max2)

        if overlap_end <= overlap_start:
            return 0.0

        overlap_length = overlap_end - overlap_start
        range1_length = max1 - min1
        range2_length = max2 - min2

        return 2 * overlap_length / (range1_length + range2_length)


class FingerprintAnalyzer:
    """动作指纹分析器."""

    # 指标重要性阈值
    DOMINANT_THRESHOLD = 0.3          # 主导指标阈值（变化幅度）
    SIGNIFICANCE_RATIO = 0.1          # 相对最大变化的比例

    def __init__(self, min_significance: float = 0.05):
        """
        Args:
            min_significance: 最小重要性阈值（过滤掉变化太小的指标）
        """
        self.min_significance = min_significance

    def analyze(
        self,
        pose_sequence: PoseSequence,
        action_name: str = "unknown",
        video_metadata: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
    ) -> ActionFingerprint:
        """分析姿态序列，生成动作指纹.

        Args:
            pose_sequence: 姿态序列
            action_name: 动作名称
            video_metadata: 视频元数据
            tags: 标签列表（如 ["standard", "error:knee_valgus"]）

        Returns:
            动作指纹
        """
        # 使用所有可用指标进行分析
        metric_ids = list(METRIC_TEMPLATES.keys())

        # 计算所有指标
        calculator = MetricsCalculator(
            action_id="exploration",
            use_phase_detection=False,
            use_viewpoint_analysis=True,
        )

        results = calculator.calculate_all_metrics(
            pose_sequence=pose_sequence,
            metric_ids=metric_ids,
            action_name=action_name,
        )

        # 提取每个指标的指纹
        fingerprints = []
        for metric_id, result in results.items():
            if "error" in result or not result.get("values"):
                continue

            fingerprint = self._extract_metric_fingerprint(
                metric_id, result.get("values", [])
            )
            if fingerprint:
                fingerprints.append(fingerprint)

        # 按重要性排序
        fingerprints.sort(key=lambda x: x.significance_score, reverse=True)

        # 分离主导指标和次要指标
        if fingerprints:
            max_range = max(f.range for f in fingerprints)
            threshold = max(max_range * self.SIGNIFICANCE_RATIO, self.min_significance)

            dominant = [f for f in fingerprints if f.range >= threshold]
            secondary = [f for f in fingerprints if f.range < threshold]
        else:
            dominant = []
            secondary = []

        # 识别活跃关节
        active_joints = self._identify_active_joints(dominant)

        # 计算对称性（如果有左右对比的指标）
        symmetry_score = self._calculate_symmetry(fingerprints)

        return ActionFingerprint(
            action_id=action_name.lower().replace(" ", "_"),
            action_name=action_name,
            created_at=datetime.now().isoformat(),
            dominant_metrics=dominant[:10],  # 最多保留10个主导指标
            secondary_metrics=secondary[:20],  # 最多保留20个次要指标
            total_metrics_analyzed=len(fingerprints),
            active_joints=active_joints,
            symmetry_score=symmetry_score,
            video_metadata=video_metadata or {},
            tags=tags or [],
        )

    def _extract_metric_fingerprint(
        self,
        metric_id: str,
        values: List[float],
    ) -> Optional[MetricFingerprint]:
        """从指标时间序列提取指纹."""
        if not values or len(values) < 3:
            return None

        arr = np.array(values)
        arr = arr[~np.isnan(arr)]  # 移除NaN

        if len(arr) < 3:
            return None

        metric_def = METRIC_TEMPLATES.get(metric_id)
        if not metric_def:
            return None

        # 基本统计
        mean = float(np.mean(arr))
        std = float(np.std(arr))
        min_val = float(np.min(arr))
        max_val = float(np.max(arr))
        range_val = max_val - min_val

        # 动态特征
        total_variation = np.sum(np.abs(np.diff(arr)))
        variance_coef = std / abs(mean) if mean != 0 else 0

        # 峰谷检测
        peaks = self._find_peaks(arr)
        valleys = self._find_valleys(arr)

        # 计算重要性分数（基于变化幅度和变异系数）
        significance = range_val * (1 + variance_coef)

        return MetricFingerprint(
            metric_id=metric_id,
            metric_name=metric_def.name_zh,
            category=metric_def.category.value,
            mean=mean,
            std=std,
            min=min_val,
            max=max_val,
            range=range_val,
            total_variation=float(total_variation),
            variance_coefficient=float(variance_coef),
            peak_count=len(peaks),
            valley_count=len(valleys),
            significance_score=float(significance),
        )

    def _find_peaks(self, arr: np.ndarray, window: int = 3) -> List[int]:
        """检测峰值."""
        peaks = []
        for i in range(window, len(arr) - window):
            if arr[i] == np.max(arr[i-window:i+window+1]) and arr[i] > arr[i-1]:
                peaks.append(i)
        return peaks

    def _find_valleys(self, arr: np.ndarray, window: int = 3) -> List[int]:
        """检测谷值."""
        valleys = []
        for i in range(window, len(arr) - window):
            if arr[i] == np.min(arr[i-window:i+window+1]) and arr[i] < arr[i-1]:
                valleys.append(i)
        return valleys

    def _identify_active_joints(self, fingerprints: List[MetricFingerprint]) -> List[str]:
        """识别活跃关节."""
        joint_activity = defaultdict(float)

        for fp in fingerprints:
            metric_def = METRIC_TEMPLATES.get(fp.metric_id)
            if metric_def:
                for joint in metric_def.primary_joints:
                    joint_activity[joint] += fp.significance_score

        # 返回活跃度排序的关节
        sorted_joints = sorted(joint_activity.items(), key=lambda x: x[1], reverse=True)
        return [joint for joint, _ in sorted_joints[:6]]  # 最多6个主要关节

    def _calculate_symmetry(self, fingerprints: List[MetricFingerprint]) -> Optional[float]:
        """计算左右对称性."""
        left_metrics = {}
        right_metrics = {}

        for fp in fingerprints:
            if fp.metric_id.startswith("left_"):
                base_name = fp.metric_id[5:]  # 移除 "left_" 前缀
                left_metrics[base_name] = fp
            elif fp.metric_id.startswith("right_"):
                base_name = fp.metric_id[6:]  # 移除 "right_" 前缀
                right_metrics[base_name] = fp

        if not left_metrics or not right_metrics:
            return None

        # 计算对称性得分（范围重叠度）
        symmetry_scores = []
        for base_name in set(left_metrics.keys()) & set(right_metrics.keys()):
            left = left_metrics[base_name]
            right = right_metrics[base_name]

            # 范围差异越小，对称性越好
            range_diff = abs(left.range - right.range)
            max_range = max(left.range, right.range)
            if max_range > 0:
                symmetry_scores.append(1.0 - range_diff / max_range)

        return float(np.mean(symmetry_scores)) if symmetry_scores else None


class FingerprintDatabase:
    """动作指纹数据库 (JSON Lines格式).

    支持增量存储和检索，每行一个JSON对象。
    """

    def __init__(self, db_path: Optional[str] = None):
        """
        Args:
            db_path: 数据库目录路径（将存储为多个.jsonl文件）
        """
        self.db_path = Path(db_path) if db_path else Path("data/fingerprints")
        self.db_path.mkdir(parents=True, exist_ok=True)

        # 内存中的索引
        self._fingerprints: Dict[str, List[ActionFingerprint]] = defaultdict(list)
        self._index: Dict[str, List[str]] = defaultdict(list)  # action_id -> list of entry ids

        # 加载已有数据
        self._load_from_disk()

    def add_fingerprint(
        self,
        fingerprint: ActionFingerprint,
        label: str = "unknown",
    ) -> str:
        """添加指纹到数据库.

        Args:
            fingerprint: 动作指纹
            label: 标签（standard, error:xxx, extreme, edge, unknown）

        Returns:
            条目ID
        """
        entry_id = f"{fingerprint.action_id}_{fingerprint.created_at}_{len(self._fingerprints[label])}"

        # 添加到内存
        self._fingerprints[label].append(fingerprint)
        self._index[fingerprint.action_id].append(entry_id)

        # 立即持久化到JSON Lines
        self._append_to_jsonl(label, fingerprint, entry_id)

        return entry_id

    def _append_to_jsonl(self, label: str, fingerprint: ActionFingerprint, entry_id: str) -> None:
        """追加单条记录到JSON Lines文件."""
        filepath = self.db_path / f"{label}.jsonl"

        # 构建记录
        record = {
            "id": entry_id,
            "action_id": fingerprint.action_id,
            "action_name": fingerprint.action_name,
            "created_at": fingerprint.created_at,
            "tags": fingerprint.tags,
            "total_metrics_analyzed": fingerprint.total_metrics_analyzed,
            "active_joints": fingerprint.active_joints,
            "symmetry_score": fingerprint.symmetry_score,
            "dominant_metrics": [m.to_dict() for m in fingerprint.dominant_metrics],
            "secondary_metrics": [m.to_dict() for m in fingerprint.secondary_metrics],
            "video_metadata": fingerprint.video_metadata,
        }

        # 追加写入
        with open(filepath, 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')

    def _load_from_disk(self) -> None:
        """从JSON Lines文件加载数据库."""
        if not self.db_path.exists():
            return

        for jsonl_file in self.db_path.glob("*.jsonl"):
            label = jsonl_file.stem  # 文件名作为label

            try:
                with open(jsonl_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue

                        record = json.loads(line)
                        fingerprint = self._record_to_fingerprint(record)

                        self._fingerprints[label].append(fingerprint)
                        self._index[record["action_id"]].append(record["id"])

            except Exception as e:
                print(f"加载指纹文件失败 {jsonl_file}: {e}")

    def _record_to_fingerprint(self, record: Dict) -> ActionFingerprint:
        """将记录转换为指纹对象."""
        # 重建MetricFingerprint
        dominant = [self._record_to_metric_fingerprint(m) for m in record.get("dominant_metrics", [])]
        secondary = [self._record_to_metric_fingerprint(m) for m in record.get("secondary_metrics", [])]

        return ActionFingerprint(
            action_id=record["action_id"],
            action_name=record["action_name"],
            created_at=record["created_at"],
            dominant_metrics=dominant,
            secondary_metrics=secondary,
            total_metrics_analyzed=record["total_metrics_analyzed"],
            active_joints=record["active_joints"],
            symmetry_score=record.get("symmetry_score"),
            video_metadata=record.get("video_metadata", {}),
            tags=record.get("tags", []),
        )

    def _record_to_metric_fingerprint(self, metric_record: Dict[str, Any]) -> MetricFingerprint:
        """将单条检测项记录转换为 MetricFingerprint."""
        if "statistics" in metric_record:
            stats = metric_record.get("statistics", {})
            dynamics = metric_record.get("dynamics", {})
            return MetricFingerprint(
                metric_id=metric_record.get("metric_id", ""),
                metric_name=metric_record.get("metric_name", ""),
                category=metric_record.get("category", ""),
                mean=stats.get("mean", 0.0),
                std=stats.get("std", 0.0),
                min=stats.get("min", 0.0),
                max=stats.get("max", 0.0),
                range=stats.get("range", 0.0),
                total_variation=dynamics.get("total_variation", 0.0),
                variance_coefficient=dynamics.get("variance_coefficient", 0.0),
                peak_count=dynamics.get("peak_count", 0),
                valley_count=dynamics.get("valley_count", 0),
                dominant_frequency=metric_record.get("dominant_frequency"),
                periodicity=metric_record.get("periodicity"),
                significance_score=metric_record.get("significance_score", 0.0),
            )

        return MetricFingerprint(**metric_record)

    def get_fingerprints_by_label(self, label: str) -> List[ActionFingerprint]:
        """获取指定标签的所有指纹."""
        return self._fingerprints.get(label, [])

    def get_fingerprints_by_action(
        self,
        action_id: str,
        labels: Optional[List[str]] = None
    ) -> Dict[str, List[ActionFingerprint]]:
        """获取指定动作的所有指纹（按标签分组）."""
        result = {}

        labels_to_search = labels or list(self._fingerprints.keys())

        for label in labels_to_search:
            fps = [
                fp for fp in self._fingerprints.get(label, [])
                if fp.action_id == action_id
            ]
            if fps:
                result[label] = fps

        return result

    def get_statistics(self, label: Optional[str] = None) -> Dict[str, Any]:
        """获取指纹统计信息."""
        if label:
            fps = self._fingerprints.get(label, [])
            return {
                "count": len(fps),
                "actions": list(set(f.action_id for f in fps)),
                "action_count": len(set(f.action_id for f in fps)),
            }
        else:
            return {
                label: {
                    "count": len(fps),
                    "actions": list(set(f.action_id for f in fps)),
                }
                for label, fps in self._fingerprints.items()
            }

    def get_all_labels(self) -> List[str]:
        """获取所有标签."""
        return list(self._fingerprints.keys())

    def query(
        self,
        action_id: Optional[str] = None,
        labels: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
    ) -> List[Tuple[ActionFingerprint, str]]:
        """查询指纹.

        Args:
            action_id: 动作ID过滤
            labels: 标签过滤
            tags: 标签过滤（在指纹内部）

        Returns:
            (指纹, 标签) 列表
        """
        results = []

        labels_to_search = labels or list(self._fingerprints.keys())

        for label in labels_to_search:
            for fp in self._fingerprints.get(label, []):
                # 动作ID过滤
                if action_id and fp.action_id != action_id:
                    continue

                # 标签过滤
                if tags and not any(t in fp.tags for t in tags):
                    continue

                results.append((fp, label))

        return results

    def aggregate_by_action(
        self,
        action_id: str,
        label: str = "standard",
    ) -> Optional[ActionFingerprint]:
        """聚合同一动作的多个指纹.

        用于从多个标准动作视频中学习通用参数。
        """
        fps = [
            f for f in self._fingerprints.get(label, [])
            if f.action_id == action_id
        ]

        if not fps:
            return None

        # 聚合主导指标
        from collections import defaultdict
        import numpy as np

        metric_stats = defaultdict(lambda: {
            "ranges": [],
            "means": [],
            "mins": [],
            "maxs": [],
            "stds": [],
        })

        for fp in fps:
            for metric in fp.dominant_metrics + fp.secondary_metrics:
                stats = metric_stats[metric.metric_id]
                stats["ranges"].append(metric.range)
                stats["means"].append(metric.mean)
                stats["mins"].append(metric.min)
                stats["maxs"].append(metric.max)
                stats["stds"].append(metric.std)

        # 创建聚合的MetricFingerprint
        aggregated_metrics = []
        for metric_id, stats in metric_stats.items():
            if not stats["means"]:
                continue

            aggregated_metrics.append(MetricFingerprint(
                metric_id=metric_id,
                metric_name=metric_id,  # 简化处理
                category="unknown",
                mean=np.mean(stats["means"]),
                std=np.mean(stats["stds"]),
                min=np.mean(stats["mins"]),
                max=np.mean(stats["maxs"]),
                range=np.mean(stats["ranges"]),
                total_variation=0,  # 聚合后无法计算
                variance_coefficient=np.std(stats["means"]) / (np.mean(stats["means"]) + 1e-6),
                peak_count=0,
                valley_count=0,
                significance_score=np.mean(stats["ranges"]),
            ))

        # 按重要性排序
        aggregated_metrics.sort(key=lambda x: x.significance_score, reverse=True)

        return ActionFingerprint(
            action_id=action_id,
            action_name=fps[0].action_name if fps else action_id,
            created_at=datetime.now().isoformat(),
            dominant_metrics=aggregated_metrics[:10],
            secondary_metrics=aggregated_metrics[10:],
            total_metrics_analyzed=sum(f.total_metrics_analyzed for f in fps) // len(fps),
            active_joints=list(set().union(*[set(f.active_joints) for f in fps])),
            symmetry_score=np.mean([f.symmetry_score for f in fps if f.symmetry_score is not None]) if any(f.symmetry_score is not None for f in fps) else None,
            video_metadata={"aggregated_from": len(fps)},
            tags=[label],
        )

    def save_to_disk(self) -> None:
        """保存数据库到磁盘（已实时保存，此方法用于兼容）."""
        # 数据已实时追加到JSONL，无需额外操作
        pass

    def compact_database(self) -> None:
        """压缩数据库（去重、整理）."""
        for label in self._fingerprints.keys():
            filepath = self.db_path / f"{label}.jsonl"
            temp_filepath = self.db_path / f"{label}.jsonl.tmp"

            try:
                with open(temp_filepath, 'w', encoding='utf-8') as f_out:
                    seen_ids = set()

                    for fp in self._fingerprints[label]:
                        entry_id = f"{fp.action_id}_{fp.created_at}"

                        # 去重
                        if entry_id in seen_ids:
                            continue
                        seen_ids.add(entry_id)

                        record = {
                            "id": entry_id,
                            "action_id": fp.action_id,
                            "action_name": fp.action_name,
                            "created_at": fp.created_at,
                            "tags": fp.tags,
                            "total_metrics_analyzed": fp.total_metrics_analyzed,
                            "active_joints": fp.active_joints,
                            "symmetry_score": fp.symmetry_score,
                            "dominant_metrics": [m.to_dict() for m in fp.dominant_metrics],
                            "secondary_metrics": [m.to_dict() for m in fp.secondary_metrics],
                            "video_metadata": fp.video_metadata,
                        }
                        f_out.write(json.dumps(record, ensure_ascii=False) + '\n')

                # 替换原文件
                filepath.unlink(missing_ok=True)
                temp_filepath.rename(filepath)

            except Exception as e:
                print(f"压缩数据库失败 {filepath}: {e}")
                temp_filepath.unlink(missing_ok=True)
