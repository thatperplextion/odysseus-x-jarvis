"""
Direct API Test for Phase 1 Endpoints
Tests Phase 1 API endpoints using FastAPI TestClient without requiring full server startup
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, 'c:\\Users\\JUNAID ASAD KHAN\\odysseus-1')

from fastapi.testclient import TestClient
import app

# Create test client - app is the module, app.app is the FastAPI instance
client = TestClient(app.app)

def test_phase1_endpoints():
    """Test all Phase 1 API endpoints"""
    print("\n" + "="*60)
    print("Phase 1 API Endpoint Tests")
    print("="*60)
    
    results = {}
    
    # Test 1: Autonomous Planner endpoints
    print("\n1. Testing Autonomous Planner endpoints...")
    try:
        # Create plan
        response = client.post("/api/jarvis/autonomous/create_plan", json={
            "goal": "Test goal",
            "context": {},
            "strategy": "adaptive"
        })
        print(f"   POST /api/jarvis/autonomous/create_plan: {response.status_code}")
        if response.status_code == 503:
            print("   ⚠️  Service unavailable (expected - Jarvis not initialized)")
            results['autonomous_planner'] = True
        else:
            print(f"   Response: {response.json()}")
            results['autonomous_planner'] = response.status_code == 200
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results['autonomous_planner'] = False
    
    # Test 2: Long-Running Coding endpoints
    print("\n2. Testing Long-Running Coding endpoints...")
    try:
        response = client.post("/api/jarvis/coding/create_task", json={
            "name": "Test task",
            "description": "Test description",
            "task_type": "feature_implementation",
            "priority": 5,
            "estimated_duration_hours": 1.0,
            "steps": []
        })
        print(f"   POST /api/jarvis/coding/create_task: {response.status_code}")
        if response.status_code == 503:
            print("   ⚠️  Service unavailable (expected - Jarvis not initialized)")
            results['long_running_coding'] = True
        else:
            print(f"   Response: {response.json()}")
            results['long_running_coding'] = response.status_code == 200
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results['long_running_coding'] = False
    
    # Test 3: Self-Improvement endpoints
    print("\n3. Testing Self-Improvement endpoints...")
    try:
        response = client.post("/api/jarvis/improvement/record_metric", json={
            "name": "test_metric",
            "value": 1.0,
            "unit": "test",
            "context": {}
        })
        print(f"   POST /api/jarvis/improvement/record_metric: {response.status_code}")
        if response.status_code == 503:
            print("   ⚠️  Service unavailable (expected - Jarvis not initialized)")
            results['self_improvement'] = True
        else:
            print(f"   Response: {response.json()}")
            results['self_improvement'] = response.status_code == 200
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results['self_improvement'] = False
    
    # Test 4: Repository Understanding endpoints
    print("\n4. Testing Repository Understanding endpoints...")
    try:
        response = client.post("/api/jarvis/repository/analyze", json={
            "repository_path": "c:\\Users\\JUNAID ASAD KHAN\\odysseus-1",
            "force_reanalyze": False
        })
        print(f"   POST /api/jarvis/repository/analyze: {response.status_code}")
        if response.status_code == 503:
            print("   ⚠️  Service unavailable (expected - Jarvis not initialized)")
            results['repository_understanding'] = True
        else:
            print(f"   Response: {response.json()}")
            results['repository_understanding'] = response.status_code == 200
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results['repository_understanding'] = False
    
    # Test 5: Live Debugging endpoints
    print("\n5. Testing Live Debugging endpoints...")
    try:
        response = client.post("/api/jarvis/debugging/create_session", json={
            "target_file": "test.py",
            "target_function": None
        })
        print(f"   POST /api/jarvis/debugging/create_session: {response.status_code}")
        if response.status_code == 503:
            print("   ⚠️  Service unavailable (expected - Jarvis not initialized)")
            results['live_debugging'] = True
        else:
            print(f"   Response: {response.json()}")
            results['live_debugging'] = response.status_code == 200
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results['live_debugging'] = False
    
    # Test 6: Project Management endpoints
    print("\n6. Testing Project Management endpoints...")
    try:
        response = client.post("/api/jarvis/project/create", json={
            "name": "Test Project",
            "description": "Test description",
            "priority": 5,
            "due_date": None,
            "budget": None,
            "team_members": [],
            "tags": []
        })
        print(f"   POST /api/jarvis/project/create: {response.status_code}")
        if response.status_code == 503:
            print("   ⚠️  Service unavailable (expected - Jarvis not initialized)")
            results['project_management'] = True
        else:
            print(f"   Response: {response.json()}")
            results['project_management'] = response.status_code == 200
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results['project_management'] = False
    
    # Test 7: Autonomous Development endpoints
    print("\n7. Testing Autonomous Development endpoints...")
    try:
        response = client.post("/api/jarvis/development/create_workflow", json={
            "name": "Test Workflow",
            "description": "Test description",
            "repository_path": "c:\\Users\\JUNAID ASAD KHAN\\odysseus-1",
            "project_id": None
        })
        print(f"   POST /api/jarvis/development/create_workflow: {response.status_code}")
        if response.status_code == 503:
            print("   ⚠️  Service unavailable (expected - Jarvis not initialized)")
            results['autonomous_development'] = True
        else:
            print(f"   Response: {response.json()}")
            results['autonomous_development'] = response.status_code == 200
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results['autonomous_development'] = False
    
    # Test 8: Statistics endpoints
    print("\n8. Testing Statistics endpoints...")
    try:
        endpoints = [
            "/api/jarvis/autonomous/statistics",
            "/api/jarvis/coding/statistics",
            "/api/jarvis/improvement/statistics",
            "/api/jarvis/debugging/statistics",
            "/api/jarvis/project/statistics",
            "/api/jarvis/development/statistics"
        ]
        
        all_stats_ok = True
        for endpoint in endpoints:
            response = client.get(endpoint)
            print(f"   GET {endpoint}: {response.status_code}")
            if response.status_code == 503:
                print("   ⚠️  Service unavailable (expected - Jarvis not initialized)")
            elif response.status_code != 200:
                all_stats_ok = False
        
        results['statistics'] = all_stats_ok
    except Exception as e:
        print(f"   ❌ Error: {e}")
        results['statistics'] = False
    
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
        print("\n✅ All Phase 1 API endpoints are registered and accessible")
        print("   (Services return 503 because Jarvis is not initialized in test mode)")
        return True
    else:
        print(f"\n⚠️  {total - passed} test(s) failed")
        return False


if __name__ == "__main__":
    success = test_phase1_endpoints()
    sys.exit(0 if success else 1)
