# straight_leg_raise 到 iOS 检测项映射规范

## 文档目的
- 基于训练产物 `config/action_configs/straight_leg_raise_trained.json` 与报告 `docs/reports/straight_leg_raise_20260419_130731_training_report.md`，给出可直接执行的 iOS 迁移方案。
- 明确哪些检测项可复用 iOS 现有 `itemID`，哪些必须新增 `itemID(21+)`。
- 给出可用于后端人工配置的 `detectItemIDs + detectItemParameters` 示例。

## 关键边界
- iOS 侧不定义动作，不固化动作参数，只消费后端下发的 `detectItemIDs + detectItemParameters`。
- `itemID -> keypoint_profile(17/33)` 由 iOS 注册表维护，不在后端配置中下发。
- 同逻辑但关键点体系不同（17 vs 33）时，必须新建 `itemID`，不能复用旧 `itemID`。

## 检测项覆盖结论

### 训练产物核心检测项（`metrics`）
- `ankle_dorsiflexion`
- `knee_flexion_compensation`
- `hip_abduction`
- `knee_symmetry`

### iOS 复用/新增判定
- `ankle_dorsiflexion` -> **可复用 `itemID=8`**（已有动态踝背屈策略，YOLO17）。
- `knee_flexion_compensation` -> **可复用 `itemID=7`**（已有静态膝角策略，YOLO17）。
- `hip_abduction` -> **建议新增 `itemID=22`**（现有 `itemID=19/20`语义不等价，不建议强复用）。
- `knee_symmetry` -> **建议新增 `itemID=23`**（当前无对称性差值检测项）。

### 执行结论（硬规则）
- 若后续要把 `ankle_dorsiflexion` 从 YOLO17 换成 MP33 版本（例如 toe/foot_index 参与），必须新建新 ID（如 `itemID=24`），不能继续用 `itemID=8`。

## 新增检测项编号规则
- 当前已用到 `21`，本动作建议：
- `22`: `HipAbductionMP33Strategy`（新增）
- `23`: `KneeSymmetryMP33Strategy`（新增）
- 预留：`24+` 给同逻辑不同关键点体系版本

## 逐字段 -> 逐索引映射

### itemID=8（AnkleDorsiflexion，复用）
- 现有代码有效参数位：`[0]`、`[1]`（其余位可保留占位）
- 来源字段：
- `count_layer.thresholds.enter_p1 = 121.668`
- `count_layer.thresholds.exit_p1 = 145.358`
- `count_layer.thresholds.enter_p2 = 140.381`
- `count_layer.thresholds.exit_p2 = 119.794`
- `metrics[ankle_dorsiflexion].thresholds.normal_range = [119.95, 139.39]`
- `metrics[ankle_dorsiflexion].thresholds.excellent_range = [124.81, 134.53]`
- `semantic_layer.phases[hold].exit_conditions[0].value = 117.039165...`

| iOS item8 索引 | 来源字段 | 说明 |
|---|---|---|
| `[0]` | `count_layer.thresholds.exit_p2` | p1 阈值（有效） |
| `[1]` | `count_layer.thresholds.enter_p2` | p2 阈值（有效） |
| `[2]` | `count_layer.thresholds.enter_p2` | 预留 |
| `[3]` | `count_layer.thresholds.exit_p1` | 预留 |
| `[4]` | `metrics.ankle_dorsiflexion.normal_range[0]` | 预留 |
| `[5]` | `metrics.ankle_dorsiflexion.excellent_range[0]` | 预留 |
| `[6]` | `semantic_layer.hold.exit_conditions[0].value` | 预留 |
| `[7]` | `metrics.ankle_dorsiflexion.excellent_range[1]` | 预留 |

建议参数行：
- `[119.794, 140.381, 140.381, 145.358, 119.95, 124.81, 117.039, 134.53]`

---

### itemID=7（SideKneeFlexionStatic，复用，近似映射）
- 现有代码有效参数位：`[0]`、`[1]`（静态阈值）
- 来源字段：
- `metrics[knee_flexion_compensation].thresholds.normal_range = [157.97, 174.75]`
- `metrics[knee_flexion_compensation].thresholds.excellent_range = [162.16, 170.56]`
- `metrics[knee_flexion_compensation].thresholds.target_value = 166.36`

| iOS item7 索引 | 来源字段 | 说明 |
|---|---|---|
| `[0]` | `metrics.knee_flexion_compensation.normal_range[0]` | 有效 |
| `[1]` | `metrics.knee_flexion_compensation.normal_range[1]` | 有效 |
| `[2]` | `metrics.knee_flexion_compensation.excellent_range[0]` | 预留 |
| `[3]` | `metrics.knee_flexion_compensation.excellent_range[1]` | 预留 |
| `[4]` | `metrics.knee_flexion_compensation.normal_range[0]` | 预留 |
| `[5]` | `metrics.knee_flexion_compensation.target_value` | 预留 |
| `[6]` | `metrics.knee_flexion_compensation.target_value` | 预留 |
| `[7]` | `metrics.knee_flexion_compensation.normal_range[1]` | 预留 |

建议参数行：
- `[157.97, 174.75, 162.16, 170.56, 157.97, 166.36, 166.36, 174.75]`

