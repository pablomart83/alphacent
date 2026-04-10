# Trading System Fixes - 2026-02-20

## Issues Fixed

### 1. Tradeable Instruments Expansion ✅
**Problem**: System was limited to 34 symbols (stocks, ETFs, forex only). GE, GOLD, crypto, indices, and commodities were blocked.

**Solution**: Updated `src/core/tradeable_instruments.py` with comprehensive symbol list:
- **Stocks**: 45 symbols (added GE, PYPL, CRM, ADBE, ORCL, CSCO, PEP, KO, MCD, NKE, COST, HD, LOW, TGT, SBUX, UBER, ABNB, SNAP, PLTR, COIN)
- **ETFs**: 8 symbols (SPY, QQQ, IWM, DIA, GLD, SLV, VTI, VOO)
- **Forex**: 6 pairs (EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF)
- **Indices**: 5 symbols (SPX500, NSDQ100, DJ30, UK100, GER40)
- **Commodities**: 4 symbols (GOLD, SILVER, OIL, COPPER)
- **Crypto**: 18 symbols (BTC, ETH, SOL, XRP, ADA, AVAX, DOT, LINK, NEAR, SUI, APT, ARB, OP, RENDER, INJ, DOGE, LTC, BCH)

**Total**: 81 tradeable symbols (up from 34)

### 2. Smart Position Sizing ✅
**Problem**: Position sizing was too conservative and used flawed formula:
- Old: `position_size = (balance * 1%) / 2% = balance * 0.5` (capped at 10%)
- With $100K balance, max position was $10K (10%)
- With $0.06 balance, calculated $0.03 (below $10 minimum)

**Solution**: Implemented confidence-based smart position sizing in `src/risk/risk_manager.py`:
- **Scales with confidence**: 50% confidence = 12.5% position, 90% confidence = 18.5%
- **Increased limits**: 
  - Max position: 20% (was 10%)
  - Max exposure: 90% (was 80%)
  - Daily loss limit: 5% (was 3%)
  - Max drawdown: 15% (was 10%)
- **Better capital utilization**: With $100K, can now allocate $12.5K-$18.5K per trade
- **Respects existing exposure**: Accounts for open positions when calculating new position sizes

### 3. Risk Configuration Updates ✅
Updated `src/models/dataclasses.py` RiskConfig defaults:
```python
max_position_size_pct: 0.20  # 20% (was 10%)
max_exposure_pct: 0.90       # 90% (was 80%)
max_daily_loss_pct: 0.05     # 5% (was 3%)
max_drawdown_pct: 0.15       # 15% (was 10%)
position_risk_pct: 0.02      # 2% (was 1%)
stop_loss_pct: 0.04          # 4% (was 2%)
take_profit_pct: 0.10        # 10% (was 4%)
```

## Test Results

### E2E Trade Execution Test
```
✅ Strategy generation: 27 proposals → 4 activated
✅ Signal generation: 2 signals (GE, GOLD) - NEW SYMBOLS WORKING!
✅ Risk validation: Signals validated correctly
✅ Order execution: 1 order filled (WMT)
⚠️  Position sizing: GE/GOLD rejected due to $0.06 balance (below $10 minimum)
```

### Position Sizing Examples
| Balance    | Confidence | Position Size | % of Balance |
|------------|------------|---------------|--------------|
| $100       | 50%        | $12.50        | 12.5%        |
| $100       | 90%        | $18.50        | 18.5%        |
| $1,000     | 50%        | $125.00       | 12.5%        |
| $1,000     | 90%        | $185.00       | 18.5%        |
| $100,000   | 50%        | $12,500       | 12.5%        |
| $100,000   | 90%        | $18,500       | 18.5%        |

## Current Status

### ✅ Working
- 81 tradeable symbols across 6 asset classes
- Smart confidence-based position sizing
- Proper exposure management
- Signal generation for new symbols (GE, GOLD, crypto, etc.)
- End-to-end pipeline functional

### ⚠️ Known Issues
- **eToro DEMO balance depleted**: Account has $0.06 (was ~$100K)
  - Need to reset demo account through eToro web interface
  - Or wait for account to be refunded
- **31 open positions**: May be consuming all capital

### 📋 Next Steps
1. **Reset eToro DEMO account** to restore $100K balance
2. **Close unnecessary positions** to free up capital
3. **Re-run e2e test** to verify full trading across 81 symbols
4. **Monitor position sizing** in production to ensure optimal capital utilization

## Files Modified
- `src/core/tradeable_instruments.py` - Added 47 new symbols
- `src/risk/risk_manager.py` - Smart position sizing algorithm
- `src/models/dataclasses.py` - Updated RiskConfig defaults
