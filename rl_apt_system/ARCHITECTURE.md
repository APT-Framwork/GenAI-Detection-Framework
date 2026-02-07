# System Architecture Diagrams

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     RL-BASED APT DETECTION SYSTEM                           │
│                                                                             │
│  ┌──────────────────┐      ┌──────────────────┐      ┌──────────────────┐ │
│  │  Pre-trained     │      │   Synthetic      │      │    RL Agent      │ │
│  │  Detection       │      │   Data           │      │    (DQN)         │ │
│  │  Models          │      │   Generation     │      │                  │ │
│  │                  │      │                  │      │                  │ │
│  │ • Autoencoder    │      │ • ReALTabFormer  │      │ • Q-Network      │ │
│  │ • VAE            │──────│ • Meta-Seq Gen   │──────│ • Experience     │ │
│  │ • Transformer    │      │ • Time Synthesis │      │   Replay         │ │
│  │                  │      │                  │      │ • Target Network │ │
│  └──────────────────┘      └──────────────────┘      └──────────────────┘ │
│           │                         │                         │            │
│           │                         │                         │            │
│           └─────────────────────────┴─────────────────────────┘            │
│                                     │                                      │
│                                     ▼                                      │
│                         ┌───────────────────────┐                         │
│                         │  Conditional Replay   │                         │
│                         │  Meta → Features      │                         │
│                         └───────────────────────┘                         │
│                                     │                                      │
│                                     ▼                                      │
│                         ┌───────────────────────┐                         │
│                         │   APT Environment     │                         │
│                         │   (Gym Interface)     │                         │
│                         └───────────────────────┘                         │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Data Flow Diagram

```
┌─────────────────────┐
│  Real SIEM Data     │
│  (combined_data.    │
│   xlsx)             │
└──────────┬──────────┘
           │
           ▼
┌──────────────────────────────────────────────┐
│  Conditional Replay System                   │
│  ┌────────────────────────────────────────┐  │
│  │ 1. Build CKC Index                     │  │
│  │    S1 → [indices]                      │  │
│  │    S2 → [indices]                      │  │
│  │    ...                                 │  │
│  │ 2. Sample by CKC Stage                 │  │
│  │    Query: S3                           │  │
│  │    Return: Full feature vector         │  │
│  └────────────────────────────────────────┘  │
└──────────────────┬───────────────────────────┘
                   │
                   │  Full Features (200+ dims)
                   ▼
┌──────────────────────────────────────────────┐
│  Pre-trained Detection Models                │
│  ┌────────────┬────────────┬──────────────┐  │
│  │ AE         │ VAE        │ Transformer  │  │
│  │ ↓          │ ↓          │ ↓            │  │
│  │ anomaly_   │ malicious_ │ predicted_   │  │
│  │ score      │ prob       │ next_stage   │  │
│  └────────────┴────────────┴──────────────┘  │
└──────────────────┬───────────────────────────┘
                   │
                   │  Detection Signals
                   ▼
┌──────────────────────────────────────────────┐
│  RL Environment (State Construction)         │
│  ┌────────────────────────────────────────┐  │
│  │ State = [                              │  │
│  │   anomaly_score,                       │  │
│  │   reconstruction_error,                │  │
│  │   malicious_probability,               │  │
│  │   uncertainty,                         │  │
│  │   predicted_next_ckc_stage,            │  │
│  │   prediction_confidence,               │  │
│  │   current_ckc_stage,                   │  │
│  │   time_since_first_event,              │  │
│  │   time_since_last_event,               │  │
│  │   sequence_length_so_far               │  │
│  │ ]                                      │  │
│  └────────────────────────────────────────┘  │
└──────────────────┬───────────────────────────┘
                   │
                   │  State (10 dims)
                   ▼
┌──────────────────────────────────────────────┐
│  DQN Agent                                   │
│  ┌────────────────────────────────────────┐  │
│  │ Q-Network                              │  │
│  │ Input: State (10)                      │  │
│  │ Hidden: [128, 64]                      │  │
│  │ Output: Q-values (5)                   │  │
│  │                                        │  │
│  │ Actions:                               │  │
│  │   0: Monitor                           │  │
│  │   1: Low Alert                         │  │
│  │   2: Escalate                          │  │
│  │   3: Isolate                           │  │
│  │   4: Block                             │  │
│  └────────────────────────────────────────┘  │
└──────────────────┬───────────────────────────┘
                   │
                   │  Action
                   ▼
┌──────────────────────────────────────────────┐
│  Environment (Reward Computation)            │
│  ┌────────────────────────────────────────┐  │
│  │ if correct_early_detection:            │  │
│  │     reward = +5                        │  │
│  │ elif correct_mid_detection:            │  │
│  │     reward = +2                        │  │
│  │ elif false_positive:                   │  │
│  │     reward = -1                        │  │
│  │ elif missed_attack:                    │  │
│  │     reward = -10                       │  │
│  └────────────────────────────────────────┘  │
└──────────────────┬───────────────────────────┘
                   │
                   │  Reward, Next State, Done
                   ▼
┌──────────────────────────────────────────────┐
│  Experience Replay Buffer                    │
│  Store: (s, a, r, s', done)                  │
│  Sample: Random mini-batch                   │
└──────────────────────────────────────────────┘
```

