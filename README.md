# Video Analysis V2

基于生物力学的视频姿态分析系统（重构版）

## 项目概述

本项目是原 `sop_package` 视频分析系统的重构版本，主要改进包括：

- **模型升级**: 从 YOLOv8-pose(17点) 迁移至 BlazePose(33点)
- **特征扩展**: 新增体块轮廓、边缘特征，支持耸肩、塌腰等错误识别
- **生物力学模板**: 基于解剖学定义标准化检测项
- **架构优化**: 模块化设计、配置驱动、单测覆盖

## 目录结构

```
video_analysis_v2/
├── config/                     # 配置管理
│   ├── __init__.py
│   ├── settings.py            # Pydantic Settings
│   └── metrics_config.yaml    # 检测项配置
├── src/
│   ├── api/                   # FastAPI接口
│   │   ├── main.py
│   │   ├── schemas.py         # Pydantic模型
│   │   └── endpoints.py
│   ├── core/                  # 核心模块
│   │   ├── models/            # 姿态估计模型
│   │   │   ├── base.py        # 抽象基类
│   │   │   ├── blazepose.py   # BlazePose实现
│   │   │   └── yolo_adapter.py
│   │   ├── features/          # 特征提取
│   │   │   ├── base.py
│   │   │   ├── skeleton_features.py
│   │   │   └── segment_features.py  # 体块特征（新增）
│   │   ├── metrics/           # 检测项定义
│   │   │   ├── definitions.py # 生物力学模板
│   │   │   ├── calculator.py
│   │   │   └── templates.py   # 动作模板
│   │   └── pipeline/          # 处理流程
│   │       └── video_processor.py
│   └── utils/                 # 工具函数
│       ├── geometry.py
│       └── video.py
├── tests/
│   ├── unit/                  # 单元测试
│   └── integration/           # 集成测试
├── pyproject.toml             # 项目配置
├── requirements.txt
└── README.md
```

## 安装

```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

## 快速开始

### 1. 启动服务

```bash
python -m src.api.main
```

或

```bash
uvicorn src.api.main:app --reload
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

### 3. 查询任务状态

```bash
curl http://localhost:8000/api/v2/analyze/task/123
```

## 核心特性

### 1. 姿态估计模型抽象

支持多种姿态估计模型，通过统一接口切换：

```python
from src.core.models import create_pose_estimator

# BlazePose（默认，33个关键点）
estimator = create_pose_estimator("blazepose")

# YOLOv8-pose（17个关键点，兼容旧系统）
estimator = create_pose_estimator("yolo")
```

### 2. 多维度特征提取

```python
from src.core.features import SkeletonFeatureExtractor, SegmentFeatureExtractor

# 骨骼特征
skeleton_extractor = SkeletonFeatureExtractor()
skeleton_features = skeleton_extractor.extract(pose_sequence)

# 体块特征（用于识别耸肩、塌腰）
segment_extractor = SegmentFeatureExtractor()
segment_features = segment_extractor.extract(pose_sequence, video_frames)
```

### 3. 生物力学检测项

基于解剖学定义标准化检测项：

- **关节角度**: 矢状面/冠状面/水平面
- **位置关系**: 对齐度、对称性
- **活动范围**: ROM
- **体块轮廓**: 曲率、比例

```python
from src.core.metrics import MetricCategory, get_metric_definition

# 获取检测项定义
metric = get_metric_definition("knee_flexion")
print(metric.name_zh)  # "膝关节屈曲角度"
print(metric.plane)    # "sagittal"
```

### 4. 动作模板

```python
from src.core.metrics.templates import get_action_template, get_metrics_for_action

# 获取深蹲动作模板
template = get_action_template("squat")

# 获取推荐检测项
metrics = get_metrics_for_action("squat")
# ['knee_flexion', 'knee_valgus', 'trunk_lean', 'hip_flexion', ...]
```

## 配置

通过环境变量或 `.env` 文件配置：

```bash
# 姿态估计模型
POSE_MODEL_TYPE=blazepose  # 或 yolo
POSE_BLAZEPOSE_COMPLEXITY=2

# 体块分割
SEGMENT_ENABLED=true
SEGMENT_MODEL_TYPE=mediapipe

# 视频处理
VIDEO_TARGET_FPS=30
VIDEO_SMOOTH_WINDOW=5

# API
API_HOST=0.0.0.0
API_PORT=8000
```

## 测试

```bash
# 运行所有测试
pytest

# 单元测试
pytest tests/unit/

# 集成测试
pytest tests/integration/

# 覆盖率报告
pytest --cov=src tests/ --cov-report=html
```

## 与原系统对比

| 特性 | 原系统 | V2 |
|------|--------|-----|
| 姿态模型 | YOLOv8-pose (17点) | BlazePose (33点) |
| 特征维度 | 骨骼点 | 骨骼点+体块+边缘 |
| 检测项定义 | 随意定义22项 | 生物力学结构化模板 |
| 配置管理 | 硬编码 | Pydantic Settings |
| 测试覆盖 | 无 | 单测+集成测试 |
| 错误识别 | 基于阈值 | 基于模板+多维度 |

## API兼容性

保持与原系统 API 接口格式兼容：

- `POST /analyze/task` - 创建分析任务
- `GET /analyze/task/{task_id}` - 查询任务状态
- `POST /generate/question` - 生成问卷问题

## 新检测项

基于体块分析的新检测项：

- `lumbar_curvature` - 腰椎曲率（塌腰识别）
- `thoracic_curvature` - 胸椎曲率（驼背识别）
- `shoulder_lift_ratio` - 肩部上提比例（耸肩识别）
- `pelvic_tilt` - 骨盆倾斜角度

## 许可证

MIT License
