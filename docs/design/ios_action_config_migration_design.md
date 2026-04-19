# iOS 端 action_configs 迁移设计（Knieo，重构版）

## 1. 设计前提（按当前生产真实约束）

本方案遵循以下不可变前提：
- iOS 侧不维护“动作定义”，只消费外部下发的“检测项组合 + 检测项参数”。
- 同一检测项可跨动作复用；同一动作在不同难度下可下发不同参数。
- iOS 侧职责是：拉取配置、执行检测项逻辑、输出统一检测结果；不是在端侧固化动作参数。

因此迁移目标不是“把 side_lift 参数写进 iOS”，而是：
- 补全 iOS 视觉检测基础能力，使其能按外部检测项选择 YOLO 或 MediaPipe(33)；
- 新增一批基于 mp33 的检测项策略，并保持输出格式与现有 pipeline 完全对齐。

## 2. 当前链路复核（不改主框架）

保持以下链路不变：
- 配置输入：`ActionConfig.analysisServiceConfig.detectItemIDs + detectItemParameters`
- 执行主线：`PostureBusService -> PostureAnalysisServiceNew -> PostureAnalysisPipeline -> StrategyFactory`
- 事件输出：`PostureDetectionResult / PostureActionCompleted / PostureErrorSnapshot`

结论：
- 不改动作层，不改 Bus 协议，不改计数与语音总流程。
- 仅在“关键点来源层”和“检测项策略层”扩展。

## 3. 需要解决的核心问题

问题 A：检测项级别的 detector 选择
- 现状基本固定 YOLO。
- 目标：根据外部输入的检测项 ID，动态选择 YOLO17 / MP33 / 双路并行。

问题 B：17 点与 33 点策略共存
- 现有策略大量依赖 COCO17 keypoints。
- 新检测项可能依赖 MP33（toe/heel/foot_index 等）。
- 目标：允许同一轮 pipeline 中同时跑 17 点策略与 33 点策略。

问题 C：输出格式统一
- 不论策略基于 YOLO 还是 MP33，结果必须落为现有 `DetectionResult` 结构，避免改上层。

## 4. 目标架构（检测项驱动 detector）

## 4.1 路由来源改为 iOS 内置映射（不要求后端新增字段）

采用你建议的方式：
- 后端继续只下发 `detectItemIDs + detectItemParameters`。
- iOS 端维护静态注册表：`itemID -> keypoint_profile(yolo17/mp33)`。
- pipeline 根据 `detectItemIDs` 查询注册表，决定本轮需要跑 YOLO17、MP33 或双路并行。

示例（iOS 内置，不由后端下发）：

```text
itemProfileMap = {
  "2":  yolo17,
  "3":  yolo17,
  "21": mp33,
  "22": mp33
}
```

默认策略：
- 注册表中不存在的 itemID，默认按 `yolo17`（并打印告警日志）。
- 新增 mp33 检测项必须先在注册表登记再上线。

## 4.2 iOS 运行时路由

运行时新增 `DetectorRoutingResolver`（检测项路由器）：
- 输入：`detectItemIDs`
- 输出：
  - `requiredProfiles = {yolo17, mp33}`（本帧需要跑哪些 detector）
  - `itemID -> keypoint_profile` 映射（来自 iOS 注册表）

当同一轮同时存在 yolo17 和 mp33 检测项时：
- 同帧执行双 detector（或缓存/降频策略），生成两个关键点视图；
- 每个 strategy 按 itemID 绑定到对应视图，不互相影响。

## 5. 关键点统一层（避免大量兼容改造）

## 5.1 Canonical 视图定义

新增统一容器 `KeypointViews`：
- `yolo17`: 当前 COCO17 关键点字典（沿用现有策略输入）
- `mp33`: MediaPipe 33 关键点字典（新增策略使用）

建议统一规则：
- 坐标量纲统一（建议像素坐标）
- 置信度统一语义（缺失判定一致）
- 别名表统一（如 `left_toe` / `left_foot_index`）

## 5.2 不做强制 33->17 投影

按你新要求，策略是：
- 老检测项继续吃 yolo17 原视图；
- 新 mp33 检测项直接吃 mp33 原视图；
- 仅在需要 fallback 时才做可选投影，不作为主链路前置步骤。

这样能最小化兼容成本，并保持已有 17 点策略稳定。

## 6. 新增检测项策略的落地规范

## 6.1 编号规则

新增 mp33 检测项使用新 ID（递增，不复用旧 ID）。
- 现有最大为 `20`，新增从 `21` 开始。
- 示例：
  - `21`: `AnkleDorsiflexionLateralMP33Strategy`
  - `22`: `HipAbductionToeHeightMP33Strategy`

补充硬规则（按你的要求）：
- 若“计算逻辑相同但关键点体系不同（17 vs 33）”，**必须定义为新检测项 ID**，不能复用旧 ID。
- 例如“与 item2 逻辑相同但使用 mp33”的版本，应新建 `21+`，而不是复用 `2`。
- 这样可避免映射歧义，并保证线上路由确定性。

## 6.2 策略接口保持不变

所有新策略仍实现既有 `DetectionItemStrategy` 协议：
- `process(keypoints:timestamp:)`
- `updateParameters(_:)`
- `reset()/forceComplete()`

