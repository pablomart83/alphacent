# Correlation Analysis Integration Guide

## Overview
This guide shows exactly how the new `CorrelationAnalyzer` will be integrated into the existing AlphaCent system to improve portfolio management and strategy selection.

## Integration Points

### 1. PortfolioManager - Strategy Activation (PRIMARY USE)

**Location**: `src/strategy/portfolio_manager.py` - `evaluate_for_activation()` method

**Current Flow**:
```
1. Check Sharpe ratio threshold
2. Check max drawdown
3. Check win rate
4. Check minimum trades
5. Activate if all pass
```

**Enhanced Flow with Correlation Analysis**:
```python
def evaluate_for_activation(
    self, strategy: Strategy, backtest_results: BacktestResults, market_context: Optional[Dict] = None
) -> bool:
    """Enhanced with correlation analysis."""
    
    # ... existing checks (Sharpe, drawdown, win rate, trades) ...
    
    # NEW: Check correlation with existing portfolio
    active_strategies = self.strategy_engine.get_active_strategies()
    
    if len(active_strategies) > 0:
        # Initialize correlation analyzer
        from src.strategy.correlation_analyzer import CorrelationAnalyzer
        analyzer = CorrelationAnalyzer()
        
        # Get returns and signals data for active strategies
        returns_data = self._get_strategy_returns(active_strategies + [strategy])
        signals_data = self._get_strategy_signals(active_strategies + [strategy])
        
        # Calculate current portfolio diversification
        current_div = analyzer.calculate_portfolio_diversification_score(
            active_strategies, returns_data, signals_data
        )
        
        # Calculate diversification with new strategy
        new_div = analyzer.calculate_portfolio_diversification_score(
            active_strategies + [strategy], returns_data, signals_data
        )
        
        # Check if new strategy improves diversification
        if new_div['diversification_score'] < current_div['diversification_score']:
            logger.warning(
                f"Strategy {strategy.name} reduces diversification: "
                f"{current_div['diversification_score']:.3f} -> {new_div['diversification_score']:.3f}"
            )
            
            # Check if max correlation is too high
            if new_div['max_correlation'] > 0.8:
                logger.info(
                    f"Strategy {strategy.name} rejected: "
                    f"Max correlation {new_div['max_correlation']:.3f} > 0.8"
                )
                return False
            
            # Reduce allocation if correlation is high but acceptable
            if new_div['max_correlation'] > 0.7:
                logger.info(
                    f"Strategy {strategy.name} has high correlation {new_div['max_correlation']:.3f}, "
                    f"will reduce allocation"
                )
                # This will be used in auto_activate_strategy()
                strategy.metadata['correlation_penalty'] = 0.5  # 50% reduction
        else:
            logger.info(
                f"Strategy {strategy.name} improves diversification: "
                f"{current_div['diversification_score']:.3f} -> {new_div['diversification_score']:.3f}"
            )
            # Bonus allocation for improving diversification
            strategy.metadata['diversification_bonus'] = 1.2  # 20% increase
    
    return True
```

**Impact**: 
- Rejects strategies with correlation > 0.8 to existing portfolio
- Reduces allocation for strategies with correlation 0.7-0.8
- Increases allocation for strategies that improve diversification

---

### 2. PortfolioManager - Allocation Optimization

**Location**: `src/strategy/portfolio_manager.py` - `optimize_allocations()` method

**Current Implementation**: Uses `PortfolioRiskManager` for basic correlation filtering

