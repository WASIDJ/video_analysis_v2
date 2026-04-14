# 视频分析系统架构 V2.0

## 架构目标

当前架构目标是把动作训练与参数迭代拆成 4 个明确层次：

1. **analysis**：从视频与姿态序列提取可比较特征
2. **training**：从训练样本生成 candidate 配置
3. **dataset**：管理样本、拆分、回流、待标注
4. **iteration**：管理触发、评估、发布、回滚

这次 task1/task2 落地后，系统不再只是“训练一个配置”，而是具备了最小闭环：

```text
split -> evaluate -> feedback -> trigger -> compare -> promote/rollback
```

## 模块架构

```text
src/core/
├── analysis/
│   ├── fingerprint.py
│   ├── exploration.py
│   └── template_generator.py
│
├── training/
│   ├── pipeline.py
│   ├── batch_processor.py
│   ├── feature_validator.py
│   └── error_learner.py
│
├── dataset/
│   ├── models.py
│   ├── splitter.py
│   ├── repository.py
│   └── feedback_loop.py
│
├── iteration/
│   ├── models.py
│   ├── job_store.py
│   ├── queue.py
│   ├── worker.py
│   ├── service.py
│   ├── runtime.py
│   ├── state_machine.py
│   ├── triggers.py
│   ├── evaluator.py
│   ├── versioning.py
│   └── orchestrator.py
│
├── config/
│   ├── models.py
│   ├── manager.py
│   ├── validator.py
│   └── recorder.py
│
├── metrics/
├── phases/
├── viewpoint/
└── models/

src/api/
├── main.py
├── endpoints.py
└── schemas.py

src/cli/
└── iteration.py
```

## task1: 视频数据管理

### 1. 分层拆分

`DatasetSplitter` 负责按 `action_id + label` 进行分层拆分：

- 保证 `train / validation / test` 互斥
- 小样本组尽量覆盖所有 split
- 固定随机种子时结果稳定

### 2. 仓储与持久化

`DatasetRepository` 负责：

- 样本注册
- 状态管理
- 待标注任务管理
- JSON 序列化与反序列化
- 导出下一轮训练样本

### 3. 回流逻辑

`FeedbackLoop` 处理测试集样本反馈：

- `low confidence` -> `confusing_sample` + `queued_for_retraining`
- `misclassified` -> `queued_for_retraining`
- repeated misclassification -> `pending_annotation`

### 4. 下一轮训练纳入规则

当前默认纳入：

- `ready`
- `queued_for_retraining`

当前默认排除：

- `pending_annotation`

这样可以避免把待人工确认标签的样本直接喂回训练集。

## task2: 异步参数迭代触发器

### 1. 迭代状态机

`IterationStateMachine` 负责管理：

- `pending -> running`
- `running -> succeeded`
- `running -> failed`
- `running/pending -> cancelled`
- retryable failure 时回到 `pending`

### 2. 触发器

`IterationTriggerEngine` 负责 3 类触发：

- 新增样本数达到 20
- 低置信样本达到 10
- 距离上次训练超过 24 小时

并通过 `snapshot_id` 做同窗口去重。

### 3. 统一评估器

`UnifiedEvaluator` 的职责是：

- 对比 baseline 与 candidate
- 识别关键指标回退
- 生成 promotion decision
- 提取低置信 / 误判样本作为反馈输入

它不负责版本切换，也不负责样本落库。

### 4. 版本管理

`VersionStore` 管理训练产物谱系：

- 注册 baseline / candidate
- promote candidate
- rollback to baseline
- 持久化版本历史

它负责版本关系与审计，不直接负责配置生成。

### 5. 闭环编排

`IterationOrchestrator` 把评估、版本切换和样本回流串起来：

```text
baseline evaluation + candidate evaluation
  ↓
UnifiedEvaluator.compare()
  ↓
IterationOrchestrator
  ├─ promote -> VersionStore.promote_candidate()
  ├─ reject  -> VersionStore.rollback_to()
  └─ feedback -> FeedbackLoop.process_feedback()
```

### 6. 执行面

这次新增的执行面负责把“可比较的 candidate”推进成“可运行的 job”：

- `IterationJobStore`：持久化 job payload 与状态
- `IterationQueue`：in-memory async queue
- `IterationWorker`：消费 job 并驱动状态机
- `IterationService`：给 API/CLI 暴露统一 submit/status/run-once 入口
- `IterationRuntime`：装配 repository / version_store / worker / service

当前执行面是**单进程、单队列、可测试**的最小实现，不假装自己是分布式调度系统。

## API / CLI 入口

### API

- `POST /api/v2/iteration/jobs`
- `GET /api/v2/iteration/jobs/{job_id}`

### CLI

- `python manage_iteration.py enqueue --request-file request.json`
- `python manage_iteration.py status --job-id <job_id>`
- `python manage_iteration.py worker --once`

## 与原训练架构的关系

### 保持不变

- `TrainingPipeline.generate_production_config()` 仍负责生成 candidate 配置
- `ConfigManager` 仍负责动作配置读写
- `ParameterRecorder` 仍适合记录执行事实

### 新增职责

- dataset 层不再只是训练输入，而是显式维护回流与待标注状态
- iteration 层不再是“抽象规划”，而是可测试的独立模块

## 当前实现边界

### 已实现

- task1 的最小闭环
- task2 的最小闭环
- iteration 执行面最小闭环
- dataset/iteration API 与 CLI 入口
- 单元测试与集成测试覆盖
- 版本发布 / 回滚的文件持久化

### 尚未实现

- 真实异步 worker / queue
- 多进程/分布式 queue
- 真实训练 trial 搜索器
- 统一 artifact registry
- 完整 HTTP 生命周期 smoke test

## 关键验证

当前实现已通过以下测试面验证：

- dataset splitter
- dataset repository persistence
- feedback loop
- iteration state machine
- triggers
- evaluator
- versioning
- evaluator -> feedback -> repository integration
- candidate promotion / rollback integration
