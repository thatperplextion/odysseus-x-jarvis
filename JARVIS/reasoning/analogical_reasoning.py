"""
Analogical Reasoning for Jarvis OS - Phase 2 Component
Reasoning by analogy and similarity
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


class SimilarityType(Enum):
    """Types of similarity"""
    STRUCTURAL = "structural"
    SEMANTIC = "semantic"
    FUNCTIONAL = "functional"
    CONTEXTUAL = "contextual"


class AnalogyType(Enum):
    """Types of analogies"""
    DIRECT = "direct"
    INDIRECT = "indirect"
    METAPHORICAL = "metaphorical"
    ABSTRACT = "abstract"


@dataclass
class Concept:
    """A concept for analogical reasoning"""
    id: str
    name: str
    features: Dict[str, Any] = field(default_factory=dict)
    relations: Dict[str, str] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "features": self.features,
            "relations": self.relations,
            "context": self.context
        }


@dataclass
class Analogy:
    """An analogy between concepts"""
    id: str
    source_concept: str
    target_concept: str
    similarity_score: float
    similarity_type: SimilarityType
    analogy_type: AnalogyType
    mapping: Dict[str, str] = field(default_factory=dict)
    confidence: float = 0.5
    explanation: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "source_concept": self.source_concept,
            "target_concept": self.target_concept,
            "similarity_score": self.similarity_score,
            "similarity_type": self.similarity_type.value,
            "analogy_type": self.analogy_type.value,
            "mapping": self.mapping,
            "confidence": self.confidence,
            "explanation": self.explanation
        }


class AnalogicalReasoner:
    """Analogical reasoning system for similarity-based reasoning"""
    
    def __init__(self):
        self.concepts: Dict[str, Concept] = {}
        self.analogies: Dict[str, Analogy] = {}
        self.concept_counter = 0
        self.analogy_counter = 0
        
        logger.info("Analogical reasoner initialized")
    
    def add_concept(self, name: str, features: Dict[str, Any] = None,
                   relations: Dict[str, str] = None, context: Dict[str, Any] = None,
                   concept_id: str = None) -> Concept:
        """Add a concept to the knowledge base"""
        if concept_id is None:
            self.concept_counter += 1
            concept_id = f"concept_{self.concept_counter}"
        
        concept = Concept(
            id=concept_id,
            name=name,
            features=features or {},
            relations=relations or {},
            context=context or {}
        )
        
        self.concepts[concept_id] = concept
        logger.debug(f"Added concept: {concept_id} ({name})")
        return concept
    
    def calculate_similarity(self, concept1: Concept, concept2: Concept,
                           similarity_type: SimilarityType = SimilarityType.STRUCTURAL) -> float:
        """Calculate similarity between two concepts"""
        if similarity_type == SimilarityType.STRUCTURAL:
            return self._structural_similarity(concept1, concept2)
        elif similarity_type == SimilarityType.SEMANTIC:
            return self._semantic_similarity(concept1, concept2)
        elif similarity_type == SimilarityType.FUNCTIONAL:
            return self._functional_similarity(concept1, concept2)
        elif similarity_type == SimilarityType.CONTEXTUAL:
            return self._contextual_similarity(concept1, concept2)
        else:
            return 0.0
    
    def _structural_similarity(self, concept1: Concept, concept2: Concept) -> float:
        """Calculate structural similarity based on features"""
        features1 = set(concept1.features.keys())
        features2 = set(concept2.features.keys())
        
        if not features1 and not features2:
            return 1.0
        
        # Jaccard similarity
        intersection = features1 & features2
        union = features1 | features2
        
        if not union:
            return 0.0
        
        similarity = len(intersection) / len(union)
        
        # Check feature values
        value_similarity = 0.0
        for feature in intersection:
            val1 = concept1.features[feature]
            val2 = concept2.features[feature]
            if val1 == val2:
                value_similarity += 1.0
        
        if intersection:
            value_similarity /= len(intersection)
        
        return (similarity + value_similarity) / 2
    
    def _semantic_similarity(self, concept1: Concept, concept2: Concept) -> float:
        """Calculate semantic similarity based on names"""
        name1 = concept1.name.lower()
        name2 = concept2.name.lower()
        
        # Simple string similarity
        if name1 == name2:
            return 1.0
        
        # Check for substring
        if name1 in name2 or name2 in name1:
            return 0.7
        
        # Check for common words
        words1 = set(name1.split())
        words2 = set(name2.split())
        
        if not words1 and not words2:
            return 0.5
        
        intersection = words1 & words2
        union = words1 | words2
        
        if not union:
            return 0.0
        
        return len(intersection) / len(union)
    
    def _functional_similarity(self, concept1: Concept, concept2: Concept) -> float:
        """Calculate functional similarity based on relations"""
        relations1 = set(concept1.relations.keys())
        relations2 = set(concept2.relations.keys())
        
        if not relations1 and not relations2:
            return 1.0
        
        intersection = relations1 & relations2
        union = relations1 | relations2
        
        if not union:
            return 0.0
        
        return len(intersection) / len(union)
    
    def _contextual_similarity(self, concept1: Concept, concept2: Concept) -> float:
        """Calculate contextual similarity based on context"""
        context1 = set(concept1.context.keys())
        context2 = set(concept2.context.keys())
        
        if not context1 and not context2:
            return 1.0
        
        intersection = context1 & context2
        union = context1 | context2
        
        if not union:
            return 0.0
        
        return len(intersection) / len(union)
    
    def find_analogies(self, source_concept_id: str, 
                      similarity_threshold: float = 0.5) -> List[Analogy]:
        """Find analogies for a source concept"""
        if source_concept_id not in self.concepts:
            return []
        
        source = self.concepts[source_concept_id]
        analogies = []
        
        for target_id, target in self.concepts.items():
            if target_id == source_concept_id:
                continue
            
            # Calculate similarity for each type
            structural = self.calculate_similarity(source, target, SimilarityType.STRUCTURAL)
            semantic = self.calculate_similarity(source, target, SimilarityType.SEMANTIC)
            functional = self.calculate_similarity(source, target, SimilarityType.FUNCTIONAL)
            
            # Use highest similarity
            max_similarity = max(structural, semantic, functional)
            
            if max_similarity >= similarity_threshold:
                # Determine similarity type
                if structural == max_similarity:
                    sim_type = SimilarityType.STRUCTURAL
                elif semantic == max_similarity:
                    sim_type = SimilarityType.SEMANTIC
                else:
                    sim_type = SimilarityType.FUNCTIONAL
                
                # Create analogy
                self.analogy_counter += 1
                analogy_id = f"analogy_{self.analogy_counter}"
                
                analogy = Analogy(
                    id=analogy_id,
                    source_concept=source_concept_id,
                    target_concept=target_id,
                    similarity_score=max_similarity,
                    similarity_type=sim_type,
                    analogy_type=AnalogyType.DIRECT,
                    confidence=max_similarity
                )
                
                # Generate mapping
                analogy.mapping = self._generate_mapping(source, target)
                
                # Generate explanation
                analogy.explanation = self._generate_explanation(source, target, max_similarity)
                
                analogies.append(analogy)
                self.analogies[analogy_id] = analogy
        
        # Sort by similarity
        analogies.sort(key=lambda a: a.similarity_score, reverse=True)
        
        logger.debug(f"Found {len(analogies)} analogies for {source_concept_id}")
        return analogies
    
    def _generate_mapping(self, source: Concept, target: Concept) -> Dict[str, str]:
        """Generate feature mapping between concepts"""
        mapping = {}
        
        for feature in source.features:
            if feature in target.features:
                mapping[feature] = feature
        
        return mapping
    
    def _generate_explanation(self, source: Concept, target: Concept, 
                             similarity: float) -> str:
        """Generate explanation for the analogy"""
        if similarity >= 0.8:
            return f"{source.name} is very similar to {target.name}"
        elif similarity >= 0.6:
            return f"{source.name} is somewhat similar to {target.name}"
        else:
            return f"{source.name} is loosely similar to {target.name}"
    
    def apply_analogy(self, analogy: Analogy, source_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply an analogy to transfer knowledge"""
        target_data = {}
        
        # Map features
        for source_feature, target_feature in analogy.mapping.items():
            if source_feature in source_data:
                target_data[target_feature] = source_data[source_feature]
        
        logger.debug(f"Applied analogy {analogy.id}")
        return target_data
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get analogical reasoning statistics"""
        similarity_type_counts = defaultdict(int)
        analogy_type_counts = defaultdict(int)
        
        for analogy in self.analogies.values():
            similarity_type_counts[analogy.similarity_type.value] += 1
            analogy_type_counts[analogy.analogy_type.value] += 1
        
        return {
            "total_concepts": len(self.concepts),
            "total_analogies": len(self.analogies),
            "similarity_type_distribution": dict(similarity_type_counts),
            "analogy_type_distribution": dict(analogy_type_counts),
            "average_similarity": (
                sum(a.similarity_score for a in self.analogies.values()) / len(self.analogies)
                if self.analogies else 0.0
            )
        }
    
    async def health_check(self) -> str:
        """Health check for the analogical reasoner"""
        stats = self.get_statistics()
        return f"healthy ({stats['total_concepts']} concepts, {stats['total_analogies']} analogies)"
    
    async def shutdown(self):
        """Shutdown the analogical reasoner"""
        logger.info("Analogical reasoner shutting down")
