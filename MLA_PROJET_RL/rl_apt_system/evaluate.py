"""
Evaluation Script for RL-based APT Detection System
====================================================

This script evaluates a trained DQN agent on test sequences and computes
comprehensive performance metrics.

Evaluation Metrics:
-------------------
1. Episode Rewards: Total reward per test episode
2. Early Detection Rate: % of attacks detected in stages S1-S3
3. False Positive Rate: % of benign events incorrectly flagged
4. Action Distribution: Frequency of each action type
5. CKC Stage Analysis: Performance breakdown by attack stage
6. Real vs Synthetic: Comparison of performance on different data types

Usage:
------
python evaluate.py --agent_path outputs/agent_final.pth --num_episodes 100
"""

import argparse
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import json
from tqdm import tqdm
from collections import defaultdict

import torch

# Import project modules
import sys
sys.path.append(str(Path(__file__).parent))

from models.autoencoder_loader import AutoencoderLoader
from models.vae_loader import VAELoader
from models.transformer_loader import TransformerLoader
from synthetic.meta_sequence_generator import MetaSequenceGenerator
from synthetic.conditional_replay import ConditionalReplay, RealSequenceExtractor
from env.apt_env import APTEnvironment
from rl.dqn_agent import DQNAgent


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Evaluate trained RL agent')
    
    # Model and data paths
    parser.add_argument('--agent_path', type=str, required=True,
                        help='Path to trained agent checkpoint')
    parser.add_argument('--data_path', type=str, default='../combined_dataset_final.xlsx',
                        help='Path to real SIEM data')
    parser.add_argument('--ae_model', type=str, default='../autoencoder_outputs/autoencoder_anomaly_detection.pth',
                        help='Path to Autoencoder model')
    parser.add_argument('--vae_model', type=str, default='../vae_anomaly_detector_outputs/vae_anomaly_detector.pth',
                        help='Path to VAE model')
    parser.add_argument('--transformer_model', type=str, default='../transformer_outputs/transformer_next_step_prediction.pth',
                        help='Path to Transformer model')
    
    # Evaluation parameters
    parser.add_argument('--num_episodes', type=int, default=100,
                        help='Number of evaluation episodes')
    parser.add_argument('--num_synthetic', type=int, default=50,
                        help='Number of synthetic sequences')
    parser.add_argument('--num_real', type=int, default=50,
                        help='Number of real sequences')
    parser.add_argument('--max_steps', type=int, default=50,
                        help='Maximum steps per episode')
    
    # Output
    parser.add_argument('--output_dir', type=str, default='./evaluation',
                        help='Directory to save evaluation results')
    
    # Device
    parser.add_argument('--device', type=str, default='cpu',
                        help='Device to use (cpu or cuda)')
    
    return parser.parse_args()


def load_models_and_agent(args):
    """Load models and trained agent."""
    print("\n" + "="*70)
    print("LOADING MODELS AND AGENT")
    print("="*70)
    
    # Load detection models
    ae_loader = AutoencoderLoader(args.ae_model, device=args.device)
    vae_loader = VAELoader(args.vae_model, device=args.device)
    transformer_loader = TransformerLoader(args.transformer_model, device=args.device)
    
    # Initialize agent
    agent = DQNAgent(
        state_dim=10,  # Standard APT environment state dimension
        action_dim=5,   # 5 defensive actions
        device=args.device
    )
    
    # Load trained weights
    print("\n[>>] Loading trained agent...")
    agent.load(args.agent_path)
    
    return ae_loader, vae_loader, transformer_loader, agent


def generate_test_sequences(args):
    """Generate both synthetic and real test sequences."""
    print("\n" + "="*70)
    print("GENERATING TEST SEQUENCES")
    print("="*70)
    
    # Generate synthetic sequences
    print("\n[*] Generating synthetic sequences...")
    generator = MetaSequenceGenerator(use_simple_generation=True)
    synthetic_sequences = generator.generate_meta_sequences(
        num_sequences=args.num_synthetic,
        min_length=5,
        max_length=20
    )
    
    # Extract real sequences
    print("\n[*] Extracting real sequences...")
    extractor = RealSequenceExtractor(args.data_path)
    real_sequence_dicts = extractor.extract_sequences(
        min_length=5,
        max_length=20,
        num_sequences=args.num_real
    )
    
    # Convert real sequences to meta-sequence format
    real_sequences = []
    for seq_dict in real_sequence_dicts:
        meta_seq = []
        for i, (ckc, time_delta) in enumerate(zip(seq_dict['ckc_stages'], seq_dict['time_deltas'])):
            meta_seq.append({
                'ckc_stage': ckc,
                'event_index': i,
                'relative_time_delta': time_delta,
                'cumulative_time': sum(seq_dict['time_deltas'][:i+1])
            })
        real_sequences.append(meta_seq)
    
    print(f"\n[OK] Test sequences ready:")
    print(f"   Synthetic: {len(synthetic_sequences)}")
    print(f"   Real: {len(real_sequences)}")
    
    return synthetic_sequences, real_sequences