**Enhancement**:
```python
def optimize_allocations(
    self, strategies: List[Strategy], returns_data: Dict[str, pd.Series]
) -> Dict[str, float]:
    """Enhanced with multi-dimensional correlation."""
    
    # Initialize correlation analyzer
    from src.strategy.correlation_analyzer import CorrelationAnalyzer
    analyzer = CorrelationAnalyzer()
    
    # Get signals data
    signals_data = self._get_strategy_signals(strategies)
    
    # Calculate multi-dimensional correlations
    diversification = analyzer.calculate_portfolio_diversification_score(
        strategies, returns_data, signals_data
    )
    
    logger.info(
        f"Portfolio diversification: {diversification['diversification_score']:.3f}, "
        f"Max correlation: {diversification['max_correlation']:.3f}"
    )
    
    # Use existing PortfolioRiskManager for base allocations
    base_allocations = self.portfolio_risk_manager.optimize_allocations(
        strategies, returns_data
    )
    
    # Adjust allocations based on multi-dimensional correlation
    adjusted_allocations = {}
    for strategy in strategies:
        base_alloc = base_allocations[strategy.id]
        
        # Find average correlation with other strategies
        avg_corr = 0.0
        count = 0
        for other_strategy in strategies:
            if other_strategy.id != strategy.id:
                if strategy.id in diversification['correlation_matrix']:
                    if other_strategy.id in diversification['correlation_matrix'][strategy.id]:
                        avg_corr += diversification['correlation_matrix'][strategy.id][other_strategy.id]
                        count += 1
        
        if count > 0:
            avg_corr /= count
            
            # Penalize highly correlated strategies
            if avg_corr > 0.7:
                penalty = 0.7  # 30% reduction
            elif avg_corr > 0.5:
                penalty = 0.85  # 15% reduction
            else:
                penalty = 1.0  # No penalty
            
            adjusted_allocations[strategy.id] = base_alloc * penalty
            
            logger.info(
                f"Strategy {strategy.name}: avg_corr={avg_corr:.3f}, "
                f"penalty={penalty:.2f}, alloc={base_alloc:.1f}% -> {adjusted_allocations[strategy.id]:.1f}%"
            )
        else:
            adjusted_allocations[strategy.id] = base_alloc
    
    # Normalize to 100%
    total = sum(adjusted_allocations.values())
    if total > 0:
        adjusted_allocations = {
            sid: (alloc / total) * 100.0 
            for sid, alloc in adjusted_allocations.items()
        }
    
    return adjusted_allocations
```

**Impact**:
- Reduces allocation to highly correlated strategies (30% reduction if avg_corr > 0.7)
- Maintains total portfolio allocation at 100%
- Uses multi-dimensional correlation (not just returns)

---

### 3. AutonomousStrategyManager - Daily Monitoring

**Location**: `src/strategy/autonomous_strategy_manager.py` - Add new method

**New Method**:
```python
def monitor_correlation_regime_changes(self) -> List[Dict]:
    """
    Monitor correlation changes between active strategies.
    
    Called daily to detect significant correlation changes that may require rebalancing.
    
    Returns:
        List of correlation regime changes detected
    """
    from src.strategy.correlation_analyzer import CorrelationAnalyzer
    
    analyzer = CorrelationAnalyzer()
    active_strategies = self.strategy_engine.get_active_strategies()
    
    if len(active_strategies) < 2:
        return []
    
    changes = []
    
    # Check all pairs for regime changes
    for i, s1 in enumerate(active_strategies):
        for s2 in active_strategies[i+1:]:
            changed, details = analyzer.detect_correlation_regime_change(
                s1.id, s2.id, threshold=0.4
            )
            
            if changed:
                logger.warning(
                    f"Correlation regime change detected: {s1.name} & {s2.name} - "
                    f"{details['old_correlation']:.3f} -> {details['new_correlation']:.3f}"
                )
                
                changes.append({
                    'strategy1': s1.name,
                    'strategy2': s2.name,
                    'old_correlation': details['old_correlation'],
                    'new_correlation': details['new_correlation'],
                    'change': details['change'],
                })
                
                # If correlation increased significantly, consider rebalancing
                if details['new_correlation'] > 0.7 and details['old_correlation'] < 0.5:
                    logger.warning(
                        f"Correlation increased from {details['old_correlation']:.3f} to "
                        f"{details['new_correlation']:.3f} - triggering rebalance"
                    )
                    self.portfolio_manager.rebalance_portfolio()
    
    return changes
```

**Usage in Daily Cycle**:
```python
def run_strategy_cycle(self) -> Dict:
    """Enhanced with correlation monitoring."""
    
    # ... existing proposal, backtest, activation logic ...
    
    # NEW: Monitor correlation regime changes
    correlation_changes = self.monitor_correlation_regime_changes()
    
    if correlation_changes:
        logger.info(f"Detected {len(correlation_changes)} correlation regime changes")
        stats['correlation_changes'] = len(correlation_changes)
    
    return stats
```

**Impact**:
- Detects when strategies become more/less correlated over time
- Triggers portfolio rebalancing when correlation increases significantly
- Prevents portfolio from becoming too concentrated

---

### 4. Strategy Proposer - Diversification-Aware Generation

**Location**: `src/strategy/strategy_proposer.py` - `propose_strategies()` method

