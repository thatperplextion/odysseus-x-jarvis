"""
Abductive Reasoning for Jarvis OS - Phase 2 Component
Inference to the best explanation
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


class ExplanationType(Enum):
    """Types of explanations"""
    CAUSAL = "causal"
    TELEOLOGICAL = "teleological"
    FUNCTIONAL = "functional"
    INTENTIONAL = "intentional"
    STATISTICAL = "statistical"


class ExplanationQuality(Enum):
    """Quality levels for explanations"""
    POOR = 0.2
    FAIR = 0.4
    GOOD = 0.6
    EXCELLENT = 0.8


@dataclass
class Observation:
    """An observation to be explained"""
    id: str
    content: str
    timestamp: datetime = field(default_factory=datetime.now)
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "context": self.context
        }


@dataclass
class Hypothesis:
    """A hypothesis explaining observations"""
    id: str
    explanation: str
    explanation_type: ExplanationType
    evidence: List[str] = field(default_factory=list)
    confidence: float = 0.5
    quality: float = 0.5
    assumptions: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "explanation": self.explanation,
            "explanation_type": self.explanation_type.value,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "quality": self.quality,
            "assumptions": self.assumptions
        }


@dataclass
class AbductiveInference:
    """Result of abductive reasoning"""
    observation: Observation
    hypotheses: List[Hypothesis]
    best_hypothesis: Optional[Hypothesis] = None
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "observation": self.observation.to_dict(),
            "hypotheses": [h.to_dict() for h in self.hypotheses],
            "best_hypothesis": self.best_hypothesis.to_dict() if self.best_hypothesis else None,
            "timestamp": self.timestamp.isoformat()
        }


class AbductiveReasoner:
    """Abductive reasoning system for inference to best explanation"""
    
    def __init__(self):
        self.observations: Dict[str, Observation] = {}
        self.hypotheses: Dict[str, Hypothesis] = {}
        self.inference_history: List[AbductiveInference] = []
        self.observation_counter = 0
        self.hypothesis_counter = 0
        
        # Knowledge base of common explanations
        self.explanation_patterns: Dict[str, List[str]] = {
            "error": ["system failure", "user error", "network issue", "resource exhaustion"],
            "slow": ["high load", "inefficient algorithm", "network latency", "disk I/O"],
            "crash": ["memory leak", "unhandled exception", "resource conflict", "external signal"],
            "success": ["correct implementation", "optimal conditions", "user satisfaction"]
        }
        
        logger.info("Abductive reasoner initialized")
    
    def add_observation(self, content: str, context: Dict[str, Any] = None,
                       observation_id: str = None) -> Observation:
        """Add an observation to be explained"""
        if observation_id is None:
            self.observation_counter += 1
            observation_id = f"obs_{self.observation_counter}"
        
        observation = Observation(
            id=observation_id,
            content=content,
            context=context or {}
        )
        
        self.observations[observation_id] = observation
        logger.debug(f"Added observation: {observation_id}")
        return observation
    
    def generate_hypotheses(self, observation: Observation) -> List[Hypothesis]:
        """Generate hypotheses to explain an observation"""
        hypotheses = []
        
        # Extract keywords from observation
        content_lower = observation.content.lower()
        
        # Find matching explanation patterns
        for keyword, explanations in self.explanation_patterns.items():
            if keyword in content_lower:
                for explanation in explanations:
                    self.hypothesis_counter += 1
                    hypothesis_id = f"hyp_{self.hypothesis_counter}"
                    
                    hypothesis = Hypothesis(
                        id=hypothesis_id,
                        explanation=f"{keyword} caused by {explanation}",
                        explanation_type=ExplanationType.CAUSAL,
                        confidence=0.5
                    )
                    
                    hypotheses.append(hypothesis)
                    self.hypotheses[hypothesis_id] = hypothesis
        
        # Generate generic hypotheses if no matches
        if not hypotheses:
            generic_explanations = [
                "unknown cause",
                "external factor",
                "system behavior",
                "user action"
            ]
            
            for explanation in generic_explanations:
                self.hypothesis_counter += 1
                hypothesis_id = f"hyp_{self.hypothesis_counter}"
                
                hypothesis = Hypothesis(
                    id=hypothesis_id,
                    explanation=f"observation caused by {explanation}",
                    explanation_type=ExplanationType.CAUSAL,
                    confidence=0.3
                )
                
                hypotheses.append(hypothesis)
                self.hypotheses[hypothesis_id] = hypothesis
        
        logger.debug(f"Generated {len(hypotheses)} hypotheses for {observation.id}")
        return hypotheses
    
    def evaluate_hypothesis(self, hypothesis: Hypothesis, 
                          observation: Observation) -> float:
        """Evaluate the quality of a hypothesis"""
        quality = 0.5  # Base quality
        
        # Check for explanatory power
        if len(hypothesis.explanation) > 10:
            quality += 0.1
        
        # Check for evidence
        if hypothesis.evidence:
            quality += 0.2
        
        # Check for simplicity (fewer assumptions is better)
        if len(hypothesis.assumptions) == 0:
            quality += 0.1
        elif len(hypothesis.assumptions) <= 2:
            quality += 0.05
        
        # Check for consistency with context
        if observation.context:
            quality += 0.1
        
        return min(quality, 1.0)
    
    def select_best_hypothesis(self, hypotheses: List[Hypothesis],
                               observation: Observation) -> Optional[Hypothesis]:
        """Select the best hypothesis using abductive criteria"""
        if not hypotheses:
            return None
        
        # Evaluate all hypotheses
        for hypothesis in hypotheses:
            hypothesis.quality = self.evaluate_hypothesis(hypothesis, observation)
        
        # Select highest quality
        best = max(hypotheses, key=lambda h: h.quality)
        
        logger.debug(f"Selected best hypothesis: {best.id} (quality: {best.quality:.2f})")
        return best
    
    def explain(self, observation: Observation) -> AbductiveInference:
        """Generate explanation for an observation"""
        # Generate hypotheses
        hypotheses = self.generate_hypotheses(observation)
        
        # Select best hypothesis
        best_hypothesis = self.select_best_hypothesis(hypotheses, observation)
        
        # Create inference result
        inference = AbductiveInference(
            observation=observation,
            hypotheses=hypotheses,
            best_hypothesis=best_hypothesis
        )
        
        self.inference_history.append(inference)
        
        logger.info(f"Explained observation {observation.id}: {best_hypothesis.explanation if best_hypothesis else 'No hypothesis'}")
        return inference
    
    def add_evidence(self, hypothesis_id: str, evidence: str):
        """Add evidence to support a hypothesis"""
        if hypothesis_id in self.hypotheses:
            self.hypotheses[hypothesis_id].evidence.append(evidence)
            self.hypotheses[hypothesis_id].confidence = min(
                self.hypotheses[hypothesis_id].confidence + 0.1, 1.0
            )
            logger.debug(f"Added evidence to hypothesis {hypothesis_id}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get abductive reasoning statistics"""
        type_counts = defaultdict(int)
        
        for hypothesis in self.hypotheses.values():
            type_counts[hypothesis.explanation_type.value] += 1
        
        return {
            "total_observations": len(self.observations),
            "total_hypotheses": len(self.hypotheses),
            "total_inferences": len(self.inference_history),
            "type_distribution": dict(type_counts),
            "average_quality": (
                sum(h.quality for h in self.hypotheses.values()) / len(self.hypotheses)
                if self.hypotheses else 0.0
            )
        }
    
    async def health_check(self) -> str:
        """Health check for the abductive reasoner"""
        stats = self.get_statistics()
        return f"healthy ({stats['total_observations']} observations, {stats['total_hypotheses']} hypotheses)"
    
    async def shutdown(self):
        """Shutdown the abductive reasoner"""
        logger.info("Abductive reasoner shutting down")
