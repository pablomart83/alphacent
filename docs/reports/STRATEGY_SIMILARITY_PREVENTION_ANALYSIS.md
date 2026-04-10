# Strategy Similarity Prevention - Direct Feedback & Fixes

## Executive Summary

Your current system has **good exact duplicate prevention** but **no similarity detection**. Here's what you need to add to prevent similar strategies and correlated symbol trades.

---

## Current State Analysis

### ✅ What Works Well

1. **Exact Duplicate Signal Prevention** (`_coordinate_signals` in `trading_scheduler.py`)
   - Filters signals for same symbol + same direction
   - Checks existing positions before allowing new signals
   - Checks pending orders before allowing new signals
   - Keeps highest confidence signal when multiple strategies target same symbol/direction
   - Symbol concentration limit: max 3 strategies per symbol

2. **Symbol Normalization** (`symbol_normalizer.py`)
   - Handles GE vs ID_1017 vs 1017 correctly
   - Prevents duplicate positions due to symbol naming variations

### ❌ What's Missing

1. **No Strategy Similarity Detection**
   - System doesn't compare strategy rules/indicators/parameters
   - Can activate RSI(14) and RSI(15) strategies on same symbol
   - Can activate multiple nearly-identical strategies with minor parameter tweaks

2. **No Symbol Correlation Detection**
   - System doesn't know SPY and SPX500 are highly correlated
   - Can open multiple positions in correlated assets
   - No correlation data storage or calculation

3. **No Proposal-Stage Filtering**
   - `propose_strategies()` generates candidates without checking similarity to active strategies
   - Wastes backtest compute on strategies that will be rejected anyway
   - No diversity enforcement during generation

---

## Recommended Fixes (Priority Order)

### Priority 1: Add Strategy Similarity Detection at Activation

**Where:** `src/strategy/strategy_engine.py` - `activate_strategy()` method

**What to Add:**
```python
def activate_strategy(self, strategy_id: str, mode: TradingMode, allocation_percent: float = 5.0) -> None:
    """Activate strategy for demo or live trading."""
    
    # ... existing validation code ...
    
    # NEW: Check similarity to active strategies
    active_strategies = self._get_active_strategies(mode)
    for active_strategy in active_strategies:
        similarity_score = self._compute_strategy_similarity(strategy, active_strategy)
        
        if similarity_score > 80:  # Configurable threshold
            raise ValueError(
                f"Strategy '{strategy.name}' is too similar ({similarity_score:.1f}%) "
                f"to active strategy '{active_strategy.name}'. "
                f"Activation blocked to prevent redundancy."
            )
    
    # ... rest of activation logic ...
```

**Implementation Details:**

