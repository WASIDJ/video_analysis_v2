import sys
import numpy as np
from pathlib import Path
import matplotlib.pyplot as plt

sys.path.append(str(Path.cwd()))
from tests.unit.test_cat_cow_realtime_count_overlay import _extract_metric_values, _load_json

config = _load_json(Path("config/action_configs/cat_cow_trained.json"))
split = _load_json(Path("data/datasets/cat_cow_v1.0_split.json"))
video_path = split["validation"][0]["video_path"] if "validation" in split and split["validation"] else split["train"][0]["video_path"]

print(f"Analyzing video: {video_path}")

metrics_to_test = ["knee_flexion", "hip_flexion", "trunk_lean", "pelvic_tilt", "trunk_lateral_flexion", "hip_range_of_motion"]

fig, axs = plt.subplots(len(metrics_to_test), 1, figsize=(12, 4 * len(metrics_to_test)))

for i, metric in enumerate(metrics_to_test):
    try:
        _, values = _extract_metric_values(video_path, metric)
        valid_values = values[~np.isnan(values)]
        
        if len(valid_values) > 0:
            print(f"{metric}: min={np.min(valid_values):.2f}, max={np.max(valid_values):.2f}, range={np.max(valid_values)-np.min(valid_values):.2f}")
            axs[i].plot(values)
            axs[i].set_title(f"{metric} (Range: {np.max(valid_values)-np.min(valid_values):.2f})")
        else:
            print(f"{metric}: All NaN")
    except Exception as e:
        print(f"Failed to extract {metric}: {e}")

plt.tight_layout()
plt.savefig('debug_cat_cow_metrics_val.png')
print("Saved debug_cat_cow_metrics_val.png")
