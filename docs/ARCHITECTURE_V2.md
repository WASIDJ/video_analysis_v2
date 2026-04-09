# 视频分析系统架构 V2.0

## 架构核心设计原则

### 1. 数据驱动（Data-Driven）
- **Phase引擎**：通用状态机，通过JSON配置定义状态转移规则
- **配置迭代**：支持通过训练数据自动更新参数
- **零代码扩展**：新增动作无需编写Python代码

### 2. 可扩展性（Extensibility）
- **插件化设计**：新动作 = 配置文件 + 训练数据
- **探索模式**：未知动作自动进入全量分析模式
- **指纹系统**：动作特征可存储、可比较、可迭代

### 3. 持续学习（Continuous Learning）
- **多标签支持**：标准动作、错误动作、极端动作、边缘动作
- **增量统计**：聚合多个样本生成"金标准"
- **参数触发器**：基于测试集表现自动触发参数更新

---

## 模块架构

```
src/core/
├── config/                    # 配置系统
│   ├── models.py             # 数据模型（ActionConfig, MetricConfig等）
│   ├── manager.py            # 配置管理器（支持探索模式）
│   ├── validator.py          # 参数验证器
│   └── recorder.py           # 执行记录器
│
├── phases/                    # Phase引擎（重构核心）
│   ├── base.py               # 基类定义
│   ├── generic_phase_detector.py  # 通用状态机引擎 ⭐NEW
│   └── squat_phases.py       # 旧实现（待废弃）
│
├── analysis/                  # 动作分析模块 ⭐NEW
│   ├── fingerprint.py        # 动作指纹分析
│   ├── exploration.py        # 探索模式
│   └── template_generator.py # 模板自动生成
│
├── metrics/                   # 检测项系统
│   ├── definitions.py        # 检测项模板（无硬编码阈值）
│   └── calculator.py         # 检测项计算器
│
└── models/                    # 姿态估计模型
    └── base.py               # 抽象基类

config/action_configs/         # 动作配置目录
├── squat.json                # 深蹲配置（含Phase规则）
├── generated/                # 自动生成的配置
│   └── new_jump_v1.json
└── pending/                  # 待审核的新动作
    └── unknown_action_pending.json
```

---

## Phase引擎设计（Generic Phase Engine）

### 核心思想
将Phase检测从**硬编码逻辑**转变为**状态机执行器**：

```python
# 旧方式：硬编码（不可扩展）
class SquatPhaseDetector:
    def detect(self, sequence):
        if knee_angle < 160:  # 硬编码阈值
            return "descent"

# 新方式：配置驱动（可扩展）
class GenericPhaseDetector:
    def detect(self, sequence):
        # 从JSON读取规则
        # 规则1: 如果 knee_flexion 导数 < 0，则进入 descent
        # 规则2: 如果 knee_flexion 达到局部最小值，则进入 bottom
```

### JSON配置格式

```json
{
  "action_id": "squat",
  "phases": [
    {
      "phase_id": "standing",
      "phase_name": "站立起始"
    },
    {
      "phase_id": "descent",
      "phase_name": "下蹲过程"
    },
    {
      "phase_id": "bottom",
      "phase_name": "最低点"
    }
  ],
  "phase_transitions": [
    {
      "from": "standing",
      "to": "descent",
      "driver_signal": "knee_flexion",
      "type": "derivative",
      "params": {
        "direction": "decreasing",
        "threshold": -2.0
      }
    },
    {
      "from": "descent",
      "to": "bottom",
      "driver_signal": "knee_flexion",
      "type": "extremum",
      "params": {
        "mode": "valley"
      }
    }
  ]
}
```

### 转移条件类型

| 类型 | 说明 | 示例 |
|------|------|------|
| `threshold` | 阈值比较 | `value > 160` |
| `derivative` | 导数判断 | `d(value)/dt < 0` |
| `extremum` | 极值点 | 局部最小/最大 |
| `duration` | 持续时间 | 保持>0.5秒 |
| `compound` | 复合条件 | 多条件组合 |

---

## 探索模式（Exploration Mode）

### 触发条件
当 `ConfigManager.load_config(action_id, enable_exploration=True)` 找不到配置时：

```python
# 找不到配置，自动进入探索模式
config = manager.load_config("new_unknown_action", enable_exploration=True)
# 返回 ExplorationConfig，启用所有检测项
```

### 探索流程

```
新视频输入
    ↓
探索模式激活
    ↓
1. 全量指标计算（所有MetricDefinition）
    ↓
2. 指纹提取（变化幅度、极值点、主导频率）
    ↓
3. 阶段候选检测（基于主导指标）
    ↓
4. 阈值建议生成（基于统计分析）
    ↓
5. 生成初始配置（JSON）
    ↓
保存到 pending/ 待审核
```

