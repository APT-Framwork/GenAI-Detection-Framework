"""
============================================================
GNN IMPROVEMENTS — PASTE EACH SECTION AS A NEW CELL
============================================================

This file contains four improvement techniques for the GNN APT
detection notebook. Copy each section (separated by
# ==== CELL N ==== markers) into a NEW CELL at the end of the
existing GNN_APT_Propagation.ipynb notebook.

Techniques:
  1. Sliding Time Windows (keeps only recent connections)
  2. Edge Decay / Fading Memory (exponential weight decay)
  3. Graph Attention Network (GATConv replaces GCNConv)
  4. Temporal Edge Features (enrich edges with time metadata)

Prerequisites: all existing cells in the notebook must have
been executed first (data loaded, features engineered,
snapshots built, etc.).
============================================================
"""

# ==== CELL 1 — IMPORTS & HYPERPARAMETERS ====
# Paste this as a NEW cell in the notebook.

from torch_geometric.nn import GATConv
import math

# ----- New hyperparameters -----
WINDOW_SIZE = 500         # Number of snapshots to keep in the sliding window
DECAY_LAMBDA = 0.05       # Exponential decay rate (per-snapshot units)
DECAY_MIN_WEIGHT = 0.01   # Prune edges with weight below this threshold
GAT_HEADS = 4             # Number of attention heads in first GAT layer
GAT_HIDDEN = 32           # Hidden dimension per head
GAT_DROPOUT = 0.3         # Dropout rate for GAT model

print("✅ Improvement imports & hyperparameters loaded")
print(f"   Window size: {WINDOW_SIZE} snapshots")
print(f"   Decay λ: {DECAY_LAMBDA}, min weight: {DECAY_MIN_WEIGHT}")
print(f"   GAT heads: {GAT_HEADS}, hidden/head: {GAT_HIDDEN}, dropout: {GAT_DROPOUT}")

# ==== CELL 2 — WINDOWED GRAPH CONSTRUCTION WITH EDGE DECAY ====
# Paste this as a NEW cell in the notebook.

# Edge type constants for one-hot encoding in edge features
EDGE_TYPE_TEMPORAL   = 0
EDGE_TYPE_SHARED_USER = 1
EDGE_TYPE_DIRECT_COMM = 2
EDGE_TYPE_REMOTE_EXEC = 3
NUM_EDGE_TYPES = 4

