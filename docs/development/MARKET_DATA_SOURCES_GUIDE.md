# Market Data Sources Integration Guide

## Overview

This guide explains how to integrate multiple free data sources into the Market Statistics Analyzer to enhance strategy generation with real market data.

## Data Sources Stack (100% FREE)

### 1. Yahoo Finance (Primary - Already Implemented)
- **Purpose**: OHLCV data (Open, High, Low, Close, Volume)
- **Cost**: FREE, unlimited
- **Reliability**: High
- **Coverage**: Stocks, ETFs, indices, forex, crypto
- **Usage**: Primary source for all price data

### 2. Alpha Vantage (Secondary - NEW)
- **Purpose**: Pre-calculated technical indicators, sector data
- **Cost**: FREE (500 API calls/day)
- **Reliability**: High
- **Coverage**: Stocks, forex, crypto, technical indicators
- **API Key**: Get free key at https://www.alphavantage.co/support/#api-key
- **Usage**: 
  - Pre-calculated indicators (saves computation)
  - Sector performance data
  - Fallback for Yahoo Finance

### 3. FRED (Tertiary - NEW)
- **Purpose**: Macro economic context
- **Cost**: FREE, unlimited
- **Reliability**: Very High (Federal Reserve data)
- **Coverage**: Economic indicators, rates, VIX, GDP, inflation
- **API Key**: Get free key at https://fred.stlouisfed.org/docs/api/api_key.html
- **Usage**:
  - VIX (market fear index)
  - Treasury yields (risk-free rate)
  - Economic indicators (GDP, unemployment, inflation)

## Setup Instructions

### Step 1: Install Dependencies

```bash
# Activate virtual environment
source venv/bin/activate

# Install new packages
pip install alpha-vantage fredapi

# Update requirements.txt
pip freeze > requirements.txt
```

### Step 2: Get Free API Keys

#### Alpha Vantage (30 seconds)
1. Go to https://www.alphavantage.co/support/#api-key
2. Enter your email
3. Get instant API key (no verification needed)
4. Free tier: 500 calls/day (plenty for our use case)

#### FRED (2 minutes)
1. Go to https://fred.stlouisfed.org/
2. Click "My Account" → "API Keys"
3. Create account (free)
4. Request API key
5. Get instant approval
6. Free tier: Unlimited calls

### Step 3: Configure API Keys

Add to `config/autonomous_trading.yaml`:

```yaml
data_sources:
  alpha_vantage:
    enabled: true
    api_key: "YOUR_ALPHA_VANTAGE_KEY"
    calls_per_day: 500
    cache_hours: 4  # Cache data for 4 hours
  
  fred:
    enabled: true
    api_key: "YOUR_FRED_KEY"
    calls_per_day: unlimited
    cache_hours: 24  # Cache data for 24 hours
  
  yahoo_finance:
    enabled: true
    cache_hours: 1  # Cache data for 1 hour
```

### Step 4: Environment Variables (Optional)

For security, you can use environment variables instead:

```bash
# Add to .env file
ALPHA_VANTAGE_API_KEY=your_key_here
FRED_API_KEY=your_key_here

# Load in Python
import os
from dotenv import load_dotenv

load_dotenv()
alpha_key = os.getenv('ALPHA_VANTAGE_API_KEY')
fred_key = os.getenv('FRED_API_KEY')
```

## Implementation Architecture

### Data Flow

```
Strategy Generation Request
    ↓
MarketStatisticsAnalyzer.analyze_symbol()
    ↓
┌─────────────────────────────────────────┐
│ 1. Check Cache (1-24 hours)            │
│    - If cached, return immediately      │
│    - If expired, fetch new data         │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ 2. Fetch OHLCV (Yahoo Finance)         │
│    - Primary source                     │
│    - Calculate basic metrics            │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ 3. Fetch Indicators (Alpha Vantage)    │
│    - Try pre-calculated RSI, MACD, etc. │
│    - If fails, calculate locally        │
│    - Track API call count               │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ 4. Fetch Market Context (FRED)         │
│    - Get VIX (market fear)              │
│    - Get treasury yields                │
│    - Get economic indicators            │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ 5. Combine & Analyze                    │
│    - Merge all data sources             │
│    - Calculate derived metrics          │
│    - Return comprehensive statistics    │
└─────────────────────────────────────────┘
    ↓
Cache Results & Return to LLM
```

### Graceful Fallback Strategy

