# AlphaCent Security Implementation

## Overview

This document describes the security implementation for the AlphaCent Trading Platform, covering user authentication, session management, input validation, rate limiting, and security logging.

## Components

### 1. Authentication Manager (`src/core/auth.py`)

**Purpose**: Manages user authentication with bcrypt password hashing and session-based authentication.

**Key Features**:
- Bcrypt password hashing (Property 31)
- Session creation and management
- Session validation with automatic timeout
- User creation and authentication
- Session expiration handling

**Usage**:
```python
from src.core import AuthenticationManager

auth = AuthenticationManager(session_timeout_minutes=30)

# Create user
user = auth.create_user("username", "SecurePass123")

# Authenticate
session_id = auth.authenticate("username", "SecurePass123")

# Validate session
is_valid = auth.validate_session(session_id)

# Logout
auth.logout(session_id)
```

**Validates**:
- Requirement 18.1: User authentication with username/password
- Requirement 18.2: Password hashing using bcrypt
- Requirement 18.3: Session-based authentication with secure cookies
- Property 31: Password hashing

### 2. Session Manager (`src/core/auth.py`)

**Purpose**: Manages user sessions with automatic cleanup of expired sessions.

**Key Features**:
- Automatic session cleanup (background thread)
- Session validation on each request
- Session timeout enforcement
- Multi-session management per user

**Usage**:
```python
from src.core import SessionManager, AuthenticationManager

auth = AuthenticationManager()
session_mgr = SessionManager(auth, cleanup_interval_seconds=300)

# Start automatic cleanup
session_mgr.start_automatic_cleanup()

# Validate session
is_valid = session_mgr.validate_session(session_id)

# Get session info
session_info = session_mgr.get_session_info(session_id)

# Stop cleanup
session_mgr.stop_automatic_cleanup()
```

**Validates**:
- Requirement 18.4: Session timeout after inactivity
- Requirement 18.4: Clear expired sessions automatically
- Property 33: Session timeout enforcement

### 3. Input Validator (`src/core/validation.py`)

**Purpose**: Validates and sanitizes all user inputs to prevent injection attacks.

**Key Features**:
- Username, password, email, symbol validation
- Numeric and alphanumeric validation
- SQL injection prevention
- XSS attack prevention
- Command injection prevention
- Error message sanitization

**Usage**:
```python
from src.core import InputValidator, ValidationError, InputType

# Validate username
try:
    username = InputValidator.validate_username("trader123")
except ValidationError as e:
    print(f"Invalid: {e}")

# Validate password
password = InputValidator.validate_password("SecurePass123")

# Validate symbol
symbol = InputValidator.validate_symbol("aapl")  # Returns "AAPL"

# Sanitize text
sanitized = InputValidator.sanitize_text("test'; DROP TABLE users;")

# Sanitize error messages
safe_error = InputValidator.sanitize_error_message(error_msg)

# Generic validation
value = InputValidator.validate_input("123.45", InputType.NUMERIC)
```

**Validates**:
- Requirement 18.6: Input validation and sanitization
- Property 32: Input validation and sanitization

### 4. Rate Limiter (`src/core/security.py`)

**Purpose**: Enforces rate limits on authentication endpoints to prevent brute force attacks.

**Key Features**:
- Configurable max attempts and time window
- Automatic lockout after exceeding limit
- Lockout duration tracking
- Attempt window expiration
- Per-identifier rate limiting

**Usage**:
```python
from src.core import RateLimiter, RateLimitConfig

config = RateLimitConfig(
    max_attempts=3,
    window_seconds=60,
    lockout_duration_seconds=300
)
limiter = RateLimiter(config)

# Check if rate limited
if limiter.is_rate_limited("username"):
    remaining = limiter.get_lockout_remaining("username")
    print(f"Locked for {remaining} seconds")

# Record attempt
limiter.record_attempt("username")

# Get remaining attempts
remaining = limiter.get_remaining_attempts("username")

# Reset rate limit
limiter.reset("username")
```

**Validates**:
- Requirement 18.7: Rate limiting on authentication endpoints
- Property 34: Authentication rate limiting

### 5. Security Logger (`src/core/security.py`)

**Purpose**: Logs all security events for audit and monitoring.

**Key Features**:
- Comprehensive security event logging
- Event filtering by username, type, and time
- Failed login tracking
- Suspicious activity detection
- Event retention management

**Usage**:
```python
from src.core import SecurityLogger, SecurityEventType

logger = SecurityLogger(max_events=10000)

# Log events
logger.log_login_success("username", "192.168.1.1")
logger.log_login_failure("username", "Invalid password", "192.168.1.1")
logger.log_rate_limit_exceeded("username", "192.168.1.1")
logger.log_suspicious_activity("username", "Multiple failed logins", "192.168.1.1")

# Get events
events = logger.get_events(username="username", limit=100)
events = logger.get_events(event_type=SecurityEventType.LOGIN_FAILURE)
events = logger.get_events(since=datetime.now() - timedelta(hours=24))

# Get failed login count
count = logger.get_failed_login_count("username")
```

