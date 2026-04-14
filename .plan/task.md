## task1
- 视频数据管理​
    1. 按动作ID + 标签做训练集/验证集/测试集 自动拆分；​
    2. 视频自动回流：对测试集低置信、误判的已入库样本自动更新状态并打上易混淆样本标签；
    3. 多轮误判样本标记待标注标签，移入待标注数据库

## task2
- 异步参数迭代触发器​
  1. 定义迭代任务的状态机（pending/running/succeeded/failed/cancelled）和重试策略​
  2. 实现自动触发器（新增数据量达到20，低置信样本量达到10，固定时间24小时）​
  3. 训练后对训练结果支持使用统一评估器对比baseline 和candidate，实现可追溯的训练数据和可回滚的版本管理​
  4. 反馈回流：低置信/误判样本入队、待标注池、下轮训练自动纳入


## BDD 开发完成部分说明​

### task1-1 按动作ID + 标签做训练集/验证集/测试集自动拆分

**功能点：按动作ID + 标签做训练集/验证集/测试集自动拆分。结果：已实现 `DatasetSplitter`，支持按 `action_id + label` 分层拆分，保证 train/validation/test 互斥、小样本尽量覆盖、固定随机种子结果稳定。**

- Given 已准备好多个动作和多个标签的视频样本
- When 调用 `DatasetSplitter.split(samples)`
- Then 系统会输出按 `action_id + label` 分层后的 `DatasetSplit`
- Then 同一个 `sample_id` 不会同时出现在多个 split
- Then 相同随机种子下拆分结果稳定可复现

实现位置：
- `src/core/dataset/splitter.py`
- `tests/unit/test_dataset_splitter.py`

验证：
- `.venv/bin/python -m pytest tests/unit/test_dataset_splitter.py -q`
```bash
video_analysis_ryou ❯ pytest tests/unit/test_dataset_splitter.py -v
============================= test session starts ==============================
platform linux -- Python 3.11.14, pytest-9.0.3, pluggy-1.6.0
rootdir: /home/ryou/myworkspace/develop/INTERSHIP/banlan/video_analysis_ryou
configfile: pyproject.toml
plugins: anyio-4.13.0, asyncio-1.3.0, cov-7.1.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 4 items

tests/unit/test_dataset_splitter.py ....                                 [100%]

============================== 4 passed in 0.01s ===============================
```

### task1-2 视频自动回流：对测试集低置信、误判样本自动入库并打上易混淆样本标签

**功能点：视频自动回流。结果：已实现 `DatasetRepository + FeedbackLoop`，已入库的测试集低置信样本会自动打 `confusing_sample` 标签并进入 `queued_for_retraining`，误判样本会自动回流并保留来源版本。**

- Given 测试集评估结果里存在低置信样本或误判样本
- When 评估器生成 `FeedbackRecord` 并交给 `FeedbackLoop.process_feedback()`
- Then 已入库样本会在 `DatasetRepository` 中自动更新状态
- Then 低置信样本会被标记为 `confusing_sample`
- Then 误判样本会保留 `source_version`，进入下一轮训练候选

实现位置：
- `src/core/dataset/repository.py`
- `src/core/dataset/feedback_loop.py`
- `src/core/iteration/evaluator.py`
- `tests/unit/test_feedback_loop.py`
- `tests/integration/test_feedback_flow.py`

验证：
- `.venv/bin/python -m pytest tests/unit/test_feedback_loop.py tests/integration/test_feedback_flow.py -q`

```bash
video_analysis_ryou ❯ pytest tests/unit/test_feedback_loop.py tests/integration/test_feedback_flow.py -v
============================= test session starts ==============================
platform linux -- Python 3.11.14, pytest-9.0.3, pluggy-1.6.0
rootdir: /home/ryou/myworkspace/develop/INTERSHIP/banlan/video_analysis_ryou
configfile: pyproject.toml
plugins: anyio-4.13.0, asyncio-1.3.0, cov-7.1.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 5 items

tests/unit/test_feedback_loop.py ....                                    [ 80%]
tests/integration/test_feedback_flow.py .                                [100%]

============================== 5 passed in 0.02s ===============================
```



### task1-3 多轮误判样本标记待标注标签，移入待标注数据库

**功能点：多轮误判样本进入待标注池。结果：已实现误判计数与待标注任务管理，达到阈值后样本会被打上 `pending_annotation` 标签并进入待标注任务列表，且不会重复建任务。**

- Given 某个样本在多轮评估中持续被误判
- When `misclassification_count` 达到阈值
- Then 样本状态切换为 `pending_annotation`
- Then 仓储中会生成唯一的 `AnnotationTask`
- Then 该样本不会再被直接纳入下一轮训练候选

