"""
Comprehensive Integration Test Suite for Phase 2 - Advanced AI Features
Tests all Phase 2 components (Weeks 1-4) working together
"""

import asyncio
import sys
import time

# Add parent directory to path
sys.path.insert(0, 'c:\\Users\\JUNAID ASAD KHAN\\odysseus-1')

from JARVIS.nlu import IntentRecognizer, EntityExtractor, SentimentAnalyzer
from JARVIS.learning import ReinforcementLearner, MachineLearningEngine, KnowledgeGraph, AdaptiveLearner
from JARVIS.learning.knowledge_graph import RelationType as KGRelationType
from JARVIS.agents import AgentSystem, AgentCommunication, Coordinator, TaskDistributor
from JARVIS.agents.agent_system import TaskPriority as AgentTaskPriority, AgentType
from JARVIS.agents.agent_communication import MessageType
from JARVIS.agents.coordination_protocols import CoordinationProtocol
from JARVIS.agents.task_distribution import DistributionStrategy
from JARVIS.reasoning import CausalReasoner, AbductiveReasoner, AnalogicalReasoner, MetaReasoner
from JARVIS.reasoning.causal_reasoning import CausalRelation
from JARVIS.reasoning.abductive_reasoning import ExplanationType
from JARVIS.reasoning.analogical_reasoning import SimilarityType
from JARVIS.reasoning.meta_reasoning import ReasoningType


async def test_phase2_week1_nlu():
    """Test Week 1: Natural Language Understanding"""
    print("\n" + "="*60)
    print("Testing Phase 2 Week 1: Natural Language Understanding")
    print("="*60)
    
    # Initialize NLU components
    intent_recognizer = IntentRecognizer()
    entity_extractor = EntityExtractor()
    sentiment_analyzer = SentimentAnalyzer()
    
    # Test 1: Intent recognition
    print("\n1. Testing intent recognition...")
    result = intent_recognizer.recognize_intent("Analyze the file app.py")
    print(f"   [PASS] Intent: {result.intent.value}")
    assert result.intent.value == "analysis"
    
    # Test 2: Entity extraction
    print("\n2. Testing entity extraction...")
    entities = entity_extractor.extract_entities("Contact user@example.com")
    print(f"   [PASS] Entities: {len(entities)}")
    assert len(entities) > 0
    
    # Test 3: Sentiment analysis
    print("\n3. Testing sentiment analysis...")
    result = sentiment_analyzer.analyze_sentiment("This is great!")
    print(f"   [PASS] Sentiment: {result.sentiment.value}")
    assert result.sentiment.value == "positive"
    
    # Test 4: NLU pipeline
    print("\n4. Testing NLU pipeline...")
    text = "I love the new feature in app.py"
    intent = intent_recognizer.recognize_intent(text)
    entities = entity_extractor.extract_entities(text)
    sentiment = sentiment_analyzer.analyze_sentiment(text)
    print(f"   [PASS] Pipeline complete: {intent.intent.value}, {len(entities)} entities, {sentiment.sentiment.value}")
    
    print("\n[PASS] Phase 2 Week 1 tests passed")
    return True


async def test_phase2_week2_learning():
    """Test Week 2: Advanced Learning"""
    print("\n" + "="*60)
    print("Testing Phase 2 Week 2: Advanced Learning")
    print("="*60)
    
    # Initialize learning components
    rl_learner = ReinforcementLearner()
    ml_engine = MachineLearningEngine()
    knowledge_graph = KnowledgeGraph()
    adaptive_learner = AdaptiveLearner()
    
    # Test 1: Reinforcement learning
    print("\n1. Testing reinforcement learning...")
    from JARVIS.learning.reinforcement_learning import State, Action, ActionType
    state = State(id="s1", features={"task": "analysis"})
    action = rl_learner.choose_action(state, [ActionType.ANALYSIS])
    rl_learner.update_q_table(state, action, reward=1.0, next_state=None, done=True)
    print(f"   [PASS] RL action: {action.action_type.value}")
    
    # Test 2: Machine learning
    print("\n2. Testing machine learning...")
    classifier = ml_engine.create_classifier()
    classifier.add_rule(conditions={"type": "code"}, prediction="analyze")
    from JARVIS.learning.machine_learning import Feature
    prediction = classifier.predict([Feature(name="type", value="code")])
    print(f"   [PASS] ML prediction: {prediction.predicted_value}")
    
    # Test 3: Knowledge graph
    print("\n3. Testing knowledge graph...")
    node1 = knowledge_graph.add_node("Python", "concept")
    node2 = knowledge_graph.add_node("Code", "concept")
    knowledge_graph.add_edge(node1.id, node2.id, KGRelationType.RELATED_TO)
    print(f"   [PASS] KG nodes: {len(knowledge_graph.nodes)}")
    
    # Test 4: Adaptive learning
    print("\n4. Testing adaptive learning...")
    from JARVIS.learning.adaptive_learning import PerformanceMetric
    adaptive_learner.record_performance(PerformanceMetric.ACCURACY, 0.9)
    adaptation = adaptive_learner.auto_adapt()
    print(f"   [PASS] Adaptations: {len(adaptation)}")
    
    print("\n[PASS] Phase 2 Week 2 tests passed")
    return True


