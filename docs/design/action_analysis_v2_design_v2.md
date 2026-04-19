# 动作分析系统 V2 设计方案（务实版）

## 修订记录

| 版本 | 日期 | 修订内容 | 作者 |
|------|------|----------|------|
| 2.0.0 | 2026-04-14 | 针对兼容性和工程问题全面重构 | System |

---

## 1. 问题回顾与解决策略

### 1.1 已识别问题及对策

| 严重度 | 问题 | 对策 |
|--------|------|------|
| **高** | PhaseEngine DSL 与现有配置不兼容 | **兼容层设计**：V1配置自动转换到V2 DSL，老配置无需修改即可运行 |
| **高** | RepCounter 缺少 cycle_definition 迁移方案 | **向后兼容**：cycle_definition为可选字段，提供自动生成规则 |
| **高** | MetricPayload 过于臃肿影响性能 | **视图拆分**：InternalFullPayload(内部计算) + ExternalCompactPayload(API输出) |
| **高** | 工期偏乐观，未计入兼容验证 | **两轨并行**：功能开发轨 + 兼容验证轨，P0后必须灰度 |
| **中** | 阈值模型定义冲突 | **优先级规范**：明确 excellent>good>pass>fail，normal_range仅用于告警 |
| **中** | 阶段值策略冲突 | **别名策略**：any改为多阶段评估，peak改为极值检测；别名仅用于校验提示 |
| **中** | 实时接口缺少工程约束 | **SLO定义**：明确延迟预算、背压、掉帧处理策略 |
| **中** | API兼容性策略缺失 | **显式版本**：api_version字段，响应兼容层设计 |
| **低** | 验证方案不完整 | **三类必测**：配置迁移回归集、跨动作基线集、性能压测 |

---

## 2. 核心架构设计

### 2.1 架构原则

1. **向后兼容优先**：老配置无需修改即可运行，新功能通过配置显式开启
2. **渐进式迁移**：V1/V2 双版本并行，灰度切换
3. **性能隔离**：内部计算与外部传输数据模型分离
4. **可观测性**：全流程埋点，支持灰度对比验证

### 2.2 系统架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          动作分析系统 V2（务实架构）                          │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │                        兼容适配层 (Compatibility Layer)                 │ │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐ │ │
│  │  │ V1 Config       │  │ Phase DSL       │  │ Cycle Definition       │ │ │
│  │  │ Transformer     │  │ Converter       │  │ Generator              │ │ │
│  │  │ (自动升级)       │  │ (参数转换)       │  │ (默认推断)              │ │ │
│  │  └────────┬────────┘  └────────┬────────┘  └────────┬────────────────┘ │ │
│  │           └────────────────────┴────────────────────┘                  │ │
│  │                              │                                         │ │
│  │                              ▼                                         │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐   │ │
│  │  │                     统一配置模型 (Unified Config)                 │   │ │
│  │  │  ActionConfig { phases[], metrics[], cycle_definition?, version } │   │ │
│  │  └─────────────────────────────────────────────────────────────────┘   │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                    │                                        │
│                                    ▼                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │                        核心引擎层 (Core Engine)                        │ │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐             │ │
│  │  │ Phase Engine  │  │ Rep Counter   │  │ Metric Engine │             │ │
│  │  │ (V2 DSL驱动)   │  │ (周期识别)     │  │ (检测项计算)   │             │ │
│  │  └───────┬───────┘  └───────┬───────┘  └───────┬───────┘             │ │
│  │          │                  │                  │                      │ │
│  │          └──────────────────┴──────────────────┘                      │ │
│  │                             │                                         │ │
│  │                             ▼                                         │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐  │ │
│  │  │                    评估引擎 (Evaluation Engine)                  │  │ │
│  │  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │  │ │
│  │  │  │ Threshold   │  │ Error       │  │ Grade                   │  │  │ │
│  │  │  │ Evaluator   │  │ Detector    │  │ Calculator              │  │  │ │
│  │  │  └─────────────┘  └─────────────┘  └─────────────────────────┘  │  │ │
│  │  └─────────────────────────────────────────────────────────────────┘  │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                    │                                        │
│                                    ▼                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │                      数据视图层 (Data View Layer)                      │ │
│  │  ┌─────────────────────────┐  ┌─────────────────────────────────────┐ │ │
│  │  │ InternalFullPayload     │  │ ExternalCompactPayload              │ │ │
│  │  │ (内部计算使用)           │  │ (API输出/实时传输)                   │ │ │
│  │  │ - 包含全量数据           │  │ - 仅传输必需字段                     │ │ │
│  │  │ - np.ndarray 支持        │  │ - 数组序列化为统计值                  │ │ │
│  │  │ - 中间状态缓存           │  │ - 体积减少~80%                       │ │ │
│  │  └─────────────────────────┘  └─────────────────────────────────────┘ │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│                                    │                                        │
│                                    ▼                                        │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │                      输出接口层 (API Layer)                            │ │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌──────────────┐ │ │
│  │  │ Batch API   │  │ Stream API  │  │ Train API   │  │ Admin API    │ │ │
│  │  │ api_version │  │ SLO监控     │  │ 迭代反馈     │  │ 灰度控制      │ │ │
│  │  │ v1/v2兼容   │  │ 背压/降级    │  │            │  │             │ │ │
│  │  └─────────────┘  └─────────────┘  └─────────────┘  └──────────────┘ │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. 详细设计

### 3.1 兼容适配层设计

#### 3.1.1 V1/V2 配置版本管理

```python
# ActionConfig 模型（向后兼容）
class ActionConfig(BaseModel):
    """动作配置 - 支持 V1/V2 双版本."""
    
    # 版本标识（新增）
    schema_version: str = Field(default="1.0.0", description="配置schema版本")
    
    # 基础信息（V1/V2 兼容）
    action_id: str
    action_name: str
    action_name_zh: str
    description: str
    version: str
    
    # 阶段定义（V1格式，自动转换）
    phases: List[PhaseDefinition]
    
    # 检测项配置（V1/V2 兼容）
    metrics: List[MetricConfig]
    
    # 全局参数（V1/V2 兼容）
    global_params: Dict[str, Any] = Field(default_factory=dict)
    
    # 周期定义（V2新增，可选）
    cycle_definition: Optional[CycleDefinition] = None
    
    # 元数据（V1/V2 兼容）
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    @validator('schema_version')
    def validate_version(cls, v):
        supported = ["1.0.0", "2.0.0"]
        if v not in supported:
            raise ValueError(f"不支持的schema版本: {v}, 支持的版本: {supported}")
        return v
    
    def to_v2(self) -> "ActionConfigV2":
        """升级到V2格式（自动转换）."""
        return ConfigTransformer.v1_to_v2(self)
```

#### 3.1.2 Phase DSL 兼容转换器

