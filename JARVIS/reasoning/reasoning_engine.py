"""
Reasoning Engine for Jarvis OS - Phase 1 Component
Advanced reasoning with chain-of-thought, logical inference, and contextual decision-making
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Tuple
import json

logger = logging.getLogger(__name__)


class InferenceType(Enum):
    """Types of logical inference"""
    DEDUCTIVE = "deductive"  # General to specific
    INDUCTIVE = "inductive"  # Specific to general
    ABDUCTIVE = "abductive"  # Best explanation
    ANALOGICAL = "analogical"  # Pattern matching


class ReasoningStep:
    """A single step in the reasoning process"""
    
    def __init__(self, step_id: int, content: str, step_type: str = "thought"):
        self.step_id = step_id
        self.content = content
        self.step_type = step_type  # thought, observation, inference, conclusion
        self.timestamp = datetime.now()
        self.confidence: float = 1.0
        self.evidence: List[str] = []
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "content": self.content,
            "step_type": self.step_type,
            "timestamp": self.timestamp.isoformat(),
            "confidence": self.confidence,
            "evidence": self.evidence
        }


@dataclass
class ReasoningChain:
    """A chain of reasoning steps (chain-of-thought)"""
    id: str
    query: str
    steps: List[ReasoningStep] = field(default_factory=list)
    conclusion: Optional[str] = None
    confidence: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)
    context: Dict[str, Any] = field(default_factory=dict)
    
    def add_step(self, content: str, step_type: str = "thought", confidence: float = 1.0) -> None:
        """Add a reasoning step"""
        step_id = len(self.steps) + 1
        step = ReasoningStep(step_id, content, step_type)
        step.confidence = confidence
        self.steps.append(step)
    
    def set_conclusion(self, conclusion: str, confidence: float) -> None:
        """Set the final conclusion"""
        self.conclusion = conclusion
        self.confidence = confidence
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "query": self.query,
            "steps": [step.to_dict() for step in self.steps],
            "conclusion": self.conclusion,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat(),
            "context": self.context
        }


@dataclass
class Hypothesis:
    """A hypothesis for multi-hypothesis evaluation"""
    id: str
    statement: str
    evidence: List[str] = field(default_factory=list)
    confidence: float = 0.0
    probability: float = 0.0
    
    def add_evidence(self, evidence: str, supports: bool = True) -> None:
        """Add evidence for or against the hypothesis"""
        self.evidence.append(f"{evidence} ({'supports' if supports else 'contradicts'})")
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "statement": self.statement,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "probability": self.probability
        }


class ReasoningEngine:
    """Advanced reasoning engine with chain-of-thought and logical inference"""
    
    def __init__(self):
        self.reasoning_chains: Dict[str, ReasoningChain] = {}
        self.chain_counter = 0
        self.hypotheses: Dict[str, Hypothesis] = {}
        self.hypothesis_counter = 0
        self.reasoning_history: List[Dict[str, Any]] = []
        self._knowledge_base: Dict[str, Any] = {}
    
    def set_knowledge_base(self, knowledge: Dict[str, Any]) -> None:
        """Set the knowledge base for reasoning"""
        self._knowledge_base = knowledge
    
    def create_reasoning_chain(self, query: str, context: Dict[str, Any] = None) -> ReasoningChain:
        """Create a new reasoning chain for a query"""
        self.chain_counter += 1
        chain = ReasoningChain(
            id=f"chain_{self.chain_counter}",
            query=query,
            context=context or {}
        )
        self.reasoning_chains[chain.id] = chain
        logger.info(f"Created reasoning chain {chain.id} for query: {query}")
        return chain
    
    async def reason_chain_of_thought(self, query: str, context: Dict[str, Any] = None) -> ReasoningChain:
        """Perform chain-of-thought reasoning"""
        chain = self.create_reasoning_chain(query, context)
        
        # Step 1: Understand the query
        chain.add_step(f"Understanding the query: {query}", "observation", 1.0)
        
        # Step 2: Gather relevant information from context
        relevant_info = self._extract_relevant_info(query, context or {})
        chain.add_step(f"Relevant information: {relevant_info}", "observation", 0.9)
        
        # Step 3: Analyze the problem
        analysis = self._analyze_problem(query, relevant_info)
        chain.add_step(f"Problem analysis: {analysis}", "thought", 0.8)
        
        # Step 4: Consider multiple approaches
        approaches = self._generate_approaches(query, relevant_info)
        chain.add_step(f"Possible approaches: {approaches}", "thought", 0.7)
        
        # Step 5: Evaluate approaches
        best_approach = self._evaluate_approaches(approaches, relevant_info)
        chain.add_step(f"Best approach: {best_approach}", "inference", 0.8)
        
        # Step 6: Formulate conclusion
        conclusion = self._formulate_conclusion(query, best_approach, relevant_info)
        chain.set_conclusion(conclusion, 0.85)
        
        self.reasoning_history.append(chain.to_dict())
        logger.info(f"Completed chain-of-thought reasoning for: {query}")
        
        return chain
    
    def _extract_relevant_info(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Extract relevant information from context"""
        relevant = {}
        query_lower = query.lower()
        
        # Simple keyword matching (in production, use semantic search)
        for key, value in context.items():
            if any(word in str(value).lower() for word in query_lower.split()):
                relevant[key] = value
        
        # Add knowledge base information
        for key, value in self._knowledge_base.items():
            if any(word in str(value).lower() for word in query_lower.split()):
                relevant[f"kb_{key}"] = value
        
        return relevant
    
    def _analyze_problem(self, query: str, info: Dict[str, Any]) -> str:
        """Analyze the problem based on query and information"""
        query_lower = query.lower()
        
        if "how" in query_lower:
            return "This is a 'how-to' question requiring procedural reasoning"
        elif "why" in query_lower:
            return "This is a 'why' question requiring causal reasoning"
        elif "what" in query_lower:
            return "This is a 'what' question requiring definitional reasoning"
        elif "should" in query_lower or "recommend" in query_lower:
            return "This is a recommendation question requiring evaluative reasoning"
        else:
            return "This is a general query requiring comprehensive analysis"
    
    def _generate_approaches(self, query: str, info: Dict[str, Any]) -> List[str]:
        """Generate possible approaches to solve the problem"""
        query_lower = query.lower()
        
        if "create" in query_lower or "build" in query_lower:
            return [
                "Start with requirements analysis",
                "Design the architecture",
                "Implement core components",
                "Add features incrementally",
                "Test and iterate"
            ]
        elif "fix" in query_lower or "debug" in query_lower:
            return [
                "Reproduce the issue",
                "Analyze logs and error messages",
                "Identify root cause",
                "Implement fix",
                "Verify solution"
            ]
        elif "analyze" in query_lower or "understand" in query_lower:
            return [
                "Gather context",
                "Examine structure",
                "Identify patterns",
                "Draw conclusions",
                "Document findings"
            ]
        else:
            return [
                "Understand the problem",
                "Gather information",
                "Analyze options",
                "Make decision",
                "Take action"
            ]
    
    def _evaluate_approaches(self, approaches: List[str], info: Dict[str, Any]) -> str:
        """Evaluate approaches and select the best one"""
        # Simple evaluation: prefer the first approach (in production, use more sophisticated logic)
        return approaches[0] if approaches else "No clear approach identified"
    
    def _formulate_conclusion(self, query: str, approach: str, info: Dict[str, Any]) -> str:
        """Formulate the final conclusion"""
        return f"Based on the analysis, the recommended approach is: {approach}"
    
    async def deductive_reasoning(self, premises: List[str], conclusion: str) -> Tuple[bool, float]:
        """Perform deductive reasoning (general to specific)"""
        # Deductive reasoning: if premises are true, conclusion must be true
        # Simplified implementation
        
        confidence = 1.0
        valid = True
        
        # Check if conclusion follows from premises
        # This is a simplified check - in production, use formal logic
        for premise in premises:
            if conclusion.lower() not in premise.lower():
                # Conclusion doesn't obviously follow
                confidence *= 0.8
        
        logger.info(f"Deductive reasoning: {valid} (confidence: {confidence})")
        return valid, confidence
    
    async def inductive_reasoning(self, observations: List[str]) -> Tuple[str, float]:
        """Perform inductive reasoning (specific to general)"""
        # Inductive reasoning: generalize from specific observations
        
        if not observations:
            return "No observations provided", 0.0
        
        # Extract common patterns
        common_words = set()
        for obs in observations:
            words = set(obs.lower().split())
            if not common_words:
                common_words = words
            else:
                common_words.intersection_update(words)
        
        # Form generalization
        generalization = " ".join(common_words) if common_words else "No clear pattern"
        confidence = min(1.0, len(observations) / 5.0)  # More observations = higher confidence
        
        logger.info(f"Inductive reasoning: {generalization} (confidence: {confidence})")
        return generalization, confidence
    
    async def abductive_reasoning(self, observations: List[str], possible_explanations: List[str]) -> Tuple[str, float]:
        """Perform abductive reasoning (inference to best explanation)"""
        # Abductive reasoning: find the best explanation for observations
        
        best_explanation = ""
        best_score = 0.0
        
        for explanation in possible_explanations:
            score = 0.0
            explanation_lower = explanation.lower()
            
            # Score based on how well explanation covers observations
            for obs in observations:
                obs_lower = obs.lower()
                if any(word in explanation_lower for word in obs_lower.split()):
                    score += 1.0
            
            score /= len(observations) if observations else 1
            
            if score > best_score:
                best_score = score
                best_explanation = explanation
        
        logger.info(f"Abductive reasoning: {best_explanation} (confidence: {best_score})")
        return best_explanation, best_score
    
    async def analogical_reasoning(self, source: str, target: str, context: Dict[str, Any] = None) -> Tuple[str, float]:
        """Perform analogical reasoning (pattern matching)"""
        # Analogical reasoning: apply knowledge from source to target
        
        # Extract key features from source and target
        source_features = set(source.lower().split())
        target_features = set(target.lower().split())
        
        # Calculate similarity
        intersection = source_features.intersection(target_features)
        union = source_features.union(target_features)
        similarity = len(intersection) / len(union) if union else 0.0
        
        # Generate analogy
        if similarity > 0.5:
            analogy = f"Similar to {source}, {target} likely shares characteristics"
        else:
            analogy = f"Limited similarity between {source} and {target}"
        
        logger.info(f"Analogical reasoning: {analogy} (confidence: {similarity})")
        return analogy, similarity
    
    def create_hypothesis(self, statement: str) -> Hypothesis:
        """Create a new hypothesis"""
        self.hypothesis_counter += 1
        hypothesis = Hypothesis(
            id=f"hypothesis_{self.hypothesis_counter}",
            statement=statement
        )
        self.hypotheses[hypothesis.id] = hypothesis
        logger.info(f"Created hypothesis {hypothesis.id}: {statement}")
        return hypothesis
    
    async def evaluate_hypotheses(self, hypotheses: List[Hypothesis], evidence: List[str]) -> List[Hypothesis]:
        """Evaluate multiple hypotheses against evidence"""
        for hypothesis in hypotheses:
            supporting = 0
            total = 0
            
            for ev in evidence:
                total += 1
                # Simple check: if evidence words appear in hypothesis, consider it supporting
                if any(word in hypothesis.statement.lower() for word in ev.lower().split()):
                    supporting += 1
                    hypothesis.add_evidence(ev, supports=True)
                else:
                    hypothesis.add_evidence(ev, supports=False)
            
            # Calculate probability
            hypothesis.probability = supporting / total if total > 0 else 0.0
            hypothesis.confidence = hypothesis.probability
        
        # Sort by probability
        hypotheses.sort(key=lambda h: h.probability, reverse=True)
        
        logger.info(f"Evaluated {len(hypotheses)} hypotheses")
        return hypotheses
    
    async def contextual_reasoning(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Perform reasoning with contextual awareness"""
        # Use context to inform reasoning
        chain = await self.reason_chain_of_thought(query, context)
        
        # Add context-specific reasoning
        if "previous_actions" in context:
            chain.add_step(f"Considering previous actions: {context['previous_actions']}", "thought", 0.8)
        
        if "current_state" in context:
            chain.add_step(f"Current system state: {context['current_state']}", "observation", 0.9)
        
        if "goals" in context:
            chain.add_step(f"Aligning with goals: {context['goals']}", "thought", 0.85)
        
        return chain.to_dict()
    
    def get_reasoning_chain(self, chain_id: str) -> Optional[ReasoningChain]:
        """Get a reasoning chain by ID"""
        return self.reasoning_chains.get(chain_id)
    
    def get_reasoning_history(self) -> List[Dict[str, Any]]:
        """Get the reasoning history"""
        return self.reasoning_history
    
    async def health_check(self) -> str:
        """Health check for the reasoning engine"""
        return "healthy"
    
    async def shutdown(self) -> None:
        """Shutdown the reasoning engine"""
        logger.info("Reasoning engine shutting down")
