"""
Automated Scaling Evaluation
==============================
Runs the RL agent evaluation at increasing episode counts (1000 → 10000)
and plots the metric evolution to analyze performance stability.
"""

import os
import sys
import json
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
from synthetic.data_loader import FEATURE_COLUMNS
from synthetic.real_data_loader import load_real_data, build_real_sequences, MACHINE_POOL
from evaluate_real import evaluate_with_predetection


def main():
    print("=" * 70)
    print("AUTOMATED SCALING EVALUATION (1000 -> 10000 episodes)")
    print("=" * 70)

    # ─── Load models ONCE (expensive, don't repeat) ───
    print("\n[1/3] Loading models (one-time)...")
    ae_loader = AutoencoderLoader(variant='reg_ae_64', device='cpu')
    vae_loader = VAELoader(variant='beta_vae', device='cpu')
    transformer_loader = TransformerLoader(device='cpu')

    try:
        gnn_loader = GNNLoader(device='cpu')
    except Exception as e:
        print(f"[GNN] Warning: {e}")
        gnn_loader = None

    # Build GNN graph ONCE
    if gnn_loader is not None and gnn_loader.enabled:
        print("  Building GNN graph...")
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

    env = APTEnvironment(
        autoencoder_loader=ae_loader,
        vae_loader=vae_loader,
        transformer_loader=transformer_loader,
        gnn_loader=gnn_loader,
    )

    agent_path = os.path.join(os.path.dirname(__file__), 'outputs', 'agent_best.pth')
    agent = DQNAgent(state_dim=APTEnvironment.STATE_DIM, action_dim=5)
    if os.path.exists(agent_path):
        agent.load(agent_path)
        print("  Agent loaded.")
    else:
        print(f"  WARNING: {agent_path} not found!")
        return

    # Load real data ONCE
    print("\n[2/3] Loading real data (one-time)...")
    mal_merged, benign_df = load_real_data()

    # ─── Sweep episode counts ───
    episode_counts = [1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000]

    tracked_metrics = {
        'Accuracy': [],
        'Precision': [],
        'Recall': [],
        'F1 Score': [],
        'FPR': [],
        'Pre-Detection Rate': [],
    }

    all_results = []

    print("\n[3/3] Running evaluation sweep...")
    print("-" * 70)

    for total_ep in episode_counts:
        attack_count = total_ep // 2
        print(f"\n>>> Evaluating {total_ep} episodes "
              f"({attack_count} attack + {attack_count} benign)...")

        sequences = build_real_sequences(
            mal_merged, benign_df,
            num_sequences=attack_count,
            benign_ratio=1.0,
            seed=999,
        )

        results = evaluate_with_predetection(agent, env, sequences, len(sequences))

        tracked_metrics['Accuracy'].append(results['accuracy'] * 100)
        tracked_metrics['Precision'].append(results['precision'] * 100)
        tracked_metrics['Recall'].append(results['recall'] * 100)
        tracked_metrics['F1 Score'].append(results['f1'] * 100)
        tracked_metrics['FPR'].append(results['false_positive_rate'] * 100)
        tracked_metrics['Pre-Detection Rate'].append(results['pre_detection_rate'] * 100)

        print(f"    Accuracy={results['accuracy']:.1%}  "
              f"Precision={results['precision']:.1%}  "
              f"Recall={results['recall']:.1%}  "
              f"F1={results['f1']:.3f}  "
              f"FPR={results['false_positive_rate']:.1%}  "
              f"PreDet={results['pre_detection_rate']:.1%}")

        all_results.append({
            'total_episodes': total_ep,
            'attack_episodes': results['total_attack_episodes'],
            'benign_episodes': results['total_benign_episodes'],
            'accuracy': results['accuracy'],
            'precision': results['precision'],
            'recall': results['recall'],
            'f1': results['f1'],
            'fpr': results['false_positive_rate'],
            'pre_detection_rate': results['pre_detection_rate'],
            'true_positives': results['true_positives'],
            'false_positives': results['false_positives'],
            'false_negatives': results['false_negatives'],
            'true_negatives': results['true_negatives'],
            'avg_steps_to_detection': results['avg_steps_to_detection'],
        })

    # ─── Save raw results ───
    os.makedirs('./evaluation', exist_ok=True)
    with open('./evaluation/scaling_results.json', 'w') as f:
        json.dump(all_results, f, indent=2)
    print(f"\nRaw results saved to ./evaluation/scaling_results.json")

    # ─── Plot ───
    print("\nGenerating plot...")

    colors = {
        'Accuracy':            '#2ecc71',  # green
        'Precision':           '#3498db',  # blue
        'Recall':              '#e74c3c',  # red
        'F1 Score':            '#9b59b6',  # purple
        'FPR':                 '#e67e22',  # orange
        'Pre-Detection Rate':  '#1abc9c',  # teal
    }

    fig, ax = plt.subplots(figsize=(14, 8))
    fig.patch.set_facecolor('#1a1a2e')
    ax.set_facecolor('#16213e')

    for metric_name, values in tracked_metrics.items():
        color = colors[metric_name]
        ax.plot(episode_counts, values,
                marker='o', linewidth=2.5, markersize=8,
                color=color, label=metric_name,
                markeredgecolor='white', markeredgewidth=1.2)

        # Annotate final value
        ax.annotate(f'{values[-1]:.1f}%',
                     xy=(episode_counts[-1], values[-1]),
                     xytext=(10, 0), textcoords='offset points',
                     fontsize=9, color=color, fontweight='bold')

    ax.set_xlabel('Total Evaluation Episodes', fontsize=13, color='white', fontweight='bold')
    ax.set_ylabel('Metric Value (%)', fontsize=13, color='white', fontweight='bold')
    ax.set_title('RL APT Agent — Metric Stability Across Evaluation Scale\n'
                 '(Balanced 50/50 Attack vs Benign, Variable-Length Sequences)',
                 fontsize=14, color='white', fontweight='bold', pad=15)

    ax.set_xticks(episode_counts)
    ax.set_xticklabels([f'{x//1000}K' for x in episode_counts],
                        fontsize=10, color='white')
    ax.tick_params(axis='y', colors='white', labelsize=10)

    ax.set_ylim(0, 105)
    ax.grid(True, alpha=0.2, color='white', linestyle='--')

    legend = ax.legend(loc='lower left', fontsize=11,
                        facecolor='#0f3460', edgecolor='white',
                        framealpha=0.9)
    for text in legend.get_texts():
        text.set_color('white')

    plt.tight_layout()
    plot_path = './evaluation/metric_scaling_plot.png'
    fig.savefig(plot_path, dpi=200, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    plt.close()

    print(f"Plot saved to {plot_path}")

    # ─── Print summary table ───
    print("\n" + "=" * 90)
    print(f"{'Episodes':>10} | {'Accuracy':>9} | {'Precision':>9} | {'Recall':>8} | "
          f"{'F1':>7} | {'FPR':>7} | {'PreDet':>8}")
    print("-" * 90)
    for r in all_results:
        print(f"{r['total_episodes']:>10} | "
              f"{r['accuracy']:>8.1%} | "
              f"{r['precision']:>8.1%} | "
              f"{r['recall']:>7.1%} | "
              f"{r['f1']:>6.3f} | "
              f"{r['fpr']:>6.1%} | "
              f"{r['pre_detection_rate']:>7.1%}")
    print("=" * 90)
    print("\nDone!")


if __name__ == '__main__':
    main()