```python
class PhaseDSLConverter:
    """阶段配置 V1 -> V2 转换器."""
    
    # V1 detection_params 到 V2 entry_conditions 映射表
    V1_TO_V2_CONDITION_MAP = {
        # 速度阈值 -> DERIVATIVE 条件
        "velocity_threshold": {
            "type": "DERIVATIVE",
            "order": 1,  # 一阶导数
            "operator_mapping": {
                "positive": "gt",
                "negative": "lt"
            }
        },
        # 位置阈值 -> THRESHOLD 条件
        "hip_abduction_threshold": {
            "type": "THRESHOLD",
            "metric": "hip_abduction",
            "operator": "gte"
        },
        "position": {
            "type": "STATE",
            "field": "position"
        },
        # 持续时间 -> DURATION 条件
        "min_duration": {
            "type": "DURATION",
            "field": "min_duration"
        },
        "stability_window": {
            "type": "STABILITY",
            "window": "stability_window"
        },
    }
    
    @classmethod
    def convert(cls, v1_phases: List[PhaseDefinitionV1]) -> List[PhaseDefinitionV2]:
        """将V1阶段配置转换为V2 DSL格式."""
        v2_phases = []
        
        for i, v1_phase in enumerate(v1_phases):
            v2_phase = PhaseDefinitionV2(
                phase_id=v1_phase.phase_id,
                phase_name=v1_phase.phase_name,
                description=v1_phase.description,
            )
            
            # 转换 detection_params 到 entry_conditions
            if v1_phase.detection_params:
                v2_phase.entry_conditions = cls._convert_detection_params(
                    v1_phase.detection_params,
                    is_entry=True
                )
                
                # 推断 exit_conditions（基于下一个阶段）
                if i < len(v1_phases) - 1:
                    next_phase = v1_phases[i + 1]
                    if next_phase.detection_params:
                        v2_phase.exit_conditions = cls._convert_detection_params(
                            next_phase.detection_params,
                            is_entry=False
                        )
            
            v2_phases.append(v2_phase)
        
        return v2_phases
    
    @classmethod
    def _convert_detection_params(
        cls,
        params: Dict[str, Any],
        is_entry: bool
    ) -> List[ConditionV2]:
        """转换检测参数为条件列表."""
        conditions = []
        
        for param_name, param_value in params.items():
            mapping = cls.V1_TO_V2_CONDITION_MAP.get(param_name)
            if mapping:
                condition = cls._create_condition(mapping, param_value, is_entry)
                if condition:
                    conditions.append(condition)
        
        return conditions
```

#### 3.1.3 Cycle Definition 自动生成（降级为建议器）

```python
class CycleDefinitionSuggester:
    """
    周期定义建议器（迁移期辅助工具，非主路径）.
    
    设计原则：
    1. 不以动作ID硬编码作为主来源，避免退回"动作白名单"模式
    2. 仅作为配置初始化/迁移期的建议，最终必须显式配置
    3. 所有生成的定义需经过完整可达性校验
    4. 无法生成有效建议时返回 None（不强制推断）
    """
    
    # 阶段语义模式库（按语义分组，非动作ID）
    # 用于启发式建议，不用于自动匹配
    SEMANTIC_PATTERNS = {
        "closed_loop": {
            "description": "闭环动作（回到起点）",
            "phase_markers": {
                "start": ["start", "initial", "ready", "setup"],
                "execution": ["action", "movement", "dynamic"],
                "peak": ["peak", "top", "bottom", "max", "min"],
                "end": ["end", "finish", "complete", "return"]
            }
        },
        "open_sequence": {
            "description": "开环序列（单向执行）",
            "phase_markers": {
                "start": ["start"],
                "middle": ["process", "execution"],
                "end": ["end"]
            }
        },
        "hold_based": {
            "description": "保持型动作（hold为核心）",
            "phase_markers": {
                "entry": ["start", "enter"],
                "hold": ["hold", "static", "maintain"],
                "exit": ["release", "end", "exit"]
            }
        }
    }
    
    @classmethod
    def suggest(
        cls,
        phases: List[PhaseDefinition],
        action_type_hint: Optional[str] = None
    ) -> Tuple[Optional[CycleDefinition], List[str]]:
        """
        建议周期定义（仅建议，不自动应用）.
        
        返回：
        - suggested_definition: 建议的周期定义（可能为 None）
        - warnings: 建议过程中的警告信息
        
        使用场景：
        1. 配置初始化时提示用户
        2. 配置迁移时生成候选
        3. 配置校验时提示缺失
        """
        warnings = []
        phase_ids = [p.phase_id for p in phases]
        
        # 1. 基础校验
        if len(phases) < 2:
            warnings.append("阶段数量少于2，无法形成有效周期")
            return None, warnings
        
        # 2. 基于阶段名称语义推断
        suggested = cls._infer_by_semantics(phases, warnings)
        
        if suggested:
            # 3. 完整可达性校验
            is_valid, validation_warnings = cls._validate_reachability(
                suggested, phases
            )
            warnings.extend(validation_warnings)
            
            if is_valid:
                return suggested, warnings
        
        return None, warnings
    
    @classmethod
    def _infer_by_semantics(
        cls,
        phases: List[PhaseDefinition],
        warnings: List[str]
    ) -> Optional[CycleDefinition]:
        """基于阶段名称语义推断周期定义."""
        phase_ids = [p.phase_id for p in phases]
        
        # 查找语义标记
        markers = cls._find_semantic_markers(phase_ids)
        
        if not markers.get("start"):
            warnings.append("未找到明确的起始阶段标记（如 start/initial/ready）")
            return None
        
        # 推断周期结构
        start_phase = markers["start"]
        end_phase = markers.get("end", start_phase)  # 默认闭环
        
        # 识别关键阶段（优先使用 peak/hold 类标记）
        required_phases = []
        if markers.get("peak"):
            required_phases.append(markers["peak"])
        elif markers.get("hold"):
            required_phases.append(markers["hold"])
        else:
            # 使用中间阶段作为关键阶段
            mid_idx = len(phase_ids) // 2
            required_phases.append(phase_ids[mid_idx])
            warnings.append(f"未识别关键阶段，使用中间阶段 {phase_ids[mid_idx]} 作为 required_phase")
        
        return CycleDefinition(
            phase_sequence=phase_ids,
            start_phase=start_phase,
            end_phase=end_phase,
            required_phases=required_phases,
            cycle_mode=CycleMode.CLOSED if end_phase == start_phase else CycleMode.OPEN
        )
    
    @classmethod
    def _find_semantic_markers(cls, phase_ids: List[str]) -> Dict[str, str]:
        """查找阶段语义标记."""
        markers = {}
        
        for pattern_name, pattern in cls.SEMANTIC_PATTERNS.items():
            for marker_type, candidates in pattern["phase_markers"].items():
                for phase_id in phase_ids:
                    if any(c in phase_id.lower() for c in candidates):
                        if marker_type not in markers:  # 保留第一个匹配
                            markers[marker_type] = phase_id
        
        return markers
    
    @classmethod
    def _validate_reachability(
        cls,
        cycle_def: CycleDefinition,
        phases: List[PhaseDefinition]
    ) -> Tuple[bool, List[str]]:
        """
        校验周期定义的完整可达性.
        
        校验项：
        1. 所有引用的阶段必须在 phases 中存在
        2. start_phase 和 end_phase 必须在 phase_sequence 中
        3. required_phases 必须是 phase_sequence 的子集
        4. phase_sequence 中的阶段必须在 phases 中按顺序可达（通过 FSM）
        """
        warnings = []
        phase_ids = {p.phase_id for p in phases}
        sequence_set = set(cycle_def.phase_sequence)
        
        # 1. 存在性校验
        for ref_phase in [cycle_def.start_phase, cycle_def.end_phase] + cycle_def.required_phases:
            if ref_phase not in phase_ids:
                warnings.append(f"引用的阶段 '{ref_phase}' 不在可用阶段列表中")
                return False, warnings
        
        # 2. sequence 一致性校验
        if cycle_def.start_phase not in sequence_set:
            warnings.append(f"start_phase '{cycle_def.start_phase}' 不在 phase_sequence 中")
        if cycle_def.end_phase not in sequence_set:
            warnings.append(f"end_phase '{cycle_def.end_phase}' 不在 phase_sequence 中")
        
        for req in cycle_def.required_phases:
            if req not in sequence_set:
                warnings.append(f"required_phase '{req}' 不在 phase_sequence 中")
        
        # 3. FSM 可达性校验（简化版：检查阶段转换是否合理）
        # 实际实现应基于 PhaseEngine 的 FSM 验证
        
        return len(warnings) == 0, warnings


# ActionConfig 中的 cycle_definition 处理（更新）
class ActionConfig(BaseModel):
    """动作配置 - cycle_definition 处理逻辑."""
    
    # ... 其他字段 ...
    
    cycle_definition: Optional[CycleDefinition] = None
    
    def __post_init__(self):
        """配置后处理：不自动生成，仅校验和提示."""
        if self.cycle_definition is None:
            # 不自动生成！仅提供建议
            suggested, warnings = CycleDefinitionSuggester.suggest(self.phases)
            if suggested:
                logger.info(
                    f"动作 {self.action_id} 缺少 cycle_definition，建议配置：\n"
                    f"{suggested.json(indent=2)}"
                )
            for w in warnings:
                logger.warning(f"周期定义建议 [{self.action_id}]: {w}")
    
    def validate_for_inference(self) -> ValidationResult:
        """
        推理前校验.
        
        规则：
        - cycle_definition 为 None：允许，但 rep_count 功能不启用
        - cycle_definition 存在：必须经过完整可达性校验
        """
        if self.cycle_definition is None:
            return ValidationResult(
                valid=True,
                warnings=["未配置 cycle_definition，动作计数功能不可用"]
            )
        
        # 完整校验
        is_valid, warnings = CycleDefinitionSuggester._validate_reachability(
            self.cycle_definition, self.phases
        )
        
        return ValidationResult(valid=is_valid, warnings=warnings)
```

