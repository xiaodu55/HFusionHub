# Copyright (c) 2026 HFusionHub. All rights reserved.
"""
知识图谱模块单元测试

测试覆盖：
- 数据模型：Entity, Relation, GraphNode, GraphEdge, GraphPath, SubGraph
- 图数据库接口：GraphDatabase, InMemoryGraphDatabase
- 知识图谱管理器：KnowledgeGraphManager
- 图谱构建器：GraphBuilder
- 工厂类：KnowledgeGraphFactory
"""

import pytest
from typing import Dict, List, Any

from app.core.rag.knowledge_graph import (
    EntityType,
    RelationType,
    GraphQueryType,
    Entity,
    Relation,
    GraphNode,
    GraphEdge,
    GraphPath,
    SubGraph,
    GraphQueryResult,
    GraphDatabase,
    Neo4jDatabase,
    InMemoryGraphDatabase,
    KnowledgeGraphManager,
    GraphBuilder,
    KnowledgeGraphFactory,
    get_knowledge_graph_manager,
    reset_knowledge_graph_manager,
)


# =============================================================================
# 测试数据模型
# =============================================================================

class TestEntityType:
    """测试 EntityType 枚举"""

    def test_entity_type_values(self):
        """测试枚举值"""
        assert EntityType.PERSON.value == "person"
        assert EntityType.ORGANIZATION.value == "organization"
        assert EntityType.LOCATION.value == "location"
        assert EntityType.CONCEPT.value == "concept"
        assert EntityType.TECHNOLOGY.value == "technology"
        assert EntityType.PRODUCT.value == "product"
        assert EntityType.EVENT.value == "event"
        assert EntityType.OTHER.value == "other"

    def test_entity_type_count(self):
        """测试枚举数量"""
        assert len(EntityType) == 8


class TestRelationType:
    """测试 RelationType 枚举"""

    def test_relation_type_values(self):
        """测试枚举值"""
        assert RelationType.IS_A.value == "is_a"
        assert RelationType.PART_OF.value == "part_of"
        assert RelationType.USES.value == "uses"
        assert RelationType.CREATED_BY.value == "created_by"
        assert RelationType.LOCATED_IN.value == "located_in"
        assert RelationType.RELATED_TO.value == "related_to"
        assert RelationType.DEPENDS_ON.value == "depends_on"
        assert RelationType.INHERITS.value == "inherits"
        assert RelationType.IMPLEMENTS.value == "implements"
        assert RelationType.OTHER.value == "other"

    def test_relation_type_count(self):
        """测试枚举数量"""
        assert len(RelationType) == 10


class TestGraphQueryType:
    """测试 GraphQueryType 枚举"""

    def test_graph_query_type_values(self):
        """测试枚举值"""
        assert GraphQueryType.ENTITY_SEARCH.value == "entity_search"
        assert GraphQueryType.RELATION_SEARCH.value == "relation_search"
        assert GraphQueryType.PATH_SEARCH.value == "path_search"
        assert GraphQueryType.NEIGHBOR_SEARCH.value == "neighbor_search"
        assert GraphQueryType.SUBGRAPH.value == "subgraph"

    def test_graph_query_type_count(self):
        """测试枚举数量"""
        assert len(GraphQueryType) == 5


class TestEntity:
    """测试 Entity 数据模型"""

    def test_create_entity(self):
        """测试创建实体"""
        entity = Entity(
            id="e1",
            name="Python",
            entity_type=EntityType.TECHNOLOGY,
            description="A programming language",
            properties={"version": "3.10"},
            aliases=["Python3"]
        )

        assert entity.id == "e1"
        assert entity.name == "Python"
        assert entity.entity_type == EntityType.TECHNOLOGY
        assert entity.description == "A programming language"
        assert entity.properties == {"version": "3.10"}
        assert entity.aliases == ["Python3"]

    def test_entity_default_values(self):
        """测试默认值"""
        entity = Entity(id="e1", name="Test", entity_type=EntityType.OTHER)

        assert entity.description == ""
        assert entity.properties == {}
        assert entity.aliases == []

    def test_entity_validation_empty_id(self):
        """测试空 ID 验证"""
        with pytest.raises(ValueError, match="Entity id cannot be empty"):
            Entity(id="", name="Test", entity_type=EntityType.OTHER)

    def test_entity_validation_empty_name(self):
        """测试空名称验证"""
        with pytest.raises(ValueError, match="Entity name cannot be empty"):
            Entity(id="e1", name="", entity_type=EntityType.OTHER)


