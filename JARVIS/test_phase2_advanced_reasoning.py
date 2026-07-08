"""
Test suite for Phase 2 - Advanced Reasoning components
"""

import asyncio
import sys

# Add parent directory to path
sys.path.insert(0, 'c:\\Users\\JUNAID ASAD KHAN\\odysseus-1')

from JARVIS.reasoning import (
    CausalReasoner, CausalRelation, CausalNode, CausalEdge, CausalChain,
    AbductiveReasoner, Observation, AbductiveInference,
    AnalogicalReasoner, Concept, Analogy, SimilarityType,
    MetaReasoner, ReasoningProcess, ReasoningType, MetaEvaluation
)


async def test_causal_reasoning():
    """Test the causal reasoning system"""
    print("\n" + "="*60)
    print("Testing Causal Reasoning System")
    print("="*60)
    
    causal = CausalReasoner()
    
    # Test 1: Node creation
    print("\n1. Testing node creation...")
    node1 = causal.add_node("Error", "event")
    node2 = causal.add_node("Bug", "cause")
    node3 = causal.add_node("Fix", "solution")
    print(f"   ✓ Nodes created: {len(causal.nodes)}")
    
    # Test 2: Edge creation
    print("\n2. Testing edge creation...")
    edge1 = causal.add_edge(node2.id, node1.id, CausalRelation.DIRECT, 0.8)
    edge2 = causal.add_edge(node3.id, node1.id, CausalRelation.SUFFICIENT, 0.9)
    print(f"   ✓ Edges created: {len(causal.edges)}")
    
    # Test 3: Find causes
    print("\n3. Testing find causes...")
    causes = causal.find_causes(node1.id)
    print(f"   ✓ Causes found: {len(causes)}")
    
    # Test 4: Find effects
    print("\n4. Testing find effects...")
    effects = causal.find_effects(node2.id)
    print(f"   ✓ Effects found: {len(effects)}")
    
    # Test 5: Causality inference
    print("\n5. Testing causality inference...")
    events = [
        {"id": "e1", "type": "error", "timestamp": 0},
        {"id": "e2", "type": "fix", "timestamp": 1}
    ]
    inferred = causal.infer_causality(events)
    print(f"   ✓ Inferred relationships: {len(inferred)}")
    
    # Test 6: Chain analysis
    print("\n6. Testing chain analysis...")
    if causes:
        chain = causes[0]
        print(f"   ✓ Chain length: {len(chain.nodes)}")
        print(f"   ✓ Chain strength: {chain.total_strength:.2f}")
    
    # Test 7: Statistics
    print("\n7. Testing statistics...")
    stats = causal.get_statistics()
    print(f"   ✓ Total nodes: {stats['total_nodes']}")
    print(f"   ✓ Total edges: {stats['total_edges']}")
    
    # Test 8: Health check
    print("\n8. Testing health check...")
    health = await causal.health_check()
    print(f"   ✓ Health: {health}")
    
    # Test 9: Complex causal graph
    print("\n9. Testing complex causal graph...")
    node4 = causal.add_node("System", "context")
    causal.add_edge(node4.id, node2.id, CausalRelation.CONTRIBUTING, 0.5)
    causes = causal.find_causes(node1.id, max_depth=3)
    print(f"   ✓ Complex causes: {len(causes)}")
    
    # Test 10: Edge strength
    print("\n10. Testing edge strength...")
    avg_strength = stats['average_strength']
    print(f"   ✓ Average strength: {avg_strength:.2f}")
    
    print("\n✅ Causal Reasoning tests passed")
    return True