def evaluate_episode(env, agent, sequence):
    """Evaluate agent on one episode."""
    state = env.reset(sequence)
    episode_reward = 0
    
    done = False
    while not done:
        # Select action (greedy, no exploration)
        action = agent.select_action(state, training=False)
        
        # Execute action
        next_state, reward, done, info = env.step(action)
        
        state = next_state
        episode_reward += reward
    
    return episode_reward, env.get_episode_summary()


def compute_metrics(summaries):
    """Compute evaluation metrics from episode summaries."""
    metrics = {
        'total_episodes': len(summaries),
        'avg_reward': np.mean([s['total_reward'] for s in summaries]),
        'std_reward': np.std([s['total_reward'] for s in summaries]),
        'early_detection_rate': np.mean([s['early_detection'] for s in summaries]),
        'action_distribution': defaultdict(int),
        'ckc_stage_distribution': defaultdict(int),
        'avg_steps': np.mean([s['total_steps'] for s in summaries])
    }
    
    # Aggregate action distribution
    for summary in summaries:
        for action, count in summary['action_distribution'].items():
            metrics['action_distribution'][action] += count
    
    # Aggregate CKC stage distribution
    for summary in summaries:
        for stage in summary['ckc_stages_seen']:
            metrics['ckc_stage_distribution'][f'S{stage}'] += 1
    
    return metrics


def plot_evaluation_results(synthetic_metrics, real_metrics, output_dir):
    """Plot evaluation results comparing synthetic and real sequences."""
    
    # Create figure with subplots
    fig = plt.figure(figsize=(16, 10))
    
    # 1. Reward comparison
    ax1 = plt.subplot(2, 3, 1)
    data = [
        [synthetic_metrics['avg_reward'], real_metrics['avg_reward']]
    ]
    x = ['Synthetic', 'Real']
    ax1.bar(x, [synthetic_metrics['avg_reward'], real_metrics['avg_reward']], 
            color=['#3498db', '#e74c3c'], alpha=0.7)
    ax1.set_ylabel('Average Reward')
    ax1.set_title('Performance: Synthetic vs Real')
    ax1.grid(True, alpha=0.3)
    
    # 2. Early detection rate
    ax2 = plt.subplot(2, 3, 2)
    rates = [
        synthetic_metrics['early_detection_rate'] * 100,
        real_metrics['early_detection_rate'] * 100
    ]
    ax2.bar(x, rates, color=['#3498db', '#e74c3c'], alpha=0.7)
    ax2.set_ylabel('Early Detection Rate (%)')
    ax2.set_title('Early Detection (S1-S3)')
    ax2.set_ylim([0, 100])
    ax2.grid(True, alpha=0.3)
    
    # 3. Action distribution - Synthetic
    ax3 = plt.subplot(2, 3, 3)
    actions = list(synthetic_metrics['action_distribution'].keys())
    counts = list(synthetic_metrics['action_distribution'].values())
    ax3.bar(actions, counts, color='#3498db', alpha=0.7)
    ax3.set_xlabel('Action')
    ax3.set_ylabel('Frequency')
    ax3.set_title('Action Distribution (Synthetic)')
    ax3.tick_params(axis='x', rotation=45)
    ax3.grid(True, alpha=0.3)
    
    # 4. Action distribution - Real
    ax4 = plt.subplot(2, 3, 4)
    actions = list(real_metrics['action_distribution'].keys())
    counts = list(real_metrics['action_distribution'].values())
    ax4.bar(actions, counts, color='#e74c3c', alpha=0.7)
    ax4.set_xlabel('Action')
    ax4.set_ylabel('Frequency')
    ax4.set_title('Action Distribution (Real)')
    ax4.tick_params(axis='x', rotation=45)
    ax4.grid(True, alpha=0.3)
    
    # 5. CKC stage distribution - Synthetic
    ax5 = plt.subplot(2, 3, 5)
    stages = sorted(synthetic_metrics['ckc_stage_distribution'].keys())
    counts = [synthetic_metrics['ckc_stage_distribution'][s] for s in stages]
    ax5.bar(stages, counts, color='#3498db', alpha=0.7)
    ax5.set_xlabel('CKC Stage')
    ax5.set_ylabel('Frequency')
    ax5.set_title('CKC Distribution (Synthetic)')
    ax5.grid(True, alpha=0.3)
    
    # 6. CKC stage distribution - Real
    ax6 = plt.subplot(2, 3, 6)
    stages = sorted(real_metrics['ckc_stage_distribution'].keys())
    counts = [real_metrics['ckc_stage_distribution'][s] for s in stages]
    ax6.bar(stages, counts, color='#e74c3c', alpha=0.7)
    ax6.set_xlabel('CKC Stage')
    ax6.set_ylabel('Frequency')
    ax6.set_title('CKC Distribution (Real)')
    ax6.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(Path(output_dir) / 'evaluation_results.png', dpi=150, bbox_inches='tight')
    plt.close()
    
    print(f"[OK] Evaluation plots saved to {output_dir}/evaluation_results.png")


