"""
============================================================
GNN IMPROVEMENTS v2 — TUNED VERSION
============================================================

FIXES from v1:
  1. Window too narrow → graphs were too sparse (avg 1.6 edges).
     FIX: Increased window, reduced decay rate.
  2. pos_weight was 0.19 → model was penalizing positive predictions.
     FIX: Corrected pos_weight direction (neg/pos ratio) so positives
     are upweighted when they are the minority class.
  3. Severe overfitting → val loss diverged from epoch 1.
     FIX: Stronger dropout, weight decay, early stopping, and
     fewer parameters (2 heads instead of 4).

INSTRUCTIONS: Replace the old new cells (43-51) with these 9 cells.
Run all original cells first, then these.
============================================================
"""

# ==== CELL 1 — IMPORTS & TUNED HYPERPARAMETERS ====

from torch_geometric.nn import GATConv
import math

# ----- Tuned hyperparameters -----
WINDOW_SIZE       = 2000     # Wider window to keep more edges (was 500)
DECAY_LAMBDA      = 0.002    # Gentler decay (was 0.05) — edge at age 500 still ~37%
DECAY_MIN_WEIGHT  = 0.001    # Lower prune threshold
GAT_HEADS         = 2        # Fewer heads to reduce overfitting (was 4)
GAT_HIDDEN        = 16       # Smaller hidden dim (was 32) — less capacity = less overfit
GAT_DROPOUT       = 0.5      # Stronger dropout (was 0.3)
GAT_WEIGHT_DECAY  = 5e-4     # Stronger L2 reg (was 1e-4)
GAT_LR            = 5e-4     # Lower LR (was 1e-3) — smoother convergence
GAT_EPOCHS        = 80       # More epochs with early stopping
EARLY_STOP_PATIENCE = 15     # Stop if val F1 doesn't improve for 15 epochs
POS_WEIGHT_MULTIPLIER = 2.0  # Upweight positives more aggressively

print("✅ v2 Hyperparameters loaded")
print(f"   Window: {WINDOW_SIZE}, λ: {DECAY_LAMBDA}, min_w: {DECAY_MIN_WEIGHT}")
print(f"   GAT: heads={GAT_HEADS}, hidden={GAT_HIDDEN}, drop={GAT_DROPOUT}")
print(f"   Training: lr={GAT_LR}, wd={GAT_WEIGHT_DECAY}, epochs={GAT_EPOCHS}, patience={EARLY_STOP_PATIENCE}")


# ==== CELL 2 — WINDOWED GRAPH CONSTRUCTION WITH EDGE DECAY (same logic, uses new params) ====

EDGE_TYPE_TEMPORAL    = 0
EDGE_TYPE_SHARED_USER = 1
EDGE_TYPE_DIRECT_COMM = 2
EDGE_TYPE_REMOTE_EXEC = 3
NUM_EDGE_TYPES = 4

def _add_or_update_edge(G, m1, m2, weight, edge_type, age):
    """Add edge or update if new weight is higher (more recent)."""
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


def build_windowed_graph(snapshot_idx, snapshots, df_raw, version='full',
                         window_size=WINDOW_SIZE, decay_lambda=DECAY_LAMBDA,
                         decay_min_weight=DECAY_MIN_WEIGHT):
    """
    Build graph using sliding window + exponential edge decay.
    """
    G = nx.Graph()

    snap = snapshots[snapshot_idx]
    curr_end_idx = snap['end_idx']

    win_start_snap = max(0, snapshot_idx - window_size + 1)
    if win_start_snap == 0:
        data_start = 0
    else:
        data_start = snapshots[win_start_snap - 1]['end_idx'] + 1

    window_df = df_raw.iloc[data_start : curr_end_idx + 1].copy()

    prev_end = snapshots[snapshot_idx - 1]['end_idx'] if snapshot_idx > 0 else -1
    new_df = df_raw.iloc[prev_end + 1 : curr_end_idx + 1]

    machines_in_window = window_df['machine_name'].unique()
    new_machines = new_df['machine_name'].unique() if len(new_df) > 0 else []

    # --- Node features & labels ---
    for machine in machines_in_window:
        machine_history = window_df[window_df['machine_name'] == machine]
        features = get_node_features(machine_history, version=version)

        if machine in new_machines:
            machine_new = new_df[new_df['machine_name'] == machine]
            has_malicious = int(machine_new['label'].max() > 0)
        else:
            has_malicious = 0

        G.add_node(machine, features=features, label=has_malicious)

    # --- Edges with decay ---
    all_machines = list(machines_in_window)

    for s_idx in range(win_start_snap, snapshot_idx + 1):
        s = snapshots[s_idx]
        s_end = s['end_idx']
        s_start_data = (snapshots[s_idx - 1]['end_idx'] + 1) if s_idx > 0 else 0
        s_df = df_raw.iloc[s_start_data : s_end + 1]

        age = snapshot_idx - s_idx
        weight = math.exp(-decay_lambda * age)
        if weight < decay_min_weight:
            continue

        s_machines = set(s_df['machine_name'].unique())

        # Temporal proximity
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

        # Shared user
        user_machines_s = (s_df[s_df['src_user'] != 'none']
                           .groupby('src_user')['machine_name'].apply(set).to_dict())
        for user, u_mach in user_machines_s.items():
            u_mach_list = [m for m in u_mach if m in all_machines]
            for ci in range(len(u_mach_list)):
                for cj in range(ci + 1, len(u_mach_list)):
                    _add_or_update_edge(G, u_mach_list[ci], u_mach_list[cj],
                                        weight, EDGE_TYPE_SHARED_USER, age)

        # Direct communication
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

        # Remote execution
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


