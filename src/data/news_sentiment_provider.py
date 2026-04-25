"""
News Sentiment Provider — Marketaux API client with DB-backed cache.

Design:
- Fetches news + pre-scored sentiment per ticker from Marketaux (free: 100 req/day)
- Stores rolling sentiment score in DB table `symbol_news_sentiment`
- TTL varies by context: 6h (earnings week), 24h (normal), 48h (weekend), 72h (quiet)
- Change detection: if no new articles since last fetch, extends TTL without API call
- Score = 0.0 (neutral) when no data — never blocks a trade

Sentiment score convention (stored in DB):
  -1.0 = very bearish
   0.0 = neutral (no data or balanced)
  +1.0 = very bullish

Marketaux returns sentiment_score on 0-1 scale (0.5 = neutral).
We convert: db_score = (marketaux_score - 0.5) * 2  →  range -1.0 to +1.0
"""

import logging
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import requests

logger = logging.getLogger(__name__)

# Marketaux API
_MARKETAUX_BASE = "https://api.marketaux.com/v1/news/all"
_ARTICLES_PER_REQUEST = 10  # more articles = more reliable average
_REQUEST_TIMEOUT = 10

# TTL rules (hours)
_TTL_EARNINGS_WEEK = 6
_TTL_NORMAL = 24
_TTL_WEEKEND = 48
_TTL_QUIET = 72   # symbol with very few articles

# Symbols that don't have news on Marketaux (forex, commodities, indices)
_NO_NEWS_SYMBOLS = {
    'EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'NZDUSD', 'EURGBP',
    'SPX500', 'NSDQ100', 'DJ30', 'UK100', 'GER40',
    'GOLD', 'SILVER', 'OIL', 'COPPER', 'NATGAS', 'PLATINUM', 'ALUMINUM', 'ZINC',
    'WEAT', 'DBA', 'UNG', 'USO', 'PALL',
}


