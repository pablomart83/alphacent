# Hedge Fund Fundamental Analysis Research — What Top Funds Do vs What We're Missing

## How Top Quant Funds Approach Fundamental Analysis

### The AQR / Two Sigma / D.E. Shaw Model: Multi-Factor Composite Scoring

The dominant approach at institutional quant funds isn't single-factor templates (like our "Earnings Momentum" or "Dividend Aristocrat"). It's multi-factor composite scoring where every stock gets a single score combining 4-6 orthogonal factors, and the portfolio is constructed from the top/bottom deciles.

AQR's approach ([$187B AUM as of 2025](https://www.ainvest.com/news/aqr-q4-2025-rebalancing-conviction-momentum-quality-factors-cyclical-bets-exit-2603/), content rephrased for compliance) blends:

1. **Value** — Price relative to fundamentals (P/E, P/B, P/S, EV/EBITDA, FCF yield)
2. **Momentum** — 12-month price return minus last month (avoids short-term reversal)
3. **Quality/Profitability** — Gross profitability (GP/Assets), ROE stability, low accruals
4. **Low Volatility** — Lower-beta stocks tend to outperform on risk-adjusted basis
5. **Size** — Small-cap premium (Fama-French SMB)

The key insight: **no single factor works all the time**. Value dominated 2025 while momentum led 2023-2024. The edge comes from combining uncorrelated factors so the portfolio always has exposure to whichever factor is working. ([Source: TMX](https://money.tmx.com/content-hub/value-momentum-content-hub/why-value-outpaced-momentum-2025-top-factor/), content rephrased)

### What We're Missing vs Institutional Approach

| What Institutions Do | What We Have | Gap |
|---|---|---|
| Multi-factor composite score per stock | Single-factor templates (one factor per template) | **Critical** — no factor diversification |
| Fama-French 5-factor decomposition | No factor attribution at all | **Critical** — can't measure what's driving returns |
| Accruals quality (Sloan ratio) | Not implemented | **High** — proven 10%+ annual alpha |
| Free cash flow yield | Not used in any template | **High** — better than P/E for valuation |
| Piotroski F-Score (9-point quality) | Partial (ROE + D/E only) | **High** — missing 7 of 9 criteria |
| Standardized Unexpected Earnings (SUE) | Raw earnings surprise % | **Medium** — SUE normalizes by historical volatility |
| Earnings call transcript NLP | Not implemented | **Medium** — FMP has the endpoint |
| Institutional ownership changes (13F) | Not implemented | **Medium** — FMP has the endpoint |
| Sector-neutral portfolio construction | No sector neutrality | **High** — sector bets dominate factor bets |
| Cross-sectional ranking (percentile) | Absolute thresholds (P/E < 18) | **Critical** — absolute thresholds are regime-dependent |

---

## Specific Factors We Should Implement

### 1. Accruals Quality (Sloan Ratio) — Proven Alpha, Easy to Compute

The accruals anomaly, documented by Sloan (1996), shows that companies with low accruals (earnings backed by cash flow) outperform those with high accruals (earnings from accounting adjustments) by roughly 10% annually. ([Source: Stockopedia](https://www.stockopedia.com/content/the-accrual-anomaly-why-investors-should-care-about-accruals-earnings-quality-63003), content rephrased)

**Formula**: `Accruals Ratio = (Net Income - Operating Cash Flow) / Total Assets`

- Low accruals (< 0) = earnings backed by real cash = GOOD
- High accruals (> 0.10) = earnings from accounting = BAD

**FMP data needed**: Income statement (net income) + Cash flow statement (operating cash flow) + Balance sheet (total assets). All available via FMP stable API.

**Why we don't have it**: Our fundamental filter checks profitability (EPS > 0) and growth (revenue growth > 0) but never checks earnings quality. A company can report positive EPS while burning cash — the accruals ratio catches this.

### 2. Free Cash Flow Yield — Better Than P/E

FCF Yield = Free Cash Flow / Market Cap. It's harder to manipulate than earnings and directly measures how much cash a business generates relative to its price.

**Formula**: `FCF Yield = (Operating Cash Flow - CapEx) / Market Cap`

**FMP data needed**: Cash flow statement (`operatingCashFlow`, `capitalExpenditure`) + Profile (`marketCap`). All available.

**Why it matters**: Our Relative Value template uses P/E only. P/E is easily distorted by one-time charges, depreciation methods, and tax strategies. FCF yield cuts through the noise.

### 3. Piotroski F-Score — 9-Point Quality Composite

The F-Score evaluates 9 binary criteria across profitability, leverage, and efficiency. Stocks scoring 8-9 historically outperform by 7.5% annually vs those scoring 0-1. ([Source: QuantifiedStrategies](https://www.quantifiedstrategies.com/piotroski-f-score-strategy/), content rephrased)

**The 9 criteria** (1 point each):
1. Positive net income ✅ (we check this)
2. Positive operating cash flow ❌ (we don't check)
3. ROA increasing year-over-year ❌
4. Cash flow > net income (quality) ❌ (this IS the accruals check)
5. Decreasing long-term debt ratio ❌
6. Increasing current ratio ❌
7. No new share issuance ✅ (we check dilution)
8. Increasing gross margin ❌
9. Increasing asset turnover ❌

**We currently check 2 of 9**. The missing 7 are all computable from FMP data (income statement, balance sheet, cash flow statement).

### 4. Standardized Unexpected Earnings (SUE) — Better Than Raw Surprise

Our Earnings Momentum template uses raw earnings surprise (actual - estimated / |estimated|). The institutional approach uses SUE, which normalizes by the historical standard deviation of surprises for that company.

**Formula**: `SUE = (Actual EPS - Expected EPS) / StdDev(historical surprises)`

A 5% surprise for a company that always beats by 4-6% is unremarkable (SUE ≈ 0.5). A 5% surprise for a company that usually hits estimates exactly is significant (SUE ≈ 3.0).

**FMP data needed**: Historical analyst estimates (already fetched via `/analyst-estimates`). We just need to compute the standard deviation of past surprises.

### 5. Earnings Call Transcript Sentiment — FMP Has This

FMP provides earnings call transcripts via `/stable/earning-call-transcript`. ([Source: FMP docs](https://intelligence.financialmodelingprep.com/developer/docs/stable/latest-transcripts))

Institutional funds use NLP to extract:
- Management tone shifts (more hedging language = bearish)
- Uncertainty words ("challenging", "headwinds", "uncertain")
- Forward guidance sentiment
- Q&A dynamics (defensive answers = red flag)

This could be implemented with a simple keyword-based sentiment scorer or an LLM call. We already have an LLM service configured (qwen2.5-coder).

### 6. Institutional Ownership Changes (13F) — Smart Money Tracking

FMP provides 13F filing data via `/stable/institutional-ownership`. ([Source: FMP docs](https://financialmodelingprep.com/datasets/form-13f))

Key signals:
- Increasing institutional ownership = smart money accumulating
- Decreasing institutional ownership = smart money exiting
- New positions from top-performing funds = high conviction signal

### 7. Cross-Sectional Ranking Instead of Absolute Thresholds

Our biggest structural gap: we use absolute thresholds (P/E < 18, ROE > 15%, revenue growth > 2%). Institutions use cross-sectional percentile rankings.

**Example**: Instead of "buy if P/E < 18", rank all stocks in the universe by P/E and buy the bottom 20%. This automatically adapts to market conditions — in a high-P/E market, the bottom 20% might be P/E 15-25, which is still relatively cheap.

This requires scoring all ~75 stock symbols in our universe simultaneously, not evaluating each in isolation.

---

## Recommended New Templates / Upgrades

### NEW: Multi-Factor Composite Score (replaces individual factor templates)

Instead of 13 separate AE templates, create ONE composite scoring system:

```
Composite Score = w1 * Value_Rank + w2 * Momentum_Rank + w3 * Quality_Rank + w4 * Growth_Rank

Where:
- Value_Rank = percentile rank of (FCF Yield + 1/PE + 1/PS) / 3
- Momentum_Rank = percentile rank of 12-month return minus 1-month return
- Quality_Rank = percentile rank of (Piotroski F-Score + inverse Accruals Ratio) / 2
- Growth_Rank = percentile rank of (Revenue Acceleration + Earnings Surprise SUE) / 2
```

LONG the top 20%, SHORT the bottom 20%. Rebalance monthly.

This is fundamentally how AQR, Two Sigma, and D.E. Shaw operate — not with individual factor templates but with composite scores.

### UPGRADE: Earnings Momentum → PEAD with SUE

Replace raw earnings surprise with SUE-based quantile sorting. Hold for 60 days post-announcement. Research shows this generates roughly 12.5% annual returns. ([Source: collinseow.com](https://collinseow.com/post-earnings/), content rephrased)

### UPGRADE: Quality Mean Reversion → Piotroski F-Score Filter

Expand from 2 checks (ROE, D/E) to full 9-point F-Score. Only enter when F-Score ≥ 7 AND price is technically oversold.

### NEW: Accruals Quality Long/Short

Long stocks with accruals ratio < -0.05 (cash-rich earnings), short stocks with accruals ratio > 0.10 (accounting-heavy earnings). Monthly rebalance.

### NEW: Earnings Call Sentiment

Use FMP transcript endpoint + simple NLP to score management tone. Enter LONG when sentiment is positive + earnings beat. Enter SHORT when sentiment is negative + earnings miss. The combination of quantitative surprise + qualitative tone is more powerful than either alone.

---

## FMP Endpoints We're Not Using But Should

| Endpoint | What It Provides | Use Case |
|---|---|---|
| `/stable/cash-flow-statement` | Operating CF, CapEx, FCF | Accruals ratio, FCF yield |
| `/stable/earning-call-transcript` | Full transcript text | NLP sentiment analysis |
| `/stable/institutional-ownership` | 13F holdings data | Smart money tracking |
| `/stable/financial-growth` | YoY growth rates pre-computed | F-Score criteria (ROA change, margin change) |
| `/stable/ratios` | Pre-computed financial ratios | Current ratio, asset turnover for F-Score |
| `/stable/key-metrics` (quarterly) | Already using | Need to extract more fields |

---

## Implementation Priority

### Phase 1: Low-Hanging Fruit (use existing FMP data better)
1. Add accruals ratio to fundamental filter (income stmt + cash flow stmt)
2. Add FCF yield to Relative Value template
3. Expand quality checks to full Piotroski F-Score
4. Replace raw earnings surprise with SUE
5. Switch from absolute thresholds to cross-sectional percentile ranking

### Phase 2: New Data Sources (new FMP endpoints)
6. Integrate cash flow statement endpoint
7. Integrate earnings call transcript endpoint + basic NLP
8. Integrate institutional ownership (13F) endpoint

### Phase 3: Architectural Shift
9. Build multi-factor composite scoring system
10. Replace individual AE templates with composite-score-based portfolio construction
11. Add sector-neutral portfolio construction
12. Add factor attribution reporting (decompose returns into value/momentum/quality/growth)

---

## Key Takeaway

Our current AE system treats fundamental analysis as a collection of independent signals (13 templates, each checking one thing). Top hedge funds treat it as a unified scoring system where every stock gets a composite rank across multiple orthogonal factors, and the portfolio is constructed from the extremes.

The single biggest improvement would be moving from "template per factor" to "composite score across all factors" — this is the architectural shift that separates retail-grade fundamental analysis from institutional-grade.