print("✅ Windowed graph builder defined (v2 tuned params)")


# ==== CELL 3 — BUILD WINDOWED GRAPHS ====

WINDOWED_GRAPHS_FILE_V2 = 'nx_graphs_windowed_v2.pkl'

if os.path.exists(WINDOWED_GRAPHS_FILE_V2):
    print(f"Loading existing windowed graphs from {WINDOWED_GRAPHS_FILE_V2}...")
    with open(WINDOWED_GRAPHS_FILE_V2, 'rb') as f:
        data_loaded = pickle.load(f)
        nx_graphs_windowed_full = data_loaded['full']
    print(f"Loaded {len(nx_graphs_windowed_full)} windowed graphs.")
else:
    print("Building Windowed Graphs v2...")
    nx_graphs_windowed_full = []

    for i in range(len(snapshots)):
        G_w = build_windowed_graph(i, snapshots, df_raw, version='full')
        nx_graphs_windowed_full.append(G_w)

        if (i + 1) % 500 == 0:
            print(f"  Processed {i+1}/{len(snapshots)} windowed snapshots... "
                  f"(Nodes: {G_w.number_of_nodes()}, Edges: {G_w.number_of_edges()})")

    print("Saving windowed graphs...")
    with open(WINDOWED_GRAPHS_FILE_V2, 'wb') as f:
        pickle.dump({'full': nx_graphs_windowed_full}, f)

print(f"\n✅ Built {len(nx_graphs_windowed_full)} windowed graphs (v2).")
if len(nx_graphs_windowed_full) > 0:
    last_g = nx_graphs_windowed_full[-1]
    print(f"Final Windowed Graph  — Nodes: {last_g.number_of_nodes()}, Edges: {last_g.number_of_edges()}")
    last_cum = nx_graphs_full[-1]
    print(f"Final Cumulative Graph — Nodes: {last_cum.number_of_nodes()}, Edges: {last_cum.number_of_edges()}")
    # Edge density stats
    all_edges = [g.number_of_edges() for g in nx_graphs_windowed_full]
    print(f"Avg edges/graph (windowed): {np.mean(all_edges):.1f}")


# ==== CELL 4 — GAT MODEL DEFINITION (v2 — smaller, with early stopping) ====

EDGE_FEATURE_DIM = 1 + NUM_EDGE_TYPES + 1  # = 6

class GATRiskModel(nn.Module):
    """
    Graph Attention Network — v2 (less capacity, more regularization).
    """
    def __init__(self, in_channels, hidden_channels=GAT_HIDDEN,
                 heads=GAT_HEADS, dropout=GAT_DROPOUT, edge_dim=None):
        super().__init__()
        self.conv1 = GATConv(in_channels, hidden_channels, heads=heads,
                             dropout=dropout, edge_dim=edge_dim)
        self.bn1 = nn.BatchNorm1d(hidden_channels * heads)
        self.conv2 = GATConv(hidden_channels * heads, hidden_channels,
                             heads=1, concat=False, dropout=dropout,
                             edge_dim=edge_dim)
        self.bn2 = nn.BatchNorm1d(hidden_channels)
        self.dropout = nn.Dropout(dropout)
        self.linear = nn.Linear(hidden_channels, 1)

    def forward(self, x, edge_index, edge_attr=None):
        h = self.conv1(x, edge_index, edge_attr=edge_attr)
        h = self.bn1(h)
        h = F.elu(h)
        h = self.dropout(h)
        h = self.conv2(h, edge_index, edge_attr=edge_attr)
        h = self.bn2(h)
        h = F.elu(h)
        h = self.dropout(h)
        return self.linear(h).squeeze(-1)

    def get_embeddings(self, x, edge_index, edge_attr=None):
        h = F.elu(self.bn1(self.conv1(x, edge_index, edge_attr=edge_attr)))
        h = self.dropout(h)
        h = F.elu(self.bn2(self.conv2(h, edge_index, edge_attr=edge_attr)))
        return h


