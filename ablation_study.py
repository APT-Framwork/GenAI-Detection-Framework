"""
Ablation Study: Remove one model at a time
=============================================

For each ablation:
1. Train a NEW agent (saved to outputs_ablation/<name>/)
2. Evaluate on 2000 balanced episodes
3. Compare all 5 configurations (full + 4 ablations)
4. Plot comparison

Ablation configs:
  - Full:          AE + VAE + Transformer + GNN  (baseline)
  - No AE:         --- + VAE + Transformer + GNN
  - No VAE:        AE + --- + Transformer + GNN
  - No Transformer: AE + VAE + ---         + GNN
  - No GNN:        AE + VAE + Transformer + ---
"""

import os
import sys
import json
import time
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

sys.path.insert(0, os.path.dirname(__file__))

from models.autoencoder_loader import AutoencoderLoader
from models.vae_loader import VAELoader
from models.transformer_loader import TransformerLoader
from models.gnn_loader import GNNLoader
from rl.dqn_agent import DQNAgent
from env.apt_env import APTEnvironment
from synthetic.data_loader import FEATURE_COLUMNS, APTDataLoader
from synthetic.real_data_loader import load_real_data, build_real_sequences, MACHINE_POOL
from evaluate_real import evaluate_with_predetection


# ─── Wrapper loaders that return zeros when disabled ───

class DisabledAE:
    """Dummy AE that returns zeros."""
    def __init__(self):
        self.variant = 'disabled'
        self.model = None
    def get_anomaly_score(self, x):
        n = x.shape[0]
        return {'anomaly_score': np.zeros(n), 'reconstruction_error': np.zeros(n)}
    def encode(self, x):
        return np.zeros((x.shape[0], 64), dtype=np.float32)


class DisabledVAE:
    """Dummy VAE that returns zeros."""
    def __init__(self):
        self.variant = 'disabled'
        self.model = None
    def get_malicious_probability(self, x):
        n = x.shape[0]
        return {'malicious_probability': np.zeros(n), 'uncertainty': np.zeros(n)}


class DisabledTransformer:
    """Dummy Transformer that returns neutral predictions."""
    def __init__(self):
        self.model = None
    def predict_next_stage(self, x):
        return {'predicted_next_ckc_stage': 0, 'prediction_confidence': 0.5}


class DisabledGNN:
    """Dummy GNN that returns zeros."""
    def __init__(self):
        self.enabled = False
        self.df_rl = None
        self.model = None
    def get_rl_state_features(self, **kwargs):
        return {
            'GNN_node_risk_current_host': 0.0,
            'GNN_neighbor_risk': 0.0,
            'risk_growth': 0.0,
        }
    def build_graph(self, *a, **k): pass
    def run_inference(self, *a, **k): pass


def build_gnn_graph(gnn_loader):
    """Build GNN graph from real data."""
    if gnn_loader is None or not gnn_loader.enabled:
        return
    feat_df = pd.read_parquet(os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'feature_selection_outputs2', 'feature_matrix_no_leakage.parquet'))
    labels_df = pd.read_parquet(os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'feature_selection_outputs2', 'labels.parquet'))
    mal_mask = labels_df['malicious'] == 1
    mal_features = feat_df.loc[mal_mask].reset_index(drop=True)

    feat_matrix = np.zeros((len(mal_features), len(FEATURE_COLUMNS)), dtype=np.float32)
    for i, col in enumerate(FEATURE_COLUMNS):
        if col in mal_features.columns:
            feat_matrix[:, i] = mal_features[col].values.astype(np.float32)

    gnn_df = pd.DataFrame()
    gnn_df['timestamp'] = pd.Timestamp('2024-01-01') + pd.to_timedelta(
        np.arange(len(mal_features)), unit='min')
    gnn_df['machine_name'] = np.random.choice(MACHINE_POOL, size=len(mal_features))
    gnn_df['src_user'] = 'user1'
    gnn_df['src_ip'] = '192.168.1.1'
    gnn_loader.build_graph(gnn_df, feat_matrix)
    gnn_loader.run_inference(gnn_df)


