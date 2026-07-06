"""
Entity Extraction System for Jarvis OS - Phase 2 Component
Named Entity Recognition for extracting structured information from text
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Tuple
import re
from collections import defaultdict

logger = logging.getLogger(__name__)


class EntityType(Enum):
    """Types of entities"""
    PERSON = "person"
    ORGANIZATION = "organization"
    LOCATION = "location"
    DATE = "date"
    TIME = "time"
    NUMBER = "number"
    EMAIL = "email"
    URL = "url"
    FILE_PATH = "file_path"
    COMMAND = "command"
    VARIABLE = "variable"
    FUNCTION = "function"
    CLASS = "class"
    MODULE = "module"
    CUSTOM = "custom"


@dataclass
class Entity:
    """An extracted entity"""
    text: str
    entity_type: EntityType
    start_pos: int
    end_pos: int
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "entity_type": self.entity_type.value,
            "start_pos": self.start_pos,
            "end_pos": self.end_pos,
            "confidence": self.confidence,
            "metadata": self.metadata
        }


@dataclass
class EntityPattern:
    """A pattern for matching entities"""
    entity_type: EntityType
    pattern: str
    flags: int = re.IGNORECASE
    priority: int = 0


class EntityExtractor:
    """Entity extraction system for named entity recognition"""
    
    def __init__(self):
        self.patterns: List[EntityPattern] = []
        self.custom_entities: Dict[str, List[str]] = defaultdict(list)
        self.extraction_counter = 0
        self.extraction_history: List[Dict[str, Any]] = []
        
        # Initialize default patterns
        self._initialize_default_patterns()
        
        logger.info("Entity extraction system initialized")
    
    def _initialize_default_patterns(self):
        """Initialize default entity patterns"""
        
        # Email patterns
        self.patterns.append(EntityPattern(
            entity_type=EntityType.EMAIL,
            pattern=r'[\w\.-]+@[\w\.-]+\.\w{2,}',
            priority=10
        ))
        
        # URL patterns
        self.patterns.append(EntityPattern(
            entity_type=EntityType.URL,
            pattern=r'https?://[^\s<>"{}|\\^`\[\]]+',
            priority=10
        ))
        
        # File path patterns
        self.patterns.append(EntityPattern(
            entity_type=EntityType.FILE_PATH,
            pattern=r'[\w/\\.-]+\.\w+',
            priority=9
        ))
        
        # Date patterns
        self.patterns.append(EntityPattern(
            entity_type=EntityType.DATE,
            pattern=r'\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}|\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4}',
            priority=8
        ))
        
        # Time patterns
        self.patterns.append(EntityPattern(
            entity_type=EntityType.TIME,
            pattern=r'\d{1,2}:\d{2}(?::\d{2})?(?:\s*[AP]M)?',
            priority=8
        ))
        
        # Number patterns
        self.patterns.append(EntityPattern(
            entity_type=EntityType.NUMBER,
            pattern=r'\b\d+(?:\.\d+)?\b',
            priority=7
        ))
        
        # Command patterns (common shell commands)
        self.patterns.append(EntityPattern(
            entity_type=EntityType.COMMAND,
            pattern=r'\b(?:git|npm|pip|python|node|java|go|rust|docker|kubectl|aws|az|gcloud)\b',
            priority=9
        ))
        
        # Function patterns (code functions)
        self.patterns.append(EntityPattern(
            entity_type=EntityType.FUNCTION,
            pattern=r'\b[a-zA-Z_][a-zA-Z0-9_]*\s*\(',
            priority=6
        ))
        
        # Class patterns (code classes)
        self.patterns.append(EntityPattern(
            entity_type=EntityType.CLASS,
            pattern=r'\bclass\s+[A-Z][a-zA-Z0-9_]*\b',
            priority=6
        ))
        
        # Module patterns (code modules)
        self.patterns.append(EntityPattern(
            entity_type=EntityType.MODULE,
            pattern=r'\b(?:import|from)\s+[a-zA-Z_][a-zA-Z0-9_.]*\b',
            priority=6
        ))
        
        # Variable patterns (code variables)
        self.patterns.append(EntityPattern(
            entity_type=EntityType.VARIABLE,
            pattern=r'\b[a-zA-Z_][a-zA-Z0-9_]*\s*=',
            priority=5
        ))
        
        # Sort by priority (higher first)
        self.patterns.sort(key=lambda p: p.priority, reverse=True)
    
    def add_custom_entity(self, entity_type: EntityType, values: List[str]):
        """Add custom entity values"""
        for value in values:
            self.custom_entities[value.lower()].append(entity_type)
        logger.info(f"Added {len(values)} custom entities for {entity_type.value}")
    
    def extract_entities(self, text: str, context: Dict[str, Any] = None) -> List[Entity]:
        """Extract entities from text"""
        entities = []
        
        # Extract using patterns
        for pattern in self.patterns:
            matches = re.finditer(pattern.pattern, text, flags=pattern.flags)
            for match in matches:
                entity = Entity(
                    text=match.group(),
                    entity_type=pattern.entity_type,
                    start_pos=match.start(),
                    end_pos=match.end(),
                    confidence=0.9,
                    metadata={"pattern": pattern.pattern}
                )
                entities.append(entity)
        
        # Extract custom entities
        for custom_value, entity_types in self.custom_entities.items():
            for match in re.finditer(re.escape(custom_value), text, re.IGNORECASE):
                for entity_type in entity_types:
                    entity = Entity(
                        text=match.group(),
                        entity_type=entity_type,
                        start_pos=match.start(),
                        end_pos=match.end(),
                        confidence=1.0,
                        metadata={"custom": True}
                    )
                    entities.append(entity)
        
        # Remove overlapping entities (keep longer ones)
        entities = self._remove_overlaps(entities)
        
        # Record in history
        self.extraction_counter += 1
        self.extraction_history.append({
            "text": text,
            "entities": [e.to_dict() for e in entities],
            "timestamp": datetime.now().isoformat()
        })
        
        logger.info(f"Extracted {len(entities)} entities from text")
        return entities
    
    def _remove_overlaps(self, entities: List[Entity]) -> List[Entity]:
        """Remove overlapping entities, keeping longer ones"""
        if not entities:
            return entities
        
        # Sort by start position, then by length (longer first)
        entities.sort(key=lambda e: (e.start_pos, -(e.end_pos - e.start_pos)))
        
        non_overlapping = []
        for entity in entities:
            # Check if this entity overlaps with any already added entity
            overlaps = False
            for added in non_overlapping:
                if (entity.start_pos < added.end_pos and 
                    entity.end_pos > added.start_pos):
                    overlaps = True
                    break
            
            if not overlaps:
                non_overlapping.append(entity)
        
        return non_overlapping
    
    def extract_entities_by_type(self, text: str, entity_type: EntityType) -> List[Entity]:
        """Extract entities of a specific type"""
        all_entities = self.extract_entities(text)
        return [e for e in all_entities if e.entity_type == entity_type]
    
    def get_entity_summary(self, text: str) -> Dict[str, Any]:
        """Get a summary of entities in text"""
        entities = self.extract_entities(text)
        
        by_type = defaultdict(list)
        for entity in entities:
            by_type[entity.entity_type.value].append(entity.text)
        
        return {
            "total_entities": len(entities),
            "by_type": dict(by_type),
            "unique_entities": len(set(e.text.lower() for e in entities))
        }
    
    def get_extraction_stats(self) -> Dict[str, Any]:
        """Get statistics about entity extraction"""
        entity_type_counts = defaultdict(int)
        
        for entry in self.extraction_history:
            for entity in entry["entities"]:
                entity_type = entity["entity_type"]
                entity_type_counts[entity_type] += 1
        
        return {
            "total_extractions": self.extraction_counter,
            "entity_type_distribution": dict(entity_type_counts),
            "total_patterns": len(self.patterns),
            "custom_entities": len(self.custom_entities)
        }
    
    async def health_check(self) -> str:
        """Health check for the entity extraction system"""
        stats = self.get_extraction_stats()
        return f"healthy ({stats['total_patterns']} patterns, {stats['total_extractions']} extractions)"
    
    async def shutdown(self):
        """Shutdown the entity extraction system"""
        logger.info("Entity extraction system shutting down")
