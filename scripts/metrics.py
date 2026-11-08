"""Position error metrics shared by the training and baseline scripts."""
import numpy as np


def position_errors(predictions, labels, recordings):
    errors = np.linalg.norm(predictions - labels, axis=1)
    per_recording = {
        str(name): float(errors[recordings == name].mean())
        for name in np.unique(recordings)
    }
    return {
        "packets": len(errors),
        "recordings": len(per_recording),
        "mean_distance_m": float(errors.mean()),
        "recording_balanced_mean_distance_m": float(np.mean(list(per_recording.values()))),
        "median_distance_m": float(np.median(errors)),
        "p90_distance_m": float(np.percentile(errors, 90)),
        "axis_mae_m": dict(zip("xyz", np.abs(predictions - labels).mean(axis=0).tolist())),
        "per_recording_mean_distance_m": per_recording,
    }
