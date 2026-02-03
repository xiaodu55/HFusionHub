# Copyright (c) 2026 HFusionHub. All rights reserved.
"""
知识图谱模块 - 实体关系检索和图谱管理

参考项目：
- LangGraph: 状态机、多 Agent 协作
- LlamaIndex: 知识图谱索引
- GraphRAG: 图谱增强检索

设计模式：
- 枚举模式: EntityType, RelationType - 类型安全的枚举定义
- 策略模式: 多种图谱查询策略，运行时可切换
- 工厂模式: KnowledgeGraphFactory - 统一图谱创建
- 单例模式: 全局唯一图谱管理器
- 建造者模式: GraphBuilder - 构建知识图谱
"""

import logging
from enum import Enum
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

from .utils import (
    RELATION_WEIGHT_MIN,
    RELATION_WEIGHT_MAX,
    MAX_PATH_DEPTH,
    ENTITY_MATCH_BASE_SCORE,
    NEIGHBOR_RELATION_SCORE,
)

logger = logging.getLogger(__name__)


# =============================================================================
# 枚举定义
# =============================================================================

class EntityType(str, Enum):
    """实体类型"""
    PERSON = "person"           # 人物
    ORGANIZATION = "organization"  # 组织
    LOCATION = "location"       # 地点
    CONCEPT = "concept"         # 概念
    TECHNOLOGY = "technology"   # 技术
    PRODUCT = "product"         # 产品
    EVENT = "event"             # 事件
    OTHER = "other"             # 其他


class RelationType(str, Enum):
    """关系类型"""
    IS_A = "is_a"               # 是一种
    PART_OF = "part_of"         # 是一部分
    USES = "uses"               # 使用
    CREATED_BY = "created_by"   # 创建者
    LOCATED_IN = "located_in"   # 位于
    RELATED_TO = "related_to"   # 相关
    DEPENDS_ON = "depends_on"   # 依赖
    INHERITS = "inherits"       # 继承
    IMPLEMENTS = "implements"   # 实现
    OTHER = "other"             # 其他


class GraphQueryType(str, Enum):
    """图谱查询类型"""
    ENTITY_SEARCH = "entity_search"      # 实体搜索
    RELATION_SEARCH = "relation_search"  # 关系搜索
    PATH_SEARCH = "path_search"          # 路径搜索
    NEIGHBOR_SEARCH = "neighbor_search"  # 邻居搜索
    SUBGRAPH = "subgraph"                # 子图查询


# =============================================================================
# 数据模型
# =============================================================================

@dataclass
class Entity:
    """实体"""
    id: str
    name: str
    entity_type: EntityType
    properties: Dict[str, Any] = field(default_factory=dict)
    description: str = ""
    aliases: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.id:
            raise ValueError("Entity id cannot be empty")
        if not self.name:
            raise ValueError("Entity name cannot be empty")


@dataclass
class Relation:
    """关系"""
    id: str
    source_id: str
    target_id: str
    relation_type: RelationType
    properties: Dict[str, Any] = field(default_factory=dict)
    weight: float = 1.0
    description: str = ""

    def __post_init__(self):
        if not self.id:
            raise ValueError("Relation id cannot be empty")
        if not self.source_id:
            raise ValueError("Relation source_id cannot be empty")
        if not self.target_id:
            raise ValueError("Relation target_id cannot be empty")
        if not RELATION_WEIGHT_MIN <= self.weight <= RELATION_WEIGHT_MAX:
            raise ValueError(f"Relation weight must be between {RELATION_WEIGHT_MIN} and {RELATION_WEIGHT_MAX}")


@dataclass
class GraphNode:
    """图节点（用于返回结果）"""
    entity: Entity
    score: float = 0.0
    depth: int = 0
    path: List[str] = field(default_factory=list)


@dataclass
class GraphEdge:
    """图边（用于返回结果）"""
    relation: Relation
    score: float = 0.0


@dataclass
class GraphPath:
    """图路径"""
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    total_score: float = 0.0


@dataclass
class SubGraph:
    """子图"""
    nodes: List[GraphNode]
    edges: List[GraphEdge]
    center_entity: Optional[str] = None
    radius: int = 1


