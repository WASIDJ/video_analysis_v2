# 静态锻炼动作视觉分析与参数提取设计方案

## 1. 业务定义与目标
- **静态动作定义**：通过将身体维持在一个固定的标准姿势以达成锻炼效果的动作（如：平板支撑、单脚站立、靠墙静蹲、弓箭步维持等）。
- **判定标准**：当该动作的核心检测项（如膝关节屈曲、躯干前倾等）组合**同时**维持在合理的阈值区间内时，视为“动作正确（Valid/Holding）”。
- **计数逻辑（iOS 端）**：不采用动态动作的“计次（Reps）”，而是采用**计时（Timing）**。即所有核心静态检测项处于“正确”区间并维持 1 秒，视为 1 Count（计次显示可转换为秒数累加）。

## 2. 核心挑战与设计原则
- **为什么不复用动态动作训练方案？**
  - 动态训练管线（Training Pipeline）的核心是寻找动作的相位切换（P1->P2）边界、寻找运动波峰波谷（Peak/Valley）以及计算循环距离。
  - 静态动作**没有时序上的波峰波谷**，其本质是一个“稳态区间（Steady-State）”问题。强行复用动态管线不仅会导致死锁（找不到足够振幅的 Peak），还会增加不必要的系统复杂度和数据标注成本。
- **设计原则（最少数据量）**：
  - **极简数据输入**：针对每个动作，仅需 1~3 个非常标准的示范视频即可，不需要几十个包含各类错误的复杂样本。
  - **静态统计算法**：抛弃复杂的寻找波峰波谷的逻辑，直接在视频的“稳定维持期”提取各关节角度的统计学分布（中位数、分位数）。
  - **解耦的架构**：设计一条完全独立的轻量级 `static_action_extractor.py` 管线，专门输出静态区间参数。

---

## 3. 参数获取方案设计（Python 提取端）

我们只需要一条非常轻量级的统计提取管线。

### 3.1 数据准备（极简标注）
为每个静态动作（如 `plank`）准备 1~3 个标准演示视频。
在配置文件中，人工（或通过极简的脚本标注）指定该视频中**真正处于静态维持阶段的时间窗口**。
例如：`plank_standard_01.mp4`，维持窗口为 `[00:03.000, 00:15.000]`（跳过进入和退出的动作）。

### 3.2 自动化统计提取管线 (Static Extractor)
1. **运行 Pose Estimation**：在标注的 `[start_time, end_time]` 稳态窗口内，逐帧提取姿态序列。
2. **计算核心 Metric**：对动作相关的检测项（如平板支撑的 `trunk_lean`, `hip_flexion`）计算每一帧的角度。
3. **统计学分布计算**：
   - 剔除异常值（NaN 或由于自遮挡导致的置信度过低点）。
   - 计算该 Metric 在稳态窗口内的百分位数（Percentiles）：
     - `P50 (Median)`: 标准动作的绝对核心锚点。
     - `[P10, P90]`: 作为 **优秀区间 (`excellent_range`)**。
     - `[P05, P95]` + 一定的人工容差偏移量（如 ±5°）：作为 **合格/正常区间 (`normal_range`)**。
4. **生成静态配置文件**：
   输出一份与动态 JSON 结构解耦的静态配置（无需 `count_layer` 的 p1p2，只需要 `evaluation_layer` 的阈值）。

---

## 4. iOS 端状态机与计时设计 (iOS Implementation)

iOS 端需要新增一种全新的策略类型：**`StaticHoldStrategy`（静态维持策略）**。

### 4.1 逻辑门判定 (AND 逻辑)
不再使用复杂的 `P2_IDLE -> P1_RISE -> P2_RETURN` 状态机。
状态机简化为两个状态：`Holding` (维持中) 和 `Resting` (休息/不达标)。

判定公式：
```swift
let isPostureValid = 
    (metricA >= metricA_normal_range.min && metricA <= metricA_normal_range.max) &&
    (metricB >= metricB_normal_range.min && metricB <= metricB_normal_range.max) &&
    ...
```

### 4.2 抗抖动与计时器 (Debounce & Timer)
为防止用户在阈值边缘微小晃动导致计时器频繁启停（Flickering），需要引入滞回/抗抖动逻辑：
- **进入 Holding**：连续 `N` 帧（如 0.5 秒）满足 `isPostureValid == true`，才触发“开始计时”事件。
- **退出 Holding**：连续 `M` 帧（如 0.5 秒）出现 `isPostureValid == false`，才触发“暂停计时”事件，并给出错误提示（如“腰部塌陷”）。
- **计时累加**：在 `Holding` 状态下，每经过 1 秒，向业务层抛出 `count += 1` 的事件。

### 4.3 左右交替的静态动作（如单腿站立/弓箭步）
与动态动作类似，下发时明确实例化 `LeftStaticHoldStrategy` 和 `RightStaticHoldStrategy`。
- 如果配置为“单侧维持”（例如左脚站立 30 秒），只需实例化左侧检测项。
- 如果配置为“交替维持”，则分两个小节（Sets）进行，先考核左侧，再考核右侧。

---

## 5. 预期产出与落地路线图

1. **新建静态提取脚本**：开发 `src/scripts/extract_static_action.py`，输入带有 `time_window` 的 JSON，输出包含 `normal_range` 的静态参数配置。
2. **建立静态配置规范**：定义 `static_action_config_schema.json`（去除 P1/P2，强化多条件 AND 逻辑的表达）。
3. **iOS 策略支持**：在 iOS 端实现 `StaticHoldMP33Strategy` 基类，支持读取多个 Metric 的范围阈值，内置防抖计时器。
4. **试点动作**：以“平板支撑 (Plank)”或“靠墙静蹲 (Wall Sit)”作为首个试点，用 1 个标准视频提取参数，打通 iOS 端“1秒1次”的计数闭环。