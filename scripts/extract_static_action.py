import json
import argparse
import numpy as np
from pathlib import Path
from typing import Any, Dict, List

import cv2
import logging
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

from config.settings import Settings
from src.core.models.base import create_pose_estimator
from src.core.metrics.definitions import METRIC_TEMPLATES
from src.core.metrics.calculator import MetricsCalculator
from src.utils.video import VideoFrameIterator


def extract_static_metrics(
    video_path: str,
    time_window: tuple[float, float],
    metrics_to_extract: List[str],
    settings: Settings
) -> Dict[str, List[float]]:
    """提取指定时间窗口内的静态指标数据."""
    
    logger.info(f"处理视频: {video_path}, 时间窗口: {time_window}")
    
    # 1. 提取指定时间窗口内的姿态序列
    estimator = create_pose_estimator(
        settings.pose.model_type,
        min_pose_detection_confidence=settings.pose.blazepose_min_detection_confidence,
        min_tracking_confidence=settings.pose.blazepose_min_tracking_confidence,
    )
    
    start_time, end_time = time_window
    pose_sequence = estimator.process_video(
        video_path, target_fps=settings.video.target_fps
    )
    
    if len(pose_sequence) == 0:
        logger.warning(f"视频 {video_path} 未提取到姿态")
        return {}

    # 根据时间窗口过滤帧
    fps = settings.video.target_fps or getattr(pose_sequence, 'fps', 30.0)
    if not fps:
        fps = 30.0
        
    start_frame = int(start_time * fps)
    end_frame = int(end_time * fps)
    
    # 限制在实际帧数范围内
    start_frame = max(0, min(start_frame, len(pose_sequence) - 1))
    end_frame = max(start_frame, min(end_frame, len(pose_sequence) - 1))
    
    logger.info(f"实际帧窗口: [{start_frame}, {end_frame}]")
    
    # 创建一个仅包含目标时间窗口的子序列
    import copy
    window_sequence = copy.deepcopy(pose_sequence)
    window_sequence.frames = pose_sequence.frames[start_frame:end_frame+1]
    
    if len(window_sequence) == 0:
        logger.warning("指定时间窗口内无有效帧")
        return {}

    # 2. 计算指标
    # 我们关闭自动选侧，分别计算左右侧（如果适用），或者由外部配置文件指定侧面
    # 这里我们采用一种简化策略：使用 MetricsCalculator 计算所有指定的 metric
    
    calculator = MetricsCalculator(
        action_id="static_action",
        min_confidence=settings.metrics.min_keypoint_confidence,
        use_phase_detection=False,
        use_viewpoint_analysis=False,
        auto_select_side=False, # 静态动作通常由配置决定，或者合并左右
    )
    
    results = {m: [] for m in metrics_to_extract}
    
    for m in metrics_to_extract:
        metric_def = METRIC_TEMPLATES.get(m)
        if not metric_def:
            logger.warning(f"未找到指标定义: {m}")
            continue
            
        res = calculator.calculate_metric(
            metric_def=metric_def,
            pose_sequence=window_sequence,
            action_name="static_action"
        )
        
        values = np.array(res.get("values", []), dtype=float)
        results[m] = values.tolist()
        
    return results


def analyze_static_action(config_path: str, output_path: str):
    """分析静态动作并生成配置."""
    settings = Settings()
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
        
    action_id = config.get("action_id", "unknown_static")
    action_name = config.get("action_name", action_id)
    metrics_list = config.get("metrics", [])
    video_samples = config.get("video_samples", [])
    global_tolerance = config.get("tolerance_offset", 5.0)
    
    # 统一处理 metrics_list 为 dict 格式
    parsed_metrics = {}
    for m in metrics_list:
        if isinstance(m, str):
            parsed_metrics[m] = {
                "metric_id": m,
                "tolerance_offset": global_tolerance,
                "needs_absolute_value": m in ["pelvic_tilt", "trunk_lean"]
            }
        elif isinstance(m, dict):
            m_id = m.get("metric_id")
            if m_id:
                parsed_metrics[m_id] = {
                    "metric_id": m_id,
                    "tolerance_offset": m.get("tolerance_offset", global_tolerance),
                    "needs_absolute_value": m.get("needs_absolute_value", m_id in ["pelvic_tilt", "trunk_lean"])
                }
                
    metrics_to_extract = list(parsed_metrics.keys())
    
    logger.info(f"开始分析静态动作: {action_name} ({action_id})")
    
    # 聚合所有样本的数据
    aggregated_data = {m: [] for m in metrics_to_extract}
    
    for sample in video_samples:
        video_path = sample.get("video_path")
        time_window = sample.get("time_window", [0.0, 999.0])
        
        sample_results = extract_static_metrics(
            video_path, 
            tuple(time_window), 
            metrics_to_extract, 
            settings
        )
        
        for m, vals in sample_results.items():
            # 过滤 NaN
            valid_vals = [v for v in vals if not np.isnan(v)]
            aggregated_data[m].extend(valid_vals)
            
    # 计算统计分布
    final_metrics = []
    
    for m, vals in aggregated_data.items():
        if not vals:
            logger.warning(f"指标 {m} 无有效数据，跳过")
            continue
            
        vals_arr = np.array(vals)
        
        m_config = parsed_metrics[m]
        needs_abs = m_config["needs_absolute_value"]
        m_tolerance = m_config["tolerance_offset"]
        
        # P50 (Median): 标准动作的绝对核心锚点
        p50 = float(np.percentile(vals_arr, 50))
        
        # [P10, P90]: 优秀区间
        p10 = float(np.percentile(vals_arr, 10))
        p90 = float(np.percentile(vals_arr, 90))
        
        # [P05, P95] + 容差: 合格/正常区间
        p05 = float(np.percentile(vals_arr, 5))
        p95 = float(np.percentile(vals_arr, 95))
        
        normal_min = p05 - m_tolerance
        normal_max = p95 + m_tolerance
        
        metric_config = {
            "metric_id": m,
            "enabled": True,
            "evaluation_phase": "holding",
            "needs_absolute_value": needs_abs,
            "thresholds": {
                "target_value": round(p50, 2),
                "excellent_range": [round(p10, 2), round(p90, 2)],
                "normal_range": [round(normal_min, 2), round(normal_max, 2)]
            }
        }
        final_metrics.append(metric_config)
        
        logger.info(f"指标 {m} 统计结果: 目标={p50:.2f}, 优秀=[{p10:.2f}, {p90:.2f}], 合格=[{normal_min:.2f}, {normal_max:.2f}]")

    # 构建最终输出 JSON
    from datetime import datetime
    output_config = {
        "schema_version": "1.0.0-static",
        "action_id": action_id,
        "action_name": action_name,
        "type": "static",
        "created_at": datetime.now().isoformat(),
        "metrics": final_metrics
    }
    
    # 确保输出目录存在
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_config, f, indent=2, ensure_ascii=False)
        
    logger.info(f"静态动作配置已生成: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="提取静态动作分析配置")
    parser.add_argument("--config", type=str, required=True, help="输入配置文件路径 (JSON)")
    parser.add_argument("--output", type=str, required=True, help="输出配置文件路径 (JSON)")
    
    args = parser.parse_args()
    analyze_static_action(args.config, args.output)