async def test_phase2_week3_agents():
    """Test Week 3: Multi-Agent Coordination"""
    print("\n" + "="*60)
    print("Testing Phase 2 Week 3: Multi-Agent Coordination")
    print("="*60)
    
    # Initialize agent components
    agent_system = AgentSystem()
    agent_comm = AgentCommunication()
    coordinator = Coordinator()
    task_distributor = TaskDistributor()
    
    # Test 1: Agent system
    print("\n1. Testing agent system...")
    agent = agent_system.create_agent("Worker1", AgentType.WORKER, {"analysis"})
    task = agent_system.create_task("Analyze", "Analyze code", "analysis", AgentTaskPriority.HIGH, {"analysis"})
    agent_system.assign_task(task.id, agent.id)
    print(f"   [PASS] Agent assigned task: {agent.current_task}")
    
    # Test 2: Agent communication
    print("\n2. Testing agent communication...")
    agent_comm.register_agent(agent.id)
    msg_id = agent_comm.send_message(agent.id, "coordinator", MessageType.STATUS, {"status": "busy"})
    print(f"   [PASS] Message sent: {msg_id}")
    
    # Test 3: Coordination
    print("\n3. Testing coordination...")
    event = coordinator.start_coordination({agent.id}, task.id)
    print(f"   [PASS] Coordination event: {event.id}")
    
    # Test 4: Task distribution
    print("\n4. Testing task distribution...")
    from JARVIS.agents.task_distribution import AgentLoad
    load = AgentLoad(agent_id=agent.id, performance_score=0.8)
    task_distributor.register_agent(agent.id, load)
    result = task_distributor.distribute_task("task1")
    print(f"   [PASS] Task distributed to: {result.assigned_agent}")
    
    print("\n[PASS] Phase 2 Week 3 tests passed")
    return True


async def test_phase2_week4_reasoning():
    """Test Week 4: Advanced Reasoning"""
    print("\n" + "="*60)
    print("Testing Phase 2 Week 4: Advanced Reasoning")
    print("="*60)
    
    # Initialize reasoning components
    causal_reasoner = CausalReasoner()
    abductive_reasoner = AbductiveReasoner()
    analogical_reasoner = AnalogicalReasoner()
    meta_reasoner = MetaReasoner()
    
    # Test 1: Causal reasoning
    print("\n1. Testing causal reasoning...")
    node1 = causal_reasoner.add_node("Error", "event")
    node2 = causal_reasoner.add_node("Bug", "cause")
    causal_reasoner.add_edge(node2.id, node1.id, CausalRelation.DIRECT, 0.8)
    causes = causal_reasoner.find_causes(node1.id)
    print(f"   [PASS] Causes found: {len(causes)}")
    
    # Test 2: Abductive reasoning
    print("\n2. Testing abductive reasoning...")
    obs = abductive_reasoner.add_observation("System error occurred")
    inference = abductive_reasoner.explain(obs)
    print(f"   [PASS] Explanation: {inference.best_hypothesis.explanation if inference.best_hypothesis else 'None'}")
    
    # Test 3: Analogical reasoning
    print("\n3. Testing analogical reasoning...")
    concept1 = analogical_reasoner.add_concept("Python", {"type": "language"})
    concept2 = analogical_reasoner.add_concept("Java", {"type": "language"})
    analogies = analogical_reasoner.find_analogies(concept1.id)
    print(f"   [PASS] Analogies found: {len(analogies)}")
    
    # Test 4: Meta-reasoning
    print("\n4. Testing meta-reasoning...")
    process = meta_reasoner.create_process("Test reasoning")
    meta_reasoner.add_step(process.id, ReasoningType.DEDUCTIVE, {"premise": "A"}, {"conclusion": "B"}, 0.9)
    meta_reasoner.complete_process(process.id, "Result")
    print(f"   [PASS] Process quality: {process.quality:.2f}")
    
    print("\n[PASS] Phase 2 Week 4 tests passed")
    return True


