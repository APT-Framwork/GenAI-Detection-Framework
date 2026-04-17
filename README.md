# RL-based APT Detection and Response System

🎯 **Reinforcement Learning for Early APT Detection using Multi-Model Ensemble**

This system implements a Deep Q-Network (DQN) agent that learns optimal defensive actions against Advanced Persistent Threat (APT) attacks. The agent combines outputs from four specialized deep learning models (Autoencoder, Beta-VAE, Transformer, GNN) to make real-time intervention decisions mapped to the Cyber Kill Chain.

---

## 🏗️ System Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│                    WAZUH SIEM ALERTS                                │
│              (55-dim feature vectors per alert)                     │
└──────────────────────────┬─────────────────────────────────────────┘
                           │
      ┌──────────┬─────────┴─────────┬──────────┐
      ▼          ▼                   ▼          ▼
┌──────────┐ ┌──────────┐   ┌───────────┐ ┌──────────┐
│Autoencoder│ │ Beta-VAE │   │Transformer│ │   GNN    │
│ anomaly   │ │ malicious│   │ next CKC  │ │ lateral  │
│ score     │ │ prob.    │   │ stage     │ │ movement │
└─────┬────┘ └─────┬────┘   └─────┬─────┘ └─────┬────┘
      │            │              │              │
      └──────┬─────┴──────┬───────┴──────┬───────┘
             ▼            ▼              ▼
      ┌──────────────────────────────────────────┐
      │  RL Environment  (13-dim state vector)   │
      └─────────────────┬────────────────────────┘
                        ▼
      ┌──────────────────────────────────────────┐
      │  DQN Agent → 5 Actions                   │
      │  Monitor | Alert | Escalate |             │
      │  Isolate Host | Block User/IP             │
      └──────────────────────────────────────────┘
```

---

## 📋 Table of Contents

- [Key Concepts](#-key-concepts)
- [Project Structure](#-project-structure)
- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [System Components](#-system-components)
- [Training](#-training)
- [Evaluation](#-evaluation)
- [Results](#-results)
- [Ablation Study](#-ablation-study)

---

## 🎓 Key Concepts

### 1. **Four Pre-trained Detection Models**

Each model analyzes the same 55-dim alert features from a different perspective:

| Model | Architecture | Output | Purpose |
|:---|:---|:---|:---|
| **Autoencoder** | RegularizedAE (55→64→55) | anomaly_score, reconstruction_error | Detect unusual alerts |
| **Beta-VAE** | VAE (55→32→55) | malicious_probability, uncertainty | Estimate malicious likelihood |
| **Transformer** | 4-layer Encoder (64→128→8) | predicted_next_stage, confidence | Anticipate next attack stage |
| **GNN** | 3-layer GraphSAGE (55→128→1) | node_risk, neighbor_risk, risk_growth | Detect lateral movement |

⚠️ **These models are pre-trained and frozen** — they provide detection signals to the RL agent.

### 2. **Feature Engineering (25 features → 55 columns)**

Raw Wazuh SIEM alerts are transformed into 55-dimensional vectors:
- **32 columns**: SecBERT embeddings (log message + command) reduced via PCA to 16 dims each
- **4 columns**: Numerical features (firedtimes, cmd_length, path_depth, etc.)
- **19 columns**: Binary flags (decoder type, location, syscheck events, etc.)

### 3. **RL Problem Definition**

**State Space** (13 features from 4 models + temporal context):
```python
[
    anomaly_score,              # Autoencoder
    reconstruction_error,       # Autoencoder
    malicious_probability,      # Beta-VAE
    uncertainty,                # Beta-VAE
    predicted_next_ckc_stage,   # Transformer
    prediction_confidence,      # Transformer
    current_ckc_stage,          # Context
    time_since_first_event,     # Temporal
    time_since_last_event,      # Temporal
    sequence_length_so_far,     # Counter
    gnn_node_risk,              # GNN
    gnn_neighbor_risk,          # GNN
    gnn_risk_growth             # GNN
]
```

**Action Space** (5 discrete actions):
| Action | Name | Description |
|:---:|:---|:---|
| 0 | Monitor | Continue observing |
| 1 | Low Alert | Flag for review |
| 2 | Escalate to SOC | Alert security team |
| 3 | Isolate Host | Network-isolate machine |
| 4 | Block User/IP | Block suspicious actor |

**Reward Function** (strongly prioritizes early detection):
- Correct intervention at S1-S2: **+15** | S3: **+10** | S4: **+7** | S5: **+3**
- Too late (S6-S7): **0 to -2**
- False positive: **-2 to -3**
- Missed attack (end of episode): **-15**

### 4. **DQN Algorithm**

- **Q-Network**: Input(13) → Hidden(128,64) → Output(5 Q-values)
- **Experience Replay**: Buffer of 10,000 transitions, mini-batch size 64
- **Target Network**: Updated every 100 steps for stable learning
- **Epsilon-Greedy**: 1.0 → 0.01 (decay 0.995 per episode)

---

## 📁 Project Structure

```
RL_agent/
│
├── models/                          # Pre-trained model loaders
│   ├── autoencoder_loader.py        # RegularizedAE (anomaly detection)
│   ├── vae_loader.py                # Beta-VAE (malicious probability)
│   ├── transformer_loader.py        # CKC stage predictor
│   └── gnn_loader.py               # GraphSAGE (lateral movement)
│
├── synthetic/                       # Data loading & sequences
│   ├── data_loader.py              # Feature columns + dataset loader
│   └── real_data_loader.py         # Variable-length sequence construction
│
├── env/                             # RL environment
│   └── apt_env.py                   # 13-dim state, 5 actions, rewards
│
├── rl/                              # RL agent
│   └── dqn_agent.py                 # DQN with replay buffer + target net
│
├── outputs/                         # Production agent
│   └── agent_best.pth              # Best trained model (3,000 episodes)
│
├── outputs_ablation/                # Ablation study agents
│   ├── no_ae/                       # Trained without Autoencoder
│   ├── no_vae/                      # Trained without VAE
│   ├── no_transformer/              # Trained without Transformer
│   └── no_gnn/                      # Trained without GNN
│
├── evaluation/                      # Results & plots
│   ├── ablation_study_plot.png
│   ├── metric_scaling_plot.png
│   └── *.json
│
├── train.py                         # Training script
├── evaluate_real.py                 # Real data evaluation
├── evaluate_scaling.py              # Scaling test (1K-10K episodes)
├── ablation_study.py                # Ablation analysis
├── AGENT_ARCHITECTURE.md            # Detailed architecture guide
└── ARCHITECTURE.md                  # Architecture diagrams
```

---

## 🔧 Installation

### Prerequisites

- Python 3.8+
- PyTorch 1.10+

### Install Dependencies

```bash
pip install torch numpy pandas matplotlib scikit-learn
pip install torch_geometric  # For GNN (optional)
```

### Verify Pre-trained Models

Model weights are stored in `data/`:
```
data/reg_ae_top25_features.pth           # Autoencoder
data/beta_vae_top25_features.pth         # Beta-VAE
data/transformer_next_step_prediction_top25.pth  # Transformer
data/gnn_propagation_best_no_rule.pth    # GNN
```

---

## 🚀 Quick Start

### 1. Train the RL Agent

```bash
python train.py --num_episodes 3000 --device cpu --output_dir ./outputs
```

### 2. Evaluate on Real Data

```bash
python evaluate_real.py --total_episodes 2000
```

### 3. Run Ablation Study

```bash
python ablation_study.py
```

### 4. Run Scaling Test

```bash
python evaluate_scaling.py
```

---

## 🧩 System Components

### Model Loaders

```python
from models.autoencoder_loader import AutoencoderLoader
from models.vae_loader import VAELoader
from models.transformer_loader import TransformerLoader
from models.gnn_loader import GNNLoader

