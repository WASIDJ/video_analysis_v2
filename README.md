# Video Analysis Ryou

基于生物力学的视频姿态分析与参数迭代系统。

当前仓库不只是“视频分析 V2”，还已经落地了 `task1 / task2` 的最小闭环：

- task1：数据集拆分、反馈回流、待标注池
- task2：迭代状态机、触发器、统一评估、版本发布/回滚、API/CLI 执行入口

## 当前能力

### 分析与训练

- BlazePose / YOLO 姿态估计抽象
- 骨骼与体块特征提取
- 生物力学检测项与动作模板
- 指纹提取、错误条件学习、训练配置生成

### task1：视频数据管理

- 按 `action_id + label` 自动拆分 `train / validation / test`
- 低置信样本自动打 `confusing_sample`
- 误判样本自动回流并保留 `source_version`
- 多轮误判样本进入 `pending_annotation`
- `DatasetRepository` 支持 JSON 持久化

### task2：异步参数迭代触发器

- `pending / running / succeeded / failed / cancelled` 状态机
- 3 类自动触发器
  - 新增样本数达到 20
  - 低置信样本数达到 10
  - 距离上次训练超过 24 小时
- `UnifiedEvaluator` 对比 baseline / candidate
- `VersionStore` 支持注册、发布、回滚、历史记录
- `IterationJobStore + IterationQueue + IterationWorker` 执行面
- API / CLI 入口可提交和查询 iteration job

## 目录结构

```text
video_analysis_ryou/
├── config/
├── docs/
├── src/
│   ├── api/
│   ├── cli/
│   ├── core/
│   │   ├── analysis/
│   │   ├── dataset/
│   │   ├── features/
│   │   ├── iteration/
│   │   ├── metrics/
│   │   ├── models/
│   │   ├── pipeline/
│   │   ├── training/
│   │   └── viewpoint/
│   └── utils/
├── tests/
│   ├── integration/
│   └── unit/
├── .plan/
├── pyproject.toml
├── train_action.py
└── manage_iteration.py
```

## 安装

推荐使用 `uv`：

```bash
uv venv --python 3.11 .venv
source .venv/bin/activate
uv sync --python .venv/bin/python --extra dev
```

## 快速开始

### 1. 启动 API

```bash
.venv/bin/python -m src.api.main
```

或：

```bash
.venv/bin/python -m uvicorn src.api.main:app --reload
```

### 2. 创建分析任务

```bash
curl -X POST http://localhost:8000/api/v2/analyze/task \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": 123,
    "analysis_params": {
      "video_infos": [
        {
          "video_url": "https://example.com/video.mp4",
          "actionEvaluation": "correct",
          "actionName": "squat"
        }
      ],
      "metric_details": {
        "taskStage": "analysis",
        "stageCode": 1
      },
      "analysis_type": "videoAnalysis"
    }
  }'
```

### 3. 提交 iteration job

```bash
curl -X POST http://localhost:8000/api/v2/iteration/jobs \
  -H "Content-Type: application/json" \
  -d @request.json
```

### 4. 查询 iteration job

```bash
curl http://localhost:8000/api/v2/iteration/jobs/<job_id>
```

### 5. 使用 CLI 执行 iteration

```bash
.venv/bin/python manage_iteration.py enqueue --request-file request.json
.venv/bin/python manage_iteration.py status --job-id <job_id>
.venv/bin/python manage_iteration.py worker --once
```

## 核心模块

### 数据集管理

- `src/core/dataset/splitter.py`
- `src/core/dataset/repository.py`
- `src/core/dataset/feedback_loop.py`

### 迭代执行

- `src/core/iteration/state_machine.py`
- `src/core/iteration/triggers.py`
- `src/core/iteration/evaluator.py`
- `src/core/iteration/versioning.py`
- `src/core/iteration/job_store.py`
- `src/core/iteration/queue.py`
- `src/core/iteration/worker.py`
- `src/core/iteration/service.py`
- `src/core/iteration/runtime.py`

### API / CLI

- `src/api/main.py`
- `src/api/endpoints.py`
- `src/api/schemas.py`
- `src/cli/iteration.py`
- `manage_iteration.py`

## 测试

### 全量

```bash
.venv/bin/python -m pytest tests/unit -q
.venv/bin/python -m pytest tests/integration -q
```

### task1

```bash
.venv/bin/python -m pytest tests/unit/test_dataset_splitter.py -q
.venv/bin/python -m pytest tests/unit/test_feedback_loop.py tests/integration/test_feedback_flow.py -q
.venv/bin/python -m pytest tests/unit/test_dataset_repository.py tests/unit/test_feedback_loop.py -q
```

### task2

```bash
.venv/bin/python -m pytest tests/unit/test_iteration_state_machine.py tests/unit/test_iteration_worker.py -q
.venv/bin/python -m pytest tests/unit/test_iteration_triggers.py -q
.venv/bin/python -m pytest tests/unit/test_iteration_evaluator.py tests/unit/test_versioning.py tests/integration/test_candidate_promotion_flow.py -q
.venv/bin/python -m pytest tests/unit/test_iteration_cli.py tests/integration/test_iteration_api.py -q
```

## 文档

- [docs/TRAINING_GUIDE.md](/home/ryou/myworkspace/develop/INTERSHIP/banlan/video_analysis_ryou/docs/TRAINING_GUIDE.md)
- [docs/ARCHITECTURE_V2.md](/home/ryou/myworkspace/develop/INTERSHIP/banlan/video_analysis_ryou/docs/ARCHITECTURE_V2.md)
- [docs/understanding/测试与微调系统_V2.md](/home/ryou/myworkspace/develop/INTERSHIP/banlan/video_analysis_ryou/docs/understanding/测试与微调系统_V2.md)
- [docs/understanding/总数据SOP.md](/home/ryou/myworkspace/develop/INTERSHIP/banlan/video_analysis_ryou/docs/understanding/总数据SOP.md)
- [.plan/task.md](/home/ryou/myworkspace/develop/INTERSHIP/banlan/video_analysis_ryou/.plan/task.md)

## 当前边界

已实现：

- task1 最小闭环
- task2 最小闭环
- 单进程 in-memory queue 执行面
- API / CLI 的 submit / status / run-once

未实现：

- 外部 broker / 分布式 worker
- 真实训练 trial 搜索器
- 统一 artifact registry
- 完整生产级调度系统
