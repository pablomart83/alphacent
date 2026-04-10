# Sector Rotation Strategy Integration

## Overview
The Sector Rotation Strategy is integrated into the autonomous trading system with special handling for its fixed sector ETF symbols.

## Key Differences from Standard Strategies

### 1. Fixed Symbols
Unlike standard strategies that trade individual stocks, the Sector Rotation strategy trades a fixed set of sector ETFs:
- XLE (Energy)
- XLF (Financials)
- XLK (Technology)
- XLU (Utilities)
- XLV (Healthcare)
- XLI (Industrials)
- XLP (Consumer Staples)
- XLY (Consumer Discretionary)

### 2. Template Configuration
The Sector Rotation template in `src/strategy/strategy_templates.py` includes:
```python
metadata={
    "fixed_symbols": ["XLE", "XLF", "XLK", "XLU", "XLV", "XLI", "XLP", "XLY"],
    "requires_macro_data": True,
    "strategy_category": "alpha_edge",
    "uses_sector_etfs": True
}
```

### 3. Strategy Proposer Integration
The `generate_strategies_from_templates` method in `src/strategy/strategy_proposer.py` checks for `fixed_symbols` in template metadata:
```python
if template.metadata and 'fixed_symbols' in template.metadata:
    strategy_symbol = template.metadata['fixed_symbols']
else:
    strategy_symbol = [assigned_symbol]
```

### 4. Signal Generation
The strategy uses the standard signal generation pipeline but:
- Trades all 8 sector ETFs simultaneously
- Rebalances monthly based on regime changes
- Uses momentum scoring to select top 3 sectors

### 5. Fundamental Filtering
Sector ETFs are NOT subject to fundamental filtering (EPS, revenue growth, etc.) since:
- ETFs don't have individual company fundamentals
- Sector selection is based on macro regime and momentum

## Implementation Files

### Core Strategy
- `src/strategy/sector_rotation.py` - Main strategy implementation
- `tests/test_sector_rotation.py` - Comprehensive test suite

### Integration Points
- `src/strategy/strategy_templates.py` - Template definition
- `src/strategy/strategy_proposer.py` - Symbol assignment logic
- `src/strategy/strategy_engine.py` - Signal generation (no changes needed)

## Usage

### Manual Strategy Creation
```python
from src.strategy.sector_rotation import SectorRotationStrategy

config = {
    'alpha_edge': {
        'sector_rotation': {
            'enabled': True,
            'max_positions': 3,
            'rebalance_frequency_days': 30,
            'sectors': ['XLE', 'XLF', 'XLK', 'XLU', 'XLV', 'XLI', 'XLP', 'XLY']
        }
    }
}

strategy = SectorRotationStrategy(config, market_analyzer, market_data_manager)
recommendations = strategy.get_recommended_sectors()
```

### Autonomous Strategy Proposal
The strategy will be automatically proposed by the StrategyProposer when:
- Market regime matches (works in all regimes)
- Template-based generation is enabled
- The Sector Rotation template is selected

## Configuration

Add to `config/autonomous_trading.yaml`:
```yaml
alpha_edge:
  sector_rotation:
    enabled: true
    max_positions: 3
    rebalance_frequency_days: 30
    sectors:
      - XLE  # Energy
      - XLF  # Financials
      - XLK  # Technology
      - XLU  # Utilities
      - XLV  # Healthcare
      - XLI  # Industrials
      - XLP  # Consumer Staples
      - XLY  # Consumer Discretionary
```

## Testing
Run the test suite:
```bash
source venv/bin/activate
python -m pytest tests/test_sector_rotation.py -v
```

All 24 tests pass successfully.

## Future Enhancements
1. Add sector correlation analysis to avoid over-concentration
2. Implement dynamic position sizing based on sector volatility
3. Add sector-specific stop losses based on historical drawdowns
4. Integrate with portfolio rebalancing system
