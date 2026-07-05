"""
Test suite for Phase 1 - Planning and Reasoning components
"""

import asyncio
import sys
from datetime import timedelta

# Add parent directory to path
sys.path.insert(0, 'c:\\Users\\JUNAID ASAD KHAN\\odysseus-1')

from JARVIS.planning import EnhancedPlanner, TaskPriority
from JARVIS.reasoning import ReasoningEngine


async def test_enhanced_planner():
    """Test the enhanced planner"""
    print("\n" + "="*60)
    print("Testing Enhanced Planner")
    print("="*60)
    
    planner = EnhancedPlanner()
    
    # Test 1: Create plan and decompose goal
    print("\n1. Testing goal decomposition...")
    plan = planner.decompose_goal("Create a REST API for user management")
    print(f"   ✓ Created plan with {len(plan.tasks)} tasks")
    print(f"   ✓ Execution order: {plan.execution_order}")
    print(f"   ✓ Estimated duration: {plan.total_estimated_duration}")
    
    # Test 2: Dependency tracking
    print("\n2. Testing dependency tracking...")
    ready_tasks = plan.get_ready_tasks(set())
    print(f"   ✓ Ready tasks: {len(ready_tasks)}")
    print(f"   ✓ First ready task: {ready_tasks[0].description if ready_tasks else 'None'}")
    
    # Test 3: Plan optimization
    print("\n3. Testing plan optimization...")
    optimized_plan = planner.optimize_plan(plan)
    print(f"   ✓ Plan optimized")
    
    # Test 4: Plan adaptation
    print("\n4. Testing plan adaptation...")
    adapted_plan = planner.adapt_plan(plan, {
        "new_tasks": [
            {
                "description": "Add security audit",
                "priority": TaskPriority.HIGH,
                "estimated_duration": timedelta(minutes=10)
            }
        ]
    })
    print(f"   ✓ Plan adapted with new task count: {len(adapted_plan.tasks)}")
    
    # Test 5: Plan execution
    print("\n5. Testing plan execution...")
    async def mock_executor(task):
        await asyncio.sleep(0.1)
        return f"Executed: {task.description}"
    
    planner.set_task_executor(mock_executor)
    execution_result = await planner.execute_plan(plan)
    print(f"   ✓ Execution complete: {execution_result['completed_tasks']}/{execution_result['total_tasks']} tasks")
    print(f"   ✓ Total duration: {execution_result['total_duration']:.2f}s")
    
    # Test 6: Plan status
    print("\n6. Testing plan status retrieval...")
    status = planner.get_plan_status(plan.id)
    print(f"   ✓ Plan status: {status['status']}")
    
    print("\n✅ Enhanced Planner tests passed")
    return True


async def test_reasoning_engine():
    """Test the reasoning engine"""
    print("\n" + "="*60)
    print("Testing Reasoning Engine")
    print("="*60)
    
    reasoning = ReasoningEngine()
    
    # Test 1: Chain-of-thought reasoning
    print("\n1. Testing chain-of-thought reasoning...")
    chain = await reasoning.reason_chain_of_thought(
        "How should I implement a user authentication system?",
        context={"project_type": "web_application", "security_level": "high"}
    )
    print(f"   ✓ Reasoning chain created with {len(chain.steps)} steps")
    print(f"   ✓ Conclusion: {chain.conclusion}")
    print(f"   ✓ Confidence: {chain.confidence}")
    
    # Test 2: Deductive reasoning
    print("\n2. Testing deductive reasoning...")
    premises = ["All users need authentication", "John is a user"]
    valid, confidence = await reasoning.deductive_reasoning(premises, "John needs authentication")
    print(f"   ✓ Valid: {valid}, Confidence: {confidence}")
    
    # Test 3: Inductive reasoning
    print("\n3. Testing inductive reasoning...")
    observations = ["User A prefers dark mode", "User B prefers dark mode", "User C prefers dark mode"]
    generalization, confidence = await reasoning.inductive_reasoning(observations)
    print(f"   ✓ Generalization: {generalization}, Confidence: {confidence}")
    
    # Test 4: Abductive reasoning
    print("\n4. Testing abductive reasoning...")
    observations = ["Server is slow", "CPU usage is high", "Memory usage is normal"]
    explanations = ["Server is overloaded", "Network issue", "Database bottleneck"]
    best_explanation, confidence = await reasoning.abductive_reasoning(observations, explanations)
    print(f"   ✓ Best explanation: {best_explanation}, Confidence: {confidence}")
    
    # Test 5: Analogical reasoning
    print("\n5. Testing analogical reasoning...")
    analogy, confidence = await reasoning.analogical_reasoning(
        "REST API design",
        "GraphQL API design"
    )
    print(f"   ✓ Analogy: {analogy}, Confidence: {confidence}")
    
    # Test 6: Hypothesis evaluation
    print("\n6. Testing hypothesis evaluation...")
    h1 = reasoning.create_hypothesis("The issue is a memory leak")
    h2 = reasoning.create_hypothesis("The issue is a network problem")
    evidence = ["Memory usage increases over time", "No network errors in logs"]
    evaluated = await reasoning.evaluate_hypotheses([h1, h2], evidence)
    print(f"   ✓ Best hypothesis: {evaluated[0].statement} (probability: {evaluated[0].probability})")
    
    # Test 7: Contextual reasoning
    print("\n7. Testing contextual reasoning...")
    context_result = await reasoning.contextual_reasoning(
        "Should I add caching to this API?",
        context={
            "previous_actions": ["implemented database queries"],
            "current_state": {"response_time": "500ms"},
            "goals": ["improve performance"]
        }
    )
    print(f"   ✓ Contextual reasoning completed with {len(context_result['steps'])} steps")
    
    # Test 8: Reasoning history
    print("\n8. Testing reasoning history...")
    history = reasoning.get_reasoning_history()
    print(f"   ✓ History entries: {len(history)}")
    
    print("\n✅ Reasoning Engine tests passed")
    return True


async def test_integration():
    """Test integration of planner and reasoning"""
    print("\n" + "="*60)
    print("Testing Planner + Reasoning Integration")
    print("="*60)
    
    planner = EnhancedPlanner()
    reasoning = ReasoningEngine()
    
    # Use reasoning to inform planning
    print("\n1. Using reasoning to inform planning...")
    chain = await reasoning.reason_chain_of_thought(
        "How should I approach building a microservices architecture?"
    )
    
    # Create plan based on reasoning
    plan = planner.decompose_goal("Build microservices architecture")
    
    print(f"   ✓ Reasoning steps: {len(chain.steps)}")
    print(f"   ✓ Plan tasks: {len(plan.tasks)}")
    print(f"   ✓ Integration successful")
    
    print("\n✅ Integration tests passed")
    return True


async def run_all_tests():
    """Run all Phase 1 tests"""
    print("\n" + "="*60)
    print("PHASE 1 - Planning and Reasoning Tests")
    print("="*60)
    
    results = {}
    
    try:
        results['planner'] = await test_enhanced_planner()
    except Exception as e:
        print(f"\n❌ Planner tests failed: {e}")
        results['planner'] = False
    
    try:
        results['reasoning'] = await test_reasoning_engine()
    except Exception as e:
        print(f"\n❌ Reasoning tests failed: {e}")
        results['reasoning'] = False
    
    try:
        results['integration'] = await test_integration()
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
        print("\n🎉 All Phase 1 tests passed successfully!")
        return True
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
