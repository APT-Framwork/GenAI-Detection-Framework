# RL-based APT Detection and Response System

🎯 **Master-Level Implementation of Reinforcement Learning for Early APT Detection**

This project implements a sophisticated Reinforcement Learning system that learns optimal defensive actions against Advanced Persistent Threat (APT) attacks mapped to the Cyber Kill Chain (CKC). The system uses pre-trained deep learning models for detection and an RL agent (DQN) for decision-making.

---

## 🏗️ System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    RL-BASED APT DETECTION SYSTEM                 │
└─────────────────────────────────────────────────────────────────┘

┌──────────────────┐     ┌──────────────────┐     ┌──────────────┐
│  Pre-trained     │     │   Synthetic      │     │    RL Agent  │
│  Detection       │────▶│   Meta-Seq       │────▶│    (DQN)     │
│  Models          │     │   Generator      │     │              │
└──────────────────┘     └──────────────────┘     └──────────────┘
      │                          │                        │
      │ Autoencoder             │ ReALTabFormer          │ Q-Network
      │ VAE                     │ + Time Synthesis       │ Experience
      │ Transformer             │                        │ Replay
      │                          │                        │
      └───────────────────┬──────┴────────────────────────┘
                          ▼
                ┌──────────────────────┐
                │  Conditional Replay  │
                │  (Meta → Features)   │
                └──────────────────────┘
                          │
                          ▼
                ┌──────────────────────┐
                │   APT Environment    │
                │   (Gym-style)        │
                └──────────────────────┘
```

---

## 📋 Table of Contents

- [Key Concepts](#-key-concepts)
- [Project Structure](#-project-structure)
- [Installation](#-installation)
- [Quick Start](#-quick-start)
- [Detailed Usage](#-detailed-usage)
- [System Components](#-system-components)
- [Training](#-training)
- [Evaluation](#-evaluation)
- [Academic Explanation](#-academic-explanation)
- [Results](#-results)
- [Troubleshooting](#-troubleshooting)

---

## 🎓 Key Concepts

### 1. **Pre-trained Detection Models (DO NOT RETRAIN)**

Three models provide detection signals:

- **Autoencoder (AE)**: Anomaly detection via reconstruction error
- **VAE**: Malicious probability estimation (trained on benign data only)
- **Transformer**: Next CKC stage prediction from event sequences

⚠️ **Critical**: These models require **full original feature vectors** (200+ features).

### 2. **Synthetic Meta-Sequence Generation**

ReALTabFormer generates **high-level metadata** only:
- CKC stage progression (S1 → S2 → S3 → ... → S7)
- Event indices
- Synthetic time deltas

**Why meta-level?** ReALTabFormer was trained on 20 high-level columns, not 200+ raw SIEM features.

### 3. **Conditional Replay (CRITICAL INNOVATION)**

Maps synthetic meta-sequences to real feature vectors:

```python
For each (ckc_stage, time) in meta-sequence:
    1. Query real dataset for events with matching CKC stage
    2. Sample a real event
    3. Inject synthetic time information
    4. Return full feature vector → feed to detection models