@dataclass
class GraphQueryResult:
    """图谱查询结果"""
    query_type: GraphQueryType
    entities: List[GraphNode]
    relations: List[GraphEdge]
    paths: List[GraphPath]
    subgraph: Optional[SubGraph] = None
    total_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# 图数据库接口
# =============================================================================

class GraphDatabase(ABC):
    """图数据库抽象基类"""

    @abstractmethod
    async def connect(self) -> bool:
        """连接数据库"""
        pass

    @abstractmethod
    async def disconnect(self) -> bool:
        """断开连接"""
        pass

    @abstractmethod
    async def is_connected(self) -> bool:
        """检查连接状态"""
        pass

    @abstractmethod
    async def add_entity(self, entity: Entity) -> bool:
        """添加实体"""
        pass

    @abstractmethod
    async def add_relation(self, relation: Relation) -> bool:
        """添加关系"""
        pass

    @abstractmethod
    async def get_entity(self, entity_id: str) -> Optional[Entity]:
        """获取实体"""
        pass

    @abstractmethod
    async def get_relation(self, relation_id: str) -> Optional[Relation]:
        """获取关系"""
        pass

    @abstractmethod
    async def search_entities(
        self,
        query: str,
        entity_type: Optional[EntityType] = None,
        limit: int = 10
    ) -> List[Entity]:
        """搜索实体"""
        pass

    @abstractmethod
    async def search_relations(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        relation_type: Optional[RelationType] = None,
        limit: int = 10
    ) -> List[Relation]:
        """搜索关系"""
        pass

    @abstractmethod
    async def get_neighbors(
        self,
        entity_id: str,
        depth: int = 1,
        relation_types: Optional[List[RelationType]] = None
    ) -> Tuple[List[Entity], List[Relation]]:
        """获取邻居节点"""
        pass

    @abstractmethod
    async def find_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = 5
    ) -> Optional[GraphPath]:
        """查找路径"""
        pass

    @abstractmethod
    async def get_subgraph(
        self,
        center_id: str,
        radius: int = 1
    ) -> SubGraph:
        """获取子图"""
        pass

    @abstractmethod
    async def delete_entity(self, entity_id: str) -> bool:
        """删除实体"""
        pass

    @abstractmethod
    async def delete_relation(self, relation_id: str) -> bool:
        """删除关系"""
        pass

    @abstractmethod
    async def clear(self) -> bool:
        """清空图谱"""
        pass


# =============================================================================
# Neo4j 图数据库实现
# =============================================================================

