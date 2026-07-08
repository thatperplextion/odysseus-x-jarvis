"""
Meta-Reasoning for Jarvis OS - Phase 2 Component
Reasoning about reasoning processes
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Callable
from collections import defaultdict

logger = logging.getLogger(__name__)


class ReasoningType(Enum):
    """Types of reasoning processes"""
    DEDUCTIVE = "deductive"
    INDUCTIVE = "inductive"
    ABDUCTIVE = "abductive"
    ANALOGICAL = "analogical"
    CAUSAL = "causal"
    META = "meta"


class ReasoningQuality(Enum):
    """Quality levels for reasoning"""
    POOR = 0.2
    FAIR = 0.4
    GOOD = 0.6
    EXCELLENT = 0.8


@dataclass
class ReasoningStep:
    """A step in a reasoning process"""
    id: str
    reasoning_type: ReasoningType
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]
    confidence: float = 0.5
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "reasoning_type": self.reasoning_type.value,
            "input_data": self.input_data,
            "output_data": self.output_data,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata
        }


@dataclass
class ReasoningProcess:
    """A complete reasoning process"""
    id: str
    name: str
    steps: List[ReasoningStep]
    final_result: Any
    quality: float = 0.5
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "steps": [s.to_dict() for s in self.steps],
            "final_result": str(self.final_result) if self.final_result else None,
            "quality": self.quality,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class MetaEvaluation:
    """Evaluation of a reasoning process"""
    process_id: str
    evaluation_type: str
    score: float
    feedback: str
    suggestions: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "process_id": self.process_id,
            "evaluation_type": self.evaluation_type,
            "score": self.score,
            "feedback": self.feedback,
            "suggestions": self.suggestions,
            "timestamp": self.timestamp.isoformat()
        }


class MetaReasoner:
    """Meta-reasoning system for reasoning about reasoning"""
    
    def __init__(self):
        self.processes: Dict[str, ReasoningProcess] = {}
        self.evaluations: Dict[str, List[MetaEvaluation]] = defaultdict(list)
        self.process_counter = 0
        self.step_counter = 0
        
        # Reasoning quality metrics
        self.quality_criteria: Dict[str, Callable] = {
            "coherence": self._evaluate_coherence,
            "consistency": self._evaluate_consistency,
            "efficiency": self._evaluate_efficiency,
            "confidence": self._evaluate_confidence,
            "completeness": self._evaluate_completeness
        }
        
        logger.info("Meta reasoner initialized")
    
    def create_process(self, name: str, initial_data: Dict[str, Any] = None,
                      process_id: str = None) -> ReasoningProcess:
        """Create a new reasoning process"""
        if process_id is None:
            self.process_counter += 1
            process_id = f"process_{self.process_counter}"
        
        process = ReasoningProcess(
            id=process_id,
            name=name,
            steps=[],
            final_result=None
        )
        
        self.processes[process_id] = process
        logger.debug(f"Created reasoning process: {process_id}")
        return process
    
    def add_step(self, process_id: str, reasoning_type: ReasoningType,
                input_data: Dict[str, Any], output_data: Dict[str, Any],
                confidence: float = 0.5, metadata: Dict[str, Any] = None) -> ReasoningStep:
        """Add a reasoning step to a process"""
        if process_id not in self.processes:
            raise ValueError(f"Process {process_id} not found")
        
        self.step_counter += 1
        step_id = f"step_{self.step_counter}"
        
        step = ReasoningStep(
            id=step_id,
            reasoning_type=reasoning_type,
            input_data=input_data,
            output_data=output_data,
            confidence=confidence,
            metadata=metadata or {}
        )
        
        self.processes[process_id].steps.append(step)
        logger.debug(f"Added step {step_id} to process {process_id}")
        return step
    
    def complete_process(self, process_id: str, final_result: Any):
        """Mark a reasoning process as complete"""
        if process_id not in self.processes:
            raise ValueError(f"Process {process_id} not found")
        
        self.processes[process_id].final_result = final_result
        
        # Auto-evaluate quality
        quality = self.evaluate_process_quality(process_id)
        self.processes[process_id].quality = quality
        
        logger.info(f"Completed process {process_id} with quality {quality:.2f}")
    
    def evaluate_process_quality(self, process_id: str) -> float:
        """Evaluate the overall quality of a reasoning process"""
        if process_id not in self.processes:
            return 0.0
        
        process = self.processes[process_id]
        
        if not process.steps:
            return 0.5
        
        # Evaluate each criterion
        scores = []
        for criterion_name, criterion_func in self.quality_criteria.items():
            score = criterion_func(process)
            scores.append(score)
        
        # Average score
        quality = sum(scores) / len(scores) if scores else 0.5
        
        return quality
    
    def _evaluate_coherence(self, process: ReasoningProcess) -> float:
        """Evaluate coherence of reasoning steps"""
        if len(process.steps) < 2:
            return 1.0
        
        coherence_score = 1.0
        
        # Check if outputs match inputs of next steps
        for i in range(len(process.steps) - 1):
            current_output = process.steps[i].output_data
            next_input = process.steps[i + 1].input_data
            
            # Simple check: if keys overlap, coherence is higher
            overlap = set(current_output.keys()) & set(next_input.keys())
            if overlap:
                coherence_score += 0.1
        
        return min(coherence_score, 1.0)
    
    def _evaluate_consistency(self, process: ReasoningProcess) -> float:
        """Evaluate consistency of reasoning"""
        if not process.steps:
            return 1.0
        
        # Check for consistent confidence levels
        confidences = [step.confidence for step in process.steps]
        if not confidences:
            return 1.0
        
        avg_confidence = sum(confidences) / len(confidences)
        variance = sum((c - avg_confidence) ** 2 for c in confidences) / len(confidences)
        
        # Lower variance is better
        consistency = 1.0 - min(variance, 1.0)
        return consistency
    
    def _evaluate_efficiency(self, process: ReasoningProcess) -> float:
        """Evaluate efficiency of reasoning"""
        if not process.steps:
            return 1.0
        
        # Fewer steps is generally more efficient
        step_count = len(process.steps)
        
        if step_count <= 3:
            return 1.0
        elif step_count <= 5:
            return 0.8
        elif step_count <= 10:
            return 0.6
        else:
            return 0.4
    
    def _evaluate_confidence(self, process: ReasoningProcess) -> float:
        """Evaluate overall confidence"""
        if not process.steps:
            return 0.5
        
        confidences = [step.confidence for step in process.steps]
        return sum(confidences) / len(confidences)
    
    def _evaluate_completeness(self, process: ReasoningProcess) -> float:
        """Evaluate completeness of reasoning"""
        if not process.steps:
            return 0.5
        
        # Check if process has a clear conclusion
        if process.final_result is not None:
            return 1.0
        else:
            return 0.5
    
    def evaluate_process(self, process_id: str, evaluation_type: str = "general") -> MetaEvaluation:
        """Perform a detailed evaluation of a reasoning process"""
        if process_id not in self.processes:
            raise ValueError(f"Process {process_id} not found")
        
        process = self.processes[process_id]
        
        # Calculate score
        score = self.evaluate_process_quality(process_id)
        
        # Generate feedback
        if score >= 0.8:
            feedback = "Excellent reasoning process"
            suggestions = []
        elif score >= 0.6:
            feedback = "Good reasoning process with minor issues"
            suggestions = ["Consider improving step coherence", "Review confidence levels"]
        elif score >= 0.4:
            feedback = "Fair reasoning process with notable issues"
            suggestions = ["Improve step connections", "Increase confidence", "Reduce step count"]
        else:
            feedback = "Poor reasoning process requiring significant improvement"
            suggestions = ["Redesign reasoning flow", "Add more justification", "Review all steps"]
        
        evaluation = MetaEvaluation(
            process_id=process_id,
            evaluation_type=evaluation_type,
            score=score,
            feedback=feedback,
            suggestions=suggestions
        )
        
        self.evaluations[process_id].append(evaluation)
        
        logger.debug(f"Evaluated process {process_id}: {score:.2f}")
        return evaluation
    
    def get_process_statistics(self, process_id: str) -> Dict[str, Any]:
        """Get statistics for a specific process"""
        if process_id not in self.processes:
            return {}
        
        process = self.processes[process_id]
        
        type_counts = defaultdict(int)
        for step in process.steps:
            type_counts[step.reasoning_type.value] += 1
        
        return {
            "process_id": process_id,
            "name": process.name,
            "total_steps": len(process.steps),
            "quality": process.quality,
            "type_distribution": dict(type_counts),
            "average_confidence": (
                sum(s.confidence for s in process.steps) / len(process.steps)
                if process.steps else 0.0
            )
        }
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get meta-reasoning statistics"""
        type_counts = defaultdict(int)
        total_evaluations = sum(len(evals) for evals in self.evaluations.values())
        
        for process in self.processes.values():
            for step in process.steps:
                type_counts[step.reasoning_type.value] += 1
        
        return {
            "total_processes": len(self.processes),
            "total_steps": sum(len(p.steps) for p in self.processes.values()),
            "total_evaluations": total_evaluations,
            "type_distribution": dict(type_counts),
            "average_quality": (
                sum(p.quality for p in self.processes.values()) / len(self.processes)
                if self.processes else 0.0
            )
        }
    
    async def health_check(self) -> str:
        """Health check for the meta reasoner"""
        stats = self.get_statistics()
        return f"healthy ({stats['total_processes']} processes, {stats['total_steps']} steps)"
    
    async def shutdown(self):
        """Shutdown the meta reasoner"""
        logger.info("Meta reasoner shutting down")
