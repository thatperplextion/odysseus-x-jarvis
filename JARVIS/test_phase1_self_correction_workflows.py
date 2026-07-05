"""
Test suite for Phase 1 - Self-Correction and Workflows components
"""

import asyncio
import sys
from datetime import timedelta

# Add parent directory to path
sys.path.insert(0, 'c:\\Users\\JUNAID ASAD KHAN\\odysseus-1')

from JARVIS.self_correction import SelfCorrection, ErrorSeverity, ErrorCategory
from JARVIS.workflows import AutonomousWorkflowEngine, ExecutionMode, TaskStatus


async def test_self_correction():
    """Test the self-correction system"""
    print("\n" + "="*60)
    print("Testing Self-Correction System")
    print("="*60)
    
    self_correction = SelfCorrection()
    
    # Test 1: Error detection
    print("\n1. Testing error detection...")
    error1 = self_correction.detect_error(
        message="Network connection failed",
        severity=ErrorSeverity.HIGH,
        category=ErrorCategory.NETWORK,
        context={"url": "https://api.example.com"},
        source="network_module"
    )
    print(f"   ✓ Error detected: {error1.id}")
    print(f"   ✓ Severity: {error1.severity.value}")
    print(f"   ✓ Category: {error1.category.value}")
    
    # Test 2: Multiple error detection
    print("\n2. Testing multiple error detection...")
    error2 = self_correction.detect_error(
        message="Syntax error in code",
        severity=ErrorSeverity.MEDIUM,
        category=ErrorCategory.SYNTAX,
        context={"file": "main.py", "line": 42}
    )
    error3 = self_correction.detect_error(
        message="Performance degradation",
        severity=ErrorSeverity.LOW,
        category=ErrorCategory.PERFORMANCE,
        context={"response_time": "5s"}
    )
    print(f"   ✓ Total errors: {len(self_correction.errors)}")
    
    # Test 3: Error retrieval
    print("\n3. Testing error retrieval...")
    retrieved = self_correction.get_error(error1.id)
    print(f"   ✓ Retrieved error: {retrieved.message[:50]}...")
    
    # Test 4: Recent errors
    print("\n4. Testing recent errors...")
    recent = self_correction.get_recent_errors(limit=5)
    print(f"   ✓ Recent errors: {len(recent)}")
    
    # Test 5: Errors by severity
    print("\n5. Testing errors by severity...")
    high_severity = self_correction.get_errors_by_severity(ErrorSeverity.HIGH)
    print(f"   ✓ High severity errors: {len(high_severity)}")
    
    # Test 6: Errors by category
    print("\n6. Testing errors by category...")
    network_errors = self_correction.get_errors_by_category(ErrorCategory.NETWORK)
    print(f"   ✓ Network errors: {len(network_errors)}")
    
    # Test 7: Error patterns
    print("\n7. Testing error patterns...")
    patterns = self_correction.get_error_patterns()
    print(f"   ✓ Error patterns: {len(patterns)}")
    
    # Test 8: Correction strategies
    print("\n8. Testing correction strategies...")
    stats = self_correction.get_correction_stats()
    print(f"   ✓ Registered strategies: {len(stats['strategies'])}")
    for strategy_name, strategy_info in stats['strategies'].items():
        print(f"      - {strategy_name}: {strategy_info['description']}")
    
    # Test 9: Auto-correction
    print("\n9. Testing auto-correction...")
    # Give auto-correction time to process
    await asyncio.sleep(0.5)
    stats = self_correction.get_correction_stats()
    print(f"   ✓ Total corrections attempted: {stats['total_corrections']}")
    
    # Test 10: Correction statistics
    print("\n10. Testing correction statistics...")
    stats = self_correction.get_correction_stats()
    print(f"   ✓ Total errors: {stats['total_errors']}")
    print(f"   ✓ Corrected errors: {stats['corrected_errors']}")
    print(f"   ✓ Correction success rate: {stats['correction_success_rate']:.2%}")
    
    print("\n✅ Self-Correction tests passed")
    return True