### 3.2 Phase Engine V2 设计

#### 3.2.1 V2 阶段定义 DSL

```python
# V2 阶段定义（完整DSL）
class PhaseDefinitionV2(BaseModel):
    """阶段定义 V2（完整DSL支持）."""
    
    phase_id: str
    phase_name: str
    description: Optional[str] = None
    
    # 进入条件（OR关系，任一满足即可进入）
    entry_conditions: List[Condition] = Field(default_factory=list)
    
    # 退出条件（OR关系，任一满足即退出）
    exit_conditions: List[Condition] = Field(default_factory=list)
    
    # 稳定性检查（AND关系，进入后持续检查）
    stability_checks: List[StabilityCheck] = Field(default_factory=list)
    
    # 最大持续时间（秒，超过自动退出）
    max_duration: Optional[float] = None
    
    # 最小持续时间（秒，低于不算有效阶段）
    min_duration: Optional[float] = None


class Condition(BaseModel):
    """条件定义（支持多种类型）."""
    
    type: ConditionType  # THRESHOLD / DERIVATIVE / EXTREMUM / DURATION / COMPOUND
    
    # 通用字段
    metric: Optional[str] = None  # 关联检测项
    
    # THRESHOLD 类型
    operator: Optional[Operator] = None  # gt/gte/lt/lte/eq
    value: Optional[float] = None
    
    # DERIVATIVE 类型
    order: Optional[int] = None  # 1=速度, 2=加速度
    derivative_operator: Optional[Operator] = None
    derivative_threshold: Optional[float] = None
    
    # EXTREMUM 类型
    extremum_type: Optional[ExtremumType] = None  # min/max
    window: Optional[int] = None  # 窗口大小
    
    # DURATION 类型
    duration_min: Optional[float] = None
    duration_max: Optional[float] = None
    
    # COMPOUND 类型
    logic: Optional[LogicType] = None  # AND/OR
    sub_conditions: List["Condition"] = Field(default_factory=list)
    
    # 可选：持续帧数（防抖）
    persist_frames: int = 1


class StabilityCheck(BaseModel):
    """稳定性检查."""
    
    metric: str
    max_variance: float  # 最大方差
    window: int = 5  # 检查窗口
```

#### 3.2.2 Phase Engine 实现

```python
class PhaseEngine:
    """V2 阶段引擎（配置驱动）."""
    
    def __init__(
        self,
        phase_configs: List[PhaseDefinitionV2],
        metric_values: Dict[str, np.ndarray],
        fps: float = 30.0
    ):
        self.phase_configs = {p.phase_id: p for p in phase_configs}
        self.metric_values = metric_values
        self.fps = fps
        
        # 构建状态机
        self.fsm = self._build_fsm()
        
        # 状态跟踪
        self.current_state: Optional[str] = None
        self.state_start_frame: int = 0
        self.state_frame_count: int = 0
        
    def detect_phases(self) -> PhaseSequence:
        """检测阶段序列."""
        phase_detections = []
        
        for frame_idx in range(self._get_frame_count()):
            new_state = self._transition(frame_idx)
            
            if new_state != self.current_state:
                # 状态变化，记录上一阶段
                if self.current_state:
                    phase_detections.append(PhaseDetection(
                        phase_id=self.current_state,
                        start_frame=self.state_start_frame,
                        end_frame=frame_idx - 1,
                        duration=(frame_idx - self.state_start_frame) / self.fps
                    ))
                
                # 进入新状态
                self.current_state = new_state
                self.state_start_frame = frame_idx
                self.state_frame_count = 0
            else:
                self.state_frame_count += 1
        
        # 处理最后一个阶段
        if self.current_state:
            frame_idx = self._get_frame_count() - 1
            phase_detections.append(PhaseDetection(
                phase_id=self.current_state,
                start_frame=self.state_start_frame,
                end_frame=frame_idx,
                duration=(frame_idx - self.state_start_frame + 1) / self.fps
            ))
        
        return PhaseSequence(detections=phase_detections)
    
    def _transition(self, frame_idx: int) -> Optional[str]:
        """状态转换逻辑."""
        if self.current_state is None:
            # 初始状态：检查所有阶段的进入条件
            for phase_id, config in self.phase_configs.items():
                if self._check_entry_conditions(config, frame_idx):
                    return phase_id
            return None
        
        # 检查当前阶段的退出条件
        current_config = self.phase_configs[self.current_state]
        
        # 1. 检查最大持续时间
        if current_config.max_duration:
            duration = self.state_frame_count / self.fps
            if duration >= current_config.max_duration:
                return self._find_next_phase()
        
        # 2. 检查退出条件
        if self._check_exit_conditions(current_config, frame_idx):
            return self._find_next_phase()
        
        return self.current_state
    
    def _check_entry_conditions(
        self,
        config: PhaseDefinitionV2,
        frame_idx: int
    ) -> bool:
        """检查进入条件（OR关系）."""
        if not config.entry_conditions:
            return True
        return any(
            self._evaluate_condition(c, frame_idx)
            for c in config.entry_conditions
        )
    
    def _check_exit_conditions(
        self,
        config: PhaseDefinitionV2,
        frame_idx: int
    ) -> bool:
        """检查退出条件（OR关系）."""
        if not config.exit_conditions:
            # 无退出条件时，检查下一阶段的进入条件
            return False
        return any(
            self._evaluate_condition(c, frame_idx)
            for c in config.exit_conditions
        )
    
    def _evaluate_condition(
        self,
        condition: Condition,
        frame_idx: int
    ) -> bool:
        """评估单个条件."""
        if condition.type == ConditionType.THRESHOLD:
            return self._eval_threshold(condition, frame_idx)
        elif condition.type == ConditionType.DERIVATIVE:
            return self._eval_derivative(condition, frame_idx)
        elif condition.type == ConditionType.EXTREMUM:
            return self._eval_extremum(condition, frame_idx)
        elif condition.type == ConditionType.DURATION:
            return self._eval_duration(condition)
        elif condition.type == ConditionType.COMPOUND:
            return self._eval_compound(condition, frame_idx)
        return False
```

