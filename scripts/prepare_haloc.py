"""Convert the six official HALOC packet CSVs into ThroughWi model inputs."""
import argparse
import csv
import json
from pathlib import Path

import numpy as np

from prepare_captures import N_BYTES, csi_features

PARTITIONS = ("train", "train", "train", "train", "val", "test")


def prepare(source, output, byte_order):
    inputs, targets, recordings, partitions = [], [], [], []
    for index, partition in enumerate(PARTITIONS):
        filename = f"{index}.csv"
        with (source / filename).open(newline="", encoding="utf-8-sig") as file:
            rows = csv.DictReader(file)
            missing = {"data", "x", "y", "z"} - set(rows.fieldnames or [])
            if missing:
                raise ValueError(f"{filename} missing columns: {sorted(missing)}")
            count = 0
            for line, row in enumerate(rows, start=2):
                try:
                    values = json.loads(row["data"])
                    raw = np.asarray(values, dtype=np.float32)
                    target = [float(row[axis]) for axis in "xyz"]
                    if raw.shape != (N_BYTES,) or not np.isfinite(raw).all() or not np.isfinite(target).all():
                        raise ValueError(f"Expected {N_BYTES} finite CSI values and finite XYZ")
                except (TypeError, ValueError) as error:
                    raise ValueError(f"{filename} line {line}: {error}") from error
                inputs.append(csi_features(raw, byte_order))
                targets.append(target)
                recordings.append(filename)
                partitions.append(partition)
                count += 1
            if not count:
                raise ValueError(f"{filename} is empty")
            print(f"{filename}: {count:,} packets ({partition})", flush=True)

    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output, X=np.asarray(inputs, dtype=np.float32), Y=np.asarray(targets, dtype=np.float32),
        recording=np.asarray(recordings), split=np.asarray(partitions), byte_order=byte_order,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Directory containing 0.csv through 5.csv")
    parser.add_argument("--out", type=Path, default=Path("work/haloc.npz"))
    parser.add_argument("--byte-order", choices=("qi", "iq"), default="qi")
    args = parser.parse_args()
    prepare(args.source, args.out, args.byte_order)
