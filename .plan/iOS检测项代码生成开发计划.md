# iOS 检测项代码生成开发计划

> [!SUMMARY]
> 当前目标已经从“大而全的动作迁移自动化”收敛为“训练后检测项 iOS 候选代码与配置 dry-run 生成”。最近两次提交已经完成 Python 侧 dry-run 闭环；本轮结合 `/home/ryou/myworkspace/develop/INTERSHIP/banlan/coaichingapp-IOS` 的 `origin/dev` 继续 review，确认 dev 分支已有真实 iOS 姿态检测 runtime。当前工作区仍停在 `master`，但 `origin/dev` 已包含 `Knieo/Sources/Vision/PostureAnalysis/...`，因此下一步工作从“找不到 runtime”调整为“扫描 dev runtime，确认 item 7/8 已有、22/23 待补，再按真实协议修正 Swift 模板”。

## 1. Review 后结论

### 1.1 已经能做到

- 从现有 `train_action.py` 训练入口追加可选 iOS codegen dry-run，不需要另起一套独立平台。
- 训练成功后直接复用 `result["generated_config_path"]`，从 trained action config 提取 enabled metrics。
- 通过 `config/ios_codegen/metric_item_registry.json` 把 Python metric 映射到 iOS item 信息。
- 为 `straight_leg_raise` 生成 4 个检测项参数：
  - `ankle_dorsiflexion` -> item `8`，复用候选。
  - `knee_flexion_compensation` -> item `7`，复用候选。
  - `hip_abduction` -> item `22`，生成候选 Swift strategy。
  - `knee_symmetry` -> item `23`，生成候选 Swift strategy。
- 输出 review 产物：
  - `ios_payload.json`
  - `codegen_plan.json`
  - `validation_result.json`
  - `generated/*.swift`
  - `patches/*.txt`
  - `summary.md`
- 默认不写入 iOS 项目；`--ios-codegen-write` 当前仍应保持未开放。
- 已实现 `--ios-project` 只读 scanner：可以扫描 Swift runtime、`StrategyFactory` 已注册 item，并把每个目标 item 标记为 `verified_present`、`verified_missing` 或 `not_verifiable`。

### 1.2 现在不能承诺

- 不能承诺当前工作区 `master` 分支包含本地检测策略运行时；runtime 在 `origin/dev`。
- 不能承诺当前生成的 Swift strategy 能直接加入 `origin/dev` 并编译通过；模板还没有完全对齐真实 `DetectionItemStrategy` 协议。
- 不能把 `patches/*.txt` 描述成可直接 `git apply` 的补丁；它现在只是人工 review 片段。
- 不能把 scanner 结果等同于功能验收。scanner 只能确认注册入口是否存在，不能证明动作效果正确。
- 不能自动写入 iOS 项目、自动提交 iOS PR、自动合并。
- 不能保证 8/7 复用在产品效果上完全等价；目前只是 registry 语义上的候选复用。

### 1.3 DDL 口径

本开发计划不包含 DDL。

如果后续要把 `detectItemIDs`、`detectItemParameters` 或检测项注册信息落到后端配置表，需要单独拆 DDL 评审，至少包括：

- 表结构或字段变更说明。
- 兼容旧 action 配置的策略。
- 回滚方式。
- 灰度和验证方式。
- 谁负责执行数据库变更。

在 DDL 没有单独评审前，本计划只能交付 dry-run 文件和人工 review 材料，不能承诺线上配置落库。

## 2. 当前事实依据

### 2.1 最近两次相关提交

`43cab34 梳理 iOS 检测项迁移方案`

- 新增原始开发计划和理解文档。
- 目标是先沉淀迁移路径，不改变运行时行为。

`040f96a 从训练配置生成 iOS 检测项代码`

- 新增 `src/core/ios_codegen/`。
- 新增 `config/ios_codegen/metric_item_registry.json`。
- 扩展 `train_action.py`，支持：
  - `--ios-codegen`
  - `--ios-codegen-output`
  - `--ios-project`
  - `--ios-codegen-write`
- 新增单测：
  - `tests/unit/test_ios_codegen.py`
  - `tests/unit/test_train_action_ios_codegen.py`

### 2.2 iOS 仓库 review 结果

review 路径：

