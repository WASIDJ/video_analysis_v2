# Video Analysis Ryou TDD Development Plan

## 1. Goal

以 [plan/task.md](/home/ryou/myworkspace/develop/INTERSHIP/banlan/video_analysis_ryou/plan/task.md) 的 `task1` 和 `task2` 为主线，先把训练数据管理和参数迭代系统做成可测试、可追溯、可回滚的闭环，再接入现有 `training / analysis / config` 模块。

本计划默认采用 TDD:

1. 先写行为测试定义边界。
2. 跑出失败结果确认需求未满足。
3. 只写最小实现让测试通过。
4. 在测试保护下重构。

## 2. Current Baseline

现有代码已经具备这些基础能力：

- `src/core/analysis/*`: 指纹、探索模式、模板生成。
- `src/core/training/*`: 特征验证、错误条件学习、训练管道、批处理入口。
- `src/core/config/*`: 动作配置、版本更新、执行记录。

当前明显缺口：

- 没有训练数据集管理模块，无法做训练/验证/测试拆分。
- 没有误判回流与待标注池模型。
- 没有迭代任务状态机、触发器、评估器、版本仓库。
- `training` 和 `analysis` 关键模块单测覆盖明显不足。
- 当前仓库还有既有基线问题：
  - `tests/unit/test_geometry.py` 有失败用例。
  - `src/api/main.py` 的导入路径目前不正确。

## 3. Delivery Strategy

优先顺序不是“先把功能堆完”，而是先把可演进骨架和测试面搭起来：

1. 稳定测试基线
2. 交付 task1 的数据域模型与回流链路
3. 交付 task2 的迭代编排与评估闭环
4. 最后补 API / CLI / 持久化接入

## 4. Proposed Modules

### 4.1 Task1: 视频数据管理

建议新增模块：

- `src/core/dataset/models.py`
  - `VideoSample`
  - `DatasetSplit`
  - `FeedbackSample`
  - `AnnotationTask`
- `src/core/dataset/splitter.py`
  - 按 `action_id + label` 分层拆分训练/验证/测试集
- `src/core/dataset/repository.py`
  - 样本入库、查询、状态更新
- `src/core/dataset/feedback_loop.py`
  - 低置信 / 误判样本回流
  - 多轮误判转待标注

### 4.2 Task2: 异步参数迭代触发器

建议新增模块：

- `src/core/iteration/models.py`
  - `IterationJob`
  - `IterationStatus`
  - `RetryPolicy`
- `src/core/iteration/state_machine.py`
  - `pending -> running -> succeeded / failed / cancelled`
- `src/core/iteration/triggers.py`
  - 新增数据量达到 20
  - 低置信样本量达到 10
  - 固定时间 24 小时
- `src/core/iteration/evaluator.py`
  - baseline / candidate 对比
- `src/core/iteration/versioning.py`
  - 数据版本、配置版本、回滚记录
- `src/core/iteration/orchestrator.py`
  - 触发训练、评估、回写、回滚

## 5. TDD Milestones

### Milestone 0: Stabilize Test Baseline

目标：

- 让后续 TDD 不建立在脆弱基线上。

先写/补的测试：

- `tests/unit/test_geometry.py`
  - 明确 `calculate_angle_2d` 的角定义是内角还是外角。
- `tests/unit/test_api_imports.py`
  - `src.api.main` 可导入，FastAPI app 可初始化。

完成标准：

- 当前已有单测通过。
- 测试命名统一为“一个测试只验证一个行为”。

### Milestone 1: Dataset Splitter

目标：

- 实现按 `action_id + label` 自动拆分训练/验证/测试集。

RED tests:

- `tests/unit/test_dataset_splitter.py`
  - 相同动作不同标签分别按比例拆分。
  - 样本不足时不丢失标签覆盖。
  - 指定随机种子时拆分稳定。
  - 同一 `sample_id` 不会同时出现在多个 split。

GREEN implementation:

- 先支持内存对象拆分。
- 再支持 repository 持久化。

