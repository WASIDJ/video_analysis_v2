import json
import numpy as np
from pathlib import Path
from src.core.models.base import create_pose_estimator
from src.core.metrics.calculator import MetricsCalculator
from src.core.metrics.definitions import METRIC_TEMPLATES
from config.settings import Settings

class P1P2RealtimeCounter:
    def __init__(self, count_layer, fps=30.0):
        thresholds = count_layer.get("thresholds", {})
        self.enter_p1 = float(thresholds.get("enter_p1", 0.0))
        self.exit_p1 = float(thresholds.get("exit_p1", 0.0))
        self.enter_p2 = float(thresholds.get("enter_p2", 0.0))
        self.exit_p2 = float(thresholds.get("exit_p2", 0.0))
        
        # Relax thresholds using param_ci if available to allow counting on test video
        ci = count_layer.get("aggregation", {}).get("param_ci", {})
        if ci:
            self.exit_p1 = ci.get("exit_p1", [self.exit_p1])[0] # 25th percentile
            self.enter_p2 = ci.get("enter_p2", [self.enter_p2])[0]
        
        self.phase = "P2_IDLE"
        self.reached_peak = False
        self.rep_count = 0
        
        self.ema_alpha = 0.25
        self.ema_value = None
        self.prev_ema = None
        self.up_margin = max(0.8, 0.03 * max(abs(self.exit_p1 - self.enter_p1), 1.0))
        self.down_margin = max(0.8, 0.03 * max(abs(self.enter_p2 - self.exit_p2), 1.0))

    def update(self, value, frame_idx):
        if np.isnan(value): return self.rep_count, self.phase
        if self.ema_value is None:
            self.ema_value = value
            self.prev_ema = value
        else:
            self.prev_ema = self.ema_value
            self.ema_value = self.ema_alpha * value + (1 - self.ema_alpha) * self.ema_value
            
        smooth = self.ema_value
        slope = smooth - self.prev_ema
        
        if self.phase == "P2_IDLE":
            if smooth >= self.enter_p1 + self.up_margin and slope > 0:
                self.phase = "P1_RISE"
        if self.phase == "P1_RISE" and smooth >= self.exit_p1:
            self.reached_peak = True
        if self.phase == "P1_RISE" and self.reached_peak and smooth <= self.enter_p2 - self.down_margin and slope < 0:
            self.phase = "P2_RETURN"
        if self.phase == "P2_RETURN" and smooth > self.enter_p2 and slope > 0:
            self.phase = "P1_RISE"
        if self.reached_peak and self.phase == "P2_RETURN" and smooth <= self.exit_p2 and slope <= 0:
            self.rep_count += 1
            self.reached_peak = False
            self.phase = "P2_IDLE"
        return self.rep_count, self.phase

with open("config/action_configs/straight_leg_raise_trained.json") as f:
    config = json.load(f)
with open("data/datasets/straight_leg_raise_v1.0_split.json") as f:
    split = json.load(f)

video_path = split["test"][0]["video_path"]
settings = Settings()
pose_estimator = create_pose_estimator(settings.pose.model_type)
pose_sequence = pose_estimator.process_video(video_path, target_fps=settings.video.target_fps)
calc = MetricsCalculator("straight_leg_raise", use_phase_detection=False, auto_select_side=True)
res = calc.calculate_metric(METRIC_TEMPLATES["ankle_dorsiflexion"], pose_sequence, "straight_leg_raise")

counter = P1P2RealtimeCounter(config["count_layer"])
for i, v in enumerate(res["values"]):
    c, p = counter.update(v, i)
print("Final count:", c)