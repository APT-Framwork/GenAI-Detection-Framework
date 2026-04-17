# System Architecture Diagrams

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     RL-BASED APT DETECTION SYSTEM                           │
│                                                                             │
│  ┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐ │
│  │  Pre-trained     │      │   Data Pipeline   │      │    RL Agent      │ │
│  │  Detection       │      │                  │      │    (DQN)         │ │
│  │  Models          │      │ • Real Wazuh     │      │                  │ │
│  │                  │      │   alerts (55 feat)│      │ • Q-Network      │ │
│  │ • Autoencoder    │      │ • Synthetic data  │      │ • Experience     │ │
│  │ • Beta-VAE       │──────│   (ReALTabFormer)│──────│   Replay         │ │
│  │ • Transformer    │      │ • Variable-length │      │ • Target Network │ │
│  │ • GNN (GraphSAGE)│      │   sequences      │      │                  │ │
│  └──────────────────┘      └──────────────────┘      └──────────────────┘ │
│           │                         │                         │            │
│           └─────────────────────────┴─────────────────────────┘            │
│                                     │                                      │
│                                     ▼                                      │
│                         ┌───────────────────────┐                         │
│                         │   APT Environment     │                         │
│                         │   (Gym Interface)     │                         │
│                         │   13-dim state space  │                         │
│                         └───────────────────────┘                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow Diagram

```
┌─────────────────────┐     ┌─────────────────────┐
│  Real Wazuh Alerts  │     │  Synthetic Alerts    │
│  (combined_dataset  │     │  (ReALTabFormer      │
│   _final.xlsx)      │     │   generated)         │
│  115,726 alerts     │     │  120,000 alerts      │
└──────────┬──────────┘     └──────────┬──────────┘
           │                           │
           └───────────┬───────────────┘
                       │
                       ▼
           ┌───────────────────────┐
           │  Feature Engineering  │
           │  25 features → 55 cols│
           │  (SecBERT PCA +       │
           │   binary flags)       │
           └───────────┬───────────┘
                       │  55-dim feature vectors
                       │
      ┌────────┬───────┴───────┬────────┐
      │        │               │        │
      ▼        ▼               ▼        ▼
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│    AE    │ │   VAE    │ │Transformer│ │   GNN    │
│          │ │          │ │          │ │(GraphSAGE)│
│ anomaly_ │ │malicious_│ │predicted_│ │ node_risk │
│ score    │ │prob      │ │next_stage│ │ neighbor_ │
│ recon_err│ │uncertainty│ │pred_conf │ │ risk      │
│          │ │          │ │          │ │ risk_growth│
└────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘
     │  2 vals     │ 2 vals     │ 2 vals     │ 3 vals
     └──────┬──────┴──────┬─────┴──────┬─────┘
            │             │            │
            │    + 4 temporal/context features
            │             │            │
            ▼             ▼            ▼
┌──────────────────────────────────────────────┐
│  RL Environment (State Construction)         │
│  ┌────────────────────────────────────────┐  │
│  │ State = [                              │  │
│  │   anomaly_score,          # AE         │  │
│  │   reconstruction_error,   # AE         │  │
│  │   malicious_probability,  # VAE        │  │
│  │   uncertainty,            # VAE        │  │
│  │   predicted_next_ckc,     # Transformer│  │
│  │   prediction_confidence,  # Transformer│  │
│  │   current_ckc_stage,      # Context    │  │
│  │   time_since_first_event, # Temporal   │  │
│  │   time_since_last_event,  # Temporal   │  │
│  │   sequence_length_so_far, # Counter    │  │
│  │   gnn_node_risk,          # GNN        │  │
│  │   gnn_neighbor_risk,      # GNN        │  │
│  │   gnn_risk_growth         # GNN        │  │
│  │ ]                                      │  │
│  └────────────────────────────────────────┘  │
└──────────────────┬───────────────────────────┘
                   │
                   │  State (13 dims)
                   ▼
┌──────────────────────────────────────────────┐
│  DQN Agent                                   │
│  ┌────────────────────────────────────────┐  │
│  │ Q-Network                              │  │
│  │ Input: State (13)                      │  │
│  │ Hidden: [128, 64] + ReLU + Dropout     │  │
│  │ Output: Q-values (5)                   │  │
│  │                                        │  │
│  │ Actions:                               │  │
│  │   0: Monitor                           │  │
│  │   1: Low Alert                         │  │
│  │   2: Escalate to SOC                   │  │
│  │   3: Isolate Host                      │  │
│  │   4: Block User/IP                     │  │
│  └────────────────────────────────────────┘  │
└──────────────────┬───────────────────────────┘
                   │
                   │  Action
                   ▼
┌──────────────────────────────────────────────┐
│  Environment (Reward Computation)            │
│  ┌────────────────────────────────────────┐  │
│  │ Intervention on malicious:             │  │
│  │   S1-S2: +15  (excellent early catch)  │  │
│  │   S3:    +10  (good: caught delivery)  │  │
│  │   S4:     +7  (caught exploitation)    │  │
│  │   S5:     +3  (borderline)             │  │
│  │   S6:     +0  (too late)               │  │
│  │   S7:     -2  (damage done)            │  │
│  │ False positive: -2 to -3               │  │
│  │ Missed attack:  -15                    │  │
│  └────────────────────────────────────────┘  │
└──────────────────┬───────────────────────────┘
                   │
                   │  Reward, Next State, Done
                   ▼
┌──────────────────────────────────────────────┐
│  Experience Replay Buffer (10,000)           │
│  Store: (s, a, r, s', done)                  │
│  Sample: Random mini-batch (64)              │
└──────────────────────────────────────────────┘
```

