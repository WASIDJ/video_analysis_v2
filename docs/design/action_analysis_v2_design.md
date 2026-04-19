# 动作分析系统 V2 设计方案

## 1. 现状分析与问题定义

### 1.1 当前架构痛点

| 问题域 | 现状 | 影响 |
|--------|------|------|
| **阶段引擎** | 推理侧依赖 `squat_phases.create_phase_detector(action_name)`，仅支持深蹲 | 新动作无法自动进行阶段检测和计数 |
| **动作计数** | 无完整的 rep/cycle 计数器实现 | 无法自动统计动作完成次数 |
| **阈值评估** | `thresholds` 仅存储于配置，推理端未消费 | 无法基于训练参数进行等级评分（优秀/良好/及格） |
| **配置一致性** | 模板引用的 metric_id 可能在定义库中缺失 | 运行时错误，配置与代码不同步 |
| **数据格式** | 训练指纹结构与推理结果结构并行 | 训练与生产无法无缝复用同一套对象 |
| **实时能力** | 主流程为"整段视频处理后输出" | 无法支持实时流式分析 |

### 1.2 核心设计目标

1. **训练参数直接用于生产**：训练产出的 `error_conditions` 和 `thresholds` 可直接用于实时推理
2. **零代码扩展新动作**：通过配置即可支持新动作的阶段检测、计数、错误识别
3. **统一数据格式**：定义 `MetricPayload` 规范，打通训练-迭代-生产链路
4. **实时分析能力**：支持逐帧/滑窗计算，输出实时错误和计数

---

## 2. 系统架构设计

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           动作分析系统 V2                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐              │
│  │   配置管理层     │  │   阶段引擎层     │  │   检测项计算层   │              │
│  │  ConfigManager  │  │  PhaseEngine    │  │  MetricsEngine  │              │
│  └────────┬────────┘  └────────┬────────┘  └────────┬────────┘              │
│           │                    │                    │                       │
│           ▼                    ▼                    ▼                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      统一调度层 (ActionAnalyzer)                     │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │   │
│  │  │  阶段检测    │  │  动作计数    │  │  阈值评估    │  │  错误识别    │ │   │
│  │  │  PhaseDet   │  │  RepCounter │  │  Threshold  │  │  ErrorDet   │ │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      统一数据模型 (MetricPayload)                    │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐ │   │
│  │  │  Definition │  │   Config    │  │   Runtime   │  │ Fingerprint │ │   │
│  │  │   (能力)     │  │   (参数)     │  │   (实时值)   │  │   (特征)     │ │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│           │                                                                 │
│           ▼                                                                 │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      输出接口层                                      │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │   │
│  │  │  批量分析    │  │  实时分析    │  │  训练迭代    │                  │   │
│  │  │ Batch API   │  │ Stream API  │  │ Train API   │                  │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘                  │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 核心模块职责

| 模块 | 职责 | 输入 | 输出 |
|------|------|------|------|
| **ConfigManager** | 配置加载、校验、版本管理 | action_id, version | ActionConfig |
| **PhaseEngine** | 基于配置的阶段检测 | PoseSequence, PhaseConfig | PhaseSequence |
| **RepCounter** | 基于阶段序列的动作计数 | PhaseSequence | rep_count, rep_ranges |
| **MetricsEngine** | 检测项计算与评估 | PoseSequence, MetricConfigs | MetricResults |
| **ThresholdEvaluator** | 阈值等级评估 | metric_value, thresholds | grade, score |
| **ErrorDetector** | 错误条件识别 | metric_value, error_conditions | errors[] |
| **ActionAnalyzer** | 统一调度编排 | video/config | AnalysisResult |

---

## 3. 详细设计

### 3.1 统一阶段引擎 (PhaseEngine)

#### 3.1.1 设计原则

- **配置驱动**：阶段定义完全来自 `ActionConfig.phases`，不再硬编码动作类型
- **状态机实现**：基于 FSM (Finite State Machine) 的阶段流转
- **规则可扩展**：支持阈值、导数、极值、持续时间、复合条件等多种规则

#### 3.1.2 阶段定义 DSL

