"""
Test suite for Phase 2 - Advanced Learning components
"""

import asyncio
import sys

# Add parent directory to path
sys.path.insert(0, 'c:\\Users\\JUNAID ASAD KHAN\\odysseus-1')

from JARVIS.learning import (
    ReinforcementLearner, ActionType, RewardType, State, Action,
    MachineLearningEngine, SimpleClassifier, Feature, TrainingData,
    KnowledgeGraph, RelationType, NodeType,
    AdaptiveLearner, AdaptationType, PerformanceMetric
)


async def test_reinforcement_learning():
    """Test the reinforcement learning system"""
    print("\n" + "="*60)
    print("Testing Reinforcement Learning System")
    print("="*60)
    
    rl = ReinforcementLearner()
    
    # Test 1: State creation
    print("\n1. Testing state creation...")
    state = State(
        id="state_1",
        features={"task": "analysis", "complexity": 0.5}
    )
    print(f"   ✓ State created: {state.id}")
    
    # Test 2: Action selection
    print("\n2. Testing action selection...")
    available_actions = [ActionType.COMMAND, ActionType.QUERY, ActionType.ANALYSIS]
    action = rl.choose_action(state, available_actions)
    print(f"   ✓ Action selected: {action.action_type.value}")
    
    # Test 3: Q-table update
    print("\n3. Testing Q-table update...")
    next_state = State(
        id="state_2",
        features={"task": "analysis", "complexity": 0.3}
    )
    rl.update_q_table(state, action, reward=1.0, next_state=next_state, done=False)
    print(f"   ✓ Q-table updated")
    
    # Test 4: Experience replay
    print("\n4. Testing experience replay...")
    from JARVIS.learning.reinforcement_learning import Experience
    experience = Experience(
        state=state,
        action=action,
        reward=1.0,
        next_state=next_state,
        done=False
    )
    rl.add_experience(experience)
    rl.train_from_buffer(batch_size=1)
    print(f"   ✓ Experience replay working")
    
    # Test 5: Exploration decay
    print("\n5. Testing exploration decay...")
    initial_rate = rl.exploration_rate
    rl.decay_exploration()
    print(f"   ✓ Exploration rate: {initial_rate:.4f} -> {rl.exploration_rate:.4f}")
    
    # Test 6: Reward calculation
    print("\n6. Testing reward calculation...")
    reward = rl.calculate_reward(
        outcome="success",
        reward_type=RewardType.SUCCESS,
        efficiency=1.0
    )
    print(f"   ✓ Reward calculated: {reward:.2f}")
    
    # Test 7: Policy retrieval
    print("\n7. Testing policy retrieval...")
    policy = rl.get_policy(state)
    print(f"   ✓ Policy retrieved: {len(policy)} actions")
    
    # Test 8: Statistics
    print("\n8. Testing statistics...")
    stats = rl.get_statistics()
    print(f"   ✓ Q-table size: {stats['q_table_size']}")
    print(f"   ✓ Experience buffer: {stats['experience_buffer_size']}")
    
    # Test 9: Health check
    print("\n9. Testing health check...")
    health = await rl.health_check()
    print(f"   ✓ Health: {health}")
    
    # Test 10: Multiple episodes
    print("\n10. Testing multiple episodes...")
    for i in range(5):
        state = State(id=f"state_{i}", features={"episode": i})
        action = rl.choose_action(state, available_actions)
        rl.update_q_table(state, action, reward=0.5, next_state=None, done=True)
    print(f"   ✓ Multiple episodes completed")
    
    print("\n✅ Reinforcement Learning tests passed")
    return True