def train_agent(env, sequences, num_episodes, save_dir):
    """Train a fresh DQN agent."""
    os.makedirs(save_dir, exist_ok=True)
    agent = DQNAgent(state_dim=APTEnvironment.STATE_DIM, action_dim=5)

    best_avg_reward = -float('inf')
    reward_window = []

    for ep in range(num_episodes):
        seq = sequences[ep % len(sequences)]
        state = env.reset(sequence=seq)
        episode_reward = 0
        step = 0

        while True:
            action = agent.select_action(state)
            next_state, reward, done, info = env.step(action)
            agent.store_transition(state, action, reward, next_state, done)
            agent.train_step()
            episode_reward += reward
            state = next_state
            step += 1
            if done:
                break

        agent.update_epsilon()
        reward_window.append(episode_reward)
        if len(reward_window) > 100:
            reward_window.pop(0)
        avg_reward = np.mean(reward_window)

        # Only save best after warmup (agent needs time to learn)
        if ep >= 500 and avg_reward > best_avg_reward:
            best_avg_reward = avg_reward
            agent.save(os.path.join(save_dir, 'agent_best.pth'))

        if (ep + 1) % 100 == 0:
            print(f"    Ep {ep+1:>5}/{num_episodes} | "
                  f"Reward: {episode_reward:>7.1f} | "
                  f"Avg: {avg_reward:>7.2f} | "
                  f"Eps: {agent.epsilon:.4f}")

    agent.save(os.path.join(save_dir, 'agent_final.pth'))
    print(f"    Best avg reward: {best_avg_reward:.2f}")
    return agent