实现位置：
- `src/core/dataset/models.py`
- `src/core/dataset/repository.py`
- `src/core/dataset/feedback_loop.py`
- `tests/unit/test_dataset_repository.py`
- `tests/unit/test_feedback_loop.py`

验证：
- `.venv/bin/python -m pytest tests/unit/test_dataset_repository.py tests/unit/test_feedback_loop.py -q`
```bash
video_analysis_ryou ❯ pytest tests/unit/test_dataset_repository.py tests/unit/test_feedback_loop.py -v

============================= test session starts ==============================
platform linux -- Python 3.11.14, pytest-9.0.3, pluggy-1.6.0
rootdir: /home/ryou/myworkspace/develop/INTERSHIP/banlan/video_analysis_ryou
configfile: pyproject.toml
plugins: anyio-4.13.0, asyncio-1.3.0, cov-7.1.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 6 items

tests/unit/test_dataset_repository.py ..                                 [ 33%]
tests/unit/test_feedback_loop.py ....                                    [100%]

============================== 6 passed in 0.01s ===============================
```

### task2-1 定义迭代任务状态机和重试策略

**功能点：定义迭代任务状态机。结果：已实现 `IterationStateMachine` 和 `RetryPolicy`，支持 `pending/running/succeeded/failed/cancelled` 状态流转，并支持可重试失败自动回到 `pending`。**

- Given 一个新建的 iteration job
- When worker 开始处理任务
- Then 任务从 `pending` 进入 `running`
- When 执行成功
- Then 任务进入 `succeeded`
- When 执行失败且仍可重试
- Then 任务回到 `pending` 并累计 `retry_count`
- When 超过最大重试次数
- Then 任务进入 `failed`

实现位置：
- `src/core/iteration/models.py`
- `src/core/iteration/state_machine.py`
- `src/core/iteration/worker.py`
- `tests/unit/test_iteration_state_machine.py`
- `tests/unit/test_iteration_worker.py`

验证：
- `.venv/bin/python -m pytest tests/unit/test_iteration_state_machine.py tests/unit/test_iteration_worker.py -q`

```bash
video_analysis_ryou ❯ pytest tests/unit/test_iteration_state_machine.py tests/unit/test_iteration_worker.py -v
============================= test session starts ==============================
platform linux -- Python 3.11.14, pytest-9.0.3, pluggy-1.6.0
rootdir: /home/ryou/myworkspace/develop/INTERSHIP/banlan/video_analysis_ryou
configfile: pyproject.toml
plugins: anyio-4.13.0, asyncio-1.3.0, cov-7.1.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 5 items

tests/unit/test_iteration_state_machine.py ...                           [ 60%]
tests/unit/test_iteration_worker.py ..                                   [100%]

============================== 5 passed in 0.02s ===============================
```

### task2-2 实现自动触发器（新增数据量达到20，低置信样本量达到10，固定时间24小时）

**功能点：实现自动触发器。结果：已实现 `IterationTriggerEngine`，支持 3 类触发条件，并通过 `snapshot_id` 防止同一窗口内重复触发。**

- Given 某动作新增样本达到 20
- When 触发器评估快照
- Then 返回 `triggered=True`
- Given 低置信样本达到 10
- When 触发器评估快照
- Then 返回 `triggered=True`
- Given 距离上次训练已超过 24 小时
- When 触发器评估快照
- Then 返回 `triggered=True`
- Given 同一快照重复上报
- When 再次评估
- Then 系统不会重复触发

实现位置：
- `src/core/iteration/triggers.py`
- `tests/unit/test_iteration_triggers.py`

验证：
- `.venv/bin/python -m pytest tests/unit/test_iteration_triggers.py -q`

```bash
video_analysis_ryou ❯ pytest tests/unit/test_iteration_triggers.py -v

============================= test session starts ==============================
platform linux -- Python 3.11.14, pytest-9.0.3, pluggy-1.6.0
rootdir: /home/ryou/myworkspace/develop/INTERSHIP/banlan/video_analysis_ryou
configfile: pyproject.toml
plugins: anyio-4.13.0, asyncio-1.3.0, cov-7.1.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 4 items

tests/unit/test_iteration_triggers.py ....                               [100%]

============================== 4 passed in 0.01s ===============================
```

### task2-3 训练结果使用统一评估器对比 baseline 和 candidate，实现可追溯的训练数据和可回滚的版本管理

**功能点：统一评估器 + 版本管理。结果：已实现 `UnifiedEvaluator + VersionStore + IterationOrchestrator`，支持 baseline/candidate 对比、识别指标回退、candidate 发布、baseline 回滚，以及版本历史持久化。**

- Given 一组 baseline evaluation 和 candidate evaluation
- When `UnifiedEvaluator.compare()` 被调用
- Then 系统会输出是否可晋级的 `EvaluationDecision`
- When candidate 优于 baseline
- Then `VersionStore.promote_candidate()` 会将 candidate 激活
- When candidate 退化
- Then `VersionStore.rollback_to()` 会恢复 baseline
- Then 版本切换历史会被持久化保存，支持追溯

