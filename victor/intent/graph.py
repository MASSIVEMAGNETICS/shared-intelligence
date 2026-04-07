"""
IntentGraph — The living directed graph of Victor's ongoing ambitions.

Every goal, project, obligation, creative seed, strategic mission, or
dormant idea is a node.  Relationships between them (blocks, depends-on,
advances, contradicts, descended-from, emotionally-linked) are typed
directed edges.

This gives Victor continuity of *work*, not just continuity of chat.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Iterator, Optional


class NodeType(str, Enum):
    PROJECT = "project"
    DEPENDENCY = "dependency"
    OBLIGATION = "obligation"
    CREATIVE_SEED = "creative_seed"
    STRATEGIC_MISSION = "strategic_mission"
    ABANDONED = "abandoned"  # dormant but revivable


class NodeStatus(str, Enum):
    ACTIVE = "active"
    DORMANT = "dormant"
    ABANDONED = "abandoned"
    COMPLETED = "completed"


class EdgeType(str, Enum):
    BLOCKED_BY = "blocked_by"
    DEPENDS_ON = "depends_on"
    CONTRADICTS = "contradicts"
    ADVANCES = "advances"
    DESCENDED_FROM = "descended_from"
    EMOTIONALLY_LINKED_TO = "emotionally_linked_to"


@dataclass
class IntentNode:
    """
    A single node in the intent graph.

    Attributes
    ----------
    id:
        Unique identifier.
    node_type:
        Semantic category (project, obligation, creative seed, …).
    title:
        Short human-readable label.
    description:
        Expanded description of the intent.
    status:
        Current lifecycle status.
    created_at:
        ISO-8601 UTC creation time.
    updated_at:
        ISO-8601 UTC of last mutation.
    metadata:
        Extensible key-value store.
    """

    id: str
    node_type: NodeType
    title: str
    description: str
    status: NodeStatus
    created_at: str  # ISO-8601 UTC
    updated_at: str  # ISO-8601 UTC
    metadata: dict

    @classmethod
    def create(
        cls,
        node_type: NodeType,
        title: str,
        description: str,
        status: NodeStatus = NodeStatus.ACTIVE,
        metadata: Optional[dict] = None,
    ) -> "IntentNode":
        ts = datetime.now(timezone.utc).isoformat()
        return cls(
            id=str(uuid.uuid4()),
            node_type=node_type,
            title=title,
            description=description,
            status=status,
            created_at=ts,
            updated_at=ts,
            metadata=dict(metadata or {}),
        )

    def update_status(self, status: NodeStatus) -> None:
        self.status = status
        self.updated_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "node_type": self.node_type.value,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IntentNode":
        return cls(
            id=data["id"],
            node_type=NodeType(data["node_type"]),
            title=data["title"],
            description=data["description"],
            status=NodeStatus(data["status"]),
            created_at=data["created_at"],
            updated_at=data.get("updated_at", data["created_at"]),
            metadata=data.get("metadata", {}),
        )


@dataclass
class IntentEdge:
    """
    A directed relationship between two intent nodes.

    Attributes
    ----------
    id:
        Unique identifier.
    source_id:
        ID of the source node.
    target_id:
        ID of the target node.
    edge_type:
        Semantic relationship type.
    weight:
        Optional strength / salience of the relationship (0.0–1.0).
    metadata:
        Extensible key-value store.
    """

    id: str
    source_id: str
    target_id: str
    edge_type: EdgeType
    weight: float  # 0.0–1.0
    metadata: dict

    @classmethod
    def create(
        cls,
        source_id: str,
        target_id: str,
        edge_type: EdgeType,
        weight: float = 1.0,
        metadata: Optional[dict] = None,
    ) -> "IntentEdge":
        if not 0.0 <= weight <= 1.0:
            raise ValueError(f"weight must be in [0.0, 1.0], got {weight}")
        return cls(
            id=str(uuid.uuid4()),
            source_id=source_id,
            target_id=target_id,
            edge_type=edge_type,
            weight=weight,
            metadata=dict(metadata or {}),
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type.value,
            "weight": self.weight,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IntentEdge":
        return cls(
            id=data["id"],
            source_id=data["source_id"],
            target_id=data["target_id"],
            edge_type=EdgeType(data["edge_type"]),
            weight=data.get("weight", 1.0),
            metadata=data.get("metadata", {}),
        )


class IntentGraph:
    """
    Directed graph of :class:`IntentNode` objects connected by
    :class:`IntentEdge` relationships.

    Provides both mutation (add/update nodes and edges) and graph-level
    queries (neighbours, dependents, blockers, active missions).
    """

    def __init__(self) -> None:
        self._nodes: dict[str, IntentNode] = {}
        self._edges: list[IntentEdge] = []

    # ------------------------------------------------------------------
    # Nodes
    # ------------------------------------------------------------------

    def add_node(self, node: IntentNode) -> None:
        if node.id in self._nodes:
            raise ValueError(f"Node {node.id!r} already exists.")
        self._nodes[node.id] = node

    def get_node(self, node_id: str) -> Optional[IntentNode]:
        return self._nodes.get(node_id)

    def update_node_status(self, node_id: str, status: NodeStatus) -> None:
        node = self._nodes.get(node_id)
        if node is None:
            raise KeyError(f"Node {node_id!r} not found.")
        node.update_status(status)

    def nodes_by_status(self, status: NodeStatus) -> list[IntentNode]:
        return [n for n in self._nodes.values() if n.status == status]

    def nodes_by_type(self, node_type: NodeType) -> list[IntentNode]:
        return [n for n in self._nodes.values() if n.node_type == node_type]

    def active_nodes(self) -> list[IntentNode]:
        return self.nodes_by_status(NodeStatus.ACTIVE)

    def dormant_nodes(self) -> list[IntentNode]:
        return self.nodes_by_status(NodeStatus.DORMANT)

    def revivable_nodes(self) -> list[IntentNode]:
        """Dormant or abandoned nodes that are potentially recoverable."""
        return [
            n
            for n in self._nodes.values()
            if n.status in (NodeStatus.DORMANT, NodeStatus.ABANDONED)
        ]

    # ------------------------------------------------------------------
    # Edges
    # ------------------------------------------------------------------

    def add_edge(self, edge: IntentEdge) -> None:
        if edge.source_id not in self._nodes:
            raise KeyError(f"Source node {edge.source_id!r} not found.")
        if edge.target_id not in self._nodes:
            raise KeyError(f"Target node {edge.target_id!r} not found.")
        self._edges.append(edge)

    def edges_from(self, node_id: str) -> list[IntentEdge]:
        return [e for e in self._edges if e.source_id == node_id]

    def edges_to(self, node_id: str) -> list[IntentEdge]:
        return [e for e in self._edges if e.target_id == node_id]

    def edges_by_type(self, edge_type: EdgeType) -> list[IntentEdge]:
        return [e for e in self._edges if e.edge_type == edge_type]

    def blockers_of(self, node_id: str) -> list[IntentNode]:
        """Return nodes that block *node_id*."""
        blocker_ids = {
            e.target_id
            for e in self.edges_from(node_id)
            if e.edge_type == EdgeType.BLOCKED_BY
        }
        return [self._nodes[nid] for nid in blocker_ids if nid in self._nodes]

    def dependents_of(self, node_id: str) -> list[IntentNode]:
        """Return nodes that depend on *node_id*."""
        dep_ids = {
            e.source_id
            for e in self.edges_to(node_id)
            if e.edge_type == EdgeType.DEPENDS_ON
        }
        return [self._nodes[nid] for nid in dep_ids if nid in self._nodes]

    def advances(self, node_id: str) -> list[IntentNode]:
        """Return nodes that *node_id* advances."""
        adv_ids = {
            e.target_id
            for e in self.edges_from(node_id)
            if e.edge_type == EdgeType.ADVANCES
        }
        return [self._nodes[nid] for nid in adv_ids if nid in self._nodes]

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": [e.to_dict() for e in self._edges],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IntentGraph":
        graph = cls()
        for raw in data.get("nodes", []):
            graph.add_node(IntentNode.from_dict(raw))
        for raw in data.get("edges", []):
            graph.add_edge(IntentEdge.from_dict(raw))
        return graph

    def __len__(self) -> int:
        return len(self._nodes)

    def __iter__(self) -> Iterator[IntentNode]:
        return iter(self._nodes.values())
