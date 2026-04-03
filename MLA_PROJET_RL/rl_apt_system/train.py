"""
Training Script for RL-based APT Detection System
==================================================

This script trains a DQN agent to make optimal defensive decisions
against APT attacks using pre-trained detection models and synthetic
meta-sequences with conditional replay.

Training Process:
-----------------
1. Load pre-trained models (AE, VAE, Transformer)
2. Load real SIEM data for conditional replay
3. Generate synthetic meta-sequences (or use real sequences)
4. Initialize RL environment and DQN agent
5. Train agent through episodes:
   - Reset environment with new sequence
   - Agent observes state and selects action
   - Environment computes reward
   - Agent stores transition and trains
6. Save trained agent and training metrics

Usage:
------
python train.py --data_path path/to/data.xlsx --num_episodes 1000 --device cuda
"""

import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
import json
import time
from datetime import datetime
from tqdm import tqdm

import torch

# Import project modules
import sys
sys.path.append(str(Path(__file__).parent))

from models.autoencoder_loader import AutoencoderLoader
from models.vae_loader import VAELoader
from models.transformer_loader import TransformerLoader
from synthetic.meta_sequence_generator import MetaSequenceGenerator
from synthetic.conditional_replay import ConditionalReplay
from env.apt_env import APTEnvironment
from rl.dqn_agent import DQNAgent


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Train RL agent for APT detection')
    
    # Data paths
    parser.add_argument('--data_path', type=str, default='../combined_dataset_final.xlsx',
                        help='Path to real SIEM data')
    parser.add_argument('--ae_model', type=str, default='../autoencoder_outputs/autoencoder_anomaly_detection.pth',
                        help='Path to Autoencoder model')
    parser.add_argument('--vae_model', type=str, default='../vae_anomaly_detector_outputs/vae_anomaly_detector.pth',
                        help='Path to VAE model')
    parser.add_argument('--transformer_model', type=str, default='../transformer_outputs/transformer_next_step_prediction.pth',
                        help='Path to Transformer model')
    
    # Training parameters
    parser.add_argument('--num_episodes', type=int, default=500,
                        help='Number of training episodes')
    parser.add_argument('--max_steps', type=int, default=50,
                        help='Maximum steps per episode')
    parser.add_argument('--batch_size', type=int, default=64,
                        help='Batch size for DQN training')
    parser.add_argument('--learning_rate', type=float, default=1e-4,
                        help='Learning rate')
    parser.add_argument('--gamma', type=float, default=0.99,
                        help='Discount factor')
    parser.add_argument('--epsilon_start', type=float, default=1.0,
                        help='Initial exploration rate')
    parser.add_argument('--epsilon_end', type=float, default=0.01,
                        help='Final exploration rate')
    parser.add_argument('--epsilon_decay', type=float, default=0.995,
                        help='Epsilon decay rate per episode')
    
    # Synthetic data generation
    parser.add_argument('--num_synthetic', type=int, default=100,
                        help='Number of synthetic sequences to generate')
    parser.add_argument('--use_real_sequences', action='store_true',
                        help='Use real sequences instead of synthetic')
    
    # Output
    parser.add_argument('--output_dir', type=str, default='./outputs',
                        help='Directory to save outputs')
    parser.add_argument('--save_freq', type=int, default=50,
                        help='Save model every N episodes')
    
    # Device
    parser.add_argument('--device', type=str, default='cpu',
                        help='Device to use (cpu or cuda)')
    
    return parser.parse_args()


def load_models(args):
    """Load pre-trained detection models."""
    print("\n" + "="*70)
    print("LOADING PRE-TRAINED MODELS")
    print("="*70)
    
    # Load Autoencoder
    print("\n[1] Loading Autoencoder...")
    ae_loader = AutoencoderLoader(args.ae_model, device=args.device)
    
    # Load VAE
    print("\n[2] Loading VAE...")
    vae_loader = VAELoader(args.vae_model, device=args.device)
    
    # Load Transformer
    print("\n[3] Loading Transformer...")
    transformer_loader = TransformerLoader(args.transformer_model, device=args.device)
    
    return ae_loader, vae_loader, transformer_loader


