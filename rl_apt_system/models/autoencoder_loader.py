"""
Autoencoder Model Loader
========================

This module loads the pre-trained Autoencoder for anomaly detection.
The AE was trained to reconstruct SIEM events and produces:
- anomaly_score: reconstruction error indicating anomalous behavior
- reconstruction_error: MSE between input and reconstructed output

[WARNING] CRITICAL: This model requires FULL original feature vectors.
   Never feed synthetic tabular rows directly without conditional replay.
"""

import torch
import torch.nn as nn
import numpy as np
from pathlib import Path


class SIEMAutoencoder(nn.Module):
    """
    SIEM Autoencoder architecture for dimensionality reduction and anomaly detection.
    
    Architecture:
    - Encoder: projects high-dimensional SIEM features to latent space
    - Decoder: reconstructs original features from latent representation
    - Dropout: regularization to prevent overfitting
    
    The reconstruction error serves as an anomaly score:
    - Low error → normal/benign behavior
    - High error → anomalous/potentially malicious behavior
    """
    
    def __init__(self, input_dim: int, latent_dim: int = 64, dropout_rate: float = 0.2):
        super(SIEMAutoencoder, self).__init__()
        
        self.input_dim = input_dim
        self.latent_dim = latent_dim
        
        # Encoder: input_dim → hidden layers → latent_dim
        self.encoder = nn.Sequential(
            nn.Linear(input_dim, 256),
            nn.BatchNorm1d(256),
            nn.ReLU(),
            nn.Dropout(dropout_rate),
            nn.Linear(256, 128),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.Dropout(dropout_rate),
            nn.Linear(128, latent_dim),
            nn.BatchNorm1d(latent_dim),
            nn.ReLU()
        )
        
        # Decoder: latent_dim → hidden layers → input_dim
        self.decoder = nn.Sequential(
            nn.Linear(latent_dim, 128),
            nn.BatchNorm1d(128),
            nn.ReLU(),
            nn.Dropout(dropout_rate),
            nn.Linear(128, 256),
            nn.BatchNorm1d(256),
            nn.ReLU(),
            nn.Dropout(dropout_rate),
            nn.Linear(256, input_dim)
        )
    
    def forward(self, x):
        """
        Forward pass through encoder and decoder.
        
        Args:
            x: Input tensor of shape (batch_size, input_dim)
        
        Returns:
            reconstruction: Reconstructed input of shape (batch_size, input_dim)
            latent: Latent representation of shape (batch_size, latent_dim)
        """
        latent = self.encoder(x)
        reconstruction = self.decoder(latent)
        return reconstruction, latent


class AutoencoderLoader:
    """
    Loader for pre-trained Autoencoder model.
    
    Handles model initialization, weight loading, and inference.
    """
    
    def __init__(self, model_path: str, device: str = 'cpu'):
        """
        Initialize the Autoencoder loader.
        
        Args:
            model_path: Path to saved model weights (.pth file)
            device: Device to load model on ('cpu' or 'cuda')
        """
        self.device = torch.device(device)
        self.model_path = Path(model_path)
        self.model = None
        self.scaler = None  # Will be set externally if needed
        
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        
        self._load_model()
    
    def _load_model(self):
        """Load the pre-trained model weights."""
        # Load checkpoint
        checkpoint = torch.load(self.model_path, map_location=self.device, weights_only=False)
        
        # Extract model configuration
        if isinstance(checkpoint, dict):
            input_dim = checkpoint.get('input_dim', 200)  # Default fallback
            latent_dim = checkpoint.get('latent_dim', 64)
            state_dict = checkpoint.get('model_state_dict', checkpoint)
        else:
            # If checkpoint is just state_dict
            state_dict = checkpoint
            # Infer dimensions from state_dict
            input_dim = state_dict['encoder.0.weight'].shape[1]
            latent_dim = state_dict['encoder.4.weight'].shape[0]
        
        # Initialize model
        self.model = SIEMAutoencoder(
            input_dim=input_dim,
            latent_dim=latent_dim,
            dropout_rate=0.2
        )
        
        # Load weights
        self.model.load_state_dict(state_dict)
        self.model.to(self.device)
        self.model.eval()
        
        print(f"[OK] Autoencoder loaded successfully")
        print(f"   Input dim: {input_dim}, Latent dim: {latent_dim}")
        print(f"   Device: {self.device}")
    
    def set_scaler(self, scaler):
        """Set the preprocessing scaler (optional)."""
        self.scaler = scaler
    
    def get_anomaly_score(self, features: np.ndarray) -> dict:
        """
        Compute anomaly score for input features.
        
        Args:
            features: NumPy array of shape (n_samples, input_dim) or (input_dim,)
        
        Returns:
            Dictionary containing:
            - anomaly_score: Mean reconstruction error per sample
            - reconstruction_error: Full reconstruction error per sample
            - latent_vector: Latent representation
        """
        # Ensure 2D array
        if features.ndim == 1:
            features = features.reshape(1, -1)
        
        # Apply scaling if scaler is set
        if self.scaler is not None:
            features = self.scaler.transform(features)
        
        # Convert to tensor
        x = torch.FloatTensor(features).to(self.device)
        
        # Forward pass (no gradient computation)
        with torch.no_grad():
            reconstruction, latent = self.model(x)
            
            # Compute reconstruction error (MSE per sample)
            recon_error = torch.mean((x - reconstruction) ** 2, dim=1)
        
        # Convert to numpy
        anomaly_score = recon_error.cpu().numpy()
        reconstruction_error = recon_error.cpu().numpy()
        latent_vector = latent.cpu().numpy()
        
        return {
            'anomaly_score': anomaly_score,
            'reconstruction_error': reconstruction_error,
            'latent_vector': latent_vector
        }
    
    def encode(self, features: np.ndarray) -> np.ndarray:
        """
        Encode features to latent representation.
        
        Args:
            features: Input features of shape (n_samples, input_dim)
        
        Returns:
            Latent vectors of shape (n_samples, latent_dim)
        """
        if features.ndim == 1:
            features = features.reshape(1, -1)
        
        if self.scaler is not None:
            features = self.scaler.transform(features)
        
        x = torch.FloatTensor(features).to(self.device)
        
        with torch.no_grad():
            latent = self.model.encoder(x)
        
        return latent.cpu().numpy()


# Example usage and testing
if __name__ == "__main__":
    print("\n" + "="*70)
    print("AUTOENCODER LOADER - TEST")
    print("="*70)
    
    # Example: Load model
    model_path = "../autoencoder_outputs/autoencoder_anomaly_detection.pth"
    
    try:
        loader = AutoencoderLoader(model_path, device='cpu')
        
        # Test with random data
        n_samples = 5
        input_dim = loader.model.input_dim
        test_features = np.random.randn(n_samples, input_dim)
        
        print(f"\n[*] Testing with {n_samples} random samples...")
        results = loader.get_anomaly_score(test_features)
        
        print(f"\n[OK] Results:")
        print(f"   Anomaly scores: {results['anomaly_score']}")
        print(f"   Latent shape: {results['latent_vector'].shape}")
        
    except FileNotFoundError as e:
        print(f"\n[WARNING] {e}")
        print("   Please ensure the model file exists at the specified path.")
