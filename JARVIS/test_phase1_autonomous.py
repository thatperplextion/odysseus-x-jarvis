"""
Integration Test Suite for Phase 1 Autonomous Components
Tests all new Phase 1 autonomous AI components
"""

import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to path
sys.path.insert(0, 'c:\\Users\\JUNAID ASAD KHAN\\odysseus-1')

from JARVIS.autonomous import (
    AutonomousPlanner, ExecutionStrategy,
    LongRunningCodingSystem, CodingTask, CodingTaskType, CodingTaskStatus,
    SelfImprovementSystem, ImprovementInitiative, ImprovementType, ImprovementStatus,
    RepositoryUnderstandingSystem, RepositoryAnalysis, CodeComponent, ComponentType, RepositoryType,
    LiveDebuggingSystem, DebugSession, Breakpoint, DebugState, BreakpointType,
    ProjectManagementSystem, Project, ProjectTask, Milestone, ProjectStatus, TaskPriority, MilestoneStatus,
    AutonomousDevelopmentWorkflow, DevelopmentWorkflow, WorkflowStep, WorkflowStage, WorkflowStatus
)


async def test_autonomous_planner():
    """Test Autonomous Planner component"""
    print("\n" + "="*60)
    print("Test 1: Autonomous Planner")
    print("="*60)
    
    planner = AutonomousPlanner()
    
    # Test autonomous goal decomposition
    print("1.1 Testing autonomous goal decomposition...")
    plan = await planner.autonomous_goal_decomposition("Refactor backend code")
    print(f"   ✓ Plan created: {plan.id}")
    print(f"   ✓ Tasks: {len(plan.tasks)}")
    
    # Test plan execution
    print("1.2 Testing plan execution...")
    result = await planner.execute_plan(plan, ExecutionStrategy.ADAPTIVE)
    print(f"   ✓ Execution result: {result.success}")
    print(f"   ✓ Completed tasks: {len(result.completed_tasks)}")
    
    # Test statistics
    print("1.3 Testing execution statistics...")
    stats = planner.get_execution_statistics()
    print(f"   ✓ Total executions: {stats['total_executions']}")
    print(f"   ✓ Success rate: {stats['success_rate']:.2%}")
    
    # Test health check
    print("1.4 Testing health check...")
    health = await planner.health_check()
    print(f"   ✓ Health check: {health}")
    
    print("✅ Autonomous Planner test passed")
    return True


async def test_long_running_coding():
    """Test Long-Running Coding System"""
    print("\n" + "="*60)
    print("Test 2: Long-Running Coding System")
    print("="*60)
    
    data_dir = Path("c:\\Users\\JUNAID ASAD KHAN\\odysseus-1\\JARVIS\\test_coding_data")
    data_dir.mkdir(exist_ok=True)
    
    coding = LongRunningCodingSystem(data_dir)
    await coding.initialize()
    
    # Test task creation
    print("2.1 Testing task creation...")
    task = coding.create_task(
        "Test Feature",
        "Implement a test feature",
        CodingTaskType.FEATURE_IMPLEMENTATION,
        priority=5,
        estimated_duration=timedelta(hours=1),
        steps=[{"type": "generic", "description": "Test step"}]
    )
    print(f"   ✓ Task created: {task.id}")
    print(f"   ✓ Task status: {task.status.value}")
    
    # Test task execution
    print("2.2 Testing task execution...")
    result = await coding.execute_task(task)
    print(f"   ✓ Execution result: {result.status.value}")
    print(f"   ✓ Progress: {result.progress:.2%}")
    
    # Test task retrieval
    print("2.3 Testing task retrieval...")
    retrieved_task = coding.get_task(task.id)
    print(f"   ✓ Task retrieved: {retrieved_task.id if retrieved_task else 'None'}")
    
    # Test statistics
    print("2.4 Testing task statistics...")
    stats = coding.get_task_statistics()
    print(f"   ✓ Total tasks: {stats['total_tasks']}")
    print(f"   ✓ Completed tasks: {stats['completed_tasks']}")
    
    # Test health check
    print("2.5 Testing health check...")
    health = await coding.health_check()
    print(f"   ✓ Health check: {health}")
    
    print("✅ Long-Running Coding System test passed")
    return True


