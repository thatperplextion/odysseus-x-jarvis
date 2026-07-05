"""
Jarvis OS Test Suite
Tests core functionality of the Jarvis Operating System
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from JARVIS import get_jarvis


async def test_kernel():
    """Test kernel functionality"""
    print("\n=== Testing Kernel ===")
    jarvis = get_jarvis()
    
    # Test command execution
    process_id = await jarvis.subsystems['kernel'].execute_command("test command")
    print(f"✓ Command execution: {process_id}")
    
    # Get kernel status
    status = jarvis.subsystems['kernel'].get_status()
    print(f"✓ Kernel status: {status['state']}")
    
    return True


async def test_consciousness():
    """Test consciousness layer"""
    print("\n=== Testing Consciousness ===")
    jarvis = get_jarvis()
    
    # Test response generation
    response = jarvis.subsystems['consciousness'].generate_response("Hello Jarvis")
    print(f"✓ Response generation: {response}")
    
    # Get consciousness status
    status = jarvis.subsystems['consciousness'].get_status()
    print(f"✓ Consciousness status: {status['personality']}")
    
    return True


async def test_automation():
    """Test automation engine"""
    print("\n=== Testing Automation ===")
    jarvis = get_jarvis()
    
    # Create a simple workflow
    workflow_id = await jarvis.subsystems['automation'].create_workflow(
        name="Test Workflow",
        description="A test workflow",
        triggers=[],
        actions=[
            {"type": "log_message", "parameters": {"message": "Test action"}}
        ]
    )
    print(f"✓ Workflow creation: {workflow_id}")
    
    # Get automation status
    status = jarvis.subsystems['automation'].get_status()
    print(f"✓ Automation status: {status['workflows']} workflows")
    
    return True


async def test_interface():
    """Test system interface"""
    print("\n=== Testing System Interface ===")
    jarvis = get_jarvis()
    
    # Get system metrics
    metrics = jarvis.subsystems['interface'].get_system_metrics()
    print(f"✓ System metrics: CPU {metrics.get('cpu', {}).get('percent', 0)}%")
    
    # List processes
    processes = jarvis.subsystems['interface'].list_processes()
    print(f"✓ Process listing: {len(processes)} processes")
    
    return True


async def test_security():
    """Test security manager"""
    print("\n=== Testing Security ===")
    jarvis = get_jarvis()
    
    # Test permission check
    from JARVIS.security import Permission
    allowed = jarvis.subsystems['security'].check_permission(
        'system', Permission.FILE_READ
    )
    print(f"✓ Permission check: {allowed}")
    
    # Get security status
    status = jarvis.subsystems['security'].get_status()
    print(f"✓ Security status: {status['security_level']}")
    
    return True


async def test_learning():
    """Test learning engine"""
    print("\n=== Testing Learning ===")
    jarvis = get_jarvis()
    
    # Add observation
    await jarvis.subsystems['learning'].add_observation(
        'command',
        {'command': 'test', 'context': {}}
    )
    print("✓ Observation added")
    
    # Get learning status
    status = jarvis.subsystems['learning'].get_status()
    print(f"✓ Learning status: {status['metrics']['observations_processed']} observations")
    
    return True


async def test_communication():
    """Test communication manager"""
    print("\n=== Testing Communication ===")
    jarvis = get_jarvis()
    
    # Send text message
    message_id = await jarvis.subsystems['communication'].send_text_message(
        "Test message",
        "test_user"
    )
    print(f"✓ Text message: {message_id}")
    
    # Get communication status
    status = jarvis.subsystems['communication'].get_status()
    print(f"✓ Communication status: {status['voice_enabled']}")
    
    return True


async def test_integration():
    """Test integration manager"""
    print("\n=== Testing Integration ===")
    jarvis = get_jarvis()

    status = jarvis.subsystems['integration'].get_status()
    print(f"✓ Integration status: Odysseus bridge {status['odysseus_bridge_active']}")

    return True


async def test_autonomous():
    """Test autonomous agent"""
    print("\n=== Testing Autonomous Agent ===")
    jarvis = get_jarvis()

    result = await jarvis.process_command("status")
    print(f"✓ Command processing: {result.get('success')} - {result.get('response', '')[:60]}")

    if jarvis.autonomous_agent:
        status = jarvis.autonomous_agent.get_status()
        print(f"✓ Autonomous mode: {status.get('autonomous_mode')}")

    return True


async def run_all_tests():
    """Run all tests"""
    print("=" * 50)
    print("Jarvis OS Test Suite")
    print("=" * 50)
    
    # Initialize Jarvis
    print("\nInitializing Jarvis...")
    jarvis = get_jarvis()
    await jarvis.initialize()
    print("✓ Jarvis initialized")
    
    # Run tests
    tests = [
        test_kernel,
        test_consciousness,
        test_automation,
        test_interface,
        test_security,
        test_learning,
        test_communication,
        test_integration,
        test_autonomous,
    ]
    
    results = []
    for test in tests:
        try:
            result = await test()
            results.append((test.__name__, result))
        except Exception as e:
            print(f"✗ {test.__name__} failed: {e}")
            results.append((test.__name__, False))
    
    # Shutdown
    print("\nShutting down Jarvis...")
    await jarvis.shutdown()
    print("✓ Jarvis shutdown")
    
    # Summary
    print("\n" + "=" * 50)
    print("Test Summary")
    print("=" * 50)
    
    passed = sum(1 for _, result in results if result)
    total = len(results)
    
    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")
    
    print(f"\nTotal: {passed}/{total} tests passed")
    
    return passed == total


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