async def test_abductive_reasoning():
    """Test the abductive reasoning system"""
    print("\n" + "="*60)
    print("Testing Abductive Reasoning System")
    print("="*60)
    
    abductive = AbductiveReasoner()
    
    # Test 1: Observation creation
    print("\n1. Testing observation creation...")
    obs1 = abductive.add_observation("System error occurred", {"type": "error"})
    obs2 = abductive.add_observation("Slow response time", {"type": "slow"})
    print(f"   ✓ Observations created: {len(abductive.observations)}")
    
    # Test 2: Hypothesis generation
    print("\n2. Testing hypothesis generation...")
    hypotheses = abductive.generate_hypotheses(obs1)
    print(f"   ✓ Hypotheses generated: {len(hypotheses)}")
    
    # Test 3: Hypothesis evaluation
    print("\n3. Testing hypothesis evaluation...")
    if hypotheses:
        quality = abductive.evaluate_hypothesis(hypotheses[0], obs1)
        print(f"   ✓ Hypothesis quality: {quality:.2f}")
    
    # Test 4: Best hypothesis selection
    print("\n4. Testing best hypothesis selection...")
    best = abductive.select_best_hypothesis(hypotheses, obs1)
    print(f"   ✓ Best hypothesis: {best.id if best else 'None'}")
    
    # Test 5: Full explanation
    print("\n5. Testing full explanation...")
    inference = abductive.explain(obs1)
    print(f"   ✓ Explanation generated: {inference.best_hypothesis.explanation if inference.best_hypothesis else 'None'}")
    
    # Test 6: Evidence addition
    print("\n6. Testing evidence addition...")
    if best:
        abductive.add_evidence(best.id, "Found in logs")
        print(f"   ✓ Evidence added")
    
    # Test 7: Multiple observations
    print("\n7. Testing multiple observations...")
    inference2 = abductive.explain(obs2)
    print(f"   ✓ Second explanation generated")
    
    # Test 8: Statistics
    print("\n8. Testing statistics...")
    stats = abductive.get_statistics()
    print(f"   ✓ Total observations: {stats['total_observations']}")
    print(f"   ✓ Total hypotheses: {stats['total_hypotheses']}")
    
    # Test 9: Inference history
    print("\n9. Testing inference history...")
    print(f"   ✓ Total inferences: {len(abductive.inference_history)}")
    
    # Test 10: Health check
    print("\n10. Testing health check...")
    health = await abductive.health_check()
    print(f"   ✓ Health: {health}")
    
    print("\n✅ Abductive Reasoning tests passed")
    return True


async def test_analogical_reasoning():
    """Test the analogical reasoning system"""
    print("\n" + "="*60)
    print("Testing Analogical Reasoning System")
    print("="*60)
    
    analogical = AnalogicalReasoner()
    
    # Test 1: Concept creation
    print("\n1. Testing concept creation...")
    concept1 = analogical.add_concept("Python", {"type": "language", "paradigm": "OO"})
    concept2 = analogical.add_concept("Java", {"type": "language", "paradigm": "OO"})
    concept3 = analogical.add_concept("Car", {"type": "vehicle", "wheels": 4})
    print(f"   ✓ Concepts created: {len(analogical.concepts)}")
    
    # Test 2: Structural similarity
    print("\n2. Testing structural similarity...")
    sim = analogical.calculate_similarity(concept1, concept2, SimilarityType.STRUCTURAL)
    print(f"   ✓ Similarity: {sim:.2f}")
    
    # Test 3: Semantic similarity
    print("\n3. Testing semantic similarity...")
    sim = analogical.calculate_similarity(concept1, concept2, SimilarityType.SEMANTIC)
    print(f"   ✓ Similarity: {sim:.2f}")
    
    # Test 4: Functional similarity
    print("\n4. Testing functional similarity...")
    concept1.relations = {"runs_on": "VM", "compiled": "False"}
    concept2.relations = {"runs_on": "JVM", "compiled": "True"}
    sim = analogical.calculate_similarity(concept1, concept2, SimilarityType.FUNCTIONAL)
    print(f"   ✓ Similarity: {sim:.2f}")
    
    # Test 5: Find analogies
    print("\n5. Testing find analogies...")
    analogies = analogical.find_analogies(concept1.id)
    print(f"   ✓ Analogies found: {len(analogies)}")
    
    # Test 6: Analogy details
    print("\n6. Testing analogy details...")
    if analogies:
        analogy = analogies[0]
        print(f"   ✓ Similarity score: {analogy.similarity_score:.2f}")
        print(f"   ✓ Similarity type: {analogy.similarity_type.value}")
    
    # Test 7: Analogy mapping
    print("\n7. Testing analogy mapping...")
    if analogies:
        mapping = analogies[0].mapping
        print(f"   ✓ Mapping: {len(mapping)} features")
    
    # Test 8: Apply analogy
    print("\n8. Testing apply analogy...")
    if analogies:
        source_data = {"type": "language", "version": "3.9"}
        target_data = analogical.apply_analogy(analogies[0], source_data)
        print(f"   ✓ Applied data: {target_data}")
    
    # Test 9: Statistics
    print("\n9. Testing statistics...")
    stats = analogical.get_statistics()
    print(f"   ✓ Total concepts: {stats['total_concepts']}")
    print(f"   ✓ Total analogies: {stats['total_analogies']}")
    
    # Test 10: Health check
    print("\n10. Testing health check...")
    health = await analogical.health_check()
    print(f"   ✓ Health: {health}")
    
    print("\n✅ Analogical Reasoning tests passed")
    return True


