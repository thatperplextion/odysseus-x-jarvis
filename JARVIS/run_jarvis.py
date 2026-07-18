"""
Jarvis OS Demo - Run and Test Jarvis
Demonstrates all Phase 1 and Phase 2 capabilities
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from JARVIS.jarvis_core import JarvisCore


async def demo_nlu(jarvis):
    """Demonstrate Natural Language Understanding"""
    print("\n" + "="*60)
    print("DEMO: Natural Language Understanding (Phase 2 Week 1)")
    print("="*60)
    
    nlu_intent = jarvis.subsystems.get('intent_recognizer')
    nlu_entity = jarvis.subsystems.get('entity_extractor')
    nlu_sentiment = jarvis.subsystems.get('sentiment_analyzer')
    
    if not all([nlu_intent, nlu_entity, nlu_sentiment]):
        print("NLU components not available")
        return
    
    test_inputs = [
        "Analyze the file app.py",
        "Contact user@example.com",
        "I love the new feature!",
        "The system is slow and needs optimization"
    ]
    
    for text in test_inputs:
        print(f"\nInput: '{text}'")
        
        # Intent recognition
        intent_result = nlu_intent.recognize_intent(text)
        print(f"  Intent: {intent_result.intent.value} (confidence: {intent_result.confidence:.2f})")
        
        # Entity extraction
        entities = nlu_entity.extract_entities(text)
        if entities:
            print(f"  Entities: {', '.join([f'{e.text} ({e.entity_type.value})' for e in entities])}")
        
        # Sentiment analysis
        sentiment_result = nlu_sentiment.analyze_sentiment(text)
        print(f"  Sentiment: {sentiment_result.sentiment.value} (intensity: {sentiment_result.intensity:.2f})")


async def demo_learning(jarvis):
    """Demonstrate Advanced Learning"""
    print("\n" + "="*60)
    print("DEMO: Advanced Learning (Phase 2 Week 2)")
    print("="*60)
    
    rl_learner = jarvis.subsystems.get('reinforcement_learner')
    ml_engine = jarvis.subsystems.get('ml_engine')
    knowledge_graph = jarvis.subsystems.get('knowledge_graph')
    
    if not all([rl_learner, ml_engine, knowledge_graph]):
        print("Learning components not available")
        return
    
    # Reinforcement Learning demo
    print("\n1. Reinforcement Learning:")
    from JARVIS.learning.reinforcement_learning import State, Action, ActionType
    state = State(id="demo_state", features={"task": "analysis", "complexity": "high"})
    action = rl_learner.choose_action(state, [ActionType.ANALYSIS, ActionType.OPTIMIZATION])
    print(f"   State: {state.features}")
    print(f"   Chosen action: {action.action_type.value}")
    
    # Machine Learning demo
    print("\n2. Machine Learning:")
    classifier = ml_engine.create_classifier()
    classifier.add_rule(conditions={"type": "code", "language": "python"}, prediction="analyze")
    from JARVIS.learning.machine_learning import Feature
    prediction = classifier.predict([
        Feature(name="type", value="code"),
        Feature(name="language", value="python")
    ])
    print(f"   Prediction: {prediction.predicted_value} (confidence: {prediction.confidence:.2f})")
    
    # Knowledge Graph demo
    print("\n3. Knowledge Graph:")
    node1 = knowledge_graph.add_node("Python", "language")
    node2 = knowledge_graph.add_node("Code", "concept")
    knowledge_graph.add_edge(node1.id, node2.id, knowledge_graph.RelationType.RELATED_TO)
    print(f"   Nodes: {len(knowledge_graph.nodes)}")
    print(f"   Edges: {len(knowledge_graph.edges)}")
    
    # BFS traversal
    path = knowledge_graph.bfs_traverse(node1.id)
    print(f"   BFS path from Python: {' -> '.join([knowledge_graph.get_node(n).label for n in path])}")


async def demo_agents(jarvis):
    """Demonstrate Multi-Agent Coordination"""
    print("\n" + "="*60)
    print("DEMO: Multi-Agent Coordination (Phase 2 Week 3)")
    print("="*60)
    
    agent_system = jarvis.subsystems.get('agent_system')
    agent_comm = jarvis.subsystems.get('agent_communication')
    
    if not all([agent_system, agent_comm]):
        print("Agent components not available")
        return
    
    from JARVIS.agents.agent_system import AgentType, TaskPriority
    
    # Create agents
    print("\n1. Creating agents:")
    agent1 = agent_system.create_agent("Analyzer", AgentType.WORKER, {"analysis", "optimization"})
    agent2 = agent_system.create_agent("Learner", AgentType.LEARNER, {"learning", "adaptation"})
    print(f"   Created: {agent1.name} ({agent1.agent_type.value})")
    print(f"   Created: {agent2.name} ({agent2.agent_type.value})")
    
    # Create tasks
    print("\n2. Creating tasks:")
    task1 = agent_system.create_task("Analyze Code", "Analyze the codebase", "analysis", 
                                     TaskPriority.HIGH, {"analysis"})
    task2 = agent_system.create_task("Learn Pattern", "Learn from data", "learning", 
                                     TaskPriority.MEDIUM, {"learning"})
    print(f"   Created: {task1.title} (priority: {task1.priority.value})")
    print(f"   Created: {task2.title} (priority: {task2.priority.value})")
    
    # Assign tasks
    print("\n3. Assigning tasks:")
    agent_system.assign_task(task1.id, agent1.id)
    agent_system.assign_task(task2.id, agent2.id)
    print(f"   {agent1.name} assigned to: {task1.title}")
    print(f"   {agent2.name} assigned to: {task2.title}")
    
    # Agent communication
    print("\n4. Agent communication:")
    from JARVIS.agents.agent_communication import MessageType
    agent_comm.register_agent(agent1.id)
    agent_comm.register_agent(agent2.id)
    msg_id = agent_comm.send_message(agent1.id, agent2.id, MessageType.STATUS, 
                                     {"status": "working", "progress": 0.5})
    print(f"   Message sent: {msg_id}")
    messages = agent_comm.get_messages_for_agent(agent2.id)
    print(f"   Messages received by {agent2.name}: {len(messages)}")


async def demo_reasoning(jarvis):
    """Demonstrate Advanced Reasoning"""
    print("\n" + "="*60)
    print("DEMO: Advanced Reasoning (Phase 2 Week 4)")
    print("="*60)
    
    causal_reasoner = jarvis.subsystems.get('causal_reasoner')
    abductive_reasoner = jarvis.subsystems.get('abductive_reasoner')
    analogical_reasoner = jarvis.subsystems.get('analogical_reasoner')
    meta_reasoner = jarvis.subsystems.get('meta_reasoner')
    
    if not all([causal_reasoner, abductive_reasoner, analogical_reasoner, meta_reasoner]):
        print("Reasoning components not available")
        return
    
    # Causal reasoning
    print("\n1. Causal Reasoning:")
    from JARVIS.reasoning.causal_reasoning import CausalRelation
    node1 = causal_reasoner.add_node("System Slow", "symptom")
    node2 = causal_reasoner.add_node("High CPU", "cause")
    node3 = causal_reasoner.add_node("Memory Leak", "cause")
    causal_reasoner.add_edge(node2.id, node1.id, CausalRelation.DIRECT, 0.9)
    causal_reasoner.add_edge(node3.id, node1.id, CausalRelation.DIRECT, 0.7)
    causes = causal_reasoner.find_causes(node1.id)
    print(f"   Symptom: {node1.label}")
    print(f"   Causes: {[causal_reasoner.get_node(c).label for c in causes]}")
    
    # Abductive reasoning
    print("\n2. Abductive Reasoning:")
    obs = abductive_reasoner.add_observation("Application crashed unexpectedly")
    inference = abductive_reasoner.explain(obs)
    if inference.best_hypothesis:
        print(f"   Observation: {obs.text}")
        print(f"   Best explanation: {inference.best_hypothesis.explanation}")
        print(f"   Confidence: {inference.best_hypothesis.confidence:.2f}")
    
    # Analogical reasoning
    print("\n3. Analogical Reasoning:")
    concept1 = analogical_reasoner.add_concept("Python", {"type": "language", "paradigm": "OO"})
    concept2 = analogical_reasoner.add_concept("Java", {"type": "language", "paradigm": "OO"})
    analogies = analogical_reasoner.find_analogies(concept1.id)
    if analogies:
        analogy = analogies[0]
        print(f"   Source: {analogical_reasoner.get_concept(analogy.source_id).label}")
        print(f"   Target: {analogical_reasoner.get_concept(analogy.target_id).label}")
        print(f"   Similarity: {analogy.similarity_score:.2f}")
    
    # Meta-reasoning
    print("\n4. Meta-Reasoning:")
    from JARVIS.reasoning.meta_reasoning import ReasoningType
    process = meta_reasoner.create_process("Debug Analysis")
    meta_reasoner.add_step(process.id, ReasoningType.ABDUCTIVE, 
                          {"observation": obs.id}, {"hypothesis": "explanation"}, 0.85)
    meta_reasoner.complete_process(process.id, "Analysis complete")
    print(f"   Process: {process.name}")
    print(f"   Quality score: {process.quality:.2f}")
    print(f"   Status: {process.status}")


async def demo_integration(jarvis):
    """Demonstrate Cross-Component Integration"""
    print("\n" + "="*60)
    print("DEMO: Cross-Component Integration")
    print("="*60)
    
    print("\nFull Pipeline: User Input → NLU → Learning → Agents → Reasoning")
    
    # Get components
    nlu_intent = jarvis.subsystems.get('intent_recognizer')
    nlu_entity = jarvis.subsystems.get('entity_extractor')
    knowledge_graph = jarvis.subsystems.get('knowledge_graph')
    agent_system = jarvis.subsystems.get('agent_system')
    abductive_reasoner = jarvis.subsystems.get('abductive_reasoner')
    meta_reasoner = jarvis.subsystems.get('meta_reasoner')
    
    if not all([nlu_intent, nlu_entity, knowledge_graph, agent_system, 
                abductive_reasoner, meta_reasoner]):
        print("Some components not available for full pipeline")
        return
    
    # Step 1: NLU processing
    user_input = "The system is slow, please analyze the performance"
    print(f"\n1. NLU Processing:")
    print(f"   Input: '{user_input}'")
    intent = nlu_intent.recognize_intent(user_input)
    entities = nlu_entity.extract_entities(user_input)
    print(f"   Intent: {intent.intent.value}")
    print(f"   Entities: {len(entities)} extracted")
    
    # Step 2: Learning - add to knowledge graph
    print(f"\n2. Learning:")
    if entities:
        for entity in entities:
            node = knowledge_graph.add_node(entity.text, "entity")
            print(f"   Added to knowledge graph: {entity.text}")
    
    # Step 3: Agents - create task
    print(f"\n3. Agents:")
    from JARVIS.agents.agent_system import AgentType, TaskPriority
    agent = agent_system.create_agent("PerformanceAgent", AgentType.WORKER, {"analysis"})
    task = agent_system.create_task("Performance Analysis", "Analyze system performance", 
                                    "analysis", TaskPriority.HIGH, {"analysis"})
    agent_system.assign_task(task.id, agent.id)
    print(f"   Created agent: {agent.name}")
    print(f"   Assigned task: {task.title}")
    
    # Step 4: Reasoning - explain the issue
    print(f"\n4. Reasoning:")
    obs = abductive_reasoner.add_observation("System is slow")
    inference = abductive_reasoner.explain(obs)
    if inference.best_hypothesis:
        print(f"   Explanation: {inference.best_hypothesis.explanation}")
    
    # Step 5: Meta-reasoning - evaluate
    print(f"\n5. Meta-Reasoning:")
    from JARVIS.reasoning.meta_reasoning import ReasoningType
    process = meta_reasoner.create_process("Performance Pipeline")
    meta_reasoner.add_step(process.id, ReasoningType.ABDUCTIVE, 
                          {"input": user_input}, {"output": "analysis"}, 0.9)
    meta_reasoner.complete_process(process.id, "Pipeline complete")
    print(f"   Pipeline quality: {process.quality:.2f}")
    
    print("\n✅ Full pipeline executed successfully!")


async def main():
    """Main demo function"""
    print("\n" + "="*60)
    print("JARVIS OS - DEMO")
    print("="*60)
    print("Version: 1.5.0 (Phase 2 Complete)")
    print("Demonstrating all Phase 1 and Phase 2 capabilities")
    print("="*60)
    
    # Initialize Jarvis
    print("\nInitializing Jarvis OS...")
    jarvis = JarvisCore()
    
    try:
        await jarvis.initialize()
        print("\n✅ Jarvis OS initialized successfully!")
        
        # Show subsystems
        print(f"\nLoaded Subsystems ({len(jarvis.subsystems)}):")
        for name, subsystem in jarvis.subsystems.items():
            print(f"  - {name}")
        
        # Run demos
        await demo_nlu(jarvis)
        await demo_learning(jarvis)
        await demo_agents(jarvis)
        await demo_reasoning(jarvis)
        await demo_integration(jarvis)
        
        print("\n" + "="*60)
        print("DEMO COMPLETE")
        print("="*60)
        print("Jarvis OS is fully functional with all Phase 1 and Phase 2 capabilities!")
        print("="*60 + "\n")
        
    except Exception as e:
        print(f"\n❌ Error during demo: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        print("Shutting down Jarvis OS...")
        await jarvis.shutdown()
        print("✅ Shutdown complete")


if __name__ == "__main__":
    asyncio.run(main())
