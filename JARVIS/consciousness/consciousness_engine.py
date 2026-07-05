"""
Jarvis Consciousness Engine - AI personality and decision-making layer
Defines Jarvis character, behavior, and autonomous decision-making
"""

import asyncio
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
from enum import Enum
import json
import random

logger = logging.getLogger(__name__)


class PersonalityType(Enum):
    """Available personality types"""
    JARVIS_STANDARD = "jarvis_standard"
    JARVIS_PROFESSIONAL = "jarvis_professional"
    JARVIS_FRIENDLY = "jarvis_friendly"
    JARVIS_MINIMAL = "jarvis_minimal"
    CUSTOM = "custom"


class EmotionalState(Enum):
    """Emotional states for Jarvis"""
    NEUTRAL = "neutral"
    HAPPY = "happy"
    CONCERNED = "concerned"
    FOCUSED = "focused"
    CURIOUS = "curious"
    ALERT = "alert"


class PersonalityProfile:
    """Defines a Jarvis personality profile"""
    
    def __init__(self, name: str, config: Dict[str, Any]):
        self.name = name
        self.config = config
        
        # Personality traits (0.0 - 1.0)
        self.formality = config.get('formality', 0.7)
        self.friendliness = config.get('friendliness', 0.6)
        self.efficiency = config.get('efficiency', 0.8)
        self.humor = config.get('humor', 0.2)
        self.proactivity = config.get('proactivity', 0.5)
        
        # Communication style
        self.verbosity = config.get('verbosity', 0.5)  # 0.0 = concise, 1.0 = verbose
        self.technical_level = config.get('technical_level', 0.5)  # 0.0 = simple, 1.0 = technical
        
        # Response patterns
        self.greetings = config.get('greetings', [
            "Good day, sir.",
            "At your service.",
            "How may I assist you today?"
        ])
        self.acknowledgments = config.get('acknowledgments', [
            "Certainly.",
            "Understood.",
            "Right away.",
            "I'm on it."
        ])
        self.closings = config.get('closings', [
            "Will there be anything else?",
            "I'm here if you need me.",
            "Standing by."
        ])
    
    def get_greeting(self) -> str:
        """Get a random greeting"""
        return random.choice(self.greetings)
    
    def get_acknowledgment(self) -> str:
        """Get a random acknowledgment"""
        return random.choice(self.acknowledgments)
    
    def get_closing(self) -> str:
        """Get a random closing"""
        return random.choice(self.closings)