def save_evaluation_report(synthetic_metrics, real_metrics, output_dir):
    """Save evaluation report to JSON and text."""
    report = {
        'synthetic_sequences': synthetic_metrics,
        'real_sequences': real_metrics
    }
    
    # Save JSON
    json_path = Path(output_dir) / 'evaluation_report.json'
    with open(json_path, 'w') as f:
        json.dump(report, f, indent=2, default=str)
    
    # Save text report
    text_path = Path(output_dir) / 'evaluation_report.txt'
    with open(text_path, 'w') as f:
        f.write("="*70 + "\n")
        f.write("RL-BASED APT DETECTION SYSTEM - EVALUATION REPORT\n")
        f.write("="*70 + "\n\n")
        
        f.write("SYNTHETIC SEQUENCES\n")
        f.write("-"*70 + "\n")
        f.write(f"Episodes: {synthetic_metrics['total_episodes']}\n")
        f.write(f"Average Reward: {synthetic_metrics['avg_reward']:.2f} ± {synthetic_metrics['std_reward']:.2f}\n")
        f.write(f"Early Detection Rate: {synthetic_metrics['early_detection_rate']*100:.1f}%\n")
        f.write(f"Average Steps per Episode: {synthetic_metrics['avg_steps']:.1f}\n\n")
        
        f.write("REAL SEQUENCES\n")
        f.write("-"*70 + "\n")
        f.write(f"Episodes: {real_metrics['total_episodes']}\n")
        f.write(f"Average Reward: {real_metrics['avg_reward']:.2f} ± {real_metrics['std_reward']:.2f}\n")
        f.write(f"Early Detection Rate: {real_metrics['early_detection_rate']*100:.1f}%\n")
        f.write(f"Average Steps per Episode: {real_metrics['avg_steps']:.1f}\n\n")
    
    print(f"[OK] Evaluation report saved to:")
    print(f"   {json_path}")
    print(f"   {text_path}")


def main():
    """Main evaluation function."""
    args = parse_args()
    
    # Create output directory
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("\n" + "="*70)
    print("RL-BASED APT DETECTION SYSTEM - EVALUATION")
    print("="*70)
    print(f"Output directory: {output_dir}")
    
    # 1. Load models and agent
    ae_loader, vae_loader, transformer_loader, agent = load_models_and_agent(args)
    
    # 2. Initialize conditional replay
    conditional_replay = ConditionalReplay(args.data_path)
    
    # 3. Generate test sequences
    synthetic_sequences, real_sequences = generate_test_sequences(args)
    
    # 4. Initialize environment
    env = APTEnvironment(
        autoencoder_loader=ae_loader,
        vae_loader=vae_loader,
        transformer_loader=transformer_loader,
        conditional_replay=conditional_replay,
        max_steps=args.max_steps
    )
    
    # 5. Evaluate on synthetic sequences
    print("\n" + "="*70)
    print("EVALUATING ON SYNTHETIC SEQUENCES")
    print("="*70)
    
    synthetic_summaries = []
    for i, sequence in enumerate(tqdm(synthetic_sequences, desc="Synthetic")):
        reward, summary = evaluate_episode(env, agent, sequence)
        synthetic_summaries.append(summary)
    
    synthetic_metrics = compute_metrics(synthetic_summaries)
    
    # 6. Evaluate on real sequences
    print("\n" + "="*70)
    print("EVALUATING ON REAL SEQUENCES")
    print("="*70)
    
    real_summaries = []
    for i, sequence in enumerate(tqdm(real_sequences, desc="Real")):
        reward, summary = evaluate_episode(env, agent, sequence)
        real_summaries.append(summary)
    
    real_metrics = compute_metrics(real_summaries)
    
    # 7. Print results
    print("\n" + "="*70)
    print("EVALUATION RESULTS")
    print("="*70)
    
    print("\n[RESULTS] SYNTHETIC SEQUENCES:")
    print(f"   Average Reward: {synthetic_metrics['avg_reward']:.2f} ± {synthetic_metrics['std_reward']:.2f}")
    print(f"   Early Detection Rate: {synthetic_metrics['early_detection_rate']*100:.1f}%")
    print(f"   Average Steps: {synthetic_metrics['avg_steps']:.1f}")
    
    print("\n[RESULTS] REAL SEQUENCES:")
    print(f"   Average Reward: {real_metrics['avg_reward']:.2f} ± {real_metrics['std_reward']:.2f}")
    print(f"   Early Detection Rate: {real_metrics['early_detection_rate']*100:.1f}%")
    print(f"   Average Steps: {real_metrics['avg_steps']:.1f}")
    
    # 8. Plot results
    plot_evaluation_results(synthetic_metrics, real_metrics, output_dir)
    
    # 9. Save report
    save_evaluation_report(synthetic_metrics, real_metrics, output_dir)
    
    print("\n" + "="*70)
    print("EVALUATION COMPLETE")
    print("="*70)


if __name__ == "__main__":
    main()