### 动作指纹（ActionFingerprint）

```python
@dataclass
class ActionFingerprint:
    action_id: str
    dominant_metrics: List[MetricFingerprint]  # 主导运动特征
    secondary_metrics: List[MetricFingerprint]  # 次要特征
    active_joints: List[str]                    # 活跃关节
    symmetry_score: float                       # 对称性
    tags: List[str]                             # ["standard", "error:knee_valgus"]
```

---

## 参数迭代系统

### 数据分类标签

| 标签 | 用途 | 迭代目标 |
|------|------|----------|
| `standard` | 标准动作 | 构建金标准阈值 |
| `error:{type}` | 错误动作 | 学习错误判断条件 |
| `extreme` | 极端错误 | 定义边界值 |
| `edge` | 边缘动作 | 细化判断依据 |

### 增量统计流程

```python
# 1. 收集标准动作指纹
standard_fps = db.get_fingerprints_by_label("standard", action_id="squat")

# 2. 聚合统计
agg = db.aggregate_by_action("squat", label="standard")
# 生成: mean, std, percentiles for each metric

# 3. 更新配置阈值
manager.update_metric_thresholds(
    action_id="squat",
    metric_id="knee_flexion",
    new_thresholds={
        "target_value": 110.0,
        "normal_range": (90, 120),  # 基于聚合结果
        "excellent_range": (100, 120),
    },
    source="training"  # 标记为训练数据更新
)
```

### 触发器设计

```python
class ParameterIterationTrigger:
    """参数迭代触发器"""

    def check_and_trigger(self, action_id: str) -> bool:
        # 1. 检查样本量
        if db.get_sample_count(action_id, "standard") < 10:
            return False

        # 2. 在测试集上评估当前参数
        current_score = self.evaluate_current_params(action_id)

        # 3. 计算新参数（基于增量统计）
        new_params = self.compute_new_params(action_id)
        new_score = self.evaluate_params(action_id, new_params)

        # 4. 判断是否更新
        improvement = (new_score - current_score) / current_score
        if improvement > 0.05:  # 提升超过5%
            self.apply_params(action_id, new_params)
            return True
        return False
```

---

## 使用示例

### 1. 新动作探索

```python
from core.config.manager import ConfigManager
from core.analysis.exploration import ExplorationAnalyzer

# 探索新动作
analyzer = ExplorationAnalyzer()
result = analyzer.explore(
    pose_sequence=sequence,
    suggested_name="jumping_jack"
)

# 查看发现的特征
print(f"主导指标: {result.suggested_metrics}")
print(f"建议阶段: {result.suggested_phases}")
print(f"置信度: {result.confidence}")

# 生成配置
from core.analysis.template_generator import create_exploration_template
filepath = create_exploration_template(result)
print(f"配置已保存到: {filepath}")
# 输出: config/action_configs/pending/jumping_jack_pending.json
```

### 2. 配置审核与激活

```python
manager = ConfigManager()

# 查看待审核动作
pending = manager.list_pending_actions()
# [{"action_id": "jumping_jack", "confidence": 0.72}]

# 批准动作
manager.approve_pending_action("jumping_jack")
# 配置移动到主目录，可正式使用
```

### 3. 通过训练迭代参数

```python
# 收集多个标准动作样本
for video in standard_videos:
    fingerprint = analyzer.analyze(video, tags=["standard"])
    db.add_fingerprint(fingerprint, label="standard")

# 触发迭代更新
manager.update_metric_thresholds(
    action_id="squat",
    metric_id="knee_flexion",
    new_thresholds=compute_from_aggregated_stats(db),
    source="training"
)
```

---

## 与V1架构对比

| 特性 | V1 | V2 |
|------|-----|-----|
| 新增动作成本 | 写Python代码 + 配置文件 | 仅需配置文件 |
| Phase检测 | 硬编码（squat_phases.py） | 通用状态机 + JSON规则 |
| 未知动作 | 报错/失败 | 探索模式自动分析 |
| 参数优化 | 手动调整 | 数据驱动自动迭代 |
| 知识积累 | 代码中 | 指纹数据库 + 配置历史 |

---

## 后续优化方向

1. **在线学习**：实时根据用户反馈调整参数
2. **迁移学习**：相似动作间共享参数（如深蹲→弓步蹲）
3. **可视化工具**：参数迭代过程的可视化展示
4. **A/B测试**：新旧参数并行对比