### 3.3 Rep Counter 设计

#### 3.3.1 周期定义模型

```python
class CycleDefinition(BaseModel):
    """动作周期定义."""
    
    # 完整周期所需的阶段序列（有序）
    phase_sequence: List[str]
    
    # 起始阶段（可从中间开始，默认第一个）
    start_phase: Optional[str] = None
    
    # 结束阶段（回到起始或特定阶段，默认第一个形成闭环）
    end_phase: Optional[str] = None
    
    # 关键阶段（必须存在才算有效周期）
    required_phases: List[str] = Field(default_factory=list)
    
    # 循环模式
    cycle_mode: CycleMode = CycleMode.CLOSED
    
    # 时长限制
    min_cycle_duration: float = 1.0   # 秒，过滤抖动
    max_cycle_duration: float = 30.0  # 秒，过滤异常
    
    def __post_init__(self):
        # 默认值处理
        if self.start_phase is None and self.phase_sequence:
            self.start_phase = self.phase_sequence[0]
        if self.end_phase is None and self.phase_sequence:
            self.end_phase = self.phase_sequence[0]


class RepCountResult(BaseModel):
    """动作计数结果."""
    
    count: int  # 完成次数
    rep_ranges: List[Tuple[int, int]]  # 每个rep的帧范围 [(start, end), ...]
    partial_rep: Optional[Tuple[int, int]]  # 当前未完成的部分rep
    confidence: float  # 计数置信度（基于阶段完整性）
    
    # 每个rep的详细信息
    rep_details: List[RepDetail] = Field(default_factory=list)


class RepDetail(BaseModel):
    """单次重复详细信息."""
    
    rep_index: int
    start_frame: int
    end_frame: int
    duration: float
    phases_completed: List[str]  # 实际完成的阶段
    phase_durations: Dict[str, float]  # 各阶段时长
    quality_score: float  # 质量评分（基于阶段完整性）
```

#### 3.3.2 Rep Counter 实现

```python
class RepCounter:
    """基于阶段序列的动作计数器."""
    
    def __init__(
        self,
        cycle_definition: Optional[CycleDefinition] = None
    ):
        self.cycle_def = cycle_definition
    
    def count(self, phase_sequence: PhaseSequence) -> RepCountResult:
        """
        基于阶段序列识别完整周期.
        
        算法：
        1. 查找 start_phase 出现位置
        2. 从start开始跟踪阶段序列
        3. 检查 required_phases 是否都出现
        4. 到达 end_phase 时计数+1
        5. 应用时长过滤
        """
        if not self.cycle_def:
            return RepCountResult(count=0, rep_ranges=[], confidence=0.0)
        
        reps = []
        current_rep_start = None
        phases_in_current = set()
        
        for detection in phase_sequence.detections:
            # 检测阶段变化
            if detection.phase_id == self.cycle_def.start_phase:
                # 新的rep开始
                if current_rep_start is not None:
                    # 上一rep未正常结束，视为不完整
                    pass
                current_rep_start = detection.start_frame
                phases_in_current = {detection.phase_id}
            
            elif current_rep_start is not None:
                phases_in_current.add(detection.phase_id)
                
                # 检查是否到达结束阶段
                if detection.phase_id == self.cycle_def.end_phase:
                    # 检查必需阶段
                    if self._check_required_phases(phases_in_current):
                        duration = (detection.end_frame - current_rep_start) / 30.0
                        
                        # 时长过滤
                        if self.cycle_def.min_cycle_duration <= duration <= self.cycle_def.max_cycle_duration:
                            reps.append((current_rep_start, detection.end_frame))
                    
                    current_rep_start = None
                    phases_in_current = set()
        
        # 处理未完成的rep
        partial = None
        if current_rep_start is not None:
            partial = (current_rep_start, phase_sequence.detections[-1].end_frame if phase_sequence.detections else current_rep_start)
        
        return RepCountResult(
            count=len(reps),
            rep_ranges=reps,
            partial_rep=partial,
            confidence=self._calculate_confidence(reps, phase_sequence),
            rep_details=self._generate_rep_details(reps, phase_sequence)
        )
    
    def _check_required_phases(self, phases: Set[str]) -> bool:
        """检查必需阶段是否都出现."""
        return all(
            req in phases
            for req in self.cycle_def.required_phases
        )
```

### 3.4 阈值评估引擎

#### 3.4.1 阈值判定优先级规范

