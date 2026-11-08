"""Evaluate a constant geometric median fitted to distinct training positions."""
import argparse
import json
from pathlib import Path

import numpy as np

from metrics import position_errors


def geometric_median(points):
    estimate = points.mean(axis=0)
    for _ in range(10_000):
        distance = np.linalg.norm(points - estimate, axis=1)
        weight = 1 / np.maximum(distance, 1e-12)
        update = np.average(points, axis=0, weights=weight)
        if np.linalg.norm(update - estimate) < 1e-11:
            return update
        estimate = update
    raise RuntimeError("Geometric median did not converge")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("work/captures.npz"))
    parser.add_argument("--out", type=Path, default=Path("work/baseline.json"))
    args = parser.parse_args()
    with np.load(args.data) as data:
        train = data["split"] == "train"
        test = data["split"] == "test"
        labels = data["Y"].astype(np.float64)
        positions = np.unique(labels[train], axis=0)
        center = geometric_median(positions)
        results = {
            "method": "geometric_median_of_distinct_training_positions",
            "training_positions": len(positions),
            "constant_xyz_m": center.tolist(),
            "test": position_errors(np.broadcast_to(center, labels[test].shape),
                                    labels[test], data["recording"][test]),
        }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2) + "\n")
    print(f"Test mean distance: {results['test']['mean_distance_m']:.6f} m")
