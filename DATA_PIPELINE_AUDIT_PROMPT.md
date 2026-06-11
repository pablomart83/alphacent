# AlphaCent — DATA MANAGEMENT PIPELINE Forensic Audit

You are performing a full end-to-end forensic audit of the **data ingestion / price
pipeline** of AlphaCent, a LIVE autonomous trading platform on EC2 (Ubuntu,
PostgreSQL 16, Python 3.11/FastAPI, React/Vite). REAL MONEY trades on signals derived
from this data (~$1,300 real / ~$10K virtual live book). **If the data is wrong, every
downstream decision is wrong** — stale bars, gaps, look-ahead, wrong-source routing,
timezone/DST corruption, duplicate or mis-keyed rows, and silent fetch failures are
existential. The goal: find EVERY bug, misconfiguration, error, race, and
not-best-practice across all data sources, all intervals, all sync paths — exhaustively,
with evidence. This code was written incrementally by earlier models; treat nothing as
correct because it "looks done."

## GROUND RULES
1. Read `Session_Continuation.md` and `.kiro/steering/trading-system-context.md` FIRST
   (esp. the "Data Pipeline — Critical Rules", symbol-canonicalization, and
   price-freshness sections). They are the source of truth for state and permanent rules.
2. VERIFY, DON'T TRUST — triangulate. Prove every claim with a real DB query result, a
   log line, or an exact code path you read. State explicitly what you verified vs assumed.
   Past "fixes" have been dead code, half-wired, or based on a misdiagnosis (e.g. the
   ALUMINUM/ZINC FMP routing bug passed the Yahoo wire-form to the FMP SYMBOL_MAP and
   silently fell through to thin data). Treat the changelog as claims to falsify.
3. Think like a quant who has to TRADE on this data. "Would I take a real-money signal
   computed from this bar?" is the bar. A 1d bar that silently includes a provisional
   intraday "today" candle, or a 4h bar resampled across a DST boundary, is a bug even if
   nothing crashes.
4. PROPER ROOT-CAUSE FIXES ONLY — no patches, stopgaps, skip-flags, or hardcoded
   fallbacks that mask a real fetch failure (steering rule). A silent fallback that returns
   wrong/thin data instead of erroring is the most dangerous pattern here.
5. Live system. Deploy workflow is mandatory: edit LOCAL → getDiagnostics → scp →
   `systemctl restart alphacent` (if Python/config changed) → `curl -sf .../health` →
   git commit/push. Never edit on EC2. Sync `config/autonomous_trading.yaml` and
   `config/symbols.yaml` FROM EC2 before reading them only if the UI writes them
   (autonomous_trading.yaml is UI-owned; symbols.yaml is repo-owned — confirm).
6. Do NOT mass-delete/prune historical data or change retention without explicit
   confirmation — flag it. (Reading, EXPLAIN ANALYZE, and adding indexes are fine; a
   bulk DELETE or a `VACUUM FULL` lock on a live table is not, without a go-ahead.)
7. Do NOT run inline python on EC2 (`ssh ... 'python3 -c'`). Use DB queries and log reads.

## ACCESS
- SSH: `ssh -i ~/Downloads/alphacent-key.pem -o StrictHostKeyChecking=no ubuntu@34.252.61.149`
- DB:  `ssh ... 'sudo -u postgres psql alphacent -t -A -c "SQL"'`  (use `EXPLAIN (ANALYZE, BUFFERS)` to prove query cost)
- Logs (read errors.log FIRST): `logs/errors.log`, `logs/alphacent.log`, `logs/cycles/cycle_history.log`. Grep for the data-pipeline log lines:
  `"Syncing N positions"`, `"FMP"`, `"Yahoo"`, `"Binance"`, `"quick_price_update"`,
  `"_sync_price_data"`, `"resample"`, `"stale"`, `"AmbiguousTimeError"`, `"batch download"`.
- Config sync (only if needed): `scp -i ~/Downloads/alphacent-key.pem ubuntu@34.252.61.149:/home/ubuntu/alphacent/config/<file> config/<file>`