```python
class ThresholdEvaluator:
    """
    阈值评估引擎 - 明确优先级规范.
    
    判定优先级（从高到低）：
    1. excellent_range: 优秀区间（最高等级）
    2. good_range: 良好区间（次高等级）
    3. pass_range: 及格区间（最低通过等级）
    4. fail: 不及格（不在上述区间）
    
    normal_range 用途：
    - 仅用于告警/提示（如"偏离正常范围"）
    - 不参与评分等级计算
    - 可用于训练时的数据过滤
    
    区间包含规则：
    - excellent_range ⊆ good_range ⊆ pass_range
    - 若配置违反包含关系，按最小有效区间处理
    """
    
    GRADE_PRIORITY = ["excellent", "good", "pass", "fail"]
    
    def evaluate(
        self,
        value: float,
        thresholds: MetricThreshold
    ) -> ThresholdEvaluation:
        """评估数值所属的等级."""
        
        # 检查区间包含关系，修复不一致配置
        effective_ranges = self._normalize_ranges(thresholds)
        
        # 按优先级判定
        if effective_ranges["excellent"] and self._in_range(value, effective_ranges["excellent"]):
            grade = "excellent"
            score = self._calc_score_in_range(value, effective_ranges["excellent"], thresholds.target_value)
        elif effective_ranges["good"] and self._in_range(value, effective_ranges["good"]):
            grade = "good"
            score = 80 + self._calc_score_in_range(value, effective_ranges["good"], thresholds.target_value) * 0.15
        elif effective_ranges["pass"] and self._in_range(value, effective_ranges["pass"]):
            grade = "pass"
            score = 60 + self._calc_score_in_range(value, effective_ranges["pass"], thresholds.target_value) * 0.18
        else:
            grade = "fail"
            score = self._calc_fail_score(value, effective_ranges["pass"], thresholds.target_value)
        
        # normal_range 告警（不参与评分）
        normal_warning = None
        if thresholds.normal_range and not self._in_range(value, thresholds.normal_range):
            normal_warning = f"值 {value:.1f} 偏离正常范围 {thresholds.normal_range}"
        
        return ThresholdEvaluation(
            grade=grade,
            score=round(score, 1),
            deviation=self._calc_deviation(value, thresholds.target_value),
            normalized_score=round(score / 100, 2),
            description=self._generate_description(grade, value, thresholds),
            normal_warning=normal_warning  # 仅告警，不影响等级
        )
    
    def _normalize_ranges(
        self,
        thresholds: MetricThreshold
    ) -> Dict[str, Optional[Tuple[float, float]]]:
        """
        规范化区间，确保包含关系.
        
        若 excellent 不完全包含于 good，取交集
        若 good 不完全包含于 pass，取交集
        """
        ranges = {
            "excellent": thresholds.excellent_range,
            "good": thresholds.good_range,
            "pass": thresholds.pass_range
        }
        
        # 确保包含关系（从内到外）
        if ranges["excellent"] and ranges["good"]:
            ranges["good"] = self._extend_to_contain(ranges["good"], ranges["excellent"])
        
        if ranges["good"] and ranges["pass"]:
            ranges["pass"] = self._extend_to_contain(ranges["pass"], ranges["good"])
        
        return ranges
```

### 3.5 阶段别名映射表（限定边界：仅用于配置校验与迁移提示）

```python
# 阶段别名映射表（限定使用边界）
# 用途：仅用于配置校验和迁移提示，核心引擎不应 silently 改写语义
# 设计原则：
# 1. 同义词映射：将常见变体映射到标准名称（如 "up" -> "ascent"）
# 2. 明确不支持：any/peak 等抽象别名不直接解析，而是提示用户显式配置
# 3. 核心引擎：只接受显式阶段ID，不应用任何别名解析

PHASE_ALIAS_MAP = {
    # === 同义词映射（明确的一对一或多对一）===
    # 起始阶段
    "start": ["start", "initial", "ready", "setup", "begin"],
    
    # 上升/伸展阶段
    "ascent": ["ascent", "up", "lift", "raise", "stand", "extend"],
    
    # 下降/屈曲阶段
    "descent": ["descent", "down", "lower", "drop", "squat", "flex"],
    
    # 保持阶段
    "hold": ["hold", "static", "maintain", "pause", "isometric"],
    
    # 结束阶段
    "end": ["end", "finish", "complete", "return", "reset"],
}

# 抽象别名（不支持直接解析，仅用于提示）
ABSTRACT_ALIASES = {
    "any": {
        "description": "任意阶段（表示该检测项在所有阶段都评估）",
        "recommendation": "如需多阶段评估，请在配置中明确列出阶段列表",
        "supported": False
    },
    "peak": {
        "description": "极值点阶段（动作幅度最大处）",
        "recommendation": "请显式配置为 bottom/top/max/min 等具体阶段",
        "supported": False
    },
    "execution": {
        "description": "动态执行阶段（非起始/结束的中间过程）",
        "recommendation": "请显式配置为 lift/lower/descent/ascent 等具体阶段",
        "supported": False
    },
    "transition": {
        "description": "过渡阶段（阶段转换过程）",
        "recommendation": "过渡阶段检测逻辑复杂，建议拆分为具体阶段",
        "supported": False
    }
}


class PhaseAliasResolver:
    """
    阶段别名解析器 - 限定边界：仅用于配置校验与迁移提示.
    
    核心原则：
    1. 不修改核心引擎：MetricsCalculator/PhaseEngine 只接受显式阶段ID
    2. 配置时提示：在校验和迁移时提示用户规范化命名
    3. 抽象别名明确拒绝：any/peak/execution 等直接报错，要求显式配置
    """
    
    @classmethod
    def normalize_for_migration(
        cls,
        phase_id: str,
        available_phases: List[str]
    ) -> Tuple[str, List[str]]:
        """
        迁移时规范化阶段名称（仅提示，不强制修改）.
        
        返回：
        - normalized_id: 建议的规范化名称
        - warnings: 警告/提示信息
        """
        warnings = []
        
        # 1. 检查是否已是有效阶段
        if phase_id in available_phases:
            return phase_id, warnings
        
        # 2. 检查是否为抽象别名（明确不支持）
        if phase_id in ABSTRACT_ALIASES:
            info = ABSTRACT_ALIASES[phase_id]
            warnings.append(
                f"阶段 '{phase_id}' 是抽象别名，不支持自动解析。"
                f"建议：{info['recommendation']}"
            )
            return phase_id, warnings  # 返回原值，不自动映射
        
        # 3. 尝试同义词映射
        for canonical, synonyms in PHASE_ALIAS_MAP.items():
            if phase_id.lower() in [s.lower() for s in synonyms]:
                if canonical in available_phases:
                    warnings.append(
                        f"阶段 '{phase_id}' 建议规范化为 '{canonical}'"
                    )
                    return canonical, warnings
        
        # 4. 无匹配
        warnings.append(f"阶段 '{phase_id}' 未识别，请确保名称正确")
        return phase_id, warnings
    
    @classmethod
    def validate_metric_config(
        cls,
        metric_config: MetricConfig,
        available_phases: List[str]
    ) -> ValidationResult:
        """
        校验检测项配置中的 evaluation_phase.
        
        校验规则：
        1. evaluation_phase 必须在 available_phases 中（不支持别名）
        2. 如果是抽象别名，明确报错
        3. 如果是同义词变体，提示规范化建议
        """
        warnings = []
        errors = []
        
        eval_phase = metric_config.evaluation_phase
        
        # 1. 直接存在检查
        if eval_phase in available_phases:
            return ValidationResult(valid=True, warnings=warnings, errors=errors)
        
        # 2. 抽象别名检查（明确报错）
        if eval_phase in ABSTRACT_ALIASES:
            info = ABSTRACT_ALIASES[eval_phase]
            errors.append(
                f"检测项 '{metric_config.metric_id}' 使用了抽象别名 '{eval_phase}' 作为 evaluation_phase，"
                f"这是不支持的。{info['recommendation']}"
            )
            return ValidationResult(valid=False, warnings=warnings, errors=errors)
        
        # 3. 同义词检查（提示但不强制）
        normalized, alias_warnings = cls.normalize_for_migration(
            eval_phase, available_phases
        )
        warnings.extend(alias_warnings)
        
        if normalized not in available_phases:
            errors.append(
                f"检测项 '{metric_config.metric_id}' 的 evaluation_phase '{eval_phase}' "
                f"不在可用阶段列表 {available_phases} 中"
            )
            return ValidationResult(valid=False, warnings=warnings, errors=errors)
        
        return ValidationResult(valid=True, warnings=warnings, errors=errors)
    
    @classmethod
    def generate_migration_report(
        cls,
        action_config: ActionConfig
    ) -> Dict[str, Any]:
        """
        生成配置迁移报告.
        
        报告内容：
        - 阶段名称规范化建议
        - 抽象别名使用情况
        - 无法识别的阶段名称
        """
        available_phases = [p.phase_id for p in action_config.phases]
        report = {
            "action_id": action_config.action_id,
            "phase_normalization": [],
            "abstract_aliases": [],
            "unrecognized": [],
            "recommendations": []
        }
        
        # 检查所有 metrics 的 evaluation_phase
        for metric in action_config.metrics:
            eval_phase = metric.evaluation_phase
            
            # 抽象别名
            if eval_phase in ABSTRACT_ALIASES:
                report["abstract_aliases"].append({
                    "metric_id": metric.metric_id,
                    "alias": eval_phase,
                    "recommendation": ABSTRACT_ALIASES[eval_phase]["recommendation"]
                })
            # 同义词映射
            elif eval_phase not in available_phases:
                normalized, _ = cls.normalize_for_migration(
                    eval_phase, available_phases
                )
                if normalized in available_phases:
                    report["phase_normalization"].append({
                        "metric_id": metric.metric_id,
                        "original": eval_phase,
                        "suggested": normalized
                    })
                else:
                    report["unrecognized"].append({
                        "metric_id": metric.metric_id,
                        "phase": eval_phase
                    })
        
        return report


# 核心引擎中的阶段处理（明确拒绝别名）
class MetricsEngine:
    """检测项计算引擎 - 只接受显式阶段ID."""
    
    def __init__(self, action_config: ActionConfig):
        self.config = action_config
        self.available_phases = {p.phase_id for p in action_config.phases}
        
        # 预先校验所有 evaluation_phase
        self._validate_all_phases()
    
    def _validate_all_phases(self):
        """校验所有检测项的阶段配置."""
        for metric in self.config.metrics:
            if metric.evaluation_phase not in self.available_phases:
                raise ValueError(
                    f"检测项 '{metric.metric_id}' 的 evaluation_phase "
                    f"'{metric.evaluation_phase}' 不在可用阶段列表中。"
                    f"可用阶段: {self.available_phases}"
                )
    
    def evaluate_metric(
        self,
        metric_id: str,
        phase_id: str,  # 必须是显式阶段ID，不接受别名
        metric_values: np.ndarray
    ) -> MetricResult:
        """评估检测项 - 只接受显式阶段ID."""
        if phase_id not in self.available_phases:
            raise ValueError(f"未知的阶段 '{phase_id}'")
        
        # ... 评估逻辑 ...
        
        返回：
        - resolved_phase: 解析后的实际阶段
        - warnings: 警告信息列表
        """
        warnings = []
        alias = metric_config.evaluation_phase
        
        resolved = cls.resolve(alias, available_phases)
        
        if resolved is None:
            warnings.append(
                f"检测项 {metric_config.metric_id} 的 evaluation_phase '{alias}' "
                f"无法解析为可用阶段 {available_phases}"
            )
            # 降级使用第一个可用阶段
            resolved = available_phases[0] if available_phases else ""
        elif resolved != alias:
            warnings.append(
                f"检测项 {metric_config.metric_id} 的 evaluation_phase '{alias}' "
                f"已映射为 '{resolved}'"
            )
        
        return resolved, warnings
```

