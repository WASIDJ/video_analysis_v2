# bulgarian_squat 到 iOS 检测项映射规范

## 文档目的
- 基于训练产物 `config/action_configs/bulgarian_squat_trained.json` 与报告 `docs/reports/bulgarian_squat_20260420_112744_training_report.md`，给出可直接执行的 iOS 迁移方案。
- 明确哪些检测项可复用 iOS 现有 `itemID`，哪些必须新增 `itemID(21+)`。
- 给出可用于后端人工配置的 `detectItemIDs + detectItemParameters` 示例。

## 关键边界
- iOS 侧不定义动作，不固化动作参数，只消费后端下发的 `detectItemIDs + detectItemParameters`。
- `itemID -> keypoint_profile(17/33)` 由 iOS 注册表维护，不在后端配置中下发。
- 同逻辑但关键点体系不同（17 vs 33）时，必须新建 `itemID`，不能复用旧 `itemID`。

## 检测项覆盖结论

### 训练产物核心检测项（`metrics`）
- `trunk_lean` (躯干前倾角)
- `knee_flexion_compensation` (膝盖代偿角/后侧腿)
- `ankle_dorsiflexion_lateral` (踝背屈/外侧视角) - 主控计数指标
- `hip_flexion` (髋屈角)

### iOS 复用/新增判定与影响分析
- `ankle_dorsiflexion_lateral` -> **建议新增 `itemID=26`**。
  - *原因分析*：这是主控计数的 metric，控制 p1/p2 的 4 个阈值流转，同时还需要对下蹲深度进行评估（`normal_range`, `excellent_range`）。为了承载完整的 8 槽位配置并支持动态状态机，不能复用原有的简单项。
- `trunk_lean` -> **建议新增 `itemID=27`**（或检查现有躯干检测项的槽位）。
  - *原因分析*：该项需要在下蹲的 Hold 阶段判断躯干是否过度前倾或后仰，需要动态的区间评估。若现有的躯干检测项（如 itemID=5 等）不支持 8 槽位动态评估，必须新增。
- `knee_flexion_compensation` -> **建议新增 `itemID=28`**。
  - *原因分析*：如同直腿抬高中的结论，现有涉及 knee 的检测项（如 itemID=7）多为仅支持 2 个槽位的静态项。此处需在特定相位动态评估。
- `hip_flexion` -> **建议新增 `itemID=29`**。
  - *原因分析*：判断髋关节折叠程度，现有库若无等价动态 8 槽位检测项则必须新增。

### 执行结论（硬规则）
为了保证动作计数的鲁棒性与评估的完整性（支持 8 槽位协议），保加利亚蹲的核心指标均采用新的 MP33 动态检测项接入 iOS。

## 新增检测项编号规则
- 承接之前的分配记录（直腿抬高用到了 25），本动作建议全部新建：
- `26`: `AnkleDorsiflexionLateralMP33Strategy`（新增，主计数锚点）
- `27`: `TrunkLeanMP33Strategy`（新增）
- `28`: `KneeFlexionCompensationMP33Strategy`（复用/扩展 ID=25 的逻辑，或直接使用28处理特定视角的后腿）
- `29`: `HipFlexionMP33Strategy`（新增）

## 逐字段 -> 逐索引映射

### itemID=26（KneeFlexionMP33，主计数锚点）
- 支持 8 槽位协议（`[0..3]` 相位阈值，`[4..7]` 评估阈值）。
- 极性：`peak_to_valley_to_peak`（下蹲时膝盖弯曲角变小再变大，数值体现为高-低-高，依据优化后的手动校验参数）。
- 来源字段（采用真实人工覆盖修正后的阈值，因为原 `ankle` 指标严重受遮挡影响）：
- `enter_p1 = 118.0` 
- `exit_p1 = 110.0` 
- `enter_p2 = 112.0` 
- `exit_p2 = 118.0` 
- `normal_range = [80.10, 130.36]` (复用 knee_flexion_compensation 的部分评价区间)
- `excellent_range = [92.67, 117.80]`

| iOS item26 索引 | 来源字段 | 说明 |
|---|---|---|
| `[0]` | `enter_p1` | enter_p1 (Idle->Rise 阈值) |
| `[1]` | `exit_p1` | exit_p1 (Rise->Peak 阈值) |
| `[2]` | `enter_p2` | enter_p2 (Peak->Return 阈值) |
| `[3]` | `exit_p2` | exit_p2 (Return->Idle 阈值) |
| `[4]` | `metrics...normal_range[0]` | 正常区间下界 |
| `[5]` | `metrics...excellent_range[0]` | 优秀区间下界 |
| `[6]` | `metrics...excellent_range[1]` | 优秀区间上界 |
| `[7]` | `metrics...normal_range[1]` | 正常区间上界 |

