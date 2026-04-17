"""
Beta-VAE Loader
===============

Loads the retrained Beta-VAE model (25 features → 55 columns).
Supports three variants trained differently.

Model Variants:
--------------
- beta_vae_top25_features.pth          → trained on all data, latent=32
- beta_vae_top25_features_32dim.pth    → trained on all data, latent=32 (alternate)
- beta_vae_malicious_only_32dim.pth    → trained on malicious data only, latent=32

Architecture (encoder_l1/bn1/l2/bn2/l3/bn3 + fc_z_mean/fc_z_log_var + decoder):
--------------------------------------------------------------------------------
encoder_l1: Linear(55→512), BN(512), ReLU
encoder_l2: Linear(512→256), BN(256), ReLU
encoder_l3: Linear(256→128), BN(128), ReLU
fc_z_mean: Linear(128→32)
fc_z_log_var: Linear(128→32)
decoder_l1: Linear(32→128), BN(128), ReLU
decoder_l2: Linear(128→256), BN(256), ReLU
decoder_l3: Linear(256→512), BN(512), ReLU
decoder_out: Linear(512→55)
center: Buffer(32) — learned center for anomaly scoring
"""

import os
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, Optional


class BetaVAE(nn.Module):
    """
    Beta-VAE for anomaly detection.
    Trained on the 25 selected features (55 columns after embedding expansion).
    """

    def __init__(self, input_dim: int = 55, latent_dim: int = 32):
        super(BetaVAE, self).__init__()

        self.input_dim = input_dim
        self.latent_dim = latent_dim

        # Learnable center for anomaly scoring
        self.register_buffer('center', torch.zeros(latent_dim))

        # Encoder
        self.encoder_l1 = nn.Linear(input_dim, 512)
        self.encoder_bn1 = nn.BatchNorm1d(512)
        self.encoder_l2 = nn.Linear(512, 256)
        self.encoder_bn2 = nn.BatchNorm1d(256)
        self.encoder_l3 = nn.Linear(256, 128)
        self.encoder_bn3 = nn.BatchNorm1d(128)

        # Latent space
        self.fc_z_mean = nn.Linear(128, latent_dim)
        self.fc_z_log_var = nn.Linear(128, latent_dim)

        # Decoder
        self.decoder_l1 = nn.Linear(latent_dim, 128)
        self.decoder_bn1 = nn.BatchNorm1d(128)
        self.decoder_l2 = nn.Linear(128, 256)
        self.decoder_bn2 = nn.BatchNorm1d(256)
        self.decoder_l3 = nn.Linear(256, 512)
        self.decoder_bn3 = nn.BatchNorm1d(512)
        self.decoder_out = nn.Linear(512, input_dim)

    def encode(self, x: torch.Tensor):
        """Encode input to latent distribution parameters."""
        h = F.relu(self.encoder_bn1(self.encoder_l1(x)))
        h = F.relu(self.encoder_bn2(self.encoder_l2(h)))
        h = F.relu(self.encoder_bn3(self.encoder_l3(h)))
        z_mean = self.fc_z_mean(h)
        z_log_var = self.fc_z_log_var(h)
        return z_mean, z_log_var

    def reparameterize(self, z_mean: torch.Tensor, z_log_var: torch.Tensor) -> torch.Tensor:
        """Reparameterization trick."""
        if self.training:
            std = torch.exp(0.5 * z_log_var)
            eps = torch.randn_like(std)
            return z_mean + eps * std
        return z_mean

    def decode(self, z: torch.Tensor) -> torch.Tensor:
        """Decode latent vector to reconstruction."""
        h = F.relu(self.decoder_bn1(self.decoder_l1(z)))
        h = F.relu(self.decoder_bn2(self.decoder_l2(h)))
        h = F.relu(self.decoder_bn3(self.decoder_l3(h)))
        return self.decoder_out(h)

    def forward(self, x: torch.Tensor):
        """Full forward pass."""
        z_mean, z_log_var = self.encode(x)
        z = self.reparameterize(z_mean, z_log_var)
        recon = self.decode(z)
        return recon, z_mean, z_log_var, z


