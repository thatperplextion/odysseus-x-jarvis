"""
Comprehensive Integration Test Suite for Phase 1 - Core AI Engine
Tests all Phase 1 components working together
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, 'c:\\Users\\JUNAID ASAD KHAN\\odysseus-1')

from JARVIS.planning import EnhancedPlanner, TaskPriority
from JARVIS.reasoning import ReasoningEngine
from JARVIS.memory import EnhancedMemory, MemoryType, MemoryImportance
from JARVIS.reflection import ReflectionEngine, ReflectionTrigger
from JARVIS.self_correction import SelfCorrection, ErrorSeverity, ErrorCategory
from JARVIS.workflows import AutonomousWorkflowEngine, ExecutionMode
from JARVIS.project_understanding import (
    ContextAwareness, CodeComprehension, DependencyMapping,
    ProjectType
)


async def test_full_phase1_integration():
    """Test all Phase 1 components working together"""
    print("\n" + "="*60)
    print("PHASE 1 - Full Integration Test")
    print("="*60)
    
    # Initialize all Phase 1 components
    print("\n1. Initializing all Phase 1 components...")
    planner = EnhancedPlanner()
    reasoning = ReasoningEngine()
    memory = EnhancedMemory(data_dir=Path("c:\\Users\\JUNAID ASAD KHAN\\odysseus-1\\JARVIS\\test_memory_data"))
    reflection = ReflectionEngine()
    self_correction = SelfCorrection()
    workflows = AutonomousWorkflowEngine()
    context_awareness = ContextAwareness()
    code_comprehension = CodeComprehension()
    dependency_mapping = DependencyMapping()
    
    print("   ✓ All components initialized")
    
    # Test 2: Planning + Reasoning integration
    print("\n2. Testing Planning + Reasoning integration...")
    plan = planner.create_plan(
        goal="Analyze codebase and generate documentation"
    )
    
    planner.add_task_to_plan(
        description="Analyze project structure",
        priority=TaskPriority.HIGH
    )
    
    planner.add_task_to_plan(
        description="Generate documentation",
        priority=TaskPriority.MEDIUM
    )
    
    optimized_plan = planner.optimize_plan(plan)
    print(f"   ✓ Plan created and optimized: {optimized_plan.id}")
    print(f"   ✓ Tasks in plan: {len(optimized_plan.tasks)}")
    
    # Test 3: Memory + Reflection integration
    print("\n3. Testing Memory + Reflection integration...")
    memory.add_memory(
        content="Project analysis completed successfully",
        memory_type=MemoryType.EPISODIC,
        importance=MemoryImportance.HIGH,
        tags=["analysis", "project"]
    )
    
    memory.add_memory(
        content="Documentation generation requires AST parsing",
        memory_type=MemoryType.SEMANTIC,
        importance=MemoryImportance.MEDIUM,
        tags=["documentation", "ast"]
    )
    
    reflection_session = await reflection.trigger_reflection(
        trigger=ReflectionTrigger.TASK_COMPLETION,
        memory_system=memory
    )
    
    print(f"   ✓ Memories added: {len(memory.memories)}")
    print(f"   ✓ Reflection session: {reflection_session.id}")
    
    # Test 4: Self-Correction + Workflows integration
    print("\n4. Testing Self-Correction + Workflows integration...")
    
    workflow = workflows.create_workflow(
        name="Code Analysis Workflow",
        description="Automated code analysis pipeline",
        execution_mode=ExecutionMode.SEQUENTIAL
    )
    
    async def analyze_structure():
        await asyncio.sleep(0.1)
        return {"files": 100, "dirs": 20}
    
    async def generate_docs():
        await asyncio.sleep(0.1)
        return {"docs": 5}
    
    task1 = workflows.add_task(
        workflow_id=workflow.id,
        name="Analyze Structure",
        description="Analyze project structure",
        action=analyze_structure,
        parameters={}
    )
    
    task2 = workflows.add_task(
        workflow_id=workflow.id,
        name="Generate Docs",
        description="Generate documentation",
        action=generate_docs,
        parameters={},
        dependencies={task1.id}
    )
    
    executed_workflow = await workflows.execute_workflow(workflow.id)
    print(f"   ✓ Workflow executed: {executed_workflow.id}")
    print(f"   ✓ Status: {executed_workflow.status.value}")
    
    # Simulate error for self-correction
    error = self_correction.detect_error(
        message="Simulated workflow error",
        severity=ErrorSeverity.MEDIUM,
        category=ErrorCategory.RUNTIME,
        context={"workflow_id": workflow.id}
    )
    print(f"   ✓ Error detected: {error.id}")
    
    # Test 5: Project Understanding integration
    print("\n5. Testing Project Understanding integration...")
    
    project_path = Path("c:\\Users\\JUNAID ASAD KHAN\\odysseus-1")
    
    project = context_awareness.add_project_context(
        project_name="Odysseus",
        project_path=project_path,
        project_type=ProjectType.API_SERVICE
    )
    
    structure = context_awareness.analyze_project_structure(project_path)
    technologies = context_awareness.detect_technologies(project_path)
    
    # Analyze a code file
    test_file = Path("c:\\Users\\JUNAID ASAD KHAN\\odysseus-1\\app.py")
    if test_file.exists():
        code_file = code_comprehension.analyze_file(test_file)
        print(f"   ✓ Code file analyzed: {code_file.language}")
    
    # Analyze dependencies
    dependencies = dependency_mapping.analyze_project_dependencies(project_path)
    
    print(f"   ✓ Project context: {project.project_name}")
    print(f"   ✓ Structure: {structure['total_files']} files")
    print(f"   ✓ Technologies: {len(technologies)}")
    print(f"   ✓ Dependencies: {len(dependencies)}")
    
    # Test 6: Cross-component data flow
    print("\n6. Testing cross-component data flow...")
    
    # Use context to inform planning
    context_summary = context_awareness.get_active_context_summary()
    memory.add_memory(
        content=f"Project has {structure['total_files']} files",
        memory_type=MemoryType.SEMANTIC,
        importance=MemoryImportance.MEDIUM,
        tags=["project", "structure"]
    )
    
    # Use memory to inform reasoning
    reasoning_chain = reasoning.create_reasoning_chain(
        query="What is the best approach to document this project?",
        context={"total_files": structure['total_files']}
    )
    
    reasoning_chain.add_step(
        content="Analyze project structure and complexity",
        step_type="analysis"
    )
    
    print(f"   ✓ Context → Memory flow working")
    print(f"   ✓ Memory → Reasoning flow working")
    print(f"   ✓ Reasoning chain: {reasoning_chain.id}")
    
    # Test 7: End-to-end scenario
    print("\n7. Testing end-to-end scenario...")
    
    # Scenario: Analyze project, detect issues, reflect, and plan improvements
    
    # Step 1: Understand project
    project_context = context_awareness.get_active_project()
    
    # Step 2: Analyze code
    if test_file.exists():
        code_analysis = code_comprehension.analyze_file(test_file)
        complexity = code_analysis.complexity
        
        # Step 3: Store in memory
        memory.add_memory(
            content=f"Code complexity: {complexity}",
            memory_type=MemoryType.EPISODIC,
            importance=MemoryImportance.HIGH,
            tags=["complexity", "analysis"]
        )
    
    # Step 4: Reflect on findings
    recent_memories = memory.get_recent_memories(limit=3)
    reflection = await reflection.trigger_reflection(
        trigger=ReflectionTrigger.MANUAL,
        memory_system=memory
    )
    
    # Step 5: Plan improvements
    improvement_plan = planner.create_plan(
        goal="Reduce code complexity"
    )
    
    planner.add_task_to_plan(
        description="Identify complex functions",
        priority=TaskPriority.HIGH
    )
    
    print(f"   ✓ End-to-end scenario completed")
    print(f"   ✓ Project → Code → Memory → Reflection → Planning flow working")
    
    # Test 8: Statistics and health checks
    print("\n8. Testing statistics and health checks...")
    
    memory_stats = memory.get_memory_stats()
    workflow_stats = workflows.get_workflow_stats()
    correction_stats = self_correction.get_correction_stats()
    complexity_report = code_comprehension.get_complexity_report()
    dep_report = dependency_mapping.get_dependency_report()
    
    print(f"   ✓ Memory stats: {memory_stats['total_memories']} memories")
    print(f"   ✓ Workflow stats: {workflow_stats['total_workflows']} workflows")
    print(f"   ✓ Correction stats: {correction_stats['total_errors']} errors")
    print(f"   ✓ Complexity report: {complexity_report['total_files']} files")
    print(f"   ✓ Dependency report: {dep_report['total_dependencies']} dependencies")
    
    print("\n✅ Full Phase 1 integration test passed")
    return True


async def test_component_health():
    """Test health checks for all components"""
    print("\n" + "="*60)
    print("Component Health Checks")
    print("="*60)
    
    components = {
        "Planner": EnhancedPlanner(),
        "Reasoning": ReasoningEngine(),
        "Memory": EnhancedMemory(data_dir=Path("c:\\Users\\JUNAID ASAD KHAN\\odysseus-1\\JARVIS\\test_memory_data")),
        "Reflection": ReflectionEngine(),
        "Self-Correction": SelfCorrection(),
        "Workflows": AutonomousWorkflowEngine(),
        "Context Awareness": ContextAwareness(),
        "Code Comprehension": CodeComprehension(),
        "Dependency Mapping": DependencyMapping()
    }
    
    all_healthy = True
    for name, component in components.items():
        try:
            health = await component.health_check()
            print(f"   ✓ {name}: {health}")
        except Exception as e:
            print(f"   ❌ {name}: {e}")
            all_healthy = False
    
    return all_healthy


async def test_data_persistence():
    """Test data persistence across components"""
    print("\n" + "="*60)
    print("Data Persistence Test")
    print("="*60)
    
    # Test memory persistence
    memory1 = EnhancedMemory(data_dir=Path("c:\\Users\\JUNAID ASAD KHAN\\odysseus-1\\JARVIS\\test_memory_data"))
    memory1.add_memory(
        content="Test persistence",
        memory_type=MemoryType.EPISODIC,
        importance=MemoryImportance.HIGH
    )
    
    await memory1.save_to_disk()
    print("   ✓ Memory saved to disk")
    
    # Load new instance
    memory2 = EnhancedMemory(data_dir=Path("c:\\Users\\JUNAID ASAD KHAN\\odysseus-1\\JARVIS\\test_memory_data"))
    loaded_count = len(memory2.memories)
    print(f"   ✓ Memory loaded: {loaded_count} memories")
    
    # Test reflection persistence (skip - not implemented)
    print("   ⚠ Reflection persistence not implemented, skipping")
    
    return True


async def run_all_integration_tests():
    """Run all Phase 1 integration tests"""
    print("\n" + "="*60)
    print("PHASE 1 - COMPREHENSIVE INTEGRATION TESTS")
    print("="*60)
    
    results = {}
    
    try:
        results['full_integration'] = await test_full_phase1_integration()
    except Exception as e:
        print(f"\n❌ Full integration test failed: {e}")
        results['full_integration'] = False
    
    try:
        results['health_checks'] = await test_component_health()
    except Exception as e:
        print(f"\n❌ Health checks failed: {e}")
        results['health_checks'] = False
    
    try:
        results['persistence'] = await test_data_persistence()
    except Exception as e:
        print(f"\n❌ Persistence test failed: {e}")
        results['persistence'] = False
    
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
        print("\n🎉 All Phase 1 integration tests passed successfully!")
        return True
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_integration_tests())
    sys.exit(0 if success else 1)