REFACTOR:

- 抽出分层统计函数与冲突校验函数。

### Milestone 2: Feedback Loop

目标：

- 测试集低置信 / 误判样本自动回流。

RED tests:

- `tests/unit/test_feedback_loop.py`
  - 低置信样本被标记为 `confusing_sample`。
  - 误判样本进入回流队列且保留来源版本。
  - 多轮误判后转入 `pending_annotation`。
  - 已入待标注池的样本不会重复入队。

integration tests:

- `tests/integration/test_feedback_flow.py`
  - evaluator 输出 -> feedback loop -> repository 状态变化完整贯通。

### Milestone 3: Iteration State Machine

目标：

- 定义迭代任务生命周期与重试策略。

RED tests:

- `tests/unit/test_iteration_state_machine.py`
  - `pending` 只能转到 `running / cancelled`
  - `running` 只能转到 `succeeded / failed / cancelled`
  - 超过最大重试后不再回到 `pending`
  - 失败时记录错误原因与重试次数

integration tests:

- `tests/integration/test_iteration_retry_flow.py`
  - 临时失败会重试
  - 永久失败最终停止

### Milestone 4: Trigger Engine

目标：

- 达到阈值或定时条件时自动触发迭代。

RED tests:

- `tests/unit/test_iteration_triggers.py`
  - 新样本数达到 20 触发
  - 低置信样本达到 10 触发
  - 距离上次训练超过 24 小时触发
  - 同一窗口内不会重复触发

### Milestone 5: Evaluator + Versioning

目标：

- 训练后统一评估 baseline 和 candidate，并支持回滚。

RED tests:

- `tests/unit/test_iteration_evaluator.py`
  - candidate 优于 baseline 时标记可发布
  - 指标退化时拒绝发布
  - 评估结果绑定训练数据版本与配置版本
- `tests/unit/test_versioning.py`
  - 发布时生成新版本
  - 回滚时恢复 baseline 版本引用
  - 每次版本切换保留审计记录

integration tests:

- `tests/integration/test_candidate_promotion_flow.py`
  - trigger -> train -> evaluate -> publish / rollback 全链路

## 6. Test Pyramid

目标比例：

- 70% unit
- 20% integration
- 10% smoke / e2e

建议目录：

- `tests/unit/dataset/*`
- `tests/unit/iteration/*`
- `tests/integration/feedback/*`
- `tests/integration/iteration/*`
- `tests/smoke/test_training_job_smoke.py`

## 7. Immediate Test Enrichment

在真正开 task1/task2 之前，先补齐现有训练域基础测试：

- `tests/unit/test_feature_validator.py`
  - 验证报告聚合
  - 物理极限校验
  - 批量验证行为
- `tests/unit/test_error_learner.py`
  - 高偏差 / 低偏差阈值学习
  - 样本不足时不产出条件
  - 多错误类型分组学习
- `tests/unit/test_training_pipeline_helpers.py`
  - 标签判定
  - 指标聚合
  - 配置置信度
  - JSON 批处理配置解析

## 8. Acceptance Criteria

### Task1 acceptance

- 样本能按 `action_id + label` 分层拆分。
- 测试集低置信 / 误判样本能自动回流并带上混淆标签。
- 多轮误判样本进入待标注池，且状态可追踪。

### Task2 acceptance

- 迭代任务有明确状态机和重试上限。
- 三类触发器都可独立验证。
- baseline / candidate 对比结果可审计。
- 支持基于版本记录回滚。

## 9. Recommended Execution Order

1. 修复现有基线失败测试和导入问题。
2. 合入本次补充的训练域测试。
3. 按 Milestone 1 -> 5 开始 feature TDD。
4. 每个 milestone 结束时跑对应 unit + integration，而不是等到最后一次性验证。

## 10. Commands

```bash
uv run pytest tests/unit/test_feature_validator.py tests/unit/test_error_learner.py tests/unit/test_training_pipeline_helpers.py -q
uv run pytest tests/unit -q
uv run pytest tests/integration -q
```
