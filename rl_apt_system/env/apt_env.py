"""
APT Detection RL Environment
=============================

Custom OpenAI Gym-style environment for training RL agents on APT detection.

Environment Dynamics:
---------------------
- One episode = one attack sequence (real or synthetic)
- Each step = one event in the sequence
- Agent observes detection signals and chooses defensive action
- Reward encourages early detection and penalizes false positives/negatives

State Space (Numerical Vector):
--------------------------------
[
    anomaly_score,              # From Autoencoder
    reconstruction_error,       # From Autoencoder
    malicious_probability,      # From VAE
    uncertainty,                # From VAE
    predicted_next_ckc_stage,   # From Transformer (encoded 0-6)
    prediction_confidence,      # From Transformer
    current_ckc_stage,          # Current stage (encoded 0-6)
    time_since_first_event,     # Normalized time
    time_since_last_event,      # Normalized time
    sequence_length_so_far,     # Number of events seen
]

Action Space (Discrete):
------------------------
0: Monitor          - Continue observation, no intervention
1: Low Alert        - Log suspicious activity
2: Escalate to SOC  - Notify security team
3: Isolate Host     - Disconnect affected system
4: Block User/IP    - Block network access

Reward Function:
----------------
Designed to prioritize early detection:
- Correct response at S1-S3: +5  (early stages)
- Correct response at S4-S5: +2  (mid stages)
- Correct response at S7: 0      (too late)
- False negative: -10            (missed attack)
- False positive: -1             (alert fatigue)
- Overreaction: -2               (too aggressive too early)
"""

import numpy as np
try:
    import gymnasium as gym
    from gymnasium import spaces
except ImportError:
    import gym
    from gym import spaces
from typing import Dict, List, Tuple, Optional
import warnings