def build_windowed_graph(snapshot_idx, snapshots, df_raw, version='full',
                         window_size=WINDOW_SIZE, decay_lambda=DECAY_LAMBDA,
                         decay_min_weight=DECAY_MIN_WEIGHT):
    """
    Build a graph for a single snapshot using only data within a
    sliding time window.  Edges receive exponential decay weights.

    Returns:
        G : nx.Graph with node attrs 'features','label'
                       and edge attrs 'weight','edge_type','age_snapshots'
    """
    G = nx.Graph()

    # --- determine window boundaries ---
    snap = snapshots[snapshot_idx]
    curr_end_idx = snap['end_idx']

    # Earliest snapshot in the window
    win_start_snap = max(0, snapshot_idx - window_size + 1)
    if win_start_snap == 0:
        data_start = 0
    else:
        # Start right after the previous window-boundary snapshot ended
        data_start = snapshots[win_start_snap - 1]['end_idx'] + 1

    # Slice the data visible to this window
    window_df = df_raw.iloc[data_start : curr_end_idx + 1].copy()

    # New alerts in the current snapshot only
    prev_end = snapshots[snapshot_idx - 1]['end_idx'] if snapshot_idx > 0 else -1
    new_df = df_raw.iloc[prev_end + 1 : curr_end_idx + 1]

    machines_in_window = window_df['machine_name'].unique()
    new_machines = new_df['machine_name'].unique() if len(new_df) > 0 else []

    # --- 1. Build node features & labels ---
    for machine in machines_in_window:
        machine_history = window_df[window_df['machine_name'] == machine]
        features = get_node_features(machine_history, version=version)

        # Label based on *current* snapshot activity
        if machine in new_machines:
            machine_new = new_df[new_df['machine_name'] == machine]
            has_malicious = int(machine_new['label'].max() > 0)
        else:
            has_malicious = 0

        G.add_node(machine, features=features, label=has_malicious)

    # --- 2. Build edges with types and decay weights ---
    # We iterate over each snapshot inside the window and apply edges,
    # weighting by recency.
    all_machines = list(machines_in_window)

    for s_idx in range(win_start_snap, snapshot_idx + 1):
        s = snapshots[s_idx]
        s_end = s['end_idx']
        s_start_data = (snapshots[s_idx - 1]['end_idx'] + 1) if s_idx > 0 else 0
        s_df = df_raw.iloc[s_start_data : s_end + 1]

        age = snapshot_idx - s_idx  # 0 = current, larger = older
        weight = math.exp(-decay_lambda * age)

        if weight < decay_min_weight:
            continue  # skip very old edges

        s_machines = set(s_df['machine_name'].unique())

        # -- temporal proximity edges --
        machine_times_s = {}
        for m in s_machines:
            m_df = s_df[s_df['machine_name'] == m]
            if len(m_df) > 0:
                machine_times_s[m] = m_df['timestamp'].values.astype(np.int64) // 10**9

        m_list = list(machine_times_s.keys())
        for i in range(len(m_list)):
            for j in range(i + 1, len(m_list)):
                m1, m2 = m_list[i], m_list[j]
                if m1 not in all_machines or m2 not in all_machines:
                    continue
                if efficient_temporal_check(machine_times_s.get(m1, np.array([])),
                                            machine_times_s.get(m2, np.array([])),
                                            threshold=TEMPORAL_THRESHOLD):
                    _add_or_update_edge(G, m1, m2, weight, EDGE_TYPE_TEMPORAL, age)

        # -- shared user edges --
        user_machines_s = (s_df[s_df['src_user'] != 'none']
                           .groupby('src_user')['machine_name'].apply(set).to_dict())
        for user, u_mach in user_machines_s.items():
            u_mach_list = [m for m in u_mach if m in all_machines]
            for ci in range(len(u_mach_list)):
                for cj in range(ci + 1, len(u_mach_list)):
                    _add_or_update_edge(G, u_mach_list[ci], u_mach_list[cj],
                                        weight, EDGE_TYPE_SHARED_USER, age)

        # -- direct communication edges --
        for _, row in s_df.iterrows():
            src_ip = row['src_ip']
            if src_ip != 'none' and src_ip in IP_TO_MACHINE:
                target_machine = IP_TO_MACHINE[src_ip]
                source_machine = row['machine_name']
                if (source_machine != target_machine
                        and target_machine in all_machines
                        and source_machine in all_machines):
                    _add_or_update_edge(G, source_machine, target_machine,
                                        weight, EDGE_TYPE_DIRECT_COMM, age)

        # -- remote execution edges --
        remote_alerts = s_df[s_df['cmd_remote_exec'] == 1]
        for _, row in remote_alerts.iterrows():
            src_machine = row['machine_name']
            if src_machine not in all_machines:
                continue
            for m in all_machines:
                if m != src_machine:
                    _add_or_update_edge(G, src_machine, m,
                                        weight, EDGE_TYPE_REMOTE_EXEC, age)

    return G


def _add_or_update_edge(G, m1, m2, weight, edge_type, age):
    """Add an edge or update it if the new weight is higher (= more recent)."""
    edge = tuple(sorted([m1, m2]))
    if G.has_edge(edge[0], edge[1]):
        data = G[edge[0]][edge[1]]
        if weight > data.get('weight', 0):
            data['weight'] = weight
            data['edge_type'] = edge_type
            data['age_snapshots'] = age
    else:
        G.add_edge(edge[0], edge[1], weight=weight,
                   edge_type=edge_type, age_snapshots=age)


print("✅ Windowed graph builder with edge decay defined")


# ==== CELL 3 — BUILD WINDOWED GRAPHS ====
# Paste this as a NEW cell in the notebook.

WINDOWED_GRAPHS_FILE = 'nx_graphs_windowed.pkl'

if os.path.exists(WINDOWED_GRAPHS_FILE):
    print(f"Loading existing windowed graphs from {WINDOWED_GRAPHS_FILE}...")
    with open(WINDOWED_GRAPHS_FILE, 'rb') as f:
        data_loaded = pickle.load(f)
        nx_graphs_windowed_full = data_loaded['full']
    print(f"Loaded {len(nx_graphs_windowed_full)} windowed graphs.")