class Neo4jDatabase(GraphDatabase):
    """Neo4j 图数据库实现"""

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        user: str = "neo4j",
        password: str = "password",
        database: str = "neo4j"
    ):
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self._driver = None
        self._connected = False

    async def connect(self) -> bool:
        """连接 Neo4j 数据库"""
        try:
            from neo4j import AsyncGraphDatabase
            self._driver = AsyncGraphDatabase.driver(
                self.uri,
                auth=(self.user, self.password)
            )
            # 验证连接
            await self._driver.verify_connectivity()
            self._connected = True
            logger.info(f"Connected to Neo4j at {self.uri}")
            return True
        except ImportError:
            logger.warning("neo4j package not installed, using mock connection")
            self._connected = True
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")
            self._connected = False
            return False

    async def disconnect(self) -> bool:
        """断开连接"""
        try:
            if self._driver:
                await self._driver.close()
            self._connected = False
            logger.info("Disconnected from Neo4j")
            return True
        except Exception as e:
            logger.error(f"Failed to disconnect from Neo4j: {e}")
            return False

    async def is_connected(self) -> bool:
        """检查连接状态"""
        return self._connected

    async def add_entity(self, entity: Entity) -> bool:
        """添加实体"""
        if not self._connected:
            logger.error("Not connected to Neo4j")
            return False

        try:
            if self._driver:
                async with self._driver.session(database=self._database) as session:
                    query = """
                    MERGE (e:Entity {id: $id})
                    SET e.name = $name,
                        e.entity_type = $entity_type,
                        e.description = $description,
                        e.aliases = $aliases,
                        e += $properties
                    """
                    await session.run(
                        query,
                        id=entity.id,
                        name=entity.name,
                        entity_type=entity.entity_type.value,
                        description=entity.description,
                        aliases=entity.aliases,
                        properties=entity.properties
                    )
            logger.info(f"Added entity: {entity.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to add entity: {e}")
            return False

    async def add_relation(self, relation: Relation) -> bool:
        """添加关系"""
        if not self._connected:
            logger.error("Not connected to Neo4j")
            return False

        try:
            if self._driver:
                async with self._driver.session(database=self._database) as session:
                    query = """
                    MATCH (source:Entity {id: $source_id})
                    MATCH (target:Entity {id: $target_id})
                    MERGE (source)-[r:RELATION {id: $id}]->(target)
                    SET r.relation_type = $relation_type,
                        r.weight = $weight,
                        r.description = $description,
                        r += $properties
                    """
                    await session.run(
                        query,
                        id=relation.id,
                        source_id=relation.source_id,
                        target_id=relation.target_id,
                        relation_type=relation.relation_type.value,
                        weight=relation.weight,
                        description=relation.description,
                        properties=relation.properties
                    )
            logger.info(f"Added relation: {relation.id}")
            return True
        except Exception as e:
            logger.error(f"Failed to add relation: {e}")
            return False

    async def get_entity(self, entity_id: str) -> Optional[Entity]:
        """获取实体"""
        if not self._connected:
            return None

        try:
            if self._driver:
                async with self._driver.session(database=self._database) as session:
                    query = """
                    MATCH (e:Entity {id: $id})
                    RETURN e
                    """
                    result = await session.run(query, id=entity_id)
                    record = await result.single()
                    if record:
                        node = record["e"]
                        return Entity(
                            id=node["id"],
                            name=node["name"],
                            entity_type=EntityType(node["entity_type"]),
                            properties=dict(node),
                            description=node.get("description", ""),
                            aliases=node.get("aliases", [])
                        )
            return None
        except Exception as e:
            logger.error(f"Failed to get entity: {e}")
            return None

    async def get_relation(self, relation_id: str) -> Optional[Relation]:
        """获取关系"""
        if not self._connected:
            return None

        try:
            if self._driver:
                async with self._driver.session(database=self._database) as session:
                    query = """
                    MATCH ()-[r:RELATION {id: $id}]->()
                    RETURN r, startNode(r) as source, endNode(r) as target
                    """
                    result = await session.run(query, id=relation_id)
                    record = await result.single()
                    if record:
                        rel = record["r"]
                        return Relation(
                            id=rel["id"],
                            source_id=record["source"]["id"],
                            target_id=record["target"]["id"],
                            relation_type=RelationType(rel["relation_type"]),
                            properties=dict(rel),
                            weight=rel.get("weight", 1.0),
                            description=rel.get("description", "")
                        )
            return None
        except Exception as e:
            logger.error(f"Failed to get relation: {e}")
            return None

    async def search_entities(
        self,
        query: str,
        entity_type: Optional[EntityType] = None,
        limit: int = 10
    ) -> List[Entity]:
        """搜索实体"""
        if not self._connected:
            return []

        try:
            if self._driver:
                async with self._driver.session(database=self._database) as session:
                    if entity_type:
                        cypher_query = """
                        MATCH (e:Entity)
                        WHERE e.entity_type = $entity_type
                          AND (e.name CONTAINS $query OR e.description CONTAINS $query)
                        RETURN e
                        LIMIT $limit
                        """
                        result = await session.run(
                            cypher_query,
                            query=query,
                            entity_type=entity_type.value,
                            limit=limit
                        )
                    else:
                        cypher_query = """
                        MATCH (e:Entity)
                        WHERE e.name CONTAINS $query OR e.description CONTAINS $query
                        RETURN e
                        LIMIT $limit
                        """
                        result = await session.run(
                            cypher_query,
                            query=query,
                            limit=limit
                        )

                    entities = []
                    async for record in result:
                        node = record["e"]
                        entities.append(Entity(
                            id=node["id"],
                            name=node["name"],
                            entity_type=EntityType(node["entity_type"]),
                            properties=dict(node),
                            description=node.get("description", ""),
                            aliases=node.get("aliases", [])
                        ))
                    return entities
            return []
        except Exception as e:
            logger.error(f"Failed to search entities: {e}")
            return []

    async def search_relations(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        relation_type: Optional[RelationType] = None,
        limit: int = 10
    ) -> List[Relation]:
        """搜索关系"""
        if not self._connected:
            return []

        try:
            if self._driver:
                async with self._driver.session(database=self._database) as session:
                    conditions = []
                    params = {"limit": limit}

                    if source_id:
                        conditions.append("source.id = $source_id")
                        params["source_id"] = source_id
                    if target_id:
                        conditions.append("target.id = $target_id")
                        params["target_id"] = target_id
                    if relation_type:
                        conditions.append("r.relation_type = $relation_type")
                        params["relation_type"] = relation_type.value

                    where_clause = " AND ".join(conditions) if conditions else "true"

                    cypher_query = f"""
                    MATCH (source:Entity)-[r:RELATION]->(target:Entity)
                    WHERE {where_clause}
                    RETURN r, source, target
                    LIMIT $limit
                    """

                    result = await session.run(cypher_query, **params)
                    relations = []
                    async for record in result:
                        rel = record["r"]
                        relations.append(Relation(
                            id=rel["id"],
                            source_id=record["source"]["id"],
                            target_id=record["target"]["id"],
                            relation_type=RelationType(rel["relation_type"]),
                            properties=dict(rel),
                            weight=rel.get("weight", 1.0),
                            description=rel.get("description", "")
                        ))
                    return relations
            return []
        except Exception as e:
            logger.error(f"Failed to search relations: {e}")
            return []

    async def get_neighbors(
        self,
        entity_id: str,
        depth: int = 1,
        relation_types: Optional[List[RelationType]] = None
    ) -> Tuple[List[Entity], List[Relation]]:
        """获取邻居节点"""
        if not self._connected:
            return [], []

        try:
            if self._driver:
                async with self._driver.session(database=self._database) as session:
                    if relation_types:
                        type_list = [rt.value for rt in relation_types]
                        cypher_query = """
                        MATCH (e:Entity {id: $id})-[r:RELATION*1..$depth]-(neighbor:Entity)
                        WHERE ALL(r2 IN r WHERE r2.relation_type IN $relation_types)
                        RETURN DISTINCT neighbor, r
                        """
                        result = await session.run(
                            cypher_query,
                            id=entity_id,
                            depth=depth,
                            relation_types=type_list
                        )
                    else:
                        cypher_query = """
                        MATCH (e:Entity {id: $id})-[r:RELATION*1..$depth]-(neighbor:Entity)
                        RETURN DISTINCT neighbor, r
                        """
                        result = await session.run(
                            cypher_query,
                            id=entity_id,
                            depth=depth
                        )

                    entities = []
                    relations = []
                    async for record in result:
                        node = record["neighbor"]
                        entities.append(Entity(
                            id=node["id"],
                            name=node["name"],
                            entity_type=EntityType(node["entity_type"]),
                            properties=dict(node),
                            description=node.get("description", ""),
                            aliases=node.get("aliases", [])
                        ))

                    return entities, relations
            return [], []
        except Exception as e:
            logger.error(f"Failed to get neighbors: {e}")
            return [], []

    async def find_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = MAX_PATH_DEPTH
    ) -> Optional[GraphPath]:
        """查找路径"""
        if not self._connected:
            return None

        try:
            if self._driver:
                async with self._driver.session(database=self._database) as session:
                    cypher_query = """
                    MATCH path = shortestPath(
                        (source:Entity {id: $source_id})-[*1..$max_depth]-(target:Entity {id: $target_id})
                    )
                    RETURN path
                    """
                    result = await session.run(
                        cypher_query,
                        source_id=source_id,
                        target_id=target_id,
                        max_depth=max_depth
                    )
                    record = await result.single()
                    if record:
                        path = record["path"]
                        nodes = []
                        edges = []
                        for node in path.nodes:
                            nodes.append(GraphNode(
                                entity=Entity(
                                    id=node["id"],
                                    name=node["name"],
                                    entity_type=EntityType(node["entity_type"]),
                                    properties=dict(node),
                                    description=node.get("description", ""),
                                    aliases=node.get("aliases", [])
                                )
                            ))
                        for rel in path.relationships:
                            edges.append(GraphEdge(
                                relation=Relation(
                                    id=rel["id"],
                                    source_id=rel.start_node["id"],
                                    target_id=rel.end_node["id"],
                                    relation_type=RelationType(rel["relation_type"]),
                                    properties=dict(rel),
                                    weight=rel.get("weight", 1.0),
                                    description=rel.get("description", "")
                                )
                            ))
                        return GraphPath(nodes=nodes, edges=edges)
            return None
        except Exception as e:
            logger.error(f"Failed to find path: {type(e).__name__}: {e}")
            return None

    async def get_subgraph(
        self,
        center_id: str,
        radius: int = 1
    ) -> SubGraph:
        """获取子图"""
        if not self._connected:
            return SubGraph(nodes=[], edges=[])

        try:
            if self._driver:
                async with self._driver.session(database=self._database) as session:
                    cypher_query = """
                    MATCH (center:Entity {id: $center_id})-[r:RELATION*1..$radius]-(neighbor:Entity)
                    RETURN DISTINCT center, neighbor, r
                    """
                    result = await session.run(
                        cypher_query,
                        center_id=center_id,
                        radius=radius
                    )

                    nodes_dict = {}
                    edges_dict = []

                    async for record in result:
                        center_node = record["center"]
                        neighbor_node = record["neighbor"]

                        if center_node["id"] not in nodes_dict:
                            nodes_dict[center_node["id"]] = GraphNode(
                                entity=Entity(
                                    id=center_node["id"],
                                    name=center_node["name"],
                                    entity_type=EntityType(center_node["entity_type"]),
                                    properties=dict(center_node),
                                    description=center_node.get("description", ""),
                                    aliases=center_node.get("aliases", [])
                                )
                            )

                        if neighbor_node["id"] not in nodes_dict:
                            nodes_dict[neighbor_node["id"]] = GraphNode(
                                entity=Entity(
                                    id=neighbor_node["id"],
                                    name=neighbor_node["name"],
                                    entity_type=EntityType(neighbor_node["entity_type"]),
                                    properties=dict(neighbor_node),
                                    description=neighbor_node.get("description", ""),
                                    aliases=neighbor_node.get("aliases", [])
                                )
                            )

                    return SubGraph(
                        nodes=list(nodes_dict.values()),
                        edges=edges_dict,
                        center_entity=center_id,
                        radius=radius
                    )
            return SubGraph(nodes=[], edges=[])
        except Exception as e:
            logger.error(f"Failed to get subgraph: {e}")
            return SubGraph(nodes=[], edges=[])

    async def delete_entity(self, entity_id: str) -> bool:
        """删除实体"""
        if not self._connected:
            return False

        try:
            if self._driver:
                async with self._driver.session(database=self._database) as session:
                    query = """
                    MATCH (e:Entity {id: $id})
                    DETACH DELETE e
                    """
                    await session.run(query, id=entity_id)
            logger.info(f"Deleted entity: {entity_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete entity: {e}")
            return False

    async def delete_relation(self, relation_id: str) -> bool:
        """删除关系"""
        if not self._connected:
            return False

        try:
            if self._driver:
                async with self._driver.session(database=self._database) as session:
                    query = """
                    MATCH ()-[r:RELATION {id: $id}]->()
                    DELETE r
                    """
                    await session.run(query, id=relation_id)
            logger.info(f"Deleted relation: {relation_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete relation: {e}")
            return False

    async def clear(self) -> bool:
        """清空图谱"""
        if not self._connected:
            return False

        try:
            if self._driver:
                async with self._driver.session(database=self._database) as session:
                    await session.run("MATCH (n) DETACH DELETE n")
            logger.info("Cleared graph database")
            return True
        except Exception as e:
            logger.error(f"Failed to clear graph: {e}")
            return False