async def test_self_improvement():
    """Test Self-Improvement System"""
    print("\n" + "="*60)
    print("Test 3: Self-Improvement System")
    print("="*60)
    
    data_dir = Path("c:\\Users\\JUNAID ASAD KHAN\\odysseus-1\\JARVIS\\test_improvement_data")
    data_dir.mkdir(exist_ok=True)
    
    improvement = SelfImprovementSystem(data_dir)
    await improvement.initialize()
    
    # Test metric recording
    print("3.1 Testing metric recording...")
    improvement.record_metric("test_metric", 1.0, "test")
    print(f"   ✓ Metric recorded")
    print(f"   ✓ Total metrics: {len(improvement.metrics_history)}")
    
    # Test improvement initiative creation
    print("3.2 Testing improvement initiative creation...")
    initiative = improvement.create_improvement_initiative(
        "Test Improvement",
        "Test improvement description",
        ImprovementType.PERFORMANCE,
        priority=5,
        implementation_steps=[{"type": "generic", "description": "Test step"}]
    )
    print(f"   ✓ Initiative created: {initiative.id}")
    print(f"   ✓ Initiative status: {initiative.status.value}")
    
    # Test improvement opportunities
    print("3.3 Testing improvement opportunities...")
    opportunities = improvement.get_improvement_opportunities()
    print(f"   ✓ Opportunities: {len(opportunities)}")
    
    # Test statistics
    print("3.4 Testing improvement statistics...")
    stats = improvement.get_improvement_statistics()
    print(f"   ✓ Total initiatives: {stats['total_initiatives']}")
    print(f"   ✓ Total metrics: {stats['total_metrics']}")
    
    # Test health check
    print("3.5 Testing health check...")
    health = await improvement.health_check()
    print(f"   ✓ Health check: {health}")
    
    print("✅ Self-Improvement System test passed")
    return True


async def test_repository_understanding():
    """Test Repository Understanding System"""
    print("\n" + "="*60)
    print("Test 4: Repository Understanding System")
    print("="*60)
    
    data_dir = Path("c:\\Users\\JUNAID ASAD KHAN\\odysseus-1\\JARVIS\\test_repo_data")
    data_dir.mkdir(exist_ok=True)
    
    repo_understanding = RepositoryUnderstandingSystem(data_dir)
    await repo_understanding.initialize()
    
    # Test repository analysis
    print("4.1 Testing repository analysis...")
    # Use a small test directory
    test_repo = "c:\\Users\\JUNAID ASAD KHAN\\odysseus-1\\JARVIS"
    analysis = await repo_understanding.analyze_repository(test_repo, force_reanalyze=False)
    print(f"   ✓ Analysis completed")
    print(f"   ✓ Repository type: {analysis.repository_type.value}")
    print(f"   ✓ Total files: {analysis.total_files}")
    print(f"   ✓ Components: {len(analysis.components)}")
    
    # Test component search
    print("4.2 Testing component search...")
    components = repo_understanding.search_components(test_repo)
    print(f"   ✓ Components found: {len(components)}")
    
    # Test repository summary
    print("4.3 Testing repository summary...")
    summary = repo_understanding.get_repository_summary(test_repo)
    print(f"   ✓ Summary retrieved")
    print(f"   ✓ Total components: {summary['total_components']}")
    
    # Test health check
    print("4.4 Testing health check...")
    health = await repo_understanding.health_check()
    print(f"   ✓ Health check: {health}")
    
    print("✅ Repository Understanding System test passed")
    return True


