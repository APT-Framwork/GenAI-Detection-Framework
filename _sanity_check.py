"""Quick sanity check on the evaluation results."""
import os, sys, json
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

# Load the saved results
with open('./evaluation/real_data_evaluation.json') as f:
    results = json.load(f)

print("=" * 60)
print("SANITY CHECK ON RESULTS")
print("=" * 60)

# Check 1: Are "benign" sequences actually benign?
print("\n1. BENIGN SEQUENCE PROBLEM:")
print("   The 'benign' sequences used S1/S3 MALICIOUS alert features")
print("   but labeled them as ckc_stage=0 (benign).")
print("   These are NOT real benign traffic - they're malicious!")
print("   -> FPR is unreliable (those 'false positives' are probably correct!)")

# Check 2: Feature padding
print("\n2. FEATURE PADDING ISSUE:")
print("   Only 42/55 features found in real data parquet")
print("   13 features padded with zeros")
print("   If AE was trained with those 13 features as non-zero,")
print("   reconstruction error will be ALWAYS high -> everything looks anomalous")

# Check 3: Verify with AE/VAE what they actually see
from models.autoencoder_loader import AutoencoderLoader
from models.vae_loader import VAELoader
from synthetic.real_data_loader import load_real_data, build_real_sequences, FEATURE_COLUMNS

print("\n3. MODEL OUTPUT CHECK:")
ae_loader = AutoencoderLoader(variant='reg_ae_64', device='cpu')
vae_loader = VAELoader(variant='beta_vae', device='cpu')

# Load real data
real_merged = load_real_data()
seqs = build_real_sequences(real_merged, num_sequences=20, seed=999)

# Check what AE and VAE output for attack vs "benign"
attack_seqs = [s for s in seqs if s['label'] == 1]
benign_seqs = [s for s in seqs if s['label'] == 0]

print(f"\n   Attack sequences: {len(attack_seqs)}")
print(f"   Benign sequences: {len(benign_seqs)}")

# Test on first steps of attack sequences
ae_scores_atk = []
vae_probs_atk = []
for s in attack_seqs[:10]:
    feat = s['features'][0:1]  # First step
    ae_r = ae_loader.get_anomaly_score(feat)
    vae_r = vae_loader.get_malicious_probability(feat)
    ae_scores_atk.append(float(ae_r['anomaly_score'][0]))
    vae_probs_atk.append(float(vae_r['malicious_probability'][0]))

# Test on benign sequences
ae_scores_ben = []
vae_probs_ben = []
for s in benign_seqs[:10]:
    feat = s['features'][0:1]
    ae_r = ae_loader.get_anomaly_score(feat)
    vae_r = vae_loader.get_malicious_probability(feat)
    ae_scores_ben.append(float(ae_r['anomaly_score'][0]))
    vae_probs_ben.append(float(vae_r['malicious_probability'][0]))

print(f"\n   AE anomaly scores (attack steps): {[f'{s:.3f}' for s in ae_scores_atk]}")
print(f"   AE anomaly scores ('benign' steps): {[f'{s:.3f}' for s in ae_scores_ben]}")
print(f"   -> Attack mean: {np.mean(ae_scores_atk):.4f}, Benign mean: {np.mean(ae_scores_ben):.4f}")

print(f"\n   VAE malicious prob (attack steps): {[f'{p:.3f}' for p in vae_probs_atk]}")
print(f"   VAE malicious prob ('benign' steps): {[f'{p:.3f}' for p in vae_probs_ben]}")
print(f"   -> Attack mean: {np.mean(vae_probs_atk):.4f}, Benign mean: {np.mean(vae_probs_ben):.4f}")

# Check 4: Are attack and benign features actually different?
print(f"\n4. FEATURE SIMILARITY CHECK:")
if attack_seqs and benign_seqs:
    atk_feat = np.mean([s['features'][0] for s in attack_seqs[:10]], axis=0)
    ben_feat = np.mean([s['features'][0] for s in benign_seqs[:10]], axis=0)
    cosine_sim = np.dot(atk_feat, ben_feat) / (np.linalg.norm(atk_feat) * np.linalg.norm(ben_feat) + 1e-8)
    l2_dist = np.linalg.norm(atk_feat - ben_feat)
    print(f"   Cosine similarity between attack/benign features: {cosine_sim:.4f}")
    print(f"   L2 distance: {l2_dist:.4f}")
    print(f"   (If cosine_sim > 0.95, features are very similar -> poor separation)")

# Check 5: Does agent always escalate regardless of input?
print(f"\n5. BIAS CHECK - Does agent always escalate?")
print(f"   Action distribution: {results['action_distribution']}")
total_actions = sum(results['action_distribution'].values())
escalate_pct = (results['action_distribution']['Escalate to SOC'] + 
                results['action_distribution']['Isolate Host'] + 
                results['action_distribution']['Block User/IP']) / total_actions * 100
print(f"   Intervention rate: {escalate_pct:.1f}% of all steps")
print(f"   If >50%, agent may be blindly escalating everything")

print("\n" + "=" * 60)
