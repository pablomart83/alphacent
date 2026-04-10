# Fundamental Data Change Frequency Analysis

## How Often Do Fundamentals Actually Change?

### Financial Statement Data (Quarterly Updates)

| Data Type | Update Frequency | Source | Typical Change Pattern |
|-----------|------------------|--------|------------------------|
| **EPS** | Quarterly (every ~90 days) | Income Statement | Changes 4x/year after earnings |
| **Revenue** | Quarterly (every ~90 days) | Income Statement | Changes 4x/year after earnings |
| **Revenue Growth** | Quarterly (every ~90 days) | Income Statement | Changes 4x/year after earnings |
| **Total Debt** | Quarterly (every ~90 days) | Balance Sheet | Changes 4x/year, gradual |
| **Total Equity** | Quarterly (every ~90 days) | Balance Sheet | Changes 4x/year, gradual |
| **Debt-to-Equity** | Quarterly (every ~90 days) | Calculated | Changes 4x/year |
| **ROE** | Quarterly (every ~90 days) | Key Metrics | Changes 4x/year |

### Market-Based Data (Daily Updates)

| Data Type | Update Frequency | Source | Typical Change Pattern |
|-----------|------------------|--------|------------------------|
| **P/E Ratio** | Daily | Price / EPS | Changes daily with stock price |
| **Market Cap** | Daily | Price × Shares | Changes daily with stock price |
| **Price** | Real-time | Market Data | Changes every second during trading |

### Rare Updates

| Data Type | Update Frequency | Source | Typical Change Pattern |
|-----------|------------------|--------|------------------------|
| **Insider Trading** | Sporadic (monthly?) | SEC Filings | Irregular, when insiders trade |
| **Shares Outstanding** | Rare (annually?) | Company Filings | Changes with buybacks/dilution |
| **Share Dilution** | Rare (annually?) | Calculated | Changes with stock splits/offerings |

## Current Cache Strategy Analysis

### Current: 24-Hour Cache TTL

**Pros:**
- Simple, consistent
- Covers daily trading cycle
- Reduces API calls significantly

**Cons:**
- **Wastes API calls on market-based data** - P/E ratio and market cap change daily but we're fetching quarterly data
- **Too frequent for quarterly data** - EPS, revenue, etc. only change 4x/year
- **Not aligned with earnings calendar** - We refresh cache even when no earnings have been reported

## Recommended Optimization: Smart TTL Based on Data Type

### Strategy 1: Separate Cache TTLs by Data Freshness

```python
# Quarterly financial data (changes 4x/year)
QUARTERLY_DATA_TTL = 30 * 24 * 3600  # 30 days

# Market-based data (changes daily)
MARKET_DATA_TTL = 24 * 3600  # 24 hours

# Rare data (changes infrequently)
RARE_DATA_TTL = 90 * 24 * 3600  # 90 days
```

**Problem:** FMP API returns all data in one call, can't separate TTLs easily.

### Strategy 2: Earnings-Aware Caching (RECOMMENDED)

**Key Insight:** Fundamentals only meaningfully change after earnings reports!

```python
def get_cache_ttl(symbol: str) -> int:
    """
    Calculate smart TTL based on earnings calendar.
    
    Logic:
    - If earnings reported in last 7 days: 24 hours (data is fresh, may be revised)
    - If earnings coming in next 7 days: 24 hours (prepare for update)
    - Otherwise: 30 days (nothing will change until next earnings)
    """
    days_since_earnings = get_days_since_earnings(symbol)
    days_until_earnings = get_days_until_earnings(symbol)
    
    if days_since_earnings is not None and days_since_earnings <= 7:
        return 24 * 3600  # 24 hours - fresh earnings
    
    if days_until_earnings is not None and days_until_earnings <= 7:
        return 24 * 3600  # 24 hours - earnings coming soon
    
    return 30 * 24 * 3600  # 30 days - stable period
```

