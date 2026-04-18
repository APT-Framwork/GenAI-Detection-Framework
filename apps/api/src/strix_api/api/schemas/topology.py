"""Topology-tab response schemas.

Topology nodes are hosts with a derived health status; edges are
co-occurrence in the same attack chain over the requested window. We
deliberately don't try to mirror network topology (no port-scan data) —
the value is showing which hosts the *attacks* tied together.
"""

from __future__ import annotations

from typing import Literal

from strix_api.api.schemas.common import StrixBase, WindowLiteral

NodeStatus = Literal["healthy", "warning", "compromised"]
NodeType = Literal["server", "endpoint", "firewall", "database", "manager"]


class TopologyNode(StrixBase):
    id: str  # host_id (uuid string)
    label: str  # agent_name
    type: NodeType
    status: NodeStatus
    ip: str | None
    open_chains: int
    max_ckc_stage: int  # 0..7; 0 = nothing seen


class TopologyEdge(StrixBase):
    id: str  # `${source}::${target}`
    source: str
    target: str
    chain_count: int  # how many chains tied these two hosts together
    type: Literal["normal", "malicious"]


class TopologyResponse(StrixBase):
    window: WindowLiteral
    generated_at: str
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]


__all__ = [
    "NodeStatus",
    "NodeType",
    "TopologyEdge",
    "TopologyNode",
    "TopologyResponse",
]
