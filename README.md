# ThroughWi Localization

ThroughWi is an American University of Beirut electrical and computer engineering final-year project. This repository documents the localization component of the team's Spring 2026 final report, connecting ESP32 CSI acquisition, residential data collection, public-data training, and residential fine-tuning.

**Team** · Hussein Yaacoub, Hassan Khalil, Jihad Mobarak, and Ali Assaad

**Advisor** · Dr. Fadi Zaraket

## Project achievements

- An ESP32 and commodity Wi-Fi access point provide device-free sensing, with active packet triggering and host-side serial logging.
- The acquisition check recorded 1,500 CSI frames in 150 seconds, or 10 frames/s. The earlier passive implementation obtained approximately 0.2 frames/s.
- The residential campaign comprises 29 recordings across two homes, with 43,147 cleaned packets and 26,812 position-labeled packets for localization.
- Three neural regressors were trained on HALOC and fine-tuned on the residential recordings. The Multi-Scale CNN achieved the lowest residential mean Euclidean error among these models, at **1.090 m**.

## Localization results from the report

These figures are the results documented in the ThroughWi Spring 2026 final report, §§7.3 and 7.5.

| Model | HALOC mean error (m) | Residential mean error after fine-tuning (m) |
| --- | ---: | ---: |
| Multi-Scale CNN | 2.685 | **1.090** |
| Deep SE-ResNet | **2.524** | 1.171 |
| Transformer | 2.581 | 1.389 |

The report's initial HALOC reference models achieved 3.21 m (LightGBM) and 2.84 m (ResNet CNN). HALOC and residential columns describe their respective test domains.

The full FYP report also covers people counting, material classification, and broader project objectives. This repository focuses on localization and its acquisition pipeline.

## Repository contents

| Directory | Contents |
| --- | --- |
| [firmware](firmware/) and [capture](capture/) | ESP32 acquisition firmware and Python serial logger |
| [data](data/) | 29 compressed residential recordings, pseudonymized access-point identifiers, recording manifest, and partition assignments |
| [notebooks/historical](notebooks/historical/) | Original experiment notebooks |
| [scripts](scripts/) | Preparation, training, fine-tuning, and supplementary evaluation utilities |
| [results](results/) | Result records and supplementary calculations, with provenance |

The original notebooks document the experimental implementation. The standalone scripts are later utilities with some different defaults. See [experiment notes](docs/experiments.md) for the distinction and usage details.

## Prepare the residential data

Use Python 3.10 or later. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/prepare_captures.py --byte-order iq
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`. Preparation writes `work/captures.npz` and a per-recording audit. The explicit `iq` option matches the pairing convention in the original residential cleaning notebook.

## Training utilities

Download the six HALOC CSVs from the [official dataset record](https://zenodo.org/records/10715595) into `data/external/HALOC/`. HALOC is distributed separately under its own terms.

The standalone runner supports Multi-Scale CNN, Transformer, and SE-ResNet, optional pretrained initialization, validation-based model selection, and checkpoint output with normalization statistics. Its commands and implementation differences are documented in [experiment notes](docs/experiments.md). Results from new runs are separate from the report's recorded results.

See [capture setup](docs/capture.md) for flashing the board and collecting data, and [data documentation](data/README.md) for the recording inventory.