实现位置：
- `src/core/iteration/evaluator.py`
- `src/core/iteration/versioning.py`
- `src/core/iteration/orchestrator.py`
- `tests/unit/test_iteration_evaluator.py`
- `tests/unit/test_versioning.py`
- `tests/integration/test_candidate_promotion_flow.py`

验证：
- `.venv/bin/python -m pytest tests/unit/test_iteration_evaluator.py tests/unit/test_versioning.py tests/integration/test_candidate_promotion_flow.py -q`

```bash
video_analysis_ryou ❯ pytest tests/unit/test_iteration_evaluator.py tests/unit/test_versioning.py tests/integration/test_candidate_promotion_flow.py -v
============================= test session starts ==============================
platform linux -- Python 3.11.14, pytest-9.0.3, pluggy-1.6.0
rootdir: /home/ryou/myworkspace/develop/INTERSHIP/banlan/video_analysis_ryou
configfile: pyproject.toml
plugins: anyio-4.13.0, asyncio-1.3.0, cov-7.1.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 7 items

tests/unit/test_iteration_evaluator.py ...                               [ 42%]
tests/unit/test_versioning.py ..                                         [ 71%]
tests/integration/test_candidate_promotion_flow.py ..                    [100%]

============================== 7 passed in 0.02s ===============================
```

### task2-4 反馈回流：低置信/误判样本入队、待标注池、下轮训练自动纳入

**功能点：反馈回流进入下一轮训练。结果：已实现 `IterationJobStore + IterationQueue + IterationWorker + IterationService` 执行面，并通过 API/CLI 暴露 enqueue/status/run-once 入口，低置信与误判样本能够在评估后自动进入回流流程并参与下一轮训练候选。**

- Given 一个 baseline/candidate 对比任务
- When 通过 API 或 CLI 提交 iteration job
- Then 任务会进入 `IterationQueue`
- When worker 执行该任务
- Then 系统会完成 compare -> promote/rollback -> feedback enqueue
- Then `DatasetRepository.list_samples_for_iteration()` 会返回 `ready + queued_for_retraining` 样本
- Then 待标注样本仍会被排除在下一轮训练之外

实现位置：
- `src/core/iteration/job_store.py`
- `src/core/iteration/queue.py`
- `src/core/iteration/worker.py`
- `src/core/iteration/service.py`
- `src/core/iteration/runtime.py`
- `src/api/endpoints.py`
- `src/api/schemas.py`
- `src/cli/iteration.py`
- `manage_iteration.py`
- `tests/unit/test_iteration_cli.py`
- `tests/unit/test_iteration_worker.py`
- `tests/integration/test_iteration_api.py`

验证：
- `.venv/bin/python -m pytest tests/unit/test_iteration_cli.py tests/unit/test_iteration_worker.py tests/integration/test_iteration_api.py -q`
- `.venv/bin/python -m pytest tests/unit -q`
- `.venv/bin/python -m pytest tests/integration -q`

```bash
video_analysis_ryou ❯ pytest tests/unit/test_iteration_cli.py tests/unit/test_iteration_worker.py tests/integration/test_iteration_api.py -v
============================= test session starts ==============================
platform linux -- Python 3.11.14, pytest-9.0.3, pluggy-1.6.0
rootdir: /home/ryou/myworkspace/develop/INTERSHIP/banlan/video_analysis_ryou
configfile: pyproject.toml
plugins: anyio-4.13.0, asyncio-1.3.0, cov-7.1.0
asyncio: mode=Mode.AUTO, debug=False, asyncio_default_fixture_loop_scope=None, asyncio_default_test_loop_scope=function
collected 7 items

tests/unit/test_iteration_cli.py .                                       [ 14%]
tests/unit/test_iteration_worker.py ..                                   [ 42%]
tests/integration/test_iteration_api.py ....                             [100%]

============================== 7 passed in 0.25s ===============================

```

### 开发完成结论

**结论：task1 / task2 的“已开发完成部分”已经按 BDD 方式落地，当前仓库已具备数据集拆分、回流与待标注、迭代状态机、自动触发、统一评估、版本发布/回滚、以及 API/CLI 可操作入口。**

补充说明：
- 当前执行面是单进程、in-memory queue 的最小实现，适合本地验证与工程演示
- 尚未接入真实分布式 broker、真实训练搜索器、统一 artifact registry
- 最近相关提交可追溯到：
  - `9614ba5` `Preserve feedback state across retraining cycles`
  - `408f2f1` `Gate parameter promotion on evaluated evidence`
  - `fe47ec7` `Make iteration jobs executable through operator entrypoints`
  - `82bc370` `Harden iteration entrypoints for lifespan-safe verification`
