# bulgarian_squat 训练执行报告

## 1. 输入配置
- 配置文件: `/Users/zzh/workspace/code/test_cos/video_analysis_v2/scripts/bulgarian_squat_training.json`
- 动作ID: `bulgarian_squat`
- 动作中文名: `保加利亚蹲`
- 视频数量: `8`

### 标签分布
- `standard`: 8

## 2. 训练结果
- 训练成功: `True`
- 处理视频数: `8`
- 生成配置: `config/action_configs/bulgarian_squat_trained.json`
- 指纹库路径: `data/fingerprints`
- 质量置信度: `0.9356`
- 覆盖错误类型数: `0`

### 警告
- 无

## 3. 自动拆分与评估
- 数据集版本: `bulgarian_squat-dataset-20260420112744`
- 候选版本: `bulgarian_squat-candidate-20260420112744`
- 拆分清单: `data/datasets/bulgarian_squat_bulgarian_squat-dataset-20260420112744_split.json`
- 评估结果: `data/evaluations/bulgarian_squat/bulgarian_squat-candidate-20260420112744.json`
- 评估总分: `1.0000`

## 4. 原始结果快照
```json
{
  "action_id": "bulgarian_squat",
  "success": true,
  "videos_processed": 8,
  "fingerprint_db_path": "data/fingerprints",
  "generated_config_path": "config/action_configs/bulgarian_squat_trained.json",
  "quality_report": {
    "passed": true,
    "warnings": [],
    "standard_samples": 8,
    "error_types_covered": 0,
    "covered_error_types": [],
    "confidence": 0.9356205786784305
  },
  "warnings": [],
  "requires_manual_review": false
}
```