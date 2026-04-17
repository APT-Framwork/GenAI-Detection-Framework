"""
GNN Propagation Loader
======================

Loads the GraphSAGE model for APT propagation detection.
Implements the same graph construction and RL state feature extraction
as in GNN_Network_Propagation.ipynb.

Model: gnn_propagation_best_no_rule.pth
Architecture:
    3 SAGEConv layers: (55→128), (128→128), (128→128)
    3 BatchNorm layers with residual connections
    Head: Linear(128→64), ReLU, Dropout(0.3), Linear(64→1)

Graph Construction (3 edge types + self-loops):
    1. Intra-machine temporal: same machine, 30-min window, max 3 neighbors
    2. Cross-machine user: same user, different machines, 30-min, max 5
    3. Cross-machine IP: same IP, different machines, 30-min, max 5
    4. Self-loops

RL State Features (3 features after redundancy removal):
    - GNN_node_risk_current_host: mean alert risk on target machine
    - GNN_neighbor_risk: mean risk on externally-connected machines
    - risk_growth: change in global risk vs previous time window
"""

import os
import time
import pickle
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, List, Optional, Tuple

try:
    from torch_geometric.nn import SAGEConv, BatchNorm
    from torch_geometric.data import Data
    HAS_PYG = True
except ImportError:
    HAS_PYG = False
    print("[WARNING] torch_geometric not installed. GNN features will be disabled.")


class APTPropagationGNN(nn.Module):
    """GraphSAGE for alert-level APT propagation detection."""

    def __init__(self, in_ch: int = 55, hid: int = 128, layers: int = 3, drop: float = 0.3):
        super().__init__()
        self.num_layers = layers
        self.drop = drop

        self.convs = nn.ModuleList()
        self.bns = nn.ModuleList()

        self.convs.append(SAGEConv(in_ch, hid))
        self.bns.append(BatchNorm(hid))
        for _ in range(layers - 1):
            self.convs.append(SAGEConv(hid, hid))
            self.bns.append(BatchNorm(hid))

        self.head = nn.Sequential(
            nn.Linear(hid, 64), nn.ReLU(), nn.Dropout(drop),
            nn.Linear(64, 1),
        )

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        for i in range(self.num_layers):
            x_in = x
            x = self.convs[i](x, edge_index)
            x = self.bns[i](x)
            x = F.relu(x)
            if i > 0:  # Residual from layer 1 onwards
                x = x + x_in
            x = F.dropout(x, p=self.drop, training=self.training)
        return self.head(x).squeeze(-1)