区别仅在于：
- 策略内部读取 `mp33` 关键点视图。
- 输出仍是标准 `DetectionResult`（`itemID/score/errorInfo/phase/raiseCount/isCompleted/errorMetrics`）。

## 6.3 参数协议

参数仍由外部下发，iOS 不固化动作参数。
- 可沿用现有 `[0..7]` 相位/评估索引协议；
- 若某 mp33 检测项参数维度不同，由后端与策略约定，但必须在检测项维度文档化。

## 6.4 iOS 注册表治理

新增检测项时需同步维护三张表（均在 iOS 侧）：
- `itemID -> keypoint_profile`（17/33 路由）
- `itemID -> strategy constructor`（StrategyFactory 注册）
- `itemID -> parameter schema`（参数长度与索引语义）

上线前校验：
- `detectItemIDs` 中每个 itemID 在三张表均可解析；
- 若 profile 为 mp33，则必须可获取 mp33 关键点视图；
- 参数长度与 schema 一致，不一致直接拒绝配置并打日志。

## 7. 与生产逻辑兼容策略

为避免影响线上：
- 默认行为保持 YOLO17 + 老策略。
- 仅当配置中出现 mp33 检测项时才启用 mp33 detector。
- 若 mp33 detector 初始化失败：
  - 该类检测项返回 `missingBodyPart` / 降级状态；
  - 不影响 yolo17 检测项继续运行。

## 8. 实施阶段（按风险最小优先）

阶段 1（基础能力）
- 增加 iOS 内置 `itemID -> profile` 注册表与 detector 路由器。
- 支持同帧 yolo17/mp33 双视图输出。
- pipeline 维持原输出协议。

阶段 2（策略扩展）
- 增加首批 mp33 策略（ID 21+）。
- 在 `StrategyFactory` 注册新策略。

阶段 3（灰度验证）
- 同动作配置 A/B：
  - 版本 A：旧检测项组合
  - 版本 B：含 mp33 新检测项组合
- 比对计数偏差、错误识别一致率、性能与耗电。

阶段 4（规模化迁移）
- 逐动作把依赖 33 点几何信息的检测项迁移为新 ID。
- 老检测项按需保留，长期共存。

## 9. 验收标准

- 不改动作层、参数层职责边界：iOS 不写死动作参数。
- 新旧检测项可在同一动作配置中并存运行。
- 上层业务无感：事件与字段格式不变。
- 性能达标：双 detector 开启后帧率与耗电在可接受范围。

## 10. 结论

最终设计不是“在 iOS 写 side_lift 参数”，而是：
- 保持“外部配置驱动检测项组合”的生产架构；
- 在 iOS 增加“检测项级 detector 路由 + mp33 新检测项策略”；
- 用新增检测项 ID（21+）承接 MediaPipe 33 点算法；
- 输出继续对齐现有 pipeline，实现无缝接入。

## 11. 实施状态标记（已实现/待实现）

以下状态用于和 iOS 仓库当前实现对齐（Knieo）：

已实现：
- [x] 保持输入协议不变：继续消费 `detectItemIDs + detectItemParameters`。
- [x] 检测项级路由能力：支持按 `itemID -> keypoint_profile` 决定关键点来源（17/33）。
- [x] 双路关键点处理：在同一轮分析中可同时处理 yolo17 与 mp33 视图。
- [x] 新增 mp33 检测项示例：`itemID=21`（ankle dorsiflexion lateral）策略并接入策略工厂。
- [x] 对旧检测项保持兼容：未注册项默认按 yolo17 处理。

待实现（建议下一阶段）：
- [ ] 将注册表三张表（profile/strategy/schema）收敛为单一配置源并加启动时校验。
- [ ] 完成 `itemID=21` 的线上参数回归（以训练评估结果替换联调参数）。
- [ ] 增加 detector 异常降级观测指标（命中率、回退次数、耗时）。
- [ ] 构建动作级 A/B 评估面板（`2/3` vs `2/3/21`）。

## 12. 新动作迁移实施步骤（SOP）

面向后续新增动作，按以下步骤执行：

1. 动作训练产出  
- 使用通用训练脚本生成配置与评估产物（配置 JSON、数据拆分清单、评估结果）。

2. 检测项清单盘点  
- 将训练产物中的核心 metric 映射到 iOS 现有 itemID。  
- 若依赖 33 点且无法安全复用旧 itemID，分配新 ID（从 `21+` 递增）。

3. 注册表与策略实现  
- 在 iOS 注册三张表：`itemID -> profile`、`itemID -> strategy`、`itemID -> parameter schema`。  
- 新增/更新对应策略，保持 `DetectionResult` 输出结构不变。

4. 后端配置接入  
- 后端只下发 `detectItemIDs + detectItemParameters`。  
- 参数顺序严格与 `detectItemIDs` 一一对应。

5. 联调验证  
- 先跑最小组合（旧项），再跑完整组合（含新 mp33 项）。  
- 关注：计数准确率、错误识别率、误报漏报、性能（FPS/耗电）。

6. 灰度与发布  
- 按动作或难度分层灰度。  
- 监控注册表缺项、参数长度不匹配、mp33 回退等告警。  
- 达标后放量并固化参数版本。
