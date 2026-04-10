# Hedge Fund Strategy Research 2025-2026 — DSL & Fundamental (AE) Templates

## Paste your research findings below

---
Implementable Algorithmic Trading System Design: Volatility Scaling, Fundamental Metrics, Technical Templates, and Multi-Asset Strategies for eToro
Executive Summary
Seven implementable enhancements can materially improve the performance of a 156-instrument autonomous trading system using only FMP and yfinance data, with volatility-scaled position sizing, cross-sectional ranking, and quality filtering delivering the highest expected impact.

The single most consequential upgrade is volatility-scaled position sizing, which nearly tripled CAGR for multi-asset time-series momentum (12.25% vs. 4.56% unscaled) across 38 futures contracts 

 and produces significant Sharpe ratio improvements in crypto 

, equities, and commodities alike. The optimal implementation uses asset-class-specific estimators — Yang-Zhang for equities and commodities, Parkinson for crypto, close-to-close for forex — with an EWMA decay factor of λ = 0.94 for most assets and a 126-day realized variance window validated by Barroso and Santa-Clara (2015) 

. This requires only price data already available through yfinance and integrates directly into existing position-sizing logic.

Two fundamental screening changes compound this gain. First, replacing fixed cutoffs (P/E < 18, ROE > 15%) with cross-sectional tercile ranking eliminates regime sensitivity — Asness's research confirms that relative value spreads, not absolute levels, drive returns 

 — and terciles (~32 stocks per bucket) are statistically preferable to quintiles for a ~97-stock universe 

. Second, applying the Piotroski F-Score as a quality gate (≥7) on value-ranked stocks adds approximately 7.5% annual alpha versus unfiltered value selection, using annual fiscal-year comparisons with quarterly rebalancing and a 4–6 month signal window 

. Capitalizing R&D (33% depreciation for tech, 20% for pharma) and 30% of SGA (15% depreciation) into an intangibles-adjusted P/B further corrects the ~12% earnings understatement that distorts traditional value metrics for knowledge-intensive firms 

.

For technical and multi-asset expansion, the most robust DSL templates include Keltner channel breakouts filtered by ADX > 25 for trend-following, Bollinger Band mean reversion gated by ADX < 25 for ranging markets, and cross-asset lead-lag signals — particularly BTC-to-altcoin momentum, which shows unidirectional Granger causality with consistent outperformance 

. Earnings transcript sentiment using the Loughran-McDonald dictionary with Q&A section overweighting (60/40 vs. prepared remarks) provides an orthogonal alpha source implementable through FMP's transcript endpoint 

. Additional multi-asset templates — forex carry sorted by rate differentials, commodity roll-yield capture in backwardation, and macro-conditioned ETF sector rotation — extend systematic coverage across the full instrument set with clear entry/exit rules and multi-year backtest support 

.

Introduction and System Context
This report addresses seven specific research areas for an autonomous algorithmic trading system operating on eToro across 156 instruments — approximately 97 stocks, 27 ETFs, 8 forex pairs, 5 indices, 8 commodities, and 11 crypto assets. The system relies exclusively on FMP (Financial Modeling Prep) API and yfinance for data, with DSL-based technical and fundamental strategy templates, regime-dependent factor weighting, walk-forward validation, and expectancy-based activation already operational. Each section below provides implementable formulas, parameter ranges, and evidence grounded in academic research and backtests, all achievable without Bloomberg, FactSet, or proprietary feeds.

Volatility-Scaled Position Sizing Across Asset Classes
Core Formula and Volatility Estimators. The fundamental position-sizing formula is $w_t = \sigma_{target} / \hat{\sigma}t$, where $\hat{\sigma}t$ is the ex-ante realized volatility estimate. Moskowitz, Ooi, and Pedersen (2012) applied approximately 40% target volatility across 58 futures contracts, ensuring that high-volatility assets do not dominate portfolio returns 