class APTEnvironment(gym.Env):
    """
    OpenAI Gym environment for APT detection with RL.
    
    Simulates the evolution of an APT attack through CKC stages,
    with the agent making defensive decisions at each step.
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
    
    def __init__(
        self,
        autoencoder_loader,
        vae_loader,
        transformer_loader,
        conditional_replay,
        max_steps: int = 50,
        early_stop_on_intervention: bool = True
    ):
        """
        Initialize the APT environment.
        
        Args:
            autoencoder_loader: Loaded Autoencoder model
            vae_loader: Loaded VAE model
            transformer_loader: Loaded Transformer model
            conditional_replay: ConditionalReplay instance for feature generation
            max_steps: Maximum steps per episode
            early_stop_on_intervention: Whether to end episode after intervention action
        """
        super(APTEnvironment, self).__init__()
        
        # Model loaders
        self.ae_loader = autoencoder_loader
        self.vae_loader = vae_loader
        self.transformer_loader = transformer_loader
        self.conditional_replay = conditional_replay
        
        # Environment settings
        self.max_steps = max_steps
        self.early_stop_on_intervention = early_stop_on_intervention
        
        # Define action and observation space
        # Action space: 5 discrete actions
        self.action_space = spaces.Discrete(5)
        
        # Observation space: 10 continuous features
        # All normalized to roughly [0, 10] range
        self.observation_space = spaces.Box(
            low=np.array([0, 0, 0, 0, 0, 0, 0, 0, 0, 0], dtype=np.float32),
            high=np.array([10, 10, 1, 10, 6, 1, 6, 10, 10, 100], dtype=np.float32),
            dtype=np.float32
        )
        
        # Episode state
        self.current_sequence = None
        self.current_step = 0
        self.sequence_features = None
        self.sequence_ckc_stages = None
        self.sequence_time_deltas = None
        self.episode_start_time = 0
        self.last_event_time = 0
        self.done = False
        
        # History tracking
        self.state_history = []
        self.action_history = []
        self.reward_history = []
    
    def reset(self, sequence: Optional[List[Dict]] = None) -> np.ndarray:
        """
        Reset environment for a new episode.
        
        Args:
            sequence: Optional meta-sequence to use (if None, generates random)
        
        Returns:
            Initial observation
        """
        # Reset state
        self.current_step = 0
        self.episode_start_time = 0
        self.last_event_time = 0
        self.done = False
        self.state_history = []
        self.action_history = []
        self.reward_history = []
        
        # Load sequence
        if sequence is None:
            # Generate random sequence if none provided
            from ..synthetic.meta_sequence_generator import MetaSequenceGenerator
            gen = MetaSequenceGenerator(use_simple_generation=True)
            sequences = gen.generate_meta_sequences(num_sequences=1, min_length=5, max_length=20)
            sequence = sequences[0]
        
        self.current_sequence = sequence
        
        # Replay sequence to get full features
        self.sequence_features, _ = self.conditional_replay.replay_meta_sequence(sequence)
        
        # Extract CKC stages and time deltas
        self.sequence_ckc_stages = [event['ckc_stage'] for event in sequence]
        self.sequence_time_deltas = [event.get('cumulative_time', 0) for event in sequence]
        
        # Get initial observation
        obs = self._get_observation()
        
        return obs
    
    def _get_observation(self) -> np.ndarray:
        """
        Construct observation vector from current state.
        
        Returns:
            State vector of shape (10,)
        """
        if self.current_step >= len(self.sequence_features):
            # Return zeros if beyond sequence
            return np.zeros(10, dtype=np.float32)
        
        # Get current event features
        current_features = self.sequence_features[self.current_step].reshape(1, -1)
        current_ckc_stage = self.sequence_ckc_stages[self.current_step]
        current_time = self.sequence_time_deltas[self.current_step]
        
        # Get detection signals from models
        # 1. Autoencoder: anomaly detection (expects 313 features)
        ae_result = self.ae_loader.get_anomaly_score(current_features)
        anomaly_score = float(ae_result['anomaly_score'][0])
        reconstruction_error = float(ae_result['reconstruction_error'][0])
        
        # 2. VAE: malicious probability (expects 191 features)
        # Truncate features to match VAE input dimension
        vae_features = current_features[:, :191]
        vae_result = self.vae_loader.get_malicious_probability(vae_features)
        malicious_prob = float(vae_result['malicious_probability'][0])
        uncertainty = float(vae_result['uncertainty'][0])
        
        # 3. Transformer: next stage prediction
        # Need sequence up to current step
        if self.current_step == 0:
            # First event: no history
            predicted_next_stage = current_ckc_stage  # Default
            prediction_confidence = 0.5
        else:
            # Use latent vectors from AE for transformer input
            sequence_so_far = self.sequence_features[:self.current_step + 1]
            
            # Use autoencoder to encode
            latent_sequence = self.ae_loader.encode(sequence_so_far)
            
            # Predict next stage
            trans_result = self.transformer_loader.predict_next_stage(latent_sequence)
            predicted_next_stage = int(trans_result['predicted_next_ckc_stage'])
            prediction_confidence = float(trans_result['prediction_confidence'])
        
        # Temporal features
        time_since_first = current_time - self.episode_start_time
        time_since_last = current_time - self.last_event_time if self.current_step > 0 else 0
        
        # Construct observation vector
        obs = np.array([
            anomaly_score,
            reconstruction_error,
            malicious_prob,
            uncertainty,
            predicted_next_stage - 1,  # Convert to 0-indexed
            prediction_confidence,
            current_ckc_stage - 1,      # Convert to 0-indexed
            time_since_first / 3600.0,  # Normalize to hours
            time_since_last / 60.0,     # Normalize to minutes
            self.current_step
        ], dtype=np.float32)
        
        # Clip to observation space bounds
        obs = np.clip(obs, self.observation_space.low, self.observation_space.high)
        
        return obs
    
    def _calculate_reward(self, action: int) -> float:
        """
        Calculate reward for the current action.
        
        Reward structure prioritizes early detection:
        - Early intervention (S1-S3): High reward if correct
        - Mid intervention (S4-S5): Medium reward if correct
        - Late intervention (S6-S7): Low/no reward
        - False positives: Small penalty
        - Missed attacks: Large penalty
        
        Args:
            action: Action taken by agent
        
        Returns:
            Reward value
        """
        current_ckc = self.sequence_ckc_stages[self.current_step]
        
        # Determine if this is an "attack" event (malicious)
        # For simplicity, we consider all CKC stages as malicious
        is_malicious = True
        
        # Determine if action is an intervention (not just monitoring)
        is_intervention = action >= self.ACTION_LOW_ALERT
        
        # Base reward calculation
        reward = 0.0
        
        if is_intervention:
            if is_malicious:
                # Correct intervention on malicious event
                # Reward based on CKC stage (earlier = better)
                if current_ckc <= 3:
                    # Early stages: high reward
                    reward = 5.0
                elif current_ckc <= 5:
                    # Mid stages: medium reward
                    reward = 2.0
                else:
                    # Late stages: low reward (too late)
                    reward = 0.0
                
                # Bonus for more aggressive action when warranted
                if action >= self.ACTION_ISOLATE and current_ckc >= 5:
                    reward += 1.0
                
                # Penalty for overreaction in early stages
                if action >= self.ACTION_ISOLATE and current_ckc <= 2:
                    reward -= 2.0
            
            else:
                # False positive: intervened on benign event
                reward = -1.0
                
                # Heavier penalty for aggressive false positives
                if action >= self.ACTION_ISOLATE:
                    reward -= 1.0
        
        else:
            # Monitoring action
            if is_malicious and current_ckc >= 6:
                # Should have intervened by now (late stage)
                reward = -5.0  # Missed attack penalty
            else:
                # Monitoring is acceptable in early stages
                reward = 0.0
        
        # End-of-episode penalty for letting attack complete
        if self.current_step == len(self.sequence_features) - 1 and not is_intervention:
            # Reached end without intervention
            reward -= 10.0  # Large penalty for complete miss
        
        return reward
    
    def step(self, action: int) -> Tuple[np.ndarray, float, bool, Dict]:
        """
        Execute one step in the environment.
        
        Args:
            action: Action to take
        
        Returns:
            Tuple of (observation, reward, done, info)
        """
        if self.done:
            warnings.warn("Episode already done. Call reset() to start new episode.")
            return self._get_observation(), 0.0, True, {}
        
        # Calculate reward
        reward = self._calculate_reward(action)
        
        # Record history
        self.state_history.append(self._get_observation())
        self.action_history.append(action)
        self.reward_history.append(reward)
        
        # Update time tracking
        if self.current_step == 0:
            self.episode_start_time = self.sequence_time_deltas[0]
        self.last_event_time = self.sequence_time_deltas[self.current_step]
        
        # Move to next step
        self.current_step += 1
        
        # Check if episode is done
        done = False
        
        if self.current_step >= len(self.sequence_features):
            # Reached end of sequence
            done = True
        
        elif self.early_stop_on_intervention and action >= self.ACTION_ESCALATE:
            # Significant intervention taken, episode ends
            done = True
        
        elif self.current_step >= self.max_steps:
            # Max steps reached
            done = True
        
        self.done = done
        
        # Get next observation (if not done)
        obs = self._get_observation() if not done else np.zeros(10, dtype=np.float32)
        
        # Info dict
        info = {
            'current_ckc_stage': self.sequence_ckc_stages[min(self.current_step, len(self.sequence_ckc_stages) - 1)],
            'action_taken': self.ACTION_NAMES[action],
            'sequence_length': len(self.sequence_features),
            'total_reward': sum(self.reward_history)
        }
        
        return obs, reward, done, info
    
    def render(self, mode='human'):
        """Render the environment state."""
        if mode == 'human':
            print("\n" + "="*60)
            print(f"APT Environment - Step {self.current_step}/{len(self.sequence_features)}")
            print("="*60)
            
            if self.current_step > 0:
                current_ckc = self.sequence_ckc_stages[self.current_step - 1]
                last_action = self.action_history[-1] if self.action_history else None
                last_reward = self.reward_history[-1] if self.reward_history else 0
                
                print(f"Current CKC Stage: S{current_ckc}")
                print(f"Last Action: {self.ACTION_NAMES.get(last_action, 'None')}")
                print(f"Last Reward: {last_reward:.2f}")
                print(f"Total Reward: {sum(self.reward_history):.2f}")
            
            print("="*60)
    
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
            ) if self.action_history else False
        }


# Example usage and testing
if __name__ == "__main__":
    print("\n" + "="*70)
    print("APT ENVIRONMENT - TEST")
    print("="*70)
    
    print("\n[WARNING] Note: This test requires loaded models and data.")
    print("   Run from main training script with initialized models.")
    
    # Placeholder test structure
    print("\n[OK] Environment class defined successfully")
    print("   Action space: Discrete(5)")
    print("   Observation space: Box(10,)")
    print(f"   Actions: {APTEnvironment.ACTION_NAMES}")
