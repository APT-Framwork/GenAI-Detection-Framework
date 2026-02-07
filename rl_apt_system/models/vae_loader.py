"""
VAE (Variational Autoencoder) Model Loader
===========================================

This module loads the pre-trained VAE for malicious event detection.
The VAE was trained on BENIGN data only and produces:
- malicious_probability: probability that an event is malicious (high reconstruction error)
- uncertainty: variance/entropy in the latent space indicating model confidence

[WARNING] CRITICAL: This model requires FULL original feature vectors.
   Never feed synthetic tabular rows directly without conditional replay.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from pathlib import Path


class SIEMVAE(nn.Module):
    """
    SIEM Variational Autoencoder for anomaly detection.
    
    Architecture:
    - Encoder: projects input to latent distribution (mean and log-variance)
    - Reparameterization: samples from latent distribution
    - Decoder: reconstructs input from latent sample
    
    Trained on benign data only, so malicious events have high reconstruction error.
    The latent space variance provides uncertainty estimation.
    """
    
    def __init__(self, input_dim: int, latent_dim: int = 32, dropout_rate: float = 0.3):
        super(SIEMVAE, self).__init__()
        
        self.input_dim = input_dim
        self.latent_dim = latent_dim
        
        # Encoder layers with named layers to match saved model
        # Architecture: input → 512 → 256 → 128 → latent
        self.encoder_l1 = nn.Linear(input_dim, 512)
        self.encoder_bn1 = nn.BatchNorm1d(512)
        self.encoder_l2 = nn.Linear(512, 256)
        self.encoder_bn2 = nn.BatchNorm1d(256)
        self.encoder_l3 = nn.Linear(256, 128)
        self.encoder_bn3 = nn.BatchNorm1d(128)
        self.dropout = nn.Dropout(dropout_rate)
        self.relu = nn.ReLU()
        
        # Latent distribution parameters
        self.fc_z_mean = nn.Linear(128, latent_dim)
        self.fc_z_log_var = nn.Linear(128, latent_dim)
        
        # Decoder layers with named layers to match saved model
        # Architecture: latent → 128 → 256 → 512 → output
        self.decoder_l1 = nn.Linear(latent_dim, 128)
        self.decoder_bn1 = nn.BatchNorm1d(128)
        self.decoder_l2 = nn.Linear(128, 256)
        self.decoder_bn2 = nn.BatchNorm1d(256)
        self.decoder_l3 = nn.Linear(256, 512)
        self.decoder_bn3 = nn.BatchNorm1d(512)
        self.decoder_out = nn.Linear(512, input_dim)
    
    def encode(self, x):
        """Encode input to latent distribution parameters."""
        h = self.relu(self.encoder_bn1(self.encoder_l1(x)))
        h = self.dropout(h)
        h = self.relu(self.encoder_bn2(self.encoder_l2(h)))
        h = self.dropout(h)
        h = self.relu(self.encoder_bn3(self.encoder_l3(h)))
        h = self.dropout(h)
        
        z_mean = self.fc_z_mean(h)
        z_log_var = self.fc_z_log_var(h)
        return z_mean, z_log_var
    
    def reparameterize(self, z_mean, z_log_var):
        """
        Reparameterization trick: z = mean + std * epsilon
        where epsilon ~ N(0, 1)
        """
        std = torch.exp(0.5 * z_log_var)
        eps = torch.randn_like(std)
        z = z_mean + eps * std
        return z
    
    def decode(self, z):
        """Decode latent vector to reconstruction."""
        h = self.relu(self.decoder_bn1(self.decoder_l1(z)))
        h = self.dropout(h)
        h = self.relu(self.decoder_bn2(self.decoder_l2(h)))
        h = self.dropout(h)
        h = self.relu(self.decoder_bn3(self.decoder_l3(h)))
        h = self.dropout(h)
        reconstruction = self.decoder_out(h)
        return reconstruction
    
    def forward(self, x):
        """
        Forward pass through VAE.
        
        Args:
            x: Input tensor of shape (batch_size, input_dim)
        
        Returns:
            reconstruction: Reconstructed input
            z_mean: Mean of latent distribution
            z_log_var: Log-variance of latent distribution
        """
        z_mean, z_log_var = self.encode(x)
        z = self.reparameterize(z_mean, z_log_var)
        reconstruction = self.decode(z)
        return reconstruction, z_mean, z_log_var


class VAELoader:
    """
    Loader for pre-trained VAE model.
    
    Handles model initialization, weight loading, and inference.
    Provides malicious probability and uncertainty estimation.
    """
    
    def __init__(self, model_path: str, threshold: float = None, device: str = 'cpu'):
        """
        Initialize the VAE loader.
        
        Args:
            model_path: Path to saved model weights (.pth file)
            threshold: Reconstruction error threshold for malicious classification
            device: Device to load model on ('cpu' or 'cuda')
        """
        self.device = torch.device(device)
        self.model_path = Path(model_path)
        self.model = None
        self.scaler = None
        self.threshold = threshold  # Will be set from training/validation
        
        if not self.model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")
        
        self._load_model()
    
    def _load_model(self):
        """Load the pre-trained model weights."""
        # Load checkpoint
        checkpoint = torch.load(self.model_path, map_location=self.device, weights_only=False)
        
        # Extract model configuration
        if isinstance(checkpoint, dict):
            input_dim = checkpoint.get('input_dim', 200)
            latent_dim = checkpoint.get('latent_dim', 32)
            state_dict = checkpoint.get('model_state_dict', checkpoint)
            self.threshold = checkpoint.get('threshold', self.threshold)
        else:
            state_dict = checkpoint
            # Infer dimensions
            input_dim = state_dict['encoder.0.weight'].shape[1]
            latent_dim = state_dict['fc_mean.weight'].shape[0]
        
        # Initialize model
        self.model = SIEMVAE(
            input_dim=input_dim,
            latent_dim=latent_dim,
            dropout_rate=0.3
        )
        
        # Load weights
        self.model.load_state_dict(state_dict)
        self.model.to(self.device)
        self.model.eval()
        
        print(f"[OK] VAE loaded successfully")
        print(f"   Input dim: {input_dim}, Latent dim: {latent_dim}")
        print(f"   Threshold: {self.threshold if self.threshold else 'Not set'}")
        print(f"   Device: {self.device}")
    
    def set_scaler(self, scaler):
        """Set the preprocessing scaler (optional)."""
        self.scaler = scaler
    
    def set_threshold(self, threshold: float):
        """Set the malicious classification threshold."""
        self.threshold = threshold
    
    def get_malicious_probability(self, features: np.ndarray) -> dict:
        """
        Compute malicious probability and uncertainty for input features.
        
        Args:
            features: NumPy array of shape (n_samples, input_dim) or (input_dim,)
        
        Returns:
            Dictionary containing:
            - malicious_probability: Probability that sample is malicious [0, 1]
            - uncertainty: Uncertainty estimate based on latent variance
            - reconstruction_error: Raw reconstruction error
            - z_mean: Latent mean
            - z_log_var: Latent log-variance
        """
        # Ensure 2D array
        if features.ndim == 1:
            features = features.reshape(1, -1)
        
        # Apply scaling if scaler is set
        if self.scaler is not None:
            features = self.scaler.transform(features)
        
        # Convert to tensor
        x = torch.FloatTensor(features).to(self.device)
        
        # Forward pass
        with torch.no_grad():
            reconstruction, z_mean, z_log_var = self.model(x)
            
            # Compute reconstruction error
            recon_error = torch.mean((x - reconstruction) ** 2, dim=1)
            
            # Compute uncertainty (average variance in latent space)
            # Higher variance = higher uncertainty
            z_var = torch.exp(z_log_var)
            uncertainty = torch.mean(z_var, dim=1)
        
        # Convert to numpy
        recon_error_np = recon_error.cpu().numpy()
        uncertainty_np = uncertainty.cpu().numpy()
        z_mean_np = z_mean.cpu().numpy()
        z_log_var_np = z_log_var.cpu().numpy()
        
        # Compute malicious probability
        # If threshold is set, use sigmoid-based probability
        if self.threshold is not None:
            # Probability increases as reconstruction error exceeds threshold
            # Use sigmoid for smooth transition
            diff = (recon_error_np - self.threshold) / (self.threshold * 0.5)
            malicious_prob = 1 / (1 + np.exp(-diff))
        else:
            # Normalize reconstruction error to [0, 1] range
            # Higher error = higher probability
            # This is a heuristic without threshold
            malicious_prob = np.clip(recon_error_np / (recon_error_np.mean() + 2 * recon_error_np.std()), 0, 1)
        
        return {
            'malicious_probability': malicious_prob,
            'uncertainty': uncertainty_np,
            'reconstruction_error': recon_error_np,
            'z_mean': z_mean_np,
            'z_log_var': z_log_var_np
        }
    
    def get_latent_representation(self, features: np.ndarray) -> dict:
        """
        Get latent representation of features.
        
        Args:
            features: Input features
        
        Returns:
            Dictionary with z_mean and z_log_var
        """
        if features.ndim == 1:
            features = features.reshape(1, -1)
        
        if self.scaler is not None:
            features = self.scaler.transform(features)
        
        x = torch.FloatTensor(features).to(self.device)
        
        with torch.no_grad():
            z_mean, z_log_var = self.model.encode(x)
        
        return {
            'z_mean': z_mean.cpu().numpy(),
            'z_log_var': z_log_var.cpu().numpy()
        }


# Example usage and testing
if __name__ == "__main__":
    print("\n" + "="*70)
    print("VAE LOADER - TEST")
    print("="*70)
    
    # Example: Load model
    model_path = "../vae_anomaly_detector_outputs/vae_anomaly_detector.pth"
    
    try:
        loader = VAELoader(model_path, threshold=0.05, device='cpu')
        
        # Test with random data
        n_samples = 5
        input_dim = loader.model.input_dim
        test_features = np.random.randn(n_samples, input_dim)
        
        print(f"\n[*] Testing with {n_samples} random samples...")
        results = loader.get_malicious_probability(test_features)
        
        print(f"\n[OK] Results:")
        print(f"   Malicious probabilities: {results['malicious_probability']}")
        print(f"   Uncertainties: {results['uncertainty']}")
        print(f"   Reconstruction errors: {results['reconstruction_error']}")
        
    except FileNotFoundError as e:
        print(f"\n[WARNING] {e}")
        print("   Please ensure the model file exists at the specified path.")
