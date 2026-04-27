import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

import cv2
import numpy as np

# 确保能找到项目模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import Settings
from src.core.models.base import create_pose_estimator
from src.core.metrics.definitions import METRIC_TEMPLATES
from src.core.metrics.calculator import MetricsCalculator
from src.utils.video import VideoFrameIterator


class StaticHoldCounter:
    """使用多条件 AND 逻辑的静态维持计时器."""

    def __init__(self, metrics_config: List[Dict[str, Any]], fps: float):
        self.fps = fps
        self.metrics_config = metrics_config
        
        # 提取各个指标的 normal_range 和取绝对值的要求
        self.ranges = {}
        self.needs_abs = {}
        for m in metrics_config:
            metric_id = m.get("metric_id")
            normal_range = m.get("thresholds", {}).get("normal_range")
            needs_abs = m.get("needs_absolute_value", False)
            if metric_id and normal_range and len(normal_range) == 2:
                self.ranges[metric_id] = (float(normal_range[0]), float(normal_range[1]))
                self.needs_abs[metric_id] = needs_abs
                
        # 状态机：'Resting' 或 'Holding'
        self.phase = "Resting"
        self.total_frames_held = 0  # 累计达标帧数
        self.current_holding_frames = 0  # 当前连续达标帧数
        self.current_resting_frames = 0  # 当前连续不达标帧数
        
        # 抗抖动配置 (0.5秒)
        self.debounce_frames = max(2, int(0.5 * fps))

    def update(self, current_metrics: Dict[str, float]) -> Tuple[float, str, Dict[str, bool]]:
        """更新状态并返回 (当前累积秒数, 当前状态, 各个指标是否达标)."""
        
        metric_status = {}
        all_valid = True
        
        # 1. 检查所有必要指标是否达标 (AND 逻辑)
        for metric_id, (min_val, max_val) in self.ranges.items():
            val = current_metrics.get(metric_id)
            if val is None or np.isnan(val):
                is_valid = False
            else:
                # 兼容 JSON 中指定的绝对值判断 (抹平朝向问题)
                if self.needs_abs.get(metric_id, False):
                    val = abs(val)
                is_valid = (min_val <= val <= max_val)
                
            metric_status[metric_id] = is_valid
            if not is_valid:
                all_valid = False
                
        # 2. 状态机流转与防抖
        if all_valid:
            self.current_resting_frames = 0
            self.current_holding_frames += 1
            
            if self.phase == "Resting" and self.current_holding_frames >= self.debounce_frames:
                self.phase = "Holding"
                self.total_frames_held += self.debounce_frames
            elif self.phase == "Holding":
                # 如果在 Holding 状态且当前帧达标，则累加时间
                self.total_frames_held += 1
        else:
            self.current_holding_frames = 0
            self.current_resting_frames += 1
            
            if self.phase == "Holding" and self.current_resting_frames >= self.debounce_frames:
                self.phase = "Resting"

        # 3. 计算累积时间 (秒)
        total_seconds = self.total_frames_held / self.fps
        
        return total_seconds, self.phase, metric_status


