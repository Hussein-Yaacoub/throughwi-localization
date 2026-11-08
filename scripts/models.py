"""Localization model definitions extracted from the team's v2 notebook."""
import torch
from torch import nn


class MultiScaleCNN(nn.Module):
    def __init__(self, n_sub=128, dropout=0.3):
        super().__init__()
        # Three parallel branches with different receptive fields
        self.branch_fine = nn.Sequential(
            nn.Conv1d(2, 64, 3, padding=1), nn.BatchNorm1d(64), nn.ReLU(),
            nn.Conv1d(64, 64, 3, padding=1), nn.BatchNorm1d(64), nn.ReLU(),
        )
        self.branch_mid = nn.Sequential(
            nn.Conv1d(2, 64, 7, padding=3), nn.BatchNorm1d(64), nn.ReLU(),
            nn.Conv1d(64, 64, 7, padding=3), nn.BatchNorm1d(64), nn.ReLU(),
        )
        self.branch_wide = nn.Sequential(
            nn.Conv1d(2, 64, 15, padding=7), nn.BatchNorm1d(64), nn.ReLU(),
            nn.Conv1d(64, 64, 15, padding=7), nn.BatchNorm1d(64), nn.ReLU(),
        )
        # Merge: 64*3 = 192 channels
        self.merge = nn.Sequential(
            nn.Conv1d(192, 256, 3, padding=1), nn.BatchNorm1d(256), nn.ReLU(), nn.MaxPool1d(2),
            nn.Conv1d(256, 256, 3, padding=1), nn.BatchNorm1d(256), nn.ReLU(), nn.MaxPool1d(2),
            nn.Conv1d(256, 512, 3, padding=1), nn.BatchNorm1d(512), nn.ReLU(), nn.MaxPool1d(2),
            nn.Conv1d(512, 512, 3, padding=1), nn.BatchNorm1d(512), nn.ReLU(),
            nn.AdaptiveAvgPool1d(1),
        )
        self.regressor = nn.Sequential(
            nn.Flatten(), nn.Linear(512, 256), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(256, 64), nn.ReLU(), nn.Dropout(dropout), nn.Linear(64, 3),
        )

    def forward(self, x):
        f = self.branch_fine(x)
        m = self.branch_mid(x)
        w = self.branch_wide(x)
        x = torch.cat([f, m, w], dim=1)
        x = self.merge(x)
        return self.regressor(x)


class CSI_Transformer(nn.Module):
    def __init__(self, n_sub=128, d_model=64, nhead=4, n_layers=4, dropout=0.3):
        super().__init__()
        self.input_proj = nn.Linear(2, d_model)
        self.pos_embed = nn.Parameter(torch.randn(1, n_sub, d_model) * 0.02)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model, nhead=nhead, dim_feedforward=d_model*4,
            dropout=dropout, batch_first=True, activation='gelu',
        )
        self.encoder = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)
        self.pool = nn.Sequential(
            nn.AdaptiveAvgPool1d(1), nn.Flatten(),
        )
        self.regressor = nn.Sequential(
            nn.Linear(d_model, 128), nn.GELU(), nn.Dropout(dropout),
            nn.Linear(128, 64), nn.GELU(), nn.Dropout(dropout),
            nn.Linear(64, 3),
        )

    def forward(self, x):
        # x: (B, 2, 128) -> (B, 128, 2)
        x = x.permute(0, 2, 1)
        x = self.input_proj(x) + self.pos_embed
        x = self.encoder(x)
        # (B, 128, d_model) -> pool over sequence
        x = x.permute(0, 2, 1)  # (B, d_model, 128)
        x = self.pool(x)
        return self.regressor(x)


class SEBlock(nn.Module):
    """Squeeze-and-Excitation channel attention"""
    def __init__(self, channels, reduction=4):
        super().__init__()
        self.fc = nn.Sequential(
            nn.AdaptiveAvgPool1d(1), nn.Flatten(),
            nn.Linear(channels, channels // reduction), nn.ReLU(),
            nn.Linear(channels // reduction, channels), nn.Sigmoid(),
        )
    def forward(self, x):
        w = self.fc(x).unsqueeze(-1)
        return x * w


class SEResBlock(nn.Module):
    def __init__(self, channels, kernel_size=3):
        super().__init__()
        self.conv1 = nn.Conv1d(channels, channels, kernel_size, padding=kernel_size//2)
        self.bn1 = nn.BatchNorm1d(channels)
        self.conv2 = nn.Conv1d(channels, channels, kernel_size, padding=kernel_size//2)
        self.bn2 = nn.BatchNorm1d(channels)
        self.se = SEBlock(channels)
    def forward(self, x):
        residual = x
        x = torch.relu(self.bn1(self.conv1(x)))
        x = self.bn2(self.conv2(x))
        x = self.se(x)
        return torch.relu(x + residual)


class DeepSEResNet(nn.Module):
    def __init__(self, n_sub=128, dropout=0.3):
        super().__init__()
        self.stem = nn.Sequential(
            nn.Conv1d(2, 64, 7, padding=3), nn.BatchNorm1d(64), nn.ReLU(),
        )
        self.layer1 = nn.Sequential(SEResBlock(64), SEResBlock(64), SEResBlock(64), nn.MaxPool1d(2))
        self.expand1 = nn.Sequential(nn.Conv1d(64, 128, 1), nn.BatchNorm1d(128), nn.ReLU())
        self.layer2 = nn.Sequential(SEResBlock(128), SEResBlock(128), SEResBlock(128), nn.MaxPool1d(2))
        self.expand2 = nn.Sequential(nn.Conv1d(128, 256, 1), nn.BatchNorm1d(256), nn.ReLU())
        self.layer3 = nn.Sequential(SEResBlock(256), SEResBlock(256), SEResBlock(256), nn.MaxPool1d(2))
        self.expand3 = nn.Sequential(nn.Conv1d(256, 512, 1), nn.BatchNorm1d(512), nn.ReLU())
        self.layer4 = nn.Sequential(SEResBlock(512), SEResBlock(512))
        self.pool = nn.AdaptiveAvgPool1d(1)
        self.regressor = nn.Sequential(
            nn.Flatten(), nn.Linear(512, 256), nn.ReLU(), nn.Dropout(dropout),
            nn.Linear(256, 64), nn.ReLU(), nn.Dropout(dropout), nn.Linear(64, 3),
        )

    def forward(self, x):
        x = self.stem(x)
        x = self.expand1(self.layer1(x))
        x = self.expand2(self.layer2(x))
        x = self.expand3(self.layer3(x))
        x = self.pool(self.layer4(x))
        return self.regressor(x)


MODELS = {
    "multiscale": MultiScaleCNN,
    "transformer": CSI_Transformer,
    "se_resnet": DeepSEResNet,
}
