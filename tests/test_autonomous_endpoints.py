"""
Manual test script for autonomous control endpoints.

This script tests the three new autonomous control endpoints:
1. POST /api/strategies/autonomous/trigger
2. GET /api/strategies/autonomous/config
3. PUT /api/strategies/autonomous/config

Run this after starting the backend server.
"""

import requests
import json
from typing import Dict, Any


BASE_URL = "http://localhost:8000"
API_BASE = f"{BASE_URL}/api/strategies"


def test_get_config():
    """Test GET /api/strategies/autonomous/config endpoint."""
    print("\n=== Testing GET /api/strategies/autonomous/config ===")
    
    try:
        response = requests.get(f"{API_BASE}/autonomous/config")
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✓ Successfully retrieved configuration")
            print(f"Config keys: {list(data.get('config', {}).keys())}")
            print(f"Last updated: {data.get('last_updated')}")
            return data.get('config', {})
        else:
            print(f"✗ Failed: {response.text}")
            return None
    except Exception as e:
        print(f"✗ Error: {e}")
        return None


def test_update_config(updates: Dict[str, Any]):
    """Test PUT /api/strategies/autonomous/config endpoint."""
    print("\n=== Testing PUT /api/strategies/autonomous/config ===")
    
    try:
        payload = {"config": updates}
        response = requests.put(
            f"{API_BASE}/autonomous/config",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✓ Successfully updated configuration")
            print(f"Success: {data.get('success')}")
            print(f"Message: {data.get('message')}")
            return True
        else:
            print(f"✗ Failed: {response.text}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_trigger_cycle(force: bool = False):
    """Test POST /api/strategies/autonomous/trigger endpoint."""
    print("\n=== Testing POST /api/strategies/autonomous/trigger ===")
    
    try:
        payload = {"force": force}
        response = requests.post(
            f"{API_BASE}/autonomous/trigger",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✓ Successfully triggered cycle")
            print(f"Success: {data.get('success')}")
            print(f"Message: {data.get('message')}")
            print(f"Cycle ID: {data.get('cycle_id')}")
            print(f"Estimated Duration: {data.get('estimated_duration')}s")
            return True
        else:
            print(f"✗ Failed: {response.text}")
            return False
    except Exception as e:
        print(f"✗ Error: {e}")
        return False


def test_validation_errors():
    """Test configuration validation."""
    print("\n=== Testing Configuration Validation ===")
    
    # Test invalid Sharpe ratio
    print("\n1. Testing invalid Sharpe ratio (negative):")
    test_update_config({
        "activation_thresholds": {
            "min_sharpe": -1.0
        }
    })
    
    # Test invalid drawdown
    print("\n2. Testing invalid drawdown (> 1):")
    test_update_config({
        "activation_thresholds": {
            "max_drawdown": 1.5
        }
    })
    
    # Test invalid frequency
    print("\n3. Testing invalid frequency:")
    test_update_config({
        "autonomous": {
            "proposal_frequency": "hourly"
        }
    })
    
    # Test min > max strategies
    print("\n4. Testing min > max strategies:")
    test_update_config({
        "autonomous": {
            "min_active_strategies": 15,
            "max_active_strategies": 10
        }
    })


def run_all_tests():
    """Run all endpoint tests."""
    print("=" * 60)
    print("AUTONOMOUS CONTROL ENDPOINTS TEST SUITE")
    print("=" * 60)
    
    # Test 1: Get current configuration
    current_config = test_get_config()
    
    if current_config:
        # Test 2: Update configuration (valid update)
        print("\n=== Testing Valid Configuration Update ===")
        test_update_config({
            "autonomous": {
                "enabled": True,
                "max_active_strategies": 12
            },
            "activation_thresholds": {
                "min_sharpe": 1.8
            }
        })
        
        # Test 3: Verify update
        updated_config = test_get_config()
        if updated_config:
            print(f"\nVerification:")
            print(f"  max_active_strategies: {updated_config.get('autonomous', {}).get('max_active_strategies')}")
            print(f"  min_sharpe: {updated_config.get('activation_thresholds', {}).get('min_sharpe')}")
    
    # Test 4: Validation errors
    test_validation_errors()
    
    # Test 5: Trigger cycle (without force - may fail if not scheduled)
    print("\n=== Testing Cycle Trigger (without force) ===")
    test_trigger_cycle(force=False)
    
    # Test 6: Trigger cycle (with force)
    print("\n=== Testing Cycle Trigger (with force) ===")
    test_trigger_cycle(force=True)
    
    print("\n" + "=" * 60)
    print("TEST SUITE COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    print("\nNOTE: This test requires the backend server to be running.")
    print("Start the server with: python -m uvicorn src.api.main:app --reload")
    print("\nPress Enter to continue or Ctrl+C to cancel...")
    input()
    
    run_all_tests()
