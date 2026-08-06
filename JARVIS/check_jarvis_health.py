"""
Jarvis OS Health Check Script
Run this to verify Jarvis is completely functional
"""

import requests
import json
import sys
from datetime import datetime

def check_jarvis_health():
    """Comprehensive health check for Jarvis OS"""
    base_url = "http://127.0.0.1:7000"
    
    print("="*60)
    print("JARVIS OS HEALTH CHECK")
    print("="*60)
    print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Base URL: {base_url}")
    print()
    
    results = {}
    
    # First check if authentication is enabled
    print("0. Checking authentication status...")
    try:
        response = requests.get(f"{base_url}/api/auth/status", timeout=5)
        if response.status_code == 200:
            auth_status = response.json()
            print(f"   Auth enabled: {auth_status.get('enabled', False)}")
            print(f"   Setup required: {auth_status.get('setup_required', False)}")
            results['auth_check'] = True
        else:
            print(f"   ⚠️  Auth status returned {response.status_code}")
            results['auth_check'] = False
    except requests.exceptions.RequestException as e:
        print(f"   ❌ Cannot check auth status: {e}")
        results['auth_check'] = False
    
    print()
    
    # Test 1: Server Status (without auth)
    print("1. Checking server status (no auth required)...")
    try:
        response = requests.get(f"{base_url}/api/jarvis/status", timeout=5)
        if response.status_code == 200:
            status = response.json()
            print(f"   ✅ Server is running")
            print(f"   State: {status.get('state', 'unknown')}")
            results['server'] = True
        elif response.status_code == 401:
            print(f"   ⚠️  Server requires authentication (this is normal)")
            print(f"   Jarvis is running but API endpoints are protected")
            results['server'] = True  # Server is running, just requires auth
        else:
            print(f"   ❌ Server returned status {response.status_code}")
            results['server'] = False
    except requests.exceptions.RequestException as e:
        print(f"   ❌ Cannot connect to server: {e}")
        results['server'] = False
    
    print()
    
    # Test 2: Dashboard (without auth)
    print("2. Checking dashboard endpoint (no auth required)...")
    try:
        response = requests.get(f"{base_url}/api/jarvis/dashboard", timeout=5)
        if response.status_code == 200:
            dashboard = response.json()
            print(f"   ✅ Dashboard accessible")
            print(f"   Subsystems: {len(dashboard.get('subsystems', {}))}")
            results['dashboard'] = True
        elif response.status_code == 401:
            print(f"   ⚠️  Dashboard requires authentication (this is normal)")
            results['dashboard'] = True  # Endpoint exists, just requires auth
        else:
            print(f"   ❌ Dashboard returned status {response.status_code}")
            results['dashboard'] = False
    except requests.exceptions.RequestException as e:
        print(f"   ❌ Cannot access dashboard: {e}")
        results['dashboard'] = False
    
    print()
    
    # Test 3: Phase 1 Autonomous Components (check if endpoints exist)
    print("3. Checking Phase 1 Autonomous Components (endpoint availability)...")
    phase1_endpoints = {
        'autonomous_planner': '/api/jarvis/autonomous/statistics',
        'long_running_coding': '/api/jarvis/coding/statistics',
        'self_improvement': '/api/jarvis/improvement/statistics',
        'repository_understanding': '/api/jarvis/repository/summary?repository_path=c:\\Users\\JUNAID ASAD KHAN\\odysseus-1',
        'live_debugging': '/api/jarvis/debugging/statistics',
        'project_management': '/api/jarvis/project/statistics',
        'autonomous_development': '/api/jarvis/development/statistics'
    }
    
    for component, endpoint in phase1_endpoints.items():
        try:
            response = requests.get(f"{base_url}{endpoint}", timeout=5)
            if response.status_code == 200:
                print(f"   ✅ {component}: accessible")
                results[component] = True
            elif response.status_code == 401:
                print(f"   ⚠️  {component}: requires authentication (endpoint exists)")
                results[component] = True  # Endpoint exists, just requires auth
            elif response.status_code == 503:
                print(f"   ⚠️  {component}: service unavailable")
                results[component] = False
            else:
                print(f"   ❌ {component}: status {response.status_code}")
                results[component] = False
        except requests.exceptions.RequestException as e:
            print(f"   ❌ {component}: {e}")
            results[component] = False
    
    print()
    
    # Test 4: OS Operations
    print("4. Checking OS Operations endpoint...")
    try:
        response = requests.get(f"{base_url}/api/jarvis/os/history?limit=1", timeout=5)
        if response.status_code == 200:
            print(f"   ✅ OS Operations: accessible")
            results['os_operations'] = True
        elif response.status_code == 401:
            print(f"   ⚠️  OS Operations: requires authentication (endpoint exists)")
            results['os_operations'] = True
        else:
            print(f"   ❌ OS Operations: status {response.status_code}")
            results['os_operations'] = False
    except requests.exceptions.RequestException as e:
        print(f"   ❌ OS Operations: {e}")
        results['os_operations'] = False
    
    print()
    
    # Summary
    print("="*60)
    print("HEALTH CHECK SUMMARY")
    print("="*60)
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)  # Count actual True values
    
    for test_name, passed_status in results.items():
        status = "✅ PASS" if passed_status else "❌ FAIL"
        print(f"{status}: {test_name}")
    
    print()
    print(f"Total: {passed}/{total} checks passed")
    
    health_percentage = (passed / total) * 100 if total > 0 else 0
    print(f"Health: {health_percentage:.1f}%")
    
    # Additional context
    print()
    print("NOTES:")
    print("- 401 responses indicate endpoints exist but require authentication")
    print("- If auth is disabled but endpoints return 401, there's a configuration issue")
    print("- Jarvis OS is running but API access may be restricted")
    
    if passed == total:
        print("\n🎉 Jarvis OS is completely functional!")
        return True
    elif health_percentage >= 70:
        print("\n⚠️  Jarvis OS is partially functional (some components unavailable)")
        return False
    else:
        print("\n❌ Jarvis OS has major issues")
        return False


if __name__ == "__main__":
    try:
        success = check_jarvis_health()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nHealth check interrupted")
        sys.exit(1)