# =============================================================================
# 内存图数据库（用于测试和开发）
# =============================================================================

class InMemoryGraphDatabase(GraphDatabase):
    """内存图数据库（用于测试和开发）"""

    def __init__(self):
        self._entities: Dict[str, Entity] = {}
        self._relations: Dict[str, Relation] = {}
        self._connected = False

    async def connect(self) -> bool:
        """连接"""
        self._connected = True
        logger.info("Connected to in-memory graph database")
        return True

    async def disconnect(self) -> bool:
        """断开连接"""
        self._connected = False
        logger.info("Disconnected from in-memory graph database")
        return True

    async def is_connected(self) -> bool:
        """检查连接状态"""
        return self._connected

    async def add_entity(self, entity: Entity) -> bool:
        """添加实体"""
        self._entities[entity.id] = entity
        return True

    async def add_relation(self, relation: Relation) -> bool:
        """添加关系"""
        self._relations[relation.id] = relation
        return True

    async def get_entity(self, entity_id: str) -> Optional[Entity]:
        """获取实体"""
        return self._entities.get(entity_id)

    async def get_relation(self, relation_id: str) -> Optional[Relation]:
        """获取关系"""
        return self._relations.get(relation_id)

    async def search_entities(
        self,
        query: str,
        entity_type: Optional[EntityType] = None,
        limit: int = 10
    ) -> List[Entity]:
        """搜索实体"""
        results = []
        for entity in self._entities.values():
            if entity_type and entity.entity_type != entity_type:
                continue
            if query.lower() in entity.name.lower() or query.lower() in entity.description.lower():
                results.append(entity)
                if len(results) >= limit:
                    break
        return results

    async def search_relations(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        relation_type: Optional[RelationType] = None,
        limit: int = 10
    ) -> List[Relation]:
        """搜索关系"""
        results = []
        for relation in self._relations.values():
            if source_id and relation.source_id != source_id:
                continue
            if target_id and relation.target_id != target_id:
                continue
            if relation_type and relation.relation_type != relation_type:
                continue
            results.append(relation)
            if len(results) >= limit:
                break
        return results

    async def get_neighbors(
        self,
        entity_id: str,
        depth: int = 1,
        relation_types: Optional[List[RelationType]] = None
    ) -> Tuple[List[Entity], List[Relation]]:
        """获取邻居节点（支持多级遍历）"""
        visited = {entity_id}
        current_level = {entity_id}
        all_neighbors = set()
        all_relations = []

        for _ in range(depth):
            next_level = set()
            for eid in current_level:
                for relation in self._relations.values():
                    if relation_types and relation.relation_type not in relation_types:
                        continue

                    if relation.source_id == eid and relation.target_id not in visited:
                        next_level.add(relation.target_id)
                        all_neighbors.add(relation.target_id)
                        all_relations.append(relation)
                        visited.add(relation.target_id)
                    elif relation.target_id == eid and relation.source_id not in visited:
                        next_level.add(relation.source_id)
                        all_neighbors.add(relation.source_id)
                        all_relations.append(relation)
                        visited.add(relation.source_id)
            current_level = next_level

        entities = [self._entities[eid] for eid in all_neighbors if eid in self._entities]
        return entities, all_relations

    async def find_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = MAX_PATH_DEPTH
    ) -> Optional[GraphPath]:
        """查找路径（BFS）"""
        if source_id not in self._entities or target_id not in self._entities:
            return None

        visited = {source_id}
        # Queue stores (current_entity_id, list_of_relation_ids)
        queue = [(source_id, [])]

        while queue:
            current, path = queue.pop(0)

            if current == target_id:
                # Build node list from path: source -> target via relations
                node_ids = [source_id]
                for rel_id in path:
                    rel = self._relations[rel_id]
                    if rel.source_id == node_ids[-1]:
                        node_ids.append(rel.target_id)
                    else:
                        node_ids.append(rel.source_id)
                nodes = [GraphNode(entity=self._entities[nid]) for nid in node_ids if nid in self._entities]
                edges = [GraphEdge(relation=self._relations[rid]) for rid in path]
                return GraphPath(nodes=nodes, edges=edges)

            if len(path) >= max_depth:
                continue

            for relation in self._relations.values():
                next_id = None
                if relation.source_id == current and relation.target_id not in visited:
                    next_id = relation.target_id
                elif relation.target_id == current and relation.source_id not in visited:
                    next_id = relation.source_id

                if next_id:
                    visited.add(next_id)
                    queue.append((next_id, path + [relation.id]))

        return None

    async def get_subgraph(
        self,
        center_id: str,
        radius: int = 1
    ) -> SubGraph:
        """获取子图"""
        if center_id not in self._entities:
            return SubGraph(nodes=[], edges=[])

        visited = {center_id}
        current_level = {center_id}

        for _ in range(radius):
            next_level = set()
            for eid in current_level:
                for relation in self._relations.values():
                    if relation.source_id == eid and relation.target_id not in visited:
                        next_level.add(relation.target_id)
                        visited.add(relation.target_id)
                    elif relation.target_id == eid and relation.source_id not in visited:
                        next_level.add(relation.source_id)
                        visited.add(relation.source_id)
            current_level = next_level

        nodes = [GraphNode(entity=self._entities[eid]) for eid in visited if eid in self._entities]
        edges = [
            GraphEdge(relation=rel)
            for rel in self._relations.values()
            if rel.source_id in visited and rel.target_id in visited
        ]

        return SubGraph(nodes=nodes, edges=edges, center_entity=center_id, radius=radius)

    async def delete_entity(self, entity_id: str) -> bool:
        """删除实体"""
        if entity_id in self._entities:
            del self._entities[entity_id]
            # 删除相关关系
            to_delete = [
                rid for rid, rel in self._relations.items()
                if rel.source_id == entity_id or rel.target_id == entity_id
            ]
            for rid in to_delete:
                del self._relations[rid]
            return True
        return False

    async def delete_relation(self, relation_id: str) -> bool:
        """删除关系"""
        if relation_id in self._relations:
            del self._relations[relation_id]
            return True
        return False

    async def clear(self) -> bool:
        """清空图谱"""
        self._entities.clear()
        self._relations.clear()
        return True