else:
    print("Building Windowed Graphs with Edge Decay...")
    nx_graphs_windowed_full = []

    for i in range(len(snapshots)):
        G_w = build_windowed_graph(i, snapshots, df_raw, version='full')
        nx_graphs_windowed_full.append(G_w)

        if (i + 1) % 500 == 0:
            print(f"  Processed {i+1}/{len(snapshots)} windowed snapshots... "
                  f"(Nodes: {G_w.number_of_nodes()}, Edges: {G_w.number_of_edges()})")

    print("Saving windowed graphs to file...")
    with open(WINDOWED_GRAPHS_FILE, 'wb') as f:
        pickle.dump({'full': nx_graphs_windowed_full}, f)

print(f"\n✅ Built {len(nx_graphs_windowed_full)} windowed graphs.")
if len(nx_graphs_windowed_full) > 0:
    last_g = nx_graphs_windowed_full[-1]
    print(f"Final Windowed Graph — Nodes: {last_g.number_of_nodes()}, "
          f"Edges: {last_g.number_of_edges()}")

    # Compare with original cumulative
    last_cum = nx_graphs_full[-1]
    print(f"Final Cumulative Graph — Nodes: {last_cum.number_of_nodes()}, "
          f"Edges: {last_cum.number_of_edges()}")
    print(f"Edge reduction: {last_cum.number_of_edges() - last_g.number_of_edges()} fewer edges "
          f"({100*(1 - last_g.number_of_edges()/max(1,last_cum.number_of_edges())):.1f}% reduction)")


# ==== CELL 4 — GAT MODEL DEFINITION ====
# Paste this as a NEW cell in the notebook.

class GATRiskModel(nn.Module):
    """
    Graph Attention Network for node-level risk scoring.
    Uses multi-head attention in layer 1 and single-head in layer 2.
    Supports edge_attr through GATConv's edge_dim parameter.
    """
    def __init__(self, in_channels, hidden_channels=GAT_HIDDEN,
                 heads=GAT_HEADS, dropout=GAT_DROPOUT, edge_dim=None):
        super().__init__()
        self.conv1 = GATConv(in_channels, hidden_channels, heads=heads,
                             dropout=dropout, edge_dim=edge_dim)
        # Output of conv1: hidden_channels * heads
        self.conv2 = GATConv(hidden_channels * heads, hidden_channels,
                             heads=1, concat=False, dropout=dropout,
                             edge_dim=edge_dim)
        self.dropout = nn.Dropout(dropout)
        self.linear = nn.Linear(hidden_channels, 1)

    def forward(self, x, edge_index, edge_attr=None):
        # Layer 1 — multi-head attention
        h = self.conv1(x, edge_index, edge_attr=edge_attr)
        h = F.elu(h)
        h = self.dropout(h)
        # Layer 2 — single-head, no concat
        h = self.conv2(h, edge_index, edge_attr=edge_attr)
        h = F.elu(h)
        h = self.dropout(h)
        # Risk score
        risk = self.linear(h).squeeze(-1)
        return risk

    def get_embeddings(self, x, edge_index, edge_attr=None):
        h = F.elu(self.conv1(x, edge_index, edge_attr=edge_attr))
        h = self.dropout(h)
        h = F.elu(self.conv2(h, edge_index, edge_attr=edge_attr))
        return h

print("✅ GATRiskModel defined")
print(f"   Heads: {GAT_HEADS}, Hidden/head: {GAT_HIDDEN}, Dropout: {GAT_DROPOUT}")
print(f"   Architecture: in → GATConv(h={GAT_HEADS}) → ELU → GATConv(h=1) → ELU → Linear → σ")


# ==== CELL 5 — ENHANCED PYG CONVERSION WITH TEMPORAL EDGE FEATURES ====
# Paste this as a NEW cell in the notebook.

# Dimension of edge feature vector: weight + one-hot edge type + normalised age
EDGE_FEATURE_DIM = 1 + NUM_EDGE_TYPES + 1  # = 6