```python
def analyze_symbol(self, symbol, period=90):
    """Analyze symbol with graceful fallback."""
    
    # 1. Always get OHLCV from Yahoo Finance (primary)
    try:
        ohlcv = self.yahoo.download(symbol, period=f"{period}d")
    except Exception as e:
        logger.error(f"Yahoo Finance failed: {e}")
        raise  # Can't proceed without OHLCV
    
    # 2. Try Alpha Vantage for indicators (optional)
    try:
        if self.alpha_vantage_enabled:
            rsi = self.alpha_vantage.get_rsi(symbol)
            macd = self.alpha_vantage.get_macd(symbol)
        else:
            raise Exception("Alpha Vantage disabled")
    except Exception as e:
        logger.warning(f"Alpha Vantage failed, calculating locally: {e}")
        rsi = self._calculate_rsi(ohlcv)
        macd = self._calculate_macd(ohlcv)
    
    # 3. Try FRED for market context (optional)
    try:
        if self.fred_enabled:
            vix = self.fred.get_series_latest_release('VIXCLS')
            treasury = self.fred.get_series_latest_release('DGS10')
        else:
            raise Exception("FRED disabled")
    except Exception as e:
        logger.warning(f"FRED failed, using defaults: {e}")
        vix = None  # Optional context
        treasury = None
    
    # 4. Combine all data
    return {
        'ohlcv': ohlcv,  # Always available
        'rsi': rsi,  # Always available (calculated or fetched)
        'macd': macd,  # Always available (calculated or fetched)
        'vix': vix,  # Optional (None if unavailable)
        'treasury': treasury  # Optional (None if unavailable)
    }
```

## API Usage Examples

### Alpha Vantage Examples

```python
from alpha_vantage.timeseries import TimeSeries
from alpha_vantage.techindicators import TechIndicators

# Initialize
ts = TimeSeries(key='YOUR_KEY', output_format='pandas')
ti = TechIndicators(key='YOUR_KEY', output_format='pandas')

# Get OHLCV data
data, meta = ts.get_daily(symbol='AAPL', outputsize='full')

# Get pre-calculated RSI
rsi_data, meta = ti.get_rsi(symbol='AAPL', interval='daily', time_period=14)

# Get pre-calculated MACD
macd_data, meta = ti.get_macd(symbol='AAPL', interval='daily')

# Get pre-calculated Bollinger Bands
bbands_data, meta = ti.get_bbands(symbol='AAPL', interval='daily', time_period=20)

# Get sector performance
from alpha_vantage.sectorperformance import SectorPerformances
sp = SectorPerformances(key='YOUR_KEY', output_format='pandas')
sector_data, meta = sp.get_sector()
```

### FRED Examples

```python
from fredapi import Fred

# Initialize
fred = Fred(api_key='YOUR_KEY')

# Get VIX (market volatility/fear index)
vix = fred.get_series('VIXCLS')  # CBOE Volatility Index
current_vix = vix.iloc[-1]

# Get treasury yields
treasury_10y = fred.get_series('DGS10')  # 10-Year Treasury
treasury_2y = fred.get_series('DGS2')   # 2-Year Treasury

# Get economic indicators
gdp = fred.get_series('GDP')  # Gross Domestic Product
unemployment = fred.get_series('UNRATE')  # Unemployment Rate
inflation = fred.get_series('CPIAUCSL')  # Consumer Price Index

# Get latest value
latest_vix = fred.get_series_latest_release('VIXCLS').iloc[-1]
latest_treasury = fred.get_series_latest_release('DGS10').iloc[-1]
```

## Rate Limiting & Caching

### Alpha Vantage Rate Limits

```python
class AlphaVantageRateLimiter:
    def __init__(self, max_calls_per_day=500):
        self.max_calls = max_calls_per_day
        self.calls_today = 0
        self.last_reset = datetime.now().date()
    
    def can_make_call(self):
        # Reset counter at midnight
        if datetime.now().date() > self.last_reset:
            self.calls_today = 0
            self.last_reset = datetime.now().date()
        
        return self.calls_today < self.max_calls
    
    def record_call(self):
        self.calls_today += 1
        logger.info(f"Alpha Vantage calls today: {self.calls_today}/{self.max_calls}")
        
        if self.calls_today >= self.max_calls * 0.9:
            logger.warning(f"Approaching Alpha Vantage daily limit: {self.calls_today}/{self.max_calls}")
```

### Intelligent Caching

```python
class DataCache:
    def __init__(self):
        self.cache = {}
        self.cache_duration = {
            'ohlcv': timedelta(hours=1),      # Yahoo Finance
            'indicators': timedelta(hours=4),  # Alpha Vantage
            'macro': timedelta(hours=24)       # FRED
        }
    
    def get(self, key, data_type='ohlcv'):
        if key in self.cache:
            data, timestamp = self.cache[key]
            age = datetime.now() - timestamp
            
            if age < self.cache_duration[data_type]:
                logger.info(f"Cache hit: {key} (age: {age})")
                return data
            else:
                logger.info(f"Cache expired: {key} (age: {age})")
        
        return None
    
    def set(self, key, data, data_type='ohlcv'):
        self.cache[key] = (data, datetime.now())
        logger.info(f"Cached: {key} (type: {data_type})")
```