```python
# 阶段定义配置（JSON 可配置）
{
  "phase_id": "hold",           # 阶段标识
  "phase_name": "保持顶点",      # 显示名称
  "description": "在最高点保持",
  "entry_conditions": [         # 进入条件（OR 关系）
    {
      "type": "THRESHOLD",      # 条件类型
      "metric": "hip_abduction",
      "operator": "gte",
      "value": 30,
      "duration": 3             # 持续帧数
    }
  ],
  "exit_conditions": [          # 退出条件
    {
      "type": "THRESHOLD",
      "metric": "hip_abduction",
      "operator": "lt",
      "value": 25
    },
    {
      "type": "DURATION",       # 最大持续时间
      "max_duration": 5.0       # 秒
    }
  ],
  "stability_checks": [         # 稳定性检查
    {
      "metric": "hip_abduction",
      "max_variance": 5.0       # 最大方差
    }
  ]
}
```

#### 3.1.3 PhaseEngine 接口

```python
class PhaseEngine:
    """统一阶段引擎."""

    def __init__(self, phase_configs: List[PhaseConfig]):
        self.phase_configs = {p.phase_id: p for p in phase_configs}
        self.fsm = PhaseFSM(phase_configs)

    def detect_phases(
        self,
        pose_sequence: PoseSequence,
        metric_values: Dict[str, np.ndarray]
    ) -> PhaseSequence:
        """检测阶段序列."""
        pass

    def get_key_frame(
        self,
        phase_id: str,
        metric_id: Optional[str] = None
    ) -> Optional[int]:
        """获取指定阶段的关键帧."""
        pass

    def get_phase_ranges(self) -> List[Tuple[int, int]]:
        """获取所有阶段的时间范围."""
        pass
```

### 3.2 动作计数器 (RepCounter)

#### 3.2.1 计数策略

```python
class RepCounter:
    """基于阶段序列的动作计数器."""

    def __init__(
        self,
        cycle_definition: CycleDefinition,  # 周期定义
        min_cycle_duration: float = 1.0,     # 最小周期时长
        max_cycle_duration: float = 30.0,    # 最大周期时长
    ):
        self.cycle_definition = cycle_definition

    def count(
        self,
        phase_sequence: PhaseSequence
    ) -> RepCountResult:
        """
        基于阶段序列识别完整周期.

        周期定义示例：
        - 深蹲: ["start", "descent", "bottom", "ascent", "end"]
        - 侧抬腿: ["start", "lift", "hold", "lower"]
        - 可配置起点和终点（支持部分周期）
        """
        pass
```

#### 3.2.2 周期定义配置

```python
@dataclass
class CycleDefinition:
    """动作周期定义."""

    # 完整周期所需的阶段序列
    phase_sequence: List[str]

    # 起始阶段（可从中间开始）
    start_phase: Optional[str] = None

    # 结束阶段（回到起始或特定阶段）
    end_phase: Optional[str] = None

    # 关键阶段（必须存在才能算一个有效周期）
    required_phases: List[str] = field(default_factory=list)

    # 循环模式
    cycle_mode: CycleMode = CycleMode.CLOSED  # CLOSED: 回到起点, OPEN: 线性序列
```

### 3.3 阈值评估引擎 (ThresholdEvaluator)

#### 3.3.1 评估模型

```python
@dataclass
class ThresholdEvaluation:
    """阈值评估结果."""

    grade: Literal["excellent", "good", "pass", "fail"]
    score: float                    # 0-100 分
    deviation: float                # 与 target 的偏差
    normalized_score: float         # 归一化分数 (0-1)
    description: str                # 评估描述

class ThresholdEvaluator:
    """阈值评估引擎."""

    def evaluate(
        self,
        value: float,
        thresholds: MetricThreshold
    ) -> ThresholdEvaluation:
        """
        基于阈值配置评估数值.

        评估逻辑：
        1. 检查是否在 excellent_range -> 优秀
        2. 检查是否在 good_range -> 良好
        3. 检查是否在 pass_range -> 及格
        4. 否则 -> 不及格

        分数计算：
        - 在范围内：根据距离 target 的接近程度计算
        - 在范围外：根据超出程度扣分
        """
        pass

    def evaluate_with_symmetry(
        self,
        left_value: float,
        right_value: float,
        thresholds: MetricThreshold,
        symmetry_weight: float = 0.3
    ) -> ThresholdEvaluation:
        """考虑对称性的评估（用于双侧动作）."""
        pass
```

#### 3.3.2 阈值配置格式

