"""
Adaptive Learning System for Jarvis OS - Phase 2 Component
Dynamic learning and adaptation based on performance and feedback
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Tuple
from collections import defaultdict

logger = logging.getLogger(__name__)


class AdaptationType(Enum):
    """Types of adaptations"""
    PARAMETER_TUNING = "parameter_tuning"
    STRATEGY_SWITCHING = "strategy_switching"
    MODEL_UPDATE = "model_update"
    KNOWLEDGE_UPDATE = "knowledge_update"
    BEHAVIOR_MODIFICATION = "behavior_modification"


class PerformanceMetric(Enum):
    """Types of performance metrics"""
    ACCURACY = "accuracy"
    PRECISION = "precision"
    RECALL = "recall"
    F1_SCORE = "f1_score"
    EFFICIENCY = "efficiency"
    USER_SATISFACTION = "user_satisfaction"
    ERROR_RATE = "error_rate"
    RESPONSE_TIME = "response_time"


@dataclass
class PerformanceData:
    """Performance data for tracking"""
    metric: PerformanceMetric
    value: float
    timestamp: datetime = field(default_factory=datetime.now)
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric": self.metric.value,
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
            "context": self.context
        }


@dataclass
class Adaptation:
    """An adaptation applied to the system"""
    adaptation_type: AdaptationType
    target: str
    parameters: Dict[str, Any]
    reason: str
    timestamp: datetime = field(default_factory=datetime.now)
    effectiveness: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "adaptation_type": self.adaptation_type.value,
            "target": self.target,
            "parameters": self.parameters,
            "reason": self.reason,
            "timestamp": self.timestamp.isoformat(),
            "effectiveness": self.effectiveness
        }


class AdaptiveLearner:
    """Adaptive learning system for dynamic optimization"""
    
    def __init__(self, adaptation_threshold: float = 0.1,
                 performance_window: int = 100):
        self.adaptation_threshold = adaptation_threshold
        self.performance_window = performance_window
        
        # Performance history
        self.performance_history: Dict[PerformanceMetric, List[PerformanceData]] = defaultdict(list)
        
        # Adaptation history
        self.adaptation_history: List[Adaptation] = []
        
        # Current parameters
        self.current_parameters: Dict[str, Any] = {}
        
        # Performance thresholds
        self.performance_thresholds: Dict[PerformanceMetric, float] = {
            PerformanceMetric.ACCURACY: 0.8,
            PerformanceMetric.PRECISION: 0.8,
            PerformanceMetric.RECALL: 0.8,
            PerformanceMetric.F1_SCORE: 0.8,
            PerformanceMetric.EFFICIENCY: 0.7,
            PerformanceMetric.USER_SATISFACTION: 0.7,
            PerformanceMetric.ERROR_RATE: 0.2,
            PerformanceMetric.RESPONSE_TIME: 1.0
        }
        
        logger.info("Adaptive learning system initialized")
    
    def record_performance(self, metric: PerformanceMetric, value: float,
                          context: Dict[str, Any] = None):
        """Record performance data"""
        data = PerformanceData(
            metric=metric,
            value=value,
            context=context or {}
        )
        
        self.performance_history[metric].append(data)
        
        # Maintain window size
        if len(self.performance_history[metric]) > self.performance_window:
            self.performance_history[metric].pop(0)
        
        logger.debug(f"Recorded performance: {metric.value} = {value:.3f}")
    
    def get_performance_summary(self, metric: PerformanceMetric) -> Dict[str, float]:
        """Get summary statistics for a metric"""
        history = self.performance_history[metric]
        
        if not history:
            return {"average": 0.0, "min": 0.0, "max": 0.0, "count": 0}
        
        values = [d.value for d in history]
        
        return {
            "average": sum(values) / len(values),
            "min": min(values),
            "max": max(values),
            "count": len(values),
            "trend": self._calculate_trend(values)
        }
    
    def _calculate_trend(self, values: List[float]) -> float:
        """Calculate trend (positive = improving, negative = declining)"""
        if len(values) < 2:
            return 0.0
        
        # Simple linear regression slope
        n = len(values)
        x = list(range(n))
        sum_x = sum(x)
        sum_y = sum(values)
        sum_xy = sum(x[i] * values[i] for i in range(n))
        sum_x2 = sum(x[i] ** 2 for i in range(n))
        
        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x ** 2)
        return slope
    
    def should_adapt(self, metric: PerformanceMetric) -> bool:
        """Determine if adaptation is needed for a metric"""
        summary = self.get_performance_summary(metric)
        threshold = self.performance_thresholds.get(metric, 0.5)
        
        # Check if average is below threshold
        if summary["average"] < threshold - self.adaptation_threshold:
            return True
        
        # Check if trend is declining
        if summary["trend"] < -self.adaptation_threshold:
            return True
        
        return False
    
    def adapt_parameter(self, parameter_name: str, current_value: float,
                      metric: PerformanceMetric) -> Adaptation:
        """Adapt a parameter based on performance"""
        summary = self.get_performance_summary(metric)
        trend = summary["trend"]
        
        # Calculate adjustment
        if trend < 0:
            # Performance declining, increase parameter
            adjustment = current_value * 0.1
            new_value = current_value + adjustment
            reason = f"Performance declining (trend: {trend:.3f}), increasing parameter"
        else:
            # Performance improving, fine-tune parameter
            adjustment = current_value * 0.05
            new_value = current_value - adjustment
            reason = f"Performance improving (trend: {trend:.3f}), fine-tuning parameter"
        
        # Create adaptation
        adaptation = Adaptation(
            adaptation_type=AdaptationType.PARAMETER_TUNING,
            target=parameter_name,
            parameters={"old_value": current_value, "new_value": new_value},
            reason=reason
        )
        
        self.adaptation_history.append(adaptation)
        self.current_parameters[parameter_name] = new_value
        
        logger.info(f"Adapted parameter {parameter_name}: {current_value:.3f} -> {new_value:.3f}")
        return adaptation
    
    def switch_strategy(self, current_strategy: str, 
                       available_strategies: List[str],
                       metric: PerformanceMetric) -> Adaptation:
        """Switch to a different strategy based on performance"""
        summary = self.get_performance_summary(metric)
        
        if not available_strategies:
            raise ValueError("No available strategies to switch to")
        
        # Select best strategy (simple: rotate through available)
        current_index = available_strategies.index(current_strategy) if current_strategy in available_strategies else -1
        next_index = (current_index + 1) % len(available_strategies)
        new_strategy = available_strategies[next_index]
        
        adaptation = Adaptation(
            adaptation_type=AdaptationType.STRATEGY_SWITCHING,
            target="strategy",
            parameters={"old_strategy": current_strategy, "new_strategy": new_strategy},
            reason=f"Performance {summary['average']:.3f} below threshold, switching strategy"
        )
        
        self.adaptation_history.append(adaptation)
        
        logger.info(f"Switched strategy: {current_strategy} -> {new_strategy}")
        return adaptation
    
    def evaluate_adaptation(self, adaptation: Adaptation, metric: PerformanceMetric,
                          before_value: float, after_value: float) -> float:
        """Evaluate the effectiveness of an adaptation"""
        improvement = after_value - before_value
        adaptation.effectiveness = improvement
        
        logger.info(f"Evaluated adaptation: {adaptation.adaptation_type.value}, effectiveness: {improvement:.3f}")
        return improvement
    
    def get_adaptation_summary(self) -> Dict[str, Any]:
        """Get summary of adaptations"""
        adaptation_counts = defaultdict(int)
        effectiveness_sum = defaultdict(float)
        
        for adaptation in self.adaptation_history:
            adaptation_counts[adaptation.adaptation_type.value] += 1
            effectiveness_sum[adaptation.adaptation_type.value] += adaptation.effectiveness
        
        avg_effectiveness = {}
        for adaptation_type in adaptation_counts:
            avg_effectiveness[adaptation_type] = (
                effectiveness_sum[adaptation_type] / adaptation_counts[adaptation_type]
            )
        
        return {
            "total_adaptations": len(self.adaptation_history),
            "adaptation_distribution": dict(adaptation_counts),
            "average_effectiveness": avg_effectiveness,
            "current_parameters": self.current_parameters
        }
    
    def get_all_performance_summaries(self) -> Dict[str, Dict[str, float]]:
        """Get performance summaries for all metrics"""
        summaries = {}
        for metric in PerformanceMetric:
            summaries[metric.value] = self.get_performance_summary(metric)
        return summaries
    
    def set_performance_threshold(self, metric: PerformanceMetric, threshold: float):
        """Set performance threshold for a metric"""
        self.performance_thresholds[metric] = threshold
        logger.debug(f"Set threshold for {metric.value}: {threshold}")
    
    def auto_adapt(self) -> List[Adaptation]:
        """Automatically adapt based on all performance metrics"""
        adaptations = []
        
        for metric in PerformanceMetric:
            if self.should_adapt(metric):
                # Determine adaptation type based on metric
                if metric in [PerformanceMetric.ACCURACY, PerformanceMetric.PRECISION, 
                            PerformanceMetric.RECALL, PerformanceMetric.F1_SCORE]:
                    # Model performance issue - suggest model update
                    adaptation = Adaptation(
                        adaptation_type=AdaptationType.MODEL_UPDATE,
                        target="model",
                        parameters={"metric": metric.value},
                        reason=f"{metric.value} below threshold"
                    )
                    adaptations.append(adaptation)
                
                elif metric == PerformanceMetric.EFFICIENCY:
                    # Efficiency issue - suggest parameter tuning
                    adaptation = Adaptation(
                        adaptation_type=AdaptationType.PARAMETER_TUNING,
                        target="efficiency_parameters",
                        parameters={"metric": metric.value},
                        reason=f"{metric.value} below threshold"
                    )
                    adaptations.append(adaptation)
                
                elif metric == PerformanceMetric.USER_SATISFACTION:
                    # User satisfaction issue - suggest behavior modification
                    adaptation = Adaptation(
                        adaptation_type=AdaptationType.BEHAVIOR_MODIFICATION,
                        target="behavior",
                        parameters={"metric": metric.value},
                        reason=f"{metric.value} below threshold"
                    )
                    adaptations.append(adaptation)
        
        if adaptations:
            logger.info(f"Auto-adaptation: {len(adaptations)} adaptations suggested")
        
        return adaptations
    
    async def health_check(self) -> str:
        """Health check for the adaptive learning system"""
        summary = self.get_adaptation_summary()
        perf_summaries = self.get_all_performance_summaries()
        return f"healthy ({summary['total_adaptations']} adaptations, {len(perf_summaries)} metrics tracked)"
    
    async def shutdown(self):
        """Shutdown the adaptive learning system"""
        logger.info("Adaptive learning system shutting down")
