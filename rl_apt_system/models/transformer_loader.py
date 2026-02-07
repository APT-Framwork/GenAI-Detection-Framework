"""
Transformer Model Loader
========================

This module loads the pre-trained Transformer sequence model for CKC prediction.
The Transformer was trained on sequences of latent vectors and produces:
- predicted_next_ckc_stage: predicted next stage in the Cyber Kill Chain
- prediction_confidence: confidence score for the prediction

[WARNING] CRITICAL: This model expects sequences of latent vectors or features.
   Input sequences must maintain temporal ordering.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from pathlib import Path
import math


class PositionalEncoding(nn.Module):
    """
    Positional encoding for Transformer.
    Adds temporal position information to input embeddings.
    """
    
    def __init__(self, d_model: int, max_len: int = 500, dropout: float = 0.1):
        super(PositionalEncoding, self).__init__()
        self.dropout = nn.Dropout(p=dropout)
        
        # Compute positional encodings
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)  # (1, max_len, d_model)
        
        self.register_buffer('pe', pe)
    
    def forward(self, x):
        """
        Args:
            x: Tensor of shape (batch_size, seq_len, d_model)
        Returns:
            Tensor with positional encoding added
        """
        x = x + self.pe[:, :x.size(1), :]
        return self.dropout(x)


class TransformerCKCPredictor(nn.Module):
    """
    Transformer model for predicting next CKC stage from event sequences.
    
    Architecture:
    - Input projection: projects input features to model dimension
    - Positional encoding: adds temporal information
    - Transformer encoder: processes sequence with self-attention
    - Output head: predicts next CKC stage (7 classes: S1-S7)
    """
    
    def __init__(
        self,
        input_dim: int,
        d_model: int = 128,
        n_heads: int = 8,
        n_layers: int = 4,
        d_ff: int = 512,
        dropout: float = 0.1,
        num_classes: int = 8  # Changed from 7 to 8 to match saved model
    ):
        super(TransformerCKCPredictor, self).__init__()
        
        self.input_dim = input_dim
        self.d_model = d_model
        self.num_classes = num_classes
        
        # Input projection: map input features to d_model
        # Split Linear and BatchNorm for proper dimension handling
        self.input_linear = nn.Linear(input_dim, d_model)
        self.input_bn = nn.BatchNorm1d(d_model)
        
        # Positional encoding
        self.pos_encoder = PositionalEncoding(d_model, dropout=dropout)
        
        # Transformer encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=n_heads,
            dim_feedforward=d_ff,
            dropout=dropout,
            activation='relu',
            batch_first=True
        )
        self.transformer_encoder = nn.TransformerEncoder(encoder_layer, num_layers=n_layers)
        
        # Output head for CKC stage prediction
        self.output_head = nn.Sequential(
            nn.Linear(d_model, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, num_classes)
        )
    
    def forward(self, x, src_mask=None, src_key_padding_mask=None):
        """
        Forward pass through Transformer.
        
        Args:
            x: Input sequence of shape (batch_size, seq_len, input_dim)
            src_mask: Optional attention mask
            src_key_padding_mask: Optional padding mask
        
        Returns:
            logits: Class logits of shape (batch_size, num_classes)
        """
        # Project input to model dimension
        # x shape: (batch, seq_len, input_dim)
        x = self.input_linear(x)  # (batch, seq_len, d_model)
        
        # Apply BatchNorm: need to transpose for BatchNorm1d
        # BatchNorm1d expects (batch, features, seq_len)
        x = x.transpose(1, 2)  # (batch, d_model, seq_len)
        x = self.input_bn(x)
        x = x.transpose(1, 2)  # (batch, seq_len, d_model)
        
        # Add positional encoding
        x = self.pos_encoder(x)
        
        # Apply transformer encoder
        encoded = self.transformer_encoder(
            x,
            mask=src_mask,
            src_key_padding_mask=src_key_padding_mask
        )  # (batch, seq_len, d_model)
        
        # Take the last sequence position for prediction
        # (predicting next stage based on sequence so far)
        last_hidden = encoded[:, -1, :]  # (batch, d_model)
        
        # Predict next CKC stage
        logits = self.output_head(last_hidden)  # (batch, num_classes)
        
        return logits


class TransformerLoader:
    """
    Loader for pre-trained Transformer model.
    
    Handles model initialization, weight loading, and inference.
    Provides CKC stage prediction with confidence scores.
    """
    
    def __init__(self, model_path: str, device: str = 'cpu'):
        """
        Initialize the Transformer loader.
        
        Args:
            model_path: Path to saved model weights (.pth file)
            device: Device to load model on ('cpu' or 'cuda')
        """
        self.device = torch.device(device)
        self.model_path = Path(model_path)
        self.model = None
        self.scaler = None
        
        # CKC stage mapping (1-indexed to 0-indexed)
        self.ckc_stages = {
            0: 'S1_Reconnaissance',
            1: 'S2_Weaponization',
            2: 'S3_Delivery',
            3: 'S4_Exploitation',
            4: 'S5_Installation',
            5: 'S6_C2',
            6: 'S7_Actions'
        }
        
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        
        self._load_model()
    
    def _load_model(self):
        """Load the pre-trained model weights."""
        # Load checkpoint
        checkpoint = torch.load(self.model_path, map_location=self.device, weights_only=False)
        
        # Extract model configuration
        if isinstance(checkpoint, dict):
            input_dim = checkpoint.get('input_dim', 64)  # latent dimension
            d_model = checkpoint.get('d_model', 128)
            n_heads = checkpoint.get('n_heads', 8)
            n_layers = checkpoint.get('n_layers', 4)
            d_ff = checkpoint.get('d_ff', 512)
            dropout = checkpoint.get('dropout', 0.1)
            num_classes = checkpoint.get('num_classes', 8)  # Default to 8
            state_dict = checkpoint.get('model_state_dict', checkpoint)
        else:
            state_dict = checkpoint
            # Infer dimensions - check both possible key names
            if 'input_projection.0.weight' in state_dict:
                input_dim = state_dict['input_projection.0.weight'].shape[1]
                d_model = state_dict['input_projection.0.weight'].shape[0]
            elif 'input_linear.weight' in state_dict:
                input_dim = state_dict['input_linear.weight'].shape[1]
                d_model = state_dict['input_linear.weight'].shape[0]
            else:
                # Fallback defaults
                input_dim = 64
                d_model = 128
            
            num_classes = state_dict['output_head.3.weight'].shape[0]  # Changed from .2 to .3
            n_heads = 8
            n_layers = 4
            d_ff = 512
            dropout = 0.1
        
        # Rename keys if needed (input_projection.0 -> input_linear, input_projection.1 -> input_bn)
        new_state_dict = {}
        for key, value in state_dict.items():
            if key.startswith('input_projection.0'):
                new_key = key.replace('input_projection.0', 'input_linear')
                new_state_dict[new_key] = value
            elif key.startswith('input_projection.1'):
                new_key = key.replace('input_projection.1', 'input_bn')
                new_state_dict[new_key] = value
            else:
                new_state_dict[key] = value
        
        # Initialize model
        self.model = TransformerCKCPredictor(
            input_dim=input_dim,
            d_model=d_model,
            n_heads=n_heads,
            n_layers=n_layers,
            d_ff=d_ff,
            dropout=dropout,
            num_classes=num_classes
        )
        
        # Load weights (strict=False to ignore extra keys like transformer_encoder.norm)
        self.model.load_state_dict(new_state_dict, strict=False)
        self.model.to(self.device)
        self.model.eval()
        
        print(f"[OK] Transformer loaded successfully")
        print(f"   Input dim: {input_dim}, d_model: {d_model}")
        print(f"   Heads: {n_heads}, Layers: {n_layers}")
        print(f"   Classes: {num_classes} (CKC stages)")
        print(f"   Device: {self.device}")
    
    def set_scaler(self, scaler):
        """Set the preprocessing scaler (optional)."""
        self.scaler = scaler
    
    def predict_next_stage(self, sequence: np.ndarray) -> dict:
        """
        Predict the next CKC stage from a sequence of events.
        
        Args:
            sequence: NumPy array of shape (seq_len, input_dim) or (batch, seq_len, input_dim)
        
        Returns:
            Dictionary containing:
            - predicted_next_ckc_stage: Predicted stage (1-7)
            - prediction_confidence: Confidence score [0, 1]
            - stage_probabilities: Probability distribution over all stages
            - stage_name: Human-readable stage name
        """
        # Ensure 3D array (batch, seq_len, input_dim)
        if sequence.ndim == 2:
            sequence = sequence[np.newaxis, :, :]  # Add batch dimension
        
        # Apply scaling if scaler is set
        if self.scaler is not None:
            batch_size, seq_len, input_dim = sequence.shape
            sequence_flat = sequence.reshape(-1, input_dim)
            sequence_scaled = self.scaler.transform(sequence_flat)
            sequence = sequence_scaled.reshape(batch_size, seq_len, input_dim)
        
        # Convert to tensor
        x = torch.FloatTensor(sequence).to(self.device)
        
        # Forward pass
        with torch.no_grad():
            logits = self.model(x)  # (batch, num_classes)
            probs = F.softmax(logits, dim=-1)  # (batch, num_classes)
            
            # Get predicted class and confidence
            confidence, predicted_class = torch.max(probs, dim=-1)
        
        # Convert to numpy
        predicted_class_np = predicted_class.cpu().numpy()
        confidence_np = confidence.cpu().numpy()
        probs_np = probs.cpu().numpy()
        
        # Convert 0-indexed to 1-indexed CKC stages
        predicted_stage = predicted_class_np + 1
        
        # Get stage name
        stage_name = self.ckc_stages.get(predicted_class_np[0], 'Unknown')
        
        return {
            'predicted_next_ckc_stage': predicted_stage[0] if len(predicted_stage) == 1 else predicted_stage,
            'prediction_confidence': confidence_np[0] if len(confidence_np) == 1 else confidence_np,
            'stage_probabilities': probs_np[0] if len(probs_np) == 1 else probs_np,
            'stage_name': stage_name
        }
    
    def predict_batch(self, sequences: list) -> list:
        """
        Predict next CKC stage for a batch of sequences.
        
        Args:
            sequences: List of sequences, each of shape (seq_len, input_dim)
        
        Returns:
            List of prediction dictionaries
        """
        results = []
        for seq in sequences:
            result = self.predict_next_stage(seq)
            results.append(result)
        return results


# Example usage and testing
if __name__ == "__main__":
    print("\n" + "="*70)
    print("TRANSFORMER LOADER - TEST")
    print("="*70)
    
    # Example: Load model
    model_path = "../transformer_outputs/transformer_next_step_prediction.pth"
    
    try:
        loader = TransformerLoader(model_path, device='cpu')
        
        # Test with random sequence
        seq_len = 10
        input_dim = loader.model.input_dim
        test_sequence = np.random.randn(seq_len, input_dim)
        
        print(f"\n[*] Testing with sequence of length {seq_len}...")
        result = loader.predict_next_stage(test_sequence)
        
        print(f"\n[OK] Prediction:")
        print(f"   Next CKC stage: S{result['predicted_next_ckc_stage']}")
        print(f"   Confidence: {result['prediction_confidence']:.4f}")
        print(f"   Stage name: {result['stage_name']}")
        print(f"   All probabilities: {result['stage_probabilities']}")
        
    except FileNotFoundError as e:
        print(f"\n[WARNING] {e}")
        print("   Please ensure the model file exists at the specified path.")