```text
/home/ryou/myworkspace/develop/INTERSHIP/banlan/coaichingapp-IOS
```

分支事实：

- 当前工作区：`master...origin/master`。
- 已更新的开发分支：`origin/dev`，提交 `c2fd93d add feature:more detectItems`。
- 本轮 review 使用 `git show origin/dev:...` 和 `git grep origin/dev`，未切换或修改 iOS 工作区。

`origin/dev` 中已经存在真实姿态检测 runtime：

```text
Knieo/Sources/Vision/PostureAnalysis/Domain/Models/DetectionTypes.swift
Knieo/Sources/Vision/PostureAnalysis/Domain/Strategy/DetectionItemStrategy.swift
Knieo/Sources/Vision/PostureAnalysis/Domain/Strategy/StrategyFactory.swift
Knieo/Sources/Vision/PostureAnalysis/Domain/Strategy/Items/*.swift
Knieo/Sources/Vision/PostureAnalysis/Interface/PostureAnalysisServiceNew.swift
Knieo/Sources/Service/Action/ActionDetectionParameterFetcher.swift
Knieo/Sources/Bus/Helpers/PostureBusHelper.swift
```

关键协议事实：

- iOS 端策略协议是 `DetectionItemStrategy`。
- 基类是 `BaseDetectionItemStrategy`。
- 关键点类型是 `typealias Keypoints = [String: [Float]]`，不是旧模板假设的 `KeypointViews`。
- `DetectionResult` 使用 `score: Float`、`phase`、`raiseCount`、`isCompleted` 等字段。
- `StrategyFactory.createStrategy(for:parameters:)` 通过 `switch itemID` 注册已有检测项。
- `ActionDetectionParameterFetcher` 从 `/app-api/resources/user-action-detection-config/get?actionId=` 拉取个性化参数，并按 `detectItemIDs` 顺序组装 `[[Float]]`。
- `PostureBusHelper.configurePostureAnalysis(...)` 接收 `importantBodyParts`、`detectItemIDs`、`detectItemParameters: [[[Float]]]`。

`origin/dev` 的 `StrategyFactory` 已注册 item：

```text
2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21
SingleCalfRaise, DorsiflexionHold, SingleLegStance
```

对 `straight_leg_raise` 的直接影响：

- item `7`、`8` 已在 iOS dev runtime 中注册，可以作为复用候选继续检查。
- item `22`、`23` 没有注册，应走新增策略 review。
- 当前 Python 生成的 Swift 模板必须改成继承/适配 `BaseDetectionItemStrategy`，使用 `[Float]` 参数和 `Keypoints` 字典。

## 3. 目标与非目标

### 3.1 第一阶段目标

第一阶段只做一个可验证闭环：

```text
训练成功
  -> 读取 generated_config_path
  -> 生成 iOS dry-run 候选产物
  -> 输出校验结果
  -> 交给开发者 review
```

命令形态：

```bash
python train_action.py \
  --config scripts/straight_leg_raise_training.json \
  --ios-codegen \
  --ios-codegen-output data/ios_codegen/straight_leg_raise
```

如果提供 iOS 项目路径，第一阶段也只能做只读扫描：

```bash
python train_action.py \
  --config scripts/straight_leg_raise_training.json \
  --ios-codegen \
  --ios-project /home/ryou/myworkspace/develop/INTERSHIP/banlan/coaichingapp-IOS \
  --ios-codegen-output data/ios_codegen/straight_leg_raise
```

注意：如果要扫描本机文件系统，`coaichingapp-IOS` 工作区需要切到包含 `Knieo/Sources/Vision/PostureAnalysis` 的 dev 分支。当前本机工作区仍在 `master`，直接扫描该目录会得到 `not_verifiable`；本轮人工 review 已确认 `origin/dev` 有 runtime。

### 3.2 非目标

- 不做一次覆盖所有动作的迁移平台。
- 不自动修改 iOS 仓库。
- 不自动修改 Xcode project。
- 不自动提交或合并 PR。
- 不在本计划内处理数据库 DDL。
- 不在缺少真实 iOS runtime 类型时承诺 Swift 可编译。

## 4. 现有链路与已完成能力

当前链路：