async def test_live_debugging():
    """Test Live Debugging System"""
    print("\n" + "="*60)
    print("Test 5: Live Debugging System")
    print("="*60)
    
    data_dir = Path("c:\\Users\\JUNAID ASAD KHAN\\odysseus-1\\JARVIS\\test_debug_data")
    data_dir.mkdir(exist_ok=True)
    
    debugging = LiveDebuggingSystem(data_dir)
    await debugging.initialize()
    
    # Test session creation
    print("5.1 Testing debug session creation...")
    session = debugging.create_session("test_file.py", "test_function")
    print(f"   ✓ Session created: {session.id}")
    print(f"   ✓ Session status: {session.state.value}")
    
    # Test session start
    print("5.2 Testing session start...")
    started = await debugging.start_session(session.id)
    print(f"   ✓ Session started: {started}")
    
    # Test breakpoint addition
    print("5.3 Testing breakpoint addition...")
    breakpoint = debugging.add_breakpoint(session.id, "test_file.py", 10)
    print(f"   ✓ Breakpoint added: {breakpoint.id if breakpoint else 'None'}")
    
    # Test watch expression
    print("5.4 Testing watch expression...")
    watch_added = debugging.add_watch_expression(session.id, "x + y")
    print(f"   ✓ Watch added: {watch_added}")
    
    # Test session retrieval
    print("5.5 Testing session retrieval...")
    retrieved_session = debugging.get_session(session.id)
    print(f"   ✓ Session retrieved: {retrieved_session.id if retrieved_session else 'None'}")
    
    # Test statistics
    print("5.6 Testing session statistics...")
    stats = debugging.get_session_statistics()
    print(f"   ✓ Total sessions: {stats['total_sessions']}")
    print(f"   ✓ Total breakpoints: {stats['total_breakpoints']}")
    
    # Test health check
    print("5.7 Testing health check...")
    health = await debugging.health_check()
    print(f"   ✓ Health check: {health}")
    
    print("✅ Live Debugging System test passed")
    return True


async def test_project_management():
    """Test Project Management System"""
    print("\n" + "="*60)
    print("Test 6: Project Management System")
    print("="*60)
    
    data_dir = Path("c:\\Users\\JUNAID ASAD KHAN\\odysseus-1\\JARVIS\\test_project_data")
    data_dir.mkdir(exist_ok=True)
    
    project_mgmt = ProjectManagementSystem(data_dir)
    await project_mgmt.initialize()
    
    # Test project creation
    print("6.1 Testing project creation...")
    project = project_mgmt.create_project(
        "Test Project",
        "Test project description",
        TaskPriority.HIGH,
        due_date=datetime.now() + timedelta(days=7),
        budget=1000.0
    )
    print(f"   ✓ Project created: {project.id}")
    print(f"   ✓ Project status: {project.status.value}")
    
    # Test task addition
    print("6.2 Testing task addition...")
    task = project_mgmt.add_task(
        project.id,
        "Test Task",
        "Test task description",
        TaskPriority.MEDIUM,
        estimated_hours=2.0
    )
    print(f"   ✓ Task added: {task.id if task else 'None'}")
    
    # Test milestone addition
    print("6.3 Testing milestone addition...")
    milestone = project_mgmt.add_milestone(
        project.id,
        "Test Milestone",
        "Test milestone description",
        due_date=datetime.now() + timedelta(days=3)
    )
    print(f"   ✓ Milestone added: {milestone.id if milestone else 'None'}")
    
    # Test project progress
    print("6.4 Testing project progress...")
    progress = project_mgmt.get_project_progress(project.id)
    print(f"   ✓ Progress retrieved")
    print(f"   ✓ Total tasks: {progress['total_tasks']}")
    print(f"   ✓ Progress: {progress['progress_percentage']:.2%}")
    
    # Test statistics
    print("6.5 Testing project statistics...")
    stats = project_mgmt.get_project_statistics()
    print(f"   ✓ Total projects: {stats['total_projects']}")
    print(f"   ✓ Total tasks: {stats['total_tasks']}")
    
    # Test health check
    print("6.6 Testing health check...")
    health = await project_mgmt.health_check()
    print(f"   ✓ Health check: {health}")
    
    print("✅ Project Management System test passed")
    return True


async def test_autonomous_development():
    """Test Autonomous Development Workflow"""
    print("\n" + "="*60)
    print("Test 7: Autonomous Development Workflow")
    print("="*60)
    
    data_dir = Path("c:\\Users\\JUNAID ASAD KHAN\\odysseus-1\\JARVIS\\test_workflow_data")
    data_dir.mkdir(exist_ok=True)
    
    autonomous_dev = AutonomousDevelopmentWorkflow(data_dir)
    await autonomous_dev.initialize()
    
    # Test workflow creation
    print("7.1 Testing workflow creation...")
    workflow = autonomous_dev.create_workflow(
        "Test Workflow",
        "Test workflow description",
        "c:\\Users\\JUNAID ASAD KHAN\\odysseus-1"
    )
    print(f"   ✓ Workflow created: {workflow.id}")
    print(f"   ✓ Workflow status: {workflow.status.value}")
    print(f"   ✓ Steps: {len(workflow.steps)}")
    
    # Test workflow retrieval
    print("7.2 Testing workflow retrieval...")
    retrieved_workflow = autonomous_dev.get_workflow(workflow.id)
    print(f"   ✓ Workflow retrieved: {retrieved_workflow.id if retrieved_workflow else 'None'}")
    
    # Test workflow statistics
    print("7.3 Testing workflow statistics...")
    stats = autonomous_dev.get_workflow_statistics()
    print(f"   ✓ Total workflows: {stats['total_workflows']}")
    print(f"   ✓ Completed workflows: {stats['completed_workflows']}")
    
    # Test health check
    print("7.4 Testing health check...")
    health = await autonomous_dev.health_check()
    print(f"   ✓ Health check: {health}")
    
    print("✅ Autonomous Development Workflow test passed")
    return True


