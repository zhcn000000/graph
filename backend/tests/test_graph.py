from networkx import DiGraph

import pytest

from knowgraph.database.graph import AgeGraphManager
from knowgraph.graph.schema import EntityType, get_entity_uri, parse_entity_uri

TEST_DB_NAME = "test_data"


class TestStaticUtilityMethods:
    """Tests for static utility methods — no database required."""

    def test_uri_to_match_params_valid(self):
        result = AgeGraphManager._uri_to_match_params("cidoc:artifact/青铜鼎")
        assert result == ("artifact", "青铜鼎")

    def test_uri_to_match_params_invalid_prefix(self):
        result = AgeGraphManager._uri_to_match_params("http://example.com/artifact/青铜鼎")
        assert result is None

    def test_uri_to_match_params_empty(self):
        result = AgeGraphManager._uri_to_match_params("")
        assert result is None

    def test_uri_to_match_params_no_slash(self):
        result = AgeGraphManager._uri_to_match_params("cidoc:artifact")
        assert result is None

    def test_node_props_to_uri_with_entity_type_and_name(self):
        data = {"entity_type": "artifact", "name": "青铜鼎"}
        result = AgeGraphManager._node_props_to_uri(data)
        assert result == "cidoc:artifact/青铜鼎"

    def test_node_props_to_uri_with_properties_inner(self):
        data = {"properties": {"entity_type": "museum", "name": "大都会博物馆"}}
        result = AgeGraphManager._node_props_to_uri(data)
        assert result == "cidoc:museum/大都会博物馆"

    def test_node_props_to_uri_missing_fields(self):
        result = AgeGraphManager._node_props_to_uri({"foo": "bar"})
        assert result is None

    def test_node_props_to_uri_empty_dict(self):
        result = AgeGraphManager._node_props_to_uri({})
        assert result is None

    def test_node_props_to_uri_invalid_entity_type(self):
        result = AgeGraphManager._node_props_to_uri({"entity_type": "invalid", "name": "test"})
        assert result is None

    def test_digraph_to_json_empty(self):
        graph = DiGraph()
        result = AgeGraphManager.digraph_to_json(graph)
        assert result == {"nodes": [], "edges": []}

    def test_digraph_to_json_single_node(self):
        graph = DiGraph()
        graph.add_node("n1", entity_type="artifact", name="青铜鼎", properties={"description": "商代青铜器"})
        result = AgeGraphManager.digraph_to_json(graph)
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["name"] == "青铜鼎"
        assert result["nodes"][0]["entity_type"] == "artifact"
        assert result["nodes"][0]["uri"] == "cidoc:artifact/青铜鼎"

    def test_digraph_to_json_single_edge(self):
        graph = DiGraph()
        graph.add_node("n1", entity_type="artifact", name="青铜鼎")
        graph.add_node("n2", entity_type="museum", name="大都会博物馆")
        graph.add_edge("n1", "n2", label="collected_by", properties={"description": "收藏关系"})
        result = AgeGraphManager.digraph_to_json(graph)
        assert len(result["nodes"]) == 2
        assert len(result["edges"]) == 1
        edge = result["edges"][0]
        assert edge["start_uri"] == "cidoc:artifact/青铜鼎"
        assert edge["end_uri"] == "cidoc:museum/大都会博物馆"
        assert edge["label"] == "collected_by"

    def test_digraph_to_json_node_uri_from_key_fallback(self):
        graph = DiGraph()
        graph.add_node("generic_node", label="Thing", properties={"foo": "bar"})
        result = AgeGraphManager.digraph_to_json(graph)
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["uri"] == "generic_node"

    def test_digraph_to_json_node_without_name_or_type(self):
        graph = DiGraph()
        graph.add_node(42, label="Unknown")
        result = AgeGraphManager.digraph_to_json(graph)
        assert len(result["nodes"]) == 1
        assert result["nodes"][0]["uri"] == "42"

    def test_digraph_to_json_multiple_edges(self):
        graph = DiGraph()
        graph.add_node("a", entity_type="artifact", name="器物A")
        graph.add_node("b", entity_type="dynasty", name="商朝")
        graph.add_node("c", entity_type="material", name="青铜")
        graph.add_edge("a", "b", label="belongs_to_dynasty")
        graph.add_edge("a", "c", label="made_of_material")
        result = AgeGraphManager.digraph_to_json(graph)
        assert len(result["nodes"]) == 3
        assert len(result["edges"]) == 2

    def test_digraph_to_json_edge_without_properties(self):
        graph = DiGraph()
        graph.add_node("n1", entity_type="artifact", name="瓷器")
        graph.add_node("n2", entity_type="location", name="景德镇")
        graph.add_edge("n1", "n2", label="located_at")
        result = AgeGraphManager.digraph_to_json(graph)
        assert len(result["edges"]) == 1
        assert result["edges"][0]["label"] == "located_at"


