"""
RL APT Detection System - Training Script
==========================================

Trains the DQN agent using 4 detection models (AE, VAE, Transformer, GNN)
on both real and synthetic alert data.

Usage:
    python train.py --num_episodes 500 --ae_variant reg_ae_64 --vae_variant beta_vae
"""

import os
import sys
import json
import time
import argparse
import numpy as np
import torch

# Add parent to path
sys.path.insert(0, os.path.dirname(__file__))

from models.autoencoder_loader import AutoencoderLoader
from models.vae_loader import VAELoader
from models.transformer_loader import TransformerLoader
from models.gnn_loader import GNNLoader
from rl.dqn_agent import DQNAgent
from env.apt_env import APTEnvironment
from synthetic.data_loader import APTDataLoader


def parse_args():
    parser = argparse.ArgumentParser(description='Train RL APT Detection Agent')

    # Training params
    parser.add_argument('--num_episodes', type=int, default=500)
    parser.add_argument('--learning_rate', type=float, default=0.001)
    parser.add_argument('--gamma', type=float, default=0.99)
    parser.add_argument('--epsilon_start', type=float, default=1.0)
    parser.add_argument('--epsilon_end', type=float, default=0.01)
    parser.add_argument('--epsilon_decay', type=float, default=0.995)
    parser.add_argument('--batch_size', type=int, default=64)
    parser.add_argument('--device', type=str, default='cpu')
    parser.add_argument('--output_dir', type=str, default='./outputs')

    # Model selection
    parser.add_argument('--ae_variant', type=str, default='reg_ae_64',
                        choices=['reg_ae_64', 'reg_ae_32'],
                        help='Autoencoder variant')
    parser.add_argument('--vae_variant', type=str, default='beta_vae',
                        choices=['beta_vae', 'beta_vae_32', 'beta_vae_malicious'],
                        help='VAE variant')

    # Data
    parser.add_argument('--data_source', type=str, default='synthetic',
                        choices=['synthetic', 'real', 'both'])
    parser.add_argument('--campaign_mode', type=str, default='normal',
                        choices=['stealth', 'slow', 'normal', 'fast', 'blitz'])

    return parser.parse_args()