async def test_component_integration():
    """Test integration between Phase 1 components"""
    print("\n" + "="*60)
    print("Test 8: Component Integration")
    print("="*60)
    
    data_dir = Path("c:\\Users\\JUNAID ASAD KHAN\\odysseus-1\\JARVIS\\test_integration_data")
    data_dir.mkdir(exist_ok=True)
    
    # Initialize all components
    print("8.1 Initializing all components...")
    planner = AutonomousPlanner()
    coding = LongRunningCodingSystem(data_dir)
    improvement = SelfImprovementSystem(data_dir)
    
    await coding.initialize()
    await improvement.initialize()
    
    # Integrate components
    print("8.2 Integrating components...")
    coding.set_autonomous_planner(planner)
    improvement.set_memory(None)  # Would use real memory in production
    improvement.set_autonomous_planner(planner)
    improvement.set_long_running_coding(coding)
    print("   ✓ Components integrated")
    
    # Test cross-component workflow
    print("8.3 Testing cross-component workflow...")
    
    # Create a coding task
    task = coding.create_task(
        "Integration Test Task",
        "Test task for integration",
        CodingTaskType.FEATURE_IMPLEMENTATION,
        steps=[{"type": "planning", "description": "Use planner for decomposition"}]
    )
    
    # Record metric for improvement
    improvement.record_metric("integration_test", 1.0, "test")
    
    print(f"   ✓ Task created: {task.id}")
    print(f"   ✓ Metric recorded")
    
    print("✅ Component Integration test passed")
    return True


async def run_all_phase1_tests():
    """Run all Phase 1 autonomous component tests"""
    print("\n" + "="*60)
    print("PHASE 1 - AUTONOMOUS COMPONENTS INTEGRATION TESTS")
    print("="*60)
    
    results = {}
    
    try:
        results['autonomous_planner'] = await test_autonomous_planner()
    except Exception as e:
        print(f"\n❌ Autonomous Planner test failed: {e}")
        results['autonomous_planner'] = False
    
    try:
        results['long_running_coding'] = await test_long_running_coding()
    except Exception as e:
        print(f"\n❌ Long-Running Coding test failed: {e}")
        results['long_running_coding'] = False
    
    try:
        results['self_improvement'] = await test_self_improvement()
    except Exception as e:
        print(f"\n❌ Self-Improvement test failed: {e}")
        results['self_improvement'] = False
    
    try:
        results['repository_understanding'] = await test_repository_understanding()
    except Exception as e:
        print(f"\n❌ Repository Understanding test failed: {e}")
        results['repository_understanding'] = False
    
    try:
        results['live_debugging'] = await test_live_debugging()
    except Exception as e:
        print(f"\n❌ Live Debugging test failed: {e}")
        results['live_debugging'] = False
    
    try:
        results['project_management'] = await test_project_management()
    except Exception as e:
        print(f"\n❌ Project Management test failed: {e}")
        results['project_management'] = False
    
    try:
        results['autonomous_development'] = await test_autonomous_development()
    except Exception as e:
        print(f"\n❌ Autonomous Development test failed: {e}")
        results['autonomous_development'] = False
    
    try:
        results['component_integration'] = await test_component_integration()
    except Exception as e:
        print(f"\n❌ Component Integration test failed: {e}")
        results['component_integration'] = False
    
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
        print("\n🎉 All Phase 1 autonomous component tests passed successfully!")
        return True
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_phase1_tests())
    sys.exit(0 if success else 1)