class TestRelation:
    """测试 Relation 数据模型"""

    def test_create_relation(self):
        """测试创建关系"""
        relation = Relation(
            id="r1",
            source_id="e1",
            target_id="e2",
            relation_type=RelationType.USES,
            weight=0.8,
            description="uses relationship",
            properties={"strength": "strong"}
        )

        assert relation.id == "r1"
        assert relation.source_id == "e1"
        assert relation.target_id == "e2"
        assert relation.relation_type == RelationType.USES
        assert relation.weight == 0.8
        assert relation.description == "uses relationship"
        assert relation.properties == {"strength": "strong"}

    def test_relation_default_values(self):
        """测试默认值"""
        relation = Relation(
            id="r1",
            source_id="e1",
            target_id="e2",
            relation_type=RelationType.RELATED_TO
        )

        assert relation.weight == 1.0
        assert relation.description == ""
        assert relation.properties == {}

    def test_relation_validation_empty_id(self):
        """测试空 ID 验证"""
        with pytest.raises(ValueError, match="Relation id cannot be empty"):
            Relation(id="", source_id="e1", target_id="e2", relation_type=RelationType.RELATED_TO)

    def test_relation_validation_empty_source(self):
        """测试空源节点验证"""
        with pytest.raises(ValueError, match="Relation source_id cannot be empty"):
            Relation(id="r1", source_id="", target_id="e2", relation_type=RelationType.RELATED_TO)

    def test_relation_validation_empty_target(self):
        """测试空目标节点验证"""
        with pytest.raises(ValueError, match="Relation target_id cannot be empty"):
            Relation(id="r1", source_id="e1", target_id="", relation_type=RelationType.RELATED_TO)

    def test_relation_validation_weight(self):
        """测试权重验证"""
        with pytest.raises(ValueError, match="Relation weight must be between"):
            Relation(id="r1", source_id="e1", target_id="e2", relation_type=RelationType.RELATED_TO, weight=11)


class TestGraphNode:
    """测试 GraphNode 数据模型"""

    def test_create_graph_node(self):
        """测试创建图节点"""
        entity = Entity(id="e1", name="Test", entity_type=EntityType.OTHER)
        node = GraphNode(entity=entity, score=0.9, depth=2, path=["e1", "e2"])

        assert node.entity == entity
        assert node.score == 0.9
        assert node.depth == 2
        assert node.path == ["e1", "e2"]

    def test_graph_node_default_values(self):
        """测试默认值"""
        entity = Entity(id="e1", name="Test", entity_type=EntityType.OTHER)
        node = GraphNode(entity=entity)

        assert node.score == 0.0
        assert node.depth == 0
        assert node.path == []


class TestGraphEdge:
    """测试 GraphEdge 数据模型"""

    def test_create_graph_edge(self):
        """测试创建图边"""
        relation = Relation(
            id="r1",
            source_id="e1",
            target_id="e2",
            relation_type=RelationType.RELATED_TO
        )
        edge = GraphEdge(relation=relation, score=0.8)

        assert edge.relation == relation
        assert edge.score == 0.8

    def test_graph_edge_default_values(self):
        """测试默认值"""
        relation = Relation(
            id="r1",
            source_id="e1",
            target_id="e2",
            relation_type=RelationType.RELATED_TO
        )
        edge = GraphEdge(relation=relation)

        assert edge.score == 0.0


class TestGraphPath:
    """测试 GraphPath 数据模型"""

    def test_create_graph_path(self):
        """测试创建图路径"""
        entity1 = Entity(id="e1", name="A", entity_type=EntityType.OTHER)
        entity2 = Entity(id="e2", name="B", entity_type=EntityType.OTHER)
        relation = Relation(id="r1", source_id="e1", target_id="e2", relation_type=RelationType.RELATED_TO)

        path = GraphPath(
            nodes=[GraphNode(entity=entity1), GraphNode(entity=entity2)],
            edges=[GraphEdge(relation=relation)],
            total_score=0.9
        )

        assert len(path.nodes) == 2
        assert len(path.edges) == 1
        assert path.total_score == 0.9

    def test_graph_path_default_values(self):
        """测试默认值"""
        path = GraphPath(nodes=[], edges=[])

        assert path.total_score == 0.0


