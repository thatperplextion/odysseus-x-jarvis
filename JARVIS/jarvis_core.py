"""
Jarvis Core - Main entry point and coordinator for the Jarvis Operating System
Built on top of Odysseus AI workspace platform
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime
import json

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.constants import DATA_DIR

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class JarvisCore:
    """
    Main Jarvis OS coordinator.
    Manages initialization, lifecycle, and coordination between all subsystems.
    """

    def __init__(self):
        self.version = "1.1.0"  # Phase 1 version
        self.startup_time = datetime.now()
        self.subsystems = {}
        self.state = "initializing"
        self.config = {}
        self.event_loop = None
        self.shutdown_requested = False
        self.autonomous_agent = None
        self.ui = None
        self.odysseus_components: Dict[str, Any] = {}

        self.jarvis_dir = Path(__file__).parent
        self.jarvis_data_dir = Path(DATA_DIR) / "jarvis"
        self.jarvis_data_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Jarvis OS v{self.version} initializing (Phase 1 - Core AI Engine)...")
        logger.info(f"Jarvis data directory: {self.jarvis_data_dir}")

    def connect_odysseus(self, components: Dict[str, Any]):
        """Inject Odysseus platform components for deep integration"""
        self.odysseus_components = components or {}
        logger.info(f"Odysseus bridge connected ({len(self.odysseus_components)} components)")

        if 'integration' in self.subsystems:
            self.subsystems['integration'].connect_odysseus(components)

    async def initialize(self):
        """Initialize all Jarvis subsystems"""
        logger.info("Starting Jarvis OS initialization...")

        try:
            await self._load_configuration()

            # Phase 1: Core AI Engine components
            await self._initialize_planning()
            await self._initialize_reasoning()
            await self._initialize_memory()
            await self._initialize_reflection()
            await self._initialize_self_correction()
            await self._initialize_workflows()
            await self._initialize_project_understanding()

            # Phase 2: Advanced AI Features
            await self._initialize_nlu()
            await self._initialize_advanced_learning()
            await self._initialize_multi_agent()
            await self._initialize_advanced_reasoning()

            # Original subsystems
            await self._initialize_kernel()
            await self._initialize_consciousness()
            await self._initialize_automation()
            await self._initialize_interface()
            await self._initialize_communication()
            await self._initialize_security()
            await self._initialize_learning()
            await self._initialize_integration()

            # Wire cross-subsystem references
            await self._wire_subsystems()

            # Initialize UI dashboard
            await self._initialize_ui()

            # Initialize autonomous agent
            await self._initialize_autonomous()

            # Connect Odysseus if components were injected before init
            if self.odysseus_components:
                self.connect_odysseus(self.odysseus_components)

            self.state = "running"
            logger.info("Jarvis OS initialization complete")

            await self._start_event_loop()

        except Exception as e:
            logger.error(f"Failed to initialize Jarvis OS: {e}", exc_info=True)
            self.state = "error"
            raise

    async def _load_configuration(self):
        """Load Jarvis configuration"""
        logger.info("Loading Jarvis configuration...")

        config_file = self.jarvis_dir / "Config" / "jarvis_config.json"
        example_file = self.jarvis_dir / "Config" / "jarvis_config.json.example"

        default_config = {
            "version": self.version,
            "personality": "jarvis_standard",
            "security_level": "high",
            "learning_enabled": True,
            "automation_enabled": True,
            "voice_enabled": True,
            "autonomous_mode": True,
            "autonomous_interval": 30,
            "monitoring_interval": 5,
            "max_concurrent_tasks": 10,
            "resource_limits": {
                "cpu_percent": 80,
                "memory_percent": 80,
                "network_bandwidth": 1000000
            },
            "permissions": {
                "file_access": "restricted",
                "process_control": "monitored",
                "network_access": "filtered",
                "system_changes": "authorized"
            }
        }

        if config_file.exists():
            with open(config_file, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                self.config = {**default_config, **user_config}
        elif example_file.exists():
            with open(example_file, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                self.config = {**default_config, **user_config}
        else:
            self.config = default_config

        config_file.parent.mkdir(parents=True, exist_ok=True)
        if not config_file.exists():
            with open(config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2)

        logger.info(f"Configuration loaded: {len(self.config)} settings")

    async def _initialize_planning(self):
        """Initialize Phase 1 Enhanced Planner"""
        logger.info("Initializing Phase 1 Enhanced Planner...")
        from JARVIS.planning import EnhancedPlanner
        planner = EnhancedPlanner()
        await planner.health_check()
        self.subsystems['planning'] = planner
        logger.info("Phase 1 Enhanced Planner initialized")

    async def _initialize_reasoning(self):
        """Initialize Phase 1 Reasoning Engine"""
        logger.info("Initializing Phase 1 Reasoning Engine...")
        from JARVIS.reasoning import ReasoningEngine
        reasoning = ReasoningEngine()
        await reasoning.health_check()
        self.subsystems['reasoning'] = reasoning
        logger.info("Phase 1 Reasoning Engine initialized")

    async def _initialize_memory(self):
        """Initialize Phase 1 Enhanced Memory"""
        logger.info("Initializing Phase 1 Enhanced Memory...")
        from JARVIS.memory import EnhancedMemory
        memory = EnhancedMemory(self.jarvis_data_dir)
        await memory.initialize()
        self.subsystems['memory'] = memory
        logger.info("Phase 1 Enhanced Memory initialized")

    async def _initialize_reflection(self):
        """Initialize Phase 1 Reflection Engine"""
        logger.info("Initializing Phase 1 Reflection Engine...")
        from JARVIS.reflection import ReflectionEngine
        reflection = ReflectionEngine()
        await reflection.health_check()
        self.subsystems['reflection'] = reflection
        logger.info("Phase 1 Reflection Engine initialized")

    async def _initialize_self_correction(self):
        """Initialize Phase 1 Self-Correction System"""
        logger.info("Initializing Phase 1 Self-Correction System...")
        from JARVIS.self_correction import SelfCorrection
        self_correction = SelfCorrection()
        await self_correction.health_check()
        self.subsystems['self_correction'] = self_correction
        logger.info("Phase 1 Self-Correction System initialized")

    async def _initialize_workflows(self):
        """Initialize Phase 1 Autonomous Workflow Engine"""
        logger.info("Initializing Phase 1 Autonomous Workflow Engine...")
        from JARVIS.workflows import AutonomousWorkflowEngine
        workflows = AutonomousWorkflowEngine()
        await workflows.health_check()
        self.subsystems['workflows'] = workflows
        logger.info("Phase 1 Autonomous Workflow Engine initialized")

    async def _initialize_project_understanding(self):
        """Initialize Phase 1 Project Understanding System"""
        logger.info("Initializing Phase 1 Project Understanding System...")
        from JARVIS.project_understanding import ContextAwareness, CodeComprehension, DependencyMapping
        context_awareness = ContextAwareness()
        code_comprehension = CodeComprehension()
        dependency_mapping = DependencyMapping()
        await context_awareness.health_check()
        await code_comprehension.health_check()
        await dependency_mapping.health_check()
        self.subsystems['context_awareness'] = context_awareness
        self.subsystems['code_comprehension'] = code_comprehension
        self.subsystems['dependency_mapping'] = dependency_mapping
        logger.info("Phase 1 Project Understanding System initialized")

    async def _initialize_nlu(self):
        """Initialize Phase 2 Natural Language Understanding System"""
        logger.info("Initializing Phase 2 Natural Language Understanding System...")
        from JARVIS.nlu import IntentRecognizer, EntityExtractor, SentimentAnalyzer
        intent_recognizer = IntentRecognizer()
        entity_extractor = EntityExtractor()
        sentiment_analyzer = SentimentAnalyzer()
        await intent_recognizer.health_check()
        await entity_extractor.health_check()
        await sentiment_analyzer.health_check()
        self.subsystems['intent_recognizer'] = intent_recognizer
        self.subsystems['entity_extractor'] = entity_extractor
        self.subsystems['sentiment_analyzer'] = sentiment_analyzer
        logger.info("Phase 2 Natural Language Understanding System initialized")

    async def _initialize_advanced_learning(self):
        """Initialize Phase 2 Advanced Learning System"""
        logger.info("Initializing Phase 2 Advanced Learning System...")
        from JARVIS.learning import ReinforcementLearner, MachineLearningEngine, KnowledgeGraph, AdaptiveLearner
        rl_learner = ReinforcementLearner()
        ml_engine = MachineLearningEngine()
        knowledge_graph = KnowledgeGraph()
        adaptive_learner = AdaptiveLearner()
        await rl_learner.health_check()
        await ml_engine.health_check()
        await knowledge_graph.health_check()
        await adaptive_learner.health_check()
        self.subsystems['reinforcement_learner'] = rl_learner
        self.subsystems['ml_engine'] = ml_engine
        self.subsystems['knowledge_graph'] = knowledge_graph
        self.subsystems['adaptive_learner'] = adaptive_learner
        logger.info("Phase 2 Advanced Learning System initialized")

    async def _initialize_multi_agent(self):
        """Initialize Phase 2 Multi-Agent System"""
        logger.info("Initializing Phase 2 Multi-Agent System...")
        from JARVIS.agents import AgentSystem, AgentCommunication, Coordinator, TaskDistributor
        agent_system = AgentSystem()
        agent_comm = AgentCommunication()
        coordinator = Coordinator()
        task_distributor = TaskDistributor()
        await agent_system.health_check()
        await agent_comm.health_check()
        await coordinator.health_check()
        await task_distributor.health_check()
        self.subsystems['agent_system'] = agent_system
        self.subsystems['agent_communication'] = agent_comm
        self.subsystems['coordinator'] = coordinator
        self.subsystems['task_distributor'] = task_distributor
        logger.info("Phase 2 Multi-Agent System initialized")

    async def _initialize_advanced_reasoning(self):
        """Initialize Phase 2 Advanced Reasoning System"""
        logger.info("Initializing Phase 2 Advanced Reasoning System...")
        from JARVIS.reasoning import CausalReasoner, AbductiveReasoner, AnalogicalReasoner, MetaReasoner
        causal_reasoner = CausalReasoner()
        abductive_reasoner = AbductiveReasoner()
        analogical_reasoner = AnalogicalReasoner()
        meta_reasoner = MetaReasoner()
        await causal_reasoner.health_check()
        await abductive_reasoner.health_check()
        await analogical_reasoner.health_check()
        await meta_reasoner.health_check()
        self.subsystems['causal_reasoner'] = causal_reasoner
        self.subsystems['abductive_reasoner'] = abductive_reasoner
        self.subsystems['analogical_reasoner'] = analogical_reasoner
        self.subsystems['meta_reasoner'] = meta_reasoner
        logger.info("Phase 2 Advanced Reasoning System initialized")

    async def _initialize_kernel(self):
        logger.info("Initializing Jarvis kernel...")
        from JARVIS.kernel.jarvis_kernel import JarvisKernel
        kernel = JarvisKernel(self.config, self.jarvis_data_dir)
        await kernel.initialize()
        self.subsystems['kernel'] = kernel

    async def _initialize_consciousness(self):
        logger.info("Initializing consciousness layer...")
        from JARVIS.consciousness.consciousness_engine import ConsciousnessEngine
        consciousness = ConsciousnessEngine(
            self.config.get('personality', 'jarvis_standard'),
            self.jarvis_data_dir,
            self.jarvis_dir
        )
        await consciousness.initialize()
        self.subsystems['consciousness'] = consciousness

    async def _initialize_automation(self):
        logger.info("Initializing automation engine...")
        from JARVIS.automation.automation_engine import AutomationEngine
        automation = AutomationEngine(
            self.config,
            self.jarvis_data_dir,
            self.subsystems.get('kernel')
        )
        await automation.initialize()
        self.subsystems['automation'] = automation

    async def _initialize_interface(self):
        logger.info("Initializing system interface...")
        from JARVIS.interface.system_interface import SystemInterface
        interface = SystemInterface(self.config, self.jarvis_data_dir)
        await interface.initialize()
        self.subsystems['interface'] = interface

    async def _initialize_communication(self):
        logger.info("Initializing communication layer...")
        from JARVIS.communication.communication_manager import CommunicationManager
        communication = CommunicationManager(
            self.config,
            self.jarvis_data_dir,
            self.subsystems.get('consciousness')
        )
        await communication.initialize()
        self.subsystems['communication'] = communication

    async def _initialize_security(self):
        logger.info("Initializing security layer...")
        from JARVIS.security.security_manager import SecurityManager
        security = SecurityManager(
            self.config.get('security_level', 'high'),
            self.jarvis_data_dir
        )
        await security.initialize()
        self.subsystems['security'] = security

    async def _initialize_learning(self):
        if not self.config.get('learning_enabled', True):
            logger.info("Learning system disabled in configuration")
            return
        logger.info("Initializing learning system...")
        from JARVIS.learning.learning_engine import LearningEngine
        learning = LearningEngine(self.config, self.jarvis_data_dir)
        await learning.initialize()
        self.subsystems['learning'] = learning

    async def _initialize_integration(self):
        logger.info("Initializing integration layer...")
        from JARVIS.integration.integration_manager import IntegrationManager
        integration = IntegrationManager(
            self.config,
            self.jarvis_data_dir,
            self.subsystems
        )
        await integration.initialize()
        self.subsystems['integration'] = integration

    async def _wire_subsystems(self):
        """Connect subsystems that depend on each other"""
        interface = self.subsystems.get('interface')
        kernel = self.subsystems.get('kernel')
        automation = self.subsystems.get('automation')
        planning = self.subsystems.get('planning')
        reasoning = self.subsystems.get('reasoning')
        memory = self.subsystems.get('memory')
        reflection = self.subsystems.get('reflection')
        self_correction = self.subsystems.get('self_correction')
        workflows = self.subsystems.get('workflows')
        context_awareness = self.subsystems.get('context_awareness')
        code_comprehension = self.subsystems.get('code_comprehension')
        dependency_mapping = self.subsystems.get('dependency_mapping')
        intent_recognizer = self.subsystems.get('intent_recognizer')
        entity_extractor = self.subsystems.get('entity_extractor')
        sentiment_analyzer = self.subsystems.get('sentiment_analyzer')
        reinforcement_learner = self.subsystems.get('reinforcement_learner')
        ml_engine = self.subsystems.get('ml_engine')
        knowledge_graph = self.subsystems.get('knowledge_graph')
        adaptive_learner = self.subsystems.get('adaptive_learner')
        agent_system = self.subsystems.get('agent_system')
        agent_communication = self.subsystems.get('agent_communication')
        coordinator = self.subsystems.get('coordinator')
        task_distributor = self.subsystems.get('task_distributor')
        causal_reasoner = self.subsystems.get('causal_reasoner')
        abductive_reasoner = self.subsystems.get('abductive_reasoner')
        analogical_reasoner = self.subsystems.get('analogical_reasoner')
        meta_reasoner = self.subsystems.get('meta_reasoner')

        if kernel and interface:
            kernel.set_system_interface(interface)

        if automation and interface:
            automation.set_system_interface(interface)

        if automation and self.subsystems.get('communication'):
            automation.set_communication(self.subsystems['communication'])

        # Wire Phase 1 components
        if planning and reasoning:
            # Reasoning can inform planning
            pass  # Integration point for future enhancement

        if memory and reflection:
            # Reflection uses memory for analysis
            pass  # Integration point for future enhancement

        if reasoning and memory:
            # Reasoning can access memory for context
            pass  # Integration point for future enhancement

        if self_correction and workflows:
            # Self-correction can handle workflow errors
            pass  # Integration point for future enhancement

        if workflows and planning:
            # Workflows can execute plans
            pass  # Integration point for future enhancement

        if context_awareness and reasoning:
            # Context awareness provides context for reasoning
            pass  # Integration point for future enhancement

        if code_comprehension and context_awareness:
            # Code comprehension enhances project understanding
            pass  # Integration point for future enhancement

        if dependency_mapping and code_comprehension:
            # Dependency mapping complements code analysis
            pass  # Integration point for future enhancement

        if intent_recognizer and reasoning:
            # Intent recognition can inform reasoning
            pass  # Integration point for future enhancement

        if entity_extractor and context_awareness:
            # Entity extraction enhances context understanding
            pass  # Integration point for future enhancement

        if sentiment_analyzer and memory:
            # Sentiment analysis can enhance memory storage
            pass  # Integration point for future enhancement

        if reinforcement_learner and workflows:
            # RL can optimize workflow execution
            pass  # Integration point for future enhancement

        if ml_engine and reasoning:
            # ML models can enhance reasoning
            pass  # Integration point for future enhancement

        if knowledge_graph and memory:
            # Knowledge graph can enhance memory retrieval
            pass  # Integration point for future enhancement

        if adaptive_learner and self_correction:
            # Adaptive learning can enhance self-correction
            pass  # Integration point for future enhancement

        if agent_system and workflows:
            # Agent system can execute workflows
            pass  # Integration point for future enhancement

        if agent_communication and planning:
            # Agent communication can enhance planning coordination
            pass  # Integration point for future enhancement

        if coordinator and reasoning:
            # Coordinator can enhance reasoning with multi-agent consensus
            pass  # Integration point for future enhancement

        if task_distributor and workflows:
            # Task distributor can optimize workflow task assignment
            pass  # Integration point for future enhancement

        if causal_reasoner and reasoning:
            # Causal reasoning can enhance reasoning with cause-effect analysis
            pass  # Integration point for future enhancement

        if abductive_reasoner and planning:
            # Abductive reasoning can enhance planning with explanation generation
            pass  # Integration point for future enhancement

        if analogical_reasoner and knowledge_graph:
            # Analogical reasoning can enhance knowledge graph with similarity matching
            pass  # Integration point for future enhancement

        if meta_reasoner and self_correction:
            # Meta-reasoning can enhance self-correction with reasoning evaluation
            pass  # Integration point for future enhancement

        # Add jarvis data dir to safe paths for file operations
        if interface:
            interface.fs_manager.safe_directories.append(self.jarvis_data_dir)

    async def _initialize_ui(self):
        logger.info("Initializing Jarvis UI...")
        from JARVIS.ui.jarvis_ui import JarvisUI
        self.ui = JarvisUI(self.subsystems)
        await self.ui.initialize()

    async def _initialize_autonomous(self):
        logger.info("Initializing autonomous agent...")
        from JARVIS.autonomous.autonomous_agent import AutonomousAgent
        self.autonomous_agent = AutonomousAgent(self)
        await self.autonomous_agent.initialize()

    async def process_command(self, text: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Process a command through the autonomous agent"""
        if not self.autonomous_agent:
            return {'success': False, 'response': 'Autonomous agent not initialized'}
        return await self.autonomous_agent.process_command(text, context)

    async def _start_event_loop(self):
        logger.info("Starting Jarvis event loop...")
        self.event_loop = asyncio.create_task(self._event_loop_handler())

    async def _event_loop_handler(self):
        while not self.shutdown_requested:
            try:
                await self._process_events()
                await self._periodic_maintenance()
                await asyncio.sleep(self.config.get('monitoring_interval', 5))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in event loop: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _process_events(self):
        events = []
        for subsystem in self.subsystems.values():
            if hasattr(subsystem, 'get_events'):
                subsystem_events = await subsystem.get_events()
                events.extend(subsystem_events)

        if events and 'consciousness' in self.subsystems:
            await self.subsystems['consciousness'].process_events(events)

        if events and 'automation' in self.subsystems:
            for event in events:
                await self.subsystems['automation'].emit_event(
                    event.get('type', 'unknown'),
                    event.get('data', {})
                )

    async def _periodic_maintenance(self):
        for name, subsystem in self.subsystems.items():
            if hasattr(subsystem, 'health_check'):
                health = await subsystem.health_check()
                if health != 'healthy' and not health.startswith('healthy'):
                    logger.warning(f"Subsystem {name} health: {health}")

        if 'kernel' in self.subsystems:
            await self.subsystems['kernel'].cleanup_resources()

    async def shutdown(self):
        logger.info("Starting Jarvis OS shutdown...")
        self.shutdown_requested = True
        self.state = "shutting_down"

        if self.autonomous_agent:
            await self.autonomous_agent.shutdown()

        if self.ui:
            await self.ui.shutdown()

        if self.event_loop:
            self.event_loop.cancel()
            try:
                await self.event_loop
            except asyncio.CancelledError:
                pass

        for name in reversed(list(self.subsystems.keys())):
            subsystem = self.subsystems[name]
            if hasattr(subsystem, 'shutdown'):
                logger.info(f"Shutting down {name}...")
                try:
                    await subsystem.shutdown()
                except Exception as e:
                    logger.error(f"Error shutting down {name}: {e}", exc_info=True)

        self.state = "shutdown"
        logger.info("Jarvis OS shutdown complete")

    def get_status(self) -> Dict[str, Any]:
        uptime = datetime.now() - self.startup_time
        subsystem_status = {}
        for name, subsystem in self.subsystems.items():
            if hasattr(subsystem, 'get_status'):
                subsystem_status[name] = subsystem.get_status()
            else:
                subsystem_status[name] = "active"

        return {
            "version": self.version,
            "state": self.state,
            "uptime_seconds": uptime.total_seconds(),
            "subsystems": subsystem_status,
            "autonomous": self.autonomous_agent.get_status() if self.autonomous_agent else None,
            "ui": self.ui.get_status() if self.ui else None,
            "odysseus_connected": bool(self.odysseus_components),
            "configuration": {
                "personality": self.config.get('personality'),
                "security_level": self.config.get('security_level'),
                "learning_enabled": self.config.get('learning_enabled'),
                "automation_enabled": self.config.get('automation_enabled'),
                "autonomous_mode": self.config.get('autonomous_mode'),
            }
        }

    def get_dashboard(self) -> Dict[str, Any]:
        """Get full dashboard data for UI"""
        if self.ui:
            return self.ui.get_dashboard_data()
        return {}


