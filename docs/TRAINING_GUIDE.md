# 训练系统使用指南

## 快速开始

### 使用配置文件训练（推荐）

创建JSON配置文件 `my_action.json`:

```json
{
  "action_id": "jumping_jack",
  "action_name_zh": "开合跳",
  "videos": [
    {"video_path": "./std1.mp4", "tags": ["standard"]},
    {"video_path": "./std2.mp4", "tags": ["standard"]},
    {"video_path": "./std3.mp4", "tags": ["standard"]},
    {"video_path": "./err1.mp4", "tags": ["error:knee_valgus"]},
    {"video_path": "./err2.mp4", "tags": ["error:knee_valgus"]}
  ]
}
```

运行训练:
```bash
python train_action.py --config my_action.json
```

## 标签系统

| 标签 | 用途 | 样本数建议 |
|------|------|----------|
| `standard` | 标准动作，用于建立"金标准" | ≥3 |
| `error:{类型}` | 特定错误类型，用于学习错误判断 | ≥2/类型 |
| `extreme` | 极端错误，用于定义边界 | ≥1 |
| `edge` | 边缘动作，用于细化判断依据 | ≥1 |

## 完整流程

```
1. 批量视频处理
   ↓
2. 指纹提取 (ActionFingerprint)
   ↓
3. 机器审核 (FeatureValidator) - 自动剔除伪特征
   ↓
4. 错误条件学习 (ErrorConditionLearner) - 对比标准与错误样本
   ↓
5. 生成配置文件 (xxx_trained.json)
   ↓
6. 质量验证
   ├─ 通过 → 移动到 config/action_configs/
   └─ 未通过 → 待审核目录，人工确认
```

## 输出文件

### 1. 配置文件
`config/action_configs/{action_id}_trained.json`

### 2. 指纹数据库
`data/fingerprints/{label}.jsonl`

## 机器审核规则

自动剔除：
- NaN比例 > 30%
- 变化幅度 < 5°
- 超出物理极限（如膝角>180°）
