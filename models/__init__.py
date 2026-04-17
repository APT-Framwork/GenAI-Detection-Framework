"""
Model Loaders Package
=====================

Provides loaders for all detection models used in the RL APT system:
- RegularizedAE (anomaly detection via reconstruction error)
- BetaVAE (malicious probability estimation)
- TransformerCKCPredictor (next CKC stage prediction)
- APTPropagationGNN (lateral movement / propagation detection)
"""

from .autoencoder_loader import AutoencoderLoader, RegularizedAE
from .vae_loader import VAELoader, BetaVAE
from .transformer_loader import TransformerLoader, TransformerCKCPredictor
from .gnn_loader import GNNLoader

__all__ = [
    'AutoencoderLoader', 'RegularizedAE',
    'VAELoader', 'BetaVAE',
    'TransformerLoader', 'TransformerCKCPredictor',
    'GNNLoader',
]
