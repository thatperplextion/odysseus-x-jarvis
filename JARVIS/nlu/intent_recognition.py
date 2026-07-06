"""
Intent Recognition System for Jarvis OS - Phase 2 Component
Natural Language Understanding for user commands and queries
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


class Intent(Enum):
    """Types of intents"""
    QUERY = "query"  # Information query
    COMMAND = "command"  # Execute a command
    TASK = "task"  # Perform a complex task
    ANALYSIS = "analysis"  # Analyze something
    PLANNING = "planning"  # Plan something
    REFLECTION = "reflection"  # Reflect on past actions
    CONVERSATION = "conversation"  # General conversation
    UNKNOWN = "unknown"


class IntentConfidence(Enum):
    """Confidence levels for intent recognition"""
    HIGH = 0.9
    MEDIUM = 0.7
    LOW = 0.5
    VERY_LOW = 0.3


@dataclass
class IntentMatch:
    """A matched intent with confidence"""
    intent: Intent
    confidence: float
    matched_patterns: List[str] = field(default_factory=list)
    entities: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent.value,
            "confidence": self.confidence,
            "matched_patterns": self.matched_patterns,
            "entities": self.entities,
            "metadata": self.metadata
        }


@dataclass
class IntentPattern:
    """A pattern for matching intents"""
    intent: Intent
    patterns: List[str]
    required_entities: Set[str] = field(default_factory=set)
    optional_entities: Set[str] = field(default_factory=set)
    examples: List[str] = field(default_factory=list)
    priority: int = 0  # Higher priority checked first


class IntentRecognizer:
    """Intent recognition system for natural language understanding"""
    
    def __init__(self):
        self.patterns: List[IntentPattern] = []
        self.intent_counter = 0
        self.recognition_history: List[Dict[str, Any]] = []
        
        # Initialize default patterns
        self._initialize_default_patterns()
        
        logger.info("Intent recognition system initialized")
    
    def _initialize_default_patterns(self):
        """Initialize default intent patterns"""
        
        # Query patterns
        self.patterns.append(IntentPattern(
            intent=Intent.QUERY,
            patterns=[
                r"what is",
                r"what's",
                r"how do",
                r"how does",
                r"tell me about",
                r"explain",
                r"describe",
                r"show me",
                r"display",
                r"get",
                r"find",
                r"search",
                r"look up"
            ],
            examples=[
                "What is the weather today?",
                "How do I create a new user?",
                "Tell me about the project structure",
                "Show me the recent logs"
            ],
            priority=10
        ))
        
        # Command patterns
        self.patterns.append(IntentPattern(
            intent=Intent.COMMAND,
            patterns=[
                r"run",
                r"execute",
                r"start",
                r"stop",
                r"restart",
                r"kill",
                r"delete",
                r"remove",
                r"create",
                r"add",
                r"update",
                r"modify",
                r"change",
                r"set",
                r"enable",
                r"disable"
            ],
            examples=[
                "Run the backup script",
                "Stop the server",
                "Create a new user",
                "Enable debug mode"
            ],
            priority=10
        ))
        
        # Task patterns
        self.patterns.append(IntentPattern(
            intent=Intent.TASK,
            patterns=[
                r"help me",
                r"assist me",
                r"perform",
                r"complete",
                r"do",
                r"handle",
                r"manage",
                r"organize",
                r"coordinate"
            ],
            examples=[
                "Help me analyze the codebase",
                "Perform a security audit",
                "Complete the deployment"
            ],
            priority=8
        ))
        
        # Analysis patterns
        self.patterns.append(IntentPattern(
            intent=Intent.ANALYSIS,
            patterns=[
                r"analyze",
                r"evaluate",
                r"assess",
                r"review",
                r"audit",
                r"inspect",
                r"examine",
                r"check",
                r"verify",
                r"validate"
            ],
            examples=[
                "Analyze the performance",
                "Evaluate the code quality",
                "Review the security"
            ],
            priority=9
        ))
        
        # Planning patterns
        self.patterns.append(IntentPattern(
            intent=Intent.PLANNING,
            patterns=[
                r"plan",
                r"schedule",
                r"organize",
                r"design",
                r"architect",
                r"strategy",
                r"roadmap",
                r"timeline"
            ],
            examples=[
                "Plan the deployment",
                "Schedule the meeting",
                "Design the architecture"
            ],
            priority=8
        ))
        
        # Reflection patterns
        self.patterns.append(IntentPattern(
            intent=Intent.REFLECTION,
            patterns=[
                r"reflect",
                r"review past",
                r"what went wrong",
                r"what went well",
                r"learn from",
                r"improve",
                r"optimize",
                r"better"
            ],
            examples=[
                "Reflect on the last deployment",
                "What went wrong with the test?",
                "How can we improve performance?"
            ],
            priority=7
        ))
        
        # Conversation patterns
        self.patterns.append(IntentPattern(
            intent=Intent.CONVERSATION,
            patterns=[
                r"hello",
                r"hi",
                r"hey",
                r"good morning",
                r"good afternoon",
                r"good evening",
                r"thanks",
                r"thank you",
                r"you're welcome",
                r"how are you",
                r"what's up"
            ],
            examples=[
                "Hello Jarvis",
                "Thanks for the help",
                "How are you doing?"
            ],
            priority=5
        ))
        
        # Sort by priority (higher first)
        self.patterns.sort(key=lambda p: p.priority, reverse=True)
    
    def add_pattern(self, intent: Intent, patterns: List[str],
                   examples: List[str] = None, priority: int = 0) -> IntentPattern:
        """Add a custom intent pattern"""
        pattern = IntentPattern(
            intent=intent,
            patterns=patterns,
            examples=examples or [],
            priority=priority
        )
        self.patterns.append(pattern)
        self.patterns.sort(key=lambda p: p.priority, reverse=True)
        logger.info(f"Added pattern for intent: {intent.value}")
        return pattern
    
    def recognize_intent(self, text: str, context: Dict[str, Any] = None) -> IntentMatch:
        """Recognize the intent from text"""
        text_lower = text.lower()
        matched_intents = []
        
        # Check each pattern
        for pattern in self.patterns:
            matches = []
            for pattern_str in pattern.patterns:
                if re.search(pattern_str, text_lower):
                    matches.append(pattern_str)
            
            if matches:
                confidence = self._calculate_confidence(matches, text_lower, pattern)
                matched_intents.append((pattern, confidence, matches))
        
        # Sort by confidence
        matched_intents.sort(key=lambda x: x[1], reverse=True)
        
        if matched_intents:
            best_pattern, confidence, matches = matched_intents[0]
            
            # Extract entities
            entities = self._extract_entities(text, best_pattern)
            
            intent_match = IntentMatch(
                intent=best_pattern.intent,
                confidence=confidence,
                matched_patterns=matches,
                entities=entities,
                metadata={"context": context or {}}
            )
            
            # Record in history
            self.recognition_history.append({
                "text": text,
                "intent": intent_match.to_dict(),
                "timestamp": datetime.now().isoformat()
            })
            
            logger.info(f"Recognized intent: {best_pattern.intent.value} (confidence: {confidence:.2f})")
            return intent_match
        
        # No match found
        return IntentMatch(
            intent=Intent.UNKNOWN,
            confidence=0.0,
            metadata={"context": context or {}}
        )
    
    def _calculate_confidence(self, matches: List[str], text: str, pattern: IntentPattern) -> float:
        """Calculate confidence score for intent match"""
        base_confidence = 0.5
        
        # More matches = higher confidence
        match_bonus = min(len(matches) * 0.1, 0.3)
        
        # Pattern priority affects confidence
        priority_bonus = min(pattern.priority * 0.02, 0.2)
        
        # Check for example similarity
        example_bonus = 0.0
        for example in pattern.examples:
            if self._text_similarity(text.lower(), example.lower()) > 0.7:
                example_bonus = 0.2
                break
        
        confidence = base_confidence + match_bonus + priority_bonus + example_bonus
        return min(confidence, 1.0)
    
    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate simple text similarity"""
        words1 = set(text1.split())
        words2 = set(text2.split())
        
        if not words1 or not words2:
            return 0.0
        
        intersection = words1.intersection(words2)
        union = words1.union(words2)
        
        return len(intersection) / len(union)
    
    def _extract_entities(self, text: str, pattern: IntentPattern) -> Dict[str, Any]:
        """Extract entities from text"""
        entities = {}
        
        # Common entity patterns
        entity_patterns = {
            "file_path": r'[\w/\\.-]+\.\w+',
            "url": r'https?://[^\s]+',
            "email": r'[\w\.-]+@[\w\.-]+\.\w+',
            "number": r'\d+',
            "time": r'\d+:\d+',
            "date": r'\d{4}-\d{2}-\d{2}|\d{2}/\d{2}/\d{4}',
            "quoted_text": r'"([^"]+)"|\'([^\']+)\''
        }
        
        for entity_type, pattern_str in entity_patterns.items():
            matches = re.findall(pattern_str, text)
            if matches:
                entities[entity_type] = matches
        
        return entities
    
    def get_recognition_stats(self) -> Dict[str, Any]:
        """Get statistics about intent recognition"""
        intent_counts = defaultdict(int)
        confidence_sum = defaultdict(float)
        
        for entry in self.recognition_history:
            intent = entry["intent"]["intent"]
            confidence = entry["intent"]["confidence"]
            intent_counts[intent] += 1
            confidence_sum[intent] += confidence
        
        avg_confidence = {}
        for intent in intent_counts:
            avg_confidence[intent] = confidence_sum[intent] / intent_counts[intent]
        
        return {
            "total_recognitions": len(self.recognition_history),
            "intent_distribution": dict(intent_counts),
            "average_confidence": avg_confidence,
            "total_patterns": len(self.patterns)
        }
    
    async def health_check(self) -> str:
        """Health check for the intent recognition system"""
        stats = self.get_recognition_stats()
        return f"healthy ({stats['total_patterns']} patterns, {stats['total_recognitions']} recognitions)"
    
    async def shutdown(self):
        """Shutdown the intent recognition system"""
        logger.info("Intent recognition system shutting down")