# =============================================================================
# 知识图谱管理器
# =============================================================================

class KnowledgeGraphManager:
    """知识图谱管理器"""

    def __init__(self, database: Optional[GraphDatabase] = None):
        self.database = database or InMemoryGraphDatabase()
        self._initialized = False

    async def initialize(self) -> bool:
        """初始化图谱"""
        if self._initialized:
            return True

        success = await self.database.connect()
        if success:
            self._initialized = True
            logger.info("Knowledge graph initialized")
        return success

    async def shutdown(self) -> bool:
        """关闭图谱"""
        if not self._initialized:
            return True

        success = await self.database.disconnect()
        if success:
            self._initialized = False
            logger.info("Knowledge graph shutdown")
        return success

    async def add_entity(self, entity: Entity) -> bool:
        """添加实体"""
        return await self.database.add_entity(entity)

    async def add_relation(self, relation: Relation) -> bool:
        """添加关系"""
        return await self.database.add_relation(relation)

    async def get_entity(self, entity_id: str) -> Optional[Entity]:
        """获取实体"""
        return await self.database.get_entity(entity_id)

    async def get_relation(self, relation_id: str) -> Optional[Relation]:
        """获取关系"""
        return await self.database.get_relation(relation_id)

    async def search_entities(
        self,
        query: str,
        entity_type: Optional[EntityType] = None,
        limit: int = 10
    ) -> List[Entity]:
        """搜索实体"""
        return await self.database.search_entities(query, entity_type, limit)

    async def search_relations(
        self,
        source_id: Optional[str] = None,
        target_id: Optional[str] = None,
        relation_type: Optional[RelationType] = None,
        limit: int = 10
    ) -> List[Relation]:
        """搜索关系"""
        return await self.database.search_relations(source_id, target_id, relation_type, limit)

    async def get_neighbors(
        self,
        entity_id: str,
        depth: int = 1,
        relation_types: Optional[List[RelationType]] = None
    ) -> Tuple[List[Entity], List[Relation]]:
        """获取邻居节点"""
        return await self.database.get_neighbors(entity_id, depth, relation_types)

    async def find_path(
        self,
        source_id: str,
        target_id: str,
        max_depth: int = MAX_PATH_DEPTH
    ) -> Optional[GraphPath]:
        """查找路径"""
        return await self.database.find_path(source_id, target_id, max_depth)

    async def get_subgraph(
        self,
        center_id: str,
        radius: int = 1
    ) -> SubGraph:
        """获取子图"""
        return await self.database.get_subgraph(center_id, radius)

    async def delete_entity(self, entity_id: str) -> bool:
        """删除实体"""
        return await self.database.delete_entity(entity_id)

    async def delete_relation(self, relation_id: str) -> bool:
        """删除关系"""
        return await self.database.delete_relation(relation_id)

    async def clear(self) -> bool:
        """清空图谱"""
        return await self.database.clear()

    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            "initialized": self._initialized,
            "database_type": type(self.database).__name__
        }