. The choice of volatility estimator should vary by asset class. The Yang-Zhang estimator, which combines overnight (close-to-open), open-to-close, and Rogers-Satchell components as $\sigma{YZ} = \sqrt{\sigma^2{co} + k \cdot \sigma^2_{oc} + (1-k) \cdot \sigma^2_{RS}}$ with $k = 0.34/(1.34 + T/(T-2))$, achieves up to 14 times the efficiency of close-to-close estimators and is preferred for equities and commodities where overnight gap risk is significant 

. The Parkinson estimator, based on high-low ranges, offers up to 5.2 times the efficiency of close-to-close and is suitable for crypto assets that trade 24/7 with minimal gaps 

. For forex, where base volatility is lower, the standard close-to-close estimator $\sigma_{cc} = \sqrt{(1/(T-1)) \times \sum (\ln(C_i/C_{i-1}))^2}$ annualized by $\sqrt{252}$ is adequate 

.

Optimal Lookback Windows. Barroso and Santa-Clara (2015) found that a 126-day (six-month) realized variance window effectively predicts momentum risk and nearly doubles the Sharpe ratio for momentum strategies 

. The RiskMetrics EWMA model uses $\sigma^2_t = \lambda \cdot \sigma^2_{t-1} + (1-\lambda) \cdot r^2_{t-1}$, with $\lambda = 0.94$ recommended for daily data and $\lambda = 0.97$ for monthly 

. For crypto, where volatility clustering is extreme, a shorter EWMA with $\lambda \approx 0.90$– $0.94$ is advisable; for forex, longer lookbacks ($\lambda = 0.97$ or 60-day windows) help avoid excessive position turnover.

Multi-Asset Evidence. The performance gains from volatility scaling are substantial and consistent across asset classes. Alpha Architect's backtest across 38 futures (22 commodities, 7 bonds, 9 equity indices) from 1998–2016 found that volatility-scaled time-series momentum (TSMOM) achieved a CAGR of 12.25% versus just 4.56% unscaled, with a −27.56% correlation to SPY 

. Without volatility scaling, TSMOM monthly alpha drops from 1.08% to 0.39% 

. For crypto specifically, Grobys et al. (2024) report that volatility-scaling produces "impressive payoffs" for crypto momentum both before and after factor risk adjustment, though power-law tail risk remains unchanged 

. Habeli, Barakchian, and Motavasseli (2025) confirm that volatility scaling increases Sharpe ratios for crypto momentum-based strategies, with effects strengthening over longer horizons 

. Moreira and Muir (2017) demonstrate that managed portfolios taking less risk when volatility is high produce large alphas and substantially increase Sharpe ratios across momentum, value, and market factors 

.

Impact of Volatility Scaling on Momentum Strategy Returns
Volatility Scaling Impact Across Asset Classes

Chart Explanation: This chart illustrates the dramatic improvement in annualized returns when volatility scaling is applied to momentum strategies. The multi-asset TSMOM figures (4.56% unscaled vs. 12.25% scaled) are directly from Alpha Architect's backtest 

. Crypto and commodity estimates reflect the directional magnitude of improvements documented in the academic literature 

.

Asset Class	Recommended Estimator	Lookback / EWMA λ	Key Consideration
Equities	Yang-Zhang 

126-day or EWMA λ=0.94 

Gap risk from overnight sessions
Crypto	Parkinson or Close-to-Close 

EWMA λ=0.90–0.94	24/7 trading, extreme vol clustering
Forex	Close-to-Close 

60-day or EWMA λ=0.97 

Low base volatility, avoid turnover
Commodities	Yang-Zhang 

126-day or EWMA λ=0.94 

Overnight jumps, inventory-driven spikes
Table: Recommended Volatility Estimators and Lookback Windows by Asset Class

Intangibles-Adjusted Value Metrics
R&D Capitalization via Perpetual Inventory Method. The standard approach builds a knowledge capital stock using $KC_t = R&D_t + (1 - \delta) \times KC_{t-1}$, where $\delta$ is the annual depreciation rate. Common academic schedules use $\delta \approx 33%$ (three-year useful life) for technology R&D and $\delta \approx 20%$ (five-year useful life) for pharmaceutical R&D 

