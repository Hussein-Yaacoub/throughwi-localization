"""Prepare the frozen residential recording split for localization."""
import argparse
import csv
import gzip
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
N_BYTES = 256


def csi_features(raw, byte_order):
    """Convert 128 signed byte pairs into amplitude followed by phase."""
    pairs = np.asarray(raw, dtype=np.float32).reshape(-1, 2)
    in_phase, quadrature = pairs.T if byte_order == "iq" else pairs.T[::-1]
    return np.concatenate((np.hypot(in_phase, quadrature), np.arctan2(quadrature, in_phase)), axis=-1)


def prepare(data_dir, output, byte_order):
    with (data_dir / "recordings.csv").open(newline="") as file:
        recordings = list(csv.DictReader(file))

    inputs, targets, recording_ids, partitions = [], [], [], []
    summary = {"byte_order": byte_order, "recordings": {}}
    for record in recordings:
        name = record["recording"]
        path = data_dir / "captures" / f"{name}.gz"
        with gzip.open(path, "rt", newline="") as file:
            rows = list(csv.DictReader(file))

        trim = int(record["trim_last"])
        if trim >= len(rows):
            raise ValueError(f"Trimming {trim} rows would empty {name}")
        valid, bad_length, bad_payload = 0, 0, 0
        split = record["split"]
        target = [float(record[f"{axis}_m"]) for axis in "xyz"] if split else None
        for row in rows[: len(rows) - trim]:
            if row["csi_len"] != str(N_BYTES):
                bad_length += 1
                continue
            values = row["csi_raw"].split()
            if len(values) != N_BYTES:
                bad_payload += 1
                continue
            try:
                raw = np.asarray(values, dtype=np.float32)
            except ValueError:
                bad_payload += 1
                continue
            if not np.isfinite(raw).all():
                bad_payload += 1
                continue
            valid += 1
            if split:
                inputs.append(csi_features(raw, byte_order))
                targets.append(target)
                recording_ids.append(name)
                partitions.append(split)

        if split and not valid:
            raise ValueError(f"No usable localization packets in {name}")
        summary["recordings"][name] = {
            "raw": len(rows), "trimmed": trim, "length_rejected": bad_length,
            "payload_rejected": bad_payload, "usable": valid, "split": split,
        }

    output.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output / "captures.npz",
        X=np.asarray(inputs, dtype=np.float32),
        Y=np.asarray(targets, dtype=np.float32),
        recording=np.asarray(recording_ids),
        split=np.asarray(partitions),
        byte_order=byte_order,
    )
    summary["usable_all"] = sum(record["usable"] for record in summary["recordings"].values())
    summary["localization_packets"] = {
        split: partitions.count(split) for split in ("train", "val", "test")
    }
    (output / "captures_audit.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(f"Usable packets: {summary['usable_all']}. Localization: {summary['localization_packets']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "data")
    parser.add_argument("--out", type=Path, default=ROOT / "work")
    parser.add_argument("--byte-order", choices=("qi", "iq"), default="qi",
                        help="qi follows ESP-IDF; iq follows the historical capture notebook")
    args = parser.parse_args()
    prepare(args.data, args.out, args.byte_order)