风险说明：
- 该项是“补偿检测项”，在训练产物中未学习到错误条件（报告 `error_types_covered=0`），需后续回放校准阈值。

---

### itemID=22（HipAbductionMP33，新增）
- 现有 iOS 无等价项，必须新增。
- 建议参数协议：8 槽位（`[0..3]`相位阈值，`[4..7]`评估阈值）。
- 来源字段：
- `metrics[hip_abduction].thresholds.normal_range = [64.57, 90.17]`
- `metrics[hip_abduction].thresholds.excellent_range = [70.97, 83.77]`
- `metrics[hip_abduction].thresholds.target_value = 77.37`

建议参数行（首版联调）：
- `[64.57, 70.97, 83.77, 90.17, 64.57, 70.97, 83.77, 90.17]`

最终回填来源：
- `data/evaluations/straight_leg_raise/*.json` 回放统计 + 线上灰度样本。

---

### itemID=23（KneeSymmetryMP33，新增）
- 现有 iOS 无“对称性差值”检测项，必须新增。
- 建议参数协议：8 槽位（前4相位、后4评估）。
- 来源字段：
- `metrics[knee_symmetry].thresholds.normal_range = [0.12, 0.22]`
- `metrics[knee_symmetry].thresholds.excellent_range = [0.14, 0.19]`
- `metrics[knee_symmetry].thresholds.target_value = 0.17`

建议参数行（首版联调）：
- `[0.12, 0.14, 0.19, 0.22, 0.12, 0.14, 0.19, 0.22]`

最终回填来源：
- 训练评估回放分布（按设备、摄像头位姿分桶）。

## 外部配置示例（可人工配置）

### 最小可用（可直接上线试跑）
```json
{
  "detectItemIDs": ["8", "7"],
  "detectItemParameters": [[
    [119.794, 140.381, 140.381, 145.358, 119.95, 124.81, 117.039, 134.53],
    [157.97, 174.75, 162.16, 170.56, 157.97, 166.36, 166.36, 174.75]
  ]]
}
```

### 完整覆盖（含新增项）
```json
{
  "detectItemIDs": ["8", "7", "22", "23"],
  "detectItemParameters": [[
    [119.794, 140.381, 140.381, 145.358, 119.95, 124.81, 117.039, 134.53],
    [157.97, 174.75, 162.16, 170.56, 157.97, 166.36, 166.36, 174.75],
    [64.57, 70.97, 83.77, 90.17, 64.57, 70.97, 83.77, 90.17],
    [0.12, 0.14, 0.19, 0.22, 0.12, 0.14, 0.19, 0.22]
  ]]
}
```

### 字段占位模板（后端编译接入）
```json
{
  "detectItemIDs": ["8", "7", "22", "23"],
  "detectItemParameters": [[
    ["item8_p0", "item8_p1", "item8_p2", "item8_p3", "item8_p4", "item8_p5", "item8_p6", "item8_p7"],
    ["item7_p0", "item7_p1", "item7_p2", "item7_p3", "item7_p4", "item7_p5", "item7_p6", "item7_p7"],
    ["item22_p0", "item22_p1", "item22_p2", "item22_p3", "item22_p4", "item22_p5", "item22_p6", "item22_p7"],
    ["item23_p0", "item23_p1", "item23_p2", "item23_p3", "item23_p4", "item23_p5", "item23_p6", "item23_p7"]
  ]]
}
```

## 已可直接上线项 vs 需新增开发项
- 已可直接上线项：
- `itemID=8`（ankle dorsiflexion 主计数锚点）
- `itemID=7`（knee compensation 静态约束）
- 需新增开发项：
- `itemID=22`（hip_abduction）
- `itemID=23`（knee_symmetry）
- 需补学习项：
- 错误条件未学出（`bent_leg`、`excessive_hip_abduction`），需追加错误样本并重训

## 冲突清单与处理建议
- 冲突1：训练报告显示 `error_types_covered=0`，当前无法可靠落地错误分类规则。  
- 处理：补充错误样本（每类>=3~5），重跑训练并确认 `covered_error_types` 非空。
- 冲突2：`hip_abduction`、`knee_symmetry` 在 iOS 现有策略库无等价实现。  
- 处理：新增 `itemID=22/23` 并在注册表补齐 `item->profile/strategy/schema`。
- 冲突3：`itemID=7` 为静态策略，仅前2参数生效。  
- 处理：在后端配置说明中标注“仅 [0],[1] 有效”，避免误解其余槽位。

## 实施顺序
- 1. 先上线最小组合 `["8","7"]` 验证计数稳定性。
- 2. 实现并接入 `itemID=22/23`，切换到完整组合。
- 3. 补错误样本重训，产出错误条件后再启用错误告警。
- 4. 灰度放量并监控计数偏差、误报漏报、性能影响。

## 验收点
- 参数对齐：`detectItemIDs.count == detectItemParameters[0].count`，每行长度符合 schema。
- 计数：完整组合不低于最小组合计数准确率。
- 错误识别：重训后 `covered_error_types` 包含目标错误类型。
- 性能：新增项后帧率与耗电在可接受范围内。