```text
train_action.py
  -> BatchProcessor.process()
  -> result["generated_config_path"]
  -> PostTrainEvaluator.evaluate_from_batch_result()
  -> artifacts.evaluation_path
  -> run_ios_codegen(...)
  -> dry-run artifacts
```

`run_ios_codegen(...)` 当前接口：

```python
def run_ios_codegen(
    action_id: str,
    action_config_path: str | Path,
    output_dir: str | Path,
    evaluation_path: str | Path | None = None,
    ios_project: str | Path | None = None,
    write: bool = False,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
) -> IosCodegenResult:
    ...
```

已完成能力：

- 读取 action config。
- 读取 registry。
- 根据 enabled metrics 生成 item 参数。
- 未知 metric 阻断生成，不猜测映射。
- 为 `generate` 项输出候选 Swift。
- 输出 summary、payload、plan、validation。
- 只读扫描 iOS 项目路径，识别 runtime 和 StrategyFactory item 注册状态。
- `write=True` 时显式阻断。

当前缺口：

- `evaluation_path` 参数尚未参与实际策略。
- patch 文本只是简化提示，不是可应用补丁。
- Swift 模板还没有按 `origin/dev` 的真实 `DetectionItemStrategy` / `BaseDetectionItemStrategy` 协议改写。
- scanner 当前扫描文件系统路径，不会自动读取 git remote ref；如果 iOS 工作区不在 dev 分支，结果会反映当前工作区而不是 `origin/dev`。

## 5. dry-run 输出定义

输出目录：

```text
data/ios_codegen/{action_id}/
```

产物：

```text
ios_payload.json
codegen_plan.json
validation_result.json
generated/
  HipAbductionMP33Strategy.swift
  KneeSymmetryMP33Strategy.swift
patches/
  profile_registry.patch.txt
  strategy_factory.patch.txt
  parameter_schema.patch.txt
summary.md
```

说明：

- `ios_payload.json`：给后端/iOS 配置 review 的候选 payload。
- `codegen_plan.json`：本次生成计划，说明 metric 到 item 的映射。
- `validation_result.json`：dry-run 校验结果。
- `generated/*.swift`：候选 Swift strategy，不保证当前 iOS 工程可编译。
- `patches/*.txt`：人工 review 片段，不保证可直接应用。
- `summary.md`：给开发者看的摘要。

## 6. `straight_leg_raise` 第一版规则

### 6.1 registry 映射

| metric | itemID | 当前状态 | builder/generator | 说明 |
|---|---:|---|---|---|
| `ankle_dorsiflexion` | `8` | `reuse` | `item8_dynamic_v1` | 候选复用，需真实 iOS runtime 验证 |
| `knee_flexion_compensation` | `7` | `reuse` | `item7_static_v1` | 候选复用，需真实 iOS runtime 验证 |
| `hip_abduction` | `22` | `generate` | `hip_abduction_mp33_v1` | 生成候选 Swift |
| `knee_symmetry` | `23` | `generate` | `knee_symmetry_mp33_v1` | 生成候选 Swift，单位需复核 |

### 6.2 参数规则

`range8_v1`：

```text
[normal_min, excellent_min, excellent_max, normal_max,
 normal_min, excellent_min, excellent_max, normal_max]
```

`item7_static_v1`：

```text
[normal_min, normal_max, excellent_min, excellent_max,
 normal_min, target, target, normal_max]
```

`item8_dynamic_v1`：

```text
[
  count_layer.thresholds.exit_p2,
  count_layer.thresholds.enter_p2,
  count_layer.thresholds.enter_p2,
  count_layer.thresholds.exit_p1,
  metrics.ankle_dorsiflexion.normal_range[0],
  metrics.ankle_dorsiflexion.excellent_range[0],
  semantic_layer.hold.exit_conditions[0].value,
  metrics.ankle_dorsiflexion.excellent_range[1]
]
```

## 7. iOS 项目扫描计划

`--ios-project` 已实现只读 scanner。scanner 只输出事实，不修改项目。

### 7.1 扫描目标

扫描目标分三层：

1. 工程是否存在本地检测运行时：
   - `DetectionItemStrategy`
   - `BaseDetectionItemStrategy`
   - `Keypoints`
   - `DetectionResult`
2. 工程是否存在注册/工厂入口：
   - `StrategyFactory`
   - `StrategyFactory.createStrategy(for:parameters:)` 中的 `case "itemID"`
