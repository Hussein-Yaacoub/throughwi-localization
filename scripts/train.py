"""Train or fine-tune a ThroughWi localization model and save a standalone checkpoint."""
import argparse
import json
from pathlib import Path
import random

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, Dataset

from metrics import position_errors
from models import MODELS


class Packets(Dataset):
    def __init__(self, features, targets, augment=False):
        self.features = torch.from_numpy(features.reshape(-1, 2, 128))
        self.targets = torch.from_numpy(targets)
        self.augment = augment

    def __len__(self):
        return len(self.targets)

    def __getitem__(self, index):
        x = self.features[index]
        if self.augment:
            x = (x + torch.randn_like(x) * 0.05) * (torch.rand(128) > 0.05)
        return x, self.targets[index]


def fit_scale(values):
    mean = values.mean(axis=0, dtype=np.float64).astype(np.float32)
    std = values.std(axis=0, dtype=np.float64).astype(np.float32)
    return mean, np.where(std > 1e-8, std, 1.0).astype(np.float32)


def load_data(path):
    with np.load(path) as archive:
        features, targets = archive["X"], archive["Y"]
        partitions, recordings = archive["split"], archive["recording"]
        byte_order = str(archive["byte_order"].item())

    if features.shape != (len(targets), 256) or targets.shape != (len(features), 3):
        raise ValueError("Expected X with 256 features and Y with three position coordinates")
    if len(partitions) != len(features) or len(recordings) != len(features):
        raise ValueError("Partition and recording labels must match the packet count")
    if set(partitions) != {"train", "val", "test"}:
        raise ValueError("Dataset must have nonempty train, val, and test partitions")
    for recording in np.unique(recordings):
        if len(np.unique(partitions[recordings == recording])) != 1:
            raise ValueError(f"Recording overlaps partitions: {recording}")
    return features, targets, partitions, recordings, byte_order


@torch.inference_mode()
def predict(model, loader, device, target_mean, target_std):
    model.eval()
    batches = [model(features.to(device)).cpu().numpy() for features, _ in loader]
    return np.concatenate(batches) * target_std + target_mean


def run(args):
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    device = torch.device(args.device)
    features, targets, split, recordings, byte_order = load_data(args.data)
    model = MODELS[args.model]().to(device)

    if args.init:
        source = torch.load(args.init, map_location="cpu", weights_only=True)
        if source["model"] != args.model or source["byte_order"] != byte_order:
            raise ValueError("Initial checkpoint must match the model architecture and CSI byte order")
        model.load_state_dict(source["state_dict"])

    train = split == "train"
    x_mean, x_std = fit_scale(features[train])
    y_mean, y_std = fit_scale(targets[train])
    features = ((features - x_mean) / x_std).astype(np.float32)
    normalized_targets = ((targets - y_mean) / y_std).astype(np.float32)

    def loader(name):
        mask = split == name
        training = name == "train"
        dataset = Packets(features[mask], normalized_targets[mask], augment=training)
        return DataLoader(dataset, batch_size=args.batch_size, shuffle=training)

    args.out.mkdir(parents=True, exist_ok=False)
    train_loader, val_loader = loader("train"), loader("val")
    val = split == "val"
    learning_rate = args.lr or (5e-4 if args.init or args.model == "transformer" else 1e-3)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate,
                                  weight_decay=1e-3 if args.init else 1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=args.epochs)
    loss_fn = nn.HuberLoss()
    history = []
    best = float("inf")
    checkpoint = args.out / "best.pt"
    for epoch in range(1, args.epochs + 1):
        model.train()
        total_loss = 0.0
        for x, y in train_loader:
            x, y = x.to(device), y.to(device)
            optimizer.zero_grad(set_to_none=True)
            loss = loss_fn(model(x), y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * len(x)
        scheduler.step()

        predictions = predict(model, val_loader, device, y_mean, y_std)
        score = float(np.linalg.norm(predictions - targets[val], axis=1).mean())
        if not np.isfinite(score):
            raise RuntimeError("Nonfinite validation error")
        history.append({"epoch": epoch, "loss": total_loss / len(train_loader.dataset),
                        "validation_mean_distance_m": score})
        print(f"Epoch {epoch}/{args.epochs}: validation mean distance {score:.4f} m", flush=True)
        if score < best:
            best = score
            torch.save({
                "model": args.model, "byte_order": byte_order, "epoch": epoch,
                "state_dict": model.state_dict(),
                "x_mean": torch.from_numpy(x_mean), "x_std": torch.from_numpy(x_std),
                "y_mean": torch.from_numpy(y_mean), "y_std": torch.from_numpy(y_std),
            }, checkpoint)

    results = {"model": args.model, "data": str(args.data), "initial_checkpoint": str(args.init or ""),
               "seed": args.seed, "device": str(device), "torch": str(torch.__version__),
               "byte_order": byte_order, "batch_size": args.batch_size, "learning_rate": learning_rate,
               "history": history}
    if args.test:
        model.load_state_dict(torch.load(checkpoint, map_location=device, weights_only=True)["state_dict"])
        test = split == "test"
        predictions = predict(model, loader("test"), device, y_mean, y_std)
        results["test"] = position_errors(predictions, targets[test], recordings[test])
        print(f"Test mean distance: {results['test']['mean_distance_m']:.4f} m")
    (args.out / "metrics.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path, help="NPZ produced by a preparation script")
    parser.add_argument("--out", type=Path, required=True, help="New directory for checkpoint and metrics")
    parser.add_argument("--model", choices=MODELS, default="multiscale")
    parser.add_argument("--init", type=Path, help="Checkpoint from source-domain training")
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--lr", type=float)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--test", action="store_true", help="Evaluate held-out test after model selection")
    args = parser.parse_args()
    if args.epochs < 1 or args.batch_size < 1 or (args.lr is not None and args.lr <= 0):
        parser.error("epochs, batch size, and learning rate must be positive")
    run(args)