def main():
    print("=" * 70)
    print("ABLATION STUDY: Model Contribution Analysis")
    print("=" * 70)

    # ─── Define ablation configurations ───
    ablations = {
        'No AE':             {'ae': False, 'vae': True,  'trans': True,  'gnn': True},
        'No VAE':            {'ae': True,  'vae': False, 'trans': True,  'gnn': True},
        'No Transformer':    {'ae': True,  'vae': True,  'trans': False, 'gnn': True},
        'No GNN':            {'ae': True,  'vae': True,  'trans': True,  'gnn': False},
    }

    # ─── Load real models ONCE ───
    print("\n[1/4] Loading real models...")
    real_ae = AutoencoderLoader(variant='reg_ae_64', device='cpu')
    real_vae = VAELoader(variant='beta_vae', device='cpu')
    real_trans = TransformerLoader(device='cpu')
    try:
        real_gnn = GNNLoader(device='cpu')
    except Exception:
        real_gnn = DisabledGNN()

    # ─── Load training data ONCE ───
    print("\n[2/4] Loading training data...")

    # Synthetic sequences
    loader = APTDataLoader()
    loader.load_all()
    syn_sequences = loader.get_training_sequences(num_sequences=500)

    # Real sequences
    mal_merged, benign_df = load_real_data()
    real_sequences = build_real_sequences(mal_merged, benign_df, num_sequences=500, seed=42)

    train_sequences = syn_sequences + real_sequences
    np.random.shuffle(train_sequences)
    print(f"  Training sequences: {len(train_sequences)}")

    # Eval sequences (separate seed)
    eval_sequences = build_real_sequences(mal_merged, benign_df, num_sequences=500, benign_ratio=1.0, seed=999)
    print(f"  Eval sequences: {len(eval_sequences)}")

    # ─── Run each ablation ───
    print("\n[3/4] Running ablation experiments...")
    all_results = {}
    base_dir = os.path.join(os.path.dirname(__file__), 'outputs_ablation')
    os.makedirs(base_dir, exist_ok=True)

    for name, config in ablations.items():
        print(f"\n{'='*70}")
        print(f"  ABLATION: {name}")
        print(f"  AE={config['ae']}, VAE={config['vae']}, "
              f"Transformer={config['trans']}, GNN={config['gnn']}")
        print(f"{'='*70}")

        # Select real or disabled loaders
        ae = real_ae if config['ae'] else DisabledAE()
        vae = real_vae if config['vae'] else DisabledVAE()
        trans = real_trans if config['trans'] else DisabledTransformer()
        gnn = real_gnn if config['gnn'] else DisabledGNN()

        # Build GNN graph if enabled
        if config['gnn'] and hasattr(gnn, 'enabled') and gnn.enabled:
            build_gnn_graph(gnn)

        # Create environment with this config
        env = APTEnvironment(
            autoencoder_loader=ae,
            vae_loader=vae,
            transformer_loader=trans,
            gnn_loader=gnn,
        )

        # Train a fresh agent
        save_dir = os.path.join(base_dir, name.lower().replace(' ', '_').replace('(', '').replace(')', ''))
        print(f"\n  Training agent for '{name}'...")
        t0 = time.time()
        agent = train_agent(env, train_sequences, num_episodes=3000, save_dir=save_dir)
        train_time = time.time() - t0
        print(f"  Training done in {train_time:.1f}s")

        # Use the final trained agent (fully converged, epsilon=0.01)
        final_path = os.path.join(save_dir, 'agent_final.pth')
        eval_agent = DQNAgent(state_dim=APTEnvironment.STATE_DIM, action_dim=5)
        eval_agent.load(final_path)
        eval_agent.epsilon = 0.0  # Pure exploitation for evaluation

        # Evaluate
        print(f"  Evaluating on 2000 balanced episodes...")
        results = evaluate_with_predetection(eval_agent, env, eval_sequences, len(eval_sequences))

        all_results[name] = {
            'accuracy': results['accuracy'],
            'precision': results['precision'],
            'recall': results['recall'],
            'f1': results['f1'],
            'fpr': results['false_positive_rate'],
            'pre_detection_rate': results['pre_detection_rate'],
            'avg_steps': results['avg_steps_to_detection'],
            'train_time': train_time,
        }

        print(f"  Results: Acc={results['accuracy']:.1%} "
              f"Prec={results['precision']:.1%} "
              f"Rec={results['recall']:.1%} "
              f"F1={results['f1']:.3f} "
              f"FPR={results['false_positive_rate']:.1%} "
              f"PreDet={results['pre_detection_rate']:.1%}")

    # ─── Save results ───
    os.makedirs('./evaluation', exist_ok=True)
    with open('./evaluation/ablation_results.json', 'w') as f:
        json.dump(all_results, f, indent=2)

    # ─── Print comparison table ───
    print("\n\n" + "=" * 100)
    print("ABLATION STUDY RESULTS")
    print("=" * 100)
    print(f"{'Configuration':>20} | {'Accuracy':>9} | {'Precision':>9} | {'Recall':>8} | "
          f"{'F1':>7} | {'FPR':>7} | {'PreDet':>8} | {'Time':>6}")
    print("-" * 100)
    for name, r in all_results.items():
        print(f"{name:>20} | "
              f"{r['accuracy']:>8.1%} | "
              f"{r['precision']:>8.1%} | "
              f"{r['recall']:>7.1%} | "
              f"{r['f1']:>6.3f} | "
              f"{r['fpr']:>6.1%} | "
              f"{r['pre_detection_rate']:>7.1%} | "
              f"{r['train_time']:>5.0f}s")
    print("=" * 100)

    # ─── Plot ───
    print("\nGenerating ablation plot...")

    configs = list(all_results.keys())
    metrics = {
        'Accuracy':     [all_results[c]['accuracy'] * 100 for c in configs],
        'Precision':    [all_results[c]['precision'] * 100 for c in configs],
        'Recall':       [all_results[c]['recall'] * 100 for c in configs],
        'F1 Score':     [all_results[c]['f1'] * 100 for c in configs],
        'FPR':          [all_results[c]['fpr'] * 100 for c in configs],
        'Pre-Detection': [all_results[c]['pre_detection_rate'] * 100 for c in configs],
    }

    colors = {
        'Accuracy':      '#2ecc71',
        'Precision':     '#3498db',
        'Recall':        '#e74c3c',
        'F1 Score':      '#9b59b6',
        'FPR':           '#e67e22',
        'Pre-Detection': '#1abc9c',
    }

    fig, ax = plt.subplots(figsize=(16, 9))
    fig.patch.set_facecolor('#1a1a2e')
    ax.set_facecolor('#16213e')

    x = np.arange(len(configs))
    bar_width = 0.12
    offsets = np.arange(len(metrics)) - len(metrics) / 2 + 0.5

    for i, (metric_name, values) in enumerate(metrics.items()):
        bars = ax.bar(x + offsets[i] * bar_width, values,
                      bar_width, label=metric_name,
                      color=colors[metric_name], alpha=0.85,
                      edgecolor='white', linewidth=0.5)
        # Add value labels on bars
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                    f'{val:.1f}', ha='center', va='bottom',
                    fontsize=7, color='white', fontweight='bold')

    ax.set_xlabel('Model Configuration', fontsize=13, color='white', fontweight='bold')
    ax.set_ylabel('Metric Value (%)', fontsize=13, color='white', fontweight='bold')
    ax.set_title('Ablation Study: Impact of Removing Each Detection Model\n'
                 '(2000 balanced episodes per configuration)',
                 fontsize=14, color='white', fontweight='bold', pad=15)

    ax.set_xticks(x)
    short_labels = ['No AE', 'No VAE', 'No\nTransformer', 'No GNN']
    ax.set_xticklabels(short_labels, fontsize=11, color='white')
    ax.tick_params(axis='y', colors='white', labelsize=10)
    ax.set_ylim(0, 110)
    ax.grid(True, alpha=0.15, color='white', linestyle='--', axis='y')

    legend = ax.legend(loc='upper right', fontsize=10,
                        facecolor='#0f3460', edgecolor='white', framealpha=0.9)
    for text in legend.get_texts():
        text.set_color('white')

    plt.tight_layout()
    plot_path = './evaluation/ablation_study_plot.png'
    fig.savefig(plot_path, dpi=200, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    plt.close()

    print(f"Plot saved to {plot_path}")
    print("Done!")


if __name__ == '__main__':
    main()