**Validates**:
- Requirement 18.8: Log all authentication attempts with outcome
- Requirement 18.8: Log security events
- Property 35: Security event logging

### 6. Secure Authentication Manager (`src/core/security.py`)

**Purpose**: Combines authentication, rate limiting, and security logging into a single interface.

**Key Features**:
- Integrated authentication with rate limiting
- Automatic security event logging
- Rate limit reset on successful authentication
- Comprehensive security monitoring

**Usage**:
```python
from src.core import (
    AuthenticationManager, RateLimiter, RateLimitConfig,
    SecurityLogger, SecureAuthenticationManager
)

auth = AuthenticationManager()
config = RateLimitConfig(max_attempts=3, window_seconds=60)
limiter = RateLimiter(config)
sec_logger = SecurityLogger()

secure_auth = SecureAuthenticationManager(auth, limiter, sec_logger)

# Authenticate with rate limiting and logging
session_id = secure_auth.authenticate("username", "password", "192.168.1.1")

# Logout with logging
secure_auth.logout(session_id, "192.168.1.1")
```

**Validates**:
- Requirements 18.1, 18.7, 18.8
- Properties 31, 32, 33, 34, 35

## Security Properties Validated

The implementation validates the following correctness properties from the design document:

- **Property 31**: Password hashing - All passwords are hashed using bcrypt before storage
- **Property 32**: Input validation and sanitization - All user inputs are validated and sanitized
- **Property 33**: Session timeout enforcement - Sessions automatically expire after inactivity
- **Property 34**: Authentication rate limiting - Rate limits prevent brute force attacks
- **Property 35**: Security event logging - All security events are logged with details

## Testing

Comprehensive unit tests are provided in:
- `tests/test_auth.py` - 23 tests for authentication and session management
- `tests/test_validation.py` - 23 tests for input validation and sanitization
- `tests/test_security.py` - 27 tests for rate limiting and security logging

Total: 73 tests, all passing

Run tests:
```bash
python -m pytest tests/test_auth.py tests/test_validation.py tests/test_security.py -v
```

## Example

See `examples/security_example.py` for a complete demonstration of all security features.

Run example:
```bash
python examples/security_example.py
```

## Integration with Backend API

The security components are designed to integrate with the FastAPI backend:

```python
from fastapi import FastAPI, Depends, HTTPException, Cookie
from src.core import SecureAuthenticationManager, InputValidator

app = FastAPI()

# Initialize security components
secure_auth = SecureAuthenticationManager(auth, limiter, sec_logger)

@app.post("/auth/login")
async def login(username: str, password: str, request: Request):
    # Validate inputs
    try:
        username = InputValidator.validate_username(username)
        password = InputValidator.validate_password(password)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Authenticate with rate limiting
    ip_address = request.client.host
    session_id = secure_auth.authenticate(username, password, ip_address)
    
    if not session_id:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    
    # Set secure cookie
    response = JSONResponse({"status": "success"})
    response.set_cookie(
        key="session_id",
        value=session_id,
        httponly=True,
        secure=True,
        samesite="strict"
    )
    return response

@app.get("/protected")
async def protected_route(session_id: str = Cookie(None)):
    if not session_mgr.validate_session(session_id):
        raise HTTPException(status_code=401, detail="Invalid session")
    
    username = auth.get_session_user(session_id)
    return {"message": f"Hello {username}"}
```

## Security Best Practices

1. **Password Requirements**:
   - Minimum 8 characters
   - At least one uppercase letter
   - At least one lowercase letter
   - At least one digit

2. **Session Management**:
   - Default timeout: 30 minutes
   - Automatic cleanup every 5 minutes
   - Session validation on each request

3. **Rate Limiting**:
   - Default: 3 attempts per 60 seconds
   - Lockout duration: 5 minutes
   - Reset on successful authentication

4. **Input Validation**:
   - All user inputs validated before processing
   - SQL injection patterns removed
   - XSS patterns removed
   - Command injection characters removed

5. **Security Logging**:
   - All authentication attempts logged
   - Failed logins tracked
   - Suspicious activity flagged
   - Events retained for audit

## Future Enhancements

Potential improvements for future versions:

1. **Multi-factor Authentication (MFA)**: Add TOTP or SMS-based 2FA
2. **Password Reset**: Implement secure password reset flow
3. **Account Lockout**: Permanent lockout after repeated violations
4. **IP Whitelisting**: Restrict access to specific IP ranges
5. **Session Persistence**: Store sessions in database for multi-instance support
6. **Audit Trail**: Enhanced audit logging with detailed activity tracking
7. **CAPTCHA**: Add CAPTCHA after failed login attempts
8. **Biometric Auth**: Support for fingerprint/face recognition
