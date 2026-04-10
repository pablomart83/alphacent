# Authentication Session Fix

## Issue

The frontend is receiving 401 Unauthorized errors when trying to access protected API endpoints:

```
2026-02-21 19:38:13 - src.api.middleware - WARNING - Invalid session for /strategies/autonomous/status
INFO:     127.0.0.1:59334 - "GET /strategies/autonomous/status HTTP/1.1" 401 Unauthorized
```

## Root Cause

The frontend is trying to access protected endpoints without a valid session cookie. The authentication system is working correctly (verified by test script), but the browser doesn't have a session cookie set.

## Solution

The user needs to log in through the frontend login page. Here's how:

### Option 1: Use the Frontend Login Page

1. Navigate to the login page in your browser (usually at `http://localhost:3000/login` or similar)
2. Enter the default credentials:
   - **Username**: `admin`
   - **Password**: `admin123`
3. Click "Login"
4. The session cookie will be set automatically
5. You'll be redirected to the dashboard

### Option 2: Manually Set Session Cookie (For Testing)

If you need to quickly test without going through the login flow:

1. Run the test script to get a valid session:
   ```bash
   python scripts/utilities/test_auth_session.py
   ```

2. Copy the session ID from the output (e.g., `c8oHvPsp4rTnT-iEsUOVg_iI2m9N9nMasduyWPg1zrM`)

3. Open browser DevTools (F12)

4. Go to Application/Storage > Cookies

5. Add a new cookie:
   - **Name**: `session_id`
   - **Value**: (paste the session ID from step 2)
   - **Domain**: `localhost`
   - **Path**: `/`
   - **HttpOnly**: unchecked
   - **Secure**: unchecked

6. Refresh the page

### Option 3: Use curl to Login and Get Session

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}' \
  -c cookies.txt

# The session cookie is now saved in cookies.txt
# Use it for subsequent requests:
curl http://localhost:8000/strategies/autonomous/status \
  -b cookies.txt
```

## Verification

After logging in, verify the session is working:

1. Check browser DevTools > Application > Cookies
2. You should see a `session_id` cookie
3. The frontend should now load data without 401 errors
4. Check the browser console - no more authentication errors

## Default Credentials

The system creates a default user on first startup:

- **Username**: `admin`
- **Password**: `admin123`

**⚠️ IMPORTANT**: Change this password in production!

## Session Details

- **Session Timeout**: 30 minutes of inactivity
- **Session Extension**: Each request extends the session by 30 minutes
- **Automatic Cleanup**: Expired sessions are cleaned up every 5 minutes

## Testing Authentication

Run the authentication test script to verify the system is working:

```bash
python scripts/utilities/test_auth_session.py
```

This script tests:
- Login endpoint
- Session cookie creation
- Session validation
- Protected endpoint access

## Troubleshooting

### Issue: Login page not loading

**Solution**: Make sure the frontend is running:
```bash
cd frontend
npm start
```

### Issue: "Invalid username or password"

**Solution**: Use the default credentials:
- Username: `admin`
- Password: `admin123`

### Issue: Session expires immediately

**Solution**: Check the backend logs for errors. The session manager should be initialized correctly.

### Issue: CORS errors

**Solution**: Make sure the backend CORS settings allow the frontend origin. Check `src/api/app.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],  # Frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## Implementation Details

### Authentication Flow

1. User submits credentials to `/auth/login`
2. Backend validates credentials using bcrypt
3. Backend creates session with unique ID
4. Backend sets `session_id` cookie in response
5. Frontend stores cookie automatically
6. Frontend includes cookie in all subsequent requests
7. Middleware validates session on each request
8. Session is extended on each valid request

### Session Cookie Settings

```python
response.set_cookie(
    key="session_id",
    value=session_id,
    httponly=False,  # Allow JavaScript to read for WebSocket
    secure=False,    # Set to True in production with HTTPS
    samesite="lax",
    max_age=30 * 60  # 30 minutes
)
```

### Protected Endpoints

All endpoints except these require authentication:
- `/` (root)
- `/health`
- `/docs`
- `/openapi.json`
- `/auth/login`
- `/auth/status`
- `/config`

## Next Steps

1. **Log in through the frontend** - This is the recommended approach
2. **Verify session is working** - Check browser cookies and console
3. **Continue using the application** - All API calls should now work

## Related Files

- `src/api/middleware.py` - Authentication middleware
- `src/core/auth.py` - Authentication manager
- `src/api/routers/auth.py` - Login/logout endpoints
- `scripts/utilities/test_auth_session.py` - Authentication test script