print(f"✅ GATRiskModel v2 defined (heads={GAT_HEADS}, hidden={GAT_HIDDEN}, "
      f"edge_dim={EDGE_FEATURE_DIM}, with BatchNorm)")


# ==== CELL 5 — ENHANCED PYG CONVERSION ====

def nx_to_pyg_enhanced(G, snapshot_idx=0):
    """Convert windowed NX graph to PyG Data with edge_attr."""
    nodes = sorted(G.nodes())
    node_to_idx = {n: i for i, n in enumerate(nodes)}

    features, labels = [], []
    for n in nodes:
        features.append(G.nodes[n]['features'])
        labels.append(G.nodes[n]['label'])

    x = torch.FloatTensor(np.array(features))
    y = torch.FloatTensor(np.array(labels))

    edge_list, edge_attrs = [], []
    for u, v, data in G.edges(data=True):
        i, j = node_to_idx[u], node_to_idx[v]
        w = data.get('weight', 1.0)
        etype = data.get('edge_type', 0)
        age = data.get('age_snapshots', 0)

        one_hot = [0.0] * NUM_EDGE_TYPES
        if 0 <= etype < NUM_EDGE_TYPES:
            one_hot[etype] = 1.0
        norm_age = min(age / max(WINDOW_SIZE, 1), 1.0)
        feat = [w] + one_hot + [norm_age]

        edge_list.append([i, j]); edge_attrs.append(feat)
        edge_list.append([j, i]); edge_attrs.append(feat)

    if len(edge_list) > 0:
        edge_index = torch.LongTensor(edge_list).t().contiguous()
        edge_attr = torch.FloatTensor(edge_attrs)
    else:
        edge_index = torch.LongTensor([[0], [0]])
        edge_attr = torch.FloatTensor([[1.0] + [0.0]*NUM_EDGE_TYPES + [0.0]])

    d = Data(x=x, edge_index=edge_index, y=y, edge_attr=edge_attr)
    d.machine_names = nodes
    d.snapshot_idx = snapshot_idx
    return d


print(f"✅ Enhanced PyG conversion defined (edge_attr dim = {EDGE_FEATURE_DIM})")


# ==== CELL 6 — DATA PREP ====

print("Converting windowed graphs to PyG...")
pyg_windowed = [nx_to_pyg_enhanced(G, i) for i, G in enumerate(nx_graphs_windowed_full)]
pyg_windowed_norm, scaler_windowed = normalize_pyg_data(pyg_windowed)

avg_nodes_w = np.mean([d.x.shape[0] for d in pyg_windowed_norm])
avg_edges_w = np.mean([d.edge_index.shape[1] for d in pyg_windowed_norm])
print(f"  Graphs: {len(pyg_windowed_norm)}, Avg nodes: {avg_nodes_w:.1f}, Avg edges: {avg_edges_w:.1f}")
print(f"  Node feat dim: {pyg_windowed_norm[0].x.shape[1]}, Edge feat dim: {pyg_windowed_norm[0].edge_attr.shape[1]}")

# Temporal split
train_w, val_w, test_w = split_temporal(pyg_windowed_norm)

# --- CORRECTED pos_weight ---
# pos_weight = neg_count / pos_count  (upweight the *minority* class)
total_pos = sum(d.y.sum().item() for d in train_w)
total_neg = sum((d.y == 0).sum().item() for d in train_w)
total_all = total_pos + total_neg
print(f"\n  Train: {len(train_w)} graphs — {int(total_pos)} positive nodes, "
      f"{int(total_neg)} negative nodes ({100*total_pos/max(total_all,1):.1f}% positive)")

if total_pos > 0:
    raw_pos_weight = total_neg / total_pos
else:
    raw_pos_weight = 1.0

# Apply multiplier to further upweight positives
pos_weight_w = torch.tensor(raw_pos_weight * POS_WEIGHT_MULTIPLIER)
print(f"  Raw pos_weight: {raw_pos_weight:.2f}, with {POS_WEIGHT_MULTIPLIER}x multiplier: {pos_weight_w.item():.2f}")

