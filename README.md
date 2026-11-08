# ThroughWi Localization

ThroughWi is an AUB electrical and computer engineering final-year project on device-free indoor localization using Wi-Fi channel state information (CSI) from an ESP32. This repository covers the localization experiments and their data collection.

**Team** · Hussein Yaacoub, Hassan Khalil, Jihad Mobarak, and Ali Assaad

**Advisor** · Dr. Fadi Zaraket

| Directory | Contents |
| --- | --- |
| [firmware](firmware/) and [capture](capture/) | ESP32 acquisition firmware and Python serial logger |
| [data](data/) | 29 compressed residential recordings with pseudonymized access-point identifiers, a recording manifest, and the frozen split |
| [scripts](scripts/) | CSI preparation, geometric-median baseline, and PyTorch training and fine-tuning |
| [notebooks/historical](notebooks/historical/) | Team notebooks for the original experiments, retained as a reference |
| [results](results/) | Recomputed baseline and provenance for numbers quoted from the report |

## Run the residential baseline

Use Python 3.10 or later. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/prepare_captures.py
python scripts/baseline.py
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`. Preparation writes `work/captures.npz` and a per-recording audit. Baseline evaluation writes `work/baseline.json`. The expected test mean is **1.262589 m** over 5,941 packets from four recordings. The mean giving equal weight to each recording is **1.259495 m**.

## Train or fine-tune

Download the six HALOC CSVs from the [official dataset record](https://zenodo.org/records/10715595) into `data/external/HALOC/`. The upstream dataset is distributed separately under its own terms. This workflow follows HALOC's sequence split (0–3 train, 4 validation, 5 test) and derives 128 amplitude and 128 phase values per packet. It is a new implementation. See the [experiment notes](docs/experiments.md) for the distinction from the original preprocessing.

```bash
python -m pip install -r requirements-training.txt
python scripts/prepare_haloc.py data/external/HALOC
python scripts/train.py work/haloc.npz --out runs/haloc-multiscale --epochs 120
python scripts/train.py work/captures.npz --out runs/residential-multiscale \
  --init runs/haloc-multiscale/best.pt --epochs 30 --test
```

CUDA is used when available. To train on residential data from scratch, omit `--init` and choose a new output directory. Use `--model transformer` or `--model se_resnet` to select another architecture. Use the same architecture and CSI byte order in both stages. Training fits normalization on training packets only, saves the best validation checkpoint with its normalization statistics, and evaluates test packets only when `--test` is set. Each run directory includes `best.pt` and `metrics.json`.

## Reported and recomputed results

| Dataset | Method | Mean Euclidean error | Source |
| --- | --- | ---: | --- |
| HALOC | Three-model ensemble | 2.44 m | FYP report §7.3 |
| Residential pilot | Fine-tuned Multi-Scale CNN | 1.09 m | FYP report §7.5 |
| Residential pilot | Constant geometric median | 1.263 m | [Recomputed from the bundled recordings and split](results/residential_baseline.json) |

The original checkpoints and HALOC preprocessing output are pending recovery. The first two rows record the team's reported results. The HALOC and residential errors come from separate test sets, so their difference does not measure the effect of fine-tuning. The residential labels use a constant height and the test split covers four recordings. See the [data notes](data/README.md) and [experiment notes](docs/experiments.md).

See [capture setup](docs/capture.md) for flashing the board and collecting new data.