def generate_training_sequences(args):
    """Generate or load training sequences."""
    print("\n" + "="*70)
    print("GENERATING TRAINING SEQUENCES")
    print("="*70)
    
    generator = MetaSequenceGenerator(
        use_simple_generation=True,
        real_data_path=args.data_path
    )
    
    sequences = generator.generate_meta_sequences(
        num_sequences=args.num_synthetic,
        min_length=5,
        max_length=20
    )
    
    generator.print_sequence_statistics(sequences)
    
    return sequences


def train_episode(env, agent, sequence):
    """Train for one episode."""
    state = env.reset(sequence)
    episode_reward = 0
    episode_loss = []
    
    done = False
    while not done:
        # Select action
        action = agent.select_action(state, training=True)
        
        # Execute action
        next_state, reward, done, info = env.step(action)
        
        # Store transition
        agent.store_transition(state, action, reward, next_state, done)
        
        # Train agent
        loss = agent.train_step()
        if loss is not None:
            episode_loss.append(loss)
        
        # Update state
        state = next_state
        episode_reward += reward
    
    # Update epsilon
    agent.update_epsilon()
    
    return episode_reward, episode_loss, env.get_episode_summary()


def plot_training_curves(rewards, losses, output_dir):
    """Plot and save training curves."""
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))
    
    # Rewards
    axes[0].plot(rewards, alpha=0.6, label='Episode Reward')
    # Moving average
    if len(rewards) >= 10:
        window = min(50, len(rewards) // 10)
        moving_avg = pd.Series(rewards).rolling(window=window, min_periods=1).mean()
        axes[0].plot(moving_avg, 'r-', linewidth=2, label=f'Moving Avg ({window})')
    axes[0].set_xlabel('Episode')
    axes[0].set_ylabel('Total Reward')
    axes[0].set_title('Training Rewards')
    axes[0].legend()
    axes[0].grid(True, alpha=0.3)
    
    # Losses
    if losses:
        axes[1].plot(losses, alpha=0.6)
        if len(losses) >= 10:
            window = min(100, len(losses) // 10)
            moving_avg = pd.Series(losses).rolling(window=window, min_periods=1).mean()
            axes[1].plot(moving_avg, 'r-', linewidth=2, label=f'Moving Avg ({window})')
        axes[1].set_xlabel('Training Step')
        axes[1].set_ylabel('Loss')
        axes[1].set_title('Training Loss')
        axes[1].legend()
        axes[1].grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(Path(output_dir) / 'training_curves.png', dpi=150)
    plt.close()
    
    print(f"[OK] Training curves saved to {output_dir}/training_curves.png")


def save_training_history(history, output_dir):
    """Save training history to JSON."""
    import numpy as np
    
    # Convert numpy types to native Python types for JSON serialization
    def convert_to_native(obj):
        if isinstance(obj, dict):
            return {key: convert_to_native(value) for key, value in obj.items()}
        elif isinstance(obj, list):
            return [convert_to_native(item) for item in obj]
        elif isinstance(obj, (np.integer, np.int64, np.int32)):
            return int(obj)
        elif isinstance(obj, (np.floating, np.float64, np.float32)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        else:
            return obj
    
    history_native = convert_to_native(history)
    history_path = Path(output_dir) / 'training_history.json'
    with open(history_path, 'w') as f:
        json.dump(history_native, f, indent=2)
    print(f"[OK] Training history saved to {history_path}")


def main():
    """Main training function."""
    args = parse_args()
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("\n" + "="*70)
    print("RL-BASED APT DETECTION SYSTEM - TRAINING")
    print("="*70)
    print(f"Start time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Output directory: {output_dir}")
    print(f"Device: {args.device}")
    
    # 1. Load pre-trained models
    ae_loader, vae_loader, transformer_loader = load_models(args)
    
    # 2. Initialize conditional replay
    print("\n" + "="*70)
    print("INITIALIZING CONDITIONAL REPLAY")
    print("="*70)
    conditional_replay = ConditionalReplay(args.data_path)
    
    # 3. Generate training sequences
    sequences = generate_training_sequences(args)
    
    # 4. Initialize environment
    print("\n" + "="*70)
    print("INITIALIZING RL ENVIRONMENT")
    print("="*70)
    env = APTEnvironment(
        autoencoder_loader=ae_loader,
        vae_loader=vae_loader,
        transformer_loader=transformer_loader,
        conditional_replay=conditional_replay,
        max_steps=args.max_steps
    )
    print("[OK] Environment initialized")
    
    # 5. Initialize DQN agent
    print("\n" + "="*70)
    print("INITIALIZING DQN AGENT")
    print("="*70)
    agent = DQNAgent(
        state_dim=env.observation_space.shape[0],
        action_dim=env.action_space.n,
        learning_rate=args.learning_rate,
        gamma=args.gamma,
        epsilon_start=args.epsilon_start,
        epsilon_end=args.epsilon_end,
        epsilon_decay=args.epsilon_decay,
        batch_size=args.batch_size,
        device=args.device
    )
    
    # 6. Training loop
    print("\n" + "="*70)
    print("STARTING TRAINING")
    print("="*70)
    print(f"Episodes: {args.num_episodes}")
    print(f"Sequences: {len(sequences)}")
    
    rewards = []
    all_losses = []
    episode_summaries = []
    
    start_time = time.time()
    
    for episode in tqdm(range(args.num_episodes), desc="Training"):
        # Select sequence (cycle through available sequences)
        sequence = sequences[episode % len(sequences)]
        
        # Train episode
        episode_reward, episode_losses, summary = train_episode(env, agent, sequence)
        
        # Record metrics
        rewards.append(episode_reward)
        all_losses.extend(episode_losses)
        episode_summaries.append(summary)
        
        # Print progress
        if (episode + 1) % 10 == 0:
            avg_reward = np.mean(rewards[-10:])
            avg_loss = np.mean(episode_losses) if episode_losses else 0
            stats = agent.get_training_stats()
            
            tqdm.write(f"\nEpisode {episode + 1}/{args.num_episodes}")
            tqdm.write(f"  Avg Reward (last 10): {avg_reward:.2f}")
            tqdm.write(f"  Avg Loss: {avg_loss:.4f}")
            tqdm.write(f"  Epsilon: {stats['epsilon']:.4f}")
            tqdm.write(f"  Buffer: {stats['buffer_size']}/{10000}")
        
        # Save checkpoint
        if (episode + 1) % args.save_freq == 0:
            checkpoint_path = output_dir / f"agent_episode_{episode + 1}.pth"
            agent.save(str(checkpoint_path))
    
    training_time = time.time() - start_time
    
    # 7. Save final model
    print("\n" + "="*70)
    print("SAVING FINAL MODEL")
    print("="*70)
    final_model_path = output_dir / "agent_final.pth"
    agent.save(str(final_model_path))
    
    # 8. Save training history
    history = {
        'rewards': rewards,
        'episode_summaries': episode_summaries,
        'training_time_seconds': training_time,
        'hyperparameters': vars(args)
    }
    save_training_history(history, output_dir)
    
    # 9. Plot training curves
    plot_training_curves(rewards, all_losses, output_dir)
    
    # 10. Print final statistics
    print("\n" + "="*70)
    print("TRAINING COMPLETE")
    print("="*70)
    print(f"Total episodes: {args.num_episodes}")
    print(f"Training time: {training_time / 60:.2f} minutes")
    print(f"Average reward (last 100): {np.mean(rewards[-100:]):.2f}")
    print(f"Final epsilon: {agent.epsilon:.4f}")
    print(f"Total training steps: {agent.steps_done}")
    print(f"Output directory: {output_dir}")
    print("="*70)


if __name__ == "__main__":
    main()
