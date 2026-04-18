"""Vendored model architectures matching the Top-25 (55-dim) checkpoints.

These are bit-faithful copies of the classes defined in:
  - TP1_AE_FeatureSelection.ipynb  → `RegularizedAutoencoder`
  - TP2_VAE_FeatureSelection.ipynb → `BetaVAE`
  - GNN_Network_Propagation.ipynb  → `APTPropagationGNN`

The notebook source uses LeakyReLU(0.2) for AE (§5.10 fix vs the upstream
SIEMAutoencoder loader that used plain ReLU). Centers are learnable
parameters used at training time for center-loss; at inference they are
just frozen weights loaded with the rest of the state_dict.

Workers never instantiate these directly — they go through the loaders in
`autoencoder.py` / `vae.py` / `gnn.py` which apply `eval()` and the
`torch.inference_mode()` decorator.
"""

from __future__ import annotations

import torch
from torch import nn


class RegularizedAutoencoder(nn.Module):
    """Per TP1_AE_FeatureSelection.ipynb cell 9 ("Reg AE — VAE-style with center")."""

    def __init__(self, input_dim: int, latent_dim: int = 64, dropout_rate: float = 0.2) -> None:
        super().__init__()
        self.input_dim = input_dim
        self.latent_dim = latent_dim

        self.encoder_body = nn.Sequential(
            nn.Linear(input_dim, 256),
            nn.BatchNorm1d(256),
            nn.LeakyReLU(0.2),
            nn.Dropout(dropout_rate),
            nn.Linear(256, 128),
            nn.BatchNorm1d(128),
            nn.LeakyReLU(0.2),
            nn.Dropout(dropout_rate),
        )
        self.fc_mu = nn.Linear(128, latent_dim)
        self.fc_logvar = nn.Linear(128, latent_dim)

        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 128),
            nn.BatchNorm1d(128),
            nn.LeakyReLU(0.2),
            nn.Dropout(dropout_rate),
            nn.Linear(128, 256),
            nn.BatchNorm1d(256),
            nn.LeakyReLU(0.2),
            nn.Dropout(dropout_rate),
            nn.Linear(256, input_dim),
        )
        self.center = nn.Parameter(torch.zeros(latent_dim))

    def encode(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        h = self.encoder_body(x)
        mu = self.fc_mu(h)
        logvar = self.fc_logvar(h)
        # At inference (eval mode) we use mu directly — no reparam noise.
        return mu, mu, logvar

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor, torch.Tensor]:
        z, mu, logvar = self.encode(x)
        return self.decoder(z), z, mu, logvar


class BetaVAE(nn.Module):
    """Per TP2_VAE_FeatureSelection.ipynb cell 9. Architecturally identical to
    `SIEMVAE` but with an extra learnable `center` parameter for center-loss."""

    def __init__(self, input_dim: int, latent_dim: int = 32, dropout_rate: float = 0.3) -> None:
        super().__init__()
        self.input_dim = input_dim
        self.latent_dim = latent_dim

        self.encoder_l1 = nn.Linear(input_dim, 512)
        self.encoder_bn1 = nn.BatchNorm1d(512)
        self.encoder_l2 = nn.Linear(512, 256)
        self.encoder_bn2 = nn.BatchNorm1d(256)
        self.encoder_l3 = nn.Linear(256, 128)
        self.encoder_bn3 = nn.BatchNorm1d(128)
        self.dropout = nn.Dropout(dropout_rate)

        self.fc_z_mean = nn.Linear(128, latent_dim)
        self.fc_z_log_var = nn.Linear(128, latent_dim)

        self.center = nn.Parameter(torch.zeros(latent_dim))

        self.decoder_l1 = nn.Linear(latent_dim, 128)
        self.decoder_bn1 = nn.BatchNorm1d(128)
        self.decoder_l2 = nn.Linear(128, 256)
        self.decoder_bn2 = nn.BatchNorm1d(256)
        self.decoder_l3 = nn.Linear(256, 512)
        self.decoder_bn3 = nn.BatchNorm1d(512)
        self.decoder_out = nn.Linear(512, input_dim)

    def encode(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h = torch.relu(self.encoder_bn1(self.encoder_l1(x)))
        h = self.dropout(h)
        h = torch.relu(self.encoder_bn2(self.encoder_l2(h)))
        h = self.dropout(h)
        h = torch.relu(self.encoder_bn3(self.encoder_l3(h)))
        return self.fc_z_mean(h), self.fc_z_log_var(h)

    def decode(self, z: torch.Tensor) -> torch.Tensor:
        h = torch.relu(self.decoder_bn1(self.decoder_l1(z)))
        h = self.dropout(h)
        h = torch.relu(self.decoder_bn2(self.decoder_l2(h)))
        h = self.dropout(h)
        h = torch.relu(self.decoder_bn3(self.decoder_l3(h)))
        h = self.dropout(h)
        return self.decoder_out(h)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        z_mean, z_log_var = self.encode(x)
        # Eval mode: skip reparam noise (deterministic output)
        if self.training:
            std = torch.exp(0.5 * z_log_var)
            z = z_mean + std * torch.randn_like(std)
        else:
            z = z_mean
        return self.decode(z), z_mean, z_log_var


class APTPropagationGNN(nn.Module):
    """Per GNN_Network_Propagation.ipynb cell 5. GraphSAGE for alert-level
    APT propagation detection.
    """

    def __init__(self, in_ch: int, hid: int = 128, layers: int = 3, drop: float = 0.3) -> None:
        # `torch_geometric` is import-time heavy; defer until the class is touched.
        from torch_geometric.nn import BatchNorm, SAGEConv

        super().__init__()
        self.layers = layers
        self.drop = drop
        self.convs = nn.ModuleList()
        self.bns = nn.ModuleList()

        self.convs.append(SAGEConv(in_ch, hid))
        self.bns.append(BatchNorm(hid))
        for _ in range(layers - 1):
            self.convs.append(SAGEConv(hid, hid))
            self.bns.append(BatchNorm(hid))

        self.head = nn.Sequential(
            nn.Linear(hid, 64),
            nn.ReLU(),
            nn.Dropout(drop),
            nn.Linear(64, 1),
        )

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        import torch.nn.functional as F  # noqa: PLC0415 — local

        for i in range(self.layers):
            x_in = x
            x = self.convs[i](x, edge_index)
            x = self.bns[i](x)
            x = F.relu(x)
            if i > 0:
                x = x + x_in
            x = F.dropout(x, p=self.drop, training=self.training)
        return self.head(x).squeeze(-1)


class _PositionalEncoding(nn.Module):
    """Standard sinusoidal positional encoding used by the Transformer."""

    def __init__(self, d_model: int, max_len: int = 500, dropout: float = 0.1) -> None:
        import math

        super().__init__()
        self.dropout = nn.Dropout(p=dropout)
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(
            torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model)
        )
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)  # (1, max_len, d_model)
        self.register_buffer("pe", pe)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x = x + self.pe[:, : x.size(1), :]
        return self.dropout(x)