class TestSubGraph:
    """测试 SubGraph 数据模型"""

    def test_create_subgraph(self):
        """测试创建子图"""
        entity1 = Entity(id="e1", name="A", entity_type=EntityType.OTHER)
        entity2 = Entity(id="e2", name="B", entity_type=EntityType.OTHER)
        relation = Relation(id="r1", source_id="e1", target_id="e2", relation_type=RelationType.RELATED_TO)

        subgraph = SubGraph(
            nodes=[GraphNode(entity=entity1), GraphNode(entity=entity2)],
            edges=[GraphEdge(relation=relation)],
            center_entity="e1",
            radius=2
        )

        assert len(subgraph.nodes) == 2
        assert len(subgraph.edges) == 1
        assert subgraph.center_entity == "e1"
        assert subgraph.radius == 2

    def test_subgraph_default_values(self):
        """测试默认值"""
        subgraph = SubGraph(nodes=[], edges=[])

        assert subgraph.center_entity is None
        assert subgraph.radius == 1


class TestGraphQueryResult:
    """测试 GraphQueryResult 数据模型"""

    def test_create_graph_query_result(self):
        """测试创建图查询结果"""
        entity = Entity(id="e1", name="Test", entity_type=EntityType.OTHER)
        relation = Relation(id="r1", source_id="e1", target_id="e2", relation_type=RelationType.RELATED_TO)

        result = GraphQueryResult(
            query_type=GraphQueryType.ENTITY_SEARCH,
            entities=[GraphNode(entity=entity)],
            relations=[GraphEdge(relation=relation)],
            paths=[],
            total_count=1,
            metadata={"key": "value"}
        )

        assert result.query_type == GraphQueryType.ENTITY_SEARCH
        assert len(result.entities) == 1
        assert len(result.relations) == 1
        assert result.total_count == 1
        assert result.metadata == {"key": "value"}


# =============================================================================
# 测试图数据库接口
# =============================================================================