. For organizational capital derived from SGA spending, Eisfeldt and Papanikolaou (2013) propose $OC_t = 0.3 \times SGA_t + (1 - 0.15) \times OC_{t-1}$, capitalizing 30% of SGA at a 15% depreciation rate 

. Both formulas require only income statement data (R&D expense, SGA expense) available through FMP, with the perpetual inventory initialized by setting $KC_0$ equal to the first available R&D expense divided by the sum of the depreciation rate and a reasonable growth rate.

Adjusted P/B Formula and Evidence. The intangibles-adjusted price-to-book ratio is computed as $\text{Adjusted P/B} = \text{Market Cap} / (\text{GAAP Book Value} + KC + OC)$. This adjustment matters because GAAP earnings are understated by approximately 12% due to the expensing rather than capitalizing of intangible investments 

. Lev and Srivastava (2019) argue that this systematic measurement error explains the apparent demise of value investing — unadjusted book values systematically understate intangible-heavy firms, causing the traditional value factor to misclassify growth-oriented companies with substantial knowledge capital 

. Eisfeldt, Kim, and Papanikolaou (2022) further confirm that intangible value is priced in the cross-section of returns 

. For your ~97-stock universe spanning mega-cap to mid-cap, applying sector-specific depreciation rates (33% for tech, 20% for pharma/biotech, 15% for consumer/industrial organizational capital) and computing adjusted P/B should meaningfully improve value stock identification, particularly for technology and healthcare names where intangible intensity is highest.

Cross-Sectional Ranking Versus Absolute Thresholds
Why Percentile Ranking Dominates. Your current fixed cutoffs (P/E < 18, ROE > 15%) are vulnerable to regime shifts. Cliff Asness of AQR emphasizes that what matters is the relative spread between cheap and expensive portfolios, not absolute valuation levels — the cheap-to-expensive P/B ratio varies substantially across regimes, typically ranging between about 4 and 10 

. Seeking Alpha's quantitative system explicitly uses cross-sectional sector-relative percentile grading rather than absolute cutoffs, comparing over 100 metrics for each stock against the same metrics for other stocks in its sector 

. O'Shaughnessy's backtest evidence shows that composite relative-value scores based on average rankings across multiple ratios "dramatically beat the market" 

. Walter, Weber, and Weiss (2023) further demonstrate that methodological decisions in portfolio sorts — including breakpoint definitions and number of buckets — create substantial "non-standard errors" in estimated return differentials, reinforcing that the choice between relative ranking and absolute cutoffs meaningfully affects measured alpha 

.

Optimal Bucket Count for ~97 Stocks. Cattaneo, Crump, Farrell, and Schaumburg (2020), published in the Review of Economics and Statistics, formalize optimal portfolio sorting and find that the optimal number of quantile portfolios scales with the number of available stocks — from about 10 portfolios for ~500 stocks to over 200 for ~8,000 stocks 

. For your universe of ~97 stocks, this framework indicates that quintile sorts (yielding only ~19 stocks per bucket) risk excessive estimation noise, since research suggests approximately 30 stocks are needed to diversify most firm-specific risk 

. Tercile sorts producing approximately 32 stocks per bucket are recommended for this universe size, with quartiles (~24 stocks) as an acceptable alternative if finer granularity is needed 

. The practical recommendation is to use cross-sectional percentile ranking within terciles, replacing your fixed P/E and ROE cutoffs with relative rankings that automatically adapt to shifting market valuations.

Piotroski F-Score Implementation and Signal Decay
The Nine Binary Criteria. Piotroski's original 2000 paper uses annual financial statements, comparing the most recent fiscal year to the prior fiscal year — not TTM or quarterly comparisons. The F-Score is the sum of nine binary signals (0 or 1) across three categories. Under Profitability: (1) F_ROA — net income before extraordinary items divided by beginning total assets is positive; (2) F_CFO — operating cash flow divided by beginning total assets is positive; (3) F_ΔROA — current ROA exceeds prior year ROA; (4) F_ACCRUAL — CFO exceeds ROA (cash flow exceeds accrual earnings). Under Leverage and Liquidity: (5) F_ΔLEVER — long-term debt to average total assets decreased year-over-year; (6) F_ΔLIQUID — current ratio increased year-over-year; (7) F_EQISS — no common equity issued in the prior year. Under Operating Efficiency: (8) F_ΔMARGIN — gross margin ratio increased year-over-year; (9) F_ΔTURN — asset turnover (sales divided by beginning total assets) increased year-over-year 

