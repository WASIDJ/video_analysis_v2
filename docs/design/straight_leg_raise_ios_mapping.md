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

### iOS 复用/新增判定与影响分析
- `ankle_dorsiflexion` -> **建议新增 `itemID=24`**（不再复用 `itemID=8`）。
  - *原因分析*：`itemID=8` 原有设计仅接收 2 个有效参数位，通常只用于简单的双阈值判断。但在直腿抬高中，除了需要 `p1/p2` 的 4 个阈值外，还需要评估阶段的 `normal_range`（如判断抬高幅度是否优秀或合格），总计需要 8 个槽位。强行复用会导致无法进行准确的质量评估。
- `knee_flexion_compensation` -> **建议新增 `itemID=25`**（不再复用 `itemID=7`）。
  - *原因分析*：`itemID=7` 是静态检测项，只有前 2 个参数生效（通常仅能设置一个固定的报错阈值区间）。而在本动作中，我们需要在特定相位（如 Hold 阶段）对膝盖代偿进行动态区间评估（`normal_range`, `excellent_range`），需要至少 4 个参数槽。复用静态项会导致动作评估的粒度极度受限。
- `hip_abduction` -> **建议新增 `itemID=22`**（现有 `itemID=19/20`语义不等价，不建议强复用）。
- `knee_symmetry` -> **建议新增 `itemID=23`**（当前无对称性差值检测项）。

### 执行结论（硬规则）
为了保证动作计数的鲁棒性与评估的完整性（支持 8 槽位协议），本动作不再复用任何旧版检测项，全部作为新的 MP33 检测项接入 iOS。

## 新增检测项编号规则
- 当前已用到 `21`，本动作建议全部新建：
- `22`: `HipAbductionMP33Strategy`（新增）
- `23`: `KneeSymmetryMP33Strategy`（新增）
- `24`: `AnkleDorsiflexionMP33Strategy`（新增，替代原 8）
- `25`: `KneeFlexionCompensationMP33Strategy`（新增，替代原 7）

## 逐字段 -> 逐索引映射

### itemID=24（AnkleDorsiflexionMP33，新增）
- 完全支持 8 槽位协议（`[0..3]` 相位阈值，`[4..7]` 评估阈值）。
- 来源字段（采用放宽后的 `aggregation.param_ci` 25%下界，避免严格中位数导致用户无法达标漏计）：
- `count_layer.thresholds.enter_p1 = 121.668`
- `count_layer.aggregation.param_ci.exit_p1[0] = 125.059`
- `count_layer.aggregation.param_ci.enter_p2[0] = 120.492`
- `count_layer.thresholds.exit_p2 = 119.794`
- `metrics[ankle_dorsiflexion].thresholds.normal_range = [119.95, 139.39]`
- `metrics[ankle_dorsiflexion].thresholds.excellent_range = [124.81, 134.53]`

| iOS item24 索引 | 来源字段 | 说明 |
|---|---|---|
| `[0]` | `count_layer.thresholds.exit_p2` | enter_p1 (Idle->Rise 阈值) |
| `[1]` | `count_layer.aggregation.param_ci.enter_p2[0]` | exit_p1 (Rise->Peak 阈值) |
| `[2]` | `count_layer.aggregation.param_ci.enter_p2[0]` | enter_p2 (Peak->Return 阈值) |
| `[3]` | `count_layer.aggregation.param_ci.exit_p1[0]` | exit_p2 (Return->Idle 阈值) |
| `[4]` | `metrics.ankle_dorsiflexion.normal_range[0]` | 正常区间下界 |
| `[5]` | `metrics.ankle_dorsiflexion.excellent_range[0]` | 优秀区间下界 |
| `[6]` | `metrics.ankle_dorsiflexion.excellent_range[1]` | 优秀区间上界 |
| `[7]` | `metrics.ankle_dorsiflexion.normal_range[1]` | 正常区间上界 |

建议参数行：
- `[119.794, 120.492, 120.492, 125.059, 119.95, 124.81, 134.53, 139.39]`

---