class TestInMemoryGraphDatabase:
    """测试内存图数据库"""

    @pytest.fixture
    def db(self):
        """创建测试数据库"""
        return InMemoryGraphDatabase()

    @pytest.fixture
    def sample_entities(self):
        """创建示例实体"""
        return [
            Entity(id="e1", name="Python", entity_type=EntityType.TECHNOLOGY, description="Programming language"),
            Entity(id="e2", name="Java", entity_type=EntityType.TECHNOLOGY, description="Programming language"),
            Entity(id="e3", name="Flask", entity_type=EntityType.PRODUCT, description="Web framework"),
            Entity(id="e4", name="Django", entity_type=EntityType.PRODUCT, description="Web framework"),
        ]

    @pytest.fixture
    def sample_relations(self):
        """创建示例关系"""
        return [
            Relation(id="r1", source_id="e3", target_id="e1", relation_type=RelationType.USES, weight=0.9),
            Relation(id="r2", source_id="e4", target_id="e2", relation_type=RelationType.USES, weight=0.9),
            Relation(id="r3", source_id="e1", target_id="e2", relation_type=RelationType.RELATED_TO, weight=0.5),
        ]

    @pytest.mark.asyncio
    async def test_connect_disconnect(self, db):
        """测试连接和断开"""
        assert await db.connect() is True
        assert await db.is_connected() is True
        assert await db.disconnect() is True
        assert await db.is_connected() is False

    @pytest.mark.asyncio
    async def test_add_entity(self, db):
        """测试添加实体"""
        await db.connect()

        entity = Entity(id="e1", name="Test", entity_type=EntityType.OTHER)
        assert await db.add_entity(entity) is True

        retrieved = await db.get_entity("e1")
        assert retrieved is not None
        assert retrieved.id == "e1"
        assert retrieved.name == "Test"

    @pytest.mark.asyncio
    async def test_add_relation(self, db, sample_entities):
        """测试添加关系"""
        await db.connect()

        for entity in sample_entities:
            await db.add_entity(entity)

        relation = Relation(
            id="r1",
            source_id="e1",
            target_id="e2",
            relation_type=RelationType.RELATED_TO
        )
        assert await db.add_relation(relation) is True

        retrieved = await db.get_relation("r1")
        assert retrieved is not None
        assert retrieved.id == "r1"

    @pytest.mark.asyncio
    async def test_search_entities(self, db, sample_entities):
        """测试搜索实体"""
        await db.connect()

        for entity in sample_entities:
            await db.add_entity(entity)

        # 搜索包含 "Python" 的实体
        results = await db.search_entities("Python")
        assert len(results) == 1
        assert results[0].name == "Python"

        # 搜索包含 "language" 的实体
        results = await db.search_entities("language")
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_search_entities_with_type(self, db, sample_entities):
        """测试按类型搜索实体"""
        await db.connect()

        for entity in sample_entities:
            await db.add_entity(entity)

        # 搜索技术类型
        results = await db.search_entities("language", entity_type=EntityType.TECHNOLOGY)
        assert len(results) == 2

        # 搜索框架类型
        results = await db.search_entities("framework", entity_type=EntityType.PRODUCT)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_search_relations(self, db, sample_entities, sample_relations):
        """测试搜索关系"""
        await db.connect()

        for entity in sample_entities:
            await db.add_entity(entity)
        for relation in sample_relations:
            await db.add_relation(relation)

        # 搜索源节点为 e3 的关系
        results = await db.search_relations(source_id="e3")
        assert len(results) == 1
        assert results[0].source_id == "e3"

        # 搜索目标节点为 e1 的关系
        results = await db.search_relations(target_id="e1")
        assert len(results) == 1
        assert results[0].target_id == "e1"

    @pytest.mark.asyncio
    async def test_get_neighbors(self, db, sample_entities, sample_relations):
        """测试获取邻居节点"""
        await db.connect()

        for entity in sample_entities:
            await db.add_entity(entity)
        for relation in sample_relations:
            await db.add_relation(relation)

        # 获取 e1 的邻居
        neighbors, relations = await db.get_neighbors("e1")
        assert len(neighbors) == 2  # e2 (RELATED_TO) 和 e3 (USES)
        assert len(relations) == 2

    @pytest.mark.asyncio
    async def test_get_neighbors_with_relation_type(self, db, sample_entities, sample_relations):
        """测试按关系类型获取邻居"""
        await db.connect()

        for entity in sample_entities:
            await db.add_entity(entity)
        for relation in sample_relations:
            await db.add_relation(relation)

        # 只获取 USES 关系的邻居
        neighbors, relations = await db.get_neighbors("e3", relation_types=[RelationType.USES])
        assert len(neighbors) == 1
        assert neighbors[0].id == "e1"

    @pytest.mark.asyncio
    async def test_find_path(self, db, sample_entities, sample_relations):
        """测试查找路径"""
        await db.connect()

        for entity in sample_entities:
            await db.add_entity(entity)
        for relation in sample_relations:
            await db.add_relation(relation)

        # 查找 e3 到 e2 的路径
        path = await db.find_path("e3", "e2")
        assert path is not None
        assert len(path.nodes) > 0

    @pytest.mark.asyncio
    async def test_find_path_no_path(self, db, sample_entities):
        """测试无路径情况"""
        await db.connect()

        for entity in sample_entities:
            await db.add_entity(entity)

        # 没有关系，应该找不到路径
        path = await db.find_path("e1", "e2")
        assert path is None

    @pytest.mark.asyncio
    async def test_get_subgraph(self, db, sample_entities, sample_relations):
        """测试获取子图"""
        await db.connect()

        for entity in sample_entities:
            await db.add_entity(entity)
        for relation in sample_relations:
            await db.add_relation(relation)

        # 获取 e1 的子图
        subgraph = await db.get_subgraph("e1", radius=1)
        assert len(subgraph.nodes) > 0
        assert subgraph.center_entity == "e1"

    @pytest.mark.asyncio
    async def test_delete_entity(self, db):
        """测试删除实体"""
        await db.connect()

        entity = Entity(id="e1", name="Test", entity_type=EntityType.OTHER)
        await db.add_entity(entity)

        assert await db.delete_entity("e1") is True
        assert await db.get_entity("e1") is None

    @pytest.mark.asyncio
    async def test_delete_relation(self, db, sample_entities):
        """测试删除关系"""
        await db.connect()

        for entity in sample_entities[:2]:
            await db.add_entity(entity)

        relation = Relation(id="r1", source_id="e1", target_id="e2", relation_type=RelationType.RELATED_TO)
        await db.add_relation(relation)

        assert await db.delete_relation("r1") is True
        assert await db.get_relation("r1") is None

    @pytest.mark.asyncio
    async def test_clear(self, db, sample_entities):
        """测试清空图谱"""
        await db.connect()

        for entity in sample_entities:
            await db.add_entity(entity)

        assert await db.clear() is True
        assert await db.get_entity("e1") is None