建议参数行：
- `[118.0, 110.0, 112.0, 118.0, 80.10, 92.67, 117.80, 130.36]`

---

### itemID=27（TrunkLeanMP33，新增）
- 来源字段：
- `metrics[trunk_lean].thresholds.normal_range = [53.34, 71.41]`
- `metrics[trunk_lean].thresholds.excellent_range = [57.86, 66.89]`

建议参数行：
- `[53.34, 57.86, 66.89, 71.41, 53.34, 57.86, 66.89, 71.41]`

---

### itemID=28（KneeFlexionCompensationMP33，新增）
- 来源字段：
- `metrics[knee_flexion_compensation].thresholds.normal_range = [80.1, 130.36]`
- `metrics[knee_flexion_compensation].thresholds.excellent_range = [92.67, 117.8]`

建议参数行：
- `[80.10, 92.67, 117.80, 130.36, 80.10, 92.67, 117.80, 130.36]`

---

### itemID=29（HipFlexionMP33，新增）
- 来源字段：
- `metrics[hip_flexion].thresholds.normal_range = [120.26, 156.71]`
- `metrics[hip_flexion].thresholds.excellent_range = [129.37, 147.6]`

建议参数行：
- `[120.26, 129.37, 147.60, 156.71, 120.26, 129.37, 147.60, 156.71]`

## 外部配置示例（可人工配置）

### 最小可用（可直接上线试跑，仅计数与躯干限制）
```json
{
  "detectItemIDs": ["26", "27"],
  "detectItemParameters": [[
    [118.0, 110.0, 112.0, 118.0, 80.10, 92.67, 117.80, 130.36],
    [53.34, 57.86, 66.89, 71.41, 53.34, 57.86, 66.89, 71.41]
  ]]
}
```

### 完整覆盖（含四项动态约束）
```json
{
  "detectItemIDs": ["26", "27", "28", "29"],
  "detectItemParameters": [[
    [118.0, 110.0, 112.0, 118.0, 80.10, 92.67, 117.80, 130.36],
    [53.34, 57.86, 66.89, 71.41, 53.34, 57.86, 66.89, 71.41],
    [80.10, 92.67, 117.80, 130.36, 80.10, 92.67, 117.80, 130.36],
    [120.26, 129.37, 147.60, 156.71, 120.26, 129.37, 147.60, 156.71]
  ]]
}
```

## 已可直接上线项 vs 需新增开发项
- 已可直接上线项：
- 无
- 需新增开发项：
- `itemID=26`（knee flexion 主计数锚点）
- `itemID=27`（trunk lean 动态躯干约束）
- `itemID=28`（knee flexion compensation 动态膝盖约束）
- `itemID=29`（hip flexion 动态髋屈约束）
- 需补学习项：
- 错误条件未学出（报告显示 `error_types_covered: 0`），需追加错误样本并重训，否则目前只有“不标准”降级，没有明确的具体报错。

## 冲突清单与处理建议
- 冲突1：训练报告显示 `error_types_covered=0`，无法自动生成具体的错误打标。
  - 处理：由于目前仅输入了 8 个标准视频，未输入错误动作视频。建议采集“过度前倾”、“后腿发力”、“下蹲幅度不足”等错误视频后重新执行训练脚本。
- 冲突2：iOS 侧缺乏对侧向视角的特定处理逻辑（如识别左右腿前后的空间遮挡关系）。
  - 处理：保加利亚蹲是单侧动作。iOS 新增 `itemID=26` 时需复用原有的 `auto_select_side` 或深度检测能力，确保选取的是“前侧受力腿”作为分析目标。

## 实施顺序
- 1. 在 iOS 端实现 `itemID=26/27/28/29`，支持 8 槽位配置解析，并确保 `itemID=26` 中集成了 EMA 滤波和防抖计数逻辑。
- 2. 上线联调最小组合 `["26", "27"]` 的计数准确率与躯干约束能力。
- 3. 补充错误样本，重训产出具体错误标签（error_conditions）后，开启全量错误告警。
- 4. 灰度放量，监控各项偏差。

## 验收点
- 参数对齐：`detectItemIDs.count == detectItemParameters[0].count`，确保后端下发的 JSON 与 iOS 端策略完美映射。
- 计数准确率：对于动作幅度不同的用户，放宽的置信区间阈值（`83.46`~`103.19`）能够不漏计。
- 性能影响：新增的 4 个 MP33 策略在连续执行时是否会导致掉帧。
