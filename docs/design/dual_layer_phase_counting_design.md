# 双层相位计数与评估设计（V3）

## 1. 目标

- 用统一 `p1/p2` 计数层提升跨动作兼容性和计数稳定性。
- 保留语义层阶段（动作特定）用于错误识别与质量分析。
- 参数学习严格基于训练集聚合，避免评估泄漏和循环论证。
- 统一配置、评估、推理输出格式，便于上线门禁和回滚。

## 2. 总体架构

- 计数层（Count Layer）
  - 统一相位：`p1`（向心/上升段）、`p2`（离心/下降段）
  - 周期定义：`p1 -> p2`（闭环），计 1 rep
  - 运行依赖：主控制指标 + 聚合阈值 + 时长约束
- 语义层（Semantic Layer）
  - 动作语义阶段（如 `start/execution/hold/return/end`）
  - 用于错误识别、质量评分、可解释输出
  - 不作为主计数唯一门控
- 兼容层（Compatibility）
  - 旧 phase 到 `p1/p2` 的映射，保障历史配置可用

## 3. 训练与评估流程

1. 数据拆分
   - 按 `action_id + label (+ subject_id)` 固定随机种子拆分 `train/validation/test`。
2. 主控制指标选择
   - 基于稳定性、区分度、可解释性、周期相关性打分。
3. 单视频参数估计（仅 train）
   - 对主指标做平滑、峰谷检测，估计 `min/max/amplitude/周期间隔`。
4. 跨训练集聚合
   - 使用稳健统计（`median + IQR`）聚合阈值和时长参数。
5. 产出双层配置
   - 写入 `count_layer`、`semantic_layer`、`compatibility`。
6. 固定参数评估（val/test）
   - 计数指标：`MAE/Acc@0/Acc@1`
   - 错误指标：`precision/recall/f1/accuracy/type_accuracy`

## 4. 计数层参数学习规则

- 参数来源：仅训练集样本。
- 每视频估计：
  - `signal_min`、`signal_max`
  - `enter_p1_i = min + 0.35 * amp`
  - `exit_p1_i = min + 0.75 * amp`
  - `enter_p2_i = min + 0.65 * amp`
  - `exit_p2_i = min + 0.30 * amp`
  - `cycle_distance_i = frames / ground_truth_reps`
- 聚合策略：
  - 阈值参数：`median(param_i)`
  - `min_cycle_distance_frames = max(3, floor(median(cycle_distance_i * 0.4)))`
  - `param_ci`：使用 `P25/P75`
- 异常值处理：
  - 使用 `IQR` 剔除离群样本后再聚合。

## 5. 输出格式规范

### 5.1 配置产物

路径：`config/action_configs/{action_id}_trained.json`

- `schema_version`: `"3.0.0"`
- `count_layer`
  - `phase_mode`: `"p1p2"`
  - `control_metric`
  - `polarity`: `"valley_to_peak_to_valley"`
  - `thresholds`: `enter_p1/exit_p1/enter_p2/exit_p2`
  - `timing`: `min_phase_duration_sec/max_phase_duration_sec/min_cycle_distance_frames`
  - `aggregation`: `method/train_video_count/param_ci`
- `semantic_layer`
  - `enabled`
  - `phases`（语义阶段）
- `compatibility`
  - `phase_alias_map`

### 5.2 评估产物

路径：`data/evaluations/{action_id}/{version}.json`

- `schema_version`: `"v2.0"`
- `metric_scores`
  - 计数：`rep_count_mae/rep_count_acc_at_0/rep_count_acc_at_1`
  - 错误：`error_precision/error_recall/error_f1/error_accuracy/error_type_accuracy`
- `sample_results[]`
  - `sample_id/video_path/predicted_reps/expected_reps/expected_label/predicted_error_types/split`
- `phase_learning_info`
- `metric_selection_info`

### 5.3 拆分清单

路径：`data/datasets/{action_id}_{dataset_version}_split.json`

- `schema_version`: `"v2.0"`
- `counts.train/validation/test`
- `distribution_by_label`
- `train/validation/test` 样本明细

## 6. 上线门禁建议

- `test.rep_count_acc_at_1 >= 0.90`
- `test.rep_count_mae <= 1.0`
- `test.error_f1 >= 0.75`
- 若任一关键指标回退，拒绝发布并保留候选版本。

## 7. 迁移策略

- 历史配置无 `count_layer` 时：
  - 回退旧 `cycle_definition + semantic phases` 路径
  - 同时可在运行时动态构造默认 `p1/p2` 映射
- 新训练配置默认产出 `count_layer`，逐步完成全量动作迁移。
