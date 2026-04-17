"""
Transformer CKC Predictor Loader
=================================

Loads the retrained Transformer model for next CKC stage prediction.
Uses the AE latent vectors (64-dim) as input sequence.

Model: transformer_next_step_prediction_top25.pth
Config (from checkpoint):
    input_dim: 64
    d_model: 128
    n_heads: 8
    n_encoder_layers: 4
    dim_feedforward: 512
    dropout: 0.1
    num_classes: 8 (Benign + S1..S7)
    max_seq_length: 500
    seq_length: 4
"""

import os
import math
import numpy as np
import torch
import torch.nn as nn
from typing import Dict, Optional


class PositionalEncoding(nn.Module):
    """Sinusoidal positional encoding for Transformer."""

    def __init__(self, d_model: int, max_len: int = 500):
        super().__init__()
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)  # (1, max_len, d_model)
        self.register_buffer('pe', pe)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Add positional encoding to input. x: (batch, seq_len, d_model)"""
        return x + self.pe[:, :x.size(1), :]


class TransformerCKCPredictor(nn.Module):
    """
    Transformer encoder for predicting the next CKC stage
    from a sequence of AE latent vectors.
    """

    def __init__(
        self,
        input_dim: int = 64,
        d_model: int = 128,
        n_heads: int = 8,
        n_encoder_layers: int = 4,
        dim_feedforward: int = 512,
        dropout: float = 0.1,
        num_classes: int = 8,
        max_seq_length: int = 500,
    ):
        super().__init__()

        self.input_dim = input_dim
        self.d_model = d_model
        self.num_classes = num_classes

        # Input projection
        self.input_projection = nn.Sequential(
            nn.Linear(input_dim, d_model),
            nn.LayerNorm(d_model),
        )

        # Positional encoding
        self.pos_encoder = PositionalEncoding(d_model, max_len=max_seq_length)

        # Transformer encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=n_heads,
            dim_feedforward=dim_feedforward,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer_encoder = nn.TransformerEncoder(
            encoder_layer, num_layers=n_encoder_layers,
            norm=nn.LayerNorm(d_model),
        )

        # Output head
        self.output_head = nn.Sequential(
            nn.Linear(d_model, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, num_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Forward pass.

        Args:
            x: (batch, seq_len, input_dim) — sequence of latent vectors

        Returns:
            (batch, num_classes) — class logits for next CKC stage
        """
        # Project to d_model
        x = self.input_projection(x)

        # Add positional encoding
        x = self.pos_encoder(x)

        # Transformer encoder
        x = self.transformer_encoder(x)

        # Use the last position's output for prediction
        x = x[:, -1, :]  # (batch, d_model)

        # Classification head
        return self.output_head(x)


class TransformerLoader:
    """
    Wrapper for loading and using the Transformer CKC predictor.

    Takes sequences of AE latent vectors and predicts the next
    Cyber Kill Chain stage.
    """

    # CKC stage names mapping (0-indexed)
    CKC_STAGES = {
        0: 'Benign',
        1: 'S1 - Reconnaissance',
        2: 'S2 - Weaponization',
        3: 'S3 - Delivery',
        4: 'S4 - Exploitation',
        5: 'S5 - Installation',
        6: 'S6 - Command & Control',
        7: 'S7 - Actions on Objectives',
    }

    def __init__(
        self,
        model_path: Optional[str] = None,
        device: str = 'cpu',
    ):
        """
        Initialize the TransformerLoader.

        Args:
            model_path: Path to model checkpoint
            device: Device to load model on
        """
        self.device = torch.device(device)

        # Resolve model path
        if model_path is None:
            models_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'models')
            model_path = os.path.join(models_dir, 'transformer_next_step_prediction_top25.pth')

        self.model_path = model_path
        self.config = None
        self.model = self._load_model()

        print(f"[Transformer] Loaded: {os.path.basename(model_path)}")
        if self.config:
            print(f"              Config: input={self.config['input_dim']}, "
                  f"d_model={self.config['d_model']}, layers={self.config['n_encoder_layers']}, "
                  f"classes={self.config['num_classes']}")

    def _load_model(self) -> TransformerCKCPredictor:
        """Load the model from checkpoint."""
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model file not found: {self.model_path}")

        checkpoint = torch.load(self.model_path, map_location=self.device, weights_only=False)

        # Extract config if present
        if isinstance(checkpoint, dict) and 'config' in checkpoint:
            self.config = checkpoint['config']
            state_dict = checkpoint['model_state_dict']
        elif isinstance(checkpoint, dict) and 'model_state_dict' in checkpoint:
            state_dict = checkpoint['model_state_dict']
            self.config = None
        else:
            state_dict = checkpoint
            self.config = None

        # Build model from config or defaults
        config = self.config or {}
        model = TransformerCKCPredictor(
            input_dim=config.get('input_dim', 64),
            d_model=config.get('d_model', 128),
            n_heads=config.get('n_heads', 8),
            n_encoder_layers=config.get('n_encoder_layers', 4),
            dim_feedforward=config.get('dim_feedforward', 512),
            dropout=config.get('dropout', 0.1),
            num_classes=config.get('num_classes', 8),
            max_seq_length=config.get('max_seq_length', 500),
        ).to(self.device)

        model.load_state_dict(state_dict, strict=True)
        model.eval()

        return model

    @torch.no_grad()
    def predict_next_stage(self, latent_sequence: np.ndarray) -> Dict:
        """
        Predict the next CKC stage from a sequence of latent vectors.

        Args:
            latent_sequence: Array of shape (seq_len, latent_dim) from AE encoder

        Returns:
            Dict with predicted stage, confidence, and all probabilities
        """
        if isinstance(latent_sequence, np.ndarray):
            latent_sequence = torch.FloatTensor(latent_sequence).to(self.device)

        if latent_sequence.dim() == 2:
            latent_sequence = latent_sequence.unsqueeze(0)  # (1, seq_len, dim)

        self.model.eval()
        logits = self.model(latent_sequence)  # (1, num_classes)
        probs = torch.softmax(logits, dim=-1).squeeze(0)  # (num_classes,)

        predicted_stage = torch.argmax(probs).item()
        confidence = probs[predicted_stage].item()

        return {
            'predicted_next_ckc_stage': predicted_stage,
            'prediction_confidence': confidence,
            'stage_name': self.CKC_STAGES.get(predicted_stage, f'Unknown ({predicted_stage})'),
            'all_probabilities': probs.cpu().numpy(),
        }

    def get_model_info(self) -> Dict:
        """Get model metadata."""
        return {
            'config': self.config,
            'model_path': self.model_path,
            'parameters': sum(p.numel() for p in self.model.parameters()),
            'num_classes': self.config.get('num_classes', 8) if self.config else 8,
        }


# Example usage and testing
if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("TRANSFORMER LOADER - TEST")
    print("=" * 70)

    try:
        loader = TransformerLoader()
        info = loader.get_model_info()
        print(f"\n  Parameters: {info['parameters']:,}")
        print(f"  Classes: {info['num_classes']}")

        # Test with random latent sequence (pretending AE produced these)
        test_sequence = np.random.randn(4, 64).astype(np.float32)  # 4 steps, 64-dim latent
        result = loader.predict_next_stage(test_sequence)
        print(f"  Predicted stage: {result['stage_name']}")
        print(f"  Confidence: {result['prediction_confidence']:.4f}")
        print(f"  All probs: {result['all_probabilities']}")
        print("  [OK] Transformer loaded successfully")
    except Exception as e:
        print(f"  [ERROR] {e}")