@pytest.mark.usefixtures("setup_test_database", "mock_llm_extractor")
class TestVertexCRUD:
    """Tests for vertex create-read-update-delete — requires database."""

    @pytest.fixture
    def mgr(self):
        return AgeGraphManager(dbname=TEST_DB_NAME)

    @pytest.mark.usefixtures("clean_tables")
    async def test_amupsert_vertex_creates(self, mgr):
        result = await mgr.amupsert_vertex(
            "Artifact",
            {"entity_type": "artifact", "name": "青铜鼎", "description": "商代青铜器"},
        )
        assert result is not None
        assert result["name"] == "青铜鼎"
        assert result["entity_type"] == "artifact"
        assert result["uri"] == "cidoc:artifact/青铜鼎"

    @pytest.mark.usefixtures("clean_tables")
    async def test_amupsert_vertex_updates(self, mgr):
        await mgr.amupsert_vertex(
            "Artifact",
            {"entity_type": "artifact", "name": "青铜鼎", "description": "v1"},
        )
        result = await mgr.amupsert_vertex(
            "Artifact",
            {"entity_type": "artifact", "name": "青铜鼎", "description": "v2"},
        )
        assert result is not None
        assert result["name"] == "青铜鼎"

    @pytest.mark.usefixtures("clean_tables")
    async def test_amupsert_vertex_no_entity_type_or_name(self, mgr):
        result = await mgr.amupsert_vertex("Artifact", {"description": "no type or name"})
        assert result is None

    @pytest.mark.usefixtures("clean_tables")
    async def test_amupsert_vertex_with_uri_param(self, mgr):
        result = await mgr.amupsert_vertex(
            "Museum",
            {"uri": "cidoc:museum/大都会博物馆", "description": "世界著名博物馆"},
        )
        assert result is not None
        assert result["name"] == "大都会博物馆"
        assert result["entity_type"] == "museum"

    @pytest.mark.usefixtures("clean_tables")
    async def test_aget_vertex_found(self, mgr):
        await mgr.amupsert_vertex(
            "Museum",
            {"entity_type": "museum", "name": "故宫博物院", "description": "中国最大的博物馆"},
        )
        result = await mgr.aget_vertex("cidoc:museum/故宫博物院")
        assert result is not None
        assert result["name"] == "故宫博物院"
        assert result["entity_type"] == "museum"
        assert result["description"] == "中国最大的博物馆"

    @pytest.mark.usefixtures("clean_tables")
    async def test_aget_vertex_not_found(self, mgr):
        result = await mgr.aget_vertex("cidoc:artifact/不存在的文物")
        assert result is None

    @pytest.mark.usefixtures("clean_tables")
    async def test_aget_vertex_invalid_uri(self, mgr):
        result = await mgr.aget_vertex("invalid-uri")
        assert result is None

    @pytest.mark.usefixtures("clean_tables")
    async def test_adelete_vertex_success(self, mgr):
        await mgr.amupsert_vertex(
            "Artifact",
            {"entity_type": "artifact", "name": "测试删除"},
        )
        result = await mgr.adelete_vertex("cidoc:artifact/测试删除")
        assert result is True

        # Verify it's gone
        gone = await mgr.aget_vertex("cidoc:artifact/测试删除")
        assert gone is None

    @pytest.mark.usefixtures("clean_tables")
    async def test_adelete_vertex_not_found(self, mgr):
        result = await mgr.adelete_vertex("cidoc:artifact/不存在")
        assert result is False

    @pytest.mark.usefixtures("clean_tables")
    async def test_adelete_vertex_invalid_uri(self, mgr):
        result = await mgr.adelete_vertex("bad-uri")
        assert result is False

    @pytest.mark.usefixtures("clean_tables")
    async def test_vertex_crud_full_cycle(self, mgr):
        # Create
        created = await mgr.amupsert_vertex(
            "Artifact",
            {"entity_type": "artifact", "name": "循环测试", "description": "完整CRUD"},
        )
        assert created is not None

        # Read
        read = await mgr.aget_vertex("cidoc:artifact/循环测试")
        assert read is not None
        assert read["description"] == "完整CRUD"

        # Update
        updated = await mgr.amupsert_vertex(
            "Artifact",
            {"entity_type": "artifact", "name": "循环测试", "description": "更新后"},
        )
        assert updated is not None

        # Read again
        reread = await mgr.aget_vertex("cidoc:artifact/循环测试")
        assert reread is not None

        # Delete
        deleted = await mgr.adelete_vertex("cidoc:artifact/循环测试")
        assert deleted is True

        # Verify deletion
        final = await mgr.aget_vertex("cidoc:artifact/循环测试")
        assert final is None


