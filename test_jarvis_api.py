"""
Quick test script for Jarvis OS API endpoints
"""

import requests
import json

BASE_URL = "http://localhost:8000"

def test_jarvis():
    print("=" * 60)
    print("Testing Jarvis OS API")
    print("=" * 60)
    
    # Test 1: Status
    print("\n1. Testing Jarvis Status...")
    try:
        response = requests.get(f"{BASE_URL}/api/jarvis/status")
        print(f"Status Code: {response.status_code}")
        print(f"Response: {json.dumps(response.json(), indent=2)}")
    except Exception as e:
        print(f"Error: {e}")
    
    # Test 2: Metrics
    print("\n2. Testing System Metrics...")
    try:
        response = requests.get(f"{BASE_URL}/api/jarvis/metrics")
        print(f"Status Code: {response.status_code}")
        data = response.json()
        print(f"CPU: {data.get('cpu', {}).get('percent', 'N/A')}%")
        print(f"Memory: {data.get('memory', {}).get('percent', 'N/A')}%")
    except Exception as e:
        print(f"Error: {e}")
    
    # Test 3: Processes
    print("\n3. Testing Process List...")
    try:
        response = requests.get(f"{BASE_URL}/api/jarvis/processes")
        print(f"Status Code: {response.status_code}")
        data = response.json()
        print(f"Total Processes: {len(data.get('processes', []))}")
    except Exception as e:
        print(f"Error: {e}")
    
    # Test 4: Chat
    print("\n4. Testing Chat with Jarvis...")
    try:
        response = requests.post(
            f"{BASE_URL}/api/jarvis/chat",
            json={"command": "Hello Jarvis, introduce yourself"}
        )
        print(f"Status Code: {response.status_code}")
        data = response.json()
        print(f"Jarvis Response: {data.get('response', 'No response')}")
    except Exception as e:
        print(f"Error: {e}")
    
    # Test 5: Patterns
    print("\n5. Testing Learned Patterns...")
    try:
        response = requests.get(f"{BASE_URL}/api/jarvis/patterns")
        print(f"Status Code: {response.status_code}")
        data = response.json()
        print(f"Patterns Found: {len(data.get('patterns', []))}")
    except Exception as e:
        print(f"Error: {e}")
    
    print("\n" + "=" * 60)
    print("Test Complete")
    print("=" * 60)

if __name__ == "__main__":
    test_jarvis()