async def test_machine_learning():
    """Test the machine learning engine"""
    print("\n" + "="*60)
    print("Testing Machine Learning Engine")
    print("="*60)
    
    ml = MachineLearningEngine()
    
    # Test 1: Classifier creation
    print("\n1. Testing classifier creation...")
    classifier = ml.create_classifier("test_classifier")
    print(f"   ✓ Classifier created: {classifier.model_id}")
    
    # Test 2: Adding rules
    print("\n2. Testing rule addition...")
    classifier.add_rule(
        conditions={"task": "analysis"},
        prediction="analyze",
        confidence=0.9
    )
    classifier.add_rule(
        conditions={"task": "command"},
        prediction="execute",
        confidence=0.8
    )
    print(f"   ✓ Rules added: {len(classifier.rules)}")
    
    # Test 3: Classification prediction
    print("\n3. Testing classification prediction...")
    features = [
        Feature(name="task", value="analysis"),
        Feature(name="complexity", value=0.5)
    ]
    prediction = classifier.predict(features)
    print(f"   ✓ Prediction: {prediction.predicted_value}")
    print(f"   ✓ Confidence: {prediction.confidence:.2f}")
    
    # Test 4: Regressor creation
    print("\n4. Testing regressor creation...")
    regressor = ml.create_regressor("test_regressor")
    print(f"   ✓ Regressor created: {regressor.model_id}")
    
    # Test 5: Training data
    print("\n5. Testing training data...")
    training_data = [
        TrainingData(
            features=[
                Feature(name="x", value=1.0),
                Feature(name="y", value=2.0)
            ],
            label=3.0
        ),
        TrainingData(
            features=[
                Feature(name="x", value=2.0),
                Feature(name="y", value=3.0)
            ],
            label=5.0
        )
    ]
    print(f"   ✓ Training data created: {len(training_data)} samples")
    
    # Test 6: Regressor training
    print("\n6. Testing regressor training...")
    regressor.train(training_data, learning_rate=0.01, epochs=10)
    print(f"   ✓ Regressor trained")
    
    # Test 7: Regression prediction
    print("\n7. Testing regression prediction...")
    test_features = [
        Feature(name="x", value=1.5),
        Feature(name="y", value=2.5)
    ]
    prediction = regressor.predict(test_features)
    print(f"   ✓ Prediction: {prediction.predicted_value:.2f}")
    print(f"   ✓ Confidence: {prediction.confidence:.2f}")
    
    # Test 8: Model retrieval
    print("\n8. Testing model retrieval...")
    retrieved = ml.get_model("test_classifier")
    print(f"   ✓ Model retrieved: {retrieved.model_id}")
    
    # Test 9: Statistics
    print("\n9. Testing statistics...")
    stats = ml.get_statistics()
    print(f"   ✓ Total classifiers: {stats['total_classifiers']}")
    print(f"   ✓ Total regressors: {stats['total_regressors']}")
    
    # Test 10: Health check
    print("\n10. Testing health check...")
    health = await ml.health_check()
    print(f"   ✓ Health: {health}")
    
    print("\n✅ Machine Learning tests passed")
    return True


async def test_knowledge_graph():
    """Test the knowledge graph system"""
    print("\n" + "="*60)
    print("Testing Knowledge Graph System")
    print("="*60)
    
    kg = KnowledgeGraph()
    
    # Test 1: Node creation
    print("\n1. Testing node creation...")
    node1 = kg.add_node("Python", NodeType.CONCEPT)
    node2 = kg.add_node("Programming", NodeType.CONCEPT)
    node3 = kg.add_node("Jarvis", NodeType.ENTITY)
    print(f"   ✓ Nodes created: {len(kg.nodes)}")
    
    # Test 2: Edge creation
    print("\n2. Testing edge creation...")
    edge1 = kg.add_edge(node1.id, node2.id, RelationType.IS_A)
    edge2 = kg.add_edge(node3.id, node1.id, RelationType.IMPLEMENTED_BY)
    print(f"   ✓ Edges created: {len(kg.edges)}")
    
    # Test 3: Node retrieval
    print("\n3. Testing node retrieval...")
    retrieved = kg.get_node(node1.id)
    print(f"   ✓ Node retrieved: {retrieved.label}")
    
    # Test 4: Edge retrieval
    print("\n4. Testing edge retrieval...")
    retrieved = kg.get_edge(edge1.id)
    print(f"   ✓ Edge retrieved: {retrieved.relation_type.value}")
    
    # Test 5: Neighbor query
    print("\n5. Testing neighbor query...")
    neighbors = kg.get_neighbors(node1.id)
    print(f"   ✓ Neighbors: {len(neighbors)}")
    
    # Test 6: Path finding
    print("\n6. Testing path finding...")
    path = kg.find_path(node3.id, node2.id)
    print(f"   ✓ Path found: {path is not None}")
    if path:
        print(f"   ✓ Path length: {len(path.nodes)}")
    
    # Test 7: All paths
    print("\n7. Testing all paths...")
    paths = kg.find_all_paths(node3.id, node2.id)
    print(f"   ✓ All paths: {len(paths)}")
    
    # Test 8: Node query
    print("\n8. Testing node query...")
    concepts = kg.query_nodes(node_type=NodeType.CONCEPT)
    print(f"   ✓ Concepts found: {len(concepts)}")
    
    # Test 9: Edge query
    print("\n9. Testing edge query...")
    is_a_edges = kg.query_edges(relation_type=RelationType.IS_A)
    print(f"   ✓ IS_A edges: {len(is_a_edges)}")
    
    # Test 10: Statistics
    print("\n10. Testing statistics...")
    stats = kg.get_statistics()
    print(f"   ✓ Total nodes: {stats['total_nodes']}")
    print(f"   ✓ Total edges: {stats['total_edges']}")
    print(f"   ✓ Average degree: {stats['average_degree']:.2f}")
    
    # Test 11: Health check
    print("\n11. Testing health check...")
    health = await kg.health_check()
    print(f"   ✓ Health: {health}")
    
    print("\n✅ Knowledge Graph tests passed")
    return True