## KNOWN STATE (verify — do not assume still true; as of 2026-06-11)
- **`historical_price_cache` ≈ 2.5M rows**: 1h ≈ 1.66M (299 syms, back to 2023-09),
  4h ≈ 482K (300 syms, 2023-09), 1d ≈ 370K (305 syms, 2021-06). Sources: FMP 2.28M,
  Binance 186K, Yahoo 47K. Unique index `uq_historical_symbol_date_interval (symbol, date, interval)`.
  Plus `ix_/idx_` on symbol, date, (symbol,date DESC). **Open question to resolve: is the
  full 2.7yr of 1h history actually read by anything? WF window is 730d and ~1 live 1h
  strategy exists — quantify what the longest-lookback consumer needs, then a retention
  prune is likely (flag, don't delete).**
- **Three layers** (steering "Data Pipeline — Critical Rules"): full hourly sync
  `_sync_price_data` (1d + 1h, source of truth for EOD), quick update `_quick_price_update`
  (every 10 min, **1h bars only**, never 1d), eToro 60s position sync (current_price only).
  Verify these boundaries are actually honored in code (no path builds a provisional
  intraday 1d bar).
- **Sources & routing**: FMP `/stable/historical-price-eod/full` via `src/api/fmp_ohlc.py`
  (`SYMBOL_MAP`, `EXPLICIT_BLOCKED` for LME-metal intraday); Yahoo/yfinance via
  `_fetch_historical_from_yahoo_finance` (resamples 1h→4h); Binance via
  `src/api/binance_ohlc.py` (crypto). FIX-D mapped ALUMINUM→ALIUSD / ZINC→ZNUSD and fixed
  `market_data_manager` passing `normalized_symbol` (Yahoo wire) instead of `db_symbol`
  (display) into the FMP path. Re-verify that fix is deployed AND correct.
- **Timezone/DST**: `src/utils/yfinance_compat.py` — all yfinance calls must pass tz-aware
  UTC bounds; resample/iterate on tz-normalized data. DST boundaries previously crashed
  `pd.resample()` / `Timestamp.to_pydatetime()` with `AmbiguousTimeError`.
- **Symbol canonicalization** (steering): DB stores DISPLAY form (`BTC`, `EURUSD`);
  `to_etoro_wire_format` for eToro calls; `to_yahoo_ticker` for Yahoo. Two historical
  `normalize_symbol` functions exist — confirm the right one is used at each call site.
- `/data/quality` is now cached 60s in-process (perf fix 2026-06-11) — the full-scan
  aggregate is the reason; verify the cache is correct and the underlying query is the only
  heavy one.

## TRACE THE PIPELINE END-TO-END (the spine — prove each hop with evidence)
For a representative symbol of EACH asset class (stock, ETF, leveraged ETF, index,
commodity/LME metal, forex, crypto) and EACH interval (1d, 1h, 4h):
1. **Source selection** — which provider is chosen, and is it the RIGHT one? (LME metals
   → FMP not Yahoo; crypto → Binance; forex → ?; equities → ?). Is the symbol mapped
   correctly through `SYMBOL_MAP` / `to_yahoo_ticker` / `to_etoro_wire_format`?
2. **Fetch** — request bounds (tz-aware UTC?), pagination/limits, rate-limit handling
   (FMP Starter limits, FRED 429 backoff, Yahoo batch retry cap), error handling. Does a
   failed/partial fetch raise/queue-retry, or silently return thin/empty data?
3. **Parse/normalize** — OHLCV typing, timestamp tz, dedup, the 1h→4h resample (DST-safe?
   correct bar labeling/closed side? volume summed?), symbol written in display form.
4. **Persist** — `historical_price_cache` upsert: does it respect the unique constraint,
   avoid dup bars, set `source` and `fetched_at` correctly, and never overwrite a complete
   EOD 1d bar with a provisional intraday value?
5. **Freshness/staleness** — is "stale" computed market-hours-aware (weekends, holidays,
   half-days, LME EOD-only, 24/7 crypto)? Do `_quick_price_update` / `_sync_price_data` /
   the freshness-SLA / `data_quality_validator` agree, or do they use divergent predicates?
6. **Consumption** — what the strategy engine / backtest / WF actually read: warmup,
   look-ahead leakage (is the latest possibly-incomplete bar excluded?), interval matching
   (a 4h strategy must read 4h bars, not daily), and indicator correctness at boundaries.

For EACH hop: Is it correct? What happens on stale data, API failure, EMPTY result, a
single missing bar, a duplicate bar, a DST boundary, a market holiday, or an exception?
Is any failure swallowed silently (returns wrong data instead of erroring)? Does any
failure CASCADE (e.g. a poisoned shared DB session, or thin data → bad indicator → bad signal)?

## AUDIT CATEGORIES — investigate each exhaustively
1. **SOURCE ROUTING & SYMBOL MAPPING** — every asset class → correct provider; SYMBOL_MAP
   / wire / Yahoo-ticker conversions correct at every call site; no display-vs-wire mixups
   (the ALUMINUM bug class); `EXPLICIT_BLOCKED` correct; crypto via Binance not Yahoo.
2. **FETCH ROBUSTNESS** — rate limits + backoff (FMP, Yahoo, Binance, FRED, Marketaux);
   timeouts + bounded retries; partial-batch handling; **no silent fallback to thin/empty
   data** (the steering's #1 forbidden pattern). Circuit breakers on the data clients.
3. **INTERVAL CORRECTNESS** — 1d strictly EOD (no provisional today bar in 1d);
   `_quick_price_update` touches ONLY 1h; 1h→4h resample is DST-safe, correctly
   labeled/closed, volume aggregated; 4h strategies read 4h ATR/bars (not daily).
4. **TIMEZONE / DST** — every yfinance call passes tz-aware UTC; post-fetch tz normalize
   before resample/iterate; no `AmbiguousTimeError` paths; epoch/ISO handling consistent
   (the frontend `o.getTime` crash came from an epoch number — check the API emits
   consistent timestamp types).
5. **PERSISTENCE & INTEGRITY** — unique constraint enforced; no duplicate bars; `source`
   and `fetched_at` always set; upsert never corrupts a complete bar; no orphan/wrong-keyed
   (wire/Yahoo-form) rows polluting the cache (the `/data/quality` `_canon` collapse hints
   legacy residue exists — quantify it).
6. **FRESHNESS / STALENESS** — market-hours-aware staleness for every venue (equities
   RTH + holidays, LME EOD-only, forex 24×5, crypto 24×7); unify or at least reconcile the
   predicates (`_sync_price_data` gap test, freshness-SLA, `data_quality_validator`,
   Intel D1/D2). Look for the weekend/Monday false-stale class.
7. **SCHEDULING & CONCURRENCY** — the monitoring-loop cadences (60s sync, 10min quick,
   55min full, daily fundamentals); the 76–86 min loop-gap history; can two sync paths run
   concurrently and double-write or race? Shared-vs-isolated DB sessions on the data path
   (InFailedSqlTransaction risk). Cold-start (post-restart) first-cycle behavior.
8. **FUNDAMENTALS / SENTIMENT / MACRO** — FMP fundamentals coverage + staleness;
   Marketaux news sentiment TTL; FRED macro; insider endpoint 403/404 proxy fallback —
   are fallbacks honest (flagged) or silent?
9. **RETENTION & PERFORMANCE** — `historical_price_cache` 2.5M rows: what's actually read
   (longest lookback consumer) vs stored; prune candidate for old 1h (FLAG, don't delete);
   index coverage for the hot read paths and the `/data/quality` aggregate (EXPLAIN ANALYZE
   — currently a ~1.2s parallel seq scan, masked by a 60s cache); table bloat / VACUUM.
10. **OBSERVABILITY & SILENT FAILURE** — run `scripts/check_silent_excepts.py --ci` over
    `src/data` and `src/api/*ohlc*` and triage the dangerous ones (any swallow on a fetch/
    write/parse path). Is every sync's success/failure greppable in one `tail` (like the
    `TSL cycle:` line)? Are fetch failures counted/alerted or invisible?

## KEY FILES (read the actual source)
- `src/data/market_data_manager.py` — orchestrator: source selection, fetch, resample, cache.
- `src/api/fmp_ohlc.py` — FMP `/stable` EOD client + `SYMBOL_MAP` + `EXPLICIT_BLOCKED`.
- `src/api/binance_ohlc.py` — crypto OHLC.
- `src/utils/yfinance_compat.py` — tz-aware UTC + DST-safe resample helpers.
- `src/utils/symbol_mapper.py`, `src/utils/symbol_normalizer.py` — canonicalization (two `normalize_symbol`s).
- `src/data/data_quality_validator.py` + `/data/quality` endpoint (`src/api/routers/data_management.py`).
- `src/data/market_hours_manager.py` — market-hours / staleness awareness.
- `src/data/fmp_cache_warmer.py`, `src/data/fundamental_data_provider.py`, `src/data/news_sentiment_provider.py`.
- `src/core/monitoring_service.py` — `_sync_price_data`, `_quick_price_update`, schedule.
- Tables: `historical_price_cache`, `data_quality_reports`, `fundamental_data`, `symbol_news_sentiment`.

## OUTPUT FORMAT
Per finding: **Category (P0/P1/P2/Architecture/Opportunity) | Location (file:line or
subsystem) | What's wrong (precise ROOT CAUSE, not symptom) | Evidence (DB result / log
line / code path — actually run it) | Proper fix (root-cause) | Effort (honest:
agent wall-clock minutes-to-hours)**. Group by priority, P0 first, ordered by impact.
End with: (1) a sprint plan bundling fixes logically; (2) a watch list (not-yet-bugs);
(3) architectural recommendations (incl. the retention/prune question with the evidence
needed to decide it). If a proper fix needs research first (e.g. confirming the
longest-lookback consumer before pruning 1h history), say so and DO the research before
proposing. Be exhaustive. Read the actual source and the live DB/logs. Prove every claim.
