# Experiment documentation

## Original project experiments

The ThroughWi Spring 2026 final report is the source of the reported project results. The original notebooks in [notebooks/historical](../notebooks/historical/) document the experimental code.

The source-training configuration uses AdamW, OneCycleLR, Huber loss with delta 1, batch size 2,048, and 120 epochs. Localization fine-tuning uses 30 epochs and cosine annealing, with learning rates of 0.0005 for Multi-Scale CNN and SE-ResNet and 0.0003 for the Transformer. The original fine-tuning notebook uses a training batch size of 512. Gaussian noise of standard deviation 0.05 and 5% input-index masking are used for localization training.

Residential features and coordinate targets are standardized using training-partition statistics. Recording filenames are sorted, shuffled with NumPy seed 42, and partitioned by file. Mean Euclidean localization error is evaluated in meters after inverse standardization.

| Model | HALOC mean error (m) | Residential mean error (m) |
| --- | ---: | ---: |
| Multi-Scale CNN | 2.685 | 1.090 |
| Deep SE-ResNet | 2.524 | 1.171 |
| Transformer | 2.581 | 1.389 |

The report also lists ensemble errors of 2.440 m on HALOC and 1.145 m on residential data. The report describes validation-derived weights, while the supplied ensemble notebook computes weights from test evaluation errors. These are reported ensemble figures with that implementation discrepancy; the main README presents the single-model results.

## Standalone utilities

The standalone preparation and training scripts were added during repository organization. They are distinct from the original notebook execution.

- Residential preparation defaults to Q/I byte order. Use `--byte-order iq` to match the original cleaner's I/Q interpretation. Swapping the order preserves amplitudes and changes phases.
- The HALOC converter reads the official per-packet JSON and XYZ fields. It uses sequence assignments 0–3 for training, 4 for validation, and 5 for testing, covering 96,491 / 28,111 / 14,277 packets. It is a separate implementation from the original compact feature export.
- The training runner uses cosine scheduling for both stages and defaults to batch size 128. The original source notebook uses OneCycleLR and batch size 2,048.
- The runner defaults to a fine-tuning learning rate of 0.0005 for all architectures. Pass `--lr 0.0003` for the original Transformer fine-tuning learning rate.
- The runner's scaling replaces near-zero standard deviations with 1.0; the notebooks add a small epsilon to standard deviations.
- The runner saves weights with normalization statistics and configuration, and selects weights by validation mean Euclidean distance. Test evaluation is enabled with `--test`.

For the available command-line options:

```bash
python -m pip install -r requirements-training.txt
python scripts/prepare_haloc.py --help
python scripts/train.py --help
```

Use consistent feature conventions and matching architectures when initializing from another run. The standalone defaults are not an exact replay of the original training configuration.

## Supplementary constant-position calculation

The geometric-median utility and its result file are later supplementary calculations, not an original FYP baseline or one of the report's neural-model results. The report's initial HALOC reference results are LightGBM at 3.21 m and ResNet CNN at 2.84 m.

The supplementary utility remains available as `scripts/baseline.py`; it does not replace or redefine any reported project result.