@pytest.mark.usefixtures("setup_test_database", "mock_llm_extractor")
class TestEdgeCRUD:
    """Tests for edge create-read-update-delete — requires database."""

    @pytest.fixture
    def mgr(self):
        return AgeGraphManager(dbname=TEST_DB_NAME)

    async def _setup_two_nodes(self, mgr):
        await mgr.amupsert_vertex(
            "Artifact",
            {"entity_type": "artifact", "name": "青花瓷瓶"},
        )
        await mgr.amupsert_vertex(
            "Museum",
            {"entity_type": "museum", "name": "大都会博物馆"},
        )

    @pytest.mark.usefixtures("clean_tables")
    async def test_amupsert_edge_creates(self, mgr):
        await self._setup_two_nodes(mgr)
        result = await mgr.amupsert_edge(
            start_uri="cidoc:artifact/青花瓷瓶",
            end_uri="cidoc:museum/大都会博物馆",
            relationship_type="collected_by",
            properties={"description": "大都会收藏的青花瓷瓶"},
        )
        assert result is not None
        assert result["start_uri"] == "cidoc:artifact/青花瓷瓶"
        assert result["end_uri"] == "cidoc:museum/大都会博物馆"
        assert result["relationship_type"] == "collected_by"
        assert result["label"] == "collected_by"

    @pytest.mark.usefixtures("clean_tables")
    async def test_amupsert_edge_invalid_uri(self, mgr):
        result = await mgr.amupsert_edge(
            start_uri="bad-uri",
            end_uri="cidoc:museum/大都会博物馆",
            relationship_type="collected_by",
        )
        assert result is None

    @pytest.mark.usefixtures("clean_tables")
    async def test_amupsert_edge_missing_node(self, mgr):
        result = await mgr.amupsert_edge(
            start_uri="cidoc:artifact/不存在的文物",
            end_uri="cidoc:museum/不存在的博物馆",
            relationship_type="related_to",
        )
        assert result is None

    @pytest.mark.usefixtures("clean_tables")
    async def test_amupsert_edge_idempotent(self, mgr):
        await self._setup_two_nodes(mgr)
        await mgr.amupsert_edge(
            start_uri="cidoc:artifact/青花瓷瓶",
            end_uri="cidoc:museum/大都会博物馆",
            relationship_type="collected_by",
        )
        result = await mgr.amupsert_edge(
            start_uri="cidoc:artifact/青花瓷瓶",
            end_uri="cidoc:museum/大都会博物馆",
            relationship_type="collected_by",
        )
        assert result is not None
        assert result["relationship_type"] == "collected_by"

    @pytest.mark.usefixtures("clean_tables")
    async def test_aget_edge_found(self, mgr):
        await self._setup_two_nodes(mgr)
        await mgr.amupsert_edge(
            start_uri="cidoc:artifact/青花瓷瓶",
            end_uri="cidoc:museum/大都会博物馆",
            relationship_type="collected_by",
        )
        result = await mgr.aget_edge(
            start_uri="cidoc:artifact/青花瓷瓶",
            end_uri="cidoc:museum/大都会博物馆",
            relationship_type="collected_by",
        )
        assert result is not None
        assert result["relationship_type"] == "collected_by"

    @pytest.mark.usefixtures("clean_tables")
    async def test_aget_edge_not_found(self, mgr):
        await self._setup_two_nodes(mgr)
        result = await mgr.aget_edge(
            start_uri="cidoc:artifact/青花瓷瓶",
            end_uri="cidoc:museum/大都会博物馆",
            relationship_type="located_at",
        )
        assert result is None

    @pytest.mark.usefixtures("clean_tables")
    async def test_aget_edge_invalid_uri(self, mgr):
        result = await mgr.aget_edge(start_uri="bad", end_uri="cidoc:museum/故宫")
        assert result is None

    @pytest.mark.usefixtures("clean_tables")
    async def test_adelete_edge_success(self, mgr):
        await self._setup_two_nodes(mgr)
        await mgr.amupsert_edge(
            start_uri="cidoc:artifact/青花瓷瓶",
            end_uri="cidoc:museum/大都会博物馆",
            relationship_type="collected_by",
        )
        result = await mgr.adelete_edge(
            start_uri="cidoc:artifact/青花瓷瓶",
            end_uri="cidoc:museum/大都会博物馆",
            relationship_type="collected_by",
        )
        assert result is True

        # Verify deletion
        gone = await mgr.aget_edge(
            start_uri="cidoc:artifact/青花瓷瓶",
            end_uri="cidoc:museum/大都会博物馆",
            relationship_type="collected_by",
        )
        assert gone is None

    @pytest.mark.usefixtures("clean_tables")
    async def test_adelete_edge_not_found(self, mgr):
        await self._setup_two_nodes(mgr)
        result = await mgr.adelete_edge(
            start_uri="cidoc:artifact/青花瓷瓶",
            end_uri="cidoc:museum/大都会博物馆",
            relationship_type="collected_by",
        )
        assert result is False

    @pytest.mark.usefixtures("clean_tables")
    async def test_adelete_edge_invalid_uri(self, mgr):
        result = await mgr.adelete_edge(
            start_uri="bad-uri",
            end_uri="cidoc:museum/大都会博物馆",
            relationship_type="collected_by",
        )
        assert result is False

    @pytest.mark.usefixtures("clean_tables")
    async def test_edge_crud_full_cycle(self, mgr):
        await self._setup_two_nodes(mgr)

        # Create edge
        created = await mgr.amupsert_edge(
            start_uri="cidoc:artifact/青花瓷瓶",
            end_uri="cidoc:museum/大都会博物馆",
            relationship_type="collected_by",
            properties={"notes": "edge test"},
        )
        assert created is not None

        # Read edge
        read = await mgr.aget_edge(
            start_uri="cidoc:artifact/青花瓷瓶",
            end_uri="cidoc:museum/大都会博物馆",
        )
        assert read is not None
        assert read["relationship_type"] == "collected_by"

        # Delete edge
        deleted = await mgr.adelete_edge(
            start_uri="cidoc:artifact/青花瓷瓶",
            end_uri="cidoc:museum/大都会博物馆",
            relationship_type="collected_by",
        )
        assert deleted is True

        # Verify deletion
        gone = await mgr.aget_edge(
            start_uri="cidoc:artifact/青花瓷瓶",
            end_uri="cidoc:museum/大都会博物馆",
        )
        assert gone is None