### itemID=25（KneeFlexionCompensationMP33，新增）
- 抛弃原有的静态项，改为支持在指定相位（Hold）进行评估的动态 8 槽位检测项。
- 来源字段：
- `metrics[knee_flexion_compensation].thresholds.normal_range = [157.97, 174.75]`
- `metrics[knee_flexion_compensation].thresholds.excellent_range = [162.16, 170.56]`

建议参数行：
- `[157.97, 162.16, 170.56, 174.75, 157.97, 162.16, 170.56, 174.75]`

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
  "detectItemIDs": ["24", "25"],
  "detectItemParameters": [[
    [119.794, 120.492, 120.492, 125.059, 119.95, 124.81, 134.53, 139.39],
    [157.97, 162.16, 170.56, 174.75, 157.97, 162.16, 170.56, 174.75]
  ]]
}
```

### 完整覆盖（含新增项）
```json
{
  "detectItemIDs": ["24", "25", "22", "23"],
  "detectItemParameters": [[
    [119.794, 120.492, 120.492, 125.059, 119.95, 124.81, 134.53, 139.39],
    [157.97, 162.16, 170.56, 174.75, 157.97, 162.16, 170.56, 174.75],
    [64.57, 70.97, 83.77, 90.17, 64.57, 70.97, 83.77, 90.17],
    [0.12, 0.14, 0.19, 0.22, 0.12, 0.14, 0.19, 0.22]
  ]]
}
```

### 字段占位模板（后端编译接入）
```json
{
  "detectItemIDs": ["24", "25", "22", "23"],
  "detectItemParameters": [[
    ["item24_p0", "item24_p1", "item24_p2", "item24_p3", "item24_p4", "item24_p5", "item24_p6", "item24_p7"],
    ["item25_p0", "item25_p1", "item25_p2", "item25_p3", "item25_p4", "item25_p5", "item25_p6", "item25_p7"],
    ["item22_p0", "item22_p1", "item22_p2", "item22_p3", "item22_p4", "item22_p5", "item22_p6", "item22_p7"],
    ["item23_p0", "item23_p1", "item23_p2", "item23_p3", "item23_p4", "item23_p5", "item23_p6", "item23_p7"]
  ]]
}
```

## 已可直接上线项 vs 需新增开发项
- 已可直接上线项：
- 无（直腿抬高配置过于复杂，旧项无法承载）
- 需新增开发项：
- `itemID=24`（ankle dorsiflexion 主计数锚点，替代旧8）
- `itemID=25`（knee compensation 动态约束，替代旧7）
- `itemID=22`（hip_abduction）
- `itemID=23`（knee_symmetry）
- 需补学习项：
- 错误条件未学出（`bent_leg`、`excessive_hip_abduction`），需追加错误样本并重训

## 冲突清单与处理建议
- 冲突1：训练报告显示 `error_types_covered=0`，当前无法可靠落地错误分类规则。  
- 处理：补充错误样本（每类>=3~5），重跑训练并确认 `covered_error_types` 非空。
- 冲突2：`hip_abduction`、`knee_symmetry` 在 iOS 现有策略库无等价实现。  
- 处理：新增 `itemID=22/23` 并在注册表补齐 `item->profile/strategy/schema`。
- 冲突3：`itemID=7` / `itemID=8` 的槽位不足以承载直腿抬高的 8 槽位评估协议。  
- 处理：废弃复用方案，全面新增 `itemID=24/25`。

## 实施顺序
- 1. 在 iOS 端实现 `itemID=24/25/22/23`，并支持 8 槽位配置解析。
- 2. 上线联调计数准确率。
- 3. 补错误样本重训，产出错误条件后再启用错误告警。
- 4. 灰度放量并监控计数偏差、误报漏报、性能影响。

## 验收点
- 参数对齐：`detectItemIDs.count == detectItemParameters[0].count`，每行长度符合 schema。
- 计数：完整组合不低于最小组合计数准确率。
- 错误识别：重训后 `covered_error_types` 包含目标错误类型。
- 性能：新增项后帧率与耗电在可接受范围内。