3. 工程是否已有目标 item：
   - item `7`
   - item `8`
   - item `22`
   - item `23`

### 7.2 扫描状态

扫描结果建议使用这些状态：

| 状态 | 含义 |
|---|---|
| `verified_present` | 在 iOS 项目中确认存在 |
| `verified_missing` | 找到 runtime/registry，但目标 item 缺失 |
| `not_verifiable` | 没有找到可判断的 runtime/registry |
| `not_scanned` | 本次未传 `--ios-project` |

对 `origin/dev` 的预期扫描结果：

```text
item 8  -> verified_present
item 7  -> verified_present
item 22 -> verified_missing
item 23 -> verified_missing
```

如果扫描当前未切到 dev 的 `master` 工作区，结果应为 `not_verifiable`，这是工作区分支事实，不代表 dev 分支没有 runtime。

本轮已用 `git archive origin/dev` 展开到 `/tmp/coaichingapp-ios-dev-scan-0422` 并执行 dry-run，实测结果：

```text
scan.status = verified_runtime
runtime_symbols = DetectionItemStrategy / BaseDetectionItemStrategy / DetectionResult / Keypoints / StrategyFactory
item 8  -> verified_present
item 7  -> verified_present
item 22 -> verified_missing
item 23 -> verified_missing
```

## 8. 开发 Milestones

### Milestone 0：确认真实 iOS 接入面

状态：已完成。

目标：

- 检测项代码目标在 `coaichingapp-IOS` 的 `origin/dev` 分支。
- 真实 runtime 位于 `Knieo/Sources/Vision/PostureAnalysis`。
- iOS app 本地运行检测策略，并通过后端接口获取个性化参数。

验收：

- 已记录真实接入路径。
- 已确认当前工作区 `master` 与 `origin/dev` 的差异。

### Milestone 1：训练后 dry-run 入口

状态：已完成。

验收：

- 不传 `--ios-codegen` 时训练行为不变。
- 传 `--ios-codegen` 时训练成功后生成 dry-run 产物。
- `--ios-codegen-write` 不开放写入。

### Milestone 2：实现 iOS 项目只读 scanner

状态：已完成。

改动：

- 新增 scanner 模块，使用 `ios_project` 路径读取 Swift 文件。
- 输出 runtime、registry、item 的扫描状态。
- 把扫描结果写入 `codegen_plan.json` 和 `summary.md`。

验收：

- 不修改任何 iOS 文件。
- 能明确输出 `verified_present`、`verified_missing` 或 `not_verifiable`。
- 不再静默忽略 `ios_project` 参数。

### Milestone 3：根据真实 runtime 修正 Swift 模板

状态：部分完成。

前置条件：

- 已确认真实 iOS runtime 类型和协议。

改动：

- 根据真实 `DetectionItemStrategy` 协议调整模板。
- 根据真实 `Keypoints = [String: [Float]]` 调整关键点访问方式。
- 根据现有 `BaseDetectionItemStrategy`、`DetectionResult`、`GeometryUtils` / `MathUtils` 风格调整评分逻辑。
- 在 `StrategyFactory` 中增加 item `22`、`23` 的创建分支。

验收：

- 生成 Swift 不再引用旧假设的 `KeypointViews` 或 `ScoreRange`。
- 生成 Swift 使用 `BaseDetectionItemStrategy`、`Keypoints`、`DetectionResult?` 和 `[Float]` 参数。
- `strategy_factory.patch.txt` 输出 `case "22"` / `case "23"` 的真实工厂片段。
- 生成的 Swift 仍需进入 iOS 工程编译验证后，才能认为可合入。
- 缺关键点、参数长度错误、reset/forceComplete 行为符合真实协议。

macmini-lan 验证记录：