# =============================================================================
# 测试知识图谱管理器
# =============================================================================

class TestKnowledgeGraphManager:
    """测试知识图谱管理器"""

    @pytest.fixture
    def manager(self):
        """创建测试管理器"""
        db = InMemoryGraphDatabase()
        return KnowledgeGraphManager(database=db)

    @pytest.mark.asyncio
    async def test_initialize_shutdown(self, manager):
        """测试初始化和关闭"""
        assert await manager.initialize() is True
        assert await manager.shutdown() is True

    @pytest.mark.asyncio
    async def test_add_entity(self, manager):
        """测试添加实体"""
        await manager.initialize()

        entity = Entity(id="e1", name="Test", entity_type=EntityType.OTHER)
        assert await manager.add_entity(entity) is True

        retrieved = await manager.get_entity("e1")
        assert retrieved is not None
        assert retrieved.id == "e1"

    @pytest.mark.asyncio
    async def test_add_relation(self, manager):
        """测试添加关系"""
        await manager.initialize()

        entity1 = Entity(id="e1", name="A", entity_type=EntityType.OTHER)
        entity2 = Entity(id="e2", name="B", entity_type=EntityType.OTHER)
        await manager.add_entity(entity1)
        await manager.add_entity(entity2)

        relation = Relation(id="r1", source_id="e1", target_id="e2", relation_type=RelationType.RELATED_TO)
        assert await manager.add_relation(relation) is True

        retrieved = await manager.get_relation("r1")
        assert retrieved is not None

    @pytest.mark.asyncio
    async def test_search_entities(self, manager):
        """测试搜索实体"""
        await manager.initialize()

        entity1 = Entity(id="e1", name="Python", entity_type=EntityType.TECHNOLOGY)
        entity2 = Entity(id="e2", name="Java", entity_type=EntityType.TECHNOLOGY)
        await manager.add_entity(entity1)
        await manager.add_entity(entity2)

        results = await manager.search_entities("Python")
        assert len(results) == 1
        assert results[0].name == "Python"

    @pytest.mark.asyncio
    async def test_get_neighbors(self, manager):
        """测试获取邻居节点"""
        await manager.initialize()

        entity1 = Entity(id="e1", name="A", entity_type=EntityType.OTHER)
        entity2 = Entity(id="e2", name="B", entity_type=EntityType.OTHER)
        await manager.add_entity(entity1)
        await manager.add_entity(entity2)

        relation = Relation(id="r1", source_id="e1", target_id="e2", relation_type=RelationType.RELATED_TO)
        await manager.add_relation(relation)

        neighbors, relations = await manager.get_neighbors("e1")
        assert len(neighbors) == 1
        assert len(relations) == 1

    @pytest.mark.asyncio
    async def test_find_path(self, manager):
        """测试查找路径"""
        await manager.initialize()

        entity1 = Entity(id="e1", name="A", entity_type=EntityType.OTHER)
        entity2 = Entity(id="e2", name="B", entity_type=EntityType.OTHER)
        entity3 = Entity(id="e3", name="C", entity_type=EntityType.OTHER)
        await manager.add_entity(entity1)
        await manager.add_entity(entity2)
        await manager.add_entity(entity3)

        relation1 = Relation(id="r1", source_id="e1", target_id="e2", relation_type=RelationType.RELATED_TO)
        relation2 = Relation(id="r2", source_id="e2", target_id="e3", relation_type=RelationType.RELATED_TO)
        await manager.add_relation(relation1)
        await manager.add_relation(relation2)

        path = await manager.find_path("e1", "e3")
        assert path is not None
        assert len(path.nodes) > 0

    @pytest.mark.asyncio
    async def test_get_subgraph(self, manager):
        """测试获取子图"""
        await manager.initialize()

        entity1 = Entity(id="e1", name="A", entity_type=EntityType.OTHER)
        entity2 = Entity(id="e2", name="B", entity_type=EntityType.OTHER)
        await manager.add_entity(entity1)
        await manager.add_entity(entity2)

        relation = Relation(id="r1", source_id="e1", target_id="e2", relation_type=RelationType.RELATED_TO)
        await manager.add_relation(relation)

        subgraph = await manager.get_subgraph("e1", radius=1)
        assert len(subgraph.nodes) > 0
        assert subgraph.center_entity == "e1"

    @pytest.mark.asyncio
    async def test_delete_entity(self, manager):
        """测试删除实体"""
        await manager.initialize()

        entity = Entity(id="e1", name="Test", entity_type=EntityType.OTHER)
        await manager.add_entity(entity)

        assert await manager.delete_entity("e1") is True
        assert await manager.get_entity("e1") is None

    @pytest.mark.asyncio
    async def test_clear(self, manager):
        """测试清空图谱"""
        await manager.initialize()

        entity = Entity(id="e1", name="Test", entity_type=EntityType.OTHER)
        await manager.add_entity(entity)

        assert await manager.clear() is True
        assert await manager.get_entity("e1") is None

    def test_get_stats(self, manager):
        """测试获取统计信息"""
        stats = manager.get_stats()
        assert "initialized" in stats
        assert "database_type" in stats
        assert stats["database_type"] == "InMemoryGraphDatabase"