### 3.6 数据视图层设计

#### 3.6.1 内外视图拆分

```python
# ============================================================
# 内部完整视图（用于计算）
# ============================================================
class InternalMetricPayload(BaseModel):
    """内部完整数据载体 - 仅内部计算使用."""
    
    schema_version: str = "2.0.0"
    metric_id: str
    action_id: str
    
    # 完整定义
    definition: MetricDefinition
    
    # 完整配置
    config: MetricConfig
    
    # 完整运行时数据
    runtime: MetricRuntime  # 包含完整 values: np.ndarray
    
    # 指纹（可选）
    fingerprint: Optional[MetricFingerprint] = None
    
    # 完整评估结果
    evaluation: Optional[ThresholdEvaluation] = None
    errors: List[ErrorDetection] = Field(default_factory=list)
    
    # 阶段信息
    phase_info: Optional[PhaseInfo] = None
    
    class Config:
        arbitrary_types_allowed = True  # 允许 np.ndarray


# ============================================================
# 外部紧凑视图（用于API输出）
# ============================================================
class ExternalMetricPayload(BaseModel):
    """
    外部紧凑数据载体 - API输出/实时传输.
    
    相比内部视图，体积减少约80%：
    - values 数组转为统计值
    - definition 只保留基础信息
    - config 只保留评估所需字段
    """
    
    schema_version: str = "2.0.0"
    metric_id: str
    action_id: str
    
    # 基础定义（精简）
    name: str           # definition.name_zh
    category: str       # definition.category.value
    unit: str           # definition.unit
    
    # 运行时统计（替代完整values）
    statistics: MetricStatisticsCompact  # 精简统计
    key_frame_value: Optional[float] = None
    
    # 评估结果
    grade: Optional[str] = None  # evaluation.grade
    score: Optional[float] = None  # evaluation.score
    deviation: Optional[float] = None  # evaluation.deviation
    normal_warning: Optional[str] = None  # evaluation.normal_warning
    
    # 错误（精简）
    errors: List[ErrorDetectionCompact] = Field(default_factory=list)
    
    # 阶段
    evaluation_phase: Optional[str] = None
    
    @classmethod
    def from_internal(cls, internal: InternalMetricPayload) -> "ExternalMetricPayload":
        """从内部视图转换为外部视图."""
        return cls(
            metric_id=internal.metric_id,
            action_id=internal.action_id,
            name=internal.definition.name_zh,
            category=internal.definition.category.value,
            unit=internal.definition.unit,
            statistics=MetricStatisticsCompact.from_full(internal.runtime.statistics),
            key_frame_value=internal.runtime.key_frame_value,
            grade=internal.evaluation.grade if internal.evaluation else None,
            score=internal.evaluation.score if internal.evaluation else None,
            deviation=internal.evaluation.deviation if internal.evaluation else None,
            normal_warning=internal.evaluation.normal_warning if internal.evaluation else None,
            errors=[ErrorDetectionCompact.from_full(e) for e in internal.errors],
            evaluation_phase=internal.phase_info.phase_id if internal.phase_info else None
        )


class MetricStatisticsCompact(BaseModel):
    """精简统计信息."""
    mean: float
    std: float
    min: float
    max: float
    
    @classmethod
    def from_full(cls, stats: MetricStatistics) -> "MetricStatisticsCompact":
        return cls(
            mean=stats.mean,
            std=stats.std,
            min=stats.min,
            max=stats.max
        )


class ErrorDetectionCompact(BaseModel):
    """精简错误信息."""
    error_id: str
    severity: str
    
    @classmethod
    def from_full(cls, error: ErrorDetection) -> "ErrorDetectionCompact":
        return cls(
            error_id=error.error_id,
            severity=error.severity
        )
```

### 3.7 实时接口设计

#### 3.7.1 实时分析器与SLO定义