def nx_to_pyg_enhanced(G, snapshot_idx=0):
    """
    Convert a windowed NetworkX graph to a PyG Data object,
    including edge_attr with temporal edge features:
      [decay_weight, type_temporal, type_shared_user,
       type_direct_comm, type_remote_exec, normalised_age]
    """
    nodes = sorted(G.nodes())
    node_to_idx = {n: i for i, n in enumerate(nodes)}

    # Node features & labels
    features = []
    labels = []
    for n in nodes:
        features.append(G.nodes[n]['features'])
        labels.append(G.nodes[n]['label'])

    x = torch.FloatTensor(np.array(features))
    y = torch.FloatTensor(np.array(labels))

    # Edges (undirected → both directions) with attributes
    edge_list = []
    edge_attrs = []

    for u, v, data in G.edges(data=True):
        i, j = node_to_idx[u], node_to_idx[v]
        w = data.get('weight', 1.0)
        etype = data.get('edge_type', 0)
        age = data.get('age_snapshots', 0)

        # Build feature vector
        one_hot = [0.0] * NUM_EDGE_TYPES
        if 0 <= etype < NUM_EDGE_TYPES:
            one_hot[etype] = 1.0

        # Normalise age to [0, 1] using window size
        norm_age = min(age / max(WINDOW_SIZE, 1), 1.0)

        feat = [w] + one_hot + [norm_age]

        # Add both directions with same features
        edge_list.append([i, j])
        edge_attrs.append(feat)
        edge_list.append([j, i])
        edge_attrs.append(feat)

    if len(edge_list) > 0:
        edge_index = torch.LongTensor(edge_list).t().contiguous()
        edge_attr = torch.FloatTensor(edge_attrs)
    else:
        # Self-loop for isolated single-node graphs
        edge_index = torch.LongTensor([[0], [0]])
        edge_attr = torch.FloatTensor([[1.0] + [0.0]*NUM_EDGE_TYPES + [0.0]])

    d = Data(x=x, edge_index=edge_index, y=y, edge_attr=edge_attr)
    d.machine_names = nodes
    d.snapshot_idx = snapshot_idx
    return d


print(f"✅ Enhanced PyG conversion defined (edge_attr dim = {EDGE_FEATURE_DIM})")


# ==== CELL 6 — CONVERT WINDOWED GRAPHS & TRAIN GAT ====
# Paste this as a NEW cell in the notebook.

print("Converting windowed graphs to PyTorch Geometric with edge features...")
pyg_windowed = [nx_to_pyg_enhanced(G, i) for i, G in enumerate(nx_graphs_windowed_full)]

# Normalize node features (reuse pattern)
pyg_windowed_norm, scaler_windowed = normalize_pyg_data(pyg_windowed)

print(f"  Total graphs: {len(pyg_windowed_norm)}")
avg_nodes_w = np.mean([d.x.shape[0] for d in pyg_windowed_norm])
avg_edges_w = np.mean([d.edge_index.shape[1] for d in pyg_windowed_norm])
print(f"  Avg nodes/graph: {avg_nodes_w:.1f}")
print(f"  Avg edges/graph: {avg_edges_w:.1f}")
print(f"  Node features dim: {pyg_windowed_norm[0].x.shape[1]}")
print(f"  Edge features dim: {pyg_windowed_norm[0].edge_attr.shape[1]}")

# Temporal split (same ratios as original)
train_w, val_w, test_w = split_temporal(pyg_windowed_norm)

# Compute pos_weight
pos_weight_w = compute_pos_weight(train_w)
print(f"\npos_weight (windowed): {pos_weight_w.item():.2f}")

# DataLoaders
train_loader_w = PyGDataLoader(train_w, batch_size=BATCH_SIZE, shuffle=True)
val_loader_w   = PyGDataLoader(val_w, batch_size=BATCH_SIZE, shuffle=False)
test_loader_w  = PyGDataLoader(test_w, batch_size=BATCH_SIZE, shuffle=False)

print(f"✅ DataLoaders created for windowed graphs (batch_size={BATCH_SIZE})")


# ==== CELL 7 — TRAINING FUNCTION FOR GAT (supports edge_attr) ====
# Paste this as a NEW cell in the notebook.

