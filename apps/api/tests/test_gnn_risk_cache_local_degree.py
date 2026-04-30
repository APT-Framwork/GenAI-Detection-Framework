"""Unit test for `_GnnRiskCache.local_degree` — used as the `affected_edges`
field on the GNN multiplex stream frame.

Builds a tiny synthetic GraphSnapshot with a known star topology (node 0 wired
to nodes 1, 2, 3 in both directions) and asserts the lookup returns the right
undirected degree per node.
"""

from __future__ import annotations

import asyncio

import numpy as np

from strix_api.core.gnn_window import GraphSnapshot
from strix_api.workers.inference import _GnnRiskCache


def _star_snapshot() -> GraphSnapshot:
    # 4 nodes: 0 (hub) connected to 1, 2, 3; bidirectional edges (SAGEConv style).
    alert_ids = ("a0", "a1", "a2", "a3")
    edges = np.array(
        [
            [0, 1, 0, 2, 0, 3],  # src
            [1, 0, 2, 0, 3, 0],  # dst
        ],
        dtype=np.int64,
    )
    x = np.zeros((4, 55), dtype=np.float32)
    return GraphSnapshot(alert_ids=alert_ids, x=x, edge_index=edges)


def test_local_degree_star_topology() -> None:
    cache = _GnnRiskCache()
    snap = _star_snapshot()
    risks = np.zeros(snap.num_nodes, dtype=np.float32)

    async def _run() -> dict[str, int]:
        await cache.update_risks(snap, risks)
        return {
            aid: await cache.local_degree(aid)
            for aid in ("a0", "a1", "a2", "a3", "missing")
        }

    out = asyncio.run(_run())
    # Hub: appears 3x in row[0] and 3x in row[1] → 6 entries → degree 6
    # (matches the doc: "undirected degree" counted off `edge_index` directly,
    # which is what we want as a coarse fan-out signal).
    assert out["a0"] == 6
    assert out["a1"] == 2
    assert out["a2"] == 2
    assert out["a3"] == 2
    assert out["missing"] == 0


def test_local_degree_no_snapshot_returns_zero() -> None:
    cache = _GnnRiskCache()

    async def _run() -> int:
        return await cache.local_degree("any")

    assert asyncio.run(_run()) == 0