**Enhancement**:
```python
def propose_strategies(self, count: int = 3) -> List[Strategy]:
    """Enhanced to prefer strategies that improve diversification."""
    
    # Get active strategies
    active_strategies = self.strategy_engine.get_active_strategies()
    
    # Generate 2x candidates
    candidates = self._generate_strategy_candidates(count * 2)
    
    if len(active_strategies) > 0:
        from src.strategy.correlation_analyzer import CorrelationAnalyzer
        analyzer = CorrelationAnalyzer()
        
        # Get current portfolio data
        returns_data = self._get_strategy_returns(active_strategies)
        signals_data = self._get_strategy_signals(active_strategies)
        
        # Calculate current diversification
        current_div = analyzer.calculate_portfolio_diversification_score(
            active_strategies, returns_data, signals_data
        )
        
        # Score each candidate by diversification improvement
        candidate_scores = []
        for candidate in candidates:
            # Simulate adding candidate to portfolio
            candidate_returns = self._simulate_strategy_returns(candidate)
            candidate_signals = self._simulate_strategy_signals(candidate)
            
            returns_data_with_candidate = {**returns_data, candidate.id: candidate_returns}
            signals_data_with_candidate = {**signals_data, candidate.id: candidate_signals}
            
            new_div = analyzer.calculate_portfolio_diversification_score(
                active_strategies + [candidate],
                returns_data_with_candidate,
                signals_data_with_candidate
            )
            
            # Score = diversification improvement + base quality
            div_improvement = new_div['diversification_score'] - current_div['diversification_score']
            base_quality = candidate.metadata.get('quality_score', 0.5)
            
            total_score = base_quality + (div_improvement * 2.0)  # Weight diversification 2x
            
            candidate_scores.append((candidate, total_score, div_improvement))
            
            logger.info(
                f"Candidate {candidate.name}: quality={base_quality:.3f}, "
                f"div_improvement={div_improvement:.3f}, total_score={total_score:.3f}"
            )
        
        # Sort by total score and select top N
        candidate_scores.sort(key=lambda x: x[1], reverse=True)
        selected = [c[0] for c in candidate_scores[:count]]
        
        logger.info(f"Selected {len(selected)} strategies that improve diversification")
        return selected
    
    # No active strategies, just return top candidates by quality
    return candidates[:count]
```

**Impact**:
- Generates strategies that complement existing portfolio
- Prefers strategies with low correlation to active strategies
- Balances quality and diversification

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                  Daily Autonomous Cycle                      │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│  1. Strategy Proposer                                        │
│     - Generate candidates                                    │
│     - Score by diversification improvement ◄─────────────┐   │
│     - Select top N                                       │   │
└──────────────────────────────────────┬───────────────────┘   │
                                       │                       │
                                       ▼                       │
┌─────────────────────────────────────────────────────────────┤
│  2. Backtest Engine                                      │   │
│     - Run backtests                                      │   │
│     - Generate returns & signals data                    │   │
└──────────────────────────────────────┬───────────────────┘   │
                                       │                       │
                                       ▼                       │
┌─────────────────────────────────────────────────────────────┤
│  3. Portfolio Manager - Activation                       │   │
│     - Check Sharpe, drawdown, win rate                   │   │
│     - Calculate correlation with portfolio ◄─────────────┤   │
│     - Reject if correlation > 0.8                        │   │
│     - Adjust allocation based on correlation             │   │
└──────────────────────────────────────┬───────────────────┘   │
                                       │                       │
                                       ▼                       │
┌─────────────────────────────────────────────────────────────┤
│  4. Portfolio Manager - Allocation                       │   │
│     - Optimize allocations                               │   │
│     - Penalize highly correlated strategies ◄────────────┤   │
│     - Normalize to 100%                                  │   │
└──────────────────────────────────────┬───────────────────┘   │
                                       │                       │
                                       ▼                       │
┌─────────────────────────────────────────────────────────────┤
│  5. Correlation Monitoring                               │   │
│     - Check all strategy pairs                           │   │
│     - Detect regime changes ◄────────────────────────────┤   │
│     - Trigger rebalancing if needed                      │   │
└──────────────────────────────────────┬───────────────────┘   │
                                       │                       │
                                       ▼                       │
                            ┌──────────────────┐               │
                            │ CorrelationAnalyzer│──────────────┘
                            │                  │
                            │ - Multi-dim corr │
                            │ - Diversification│
                            │ - Regime changes │
                            │ - DB storage     │
                            └──────────────────┘