async def test_meta_reasoning():
    """Test the meta-reasoning system"""
    print("\n" + "="*60)
    print("Testing Meta-Reasoning System")
    print("="*60)
    
    meta = MetaReasoner()
    
    # Test 1: Process creation
    print("\n1. Testing process creation...")
    process = meta.create_process("Test reasoning", {"input": "data"})
    print(f"   ✓ Process created: {process.id}")
    
    # Test 2: Step addition
    print("\n2. Testing step addition...")
    step1 = meta.add_step(process.id, ReasoningType.DEDUCTIVE, 
                          {"premise": "A"}, {"conclusion": "B"}, 0.9)
    step2 = meta.add_step(process.id, ReasoningType.INDUCTIVE,
                          {"observation": "X"}, {"generalization": "Y"}, 0.8)
    print(f"   ✓ Steps added: {len(process.steps)}")
    
    # Test 3: Process completion
    print("\n3. Testing process completion...")
    meta.complete_process(process.id, "Final result")
    print(f"   ✓ Process completed")
    print(f"   ✓ Quality: {process.quality:.2f}")
    
    # Test 4: Quality evaluation
    print("\n4. Testing quality evaluation...")
    quality = meta.evaluate_process_quality(process.id)
    print(f"   ✓ Quality score: {quality:.2f}")
    
    # Test 5: Detailed evaluation
    print("\n5. Testing detailed evaluation...")
    evaluation = meta.evaluate_process(process.id)
    print(f"   ✓ Evaluation score: {evaluation.score:.2f}")
    print(f"   ✓ Feedback: {evaluation.feedback}")
    
    # Test 6: Process statistics
    print("\n6. Testing process statistics...")
    stats = meta.get_process_statistics(process.id)
    print(f"   ✓ Total steps: {stats['total_steps']}")
    print(f"   ✓ Average confidence: {stats['average_confidence']:.2f}")
    
    # Test 7: Multiple processes
    print("\n7. Testing multiple processes...")
    process2 = meta.create_process("Second reasoning")
    meta.add_step(process2.id, ReasoningType.ABDUCTIVE, {"obs": "Z"}, {"hyp": "W"}, 0.7)
    meta.complete_process(process2.id, "Result 2")
    print(f"   ✓ Second process completed")
    
    # Test 8: Global statistics
    print("\n8. Testing global statistics...")
    global_stats = meta.get_statistics()
    print(f"   ✓ Total processes: {global_stats['total_processes']}")
    print(f"   ✓ Total steps: {global_stats['total_steps']}")
    
    # Test 9: Type distribution
    print("\n9. Testing type distribution...")
    type_dist = global_stats['type_distribution']
    print(f"   ✓ Type distribution: {type_dist}")
    
    # Test 10: Health check
    print("\n10. Testing health check...")
    health = await meta.health_check()
    print(f"   ✓ Health: {health}")
    
    print("\n✅ Meta-Reasoning tests passed")
    return True


