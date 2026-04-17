"""
RL APT Detection System - Evaluation Script
=============================================

Evaluates a trained DQN agent on held-out sequences.

Usage:
    python evaluate.py --agent_path outputs/agent_best.pth
"""

import os
import sys
import json
import time
import argparse
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

from models.autoencoder_loader import AutoencoderLoader
from models.vae_loader import VAELoader
from models.transformer_loader import TransformerLoader
from models.gnn_loader import GNNLoader
from rl.dqn_agent import DQNAgent
from env.apt_env import APTEnvironment
from synthetic.data_loader import APTDataLoader


def parse_args():
    parser = argparse.ArgumentParser(description='Evaluate RL APT Detection Agent')
    parser.add_argument('--agent_path', type=str, default='./outputs/agent_best.pth')
    parser.add_argument('--num_episodes', type=int, default=50)
    parser.add_argument('--device', type=str, default='cpu')
    parser.add_argument('--ae_variant', type=str, default='reg_ae_64')
    parser.add_argument('--vae_variant', type=str, default='beta_vae')
    parser.add_argument('--data_source', type=str, default='both',
                        choices=['synthetic', 'real', 'both'])
    parser.add_argument('--output_dir', type=str, default='./evaluation')
    return parser.parse_args()


def evaluate_on_sequences(agent, env, sequences, num_episodes, label=''):
    """Evaluate agent on a set of sequences."""
    results = {
        'rewards': [],
        'steps': [],
        'early_detections': 0,
        'false_positives': 0,
        'false_negatives': 0,
        'true_positives': 0,
        'true_negatives': 0,
        'action_distribution': {name: 0 for name in APTEnvironment.ACTION_NAMES.values()},
    }

    for ep in range(min(num_episodes, len(sequences))):
        seq = sequences[ep % len(sequences)]
        state = env.reset(sequence=seq)
        episode_reward = 0
        intervened = False

        while True:
            # Force greedy action by setting agent's epsilon manually
            old_eps = getattr(agent, 'epsilon', 0.0)
            agent.epsilon = 0.0
            action = agent.select_action(state)
            agent.epsilon = old_eps
            next_state, reward, done, info = env.step(action)

            episode_reward += reward
            results['action_distribution'][APTEnvironment.ACTION_NAMES[action]] += 1

            if action >= APTEnvironment.ACTION_ESCALATE:
                intervened = True

            state = next_state
            if done:
                break

        summary = env.get_episode_summary()
        results['rewards'].append(episode_reward)
        results['steps'].append(summary['total_steps'])

        is_attack = any(s > 0 for s in seq['ckc_stages'])

        if is_attack and intervened:
            results['true_positives'] += 1
            if summary.get('early_detection', False):
                results['early_detections'] += 1
        elif is_attack and not intervened:
            results['false_negatives'] += 1
        elif not is_attack and intervened:
            results['false_positives'] += 1
        else:
            results['true_negatives'] += 1

    # Compute metrics
    tp = results['true_positives']
    fp = results['false_positives']
    fn = results['false_negatives']
    tn = results['true_negatives']
    total = tp + fp + fn + tn

    results['avg_reward'] = float(np.mean(results['rewards'])) if results['rewards'] else 0
    results['avg_steps'] = float(np.mean(results['steps'])) if results['steps'] else 0
    results['early_detection_rate'] = results['early_detections'] / max(tp + fn, 1)
    results['precision'] = tp / max(tp + fp, 1)
    results['recall'] = tp / max(tp + fn, 1)
    results['f1'] = 2 * results['precision'] * results['recall'] / max(results['precision'] + results['recall'], 1e-8)
    results['accuracy'] = (tp + tn) / max(total, 1)
    results['false_positive_rate'] = fp / max(fp + tn, 1)

    if label:
        print(f"\n  {label} Results ({min(num_episodes, len(sequences))} episodes):")
        print(f"    Avg Reward:          {results['avg_reward']:.2f}")
        print(f"    Avg Steps:           {results['avg_steps']:.1f}")
        print(f"    Precision:           {results['precision']:.3f}")
        print(f"    Recall:              {results['recall']:.3f}")
        print(f"    F1 Score:            {results['f1']:.3f}")
        print(f"    Early Detection:     {results['early_detection_rate']:.1%}")
        print(f"    False Positive Rate: {results['false_positive_rate']:.1%}")

    return results


def main():
    args = parse_args()

    print("\n" + "=" * 70)
    print("RL-BASED APT DETECTION SYSTEM — EVALUATION")
    print("=" * 70)

    os.makedirs(args.output_dir, exist_ok=True)

    # Load models
    print("\n[1/4] Loading models...")
    ae_loader = AutoencoderLoader(variant=args.ae_variant, device=args.device)
    vae_loader = VAELoader(variant=args.vae_variant, device=args.device)
    transformer_loader = TransformerLoader(device=args.device)

    try:
        gnn_loader = GNNLoader(device=args.device)
    except Exception as e:
        print(f"[GNN] Warning: {e}")
        gnn_loader = None

    # Load data
    print("\n[2/4] Loading evaluation data...")
    data_loader = APTDataLoader()
    data_loader.load_all()

    if gnn_loader is not None and gnn_loader.enabled:
        syn_df = data_loader.synthetic_df
        if syn_df is not None:
            feature_matrix = data_loader.get_feature_matrix(syn_df)
            gnn_loader.build_graph(syn_df, feature_matrix)
            gnn_loader.run_inference(syn_df)

    # Create environment
    env = APTEnvironment(
        autoencoder_loader=ae_loader,
        vae_loader=vae_loader,
        transformer_loader=transformer_loader,
        gnn_loader=gnn_loader,
    )

    # Load agent
    print(f"\n[3/4] Loading agent from {args.agent_path}...")
    agent = DQNAgent(
        state_dim=APTEnvironment.STATE_DIM,
        action_dim=5,
    )

    if os.path.exists(args.agent_path):
        agent.load(args.agent_path)
        print("  Agent loaded successfully")
    else:
        print(f"  [WARNING] Agent file not found: {args.agent_path}")
        print("  Using random agent for baseline evaluation")

    # Evaluate
    print(f"\n[4/4] Evaluating ({args.num_episodes} episodes per source)...")

    all_results = {}

    # Evaluate on synthetic sequences
    syn_sequences = data_loader.get_training_sequences(source='synthetic', min_length=3)
    if syn_sequences:
        np.random.shuffle(syn_sequences)
        all_results['synthetic'] = evaluate_on_sequences(
            agent, env, syn_sequences, args.num_episodes, label='SYNTHETIC')

    # Evaluate on real sequences
    if data_loader.real_df is not None:
        real_sequences = data_loader.get_training_sequences(source='real', min_length=3)
        if real_sequences:
            np.random.shuffle(real_sequences)
            all_results['real'] = evaluate_on_sequences(
                agent, env, real_sequences, args.num_episodes, label='REAL')

    # Save results
    report_path = os.path.join(args.output_dir, 'evaluation_report.json')

    # Clean up for JSON serialization
    serializable = {}
    for source, results in all_results.items():
        serializable[source] = {
            k: v for k, v in results.items()
            if k not in ['rewards', 'steps']
        }
        serializable[source]['avg_reward'] = results['avg_reward']
        serializable[source]['avg_steps'] = results['avg_steps']

    with open(report_path, 'w') as f:
        json.dump(serializable, f, indent=2)

    print(f"\n{'=' * 70}")
    print(f"EVALUATION COMPLETE — Report saved to {report_path}")
    print(f"{'=' * 70}\n")


if __name__ == '__main__':
    main()