# =============================================================================
# 测试图谱构建器
# =============================================================================

class TestGraphBuilder:
    """测试图谱构建器"""

    @pytest.fixture
    def builder(self):
        """创建测试构建器"""
        db = InMemoryGraphDatabase()
        manager = KnowledgeGraphManager(database=db)
        return GraphBuilder(manager)

    @pytest.mark.asyncio
    async def test_build_graph(self, builder):
        """测试构建图谱"""
        builder.add_entity(id="e1", name="Python", entity_type=EntityType.TECHNOLOGY)
        builder.add_entity(id="e2", name="Java", entity_type=EntityType.TECHNOLOGY)
        builder.add_relation(id="r1", source_id="e1", target_id="e2", relation_type=RelationType.RELATED_TO)

        assert await builder.build() is True

    def test_chained_calls(self, builder):
        """测试链式调用"""
        result = (
            builder
            .add_entity(id="e1", name="A", entity_type=EntityType.OTHER)
            .add_entity(id="e2", name="B", entity_type=EntityType.OTHER)
            .add_relation(id="r1", source_id="e1", target_id="e2", relation_type=RelationType.RELATED_TO)
        )

        assert result is builder

    def test_clear(self, builder):
        """测试清空构建器"""
        builder.add_entity(id="e1", name="A", entity_type=EntityType.OTHER)
        builder.add_relation(id="r1", source_id="e1", target_id="e2", relation_type=RelationType.RELATED_TO)

        result = builder.clear()
        assert result is builder
        assert len(builder._entities) == 0
        assert len(builder._relations) == 0


# =============================================================================
# 测试工厂类
# =============================================================================

class TestKnowledgeGraphFactory:
    """测试工厂类"""

    def test_create_in_memory_manager(self):
        """测试创建内存管理器"""
        manager = KnowledgeGraphFactory.create_in_memory_manager()
        assert manager is not None
        assert isinstance(manager.database, InMemoryGraphDatabase)

    def test_create_builder(self):
        """测试创建构建器"""
        manager = KnowledgeGraphFactory.create_in_memory_manager()
        builder = KnowledgeGraphFactory.create_builder(manager)
        assert builder is not None
        assert builder.manager is manager


# =============================================================================
# 测试全局实例
# =============================================================================