.

Performance as a Value Stock Filter. The F-Score is most powerful when used as a filter on top of value selection rather than as a standalone signal. Piotroski found that high F-Score (≥7) value stocks beat the market by 13.4% per year versus 5.9% for the full value quintile — a 7.5% annual improvement from the quality filter alone 

. Internationally, high-FSCORE firms outperform low-FSCORE firms by about 10% per year across both developed and emerging markets 

. A 23-year U.S. backtest (2000–2022) of low P/B combined with high F-Score using quarterly rebalancing beat the market by 5.8% annually 

.

Piotroski F-Score Value Stock Performance
F-Score Performance by Score Group

Chart Explanation: This chart shows the annualized excess returns for value stocks grouped by F-Score. High F-Score (≥7) value stocks dramatically outperform, generating 13.4% excess returns versus 5.9% for the mid-range group 

. The low F-Score group represents the short side of Piotroski's original long/short strategy.

Signal Decay and Rebalancing. Piotroski's original study used annual rebalancing four months after fiscal year-end to ensure data availability. The practical signal window is approximately 4–6 months after annual filings become available; beyond that, the information is largely priced in 

. However, the 2000–2022 backtest evidence suggests quarterly rebalancing improves results by capturing updated financial data more promptly, using a six-month delay on financial data to ensure only publicly available numbers are used 

. An important caveat: the long/short F-Score strategy produced negative returns over the 2011–2020 period 

, though the long-only filter on value stocks has continued to add value. For your system, implement F-Score as a quality gate (≥7) on value-ranked stocks with quarterly rebalancing, not as a standalone long/short signal.

DSL Technical Strategy Templates
Adaptive Trend-Following with Volatility Filters. The Keltner channel breakout provides a robust trend-following framework. Default parameters use a 20-period EMA center with upper and lower bands at ±2× ATR 

. The DSL template is: IF close > Keltner_upper(EMA=20, ATR_mult=2) AND ADX(14) > 25 THEN BUY; STOP = entry - 1.5×ATR(14). The ATR trailing stop at 1.5× ATR below entry adapts to market volatility across all asset classes 

. The ADX threshold of 25 serves as a critical trend-strength filter — when ADX exceeds 25, the market is trending and breakout strategies are appropriate 

. For equities, a shorter ATR period of 6 may be more responsive, while the standard 14-period works well for crypto, forex, and commodities 

.

Mean Reversion with Regime Conditioning. Mean reversion strategies should only activate in ranging markets. The DSL template is: IF close < BB_lower(20, 2) AND ADX(14) < 25 AND ATR_pct > min_threshold THEN BUY; EXIT = BB_middle(20). Bollinger Bands identify four volatility regimes, with low-volatility compression (narrow BandWidth) preceding breakouts and mean reversion working specifically in ranging conditions 

. The ADX cap below 25 ensures the strategy avoids shorting into strong bullish breakouts 

. A validated TradingView implementation trades price excursions outside Bollinger Bands back toward the moving average while filtering for ranging conditions using an ADX cap and minimum ATR percentage to avoid dead markets 

. Bollinger Bands are somewhat profitable for mean reversion in equities and work as a breakout indicator in gold 

.

Cross-Asset Lead-Lag Signals. Several lead-lag relationships have strong academic support. Hong, Torous, and Valkanov demonstrated that metal and petroleum industries lead the broad stock market by up to two months, with predictive ability correlated to the industry's propensity to forecast economic activity indicators such as industrial production growth 