```

**Why?** Ensures:
- ✅ Correct dimensionality
- ✅ Realistic features
- ✅ Controlled sequence progression
- ✅ No retraining needed

### 4. **RL Problem Definition**

**Environment**: Custom Gym-style APT environment
- One episode = one attack sequence
- Step-by-step progression through CKC stages

**State Space** (10 features):
```python
[
    anomaly_score,              # Autoencoder
    reconstruction_error,       # Autoencoder
    malicious_probability,      # VAE
    uncertainty,                # VAE
    predicted_next_ckc_stage,   # Transformer
    prediction_confidence,      # Transformer
    current_ckc_stage,          # Environment
    time_since_first_event,     # Environment
    time_since_last_event,      # Environment
    sequence_length_so_far      # Environment
]
```

**Action Space** (5 discrete actions):
- 0: Monitor (continue observation)
- 1: Low Alert (log suspicious activity)
- 2: Escalate to SOC (notify security team)
- 3: Isolate Host (disconnect system)
- 4: Block User/IP (block network access)

**Reward Function** (prioritizes early detection):
```python
Correct response at S1-S3 → +5   (early stages, high reward)
Correct response at S4-S5 → +2   (mid stages, medium reward)
Correct response at S7 → 0       (too late, no reward)
False negative → -10              (missed attack, large penalty)
False positive → -1               (alert fatigue)
Overreaction too early → -2      (aggressive action at S1-S2)
```

### 5. **DQN Algorithm**

- **Q-Network**: Approximates Q(s,a) - expected future reward
- **Experience Replay**: Store transitions, sample mini-batches
- **Target Network**: Stabilize Q-value targets
- **Epsilon-Greedy**: Balance exploration vs exploitation

---

## 📁 Project Structure

```
rl_apt_system/
│
├── models/                          # Pre-trained model loaders
│   ├── autoencoder_loader.py        # Autoencoder wrapper
│   ├── vae_loader.py                # VAE wrapper
│   └── transformer_loader.py        # Transformer wrapper
│
├── synthetic/                       # Synthetic data generation
│   ├── meta_sequence_generator.py   # Generate APT meta-sequences
│   └── conditional_replay.py        # Map meta-seq to features
│
├── env/                             # RL environment
│   └── apt_env.py                   # Gym-style APT environment
│
├── rl/                              # RL agent
│   └── dqn_agent.py                 # DQN implementation
│
├── data/                            # Data storage
│   ├── real_sequences/              # Real attack sequences
│   └── synthetic_meta_sequences/    # Generated meta-sequences
│
├── train.py                         # Training script
├── evaluate.py                      # Evaluation script
└── README.md                        # This file
```

---

## 🔧 Installation

### Prerequisites

- Python 3.8+
- PyTorch 1.10+
- CUDA (optional, for GPU acceleration)

### Step 1: Install Dependencies

```bash
pip install torch torchvision numpy pandas matplotlib seaborn scikit-learn gym tqdm
```

### Step 2: Install Transformers (for ReALTabFormer, optional)

```bash
pip install transformers
```

### Step 3: Verify Pre-trained Models

Ensure the following models are available:

```
../autoencoder_outputs/autoencoder_anomaly_detection.pth
../vae_anomaly_detector_outputs/vae_anomaly_detector.pth
../transformer_outputs/transformer_next_step_prediction.pth
```

### Step 4: Verify Real Data

Ensure real SIEM data is available:

```
../combined_dataset_final.xlsx
```

---

## 🚀 Quick Start

### 1. Train the RL Agent

```bash
python train.py \
    --data_path ../combined_dataset_final.xlsx \
    --num_episodes 500 \
    --device cuda \
    --output_dir ./outputs
```

### 2. Evaluate the Agent

```bash
python evaluate.py \
    --agent_path ./outputs/agent_final.pth \
    --num_episodes 100 \
    --device cuda \
    --output_dir ./evaluation
```

### 3. View Results

```bash
# Training curves
open outputs/training_curves.png

# Evaluation report
cat evaluation/evaluation_report.txt

# Evaluation plots
open evaluation/evaluation_results.png
```

---

## 📖 Detailed Usage

### Training Options

```bash
python train.py --help
```

**Key Parameters:**

- `--num_episodes`: Number of training episodes (default: 500)
- `--batch_size`: DQN batch size (default: 64)
- `--learning_rate`: Learning rate (default: 1e-4)
- `--gamma`: Discount factor (default: 0.99)
- `--epsilon_start`: Initial exploration rate (default: 1.0)
- `--epsilon_end`: Final exploration rate (default: 0.01)
- `--epsilon_decay`: Epsilon decay per episode (default: 0.995)
- `--num_synthetic`: Number of synthetic sequences (default: 100)
- `--save_freq`: Save checkpoint every N episodes (default: 50)

**Example with Custom Settings:**

```bash
python train.py \
    --num_episodes 1000 \
    --batch_size 128 \
    --learning_rate 5e-5 \
    --gamma 0.95 \
    --epsilon_decay 0.99 \
    --num_synthetic 200 \
    --device cuda
