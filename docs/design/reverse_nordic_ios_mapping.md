# reverse_nordic 到 iOS 检测项映射规范

## 文档目的
- 基于训练产物 `config/action_configs/reverse_nordic_trained.json` 与评估报告 `data/evaluations/reverse_nordic/20260420_v1.0.json`，给出可直接执行的 iOS 迁移方案。
- 明确哪些检测项可复用 iOS 现有 `itemID`，哪些必须新增 `itemID(21+)`。
- 给出可用于后端人工配置的 `detectItemIDs + detectItemParameters` 示例。

## 关键边界
- iOS 侧不定义动作，不固化动作参数，只消费后端下发的 `detectItemIDs + detectItemParameters`。
- `itemID -> keypoint_profile(17/33)` 由 iOS 注册表维护，不在后端配置中下发。
- 同逻辑但关键点体系不同（17 vs 33）时，必须新建 `itemID`，不能复用旧 `itemID`。
- 本次训练产出的所有核心动作评估和计数阶段，均需支持基于 MP33 骨骼点的 8 槽位动态参数协议。

## 检测项覆盖结论

### 训练产物核心检测项（`metrics`）
- `hip_flexion` (髋屈角) - **主控计数指标** & 身体躯干后倾深度评估
- `hip_external_rotation` (髋外旋角) - 辅助姿态约束

### iOS 复用/新增判定与影响分析
- `hip_flexion` -> **建议新增 `itemID=30`**。
  - *原因分析*：这是主控计数的 metric，不仅需要控制 p1/p2 的 4 个动态流转阈值，还需要对“后倾深度（Hold阶段）”进行评估（`normal_range`, `excellent_range`）。旧版静态或双槽位的检测项无法承载这 8 槽位的完整状态机与区间评估，必须新增。
- `hip_external_rotation` -> **建议新增 `itemID=31`**。
  - *原因分析*：该项需要在后倾的 Hold 阶段判断髋部外旋（姿态代偿或膝盖外翻倾向），需要动态的区间评估。现有的 iOS 库中若无等价动态 8 槽位 MP33 检测项，则必须新增。

### 执行结论（硬规则）
为了保证反北欧挺动作计数的鲁棒性与评估的完整性（支持 8 槽位协议），核心指标均采用新的 MP33 动态检测项接入 iOS。

## 新增检测项编号规则
承接之前新动作（如保加利亚蹲用到了26-29）的分配记录，本动作建议使用以下 ID：
- `30`: `HipFlexionMP33Strategy`（新增，主计数锚点与后倾深度约束）
- `31`: `HipExternalRotationMP33Strategy`（新增，髋部外旋/姿态约束）

## 逐字段 -> 逐索引映射

### itemID=30（HipFlexionMP33，主计数锚点）
- 支持 8 槽位协议（`[0..3]` 相位阈值，`[4..7]` 评估阈值）。
- 极性：`valley_to_peak_to_valley`（跪直时髋角约为180° -> 往后仰时角度变小 -> 跪直回180°。数值体现为：大-小-大）。
- 来源字段（采用 `aggregation.param_ci` 放宽边界，以增强计数鲁棒性，并在测试脚本中验证通过）：
  - `enter_p1 = 156.42` (参考：严格中位数 164.93，采用 `param_ci.enter_p1[0]`)
  - `exit_p1 = 170.73` (参考：严格中位数 174.00，采用 `param_ci.exit_p1[0]`)
  - `enter_p2 = 173.36` (参考：严格中位数 171.73，采用 `param_ci.enter_p2[1]`)
  - `exit_p2 = 167.10` (参考：严格中位数 163.79，采用 `param_ci.exit_p2[1]`)
  - `normal_range = [158.36, 172.81]`
  - `excellent_range = [161.97, 169.20]`

| iOS item30 索引 | 来源字段 | 说明 |
|---|---|---|
| `[0]` | `param_ci.enter_p1[0]` | enter_p1 (Idle->Rise 阈值) |
| `[1]` | `param_ci.exit_p1[0]` | exit_p1 (Rise->Peak 阈值) |
| `[2]` | `param_ci.enter_p2[1]` | enter_p2 (Peak->Return 阈值) |
| `[3]` | `param_ci.exit_p2[1]` | exit_p2 (Return->Idle 阈值) |
| `[4]` | `metrics...normal_range[0]` | 正常区间下界 |
| `[5]` | `metrics...excellent_range[0]` | 优秀区间下界 |
| `[6]` | `metrics...excellent_range[1]` | 优秀区间上界 |
| `[7]` | `metrics...normal_range[1]` | 正常区间上界 |