. For BTC leading altcoins, a 2026 study in Asia-Pacific Financial Markets demonstrates unidirectional Granger causality from BTC to altcoins, with small-cap cryptos exhibiting significant delayed responses and lower liquidity associated with slower reactions; a lag trading strategy using BTC's preceding returns consistently outperformed buy-and-hold 

. Altcoins with over 90% correlation to BTC include Chainlink, Stellar, Litecoin, TRON, BNB, and Ethereum 

. Oil-to-energy-stock spillover is confirmed by studies showing significant return spillover effects among oil-related sectors 

, with unidirectional Granger causality from oil prices to energy stocks in both short and long runs 

. The DSL template for lead-lag is: IF leader_return(BTC, lookback=1h) > threshold AND follower_corr(ALT, BTC, 30d) > 0.70 THEN BUY follower; EXIT after lag_window.

Earnings Transcript Sentiment Scoring
Dictionary Selection: Loughran-McDonald Over Harvard IV. The choice of sentiment dictionary is critical. Loughran and McDonald (2011) found that almost three-fourths of words identified as negative by the widely used Harvard Dictionary are not typically negative in financial contexts — words like "tax," "cost," "capital," and "liability" are flagged as negative by Harvard IV but are neutral in finance 

. The Loughran-McDonald (LM) dictionary provides seven sentiment categories specifically calibrated for financial text: negative, positive, uncertainty, litigious, strong modal, weak modal, and constraining 

. Price et al. confirm that a context-specific dictionary like LM is more powerful than the Harvard IV-4 for predicting abnormal returns and trading volume from conference calls 

.

Scoring Method and Section Weighting. The Q&A section of earnings calls carries more informational value than prepared remarks. Matsumoto, Pronk, and Roelofsen (2011) found that discussion periods are relatively more informative than presentation periods, with this greater information content positively associated with analyst following 

. The University of Chicago Booth School notes that Q&A dialogue tends to be more reflexive and less scripted than prepared remarks, despite days of preparation from management 

. For negation handling, accounting for negation in financial lexicon construction improves balanced accuracy to approximately 75% in supervised settings 

. Sentiment from earnings calls generates alpha not explained by traditional risk factors, based on analysis covering 1.8 million earnings calls from 2010–2023 

.

FMP Implementation Pipeline. FMP's API returns full-text JSON transcripts with fields for symbol, year, period, date, and content 

. The recommended pipeline is: (1) pull the transcript via the earnings call transcript endpoint; (2) split content into prepared remarks versus Q&A by detecting analyst question patterns; (3) apply the LM dictionary with a negation window of two words; (4) compute a weighted score as $0.4 \times \text{prepared_sentiment} + 0.6 \times \text{QA_sentiment} $; (5) normalize cross-sectionally across your ~97-stock universe and generate long/short signals on extreme terciles. Your local Qwen 2.5 LLM can supplement the dictionary approach by classifying ambiguous passages, but the keyword-based LM scoring should serve as the primary signal given its transparency and backtestability.

Multi-Asset Strategy Templates
Forex Carry Trade. The canonical carry strategy sorts currencies by interest rate differential, going long high-rate and short low-rate currencies. Burnside et al. found that the carry trade yields a high Sharpe ratio 

, while Koijen, Moskowitz, Pedersen, and Vrugt (2018) extended carry as a unified factor across currencies, commodities, equities, and fixed income, with the global carry factor outperforming currency-only carry over 1983–2012 

. The DSL template is: rank G10 currencies by 3-month rate differential, go long the top 3, short the bottom 3, and rebalance monthly. A volatility regime filter should modulate exposure, as carry has higher stock market exposure and is mean-reverting in regimes of high FX volatility 

.

Commodity Roll Yield. Gorton, Hayashi, and Rouwenhorst demonstrated that excess returns to backwardation strategies stem from selection of commodities when inventories are low 

. Gorton and Rouwenhorst (2006) found that fully collateralized commodity futures offered equity-like Sharpe ratios over 1959–2004, with negative correlation to equity and bond returns 

. The DSL template is: measure roll yield as (front-month − second-month) / second-month; go long commodities in backwardation (positive roll yield), short those in contango; rebalance monthly.

