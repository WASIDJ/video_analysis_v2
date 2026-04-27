# bird_dog 训练执行报告

## 1. 输入配置
- 配置文件: `/Users/zzh/workspace/code/test_cos/video_analysis_v2/scripts/bird_dog_training.json`
- 动作ID: `bird_dog`
- 动作中文名: `鸟狗式`
- 视频数量: `5`

### 标签分布
- `standard`: 5

## 2. 训练结果
- 训练成功: `True`
- 处理视频数: `5`
- 生成配置: `config/action_configs/bird_dog_trained.json`
- 指纹库路径: `data/fingerprints`
- 质量置信度: `0.9004`
- 覆盖错误类型数: `0`

### 警告
- 无

## 3. 自动拆分与评估
- 数据集版本: `bird_dog-dataset-20260420232848`
- 候选版本: `bird_dog-candidate-20260420232848`
- 拆分清单: `data/datasets/bird_dog_bird_dog-dataset-20260420232848_split.json`
- 评估结果: `data/evaluations/bird_dog/bird_dog-candidate-20260420232848.json`
- 评估总分: `1.0000`

## 4. 原始结果快照
```json
{
  "action_id": "bird_dog",
  "success": true,
  "videos_processed": 5,
  "fingerprint_db_path": "data/fingerprints",
  "generated_config_path": "config/action_configs/bird_dog_trained.json",
  "quality_report": {
    "passed": true,
    "warnings": [],
    "standard_samples": 5,
    "error_types_covered": 0,
    "covered_error_types": [],
    "confidence": 0.9004264278558232
  },
  "warnings": [],
  "requires_manual_review": false
}
```