"""
DQN Agent for APT Detection
============================

Deep Q-Network (DQN) implementation for learning optimal defensive actions
against APT attacks.

Algorithm: DQN with Experience Replay and Target Network
---------------------------------------------------------
1. Q-Network: Neural network that approximates Q(s,a) - expected future reward
2. Experience Replay: Store transitions, sample mini-batches for training
3. Target Network: Separate network for stable Q-value targets
4. Epsilon-Greedy: Balance exploration vs exploitation

Network Architecture:
---------------------
Input: State vector (10 features)
Hidden layers: Fully connected with ReLU activation
Output: Q-values for each action (5 actions)

Training Process:
-----------------
1. Observe state s_t
2. Choose action a_t (epsilon-greedy)
3. Execute action, observe reward r_t and next state s_{t+1}
4. Store transition (s_t, a_t, r_t, s_{t+1}, done) in replay buffer
5. Sample mini-batch from replay buffer
6. Compute target: r + gamma * max_a' Q_target(s', a')
7. Update Q-network to minimize TD-error
8. Periodically update target network

Hyperparameters:
----------------
- gamma: Discount factor (0.99)
- epsilon: Exploration rate (1.0 → 0.01)
- learning_rate: Adam optimizer learning rate (1e-4)
- batch_size: Mini-batch size (64)
- buffer_size: Replay buffer capacity (10000)
- target_update_freq: Update target network every N steps
"""

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
from collections import deque, namedtuple
import random
from typing import Tuple, List, Optional


# Transition tuple for experience replay
Transition = namedtuple('Transition', ('state', 'action', 'reward', 'next_state', 'done'))


class QNetwork(nn.Module):
    """
    Q-Network for DQN.
    
    Approximates Q(s,a) for all actions given state s.
    """
    
    def __init__(self, state_dim: int, action_dim: int, hidden_dims: List[int] = [128, 64]):
        """
        Initialize Q-Network.
        
        Args:
            state_dim: Dimension of state space
            action_dim: Dimension of action space (number of discrete actions)
            hidden_dims: List of hidden layer dimensions
        """
        super(QNetwork, self).__init__()
        
        self.state_dim = state_dim
        self.action_dim = action_dim
        
        # Build network layers
        layers = []
        input_dim = state_dim
        
        for hidden_dim in hidden_dims:
            layers.append(nn.Linear(input_dim, hidden_dim))
            layers.append(nn.ReLU())
            layers.append(nn.Dropout(0.1))
            input_dim = hidden_dim
        
        # Output layer
        layers.append(nn.Linear(input_dim, action_dim))
        
        self.network = nn.Sequential(*layers)
    
    def forward(self, state: torch.Tensor) -> torch.Tensor:
        """
        Forward pass: compute Q-values for all actions.
        
        Args:
            state: State tensor of shape (batch_size, state_dim) or (state_dim,)
        
        Returns:
            Q-values of shape (batch_size, action_dim) or (action_dim,)
        """
        return self.network(state)


class ReplayBuffer:
    """
    Experience replay buffer for DQN.
    
    Stores transitions and provides random sampling for training.
    """
    
    def __init__(self, capacity: int):
        """
        Initialize replay buffer.
        
        Args:
            capacity: Maximum number of transitions to store
        """
        self.buffer = deque(maxlen=capacity)
    
    def push(self, state, action, reward, next_state, done):
        """Add a transition to the buffer."""
        self.buffer.append(Transition(state, action, reward, next_state, done))
    
    def sample(self, batch_size: int) -> List[Transition]:
        """Sample a random batch of transitions."""
        return random.sample(self.buffer, batch_size)
    
    def __len__(self):
        """Return current size of buffer."""
        return len(self.buffer)