def main():
    args = parse_args()

    print("\n" + "=" * 70)
    print("RL-BASED APT DETECTION SYSTEM — TRAINING")
    print("=" * 70)

    os.makedirs(args.output_dir, exist_ok=True)

    # ─── Step 1: Load Models ───
    print("\n[1/5] Loading detection models...")

    ae_loader = AutoencoderLoader(variant=args.ae_variant, device=args.device)
    vae_loader = VAELoader(variant=args.vae_variant, device=args.device)
    transformer_loader = TransformerLoader(device=args.device)

    try:
        gnn_loader = GNNLoader(device=args.device)
    except Exception as e:
        print(f"[GNN] Warning: Could not load GNN — {e}")
        gnn_loader = None

    # ─── Step 2: Load Data ───
    print("\n[2/5] Loading training data...")

    data_loader = APTDataLoader(campaign_mode=args.campaign_mode)
    data_loader.load_all()

    # Build GNN graph on synthetic data (has actual features)
    if gnn_loader is not None and gnn_loader.enabled:
        print("\n[2.5/5] Building GNN graph and running inference...")
        syn_df = data_loader.synthetic_df
        if syn_df is not None:
            feature_matrix = data_loader.get_feature_matrix(syn_df)
            gnn_loader.build_graph(syn_df, feature_matrix)
            gnn_loader.run_inference(syn_df)

    # Get synthetic training sequences
    sequences = data_loader.get_training_sequences(
        source='synthetic',
        min_length=3,
        max_length=30,
    )

    # Load real data sequences (proper CKC sequences ending with S7)
    try:
        from synthetic.real_data_loader import load_real_data, build_real_sequences
        print("\n[2.6/5] Loading real data sequences...")
        mal_merged, benign_df = load_real_data()
        real_sequences = build_real_sequences(mal_merged, benign_df, num_sequences=500, seed=42)
        sequences.extend(real_sequences)
        np.random.shuffle(sequences)
        print(f"[Data] Mixed training: {len(sequences)} total sequences "
              f"(synthetic + real)")
    except Exception as e:
        print(f"[Real Data] Warning: Could not load real sequences: {e}")
        import traceback
        traceback.print_exc()

    if not sequences:
        print("[ERROR] No training sequences found!")
        return

    # ─── Step 3: Initialize Environment and Agent ───
    print("\n[3/5] Initializing environment and agent...")

    env = APTEnvironment(
        autoencoder_loader=ae_loader,
        vae_loader=vae_loader,
        transformer_loader=transformer_loader,
        gnn_loader=gnn_loader,
        max_steps=50,
        early_stop_on_intervention=True,
    )

    agent = DQNAgent(
        state_dim=APTEnvironment.STATE_DIM,
        action_dim=5,
        learning_rate=args.learning_rate,
        gamma=args.gamma,
        epsilon_start=args.epsilon_start,
        epsilon_end=args.epsilon_end,
        epsilon_decay=args.epsilon_decay,
        batch_size=args.batch_size,
    )

    print(f"  State dim: {APTEnvironment.STATE_DIM}")
    print(f"  Action dim: 5")
    print(f"  AE: {args.ae_variant}, VAE: {args.vae_variant}")
    print(f"  Data source: {args.data_source} ({len(sequences)} sequences)")

    # ─── Step 4: Training Loop ───
    print(f"\n[4/5] Training for {args.num_episodes} episodes...")

    rewards_history = []
    epsilon_history = []
    best_avg_reward = float('-inf')
    window_size = 50

    training_start = time.time()

    for episode in range(1, args.num_episodes + 1):
        # Select random sequence
        seq = sequences[np.random.randint(len(sequences))]

        # Reset environment
        state = env.reset(sequence=seq)
        episode_reward = 0
        steps = 0

        while True:
            # Select action
            action = agent.select_action(state)

            # Take step
            next_state, reward, done, info = env.step(action)

            # Store experience
            agent.store_transition(state, action, reward, next_state, done)

            # Train
            loss = agent.train_step()

            episode_reward += reward
            state = next_state
            steps += 1

            if done:
                break

        # Decay epsilon
        agent.update_epsilon()

        # Record
        rewards_history.append(episode_reward)
        epsilon_history.append(agent.epsilon)

        # Calculate running average
        avg_reward = np.mean(rewards_history[-window_size:])

        # Log progress
        if episode % 10 == 0 or episode <= 5:
            elapsed = time.time() - training_start
            print(f"  Episode {episode:4d}/{args.num_episodes} | "
                  f"Reward: {episode_reward:7.2f} | "
                  f"Avg Reward: {avg_reward:7.2f} | "
                  f"Epsilon: {agent.epsilon:.4f} | "
                  f"Steps: {steps:3d} | "
                  f"Time: {elapsed:.0f}s")

        # Save best model
        if episode >= window_size and avg_reward > best_avg_reward:
            best_avg_reward = avg_reward
            agent.save(os.path.join(args.output_dir, 'agent_best.pth'))
            if episode % 50 == 0:
                print(f"    -> New best avg reward: {best_avg_reward:.2f}")

        # Checkpoint every 100 episodes
        if episode % 100 == 0:
            agent.save(os.path.join(args.output_dir, f'agent_ep{episode}.pth'))

    # ─── Step 5: Save Final Model ───
    print(f"\n[5/5] Saving final model...")

    agent.save(os.path.join(args.output_dir, 'agent_final.pth'))

    # Save training log
    training_log = {
        'args': vars(args),
        'rewards_history': [float(r) for r in rewards_history],
        'epsilon_history': [float(e) for e in epsilon_history],
        'best_avg_reward': float(best_avg_reward),
        'total_time_seconds': time.time() - training_start,
        'num_sequences': len(sequences),
        'ae_variant': args.ae_variant,
        'vae_variant': args.vae_variant,
        'state_dim': APTEnvironment.STATE_DIM,
    }

    log_path = os.path.join(args.output_dir, 'training_log.json')
    with open(log_path, 'w') as f:
        json.dump(training_log, f, indent=2)

    total_time = time.time() - training_start
    print(f"\n{'=' * 70}")
    print(f"TRAINING COMPLETE")
    print(f"{'=' * 70}")
    print(f"  Episodes: {args.num_episodes}")
    print(f"  Best Avg Reward: {best_avg_reward:.2f}")
    print(f"  Final Epsilon: {agent.epsilon:.4f}")
    print(f"  Total Time: {total_time:.1f}s ({total_time/60:.1f}min)")
    print(f"  Models saved to: {args.output_dir}")
    print(f"{'=' * 70}\n")


if __name__ == '__main__':
    main()