```python
@dataclass
class MetricThreshold:
    """检测项阈值配置."""

    target_value: Optional[float] = None      # 目标值
    normal_range: Optional[Tuple[float, float]] = None   # 正常范围
    excellent_range: Optional[Tuple[float, float]] = None  # 优秀
    good_range: Optional[Tuple[float, float]] = None       # 良好
    pass_range: Optional[Tuple[float, float]] = None       # 及格
    fail_range: Optional[Tuple[float, float]] = None       # 不及格（自动计算）

    # 评分权重
    accuracy_weight: float = 0.6      # 准确度权重
    stability_weight: float = 0.4     # 稳定性权重
```

### 3.4 统一数据格式 (MetricPayload)

#### 3.4.1 四层数据模型

```python
# ============================================================
# Layer 1: Definition (能力定义 - 代码层)
# ============================================================
class MetricDefinition:
    """检测项定义 - 描述"能算什么"."""
    id: str                           # 唯一标识
    name: str                         # 英文名称
    name_zh: str                      # 中文名称
    description: str                  # 描述
    category: MetricCategory          # 分类
    plane: MovementPlane              # 运动平面
    measurement_type: str             # 测量类型
    required_keypoints: List[str]     # 必需关键点
    calculator: str                   # 计算器类型
    calculator_params: Dict[str, Any] # 计算器参数

# ============================================================
# Layer 2: Config (参数配置 - 训练/人工配置)
# ============================================================
class MetricConfig:
    """检测项配置 - 描述"怎么算对/错"."""
    metric_id: str                    # 关联的 definition
    enabled: bool                     # 是否启用
    evaluation_phase: str             # 评估阶段
    thresholds: MetricThreshold       # 阈值参数
    error_conditions: List[ErrorCondition]  # 错误条件
    weight: float                     # 权重

# ============================================================
# Layer 3: Runtime (运行时值 - 推理产出)
# ============================================================
class MetricRuntime:
    """检测项运行时值 - 描述"算出来是什么"."""
    metric_id: str                    # 关联的 definition
    values: np.ndarray                # 时序值
    statistics: MetricStatistics      # 统计信息
    key_frame_value: Optional[float]  # 关键帧值
    evaluation_phase: Optional[str]   # 评估阶段

class MetricStatistics:
    """统计信息."""
    mean: float
    std: float
    min: float
    max: float
    range: float
    stability_score: float            # 稳定性评分

# ============================================================
# Layer 4: Fingerprint (特征指纹 - 训练/比对)
# ============================================================
class MetricFingerprint:
    """检测项特征指纹 - 描述"正常应该长什么样"."""
    metric_id: str
    statistics: FingerprintStatistics  # 统计特征
    dynamics: FingerprintDynamics      # 动态特征
    significance: FingerprintSignificance  # 显著性

class FingerprintStatistics:
    """统计特征."""
    mean: float
    std: float
    cv: float                         # 变异系数
    quartiles: Tuple[float, float, float]  # 四分位数
    outlier_ratio: float              # 异常值比例

class FingerprintDynamics:
    """动态特征."""
    velocity_profile: np.ndarray      # 速度曲线
    acceleration_profile: np.ndarray  # 加速度曲线
    peak_count: int                   # 峰值数量
    valley_count: int                 # 谷值数量
```

#### 3.4.2 统一输出格式

```python
@dataclass
class MetricPayload:
    """统一检测项数据载体 - 打通训练/推理/生产."""

    # 元信息
    schema_version: str = "2.0.0"
    metric_id: str = ""
    action_id: str = ""
    source: Literal["training", "inference", "fingerprint"] = "inference"
    timestamp: str = ""

    # 四层数据（根据 source 选择性填充）
    definition: Optional[MetricDefinition] = None
    config: Optional[MetricConfig] = None
    runtime: Optional[MetricRuntime] = None
    fingerprint: Optional[MetricFingerprint] = None

    # 评估结果
    evaluation: Optional[ThresholdEvaluation] = None
    errors: List[ErrorDetection] = field(default_factory=list)

    # 阶段信息
    phase_info: Optional[PhaseInfo] = None

@dataclass
class ErrorDetection:
    """错误识别结果."""
    error_id: str
    error_name: str
    description: str
    severity: Literal["low", "medium", "high", "critical"]
    phase: Optional[str] = None
    key_frame: Optional[int] = None
    key_value: Optional[float] = None
    confidence: float = 1.0

@dataclass
class PhaseInfo:
    """阶段信息."""
    phase_id: str
    phase_name: str
    start_frame: int
    end_frame: int
    duration: float
    stability_score: float
```

### 3.5 配置一致性校验

#### 3.5.1 校验规则

