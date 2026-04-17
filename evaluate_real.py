"""
RL APT Detection System - Real Data Evaluation with Pre-Detection Stats (FIXED)
=================================================================================

Uses the CORRECT 55 feature columns and ACTUAL benign data for evaluation.
"""

import os
import sys
import json
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

from models.autoencoder_loader import AutoencoderLoader
from models.vae_loader import VAELoader
from models.transformer_loader import TransformerLoader
from models.gnn_loader import GNNLoader
from rl.dqn_agent import DQNAgent
from env.apt_env import APTEnvironment
from synthetic.data_loader import FEATURE_COLUMNS
from synthetic.real_data_loader import load_real_data, build_real_sequences, MACHINE_POOL

CKC_NAMES = {
    0: 'Benign',
    1: 'S1 Reconnaissance',
    2: 'S2 Weaponization',
    3: 'S3 Delivery',
    4: 'S4 Exploitation',
    5: 'S5 Installation',
    6: 'S6 Command & Control',
    7: 'S7 Actions on Obj.',
}


def evaluate_with_predetection(agent, env, sequences, num_episodes):
    """Evaluate with detailed pre-detection tracking."""
    results = {
        'total_episodes': 0,
        'total_attack_episodes': 0,
        'total_benign_episodes': 0,
        'true_positives': 0,
        'true_negatives': 0,
        'false_positives': 0,
        'false_negatives': 0,
        'rewards': [],
        'steps_to_detection': [],
        'detection_at_stage': {i: 0 for i in range(8)},
        'pre_detections': 0,
        'post_detections': 0,
        'action_distribution': {name: 0 for name in APTEnvironment.ACTION_NAMES.values()},
    }

    for ep in range(min(num_episodes, len(sequences))):
        seq = sequences[ep % len(sequences)]
        state = env.reset(sequence=seq)
        episode_reward = 0
        intervened = False
        intervention_step = None

        step = 0
        while True:
            old_eps = agent.epsilon
            agent.epsilon = 0.0
            action = agent.select_action(state)
            agent.epsilon = old_eps

            next_state, reward, done, info = env.step(action)
            episode_reward += reward
            results['action_distribution'][APTEnvironment.ACTION_NAMES[action]] += 1

            if action >= APTEnvironment.ACTION_ESCALATE and not intervened:
                intervened = True
                intervention_step = step

            state = next_state
            step += 1
            if done:
                break

        results['total_episodes'] += 1
        results['rewards'].append(episode_reward)

        is_attack = any(s > 0 for s in seq['ckc_stages'])
        ckc_stages = seq['ckc_stages']

        if is_attack:
            results['total_attack_episodes'] += 1
            if intervened:
                results['true_positives'] += 1
                results['steps_to_detection'].append(intervention_step)
                detected_stage = ckc_stages[min(intervention_step, len(ckc_stages) - 1)]
                results['detection_at_stage'][detected_stage] += 1
                if detected_stage < 5:
                    results['pre_detections'] += 1
                else:
                    results['post_detections'] += 1
            else:
                results['false_negatives'] += 1
        else:
            results['total_benign_episodes'] += 1
            if intervened:
                results['false_positives'] += 1
            else:
                results['true_negatives'] += 1

    tp = results['true_positives']
    fp = results['false_positives']
    fn = results['false_negatives']
    tn = results['true_negatives']
    total = tp + fp + fn + tn

    results['precision'] = tp / max(tp + fp, 1)
    results['recall'] = tp / max(tp + fn, 1)
    results['f1'] = 2 * results['precision'] * results['recall'] / max(results['precision'] + results['recall'], 1e-8)
    results['accuracy'] = (tp + tn) / max(total, 1)
    results['false_positive_rate'] = fp / max(fp + tn, 1)
    results['avg_reward'] = float(np.mean(results['rewards']))
    results['avg_steps_to_detection'] = float(np.mean(results['steps_to_detection'])) if results['steps_to_detection'] else 0
    results['pre_detection_rate'] = results['pre_detections'] / max(tp, 1)
    results['post_detection_rate'] = results['post_detections'] / max(tp, 1)

    return results


