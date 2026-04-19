# straight_leg_raise 训练执行报告

## 1. 输入配置
- 配置文件: `/Users/zzh/workspace/code/test_cos/video_analysis_v2/scripts/straight_leg_raise_training.json`
- 动作ID: `straight_leg_raise`
- 动作中文名: `直腿抬高`
- 视频数量: `14`

### 标签分布
- `error:bent_leg`: 2
- `error:excessive_hip_abduction`: 2
- `standard`: 10

## 2. 训练结果
- 训练成功: `True`
- 处理视频数: `14`
- 生成配置: `config/action_configs/straight_leg_raise_trained.json`
- 指纹库路径: `data/fingerprints`
- 质量置信度: `0.9101`
- 覆盖错误类型数: `0`

### 警告
- 以下错误类型未学习到条件: {'bent_leg', 'excessive_hip_abduction'}

## 3. 自动拆分与评估
- 数据集版本: `straight_leg_raise-dataset-20260419130731`
- 候选版本: `straight_leg_raise-candidate-20260419130731`
- 拆分清单: `data/datasets/straight_leg_raise_straight_leg_raise-dataset-20260419130731_split.json`
- 评估结果: `data/evaluations/straight_leg_raise/straight_leg_raise-candidate-20260419130731.json`
- 评估总分: `1.0000`

## 4. 原始结果快照
```json
{
  "action_id": "straight_leg_raise",
  "success": true,
  "videos_processed": 14,
  "fingerprint_db_path": "data/fingerprints",
  "generated_config_path": "config/action_configs/straight_leg_raise_trained.json",
  "quality_report": {
    "passed": true,
    "warnings": [
      "以下错误类型未学习到条件: {'bent_leg', 'excessive_hip_abduction'}"
    ],
    "standard_samples": 10,
    "error_types_covered": 0,
    "covered_error_types": [],
    "confidence": 0.9101152968406157
  },
  "warnings": [
    "以下错误类型未学习到条件: {'bent_leg', 'excessive_hip_abduction'}"
  ],
  "requires_manual_review": false
}
```