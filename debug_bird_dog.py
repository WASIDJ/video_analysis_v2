import cv2
import json
import numpy as np
from pathlib import Path
import matplotlib.pyplot as plt

from config.settings import Settings
from src.core.models.base import create_pose_estimator
from src.core.metrics.definitions import METRIC_TEMPLATES
from src.utils.video import VideoFrameIterator

def get_metrics_for_video(video_path: str, metrics_to_check: list[str]):
    settings = Settings()
    estimator = create_pose_estimator(
        settings.pose.model_type,
        min_pose_detection_confidence=settings.pose.blazepose_min_detection_confidence,
        min_tracking_confidence=settings.pose.blazepose_min_tracking_confidence,
    )
    pose_sequence = estimator.process_video(
        video_path, target_fps=settings.video.target_fps
    )
    
    from src.core.metrics.calculator import MetricsCalculator
    results = {}
    for side in ["left", "right"]:
        calculator = MetricsCalculator(
            action_id="bird_dog",
            min_confidence=settings.metrics.min_keypoint_confidence,
            use_phase_detection=False,
            use_viewpoint_analysis=False,
            auto_select_side=False, # explicitly false
        )
        calculator._selected_side = side
        
        for m in metrics_to_check:
            metric_def = METRIC_TEMPLATES.get(m)
            if metric_def:
                res = calculator.calculate_metric(
                    metric_def=metric_def,
                    pose_sequence=pose_sequence,
                    action_name="bird_dog",
                )
                values = np.array(res.get("values", []), dtype=float)
                results[f"{m}_{side}"] = values.tolist()
                
    return results

if __name__ == "__main__":
    video_path = "/Users/zzh/workspace/banlan/videos/Apr1-23Actions/add_ons/动态/鸟狗式/鸟狗式5.mp4"
    metrics = ["trunk_lean", "hip_flexion", "shoulder_flexion", "knee_flexion", "pelvic_tilt", "hip_abduction"]
    
    results = get_metrics_for_video(video_path, metrics)
    
    for m, vals in results.items():
        vals_clean = [v for v in vals if not np.isnan(v)]
        if not vals_clean:
            print(f"{m}: No valid values")
            continue
        
        # count peaks for knee_flexion
        if m.startswith("knee_flexion") or m.startswith("hip_flexion") or m.startswith("pelvic_tilt") or m.startswith("trunk_lean"):
            from scipy.signal import find_peaks
            if m.startswith("pelvic_tilt"):
                peaks, _ = find_peaks(np.abs(vals_clean), distance=20)
            elif m.startswith("trunk_lean"):
                peaks, _ = find_peaks(vals_clean, distance=20)
            elif m.startswith("hip_flexion"):
                peaks, _ = find_peaks(vals_clean, height=140, distance=20)
            else:
                peaks, _ = find_peaks(vals_clean, height=140, distance=20)
            print(f"Number of peaks found for {m}: {len(peaks)}")
            print(f"Peak values for {m}: {[vals_clean[p] for p in peaks]}")
        
    # Plotting for visual check
    plt.figure(figsize=(15, 10))
    for i, m in enumerate(metrics):
        plt.subplot(len(metrics), 1, i+1)
        plt.plot(results[m])
        plt.title(m)
        plt.ylabel("Angle")
    
    plt.tight_layout()
    plt.savefig("bird_dog_metrics.png")
    print("Saved plot to bird_dog_metrics.png")