class TestGlobalInstance:
    """测试全局实例"""

    def setup_method(self):
        """每个测试前重置"""
        reset_knowledge_graph_manager()

    def teardown_method(self):
        """每个测试后重置"""
        reset_knowledge_graph_manager()

    def test_get_knowledge_graph_manager(self):
        """测试获取全局管理器"""
        manager = get_knowledge_graph_manager()
        assert manager is not None

    def test_get_knowledge_graph_manager_singleton(self):
        """测试全局管理器是单例"""
        manager1 = get_knowledge_graph_manager()
        manager2 = get_knowledge_graph_manager()
        assert manager1 is manager2

    def test_reset_knowledge_graph_manager(self):
        """测试重置全局管理器"""
        manager1 = get_knowledge_graph_manager()
        reset_knowledge_graph_manager()
        manager2 = get_knowledge_graph_manager()
        assert manager1 is not manager2


# =============================================================================
# 测试集成场景
# =============================================================================

class TestIntegration:
    """测试集成场景"""

    @pytest.mark.asyncio
    async def test_complete_workflow(self):
        """测试完整工作流程"""
        # 创建管理器
        manager = KnowledgeGraphFactory.create_in_memory_manager()
        await manager.initialize()

        # 添加实体
        python = Entity(
            id="python",
            name="Python",
            entity_type=EntityType.TECHNOLOGY,
            description="A high-level programming language"
        )
        java = Entity(
            id="java",
            name="Java",
            entity_type=EntityType.TECHNOLOGY,
            description="A class-based programming language"
        )
        flask = Entity(
            id="flask",
            name="Flask",
            entity_type=EntityType.PRODUCT,
            description="A lightweight web framework for Python"
        )

        await manager.add_entity(python)
        await manager.add_entity(java)
        await manager.add_entity(flask)

        # 添加关系
        rel1 = Relation(
            id="r1",
            source_id="flask",
            target_id="python",
            relation_type=RelationType.USES,
            weight=0.9,
            description="Flask uses Python"
        )
        rel2 = Relation(
            id="r2",
            source_id="python",
            target_id="java",
            relation_type=RelationType.RELATED_TO,
            weight=0.5,
            description="Python is related to Java"
        )

        await manager.add_relation(rel1)
        await manager.add_relation(rel2)

        # 搜索实体
        results = await manager.search_entities("Python")
        # Should find Python entity and Flask (which has "Python" in description)
        assert len(results) >= 1
        assert any(e.name == "Python" for e in results)

        # 获取邻居
        neighbors, relations = await manager.get_neighbors("flask")
        assert len(neighbors) == 1
        assert neighbors[0].name == "Python"

        # 查找路径
        path = await manager.find_path("flask", "java")
        assert path is not None
        assert len(path.nodes) > 0

        # 获取子图
        subgraph = await manager.get_subgraph("python", radius=1)
        assert len(subgraph.nodes) > 0

        # 清空图谱
        assert await manager.clear() is True

    @pytest.mark.asyncio
    async def test_builder_workflow(self):
        """测试构建器工作流程"""
        # 创建管理器
        manager = KnowledgeGraphFactory.create_in_memory_manager()
        await manager.initialize()

        # 使用构建器构建图谱
        builder = KnowledgeGraphFactory.create_builder(manager)
        (
            builder
            .add_entity(id="e1", name="Entity1", entity_type=EntityType.CONCEPT)
            .add_entity(id="e2", name="Entity2", entity_type=EntityType.CONCEPT)
            .add_entity(id="e3", name="Entity3", entity_type=EntityType.CONCEPT)
            .add_relation(id="r1", source_id="e1", target_id="e2", relation_type=RelationType.RELATED_TO)
            .add_relation(id="r2", source_id="e2", target_id="e3", relation_type=RelationType.RELATED_TO)
        )

        assert await builder.build() is True

        # 验证实体
        entity1 = await manager.get_entity("e1")
        assert entity1 is not None
        assert entity1.name == "Entity1"

        # 验证关系
        relation1 = await manager.get_relation("r1")
        assert relation1 is not None
        assert relation1.source_id == "e1"

        # 验证路径
        path = await manager.find_path("e1", "e3")
        assert path is not None
