# side_lift 到 iOS 检测项映射规范（重构版）

## 1. 文档目的

本文件用于给 iOS 与后端联调，明确两件事：
- `side_lift` 在 iOS 侧应使用哪些检测项 ID（旧 ID 与新增 mp33 ID）；
- 字段如何映射到“检测项参数索引协议”，但参数数值由后端下发，iOS 不写死。

## 2. 关键边界（必须遵守）

- iOS 不定义动作参数，不在端侧固化 side_lift 阈值。
- iOS 只执行：`detectItemIDs + detectItemParameters (+ optional runtime meta)`。
- 同一个检测项可跨动作复用；同一动作不同难度靠外部参数差异实现。

## 3. side_lift 检测项覆盖结论

`side_lift_trained.json` 关注的核心指标：
- `hip_flexion`
- `knee_flexion`
- `ankle_dorsiflexion_lateral`

对应 iOS 检测项建议：
- `hip_flexion` -> `itemID=2`（已有）
- `knee_flexion` -> `itemID=3`（已有）
- `ankle_dorsiflexion_lateral` -> 现有无完全等价项，建议新增 `itemID=21`（mp33 策略）

结论：
- 仅 `2/3` 不是完整覆盖，只能跑通主干；
- 完整对齐需补 `21`（或同类新增 ID）。

## 4. 新增检测项编号规则

- 当前已用到 `20`，新增从 `21` 递增。
- 建议首批：
  - `21`: `AnkleDorsiflexionLateralMP33Strategy`
  - `22+`: 其他 mp33 检测项

## 5. 逐字段 -> 逐索引映射（模板）

说明：
- 下表定义“字段来源关系”，不是固定数值；
- 后端编译产物负责按表填值并下发到 iOS。

## 5.1 itemID=2（SideHipFlexion）

参数索引协议（8 槽位）：
- `[0] p1Lower`
- `[1] p1Upper`
- `[2] p2Lower`
- `[3] p2Upper`
- `[4] evalP1Lower`
- `[5] evalP1Upper`
- `[6] evalP2Lower`
- `[7] evalP2Upper`

字段映射模板：

| iOS item2 索引 | 来源字段（side_lift_trained.json） | 备注 |
|---|---|---|
| `[0]` | `count_layer.thresholds.exit_p2` | 计数层阈值 |
| `[1]` | `count_layer.thresholds.enter_p2` | 计数层阈值 |
| `[2]` | `count_layer.thresholds.enter_p2` | 与策略相位定义对齐 |
| `[3]` | `count_layer.thresholds.exit_p1` | 计数层阈值 |
| `[4]` | `metrics[hip_flexion].thresholds.normal_range[0]` | 评分阈值 |
| `[5]` | `metrics[hip_flexion].thresholds.excellent_range[0]` | 评分阈值 |
| `[6]` | `semantic_layer.phases[hold].exit_conditions[*].value` | 无则回退统计值 |
| `[7]` | `metrics[hip_flexion].thresholds.excellent_range[1]` | 评分阈值 |

## 5.2 itemID=3（SideKneeFlexion）

说明：
- 当前训练产物通常没有 `knee_flexion` 的独立 count_layer p1/p2 字段；
- 所以 item3 在计数阶段多用于协同约束，主计数仍建议以 item2 为主。

字段映射模板：

| iOS item3 索引 | 来源字段（side_lift_trained.json） | 备注 |
|---|---|---|
| `[0]` | `metrics[knee_flexion].thresholds.normal_range[0]` | 近似映射 |
| `[1]` | `metrics[knee_flexion].thresholds.excellent_range[0]` | 近似映射 |
| `[2]` | `metrics[knee_flexion].thresholds.excellent_range[1]` | 近似映射 |
| `[3]` | `metrics[knee_flexion].thresholds.normal_range[1]` | 近似映射 |
| `[4]` | `metrics[knee_flexion].thresholds.normal_range[0]` | 评分阈值 |
| `[5]` | `metrics[knee_flexion].thresholds.target_value` | 评分阈值 |
| `[6]` | `metrics[knee_flexion].thresholds.target_value` | 评分阈值 |
| `[7]` | `metrics[knee_flexion].thresholds.normal_range[1]` | 评分阈值 |

## 5.3 itemID=21（AnkleDorsiflexionLateralMP33，新增）

策略定位：
- 新 mp33 检测项，直接基于 33 点关键点计算；
- 输出格式仍对齐现有 `DetectionResult`。

参数索引建议（沿用 8 槽位）：
- `[0..3]` 相位阈值
- `[4..7]` 评估阈值

字段来源建议：
- `metrics[ankle_dorsiflexion_lateral].thresholds.normal_range/excellent_range`
- 若参与计数，补充训练产物中的 ankle count_layer 子字段（建议新增）。

## 6. side_lift 外部配置示例（后端下发）

### 6.1 可直接人工配置（仅 2/3，最小可用）

```json
{
  "detectItemIDs": ["2", "3"],
  "detectItemParameters": [[
    [113.325, 138.086, 138.086, 145.161, 109.85, 121.59, 133.467, 145.07],
    [133.1, 143.55, 164.44, 174.89, 133.1, 154.0, 154.0, 174.89]
  ]]
}
```

说明：
- 该版本用于先跑通 side_lift 主干（hip + knee）。
- 不含 `ankle_dorsiflexion_lateral`，因此不是完整覆盖版本。

### 6.2 可直接人工配置（2/3/21，完整覆盖目标）

```json
{
  "detectItemIDs": ["2", "3", "21"],
  "detectItemParameters": [[
    [113.325, 138.086, 138.086, 145.161, 109.85, 121.59, 133.467, 145.07],
    [133.1, 143.55, 164.44, 174.89, 133.1, 154.0, 154.0, 174.89],
    [18.0, 32.0, 34.0, 48.0, 20.0, 30.0, 36.0, 46.0]
  ]]
}
```

说明：
- 第三行参数是 `itemID=21`（mp33）首版建议值，仅用于联调起步。
- `itemID=21` 最终值应以训练评估回放结果回填，不建议长期使用首版建议值。

### 6.3 字段级占位模板（便于后端编译接入）

```json
{
  "detectItemIDs": ["2", "3", "21"],
  "detectItemParameters": [[
    ["item2_p0", "item2_p1", "item2_p2", "item2_p3", "item2_p4", "item2_p5", "item2_p6", "item2_p7"],
    ["item3_p0", "item3_p1", "item3_p2", "item3_p3", "item3_p4", "item3_p5", "item3_p6", "item3_p7"],
    ["item21_p0", "item21_p1", "item21_p2", "item21_p3", "item21_p4", "item21_p5", "item21_p6", "item21_p7"]
  ]]
}
```

注：
- 示例中的参数值是占位符；真实数值由后端编译填充。
- iOS 仅按顺序消费，不在端侧重算这些阈值。
- `itemID -> 17/33` 的路由由 iOS 端注册表维护，不在此配置中下发。

## 7. 实施顺序

1) 先验证 `2/3` 路径（保持现网逻辑不变）。  
2) 新增 `21` mp33 检测项策略与路由。  
3) 在 side_lift 配置中加入 `21` 做灰度。  
4) 达标后再迁移更多依赖 33 点的检测项。  

## 8. 验收点

- 配置驱动边界正确：iOS 无动作参数硬编码。
- `2/3/21` 可同帧运行且输出格式一致。
- 计数准确率与错误识别率优于仅 `2/3` 的基线。
- 参数顺序严格对齐（`ids.count == rows.count`，每行参数长度合法）。
