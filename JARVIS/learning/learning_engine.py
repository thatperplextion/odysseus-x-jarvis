"""
Jarvis Learning Engine - Machine learning and pattern recognition
Adapts and improves from user behavior and system patterns
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from enum import Enum
from dataclasses import dataclass, field
from collections import defaultdict, Counter
import json
import statistics

logger = logging.getLogger(__name__)


class PatternType(Enum):
    """Types of patterns to recognize"""
    USER_BEHAVIOR = "user_behavior"
    SYSTEM_USAGE = "system_usage"
    COMMAND_FREQUENCY = "command_frequency"
    TIME_PATTERNS = "time_patterns"
    ERROR_PATTERNS = "error_patterns"


@dataclass
class Pattern:
    """Represents a recognized pattern"""
    id: str
    type: PatternType
    pattern_data: Dict[str, Any]
    confidence: float  # 0.0 - 1.0
    first_observed: datetime = field(default_factory=datetime.now)
    last_observed: datetime = field(default_factory=datetime.now)
    occurrence_count: int = 0


@dataclass
class Prediction:
    """Represents a prediction based on patterns"""
    type: str
    prediction: Any
    confidence: float
    based_on_pattern: str
    timestamp: datetime = field(default_factory=datetime.now)


class PatternRecognizer:
    """Recognizes patterns in data"""
    
    def __init__(self):
        self.patterns: Dict[str, Pattern] = {}
        self.observation_history: List[Dict[str, Any]] = []
        self.max_history = 10000
    
    def add_observation(self, observation_type: str, data: Dict[str, Any]):
        """Add an observation for pattern recognition"""
        observation = {
            'type': observation_type,
            'data': data,
            'timestamp': datetime.now().isoformat()
        }
        
        self.observation_history.append(observation)
        
        # Trim history
        if len(self.observation_history) > self.max_history:
            self.observation_history = self.observation_history[-self.max_history:]
        
        # Try to recognize patterns
        self._recognize_patterns(observation_type, data)
    
    def _recognize_patterns(self, observation_type: str, data: Dict[str, Any]):
        """Attempt to recognize patterns in new observation"""
        if observation_type == 'command':
            self._recognize_command_patterns(data)
        elif observation_type == 'system_metric':
            self._recognize_system_patterns(data)
        elif observation_type == 'error':
            self._recognize_error_patterns(data)
        elif observation_type == 'user_activity':
            self._recognize_behavior_patterns(data)
    
    def _recognize_command_patterns(self, data: Dict[str, Any]):
        """Recognize patterns in command usage"""
        command = data.get('command', '')
        context = data.get('context', {})
        
        # Command frequency pattern
        pattern_key = f"cmd_freq_{command}"
        if pattern_key in self.patterns:
            pattern = self.patterns[pattern_key]
            pattern.occurrence_count += 1
            pattern.last_observed = datetime.now()
            
            # Update confidence based on frequency
            pattern.confidence = min(1.0, pattern.occurrence_count / 10.0)
        else:
            self.patterns[pattern_key] = Pattern(
                id=pattern_key,
                type=PatternType.COMMAND_FREQUENCY,
                pattern_data={'command': command, 'context': context},
                confidence=0.1,
                occurrence_count=1
            )
    
    def _recognize_system_patterns(self, data: Dict[str, Any]):
        """Recognize patterns in system metrics"""
        cpu = data.get('cpu_percent', 0)
        memory = data.get('memory_percent', 0)
        hour = datetime.now().hour
        
        # Time-based usage patterns
        time_pattern_key = f"time_usage_{hour}"
        if time_pattern_key in self.patterns:
            pattern = self.patterns[time_pattern_key]
            pattern.pattern_data['avg_cpu'] = (
                pattern.pattern_data.get('avg_cpu', cpu) * pattern.occurrence_count + cpu
            ) / (pattern.occurrence_count + 1)
            pattern.pattern_data['avg_memory'] = (
                pattern.pattern_data.get('avg_memory', memory) * pattern.occurrence_count + memory
            ) / (pattern.occurrence_count + 1)
            pattern.occurrence_count += 1
            pattern.last_observed = datetime.now()
            pattern.confidence = min(1.0, pattern.occurrence_count / 20.0)
        else:
            self.patterns[time_pattern_key] = Pattern(
                id=time_pattern_key,
                type=PatternType.TIME_PATTERNS,
                pattern_data={'hour': hour, 'avg_cpu': cpu, 'avg_memory': memory},
                confidence=0.1,
                occurrence_count=1
            )
    
    def _recognize_error_patterns(self, data: Dict[str, Any]):
        """Recognize patterns in errors"""
        error_type = data.get('error_type', '')
        error_message = data.get('error_message', '')
        
        # Error frequency pattern
        error_pattern_key = f"error_{error_type}"
        if error_pattern_key in self.patterns:
            pattern = self.patterns[error_pattern_key]
            pattern.occurrence_count += 1
            pattern.last_observed = datetime.now()
            pattern.confidence = min(1.0, pattern.occurrence_count / 5.0)
        else:
            self.patterns[error_pattern_key] = Pattern(
                id=error_pattern_key,
                type=PatternType.ERROR_PATTERNS,
                pattern_data={'error_type': error_type, 'error_message': error_message},
                confidence=0.2,
                occurrence_count=1
            )
    
    def _recognize_behavior_patterns(self, data: Dict[str, Any]):
        """Recognize user behavior patterns"""
        action = data.get('action', '')
        time_of_day = datetime.now().hour
        
        # Time-based behavior patterns
        behavior_pattern_key = f"behavior_{action}_{time_of_day}"
        if behavior_pattern_key in self.patterns:
            pattern = self.patterns[behavior_pattern_key]
            pattern.occurrence_count += 1
            pattern.last_observed = datetime.now()
            pattern.confidence = min(1.0, pattern.occurrence_count / 10.0)
        else:
            self.patterns[behavior_pattern_key] = Pattern(
                id=behavior_pattern_key,
                type=PatternType.USER_BEHAVIOR,
                pattern_data={'action': action, 'time_of_day': time_of_day},
                confidence=0.1,
                occurrence_count=1
            )
    
    def get_patterns(self, pattern_type: PatternType = None, 
                    min_confidence: float = 0.5) -> List[Pattern]:
        """Get recognized patterns"""
        patterns = list(self.patterns.values())
        
        if pattern_type:
            patterns = [p for p in patterns if p.type == pattern_type]
        
        patterns = [p for p in patterns if p.confidence >= min_confidence]
        
        return sorted(patterns, key=lambda p: p.confidence, reverse=True)


class PredictiveEngine:
    """Makes predictions based on recognized patterns"""
    
    def __init__(self, pattern_recognizer: PatternRecognizer):
        self.pattern_recognizer = pattern_recognizer
        self.predictions: List[Prediction] = []
        self.max_predictions = 100
    
    def predict_next_command(self, context: Dict[str, Any]) -> Optional[Prediction]:
        """Predict the next command based on context"""
        command_patterns = self.pattern_recognizer.get_patterns(
            PatternType.COMMAND_FREQUENCY,
            min_confidence=0.3
        )
        
        if not command_patterns:
            return None
        
        # Get most likely command
        top_pattern = command_patterns[0]
        command = top_pattern.pattern_data.get('command')
        
        prediction = Prediction(
            type='next_command',
            prediction=command,
            confidence=top_pattern.confidence,
            based_on_pattern=top_pattern.id
        )
        
        self._add_prediction(prediction)
        return prediction
    
    def predict_system_load(self, time_horizon: int = 60) -> Optional[Prediction]:
        """Predict system load in the future"""
        current_hour = datetime.now().hour
        future_hour = (current_hour + time_horizon // 60) % 24
        
        time_patterns = self.pattern_recognizer.get_patterns(
            PatternType.TIME_PATTERNS,
            min_confidence=0.3
        )
        
        # Find pattern for future hour
        future_pattern = None
        for pattern in time_patterns:
            if pattern.pattern_data.get('hour') == future_hour:
                future_pattern = pattern
                break
        
        if not future_pattern:
            return None
        
        prediction = Prediction(
            type='system_load',
            prediction={
                'cpu_percent': future_pattern.pattern_data.get('avg_cpu', 0),
                'memory_percent': future_pattern.pattern_data.get('avg_memory', 0)
            },
            confidence=future_pattern.confidence,
            based_on_pattern=future_pattern.id
        )
        
        self._add_prediction(prediction)
        return prediction
    
    def predict_user_action(self, context: Dict[str, Any]) -> Optional[Prediction]:
        """Predict user action based on behavior patterns"""
        current_hour = datetime.now().hour
        
        behavior_patterns = self.pattern_recognizer.get_patterns(
            PatternType.USER_BEHAVIOR,
            min_confidence=0.3
        )
        
        # Find patterns for current time
        relevant_patterns = [
            p for p in behavior_patterns
            if p.pattern_data.get('time_of_day') == current_hour
        ]
        
        if not relevant_patterns:
            return None
        
        top_pattern = relevant_patterns[0]
        action = top_pattern.pattern_data.get('action')
        
        prediction = Prediction(
            type='user_action',
            prediction=action,
            confidence=top_pattern.confidence,
            based_on_pattern=top_pattern.id
        )
        
        self._add_prediction(prediction)
        return prediction
    
    def _add_prediction(self, prediction: Prediction):
        """Add a prediction to history"""
        self.predictions.append(prediction)
        
        # Trim predictions
        if len(self.predictions) > self.max_predictions:
            self.predictions = self.predictions[-self.max_predictions:]
    
    def get_recent_predictions(self, limit: int = 20) -> List[Prediction]:
        """Get recent predictions"""
        return self.predictions[-limit:]


class OptimizationEngine:
    """Optimizes system performance based on learned patterns"""
    
    def __init__(self, pattern_recognizer: PatternRecognizer):
        self.pattern_recognizer = pattern_recognizer
        self.optimizations_applied: List[Dict[str, Any]] = []
    
    def suggest_optimizations(self) -> List[Dict[str, Any]]:
        """Suggest optimizations based on patterns"""
        suggestions = []
        
        # Check for high CPU usage patterns
        time_patterns = self.pattern_recognizer.get_patterns(
            PatternType.TIME_PATTERNS,
            min_confidence=0.5
        )
        
        for pattern in time_patterns:
            avg_cpu = pattern.pattern_data.get('avg_cpu', 0)
            if avg_cpu > 80:
                suggestions.append({
                    'type': 'cpu_optimization',
                    'pattern_id': pattern.id,
                    'suggestion': f"Schedule heavy tasks outside hour {pattern.pattern_data.get('hour')}",
                    'priority': 'high' if avg_cpu > 90 else 'medium'
                })
        
        # Check for frequent errors
        error_patterns = self.pattern_recognizer.get_patterns(
            PatternType.ERROR_PATTERNS,
            min_confidence=0.4
        )
        
        for pattern in error_patterns:
            if pattern.occurrence_count > 3:
                suggestions.append({
                    'type': 'error_resolution',
                    'pattern_id': pattern.id,
                    'suggestion': f"Investigate recurring error: {pattern.pattern_data.get('error_type')}",
                    'priority': 'high'
                })
        
        return suggestions
    
    def apply_optimization(self, optimization: Dict[str, Any]) -> bool:
        """Apply an optimization"""
        # In a real implementation, this would actually apply the optimization
        optimization['applied_at'] = datetime.now().isoformat()
        optimization['status'] = 'applied'
        self.optimizations_applied.append(optimization)
        
        logger.info(f"Applied optimization: {optimization['type']}")
        return True


class KnowledgeBase:
    """Builds domain-specific knowledge from experience"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.knowledge_file = data_dir / "knowledge_base.json"
        self.knowledge: Dict[str, Any] = {}
        
        self._load_knowledge()
    
    def _load_knowledge(self):
        """Load knowledge from disk"""
        if self.knowledge_file.exists():
            try:
                with open(self.knowledge_file, 'r') as f:
                    self.knowledge = json.load(f)
                logger.info("Loaded knowledge base")
            except Exception as e:
                logger.error(f"Failed to load knowledge base: {e}", exc_info=True)
    
    def _save_knowledge(self):
        """Save knowledge to disk"""
        try:
            with open(self.knowledge_file, 'w') as f:
                json.dump(self.knowledge, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save knowledge base: {e}", exc_info=True)
    
    def add_fact(self, category: str, fact: str, confidence: float = 1.0):
        """Add a fact to the knowledge base"""
        if category not in self.knowledge:
            self.knowledge[category] = []
        
        self.knowledge[category].append({
            'fact': fact,
            'confidence': confidence,
            'learned_at': datetime.now().isoformat()
        })
        
        self._save_knowledge()
    
    def get_facts(self, category: str = None, 
                 min_confidence: float = 0.5) -> List[Dict[str, Any]]:
        """Get facts from knowledge base"""
        if category:
            facts = self.knowledge.get(category, [])
        else:
            facts = []
            for cat_facts in self.knowledge.values():
                facts.extend(cat_facts)
        
        return [f for f in facts if f['confidence'] >= min_confidence]
    
    def query(self, query: str) -> List[Dict[str, Any]]:
        """Query the knowledge base"""
        results = []
        query_lower = query.lower()
        
        for category, facts in self.knowledge.items():
            for fact_entry in facts:
                if query_lower in fact_entry['fact'].lower():
                    results.append({
                        'category': category,
                        'fact': fact_entry['fact'],
                        'confidence': fact_entry['confidence']
                    })
        
        return results


class LearningEngine:
    """Main learning engine - coordinates pattern recognition, prediction, and optimization"""
    
    def __init__(self, config: Dict[str, Any], data_dir: Path):
        self.config = config
        self.data_dir = data_dir
        self.state = "initializing"
        
        # Initialize components
        self.pattern_recognizer = PatternRecognizer()
        self.predictive_engine = PredictiveEngine(self.pattern_recognizer)
        self.optimization_engine = OptimizationEngine(self.pattern_recognizer)
        self.knowledge_base = KnowledgeBase(data_dir)
        
        # Learning metrics
        self.metrics = {
            'observations_processed': 0,
            'patterns_recognized': 0,
            'predictions_made': 0,
            'optimizations_applied': 0
        }
        
        logger.info("Learning engine initialized")
    
    async def initialize(self):
        """Initialize learning engine"""
        logger.info("Initializing learning engine...")
        
        # Start periodic pattern analysis
        asyncio.create_task(self._periodic_analysis())
        
        self.state = "running"
        logger.info("Learning engine ready")
    
    async def add_observation(self, observation_type: str, data: Dict[str, Any]):
        """Add an observation for learning"""
        self.pattern_recognizer.add_observation(observation_type, data)
        self.metrics['observations_processed'] += 1
    
    async def _periodic_analysis(self):
        """Perform periodic analysis and optimization"""
        while self.state == "running":
            try:
                # Update pattern counts
                self.metrics['patterns_recognized'] = len(self.pattern_recognizer.patterns)
                
                # Check for optimization opportunities
                suggestions = self.optimization_engine.suggest_optimizations()
                
                # Log suggestions
                if suggestions:
                    logger.info(f"Found {len(suggestions)} optimization suggestions")
                
                await asyncio.sleep(300)  # Analyze every 5 minutes
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in periodic analysis: {e}", exc_info=True)
                await asyncio.sleep(60)
    
    def get_patterns(self, pattern_type: str = None, 
                    min_confidence: float = 0.5) -> List[Pattern]:
        """Get recognized patterns"""
        if pattern_type:
            try:
                pattern_enum = PatternType(pattern_type)
                return self.pattern_recognizer.get_patterns(pattern_enum, min_confidence)
            except ValueError:
                return []
        return self.pattern_recognizer.get_patterns(min_confidence=min_confidence)
    
    def predict(self, prediction_type: str, 
               context: Dict[str, Any] = None) -> Optional[Prediction]:
        """Make a prediction"""
        context = context or {}
        
        if prediction_type == 'next_command':
            prediction = self.predictive_engine.predict_next_command(context)
        elif prediction_type == 'system_load':
            prediction = self.predictive_engine.predict_system_load()
        elif prediction_type == 'user_action':
            prediction = self.predictive_engine.predict_user_action(context)
        else:
            return None
        
        if prediction:
            self.metrics['predictions_made'] += 1
        
        return prediction
    
    def get_optimization_suggestions(self) -> List[Dict[str, Any]]:
        """Get optimization suggestions"""
        return self.optimization_engine.suggest_optimizations()
    
    def apply_optimization(self, optimization: Dict[str, Any]) -> bool:
        """Apply an optimization"""
        result = self.optimization_engine.apply_optimization(optimization)
        if result:
            self.metrics['optimizations_applied'] += 1
        return result
    
    def add_knowledge(self, category: str, fact: str, confidence: float = 1.0):
        """Add knowledge to the knowledge base"""
        self.knowledge_base.add_fact(category, fact, confidence)
    
    def query_knowledge(self, query: str) -> List[Dict[str, Any]]:
        """Query the knowledge base"""
        return self.knowledge_base.query(query)
    
    async def health_check(self) -> str:
        """Perform health check"""
        try:
            # Check if we can add and retrieve knowledge
            test_fact = f"test_{datetime.now().timestamp()}"
            self.knowledge_base.add_fact('test', test_fact, 0.5)
            
            results = self.knowledge_base.query(test_fact)
            if results:
                return "healthy"
            
            return "unhealthy: knowledge base test failed"
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return "unhealthy"
    
    def get_status(self) -> Dict[str, Any]:
        """Get learning engine status"""
        return {
            'state': self.state,
            'metrics': self.metrics,
            'patterns_recognized': len(self.pattern_recognizer.patterns),
            'predictions_available': len(self.predictive_engine.predictions),
            'knowledge_entries': sum(len(facts) for facts in self.knowledge_base.knowledge.values())
        }
    
    async def shutdown(self):
        """Shutdown learning engine"""
        logger.info("Shutting down learning engine...")
        self.state = "shutting_down"
        
        # Save knowledge
        self.knowledge_base._save_knowledge()
        
        logger.info("Learning engine shutdown complete")