```

### Evaluation Options

```bash
python evaluate.py --help
```

**Key Parameters:**

- `--agent_path`: Path to trained agent (required)
- `--num_episodes`: Total evaluation episodes (default: 100)
- `--num_synthetic`: Synthetic test sequences (default: 50)
- `--num_real`: Real test sequences (default: 50)

---

## 🧩 System Components

### 1. Model Loaders

#### Autoencoder Loader
```python
from models.autoencoder_loader import AutoencoderLoader

ae_loader = AutoencoderLoader(
    model_path='../autoencoder_outputs/autoencoder_anomaly_detection.pth',
    device='cuda'
)

# Get anomaly score
result = ae_loader.get_anomaly_score(features)
# Returns: {'anomaly_score', 'reconstruction_error', 'latent_vector'}
```

#### VAE Loader
```python
from models.vae_loader import VAELoader

vae_loader = VAELoader(
    model_path='../vae_anomaly_detector_outputs/vae_anomaly_detector.pth',
    threshold=0.05,
    device='cuda'
)

# Get malicious probability
result = vae_loader.get_malicious_probability(features)
# Returns: {'malicious_probability', 'uncertainty', 'reconstruction_error'}
```

#### Transformer Loader
```python
from models.transformer_loader import TransformerLoader

trans_loader = TransformerLoader(
    model_path='../transformer_outputs/transformer_next_step_prediction.pth',
    device='cuda'
)

# Predict next CKC stage
result = trans_loader.predict_next_stage(sequence)
# Returns: {'predicted_next_ckc_stage', 'prediction_confidence', 'stage_probabilities'}
```

### 2. Synthetic Meta-Sequence Generator

```python
from synthetic.meta_sequence_generator import MetaSequenceGenerator

generator = MetaSequenceGenerator(use_simple_generation=True)

# Generate sequences
sequences = generator.generate_meta_sequences(
    num_sequences=100,
    min_length=5,
    max_length=20,
    attack_types=['progressive', 'repetitive', 'advanced']
)

# Each sequence: [{'ckc_stage': 1, 'event_index': 0, 'relative_time_delta': 0}, ...]
```

### 3. Conditional Replay

```python
from synthetic.conditional_replay import ConditionalReplay

replay = ConditionalReplay(real_data_path='../combined_dataset_final.xlsx')

# Map meta-sequence to features
feature_matrix, indices = replay.replay_meta_sequence(meta_sequence)
# feature_matrix shape: (seq_len, n_features)
```

### 4. APT Environment

```python
from env.apt_env import APTEnvironment

env = APTEnvironment(
    autoencoder_loader=ae_loader,
    vae_loader=vae_loader,
    transformer_loader=trans_loader,
    conditional_replay=replay,
    max_steps=50
)

# Standard Gym interface
state = env.reset(sequence)
next_state, reward, done, info = env.step(action)
```

### 5. DQN Agent

```python
from rl.dqn_agent import DQNAgent

agent = DQNAgent(
    state_dim=10,
    action_dim=5,
    learning_rate=1e-4,
    gamma=0.99,
    device='cuda'
)

# Training
action = agent.select_action(state, training=True)
agent.store_transition(state, action, reward, next_state, done)
loss = agent.train_step()