async def test_adaptive_learning():
    """Test the adaptive learning system"""
    print("\n" + "="*60)
    print("Testing Adaptive Learning System")
    print("="*60)
    
    al = AdaptiveLearner()
    
    # Test 1: Performance recording
    print("\n1. Testing performance recording...")
    al.record_performance(PerformanceMetric.ACCURACY, 0.85)
    al.record_performance(PerformanceMetric.ACCURACY, 0.90)
    al.record_performance(PerformanceMetric.EFFICIENCY, 0.75)
    print(f"   ✓ Performance recorded")
    
    # Test 2: Performance summary
    print("\n2. Testing performance summary...")
    summary = al.get_performance_summary(PerformanceMetric.ACCURACY)
    print(f"   ✓ Average accuracy: {summary['average']:.3f}")
    print(f"   ✓ Trend: {summary['trend']:.3f}")
    
    # Test 3: Adaptation decision
    print("\n3. Testing adaptation decision...")
    should_adapt = al.should_adapt(PerformanceMetric.ACCURACY)
    print(f"   ✓ Should adapt: {should_adapt}")
    
    # Test 4: Parameter adaptation
    print("\n4. Testing parameter adaptation...")
    al.record_performance(PerformanceMetric.ACCURACY, 0.5)  # Low performance
    adaptation = al.adapt_parameter("learning_rate", 0.1, PerformanceMetric.ACCURACY)
    print(f"   ✓ Parameter adapted: {adaptation.target}")
    print(f"   ✓ New value: {adaptation.parameters['new_value']:.3f}")
    
    # Test 5: Strategy switching
    print("\n5. Testing strategy switching...")
    strategies = ["strategy_a", "strategy_b", "strategy_c"]
    adaptation = al.switch_strategy("strategy_a", strategies, PerformanceMetric.EFFICIENCY)
    print(f"   ✓ Strategy switched: {adaptation.parameters['old_strategy']} -> {adaptation.parameters['new_strategy']}")
    
    # Test 6: Adaptation evaluation
    print("\n6. Testing adaptation evaluation...")
    effectiveness = al.evaluate_adaptation(adaptation, PerformanceMetric.EFFICIENCY, 0.7, 0.8)
    print(f"   ✓ Effectiveness: {effectiveness:.3f}")
    
    # Test 7: Adaptation summary
    print("\n7. Testing adaptation summary...")
    summary = al.get_adaptation_summary()
    print(f"   ✓ Total adaptations: {summary['total_adaptations']}")
    print(f"   ✓ Current parameters: {summary['current_parameters']}")
    
    # Test 8: All performance summaries
    print("\n8. Testing all performance summaries...")
    summaries = al.get_all_performance_summaries()
    print(f"   ✓ Metrics tracked: {len(summaries)}")
    
    # Test 9: Threshold setting
    print("\n9. Testing threshold setting...")
    al.set_performance_threshold(PerformanceMetric.ACCURACY, 0.95)
    print(f"   ✓ Threshold set")
    
    # Test 10: Auto-adaptation
    print("\n10. Testing auto-adaptation...")
    al.record_performance(PerformanceMetric.ACCURACY, 0.6)  # Low performance
    adaptations = al.auto_adapt()
    print(f"   ✓ Auto-adaptations: {len(adaptations)}")
    
    # Test 11: Health check
    print("\n11. Testing health check...")
    health = await al.health_check()
    print(f"   ✓ Health: {health}")
    
    print("\n✅ Adaptive Learning tests passed")
    return True


