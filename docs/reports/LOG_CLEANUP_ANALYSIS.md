# Log File Analysis and Cleanup

## Current Situation

### Problem
- **1,938 log files** consuming **492MB** of disk space
- **1,882 timestamped logs** (`alphacent_YYYYMMDD_HHMMSS.log`)
- New log file created **every time the backend starts**
- Backend appears to restart frequently (multiple times per minute during development)

### Why This Happens

The logging system (`src/core/logging_config.py`) creates a new timestamped log file on every initialization:

```python
main_log_file = log_dir / f"alphacent_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
```

This is by design for production environments where you want to track each application run separately. However, during development with frequent restarts, this creates excessive log files.

## Do We Need Them?

### Keep
- **Recent logs (last 7 days)** - Useful for debugging current issues
- **Component logs** (`api.log`, `strategy.log`, etc.) - These rotate automatically
- **Large logs** - May contain important error traces

### Can Delete
- **Old timestamped logs (>7 days)** - Historical data no longer needed
- **Empty logs** - Failed starts, no useful data
- **Small logs (<1KB)** - Usually just startup messages
- **Archived test/demo logs** - Old development artifacts

## Recommended Actions

### 1. Immediate Cleanup (Safe)
Delete old logs older than 7 days:
```bash
find logs/ -name "alphacent_*.log" -mtime +7 -delete
```

### 2. Aggressive Cleanup (If disk space is critical)
Keep only last 24 hours:
```bash
find logs/ -name "alphacent_*.log" -mtime +1 -delete
```

### 3. Delete Empty/Tiny Logs
```bash
find logs/ -name "*.log" -size 0 -delete
find logs/ -name "*.log" -size -1k -delete
```

### 4. Clean Archived Logs
```bash
rm -rf logs/archived/
rm -rf logs/tests/
```

## Long-term Solutions

### Option 1: Use Single Log File (Development)
Modify `src/core/logging_config.py` to use a single log file during development:

```python
# Instead of timestamped file:
main_log_file = log_dir / "alphacent.log"  # Single file, rotates when full
```

### Option 2: Add Log Rotation Configuration
The system already uses `RotatingFileHandler` with:
- Max size: 10MB per file
- Backup count: 5 files

This should work, but the timestamped filename prevents proper rotation.

### Option 3: Add Automatic Cleanup
Create a cleanup script that runs periodically:

```python
# scripts/utilities/cleanup_old_logs.py
import os
from datetime import datetime, timedelta
from pathlib import Path

def cleanup_old_logs(days=7):
    """Delete log files older than specified days."""
    cutoff = datetime.now() - timedelta(days=days)
    log_dir = Path("logs")
    
    for log_file in log_dir.glob("alphacent_*.log"):
        if datetime.fromtimestamp(log_file.stat().st_mtime) < cutoff:
            log_file.unlink()
            print(f"Deleted: {log_file}")
```

### Option 4: Update .gitignore
Ensure logs aren't committed to git:

```
# Logs
logs/
*.log
```

## Recommendation

For development:
1. **Immediate**: Run cleanup to delete logs older than 7 days
2. **Short-term**: Modify logging config to use single rotating log file
3. **Long-term**: Add automatic cleanup script or cron job

For production:
- Keep timestamped logs for audit trail
- Implement log aggregation/monitoring (e.g., CloudWatch, Datadog)
- Set up automated archival to S3 or similar