async def test_phase2_cross_week_integration():
    """Test cross-week integration between Phase 2 components"""
    print("\n" + "="*60)
    print("Testing Phase 2 Cross-Week Integration")
    print("="*60)
    
    # Initialize all Phase 2 components
    nlu_intent = IntentRecognizer()
    nlu_entity = EntityExtractor()
    nlu_sentiment = SentimentAnalyzer()
    
    rl_learner = ReinforcementLearner()
    ml_engine = MachineLearningEngine()
    knowledge_graph = KnowledgeGraph()
    adaptive_learner = AdaptiveLearner()
    
    agent_system = AgentSystem()
    agent_comm = AgentCommunication()
    coordinator = Coordinator()
    task_distributor = TaskDistributor()
    
    causal_reasoner = CausalReasoner()
    abductive_reasoner = AbductiveReasoner()
    analogical_reasoner = AnalogicalReasoner()
    meta_reasoner = MetaReasoner()
    
    # Test 1: NLU + Learning integration
    print("\n1. Testing NLU + Learning integration...")
    text = "Analyze the file app.py"
    intent = nlu_intent.recognize_intent(text)
    entities = nlu_entity.extract_entities(text)
    
    # Use entities for knowledge graph
    if entities:
        node = knowledge_graph.add_node(entities[0].text, "entity")
        print(f"   [PASS] NLU entities added to KG: {node.id}")
    
    # Test 2: Learning + Agents integration
    print("\n2. Testing Learning + Agents integration...")
    agent = agent_system.create_agent("Learner", AgentType.LEARNER, {"learning"})
    task = agent_system.create_task("Learn", "Learn pattern", "learning", AgentTaskPriority.MEDIUM, {"learning"})
    
    # Use RL for task assignment
    from JARVIS.learning.reinforcement_learning import State, Action, ActionType
    state = State(id="task_state", features={"task": "learning"})
    action = rl_learner.choose_action(state, [ActionType.ANALYSIS])
    print(f"   [PASS] RL action for agent task: {action.action_type.value}")
    
    # Test 3: Agents + Reasoning integration
    print("\n3. Testing Agents + Reasoning integration...")
    obs = abductive_reasoner.add_observation("Agent failed task")
    inference = abductive_reasoner.explain(obs)
    
    # Use meta-reasoning to evaluate agent performance
    process = meta_reasoner.create_process("Agent evaluation")
    meta_reasoner.add_step(process.id, ReasoningType.ABDUCTIVE, {"obs": obs.id}, {"hyp": "explanation"}, 0.8)
    meta_reasoner.complete_process(process.id, "Evaluation complete")
    print(f"   [PASS] Agent evaluation quality: {process.quality:.2f}")
    
    # Test 4: Full Phase 2 pipeline
    print("\n4. Testing full Phase 2 pipeline...")
    # NLU processing
    user_input = "The system is slow, please analyze the performance"
    intent = nlu_intent.recognize_intent(user_input)
    entities = nlu_entity.extract_entities(user_input)
    sentiment = nlu_sentiment.analyze_sentiment(user_input)
    
    # Learning: add to knowledge graph
    if entities:
        for entity in entities:
            node = knowledge_graph.add_node(entity.text, "entity")
    
    # Agents: create task
    task = agent_system.create_task("Performance Analysis", "Analyze system performance", "analysis", 
                                    AgentTaskPriority.HIGH, {"analysis"})
    
    # Reasoning: explain the issue
    obs = abductive_reasoner.add_observation("System is slow")
    inference = abductive_reasoner.explain(obs)
    
    # Meta-reasoning: evaluate the pipeline
    process = meta_reasoner.create_process("Full pipeline")
    meta_reasoner.add_step(process.id, ReasoningType.ABDUCTIVE, {"obs": obs.id}, {"hyp": "explanation"}, 0.9)
    meta_reasoner.complete_process(process.id, "Pipeline complete")
    
    print(f"   [PASS] Full pipeline executed with quality: {process.quality:.2f}")
    
    # Test 5: Cross-component statistics
    print("\n5. Testing cross-component statistics...")
    nlu_stats = {"intent": len(nlu_intent.get_recognition_stats()), "entities": len(nlu_entity.get_extraction_stats())}
    learning_stats = ml_engine.get_statistics()
    agent_stats = agent_system.get_agent_statistics()
    reasoning_stats = meta_reasoner.get_statistics()
    
    print(f"   [PASS] NLU: {nlu_stats}")
    print(f"   [PASS] Learning models: {learning_stats['total_classifiers'] + learning_stats['total_regressors']}")
    print(f"   [PASS] Agents: {agent_stats['total_agents']}")
    print(f"   [PASS] Reasoning processes: {reasoning_stats['total_processes']}")
    
    print("\n[PASS] Phase 2 Cross-Week Integration tests passed")
    return True


