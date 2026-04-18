"""GNN rolling-window graph builder — pure-domain edge logic."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np

from strix_api.core.gnn_window import (
    INTRA_WINDOW_SEC,
    NodeFact,
    build_snapshot,
    filter_window,
)


def _node(
    *, alert_id: str, agent_id: str, ts: datetime,
    srcuser: str | None = None, srcip: str | None = None,
) -> NodeFact:
    return NodeFact(
        alert_id=alert_id,
        agent_id=agent_id,
        occurred_at=ts,
        srcuser=srcuser,
        srcip=srcip,
        features_gnn_order=np.zeros((55,), dtype=np.float32),
    )


def test_filter_window_drops_old_alerts() -> None:
    now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    fresh = _node(alert_id="a", agent_id="1", ts=now - timedelta(minutes=5))
    stale = _node(alert_id="b", agent_id="1", ts=now - timedelta(hours=2))
    kept = filter_window([fresh, stale], now=now, window_minutes=60)
    assert [n.alert_id for n in kept] == ["a"]


def test_filter_window_orders_by_time() -> None:
    now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    nodes = [
        _node(alert_id="late", agent_id="1", ts=now - timedelta(minutes=1)),
        _node(alert_id="mid",  agent_id="1", ts=now - timedelta(minutes=10)),
        _node(alert_id="early",agent_id="1", ts=now - timedelta(minutes=30)),
    ]
    kept = filter_window(nodes, now=now)
    assert [n.alert_id for n in kept] == ["early", "mid", "late"]


def test_self_loops_always_added() -> None:
    now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    nodes = [_node(alert_id=f"a{i}", agent_id="1", ts=now - timedelta(seconds=i)) for i in range(3)]
    snap = build_snapshot(filter_window(nodes, now=now))
    # Every node has a self-loop
    assert snap.edge_counts["self"] == 3
    # Self-loops should appear in edge_index
    self_pairs = {(int(snap.edge_index[0, k]), int(snap.edge_index[1, k]))
                  for k in range(snap.edge_index.shape[1])}
    for i in range(3):
        assert (i, i) in self_pairs


def test_intra_machine_edges_within_window() -> None:
    now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    nodes = [
        _node(alert_id="a", agent_id="m1", ts=now - timedelta(seconds=10)),
        _node(alert_id="b", agent_id="m1", ts=now - timedelta(seconds=5)),
        _node(alert_id="c", agent_id="m1", ts=now - timedelta(seconds=1)),
    ]
    snap = build_snapshot(filter_window(nodes, now=now))
    # 3 intra-pair candidates: (a→b, a→c, b→c) → 3 directed pairs × 2 = 6 directed edges
    assert snap.edge_counts["intra"] == 6


def test_intra_capped_by_max_intra() -> None:
    now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    # 10 alerts on the same machine, all within window → MAX_INTRA=3 limit applies per source
    nodes = [
        _node(alert_id=f"a{i}", agent_id="m1", ts=now - timedelta(seconds=i))
        for i in range(10)
    ]
    snap = build_snapshot(filter_window(nodes, now=now))
    # Each source connects to up to 3 successors → max ~ 3 * N pairs * 2 directed
    assert snap.edge_counts["intra"] <= 2 * 3 * 10


def test_cross_user_edges_only_when_multi_machine() -> None:
    now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    nodes = [
        _node(alert_id="a", agent_id="m1", ts=now - timedelta(seconds=10), srcuser="alice"),
        _node(alert_id="b", agent_id="m2", ts=now - timedelta(seconds=5),  srcuser="alice"),
        _node(alert_id="c", agent_id="m1", ts=now - timedelta(seconds=1),  srcuser="bob"),
    ]
    snap = build_snapshot(filter_window(nodes, now=now))
    # `alice` appears on m1 and m2 → 1 cross pair (a, b) → 2 directed edges
    # `bob`   appears on m1 only      → 0 cross edges
    assert snap.edge_counts["user"] == 2


def test_missing_user_ip_does_not_create_cross_edges() -> None:
    now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    nodes = [
        _node(alert_id="a", agent_id="m1", ts=now, srcuser="none", srcip=""),
        _node(alert_id="b", agent_id="m2", ts=now, srcuser=None, srcip=None),
    ]
    snap = build_snapshot(filter_window(nodes, now=now))
    assert snap.edge_counts["user"] == 0
    assert snap.edge_counts["ip"] == 0


def test_empty_input_returns_empty_snapshot() -> None:
    snap = build_snapshot([])
    assert snap.num_nodes == 0
    assert snap.num_edges == 0


def test_features_assembled_in_node_order() -> None:
    now = datetime(2026, 4, 17, 12, 0, 0, tzinfo=UTC)
    nodes = []
    for i, name in enumerate(("first", "second", "third")):
        v = np.full((55,), float(i), dtype=np.float32)
        nodes.append(NodeFact(
            alert_id=name, agent_id="m1", occurred_at=now - timedelta(seconds=10 - i),
            srcuser=None, srcip=None, features_gnn_order=v,
        ))
    snap = build_snapshot(filter_window(nodes, now=now))
    # filter_window sorts by time → first/second/third order
    assert snap.alert_ids == ("first", "second", "third")
    assert snap.x.shape == (3, 55)
    assert (snap.x[0] == 0).all()
    assert (snap.x[1] == 1).all()
    assert (snap.x[2] == 2).all()


def test_intra_window_constant_matches_30_min() -> None:
    """Catch accidental changes to INTRA_WINDOW_SEC (must match the GNN training)."""
    assert INTRA_WINDOW_SEC == 30 * 60