class VAELoader:
    """
    Wrapper for loading and using the Beta-VAE model.

    Provides malicious probability and uncertainty estimation
    based on reconstruction error and latent space analysis.
    """

    # Available model variants
    MODEL_VARIANTS = {
        'beta_vae': {
            'filename': 'beta_vae_top25_features.pth',
            'latent_dim': 32,
            'description': 'Beta-VAE (all data, latent=32)',
        },
        'beta_vae_32': {
            'filename': 'beta_vae_top25_features_32dim.pth',
            'latent_dim': 32,
            'description': 'Beta-VAE 32dim (all data, latent=32)',
        },
        'beta_vae_malicious': {
            'filename': 'beta_vae_malicious_only_32dim.pth',
            'latent_dim': 32,
            'description': 'Beta-VAE (malicious only, latent=32)',
        },
    }

    def __init__(
        self,
        model_path: Optional[str] = None,
        variant: str = 'beta_vae',
        input_dim: int = 55,
        device: str = 'cpu',
    ):
        """
        Initialize the VAELoader.

        Args:
            model_path: Direct path to model file (overrides variant)
            variant: Model variant key
            input_dim: Number of input features (55 for top-25)
            device: Device to load model on
        """
        self.device = torch.device(device)
        self.input_dim = input_dim
        self.variant = variant

        # Resolve model path
        if model_path is None:
            if variant not in self.MODEL_VARIANTS:
                raise ValueError(f"Unknown variant '{variant}'. Choose from: {list(self.MODEL_VARIANTS.keys())}")
            variant_info = self.MODEL_VARIANTS[variant]
            models_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'models')
            model_path = os.path.join(models_dir, variant_info['filename'])
            self.latent_dim = variant_info['latent_dim']
        else:
            self.latent_dim = self.MODEL_VARIANTS.get(variant, {}).get('latent_dim', 32)

        self.model_path = model_path
        self.model = self._load_model()

        # Running statistics for anomaly calibration
        self._recon_errors_seen = []
        self._max_recon_error = 10.0  # Will be updated during training

        print(f"[VAE] Loaded: {os.path.basename(model_path)}")
        print(f"      Architecture: {input_dim} -> 512 -> 256 -> 128 -> {self.latent_dim} (latent) -> {input_dim}")

    def _load_model(self) -> BetaVAE:
        """Load the model from checkpoint."""
        model = BetaVAE(
            input_dim=self.input_dim,
            latent_dim=self.latent_dim,
        ).to(self.device)

        if os.path.exists(self.model_path):
            state_dict = torch.load(self.model_path, map_location=self.device, weights_only=False)
            if isinstance(state_dict, dict) and 'model_state_dict' in state_dict:
                state_dict = state_dict['model_state_dict']
            model.load_state_dict(state_dict, strict=True)
            model.eval()
        else:
            raise FileNotFoundError(f"Model file not found: {self.model_path}")

        return model

    @torch.no_grad()
    def get_malicious_probability(self, features: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Estimate malicious probability from reconstruction error.

        Higher reconstruction error → more likely malicious (anomalous).

        Args:
            features: Input features of shape (batch, 55)

        Returns:
            Dict with 'malicious_probability', 'uncertainty', 'reconstruction_error'
        """
        if isinstance(features, np.ndarray):
            features = torch.FloatTensor(features).to(self.device)

        if features.dim() == 1:
            features = features.unsqueeze(0)

        # Truncate or pad to input_dim
        if features.shape[1] > self.input_dim:
            features = features[:, :self.input_dim]
        elif features.shape[1] < self.input_dim:
            pad = torch.zeros(features.shape[0], self.input_dim - features.shape[1], device=self.device)
            features = torch.cat([features, pad], dim=1)

        self.model.eval()
        recon, z_mean, z_log_var, z = self.model(features)

        # Reconstruction error (MSE per sample)
        recon_error = torch.mean((features - recon) ** 2, dim=1)

        # Distance from center
        center_dist = torch.sum((z_mean - self.model.center) ** 2, dim=1)

        # Uncertainty from the variance of latent distribution
        uncertainty = torch.mean(torch.exp(z_log_var), dim=1)

        # Malicious probability: sigmoid of scaled reconstruction error
        # Higher error → higher probability of being malicious
        combined_score = recon_error + 0.05 * center_dist
        malicious_prob = torch.sigmoid(combined_score * 2.0 - 1.0)

        return {
            'malicious_probability': malicious_prob.cpu().numpy(),
            'uncertainty': uncertainty.cpu().numpy(),
            'reconstruction_error': recon_error.cpu().numpy(),
            'center_distance': center_dist.cpu().numpy(),
        }

    @torch.no_grad()
    def encode(self, features: np.ndarray) -> np.ndarray:
        """
        Encode features to latent space (z_mean).

        Args:
            features: Input features of shape (batch, 55)

        Returns:
            Latent vectors of shape (batch, latent_dim)
        """
        if isinstance(features, np.ndarray):
            features = torch.FloatTensor(features).to(self.device)

        if features.dim() == 1:
            features = features.unsqueeze(0)

        if features.shape[1] > self.input_dim:
            features = features[:, :self.input_dim]
        elif features.shape[1] < self.input_dim:
            pad = torch.zeros(features.shape[0], self.input_dim - features.shape[1], device=self.device)
            features = torch.cat([features, pad], dim=1)

        self.model.eval()
        z_mean, _ = self.model.encode(features)
        return z_mean.cpu().numpy()

    def get_model_info(self) -> Dict:
        """Get model metadata."""
        return {
            'variant': self.variant,
            'input_dim': self.input_dim,
            'latent_dim': self.latent_dim,
            'model_path': self.model_path,
            'description': self.MODEL_VARIANTS.get(self.variant, {}).get('description', 'Custom'),
            'parameters': sum(p.numel() for p in self.model.parameters()),
        }


# Example usage and testing
if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("VAE LOADER - TEST")
    print("=" * 70)

    for variant in ['beta_vae', 'beta_vae_32', 'beta_vae_malicious']:
        try:
            loader = VAELoader(variant=variant)
            info = loader.get_model_info()
            print(f"\n  Variant: {info['description']}")
            print(f"  Parameters: {info['parameters']:,}")

            # Test with random input
            test_input = np.random.randn(4, 55).astype(np.float32)
            result = loader.get_malicious_probability(test_input)
            print(f"  Malicious probs: {result['malicious_probability']}")
            print(f"  Uncertainties:   {result['uncertainty']}")

            # Test encoding
            latent = loader.encode(test_input)
            print(f"  Latent shape:    {latent.shape}")
            print(f"  [OK] {variant} loaded successfully")
        except Exception as e:
            print(f"  [ERROR] {variant}: {e}")