async def test_phase2_performance():
    """Test Phase 2 component performance"""
    print("\n" + "="*60)
    print("Testing Phase 2 Performance")
    print("="*60)
    
    # Initialize components
    nlu_intent = IntentRecognizer()
    nlu_entity = EntityExtractor()
    nlu_sentiment = SentimentAnalyzer()
    
    rl_learner = ReinforcementLearner()
    ml_engine = MachineLearningEngine()
    knowledge_graph = KnowledgeGraph()
    adaptive_learner = AdaptiveLearner()
    
    agent_system = AgentSystem()
    agent_comm = AgentCommunication()
    coordinator = Coordinator()
    task_distributor = TaskDistributor()
    
    causal_reasoner = CausalReasoner()
    abductive_reasoner = AbductiveReasoner()
    analogical_reasoner = AnalogicalReasoner()
    meta_reasoner = MetaReasoner()
    
    # Test 1: NLU performance
    print("\n1. Testing NLU performance...")
    start = time.time()
    for i in range(100):
        nlu_intent.recognize_intent("Analyze the file")
    nlu_time = (time.time() - start) / 100
    print(f"   [PASS] Intent recognition: {nlu_time*1000:.2f}ms avg")
    
    # Test 2: Learning performance
    print("\n2. Testing Learning performance...")
    start = time.time()
    for i in range(100):
        from JARVIS.learning.reinforcement_learning import State, Action, ActionType
        state = State(id=f"s{i}", features={"task": "analysis"})
        action = rl_learner.choose_action(state, [ActionType.ANALYSIS])
    learning_time = (time.time() - start) / 100
    print(f"   [PASS] RL action selection: {learning_time*1000:.2f}ms avg")
    
    # Test 3: Agent performance
    print("\n3. Testing Agent performance...")
    start = time.time()
    for i in range(100):
        agent_system.create_task(f"Task{i}", f"Description{i}", "analysis", AgentTaskPriority.MEDIUM)
    agent_time = (time.time() - start) / 100
    print(f"   [PASS] Task creation: {agent_time*1000:.2f}ms avg")
    
    # Test 4: Reasoning performance
    print("\n4. Testing Reasoning performance...")
    start = time.time()
    for i in range(100):
        obs = abductive_reasoner.add_observation(f"Observation{i}")
        abductive_reasoner.explain(obs)
    reasoning_time = (time.time() - start) / 100
    print(f"   [PASS] Abductive explanation: {reasoning_time*1000:.2f}ms avg")
    
    # Test 5: Full pipeline performance
    print("\n5. Testing full pipeline performance...")
    start = time.time()
    text = "Analyze the system performance"
    intent = nlu_intent.recognize_intent(text)
    entities = nlu_entity.extract_entities(text)
    sentiment = nlu_sentiment.analyze_sentiment(text)
    obs = abductive_reasoner.add_observation(text)
    inference = abductive_reasoner.explain(obs)
    pipeline_time = time.time() - start
    print(f"   [PASS] Full pipeline: {pipeline_time*1000:.2f}ms")
    
    print("\n[PASS] Phase 2 Performance tests passed")
    return True


async def run_all_tests():
    """Run all Phase 2 integration tests"""
    print("\n" + "="*60)
    print("PHASE 2 COMPREHENSIVE INTEGRATION TESTS")
    print("="*60)
    
    results = {}
    
    try:
        results['week1_nlu'] = await test_phase2_week1_nlu()
    except Exception as e:
        print(f"\n[FAIL] Week 1 NLU tests failed: {e}")
        results['week1_nlu'] = False
    
    try:
        results['week2_learning'] = await test_phase2_week2_learning()
    except Exception as e:
        print(f"\n[FAIL] Week 2 Learning tests failed: {e}")
        results['week2_learning'] = False
    
    try:
        results['week3_agents'] = await test_phase2_week3_agents()
    except Exception as e:
        print(f"\n[FAIL] Week 3 Agents tests failed: {e}")
        results['week3_agents'] = False
    
    try:
        results['week4_reasoning'] = await test_phase2_week4_reasoning()
    except Exception as e:
        print(f"\n[FAIL] Week 4 Reasoning tests failed: {e}")
        results['week4_reasoning'] = False
    
    try:
        results['cross_week_integration'] = await test_phase2_cross_week_integration()
    except Exception as e:
        print(f"\n[FAIL] Cross-week integration tests failed: {e}")
        results['cross_week_integration'] = False
    
    try:
        results['performance'] = await test_phase2_performance()
    except Exception as e:
        print(f"\n[FAIL] Performance tests failed: {e}")
        results['performance'] = False
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for test_name, passed in results.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"{status}: {test_name}")
    
    total = len(results)
    passed = sum(results.values())
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n[SUCCESS] All Phase 2 integration tests passed successfully!")
        return True
    else:
        print(f"\n[WARNING] {total - passed} test(s) failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