class GNNLoader:
    """
    Wrapper for loading and using the GNN propagation model.

    Handles graph construction, inference, and RL state feature extraction
    following the same methodology as GNN_Network_Propagation.ipynb.
    """

    # Graph construction parameters (from notebook)
    INTRA_WINDOW_SEC = 30 * 60   # 30 minutes
    CROSS_WINDOW_SEC = 30 * 60   # 30 minutes
    MAX_INTRA = 3
    MAX_CROSS = 5

    def __init__(
        self,
        model_path: Optional[str] = None,
        metadata_path: Optional[str] = None,
        device: str = 'cpu',
    ):
        """
        Initialize the GNNLoader.

        Args:
            model_path: Path to model checkpoint
            metadata_path: Path to metadata pickle (scaler, threshold, features)
            device: Device to load model on
        """
        self.device = torch.device(device)
        self.enabled = HAS_PYG

        if not self.enabled:
            print("[GNN] DISABLED — torch_geometric not installed")
            self.model = None
            self.threshold = 0.5
            self.scaler = None
            self.feature_cols = []
            return

        # Resolve paths
        if model_path is None:
            models_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'models')
            model_path = os.path.join(models_dir, 'gnn_propagation_best_no_rule.pth')
        if metadata_path is None:
            root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            metadata_path = os.path.join(root_dir, 'gnn_propagation_metadata.pkl')

        self.model_path = model_path
        self.metadata_path = metadata_path

        # Load metadata
        self._load_metadata()

        # Load model
        self.model = self._load_model()

        # Runtime state (populated after build_graph)
        self.graph_data = None
        self.df_rl = None
        self.alert_risks = None
        self.src_nodes = None
        self.dst_nodes = None

        print(f"[GNN] Loaded: {os.path.basename(model_path)}")
        print(f"      Features: {len(self.feature_cols)}, Threshold: {self.threshold:.4f}")

    def _load_metadata(self):
        """Load metadata (scaler, threshold, features) from pickle."""
        if os.path.exists(self.metadata_path):
            with open(self.metadata_path, 'rb') as f:
                metadata = pickle.load(f)
            self.feature_cols = metadata.get('features', [])
            self.threshold = metadata.get('threshold', 0.5)
            self.scaler = metadata.get('scaler', None)
            self.graph_params = metadata.get('graph_params', {})
            self.model_params = metadata.get('model_params', {})

            # Update window params if present
            if self.graph_params:
                self.INTRA_WINDOW_SEC = self.graph_params.get('intra_window_sec', self.INTRA_WINDOW_SEC)
                self.CROSS_WINDOW_SEC = self.graph_params.get('cross_window_sec', self.CROSS_WINDOW_SEC)
                self.MAX_INTRA = self.graph_params.get('max_intra', self.MAX_INTRA)
                self.MAX_CROSS = self.graph_params.get('max_cross', self.MAX_CROSS)
        else:
            print(f"[GNN] Warning: Metadata not found at {self.metadata_path}")
            self.feature_cols = []
            self.threshold = 0.918
            self.scaler = None
            self.graph_params = {}
            self.model_params = {}

    def _load_model(self) -> 'APTPropagationGNN':
        """Load the GNN model from checkpoint."""
        hid = self.model_params.get('hid', 128)
        layers = self.model_params.get('layers', 3)
        drop = self.model_params.get('drop', 0.3)

        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"GNN model not found: {self.model_path}")

        # Load checkpoint and detect actual input dimension from weights
        state_dict = torch.load(self.model_path, map_location=self.device, weights_only=False)
        if isinstance(state_dict, dict) and 'model_state_dict' in state_dict:
            state_dict = state_dict['model_state_dict']

        # Detect in_ch from first conv layer weight shape
        first_weight = state_dict.get('convs.0.lin_l.weight', None)
        if first_weight is not None:
            in_ch = first_weight.shape[1]
        else:
            in_ch = self.model_params.get('in_ch', 55)

        model = APTPropagationGNN(in_ch=in_ch, hid=hid, layers=layers, drop=drop).to(self.device)
        model.load_state_dict(state_dict, strict=True)
        model.eval()
        self._in_ch = in_ch

        return model

    def build_graph(self, df_raw: pd.DataFrame, feature_matrix: np.ndarray = None) -> 'Data':
        """
        Build the alert graph with 3 edge types + self-loops.
        Same methodology as GNN_Network_Propagation.ipynb.

        Args:
            df_raw: DataFrame with columns: timestamp, machine_name, src_user, src_ip
                    Plus the 55 feature columns
            feature_matrix: Optional pre-computed feature matrix (N, 55).
                          If None, extracted from df_raw using self.feature_cols.

        Returns:
            PyG Data object with node features, edge_index, and labels
        """
        if not self.enabled:
            return None

        t0 = time.time()
        n_nodes = len(df_raw)

        # Prepare feature matrix
        if feature_matrix is None:
            available_cols = [c for c in self.feature_cols if c in df_raw.columns]
            if len(available_cols) == 0:
                raise ValueError("No feature columns found in df_raw")
            feature_matrix = df_raw[available_cols].values.astype(np.float32)

        # Scale features if scaler available
        if self.scaler is not None:
            scaler_n = getattr(self.scaler, 'n_features_in_', feature_matrix.shape[1])
            if feature_matrix.shape[1] == scaler_n:
                feature_matrix = self.scaler.transform(feature_matrix)
            elif feature_matrix.shape[1] == scaler_n - 1:
                # Scaler was trained with rule_level (56 features), pad with 0
                padded = np.zeros((feature_matrix.shape[0], scaler_n), dtype=np.float32)
                padded[:, :feature_matrix.shape[1]] = feature_matrix
                feature_matrix = self.scaler.transform(padded)[:, :feature_matrix.shape[1]]
            else:
                print(f"[GNN] Warning: Skipping scaler (data={feature_matrix.shape[1]} vs scaler={scaler_n})")

        # Prepare temporal/machine data
        if 'timestamp' in df_raw.columns:
            timestamps = pd.to_datetime(df_raw['timestamp'], errors='coerce')
            timestamps_sec = (timestamps - timestamps.min()).dt.total_seconds().values
        else:
            timestamps_sec = np.arange(n_nodes, dtype=float)

        machine_names = df_raw.get('machine_name', pd.Series(['machine-1'] * n_nodes))
        machine_ids = pd.Categorical(machine_names).codes
        user_strs = df_raw.get('src_user', pd.Series(['none'] * n_nodes)).fillna('none').values
        ip_strs = df_raw.get('src_ip', pd.Series(['none'] * n_nodes)).fillna('none').values

        edges_src, edges_dst = [], []

        # 1. Intra-machine temporal edges
        for m_id in np.unique(machine_ids):
            mask = machine_ids == m_id
            idxs = np.where(mask)[0]
            ts = timestamps_sec[idxs]
            order = np.argsort(ts)
            idxs = idxs[order]
            ts = ts[order]

            for i in range(len(idxs)):
                count = 0
                for j in range(i + 1, len(idxs)):
                    if ts[j] - ts[i] > self.INTRA_WINDOW_SEC:
                        break
                    if count >= self.MAX_INTRA:
                        break
                    edges_src.extend([idxs[i], idxs[j]])
                    edges_dst.extend([idxs[j], idxs[i]])
                    count += 1

        # 2. Cross-machine user edges (lateral movement)
        user_machine_df = pd.DataFrame({
            'src_user': user_strs,
            'machine_name': machine_names.values if hasattr(machine_names, 'values') else machine_names,
            'idx': np.arange(n_nodes),
            'ts': timestamps_sec,
            'mid': machine_ids,
        })

        multi_machine_users = []
        for u, g in user_machine_df[user_machine_df['src_user'] != 'none'].groupby('src_user'):
            if g['mid'].nunique() >= 2:
                multi_machine_users.append(u)

        for user in multi_machine_users:
            mask = user_strs == user
            idxs = np.where(mask)[0]
            ts = timestamps_sec[idxs]
            mids = machine_ids[idxs]
            order = np.argsort(ts)
            idxs, ts, mids = idxs[order], ts[order], mids[order]

            for i in range(len(idxs)):
                count = 0
                for j in range(i + 1, len(idxs)):
                    if ts[j] - ts[i] > self.CROSS_WINDOW_SEC:
                        break
                    if count >= self.MAX_CROSS:
                        break
                    if mids[i] != mids[j]:
                        edges_src.extend([idxs[i], idxs[j]])
                        edges_dst.extend([idxs[j], idxs[i]])
                        count += 1

        # 3. Cross-machine IP edges
        multi_machine_ips = []
        valid_ip = (ip_strs != 'none') & (ip_strs != '')
        ip_df = pd.DataFrame({
            'src_ip': ip_strs[valid_ip],
            'machine_name': np.array(machine_names)[valid_ip] if hasattr(machine_names, '__getitem__') else machine_names.values[valid_ip],
        })
        for ip, g in ip_df.groupby('src_ip'):
            if g['machine_name'].nunique() >= 2:
                multi_machine_ips.append(ip)

        for ip in multi_machine_ips:
            mask = ip_strs == ip
            idxs = np.where(mask)[0]
            ts = timestamps_sec[idxs]
            mids = machine_ids[idxs]
            order = np.argsort(ts)
            idxs, ts, mids = idxs[order], ts[order], mids[order]

            for i in range(len(idxs)):
                count = 0
                for j in range(i + 1, len(idxs)):
                    if ts[j] - ts[i] > self.CROSS_WINDOW_SEC:
                        break
                    if count >= self.MAX_CROSS:
                        break
                    if mids[i] != mids[j]:
                        edges_src.extend([idxs[i], idxs[j]])
                        edges_dst.extend([idxs[j], idxs[i]])
                        count += 1

        # 4. Self-loops
        edges_src.extend(list(range(n_nodes)))
        edges_dst.extend(list(range(n_nodes)))

        # Build PyG Data
        edge_index = torch.tensor([edges_src, edges_dst], dtype=torch.long)
        x = torch.tensor(feature_matrix, dtype=torch.float)

        graph_data = Data(x=x, edge_index=edge_index).to(self.device)
        self.graph_data = graph_data

        elapsed = time.time() - t0
        print(f"[GNN] Graph built: {n_nodes:,} nodes, {edge_index.shape[1]:,} edges ({elapsed:.1f}s)")

        return graph_data

    @torch.no_grad()
    def run_inference(self, df_raw: pd.DataFrame):
        """
        Run full GNN inference and prepare RL state extraction.

        Must be called after build_graph(). Sets up internal state
        for get_rl_state_features() calls.

        Args:
            df_raw: Same DataFrame used in build_graph()
        """
        if not self.enabled or self.graph_data is None:
            return

        self.model.eval()
        logits = self.model(self.graph_data.x, self.graph_data.edge_index)
        self.alert_risks = torch.sigmoid(logits).cpu().numpy()

        # Build mapping DataFrame for RL feature extraction
        self.df_rl = pd.DataFrame()
        if 'timestamp' in df_raw.columns:
            self.df_rl['timestamp'] = pd.to_datetime(df_raw['timestamp'], errors='coerce')
        else:
            self.df_rl['timestamp'] = pd.Timestamp('2024-01-01') + pd.to_timedelta(np.arange(len(df_raw)), unit='s')

        self.df_rl['machine_name'] = df_raw.get('machine_name', 'machine-1')
        self.df_rl['alert_risk'] = self.alert_risks
        self.df_rl['is_high_risk'] = (self.alert_risks >= self.threshold).astype(int)

        # Pre-extract edges for fast neighbor lookups
        self.src_nodes = self.graph_data.edge_index[0].cpu().numpy()
        self.dst_nodes = self.graph_data.edge_index[1].cpu().numpy()

        print(f"[GNN] Inference done: {len(self.alert_risks):,} nodes scored, "
              f"high-risk: {self.df_rl['is_high_risk'].sum():,} ({self.df_rl['is_high_risk'].mean()*100:.1f}%)")

    def get_rl_state_features(
        self,
        target_machine: str,
        current_time: pd.Timestamp,
        window_minutes: int = 60,
    ) -> Dict[str, float]:
        """
        Extract GNN-based RL state features for the agent.
        Exact reproduction of get_rl_state_features from notebook.

        Returns 3 features (redundant ones removed):
            - GNN_node_risk_current_host
            - GNN_neighbor_risk
            - risk_growth

        Args:
            target_machine: Name of the machine being evaluated
            current_time: Current timestamp in the episode
            window_minutes: Time window for feature extraction

        Returns:
            Dict with 3 GNN features
        """
        # Default features
        defaults = {
            "GNN_node_risk_current_host": 0.0,
            "GNN_neighbor_risk": 0.0,
            "risk_growth": 0.0,
        }

        if not self.enabled or self.df_rl is None:
            return defaults

        start_time = current_time - pd.Timedelta(minutes=window_minutes)
        prev_start_time = start_time - pd.Timedelta(minutes=window_minutes)

        # Current and previous time window masks
        curr_mask = (self.df_rl['timestamp'] > start_time) & (self.df_rl['timestamp'] <= current_time)
        prev_mask = (self.df_rl['timestamp'] > prev_start_time) & (self.df_rl['timestamp'] <= start_time)

        curr_indices = np.where(curr_mask)[0]
        prev_indices = np.where(prev_mask)[0]

        if len(curr_indices) == 0:
            return defaults

        # Global graph risk (used for risk_growth computation)
        global_graph_risk = self.df_rl.iloc[curr_indices]['alert_risk'].mean()

        # Risk growth vs previous window
        if len(prev_indices) > 0:
            prev_global_risk = self.df_rl.iloc[prev_indices]['alert_risk'].mean()
            risk_growth = global_graph_risk - prev_global_risk
        else:
            risk_growth = global_graph_risk

        # Target machine specific features
        host_mask = curr_mask & (self.df_rl['machine_name'] == target_machine)
        host_indices = np.where(host_mask)[0]

        if len(host_indices) > 0:
            node_risk = self.df_rl.iloc[host_indices]['alert_risk'].mean()

            # Neighbor risk (lateral connections)
            neighbor_mask = np.isin(self.src_nodes, host_indices)
            neighbor_indices = np.unique(self.dst_nodes[neighbor_mask])
            external_neighbors = np.setdiff1d(neighbor_indices, host_indices)

            if len(external_neighbors) > 0:
                neighbor_risk = self.df_rl.iloc[external_neighbors]['alert_risk'].mean()
            else:
                neighbor_risk = 0.0
        else:
            node_risk = 0.0
            neighbor_risk = 0.0

        return {
            "GNN_node_risk_current_host": float(node_risk),
            "GNN_neighbor_risk": float(neighbor_risk),
            "risk_growth": float(risk_growth),
        }

    def get_model_info(self) -> Dict:
        """Get model metadata."""
        info = {
            'enabled': self.enabled,
            'model_path': getattr(self, 'model_path', None),
            'threshold': self.threshold,
            'n_features': len(self.feature_cols),
            'graph_params': {
                'intra_window_sec': self.INTRA_WINDOW_SEC,
                'cross_window_sec': self.CROSS_WINDOW_SEC,
                'max_intra': self.MAX_INTRA,
                'max_cross': self.MAX_CROSS,
            },
        }
        if self.enabled and self.model is not None:
            info['parameters'] = sum(p.numel() for p in self.model.parameters())
        return info


