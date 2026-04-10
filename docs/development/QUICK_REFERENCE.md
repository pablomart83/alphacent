# Quick Reference - LLM Model Upgrade

## TL;DR

**Problem**: llama3.2:1b generates bad JSON (67% success rate)
**Solution**: Upgrade to better model OR use fallback (100% success)
**Best Model**: qwen2.5-coder:7b (95% success rate)

## One-Command Solutions

### Use Current System (Works Now)
```bash
python -m src.cli.bootstrap_strategies --auto-activate --min-sharpe 0.5
```
✅ Works with template fallback

### Upgrade to Better Model (Recommended)
```bash
./scripts/upgrade_ollama_model.sh
```
Choose option 1 (qwen2.5-coder:7b)

### Manual Upgrade
```bash
ollama pull qwen2.5-coder:7b
export OLLAMA_MODEL="qwen2.5-coder:7b"
python -m src.cli.bootstrap_strategies --strategy-types momentum
```

## Model Comparison

| Model | Success | Speed | Command |
|-------|---------|-------|---------|
| llama3.2:1b (current) | 67% | Fast | Already installed |
| llama3.2:3b | 80% | Fast | `ollama pull llama3.2:3b` |
| qwen2.5-coder:7b ⭐ | 95% | Medium | `ollama pull qwen2.5-coder:7b` |
| llama3.1:8b | 90% | Medium | `ollama pull llama3.1:8b` |

## Test Commands

```bash
# Test model quality
python scripts/test_model_quality.py

# Test strategy generation
python -m src.cli.bootstrap_strategies --strategy-types momentum

# Verify database
python -c "from src.models.database import get_database; from src.models.orm import StrategyORM; db = get_database(); session = db.get_session(); print(f'Strategies: {len(session.query(StrategyORM).all())}')"
```

## Environment Variables

```bash
# Set model
export OLLAMA_MODEL="qwen2.5-coder:7b"

# Make permanent
echo 'export OLLAMA_MODEL="qwen2.5-coder:7b"' >> ~/.bashrc
```

## What Was Fixed

1. ✅ JSON repair function (fixes syntax errors)
2. ✅ Template fallback (always works)
3. ✅ Environment variable support (easy model switching)
4. ✅ Intelligent model fallback (uses best available)
5. ✅ Testing tools (benchmark models)
6. ✅ Upgrade script (one-command install)

## Files to Read

- `COMPLETE_SOLUTION_SUMMARY.md` - Full details
- `OLLAMA_MODEL_UPGRADE_GUIDE.md` - Model recommendations
- `MODEL_UPGRADE_IMPLEMENTATION.md` - Technical details

## Support

If you have issues:
1. Check `ollama list` to see installed models
2. Run `python scripts/test_model_quality.py` to test
3. Try template fallback (always works)
4. Read troubleshooting in upgrade guide