ETF Sector Rotation with Macro Regime Conditioning. Research published in the Journal of Portfolio Management shows that sector rotation using low-frequency economic measures (yield curve slope, PMI) via ETF portfolios responds differently to the economy through alternative optimization methods 

. A 2026 study on the TSX 60 (2000–2025) confirms that different sectors exhibit varying performance across business cycles, suggesting potential for systematic alpha through tactical sector allocation 

. The DSL template is: define regimes by yield curve (10y−2y spread > 0 = expansion, < 0 = recession) and ISM PMI (> 50 = expansion); overweight cyclicals (XLY, XLI, XLF) in expansion and defensives (XLU, XLP, XLV) in contraction; rebalance quarterly.

Crypto Momentum with Volume Confirmation. A 20-day variable moving average strategy on cryptocurrencies (excluding Bitcoin) generates excess returns of approximately 8.76% per annum after controlling for market return 

. Cryptocurrency momentum is subject to severe crashes, but volatility-scaling risk management produces impressive payoffs 

. Volume-based early-stage momentum outperforms traditional momentum in 34 of 37 countries in equities, and the principle extends to crypto 

. The DSL template is: rank top-20 cryptos by 14-day return, filter for volume > 1.5× the 20-day average, hold the top 5 for 7 days, and apply 20-day trailing volatility scalar for position sizing.

Implementation Priorities and Recommendations
Given the existing infrastructure of walk-forward validation and expectancy-based activation, the highest-impact additions can be sequenced by implementation complexity and expected return improvement. Volatility-scaled position sizing should be the first priority, as it requires only price data already available through yfinance and delivers the single largest Sharpe ratio improvement across all asset classes — nearly tripling CAGR for multi-asset TSMOM 

. The second priority is replacing absolute fundamental thresholds with cross-sectional tercile ranking, which requires minimal code changes but substantially improves regime stability 

. Third, implementing the Piotroski F-Score as a quality gate (≥7) on value-ranked stocks adds approximately 7.5% annual alpha with quarterly rebalancing 

. Fourth, the intangibles-adjusted P/B metric using FMP income statement data addresses the systematic undervaluation of knowledge-intensive firms 

. Fifth, the DSL technical templates (Keltner breakout, Bollinger mean reversion, lead-lag signals) can be added incrementally to the existing template framework. Sixth, earnings sentiment scoring via the LM dictionary and FMP transcripts provides an orthogonal alpha source 

. Finally, the multi-asset templates (carry, roll yield, sector rotation, crypto momentum) extend coverage across your full 156-instrument universe. Each addition should be validated through your existing walk-forward framework before live deployment, with decay monitoring tracking signal degradation over time.

1
alphaarchitect.com

2
researchgate.net

3
papers.ssrn.com

4
etf.com

5
theglobeandmail.com

6
cxoadvisory.com

7
fergusonwellman.com

8
alphaarchitect.com

9
quant-investing.com

10
hudson-labs.com

11
researchgate.net

12
link.springer.com

13
papers.ssrn.com

14
researchgate.net

15
caia.org

16
researchgate.net

17
papers.ssrn.com

18
researchgate.net

19
portfoliooptimizer.io

20
researchgate.net

21
papers.ssrn.com

22
Wikipedia

23
help.seekingalpha.com

24
stockopedia.com

25
tidy-finance.org

26
direct.mit.edu

27
researchgate.net

28
validea.com

29
seekingalpha.com

30
blog.traderspost.io

31
quantifiedstrategies.com

32
quantifiedstrategies.com

33
fxempire.com

34
tradingview.com

35
tradingview.com

36
quantifiedstrategies.com

37
papers.ssrn.com

38
researchgate.net

39
frontiersin.org

40
papers.ssrn.com

41
sraf.nd.edu

42
papers.ssrn.com

43
chicagobooth.edu

44
link.springer.com

45
site.financialmodelingprep.com

46
returnstacked.com

47
researchgate.net

48
papers.ssrn.com

49
mdpi.com

50
researchgate.net

51
researchgate.net