# =============================================================================
# 图谱构建器
# =============================================================================

class GraphBuilder:
    """知识图谱构建器"""

    def __init__(self, manager: KnowledgeGraphManager):
        self.manager = manager
        self._entities: List[Entity] = []
        self._relations: List[Relation] = []

    def add_entity(
        self,
        id: str,
        name: str,
        entity_type: EntityType = EntityType.OTHER,
        properties: Optional[Dict[str, Any]] = None,
        description: str = "",
        aliases: Optional[List[str]] = None
    ) -> "GraphBuilder":
        """添加实体（链式调用）"""
        entity = Entity(
            id=id,
            name=name,
            entity_type=entity_type,
            properties=properties or {},
            description=description,
            aliases=aliases or []
        )
        self._entities.append(entity)
        return self

    def add_relation(
        self,
        id: str,
        source_id: str,
        target_id: str,
        relation_type: RelationType = RelationType.RELATED_TO,
        properties: Optional[Dict[str, Any]] = None,
        weight: float = 1.0,
        description: str = ""
    ) -> "GraphBuilder":
        """添加关系（链式调用）"""
        relation = Relation(
            id=id,
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            properties=properties or {},
            weight=weight,
            description=description
        )
        self._relations.append(relation)
        return self

    async def build(self) -> bool:
        """构建图谱"""
        try:
            # 添加实体
            for entity in self._entities:
                success = await self.manager.add_entity(entity)
                if not success:
                    logger.error(f"Failed to add entity: {entity.id}")
                    return False

            # 添加关系
            for relation in self._relations:
                success = await self.manager.add_relation(relation)
                if not success:
                    logger.error(f"Failed to add relation: {relation.id}")
                    return False

            logger.info(f"Built graph with {len(self._entities)} entities and {len(self._relations)} relations")
            return True
        except Exception as e:
            logger.error(f"Failed to build graph: {e}")
            return False

    def clear(self) -> "GraphBuilder":
        """清空构建器"""
        self._entities.clear()
        self._relations.clear()
        return self


