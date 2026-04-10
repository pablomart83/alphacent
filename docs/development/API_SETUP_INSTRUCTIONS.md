# API Setup Instructions

## ✅ What's Already Done

1. ✅ Dependencies installed (`alpha-vantage`, `fredapi`)
2. ✅ Config file updated with data sources section
3. ✅ Test script created to verify API keys

## 🔑 Get Your API Keys (5 minutes)

### Alpha Vantage (Free - 500 calls/day)

1. Go to: https://www.alphavantage.co/support/#api-key
2. Enter your email
3. Click "GET FREE API KEY"
4. Copy the API key (looks like: `ABC123XYZ456`)

### FRED (Free - Unlimited calls)

1. Go to: https://fred.stlouisfed.org/docs/api/api_key.html
2. Click "Request API Key"
3. Sign in or create account (free)
4. Copy the API key (looks like: `abc123def456ghi789`)

## 📝 Add Keys to Config

Open `config/autonomous_trading.yaml` and replace the placeholder keys:

```yaml
data_sources:
  alpha_vantage:
    enabled: true
    api_key: "YOUR_ALPHA_VANTAGE_KEY_HERE"  # ← Replace this
  
  fred:
    enabled: true
    api_key: "YOUR_FRED_KEY_HERE"  # ← Replace this
```

## 🧪 Test Your Keys

Run the test script:

```bash
source venv/bin/activate
python scripts/test_api_keys.py
```

You should see:
```
✅ Alpha Vantage API working! Retrieved X data points for AAPL
✅ FRED API working! Retrieved X VIX data points
✅ All API keys are working correctly!
```

## 📊 What You'll Get

### Alpha Vantage
- Pre-calculated technical indicators (RSI, MACD, SMA, EMA, etc.)
- Sector performance data
- 500 API calls/day (plenty for your use case)

### FRED
- VIX (market volatility/fear index)
- Treasury yields (10-year, 2-year)
- GDP, unemployment, inflation data
- Unlimited API calls

### Yahoo Finance (Already Working)
- OHLCV data (Open, High, Low, Close, Volume)
- Real-time price data
- Unlimited API calls

## 🎯 Daily Usage Estimate

For 3 strategies with 2 symbols each:
- Yahoo Finance: 6 calls (unlimited)
- Alpha Vantage: 18 calls (3.6% of daily limit)
- FRED: 3 calls (unlimited)

**Total: 27 calls/day** - well within free limits!

## 🚀 Next Steps

Once your API keys are working:

1. Implement Task 9.9.1 (Market Data Integration)
2. Run integration tests
3. Start generating strategies with enhanced market context

## 📚 Resources

- Alpha Vantage Docs: https://www.alphavantage.co/documentation/
- FRED API Docs: https://fred.stlouisfed.org/docs/api/fred/
- Market Data Guide: See `MARKET_DATA_SOURCES_GUIDE.md`

## ❓ Troubleshooting

### "Invalid API key" error
- Double-check you copied the entire key
- Make sure there are no extra spaces
- Verify the key is active (check your email)

### Rate limit errors
- Alpha Vantage: 500 calls/day limit
- Add caching to reduce API calls
- Use Yahoo Finance as fallback

### Connection errors
- Check your internet connection
- Verify firewall isn't blocking API requests
- Try again in a few minutes