@pytest.mark.usefixtures("setup_test_database", "mock_llm_extractor")
class TestTraverse:
    """Tests for graph traversal — requires database."""

    @pytest.fixture
    def mgr(self):
        return AgeGraphManager(dbname=TEST_DB_NAME)

    async def _setup_graph(self, mgr):
        """Create a small graph: A -> B -> C, A -> D"""
        for entity_type, name in [
            ("artifact", "节点A"),
            ("artifact", "节点B"),
            ("artifact", "节点C"),
            ("museum", "博物馆D"),
        ]:
            await mgr.amupsert_vertex("Entity", {"entity_type": entity_type, "name": name})

        await mgr.amupsert_edge("cidoc:artifact/节点A", "cidoc:artifact/节点B", "related_to")
        await mgr.amupsert_edge("cidoc:artifact/节点B", "cidoc:artifact/节点C", "related_to")
        await mgr.amupsert_edge("cidoc:artifact/节点A", "cidoc:museum/博物馆D", "located_at")

    @pytest.mark.usefixtures("clean_tables")
    async def test_atraverse_both(self, mgr):
        await self._setup_graph(mgr)
        graph = await mgr.atraverse("cidoc:artifact/节点A", max_hops=3, direction="both")
        assert len(graph.nodes) >= 2  # A plus at least B or D

    @pytest.mark.usefixtures("clean_tables")
    async def test_atraverse_outbound(self, mgr):
        await self._setup_graph(mgr)
        graph = await mgr.atraverse("cidoc:artifact/节点A", max_hops=3, direction="outbound")
        assert len(graph.nodes) >= 2

    @pytest.mark.usefixtures("clean_tables")
    async def test_atraverse_inbound(self, mgr):
        await self._setup_graph(mgr)
        graph = await mgr.atraverse("cidoc:artifact/节点B", max_hops=3, direction="inbound")
        assert len(graph.nodes) >= 1

    @pytest.mark.usefixtures("clean_tables")
    async def test_atraverse_invalid_uri(self, mgr):
        graph = await mgr.atraverse("invalid", max_hops=3)
        assert len(graph.nodes) == 0

    @pytest.mark.usefixtures("clean_tables")
    async def test_atraverse_max_hops_zero(self, mgr):
        await self._setup_graph(mgr)
        graph = await mgr.atraverse("cidoc:artifact/节点A", max_hops=0, direction="both")
        assert len(graph.nodes) >= 1  # At least the start node itself

    @pytest.mark.usefixtures("clean_tables")
    async def test_atraverse_multi(self, mgr):
        await self._setup_graph(mgr)
        graph = await mgr.atraverse_multi(
            ["cidoc:artifact/节点A", "cidoc:artifact/节点B"],
            max_hops=3,
        )
        assert len(graph.nodes) >= 2

    @pytest.mark.usefixtures("clean_tables")
    async def test_atraverse_multi_empty_uris(self, mgr):
        graph = await mgr.atraverse_multi([], max_hops=3)
        assert len(graph.nodes) == 0

    @pytest.mark.usefixtures("clean_tables")
    async def test_atraverse_multi_invalid_uris(self, mgr):
        graph = await mgr.atraverse_multi(["bad-uri-1", "bad-uri-2"], max_hops=3)
        assert len(graph.nodes) == 0

    @pytest.mark.usefixtures("clean_tables")
    async def test_atraverse_multi_outbound(self, mgr):
        await self._setup_graph(mgr)
        graph = await mgr.atraverse_multi(
            ["cidoc:artifact/节点A"],
            max_hops=3,
            direction="outbound",
        )
        assert len(graph.nodes) >= 2


