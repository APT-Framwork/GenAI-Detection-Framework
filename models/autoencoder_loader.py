"""
Regularized Autoencoder Loader
==============================

Loads the retrained RegularizedAE model (25 features → 55 columns).
Supports both 64-dim and 32-dim latent variants.

Model Variants:
--------------
- reg_ae_top25_features.pth       → input=55, latent=64
- reg_ae_top25_features_32dim.pth → input=55, latent=32

Architecture (from checkpoint):
-------------------------------
encoder_body: Sequential(Linear(55→256), BN(256), ReLU, Drop, Linear(256→128), BN(128), ReLU)
fc_mu: Linear(128→latent_dim)
fc_logvar: Linear(128→latent_dim)
decoder: Sequential(Linear(latent_dim→128), BN(128), ReLU, Drop, Linear(128→256), BN(256), ReLU, Drop, Linear(256→55))
center: Parameter(latent_dim)
"""

import os
import numpy as np
import torch
import torch.nn as nn
from typing import Dict, Optional


class RegularizedAE(nn.Module):
    """
    Regularized Autoencoder with VAE-style mu/logvar for anomaly detection.
    Trained on the 25 selected features (55 columns after embedding expansion).
    """

    def __init__(self, input_dim: int = 55, latent_dim: int = 64, dropout: float = 0.2):
        super(RegularizedAE, self).__init__()

        self.input_dim = input_dim
        self.latent_dim = latent_dim

        # Learnable center for anomaly scoring
        self.register_buffer('center', torch.zeros(latent_dim))

        # Encoder
        self.encoder_body = nn.Sequential(
            nn.Linear(input_dim, 256),
            nn.BatchNorm1d(256),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(256, 128),
            nn.BatchNorm1d(128),
            nn.ReLU(),
        )

        # Latent space projections
        self.fc_mu = nn.Linear(128, latent_dim)
        self.fc_logvar = nn.Linear(128, latent_dim)

        # Decoder
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 128),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(128, 256),
            nn.BatchNorm1d(256),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(256, input_dim),
        )

    def encode(self, x: torch.Tensor):
        """Encode input to latent space, returning mu and logvar."""
        h = self.encoder_body(x)
        mu = self.fc_mu(h)
        logvar = self.fc_logvar(h)
        return mu, logvar

    def reparameterize(self, mu: torch.Tensor, logvar: torch.Tensor) -> torch.Tensor:
        """Reparameterization trick."""
        if self.training:
            std = torch.exp(0.5 * logvar)
            eps = torch.randn_like(std)
            return mu + eps * std
        return mu

    def decode(self, z: torch.Tensor) -> torch.Tensor:
        """Decode latent vector to reconstruction."""
        return self.decoder(z)

    def forward(self, x: torch.Tensor):
        """Full forward pass."""
        mu, logvar = self.encode(x)
        z = self.reparameterize(mu, logvar)
        recon = self.decode(z)
        return recon, mu, logvar, z


class AutoencoderLoader:
    """
    Wrapper for loading and using the RegularizedAE model.

    Provides high-level methods for anomaly scoring and encoding
    that are consumed by the RL environment.
    """

    # Available model variants
    MODEL_VARIANTS = {
        'reg_ae_64': {
            'filename': 'reg_ae_top25_features.pth',
            'latent_dim': 64,
            'description': 'Regularized AE (latent=64)',
        },
        'reg_ae_32': {
            'filename': 'reg_ae_top25_features_32dim.pth',
            'latent_dim': 32,
            'description': 'Regularized AE (latent=32)',
        },
    }

    def __init__(
        self,
        model_path: Optional[str] = None,
        variant: str = 'reg_ae_64',
        input_dim: int = 55,
        device: str = 'cpu',
    ):
        """
        Initialize the AutoencoderLoader.

        Args:
            model_path: Direct path to model file (overrides variant)
            variant: Model variant key ('reg_ae_64' or 'reg_ae_32')
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
            # Infer latent dim from variant or default
            self.latent_dim = self.MODEL_VARIANTS.get(variant, {}).get('latent_dim', 64)

        self.model_path = model_path
        self.model = self._load_model()

        print(f"[AE] Loaded: {os.path.basename(model_path)}")
        print(f"     Architecture: {input_dim} -> {self.latent_dim} (latent) -> {input_dim}")

    def _load_model(self) -> RegularizedAE:
        """Load the model from checkpoint."""
        model = RegularizedAE(
            input_dim=self.input_dim,
            latent_dim=self.latent_dim,
        ).to(self.device)

        if os.path.exists(self.model_path):
            state_dict = torch.load(self.model_path, map_location=self.device, weights_only=False)
            # Handle both OrderedDict (direct state_dict) and wrapped checkpoints
            if isinstance(state_dict, dict) and 'model_state_dict' in state_dict:
                state_dict = state_dict['model_state_dict']
            model.load_state_dict(state_dict, strict=True)
            model.eval()
        else:
            raise FileNotFoundError(f"Model file not found: {self.model_path}")

        return model

    @torch.no_grad()
    def get_anomaly_score(self, features: np.ndarray) -> Dict[str, np.ndarray]:
        """
        Compute anomaly score for input features.

        Uses reconstruction error and distance from learned center
        to produce an anomaly score.

        Args:
            features: Input features of shape (batch, 55)

        Returns:
            Dict with 'anomaly_score' and 'reconstruction_error'
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
        recon, mu, logvar, z = self.model(features)

        # Reconstruction error (MSE per sample)
        recon_error = torch.mean((features - recon) ** 2, dim=1)

        # Distance from center in latent space
        center_dist = torch.sum((mu - self.model.center) ** 2, dim=1)

        # Combined anomaly score
        anomaly_score = recon_error + 0.1 * center_dist

        return {
            'anomaly_score': anomaly_score.cpu().numpy(),
            'reconstruction_error': recon_error.cpu().numpy(),
            'center_distance': center_dist.cpu().numpy(),
        }

    @torch.no_grad()
    def encode(self, features: np.ndarray) -> np.ndarray:
        """
        Encode features to latent space (mu).
        Used to feed into the Transformer for CKC prediction.

        Args:
            features: Input features of shape (batch, 55) or (seq_len, 55)

        Returns:
            Latent vectors of shape (batch, latent_dim)
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
        mu, _ = self.model.encode(features)
        return mu.cpu().numpy()

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
    print("AUTOENCODER LOADER - TEST")
    print("=" * 70)

    for variant in ['reg_ae_64', 'reg_ae_32']:
        try:
            loader = AutoencoderLoader(variant=variant)
            info = loader.get_model_info()
            print(f"\n  Variant: {info['description']}")
            print(f"  Parameters: {info['parameters']:,}")

            # Test with random input
            test_input = np.random.randn(4, 55).astype(np.float32)
            result = loader.get_anomaly_score(test_input)
            print(f"  Anomaly scores: {result['anomaly_score']}")
            print(f"  Recon errors:   {result['reconstruction_error']}")

            # Test encoding
            latent = loader.encode(test_input)
            print(f"  Latent shape:   {latent.shape}")
            print(f"  [OK] {variant} loaded successfully")
        except Exception as e:
            print(f"  [ERROR] {variant}: {e}")