# DataLoaders
train_loader_w = PyGDataLoader(train_w, batch_size=BATCH_SIZE, shuffle=True)
val_loader_w   = PyGDataLoader(val_w, batch_size=BATCH_SIZE, shuffle=False)
test_loader_w  = PyGDataLoader(test_w, batch_size=BATCH_SIZE, shuffle=False)

print(f"✅ Data ready. Train: {len(train_w)}, Val: {len(val_w)}, Test: {len(test_w)}")


# ==== CELL 7 — TRAINING WITH EARLY STOPPING (supports edge_attr) ====

def evaluate_model_gat(model, data_loader, criterion=None, use_best_threshold=True):
    """Evaluate GAT model."""
    model.eval()
    all_logits, all_labels = [], []
    total_loss, n_batches = 0.0, 0

    with torch.no_grad():
        for batch in data_loader:
            batch = batch.to(device)
            if batch.x.shape[0] == 0:
                continue
            logits = model(batch.x, batch.edge_index, edge_attr=batch.edge_attr)
            if criterion is not None:
                total_loss += criterion(logits, batch.y).item()
            n_batches += 1
            all_logits.append(logits.cpu().numpy())
            all_labels.append(batch.y.cpu().numpy())

    if not all_labels:
        return {}, np.array([]), np.array([])

    y_true = np.concatenate(all_labels)
    y_prob = torch.sigmoid(torch.FloatTensor(np.concatenate(all_logits))).numpy()

    threshold = find_best_threshold(y_true, y_prob) if use_best_threshold else 0.5
    metrics = compute_metrics(y_true, y_prob, threshold=threshold)
    metrics['loss'] = total_loss / max(n_batches, 1) if criterion else float('nan')
    metrics['threshold'] = threshold
    return metrics, y_true, y_prob


def train_gat_v2(model, train_loader, val_loader, pos_weight,
                 epochs=GAT_EPOCHS, lr=GAT_LR, weight_decay=GAT_WEIGHT_DECAY,
                 patience=EARLY_STOP_PATIENCE):
    """Train GAT with early stopping on val F1."""
    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight.float().to(device))
    optimizer = optim.Adam(model.parameters(), lr=lr, weight_decay=weight_decay)
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=7, factor=0.5, min_lr=1e-6)

    history = {'train_loss': [], 'val_loss': [], 'val_f1': [],
               'val_auc': [], 'val_prec': [], 'val_rec': []}
    best_val_f1 = 0.0
    best_state = None
    no_improve = 0

    print(f"Training GAT v2 for up to {epochs} epochs (patience={patience})...")

    for epoch in range(epochs):
        model.train()
        total_loss, n = 0.0, 0
        for batch in train_loader:
            batch = batch.to(device)
            if batch.x.shape[0] == 0: continue
            optimizer.zero_grad()
            logits = model(batch.x, batch.edge_index, edge_attr=batch.edge_attr)
            loss = criterion(logits, batch.y)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            total_loss += loss.item(); n += 1

        avg_loss = total_loss / max(n, 1)
        history['train_loss'].append(avg_loss)

        val_m, _, _ = evaluate_model_gat(model, val_loader, criterion, True)
        history['val_loss'].append(val_m['loss'])
        history['val_f1'].append(val_m['f1'])
        history['val_auc'].append(val_m['auc_roc'])
        history['val_prec'].append(val_m['precision'])
        history['val_rec'].append(val_m['recall'])

        scheduler.step(val_m['loss'])

        improved = ""
        if val_m['f1'] > best_val_f1:
            best_val_f1 = val_m['f1']
            best_state = {k: v.clone() for k, v in model.state_dict().items()}
            no_improve = 0
            improved = " *"
        else:
            no_improve += 1

        if (epoch + 1) % 5 == 0 or epoch == 0 or improved:
            print(f"  Ep {epoch+1:3d} — TrLoss: {avg_loss:.4f} | "
                  f"VLoss: {val_m['loss']:.4f} | "
                  f"P: {val_m['precision']:.3f} R: {val_m['recall']:.3f} "
                  f"F1: {val_m['f1']:.4f} (t={val_m['threshold']:.2f}) | "
                  f"AUC: {val_m['auc_roc']:.4f}{improved}")

        if no_improve >= patience:
            print(f"  Early stopping at epoch {epoch+1}")
            break

    if best_state:
        model.load_state_dict(best_state)
    print(f"✅ Best Val F1: {best_val_f1:.4f}")
    return model, history, criterion