@pytest.mark.usefixtures("setup_test_database", "mock_llm_extractor")
class TestFindPaths:
    """Tests for path-finding — requires database."""

    @pytest.fixture
    def mgr(self):
        return AgeGraphManager(dbname=TEST_DB_NAME)

    async def _setup_path_graph(self, mgr):
        """Create a path: A -> B -> C -> D"""
        for entity_type, name in [
            ("artifact", "起点"),
            ("artifact", "中间1"),
            ("artifact", "中间2"),
            ("artifact", "终点"),
        ]:
            await mgr.amupsert_vertex("Entity", {"entity_type": entity_type, "name": name})

        await mgr.amupsert_edge("cidoc:artifact/起点", "cidoc:artifact/中间1", "related_to")
        await mgr.amupsert_edge("cidoc:artifact/中间1", "cidoc:artifact/中间2", "related_to")
        await mgr.amupsert_edge("cidoc:artifact/中间2", "cidoc:artifact/终点", "related_to")

    @pytest.mark.usefixtures("clean_tables")
    async def test_afind_paths_basic(self, mgr):
        await self._setup_path_graph(mgr)
        graph = await mgr.afind_paths("cidoc:artifact/起点", "cidoc:artifact/终点", max_hops=5)
        assert len(graph.nodes) >= 2
        assert len(graph.edges) >= 1

    @pytest.mark.usefixtures("clean_tables")
    async def test_afind_paths_no_path(self, mgr):
        await mgr.amupsert_vertex("Entity", {"entity_type": "artifact", "name": "孤岛A"})
        await mgr.amupsert_vertex("Entity", {"entity_type": "artifact", "name": "孤岛B"})
        graph = await mgr.afind_paths("cidoc:artifact/孤岛A", "cidoc:artifact/孤岛B", max_hops=5)
        assert len(graph.edges) == 0

    @pytest.mark.usefixtures("clean_tables")
    async def test_afind_paths_invalid_start_uri(self, mgr):
        graph = await mgr.afind_paths("bad", "cidoc:artifact/终点", max_hops=5)
        assert len(graph.nodes) == 0
        assert len(graph.edges) == 0

    @pytest.mark.usefixtures("clean_tables")
    async def test_afind_paths_invalid_end_uri(self, mgr):
        await self._setup_path_graph(mgr)
        graph = await mgr.afind_paths("cidoc:artifact/起点", "bad", max_hops=5)
        assert len(graph.nodes) == 0

    @pytest.mark.usefixtures("clean_tables")
    async def test_afind_entity_paths_with_path(self, mgr):
        await self._setup_path_graph(mgr)
        result = await mgr.afind_entity_paths("cidoc:artifact/起点", "cidoc:artifact/终点", max_hops=5)
        assert "nodes" in result
        assert "edges" in result
        assert len(result["edges"]) >= 1

    @pytest.mark.usefixtures("clean_tables")
    async def test_afind_entity_paths_no_path(self, mgr):
        await mgr.amupsert_vertex("Entity", {"entity_type": "artifact", "name": "X"})
        await mgr.amupsert_vertex("Entity", {"entity_type": "artifact", "name": "Y"})
        result = await mgr.afind_entity_paths("cidoc:artifact/X", "cidoc:artifact/Y", max_hops=5)
        assert result["edges"] == []


