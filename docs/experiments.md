# Experiment provenance

## Current workflow

The residential preparation command retains packets with 256 finite CSI bytes and applies the historical tail trim recorded in the manifest. The default Q/I order follows the [ESP-IDF CSI reference](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/api-guides/wifi.html#wi-fi-channel-state-information). The historical capture cleaner treated even bytes as I and odd bytes as Q. Use `--byte-order iq` to match that interpretation. Amplitudes are invariant to swapping I and Q, while phases change. The current converter preserves all 128 reported complex pairs and does not apply further phase calibration or exclude pilot and null bins.

The HALOC converter reads the official per-packet JSON array and XYZ fields and uses the official sequence assignments. The converter was checked on all 138,879 packets from the official archive (96,491 train, 28,111 validation, and 14,277 test). It is independent of the original `haloc_compact.parquet` export. It also differs from the upstream HALOC demonstration model, which uses a window of selected amplitude bins. For new runs, choose a consistent byte order for both datasets.

The model definitions come from the team's v2 notebook. The new runner uses Huber loss, AdamW, cosine scheduling, and the notebook's input augmentation. It selects checkpoint weights using validation mean Euclidean distance. It writes packet-weighted and recording-balanced test distance as separate metrics when requested. Runtime configuration and kernels can affect retrained weights and results.

## Historical experiments

The 2.44 m and 1.09 m figures come from §§7.3 and 7.5 of the ThroughWi Spring 2026 report. They refer to a HALOC ensemble and a residential single Multi-Scale CNN respectively. The original notebooks are available for inspection, with saved cell outputs cleared and their original Colab paths retained. The ensemble notebook computes weights using evaluation errors on the test splits, although the report describes validation weights. The new runner implements individual model training only. Treat the historical ensemble result as exploratory unless the original run records establish a validation-only weighting procedure or the result is rerun with one.

## Pending historical artifacts

- Original HALOC compact feature file or the exact export script, along with preprocessing versions and configuration.
- Source and fine-tuned weights for Multi-Scale CNN, Transformer, and SE-ResNet.
- Matching normalization statistics, original run logs, result JSON, and saved predictions, if available.

When these are recovered, record their source and hashes and keep the checkpoint paired with its normalization statistics and split. A fresh training run produces a separate result.