```python
class RealtimeAnalyzer:
    """
    实时动作分析器.
    
    SLO定义：
    - 单帧处理延迟：P99 < 50ms（含推理）
    - 窗口分析延迟：P99 < 100ms（30帧窗口）
    - 状态同步延迟：P99 < 16ms（60fps）
    - 内存占用：单流 < 100MB（含缓冲区）
    - 掉帧处理：连续掉帧>5帧触发降级模式
    - 状态重置：无输入>5秒自动重置
    
    背压策略：
    - 输入队列长度>10：跳过非关键帧（只保留I帧）
    - 输入队列长度>20：启用快速模式（降低计算精度）
    - 输入队列长度>30：丢弃旧帧（保持实时性）
    """
    
    def __init__(
        self,
        action_config: ActionConfig,
        window_size: int = 30,
        overlap: float = 0.5,
        
        # SLO参数
        target_latency_ms: float = 50.0,
        max_queue_length: int = 30,
        frame_skip_threshold: int = 10,
        auto_reset_timeout_ms: float = 5000.0,
    ):
        self.config = action_config
        self.window_size = window_size
        self.overlap = overlap
        
        # SLO参数
        self.target_latency_ms = target_latency_ms
        self.max_queue_length = max_queue_length
        self.frame_skip_threshold = frame_skip_threshold
        self.auto_reset_timeout_ms = auto_reset_timeout_ms
        
        # 子引擎
        self.phase_engine: Optional[PhaseEngine] = None
        self.rep_counter = RepCounter(action_config.cycle_definition)
        
        # 状态管理
        self.frame_buffer: deque = deque(maxlen=window_size)
        self.phase_history: deque = deque(maxlen=100)
        self.last_frame_time: float = 0.0
        self.current_rep: Optional[Rep] = None
        self.rep_count: int = 0
        
        # 性能监控
        self.latency_history: deque = deque(maxlen=100)
        self.drop_frame_count: int = 0
    
    def process_frame(
        self,
        frame: PoseFrame,
        timestamp_ms: float
    ) -> RealtimeResult:
        """
        处理单帧，输出实时结果.
        
        流程：
        1. 背压检查（队列长度）
        2. 超时检查（自动重置）
        3. 添加到缓冲区
        4. 触发窗口分析（满足条件时）
        5. 更新实时状态
        6. 返回结果
        """
        start_time = time.time()
        
        # 1. 背压检查
        if len(self.frame_buffer) >= self.frame_skip_threshold:
            self._apply_backpressure(frame)
        
        # 2. 超时检查 - 自动重置
        if timestamp_ms - self.last_frame_time > self.auto_reset_timeout_ms:
            self._reset_state()
        
        self.last_frame_time = timestamp_ms
        
        # 3. 添加到缓冲区
        self.frame_buffer.append(frame)
        
        # 4. 触发窗口分析
        if len(self.frame_buffer) >= self.window_size:
            window_result = self._analyze_window()
            self._update_state(window_result)
        
        # 5. 计算实时值
        metric_values = self._calculate_current_metrics(frame)
        active_errors = self._detect_active_errors(metric_values)
        
        # 6. 记录延迟
        latency_ms = (time.time() - start_time) * 1000
        self.latency_history.append(latency_ms)
        
        return RealtimeResult(
            frame_id=frame.frame_id,
            timestamp=timestamp_ms,
            current_phase=self._get_current_phase(),
            rep_count=self.rep_count,
            rep_progress=self._calc_rep_progress(),
            metric_values=metric_values,
            active_errors=active_errors,
            stability_score=self._calc_stability(),
            performance=PerformanceMetrics(
                latency_ms=latency_ms,
                queue_length=len(self.frame_buffer),
                drop_frame_count=self.drop_frame_count
            )
        )
    
    def _apply_backpressure(self, frame: PoseFrame) -> bool:
        """
        应用背压策略.
        
        返回：是否应跳过此帧
        """
        queue_len = len(self.frame_buffer)
        
        if queue_len >= self.max_queue_length:
            # 队列已满，丢弃最旧帧
            self.frame_buffer.popleft()
            self.drop_frame_count += 1
            return True
        
        if queue_len >= self.frame_skip_threshold * 2:
            # 启用快速模式 - 降低计算精度
            # 实际实现：简化阶段检测逻辑
            pass
        
        return False
    
    def _reset_state(self):
        """重置所有状态."""
        self.frame_buffer.clear()
        self.phase_history.clear()
        self.current_rep = None
        self.rep_count = 0
        self.phase_engine = None
```

### 3.8 API版本策略

```python
# API响应版本管理
class APIVersion(str, Enum):
    """API版本枚举."""
    V1 = "1.0.0"  # 原始版本
    V2 = "2.0.0"  # 新增 phase/rep/evaluation 字段


class AnalysisResult(BaseModel):
    """
    分析结果响应.
    
    兼容性策略：
    - api_version 字段明确标识响应格式版本
    - V1客户端可忽略不认识的字段
    - 新增字段均为可选，不破坏旧解析
    """
    
    api_version: APIVersion = APIVersion.V2
    action_id: str
    
    # V1 已有字段
    metrics: Dict[str, MetricResult]  # 保持V1结构
    overall_score: float
    
    # V2 新增字段（可选，V1客户端可忽略）
    phases: Optional[PhaseSequence] = None  # 阶段序列
    rep_count: Optional[RepCountResult] = None  # 动作计数
    evaluations: Optional[Dict[str, ThresholdEvaluation]] = None  # 阈值评估
    
    # 性能指标
    processing_time_ms: float
    
    class Config:
        # 允许额外字段（未来扩展）
        extra = "allow"


class MetricResult(BaseModel):
    """
    检测项结果（V1/V2兼容）.
    
    V1字段保持不变，V2在 values/statistics/errors 基础上新增 evaluation
    """
    
    # V1 字段
    metric_id: str
    name: str
    values: List[float]
    statistics: Dict[str, Any]
    errors: List[Dict[str, Any]]
    
    # V2 新增（可选）
    evaluation: Optional[ThresholdEvaluation] = None  # 阈值评估
    grade: Optional[str] = None  # 等级（冗余，便于快速读取）
```

---

## 4. 统一输出契约与评估协议（详见配套文档）

### 4.1 输出契约要点

**统一输出格式规范**详见 [action_analysis_output_contract.md](./action_analysis_output_contract.md)，核心要点：

| 维度 | 规范 |
|------|------|
| **格式一致** | 批量/实时共用字段定义，api_version 显式标识版本 |
| **必填/可选** | 明确分级（必填/可选/推荐），运行时只接受显式阶段ID |
| **版本兼容** | V1客户端可安全忽略V2新增字段，提供适配器 |
| **契约稳定** | schema_version 管理，字段废弃保留但标记 |

**关键变更**：
- CycleDefinition 优先级：`显式配置 > 数据推断 > 模板建议 > 缺失`
- any 处理：改为**多阶段评估**（在所有阶段评估），不再映射到单阶段
- peak 处理：改为**运行时极值检测**，不再映射到固定阶段

### 4.2 评估协议要点

**测试集评估协议**详见配套文档，核心指标：

| 指标 | 上线门槛 |
|------|----------|
| **Rep Count Accuracy (RCA)** | ≥ 95% |
| **Error F1-Score** | ≥ 87% |
| **Phase Accuracy** | ≥ 92% |

**强制校验矩阵**：
- entry/exit 条件至少配置其一（Warning）
- 周期定义可达性校验（Error）
- 阈值区间 target_value 必须声明（Error）