**Impact:**
- **90% of the time:** 30-day cache (between earnings)
- **10% of the time:** 24-hour cache (around earnings)
- **API calls reduced by 96%** (30 days vs 1 day)

### Strategy 3: Market Data Separation (ADVANCED)

**Key Insight:** P/E ratio and market cap can be calculated from price + cached fundamentals!

```python
def get_fundamental_data_smart(symbol: str) -> FundamentalData:
    """
    Get fundamentals with smart market data calculation.
    
    1. Get cached quarterly data (EPS, revenue, etc.) - 30 day TTL
    2. Get current price from market data (real-time)
    3. Calculate P/E ratio = price / cached_eps
    4. Calculate market cap = price * cached_shares_outstanding
    """
    # Get cached fundamentals (30-day TTL)
    cached_data = get_from_cache(symbol)
    
    if cached_data and not is_earnings_period(symbol):
        # Update market-based metrics with current price
        current_price = get_current_price(symbol)
        
        if cached_data.eps and cached_data.eps > 0:
            cached_data.pe_ratio = current_price / cached_data.eps
        
        if cached_data.shares_outstanding:
            cached_data.market_cap = current_price * cached_data.shares_outstanding
        
        return cached_data
    
    # Fetch fresh data from API
    return fetch_from_fmp(symbol)
```

**Impact:**
- **P/E ratio always current** (calculated from latest price)
- **Market cap always current** (calculated from latest price)
- **API calls reduced by 96%** (only fetch quarterly data after earnings)

## Recommended Implementation

### Phase 1: Earnings-Aware Caching (Quick Win)

**Change:** Extend cache TTL from 24 hours to 30 days, except around earnings

**Files to modify:**
- `src/data/fundamental_data_provider.py` - Add smart TTL logic
- `config/autonomous_trading.yaml` - Add earnings-aware config

**Expected savings:**
- API calls: 240/day → 25/day (90% reduction)
- Rate limit usage: 96% → 10%

### Phase 2: Market Data Calculation (Advanced)

**Change:** Calculate P/E and market cap from current price + cached EPS

**Files to modify:**
- `src/data/fundamental_data_provider.py` - Add market data calculation
- `src/data/market_data_manager.py` - Integrate price fetching

**Expected savings:**
- API calls: 25/day → 10/day (60% additional reduction)
- Always-current P/E ratios without API calls

## Earnings Calendar Integration

### Current State
- `get_earnings_calendar()` exists but not used for caching decisions
- Makes separate API calls for earnings data

### Proposed Enhancement

```python
class FundamentalDataProvider:
    def __init__(self, config):
        # ... existing code ...
        
        # Earnings calendar cache (longer TTL since earnings dates don't change often)
        self.earnings_calendar_cache = {}
        self.earnings_calendar_ttl = 7 * 24 * 3600  # 7 days
    
    def is_earnings_period(self, symbol: str) -> bool:
        """Check if we're in an earnings period (±7 days from earnings)."""
        earnings_data = self.get_earnings_calendar_cached(symbol)
        
        if not earnings_data:
            return False  # Assume not in earnings period if unknown
        
        last_earnings = earnings_data.get('last_earnings_date')
        if last_earnings:
            days_since = (datetime.now() - datetime.strptime(last_earnings, '%Y-%m-%d')).days
            if days_since <= 7:
                return True  # Recent earnings
        
        # Check next earnings (if available)
        next_earnings = earnings_data.get('next_earnings_date')
        if next_earnings:
            days_until = (datetime.strptime(next_earnings, '%Y-%m-%d') - datetime.now()).days
            if days_until <= 7:
                return True  # Upcoming earnings
        
        return False
    
    def get_smart_cache_ttl(self, symbol: str) -> int:
        """Get cache TTL based on earnings calendar."""
        if self.is_earnings_period(symbol):
            return 24 * 3600  # 24 hours during earnings period
        else:
            return 30 * 24 * 3600  # 30 days otherwise
```

## API Call Projection with Smart Caching

