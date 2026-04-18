"""Rolling-window GNN graph builder (P2-4).

The GNN was trained on a graph built from cross-machine USER and IP edges
plus intra-machine TEMPORAL edges (GNN_Network_Propagation.ipynb cell 3).
At inference we cannot rebuild the entire historical graph per alert —
that would be O(N²) and blow the latency budget. Instead we maintain a
rolling 60-min window of recent alerts in Redis (per shard) and rebuild
the subgraph + run the GNN forward once a minute (§5.3 + §6.4).

This module is the PURE-DOMAIN graph builder. It takes:
  - a list of NodeFact records (alert_id, agent_id, occurred_at, srcuser, srcip,
    plus the 55-d feature vector in GNN's alphabetical SecBERT order)

and returns:
  - GraphSnapshot { node_index, edge_index, last_alert_id_per_node }

A cache of the most recent risks per `alert_id` is kept on the snapshot so
the per-alert hot path can do an O(1) lookup instead of triggering a
graph rebuild on every alert.

Window/edge parameters mirror Section 3 of the GNN notebook:
  INTRA_WINDOW_SEC = 30 * 60     # 30 min
  CROSS_WINDOW_SEC = 30 * 60     # 30 min
  MAX_INTRA = 3
  MAX_CROSS = 5
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable

import numpy as np

from strix_api.core.constants import GNN_WINDOW_MINUTES

INTRA_WINDOW_SEC = 30 * 60
CROSS_WINDOW_SEC = 30 * 60
MAX_INTRA = 3
MAX_CROSS = 5

#: Sentinels matching the FeatureEngineerNoLeakage missing-data convention.
_USER_MISSING = frozenset({"", "none", "None", "null", "-"})
_IP_MISSING = _USER_MISSING


@dataclass(frozen=True)
class NodeFact:
    """One alert as a graph node — keyed for edge construction."""

    alert_id: str
    agent_id: str
    occurred_at: datetime
    srcuser: str | None
    srcip: str | None
    features_gnn_order: np.ndarray  # (55,) float32 in GNN's alphabetical SecBERT order


@dataclass(frozen=True)
class GraphSnapshot:
    """Output of `build_snapshot`. Worker feeds this directly to GnnLoader."""

    alert_ids: tuple[str, ...]                # length N — node order
    x: np.ndarray                              # (N, 55) float32
    edge_index: np.ndarray                     # (2, E) int64
    edge_counts: dict[str, int] = field(default_factory=dict)

    @property
    def num_nodes(self) -> int:
        return len(self.alert_ids)

    @property
    def num_edges(self) -> int:
        return int(self.edge_index.shape[1])


# ---------------------------------------------------------------- helpers


def _is_present(value: str | None, missing: frozenset[str]) -> bool:
    if value is None:
        return False
    return value.strip() not in missing


def _intra_machine_edges(
    nodes: list[NodeFact],
    indices_by_agent: dict[str, list[int]],
) -> list[tuple[int, int]]:
    """Each node connects to up to MAX_INTRA later same-machine alerts within
    INTRA_WINDOW_SEC. Bidirectional edges are emitted for SAGEConv.
    """
    edges: list[tuple[int, int]] = []
    for _agent, idxs in indices_by_agent.items():
        # idxs is already sorted ascending by occurred_at thanks to the call site
        for i_pos, i in enumerate(idxs):
            count = 0
            ts_i = nodes[i].occurred_at
            for j in idxs[i_pos + 1 :]:
                ts_j = nodes[j].occurred_at
                if (ts_j - ts_i).total_seconds() > INTRA_WINDOW_SEC:
                    break
                if count >= MAX_INTRA:
                    break
                edges.append((i, j))
                edges.append((j, i))
                count += 1
    return edges


def _cross_machine_edges(
    nodes: list[NodeFact],
    indices_by_key: dict[str, list[int]],
    *,
    window_sec: int,
    max_cross: int,
) -> list[tuple[int, int]]:
    """Cross-machine edges keyed by user OR ip. Same alert can spawn both."""
    edges: list[tuple[int, int]] = []
    for _key, idxs in indices_by_key.items():
        # Skip keys present on a single machine — no cross edge possible
        agents = {nodes[i].agent_id for i in idxs}
        if len(agents) < 2:
            continue
        for i_pos, i in enumerate(idxs):
            count = 0
            ts_i = nodes[i].occurred_at
            agent_i = nodes[i].agent_id
            for j in idxs[i_pos + 1 :]:
                ts_j = nodes[j].occurred_at
                if (ts_j - ts_i).total_seconds() > window_sec:
                    break
                if count >= max_cross:
                    break
                if nodes[j].agent_id == agent_i:
                    continue  # same machine — already covered by intra
                edges.append((i, j))
                edges.append((j, i))
                count += 1
    return edges


# ---------------------------------------------------------------- public API


def filter_window(
    nodes: Iterable[NodeFact], *, now: datetime | None = None,
    window_minutes: int = GNN_WINDOW_MINUTES,
) -> list[NodeFact]:
    """Keep alerts within the last `window_minutes` of `now`."""
    if now is None:
        now = datetime.now(timezone.utc)
    horizon = now - timedelta(minutes=window_minutes)
    kept = [n for n in nodes if n.occurred_at >= horizon]
    kept.sort(key=lambda n: n.occurred_at)  # stable temporal order
    return kept


def build_snapshot(nodes: list[NodeFact]) -> GraphSnapshot:
    """Build the (x, edge_index) tensors for a graph snapshot.

    Always adds self-loops so every node has a defined message-passing source
    even in the empty-edges case.
    """
    if not nodes:
        return GraphSnapshot(
            alert_ids=(),
            x=np.zeros((0, 55), dtype=np.float32),
            edge_index=np.zeros((2, 0), dtype=np.int64),
            edge_counts={"intra": 0, "user": 0, "ip": 0, "self": 0},
        )

    # Group by agent / user / ip for vectorised edge construction
    indices_by_agent: dict[str, list[int]] = {}
    indices_by_user: dict[str, list[int]] = {}
    indices_by_ip: dict[str, list[int]] = {}
    for i, n in enumerate(nodes):
        indices_by_agent.setdefault(n.agent_id, []).append(i)
        if _is_present(n.srcuser, _USER_MISSING):
            indices_by_user.setdefault(n.srcuser or "", []).append(i)  # type: ignore[arg-type]
        if _is_present(n.srcip, _IP_MISSING):
            indices_by_ip.setdefault(n.srcip or "", []).append(i)  # type: ignore[arg-type]

    intra = _intra_machine_edges(nodes, indices_by_agent)
    user_e = _cross_machine_edges(
        nodes, indices_by_user, window_sec=CROSS_WINDOW_SEC, max_cross=MAX_CROSS
    )
    ip_e = _cross_machine_edges(
        nodes, indices_by_ip, window_sec=CROSS_WINDOW_SEC, max_cross=MAX_CROSS
    )

    n_nodes = len(nodes)
    self_loops = [(i, i) for i in range(n_nodes)]
    all_edges = intra + user_e + ip_e + self_loops

    if not all_edges:  # pragma: no cover — defensive (we always add self-loops)
        edge_index = np.zeros((2, 0), dtype=np.int64)
    else:
        edge_index = np.array(all_edges, dtype=np.int64).T  # (2, E)

    x = np.stack([n.features_gnn_order for n in nodes], axis=0).astype(np.float32)

    return GraphSnapshot(
        alert_ids=tuple(n.alert_id for n in nodes),
        x=x,
        edge_index=edge_index,
        edge_counts={
            "intra": len(intra),
            "user": len(user_e),
            "ip": len(ip_e),
            "self": len(self_loops),
        },
    )


__all__ = [
    "GraphSnapshot",
    "NodeFact",
    "build_snapshot",
    "filter_window",
    "INTRA_WINDOW_SEC",
    "CROSS_WINDOW_SEC",
    "MAX_INTRA",
    "MAX_CROSS",
]