@pytest.mark.usefixtures("setup_test_database", "mock_llm_extractor")
class TestContextExpansion:
    """Tests for context expansion — requires database."""

    @pytest.fixture
    def mgr(self):
        return AgeGraphManager(dbname=TEST_DB_NAME)

    async def _setup_star_graph(self, mgr):
        """Create a star: center -> A, center -> B, center -> C"""
        for entity_type, name in [
            ("artifact", "中心"),
            ("artifact", "邻居A"),
            ("artifact", "邻居B"),
            ("museum", "邻居C"),
        ]:
            await mgr.amupsert_vertex("Entity", {"entity_type": entity_type, "name": name})

        await mgr.amupsert_edge("cidoc:artifact/中心", "cidoc:artifact/邻居A", "related_to")
        await mgr.amupsert_edge("cidoc:artifact/中心", "cidoc:artifact/邻居B", "related_to")
        await mgr.amupsert_edge("cidoc:artifact/中心", "cidoc:museum/邻居C", "located_at")

    @pytest.mark.usefixtures("clean_tables")
    async def test_aexpand_context_basic(self, mgr):
        await self._setup_star_graph(mgr)
        ctx = await mgr.aexpand_context("cidoc:artifact/中心", max_hops=2, direction="both")
        assert ctx["center_entity"] == "cidoc:artifact/中心"
        assert len(ctx["connected_entities"]) >= 1
        assert len(ctx["paths"]) >= 1

    @pytest.mark.usefixtures("clean_tables")
    async def test_aexpand_context_empty(self, mgr):
        """Isolated node should have no connections."""
        await mgr.amupsert_vertex("Entity", {"entity_type": "artifact", "name": "孤独"})
        ctx = await mgr.aexpand_context("cidoc:artifact/孤独", max_hops=2)
        assert ctx["center_entity"] == "cidoc:artifact/孤独"
        assert ctx["connected_entities"] == []
        assert ctx["paths"] == []


@pytest.mark.usefixtures("setup_test_database", "mock_llm_extractor")
class TestNetworkXInterop:
    """Tests for NetworkX <-> AGE graph conversion — requires database."""

    @pytest.fixture
    def mgr(self):
        return AgeGraphManager(dbname=TEST_DB_NAME)

    @pytest.mark.usefixtures("clean_tables")
    async def test_afrom_networkx_and_ato_networkx(self, mgr):
        nx_in = DiGraph()
        nx_in.add_node(
            "cidoc:artifact/青铜鼎",
            label="Artifact",
            entity_type="artifact",
            name="青铜鼎",
            properties={"description": "商代"},
        )
        nx_in.add_node(
            "cidoc:museum/故宫", label="Museum", entity_type="museum", name="故宫", properties={"description": "北京"}
        )
        nx_in.add_edge("cidoc:artifact/青铜鼎", "cidoc:museum/故宫", label="collected_by", properties={"notes": "test"})

        success = await mgr.afrom_networkx(nx_in)
        assert success is True

        # Read back via traverse
        graph_out = await mgr.atraverse("cidoc:artifact/青铜鼎", max_hops=1)
        assert len(graph_out.nodes) >= 1

    @pytest.mark.usefixtures("clean_tables")
    async def test_afrom_networkx_empty(self, mgr):
        success = await mgr.afrom_networkx(DiGraph())
        assert success is True

    @pytest.mark.usefixtures("clean_tables")
    async def test_afrom_networkx_nodes_only(self, mgr):
        nx_in = DiGraph()
        nx_in.add_node("cidoc:artifact/陶瓷", label="Artifact", entity_type="artifact", name="陶瓷")
        nx_in.add_node("cidoc:material/黏土", label="Material", entity_type="material", name="黏土")

        success = await mgr.afrom_networkx(nx_in)
        assert success is True

        ceramic = await mgr.aget_vertex("cidoc:artifact/陶瓷")
        assert ceramic is not None
        assert ceramic["name"] == "陶瓷"

        clay = await mgr.aget_vertex("cidoc:material/黏土")
        assert clay is not None
        assert clay["name"] == "黏土"

    @pytest.mark.usefixtures("clean_tables")
    async def test_afrom_networkx_edges_only(self, mgr):
        nx_in = DiGraph()
        nx_in.add_node("cidoc:artifact/花瓶", label="Artifact", entity_type="artifact", name="花瓶")
        nx_in.add_node("cidoc:dynasty/清", label="Dynasty", entity_type="dynasty", name="清")
        nx_in.add_edge(
            "cidoc:artifact/花瓶", "cidoc:dynasty/清", label="belongs_to_dynasty", properties={"confidence": 0.95}
        )

        success = await mgr.afrom_networkx(nx_in)
        assert success is True

        edge = await mgr.aget_edge("cidoc:artifact/花瓶", "cidoc:dynasty/清")
        assert edge is not None
        assert edge["relationship_type"] == "belongs_to_dynasty"


