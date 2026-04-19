# P1P2 状态机计数设计（单测/落地版）

## 1. 设计目标

- 使用训练产物中的 `count_layer` 参数，在视频逐帧处理中进行实时计数。
- 通过平滑、滞回、最小驻留时长减少阈值抖动导致的漏计与误计。
- 输出可追溯：明确参数来源、状态转移逻辑、计数触发条件。

## 2. 参数获取方式

参数来源文件：

- `config/action_configs/{action_id}_trained.json`

关键字段：

- `count_layer.control_metric`
- `count_layer.thresholds.enter_p1`
- `count_layer.thresholds.exit_p1`
- `count_layer.thresholds.enter_p2`
- `count_layer.thresholds.exit_p2`
- `count_layer.timing.min_phase_duration_sec`
- `count_layer.timing.min_cycle_distance_frames`
- `count_layer.aggregation.param_ci`（用于观测参数稳定区间）

参数生成原则（训练阶段）：

- 仅使用训练集标准样本
- 对每个样本计算控制信号的 `min/max/amplitude`
- 使用稳健聚合 `median + IQR` 得到最终阈值

## 3. 使用逻辑（运行时）

1. 读取测试视频并提取 `control_metric` 的时序值。
2. 对每个时刻信号值做 EMA 平滑。
3. 使用状态机进行相位切换：
   - `P2_IDLE -> P1_RISE -> P2_RETURN -> count`
4. 满足完整一次峰-谷闭环后计数 +1。
5. 将 `reps + phase` 实时叠加在视频右上角并输出新视频。

## 4. 状态机定义

状态：

- `P2_IDLE`：等待进入上升段
- `P1_RISE`：上升并寻找峰值
- `P2_RETURN`：回落并寻找谷值

辅助变量：

- `reached_peak`：是否已经到达峰值条件
- `last_count_frame`：最近一次计数帧
- `p1_entry_candidate/p2_entry_candidate`：候选进入帧（用于最小驻留）

## 5. 计数触发条件

以平滑后的 `smooth_value` 为准：

- 进入 `P1_RISE`：`smooth_value >= enter_p1 + up_margin` 且斜率为正并持续 `min_phase_frames`
- 峰值确认：`smooth_value >= exit_p1`
- 进入 `P2_RETURN`：峰值已确认，且 `smooth_value <= enter_p2 - down_margin` 且斜率为负并持续 `min_phase_frames`
- 计数 +1：
  - 当前 `P2_RETURN`
  - `smooth_value <= exit_p2`
  - 斜率 `<= 0`
  - `frame_idx - last_count_frame >= min_cycle_distance_frames`
  - `reached_peak == true`

## 6. 抗抖动策略

- EMA 平滑（`alpha=0.25`）
- 阈值滞回（`up_margin/down_margin`）
- 最小相位驻留帧（`min_phase_frames`）
- 最小周期间隔（`min_cycle_distance_frames`）
- 回升回退逻辑（`P2_RETURN` 中短时回升可回到 `P1_RISE`）

## 7. 已知局限

- 当前单测计数器是落地版近似实现，与训练期 `PhaseBoundaryLearner` 周期检测不完全一致。
- 使用单一控制指标时，对异常拍摄角度和噪声更敏感。
- 若测试集分布显著偏离训练集，仍可能出现漏计。

## 8. 后续优化建议

- 增加第二控制指标做联合确认（双阈值门控）。
- 将 `param_ci` 显式用于运行时自适应滞回。
- 按 `split=test` 单独统计计数误差分布并回写评估产物。
