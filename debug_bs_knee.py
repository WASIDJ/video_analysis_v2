import sys
import numpy as np
from pathlib import Path
sys.path.append(str(Path.cwd()))
from tests.unit.test_bulgarian_squat_realtime_count_overlay import P1P2RealtimeCounter, _extract_metric_values, _load_json

config = _load_json(Path("config/action_configs/bulgarian_squat_trained.json"))
split = _load_json(Path("data/datasets/bulgarian_squat_v1.0_split.json"))
video_path = split["test"][0]["video_path"]

count_layer = {
    "control_metric": "knee_flexion",
    "polarity": "peak_to_valley_to_peak",  
    "thresholds": {
        "enter_p1": 118.0,   
        "exit_p1": 110.0,     
        "enter_p2": 112.0,   
        "exit_p2": 118.0     
    },
    "timing": config.get("count_layer", {}).get("timing", {})
}

_, values = _extract_metric_values(video_path, "knee_flexion")
counter = P1P2RealtimeCounter(count_layer, fps=30)

print("Checking video max and min values:")
print(f"Max: {np.nanmax(values):.2f}, Min: {np.nanmin(values):.2f}")
print("Values around start:")
print(values[:10])

phase_min = 1000.0
phase_max = -1000.0

last_phase = counter.phase
for i, v in enumerate(values):
    c, p = counter.update(v, i)
    if counter.ema_value is not None:
        phase_min = min(phase_min, counter.ema_value)
        phase_max = max(phase_max, counter.ema_value)
        
    if p != last_phase:
        print(f"Frame {i:3d}: phase={last_phase}->{p}, reached_peak={counter.reached_peak}, count={c}, phase_min={phase_min:.2f}, phase_max={phase_max:.2f}")
        last_phase = p
        phase_min = 1000.0
        phase_max = -1000.0


        
import matplotlib.pyplot as plt
plt.plot(values, label='raw')
plt.axhline(118, color='r', linestyle='--', label='enter_p1/exit_p2')
plt.axhline(110, color='g', linestyle='--', label='exit_p1')
plt.axhline(112, color='b', linestyle='--', label='enter_p2')
plt.legend()
plt.savefig('debug_bs_knee.png')
print("Saved debug_bs_knee.png")

