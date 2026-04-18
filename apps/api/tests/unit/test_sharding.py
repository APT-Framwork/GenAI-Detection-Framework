"""Sharding — must be stable across process restarts and Python versions.

Shard selection can't use Python's built-in `hash()` (salted per-process).
If two replicas compute different shards for the same `agent_id`, per-host
session state leaks across shards. Assert deterministic SHA-1-based picks.
"""

from __future__ import annotations

from strix_api.workers.normalizer import _host_id_for, _shard_for


def test_shard_is_deterministic() -> None:
    assert _shard_for("001", 4) == _shard_for("001", 4)
    assert _shard_for("Machine-1-New", 4) == _shard_for("Machine-1-New", 4)


def test_shard_is_in_range() -> None:
    for agent in ("001", "002", "003", "100", "Machine-5-New", "manager"):
        for num in (1, 2, 4, 8, 16):
            s = _shard_for(agent, num)
            assert 0 <= s < num, (agent, num, s)


def test_shard_distributes_over_many_agents() -> None:
    """With 1000 synthetic agent ids and 8 shards, every shard should be hit."""
    buckets = {i: 0 for i in range(8)}
    for i in range(1000):
        buckets[_shard_for(f"agent-{i}", 8)] += 1
    assert all(count > 0 for count in buckets.values())


def test_shard_zero_num_shards_is_single_shard() -> None:
    """Edge-case: num_shards=0 should not ZeroDivisionError."""
    s = _shard_for("agent-1", 0)
    assert s == 0


def test_host_id_is_deterministic() -> None:
    a1 = _host_id_for("Machine-1-New")
    a2 = _host_id_for("Machine-1-New")
    assert a1 == a2
    # Different agent ids must give different host_ids
    assert _host_id_for("Machine-1-New") != _host_id_for("Machine-2-New")
