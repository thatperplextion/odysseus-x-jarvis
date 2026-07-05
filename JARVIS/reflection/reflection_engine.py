"""
Reflection Engine for Jarvis OS - Phase 1 Component
Action review, pattern extraction, and learning from past experiences
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Set, Any, Tuple
from collections import defaultdict
import json

logger = logging.getLogger(__name__)


class ReflectionType(Enum):
    """Types of reflections"""
    SUCCESS = "success"  # What went well
    FAILURE = "failure"  # What went wrong
    PATTERN = "pattern"  # Repeated patterns
    INSIGHT = "insight"  # New understanding
    IMPROVEMENT = "improvement"  # How to improve


class ReflectionTrigger(Enum):
    """Triggers for reflection"""
    TASK_COMPLETION = "task_completion"
    TASK_FAILURE = "task_failure"
    TIME_INTERVAL = "time_interval"
    MEMORY_THRESHOLD = "memory_threshold"
    MANUAL = "manual"


@dataclass
class ReflectionSession:
    """A reflection session analyzing past experiences"""
    id: str
    trigger: ReflectionTrigger
    start_time: datetime = field(default_factory=datetime.now)
    end_time: Optional[datetime] = None
    memories_analyzed: Set[str] = field(default_factory=set)
    insights_generated: List[str] = field(default_factory=list)
    patterns_identified: List[Dict[str, Any]] = field(default_factory=list)
    action_items: List[str] = field(default_factory=list)
    confidence: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "trigger": self.trigger.value,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "memories_analyzed": list(self.memories_analyzed),
            "insights_generated": self.insights_generated,
            "patterns_identified": self.patterns_identified,
            "action_items": self.action_items,
            "confidence": self.confidence
        }


@dataclass
class Pattern:
    """A pattern identified through reflection"""
    id: str
    pattern_type: str
    description: str
    occurrences: int = 0
    confidence: float = 0.0
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    related_memories: Set[str] = field(default_factory=set)
    actionable: bool = False
    suggested_actions: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "pattern_type": self.pattern_type,
            "description": self.description,
            "occurrences": self.occurrences,
            "confidence": self.confidence,
            "first_seen": self.first_seen.isoformat(),
            "last_seen": self.last_seen.isoformat(),
            "related_memories": list(self.related_memories),
            "actionable": self.actionable,
            "suggested_actions": self.suggested_actions
        }


class ReflectionEngine:
    """Reflection engine for learning from past experiences"""
    
    def __init__(self):
        self.reflection_sessions: Dict[str, ReflectionSession] = {}
        self.patterns: Dict[str, Pattern] = {}
        self.session_counter = 0
        self.pattern_counter = 0
        
        # Reflection triggers
        self.reflection_interval = timedelta(hours=6)
        self.last_reflection = datetime.now()
        
        # Pattern detection parameters
        self.min_pattern_occurrences = 3
        self.pattern_confidence_threshold = 0.7
        
        logger.info("Reflection engine initialized")
    
    async def trigger_reflection(self, trigger: ReflectionTrigger,
                                memory_system = None,
                                context: Dict[str, Any] = None) -> ReflectionSession:
        """Trigger a reflection session"""
        self.session_counter += 1
        session = ReflectionSession(
            id=f"session_{self.session_counter}",
            trigger=trigger
        )
        
        logger.info(f"Starting reflection session {session.id} triggered by {trigger.value}")
        
        try:
            # Analyze memories if memory system is provided
            if memory_system:
                await self._analyze_memories(session, memory_system, context or {})
            
            # Identify patterns
            await self._identify_patterns(session)
            
            # Generate insights
            await self._generate_insights(session)
            
            # Generate action items
            await self._generate_action_items(session)
            
            session.confidence = self._calculate_session_confidence(session)
            
        except Exception as e:
            logger.error(f"Reflection session {session.id} failed: {e}")
        
        session.end_time = datetime.now()
        self.reflection_sessions[session.id] = session
        self.last_reflection = datetime.now()
        
        logger.info(f"Reflection session {session.id} complete")
        return session
    
    async def _analyze_memories(self, session: ReflectionSession, memory_system, context: Dict[str, Any]):
        """Analyze memories for the reflection session"""
        # Get recent memories
        recent_memories = memory_system.search_memories(
            query="",
            limit=50
        )
        
        # Get memories by type based on trigger
        if session.trigger == ReflectionTrigger.TASK_FAILURE:
            # Focus on failure-related memories
            recent_memories = [m for m in recent_memories if "error" in m.content.lower() or "fail" in m.content.lower()]
        elif session.trigger == ReflectionTrigger.TASK_COMPLETION:
            # Focus on completion-related memories
            recent_memories = [m for m in recent_memories if "complete" in m.content.lower() or "success" in m.content.lower()]
        
        for memory in recent_memories:
            session.memories_analyzed.add(memory.id)
            
            # Add reflection to memory
            reflection_type = self._determine_reflection_type(memory, session.trigger)
            reflection = memory_system.add_reflection(
                memory_id=memory.id,
                reflection_type=reflection_type,
                content=f"Reflected on {memory.content[:50]}...",
                confidence=0.8,
                actionable=True
            )
            
            session.insights_generated.append(f"Reflection on memory {memory.id}: {reflection.content}")
        
        logger.info(f"Analyzed {len(session.memories_analyzed)} memories")
    
    def _determine_reflection_type(self, memory, trigger: ReflectionTrigger) -> str:
        """Determine the type of reflection for a memory"""
        content_lower = memory.content.lower()
        
        if "error" in content_lower or "fail" in content_lower:
            return ReflectionType.FAILURE.value
        elif "success" in content_lower or "complete" in content_lower:
            return ReflectionType.SUCCESS.value
        elif "pattern" in content_lower:
            return ReflectionType.PATTERN.value
        else:
            return ReflectionType.INSIGHT.value
    
    async def _identify_patterns(self, session: ReflectionSession):
        """Identify patterns in analyzed memories"""
        # Simple pattern detection (in production, use more sophisticated algorithms)
        
        # Group memories by tags
        tag_groups = defaultdict(list)
        for memory_id in session.memories_analyzed:
            # This would need access to memory objects
            pass
        
        # Look for repeated content patterns
        content_patterns = defaultdict(int)
        
        # Generate patterns from insights
        for insight in session.insights_generated:
            # Extract keywords
            words = insight.lower().split()
            for word in words:
                if len(word) > 3:  # Ignore short words
                    content_patterns[word] += 1
        
        # Create pattern objects for frequent patterns
        for word, count in content_patterns.items():
            if count >= self.min_pattern_occurrences:
                self.pattern_counter += 1
                pattern = Pattern(
                    id=f"pattern_{self.pattern_counter}",
                    pattern_type="keyword",
                    description=f"Repeated keyword: {word}",
                    occurrences=count,
                    confidence=min(1.0, count / 10.0),
                    actionable=count >= 5
                )
                
                if pattern.actionable:
                    pattern.suggested_actions = [f"Investigate significance of '{word}' pattern"]
                
                self.patterns[pattern.id] = pattern
                session.patterns_identified.append(pattern.to_dict())
        
        logger.info(f"Identified {len(session.patterns_identified)} patterns")
    
    async def _generate_insights(self, session: ReflectionSession):
        """Generate insights from the reflection session"""
        # Generate insights based on patterns
        for pattern_info in session.patterns_identified:
            if pattern_info["confidence"] > self.pattern_confidence_threshold:
                insight = f"Pattern '{pattern_info['description']}' has high confidence ({pattern_info['confidence']:.2f})"
                session.insights_generated.append(insight)
        
        # Generate general insights
        if len(session.memories_analyzed) > 10:
            session.insights_generated.append(f"Analyzed {len(session.memories_analyzed)} memories - good sample size")
        
        if session.trigger == ReflectionTrigger.TASK_FAILURE:
            session.insights_generated.append("Focus on understanding root causes of failures")
        
        logger.info(f"Generated {len(session.insights_generated)} insights")
    
    async def _generate_action_items(self, session: ReflectionSession):
        """Generate action items from the reflection session"""
        # Generate action items from patterns
        for pattern_info in session.patterns_identified:
            if pattern_info["actionable"]:
                for action in pattern_info.get("suggested_actions", []):
                    session.action_items.append(action)
        
        # Generate action items from insights
        if session.trigger == ReflectionTrigger.TASK_FAILURE:
            session.action_items.append("Review failure patterns and implement prevention strategies")
        
        if session.trigger == ReflectionTrigger.TASK_COMPLETION:
            session.action_items.append("Document successful approaches for reuse")
        
        logger.info(f"Generated {len(session.action_items)} action items")
    
    def _calculate_session_confidence(self, session: ReflectionSession) -> float:
        """Calculate overall confidence of the reflection session"""
        if not session.memories_analyzed:
            return 0.0
        
        # Confidence based on number of memories analyzed
        memory_factor = min(1.0, len(session.memories_analyzed) / 20.0)
        
        # Confidence based on patterns identified
        pattern_factor = min(1.0, len(session.patterns_identified) / 5.0)
        
        # Confidence based on action items
        action_factor = min(1.0, len(session.action_items) / 3.0)
        
        return (memory_factor * 0.4 + pattern_factor * 0.3 + action_factor * 0.3)
    
    def get_patterns(self, pattern_type: str = None, min_confidence: float = 0.0) -> List[Pattern]:
        """Get identified patterns"""
        patterns = list(self.patterns.values())
        
        if pattern_type:
            patterns = [p for p in patterns if p.pattern_type == pattern_type]
        
        patterns = [p for p in patterns if p.confidence >= min_confidence]
        
        # Sort by confidence and occurrences
        patterns.sort(key=lambda p: (p.confidence, p.occurrences), reverse=True)
        
        return patterns
    
    def get_reflection_session(self, session_id: str) -> Optional[ReflectionSession]:
        """Get a reflection session by ID"""
        return self.reflection_sessions.get(session_id)
    
    def get_recent_sessions(self, limit: int = 10) -> List[ReflectionSession]:
        """Get recent reflection sessions"""
        sessions = list(self.reflection_sessions.values())
        sessions.sort(key=lambda s: s.start_time, reverse=True)
        return sessions[:limit]
    
    async def should_reflect(self) -> Tuple[bool, ReflectionTrigger]:
        """Check if a reflection should be triggered"""
        time_since_last = datetime.now() - self.last_reflection
        
        if time_since_last >= self.reflection_interval:
            return True, ReflectionTrigger.TIME_INTERVAL
        
        return False, ReflectionTrigger.MANUAL
    
    async def health_check(self) -> str:
        """Health check for the reflection engine"""
        return f"healthy ({len(self.reflection_sessions)} sessions, {len(self.patterns)} patterns)"
    
    async def shutdown(self):
        """Shutdown the reflection engine"""
        logger.info("Reflection engine shutting down")