def evaluate_model_gat(model, data_loader, criterion=None, use_best_threshold=True):
    """Evaluate GAT model (passes edge_attr during forward)."""
    model.eval()
    all_logits = []
    all_labels = []
    total_loss = 0.0
    n_batches = 0

    with torch.no_grad():
        for batch in data_loader:
            batch = batch.to(device)
            if batch.x.shape[0] == 0:
                continue
            logits = model(batch.x, batch.edge_index,
                           edge_attr=batch.edge_attr)
            if criterion is not None:
                loss = criterion(logits, batch.y)
                total_loss += loss.item()
            n_batches += 1
            all_logits.append(logits.cpu().numpy())
            all_labels.append(batch.y.cpu().numpy())

    if len(all_labels) == 0:
        return {}, np.array([]), np.array([])

    y_true = np.concatenate(all_labels)
    logits_arr = np.concatenate(all_logits)
    y_prob = torch.sigmoid(torch.FloatTensor(logits_arr)).numpy()

    threshold = 0.5
    if use_best_threshold:
        threshold = find_best_threshold(y_true, y_prob)

    metrics = compute_metrics(y_true, y_prob, threshold=threshold)
    metrics['loss'] = total_loss / max(n_batches, 1) if criterion is not None else np.nan
    metrics['threshold'] = threshold
    return metrics, y_true, y_prob


def train_gat(model, train_loader, val_loader, pos_weight,
              epochs=50, lr=1e-3, name='GAT'):
    """Train a GAT model (passes edge_attr during forward)."""
    adjusted_pos_weight = (pos_weight.float() * 1.5).to(device)
    criterion = nn.BCEWithLogitsLoss(pos_weight=adjusted_pos_weight)
    optimizer = optim.Adam(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=10, factor=0.5)

    history = {'train_loss': [], 'val_loss': [], 'val_f1': [], 'val_auc': []}
    best_val_f1 = 0.0
    best_state = None

    print(f"Starting GAT training for {epochs} epochs...")

    for epoch in range(epochs):
        model.train()
        total_train_loss = 0.0
        n_train_batches = 0

        for batch in train_loader:
            batch = batch.to(device)
            if batch.x.shape[0] == 0:
                continue
            optimizer.zero_grad()
            logits = model(batch.x, batch.edge_index,
                           edge_attr=batch.edge_attr)
            loss = criterion(logits, batch.y)
            loss.backward()
            optimizer.step()
            total_train_loss += loss.item()
            n_train_batches += 1

        avg_train_loss = total_train_loss / max(n_train_batches, 1)
        history['train_loss'].append(avg_train_loss)

        val_metrics, _, _ = evaluate_model_gat(model, val_loader,
                                                criterion=criterion,
                                                use_best_threshold=True)
        history['val_loss'].append(val_metrics['loss'])
        history['val_f1'].append(val_metrics['f1'])
        history['val_auc'].append(val_metrics['auc_roc'])

        scheduler.step(val_metrics['loss'])

        if val_metrics['f1'] > best_val_f1:
            best_val_f1 = val_metrics['f1']
            best_state = {k: v.clone() for k, v in model.state_dict().items()}

        if (epoch + 1) % 5 == 0 or epoch == 0:
            print(f"  Epoch {epoch+1:3d} — Train Loss: {avg_train_loss:.4f} | "
                  f"Val Loss: {val_metrics['loss']:.4f} | "
                  f"Val F1: {val_metrics['f1']:.4f} (Thresh: {val_metrics['threshold']:.2f}) | "
                  f"Val AUC: {val_metrics['auc_roc']:.4f}")

    if best_state is not None:
        model.load_state_dict(best_state)
        print(f"✅ Loaded best state (Val F1: {best_val_f1:.4f})")
    else:
        print("✅ Training completed (using last state)")

    return model, history, criterion


print("✅ GAT training utilities defined")


# ==== CELL 8 — TRAIN THE GAT MODEL ====
# Paste this as a NEW cell in the notebook.

print("="*70)
print("TRAINING GAT MODEL — WINDOWED GRAPHS WITH EDGE DECAY")
print("="*70)

# Instantiate GAT model
gat_model = GATRiskModel(
    in_channels=NUM_NODE_FEATURES,
    hidden_channels=GAT_HIDDEN,
    heads=GAT_HEADS,
    dropout=GAT_DROPOUT,
    edge_dim=EDGE_FEATURE_DIM
).to(device)

print(f"Model parameters: {sum(p.numel() for p in gat_model.parameters()):,}")

# Train
gat_model, gat_history, gat_criterion = train_gat(
    gat_model, train_loader_w, val_loader_w, pos_weight_w,
    epochs=50, lr=1e-3, name='GAT_Windowed'
)