# =============================================================================
# 工厂类
# =============================================================================

class KnowledgeGraphFactory:
    """KnowledgeGraph 工厂类"""

    @staticmethod
    def create_neo4j_manager(
        uri: str = "bolt://localhost:7687",
        user: str = "neo4j",
        password: str = "password",
        database: str = "neo4j"
    ) -> KnowledgeGraphManager:
        """创建 Neo4j 图谱管理器"""
        db = Neo4jDatabase(uri=uri, user=user, password=password, database=database)
        return KnowledgeGraphManager(database=db)

    @staticmethod
    def create_in_memory_manager() -> KnowledgeGraphManager:
        """创建内存图谱管理器"""
        db = InMemoryGraphDatabase()
        return KnowledgeGraphManager(database=db)

    @staticmethod
    def create_builder(manager: KnowledgeGraphManager) -> GraphBuilder:
        """创建图谱构建器"""
        return GraphBuilder(manager)


# =============================================================================
# 全局实例
# =============================================================================

_global_manager: Optional[KnowledgeGraphManager] = None


def get_knowledge_graph_manager() -> KnowledgeGraphManager:
    """获取全局 KnowledgeGraphManager 实例"""
    global _global_manager
    if _global_manager is None:
        _global_manager = KnowledgeGraphFactory.create_in_memory_manager()
    return _global_manager


def reset_knowledge_graph_manager():
    """重置全局 KnowledgeGraphManager 实例"""
    global _global_manager
    _global_manager = None
