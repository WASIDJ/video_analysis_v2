# 训练系统使用指南

## 当前范围

当前训练系统已经覆盖两层能力：

1. **训练产物生成**
   - 批量视频处理
   - 指纹提取
   - 错误条件学习
   - 训练配置生成
2. **task1/task2 闭环骨架**
   - 数据集按 `action_id + label` 分层拆分
   - 测试集低置信 / 误判样本自动回流
   - 多轮误判进入待标注池
   - 迭代任务状态机、触发器、统一评估器、版本管理与回滚

## 核心模块

### 训练与配置

- `src/core/training/pipeline.py`
- `src/core/training/batch_processor.py`
- `src/core/training/error_learner.py`
- `src/core/training/feature_validator.py`
- `src/core/config/manager.py`

### 数据管理

- `src/core/dataset/models.py`
- `src/core/dataset/splitter.py`
- `src/core/dataset/repository.py`
- `src/core/dataset/feedback_loop.py`

### 参数迭代

- `src/core/iteration/models.py`
- `src/core/iteration/job_store.py`
- `src/core/iteration/queue.py`
- `src/core/iteration/worker.py`
- `src/core/iteration/service.py`
- `src/core/iteration/runtime.py`
- `src/core/iteration/state_machine.py`
- `src/core/iteration/triggers.py`
- `src/core/iteration/evaluator.py`
- `src/core/iteration/versioning.py`
- `src/core/iteration/orchestrator.py`

## 快速开始

### 1. 使用配置文件训练

创建 `my_action.json`:

```json
{
  "action_id": "jumping_jack",
  "action_name_zh": "开合跳",
  "videos": [
    {"video_path": "./std1.mp4", "tags": ["standard"]},
    {"video_path": "./std2.mp4", "tags": ["standard"]},
    {"video_path": "./err1.mp4", "tags": ["error:knee_valgus"]},
    {"video_path": "./err2.mp4", "tags": ["error:knee_valgus"]}
  ]
}
```

运行训练:

```bash
python train_action.py --config my_action.json
```

### 2. 做数据集拆分

```python
from src.core.dataset.models import VideoSample
from src.core.dataset.splitter import DatasetSplitter

samples = [
    VideoSample("squat-std-001", "squat", "standard", "./std1.mp4"),
    VideoSample("squat-std-002", "squat", "standard", "./std2.mp4"),
    VideoSample("squat-err-001", "squat", "error:knee_valgus", "./err1.mp4"),
]

splitter = DatasetSplitter(train_ratio=0.7, validation_ratio=0.15, test_ratio=0.15)
dataset_split = splitter.split(samples)
```

### 3. 处理测试集反馈

```python
from src.core.dataset.feedback_loop import FeedbackLoop
from src.core.dataset.models import FeedbackRecord
from src.core.dataset.repository import DatasetRepository

repository = DatasetRepository(storage_path="data/dataset_repository.json")
feedback_loop = FeedbackLoop(repository, low_confidence_threshold=0.6, annotation_threshold=3)

feedback_loop.process_feedback(
    FeedbackRecord(
        sample_id="squat-std-001",
        confidence=0.42,
        source_version="candidate-v2",
        reason="low_confidence",
    )
)
```

### 4. 对比 baseline / candidate

```python
from src.core.iteration.evaluator import UnifiedEvaluator
from src.core.iteration.models import ModelEvaluation

evaluator = UnifiedEvaluator(low_confidence_threshold=0.6)
decision = evaluator.compare(baseline_evaluation, candidate_evaluation)
```

### 5. 发布或回滚版本

```python
from src.core.iteration.versioning import VersionStore

version_store = VersionStore("data/version_store.json")
version_store.promote_candidate("squat", "candidate-v2")
version_store.rollback_to("squat", "baseline-v1")
```

### 6. 通过 CLI 提交和执行 iteration job

```bash
# 入队
.venv/bin/python manage_iteration.py enqueue --request-file request.json

# 查看状态
.venv/bin/python manage_iteration.py status --job-id <job_id>

# 消费一个任务
.venv/bin/python manage_iteration.py worker --once
```

### 7. 通过 API 提交和查询 iteration job

```bash
curl -X POST http://localhost:8000/api/v2/iteration/jobs \
  -H "Content-Type: application/json" \
  -d @request.json

curl http://localhost:8000/api/v2/iteration/jobs/<job_id>
```

## 标签系统

| 标签 | 用途 | 样本数建议 |
|------|------|------------|
| `standard` | 标准动作，用于建立金标准 | ≥3 |
| `error:{类型}` | 特定错误类型，用于学习错误判断 | ≥2/类型 |
| `extreme` | 极端错误，用于定义边界 | ≥1 |
| `edge` | 边缘动作，用于细化判断依据 | ≥1 |

## task1 工作流

### 数据管理闭环

```text
原始视频
  ↓
VideoSample / DatasetRepository
  ↓
DatasetSplitter
  ├─ train
  ├─ validation
  └─ test
       ↓
UnifiedEvaluator sample_results
       ↓
FeedbackLoop
  ├─ low confidence -> confusing_sample + queued_for_retraining
  ├─ misclassified -> queued_for_retraining
  └─ repeated misclassification -> pending_annotation
```

### 当前实现状态

- 已实现分层拆分
- 已实现仓储持久化
- 已实现回流标签与待标注任务
- 已实现“下一轮训练纳入 `ready + queued_for_retraining` 样本”

## task2 工作流

### 迭代闭环

```text
DatasetRepository
  ↓
TriggerSnapshot
  ↓
IterationTriggerEngine
  ↓
IterationStateMachine
  ↓
TrainingPipeline -> candidate config
  ↓
UnifiedEvaluator (baseline vs candidate)
  ↓
IterationOrchestrator
  ├─ promote -> VersionStore.promote_candidate()
  └─ reject -> VersionStore.rollback_to()
  ↓
FeedbackLoop 回流失败样本
```

### 当前实现状态

- 已实现迭代任务状态机
- 已实现 3 类自动触发条件
- 已实现统一评估器
- 已实现版本注册、发布、回滚与历史记录
- 已实现 candidate 评估结果自动喂给 feedback loop
- 已实现 in-memory async queue + worker
- 已实现 API/CLI submit/status/run-once 入口

## 输出物

### 训练阶段

- `config/action_configs/{action_id}_trained.json`
- `data/fingerprints/{label}.jsonl`

### 数据管理与参数迭代阶段

- `data/dataset_repository.json`
- `data/version_store.json`
- `data/iteration_jobs.json`

## 验证命令

```bash
.venv/bin/python -m pytest tests/unit/test_dataset_splitter.py tests/unit/test_feedback_loop.py tests/unit/test_dataset_repository.py -q
.venv/bin/python -m pytest tests/unit/test_iteration_state_machine.py tests/unit/test_iteration_triggers.py tests/unit/test_iteration_evaluator.py tests/unit/test_versioning.py -q
.venv/bin/python -m pytest tests/unit/test_iteration_worker.py tests/unit/test_iteration_cli.py -q
.venv/bin/python -m pytest tests/integration/test_feedback_flow.py tests/integration/test_candidate_promotion_flow.py -q
.venv/bin/python -m pytest tests/integration/test_iteration_api.py -q
.venv/bin/python -m pytest tests/unit -q
```

## 尚未覆盖的部分

- 真实异步任务执行器与外部队列
- 进程间持久化消息队列
- 真实模型训练 / 搜索器接入
- dataset snapshot 与版本库的统一 artifact registry
- 完整 HTTP smoke test（当前 API handler 已验证）
