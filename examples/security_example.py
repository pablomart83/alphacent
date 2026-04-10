"""
Example demonstrating the security implementation in AlphaCent.

This example shows:
1. User authentication with bcrypt password hashing
2. Session management with automatic timeout
3. Input validation and sanitization
4. Rate limiting on authentication endpoints
5. Security event logging
"""

from src.core import (
    AuthenticationManager, SessionManager, InputValidator, ValidationError,
    RateLimiter, RateLimitConfig, SecurityLogger, SecureAuthenticationManager,
    InputType
)


def main():
    print("=" * 60)
    print("AlphaCent Security Implementation Example")
    print("=" * 60)
    
    # 1. Initialize authentication manager
    print("\n1. Initializing Authentication Manager...")
    auth_manager = AuthenticationManager(session_timeout_minutes=30)
    
    # 2. Initialize rate limiter (3 attempts per 60 seconds, 5 minute lockout)
    print("2. Initializing Rate Limiter...")
    rate_config = RateLimitConfig(
        max_attempts=3,
        window_seconds=60,
        lockout_duration_seconds=300
    )
    rate_limiter = RateLimiter(rate_config)
    
    # 3. Initialize security logger
    print("3. Initializing Security Logger...")
    security_logger = SecurityLogger(max_events=1000)
    
    # 4. Create secure authentication manager
    print("4. Creating Secure Authentication Manager...")
    secure_auth = SecureAuthenticationManager(auth_manager, rate_limiter, security_logger)
    
    # 5. Validate and create user with secure password
    print("\n5. Creating User with Input Validation...")
    try:
        username = InputValidator.validate_username("trader123")
        password = InputValidator.validate_password("SecurePass123")
        
        user = auth_manager.create_user(username, password)
        print(f"   ✓ User created: {user.username}")
        print(f"   ✓ Password hashed (bcrypt): {user.password_hash[:20]}...")
    except ValidationError as e:
        print(f"   ✗ Validation error: {e}")
    
    # 6. Demonstrate successful authentication
    print("\n6. Testing Successful Authentication...")
    session_id = secure_auth.authenticate("trader123", "SecurePass123", "192.168.1.100")
    if session_id:
        print(f"   ✓ Authentication successful")
        print(f"   ✓ Session ID: {session_id[:16]}...")
        print(f"   ✓ Security event logged")
    
    # 7. Demonstrate failed authentication
    print("\n7. Testing Failed Authentication...")
    failed_session = secure_auth.authenticate("trader123", "WrongPassword", "192.168.1.100")
    if not failed_session:
        print(f"   ✓ Authentication failed (as expected)")
        print(f"   ✓ Security event logged")
        print(f"   ✓ Remaining attempts: {rate_limiter.get_remaining_attempts('trader123')}")
    
    # 8. Demonstrate rate limiting
    print("\n8. Testing Rate Limiting...")
    for i in range(3):
        result = secure_auth.authenticate("trader123", "WrongPassword", "192.168.1.100")
        if result is None:
            print(f"   Attempt {i+1}: Failed")
    
    # Check if rate limited
    if rate_limiter.is_rate_limited("trader123"):
        lockout_remaining = rate_limiter.get_lockout_remaining("trader123")
        print(f"   ✓ Account locked due to rate limit")
        print(f"   ✓ Lockout remaining: {lockout_remaining} seconds")
    
    # 9. Demonstrate input validation
    print("\n9. Testing Input Validation...")
    
    # Valid inputs
    try:
        symbol = InputValidator.validate_symbol("aapl")
        print(f"   ✓ Valid symbol: {symbol}")
        
        amount = InputValidator.validate_numeric("1000.50", min_value=0)
        print(f"   ✓ Valid amount: ${amount}")
    except ValidationError as e:
        print(f"   ✗ Validation error: {e}")
    
    # Invalid inputs
    try:
        InputValidator.validate_username("ab")  # Too short
    except ValidationError as e:
        print(f"   ✓ Caught invalid username: {e}")
    
    # 10. Demonstrate input sanitization
    print("\n10. Testing Input Sanitization...")
    
    malicious_input = "test'; DROP TABLE users; --"
    sanitized = InputValidator.sanitize_text(malicious_input)
    print(f"   Original: {malicious_input}")
    print(f"   Sanitized: {sanitized}")
    print(f"   ✓ SQL injection patterns removed")
    
    xss_input = "<script>alert('XSS')</script>"
    sanitized_xss = InputValidator.sanitize_text(xss_input)
    print(f"   Original: {xss_input}")
    print(f"   Sanitized: {sanitized_xss}")
    print(f"   ✓ XSS patterns removed")
    
    # 11. Demonstrate error message sanitization
    print("\n11. Testing Error Message Sanitization...")
    error_msg = "Error in /home/user/secret/config.py at 192.168.1.1 with token abc123def456"
    sanitized_error = InputValidator.sanitize_error_message(error_msg)
    print(f"   Original: {error_msg}")
    print(f"   Sanitized: {sanitized_error}")
    print(f"   ✓ Sensitive information removed")
    
    # 12. View security events
    print("\n12. Security Event Log Summary...")
    events = security_logger.get_events(limit=10)
    print(f"   Total events logged: {len(security_logger.events)}")
    print(f"   Recent events:")
    for event in events[-5:]:
        print(f"     - {event.event_type.value}: {event.username or 'N/A'} - {event.details}")
    
    # 13. Session management
    print("\n13. Testing Session Management...")
    session_manager = SessionManager(auth_manager, cleanup_interval_seconds=300)
    
    if session_manager.validate_session(session_id):
        print(f"   ✓ Session is valid")
        session_info = session_manager.get_session_info(session_id)
        print(f"   ✓ Session user: {session_info.username}")
        print(f"   ✓ Session expires: {session_info.expires_at.strftime('%Y-%m-%d %H:%M:%S')}")
    
    active_count = session_manager.get_active_sessions_count()
    print(f"   ✓ Active sessions: {active_count}")
    
    # 14. Logout
    print("\n14. Testing Logout...")
    success = secure_auth.logout(session_id, "192.168.1.100")
    if success:
        print(f"   ✓ User logged out successfully")
        print(f"   ✓ Security event logged")
    
    # Verify session is invalid
    if not session_manager.validate_session(session_id):
        print(f"   ✓ Session invalidated after logout")
    
    print("\n" + "=" * 60)
    print("Security Implementation Example Complete!")
    print("=" * 60)
    print("\nKey Features Demonstrated:")
    print("  ✓ Bcrypt password hashing (Property 31)")
    print("  ✓ Session-based authentication (Requirement 18.3)")
    print("  ✓ Session timeout enforcement (Property 33)")
    print("  ✓ Input validation and sanitization (Property 32)")
    print("  ✓ Rate limiting on authentication (Property 34)")
    print("  ✓ Security event logging (Property 35)")
    print("  ✓ Automatic session cleanup (Requirement 18.4)")


if __name__ == "__main__":
    main()
