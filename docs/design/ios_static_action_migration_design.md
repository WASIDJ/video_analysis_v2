# iOS 静态检测项策略迁移与接入规范

## 1. 文档目的
本文档旨在明确 iOS 端如何接入、管理和消费“静态动作（Static Actions）”的检测项配置。由于静态动作的判定逻辑（基于多条件 AND 的稳态维持）与动态动作（基于 P1/P2 状态机的波峰波谷流转）存在本质差异，iOS 端需要在不破坏现有 `PostureAnalysisPipeline` 架构的前提下，新增对静态策略的支持。

## 2. 关键边界与架构约束
- **输入不变**：后端依然仅下发 `detectItemIDs`（数组）和 `detectItemParameters`（二维数组）。
- **策略类型隔离**：静态动作的判定逻辑完全独立于动态动作，iOS 需要新增一个基础策略抽象类（如 `BaseStaticHoldMP33Strategy`）。
- **统一输出**：静态策略的输出仍必须封装为标准的 `DetectionResult`（含 `itemID`, `isCompleted`, `raiseCount`, `errorInfo` 等），以便上层业务（如语音播报和 UI 进度）无缝消费。
- **计次转计时机制**：动态动作的 `raiseCount` 语义为“完成次数”；静态动作的 `raiseCount` 语义被重定义为“累计达标秒数”（1 count = 1 second holding）。

## 3. 静态检测项核心逻辑设计

### 3.1 参数协议映射 (8槽位纯数字协议)
为了复用现有的 8 槽位 `detectItemParameters` 数组协议，我们约定静态检测项的参数槽位如下：

| 索引 | 语义定义 | 说明 |
|---|---|---|
| `[0]` | `normal_range.min` | 合格区间下界 |
| `[1]` | `normal_range.max` | 合格区间上界 |
| `[2]` | `needs_absolute` | 是否取绝对值（1.0 表示是，0.0 表示否，抹平朝向差异） |
| `[3]` | `debounce_seconds` | 抗抖动阈值（推荐 0.5，表示需连续达标 0.5s 才进入 Holding） |
| `[4..7]` | 预留/填充 `0.0` | 暂不参与状态机 |

### 3.2 状态机与防抖逻辑 (Debounce & Timer)
每个静态 `Strategy` 内部只维护两个状态：`Resting` (未达标/休息) 和 `Holding` (维持中)。

**逻辑流转：**
1. **输入计算**：根据配置，计算当前帧的 Metric 值（如提取 `[2]` 槽位为 1.0，则对当前计算角度取 `abs()`）。
2. **条件判断**：判断该值是否在 `[normal_range.min, normal_range.max]` 内。
3. **进入 Holding**：如果连续达标时间 >= `debounce_seconds`，状态由 `Resting` 切换为 `Holding`。
4. **退出 Holding**：如果连续不达标时间 >= `debounce_seconds`，状态由 `Holding` 切换为 `Resting`，并在 `DetectionResult` 中抛出错误码（用于触发“腰部塌陷”等纠正语音）。
5. **计时累加**：在 `Holding` 状态下，系统以帧率为基准累加时间。当累计时间跨过一个完整的 1 秒时（例如从 1.9s 跨入 2.0s），抛出一个 `isCompleted = true` 或 `raiseCount += 1` 的事件（取决于上层业务的消费习惯，建议抛出 `raiseCount` 增加以复用进度条逻辑）。

### 3.3 动作级聚合层改造 (Pipeline / Action 聚合)
由于静态动作的达标要求是**多条件同时满足（AND 逻辑）**，当后端下发 `detectItemIDs: ["40", "41"]` 时：
- `Pipeline` 会分别运行 40 号和 41 号的 `Strategy`。
- **聚合要求**：iOS 动作级总控必须判断：**只有当 40 号和 41 号同时处于 `Holding` 状态时，总控计时器才允许累加秒数**。
- 若 40 号达标，41 号在 `Resting`，总控计时器暂停，并将 41 号抛出的错误反馈给用户。

## 4. iOS 注册表扩展规范

新增静态检测项必须按照现有的注册表规则登记，并明确标记为 MP33 静态策略：
- **`itemID -> keypoint_profile`**: 登记为 `mp33`。
- **`itemID -> strategy constructor`**: 映射到对应的子类（例如 `TrunkLeanStaticHoldMP33Strategy`）。
- **`itemID -> parameter schema`**: 登记为静态专用 Schema（如上文 3.1 节定义的 4 个有效槽位）。

## 5. 冲突清单与处理建议

| 冲突点 | 描述 | 处理建议 |
|---|---|---|
| **聚合逻辑冲突** | 动态动作的多个 item 可能是 OR 关系（左右脚任一完成即计次）或分别计次。静态动作必须是强 AND 关系。 | **必须在端侧 Action 总控层增加 `ActionType` 判断。** 当识别为静态动作时，将所有分配给该动作的 item 的状态进行逻辑与运算（`itemA.isHolding && itemB.isHolding`），总控自己维护一个大计时器。 |
| **数据源冲突** | 静态动作对微小角度抖动极其敏感，可能导致频繁的 Resting/Holding 切换语音播报。 | 必须严格实现 `debounce_seconds`（滞回区间）。只有脱离安全区持续 0.5s~1.0s 以上才算作真正脱离，并在语音播报后设置较长的冷却时间（Cooldown）。 |