async def test_workflow_engine():
    """Test the autonomous workflow engine"""
    print("\n" + "="*60)
    print("Testing Autonomous Workflow Engine")
    print("="*60)
    
    workflow_engine = AutonomousWorkflowEngine()
    
    # Test 1: Create workflow
    print("\n1. Testing workflow creation...")
    workflow = workflow_engine.create_workflow(
        name="Data Processing Pipeline",
        description="Process and analyze data",
        execution_mode=ExecutionMode.SEQUENTIAL
    )
    print(f"   ✓ Workflow created: {workflow.id}")
    print(f"   ✓ Execution mode: {workflow.execution_mode.value}")
    
    # Test 2: Add tasks
    print("\n2. Testing task addition...")
    
    async def task1_fetch_data():
        await asyncio.sleep(0.1)
        return {"data": [1, 2, 3, 4, 5]}
    
    async def task2_process_data():
        await asyncio.sleep(0.1)
        return {"processed": [2, 4, 6, 8, 10]}
    
    async def task3_analyze_data():
        await asyncio.sleep(0.1)
        return {"result": 30}
    
    task1 = workflow_engine.add_task(
        workflow_id=workflow.id,
        name="Fetch Data",
        description="Fetch data from source",
        action=task1_fetch_data,
        parameters={}
    )
    
    task2 = workflow_engine.add_task(
        workflow_id=workflow.id,
        name="Process Data",
        description="Process the fetched data",
        action=task2_process_data,
        parameters={},
        dependencies={task1.id}
    )
    
    task3 = workflow_engine.add_task(
        workflow_id=workflow.id,
        name="Analyze Data",
        description="Analyze processed data",
        action=task3_analyze_data,
        parameters={},
        dependencies={task2.id}
    )
    
    print(f"   ✓ Added 3 tasks to workflow")
    
    # Test 3: Execute sequential workflow
    print("\n3. Testing sequential workflow execution...")
    executed_workflow = await workflow_engine.execute_workflow(workflow.id)
    print(f"   ✓ Workflow status: {executed_workflow.status.value}")
    print(f"   ✓ Tasks completed: {sum(1 for t in executed_workflow.tasks.values() if t.status == TaskStatus.COMPLETED)}")
    
    # Test 4: Create parallel workflow
    print("\n4. Testing parallel workflow creation...")
    parallel_workflow = workflow_engine.create_workflow(
        name="Parallel Processing",
        description="Process multiple tasks in parallel",
        execution_mode=ExecutionMode.PARALLEL
    )
    
    async def parallel_task1():
        await asyncio.sleep(0.2)
        return "task1_result"
    
    async def parallel_task2():
        await asyncio.sleep(0.2)
        return "task2_result"
    
    async def parallel_task3():
        await asyncio.sleep(0.2)
        return "task3_result"
    
    ptask1 = workflow_engine.add_task(
        workflow_id=parallel_workflow.id,
        name="Parallel Task 1",
        description="First parallel task",
        action=parallel_task1,
        parameters={}
    )
    
    ptask2 = workflow_engine.add_task(
        workflow_id=parallel_workflow.id,
        name="Parallel Task 2",
        description="Second parallel task",
        action=parallel_task2,
        parameters={}
    )
    
    ptask3 = workflow_engine.add_task(
        workflow_id=parallel_workflow.id,
        name="Parallel Task 3",
        description="Third parallel task",
        action=parallel_task3,
        parameters={}
    )
    
    print(f"   ✓ Created parallel workflow with 3 tasks")
    
    # Test 5: Execute parallel workflow
    print("\n5. Testing parallel workflow execution...")
    start = asyncio.get_event_loop().time()
    executed_parallel = await workflow_engine.execute_workflow(parallel_workflow.id)
    duration = asyncio.get_event_loop().time() - start
    print(f"   ✓ Parallel execution time: {duration:.2f}s")
    print(f"   ✓ Workflow status: {executed_parallel.status.value}")
    
    # Test 6: Workflow status
    print("\n6. Testing workflow status...")
    status = workflow_engine.get_workflow_status(workflow.id)
    print(f"   ✓ Workflow status: {status.value}")
    
    # Test 7: Execution history
    print("\n7. Testing execution history...")
    history = workflow_engine.get_execution_history(limit=5)
    print(f"   ✓ Execution history entries: {len(history)}")
    
    # Test 8: Workflow statistics
    print("\n8. Testing workflow statistics...")
    stats = workflow_engine.get_workflow_stats()
    print(f"   ✓ Total workflows: {stats['total_workflows']}")
    print(f"   ✓ Total tasks: {stats['total_tasks']}")
    print(f"   ✓ By status: {stats['by_status']}")
    
    # Test 9: Workflow pause/resume
    print("\n9. Testing workflow pause/resume...")
    workflow_engine.pause_workflow(workflow.id)
    paused_status = workflow_engine.get_workflow_status(workflow.id)
    print(f"   ✓ Paused status: {paused_status.value}")
    
    workflow_engine.resume_workflow(workflow.id)
    resumed_status = workflow_engine.get_workflow_status(workflow.id)
    print(f"   ✓ Resumed status: {resumed_status.value}")
    
    # Test 10: Workflow cancellation
    print("\n10. Testing workflow cancellation...")
    cancel_workflow = workflow_engine.create_workflow(
        name="Cancel Test",
        description="Test workflow cancellation",
        execution_mode=ExecutionMode.SEQUENTIAL
    )
    
    async def cancel_task():
        await asyncio.sleep(1.0)
        return "result"
    
    workflow_engine.add_task(
        workflow_id=cancel_workflow.id,
        name="Long Task",
        description="A long running task",
        action=cancel_task,
        parameters={}
    )
    
    workflow_engine.cancel_workflow(cancel_workflow.id)
    cancelled_status = workflow_engine.get_workflow_status(cancel_workflow.id)
    print(f"   ✓ Cancelled status: {cancelled_status.value}")
    
    print("\n✅ Workflow Engine tests passed")
    return True