## Conditional Replay Detail

```
┌─────────────────────────────────────────────────────────────────────┐
│  CONDITIONAL REPLAY: Meta-Sequence → Full Features                  │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Input: Meta-Sequence                                               │
│  [                                                                  │
│    {ckc_stage: 1, event_index: 0, time_delta: 0},                  │
│    {ckc_stage: 1, event_index: 1, time_delta: 4},                  │
│    {ckc_stage: 3, event_index: 2, time_delta: 18},                 │
│    {ckc_stage: 5, event_index: 3, time_delta: 42},                 │
│  ]                                                                  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │ For each event in meta-sequence:                              │ │
│  │                                                               │ │
│  │   1. Extract CKC stage (e.g., 3)                             │ │
│  │      ↓                                                        │ │
│  │   2. Query CKC index: indices_for_stage_3 = [45, 78, 103...] │ │
│  │      ↓                                                        │ │
│  │   3. Sample random index: idx = 78                           │ │
│  │      ↓                                                        │ │
│  │   4. Extract full features: df.iloc[78, feature_cols]        │ │
│  │      ↓                                                        │ │
│  │   5. Return feature vector (200+ dimensions)                 │ │
│  │                                                               │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
│  Output: Feature Matrix                                             │
│  [                                                                  │
│    [f1, f2, f3, ..., f200],  # Event 0 features (S1)               │
│    [f1, f2, f3, ..., f200],  # Event 1 features (S1)               │
│    [f1, f2, f3, ..., f200],  # Event 2 features (S3)               │
│    [f1, f2, f3, ..., f200],  # Event 3 features (S5)               │
│  ]                                                                  │
│                                                                     │
│  ✅ Correct dimensionality for pre-trained models                   │
│  ✅ Realistic features from real data                               │
│  ✅ Controlled CKC progression from meta-sequence                   │
└─────────────────────────────────────────────────────────────────────┘
```

## Training Loop Detail

```
┌─────────────────────────────────────────────────────────────────────┐
│  TRAINING LOOP (One Episode)                                        │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  1. INITIALIZE EPISODE                                              │
│     ┌──────────────────────────────────────────┐                   │
│     │ sequence = generate_meta_sequence()      │                   │
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
│     │      ┌──────────────────────────────────┐             │     │
│     │      │ if random() < epsilon:           │             │     │
│     │      │     action = random_action()     │             │     │
│     │      │ else:                            │             │     │
│     │      │     action = argmax(Q(state))    │             │     │
│     │      └──────────────────────────────────┘             │     │
│     │                                                        │     │
│     │   b. ENVIRONMENT EXECUTES ACTION                      │     │
│     │      ┌──────────────────────────────────┐             │     │
│     │      │ next_state, reward, done, info   │             │     │
│     │      │     = env.step(action)           │             │     │
│     │      └──────────────────────────────────┘             │     │
│     │                                                        │     │
│     │   c. STORE TRANSITION                                 │     │
│     │      ┌──────────────────────────────────┐             │     │
│     │      │ replay_buffer.push(              │             │     │
│     │      │   state, action, reward,         │             │     │
│     │      │   next_state, done               │             │     │
│     │      │ )                                │             │     │
│     │      └──────────────────────────────────┘             │     │
│     │                                                        │     │
│     │   d. TRAIN AGENT (if buffer has enough samples)      │     │
│     │      ┌──────────────────────────────────┐             │     │
│     │      │ batch = replay_buffer.sample()   │             │     │
│     │      │ Q_pred = Q(state, action)        │             │     │
│     │      │ Q_target = r + γ*max(Q(s'))      │             │     │
│     │      │ loss = MSE(Q_pred, Q_target)     │             │     │
│     │      │ optimizer.step()                 │             │     │
│     │      └──────────────────────────────────┘             │     │
│     │                                                        │     │
│     │   e. UPDATE STATE                                     │     │
│     │      state = next_state                               │     │
│     │                                                        │     │
│     └────────────────────────────────────────────────────────┘     │
│                      │                                              │
│                      ▼                                              │
│  3. UPDATE EPSILON                                                  │
│     ┌──────────────────────────────────────────┐                   │
│     │ epsilon = max(epsilon_min,               │                   │
│     │               epsilon * decay)           │                   │
│     └──────────────────────────────────────────┘                   │
│                      │                                              │
│                      ▼                                              │
│  4. LOG METRICS                                                     │
│     ┌──────────────────────────────────────────┐                   │
│     │ episode_reward, loss, epsilon            │                   │
│     └──────────────────────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────────┘
```