```python
def _compute_strategy_similarity(self, strategy1: Strategy, strategy2: Strategy) -> float:
    """
    Compute similarity score (0-100) between two strategies.
    
    Components:
    - 40% indicator similarity (matching indicator types)
    - 30% parameter similarity (how close numeric parameters are)
    - 30% rule similarity (entry/exit conditions)
    - -20% penalty if different symbols (unless correlated)
    """
    
    # 1. Indicator Similarity (40%)
    indicators1 = set(strategy1.indicators.keys())
    indicators2 = set(strategy2.indicators.keys())
    
    if not indicators1 or not indicators2:
        indicator_sim = 0.0
    else:
        common = indicators1 & indicators2
        total = indicators1 | indicators2
        indicator_sim = len(common) / len(total) if total else 0.0
    
    # 2. Parameter Similarity (30%)
    param_sim = self._compute_parameter_similarity(strategy1, strategy2)
    
    # 3. Rule Similarity (30%)
    rule_sim = self._compute_rule_similarity(strategy1, strategy2)
    
    # 4. Symbol penalty
    symbol_penalty = 0.0
    if strategy1.symbols != strategy2.symbols:
        # Check if symbols are correlated
        if not self._are_symbols_correlated(strategy1.symbols, strategy2.symbols):
            symbol_penalty = 0.2
    
    # Weighted score
    score = (
        0.4 * indicator_sim +
        0.3 * param_sim +
        0.3 * rule_sim -
        symbol_penalty
    ) * 100
    
    return max(0.0, min(100.0, score))


def _compute_parameter_similarity(self, strategy1: Strategy, strategy2: Strategy) -> float:
    """Compare indicator parameters (e.g., RSI period 14 vs 15)."""
    
    # Get common indicators
    common_indicators = set(strategy1.indicators.keys()) & set(strategy2.indicators.keys())
    
    if not common_indicators:
        return 0.0
    
    similarities = []
    
    for indicator_name in common_indicators:
        params1 = strategy1.indicators[indicator_name]
        params2 = strategy2.indicators[indicator_name]
        
        # Compare each parameter
        if isinstance(params1, dict) and isinstance(params2, dict):
            common_params = set(params1.keys()) & set(params2.keys())
            
            for param_name in common_params:
                val1 = params1[param_name]
                val2 = params2[param_name]
                
                # Numeric comparison
                if isinstance(val1, (int, float)) and isinstance(val2, (int, float)):
                    # Calculate percentage difference
                    if val1 == 0 and val2 == 0:
                        param_sim = 1.0
                    elif val1 == 0 or val2 == 0:
                        param_sim = 0.0
                    else:
                        diff = abs(val1 - val2) / max(abs(val1), abs(val2))
                        param_sim = 1.0 - min(diff, 1.0)
                    
                    similarities.append(param_sim)
                
                # String comparison
                elif isinstance(val1, str) and isinstance(val2, str):
                    similarities.append(1.0 if val1 == val2 else 0.0)
    
    return sum(similarities) / len(similarities) if similarities else 0.0


def _compute_rule_similarity(self, strategy1: Strategy, strategy2: Strategy) -> float:
    """Compare entry/exit rules (simplified text comparison)."""
    
    # Extract rule text
    entry1 = str(strategy1.entry_rules) if hasattr(strategy1, 'entry_rules') else ""
    entry2 = str(strategy2.entry_rules) if hasattr(strategy2, 'entry_rules') else ""
    exit1 = str(strategy1.exit_rules) if hasattr(strategy1, 'exit_rules') else ""
    exit2 = str(strategy2.exit_rules) if hasattr(strategy2, 'exit_rules') else ""
    
    # Simple token-based similarity
    def token_similarity(text1: str, text2: str) -> float:
        tokens1 = set(text1.lower().split())
        tokens2 = set(text2.lower().split())
        
        if not tokens1 or not tokens2:
            return 0.0
        
        common = tokens1 & tokens2
        total = tokens1 | tokens2
        return len(common) / len(total) if total else 0.0
    
    entry_sim = token_similarity(entry1, entry2)
    exit_sim = token_similarity(exit1, exit2)
    
    return (entry_sim + exit_sim) / 2
```

**Configuration:**
Add to `config/autonomous_trading.yaml`:
```yaml
similarity_detection:
  enabled: true
  strategy_similarity_threshold: 80  # Block if >80% similar
  symbol_correlation_threshold: 0.8  # Treat as correlated if >0.8
  correlation_lookback_days: 90
```

---

### Priority 2: Add Symbol Correlation Detection

**Where:** New file `src/utils/correlation_analyzer.py`

**What to Add:**
```python
"""Symbol correlation analysis for preventing redundant positions."""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
from src.data.market_data_service import MarketDataService
import logging

logger = logging.getLogger(__name__)


class CorrelationAnalyzer:
    """Analyzes price correlations between trading symbols."""
    
    def __init__(self, market_data_service: MarketDataService):
        self.market_data = market_data_service
        self._correlation_cache = {}  # (symbol1, symbol2) -> (correlation, timestamp)
        self._cache_ttl_days = 7  # Refresh weekly
    
    def get_correlation(self, symbol1: str, symbol2: str, lookback_days: int = 90) -> Optional[float]:
        """
        Get correlation coefficient between two symbols.
        
        Returns:
            Correlation coefficient (-1.0 to 1.0) or None if insufficient data
        """
        # Normalize symbol order for cache key
        cache_key = tuple(sorted([symbol1, symbol2]))
        
        # Check cache
        if cache_key in self._correlation_cache:
            correlation, timestamp = self._correlation_cache[cache_key]
            age_days = (datetime.now() - timestamp).days
            
            if age_days < self._cache_ttl_days:
                return correlation
        
        # Calculate correlation
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=lookback_days)
            
            # Fetch price data
            data1 = self.market_data.get_historical_data(symbol1, start_date, end_date)
            data2 = self.market_data.get_historical_data(symbol2, start_date, end_date)
            
            if data1 is None or data2 is None or len(data1) < 20 or len(data2) < 20:
                logger.warning(f"Insufficient data for correlation: {symbol1} vs {symbol2}")
                return None
            
            # Align dates and calculate returns
            df1 = pd.DataFrame(data1).set_index('date')
            df2 = pd.DataFrame(data2).set_index('date')
            
            # Use closing prices
            prices = pd.DataFrame({
                symbol1: df1['close'],
                symbol2: df2['close']
            }).dropna()
            
            if len(prices) < 20:
                logger.warning(f"Insufficient aligned data for correlation: {symbol1} vs {symbol2}")
                return None
            
            # Calculate daily returns
            returns = prices.pct_change().dropna()
            
            # Calculate correlation
            correlation = returns[symbol1].corr(returns[symbol2])
            
            # Cache result
            self._correlation_cache[cache_key] = (correlation, datetime.now())
            
            logger.info(f"Correlation {symbol1} vs {symbol2}: {correlation:.3f}")
            return correlation
            
        except Exception as e:
            logger.error(f"Failed to calculate correlation {symbol1} vs {symbol2}: {e}")
            return None
    
    def are_correlated(self, symbol1: str, symbol2: str, threshold: float = 0.8) -> bool:
        """Check if two symbols are highly correlated."""
        correlation = self.get_correlation(symbol1, symbol2)
        
        if correlation is None:
            # If we can't calculate correlation, assume not correlated (fail open)
            return False
        
        return abs(correlation) >= threshold
    
    def find_correlated_symbols(self, symbol: str, symbol_list: List[str], threshold: float = 0.8) -> List[Tuple[str, float]]:
        """Find all symbols in list that are correlated with given symbol."""
        correlated = []
        
        for other_symbol in symbol_list:
            if other_symbol == symbol:
                continue
            
            correlation = self.get_correlation(symbol, other_symbol)
            
            if correlation is not None and abs(correlation) >= threshold:
                correlated.append((other_symbol, correlation))
        
        return correlated
```