# Example usage and testing
if __name__ == "__main__":
    print("\n" + "=" * 70)
    print("GNN LOADER - TEST")
    print("=" * 70)

    try:
        loader = GNNLoader()
        info = loader.get_model_info()
        print(f"\n  Enabled: {info['enabled']}")
        print(f"  Threshold: {info['threshold']:.4f}")
        print(f"  Features: {info['n_features']}")
        print(f"  Parameters: {info.get('parameters', 'N/A'):,}")
        print(f"  Graph params: {info['graph_params']}")

        # Test with synthetic data
        n_alerts = 100
        df_test = pd.DataFrame({
            'timestamp': pd.date_range('2024-01-01', periods=n_alerts, freq='5min'),
            'machine_name': np.random.choice(['machine-1', 'machine-2', 'machine-3'], n_alerts),
            'src_user': np.random.choice(['root', 'admin', 'user1', 'none'], n_alerts),
            'src_ip': np.random.choice(['192.168.1.1', '10.0.0.1', 'none'], n_alerts),
        })

        # Add feature columns
        for col in loader.feature_cols:
            df_test[col] = np.random.randn(n_alerts)

        # Build graph and run inference
        graph = loader.build_graph(df_test)
        loader.run_inference(df_test)

        # Test RL feature extraction
        test_time = df_test['timestamp'].median()
        features = loader.get_rl_state_features('machine-1', test_time)
        print(f"\n  RL Features at {test_time}:")
        for k, v in features.items():
            print(f"    {k}: {v:.5f}")

        print("\n  [OK] GNN loader working correctly")
    except Exception as e:
        print(f"  [ERROR] {e}")
        import traceback
        traceback.print_exc()
