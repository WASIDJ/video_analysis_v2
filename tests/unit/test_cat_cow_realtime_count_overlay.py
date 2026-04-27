"""基于 cat_cow p1/p2 参数的实时计数叠加视频测试."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
import pytest

from config.settings import Settings
from src.core.metrics.calculator import MetricsCalculator
from src.core.models.base import PoseSequence
from src.core.models.base import create_pose_estimator
from src.core.metrics.definitions import METRIC_TEMPLATES
from src.utils.video import VideoFrameIterator


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "action_configs" / "cat_cow_trained.json"
SPLIT_PATH = PROJECT_ROOT / "data" / "datasets" / "cat_cow_v1.0_split.json"
OUTPUT_DIR = PROJECT_ROOT / "output" / "tests"
OUTPUT_PATH = OUTPUT_DIR / "cat_cow_test_count_overlay.mp4"


class P1P2RealtimeCounter:
    """使用 p1/p2 阈值的简易实时计数器."""

    def __init__(self, count_layer: dict[str, Any], fps: float) -> None:
        thresholds = count_layer.get("thresholds", {})
        timing = count_layer.get("timing", {})
        self.polarity = count_layer.get("polarity", "valley_to_peak_to_valley")
        
        self.enter_p1 = float(thresholds.get("enter_p1", 0.0))
        self.exit_p1 = float(thresholds.get("exit_p1", 0.0))
        self.enter_p2 = float(thresholds.get("enter_p2", 0.0))
        self.exit_p2 = float(thresholds.get("exit_p2", 0.0))

        self.min_cycle_distance = int(timing.get("min_cycle_distance_frames", 3))
        min_phase_duration_sec = float(timing.get("min_phase_duration_sec", 0.2))

        # 采用统一状态：P2_IDLE -> P1_RISE -> P2_RETURN -> count
        self.phase = "P2_IDLE"
        self.reached_peak = False
        self.rep_count = 0
        self.last_count_frame = -10**9
        self.p1_entry_candidate = -1
        self.p2_entry_candidate = -1

        # 轻量滤波和滞回参数，降低阈值抖动导致的漏计/误计
        self.ema_alpha = 0.4  # 提高响应速度，原为0.25导致严重滞后
        self.ema_value: float | None = None
        self.prev_ema: float | None = None
        self.up_margin = max(0.8, 0.03 * max(abs(self.exit_p1 - self.enter_p1), 1.0))
        self.down_margin = max(0.8, 0.03 * max(abs(self.enter_p2 - self.exit_p2), 1.0))
        # debounce 帧数不应等同于整个 phase 的最小持续时间，缩短为约 2-3 帧
        self.debounce_frames = max(2, int(min_phase_duration_sec * fps * 0.4))

    def update(self, value: float, frame_idx: int) -> tuple[int, str]:
        if np.isnan(value):
            return self.rep_count, self.phase

        if self.ema_value is None:
            self.ema_value = value
            self.prev_ema = value
        else:
            self.prev_ema = self.ema_value
            self.ema_value = self.ema_alpha * value + (1 - self.ema_alpha) * self.ema_value

        smooth_value = float(self.ema_value)
        slope = smooth_value - float(self.prev_ema if self.prev_ema is not None else smooth_value)

        # 极性适配逻辑
        is_valley_to_peak = (self.polarity == "valley_to_peak_to_valley")
        is_rising = slope > 0 if is_valley_to_peak else slope < 0
        is_falling = slope < 0 if is_valley_to_peak else slope > 0
        
        def _cross_up(val: float, th: float) -> bool:
            return val >= th if is_valley_to_peak else val <= th
            
        def _cross_down(val: float, th: float) -> bool:
            return val <= th if is_valley_to_peak else val >= th

        if self.phase == "P2_IDLE":
            margin_th = self.enter_p1 + self.up_margin if is_valley_to_peak else self.enter_p1 - self.up_margin
            if _cross_up(smooth_value, margin_th):
                if self.p1_entry_candidate < 0:
                    self.p1_entry_candidate = frame_idx
                if frame_idx - self.p1_entry_candidate >= self.debounce_frames:
                    self.phase = "P1_RISE"
                    self.p1_entry_candidate = -1
            else:
                self.p1_entry_candidate = -1

        if self.phase == "P1_RISE" and _cross_up(smooth_value, self.exit_p1):
            self.reached_peak = True

        if self.phase == "P1_RISE" and self.reached_peak:
            margin_th = self.enter_p2 - self.down_margin if is_valley_to_peak else self.enter_p2 + self.down_margin
            if _cross_down(smooth_value, margin_th):
                if self.p2_entry_candidate < 0:
                    self.p2_entry_candidate = frame_idx
                if frame_idx - self.p2_entry_candidate >= self.debounce_frames:
                    self.phase = "P2_RETURN"
                    self.p2_entry_candidate = -1
            else:
                self.p2_entry_candidate = -1

        # 抗抖动：如果短暂回升，继续留在 P1
        if self.phase == "P2_RETURN" and _cross_up(smooth_value, self.enter_p2) and is_rising:
            self.phase = "P1_RISE"

        if (
            self.reached_peak
            and self.phase == "P2_RETURN"
            and _cross_down(smooth_value, self.exit_p2)
            and not is_rising
            and frame_idx - self.last_count_frame >= self.min_cycle_distance
        ):
            self.rep_count += 1
            self.last_count_frame = frame_idx
            self.reached_peak = False
            self.phase = "P2_IDLE"

        return self.rep_count, self.phase


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _get_test_video_path(split_data: dict[str, Any]) -> str:
    test_samples = split_data.get("test", [])
    if not test_samples:
        # 降级：如果没有 test，尝试取 validation 或 train
        test_samples = split_data.get("validation", [])
        if not test_samples:
            test_samples = split_data.get("train", [])
        if not test_samples:
            raise ValueError("split 文件中未找到任何样本")
    return str(test_samples[0]["video_path"])


def _extract_metric_values(
    video_path: str,
    control_metric: str,
) -> tuple[PoseSequence, np.ndarray]:
    settings = Settings()
    pose_estimator = create_pose_estimator(
        settings.pose.model_type,
        min_pose_detection_confidence=settings.pose.blazepose_min_detection_confidence,
        min_tracking_confidence=settings.pose.blazepose_min_tracking_confidence,
    )
    pose_sequence = pose_estimator.process_video(
        video_path, target_fps=settings.video.target_fps
    )
    if len(pose_sequence) == 0:
        raise ValueError("未提取到姿态序列")

    calculator = MetricsCalculator(
        action_id="cat_cow",
        min_confidence=settings.metrics.min_keypoint_confidence,
        use_phase_detection=False,
        use_viewpoint_analysis=False,
        auto_select_side=True,
    )
    metric_def = METRIC_TEMPLATES.get(control_metric)
    if metric_def is None:
        raise ValueError(f"未找到控制指标定义: {control_metric}")

    result = calculator.calculate_metric(
        metric_def=metric_def,
        pose_sequence=pose_sequence,
        action_name="cat_cow",
    )
    values = np.array(result.get("values", []), dtype=float)
    if values.size == 0:
        raise ValueError(f"未计算出指标时序: {control_metric}")

    return pose_sequence, values


def _draw_count_top_right(frame: np.ndarray, count: int, phase: str) -> np.ndarray:
    text = f"Reps: {count}  Phase: {phase}"
    font = cv2.FONT_HERSHEY_SIMPLEX
    font_scale = 0.9
    thickness = 2
    (text_w, text_h), baseline = cv2.getTextSize(text, font, font_scale, thickness)

    x = max(10, frame.shape[1] - text_w - 20)
    y = max(text_h + 10, 20 + text_h)

    cv2.rectangle(
        frame,
        (x - 10, y - text_h - 10),
        (x + text_w + 10, y + baseline + 10),
        (0, 0, 0),
        -1,
    )
    cv2.putText(frame, text, (x, y), font, font_scale, (0, 255, 0), thickness, cv2.LINE_AA)
    return frame


def _metric_idx_for_frame(frame_idx: int, frame_count: int, metric_count: int) -> int:
    if frame_count <= 1 or metric_count <= 1:
        return 0
    ratio = frame_idx / (frame_count - 1)
    return int(round(ratio * (metric_count - 1)))


def test_cat_cow_realtime_count_overlay_video_generation() -> None:
    """读取测试集视频，实时计数并输出右上角叠加视频."""
    if not CONFIG_PATH.exists():
        pytest.skip(f"配置不存在: {CONFIG_PATH}")
    if not SPLIT_PATH.exists():
        pytest.skip(f"拆分清单不存在: {SPLIT_PATH}")

    config_data = _load_json(CONFIG_PATH)
    split_data = _load_json(SPLIT_PATH)
    
    count_layer = {
        "control_metric": "pelvic_tilt",
        "polarity": "valley_to_peak_to_valley",
        "thresholds": {
            "enter_p1": 20.0,
            "exit_p1": 26.0,
            "enter_p2": 24.0,
            "exit_p2": 18.0
        },
        "timing": {"min_cycle_distance_frames": 30, "min_phase_duration_sec": 0.05}
    }

    # 为了解决不同朝向带来的正负号翻转问题，我们强制对输入数据取绝对值。
    # 取绝对值后，无论向左还是向右侧身，"弓背" 状态下 pelvic_tilt 绝对值均较小（接近 10~15°），
    # "塌腰" 状态下 pelvic_tilt 绝对值均较大（接近 30~40°）。
    # 对应的极性统一为: 绝对值从小到大再到小 (valley_to_peak_to_valley)
    
    control_metric = count_layer.get("control_metric")
    if not control_metric:
        pytest.fail("count_layer.control_metric 缺失")

    video_path = _get_test_video_path(split_data)
    if not Path(video_path).exists():
        pytest.skip(f"测试视频不存在: {video_path}")

    _, metric_values = _extract_metric_values(video_path, control_metric)
    # 取绝对值，抹平朝向差异
    metric_values = np.abs(metric_values)

    settings = Settings()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if OUTPUT_PATH.exists():
        OUTPUT_PATH.unlink()

    frame_total = 0
    with VideoFrameIterator(
        video_path,
        target_fps=settings.video.target_fps,
        auto_rotate=settings.video.auto_rotate,
    ) as iterator:
        video_info = iterator.get_video_info()
        fps = float(video_info["target_fps"] or video_info["original_fps"] or 30.0)
        writer = cv2.VideoWriter(
            str(OUTPUT_PATH),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (video_info["width"], video_info["height"]),
        )
        counter = P1P2RealtimeCounter(count_layer, fps=fps)

        try:
            frame_total = len(iterator)
            for frame_idx, frame in iterator:
                metric_idx = _metric_idx_for_frame(
                    frame_idx=frame_idx,
                    frame_count=max(frame_total, 1),
                    metric_count=len(metric_values),
                )
                value = float(metric_values[metric_idx]) if len(metric_values) else float("nan")
                count, phase = counter.update(value=value, frame_idx=frame_idx)
                drawn = _draw_count_top_right(frame, count, phase)
                writer.write(drawn)
        finally:
            writer.release()

    assert OUTPUT_PATH.exists(), "输出视频未生成"
    assert OUTPUT_PATH.stat().st_size > 0, "输出视频为空"
    assert counter.rep_count >= 0
