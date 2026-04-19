import json
import numpy as np
from pathlib import Path
from src.core.models.base import create_pose_estimator
from src.core.metrics.calculator import MetricsCalculator
from src.core.metrics.definitions import METRIC_TEMPLATES
from config.settings import Settings

SPLIT_PATH = Path("data/datasets/straight_leg_raise_v1.0_split.json")
with open(SPLIT_PATH) as f:
    split_data = json.load(f)
video_path = split_data["test"][0]["video_path"]

settings = Settings()
pose_estimator = create_pose_estimator(settings.pose.model_type)
pose_sequence = pose_estimator.process_video(video_path, target_fps=settings.video.target_fps)

calc = MetricsCalculator("straight_leg_raise", use_phase_detection=False, auto_select_side=True)
res = calc.calculate_metric(METRIC_TEMPLATES["ankle_dorsiflexion"], pose_sequence, "straight_leg_raise")
values = res["values"]

print(f"Min: {np.nanmin(values)}, Max: {np.nanmax(values)}")
print("First 30 frames:", np.round(values[:30], 2).tolist())
print("Middle 30 frames:", np.round(values[len(values)//2:len(values)//2+30], 2).tolist())
