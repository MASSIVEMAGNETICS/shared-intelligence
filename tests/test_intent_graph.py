"""Tests for IntentGraph."""

import pytest
from victor.intent.graph import (
    IntentGraph,
    IntentNode,
    IntentEdge,
    NodeType,
    NodeStatus,
    EdgeType,
)


def make_node(title: str = "Test Node", node_type: NodeType = NodeType.PROJECT) -> IntentNode:
    return IntentNode.create(node_type=node_type, title=title, description="A test node.")


class TestIntentNode:
    def test_create_defaults(self):
        node = make_node()
        assert node.status == NodeStatus.ACTIVE
        assert node.node_type == NodeType.PROJECT
        assert node.id

    def test_update_status(self):
        node = make_node()
        node.update_status(NodeStatus.DORMANT)
        assert node.status == NodeStatus.DORMANT

    def test_round_trip(self):
        node = IntentNode.create(
            node_type=NodeType.CREATIVE_SEED,
            title="Album",
            description="Finish the album.",
            status=NodeStatus.DORMANT,
            metadata={"genre": "jazz"},
        )
        restored = IntentNode.from_dict(node.to_dict())
        assert restored.id == node.id
        assert restored.node_type == NodeType.CREATIVE_SEED
        assert restored.metadata["genre"] == "jazz"


class TestIntentEdge:
    def test_create(self):
        n1 = make_node("A")
        n2 = make_node("B")
        edge = IntentEdge.create(n1.id, n2.id, EdgeType.ADVANCES, weight=0.8)
        assert edge.source_id == n1.id
        assert edge.target_id == n2.id
        assert edge.weight == 0.8

    def test_invalid_weight(self):
        n1, n2 = make_node("X"), make_node("Y")
        with pytest.raises(ValueError):
            IntentEdge.create(n1.id, n2.id, EdgeType.BLOCKED_BY, weight=1.5)

    def test_round_trip(self):
        n1, n2 = make_node("P"), make_node("Q")
        edge = IntentEdge.create(n1.id, n2.id, EdgeType.DESCENDED_FROM)
        restored = IntentEdge.from_dict(edge.to_dict())
        assert restored.id == edge.id
        assert restored.edge_type == EdgeType.DESCENDED_FROM


class TestIntentGraph:
    def _make_graph(self) -> tuple[IntentGraph, IntentNode, IntentNode, IntentNode]:
        graph = IntentGraph()
        album = IntentNode.create(NodeType.CREATIVE_SEED, "Finish Album", "Music project.")
        income = IntentNode.create(NodeType.PROJECT, "Generate Income", "Revenue stream.")
        blocker = IntentNode.create(NodeType.DEPENDENCY, "Get Studio Time", "Needs booking.")
        graph.add_node(album)
        graph.add_node(income)
        graph.add_node(blocker)
        return graph, album, income, blocker

    def test_add_and_get_node(self):
        graph, album, _, _ = self._make_graph()
        retrieved = graph.get_node(album.id)
        assert retrieved is not None
        assert retrieved.title == "Finish Album"

    def test_duplicate_node_raises(self):
        graph, album, _, _ = self._make_graph()
        with pytest.raises(ValueError):
            graph.add_node(album)

    def test_add_edge_validates_nodes(self):
        graph, album, income, _ = self._make_graph()
        graph.add_edge(IntentEdge.create(album.id, income.id, EdgeType.ADVANCES))
        with pytest.raises(KeyError):
            graph.add_edge(IntentEdge.create("ghost-id", album.id, EdgeType.ADVANCES))

    def test_blockers_of(self):
        graph, album, _, blocker = self._make_graph()
        graph.add_edge(IntentEdge.create(album.id, blocker.id, EdgeType.BLOCKED_BY))
        blockers = graph.blockers_of(album.id)
        assert len(blockers) == 1
        assert blockers[0].id == blocker.id

    def test_advances(self):
        graph, album, income, _ = self._make_graph()
        graph.add_edge(IntentEdge.create(album.id, income.id, EdgeType.ADVANCES))
        advanced = graph.advances(album.id)
        assert len(advanced) == 1
        assert advanced[0].id == income.id

    def test_active_and_dormant(self):
        graph, album, income, blocker = self._make_graph()
        graph.update_node_status(album.id, NodeStatus.DORMANT)
        assert len(graph.active_nodes()) == 2  # income and blocker still active
        assert len(graph.dormant_nodes()) == 1

    def test_revivable(self):
        graph, album, income, blocker = self._make_graph()
        graph.update_node_status(album.id, NodeStatus.ABANDONED)
        revivable = graph.revivable_nodes()
        assert any(n.id == album.id for n in revivable)

    def test_nodes_by_type(self):
        graph, _, _, _ = self._make_graph()
        creative = graph.nodes_by_type(NodeType.CREATIVE_SEED)
        assert len(creative) == 1

    def test_len_and_iter(self):
        graph, _, _, _ = self._make_graph()
        assert len(graph) == 3
        ids = [n.id for n in graph]
        assert len(ids) == 3

    def test_serialisation_round_trip(self):
        graph, album, income, blocker = self._make_graph()
        graph.add_edge(IntentEdge.create(album.id, income.id, EdgeType.ADVANCES))
        restored = IntentGraph.from_dict(graph.to_dict())
        assert len(restored) == 3
        assert len(list(restored.edges_by_type(EdgeType.ADVANCES))) == 1
