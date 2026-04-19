# iOS 检测项注册表执行清单

## 1. 目的

本清单面向 iOS 开发，作为“新增/迁移检测项”时的统一执行标准。  
目标：在不改现有业务主链路前提下，让检测项稳定支持 YOLO17 与 MP33 并存。

## 2. 范围与原则

- iOS 不定义动作参数，只消费后端下发的 `detectItemIDs + detectItemParameters`。
- detector 路由由 iOS 端“检测项注册表”决定，不依赖后端额外 profile 字段。
- 同逻辑但不同关键点体系（17 vs 33）必须使用不同 `itemID`（新增递增 ID）。

## 3. 注册表三张表（必须同时维护）

## 3.1 Item -> Keypoint Profile

用途：决定检测项走 `yolo17` 还是 `mp33`。

示例：

```text
2  -> yolo17
3  -> yolo17
21 -> mp33
22 -> mp33
```

## 3.2 Item -> Strategy Constructor

用途：`StrategyFactory` 可根据 itemID 构建正确策略实例。

示例：

```text
2  -> SideHipFlexionStrategy
3  -> SideKneeFlexionStrategy
21 -> AnkleDorsiflexionLateralMP33Strategy
```

## 3.3 Item -> Parameter Schema

用途：约束每个 item 的参数长度、索引语义、默认值策略。

建议格式（示意）：

```text
itemID=2, schema=v1, length=8, indexes=[p1Lower,p1Upper,p2Lower,p2Upper,evalP1Lower,evalP1Upper,evalP2Lower,evalP2Upper]
```

## 4. 新增检测项标准流程

1. 分配新 `itemID`（递增，不复用）。
2. 确认 keypoint profile（`yolo17` 或 `mp33`）。
3. 实现/接入策略类并在 `StrategyFactory` 注册。
4. 在注册表补齐三张表条目。
5. 与后端确认参数 schema 与下发顺序。
6. 回放验证计数/错误识别，观察性能（帧率、耗电）。
7. 灰度上线并监控日志。

## 5. 上线前校验 Checklist

- [ ] `detectItemIDs` 中每个 ID 在 profile 注册表中可解析。
- [ ] 每个 ID 在 `StrategyFactory` 有对应构造器。
- [ ] 每个 ID 的参数长度与 schema 一致。
- [ ] MP33 检测项在 MP33 detector 不可用时有降级/错误输出策略。
- [ ] 输出仍为统一 `DetectionResult` 字段，不改上层事件协议。
- [ ] 日志能定位：缺失 ID、参数错位、profile 路由错误。

## 6. 常见失败场景与处理

- 场景：后端新增了 `itemID`，iOS 未注册。  
处理：拒绝该 item 执行并打告警，避免静默误判。

- 场景：参数长度不匹配。  
处理：按 schema 校验失败，整项标记不可用并输出诊断日志。

- 场景：同逻辑复用旧 ID 但切换到 33 点。  
处理：禁止；必须新建 `itemID`，否则历史策略与参数语义会冲突。

## 7. side_lift 快速落地提示

- 保持旧项：`2(yolo17)`、`3(yolo17)`。
- 新增项：`21(mp33)` 用于 `ankle_dorsiflexion_lateral`。
- 先灰度 `2/3` vs `2/3/21` 两版本配置，比较计数和错误识别收益。