```python
class ConfigValidator:
    """配置一致性校验器."""

    @staticmethod
    def validate_action_config(config: ActionConfig) -> ValidationResult:
        """
        校验动作配置的完整性.

        校验项：
        1. 所有 metric_id 必须在 METRIC_TEMPLATES 中存在
        2. 所有 evaluation_phase 必须在 phases 中存在
        3. error_conditions 中的 phase 引用必须有效
        4. thresholds 范围必须合理（excellent ⊆ good ⊆ pass）
        5. 必需关键点必须在 pose_model 中提供
        """
        pass

    @staticmethod
    def validate_template_consistency(
        template: ActionTemplate,
        definitions: Dict[str, MetricDefinition]
    ) -> ValidationResult:
        """校验模板与定义库的一致性."""
        pass
```

#### 3.5.2 校验配置

```python
@dataclass
class ValidationRule:
    """校验规则."""
    rule_id: str
    severity: Literal["error", "warning", "info"]
    check: Callable[[Any], bool]
    message: str

# 预定义校验规则
VALIDATION_RULES = [
    ValidationRule(
        rule_id="metric_id_exists",
        severity="error",
        check=lambda c: all(
            m.metric_id in METRIC_TEMPLATES
            for m in c.metrics
        ),
        message="检测项必须在定义库中存在"
    ),
    ValidationRule(
        rule_id="phase_reference_valid",
        severity="error",
        check=lambda c: all(
            m.evaluation_phase in {p.phase_id for p in c.phases}
            for m in c.metrics
        ),
        message="评估阶段必须在动作阶段定义中存在"
    ),
    ValidationRule(
        rule_id="threshold_range_consistency",
        severity="warning",
        check=lambda c: all(
            _check_threshold_consistency(m.thresholds)
            for m in c.metrics
        ),
        message="阈值范围应满足: excellent ⊆ good ⊆ pass"
    ),
]
```

### 3.6 实时分析接口

#### 3.6.1 实时分析器

```python
class RealtimeAnalyzer:
    """实时动作分析器（逐帧/滑窗）."""

    def __init__(
        self,
        action_config: ActionConfig,
        window_size: int = 30,           # 滑窗大小（帧）
        overlap: float = 0.5,            # 滑窗重叠率
    ):
        self.action_config = action_config
        self.phase_engine = PhaseEngine(action_config.phases)
        self.rep_counter = RepCounter(action_config.cycle_definition)
        self.metrics_engine = MetricsEngine(action_config.metrics)

        # 状态维护
        self.frame_buffer: deque = deque(maxlen=window_size)
        self.phase_history: List[PhaseDetection] = []
        self.current_rep: Optional[Rep] = None

    def process_frame(
        self,
        frame: PoseFrame
    ) -> RealtimeResult:
        """
        处理单帧，输出实时结果.

        返回：
        - current_phase: 当前阶段
        - rep_count: 当前计数
        - active_errors: 当前活跃错误
        - metric_values: 当前检测项值
        """
        pass

    def process_window(
        self,
        window: PoseSequence
    ) -> WindowResult:
        """处理滑窗，输出窗口分析结果."""
        pass

@dataclass
class RealtimeResult:
    """实时分析结果."""
    frame_id: int
    timestamp: float
    current_phase: Optional[PhaseInfo]
    rep_count: int
    rep_progress: float              # 当前周期进度 (0-1)
    metric_values: Dict[str, float]  # 当前帧检测项值
    active_errors: List[ErrorDetection]
    stability_score: float
```

---

## 4. 接口设计

### 4.1 批量分析接口（保持兼容）

```python
# 保持现有接口不变
class BatchAnalyzer:
    """批量视频分析器（完整视频处理）."""

    async def analyze(
        self,
        video_path: str,
        action_id: str,
        config_version: Optional[str] = None,
    ) -> AnalysisResult:
        """分析完整视频."""
        pass
```

### 4.2 实时分析接口（新增）

```python
class StreamingAnalyzer:
    """流式分析器（逐帧处理）."""

    async def create_stream(
        self,
        action_id: str,
        callback: Callable[[RealtimeResult], None],
    ) -> StreamContext:
        """创建分析流."""
        pass

    async def process_frame(
        self,
        stream_id: str,
        frame: PoseFrame,
    ) -> RealtimeResult:
        """处理单帧."""
        pass
```

### 4.3 训练接口