class DQNAgent:
    """
    DQN agent for APT detection and response.
    
    Learns optimal defensive actions through interaction with environment.
    """
    
    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_dims: List[int] = [128, 64],
        learning_rate: float = 1e-4,
        gamma: float = 0.99,
        epsilon_start: float = 1.0,
        epsilon_end: float = 0.01,
        epsilon_decay: float = 0.995,
        buffer_size: int = 10000,
        batch_size: int = 64,
        target_update_freq: int = 100,
        device: str = 'cpu'
    ):
        """
        Initialize DQN agent.
        
        Args:
            state_dim: Dimension of state space
            action_dim: Number of discrete actions
            hidden_dims: Hidden layer dimensions for Q-network
            learning_rate: Learning rate for optimizer
            gamma: Discount factor
            epsilon_start: Initial exploration rate
            epsilon_end: Minimum exploration rate
            epsilon_decay: Epsilon decay rate per episode
            buffer_size: Replay buffer capacity
            batch_size: Mini-batch size for training
            target_update_freq: Update target network every N steps
            device: Device to use ('cpu' or 'cuda')
        """
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.gamma = gamma
        self.epsilon = epsilon_start
        self.epsilon_end = epsilon_end
        self.epsilon_decay = epsilon_decay
        self.batch_size = batch_size
        self.target_update_freq = target_update_freq
        self.device = torch.device(device)
        
        # Q-networks
        self.q_network = QNetwork(state_dim, action_dim, hidden_dims).to(self.device)
        self.target_network = QNetwork(state_dim, action_dim, hidden_dims).to(self.device)
        self.target_network.load_state_dict(self.q_network.state_dict())
        self.target_network.eval()
        
        # Optimizer
        self.optimizer = optim.Adam(self.q_network.parameters(), lr=learning_rate)
        
        # Replay buffer
        self.replay_buffer = ReplayBuffer(buffer_size)
        
        # Training stats
        self.steps_done = 0
        self.episodes_done = 0
        self.losses = []
        
        print(f"[OK] DQN Agent initialized")
        print(f"   State dim: {state_dim}, Action dim: {action_dim}")
        print(f"   Hidden dims: {hidden_dims}")
        print(f"   Device: {self.device}")
    
    def select_action(self, state: np.ndarray, training: bool = True) -> int:
        """
        Select action using epsilon-greedy policy.
        
        Args:
            state: Current state
            training: If True, use epsilon-greedy; if False, use greedy
        
        Returns:
            Selected action (integer)
        """
        if training and random.random() < self.epsilon:
            # Explore: random action
            return random.randrange(self.action_dim)
        else:
            # Exploit: best action according to Q-network
            with torch.no_grad():
                state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
                q_values = self.q_network(state_tensor)
                return q_values.argmax(dim=1).item()
    
    def store_transition(self, state, action, reward, next_state, done):
        """Store transition in replay buffer."""
        self.replay_buffer.push(state, action, reward, next_state, done)
    
    def train_step(self) -> Optional[float]:
        """
        Perform one training step (if enough samples in buffer).
        
        Returns:
            Loss value if training occurred, None otherwise
        """
        if len(self.replay_buffer) < self.batch_size:
            return None
        
        # Sample batch from replay buffer
        transitions = self.replay_buffer.sample(self.batch_size)
        batch = Transition(*zip(*transitions))
        
        # Convert to tensors
        state_batch = torch.FloatTensor(np.array(batch.state)).to(self.device)
        action_batch = torch.LongTensor(batch.action).unsqueeze(1).to(self.device)
        reward_batch = torch.FloatTensor(batch.reward).unsqueeze(1).to(self.device)
        next_state_batch = torch.FloatTensor(np.array(batch.next_state)).to(self.device)
        done_batch = torch.FloatTensor(batch.done).unsqueeze(1).to(self.device)
        
        # Compute current Q-values
        current_q_values = self.q_network(state_batch).gather(1, action_batch)
        
        # Compute target Q-values
        with torch.no_grad():
            next_q_values = self.target_network(next_state_batch).max(1)[0].unsqueeze(1)
            target_q_values = reward_batch + (1 - done_batch) * self.gamma * next_q_values
        
        # Compute loss
        loss = F.mse_loss(current_q_values, target_q_values)
        
        # Optimize
        self.optimizer.zero_grad()
        loss.backward()
        # Clip gradients
        torch.nn.utils.clip_grad_norm_(self.q_network.parameters(), max_norm=1.0)
        self.optimizer.step()
        
        # Update target network
        self.steps_done += 1
        if self.steps_done % self.target_update_freq == 0:
            self.target_network.load_state_dict(self.q_network.state_dict())
        
        # Record loss
        loss_value = loss.item()
        self.losses.append(loss_value)
        
        return loss_value
    
    def update_epsilon(self):
        """Decay epsilon after each episode."""
        self.epsilon = max(self.epsilon_end, self.epsilon * self.epsilon_decay)
        self.episodes_done += 1
    
    def save(self, path: str):
        """
        Save agent state.
        
        Args:
            path: Path to save checkpoint
        """
        checkpoint = {
            'q_network_state_dict': self.q_network.state_dict(),
            'target_network_state_dict': self.target_network.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'epsilon': self.epsilon,
            'steps_done': self.steps_done,
            'episodes_done': self.episodes_done,
            'hyperparameters': {
                'state_dim': self.state_dim,
                'action_dim': self.action_dim,
                'gamma': self.gamma,
                'batch_size': self.batch_size,
                'target_update_freq': self.target_update_freq
            }
        }
        torch.save(checkpoint, path)
        print(f"[OK] Agent saved to {path}")
    
    def load(self, path: str):
        """
        Load agent state.
        
        Args:
            path: Path to checkpoint file
        """
        checkpoint = torch.load(path, map_location=self.device, weights_only=False)
        
        self.q_network.load_state_dict(checkpoint['q_network_state_dict'])
        self.target_network.load_state_dict(checkpoint['target_network_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        self.epsilon = checkpoint['epsilon']
        self.steps_done = checkpoint['steps_done']
        self.episodes_done = checkpoint['episodes_done']
        
        print(f"[OK] Agent loaded from {path}")
        print(f"   Episodes: {self.episodes_done}, Steps: {self.steps_done}")
        print(f"   Epsilon: {self.epsilon:.4f}")
    
    def get_q_values(self, state: np.ndarray) -> np.ndarray:
        """
        Get Q-values for all actions in a given state.
        
        Args:
            state: State vector
        
        Returns:
            Q-values for all actions
        """
        with torch.no_grad():
            state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            q_values = self.q_network(state_tensor)
            return q_values.cpu().numpy()[0]
    
    def get_training_stats(self) -> dict:
        """Get training statistics."""
        return {
            'episodes_done': self.episodes_done,
            'steps_done': self.steps_done,
            'epsilon': self.epsilon,
            'buffer_size': len(self.replay_buffer),
            'avg_loss_last_100': np.mean(self.losses[-100:]) if self.losses else 0,
            'total_losses_recorded': len(self.losses)
        }


# Example usage and testing
if __name__ == "__main__":
    print("\n" + "="*70)
    print("DQN AGENT - TEST")
    print("="*70)
    
    # Initialize agent
    state_dim = 10  # APT environment state dimension
    action_dim = 5  # 5 defensive actions
    
    agent = DQNAgent(
        state_dim=state_dim,
        action_dim=action_dim,
        hidden_dims=[128, 64],
        learning_rate=1e-4,
        device='cpu'
    )
    
    # Test action selection
    print("\n🧪 Testing action selection...")
    test_state = np.random.randn(state_dim).astype(np.float32)
    
    print(f"   Test state: {test_state}")
    action = agent.select_action(test_state, training=True)
    print(f"   Selected action (epsilon-greedy): {action}")
    
    q_values = agent.get_q_values(test_state)
    print(f"   Q-values: {q_values}")
    
    # Test experience replay
    print("\n🧪 Testing experience replay...")
    for i in range(10):
        state = np.random.randn(state_dim).astype(np.float32)
        action = random.randint(0, action_dim - 1)
        reward = random.uniform(-1, 1)
        next_state = np.random.randn(state_dim).astype(np.float32)
        done = False
        
        agent.store_transition(state, action, reward, next_state, done)
    
    print(f"   Buffer size: {len(agent.replay_buffer)}")
    
    # Test training
    print("\n🧪 Testing training step...")
    # Add more transitions to reach batch size
    for i in range(agent.batch_size):
        state = np.random.randn(state_dim).astype(np.float32)
        action = random.randint(0, action_dim - 1)
        reward = random.uniform(-1, 1)
        next_state = np.random.randn(state_dim).astype(np.float32)
        done = random.random() < 0.1
        
        agent.store_transition(state, action, reward, next_state, done)
    
    loss = agent.train_step()
    print(f"   Training loss: {loss:.4f}")
    
    # Test save/load
    print("\n🧪 Testing save/load...")
    import tempfile
    import os
    
    with tempfile.TemporaryDirectory() as tmpdir:
        save_path = os.path.join(tmpdir, "test_agent.pth")
        agent.save(save_path)
        
        # Create new agent and load
        new_agent = DQNAgent(state_dim=state_dim, action_dim=action_dim, device='cpu')
        new_agent.load(save_path)
    
    print("\n[OK] All tests passed!")