@pytest.mark.usefixtures("setup_test_database", "mock_llm_extractor")
class TestEdgeConnections:
    """Tests for edge connection queries — requires database."""

    @pytest.fixture
    def mgr(self):
        return AgeGraphManager(dbname=TEST_DB_NAME)

    async def _setup_edges(self, mgr):
        nodes = [
            ("artifact", "鼎"),
            ("museum", "故宫"),
            ("dynasty", "商"),
            ("material", "青铜"),
        ]
        for entity_type, name in nodes:
            await mgr.amupsert_vertex("Entity", {"entity_type": entity_type, "name": name})

        await mgr.amupsert_edge("cidoc:artifact/鼎", "cidoc:museum/故宫", "collected_by", {"description": "故宫藏鼎"})
        await mgr.amupsert_edge(
            "cidoc:artifact/鼎", "cidoc:dynasty/商", "belongs_to_dynasty", {"description": "商代青铜鼎"}
        )
        await mgr.amupsert_edge(
            "cidoc:artifact/鼎", "cidoc:material/青铜", "made_of_material", {"description": "青铜材质"}
        )

    @pytest.mark.usefixtures("clean_tables")
    async def test_aget_all_edge_connections(self, mgr):
        await self._setup_edges(mgr)
        results = await mgr.aget_all_edge_connections()
        assert len(results) >= 3
        for row in results:
            assert "relationship_type" in row
            assert "subject_name" in row
            assert "object_name" in row
            assert "predicate_uri" in row

    @pytest.mark.usefixtures("clean_tables")
    async def test_aget_all_edge_connections_empty(self, mgr):
        results = await mgr.aget_all_edge_connections()
        assert results == []

    @pytest.mark.usefixtures("clean_tables")
    async def test_aquery_edge_connections_by_subject(self, mgr):
        await self._setup_edges(mgr)
        results = await mgr.aquery_edge_connections(subject_name="鼎")
        assert len(results) >= 1
        for row in results:
            assert "鼎" in row["subject_name"]

    @pytest.mark.usefixtures("clean_tables")
    async def test_aquery_edge_connections_by_predicate(self, mgr):
        await self._setup_edges(mgr)
        results = await mgr.aquery_edge_connections(predicate="collected_by")
        assert len(results) >= 1
        for row in results:
            assert row["relationship_type"] == "collected_by"

    @pytest.mark.usefixtures("clean_tables")
    async def test_aquery_edge_connections_by_object(self, mgr):
        await self._setup_edges(mgr)
        results = await mgr.aquery_edge_connections(object_name="青铜")
        assert len(results) >= 1
        for row in results:
            assert "青铜" in row["object_name"]

    @pytest.mark.usefixtures("clean_tables")
    async def test_aquery_edge_connections_by_description(self, mgr):
        await self._setup_edges(mgr)
        results = await mgr.aquery_edge_connections(description="藏鼎")
        assert len(results) >= 1

    @pytest.mark.usefixtures("clean_tables")
    async def test_aquery_edge_connections_limit(self, mgr):
        await self._setup_edges(mgr)
        results = await mgr.aquery_edge_connections(limit=1)
        assert len(results) <= 1

    @pytest.mark.usefixtures("clean_tables")
    async def test_aquery_edge_connections_no_match(self, mgr):
        await self._setup_edges(mgr)
        results = await mgr.aquery_edge_connections(subject_name="不存在的实体")
        assert results == []

    @pytest.mark.usefixtures("clean_tables")
    async def test_aquery_edge_connections_by_entity_names(self, mgr):
        await self._setup_edges(mgr)
        results = await mgr.aquery_edge_connections_by_entity_names(["鼎"])
        assert len(results) >= 1
        for row in results:
            assert row["query_name"] == "鼎"

    @pytest.mark.usefixtures("clean_tables")
    async def test_aquery_edge_connections_by_entity_names_multiple(self, mgr):
        await self._setup_edges(mgr)
        results = await mgr.aquery_edge_connections_by_entity_names(["鼎", "故宫"])
        assert len(results) >= 2

    @pytest.mark.usefixtures("clean_tables")
    async def test_aquery_edge_connections_by_entity_names_no_match(self, mgr):
        await self._setup_edges(mgr)
        results = await mgr.aquery_edge_connections_by_entity_names(["不存在"])
        assert results == []


