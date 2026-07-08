"""
Causal Reasoning for Jarvis OS - Phase 2 Component
Cause-effect analysis and causal inference
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


class CausalRelation(Enum):
    """Types of causal relations"""
    DIRECT = "direct"
    INDIRECT = "indirect"
    CONTRIBUTING = "contributing"
    NECESSARY = "necessary"
    SUFFICIENT = "sufficient"
    NECESSARY_SUFFICIENT = "necessary_sufficient"


class CausalStrength(Enum):
    """Strength of causal relationship"""
    WEAK = 0.3
    MODERATE = 0.5
    STRONG = 0.7
    VERY_STRONG = 0.9


@dataclass
class CausalNode:
    """A node in the causal graph"""
    id: str
    label: str
    node_type: str
    properties: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "node_type": self.node_type,
            "properties": self.properties
        }


@dataclass
class CausalEdge:
    """An edge in the causal graph"""
    id: str
    source: str
    target: str
    relation: CausalRelation
    strength: float
    confidence: float = 1.0
    evidence: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "relation": self.relation.value,
            "strength": self.strength,
            "confidence": self.confidence,
            "evidence": self.evidence
        }


@dataclass
class CausalChain:
    """A chain of causal relationships"""
    nodes: List[CausalNode]
    edges: List[CausalEdge]
    total_strength: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": [e.to_dict() for e in self.edges],
            "total_strength": self.total_strength,
            "length": len(self.nodes)
        }


class CausalReasoner:
    """Causal reasoning system for cause-effect analysis"""
    
    def __init__(self):
        self.nodes: Dict[str, CausalNode] = {}
        self.edges: Dict[str, CausalEdge] = {}
        self.adjacency_list: Dict[str, Dict[str, CausalEdge]] = defaultdict(dict)
        self.node_counter = 0
        self.edge_counter = 0
        
        logger.info("Causal reasoner initialized")
    
    def add_node(self, label: str, node_type: str, properties: Dict[str, Any] = None,
                node_id: str = None) -> CausalNode:
        """Add a node to the causal graph"""
        if node_id is None:
            self.node_counter += 1
            node_id = f"cause_{self.node_counter}"
        
        node = CausalNode(
            id=node_id,
            label=label,
            node_type=node_type,
            properties=properties or {}
        )
        
        self.nodes[node_id] = node
        logger.debug(f"Added causal node: {node_id} ({label})")
        return node
    
    def add_edge(self, source_id: str, target_id: str, relation: CausalRelation,
                strength: float, confidence: float = 1.0, evidence: List[str] = None,
                edge_id: str = None) -> CausalEdge:
        """Add a causal edge"""
        if source_id not in self.nodes:
            raise ValueError(f"Source node {source_id} not found")
        if target_id not in self.nodes:
            raise ValueError(f"Target node {target_id} not found")
        
        if edge_id is None:
            self.edge_counter += 1
            edge_id = f"edge_{self.edge_counter}"
        
        edge = CausalEdge(
            id=edge_id,
            source=source_id,
            target=target_id,
            relation=relation,
            strength=strength,
            confidence=confidence,
            evidence=evidence or []
        )
        
        self.edges[edge_id] = edge
        self.adjacency_list[source_id][target_id] = edge
        
        logger.debug(f"Added causal edge: {edge_id} ({source_id} -> {target_id})")
        return edge
    
    def find_causes(self, effect_id: str, max_depth: int = 3) -> List[CausalChain]:
        """Find all causal chains leading to an effect"""
        if effect_id not in self.nodes:
            return []
        
        chains = []
        
        def dfs(current_id, path_nodes, path_edges, visited):
            if len(path_nodes) > max_depth + 1:
                return
            
            if len(path_nodes) > 1:
                # Calculate total strength
                total_strength = 1.0
                for edge in path_edges:
                    total_strength *= edge.strength
                
                chain = CausalChain(
                    nodes=path_nodes.copy(),
                    edges=path_edges.copy(),
                    total_strength=total_strength
                )
                chains.append(chain)
            
            # Find causes (nodes that point to current node)
            for source_id, edges in self.adjacency_list.items():
                for target_id, edge in edges.items():
                    if edge.target == current_id:
                        if source_id not in visited:
                            visited.add(source_id)
                            path_nodes.append(self.nodes[source_id])
                            path_edges.append(edge)
                            dfs(source_id, path_nodes, path_edges, visited)
                            path_nodes.pop()
                            path_edges.pop()
                            visited.remove(source_id)
        
        dfs(effect_id, [self.nodes[effect_id]], [], {effect_id})
        
        # Sort by strength
        chains.sort(key=lambda c: c.total_strength, reverse=True)
        return chains
    
    def find_effects(self, cause_id: str, max_depth: int = 3) -> List[CausalChain]:
        """Find all effects of a cause"""
        if cause_id not in self.nodes:
            return []
        
        chains = []
        
        def dfs(current_id, path_nodes, path_edges, visited):
            if len(path_nodes) > max_depth + 1:
                return
            
            if len(path_nodes) > 1:
                total_strength = 1.0
                for edge in path_edges:
                    total_strength *= edge.strength
                
                chain = CausalChain(
                    nodes=path_nodes.copy(),
                    edges=path_edges.copy(),
                    total_strength=total_strength
                )
                chains.append(chain)
            
            # Find effects (nodes that current node points to)
            for target_id, edge in self.adjacency_list[current_id].items():
                if target_id not in visited:
                    visited.add(target_id)
                    path_nodes.append(self.nodes[target_id])
                    path_edges.append(edge)
                    dfs(target_id, path_nodes, path_edges, visited)
                    path_nodes.pop()
                    path_edges.pop()
                    visited.remove(target_id)
        
        dfs(cause_id, [self.nodes[cause_id]], [], {cause_id})
        
        chains.sort(key=lambda c: c.total_strength, reverse=True)
        return chains
    
    def infer_causality(self, events: List[Dict[str, Any]]) -> List[Tuple[str, str, float]]:
        """Infer causal relationships from event sequence"""
        inferred = []
        
        # Simple temporal inference
        for i in range(len(events) - 1):
            event1 = events[i]
            event2 = events[i + 1]
            
            # Check if event1 could cause event2
            if self._could_be_cause(event1, event2):
                strength = self._calculate_inference_strength(event1, event2)
                inferred.append((event1.get("id", f"event_{i}"), 
                              event2.get("id", f"event_{i+1}"), 
                              strength))
        
        return inferred
    
    def _could_be_cause(self, event1: Dict[str, Any], event2: Dict[str, Any]) -> bool:
        """Check if event1 could cause event2"""
        # Simple heuristic: temporal precedence
        time1 = event1.get("timestamp", 0)
        time2 = event2.get("timestamp", 0)
        
        if time1 >= time2:
            return False
        
        # Check for semantic similarity
        type1 = event1.get("type", "")
        type2 = event2.get("type", "")
        
        # Certain types are more likely to be causally related
        causal_pairs = [
            ("error", "fix"),
            ("request", "response"),
            ("start", "complete"),
            ("create", "modify")
        ]
        
        for pair in causal_pairs:
            if type1 == pair[0] and type2 == pair[1]:
                return True
        
        return True  # Default to possible
    def _calculate_inference_strength(self, event1: Dict[str, Any], event2: Dict[str, Any]) -> float:
        """Calculate strength of causal inference"""
        strength = 0.5  # Base strength
        
        # Temporal proximity
        time1 = event1.get("timestamp", 0)
        time2 = event2.get("timestamp", 0)
        time_diff = abs(time2 - time1)
        
        if time_diff < 1.0:  # Within 1 second
            strength += 0.3
        elif time_diff < 10.0:  # Within 10 seconds
            strength += 0.1
        
        # Type relationship
        type1 = event1.get("type", "")
        type2 = event2.get("type", "")
        
        if type1 == type2:
            strength += 0.1
        
        return min(strength, 1.0)
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get causal reasoning statistics"""
        relation_counts = defaultdict(int)
        
        for edge in self.edges.values():
            relation_counts[edge.relation.value] += 1
        
        return {
            "total_nodes": len(self.nodes),
            "total_edges": len(self.edges),
            "relation_distribution": dict(relation_counts),
            "average_strength": (
                sum(e.strength for e in self.edges.values()) / len(self.edges)
                if self.edges else 0.0
            )
        }
    
    async def health_check(self) -> str:
        """Health check for the causal reasoner"""
        stats = self.get_statistics()
        return f"healthy ({stats['total_nodes']} nodes, {stats['total_edges']} edges)"
    
    async def shutdown(self):
        """Shutdown the causal reasoner"""
        logger.info("Causal reasoner shutting down")