def print_results(results):
    tp = results['true_positives']
    fp = results['false_positives']
    fn = results['false_negatives']
    tn = results['true_negatives']

    print("\n" + "=" * 70)
    print("REAL DATA EVALUATION RESULTS")
    print("=" * 70)

    print(f"\n  Total Episodes:    {results['total_episodes']}")
    print(f"  Attack Episodes:   {results['total_attack_episodes']}")
    print(f"  Benign Episodes:   {results['total_benign_episodes']}")

    print(f"\n  --- Confusion Matrix ---")
    print(f"                     Predicted Attack  Predicted Benign")
    print(f"  Actual Attack      TP = {tp:>5}         FN = {fn:>5}")
    print(f"  Actual Benign      FP = {fp:>5}         TN = {tn:>5}")

    print(f"\n  --- Core Metrics ---")
    print(f"  Accuracy:          {results['accuracy']:.1%}")
    print(f"  Precision:         {results['precision']:.1%}")
    print(f"  Recall:            {results['recall']:.1%}")
    print(f"  F1 Score:          {results['f1']:.3f}")
    print(f"  False Positive Rate: {results['false_positive_rate']:.1%}")

    print(f"\n  --- PRE-DETECTION STATS (Agent's Core Mission) ---")
    print(f"  Total Attacks Detected:     {tp}")
    print(f"  Pre-detected (before S5):   {results['pre_detections']} ({results['pre_detection_rate']:.1%})")
    print(f"  Post-detected (S5+):        {results['post_detections']} ({results['post_detection_rate']:.1%})")
    print(f"  Missed Attacks:             {fn}")
    print(f"  Avg Steps to Detection:     {results['avg_steps_to_detection']:.1f} / 7")

    print(f"\n  --- Detection by CKC Stage ---")
    for stage in range(8):
        count = results['detection_at_stage'][stage]
        if count > 0:
            pct = count / max(tp, 1) * 100
            bar = '#' * int(pct / 2)
            print(f"    {CKC_NAMES.get(stage, f'Stage {stage}'):25s}: {count:4d} ({pct:5.1f}%) {bar}")

    print(f"\n  --- Action Distribution ---")
    total_actions = sum(results['action_distribution'].values())
    for action_name, count in results['action_distribution'].items():
        pct = count / max(total_actions, 1) * 100
        bar = '#' * int(pct / 2)
        print(f"    {action_name:20s}: {count:5d} ({pct:5.1f}%) {bar}")

    print(f"\n  --- Reward ---")
    print(f"  Average Reward:    {results['avg_reward']:.2f}")
    print("=" * 70)


def main():
    print("\n" + "=" * 70)
    print("RL APT DETECTION - REAL DATA EVALUATION (FIXED)")
    print("=" * 70)

    agent_path = os.path.join(os.path.dirname(__file__), 'outputs', 'agent_best.pth')

    # Load models
    print("\n[1/5] Loading detection models...")
    ae_loader = AutoencoderLoader(variant='reg_ae_64', device='cpu')
    vae_loader = VAELoader(variant='beta_vae', device='cpu')
    transformer_loader = TransformerLoader(device='cpu')

    try:
        gnn_loader = GNNLoader(device='cpu')
    except Exception as e:
        print(f"[GNN] Warning: {e}")
        gnn_loader = None

    # Build GNN graph using correct features
    if gnn_loader is not None and gnn_loader.enabled:
        print("\n[2/5] Building GNN graph...")
        feat_df = pd.read_parquet(os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'feature_selection_outputs2', 'feature_matrix_no_leakage.parquet'))
        labels_df = pd.read_parquet(os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'feature_selection_outputs2', 'labels.parquet'))
        mal_mask = labels_df['malicious'] == 1
        mal_features = feat_df.loc[mal_mask].reset_index(drop=True)

        # Build full 55-col matrix using CORRECT features
        feat_matrix = np.zeros((len(mal_features), len(FEATURE_COLUMNS)), dtype=np.float32)
        for i, col in enumerate(FEATURE_COLUMNS):
            if col in mal_features.columns:
                feat_matrix[:, i] = mal_features[col].values.astype(np.float32)

        gnn_df = pd.DataFrame()
        gnn_df['timestamp'] = pd.Timestamp('2024-01-01') + pd.to_timedelta(np.arange(len(mal_features)), unit='min')
        gnn_df['machine_name'] = np.random.choice(MACHINE_POOL, size=len(mal_features))
        gnn_df['src_user'] = 'user1'
        gnn_df['src_ip'] = '192.168.1.1'
        gnn_loader.build_graph(gnn_df, feat_matrix)
        gnn_loader.run_inference(gnn_df)

    # Create environment
    env = APTEnvironment(
        autoencoder_loader=ae_loader,
        vae_loader=vae_loader,
        transformer_loader=transformer_loader,
        gnn_loader=gnn_loader,
    )

    # Load agent
    print(f"\n[3/5] Loading agent from {agent_path}...")
    agent = DQNAgent(state_dim=APTEnvironment.STATE_DIM, action_dim=5)
    if os.path.exists(agent_path):
        agent.load(agent_path)
        print("  Agent loaded successfully")
    else:
        print(f"  WARNING: {agent_path} not found!")

    # Build real sequences with ACTUAL benign data
    print("\n[4/5] Building evaluation sequences from real data...")
    mal_merged, benign_df = load_real_data()
    # 1000 attacks + 1000 benign (ratio=1.0) = 2000 total sequences, perfectly equal
    sequences = build_real_sequences(mal_merged, benign_df, num_sequences=1000, benign_ratio=1.0, seed=999)

    # Evaluate
    print("\n[5/5] Evaluating on real data...")
    results = evaluate_with_predetection(agent, env, sequences, len(sequences))
    print_results(results)

    # Save
    os.makedirs('./evaluation', exist_ok=True)
    save_results = {k: v for k, v in results.items()
                    if k not in ['rewards', 'steps_to_detection']}
    with open('./evaluation/real_data_evaluation.json', 'w') as f:
        json.dump(save_results, f, indent=2)
    print(f"\nReport saved to ./evaluation/real_data_evaluation.json")


if __name__ == '__main__':
    main()