@pytest.mark.usefixtures("setup_test_database", "mock_llm_extractor")
class TestGetVerticesByUris:
    """Tests for batch vertex retrieval — requires database."""

    @pytest.fixture
    def mgr(self):
        return AgeGraphManager(dbname=TEST_DB_NAME)

    @pytest.mark.usefixtures("clean_tables")
    async def test_aget_vertices_by_uris_basic(self, mgr):
        await mgr.amupsert_vertex("Entity", {"entity_type": "artifact", "name": "检索A"})
        await mgr.amupsert_vertex("Entity", {"entity_type": "museum", "name": "检索B"})
        await mgr.amupsert_vertex("Entity", {"entity_type": "dynasty", "name": "检索C"})

        results = await mgr.aget_vertices_by_uris([
            "cidoc:artifact/检索A",
            "cidoc:museum/检索B",
            "cidoc:dynasty/检索C",
        ])
        assert len(results) == 3
        names = {r["name"] for r in results}
        assert names == {"检索A", "检索B", "检索C"}

    @pytest.mark.usefixtures("clean_tables")
    async def test_aget_vertices_by_uris_partial_match(self, mgr):
        await mgr.amupsert_vertex("Entity", {"entity_type": "artifact", "name": "存在"})

        results = await mgr.aget_vertices_by_uris([
            "cidoc:artifact/存在",
            "cidoc:artifact/不存在",
        ])
        assert len(results) == 1
        assert results[0]["name"] == "存在"

    @pytest.mark.usefixtures("clean_tables")
    async def test_aget_vertices_by_uris_empty(self, mgr):
        results = await mgr.aget_vertices_by_uris([])
        assert results == []

    @pytest.mark.usefixtures("clean_tables")
    async def test_aget_vertices_by_uris_invalid_uris(self, mgr):
        results = await mgr.aget_vertices_by_uris(["bad-uri", "also-bad"])
        assert results == []

    @pytest.mark.usefixtures("clean_tables")
    async def test_aget_vertices_by_uris_mixed_valid_invalid(self, mgr):
        await mgr.amupsert_vertex("Entity", {"entity_type": "artifact", "name": "混合"})

        results = await mgr.aget_vertices_by_uris([
            "bad-uri",
            "cidoc:artifact/混合",
        ])
        assert len(results) == 1
        assert results[0]["name"] == "混合"


@pytest.mark.usefixtures("setup_test_database", "mock_llm_extractor")
class TestGraphLifecycle:
    """Tests for graph creation and deletion — requires database."""

    @pytest.fixture
    def mgr(self):
        return AgeGraphManager(dbname=TEST_DB_NAME)

    @pytest.mark.usefixtures("clean_tables")
    async def test_create_graph_already_exists(self, mgr):
        created = await mgr.acreate_graph()
        assert created is False

    @pytest.mark.usefixtures("clean_tables")
    async def test_drop_and_recreate(self, mgr):
        dropped = await mgr.adrop_graph()
        assert dropped is True

        created = await mgr.acreate_graph()
        assert created is True

        # Drop again should return True
        dropped2 = await mgr.adrop_graph()
        assert dropped2 is True

    @pytest.mark.usefixtures("clean_tables")
    async def test_drop_nonexistent_graph(self, mgr):
        await mgr.adrop_graph()
        dropped = await mgr.adrop_graph()
        assert dropped is False