class TransformerCKCPredictor(nn.Module):
    """Sequence-to-class predictor over AE latents.

    §5.10 fixes vs the upstream loader:
      * `activation='gelu'` (was 'relu')
      * `norm_first=True`   (was False)
      * `input_projection = Linear → LayerNorm → ReLU → Dropout(0.1)`

    State dict layout (verified against apps/models/transformer_model.pth):
      input_projection.0           Linear(input_dim, d_model)
      input_projection.1           LayerNorm(d_model)
      pos_encoder.pe               buffer (1, 500, d_model)
      transformer_encoder.layers.* 4 × encoder layers (d_model=128, n_heads=8)
      transformer_encoder.norm     final LayerNorm (because norm_first=True)
      output_head.0                Linear(d_model, 64)
      output_head.3                Linear(64, num_classes=8)
    """

    def __init__(
        self,
        *,
        input_dim: int,
        d_model: int = 128,
        n_heads: int = 8,
        n_layers: int = 4,
        d_ff: int = 512,
        dropout: float = 0.1,
        num_classes: int = 8,
        max_len: int = 500,
    ) -> None:
        super().__init__()
        self.input_dim = input_dim
        self.d_model = d_model
        self.num_classes = num_classes

        # Input projection (§5.10 — the saved state_dict only has Linear+LayerNorm
        # weights; ReLU and Dropout are non-parametric).
        self.input_projection = nn.Sequential(
            nn.Linear(input_dim, d_model),  # idx 0
            nn.LayerNorm(d_model),          # idx 1
            nn.ReLU(),                       # idx 2 (no params)
            nn.Dropout(dropout),             # idx 3 (no params)
        )

        self.pos_encoder = _PositionalEncoding(d_model, max_len=max_len, dropout=dropout)

        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=n_heads,
            dim_feedforward=d_ff,
            dropout=dropout,
            activation="gelu",       # §5.10 fix
            batch_first=True,
            norm_first=True,         # §5.10 fix
        )
        # `norm` argument matches the saved `transformer_encoder.norm` weights.
        self.transformer_encoder = nn.TransformerEncoder(
            encoder_layer, num_layers=n_layers, norm=nn.LayerNorm(d_model),
        )

        self.output_head = nn.Sequential(
            nn.Linear(d_model, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, num_classes),
        )

    def forward(
        self,
        x: torch.Tensor,
        *,
        src_key_padding_mask: torch.Tensor | None = None,
    ) -> torch.Tensor:
        """`x` shape (B, T, input_dim) → logits shape (B, num_classes)."""
        x = self.input_projection(x)
        x = self.pos_encoder(x)
        encoded = self.transformer_encoder(
            x, src_key_padding_mask=src_key_padding_mask
        )
        # Use the last (most-recent) sequence position for the prediction.
        last = encoded[:, -1, :]
        return self.output_head(last)


class QNetwork(nn.Module):
    """DQN Q-network. Matches the saved checkpoint:
      network.0  Linear(state_dim, 128)
      network.1  ReLU      (no params)
      network.2  Dropout   (no params)
      network.3  Linear(128, 64)
      network.4  ReLU
      network.5  Dropout
      network.6  Linear(64, action_dim)
    """

    def __init__(self, state_dim: int, action_dim: int, *, dropout: float = 0.1) -> None:
        super().__init__()
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.network = nn.Sequential(
            nn.Linear(state_dim, 128),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(128, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, action_dim),
        )

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        return self.network(state)


__all__ = [
    "APTPropagationGNN",
    "BetaVAE",
    "QNetwork",
    "RegularizedAutoencoder",
    "TransformerCKCPredictor",
]
