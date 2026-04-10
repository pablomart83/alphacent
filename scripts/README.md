# Scripts

Utility and diagnostic scripts for the AlphaCent trading platform.

## Structure

- **diagnostics/** - Scripts for checking system state, analyzing issues, debugging
  - `check_*.py` - Check various system components
  - `diagnose_*.py` - Diagnostic tools
  - `analyze_*.py` - Analysis scripts
  - `verify_*.py` - Verification utilities

- **utilities/** - Utility scripts for maintenance and operations
  - `cleanup_*.py` - Cleanup operations
  - `fix_*.py` - Fix scripts
  - `migrate_*.py` - Database migrations
  - `seed_*.py` - Data seeding
  - `demo_*.py` - Demo/example scripts

## Usage

Most scripts can be run directly:
```bash
python scripts/diagnostics/check_orders.py
python scripts/utilities/cleanup_invalid_strategies.py
```

Some scripts may require the backend to be running or specific environment variables to be set.
