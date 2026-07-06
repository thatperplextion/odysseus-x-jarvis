"""
Knowledge Graph for Jarvis OS - Phase 2 Component
Graph-based knowledge representation and reasoning
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


class RelationType(Enum):
    """Types of relations in the knowledge graph"""
    IS_A = "is_a"
    PART_OF = "part_of"
    RELATED_TO = "related_to"
    CAUSES = "causes"
    CAUSED_BY = "caused_by"
    CONTAINS = "contains"
    CONTAINED_IN = "contained_in"
    SIMILAR_TO = "similar_to"
    OPPOSITE_OF = "opposite_of"
    DEPENDS_ON = "depends_on"
    REQUIRED_FOR = "required_for"
    IMPLEMENTED_BY = "implemented_by"
    IMPLEMENTS = "implements"
    CUSTOM = "custom"


class NodeType(Enum):
    """Types of nodes in the knowledge graph"""
    CONCEPT = "concept"
    ENTITY = "entity"
    EVENT = "event"
    ATTRIBUTE = "attribute"
    VALUE = "value"
    ACTION = "action"
    CUSTOM = "custom"


@dataclass
class Node:
    """A node in the knowledge graph"""
    id: str
    label: str
    node_type: NodeType
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "node_type": self.node_type.value,
            "properties": self.properties,
            "created_at": self.created_at.isoformat()
        }


@dataclass
class Edge:
    """An edge in the knowledge graph"""
    id: str
    source: str
    target: str
    relation_type: RelationType
    weight: float = 1.0
    properties: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "relation_type": self.relation_type.value,
            "weight": self.weight,
            "properties": self.properties,
            "created_at": self.created_at.isoformat()
        }


@dataclass
class Path:
    """A path through the knowledge graph"""
    nodes: List[Node]
    edges: List[Edge]
    total_weight: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "total_weight": self.total_weight,
            "length": len(self.nodes)
        }


class KnowledgeGraph:
    """Knowledge graph for structured knowledge representation"""
    
    def __init__(self):
        self.nodes: Dict[str, Node] = {}
        self.edges: Dict[str, Edge] = {}
        self.adjacency_list: Dict[str, Dict[str, Edge]] = defaultdict(dict)
        self.node_counter = 0
        self.edge_counter = 0
        
        logger.info("Knowledge graph initialized")
    
    def add_node(self, label: str, node_type: NodeType, 
                properties: Dict[str, Any] = None, node_id: str = None) -> Node:
        """Add a node to the graph"""
        if node_id is None:
            self.node_counter += 1
            node_id = f"node_{self.node_counter}"
        
        node = Node(
            id=node_id,
            label=label,
            node_type=node_type,
            properties=properties or {}
        )
        
        self.nodes[node_id] = node
        logger.debug(f"Added node: {node_id} ({label})")
        return node
    
    def add_edge(self, source_id: str, target_id: str, relation_type: RelationType,
                weight: float = 1.0, properties: Dict[str, Any] = None, edge_id: str = None) -> Edge:
        """Add an edge to the graph"""
        if source_id not in self.nodes:
            raise ValueError(f"Source node {source_id} not found")
        if target_id not in self.nodes:
            raise ValueError(f"Target node {target_id} not found")
        
        if edge_id is None:
            self.edge_counter += 1
            edge_id = f"edge_{self.edge_counter}"
        
        edge = Edge(
            id=edge_id,
            source=source_id,
            target=target_id,
            relation_type=relation_type,
            weight=weight,
            properties=properties or {}
        )
        
        self.edges[edge_id] = edge
        self.adjacency_list[source_id][target_id] = edge
        
        logger.debug(f"Added edge: {edge_id} ({source_id} -> {target_id})")
        return edge
    
    def get_node(self, node_id: str) -> Optional[Node]:
        """Get a node by ID"""
        return self.nodes.get(node_id)
    
    def get_edge(self, edge_id: str) -> Optional[Edge]:
        """Get an edge by ID"""
        return self.edges.get(edge_id)
    
    def get_neighbors(self, node_id: str, relation_type: RelationType = None) -> List[Node]:
        """Get neighbors of a node"""
        if node_id not in self.adjacency_list:
            return []
        
        neighbors = []
        for target_id, edge in self.adjacency_list[node_id].items():
            if relation_type is None or edge.relation_type == relation_type:
                neighbors.append(self.nodes[target_id])
        
        return neighbors
    
    def find_path(self, source_id: str, target_id: str, 
                 max_depth: int = 5) -> Optional[Path]:
        """Find a path between two nodes using BFS"""
        if source_id not in self.nodes or target_id not in self.nodes:
            return None
        
        if source_id == target_id:
            return Path(nodes=[self.nodes[source_id]], edges=[])
        
        # BFS
        queue = [(source_id, [self.nodes[source_id]], [])]
        visited = {source_id}
        
        while queue:
            current_id, path_nodes, path_edges = queue.pop(0)
            
            if len(path_nodes) > max_depth:
                continue
            
            for neighbor_id, edge in self.adjacency_list[current_id].items():
                if neighbor_id == target_id:
                    # Found path
                    return Path(
                        nodes=path_nodes + [self.nodes[neighbor_id]],
                        edges=path_edges + [edge],
                        total_weight=sum(e.weight for e in path_edges + [edge])
                    )
                
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    queue.append((
                        neighbor_id,
                        path_nodes + [self.nodes[neighbor_id]],
                        path_edges + [edge]
                    ))
        
        return None
    
    def find_shortest_path(self, source_id: str, target_id: str) -> Optional[Path]:
        """Find the shortest path between two nodes"""
        return self.find_path(source_id, target_id, max_depth=10)
    
    def find_all_paths(self, source_id: str, target_id: str,
                      max_depth: int = 5) -> List[Path]:
        """Find all paths between two nodes using DFS"""
        if source_id not in self.nodes or target_id not in self.nodes:
            return []
        
        paths = []
        
        def dfs(current_id, path_nodes, path_edges, visited):
            if len(path_nodes) > max_depth:
                return
            
            if current_id == target_id:
                paths.append(Path(
                    nodes=path_nodes.copy(),
                    edges=path_edges.copy(),
                    total_weight=sum(e.weight for e in path_edges)
                ))
                return
            
            for neighbor_id, edge in self.adjacency_list[current_id].items():
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    path_nodes.append(self.nodes[neighbor_id])
                    path_edges.append(edge)
                    dfs(neighbor_id, path_nodes, path_edges, visited)
                    path_nodes.pop()
                    path_edges.pop()
                    visited.remove(neighbor_id)
        
        dfs(source_id, [self.nodes[source_id]], [], {source_id})
        return paths
    
    def query_nodes(self, node_type: NodeType = None, 
                   properties: Dict[str, Any] = None) -> List[Node]:
        """Query nodes by type and/or properties"""
        results = []
        
        for node in self.nodes.values():
            # Filter by type
            if node_type and node.node_type != node_type:
                continue
            
            # Filter by properties
            if properties:
                match = True
                for key, value in properties.items():
                    if key not in node.properties or node.properties[key] != value:
                        match = False
                        break
                if not match:
                    continue
            
            results.append(node)
        
        return results
    
    def query_edges(self, relation_type: RelationType = None,
                   source_id: str = None, target_id: str = None) -> List[Edge]:
        """Query edges by relation type and/or endpoints"""
        results = []
        
        for edge in self.edges.values():
            # Filter by relation type
            if relation_type and edge.relation_type != relation_type:
                continue
            
            # Filter by source
            if source_id and edge.source != source_id:
                continue
            
            # Filter by target
            if target_id and edge.target != target_id:
                continue
            
            results.append(edge)
        
        return results
    
    def get_subgraph(self, node_ids: Set[str]) -> 'KnowledgeGraph':
        """Extract a subgraph containing specified nodes"""
        subgraph = KnowledgeGraph()
        
        # Add nodes
        for node_id in node_ids:
            if node_id in self.nodes:
                node = self.nodes[node_id]
                subgraph.add_node(
                    label=node.label,
                    node_type=node.node_type,
                    properties=node.properties,
                    node_id=node.id
                )
        
        # Add edges between nodes in subgraph
        for edge in self.edges.values():
            if edge.source in node_ids and edge.target in node_ids:
                subgraph.add_edge(
                    source_id=edge.source,
                    target_id=edge.target,
                    relation_type=edge.relation_type,
                    weight=edge.weight,
                    properties=edge.properties,
                    edge_id=edge.id
                )
        
        return subgraph
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get graph statistics"""
        node_type_counts = defaultdict(int)
        relation_type_counts = defaultdict(int)
        
        for node in self.nodes.values():
            node_type_counts[node.node_type.value] += 1
        
        for edge in self.edges.values():
            relation_type_counts[edge.relation_type.value] += 1
        
        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "node_type_distribution": dict(node_type_counts),
            "relation_type_distribution": dict(relation_type_counts),
            "average_degree": sum(len(neighbors) for neighbors in self.adjacency_list.values()) / max(len(self.nodes), 1)
        }
    
    async def health_check(self) -> str:
        """Health check for the knowledge graph"""
        stats = self.get_statistics()
        return f"healthy ({stats['total_nodes']} nodes, {stats['total_edges']} edges)"
    
    async def shutdown(self):
        """Shutdown the knowledge graph"""
        logger.info("Knowledge graph shutting down")