print("✅ GAT v2 training utilities defined (with early stopping + grad clipping)")


# ==== CELL 8 — TRAIN GAT v2 ====

print("="*70)
print("TRAINING GAT v2 — TUNED WINDOWED GRAPHS")
print("="*70)

gat_model = GATRiskModel(
    in_channels=NUM_NODE_FEATURES,
    hidden_channels=GAT_HIDDEN,
    heads=GAT_HEADS,
    dropout=GAT_DROPOUT,
    edge_dim=EDGE_FEATURE_DIM
).to(device)

n_params = sum(p.numel() for p in gat_model.parameters())
print(f"Model parameters: {n_params:,}")
print(f"pos_weight: {pos_weight_w.item():.2f}")

gat_model, gat_history, gat_criterion = train_gat_v2(
    gat_model, train_loader_w, val_loader_w, pos_weight_w
)

# Validation summary
val_m, _, _ = evaluate_model_gat(gat_model, val_loader_w, gat_criterion, True)
print(f"\nValidation: P={val_m['precision']:.4f}  R={val_m['recall']:.4f}  "
      f"F1={val_m['f1']:.4f}  AUC={val_m['auc_roc']:.4f}")

# Plot
fig, axes = plt.subplots(1, 3, figsize=(16, 4))
axes[0].plot(gat_history['train_loss'], label='Train'); axes[0].plot(gat_history['val_loss'], label='Val')
axes[0].set_title('Loss'); axes[0].legend(); axes[0].grid(True)
axes[1].plot(gat_history['val_prec'], label='Precision'); axes[1].plot(gat_history['val_rec'], label='Recall')
axes[1].set_title('Precision vs Recall'); axes[1].legend(); axes[1].grid(True)
axes[2].plot(gat_history['val_f1'], label='F1'); axes[2].plot(gat_history['val_auc'], label='AUC-ROC')
axes[2].set_title('F1 & AUC'); axes[2].legend(); axes[2].grid(True)
plt.tight_layout(); plt.show()

torch.save({'model_state_dict': gat_model.state_dict(), 'history': gat_history,
            'val_metrics': val_m}, 'gat_windowed_v2_checkpoint.pth')
print("✅ Saved: gat_windowed_v2_checkpoint.pth")


# ==== CELL 9 — TEST SET COMPARISON ====

print("="*70)
print("TEST SET — GAT v2 (Windowed) vs Original GCN (Cumulative)")
print("="*70)

test_m_gat, y_true_gat, y_prob_gat = evaluate_model_gat(
    gat_model, test_loader_w, gat_criterion, True
)
print("\nGAT v2 Windowed — Test:")
print(f"  Precision: {test_m_gat['precision']:.4f}")
print(f"  Recall:    {test_m_gat['recall']:.4f}")
print(f"  F1:        {test_m_gat['f1']:.4f}")
print(f"  AUC-ROC:   {test_m_gat['auc_roc']:.4f}")
print(f"  AUC-PR:    {test_m_gat['auc_pr']:.4f}")
print(f"  Threshold: {test_m_gat['threshold']:.2f}")

# Try to compare with original GCN
try:
    criterion_gcn = nn.BCEWithLogitsLoss(
        pos_weight=(pos_weight_full.float() * 1.5).to(device))
    test_m_gcn, _, _ = evaluate_model(
        gcn_model_full, test_loader_full, criterion=criterion_gcn, use_best_threshold=True)

    print("\nOriginal GCN Cumulative — Test:")
    print(f"  Precision: {test_m_gcn['precision']:.4f}")
    print(f"  Recall:    {test_m_gcn['recall']:.4f}")
    print(f"  F1:        {test_m_gcn['f1']:.4f}")
    print(f"  AUC-ROC:   {test_m_gcn['auc_roc']:.4f}")
    print(f"  AUC-PR:    {test_m_gcn['auc_pr']:.4f}")

    print("\n" + "="*70)
    print(f"{'Metric':<20} {'GCN':>12} {'GAT v2':>12} {'Delta':>12}")
    print("-"*56)
    for k in ['precision', 'recall', 'f1', 'auc_roc', 'auc_pr']:
        g = test_m_gcn.get(k, 0); a = test_m_gat.get(k, 0)
        d = a - g; s = "+" if d >= 0 else ""
        print(f"  {k:<18} {g:>12.4f} {a:>12.4f} {s}{d:>11.4f}")
    print("="*70)
except Exception as e:
    print(f"\nCould not compare with GCN: {e}")
    print("Make sure the original GCN cells (14-15) have been run first.")