```python
class TrainingPipeline:
    """训练流水线."""

    async def train(
        self,
        action_id: str,
        standard_videos: List[str],
        error_videos: Dict[str, List[str]],  # error_type -> videos
        config: TrainingConfig,
    ) -> TrainingResult:
        """
        训练动作配置.

        产出：
        - thresholds: 基于统计的阈值参数
        - error_conditions: 基于对比学习的错误条件
        - fingerprint: 标准动作特征指纹
        - quality_report: 训练质量报告
        """
        pass
```

---

## 5. 实施计划

### 5.1 实施优先级

| 优先级 | 模块 | 任务 | 工作量 | 依赖 |
|--------|------|------|--------|------|
| P0 | PhaseEngine | 实现配置驱动的阶段引擎 | 3d | - |
| P0 | RepCounter | 实现基于阶段序列的计数器 | 2d | PhaseEngine |
| P0 | ThresholdEvaluator | 实现阈值评估引擎 | 2d | - |
| P0 | ActionAnalyzer | 整合各模块，统一调度 | 3d | 上述模块 |
| P1 | ConfigValidator | 实现配置一致性校验 | 2d | - |
| P1 | MetricPayload | 统一数据格式 | 2d | - |
| P1 | RealtimeAnalyzer | 实时分析接口 | 3d | ActionAnalyzer |
| P2 | TrainingPipeline | 训练接口适配 | 2d | MetricPayload |

### 5.2 关键改造点

#### 5.2.1 替换阶段检测（P0）

```python
# 改造前（calculator.py）
from src.core.phases.squat_phases import create_phase_detector
phase_detector = create_phase_detector(action_name)

# 改造后
from src.core.phases.engine import PhaseEngine
phase_engine = PhaseEngine(self._action_config.phases)
```

#### 5.2.2 添加阈值评估（P0）

```python
# 在 calculator.py 中添加
threshold_evaluator = ThresholdEvaluator()
evaluation = threshold_evaluator.evaluate(
    key_value,
    metric_config.thresholds
)
result["evaluation"] = evaluation
```

#### 5.2.3 添加动作计数（P0）

```python
# 在 ActionAnalyzer 中添加
rep_counter = RepCounter(self._action_config.cycle_definition)
rep_result = rep_counter.count(phase_sequence)
result["rep_count"] = rep_result.count
result["rep_ranges"] = rep_result.ranges
```

---

## 6. 验证方案

### 6.1 单元测试

```python
# PhaseEngine 测试
class TestPhaseEngine:
    def test_phase_detection_from_config(self): ...
    def test_fsm_state_transitions(self): ...
    def test_key_frame_extraction(self): ...

# RepCounter 测试
class TestRepCounter:
    def test_cycle_recognition(self): ...
    def test_partial_cycle_handling(self): ...
    def test_min_duration_filter(self): ...

# ThresholdEvaluator 测试
class TestThresholdEvaluator:
    def test_grade_calculation(self): ...
    def test_score_normalization(self): ...
    def test_symmetry_evaluation(self): ...
```

### 6.2 集成测试

```python
# 端到端测试
class TestActionAnalyzer:
    def test_squat_analysis(self): ...
    def test_side_leg_raise_analysis(self): ...
    def test_custom_action_analysis(self): ...
```

---

## 7. 附录

### 7.1 数据流图

```
训练流程：
Standard Videos -> Pose Estimation -> Feature Extraction ->
Fingerprint Generation -> Threshold Learning -> Error Learning ->
ActionConfig (trained) -> Validation -> Storage

推理流程：
Video -> Pose Estimation -> Phase Detection -> Rep Counting ->
Metric Calculation -> Threshold Evaluation -> Error Detection ->
Result Aggregation -> Output

实时流程：
Frame Stream -> Pose Estimation -> Window Aggregation ->
Phase Tracking -> Incremental Counting -> Real-time Metrics ->
Error Trigger -> Callback
```

### 7.2 名词对照

| 中文 | 英文 | 含义 |
|------|------|------|
| 检测项 | Metric | 可计算的生物力学指标 |
| 阶段 | Phase | 动作的时间子段（如"下蹲""站起"） |
| 周期 | Cycle/Rep | 一个完整的动作重复 |
| 阈值 | Threshold | 评判动作质量的数值边界 |
| 错误条件 | Error Condition | 触发错误识别的规则 |
| 指纹 | Fingerprint | 标准动作的特征模板 |
| 评估 | Evaluation | 基于阈值的等级判定 |

---

**文档版本**: 1.0.0  
**最后更新**: 2026-04-14  
**状态**: 待审核
