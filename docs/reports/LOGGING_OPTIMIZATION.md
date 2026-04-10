# Logging System Optimization

## Date
February 20, 2026

## Problem
- 1,885 timestamped log files created in 7 days
- 177 log files created in a single day
- Each backend restart created a new log file
- Total size: 260MB+ of mostly redundant logs

## Root Cause
The logging system created a new timestamped file on every initialization:
```python
# OLD (problematic)
main_log_file = log_dir / f"alphacent_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
```

This is fine for production deployments but excessive for development with frequent restarts.

## Solution Implemented

### Changed to Single Rotating Log File
Modified `src/core/logging_config.py` to use a single log file that rotates based on size:

```python
# NEW (sustainable)
main_log_file = log_dir / "alphacent.log"
```

### How It Works Now

**Single Main Log:**
- `logs/alphacent.log` - Main application log
- Rotates when it reaches 10MB
- Keeps 5 backup files: `alphacent.log.1`, `alphacent.log.2`, etc.
- Maximum total size: ~50MB (10MB × 5 backups)

**Component-Specific Logs:**
- `logs/api.log` - API requests and responses
- `logs/strategy.log` - Strategy execution
- `logs/risk.log` - Risk management
- `logs/execution.log` - Trade execution
- `logs/data.log` - Market data fetching
- `logs/llm.log` - LLM service calls
- `logs/security.log` - Authentication and security events
- `logs/database.log` - Database operations
- `logs/system.log` - System-level events
- `logs/validation.log` - Validation errors

Each component log also rotates at 10MB with 5 backups.

## Benefits

✅ **Sustainable:** Maximum ~550MB total (11 logs × 10MB × 5 backups)
✅ **No Clutter:** No more thousands of timestamped files
✅ **Automatic Cleanup:** Old logs automatically deleted when rotated
✅ **Still Debuggable:** Recent logs always available
✅ **Component Separation:** Easy to find specific issues

## Cleanup Performed

- Deleted 1,885 old timestamped log files
- Freed 260MB+ of disk space
- Kept component log structure intact

## Current State

```
logs/
├── alphacent.log          # Main log (rotates at 10MB)
├── api.log               # API component
├── strategy.log          # Strategy component
├── risk.log              # Risk component
├── execution.log         # Execution component
├── data.log              # Data component
├── llm.log               # LLM component
├── security.log          # Security component
├── database.log          # Database component
├── system.log            # System component
└── validation.log        # Validation component
```

When logs rotate, you'll see:
```
logs/
├── alphacent.log         # Current
├── alphacent.log.1       # Previous
├── alphacent.log.2       # Older
├── alphacent.log.3       # Even older
├── alphacent.log.4       # Oldest
└── alphacent.log.5       # About to be deleted
```

## Configuration

Current settings (in `src/core/logging_config.py`):
- **Max file size:** 10MB per log file
- **Backup count:** 5 files
- **Total max size:** ~550MB (11 logs × 10MB × 5 backups)
- **Console output:** Enabled (logs also print to terminal)

To adjust:
```python
LoggingConfig.initialize(
    log_dir=Path("logs"),
    log_level=LogSeverity.INFO,
    max_bytes=10 * 1024 * 1024,  # Change this for different max size
    backup_count=5,               # Change this for more/fewer backups
    console_output=True
)
```

## Monitoring

Check log sizes:
```bash
du -sh logs/
ls -lh logs/
```

View current logs:
```bash
tail -f logs/alphacent.log          # Main log
tail -f logs/api.log                # API requests
tail -f logs/strategy.log           # Strategy execution
```

## Production Considerations

For production deployment, consider:
1. **Log aggregation:** Send logs to CloudWatch, Datadog, or similar
2. **Longer retention:** Increase backup_count for longer history
3. **Separate error logs:** Add dedicated error log file
4. **Log shipping:** Archive old logs to S3 or similar storage
5. **Monitoring alerts:** Set up alerts for ERROR/CRITICAL logs

## Summary

The logging system is now sustainable and won't create thousands of files. It will automatically manage disk space while keeping recent logs available for debugging.