## State Space Composition

```
┌─────────────────────────────────────────────────────────────────────┐
│  STATE VECTOR (10 dimensions)                                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌─────────────────────────┬─────────────┬────────────────────────┐│
│  │ Feature                 │ Source      │ Purpose                ││
│  ├─────────────────────────┼─────────────┼────────────────────────┤│
│  │ [0] anomaly_score       │ Autoencoder │ General anomaly        ││
│  │ [1] reconstruction_err  │ Autoencoder │ Reconstruction quality ││
│  │ [2] malicious_prob      │ VAE         │ Malicious likelihood   ││
│  │ [3] uncertainty         │ VAE         │ Model confidence       ││
│  │ [4] predicted_next_ckc  │ Transformer │ Attack progression     ││
│  │ [5] prediction_conf     │ Transformer │ Prediction certainty   ││
│  │ [6] current_ckc_stage   │ Environment │ Current attack phase   ││
│  │ [7] time_since_first    │ Environment │ Attack duration        ││
│  │ [8] time_since_last     │ Environment │ Inter-event timing     ││
│  │ [9] sequence_length     │ Environment │ Events observed        ││
│  └─────────────────────────┴─────────────┴────────────────────────┘│
│                                                                     │
│  Example State:                                                     │
│  [2.3, 0.45, 0.78, 1.2, 4, 0.82, 3, 0.5, 0.08, 5]                  │
│   │    │     │     │    │   │     │   │    │     │                 │
│   │    │     │     │    │   │     │   │    │     └─ 5 events seen │
│   │    │     │     │    │   │     │   │    └─ 0.08h since last    │
│   │    │     │     │    │   │     │   └─ 0.5h since first         │
│   │    │     │     │    │   │     └─ Currently at S3              │
│   │    │     │     │    │   └─ 82% confidence                     │
│   │    │     │     │    └─ Predicts S4 next                       │
│   │    │     │     └─ Uncertainty: 1.2                            │
│   │    │     └─ 78% malicious probability                         │
│   │    └─ Reconstruction error: 0.45                              │
│   └─ Anomaly score: 2.3                                           │
└─────────────────────────────────────────────────────────────────────┘
```

## File Organization

```
rl_apt_system/
│
├── 📁 models/              # Model loaders (inference only)
│   ├── autoencoder_loader.py
│   ├── vae_loader.py
│   ├── transformer_loader.py
│   └── __init__.py
│
├── 📁 synthetic/           # Synthetic data generation
│   ├── meta_sequence_generator.py
│   ├── conditional_replay.py
│   └── __init__.py
│
├── 📁 env/                 # RL environment
│   ├── apt_env.py
│   └── __init__.py
│
├── 📁 rl/                  # RL agent
│   ├── dqn_agent.py
│   └── __init__.py
│
├── 📁 data/                # Data storage
│   ├── real_sequences/
│   └── synthetic_meta_sequences/
│
├── 📄 train.py             # Training script
├── 📄 evaluate.py          # Evaluation script
├── 📄 demo.py              # Demo/test script
│
├── 📖 README.md            # Comprehensive documentation
├── 📖 PROJECT_SUMMARY.md   # Project summary
├── 📖 QUICKSTART.md        # Quick start guide
├── 📖 ARCHITECTURE.md      # This file
│
├── 📋 requirements.txt     # Dependencies
└── 📋 __init__.py          # Package initialization
```