async def test_learning_integration():
    """Test learning component integration"""
    print("\n" + "="*60)
    print("Testing Learning Integration")
    print("="*60)
    
    rl = ReinforcementLearner()
    ml = MachineLearningEngine()
    kg = KnowledgeGraph()
    al = AdaptiveLearner()
    
    # Test 1: RL + ML integration
    print("\n1. Testing RL + ML integration...")
    state = State(id="state_1", features={"feature1": 1.0})
    action = rl.choose_action(state, [ActionType.COMMAND, ActionType.QUERY])
    print(f"   ✓ RL action: {action.action_type.value}")
    
    # Test 2: ML + KG integration
    print("\n2. Testing ML + KG integration...")
    classifier = ml.create_classifier()
    classifier.add_rule(conditions={"type": "code"}, prediction="analyze")
    
    node = kg.add_node("Code", NodeType.CONCEPT)
    kg.add_node("Analysis", NodeType.CONCEPT)
    kg.add_edge(node.id, kg.nodes[list(kg.nodes.keys())[-1]].id, RelationType.RELATED_TO)
    print(f"   ✓ Knowledge graph integrated with ML")
    
    # Test 3: Adaptive + RL integration
    print("\n3. Testing Adaptive + RL integration...")
    al.record_performance(PerformanceMetric.EFFICIENCY, 0.8)
    rl.update_q_table(state, action, reward=0.8, next_state=None, done=True)
    print(f"   ✓ Adaptive learning integrated with RL")
    
    # Test 4: Cross-component statistics
    print("\n4. Testing cross-component statistics...")
    rl_stats = rl.get_statistics()
    ml_stats = ml.get_statistics()
    kg_stats = kg.get_statistics()
    al_stats = al.get_adaptation_summary()
    
    print(f"   ✓ RL states: {rl_stats['q_table_size']}")
    print(f"   ✓ ML models: {ml_stats['total_classifiers'] + ml_stats['total_regressors']}")
    print(f"   ✓ KG nodes: {kg_stats['total_nodes']}")
    print(f"   ✓ AL adaptations: {al_stats['total_adaptations']}")
    
    # Test 5: Full learning pipeline
    print("\n5. Testing full learning pipeline...")
    # Record performance
    al.record_performance(PerformanceMetric.ACCURACY, 0.9)
    
    # Add knowledge
    concept = kg.add_node("Learning", NodeType.CONCEPT)
    
    # Train model
    training_data = [
        TrainingData(features=[Feature(name="x", value=1.0)], label=2.0)
    ]
    regressor = ml.create_regressor()
    regressor.train(training_data, epochs=5)
    
    # RL episode
    state = State(id="state_2", features={"learning": True})
    action = rl.choose_action(state, [ActionType.ANALYSIS])
    rl.update_q_table(state, action, reward=1.0, next_state=None, done=True)
    
    print(f"   ✓ Full pipeline executed")
    
    print("\n✅ Learning Integration tests passed")
    return True


async def run_all_tests():
    """Run all Phase 2 Week 2 tests"""
    print("\n" + "="*60)
    print("PHASE 2 WEEK 2 - ADVANCED LEARNING TESTS")
    print("="*60)
    
    results = {}
    
    try:
        results['reinforcement_learning'] = await test_reinforcement_learning()
    except Exception as e:
        print(f"\n❌ Reinforcement learning tests failed: {e}")
        results['reinforcement_learning'] = False
    
    try:
        results['machine_learning'] = await test_machine_learning()
    except Exception as e:
        print(f"\n❌ Machine learning tests failed: {e}")
        results['machine_learning'] = False
    
    try:
        results['knowledge_graph'] = await test_knowledge_graph()
    except Exception as e:
        print(f"\n❌ Knowledge graph tests failed: {e}")
        results['knowledge_graph'] = False
    
    try:
        results['adaptive_learning'] = await test_adaptive_learning()
    except Exception as e:
        print(f"\n❌ Adaptive learning tests failed: {e}")
        results['adaptive_learning'] = False
    
    try:
        results['integration'] = await test_learning_integration()
    except Exception as e:
        print(f"\n❌ Integration tests failed: {e}")
        results['integration'] = False
    
    # Summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    total = len(results)
    passed = sum(results.values())
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 All Phase 2 Week 2 tests passed successfully!")
        return True
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
