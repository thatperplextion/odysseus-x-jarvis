"""
Enhanced Memory System for Jarvis OS - Phase 1 Component
Advanced memory with episodic memory, semantic memory, consolidation, and forgetting
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Tuple
from collections import defaultdict
import json
import pickle
from pathlib import Path

logger = logging.getLogger(__name__)


class MemoryType(Enum):
    """Types of memory"""
    EPISODIC = "episodic"  # Specific experiences/events
    SEMANTIC = "semantic"  # General knowledge/facts
    WORKING = "working"  # Short-term/active memory
    PROCEDURAL = "procedural"  # Skills/procedures


class MemoryImportance(Enum):
    """Importance levels for memory"""
    CRITICAL = 0
    HIGH = 1
    MEDIUM = 2
    LOW = 3
    TRIVIAL = 4


@dataclass
class Memory:
    """A single memory entry"""
    id: str
    content: str
    memory_type: MemoryType
    importance: MemoryImportance = MemoryImportance.MEDIUM
    created_at: datetime = field(default_factory=datetime.now)
    last_accessed: datetime = field(default_factory=datetime.now)
    access_count: int = 0
    embedding: Optional[List[float]] = None
    tags: Set[str] = field(default_factory=set)
    related_memories: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    consolidation_level: float = 0.0  # 0.0 to 1.0
    forgetting_score: float = 0.0  # 0.0 to 1.0, higher = more likely to forget
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type.value,
            "importance": self.importance.value,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "access_count": self.access_count,
            "embedding": self.embedding,
            "tags": list(self.tags),
            "related_memories": list(self.related_memories),
            "metadata": self.metadata,
            "consolidation_level": self.consolidation_level,
            "forgetting_score": self.forgetting_score
        }


@dataclass
class Reflection:
    """A reflection on past experiences"""
    id: str
    memory_id: str
    reflection_type: str  # "success", "failure", "pattern", "insight"
    content: str
    confidence: float
    created_at: datetime = field(default_factory=datetime.now)
    actionable: bool = False
    action_suggestions: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "memory_id": self.memory_id,
            "reflection_type": self.reflection_type,
            "content": self.content,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "actionable": self.actionable,
            "action_suggestions": self.action_suggestions
        }


class EnhancedMemory:
    """Enhanced memory system with episodic and semantic memory"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.memory_file = data_dir / "enhanced_memory.pkl"
        self.reflection_file = data_dir / "reflections.pkl"
        
        self.memories: Dict[str, Memory] = {}
        self.reflections: Dict[str, Reflection] = {}
        self.memory_counter = 0
        self.reflection_counter = 0
        
        # Memory indexes
        self.tag_index: Dict[str, Set[str]] = defaultdict(set)
        self.type_index: Dict[MemoryType, Set[str]] = defaultdict(set)
        self.importance_index: Dict[MemoryImportance, Set[str]] = defaultdict(set)
        
        # Working memory (short-term)
        self.working_memory: List[str] = []
        self.working_memory_capacity = 7  # Miller's number
        
        # Consolidation parameters
        self.consolidation_threshold = 0.7
        self.consolidation_interval = timedelta(hours=1)
        self.last_consolidation = datetime.now()
        
        # Forgetting parameters
        self.forgetting_rate = 0.01  # Base forgetting rate
        self.importance_protection = 0.5  # Importance reduces forgetting
        
        logger.info("Enhanced Memory system initialized")
    
    async def initialize(self):
        """Load existing memories from disk"""
        if self.memory_file.exists():
            try:
                with open(self.memory_file, 'rb') as f:
                    data = pickle.load(f)
                    self.memories = {k: Memory(**v) if isinstance(v, dict) else v for k, v in data.items()}
                self._rebuild_indexes()
                logger.info(f"Loaded {len(self.memories)} memories from disk")
            except Exception as e:
                logger.error(f"Failed to load memories: {e}")
        
        if self.reflection_file.exists():
            try:
                with open(self.reflection_file, 'rb') as f:
                    self.reflections = pickle.load(f)
                logger.info(f"Loaded {len(self.reflections)} reflections from disk")
            except Exception as e:
                logger.error(f"Failed to load reflections: {e}")
    
    def _rebuild_indexes(self):
        """Rebuild memory indexes"""
        self.tag_index.clear()
        self.type_index.clear()
        self.importance_index.clear()
        
        for memory_id, memory in self.memories.items():
            for tag in memory.tags:
                self.tag_index[tag].add(memory_id)
            self.type_index[memory.memory_type].add(memory_id)
            self.importance_index[memory.importance].add(memory_id)
    
    def add_memory(self, content: str, memory_type: MemoryType,
                   importance: MemoryImportance = MemoryImportance.MEDIUM,
                   tags: Set[str] = None, metadata: Dict[str, Any] = None) -> Memory:
        """Add a new memory"""
        self.memory_counter += 1
        memory = Memory(
            id=f"mem_{self.memory_counter}",
            content=content,
            memory_type=memory_type,
            importance=importance,
            tags=tags or set(),
            metadata=metadata or {}
        )
        
        self.memories[memory.id] = memory
        
        # Update indexes
        for tag in memory.tags:
            self.tag_index[tag].add(memory.id)
        self.type_index[memory_type].add(memory.id)
        self.importance_index[importance].add(memory.id)
        
        # Add to working memory if episodic
        if memory_type == MemoryType.EPISODIC:
            self._add_to_working_memory(memory.id)
        
        logger.info(f"Added memory {memory.id}: {content[:50]}...")
        return memory
    
    def _add_to_working_memory(self, memory_id: str):
        """Add memory to working memory"""
        if memory_id in self.working_memory:
            self.working_memory.remove(memory_id)
        self.working_memory.insert(0, memory_id)
        
        # Maintain capacity
        if len(self.working_memory) > self.working_memory_capacity:
            removed = self.working_memory.pop()
            logger.debug(f"Removed {removed} from working memory")
    
    def get_memory(self, memory_id: str) -> Optional[Memory]:
        """Retrieve a memory by ID"""
        memory = self.memories.get(memory_id)
        if memory:
            memory.last_accessed = datetime.now()
            memory.access_count += 1
            self._add_to_working_memory(memory_id)
        return memory
    
    def search_memories(self, query: str, memory_type: MemoryType = None,
                       importance: MemoryImportance = None, tags: Set[str] = None,
                       limit: int = 10) -> List[Memory]:
        """Search memories by various criteria"""
        results = []
        
        for memory_id, memory in self.memories.items():
            # Filter by type
            if memory_type and memory.memory_type != memory_type:
                continue
            
            # Filter by importance
            if importance and memory.importance != importance:
                continue
            
            # Filter by tags
            if tags and not tags.issubset(memory.tags):
                continue
            
            # Content search (simple keyword matching)
            if query.lower() in memory.content.lower():
                results.append(memory)
        
        # Sort by relevance (access count + recency)
        results.sort(key=lambda m: (m.access_count, m.last_accessed), reverse=True)
        
        return results[:limit]
    
    def get_related_memories(self, memory_id: str, limit: int = 5) -> List[Memory]:
        """Get memories related to a given memory"""
        memory = self.get_memory(memory_id)
        if not memory:
            return []
        
        related = []
        for related_id in memory.related_memories:
            if related_id in self.memories:
                related.append(self.memories[related_id])
        
        return related[:limit]
    
    def link_memories(self, memory_id_1: str, memory_id_2: str):
        """Create a bidirectional link between two memories"""
        if memory_id_1 in self.memories and memory_id_2 in self.memories:
            self.memories[memory_id_1].related_memories.add(memory_id_2)
            self.memories[memory_id_2].related_memories.add(memory_id_1)
            logger.debug(f"Linked memories {memory_id_1} and {memory_id_2}")
    
    async def consolidate_memories(self):
        """Consolidate memories based on access patterns and importance"""
        logger.info("Starting memory consolidation...")
        consolidated_count = 0
        
        for memory_id, memory in self.memories.items():
            # Skip already consolidated memories
            if memory.consolidation_level >= 1.0:
                continue
            
            # Calculate consolidation score
            time_factor = (datetime.now() - memory.created_at).total_seconds() / 3600  # hours
            access_factor = memory.access_count / 10.0  # Normalize
            importance_factor = (4 - memory.importance.value) / 4.0  # Higher importance = higher factor
            
            consolidation_score = (time_factor * 0.3 + access_factor * 0.4 + importance_factor * 0.3)
            
            # Update consolidation level
            memory.consolidation_level = min(1.0, memory.consolidation_level + consolidation_score * 0.1)
            
            if memory.consolidation_level >= self.consolidation_threshold:
                consolidated_count += 1
                logger.debug(f"Consolidated memory {memory_id}")
        
        self.last_consolidation = datetime.now()
        logger.info(f"Consolidation complete: {consolidated_count} memories consolidated")
    
    async def apply_forgetting(self):
        """Apply forgetting mechanism to memories"""
        logger.info("Applying forgetting mechanism...")
        forgotten_count = 0
        
        memories_to_remove = []
        
        for memory_id, memory in self.memories.items():
            # Skip critical and high importance memories
            if memory.importance in (MemoryImportance.CRITICAL, MemoryImportance.HIGH):
                continue
            
            # Calculate forgetting score
            time_since_access = (datetime.now() - memory.last_accessed).total_seconds() / 86400  # days
            base_forgetting = self.forgetting_rate * time_since_access
            
            # Importance reduces forgetting
            importance_factor = self.importance_protection * (4 - memory.importance.value) / 4.0
            
            # Consolidation reduces forgetting
            consolidation_protection = memory.consolidation_level * 0.5
            
            memory.forgetting_score = base_forgetting - importance_factor - consolidation_protection
            memory.forgetting_score = max(0.0, min(1.0, memory.forgetting_score))
            
            # Remove if forgetting score is high
            if memory.forgetting_score > 0.8:
                memories_to_remove.append(memory_id)
        
        # Remove forgotten memories
        for memory_id in memories_to_remove:
            self._remove_memory(memory_id)
            forgotten_count += 1
        
        logger.info(f"Forgetting complete: {forgotten_count} memories removed")
    
    def _remove_memory(self, memory_id: str):
        """Remove a memory and update indexes"""
        if memory_id in self.memories:
            memory = self.memories[memory_id]
            
            # Remove from indexes
            for tag in memory.tags:
                self.tag_index[tag].discard(memory_id)
            self.type_index[memory.memory_type].discard(memory_id)
            self.importance_index[memory.importance].discard(memory_id)
            
            # Remove from working memory
            if memory_id in self.working_memory:
                self.working_memory.remove(memory_id)
            
            # Remove related links
            for related_id in memory.related_memories:
                if related_id in self.memories:
                    self.memories[related_id].related_memories.discard(memory_id)
            
            del self.memories[memory_id]
            logger.debug(f"Removed memory {memory_id}")
    
    def add_reflection(self, memory_id: str, reflection_type: str, content: str,
                      confidence: float, actionable: bool = False,
                      action_suggestions: List[str] = None) -> Reflection:
        """Add a reflection on a memory"""
        if memory_id not in self.memories:
            raise ValueError(f"Memory {memory_id} not found")
        
        self.reflection_counter += 1
        reflection = Reflection(
            id=f"ref_{self.reflection_counter}",
            memory_id=memory_id,
            reflection_type=reflection_type,
            content=content,
            confidence=confidence,
            actionable=actionable,
            action_suggestions=action_suggestions or []
        )
        
        self.reflections[reflection.id] = reflection
        
        # Link reflection to memory
        self.memories[memory_id].metadata["reflections"] = \
            self.memories[memory_id].metadata.get("reflections", []) + [reflection.id]
        
        logger.info(f"Added reflection {reflection.id} on memory {memory_id}")
        return reflection
    
    def get_reflections(self, memory_id: str = None) -> List[Reflection]:
        """Get reflections, optionally filtered by memory"""
        if memory_id:
            return [r for r in self.reflections.values() if r.memory_id == memory_id]
        return list(self.reflections.values())
    
    def get_working_memory(self) -> List[Memory]:
        """Get current working memory contents"""
        return [self.memories[mid] for mid in self.working_memory if mid in self.memories]
    
    def get_memory_stats(self) -> Dict[str, Any]:
        """Get memory system statistics"""
        return {
            "total_memories": len(self.memories),
            "by_type": {t.value: len(ids) for t, ids in self.type_index.items() if ids},
            "by_importance": {i.value: len(ids) for i, ids in self.importance_index.items() if ids},
            "total_reflections": len(self.reflections),
            "working_memory_size": len(self.working_memory),
            "last_consolidation": self.last_consolidation.isoformat(),
            "consolidated_memories": sum(1 for m in self.memories.values()
                                       if m.consolidation_level >= self.consolidation_threshold)
        }
    
    async def save_to_disk(self):
        """Save memories and reflections to disk"""
        try:
            with open(self.memory_file, 'wb') as f:
                pickle.dump(self.memories, f)
            with open(self.reflection_file, 'wb') as f:
                pickle.dump(self.reflections, f)
            logger.info("Saved memories and reflections to disk")
        except Exception as e:
            logger.error(f"Failed to save memories: {e}")
    
    async def health_check(self) -> str:
        """Health check for the memory system"""
        return f"healthy ({len(self.memories)} memories, {len(self.reflections)} reflections)"
    
    async def shutdown(self):
        """Shutdown the memory system"""
        await self.save_to_disk()
        logger.info("Enhanced memory system shutting down")