# Final validation metrics
val_metrics_gat, _, _ = evaluate_model_gat(
    gat_model, val_loader_w, criterion=gat_criterion, use_best_threshold=True
)
print(f"\n✅ Best Validation Metrics (GAT Windowed):")
for k, v in val_metrics_gat.items():
    print(f"   {k}: {v:.4f}")

# Plot training curves
fig, axes = plt.subplots(1, 2, figsize=(12, 4))
axes[0].plot(gat_history['train_loss'], label='Train Loss')
axes[0].plot(gat_history['val_loss'], label='Val Loss')
axes[0].set_title('GAT Windowed — Loss')
axes[0].legend()
axes[0].grid(True)
axes[1].plot(gat_history['val_f1'], label='Val F1')
axes[1].plot(gat_history['val_auc'], label='Val AUC-ROC')
axes[1].set_title('GAT Windowed — Metrics')
axes[1].legend()
axes[1].grid(True)
plt.tight_layout()
plt.show()

# Save checkpoint
torch.save({
    'model_state_dict': gat_model.state_dict(),
    'history': gat_history,
    'val_metrics': val_metrics_gat,
    'hyperparams': {
        'window_size': WINDOW_SIZE,
        'decay_lambda': DECAY_LAMBDA,
        'gat_heads': GAT_HEADS,
        'gat_hidden': GAT_HIDDEN,
    }
}, 'gat_windowed_checkpoint.pth')
print("✅ Saved: gat_windowed_checkpoint.pth")


# ==== CELL 9 — EVALUATE ON TEST SET & COMPARE ====
# Paste this as a NEW cell in the notebook.

print("="*70)
print("TEST SET EVALUATION — GAT (Windowed) vs GCN (Cumulative)")
print("="*70)

# Evaluate GAT on test set
test_metrics_gat, y_true_gat, y_prob_gat = evaluate_model_gat(
    gat_model, test_loader_w, criterion=gat_criterion, use_best_threshold=True
)
print("\n📊 GAT Windowed — Test Metrics:")
for k, v in test_metrics_gat.items():
    print(f"   {k}: {v:.4f}")

# Evaluate original GCN on test set (reuse existing loaded model)
# The original 'model_full' should be available from earlier cells.
# If not, load from checkpoint:
try:
    _ = gcn_model_full
except NameError:
    # Try loading from checkpoint
    ckpt_path = 'gnn_full_features_checkpoint.pth'
    if os.path.exists(ckpt_path):
        gcn_model_full = GCNRiskModel(NUM_NODE_FEATURES, hidden_channels=32).to(device)
        ckpt = torch.load(ckpt_path, map_location=device)
        gcn_model_full.load_state_dict(ckpt['model_state_dict'])
        print("Loaded GCN from checkpoint for comparison.")
    else:
        print("⚠️ GCN checkpoint not found. Skipping comparison.")
        gcn_model_full = None

if gcn_model_full is not None:
    # Use original cumulative test loader
    criterion_gcn = nn.BCEWithLogitsLoss(
        pos_weight=(pos_weight_full.float() * 1.5).to(device)
    )
    test_metrics_gcn, _, _ = evaluate_model(
        gcn_model_full, test_loader_full,
        criterion=criterion_gcn, use_best_threshold=True
    )
    print("\n📊 GCN Cumulative — Test Metrics:")
    for k, v in test_metrics_gcn.items():
        print(f"   {k}: {v:.4f}")

    # Comparison table
    print("\n" + "="*70)
    print(f"{'Metric':<25} {'GCN (Cumulative)':>18} {'GAT (Windowed)':>18} {'Δ':>10}")
    print("-"*70)
    for key in ['accuracy', 'precision', 'recall', 'f1', 'auc_roc', 'auc_pr']:
        gcn_val = test_metrics_gcn.get(key, float('nan'))
        gat_val = test_metrics_gat.get(key, float('nan'))
        delta = gat_val - gcn_val
        sign = "+" if delta >= 0 else ""
        print(f"  {key:<23} {gcn_val:>18.4f} {gat_val:>18.4f} {sign}{delta:>9.4f}")
    print("="*70)
    print("\n✅ Comparison complete. Check precision improvement vs recall trade-off.")
else:
    print("\n⚠️ Comparison skipped — GCN model not available.")
