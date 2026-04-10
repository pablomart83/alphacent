# Manual Tests

Manual test scripts that were used during development and debugging.

## Contents

- `test_*.py` - Various test scripts for different components
- `run_task_*.py` - Task-specific test runners

## Note

These are manual test scripts, not part of the automated test suite. They were used for:
- Integration testing
- End-to-end testing
- Feature validation
- Bug reproduction

For automated tests, see the main `tests/` directory in the project root.

## Usage

Run individual test scripts:
```bash
python tests/manual/test_correlation_analysis.py
```

Some tests may require:
- Backend running
- Database populated
- API credentials configured
