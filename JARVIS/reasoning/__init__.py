from JARVIS.reasoning.reasoning_engine import (
    ReasoningEngine,
    ReasoningChain,
    ReasoningStep,
    Hypothesis,
    InferenceType
)

# Phase 2 Advanced Reasoning Components
from JARVIS.reasoning.causal_reasoning import (
    CausalReasoner,
    CausalRelation,
    CausalStrength,
    CausalNode,
    CausalEdge,
    CausalChain
)

from JARVIS.reasoning.abductive_reasoning import (
    AbductiveReasoner,
    ExplanationType,
    ExplanationQuality,
    Observation,
    Hypothesis as AbductiveHypothesis,
    AbductiveInference
)

from JARVIS.reasoning.analogical_reasoning import (
    AnalogicalReasoner,
    SimilarityType,
    AnalogyType,
    Concept,
    Analogy
)

from JARVIS.reasoning.meta_reasoning import (
    MetaReasoner,
    ReasoningType,
    ReasoningQuality,
    ReasoningStep as MetaReasoningStep,
    ReasoningProcess,
    MetaEvaluation
)

__all__ = [
    # Original reasoning components
    'ReasoningEngine',
    'ReasoningChain',
    'ReasoningStep',
    'Hypothesis',
    'InferenceType',
    # Phase 2 components
    'CausalReasoner',
    'CausalRelation',
    'CausalStrength',
    'CausalNode',
    'CausalEdge',
    'CausalChain',
    'AbductiveReasoner',
    'ExplanationType',
    'ExplanationQuality',
    'Observation',
    'AbductiveHypothesis',
    'AbductiveInference',
    'AnalogicalReasoner',
    'SimilarityType',
    'AnalogyType',
    'Concept',
    'Analogy',
    'MetaReasoner',
    'ReasoningType',
    'ReasoningQuality',
    'MetaReasoningStep',
    'ReasoningProcess',
    'MetaEvaluation'
]