**Integration into `_coordinate_signals`:**

Modify `src/core/trading_scheduler.py`:

```python
def _coordinate_signals(
        self,
        batch_results: Dict[str, List],
        strategy_map: Dict[str, tuple],
        existing_positions: List = None,
        pending_orders: List = None
    ) -> Dict[str, List]:
    """Coordinate signals from multiple strategies to avoid redundancy."""
    
    from src.utils.correlation_analyzer import CorrelationAnalyzer
    
    # Initialize correlation analyzer
    correlation_analyzer = CorrelationAnalyzer(self.market_data)
    
    # ... existing position/order mapping code ...
    
    # NEW: Build map of symbols with existing positions/orders
    active_symbols_by_direction = {}  # direction -> [symbols]
    
    for (normalized_symbol, direction), positions in existing_positions_map.items():
        if direction not in active_symbols_by_direction:
            active_symbols_by_direction[direction] = []
        active_symbols_by_direction[direction].append(normalized_symbol)
    
    # ... existing signal grouping code ...
    
    for (normalized_symbol, direction), signal_list in signals_by_symbol_direction.items():
        # Existing exact duplicate check
        existing_key = (normalized_symbol, direction)
        if existing_key in existing_positions_map:
            position_duplicate_count += len(signal_list)
            continue
        
        # NEW: Check for correlated symbols
        if direction in active_symbols_by_direction:
            for active_symbol in active_symbols_by_direction[direction]:
                if active_symbol == normalized_symbol:
                    continue
                
                if correlation_analyzer.are_correlated(normalized_symbol, active_symbol, threshold=0.8):
                    logger.info(
                        f"Correlation filter: {normalized_symbol} is correlated with active position "
                        f"in {active_symbol} ({direction}), filtering {len(signal_list)} signal(s)"
                    )
                    position_duplicate_count += len(signal_list)
                    continue  # Skip this symbol/direction
        
        # ... rest of coordination logic ...
```

---

### Priority 3: Add Proposal-Stage Filtering

**Where:** `src/strategy/strategy_proposer.py` - `propose_strategies()` method

**What to Add:**

```python
def propose_strategies(
        self,
        count: int = 5,
        symbols: List[str] = None,
        market_regime: Optional[MarketRegime] = None,
        use_walk_forward: bool = True,
        strategy_engine = None,
        optimize_parameters: bool = False
    ) -> List[Strategy]:
    """Generate strategy proposals based on current market conditions."""
    
    # ... existing generation code ...
    
    # NEW: Filter proposals similar to active strategies BEFORE backtesting
    if strategy_engine:
        active_strategies = strategy_engine._get_active_strategies(TradingMode.DEMO) + \
                           strategy_engine._get_active_strategies(TradingMode.LIVE)
        
        if active_strategies:
            logger.info(f"Filtering proposals against {len(active_strategies)} active strategies")
            
            filtered_strategies = []
            for proposed_strategy in strategies:
                is_too_similar = False
                
                for active_strategy in active_strategies:
                    similarity = strategy_engine._compute_strategy_similarity(
                        proposed_strategy, 
                        active_strategy
                    )
                    
                    if similarity > 70:  # Lower threshold for proposals (70 vs 80 for activation)
                        logger.info(
                            f"Filtered proposal '{proposed_strategy.name}' - "
                            f"{similarity:.1f}% similar to active '{active_strategy.name}'"
                        )
                        is_too_similar = True
                        break
                
                if not is_too_similar:
                    filtered_strategies.append(proposed_strategy)
            
            logger.info(
                f"Similarity filtering: {len(filtered_strategies)}/{len(strategies)} proposals "
                f"passed ({len(strategies) - len(filtered_strategies)} filtered)"
            )
            
            strategies = filtered_strategies
    
    # ... rest of proposal logic (walk-forward, etc.) ...
```