**建议参数行：**
- `[156.42, 170.73, 173.36, 167.10, 158.36, 161.97, 169.20, 172.81]`

---

### itemID=31（HipExternalRotationMP33，辅助姿态约束）
- 该项不参与计数控制，仅做姿态评估（复制评估阈值占满前四个槽位，或填0忽略，视具体实现而定）。
- 来源字段：
  - `metrics[hip_external_rotation].thresholds.normal_range = [53.37, 64.67]`
  - `metrics[hip_external_rotation].thresholds.excellent_range = [56.19, 61.84]`

| iOS item31 索引 | 来源字段 | 说明 |
|---|---|---|
| `[0..3]` | 评估阈值复制 | (如果不参与状态机，通常复制后续4个参数) |
| `[4]` | `metrics...normal_range[0]` | 正常区间下界 |
| `[5]` | `metrics...excellent_range[0]` | 优秀区间下界 |
| `[6]` | `metrics...excellent_range[1]` | 优秀区间上界 |
| `[7]` | `metrics...normal_range[1]` | 正常区间上界 |

**建议参数行：**
- `[53.37, 56.19, 61.84, 64.67, 53.37, 56.19, 61.84, 64.67]`

## 外部配置示例（可人工配置）

### 最小可用（可直接上线试跑，仅包含主控计数与后倾深度约束）
```json
{
  "detectItemIDs": ["30"],
  "detectItemParameters": [[
    [156.42, 170.73, 173.36, 167.10, 158.36, 161.97, 169.20, 172.81]
  ]]
}
```

### 完整覆盖（含计数主控与外旋约束）
```json
{
  "detectItemIDs": ["30", "31"],
  "detectItemParameters": [[
    [156.42, 170.73, 173.36, 167.10, 158.36, 161.97, 169.20, 172.81],
    [53.37, 56.19, 61.84, 64.67, 53.37, 56.19, 61.84, 64.67]
  ]]
}
```

## 已可直接上线项 vs 需新增开发项
- **已可直接上线项**：无
- **需新增开发项**：
  - `itemID=30`（hip flexion 主计数锚点与后倾约束）
  - `itemID=31`（hip external rotation 姿态约束）
- **需补学习项**：
  - 目前的评估报告显示 `error_types_covered` 为 0。现阶段只有基于“正常/优秀”区间的动作降级（不够标准），尚无法输出具体的错误原因（如“臀部未绷紧”）。需要在收集到错误动作样本后，重新训练才能自动生成 ErrorConditions。

## 冲突清单与处理建议
- **冲突1：左右侧视角选侧（遮挡问题）**
  - 处理：反北欧挺是双侧同时受力的动作，`hip_flexion` 和 `hip_external_rotation` 的原始定义均支持双侧。iOS 侧实现 `itemID=30` 和 `31` 时，**必须复用 `auto_select_side` 逻辑**（比较置信度或 Y 轴运动幅度），自动选择清晰的、离镜头近的一侧腿进行分析，避免 BlazePose 的自身肢体遮挡导致数据抖动。

## 实施顺序
1. **iOS 开发**：在 iOS 端实现 `itemID=30` 和 `31`，支持 8 槽位配置解析，并确保 `itemID=30` 中集成了 EMA 滤波、滞回 Margin 及防抖帧计数逻辑。同时实现 `auto_select_side`。
2. **最小可用验证**：通过 Mock JSON 下发 `["30"]`，使用测试集的 `反北欧挺.mp4` 进行计数准确率回归。
3. **完整覆盖与灰度**：接入 `["30", "31"]`，验证姿态约束是否正确扣分。
4. **补充错误样本重训**：待业务产生“错误动作”素材后，将其纳入数据集重训，补齐具体错误类型标签。

## 验收点
- **参数对齐**：`detectItemIDs.count == detectItemParameters[0].count`，确保后端下发的 JSON 与 iOS 端策略完美映射。
- **计数准确率**：测试集报告显示当前训练的 MAE=0.0 (准确率 100%)。iOS 上线后应对齐这个准确率，确保放宽后的置信区间阈值（`156.42`~`173.36`）能稳健流转状态机。
- **选侧稳定性**：在侧面机位拍摄时，身体不能频繁在左右腿之间切换导致角度突变。
