"""
APT Detection RL Environment
=============================

Custom OpenAI Gym-style environment for training RL agents on APT detection.
Updated for 25-feature models + GNN integration.

State Space (13 Numerical Features):
-------------------------------------
[
    anomaly_score,              # From Autoencoder (reconstruction error)
    reconstruction_error,       # From Autoencoder (raw MSE)
    malicious_probability,      # From Beta-VAE
    uncertainty,                # From Beta-VAE (latent variance)
    predicted_next_ckc_stage,   # From Transformer (encoded 0-7)
    prediction_confidence,      # From Transformer
    current_ckc_stage,          # Current stage (encoded 0-7)
    time_since_first_event,     # Normalized time (hours)
    time_since_last_event,      # Normalized time (minutes)
    sequence_length_so_far,     # Number of events seen
    gnn_node_risk,              # GNN: risk on current host
    gnn_neighbor_risk,          # GNN: risk on connected hosts
    gnn_risk_growth,            # GNN: change in global risk
]

Action Space (Discrete 5):
---------------------------
0: Monitor, 1: Low Alert, 2: Escalate to SOC,
3: Isolate Host, 4: Block User/IP
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
import warnings

# Gym is optional — provide a fallback if not installed
try:
    import gymnasium as gym
    from gymnasium import spaces
    _GYM_BASE = gym.Env
except ImportError:
    try:
        import gym
        from gym import spaces
        _GYM_BASE = gym.Env
    except ImportError:
        # Standalone: no gym needed, define minimal shim
        class _GymSpaces:
            @staticmethod
            def Discrete(n):
                return type('Discrete', (), {'n': n, 'sample': lambda self: __import__('random').randint(0, n-1)})()
            @staticmethod
            def Box(low, high, dtype=np.float32):
                return type('Box', (), {'low': low, 'high': high, 'shape': low.shape, 'dtype': dtype})()
        spaces = _GymSpaces()
        _GYM_BASE = object


class APTEnvironment(_GYM_BASE):
    """
    OpenAI Gym environment for APT detection with RL.
    Uses 4 detection models: AE, VAE, Transformer, GNN.
    """

    metadata = {'render.modes': ['human']}

    # Action definitions
    ACTION_MONITOR = 0
    ACTION_LOW_ALERT = 1
    ACTION_ESCALATE = 2
    ACTION_ISOLATE = 3
    ACTION_BLOCK = 4

    ACTION_NAMES = {
        0: "Monitor",
        1: "Low Alert",
        2: "Escalate to SOC",
        3: "Isolate Host",
        4: "Block User/IP"
    }

    # State dimension: 10 base + 3 GNN = 13
    STATE_DIM = 13

    def __init__(
        self,
        autoencoder_loader,
        vae_loader,
        transformer_loader,
        gnn_loader=None,
        max_steps: int = 50,
        early_stop_on_intervention: bool = True,
    ):
        """
        Initialize the APT environment.

        Args:
            autoencoder_loader: Loaded AutoencoderLoader instance
            vae_loader: Loaded VAELoader instance
            transformer_loader: Loaded TransformerLoader instance
            gnn_loader: Loaded GNNLoader instance (optional, can be None)
            max_steps: Maximum steps per episode
            early_stop_on_intervention: Whether to end episode after intervention
        """
        super(APTEnvironment, self).__init__()

        # Model loaders
        self.ae_loader = autoencoder_loader
        self.vae_loader = vae_loader
        self.transformer_loader = transformer_loader
        self.gnn_loader = gnn_loader

        # Environment settings
        self.max_steps = max_steps
        self.early_stop_on_intervention = early_stop_on_intervention

        # Define action and observation space
        self.action_space = spaces.Discrete(5)

        # Observation space: 13 continuous features
        self.observation_space = spaces.Box(
            low=np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, -1], dtype=np.float32),
            high=np.array([10, 10, 1, 10, 7, 1, 7, 10, 10, 100, 1, 1, 1], dtype=np.float32),
            dtype=np.float32
        )

        # Episode state
        self.current_sequence = None
        self.current_step = 0
        self.sequence_features = None
        self.sequence_ckc_stages = None
        self.sequence_timestamps = None
        self.sequence_machines = None
        self.episode_start_time = None
        self.last_event_time = None
        self.done = False

        # History tracking
        self.state_history = []
        self.action_history = []
        self.reward_history = []

    def reset(self, sequence: Optional[Dict] = None) -> np.ndarray:
        """
        Reset environment for a new episode.

        Args:
            sequence: Dict with keys:
                'features': np.ndarray (seq_len, 55)
                'ckc_stages': list of int
                'timestamps': list of pd.Timestamp
                'machine_names': list of str

        Returns:
            Initial observation
        """
        # Reset state
        self.current_step = 0
        self.done = False
        self.state_history = []
        self.action_history = []
        self.reward_history = []

        if sequence is None:
            raise ValueError("A sequence dict must be provided to reset()")

        self.current_sequence = sequence
        self.sequence_features = sequence['features']
        self.sequence_ckc_stages = sequence['ckc_stages']

        # Handle timestamps
        if 'timestamps' in sequence and sequence['timestamps'][0] is not None:
            self.sequence_timestamps = sequence['timestamps']
        else:
            # Generate default timestamps
            from .data_loader import generate_timestamps
            self.sequence_timestamps = generate_timestamps(
                self.sequence_ckc_stages,
                campaign_mode='normal',
            )
        # Ensure timestamps are pd.Timestamp
        self.sequence_timestamps = [
            pd.Timestamp(t) if not isinstance(t, pd.Timestamp) else t
            for t in self.sequence_timestamps
        ]

        self.sequence_machines = sequence.get('machine_names',
                                              ['machine-1'] * len(self.sequence_features))

        self.episode_start_time = self.sequence_timestamps[0]
        self.last_event_time = self.episode_start_time

        # Get initial observation
        obs = self._get_observation()
        return obs

    def _get_observation(self) -> np.ndarray:
        """
        Construct observation vector from current state.
        Returns state vector of shape (13,).
        """
        if self.current_step >= len(self.sequence_features):
            return np.zeros(self.STATE_DIM, dtype=np.float32)

        # Get current event data
        current_features = self.sequence_features[self.current_step].reshape(1, -1)
        current_ckc = self.sequence_ckc_stages[self.current_step]
        current_time = self.sequence_timestamps[self.current_step]
        current_machine = self.sequence_machines[self.current_step]

        # ─── 1. Autoencoder: anomaly detection (55 features) ───
        ae_result = self.ae_loader.get_anomaly_score(current_features)
        anomaly_score = float(ae_result['anomaly_score'][0])
        reconstruction_error = float(ae_result['reconstruction_error'][0])

        # ─── 2. VAE: malicious probability (55 features) ───
        vae_result = self.vae_loader.get_malicious_probability(current_features)
        malicious_prob = float(vae_result['malicious_probability'][0])
        uncertainty = float(vae_result['uncertainty'][0])

        # ─── 3. Transformer: next stage prediction ───
        if self.current_step == 0:
            predicted_next_stage = current_ckc
            prediction_confidence = 0.5
        else:
            # Use latent vectors from AE for transformer input
            sequence_so_far = self.sequence_features[:self.current_step + 1]
            latent_sequence = self.ae_loader.encode(sequence_so_far)

            # If AE latent dim != transformer input dim (64), pad/truncate
            if latent_sequence.shape[1] < 64:
                pad = np.zeros((latent_sequence.shape[0], 64 - latent_sequence.shape[1]))
                latent_sequence = np.concatenate([latent_sequence, pad], axis=1)
            elif latent_sequence.shape[1] > 64:
                latent_sequence = latent_sequence[:, :64]

            trans_result = self.transformer_loader.predict_next_stage(latent_sequence)
            predicted_next_stage = int(trans_result['predicted_next_ckc_stage'])
            prediction_confidence = float(trans_result['prediction_confidence'])

        # ─── 4. Temporal features ───
        time_since_first = (current_time - self.episode_start_time).total_seconds()
        time_since_last = (current_time - self.last_event_time).total_seconds() if self.current_step > 0 else 0

        # ─── 5. GNN features ───
        if self.gnn_loader is not None and self.gnn_loader.enabled and self.gnn_loader.df_rl is not None:
            gnn_features = self.gnn_loader.get_rl_state_features(
                target_machine=current_machine,
                current_time=current_time,
            )
        else:
            gnn_features = {
                "GNN_node_risk_current_host": 0.0,
                "GNN_neighbor_risk": 0.0,
                "risk_growth": 0.0,
            }

        # ─── Construct observation vector (13 dims) ───
        obs = np.array([
            anomaly_score,
            reconstruction_error,
            malicious_prob,
            uncertainty,
            predicted_next_stage,
            prediction_confidence,
            current_ckc,
            time_since_first / 3600.0,          # Normalize to hours
            time_since_last / 60.0,             # Normalize to minutes
            self.current_step,
            gnn_features["GNN_node_risk_current_host"],
            gnn_features["GNN_neighbor_risk"],
            gnn_features["risk_growth"],
        ], dtype=np.float32)

        # Clip to observation space bounds
        obs = np.clip(obs, self.observation_space.low, self.observation_space.high)
        return obs

    def _calculate_reward(self, action: int) -> float:
        """
        Calculate reward for the current action.

        Reward structure STRONGLY prioritizes early detection:
        - Pre-detection (S1-S4): Very high reward for intervention
        - Post-detection (S5+): Low or negative reward (too late)
        - Monitoring malicious at S4+: Progressive penalties
        - False positives: Moderate penalty
        - Missed attacks at end: Large penalty
        """
        current_ckc = self.sequence_ckc_stages[self.current_step]
        is_malicious = current_ckc > 0
        is_intervention = action >= self.ACTION_ESCALATE  # Only Escalate/Isolate/Block count

        reward = 0.0

        if is_intervention:
            if is_malicious:
                # ─── Correct intervention: reward based on HOW EARLY ───
                if current_ckc <= 2:
                    reward = 15.0   # S1-S2: Excellent early catch
                elif current_ckc <= 3:
                    reward = 10.0   # S3: Good early catch (Delivery)
                elif current_ckc == 4:
                    reward = 7.0    # S4: Caught at exploitation
                elif current_ckc == 5:
                    reward = 3.0    # S5: Caught at installation (borderline)
                elif current_ckc == 6:
                    reward = 0.0    # S6: Too late (C2 established)
                else:
                    reward = -2.0   # S7: Way too late (damage done)

                # Bonus for strong action when warranted (S4+)
                if action >= self.ACTION_ISOLATE and current_ckc >= 4:
                    reward += 2.0
            else:
                # False positive: intervened on benign event
                reward = -2.0
                if action >= self.ACTION_ISOLATE:
                    reward -= 1.0  # Harsher for aggressive false positive

        elif action == self.ACTION_LOW_ALERT:
            # Low alert: small reward for flagging malicious, small penalty for benign
            if is_malicious:
                reward = 1.0   # Good: noticed something
            else:
                reward = -0.5  # Minor nuisance alert

        else:
            # Monitoring (action == 0)
            if is_malicious:
                # Progressive penalty for monitoring malicious events
                if current_ckc >= 6:
                    reward = -8.0   # S6-S7: Critical failure to act
                elif current_ckc >= 5:
                    reward = -5.0   # S5: Should have intervened
                elif current_ckc >= 4:
                    reward = -3.0   # S4: Should be alarming
                elif current_ckc >= 3:
                    reward = -1.0   # S3: Getting suspicious
                else:
                    reward = 0.0    # S1-S2: OK to monitor early recon
            else:
                reward = 0.0       # Correctly monitoring benign

        # End-of-episode penalty for letting attack complete without intervention
        if self.current_step == len(self.sequence_features) - 1:
            was_intervened = any(a >= self.ACTION_ESCALATE for a in self.action_history)
            if is_malicious and not was_intervened:
                reward -= 15.0  # Large penalty for complete miss

        return reward

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, Dict]:
        """
        Execute one step.

        Returns: (observation, reward, done, info)
        """
        if self.done:
            warnings.warn("Episode already done. Call reset().")
            return self._get_observation(), 0.0, True, {}

        # Calculate reward
        reward = self._calculate_reward(action)

        # Record history
        self.state_history.append(self._get_observation())
        self.action_history.append(action)
        self.reward_history.append(reward)

        # Update time tracking
        if self.current_step == 0:
            self.episode_start_time = self.sequence_timestamps[0]
        self.last_event_time = self.sequence_timestamps[self.current_step]

        # Move to next step
        self.current_step += 1

        # Check termination
        done = False
        if self.current_step >= len(self.sequence_features):
            done = True
        elif self.early_stop_on_intervention and action >= self.ACTION_ESCALATE:
            done = True
        elif self.current_step >= self.max_steps:
            done = True

        self.done = done

        # Next observation
        obs = self._get_observation() if not done else np.zeros(self.STATE_DIM, dtype=np.float32)

        info = {
            'current_ckc_stage': self.sequence_ckc_stages[min(self.current_step, len(self.sequence_ckc_stages) - 1)],
            'action_taken': self.ACTION_NAMES[action],
            'sequence_length': len(self.sequence_features),
            'total_reward': sum(self.reward_history),
        }

        return obs, reward, done, info

    def render(self, mode='human'):
        """Render the environment state."""
        if mode == 'human':
            print("\n" + "=" * 60)
            print(f"APT Environment - Step {self.current_step}/{len(self.sequence_features)}")
            print("=" * 60)

            if self.current_step > 0:
                current_ckc = self.sequence_ckc_stages[self.current_step - 1]
                last_action = self.action_history[-1] if self.action_history else None
                last_reward = self.reward_history[-1] if self.reward_history else 0

                print(f"Current CKC Stage: S{current_ckc}")
                print(f"Last Action: {self.ACTION_NAMES.get(last_action, 'None')}")
                print(f"Last Reward: {last_reward:.2f}")
                print(f"Total Reward: {sum(self.reward_history):.2f}")

            print("=" * 60)

    def get_episode_summary(self) -> Dict:
        """Get summary statistics for the completed episode."""
        return {
            'total_steps': len(self.action_history),
            'total_reward': sum(self.reward_history),
            'actions_taken': self.action_history,
            'action_distribution': {
                name: self.action_history.count(i)
                for i, name in self.ACTION_NAMES.items()
            },
            'ckc_stages_seen': self.sequence_ckc_stages,
            'early_detection': any(
                action >= self.ACTION_ESCALATE and self.sequence_ckc_stages[i] <= 3
                for i, action in enumerate(self.action_history)
            ) if self.action_history else False,
        }


# Example usage
if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("APT ENVIRONMENT - TEST")
    print("=" * 70)

    print("\n[OK] Environment class defined successfully")
    print(f"   Action space: Discrete(5)")
    print(f"   Observation space: Box({APTEnvironment.STATE_DIM},)")
    print(f"   Actions: {APTEnvironment.ACTION_NAMES}")