```

---

## Configuration

Add to `config/autonomous_trading.yaml`:

```yaml
correlation_analysis:
  enabled: true
  
  # Activation thresholds
  max_correlation_for_activation: 0.8  # Reject if > 0.8
  high_correlation_threshold: 0.7      # Reduce allocation if > 0.7
  
  # Allocation adjustments
  high_correlation_penalty: 0.7        # 30% reduction
  medium_correlation_penalty: 0.85     # 15% reduction
  diversification_bonus: 1.2           # 20% increase
  
  # Monitoring
  regime_change_threshold: 0.4         # Alert if change > 0.4
  monitoring_frequency: "daily"        # Check daily
  
  # Correlation weights (for composite score)
  returns_weight: 0.4
  signal_weight: 0.2
  drawdown_weight: 0.2
  volatility_weight: 0.2
```

---

## Example Scenarios

### Scenario 1: Rejecting Highly Correlated Strategy
```
Current Portfolio:
  - Strategy A (Mean Reversion, SPY)
  - Strategy B (Mean Reversion, QQQ)
  - Diversification Score: 0.65

New Proposal:
  - Strategy C (Mean Reversion, DIA)
  - Correlation with A: 0.85
  - Correlation with B: 0.82

Decision: REJECT
Reason: Max correlation 0.85 > 0.8 threshold
```

### Scenario 2: Reducing Allocation for Moderate Correlation
```
Current Portfolio:
  - Strategy A (Mean Reversion, SPY)
  - Strategy B (Momentum, QQQ)
  - Diversification Score: 0.75

New Proposal:
  - Strategy C (Mean Reversion, IWM)
  - Correlation with A: 0.72
  - Correlation with B: 0.45

Decision: ACTIVATE with reduced allocation
Base Allocation: 20%
Adjusted Allocation: 14% (30% penalty for high correlation with A)
```

### Scenario 3: Bonus for Improving Diversification
```
Current Portfolio:
  - Strategy A (Mean Reversion, SPY)
  - Strategy B (Mean Reversion, QQQ)
  - Diversification Score: 0.55 (low)

New Proposal:
  - Strategy C (Momentum, TLT - bonds)
  - Correlation with A: 0.15
  - Correlation with B: 0.20
  - New Diversification Score: 0.78

Decision: ACTIVATE with bonus allocation
Base Allocation: 20%
Adjusted Allocation: 24% (20% bonus for improving diversification)
```

### Scenario 4: Correlation Regime Change
```
Day 1:
  - Strategy A & B correlation: 0.35 (low)
  - Portfolio diversification: 0.80

Day 30:
  - Strategy A & B correlation: 0.78 (high)
  - Change: 0.43 > 0.4 threshold

Action: ALERT + REBALANCE
  - Reduce allocation to Strategy B from 25% to 17.5%
  - Redistribute to uncorrelated strategies
```

---

## Testing Integration

Add integration test in `test_e2e_autonomous_system.py`:

```python
def test_correlation_aware_activation():
    """Test that correlation analysis affects activation decisions."""
    
    # Create portfolio with 2 correlated strategies
    strategy1 = create_mean_reversion_strategy("A")
    strategy2 = create_mean_reversion_strategy("B")
    
    # Activate both
    portfolio_manager.auto_activate_strategy(strategy1, 20.0)
    portfolio_manager.auto_activate_strategy(strategy2, 20.0)
    
    # Propose highly correlated strategy
    strategy3 = create_mean_reversion_strategy("C")
    
    # Should be rejected due to high correlation
    should_activate = portfolio_manager.evaluate_for_activation(
        strategy3, strategy3.backtest_results
    )
    
    assert not should_activate, "Highly correlated strategy should be rejected"
    
    # Propose uncorrelated strategy
    strategy4 = create_momentum_strategy("D")
    
    # Should be activated with bonus
    should_activate = portfolio_manager.evaluate_for_activation(
        strategy4, strategy4.backtest_results
    )
    
    assert should_activate, "Uncorrelated strategy should be activated"
    assert strategy4.metadata.get('diversification_bonus') == 1.2
```

---

## Summary

The correlation analysis will be used in **4 key places**:

1. **Strategy Activation** - Reject/penalize highly correlated strategies
2. **Allocation Optimization** - Reduce allocation to correlated strategies
3. **Daily Monitoring** - Detect correlation regime changes
4. **Strategy Proposal** - Generate strategies that improve diversification

This creates a **closed-loop system** where:
- Portfolio maintains high diversification (target: 0.7+)
- Correlated strategies are automatically penalized
- Correlation changes trigger rebalancing
- New strategies are selected to complement existing portfolio

**Expected Impact**:
- Reduce portfolio volatility by 15-25%
- Improve risk-adjusted returns (Sharpe ratio +0.2 to +0.5)
- Prevent concentration risk from correlated strategies
- Adapt to changing market correlations automatically
