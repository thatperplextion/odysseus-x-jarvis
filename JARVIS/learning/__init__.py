"""
Jarvis Learning - Machine learning and pattern recognition
"""

from JARVIS.learning.learning_engine import (
    LearningEngine,
    PatternType,
    Pattern,
    Prediction,
    PatternRecognizer,
    PredictiveEngine,
    OptimizationEngine,
    KnowledgeBase
)

# Phase 2 Advanced Learning Components
from JARVIS.learning.reinforcement_learning import (
    ReinforcementLearner,
    ActionType,
    RewardType,
    State,
    Action,
    Experience,
    QTableEntry
)

from JARVIS.learning.machine_learning import (
    MachineLearningEngine,
    SimpleClassifier,
    SimpleRegressor,
    ModelType,
    PredictionType,
    Feature,
    Prediction as MLPrediction,
    TrainingData
)

from JARVIS.learning.knowledge_graph import (
    KnowledgeGraph,
    RelationType,
    NodeType,
    Node,
    Edge,
    Path
)

from JARVIS.learning.adaptive_learning import (
    AdaptiveLearner,
    AdaptationType,
    PerformanceMetric,
    PerformanceData,
    Adaptation
)

__all__ = [
    # Original learning components
    'LearningEngine',
    'PatternType',
    'Pattern',
    'Prediction',
    'PatternRecognizer',
    'PredictiveEngine',
    'OptimizationEngine',
    'KnowledgeBase',
    # Phase 2 components
    'ReinforcementLearner',
    'ActionType',
    'RewardType',
    'State',
    'Action',
    'Experience',
    'QTableEntry',
    'MachineLearningEngine',
    'SimpleClassifier',
    'SimpleRegressor',
    'ModelType',
    'PredictionType',
    'Feature',
    'MLPrediction',
    'TrainingData',
    'KnowledgeGraph',
    'RelationType',
    'NodeType',
    'Node',
    'Edge',
    'Path',
    'AdaptiveLearner',
    'AdaptationType',
    'PerformanceMetric',
    'PerformanceData',
    'Adaptation'
]