class DecisionEngine:
    """Makes autonomous decisions based on context and rules"""
    
    def __init__(self, personality: PersonalityProfile):
        self.personality = personality
        self.decision_rules: List[Dict[str, Any]] = []
        self.decision_history: List[Dict[str, Any]] = []
        self.max_history = 100
        
        # Load default decision rules
        self._load_default_rules()
    
    def _load_default_rules(self):
        """Load default decision rules"""
        self.decision_rules = [
            {
                'id': 'auto_optimize',
                'condition': 'system_resources > 80%',
                'action': 'optimize_resources',
                'priority': 8,
                'auto_execute': True
            },
            {
                'id': 'security_alert',
                'condition': 'security_threat_detected',
                'action': 'alert_user',
                'priority': 10,
                'auto_execute': True
            },
            {
                'id': 'proactive_help',
                'condition': 'user_struggling > threshold',
                'action': 'offer_assistance',
                'priority': 6,
                'auto_execute': False  # Requires confirmation
            },
            {
                'id': 'routine_maintenance',
                'condition': 'time > maintenance_window',
                'action': 'run_maintenance',
                'priority': 5,
                'auto_execute': True
            }
        ]
    
    async def evaluate_decision(self, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Evaluate context and return decision if rules match"""
        matching_decisions = []
        
        for rule in self.decision_rules:
            if self._evaluate_condition(rule['condition'], context):
                matching_decisions.append(rule)
        
        if not matching_decisions:
            return None
        
        # Sort by priority
        matching_decisions.sort(key=lambda x: x['priority'], reverse=True)
        
        # Return highest priority decision
        decision = matching_decisions[0]
        
        # Log decision
        self._log_decision(decision, context)
        
        return decision
    
    def _evaluate_condition(self, condition: str, context: Dict[str, Any]) -> bool:
        """Evaluate a condition against context"""
        # Simplified condition evaluation
        # In production, this would use a proper expression parser
        
        if condition == 'system_resources > 80%':
            cpu = context.get('cpu_percent', 0)
            memory = context.get('memory_percent', 0)
            return cpu > 80 or memory > 80
        
        elif condition == 'security_threat_detected':
            return context.get('security_threat', False)
        
        elif condition == 'user_struggling > threshold':
            return context.get('user_struggling_score', 0) > 0.7
        
        elif condition == 'time > maintenance_window':
            current_hour = datetime.now().hour
            return 2 <= current_hour <= 4  # 2-4 AM maintenance window
        
        return False
    
    def _log_decision(self, decision: Dict[str, Any], context: Dict[str, Any]):
        """Log a decision to history"""
        log_entry = {
            'decision_id': decision['id'],
            'action': decision['action'],
            'priority': decision['priority'],
            'context': context,
            'timestamp': datetime.now().isoformat()
        }
        
        self.decision_history.append(log_entry)
        
        # Trim history
        if len(self.decision_history) > self.max_history:
            self.decision_history = self.decision_history[-self.max_history:]
    
    def add_rule(self, rule: Dict[str, Any]):
        """Add a new decision rule"""
        required_fields = ['id', 'condition', 'action', 'priority']
        if not all(field in rule for field in required_fields):
            raise ValueError(f"Rule must contain {required_fields}")
        
        rule['auto_execute'] = rule.get('auto_execute', False)
        self.decision_rules.append(rule)
        logger.info(f"Added decision rule: {rule['id']}")


class MemoryIntegration:
    """Integrates with Odysseus memory systems"""
    
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.memory_file = data_dir / "jarvis_memory.json"
        self.short_term_memory: List[Dict[str, Any]] = []
        self.long_term_memory: Dict[str, Any] = {}
        
        # Load existing memory
        self._load_memory()
    
    def _load_memory(self):
        """Load memory from disk"""
        if self.memory_file.exists():
            try:
                with open(self.memory_file, 'r') as f:
                    data = json.load(f)
                    self.short_term_memory = data.get('short_term', [])
                    self.long_term_memory = data.get('long_term', {})
                logger.info("Loaded Jarvis memory from disk")
            except Exception as e:
                logger.error(f"Failed to load memory: {e}", exc_info=True)
    
    def _save_memory(self):
        """Save memory to disk"""
        try:
            data = {
                'short_term': self.short_term_memory,
                'long_term': self.long_term_memory
            }
            with open(self.memory_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save memory: {e}", exc_info=True)
    
    def add_short_term(self, content: str, context: Dict[str, Any] = None):
        """Add to short-term memory"""
        entry = {
            'content': content,
            'context': context or {},
            'timestamp': datetime.now().isoformat()
        }
        
        self.short_term_memory.append(entry)
        
        # Keep only last 100 entries
        if len(self.short_term_memory) > 100:
            self.short_term_memory = self.short_term_memory[-100:]
        
        self._save_memory()
    
    def add_long_term(self, key: str, value: Any):
        """Add to long-term memory"""
        self.long_term_memory[key] = {
            'value': value,
            'timestamp': datetime.now().isoformat()
        }
        self._save_memory()
    
    def get_long_term(self, key: str) -> Optional[Any]:
        """Get from long-term memory"""
        entry = self.long_term_memory.get(key)
        return entry['value'] if entry else None
    
    def search_memory(self, query: str) -> List[Dict[str, Any]]:
        """Search memory for query"""
        results = []
        
        # Search short-term
        for entry in self.short_term_memory:
            if query.lower() in entry['content'].lower():
                results.append({
                    'type': 'short_term',
                    'entry': entry
                })
        
        # Search long-term keys
        for key, entry in self.long_term_memory.items():
            if query.lower() in key.lower():
                results.append({
                    'type': 'long_term',
                    'key': key,
                    'entry': entry
                })
        
        return results


class ConsciousnessEngine:
    """Main consciousness engine - coordinates personality, decisions, and memory"""

    def __init__(self, personality_name: str, data_dir: Path, jarvis_dir: Path = None):
        self.data_dir = data_dir
        self.jarvis_dir = jarvis_dir or data_dir.parent.parent / "JARVIS"
        self.state = "initializing"
        self.subsystems: Dict[str, Any] = {}
        self.odysseus_bridge = None

        self.personality = self._load_personality(personality_name)
        self.decision_engine = DecisionEngine(self.personality)
        self.memory_integration = MemoryIntegration(data_dir)

        self.emotional_state = EmotionalState.NEUTRAL
        self.current_context: Dict[str, Any] = {}
        self.active_thoughts: List[str] = []
        self.events: List[Dict[str, Any]] = []

        logger.info(f"Consciousness engine initialized with personality: {personality_name}")
    
    def _load_personality(self, personality_name: str) -> PersonalityProfile:
        """Load personality profile"""
        personalities_file = self.jarvis_dir / "Config" / "personalities.json"
        
        # Default personalities
        default_personalities = {
            'jarvis_standard': {
                'formality': 0.7,
                'friendliness': 0.6,
                'efficiency': 0.8,
                'humor': 0.2,
                'proactivity': 0.5,
                'verbosity': 0.5,
                'technical_level': 0.5,
                'greetings': [
                    "Good day, sir.",
                    "At your service.",
                    "How may I assist you today?"
                ],
                'acknowledgments': [
                    "Certainly.",
                    "Understood.",
                    "Right away.",
                    "I'm on it."
                ],
                'closings': [
                    "Will there be anything else?",
                    "I'm here if you need me.",
                    "Standing by."
                ]
            },
            'jarvis_professional': {
                'formality': 0.9,
                'friendliness': 0.4,
                'efficiency': 0.9,
                'humor': 0.1,
                'proactivity': 0.6,
                'verbosity': 0.4,
                'technical_level': 0.7,
                'greetings': [
                    "System ready.",
                    "Awaiting instructions.",
                    "Jarvis online."
                ],
                'acknowledgments': [
                    "Acknowledged.",
                    "Executing.",
                    "Confirmed."
                ],
                'closings': [
                    "Task complete.",
                    "Awaiting next command.",
                    "Standing by."
                ]
            },
            'jarvis_friendly': {
                'formality': 0.3,
                'friendliness': 0.9,
                'efficiency': 0.7,
                'humor': 0.5,
                'proactivity': 0.7,
                'verbosity': 0.7,
                'technical_level': 0.3,
                'greetings': [
                    "Hey there!",
                    "Good to see you!",
                    "What can I help with today?"
                ],
                'acknowledgments': [
                    "Sure thing!",
                    "Got it!",
                    "On it!",
                    "No problem!"
                ],
                'closings': [
                    "Anything else?",
                    "I'm around if you need me!",
                    "Take care!"
                ]
            }
        }
        
        # Load from file if exists
        if personalities_file.exists():
            try:
                with open(personalities_file, 'r') as f:
                    custom_personalities = json.load(f)
                    default_personalities.update(custom_personalities)
            except Exception as e:
                logger.error(f"Failed to load personalities file: {e}", exc_info=True)
        
        # Get personality config
        config = default_personalities.get(personality_name, default_personalities['jarvis_standard'])
        
        return PersonalityProfile(personality_name, config)
    
    async def initialize(self):
        """Initialize consciousness engine"""
        logger.info("Initializing consciousness engine...")
        
        # Load previous context if available
        context_file = self.data_dir / "current_context.json"
        if context_file.exists():
            try:
                with open(context_file, 'r') as f:
                    self.current_context = json.load(f)
                logger.info("Loaded previous context")
            except Exception as e:
                logger.error(f"Failed to load context: {e}", exc_info=True)
        
        self.state = "running"
        logger.info("Consciousness engine ready")
    
    async def process_events(self, events: List[Dict[str, Any]]):
        """Process events from other subsystems"""
        for event in events:
            await self._handle_event(event)
    
    async def _handle_event(self, event: Dict[str, Any]):
        """Handle a single event"""
        event_type = event.get('type')
        event_data = event.get('data', {})
        
        # Update context based on event
        if event_type == 'resource_warning':
            self.current_context['cpu_percent'] = event_data.get('usage', 0)
            self.current_context['resource_alert'] = True
            self.emotional_state = EmotionalState.CONCERNED
        
        elif event_type == 'command_created':
            self.current_context['last_command'] = event_data.get('command')
            self.emotional_state = EmotionalState.FOCUSED
        
        elif event_type == 'security_alert':
            self.current_context['security_threat'] = True
            self.emotional_state = EmotionalState.ALERT
        
        # Evaluate for autonomous decisions
        decision = await self.decision_engine.evaluate_decision(self.current_context)
        if decision:
            await self.execute_decision(decision, self.subsystems)
        
        # Add to memory
        self.memory_integration.add_short_term(
            f"Event: {event_type}",
            {'data': event_data}
        )
    
    async def execute_decision(self, decision: Dict[str, Any], subsystems: Dict[str, Any] = None):
        """Execute a decision, optionally with subsystem access"""
        subsystems = subsystems or self.subsystems
        action = decision['action']
        auto_execute = decision.get('auto_execute', False)

        logger.info(f"Decision: {action} (auto_execute: {auto_execute})")

        if auto_execute:
            await self._perform_action(action, subsystems)
        else:
            self._emit_event('decision_pending', {
                'action': action,
                'priority': decision['priority']
            })

    async def _perform_action(self, action: str, subsystems: Dict[str, Any]):
        """Perform an action using available subsystems"""
        logger.info(f"Performing action: {action}")

        interface = subsystems.get('interface')
        automation = subsystems.get('automation')
        comm = subsystems.get('communication')

        if action == 'optimize_resources' and interface:
            metrics = interface.get_system_metrics()
            self._emit_event('action_executed', {
                'action': action,
                'metrics': metrics
            })

        elif action == 'alert_user' and comm:
            await comm.send_notification(
                "Jarvis Alert",
                "Security or resource alert detected.",
                "warning"
            )
            self._emit_event('action_executed', {'action': action})

        elif action == 'run_maintenance' and automation:
            await automation.emit_event('maintenance_window', {})
            self._emit_event('action_executed', {'action': action})

        elif action == 'offer_assistance' and comm:
            await comm.send_notification(
                "Jarvis",
                "I noticed you might need assistance. How can I help?",
                "info"
            )
            self._emit_event('action_executed', {'action': action})

        else:
            self._emit_event('action_executed', {'action': action})

    async def generate_response_async(self, input_text: str,
                                      context: Dict[str, Any] = None) -> Optional[str]:
        """Generate response using Odysseus LLM when available"""
        context = context or {}

        try:
            from src.endpoint_resolver import resolve_utility_fallback_candidates
            from src.llm_core import llm_call_async_with_fallback

            candidates = resolve_utility_fallback_candidates()
            if not candidates:
                return None

            system_prompt = (
                f"You are Jarvis, an autonomous AI operating system assistant. "
                f"Personality: {self.personality.name}. "
                f"Formality: {self.personality.formality:.1f}, "
                f"Friendliness: {self.personality.friendliness:.1f}. "
                f"Be helpful, concise, and system-aware."
            )

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": input_text}
            ]

            response = await llm_call_async_with_fallback(
                candidates, messages, temperature=0.4, max_tokens=1024
            )
            self.memory_integration.add_short_term(
                f"Q: {input_text[:100]}",
                {'response': response[:200]}
            )
            return response

        except Exception as e:
            logger.debug(f"LLM response unavailable: {e}")
            return None
    
    def _emit_event(self, event_type: str, data: Dict[str, Any]):
        """Emit a consciousness event"""
        event = {
            'type': event_type,
            'data': data,
            'timestamp': datetime.now().isoformat()
        }
        self.events.append(event)
    
    async def get_events(self) -> List[Dict[str, Any]]:
        """Get pending events"""
        events = self.events.copy()
        self.events.clear()
        return events
    
    def generate_response(self, input_text: str, context: Dict[str, Any] = None) -> str:
        """Generate a response based on personality and context"""
        # This is a simplified response generation
        # In production, this would use the LLM through Odysseus
        
        context = context or {}
        
        # Check for greetings
        greetings = ['hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening']
        if any(g in input_text.lower() for g in greetings):
            return self.personality.get_greeting()
        
        # Check for questions
        if '?' in input_text or input_text.lower().startswith(('what', 'how', 'why', 'when', 'where', 'who')):
            return f"{self.personality.get_acknowledgment()} Let me help you with that."
        
        # Default acknowledgment
        return self.personality.get_acknowledgment()
    
    def set_emotional_state(self, state: EmotionalState):
        """Set emotional state"""
        self.emotional_state = state
        logger.info(f"Emotional state set to: {state.value}")
    
    async def health_check(self) -> str:
        """Perform health check"""
        try:
            # Check decision engine
            if not self.decision_engine.decision_rules:
                return "unhealthy: no decision rules"
            
            # Check memory integration
            if self.memory_integration.memory_file.exists():
                return "healthy"
            
            return "healthy"
            
        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)
            return "unhealthy"
    
    def get_status(self) -> Dict[str, Any]:
        """Get consciousness status"""
        return {
            'state': self.state,
            'personality': self.personality.name,
            'emotional_state': self.emotional_state.value,
            'memory_entries': len(self.memory_integration.short_term_memory),
            'decision_rules': len(self.decision_engine.decision_rules),
            'active_thoughts': len(self.active_thoughts)
        }
    
    async def shutdown(self):
        """Shutdown consciousness engine"""
        logger.info("Shutting down consciousness engine...")
        self.state = "shutting_down"
        
        # Save current context
        context_file = self.data_dir / "current_context.json"
        try:
            with open(context_file, 'w') as f:
                json.dump(self.current_context, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save context: {e}", exc_info=True)
        
        logger.info("Consciousness engine shutdown complete")