## Data Quality & Validation

### Validation Checks

```python
def validate_market_data(data):
    """Validate market data quality."""
    
    checks = {
        'has_ohlcv': 'close' in data and len(data['close']) > 0,
        'sufficient_history': len(data['close']) >= 30,
        'no_missing_values': not data['close'].isna().any(),
        'reasonable_prices': (data['close'] > 0).all(),
        'reasonable_volume': (data['volume'] >= 0).all()
    }
    
    if not all(checks.values()):
        failed = [k for k, v in checks.items() if not v]
        raise ValueError(f"Data validation failed: {failed}")
    
    return True
```

## Cost Analysis

### Free Tier Limits

| Source | Free Calls | Sufficient For |
|--------|-----------|----------------|
| Yahoo Finance | Unlimited | ✅ All OHLCV needs |
| Alpha Vantage | 500/day | ✅ 50 symbols × 10 indicators |
| FRED | Unlimited | ✅ All macro data needs |

### Typical Daily Usage

For autonomous strategy generation (3 strategies, 2 symbols each):

```
Daily API Calls:
- Yahoo Finance: 6 calls (OHLCV for 6 symbols) - FREE
- Alpha Vantage: 18 calls (3 indicators × 6 symbols) - FREE (500 limit)
- FRED: 3 calls (VIX, treasury, GDP) - FREE (unlimited)

Total: 27 calls/day
Alpha Vantage usage: 5.4% of daily limit
```

### When to Upgrade

Consider paid tiers if:
- Generating > 50 strategies per day
- Trading > 100 symbols
- Need real-time data (< 15 min delay)
- Need more than 500 Alpha Vantage calls/day

**Recommendation**: Start with free tier, monitor usage, upgrade only if needed.

## Troubleshooting

### Common Issues

**Issue 1: Alpha Vantage API Key Invalid**
```
Error: Invalid API key
Solution: 
1. Check key in config file
2. Verify key at alphavantage.co
3. Ensure no extra spaces in key
```

**Issue 2: Rate Limit Exceeded**
```
Error: API call frequency exceeded
Solution:
1. Check calls_today counter
2. Wait until midnight UTC for reset
3. Enable caching to reduce calls
4. Fallback to local calculation
```

**Issue 3: FRED Series Not Found**
```
Error: Series 'VIXCLS' not found
Solution:
1. Verify series ID at fred.stlouisfed.org
2. Check if series is discontinued
3. Use alternative series
```

**Issue 4: Network Timeout**
```
Error: Connection timeout
Solution:
1. Check internet connection
2. Increase timeout in config
3. Fallback to cached data
4. Fallback to local calculation
```

## Testing

### Unit Tests

```python
def test_market_statistics_analyzer():
    """Test market statistics analyzer with all data sources."""
    
    analyzer = MarketStatisticsAnalyzer()
    
    # Test with Alpha Vantage enabled
    stats = analyzer.analyze_symbol('AAPL', period=90)
    assert 'volatility' in stats
    assert 'trend_strength' in stats
    assert 'vix' in stats
    
    # Test with Alpha Vantage disabled
    analyzer.alpha_vantage_enabled = False
    stats = analyzer.analyze_symbol('AAPL', period=90)
    assert 'volatility' in stats  # Should still work
    
    # Test with all APIs disabled
    analyzer.fred_enabled = False
    stats = analyzer.analyze_symbol('AAPL', period=90)
    assert 'volatility' in stats  # Should still work with Yahoo only
```

## Next Steps

1. ✅ Get free API keys (5 minutes)
2. ✅ Install dependencies (`pip install alpha-vantage fredapi`)
3. ✅ Add keys to config file
4. ✅ Implement MarketStatisticsAnalyzer (Task 9.9.1)
5. ✅ Test with AAPL, SPY, QQQ
6. ✅ Integrate into strategy generation (Task 9.9.2)

## Resources

- **Alpha Vantage Docs**: https://www.alphavantage.co/documentation/
- **FRED API Docs**: https://fred.stlouisfed.org/docs/api/
- **Alpha Vantage Python**: https://github.com/RomelTorres/alpha_vantage
- **FRED Python**: https://github.com/mortada/fredapi
- **Yahoo Finance Python**: https://github.com/ranaroussi/yfinance

## Support

If you encounter issues:
1. Check logs for specific error messages
2. Verify API keys are correct
3. Check rate limits haven't been exceeded
4. Test with fallback disabled to isolate issue
5. Refer to this guide's troubleshooting section