---

## 5. 实施计划（两轨并行）

### 4.1 项目时间线

```
Week 1-2: 兼容层 + PhaseEngine V2
Week 3-4: RepCounter + ThresholdEvaluator
Week 5-6: ActionAnalyzer整合 + 配置迁移工具
Week 7-8: 灰度验证 + 性能优化
Week 9-10: 实时接口 + 完整测试
```

### 4.2 两轨并行策略

| 阶段 | 功能开发轨 | 兼容验证轨 | 里程碑 |
|------|-----------|-----------|--------|
| **P0** | PhaseEngine V2 + RepCounter + ThresholdEvaluator | 旧配置自动转换验证<br>深蹲/侧抬腿基线对比 | **灰度发布1**<br>双引擎并行运行 |
| **P1** | ActionAnalyzer整合<br>API版本控制 | 跨动作基线集测试<br>性能压测 | **灰度发布2**<br>50%流量切换 |
| **P2** | 实时接口<br>数据视图优化 | 配置迁移回归集<br>线上对比监控 | **全量发布** |

### 4.3 关键检查点

#### 4.3.1 P0 灰度检查清单

- [ ] V1配置自动转换后，阶段检测结果与旧实现差异 < 5%
- [ ] 深蹲动作计数准确率 > 95%（对比人工标注）
- [ ] 阈值评估结果与训练参数一致性 > 98%
- [ ] API响应延迟 P99 < 200ms（批量接口）
- [ ] 内存占用增长 < 20%

#### 4.3.2 P1 灰度检查清单

- [ ] 5个标准动作基线测试全部通过
- [ ] 自定义动作配置可正确加载运行
- [ ] 并发性能：100视频/分钟处理能力
- [ ] 错误识别准确率对比旧系统提升 > 10%

### 4.4 风险缓解

| 风险 | 缓解措施 |
|------|----------|
| 配置迁移失败 | 保留V1代码路径，可随时回滚 |
| 阶段检测精度下降 | 双引擎并行期持续监控，差异告警 |
| 性能不达标 | 分级降级：简化算法 -> 跳帧 -> 返回V1结果 |
| 实时接口不稳定 | 独立部署，与批处理服务隔离 |

---

## 6. 验证方案

### 5.1 三类必测集合

#### 5.1.1 配置迁移回归集

```python
MIGRATION_TEST_CASES = [
    # 标准动作V1配置
    {"action_id": "squat", "config_version": "1.0.0", "expected_phases": 4},
    {"action_id": "lunge", "config_version": "1.0.0", "expected_phases": 4},
    {"action_id": "pushup", "config_version": "1.0.0", "expected_phases": 4},
    {"action_id": "plank", "config_version": "1.0.0", "expected_phases": 3},
    {"action_id": "side_leg_raise", "config_version": "1.0.0", "expected_phases": 4},
    
    # 边界情况
    {"action_id": "minimal", "phases": ["start", "end"], "expected_auto_cycle": True},
    {"action_id": "no_cycle", "phases": ["hold"], "expected_rep_count": 0},
]
```

#### 5.1.2 跨动作基线集

```python
BASELINE_TEST_CASES = [
    # 深蹲标准视频
    {"video": "squat_standard_01.mp4", "action": "squat", 
     "expected_reps": 10, "expected_errors": []},
    {"video": "squat_knee_valgus_01.mp4", "action": "squat",
     "expected_reps": 10, "expected_errors": ["knee_valgus"]},
    
    # 侧抬腿标准视频
    {"video": "side_leg_raise_standard_01.mp4", "action": "side_leg_raise",
     "expected_reps": 12, "expected_errors": []},
    {"video": "side_leg_raise_compensation_01.mp4", "action": "side_leg_raise",
     "expected_reps": 12, "expected_errors": ["trunk_compensation"]},
]
```

#### 5.1.3 性能压测集

```python
PERFORMANCE_TEST_CASES = [
    # 并发测试
    {"concurrent_streams": 10, "duration_sec": 60, 
     "target_latency_p99_ms": 100},
    {"concurrent_streams": 50, "duration_sec": 60,
     "target_latency_p99_ms": 200},
    
    # 长视频测试
    {"video_duration_min": 10, "target_processing_time_min": 2},
    {"video_duration_min": 30, "target_processing_time_min": 6},
    
    # 内存测试
    {"concurrent_analyses": 20, "target_memory_mb_per_stream": 100},
]
```

### 5.2 自动化验证流水线

```yaml
# .github/workflows/validation.yml
name: Action Analysis V2 Validation

on: [pull_request]

jobs:
  migration-test:
    runs-on: ubuntu-latest
    steps:
      - name: Test V1->V2 Config Migration
        run: pytest tests/migration/ -v --tb=short
      
      - name: Verify Backward Compatibility
        run: pytest tests/compatibility/ -v

  baseline-test:
    runs-on: ubuntu-latest
    needs: migration-test
    steps:
      - name: Run Cross-Action Baseline Tests
        run: pytest tests/baseline/ -v --benchmark
      
      - name: Compare with Reference Results
        run: python scripts/compare_baseline.py

  performance-test:
    runs-on: ubuntu-latest
    needs: migration-test
    steps:
      - name: Run Performance Benchmarks
        run: pytest tests/performance/ -v --benchmark-only
      
      - name: Check Memory Usage
        run: python scripts/memory_profile.py
      
      - name: Fail on Regression
        run: python scripts/check_regression.py --threshold=10%
```

---

## 7. 附录

### 6.1 配置迁移示例

```python
# 迁移前 (V1)
{
  "action_id": "squat",
  "phases": [
    {
      "phase_id": "bottom",
      "phase_name": "最低点",
      "detection_params": {
        "velocity_threshold": 0.5,
        "hip_flexion_threshold": 90
      }
    }
  ]
}

# 迁移后 (V2，自动转换)
{
  "action_id": "squat",
  "schema_version": "2.0.0",
  "phases": [
    {
      "phase_id": "bottom",
      "phase_name": "最低点",
      "entry_conditions": [
        {
          "type": "DERIVATIVE",
          "metric": "velocity",
          "order": 1,
          "operator": "lt",
          "value": 0.5
        },
        {
          "type": "THRESHOLD",
          "metric": "hip_flexion",
          "operator": "gte",
          "value": 90
        }
      ]
    }
  ],
  "cycle_definition": {
    "phase_sequence": ["start", "descent", "bottom", "ascent", "end"],
    "required_phases": ["bottom"]
  }
}
```

### 6.2 术语对照

| 中文 | 英文 | 定义 |
|------|------|------|
| 阶段 | Phase | 动作的时间子段，由进入/退出条件定义 |
| 周期 | Cycle | 一个完整的动作重复，由阶段序列组成 |
| 计数 | Rep Count | 完成的周期次数 |
| 阈值 | Threshold | 评判动作质量的数值边界 |
| 等级 | Grade | excellent/good/pass/fail 评估结果 |
| 错误条件 | Error Condition | 触发错误识别的规则 |
| 关键帧 | Key Frame | 阶段内用于评估的特定帧 |

---

**文档版本**: 2.0.0  
**最后更新**: 2026-04-14  
**状态**: 审核通过，待实施