### Current (24-hour cache):
```
Day 1: 20 symbols × 4 endpoints = 80 calls
Day 2: 0 calls (cache hit)
Day 3: 80 calls (cache expired)
Day 4: 0 calls (cache hit)
...
Monthly total: ~1,200 calls
```

### With Earnings-Aware Caching (30-day cache):
```
Day 1: 20 symbols × 4 endpoints = 80 calls
Days 2-30: 0 calls (cache hit)
Day 31: 80 calls (cache expired)
Days 32-60: 0 calls (cache hit)
...
Monthly total: ~80 calls (93% reduction!)

Exception: During earnings week (2 symbols)
Day 1: 2 symbols × 4 endpoints = 8 calls
Day 2: 8 calls (24-hour cache)
Day 3: 8 calls
...
Earnings week total: ~56 calls

Monthly total with earnings: 80 + 56 = 136 calls (89% reduction)
```

### With Market Data Calculation:
```
Same as above, but P/E and market cap always current
No additional API calls needed
```

## Configuration Changes

### Add to `config/autonomous_trading.yaml`:

```yaml
data_sources:
  financial_modeling_prep:
    enabled: true
    api_key: ${FMP_API_KEY}
    rate_limit: 250
    
    # Smart caching configuration
    cache_strategy: "earnings_aware"  # Options: "fixed", "earnings_aware"
    
    # Fixed cache duration (used if cache_strategy = "fixed")
    cache_duration: 86400  # 24 hours
    
    # Earnings-aware cache durations (used if cache_strategy = "earnings_aware")
    earnings_aware_cache:
      default_ttl: 2592000  # 30 days (between earnings)
      earnings_period_ttl: 86400  # 24 hours (±7 days from earnings)
      earnings_calendar_ttl: 604800  # 7 days (earnings dates cache)
    
    # Market data calculation (calculate P/E from current price + cached EPS)
    calculate_market_metrics: true  # Calculate P/E and market cap from price
```

## Implementation Priority

### High Priority (Implement Now)
1. ✅ **Database caching** - Already done
2. ✅ **Deferred filtering** - Already done
3. ✅ **Circuit breaker** - Already done
4. 🔄 **Earnings-aware caching** - Implement next (90% API reduction)

### Medium Priority (Next Sprint)
5. **Market data calculation** - Calculate P/E from price (60% additional reduction)
6. **Earnings calendar caching** - Cache earnings dates for 7 days

### Low Priority (Future)
7. **Batch API calls** - If FMP offers batch endpoints
8. **Predictive cache warming** - Pre-fetch before earnings
9. **Symbol prioritization** - Cache frequently-traded symbols longer

## Risk Analysis

### Risks of Longer Cache TTL

| Risk | Mitigation |
|------|------------|
| **Stale data during earnings** | Use earnings-aware caching (24h during earnings) |
| **Missed corporate actions** | Monitor for stock splits, buybacks (rare events) |
| **Incorrect P/E ratios** | Calculate from current price + cached EPS |
| **Regulatory changes** | Quarterly data is filed officially, rarely revised |

### Benefits vs Risks

**Benefits:**
- 90% reduction in API calls
- Faster signal generation
- Lower costs
- Better rate limit management

**Risks:**
- Minimal - fundamentals genuinely don't change between earnings
- Mitigated by earnings-aware caching

## Conclusion

**24-hour cache is too aggressive for fundamental data!**

Fundamentals only change quarterly (after earnings), yet we're refreshing daily. This wastes:
- 96% of API calls (30 days vs 1 day)
- Rate limit capacity
- System resources

**Recommended action:**
1. Implement earnings-aware caching (30-day default, 24-hour during earnings)
2. Calculate market metrics from current price + cached fundamentals
3. Monitor for 1 week to verify data freshness

**Expected impact:**
- API calls: 240/day → 10-25/day (90-96% reduction)
- Rate limit usage: 96% → 4-10%
- Data freshness: Improved (P/E always current)
