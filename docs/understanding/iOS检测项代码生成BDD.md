# iOS 检测项代码生成 BDD

> [!SUMMARY]
> 本 BDD 面向业务、算法和 iOS 协作方，描述“训练完成后自动判断检测项是否已在 iOS 实现；未实现则生成 Swift 检测项代码；测试通过后再集成”的交付行为。第一版以 `straight_leg_raise` 为样例动作，默认 dry-run，不直接写入 iOS 项目。

## 1. 业务目标

当一个动作通过 `train_action.py` 完成训练后，系统应自动衔接 iOS 检测项代码生成流程：

```text
训练完成
-> 读取生成的 action config
-> 判断检测项 iOS 实现状态
-> 已实现则生成参数配置
-> 未实现则生成 Swift strategy 和注册片段
-> 校验通过后交付 review
```

## 2. 角色

| 角色 | 关注点 |
|---|---|
| 动作训练负责人 | 训练完成后能知道 iOS 侧还缺什么能力 |
| iOS 开发负责人 | 能 review 自动生成的 Swift strategy 和注册片段 |
| 后端配置负责人 | 能拿到 `detectItemIDs + detectItemParameters` |
| 算法验证负责人 | 能看到风险，例如错误类型未覆盖或阈值语义不明确 |
| 项目负责人 | 能判断该动作是否可以进入 iOS 联调 |

## 3. Feature: 训练后触发 iOS codegen dry-run

### Scenario: 默认训练流程不受影响

**Given** 使用 `train_action.py` 训练一个动作  
**And** 没有传入 `--ios-codegen`  
**When** 训练成功  
**Then** 系统只执行原有训练和自动评估流程  
**And** 不生成 iOS codegen 产物  
**And** 不改变原有输出行为  

### Scenario: 训练成功后执行 iOS codegen

**Given** 使用 `train_action.py` 训练 `straight_leg_raise`  
**And** 命令传入 `--ios-codegen`  
**When** 训练成功并生成 `generated_config_path`  
**Then** 系统读取本次生成的 action config  
**And** 提取核心检测项  
**And** 执行 iOS codegen dry-run  

## 4. Feature: 判断检测项是否已实现

### Scenario: 已实现检测项复用现有 itemID

**Given** `straight_leg_raise` 的训练产物包含 `ankle_dorsiflexion`  
**When** iOS codegen 查询检测项 registry  
**Then** 系统识别该检测项复用 `itemID=8`  
**And** 不生成新的 Swift strategy  
**And** 只生成对应参数行  

### Scenario: 已实现检测项复用静态膝角策略

**Given** `straight_leg_raise` 的训练产物包含 `knee_flexion_compensation`  
**When** iOS codegen 查询检测项 registry  
**Then** 系统识别该检测项复用 `itemID=7`  
**And** 不生成新的 Swift strategy  
**And** 只生成对应参数行  

### Scenario: 未实现检测项进入代码生成

**Given** `straight_leg_raise` 的训练产物包含 `hip_abduction`  
**When** iOS codegen 查询检测项 registry  
**Then** 系统识别该检测项需要新增 `itemID=22`  
**And** 生成 `HipAbductionMP33Strategy.swift`  
**And** 生成 profile、factory、schema 注册片段  

### Scenario: 膝对称性检测项进入代码生成

**Given** `straight_leg_raise` 的训练产物包含 `knee_symmetry`  
**When** iOS codegen 查询检测项 registry  
**Then** 系统识别该检测项需要新增 `itemID=23`  
**And** 生成 `KneeSymmetryMP33Strategy.swift`  
**And** 生成 profile、factory、schema 注册片段  
**And** 输出“单位和归一化需要确认”的风险提示  

## 5. Feature: 生成 iOS 配置参数

### Scenario: 生成 detectItemIDs

**Given** `straight_leg_raise` 包含 4 个核心检测项  
**When** iOS codegen 完成 registry 匹配  
**Then** 系统生成 `detectItemIDs`  
**And** 结果为 `["8", "7", "22", "23"]`  

### Scenario: 生成 detectItemParameters

**Given** 每个检测项都有参数 schema  
**When** iOS codegen 从 action config 读取 thresholds 和 count_layer  
**Then** 系统生成 4 行参数  
**And** 每行参数长度为 8  
**And** 参数行顺序与 `detectItemIDs` 一一对应  

## 6. Feature: 校验生成结果

### Scenario: 生成 Swift 不允许硬编码训练阈值

**Given** 系统生成 `HipAbductionMP33Strategy.swift`  
**When** 执行 dry-run 校验  
**Then** Swift 文件中不能写死训练阈值  
**And** 阈值必须通过 `updateParameters` 注入  

### Scenario: 缺少 registry 映射时阻断 codegen

**Given** action config 中出现未知 metric  
**When** iOS codegen 查询 registry  
**Then** 系统标记 codegen 失败  
**And** 输出 `REGISTRY_MISSING_METRIC`  
**And** 不让系统猜测 itemID  

### Scenario: 参数长度不符合 schema 时阻断集成

**Given** 某检测项 schema 要求 8 个参数  
**When** 参数生成结果不是 8 个值  
**Then** 系统标记校验失败  
**And** 不允许进入集成  

## 7. Feature: 集成前 review

### Scenario: 默认只 dry-run 不写 iOS 项目

**Given** 命令传入 `--ios-codegen`  
**And** 没有传入写入开关  
**When** iOS codegen 运行完成  
**Then** 系统只生成 dry-run 文件  
**And** 不修改 iOS 项目  
**And** 输出 review 所需的 Swift 文件、patch 片段和配置 payload  

### Scenario: 输出 codegen summary

**Given** iOS codegen dry-run 成功  
**When** `train_action.py` 打印训练结果  
**Then** 输出中包含 iOS codegen summary  
**And** 展示 `ios_payload.json` 路径  
**And** 展示生成的 Swift strategy 列表  
**And** 展示待确认风险  

## 8. 第一版验收

第一版完成时，应满足：
```bash
~/myworkspace/develop/INTERSHIP/banlan/video_analysis_ryou main* ⇡                                                                                                                 13:01:16
video_analysis_ryou ❯ pytest tests/unit/test_ios_codegen.py  tests/unit/test_train_action_ios_codegen.py  -v
=================================================================================== test session starts ====================================================================================
platform linux -- Python 3.11.14, pytest-9.0.3, pluggy-1.6.0
rootdir: /home/ryou/myworkspace/develop/INTERSHIP/banlan/video_analysis_ryou
configfile: pyproject.toml
plugins: anyio-4.13.0, asyncio-1.3.0, cov-7.1.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 5 items

tests/unit/test_ios_codegen.py ...                                                                                                                                                   [ 60%]
tests/unit/test_train_action_ios_codegen.py ..                                                                                                                                       [100%]

==================================================================================== 5 passed in 0.70s =====================================================================================
```

- `train_action.py` 支持 `--ios-codegen`。
- 不传 `--ios-codegen` 时原流程不变。
- `straight_leg_raise` 能生成 `detectItemIDs = ["8", "7", "22", "23"]`。
- `hip_abduction` 能生成 `HipAbductionMP33Strategy.swift`。
- `knee_symmetry` 能生成 `KneeSymmetryMP33Strategy.swift`。
- 生成 Swift 不硬编码训练阈值。
- 未知 metric 会阻断 codegen，而不是由系统猜测。
- dry-run 成功后，产物可交给业务、算法和 iOS 共同 review。