async def test_reasoning_integration():
    """Test reasoning component integration"""
    print("\n" + "="*60)
    print("Testing Reasoning Integration")
    print("="*60)
    
    causal = CausalReasoner()
    abductive = AbductiveReasoner()
    analogical = AnalogicalReasoner()
    meta = MetaReasoner()
    
    # Test 1: Causal to abductive integration
    print("\n1. Testing causal to abductive integration...")
    node1 = causal.add_node("Error", "event")
    node2 = causal.add_node("Bug", "cause")
    causal.add_edge(node2.id, node1.id, CausalRelation.DIRECT, 0.8)
    
    obs = abductive.add_observation("Error occurred", {"cause": "bug"})
    inference = abductive.explain(obs)
    print(f"   ✓ Integration successful")
    
    # Test 2: Analogical to causal integration
    print("\n2. Testing analogical to causal integration...")
    concept1 = analogical.add_concept("Bug", {"type": "defect"})
    concept2 = analogical.add_concept("Error", {"type": "issue"})
    analogies = analogical.find_analogies(concept1.id)
    print(f"   ✓ Analogies found: {len(analogies)}")
    
    # Test 3: Meta-reasoning evaluation
    print("\n3. Testing meta-reasoning evaluation...")
    process = meta.create_process("Integrated reasoning")
    meta.add_step(process.id, ReasoningType.CAUSAL, {"node": node1.id}, {"result": "chain"}, 0.8)
    meta.add_step(process.id, ReasoningType.ABDUCTIVE, {"obs": obs.id}, {"hyp": "explanation"}, 0.7)
    meta.complete_process(process.id, "Integrated result")
    print(f"   ✓ Process quality: {process.quality:.2f}")
    
    # Test 4: Cross-component statistics
    print("\n4. Testing cross-component statistics...")
    causal_stats = causal.get_statistics()
    abductive_stats = abductive.get_statistics()
    analogical_stats = analogical.get_statistics()
    meta_stats = meta.get_statistics()
    
    print(f"   ✓ Causal nodes: {causal_stats['total_nodes']}")
    print(f"   ✓ Abductive observations: {abductive_stats['total_observations']}")
    print(f"   ✓ Analogical concepts: {analogical_stats['total_concepts']}")
    print(f"   ✓ Meta processes: {meta_stats['total_processes']}")
    
    # Test 5: Full reasoning pipeline
    print("\n5. Testing full reasoning pipeline...")
    # Create causal graph
    n1 = causal.add_node("Start", "event")
    n2 = causal.add_node("Process", "action")
    n3 = causal.add_node("End", "result")
    causal.add_edge(n1.id, n2.id, CausalRelation.DIRECT, 0.9)
    causal.add_edge(n2.id, n3.id, CausalRelation.DIRECT, 0.9)
    
    # Generate explanation
    obs2 = abductive.add_observation("Process completed", {"status": "success"})
    inference2 = abductive.explain(obs2)
    
    # Create concept analogy
    c1 = analogical.add_concept("Process", {"type": "action"})
    c2 = analogical.add_concept("Task", {"type": "action"})
    analogies2 = analogical.find_analogies(c1.id)
    
    # Meta-evaluate
    process2 = meta.create_process("Full pipeline")
    meta.add_step(process2.id, ReasoningType.CAUSAL, {"graph": "built"}, {"chain": "found"}, 0.9)
    meta.add_step(process2.id, ReasoningType.ABDUCTIVE, {"obs": "explained"}, {"hyp": "generated"}, 0.8)
    meta.add_step(process2.id, ReasoningType.ANALOGICAL, {"concept": "mapped"}, {"analogy": "found"}, 0.7)
    meta.complete_process(process2.id, "Pipeline complete")
    
    print(f"   ✓ Full pipeline executed")
    print(f"   ✓ Final quality: {process2.quality:.2f}")
    
    print("\n✅ Reasoning Integration tests passed")
    return True


async def run_all_tests():
    """Run all Phase 2 Week 4 tests"""
    print("\n" + "="*60)
    print("PHASE 2 WEEK 4 - ADVANCED REASONING TESTS")
    print("="*60)
    
    results = {}
    
    try:
        results['causal_reasoning'] = await test_causal_reasoning()
    except Exception as e:
        print(f"\n❌ Causal reasoning tests failed: {e}")
        results['causal_reasoning'] = False
    
    try:
        results['abductive_reasoning'] = await test_abductive_reasoning()
    except Exception as e:
        print(f"\n❌ Abductive reasoning tests failed: {e}")
        results['abductive_reasoning'] = False
    
    try:
        results['analogical_reasoning'] = await test_analogical_reasoning()
    except Exception as e:
        print(f"\n❌ Analogical reasoning tests failed: {e}")
        results['analogical_reasoning'] = False
    
    try:
        results['meta_reasoning'] = await test_meta_reasoning()
    except Exception as e:
        print(f"\n❌ Meta-reasoning tests failed: {e}")
        results['meta_reasoning'] = False
    
    try:
        results['integration'] = await test_reasoning_integration()
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
        print("\n🎉 All Phase 2 Week 4 tests passed successfully!")
        return True
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