ae = AutoencoderLoader(variant='reg_ae_64', device='cpu')
vae = VAELoader(variant='beta_vae', device='cpu')
trans = TransformerLoader(device='cpu')
gnn = GNNLoader(device='cpu')
```

### Environment

```python
from env.apt_env import APTEnvironment

env = APTEnvironment(
    autoencoder_loader=ae,
    vae_loader=vae,
    transformer_loader=trans,
    gnn_loader=gnn,
    max_steps=50
)

state = env.reset(sequence)                    # 13-dim state
next_state, reward, done, info = env.step(action)
```

### DQN Agent

```python
from rl.dqn_agent import DQNAgent

agent = DQNAgent(state_dim=13, action_dim=5, device='cpu')

action = agent.select_action(state, training=True)
agent.store_transition(state, action, reward, next_state, done)
agent.train_step()
```

---

## 📊 Training

### Training Data Sources

| Source | Sequences | Steps | Description |
|:---|:---:|:---:|:---|
| Synthetic (ReALTabFormer) | 500 | 7 each | Generated tabular data |
| Real (Wazuh alerts) | 600 | 5-30 each | Time-ordered attack chains |
| **Total** | **1,100** | Variable | Mixed and shuffled |

### Training Loop

```python
for episode in range(3000):
    sequence = random.choice(training_sequences)
    state = env.reset(sequence)
    while not done:
        action = agent.select_action(state)
        next_state, reward, done, info = env.step(action)
        agent.store_transition(state, action, reward, next_state, done)
        agent.train_step()
        state = next_state
    agent.update_epsilon()
```

---

## 📈 Results

### Production Agent Performance (10K episode scaling test)

| Metric | Value |
|:---|:---:|
| **Accuracy** | 84.1% |
| **Precision** | 83.4% |
| **Recall** | 85.0% |
| **F1 Score** | 0.842 |
| **False Positive Rate** | 16.9% |
| **Pre-Detection Rate** | 81.0% |

> **Pre-Detection Rate**: % of attacks stopped before S5 (Installation).

---

## 🔬 Ablation Study

Each row removes one model and retrains from scratch:

| Configuration | Accuracy | FPR | Pre-Detection |
|:---|:---:|:---:|:---:|
| **Full (All 4 Models)** | **84.1%** | **16.9%** | **81.0%** |
| No AE | 75.0% | 43.6% | 81.8% |
| No VAE | 72.3% | 52.0% | 96.3% |
| No Transformer | 73.7% | 47.4% | 78.9% |
| No GNN | 72.5% | 51.6% | 81.6% |

**Key finding**: All 4 models are essential. Removing any one causes accuracy to drop ~10% and FPR to increase 3×.

---

## 📚 References

1. **DQN**: Mnih et al. "Playing Atari with Deep Reinforcement Learning" (2013)
2. **Cyber Kill Chain**: Lockheed Martin "Intelligence-Driven Computer Network Defense" (2011)
3. **ReALTabFormer**: Solatorio & Dupriez "REaLTabFormer: Generating Realistic Relational and Tabular Data using Transformers" (2023)
4. **GraphSAGE**: Hamilton et al. "Inductive Representation Learning on Large Graphs" (2017)

---

**Year**: 2024-2025

📄 *This project is for academic purposes.*