## Model Interaction Detail

```
┌─────────────────────────────────────────────────────────────────────┐
│  HOW THE 4 MODELS FEED THE RL AGENT                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Input: Alert Feature Vector (55 dimensions)                        │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ MODEL 1: Autoencoder (RegularizedAE)                           ││
│  │   55 → Encoder(256→128) → Latent(64) → Decoder(128→256) → 55  ││
│  │   Output: anomaly_score (dist from center), recon_error (MSE)  ││
│  │   Extra: Latent vectors (64-dim) → fed to Transformer          ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ MODEL 2: Beta-VAE                                              ││
│  │   55 → Encoder(512→256→128) → Latent(32) → Decoder → 55       ││
│  │   Output: malicious_probability (sigmoid of distance),         ││
│  │           uncertainty (latent variance)                         ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ MODEL 3: Transformer (CKC Stage Predictor)                    ││
│  │   AE Latent(64) → Projection(128) → PosEnc → 4×Encoder →     ││
│  │   → MeanPool → Linear(128→64→8) → Softmax                     ││
│  │   Input: sequence of AE latent vectors (all alerts so far)     ││
│  │   Output: predicted_next_stage (0-7), prediction_confidence    ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │ MODEL 4: GNN (GraphSAGE)                                      ││
│  │   Alert graph: nodes=alerts, edges=temporal+user+IP links      ││
│  │   55 → 3×SAGEConv(128) + Residual → Linear(128→64→1) → risk   ││
│  │   Output: node_risk, neighbor_risk, risk_growth                ││
│  └─────────────────────────────────────────────────────────────────┘│
│                                                                     │
│  All outputs → 13-dim state vector → DQN Agent                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Training Loop Detail

```
┌─────────────────────────────────────────────────────────────────────┐
│  TRAINING LOOP (3,000 Episodes)                                     │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. INITIALIZE EPISODE                                              │
│     ┌──────────────────────────────────────────┐                   │
│     │ sequence = pick from training pool       │                   │
│     │   (1,100 sequences: 500 synthetic +      │                   │
│     │    600 real variable-length 5-30 steps)   │                   │
│     │ state = env.reset(sequence)              │                   │
│     │ done = False                             │                   │
│     └──────────────────────────────────────────┘                   │
│                      │                                              │
│                      ▼                                              │
│  2. EPISODE LOOP                                                    │
│     ┌────────────────────────────────────────────────────────┐     │
│     │ while not done:                                        │     │
│     │                                                        │     │
│     │   a. AGENT SELECTS ACTION (Epsilon-Greedy)            │     │
│     │      if random() < epsilon: random action             │     │
│     │      else: argmax(Q(state))                           │     │
│     │                                                        │     │
│     │   b. ENVIRONMENT PROCESSES                             │     │
│     │      - Advances to next alert in sequence             │     │
│     │      - AE: compute anomaly_score + encode to latent   │     │
│     │      - VAE: compute malicious_probability             │     │
│     │      - Transformer: predict next stage from latents   │     │
│     │      - GNN: compute risk scores for current host      │     │
│     │      - Build 13-dim state + compute reward            │     │
│     │                                                        │     │
│     │   c. STORE (state, action, reward, next_state, done)  │     │
│     │                                                        │     │
│     │   d. TRAIN on random mini-batch from buffer           │     │
│     │      Q_target = r + γ * max(Q_target_net(s'))         │     │
│     │      loss = MSE(Q_pred, Q_target)                     │     │
│     │      optimizer.step()                                  │     │
│     │                                                        │     │
│     │   e. state = next_state                               │     │
│     └────────────────────────────────────────────────────────┘     │
│                      │                                              │
│                      ▼                                              │
│  3. epsilon = max(0.01, epsilon × 0.995)                            │
│                                                                     │
│  4. Save best agent checkpoint                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## State Space Composition

```
┌─────────────────────────────────────────────────────────────────────┐
│  STATE VECTOR (13 dimensions)                                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────┬─────────────┬────────────────────────┐│
│  │ Feature                 │ Source      │ Purpose                ││
│  ├─────────────────────────┼─────────────┼────────────────────────┤│
│  │ [0] anomaly_score       │ Autoencoder │ General anomaly        ││
│  │ [1] reconstruction_err  │ Autoencoder │ Reconstruction quality ││
│  │ [2] malicious_prob      │ Beta-VAE    │ Malicious likelihood   ││
│  │ [3] uncertainty         │ Beta-VAE    │ Model confidence       ││
│  │ [4] predicted_next_ckc  │ Transformer │ Attack progression     ││
│  │ [5] prediction_conf     │ Transformer │ Prediction certainty   ││
│  │ [6] current_ckc_stage   │ Context     │ Current attack phase   ││
│  │ [7] time_since_first    │ Temporal    │ Attack duration        ││
│  │ [8] time_since_last     │ Temporal    │ Inter-event timing     ││
│  │ [9] sequence_length     │ Counter     │ Events observed        ││
│  │[10] gnn_node_risk       │ GNN         │ Risk on current host   ││
│  │[11] gnn_neighbor_risk   │ GNN         │ Connected host risk    ││
│  │[12] gnn_risk_growth     │ GNN         │ Global risk change     ││
│  └─────────────────────────┴─────────────┴────────────────────────┘│
│                                                                     │
│  Example State:                                                     │
│  [2.3, 0.45, 0.78, 1.2, 4, 0.82, 3, 0.5, 0.08, 5, 0.6, 0.3, 0.1] │
└─────────────────────────────────────────────────────────────────────┘
```

## File Organization

```
RL_agent/
│
├── 📖 AGENT_ARCHITECTURE.md     # Detailed architecture & data journey guide
├── 📖 ARCHITECTURE.md           # This file (diagrams)
├── 📖 README.md                 # Usage documentation
│
├── 📁 models/                   # Pre-trained model loaders (inference only)
│   ├── autoencoder_loader.py    # RegularizedAE (55→64→55)
│   ├── vae_loader.py            # Beta-VAE (55→32→55)
│   ├── transformer_loader.py    # CKC predictor (64→128→8 classes)
│   ├── gnn_loader.py            # GraphSAGE propagation detector
│   └── __init__.py
│
├── 📁 synthetic/                # Data loading & sequence construction
│   ├── data_loader.py           # Feature columns + APTDataLoader
│   ├── real_data_loader.py      # Variable-length real sequence builder
│   ├── meta_sequence_generator.py
│   └── __init__.py
│
├── 📁 env/                      # RL environment
│   ├── apt_env.py               # 13-dim state, 5 actions, reward function
│   └── __init__.py
│
├── 📁 rl/                       # RL agent
│   ├── dqn_agent.py             # DQN with experience replay + target network
│   └── __init__.py
│
├── 📁 outputs/                  # Production agent checkpoints
│   ├── agent_best.pth           # Best agent (3,000 episodes)
│   └── training_curves.png
│
├── 📁 outputs_ablation/         # Ablation study agents
│   ├── no_ae/                   # Trained without Autoencoder
│   ├── no_vae/                  # Trained without VAE
│   ├── no_transformer/          # Trained without Transformer
│   └── no_gnn/                  # Trained without GNN
│
├── 📁 evaluation/               # Evaluation results & plots
│   ├── ablation_study_plot.png
│   ├── metric_scaling_plot.png
│   └── *.json
│
├── 📄 train.py                  # Training script
├── 📄 evaluate_real.py          # Real data evaluation
├── 📄 evaluate_scaling.py       # Scaling test (1K-10K episodes)
├── 📄 ablation_study.py         # Ablation analysis
└── 📄 requirements.txt          # Dependencies
```