- 远端路径：`/Users/ryou/workspace/INTERNSHIP/banlan/coaichingapp-IOS`。
- 远端当前工作区仍是 `master...origin/master`，未被修改。
- `xcodebuild` 暂不可用，因为 `xcode-select -p` 指向 `/Library/Developer/CommandLineTools`，且未发现 `/Applications/Xcode*.app`。
- 当前 macmini 没有线键盘，之前的蓝牙输入状态也已丢失，暂时无法在机器本地完成 Xcode 环境修复或 GUI 编译测试。
- 已在远端 `/tmp/coaiching-ios-dev-typecheck` 创建 `origin/dev` 临时 worktree。
- 已把 codegen 生成的 `HipAbductionMP33Strategy.swift`、`KneeSymmetryMP33Strategy.swift` 放入临时 worktree，并临时 patch `StrategyFactory`。
- `swiftc -typecheck` 对核心 runtime + 全部 strategy 文件通过；唯一 warning 来自 dev 既有 `SingleLegStanceStrategy.swift` 未使用变量，不是本次生成代码。

### Milestone 4：真实集成材料

前置条件：

- Milestone 2 和 3 完成。

改动：

- patch 文本升级为可 review 的明确集成步骤。
- 如目标仓库允许，再考虑生成可应用 patch。

验收：

- 开发者能通过 git diff review。
- iOS 编译/测试通过前不允许自动合并。

### Milestone 5：写入模式

前置条件：

- 真实 iOS 编译验证已通过。
- 已有回滚方式。

改动：

- 才允许讨论 `--ios-codegen-write`。

验收：

- 默认仍 dry-run。
- 写入必须显式开启。
- 写入后必须能展示完整 diff。

## 9. 测试计划

现有测试继续保留：

```bash
.venv/bin/python -m pytest tests/unit/test_ios_codegen.py tests/unit/test_train_action_ios_codegen.py
```

新增 scanner 后补充测试：

- 无 runtime 符号时，输出 `not_verifiable`。
- 有 `DetectionItemStrategy` / `StrategyFactory` 但没有 item `22/23` 时，输出 `verified_missing`。
- 有 item `7/8` 时，输出 `verified_present`。
- `ios_project` 不存在时 codegen 失败，不静默跳过。
- scanner 不修改传入的 iOS 项目目录。

真实集成前测试：

- 目标 iOS runtime 编译测试。
- 生成 Swift 的 SwiftLint/format 检查，前提是目标项目已有对应工具。
- 手工 review `ios_payload.json` 与后端/客户端消费格式是否一致。

## 10. 风险与待确认

| 风险 | 影响 | 当前处理 |
|---|---|---|
| 当前工作区在 `master`，runtime 在 `origin/dev` | 文件系统扫描可能得到 `not_verifiable` | 扫描前切到 dev 或提供 dev 工作区 |
| Swift 模板仍按旧假设写 | 不能直接编译 | 下一步按真实协议改模板 |
| patch 文本不是可应用 patch | 容易误解为能直接集成 | 文档明确为 review 片段 |
| `knee_symmetry` unit/归一化待确认 | iOS 阈值语义可能不一致 | 继续作为 warning/review blocker |
| 8/7 已注册但效果未验收 | 产品效果可能不等价 | 标记需算法 review |
| DDL 未评审 | 无法承诺线上配置落库 | DDL 单独拆评审 |
| 自动写入 iOS 风险大 | 可能破坏工程或 Xcode project | 默认不实现写入 |

## 11. Review Checklist

后续 review 重点：

- 当前 dry-run 产物是否足够让开发者 review。
- `ios_payload.json` 是否符合后端/iOS 实际消费格式。
- `DetectionItemStrategy`、keypoint、score、参数 schema 是否已按 `origin/dev` 真实协议更新。
- 8/7 是否允许作为候选复用。
- 22/23 是否仍作为第一版生成目标。
- `knee_symmetry` 是否需要归一化修正。
- 是否需要 DDL；如果需要，必须另开 DDL 计划。

## 12. 下一步建议

下一步不要扩动作范围，先修正 Swift 模板以贴合 `origin/dev` 的真实 runtime。

最小下一步：

1. 让 iOS 工作区切到 dev，或准备一份 dev 分支工作树供 scanner 文件系统扫描。
2. 用 `--ios-project` 验证 item `7/8` present、`22/23` missing。
3. 按 `BaseDetectionItemStrategy` 改写 `HipAbductionMP33Strategy` 和 `KneeSymmetryMP33Strategy` 模板。
4. 更新 `StrategyFactory` patch 文本，让 item `22/23` 能被真实工厂创建。
5. 交给算法工程师先检查，再 review，最后进入 iOS app。
