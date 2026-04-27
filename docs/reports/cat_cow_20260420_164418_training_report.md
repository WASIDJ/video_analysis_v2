# cat_cow 训练执行报告

## 1. 输入配置
- 配置文件: `/Users/zzh/workspace/code/test_cos/video_analysis_v2/scripts/cat_cow_training.json`
- 动作ID: `cat_cow`
- 动作中文名: `猫式伸展`
- 视频数量: `5`

### 标签分布
- `standard`: 5

## 2. 训练结果
- 训练成功: `True`
- 处理视频数: `5`
- 生成配置: `config/action_configs/cat_cow_trained.json`
- 指纹库路径: `data/fingerprints`
- 质量置信度: `0.8986`
- 覆盖错误类型数: `0`

### 警告
- 无

## 3. 自动拆分与评估
- 数据集版本: `cat_cow-dataset-20260420164418`
- 候选版本: `cat_cow-candidate-20260420164418`
- 拆分清单: `data/datasets/cat_cow_cat_cow-dataset-20260420164418_split.json`
- 评估结果: `data/evaluations/cat_cow/cat_cow-candidate-20260420164418.json`
- 评估总分: `1.0000`

## 4. 原始结果快照
```json
{
  "action_id": "cat_cow",
  "success": true,
  "videos_processed": 5,
  "fingerprint_db_path": "data/fingerprints",
  "generated_config_path": "config/action_configs/cat_cow_trained.json",
  "quality_report": {
    "passed": true,
    "warnings": [],
    "standard_samples": 5,
    "error_types_covered": 0,
    "covered_error_types": [],
    "confidence": 0.8985632600737418
  },
  "warnings": [],
  "requires_manual_review": false
}
```