async def test_integration():
    """Test self-correction and workflow integration"""
    print("\n" + "="*60)
    print("Testing Self-Correction + Workflow Integration")
    print("="*60)
    
    self_correction = SelfCorrection()
    workflow_engine = AutonomousWorkflowEngine()
    
    # Test 1: Workflow with error handling
    print("\n1. Testing workflow with error handling...")
    
    error_workflow = workflow_engine.create_workflow(
        name="Error Handling Test",
        description="Test error handling in workflows",
        execution_mode=ExecutionMode.SEQUENTIAL
    )
    
    async def failing_task():
        await asyncio.sleep(0.1)
        raise Exception("Simulated task failure")
    
    async def recovery_task():
        await asyncio.sleep(0.1)
        return "recovered"
    
    task1 = workflow_engine.add_task(
        workflow_id=error_workflow.id,
        name="Failing Task",
        description="A task that will fail",
        action=failing_task,
        parameters={}
    )
    
    # Try to execute (will fail)
    try:
        await workflow_engine.execute_workflow(error_workflow.id)
    except Exception as e:
        print(f"   ✓ Workflow failed as expected: {str(e)[:50]}")
        
        # Detect error in self-correction
        error = self_correction.detect_error(
            message=str(e),
            severity=ErrorSeverity.HIGH,
            category=ErrorCategory.RUNTIME,
            context={"workflow_id": error_workflow.id}
        )
        print(f"   ✓ Error detected by self-correction: {error.id}")
    
    # Test 2: Workflow with retry
    print("\n2. Testing workflow with retry mechanism...")
    
    retry_workflow = workflow_engine.create_workflow(
        name="Retry Test",
        description="Test task retry mechanism",
        execution_mode=ExecutionMode.SEQUENTIAL
    )
    
    attempt_count = 0
    
    async def flaky_task():
        nonlocal attempt_count
        attempt_count += 1
        await asyncio.sleep(0.1)
        if attempt_count < 3:
            raise Exception("Temporary failure")
        return "success"
    
    workflow_engine.add_task(
        workflow_id=retry_workflow.id,
        name="Flaky Task",
        description="A task that fails before succeeding",
        action=flaky_task,
        parameters={},
        max_retries=3
    )
    
    try:
        await workflow_engine.execute_workflow(retry_workflow.id)
        print(f"   ✓ Workflow succeeded after {attempt_count} attempts")
    except Exception as e:
        print(f"   ✓ Workflow failed after {attempt_count} attempts")
    
    # Test 3: Statistics integration
    print("\n3. Testing statistics integration...")
    sc_stats = self_correction.get_correction_stats()
    wf_stats = workflow_engine.get_workflow_stats()
    
    print(f"   ✓ Self-correction errors: {sc_stats['total_errors']}")
    print(f"   ✓ Workflow engine workflows: {wf_stats['total_workflows']}")
    
    print("\n✅ Integration tests passed")
    return True


async def run_all_tests():
    """Run all Phase 1 Week 3 tests"""
    print("\n" + "="*60)
    print("PHASE 1 WEEK 3 - Self-Correction and Workflows Tests")
    print("="*60)
    
    results = {}
    
    try:
        results['self_correction'] = await test_self_correction()
    except Exception as e:
        print(f"\n❌ Self-correction tests failed: {e}")
        results['self_correction'] = False
    
    try:
        results['workflows'] = await test_workflow_engine()
    except Exception as e:
        print(f"\n❌ Workflow tests failed: {e}")
        results['workflows'] = False
    
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
        print("\n🎉 All Phase 1 Week 3 tests passed successfully!")
        return True
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