---

## Implementation Plan

### Phase 1: Core Similarity Detection (Week 1)
1. Add `_compute_strategy_similarity()` to `strategy_engine.py`
2. Add similarity check to `activate_strategy()`
3. Add configuration to `autonomous_trading.yaml`
4. Write unit tests for similarity calculation
5. Test with manual strategy activation

### Phase 2: Correlation Detection (Week 2)
1. Create `correlation_analyzer.py`
2. Integrate into `_coordinate_signals()`
3. Add correlation caching to database (optional)
4. Write unit tests for correlation detection
5. Test with correlated symbols (SPY/SPX500, GE/GER40)

### Phase 3: Proposal Filtering (Week 3)
1. Add similarity filtering to `propose_strategies()`
2. Adjust thresholds (70 for proposals, 80 for activation)
3. Add logging for filtered proposals
4. Test with autonomous generation cycle
5. Monitor diversity metrics

### Phase 4: Monitoring & Tuning (Week 4)
1. Add similarity metrics to dashboard
2. Track blocking statistics
3. Tune thresholds based on real data
4. Add emergency disable flag
5. Document configuration options

---

## Testing Strategy

### Unit Tests
```python
# tests/test_strategy_similarity.py

def test_identical_strategies_100_percent_similar():
    """Identical strategies should score 100%."""
    strategy1 = create_test_strategy(indicators={'RSI': {'period': 14}})
    strategy2 = create_test_strategy(indicators={'RSI': {'period': 14}})
    
    similarity = engine._compute_strategy_similarity(strategy1, strategy2)
    assert similarity > 95  # Allow small floating point differences


def test_different_symbols_reduces_similarity():
    """Different symbols should reduce similarity score."""
    strategy1 = create_test_strategy(symbols=['AAPL'], indicators={'RSI': {'period': 14}})
    strategy2 = create_test_strategy(symbols=['MSFT'], indicators={'RSI': {'period': 14}})
    
    similarity = engine._compute_strategy_similarity(strategy1, strategy2)
    assert similarity < 80  # 20% penalty for different symbols


def test_similar_parameters_high_similarity():
    """RSI(14) vs RSI(15) should be highly similar."""
    strategy1 = create_test_strategy(indicators={'RSI': {'period': 14}})
    strategy2 = create_test_strategy(indicators={'RSI': {'period': 15}})
    
    similarity = engine._compute_strategy_similarity(strategy1, strategy2)
    assert similarity > 85  # Very similar parameters


def test_activation_blocked_when_too_similar():
    """Activation should fail when strategy is too similar to active strategy."""
    # Activate first strategy
    engine.activate_strategy(strategy1.id, TradingMode.DEMO)
    
    # Try to activate similar strategy
    with pytest.raises(ValueError, match="too similar"):
        engine.activate_strategy(strategy2.id, TradingMode.DEMO)
```

### Integration Tests
```python
# tests/test_correlation_filtering.py

def test_correlated_symbols_filtered():
    """Signals for correlated symbols should be filtered."""
    # Create position in SPY
    create_position(symbol='SPY', side='LONG')
    
    # Generate signal for SPX500 (highly correlated)
    signals = {'strategy1': [create_signal(symbol='SPX500', action='ENTER_LONG')]}
    
    # Coordinate signals
    coordinated = scheduler._coordinate_signals(signals, {}, existing_positions, [])
    
    # Signal should be filtered
    assert len(coordinated) == 0
```

---

## Configuration Reference

```yaml
# config/autonomous_trading.yaml

similarity_detection:
  # Enable/disable similarity checks (emergency kill switch)
  enabled: true
  
  # Strategy similarity threshold (0-100)
  # Strategies with similarity > threshold are blocked
  strategy_similarity_threshold: 80
  
  # Proposal filtering threshold (typically lower than activation)
  proposal_similarity_threshold: 70
  
  # Symbol correlation threshold (-1.0 to 1.0)
  # Symbols with |correlation| > threshold are treated as correlated
  symbol_correlation_threshold: 0.8
  
  # Lookback period for correlation calculation
  correlation_lookback_days: 90
  
  # Cache TTL for correlation data
  correlation_cache_ttl_days: 7
  
  # Performance timeout (ms)
  # If similarity check exceeds timeout, allow strategy/trade (fail open)
  similarity_check_timeout_ms: 100
  
  # Similarity score component weights
  weights:
    indicator_similarity: 0.4
    parameter_similarity: 0.3
    rule_similarity: 0.3
    symbol_penalty: 0.2
```

