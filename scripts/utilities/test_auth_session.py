#!/usr/bin/env python3
"""
Test authentication and session management.

This script helps diagnose authentication issues by:
1. Testing login endpoint
2. Verifying session cookie is set
3. Testing protected endpoints with session
"""

import requests
import sys

# API base URL
BASE_URL = "http://localhost:8000"

def test_login():
    """Test login endpoint and get session cookie."""
    print("=" * 80)
    print("Testing Login Endpoint")
    print("=" * 80)
    
    # Login with default credentials
    login_data = {
        "username": "admin",
        "password": "admin123"
    }
    
    print(f"\n1. Attempting login with username: {login_data['username']}")
    response = requests.post(f"{BASE_URL}/auth/login", json=login_data)
    
    print(f"   Status Code: {response.status_code}")
    print(f"   Response: {response.json()}")
    
    if response.status_code == 200:
        print("   ✓ Login successful!")
        
        # Check for session cookie
        session_id = response.cookies.get("session_id")
        if session_id:
            print(f"   ✓ Session cookie set: {session_id[:16]}...")
            return session_id
        else:
            print("   ✗ No session cookie in response!")
            print(f"   Cookies: {response.cookies}")
            return None
    else:
        print("   ✗ Login failed!")
        return None


def test_session_status(session_id=None):
    """Test session status endpoint."""
    print("\n" + "=" * 80)
    print("Testing Session Status Endpoint")
    print("=" * 80)
    
    cookies = {"session_id": session_id} if session_id else {}
    
    print(f"\n2. Checking session status")
    if session_id:
        print(f"   Using session: {session_id[:16]}...")
    else:
        print("   No session cookie")
    
    response = requests.get(f"{BASE_URL}/auth/status", cookies=cookies)
    
    print(f"   Status Code: {response.status_code}")
    print(f"   Response: {response.json()}")
    
    if response.status_code == 200:
        data = response.json()
        if data.get("authenticated"):
            print(f"   ✓ Authenticated as: {data.get('username')}")
            return True
        else:
            print("   ✗ Not authenticated")
            return False
    else:
        print("   ✗ Request failed!")
        return False


def test_protected_endpoint(session_id):
    """Test a protected endpoint with session."""
    print("\n" + "=" * 80)
    print("Testing Protected Endpoint")
    print("=" * 80)
    
    cookies = {"session_id": session_id}
    
    print(f"\n3. Testing /strategies/autonomous/status endpoint")
    print(f"   Using session: {session_id[:16]}...")
    
    response = requests.get(
        f"{BASE_URL}/strategies/autonomous/status",
        cookies=cookies,
        params={"mode": "DEMO"}
    )
    
    print(f"   Status Code: {response.status_code}")
    
    if response.status_code == 200:
        print("   ✓ Request successful!")
        print(f"   Response: {response.json()}")
        return True
    elif response.status_code == 401:
        print("   ✗ Unauthorized - session invalid!")
        print(f"   Response: {response.json()}")
        return False
    else:
        print(f"   ✗ Request failed with status {response.status_code}")
        print(f"   Response: {response.text}")
        return False


def test_multiple_endpoints(session_id):
    """Test multiple protected endpoints."""
    print("\n" + "=" * 80)
    print("Testing Multiple Protected Endpoints")
    print("=" * 80)
    
    cookies = {"session_id": session_id}
    
    endpoints = [
        "/control/system/status",
        "/strategies?mode=DEMO",
        "/orders?mode=DEMO",
    ]
    
    results = {}
    
    for endpoint in endpoints:
        print(f"\n   Testing: {endpoint}")
        response = requests.get(f"{BASE_URL}{endpoint}", cookies=cookies)
        
        success = response.status_code == 200
        results[endpoint] = success
        
        if success:
            print(f"   ✓ Success (200)")
        else:
            print(f"   ✗ Failed ({response.status_code})")
    
    return results


def main():
    """Run all authentication tests."""
    print("\n" + "=" * 80)
    print("AUTHENTICATION & SESSION TESTING")
    print("=" * 80)
    print("\nThis script tests the authentication flow and session management.")
    print(f"API URL: {BASE_URL}")
    
    try:
        # Test 1: Login
        session_id = test_login()
        
        if not session_id:
            print("\n" + "=" * 80)
            print("FAILED: Could not obtain session cookie")
            print("=" * 80)
            print("\nPossible issues:")
            print("1. Backend server not running")
            print("2. Default user not created")
            print("3. Login endpoint not working")
            sys.exit(1)
        
        # Test 2: Session status
        authenticated = test_session_status(session_id)
        
        if not authenticated:
            print("\n" + "=" * 80)
            print("FAILED: Session not valid")
            print("=" * 80)
            print("\nPossible issues:")
            print("1. Session validation not working")
            print("2. Session expired immediately")
            sys.exit(1)
        
        # Test 3: Protected endpoint
        success = test_protected_endpoint(session_id)
        
        if not success:
            print("\n" + "=" * 80)
            print("FAILED: Protected endpoint rejected valid session")
            print("=" * 80)
            print("\nPossible issues:")
            print("1. Middleware not recognizing session cookie")
            print("2. Session validation failing in middleware")
            sys.exit(1)
        
        # Test 4: Multiple endpoints
        results = test_multiple_endpoints(session_id)
        
        # Summary
        print("\n" + "=" * 80)
        print("TEST SUMMARY")
        print("=" * 80)
        
        all_passed = all(results.values())
        
        print(f"\n✓ Login: SUCCESS")
        print(f"✓ Session Status: SUCCESS")
        print(f"✓ Protected Endpoint: SUCCESS")
        
        for endpoint, success in results.items():
            status = "SUCCESS" if success else "FAILED"
            symbol = "✓" if success else "✗"
            print(f"{symbol} {endpoint}: {status}")
        
        if all_passed:
            print("\n" + "=" * 80)
            print("ALL TESTS PASSED!")
            print("=" * 80)
            print("\nAuthentication is working correctly.")
            print(f"\nYour session ID: {session_id}")
            print("\nTo use this session in your browser:")
            print("1. Open browser DevTools (F12)")
            print("2. Go to Application/Storage > Cookies")
            print(f"3. Add cookie: session_id = {session_id}")
            print("4. Refresh the page")
        else:
            print("\n" + "=" * 80)
            print("SOME TESTS FAILED")
            print("=" * 80)
            sys.exit(1)
    
    except requests.exceptions.ConnectionError:
        print("\n" + "=" * 80)
        print("ERROR: Could not connect to backend server")
        print("=" * 80)
        print(f"\nMake sure the backend is running at {BASE_URL}")
        print("\nTo start the backend:")
        print("  python -m src.api.app")
        sys.exit(1)
    
    except Exception as e:
        print("\n" + "=" * 80)
        print(f"ERROR: {e}")
        print("=" * 80)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