def _draw_overlay(
    frame: np.ndarray, 
    time_seconds: float, 
    phase: str, 
    metric_status: Dict[str, bool],
    current_metrics: Dict[str, float],
    counter: StaticHoldCounter
) -> np.ndarray:
    """在视频帧上绘制实时状态和计时."""
    
    # 1. 绘制右上角主状态
    font = cv2.FONT_HERSHEY_SIMPLEX
    
    # 状态颜色
    color = (0, 255, 0) if phase == "Holding" else (0, 0, 255)
    
    text_time = f"Time: {time_seconds:.1f}s"
    text_phase = f"Status: {phase}"
    
    cv2.putText(frame, text_time, (frame.shape[1] - 250, 40), font, 1.0, color, 2, cv2.LINE_AA)
    cv2.putText(frame, text_phase, (frame.shape[1] - 250, 80), font, 0.8, color, 2, cv2.LINE_AA)
    
    # 2. 绘制左上角各指标达标情况
    y_offset = 40
    cv2.putText(frame, "Metrics Checklist:", (20, y_offset), font, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    
    for metric_id, is_valid in metric_status.items():
        y_offset += 30
        val = current_metrics.get(metric_id, float('nan'))
        
        display_val = val
        if counter.needs_abs.get(metric_id, False):
            display_val = abs(val)
            
        val_str = f"{display_val:.1f}" if not np.isnan(display_val) else "N/A"
        
        status_char = "[X]" if is_valid else "[ ]"
        m_color = (0, 255, 0) if is_valid else (0, 0, 255)
        
        text = f"{status_char} {metric_id}: {val_str}"
        cv2.putText(frame, text, (20, y_offset), font, 0.6, m_color, 2, cv2.LINE_AA)
        
    return frame


def process_static_video(video_path: str, config_path: str, output_path: str):
    """处理静态动作视频并生成叠加验证视频."""
    print(f"Loading config from: {config_path}")
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
        
    metrics_config = config.get("metrics", [])
    if not metrics_config:
        print("Error: No metrics found in config.")
        return
        
    # 兼容两种格式：一种是原始 input (list of str)，一种是 extracted_config (list of dict)
    metrics_to_extract = []
    for m in metrics_config:
        if isinstance(m, str):
            metrics_to_extract.append(m)
        elif isinstance(m, dict):
            metrics_to_extract.append(m.get("metric_id"))
            
    print(f"Target metrics: {metrics_to_extract}")
    
    settings = Settings()
    
    # 初始化姿态估计器 (使用系统标准的封装，不绕过核心库)
    from src.core.models.base import PoseSequence, Keypoint, PoseFrame
    
    estimator = create_pose_estimator(
        settings.pose.model_type,
        min_pose_detection_confidence=settings.pose.blazepose_min_detection_confidence,
        min_tracking_confidence=settings.pose.blazepose_min_tracking_confidence,
    )
    
    # 实例化指标计算器
    # 关闭动作阶段检测和视角分析，因为静态动作不需要 P1/P2
    calculator = MetricsCalculator(
        action_id=config.get("action_id", "static_action"),
        min_confidence=settings.metrics.min_keypoint_confidence,
        use_phase_detection=False,
        use_viewpoint_analysis=False,
        auto_select_side=True, # 允许自动选择侧面，这对于单侧静态动作很有用
    )

    # 准备视频写入器
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    if os.path.exists(output_path):
        os.remove(output_path)
        
    with VideoFrameIterator(
        video_path,
        target_fps=settings.video.target_fps,
        auto_rotate=settings.video.auto_rotate,
    ) as iterator:
        video_info = iterator.get_video_info()
        fps = float(video_info["target_fps"] or video_info["original_fps"] or 30.0)
        
        writer = cv2.VideoWriter(
            str(output_path),
            cv2.VideoWriter_fourcc(*"mp4v"),
            fps,
            (video_info["width"], video_info["height"]),
        )
        
        counter = StaticHoldCounter(metrics_config, fps=fps)
        
        print(f"Processing video ({fps} fps)...")
        frame_idx = 0
        
        # 为了兼容 MetricsCalculator 需要 PoseSequence 的设计，我们需要维护一个微型的 sequence
        # 由于我们是流式处理（类似 iOS 端），我们只需在 sequence 中放入当前帧即可。
        
        for frame_idx, frame in iterator:
            try:
                # 使用标准的 process_frame 接口
                pose_frame = estimator.process_frame(frame)
            except Exception as e:
                print(f"处理帧时出错: {e}")
                pose_frame = None
            
            current_metrics = {}
            
            if pose_frame:
                # 设置一下帧ID
                pose_frame.frame_id = frame_idx
                # 构造包含单帧的 PoseSequence，并把 fps 存在 metadata 里
                pose_seq = PoseSequence(frames=[pose_frame])
                pose_seq.metadata["fps"] = fps
                
                # 直接调用系统的 MetricsCalculator
                # 它会自动处理所有的 fallback、视角过滤、侧面选择等逻辑
                calculated_results = calculator.calculate_all_metrics(
                    pose_seq,
                    metric_ids=metrics_to_extract,
                    action_name=config.get("action_id", "static_action")
                )
                
                for m in metrics_to_extract:
                    res = calculated_results.get(m)
                    if res and "values" in res and len(res["values"]) > 0:
                        val = res["values"][0]
                        current_metrics[m] = float(val) if not np.isnan(val) else float('nan')
                    else:
                        current_metrics[m] = float('nan')
            else:
                if frame_idx % 30 == 0:
                    print(f"Frame {frame_idx}: No pose detected.")
                for m in metrics_to_extract:
                    current_metrics[m] = float('nan')
                if frame_idx % 30 == 0:
                    print(f"Frame {frame_idx}: No pose detected.")
                for m in metrics_to_extract:
                    current_metrics[m] = float('nan')
                    
            # 更新状态机
            time_seconds, phase, metric_status = counter.update(current_metrics)
            
            # 【动作中断与重置 (Reset)】
            # 如果目前处于 Resting 状态，且已经确认丢失动作（经历过防抖时间），我们将重置锁定的侧边
            # 这样可以在下一次重新做动作时，再次触发“寻边期”逻辑
            if phase == "Resting":
                calculator._selected_side = None
            
            # 绘制覆盖层
            drawn_frame = _draw_overlay(frame, time_seconds, phase, metric_status, current_metrics, counter)
            writer.write(drawn_frame)
            
            if frame_idx % 30 == 0:
                print(f"Processed frame {frame_idx}, Time: {time_seconds:.1f}s, Phase: {phase}")

        writer.release()
        print(f"\nDone! Total hold time: {counter.total_frames_held / fps:.1f} seconds")
        print(f"Output saved to: {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="静态动作实时验证叠加脚本")
    
    # 默认使用平板支撑作为测试
    default_video = "/Users/zzh/workspace/banlan/videos/Apr1-23Actions/add_ons/静态/小腿拉伸.mp4"
    default_config = "/Users/zzh/workspace/code/test_cos/video_analysis_v2/config/action_configs/calf_stretch_static_config.json"
    default_output = "/Users/zzh/workspace/code/test_cos/video_analysis_v2/output/tests/calf_stretch_test_timing_overlay.mp4"
    
    parser.add_argument("--video", type=str, default=default_video, help="输入测试视频路径")
    parser.add_argument("--config", type=str, default=default_config, help="静态动作配置JSON路径")
    parser.add_argument("--output", type=str, default=default_output, help="叠加渲染后的输出视频路径")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.video):
        print(f"Error: Video file not found at {args.video}")
        sys.exit(1)
        
    if not os.path.exists(args.config):
        print(f"Error: Config file not found at {args.config}")
        sys.exit(1)
        
    process_static_video(args.video, args.config, args.output)