class NewsSentimentProvider:
    """Marketaux news sentiment with DB-backed rolling cache."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self._requests_today = 0
        self._requests_reset_at = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        ) + timedelta(days=1)
        # Circuit breaker: if Marketaux returns 402 (monthly limit exhausted),
        # disable all fetches until midnight UTC to stop flooding warnings.log.
        self._api_disabled_until: datetime = datetime.utcnow().replace(
            hour=0, minute=0, second=0, microsecond=0
        )  # initialised to past — not disabled

    # ── Public API ────────────────────────────────────────────────────────

    def get_sentiment(self, symbol: str) -> float:
        """
        Get the current sentiment score for a symbol.

        Returns a value in [-1.0, +1.0]:
          +1.0 = very bullish news
           0.0 = neutral / no data
          -1.0 = very bearish news

        Always returns immediately from DB cache if fresh.
        Returns 0.0 if no data — never blocks a trade.
        """
        sym = symbol.upper().split(':')[0]
        if sym in _NO_NEWS_SYMBOLS:
            return 0.0

        cached = self._get_from_db(sym)
        if cached is not None:
            return cached

        # No data yet — return neutral, queue for background fetch
        return 0.0

    def fetch_and_store(self, symbol: str, force: bool = False) -> Optional[float]:
        """
        Fetch fresh sentiment from Marketaux and store in DB.

        Returns the new sentiment score, or None if fetch failed / rate limited.
        Called by the background sync — not at signal time.

        Args:
            symbol: Ticker symbol
            force: If True, bypass TTL check and always fetch
        """
        sym = symbol.upper().split(':')[0]
        if sym in _NO_NEWS_SYMBOLS:
            return None

        if not force and not self._needs_refresh(sym):
            return self._get_from_db(sym)

        if not self._check_rate_limit():
            logger.debug(f"[NewsSentiment] Rate limit reached for today, skipping {sym}")
            return None

        try:
            articles = self._fetch_from_marketaux(sym)
            self._requests_today += 1

            if not articles:
                # No articles found — store neutral with long TTL
                self._save_to_db(sym, 0.0, article_count=0, last_article_at=None, ttl_hours=_TTL_QUIET)
                logger.debug(f"[NewsSentiment] No articles for {sym} — stored neutral (TTL {_TTL_QUIET}h)")
                return 0.0

            # Compute weighted average sentiment
            # Marketaux sentiment_score: 0.0-1.0, 0.5 = neutral
            # Convert to -1.0 to +1.0: score = (raw - 0.5) * 2
            weighted_sum = 0.0
            weight_total = 0.0
            latest_published = None

            for article in articles:
                for entity in article.get("entities", []):
                    if entity.get("symbol", "").upper() != sym:
                        continue
                    raw = entity.get("sentiment_score")
                    match = entity.get("match_score", 1.0) or 1.0
                    if raw is None:
                        continue
                    converted = (raw - 0.5) * 2.0  # -1.0 to +1.0
                    weighted_sum += converted * match
                    weight_total += match

                pub = article.get("published_at")
                if pub:
                    try:
                        pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00")).replace(tzinfo=None)
                        if latest_published is None or pub_dt > latest_published:
                            latest_published = pub_dt
                    except Exception:
                        pass

            if weight_total == 0:
                score = 0.0
            else:
                score = max(-1.0, min(1.0, weighted_sum / weight_total))

            # Determine TTL
            ttl = self._compute_ttl(sym, len(articles))

            self._save_to_db(sym, score, article_count=len(articles),
                             last_article_at=latest_published, ttl_hours=ttl)

            label = "bullish" if score > 0.15 else "bearish" if score < -0.15 else "neutral"
            logger.info(
                f"[NewsSentiment] {sym}: score={score:+.3f} ({label}), "
                f"{len(articles)} articles, TTL={ttl}h"
            )
            return score

        except Exception as e:
            logger.warning(f"[NewsSentiment] Failed to fetch for {sym}: {e}")
            return None

    def needs_refresh(self, symbol: str) -> bool:
        """Check if a symbol needs a fresh fetch (public wrapper)."""
        return self._needs_refresh(symbol.upper().split(':')[0])

    def get_article_count(self, symbol: str) -> int:
        """Return the cached article count for a symbol (0 if unknown)."""
        sym = symbol.upper().split(':')[0]
        try:
            from src.models.database import get_database
            from sqlalchemy import text
            db = get_database()
            session = db.get_session()
            try:
                row = session.execute(text(
                    "SELECT article_count FROM symbol_news_sentiment WHERE symbol = :sym"
                ), {"sym": sym}).fetchone()
                return int(row[0]) if row and row[0] is not None else 0
            finally:
                session.close()
        except Exception:
            return 0

    def get_coverage_stats(self) -> Dict:
        """Return coverage statistics for the Data Management page."""
        try:
            from src.models.database import get_database
            db = get_database()
            session = db.get_session()
            try:
                from sqlalchemy import text
                result = session.execute(text(
                    "SELECT COUNT(*) as total, "
                    "SUM(CASE WHEN fetched_at > NOW() - INTERVAL '7 days' THEN 1 ELSE 0 END) as fresh "
                    "FROM symbol_news_sentiment"
                )).fetchone()
                return {
                    "total_cached": result[0] if result else 0,
                    "fresh_count": result[1] if result else 0,
                    "requests_today": self._requests_today,
                    "requests_remaining": max(0, 100 - self._requests_today),
                }
            finally:
                session.close()
        except Exception:
            return {"total_cached": 0, "fresh_count": 0, "requests_today": 0, "requests_remaining": 100}

    # ── Internal ──────────────────────────────────────────────────────────

    def _fetch_from_marketaux(self, symbol: str) -> List[Dict]:
        """Call Marketaux API and return raw article list."""
        # Circuit breaker: 402 means monthly quota exhausted — skip until midnight
        if datetime.utcnow() < self._api_disabled_until:
            raise ValueError("Marketaux API disabled (402 monthly limit) until midnight UTC")

        params = {
            "symbols": symbol,
            "filter_entities": "true",
            "language": "en",
            "limit": _ARTICLES_PER_REQUEST,
            "sort": "published_at",  # most recent first
            "api_token": self.api_key,
        }
        resp = requests.get(_MARKETAUX_BASE, params=params, timeout=_REQUEST_TIMEOUT)

        # 402 = monthly quota exhausted — disable until midnight to stop log spam
        if resp.status_code == 402:
            midnight_utc = (datetime.utcnow() + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            self._api_disabled_until = midnight_utc
            logger.warning(
                f"Marketaux 402 Payment Required — monthly quota exhausted. "
                f"News sentiment disabled until {midnight_utc.strftime('%Y-%m-%d %H:%M')} UTC."
            )
            raise ValueError("Marketaux 402: monthly quota exhausted")

        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            raise ValueError(f"Marketaux error: {data['error']}")

        return data.get("data", [])

    def _check_rate_limit(self) -> bool:
        """Return True if we can make another request today."""
        now = datetime.utcnow()
        if now >= self._requests_reset_at:
            self._requests_today = 0
            self._requests_reset_at = now.replace(
                hour=0, minute=0, second=0, microsecond=0
            ) + timedelta(days=1)
        return self._requests_today < 95  # Leave 5 buffer

    def _needs_refresh(self, symbol: str) -> bool:
        """Check if the DB record is stale or missing."""
        try:
            from src.models.database import get_database
            from sqlalchemy import text
            db = get_database()
            session = db.get_session()
            try:
                row = session.execute(text(
                    "SELECT fetched_at, ttl_hours FROM symbol_news_sentiment WHERE symbol = :sym"
                ), {"sym": symbol}).fetchone()
                if row is None:
                    return True
                fetched_at, ttl_hours = row
                if fetched_at is None:
                    return True
                age_hours = (datetime.utcnow() - fetched_at).total_seconds() / 3600
                return age_hours >= (ttl_hours or _TTL_NORMAL)
            finally:
                session.close()
        except Exception:
            return True

    def _get_from_db(self, symbol: str) -> Optional[float]:
        """Get cached sentiment score if fresh, else None."""
        try:
            from src.models.database import get_database
            from sqlalchemy import text
            db = get_database()
            session = db.get_session()
            try:
                row = session.execute(text(
                    "SELECT sentiment_score, fetched_at, ttl_hours "
                    "FROM symbol_news_sentiment WHERE symbol = :sym"
                ), {"sym": symbol}).fetchone()
                if row is None:
                    return None
                score, fetched_at, ttl_hours = row
                if fetched_at is None:
                    return None
                age_hours = (datetime.utcnow() - fetched_at).total_seconds() / 3600
                if age_hours >= (ttl_hours or _TTL_NORMAL):
                    return None  # Stale
                return float(score) if score is not None else 0.0
            finally:
                session.close()
        except Exception as e:
            logger.debug(f"[NewsSentiment] DB read error for {symbol}: {e}")
            return None

    def _save_to_db(self, symbol: str, score: float, article_count: int,
                    last_article_at: Optional[datetime], ttl_hours: int) -> None:
        """Upsert sentiment record into DB."""
        try:
            from src.models.database import get_database
            from sqlalchemy import text
            db = get_database()
            session = db.get_session()
            try:
                session.execute(text("""
                    INSERT INTO symbol_news_sentiment
                        (symbol, sentiment_score, article_count, last_article_at, fetched_at, ttl_hours)
                    VALUES
                        (:sym, :score, :count, :last_art, NOW(), :ttl)
                    ON CONFLICT (symbol) DO UPDATE SET
                        sentiment_score  = EXCLUDED.sentiment_score,
                        article_count    = EXCLUDED.article_count,
                        last_article_at  = EXCLUDED.last_article_at,
                        fetched_at       = EXCLUDED.fetched_at,
                        ttl_hours        = EXCLUDED.ttl_hours
                """), {
                    "sym": symbol,
                    "score": score,
                    "count": article_count,
                    "last_art": last_article_at,
                    "ttl": ttl_hours,
                })
                session.commit()
            except Exception as e:
                session.rollback()
                logger.warning(f"[NewsSentiment] DB write error for {symbol}: {e}")
            finally:
                session.close()
        except Exception as e:
            logger.debug(f"[NewsSentiment] DB access error: {e}")

    def _compute_ttl(self, symbol: str, article_count: int) -> int:
        """Determine TTL based on market context."""
        import pytz
        try:
            et_tz = pytz.timezone('US/Eastern')
            now_et = datetime.now(et_tz)
            is_weekend = now_et.weekday() >= 5
        except Exception:
            is_weekend = False

        if is_weekend:
            return _TTL_WEEKEND
        if article_count == 0:
            return _TTL_QUIET
        if article_count >= 8:
            # Very high news volume — likely earnings week, refresh more often
            return _TTL_EARNINGS_WEEK
        return _TTL_NORMAL


# ── Module-level singleton ────────────────────────────────────────────────

_provider_instance: Optional[NewsSentimentProvider] = None


def get_news_sentiment_provider() -> Optional[NewsSentimentProvider]:
    """Return the shared singleton, or None if not configured."""
    return _provider_instance


def init_news_sentiment_provider(api_key: str) -> NewsSentimentProvider:
    """Initialize the singleton. Called once at startup."""
    global _provider_instance
    _provider_instance = NewsSentimentProvider(api_key)
    logger.info("[NewsSentiment] Provider initialized")
    return _provider_instance