_jarvis_instance: Optional[JarvisCore] = None


def get_jarvis() -> JarvisCore:
    global _jarvis_instance
    if _jarvis_instance is None:
        _jarvis_instance = JarvisCore()
    return _jarvis_instance


async def start_jarvis(odysseus_components: Dict[str, Any] = None) -> JarvisCore:
    """Start Jarvis OS (used by Odysseus app startup)"""
    jarvis = get_jarvis()
    if odysseus_components:
        jarvis.odysseus_components = odysseus_components
    if jarvis.state in ("initializing", "shutdown", "error"):
        await jarvis.initialize()
        if odysseus_components:
            jarvis.connect_odysseus(odysseus_components)
    return jarvis


async def main():
    jarvis = get_jarvis()
    try:
        await jarvis.initialize()
        print("\n" + "=" * 50)
        print("  Jarvis OS - Autonomous AI Operating System")
        print("  Built on Odysseus | Type 'help' for commands | 'quit' to exit")
        print("=" * 50 + "\n")

        consciousness = jarvis.subsystems.get('consciousness')
        if consciousness:
            print(consciousness.personality.get_greeting() + "\n")

        while jarvis.state == "running":
            try:
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: input("You: ").strip()
                )
            except EOFError:
                break

            if not user_input:
                continue
            if user_input.lower() in ('quit', 'exit', 'q'):
                break

            result = await jarvis.process_command(user_input)
            print(f"Jarvis: {result.get('response', 'Done.')}\n")

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
    finally:
        await jarvis.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