# Inference
action = agent.select_action(state, training=False)
```

---

## 📊 Training

### Training Process

1. **Load Models**: Load pre-trained AE, VAE, Transformer
2. **Generate Sequences**: Create synthetic meta-sequences
3. **Initialize Environment**: Setup APT Gym environment
4. **Initialize Agent**: Create DQN agent
5. **Training Loop**:
   ```python
   for episode in range(num_episodes):
       state = env.reset(sequence)
       while not done:
           action = agent.select_action(state)
           next_state, reward, done, info = env.step(action)
           agent.store_transition(state, action, reward, next_state, done)
           loss = agent.train_step()
       agent.update_epsilon()
   ```
6. **Save**: Save trained agent and metrics

### Monitoring Training

Training outputs:
- **Console**: Episode rewards, loss, epsilon
- **training_curves.png**: Reward and loss curves
- **training_history.json**: Complete training metrics
- **Checkpoints**: Saved every N episodes

---

## 📈 Evaluation

### Evaluation Metrics

1. **Episode Rewards**: Total reward per test episode
2. **Early Detection Rate**: % detected in S1-S3
3. **Action Distribution**: Frequency of each action
4. **CKC Stage Distribution**: Events per stage
5. **Real vs Synthetic**: Performance comparison

### Evaluation Outputs

- **evaluation_results.png**: Comprehensive plots
- **evaluation_report.json**: Detailed metrics
- **evaluation_report.txt**: Human-readable summary

---

## 🎓 Academic Explanation

### Why CKC Stage is Generated at Meta-Level

**Reason**: ReALTabFormer was trained on 20 high-level columns representing attack metadata, not raw SIEM features. It learns realistic **attack progressions** (S1 → S3 → S5 → S7) but cannot generate 200+ low-level features.

**Solution**: Use ReALTabFormer for what it does best (high-level sequences), then map to real features via conditional replay.

### Why Time is Injected Synthetically

**Reason**: Temporal dynamics are critical for APT detection, but ReALTabFormer doesn't capture inter-event time distributions well.

**Solution**: 
1. Analyze real time distributions per CKC stage
2. Sample realistic time deltas during meta-sequence generation
3. Preserve temporal realism without retraining

### Why Conditional Replay Preserves Correctness

**Proof of Correctness**:

1. **Feature Validity**: Sampled from real data → valid SIEM features
2. **CKC Consistency**: Conditioning ensures correct stage → model expectations met
3. **Model Compatibility**: Full feature vectors → no dimension mismatch
4. **Distribution Preservation**: Random sampling → preserves real data distribution

**Alternative Names**:
- Conditional Data Augmentation
- Guided Feature Sampling
- Stage-Conditioned Replay

**Academic Precedent**:
- Similar to conditional GANs (conditioning on class labels)
- Related to importance sampling (sampling from conditional distribution)

---

## 📉 Results

### Expected Performance

**After 500 Episodes:**
- Average Reward: 5-15 (depends on data)
- Early Detection Rate: 60-80%
- Epsilon: ~0.01 (full exploitation)

**Action Distribution:**
- Monitor: 30-40%
- Low Alert: 20-30%
- Escalate: 15-25%
- Isolate: 10-15%
- Block: 5-10%

### Interpreting Rewards

- **Positive rewards**: Agent correctly detects attacks early
- **Negative rewards**: False positives or missed attacks
- **Increasing trend**: Agent is learning optimal policy

---

## 🐛 Troubleshooting

### Common Issues

#### 1. Model File Not Found
```
FileNotFoundError: Model file not found: ...
```
**Solution**: Verify model paths are correct and files exist.

#### 2. Dimension Mismatch
```
RuntimeError: size mismatch ...
```
**Solution**: Ensure conditional replay uses correct feature columns.

#### 3. CUDA Out of Memory
```
RuntimeError: CUDA out of memory
```
**Solution**: Reduce batch size or use `--device cpu`.

#### 4. Low Rewards
```
Average reward stays negative
```
**Solution**: 
- Increase training episodes
- Adjust reward function
- Check epsilon decay rate

---

## 📚 References

### Papers

1. **DQN**: Mnih et al. "Playing Atari with Deep Reinforcement Learning" (2013)
2. **ReALTabFormer**: Solatorio & Dupriez "REaLTabFormer: Generating Realistic Relational and Tabular Data using Transformers" (2023)
3. **Cyber Kill Chain**: Lockheed Martin "Intelligence-Driven Computer Network Defense" (2011)

### Code

- OpenAI Gym: https://gym.openai.com/
- PyTorch: https://pytorch.org/
- Transformers: https://huggingface.co/transformers/

---

## 👨‍🎓 Author

**Master-Level Project**: RL-based APT Detection and Response

**Course**: Machine Learning for Advanced Threat Detection

**Year**: 2024-2025

---

## 📄 License

This project is for academic purposes only.

---

## ✅ Checklist for Reproducibility

- [x] All pre-trained models documented and loaded correctly
- [x] Conditional replay mechanism explained and implemented
- [x] RL environment follows Gym interface
- [x] DQN implementation with experience replay and target network
- [x] Training script with comprehensive logging
- [x] Evaluation script with multiple metrics
- [x] Reward function prioritizes early detection
- [x] Academic explanations for design choices
- [x] Modular, well-commented code
- [x] README with complete usage instructions

---

**🎉 System is ready for Master-level evaluation!**