---

## Monitoring & Alerts

### Metrics to Track
1. **Similarity Blocking Rate**: % of activations blocked due to similarity
2. **Correlation Filtering Rate**: % of signals filtered due to correlation
3. **Proposal Filtering Rate**: % of proposals filtered before backtest
4. **Active Strategy Diversity**: Average inter-strategy similarity
5. **Unique Symbols Traded**: Count of distinct symbols in active strategies

### Dashboard Additions
```python
# Add to monitoring dashboard

{
  "similarity_stats": {
    "strategies_blocked_today": 3,
    "signals_filtered_today": 12,
    "proposals_filtered_today": 8,
    "avg_active_strategy_similarity": 0.35,
    "unique_symbols_traded": 15
  }
}
```

---

## Performance Considerations

### Optimization Tips
1. **Cache Strategy Signatures**: Compute once, reuse for all comparisons
2. **Cache Correlations**: Refresh weekly, not on every signal
3. **Lazy Correlation Loading**: Only calculate when needed
4. **Timeout Protection**: Abort slow checks, fail open
5. **Batch Correlation Calculation**: Pre-compute common pairs

### Expected Performance
- Strategy similarity check: **<50ms** per comparison
- Correlation lookup (cached): **<10ms** per pair
- Correlation calculation (uncached): **<500ms** per pair
- Total signal coordination: **<100ms** for typical batch

---

## Rollout Strategy

### Phase 1: Shadow Mode (Week 1)
- Deploy similarity detection
- Log blocking decisions but don't actually block
- Collect data on what would be blocked
- Tune thresholds based on data

### Phase 2: Activation Blocking (Week 2)
- Enable blocking at activation time
- Monitor for false positives
- Adjust thresholds if needed
- Keep proposal filtering disabled

### Phase 3: Full Deployment (Week 3)
- Enable proposal filtering
- Enable correlation filtering
- Monitor system behavior
- Document any issues

### Phase 4: Optimization (Week 4)
- Optimize performance based on metrics
- Add dashboard visualizations
- Fine-tune thresholds
- Document best practices

---

## Risk Mitigation

### Fail-Safe Mechanisms
1. **Emergency Disable**: Config flag to disable all similarity checks
2. **Timeout Protection**: Abort slow checks, allow strategy/trade
3. **Graceful Degradation**: If correlation data unavailable, skip check
4. **Logging**: Comprehensive logging of all blocking decisions
5. **Manual Override**: Admin can force-activate similar strategies if needed

### Rollback Plan
1. Set `similarity_detection.enabled: false` in config
2. Restart trading scheduler
3. System reverts to exact duplicate checking only
4. No data loss or corruption

---

## Expected Impact

### Before Implementation
- ❌ Multiple RSI strategies with minor parameter differences
- ❌ Positions in SPY and SPX500 simultaneously
- ❌ Wasted backtest compute on similar proposals
- ❌ Concentrated risk in correlated assets

### After Implementation
- ✅ Diverse strategy portfolio (avg similarity <40%)
- ✅ No redundant positions in correlated symbols
- ✅ Efficient proposal generation (70% fewer backtests)
- ✅ Better risk distribution across uncorrelated assets

---

## Questions & Answers

**Q: What if I want to trade both SPY and SPX500?**
A: Lower the `symbol_correlation_threshold` or add an exception list in config.

**Q: What if similarity detection blocks a good strategy?**
A: Admin can manually override by temporarily disabling checks or lowering threshold.

**Q: How do I know if thresholds are set correctly?**
A: Monitor blocking rates. If >50% of activations are blocked, thresholds may be too strict.

**Q: What's the performance impact?**
A: Minimal. Similarity checks add <100ms to activation and signal coordination.

**Q: Can I disable this feature?**
A: Yes. Set `similarity_detection.enabled: false` in config.

---

## Next Steps

1. **Review this analysis** - Confirm approach aligns with your goals
2. **Prioritize phases** - Decide which phases to implement first
3. **Allocate resources** - Assign developers to implementation
4. **Set timeline** - Establish deadlines for each phase
5. **Begin Phase 1** - Start with core similarity detection

Let me know if you want me to implement any of these fixes directly!
