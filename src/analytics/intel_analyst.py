"""Intel Analyst — comprehensive system health check library.

Runs ~50 checks across 8 categories (A-H), upserts findings into
system_findings table, and returns a summary. Manual trigger only.

Design: every check is a method returning Finding | None. Checks are
fail-quiet — an exception in one check never aborts the run. The run
orchestrator catches all exceptions and logs them.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


# ── Finding dataclass ─────────────────────────────────────────────────────────

@dataclass
class Finding:
    check_id: str
    key: str
    category: str
    severity: str          # P0 | P1 | P2 | opportunity
    title: str
    detail: str
    evidence: str
    recommended_action: str
    context_links: List[Dict] = field(default_factory=list)
    ask_kiro_prompt: str = ""


# ── Analyst ───────────────────────────────────────────────────────────────────

class IntelAnalyst:
    """Run all checks and upsert findings into system_findings."""

    def __init__(self, db, log_reader):
        self.db = db
        self.log_reader = log_reader

    # ═══════════════════════════════════════════════════════════════════════════
    # Orchestrator
    # ═══════════════════════════════════════════════════════════════════════════

    def run(self, lookback_days: int = 7) -> Dict[str, Any]:
        """Run all checks, upsert findings, return summary."""
        from sqlalchemy import text

        run_id = str(uuid4())
        t0 = time.time()
        session = self.db.get_session()

        try:
            session.execute(
                text(
                    "INSERT INTO intel_runs (id, started_at, lookback_days, status) "
                    "VALUES (:id, NOW(), :ld, 'running')"
                ),
                {"id": run_id, "ld": lookback_days},
            )
            session.commit()
        except Exception as exc:
            logger.warning(f"Intel: could not create run row: {exc}")
            try:
                session.rollback()
            except Exception:
                pass
        finally:
            session.close()

        # Collect all check methods
        checks = [
            self._check_a1_backtested_zero_signals,
            self._check_a2_pending_retirement_new_positions,
            self._check_a3_live_trade_count_zero,
            self._check_a4_wf_regime_luck,
            self._check_a5_paper_wr_divergence,
            self._check_a6_backtested_zero_paper_trades,
            self._check_a7_conviction_cluster,
            self._check_a8_zero_short_exposure,
            self._check_a9_template_family_negative,
            self._check_a10_overtrading,
            self._check_b1_order_failed_rate,
            self._check_b2_duplicate_orders,
            self._check_b3_slippage_null,
            self._check_b4_order_stuck_pending,
            self._check_b5_etoro_id_collision,
            self._check_b6_position_strategy_null,
            self._check_b8_order_size_below_minimum,
            self._check_c1_symbol_concentration,
            self._check_c2_portfolio_heat,
            self._check_c3_profitable_sl_at_entry,
            self._check_c4_zombie_positions,
            self._check_c7_position_no_stop_loss,
            self._check_d1_stale_1d_bars,
            self._check_d2_stale_4h_bars,
            self._check_d3_yahoo_delisted,
            self._check_d4_fmp_rate_limit,
            self._check_d7_duplicate_price_bars,
            self._check_d8_mqs_null_snapshots,
            self._check_e1_cycle_duration,
            self._check_e2_wf_cache_hit_rate,
            self._check_e3_low_proposals,
            self._check_e4_zero_short_wf_pass,
            self._check_e5_gate_loop,
            self._check_e8_concurrent_cycles,
            self._check_f1_new_errors,
            self._check_f2_sqlalchemy_failed_transaction,
            self._check_f3_postgres_idle_connections,
            self._check_f5_service_restart,
            self._check_f7_api_rate_limits,
            self._check_g1_strong_wf_never_activated,
            self._check_g2_underweighted_asset_class,
            self._check_g3_missed_alpha,
            self._check_g5_live_sharpe_divergence,
            self._check_g7_regime_template_loser,
            self._check_g9_extreme_degradation,
            self._check_h1_config_code_divergence,
            self._check_h3_graduation_min_trades_low,
            self._check_h4_paper_conviction_threshold,
        ]

        # Capture a DB-side cutoff BEFORE running checks. Any finding re-seen
        # this run gets last_seen = NOW() (strictly after this cutoff); anything
        # with last_seen < cutoff was NOT reproduced this run and is stale.
        _resolve_cutoff = None
        _cut_sess = self.db.get_session()
        try:
            _resolve_cutoff = _cut_sess.execute(text("SELECT NOW()")).scalar()
        except Exception:
            _resolve_cutoff = None
        finally:
            _cut_sess.close()

        findings: List[Finding] = []
        checks_failed = 0
        for check_fn in checks:
            try:
                result = check_fn(lookback_days)
                if result is None:
                    continue
                if isinstance(result, list):
                    findings.extend(result)
                else:
                    findings.append(result)
            except Exception as exc:
                checks_failed += 1
                logger.warning(f"Intel check {check_fn.__name__} failed: {exc}")

        # Upsert findings
        created = 0
        updated = 0
        for f in findings:
            try:
                c, u = self._upsert_finding(f, lookback_days)
                created += c
                updated += u
            except Exception as exc:
                logger.warning(f"Intel upsert failed for {f.check_id}/{f.key}: {exc}")

        # Auto-resolve findings that no longer reproduce.
        #
        # Without this the findings table only ever grows — a finding created
        # once stays status='open' forever even after the condition clears. That
        # was the root cause of the 244-open-P1 pileup and the stale E5/A1 noise:
        # the queue was a write-only log, not a current-state view.
        #
        # SAFETY: only auto-resolve when ALL checks ran cleanly this cycle. If any
        # check raised, its findings weren't re-upserted and we must NOT close them
        # (we don't know their current state). The cutoff is a DB timestamp taken
        # before the checks ran, so only findings re-seen this run survive.
        resolved = 0
        if checks_failed == 0 and _resolve_cutoff is not None:
            _res_sess = self.db.get_session()
            try:
                _res = _res_sess.execute(
                    text(
                        "UPDATE system_findings SET status='resolved', resolved_at=NOW(), "
                        "dismissed_reason='auto-resolved: condition no longer detected', "
                        "updated_at=NOW() "
                        "WHERE status='open' AND last_seen < :cutoff"
                    ),
                    {"cutoff": _resolve_cutoff},
                )
                _res_sess.commit()
                resolved = _res.rowcount or 0
                if resolved:
                    logger.info(f"Intel: auto-resolved {resolved} finding(s) that no longer reproduce")
            except Exception as exc:
                logger.warning(f"Intel: auto-resolve pass failed: {exc}")
                try:
                    _res_sess.rollback()
                except Exception:
                    pass
            finally:
                _res_sess.close()
        elif checks_failed > 0:
            logger.warning(
                f"Intel: skipping auto-resolve — {checks_failed} check(s) failed this run "
                f"(would risk closing findings whose state is unknown)"
            )

        duration = round(time.time() - t0, 2)

        # Update run row
        session2 = self.db.get_session()
        try:
            session2.execute(
                text(
                    "UPDATE intel_runs SET completed_at=NOW(), findings_created=:fc, "
                    "findings_updated=:fu, findings_total=:ft, duration_s=:ds, status='complete' "
                    "WHERE id=:id"
                ),
                {
                    "id": run_id,
                    "fc": created,
                    "fu": updated,
                    "ft": created + updated,
                    "ds": duration,
                },
            )
            session2.commit()
        except Exception as exc:
            logger.warning(f"Intel: could not update run row: {exc}")
            try:
                session2.rollback()
            except Exception:
                pass
        finally:
            session2.close()

        return {
            "run_id": run_id,
            "findings_created": created,
            "findings_updated": updated,
            "findings_count": created + updated,
            "duration_s": duration,
        }

    def _upsert_finding(self, f: Finding, lookback_days: int):
        """Insert or update a finding. Returns (created, updated) counts."""
        import json
        from sqlalchemy import text

        session = self.db.get_session()
        try:
            existing = session.execute(
                text(
                    "SELECT id, occurrence_count FROM system_findings "
                    "WHERE check_id=:cid AND key=:key"
                ),
                {"cid": f.check_id, "key": f.key},
            ).fetchone()

            if existing:
                session.execute(
                    text(
                        "UPDATE system_findings SET "
                        "title=:title, detail=:detail, evidence=:evidence, "
                        "recommended_action=:ra, ask_kiro_prompt=:akp, "
                        "context_links=:cl, severity=:sev, "
                        "last_seen=NOW(), occurrence_count=:occ, "
                        "lookback_days=:ld, updated_at=NOW() "
                        "WHERE check_id=:cid AND key=:key AND status='open'"
                    ),
                    {
                        "title": f.title,
                        "detail": f.detail,
                        "evidence": f.evidence,
                        "ra": f.recommended_action,
                        "akp": f.ask_kiro_prompt,
                        "cl": json.dumps(f.context_links),
                        "sev": f.severity,
                        "occ": (existing[1] or 0) + 1,
                        "ld": lookback_days,
                        "cid": f.check_id,
                        "key": f.key,
                    },
                )
                session.commit()
                return 0, 1
            else:
                session.execute(
                    text(
                        "INSERT INTO system_findings "
                        "(id, check_id, key, category, severity, title, detail, evidence, "
                        "recommended_action, context_links, ask_kiro_prompt, "
                        "first_seen, last_seen, occurrence_count, lookback_days, status, "
                        "created_at, updated_at) VALUES "
                        "(:id, :cid, :key, :cat, :sev, :title, :detail, :evidence, "
                        ":ra, :cl, :akp, NOW(), NOW(), 1, :ld, 'open', NOW(), NOW())"
                    ),
                    {
                        "id": str(uuid4()),
                        "cid": f.check_id,
                        "key": f.key,
                        "cat": f.category,
                        "sev": f.severity,
                        "title": f.title,
                        "detail": f.detail,
                        "evidence": f.evidence,
                        "ra": f.recommended_action,
                        "cl": json.dumps(f.context_links),
                        "akp": f.ask_kiro_prompt,
                        "ld": lookback_days,
                    },
                )
                session.commit()
                return 1, 0
        except Exception:
            try:
                session.rollback()
            except Exception:
                pass
            raise
        finally:
            session.close()

    # ═══════════════════════════════════════════════════════════════════════════
    # Category A — Strategy Health
    # ═══════════════════════════════════════════════════════════════════════════

    def _check_a1_backtested_zero_signals(self, lookback_days: int) -> Optional[List[Finding]]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            # Source-of-truth fix (Sprint D): previously this read
            # `strategies.performance->>'last_signal_at'`, a key that is NEVER written
            # to the performance JSON (it only ever holds avg_loss/sharpe/win_rate/etc.).
            # As a result EVERY aged BACKTESTED strategy was flagged "0 signals" — a
            # 100% false positive (verified: 188/300 BACKTESTED strategies emitted
            # signals in the last 7d; all 171 previously-flagged had submitted orders).
            # The real signal history lives in signal_decisions (stage='signal_emitted'),
            # the same source the /strategies API uses. Read from there.
            rows = session.execute(text("""
                SELECT s.id, s.name, s.activated_at, ls.last_signal_at
                FROM strategies s
                LEFT JOIN (
                    SELECT strategy_id, MAX(timestamp) AS last_signal_at
                    FROM signal_decisions
                    WHERE stage = 'signal_emitted'
                    GROUP BY strategy_id
                ) ls ON ls.strategy_id = s.id
                WHERE s.status = 'BACKTESTED'
                AND s.activated_at < NOW() - INTERVAL '3 days'
                AND (
                    ls.last_signal_at IS NULL
                    OR ls.last_signal_at < NOW() - INTERVAL '3 days'
                )
            """)).fetchall()
        finally:
            session.close()

        if not rows:
            return None

        findings = []
        for row in rows:
            days_since = (datetime.now() - row[2]).days if row[2] else "?"
            last_sig = row[3].isoformat() if row[3] else "never"
            evidence = f"Strategy: {row[1]}\nActivated: {days_since}d ago\nLast signal_emitted: {last_sig}"
            findings.append(Finding(
                check_id="A1",
                key=f"strategy:{row[0]}",
                category="A",
                # P2, not P1: a BACKTESTED (RESEARCH-stage) strategy that is idle for
                # 3+ days is research-pipeline hygiene, not a live-capital risk. Many
                # are simply daily trend strategies that fire infrequently — not broken.
                # Auto-resolution closes these once the strategy signals again.
                severity="P2",
                title=f"A1: {row[1]} — BACKTESTED {days_since}d, no signal in 3d+",
                detail="BACKTESTED strategy has not emitted a signal in the last 3+ days (per signal_decisions). Often a low-frequency daily strategy; investigate the entry conditions only if persistently idle across many cycles.",
                evidence=evidence,
                recommended_action="Check signal_decisions / strategy_engine logs for this strategy. If entry conditions never fire for current market data across many cycles, consider retiring or adjusting template parameters.",
                context_links=[{"label": "Guard / Audit", "url": "/guard/audit"}],
                ask_kiro_prompt=f'Intel finding [A1]: "{row[1]} — BACKTESTED {days_since}d, no signal in 3d+."\n\nEvidence: {evidence}\n\nRecommended action: Check signal_decisions for this strategy. Investigate only if persistently idle.',
            ))
        return findings if findings else None

    def _check_a2_pending_retirement_new_positions(self, lookback_days: int) -> Optional[List[Finding]]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            # FIX: Only flag positions opened AFTER the pending_retirement flag was set.
            # Previously used p.opened_at > NOW() - lookback_days, which falsely flagged
            # pre-existing positions that were legitimately opened before the strategy was
            # flagged for retirement. Now compares opened_at vs pending_retirement_at.
            rows = session.execute(text(f"""
                SELECT s.id, s.name, COUNT(p.id) as new_positions
                FROM strategies s
                JOIN positions p ON p.strategy_id = s.id
                WHERE s.strategy_metadata->>'pending_retirement' = 'true'
                AND p.opened_at > NOW() - INTERVAL '{lookback_days} days'
                AND p.closed_at IS NULL
                AND (
                    s.strategy_metadata->>'pending_retirement_at' IS NULL
                    OR p.opened_at > (s.strategy_metadata->>'pending_retirement_at')::timestamp
                )
                GROUP BY s.id, s.name HAVING COUNT(p.id) > 0
            """)).fetchall()
        finally:
            session.close()

        if not rows:
            return None

        findings = []
        for row in rows:
            evidence = f"Strategy: {row[1]}\nNew positions opened AFTER pending_retirement was set: {row[2]}"
            findings.append(Finding(
                check_id="A2",
                key=f"strategy:{row[0]}",
                category="A",
                severity="P0",
                title=f"A2: {row[1]} — pending_retirement but still opening positions",
                detail="Signal generation is not skipping pending_retirement strategies. New positions are being opened on a strategy marked for retirement.",
                evidence=evidence,
                recommended_action="Check trading_scheduler.py — add filter: skip strategies where strategy_metadata->>'pending_retirement' = 'true'.",
                context_links=[{"label": "Strategies", "url": "/strategies"}],
                ask_kiro_prompt=f'Intel finding [A2]: "{row[1]} — pending_retirement but still opening {row[2]} new positions."\n\nEvidence: {evidence}\n\nRecommended action: Check trading_scheduler.py — add filter to skip pending_retirement strategies.',
            ))
        return findings if findings else None

    def _check_a3_live_trade_count_zero(self, lookback_days: int) -> Optional[List[Finding]]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            rows = session.execute(text("""
                SELECT s.id, s.name, s.live_trade_count, COUNT(p.id) as closed_count
                FROM strategies s JOIN positions p ON p.strategy_id = s.id
                WHERE p.closed_at IS NOT NULL AND s.live_trade_count = 0
                GROUP BY s.id, s.name, s.live_trade_count HAVING COUNT(p.id) > 10
            """)).fetchall()
        finally:
            session.close()

        if not rows:
            return None

        findings = []
        for row in rows:
            evidence = f"Strategy: {row[1]}\nClosed positions: {row[3]}\nlive_trade_count: {row[2]}"
            findings.append(Finding(
                check_id="A3",
                key=f"strategy:{row[0]}",
                category="A",
                severity="P1",
                title=f"A3: {row[1]} — live_trade_count=0 after {row[3]} closed positions",
                detail="live_trade_count is not being incremented on async fills. Trade count metrics are wrong.",
                evidence=evidence,
                recommended_action="Check order_monitor.check_submitted_orders fill handler — add live_trade_count increment call there.",
                context_links=[{"label": "Strategies", "url": "/strategies"}],
                ask_kiro_prompt=f'Intel finding [A3]: "{row[1]} — live_trade_count=0 after {row[3]} closed positions."\n\nEvidence: {evidence}\n\nRecommended action: Check order_monitor fill handler for live_trade_count increment.',
            ))
        return findings if findings else None

    def _check_a4_wf_regime_luck(self, lookback_days: int) -> Optional[List[Finding]]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            rows = session.execute(text("""
                SELECT id, name,
                       (strategy_metadata->>'wf_test_sharpe')::float as test_s,
                       (strategy_metadata->>'wf_train_sharpe')::float as train_s,
                       (backtest_results->>'total_trades')::int as trades
                FROM strategies WHERE status IN ('BACKTESTED','PAPER')
                AND (strategy_metadata->>'wf_test_sharpe') IS NOT NULL
                AND (strategy_metadata->>'wf_train_sharpe') IS NOT NULL
                AND (strategy_metadata->>'wf_train_sharpe')::float > 0
                AND (strategy_metadata->>'wf_test_sharpe')::float /
                    (strategy_metadata->>'wf_train_sharpe')::float > 3
                AND COALESCE((backtest_results->>'total_trades')::int, 0) < 8
            """)).fetchall()
        finally:
            session.close()

        if not rows:
            return None

        findings = []
        for row in rows:
            ratio = round(row[2] / row[3], 1) if row[3] and row[3] > 0 else "?"
            evidence = f"Strategy: {row[1]}\nWF test Sharpe: {row[2]:.2f}\nWF train Sharpe: {row[3]:.2f}\nRatio: {ratio}x\nTrades: {row[4]}"
            findings.append(Finding(
                check_id="A4",
                key=f"strategy:{row[0]}",
                category="A",
                severity="P1",
                title=f"A4: {row[1]} — WF test/train ratio {ratio}x with only {row[4]} trades (regime luck)",
                detail="High test/train Sharpe ratio with low trade count indicates regime luck rather than genuine edge. The strategy likely captured a single favorable period.",
                evidence=evidence,
                recommended_action="Consider retiring or requiring re-validation with stricter WF thresholds. Add consistency gate: (test_sharpe - train_sharpe) ≤ 1.5.",
                context_links=[{"label": "Strategies", "url": "/strategies"}],
                ask_kiro_prompt=f'Intel finding [A4]: "{row[1]} — WF test/train ratio {ratio}x with {row[4]} trades (regime luck)."\n\nEvidence: {evidence}\n\nRecommended action: Consider retiring or requiring re-validation.',
            ))
        return findings if findings else None

    def _check_a5_paper_wr_divergence(self, lookback_days: int) -> Optional[List[Finding]]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            rows = session.execute(text("""
                SELECT id, name,
                       (performance->>'paper_win_rate')::float as paper_wr,
                       (backtest_results->>'win_rate')::float as wf_wr,
                       (performance->>'paper_trades')::int as paper_trades
                FROM strategies
                WHERE COALESCE((performance->>'paper_trades')::int, 0) >= 10
                AND (performance->>'paper_win_rate') IS NOT NULL
                AND (backtest_results->>'win_rate') IS NOT NULL
                AND ABS((performance->>'paper_win_rate')::float -
                        (backtest_results->>'win_rate')::float) > 0.25
            """)).fetchall()
        finally:
            session.close()

        if not rows:
            return None

        findings = []
        for row in rows:
            gap = round(abs(row[2] - row[3]) * 100, 1)
            evidence = f"Strategy: {row[1]}\nWF win rate: {row[3]*100:.1f}%\nPaper win rate: {row[2]*100:.1f}%\nGap: {gap}pp\nPaper trades: {row[4]}"
            findings.append(Finding(
                check_id="A5",
                key=f"strategy:{row[0]}",
                category="A",
                severity="P1",
                title=f"A5: {row[1]} — paper WR {row[2]*100:.0f}% vs WF {row[3]*100:.0f}% ({gap}pp gap)",
                detail="Paper win rate diverges significantly from WF win rate after 10+ trades. Edge is not translating from backtest to live paper trading.",
                evidence=evidence,
                recommended_action="Check if market regime has changed since WF period, or if entry conditions are being triggered on different bar types than backtested.",
                context_links=[{"label": "Research / Attribution", "url": "/research/attribution"}],
                ask_kiro_prompt=f'Intel finding [A5]: "{row[1]} — paper WR {row[2]*100:.0f}% vs WF {row[3]*100:.0f}% ({gap}pp gap after {row[4]} trades)."\n\nEvidence: {evidence}\n\nRecommended action: Investigate edge degradation.',
            ))
        return findings if findings else None

    def _check_a6_backtested_zero_paper_trades(self, lookback_days: int) -> Optional[List[Finding]]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            # Only flag strategies that have signals but no paper trades.
            # Strategies with 0 signals are already covered by A1 — suppress A6
            # for those to avoid duplicate findings on the same strategy.
            #
            # Source-of-truth fix (Sprint D): previously this gated on
            # `performance->>'last_signal_at' IS NOT NULL` and `performance->>'paper_trades'`,
            # but NEITHER key is ever written to the performance JSON, so the
            # `IS NOT NULL` condition was never true and A6 NEVER fired (a dead
            # detector — a false negative). Signals live in signal_decisions
            # (stage='signal_emitted') and completed paper trades live in
            # trade_journal (account_type='demo') — read from those.
            rows = session.execute(text("""
                SELECT s.id, s.name, s.activated_at
                FROM strategies s
                JOIN (
                    SELECT strategy_id, MAX(timestamp) AS last_signal_at
                    FROM signal_decisions
                    WHERE stage = 'signal_emitted'
                    GROUP BY strategy_id
                ) ls ON ls.strategy_id = s.id
                LEFT JOIN (
                    SELECT strategy_id, COUNT(*) AS n
                    FROM trade_journal
                    WHERE account_type = 'demo'
                    GROUP BY strategy_id
                ) tj ON tj.strategy_id = s.id
                WHERE s.status = 'BACKTESTED'
                AND s.activated_at < NOW() - INTERVAL '7 days'
                AND COALESCE(tj.n, 0) = 0
                AND ls.last_signal_at > NOW() - INTERVAL '7 days'
            """)).fetchall()
        finally:
            session.close()

        if not rows:
            return None

        findings = []
        for row in rows:
            days_since = (datetime.now() - row[2]).days if row[2] else "?"
            evidence = f"Strategy: {row[1]}\nActivated: {days_since}d ago\nPaper trades: 0\nNote: signals ARE firing but not converting to trades"
            findings.append(Finding(
                check_id="A6",
                key=f"strategy:{row[0]}",
                category="A",
                severity="P1",
                title=f"A6: {row[1]} — BACKTESTED {days_since}d with 0 paper trades (signals firing)",
                detail="Strategy is generating signals but none are converting to paper trades. Conviction threshold may be too high, or signals are being blocked by a gate after passing conviction.",
                evidence=evidence,
                recommended_action="Check signal_decisions for this strategy_id — look for filter:conviction rejections or gate_blocked decisions.",
                context_links=[{"label": "Guard / Audit", "url": "/guard/audit"}],
                ask_kiro_prompt=f'Intel finding [A6]: "{row[1]} — BACKTESTED {days_since}d with 0 paper trades (signals firing)."\n\nEvidence: {evidence}\n\nRecommended action: Check signal_decisions for conviction rejections or gate blocks.',
            ))
        return findings if findings else None

    def _check_a7_conviction_cluster(self, lookback_days: int) -> Optional[Finding]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            row = session.execute(text(f"""
                SELECT COUNT(DISTINCT strategy_id) as strategies,
                       COUNT(*) as rejections,
                       (SELECT COUNT(*) FROM conviction_score_logs
                        WHERE passed_threshold = false
                        AND timestamp > NOW() - INTERVAL '{lookback_days} days') as total_rejections
                FROM conviction_score_logs
                WHERE conviction_score BETWEEN 65 AND 69
                AND passed_threshold = false
                AND timestamp > NOW() - INTERVAL '{lookback_days} days'
            """)).fetchone()
        finally:
            session.close()

        # Only flag if ≥5 distinct strategies are stuck in this band
        if not row or (row[0] or 0) < 5:
            return None

        pct = round(row[1] / row[2] * 100, 1) if row[2] and row[2] > 0 else 0
        evidence = f"Distinct strategies scoring 65-69: {row[0]}\nTotal rejections in band: {row[1]}\nTotal rejections: {row[2]}\nBand share: {pct}%"
        return Finding(
            check_id="A7",
            key="conviction_threshold_calibration",
            category="A",
            severity="P1",
            title=f"A7: {row[0]} distinct strategies scoring 65-69 (just below threshold)",
            detail="Multiple strategies are consistently scoring just below the conviction threshold. This may indicate the threshold is miscalibrated or the scoring denominator is too high for certain asset classes.",
            evidence=evidence,
            recommended_action="Review conviction scorer calibration — particularly normalization denominator and asset-class effective maximums.",
            context_links=[{"label": "Research / Attribution", "url": "/research/attribution"}],
            ask_kiro_prompt=f'Intel finding [A7]: "{row[0]} distinct strategies scoring 65-69 (just below threshold)."\n\nEvidence: {evidence}\n\nRecommended action: Review conviction scorer calibration.',
        )

    def _check_a8_zero_short_exposure(self, lookback_days: int) -> Optional[Finding]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            row = session.execute(text("""
                SELECT COUNT(*) FROM positions
                WHERE side = 'SHORT' AND closed_at IS NULL AND account_type = 'demo'
            """)).fetchone()
        finally:
            session.close()

        if not row or (row[0] or 0) > 0:
            return None

        evidence = "Current open SHORT positions (demo): 0"
        return Finding(
            check_id="A8",
            key="short_exposure_zero",
            category="A",
            severity="P1",
            title="A8: 0% short exposure — directional diversity violated",
            detail="No open SHORT positions in demo account. Directional diversity requirement (min 3% short in trending_up_strong) is violated.",
            evidence=evidence,
            recommended_action="Check: (1) SHORT strategies in BACKTESTED status with 0 signals, (2) conviction scores for SHORT strategies, (3) C3 trend-consistency gate blocking all SHORTs.",
            context_links=[{"label": "Book / Positions", "url": "/book"}, {"label": "Guard / Gates", "url": "/guard/gates"}],
            ask_kiro_prompt='Intel finding [A8]: "0% short exposure — directional diversity violated."\n\nEvidence: No open SHORT positions in demo account.\n\nRecommended action: Check SHORT strategy signals and conviction scores.',
        )

    def _check_a9_template_family_negative(self, lookback_days: int) -> Optional[List[Finding]]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            rows = session.execute(text("""
                SELECT strategy_metadata->>'template_name' as tname,
                       COUNT(*) as count,
                       SUM(COALESCE((performance->>'paper_pnl')::float, 0)) as total_pnl
                FROM strategies WHERE status IN ('BACKTESTED','PAPER')
                AND COALESCE((performance->>'paper_trades')::int, 0) > 0
                AND strategy_metadata->>'template_name' IS NOT NULL
                GROUP BY tname HAVING COUNT(*) > 5
                AND SUM(COALESCE((performance->>'paper_pnl')::float, 0)) < 0
            """)).fetchall()
        finally:
            session.close()

        if not rows:
            return None

        findings = []
        for row in rows:
            evidence = f"Template: {row[0]}\nStrategy count: {row[1]}\nTotal paper P&L: ${row[2]:.2f}"
            findings.append(Finding(
                check_id="A9",
                key=f"template:{row[0]}",
                category="A",
                severity="P2",
                title=f"A9: Template '{row[0]}' — {row[1]} strategies all net negative (${row[2]:.0f})",
                detail="Template family is systematically losing across all strategies. May indicate a structural flaw in entry/exit conditions.",
                evidence=evidence,
                recommended_action="Consider disabling template or reviewing entry/exit conditions for structural flaw.",
                context_links=[{"label": "Strategies", "url": "/strategies"}],
                ask_kiro_prompt=f'Intel finding [A9]: "Template \'{row[0]}\' — {row[1]} strategies all net negative (${row[2]:.0f})."\n\nEvidence: {evidence}\n\nRecommended action: Review template for structural flaw.',
            ))
        return findings if findings else None

    def _check_a10_overtrading(self, lookback_days: int) -> Optional[List[Finding]]:
        """Flag strategies where orders are being submitted at an anomalous rate.

        Signals firing repeatedly is expected (quick-update runs every 10min).
        What matters is whether orders are actually being submitted — that's
        the real overtrading signal. A 1D strategy should submit at most 1
        order per symbol per day. A 4H strategy at most 6.

        FIX: Only count ENTRY orders. Exit/close orders are not overtrading —
        they are expected and can happen multiple times per day as positions
        are closed by TSL, zombie exit, time-based exit etc.
        """
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            rows = session.execute(text("""
                SELECT sd.strategy_id, s.name,
                       COUNT(DISTINCT (sd.symbol, DATE(sd.timestamp))) as symbol_days,
                       COUNT(*) as total_orders,
                       COUNT(*) / NULLIF(COUNT(DISTINCT (sd.symbol, DATE(sd.timestamp))), 0) as orders_per_symbol_day,
                       COALESCE(s.strategy_metadata->>'interval', '1d') as interval
                FROM signal_decisions sd
                LEFT JOIN strategies s ON s.id = sd.strategy_id
                WHERE sd.stage = 'order_submitted'
                AND sd.timestamp > NOW() - INTERVAL '24 hours'
                AND COALESCE(sd.decision_metadata->>'order_action', 'entry') = 'entry'
                GROUP BY sd.strategy_id, s.name, s.strategy_metadata->>'interval'
            """)).fetchall()
        finally:
            session.close()

        if not rows:
            return None

        # Max orders per (symbol, day) — 2× headroom over bar count
        MAX_ORDERS_PER_SYMBOL_DAY = {'1d': 2, '4h': 12, '1h': 48}

        findings = []
        for row in rows:
            interval = row[5] or '1d'
            threshold = MAX_ORDERS_PER_SYMBOL_DAY.get(interval, 2)
            orders_per_sd = row[4] or 0
            if orders_per_sd <= threshold:
                continue
            name = row[1] or row[0]
            evidence = (f"Strategy: {name}\nInterval: {interval}\n"
                       f"Entry orders submitted (24h): {row[3]}\nSymbol-days: {row[2]}\n"
                       f"Orders per symbol-day: {orders_per_sd:.1f} (max: {threshold})")
            findings.append(Finding(
                check_id="A10",
                key=f"strategy:{row[0]}",
                category="A",
                severity="P2",
                title=f"A10: {name} — {orders_per_sd:.0f} orders/symbol/day (overtrading, {interval})",
                detail=f"Strategy is submitting {orders_per_sd:.0f} entry orders per symbol per day for a {interval} strategy (max {threshold}). Frequency filter may be too loose.",
                evidence=evidence,
                recommended_action="Check alpha_edge.max_trades_per_strategy_per_month or add order cooldown.",
                context_links=[{"label": "Guard / Audit", "url": "/guard/audit"}],
                ask_kiro_prompt=f'Intel finding [A10]: "{name} — {orders_per_sd:.0f} orders/symbol/day (overtrading, {interval})."\n\nEvidence: {evidence}\n\nRecommended action: Check frequency filter.',
            ))
        return findings if findings else None

    # ═══════════════════════════════════════════════════════════════════════════
    # Category B — Execution Quality
    # ═══════════════════════════════════════════════════════════════════════════

    def _check_b1_order_failed_rate(self, lookback_days: int) -> Optional[Finding]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            row = session.execute(text("""
                SELECT
                    COUNT(*) FILTER (WHERE status='FAILED') as failed,
                    COUNT(*) as total
                FROM orders
                WHERE submitted_at > NOW() - INTERVAL '24 hours'
                AND account_type = 'demo'
            """)).fetchone()
        finally:
            session.close()

        if not row or not row[1] or row[1] == 0:
            return None

        rate = row[0] / row[1]
        if rate <= 0.30:
            return None

        evidence = f"Failed orders (24h): {row[0]}\nTotal orders (24h): {row[1]}\nFailure rate: {rate*100:.1f}%"
        return Finding(
            check_id="B1",
            key="order_failed_rate",
            category="B",
            severity="P1",
            title=f"B1: Order FAILED rate {rate*100:.0f}% in last 24h",
            detail="High order failure rate. Usually means market-closed deferrals are being written as FAILED instead of DEFERRED.",
            evidence=evidence,
            recommended_action="Check order_executor.py deferred path — should write DEFERRED not FAILED.",
            context_links=[{"label": "Book / Orders", "url": "/book/orders"}],
            ask_kiro_prompt=f'Intel finding [B1]: "Order FAILED rate {rate*100:.0f}% in last 24h."\n\nEvidence: {evidence}\n\nRecommended action: Check order_executor.py deferred path.',
        )

    def _check_b2_duplicate_orders(self, lookback_days: int) -> Optional[List[Finding]]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            rows = session.execute(text("""
                SELECT strategy_id, symbol, side, COUNT(*) as count
                FROM orders WHERE submitted_at > NOW() - INTERVAL '1 hour'
                AND account_type = 'demo'
                AND (order_action = 'entry' OR order_action IS NULL)
                GROUP BY strategy_id, symbol, side HAVING COUNT(*) > 3
            """)).fetchall()
        finally:
            session.close()

        if not rows:
            return None

        findings = []
        for row in rows:
            key = f"order_dedup:{row[0]}:{row[1]}:{row[2]}"
            evidence = f"Strategy: {row[0]}\nSymbol: {row[1]}\nDirection: {row[2]}\nOrders in last 1h: {row[3]}"
            findings.append(Finding(
                check_id="B2",
                key=key,
                category="B",
                severity="P0",
                title=f"B2: {row[1]} {row[2]} — {row[3]} duplicate orders in 1h",
                detail="Same (strategy, symbol, direction) submitted more than 3 times in 1 hour. Cross-cycle dedup may be broken.",
                evidence=evidence,
                recommended_action="Check trading_scheduler signal dedup logic. May be creating duplicate positions.",
                context_links=[{"label": "Book / Orders", "url": "/book/orders"}],
                ask_kiro_prompt=f'Intel finding [B2]: "{row[1]} {row[2]} — {row[3]} duplicate orders in 1h."\n\nEvidence: {evidence}\n\nRecommended action: Check trading_scheduler dedup logic.',
            ))
        return findings if findings else None

    def _check_b3_slippage_null(self, lookback_days: int) -> Optional[Finding]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            row = session.execute(text(f"""
                SELECT
                    COUNT(*) FILTER (WHERE slippage IS NULL) as null_count,
                    COUNT(*) as total
                FROM orders WHERE status = 'FILLED'
                AND filled_at > NOW() - INTERVAL '{lookback_days} days'
            """)).fetchone()
        finally:
            session.close()

        if not row or not row[1] or row[1] == 0:
            return None

        null_rate = row[0] / row[1]
        if null_rate <= 0.50:
            return None

        evidence = f"NULL slippage: {row[0]}\nTotal filled: {row[1]}\nNull rate: {null_rate*100:.1f}%"
        return Finding(
            check_id="B3",
            key="slippage_not_populated",
            category="B",
            severity="P2",
            title=f"B3: Slippage NULL on {null_rate*100:.0f}% of filled orders",
            detail="Execution quality is blind — slippage not being calculated on fills. Cannot measure actual vs expected fill prices.",
            evidence=evidence,
            recommended_action="In order_monitor fill handler, compute: slippage = (filled_price - expected_price) / expected_price * side_sign and save to orders.slippage column.",
            context_links=[{"label": "Research / Execution", "url": "/research/execution"}],
            ask_kiro_prompt=f'Intel finding [B3]: "Slippage NULL on {null_rate*100:.0f}% of filled orders."\n\nEvidence: {evidence}\n\nRecommended action: Add slippage calculation in order_monitor fill handler.',
        )

    def _check_b4_order_stuck_pending(self, lookback_days: int) -> Optional[List[Finding]]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            rows = session.execute(text("""
                SELECT id, symbol, side, submitted_at, status
                FROM orders WHERE status IN ('PENDING','SUBMITTED')
                AND submitted_at < NOW() - INTERVAL '2 hours'
                AND account_type = 'demo'
            """)).fetchall()
        finally:
            session.close()

        if not rows:
            return None

        findings = []
        for row in rows:
            age_h = round((datetime.now() - row[3]).total_seconds() / 3600, 1) if row[3] else "?"
            evidence = f"Order ID: {row[0]}\nSymbol: {row[1]}\nSide: {row[2]}\nStatus: {row[4]}\nAge: {age_h}h"
            findings.append(Finding(
                check_id="B4",
                key=f"order:{row[0]}",
                category="B",
                severity="P1",
                title=f"B4: {row[1]} order stuck {row[4]} for {age_h}h",
                detail="Order has been in PENDING/SUBMITTED state for over 2 hours during market hours. May need manual cancellation.",
                evidence=evidence,
                recommended_action="Check eToro API for this order ID. May need manual cancellation or the order_monitor fill check is not running.",
                context_links=[{"label": "Book / Orders", "url": "/book/orders"}],
                ask_kiro_prompt=f'Intel finding [B4]: "{row[1]} order stuck {row[4]} for {age_h}h."\n\nEvidence: {evidence}\n\nRecommended action: Check eToro API for this order.',
            ))
        return findings if findings else None

    def _check_b5_etoro_id_collision(self, lookback_days: int) -> Optional[Finding]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            rows = session.execute(text("""
                SELECT etoro_position_id, COUNT(DISTINCT account_type) as acct_count
                FROM positions WHERE etoro_position_id IS NOT NULL
                GROUP BY etoro_position_id HAVING COUNT(DISTINCT account_type) > 1
            """)).fetchall()
        finally:
            session.close()

        if not rows:
            return None

        evidence = f"Colliding eToro position IDs: {[r[0] for r in rows]}"
        return Finding(
            check_id="B5",
            key="etoro_id_collision",
            category="B",
            severity="P0",
            title=f"B5: {len(rows)} eToro position ID(s) exist in both demo and live accounts",
            detail="account_type scoping bug. eToro reuses numeric position IDs across demo/live. Without scoping, demo sync can corrupt live position rows.",
            evidence=evidence,
            recommended_action="Check OrderMonitor queries — all must filter by account_type. Verify composite unique constraint (etoro_position_id, account_type) is in place.",
            context_links=[{"label": "Book / Live", "url": "/book/live"}],
            ask_kiro_prompt=f'Intel finding [B5]: "{len(rows)} eToro position ID(s) exist in both demo and live accounts."\n\nEvidence: {evidence}\n\nRecommended action: Check OrderMonitor account_type scoping.',
        )

    def _check_b6_position_strategy_null(self, lookback_days: int) -> Optional[List[Finding]]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            rows = session.execute(text("""
                SELECT id, symbol, opened_at FROM positions
                WHERE strategy_id IS NULL AND closed_at IS NULL
                AND opened_at < NOW() - INTERVAL '10 minutes'
                AND account_type = 'demo'
            """)).fetchall()
        finally:
            session.close()

        if not rows:
            return None

        findings = []
        for row in rows:
            age_m = round((datetime.now() - row[2]).total_seconds() / 60) if row[2] else "?"
            evidence = f"Position ID: {row[0]}\nSymbol: {row[1]}\nAge: {age_m}min\nstrategy_id: NULL"
            findings.append(Finding(
                check_id="B6",
                key=f"position:{row[0]}",
                category="B",
                severity="P1",
                title=f"B6: {row[1]} position has NULL strategy_id after {age_m}min",
                detail="Race condition: position sync created row before fill set strategy_id. Position has no strategy attribution.",
                evidence=evidence,
                recommended_action="Check order_monitor fill handler — strategy_id must be set atomically with position creation.",
                context_links=[{"label": "Book / Positions", "url": "/book"}],
                ask_kiro_prompt=f'Intel finding [B6]: "{row[1]} position has NULL strategy_id after {age_m}min."\n\nEvidence: {evidence}\n\nRecommended action: Check order_monitor fill handler for race condition.',
            ))
        return findings if findings else None

    def _check_b8_order_size_below_minimum(self, lookback_days: int) -> Optional[Finding]:
        lines = self.log_reader.grep_logs(
            "Order size must be at least",
            lookback_days,
            ["errors.log", "alphacent.log"],
        )
        if not lines:
            return None

        evidence = f"Log lines ({len(lines)} occurrences):\n" + "\n".join(l["text"] for l in lines[:5])
        return Finding(
            check_id="B8",
            key="order_size_below_minimum",
            category="B",
            severity="P2",
            title=f"B8: {len(lines)} sub-minimum order size attempts",
            detail="Position sizing calculation is producing sizes below the minimum order size. These orders are being rejected.",
            evidence=evidence,
            recommended_action="Check risk_manager.calculate_position_size — MINIMUM_ORDER_SIZE guard should prevent this reaching order_executor.",
            context_links=[{"label": "Guard / Audit", "url": "/guard/audit"}],
            ask_kiro_prompt=f'Intel finding [B8]: "{len(lines)} sub-minimum order size attempts."\n\nEvidence: {evidence}\n\nRecommended action: Check risk_manager position sizing.',
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # Category C — Risk & Position Management
    # ═══════════════════════════════════════════════════════════════════════════

    def _check_c1_symbol_concentration(self, lookback_days: int) -> Optional[List[Finding]]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            rows = session.execute(text("""
                WITH equity AS (
                    SELECT COALESCE(
                        (SELECT equity FROM equity_snapshots
                         WHERE account_type = 'demo'
                         ORDER BY created_at DESC LIMIT 1),
                        (SELECT balance FROM account_info WHERE mode = 'DEMO'
                         ORDER BY updated_at DESC LIMIT 1),
                        1
                    ) as val
                )
                SELECT p.symbol,
                       SUM(p.invested_amount) as total_invested,
                       SUM(p.invested_amount) / (SELECT val FROM equity) as pct
                FROM positions p
                WHERE p.closed_at IS NULL AND p.account_type = 'demo'
                AND p.invested_amount IS NOT NULL AND p.invested_amount > 0
                GROUP BY p.symbol
                HAVING SUM(p.invested_amount) / (SELECT val FROM equity) > 0.05
                ORDER BY pct DESC
            """)).fetchall()
        finally:
            session.close()

        if not rows:
            return None

        findings = []
        for row in rows:
            pct = round((row[2] or 0) * 100, 1)
            evidence = f"Symbol: {row[0]}\nTotal invested: ${row[1]:.0f}\nConcentration: {pct}% (limit: 5%)"
            findings.append(Finding(
                check_id="C1",
                key=f"concentration:{row[0]}",
                category="C",
                severity="P1",
                title=f"C1: {row[0]} at {pct}% of equity (limit 5%)",
                detail="Symbol concentration cap not enforced cumulatively. Multiple strategies in the same symbol are accumulating beyond the 5% limit.",
                evidence=evidence,
                recommended_action="Check order_executor pre-flight — must sum existing exposure for symbol across all open positions before allowing new entry.",
                context_links=[{"label": "Guard / Risk", "url": "/guard/risk"}],
                ask_kiro_prompt=f'Intel finding [C1]: "{row[0]} at {pct}% of equity (limit 5%)."\n\nEvidence: {evidence}\n\nRecommended action: Fix cumulative symbol concentration check in order_executor.',
            ))
        return findings if findings else None

    def _check_c2_portfolio_heat(self, lookback_days: int) -> Optional[Finding]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            # FIX: Portfolio heat = sum(invested_amount × stop_loss_pct) / equity
            # NOT invested / equity (that's deployment ratio, not risk).
            # The 30% cap means: if every SL fires simultaneously, max drawdown is 30%.
            # Paper mode bypasses the heat cap (flat $5K sizing), so this check
            # is informational only for paper — flag at 80%+ to surface genuine risk.
            row = session.execute(text("""
                WITH equity AS (
                    SELECT COALESCE(
                        (SELECT equity FROM equity_snapshots
                         WHERE account_type = 'demo'
                         ORDER BY created_at DESC LIMIT 1),
                        (SELECT balance FROM account_info WHERE mode = 'DEMO'
                         ORDER BY updated_at DESC LIMIT 1),
                        1
                    ) as val
                ),
                heat_calc AS (
                    SELECT
                        SUM(p.invested_amount * COALESCE(
                            CASE WHEN p.stop_loss IS NOT NULL AND p.entry_price IS NOT NULL
                                      AND p.entry_price > 0
                                 THEN ABS(p.entry_price - p.stop_loss) / p.entry_price
                            END, 0.06
                        )) as total_heat,
                        SUM(p.invested_amount) as total_invested
                    FROM positions p
                    WHERE p.closed_at IS NULL AND p.account_type = 'demo'
                    AND p.invested_amount IS NOT NULL AND p.invested_amount > 0
                )
                SELECT
                    hc.total_heat / e.val as heat_ratio,
                    hc.total_invested / e.val as deployment_ratio,
                    hc.total_heat,
                    hc.total_invested,
                    e.val as equity_val
                FROM heat_calc hc, equity e
            """)).fetchone()
        finally:
            session.close()

        if not row or not row[0] or row[0] <= 0.80:
            return None

        heat_pct = round(row[0] * 100, 1)
        deploy_pct = round(row[1] * 100, 1)
        evidence = (
            f"Portfolio heat (risk): {heat_pct}% (limit: 30% for live, informational for paper)\n"
            f"Deployment ratio: {deploy_pct}% of equity\n"
            f"Total heat: ${row[2]:.0f}\nTotal invested: ${row[3]:.0f}\nEquity: ${row[4]:.0f}\n"
            f"Note: Paper mode uses flat $5K sizing and bypasses the heat cap gate — "
            f"this is informational only. Heat this high on a live account would be a P0."
        )
        return Finding(
            check_id="C2",
            key="portfolio_heat",
            category="C",
            severity="P2",
            title=f"C2: Portfolio heat {heat_pct}% (paper mode — informational)",
            detail="Portfolio heat is high. Note: paper mode bypasses the 30% heat cap intentionally — flat $5K sizing accumulates heat without the risk framework gate. This would be critical on a live account.",
            evidence=evidence,
            recommended_action="No action required for paper mode. Monitor live account heat separately.",
            context_links=[{"label": "Guard / Risk", "url": "/guard/risk"}],
            ask_kiro_prompt=f'Intel finding [C2]: "Portfolio heat {heat_pct}% (paper mode)."\n\nEvidence: {evidence}\n\nNote: Paper mode bypasses heat cap by design.',
        )

    def _check_c3_profitable_sl_at_entry(self, lookback_days: int) -> Optional[List[Finding]]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            rows = session.execute(text("""
                SELECT id, symbol, entry_price, current_price, stop_loss,
                       (current_price - entry_price) / NULLIF(entry_price, 0) as pnl_pct
                FROM positions WHERE closed_at IS NULL AND account_type = 'demo'
                AND side = 'LONG'
                AND stop_loss IS NOT NULL
                AND ABS(stop_loss - entry_price) / NULLIF(entry_price, 0) < 0.001
                AND (current_price - entry_price) / NULLIF(entry_price, 0) > 0.07
            """)).fetchall()
        finally:
            session.close()

        if not rows:
            return None

        findings = []
        for row in rows:
            pnl_pct = round((row[5] or 0) * 100, 1)
            evidence = f"Symbol: {row[1]}\nEntry: ${row[2]:.2f}\nCurrent: ${row[3]:.2f}\nP&L: +{pnl_pct}%\nSL: ${row[4]:.2f} (at entry)"
            findings.append(Finding(
                check_id="C3",
                key=f"position:{row[0]}",
                category="C",
                severity="P2",
                title=f"C3: {row[1]} +{pnl_pct}% but SL still at entry price",
                detail="Position is profitable >7% but trailing stop has not ratcheted above entry. TSL may not be running or price data is stale.",
                evidence=evidence,
                recommended_action="Check monitoring_service._check_trailing_stops — profit_lock and trail thresholds. Position may have stale price data preventing ratchet.",
                context_links=[{"label": "Book / Positions", "url": "/book"}],
                ask_kiro_prompt=f'Intel finding [C3]: "{row[1]} +{pnl_pct}% but SL still at entry price."\n\nEvidence: {evidence}\n\nRecommended action: Check TSL ratchet logic.',
            ))
        return findings if findings else None

    def _check_c4_zombie_positions(self, lookback_days: int) -> Optional[List[Finding]]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            rows = session.execute(text("""
                SELECT p.id, p.symbol, p.opened_at, p.unrealized_pnl,
                       p.invested_amount,
                       ABS(p.unrealized_pnl / NULLIF(p.invested_amount, 0)) as pnl_pct,
                       s.strategy_metadata->>'interval' as interval
                FROM positions p
                LEFT JOIN strategies s ON s.id = p.strategy_id
                WHERE p.closed_at IS NULL AND p.account_type = 'demo'
                AND p.invested_amount IS NOT NULL AND p.invested_amount > 0
                AND ABS(p.unrealized_pnl / NULLIF(p.invested_amount, 0)) < 0.01
                AND (
                    (COALESCE(s.strategy_metadata->>'interval', '1d') = '1d'
                     AND p.opened_at < NOW() - INTERVAL '5 days')
                    OR
                    (s.strategy_metadata->>'interval' = '4h'
                     AND p.opened_at < NOW() - INTERVAL '3 days')
                )
            """)).fetchall()
        finally:
            session.close()

        if not rows:
            return None

        findings = []
        for row in rows:
            days_open = round((datetime.now() - row[2]).days) if row[2] else "?"
            pnl_pct = round((row[5] or 0) * 100, 2)
            evidence = f"Symbol: {row[1]}\nDays open: {days_open}\nP&L: {pnl_pct}%\nInterval: {row[6] or '1d'}"
            findings.append(Finding(
                check_id="C4",
                key=f"position:{row[0]}",
                category="C",
                severity="P2",
                title=f"C4: {row[1]} zombie — flat {pnl_pct}% for {days_open}d",
                detail="Position has been flat (±1%) for longer than the zombie exit threshold. Capital is tied up with no edge.",
                evidence=evidence,
                recommended_action="Check monitoring_service zombie exit logic — flat threshold and minimum age for this interval.",
                context_links=[{"label": "Book / Positions", "url": "/book"}],
                ask_kiro_prompt=f'Intel finding [C4]: "{row[1]} zombie — flat {pnl_pct}% for {days_open}d."\n\nEvidence: {evidence}\n\nRecommended action: Check zombie exit logic.',
            ))
        return findings if findings else None

    def _check_c7_position_no_stop_loss(self, lookback_days: int) -> Optional[List[Finding]]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            rows = session.execute(text("""
                SELECT id, symbol, side, entry_price, opened_at
                FROM positions WHERE closed_at IS NULL
                AND stop_loss IS NULL AND account_type = 'demo'
            """)).fetchall()
        finally:
            session.close()

        if not rows:
            return None

        findings = []
        for row in rows:
            age_h = round((datetime.now() - row[4]).total_seconds() / 3600, 1) if row[4] else "?"
            evidence = f"Position ID: {row[0]}\nSymbol: {row[1]}\nSide: {row[2]}\nEntry: ${row[3]:.2f}\nAge: {age_h}h\nStop loss: NULL"
            findings.append(Finding(
                check_id="C7",
                key=f"position:{row[0]}",
                category="C",
                severity="P0",
                title=f"C7: {row[1]} {row[2]} — UNPROTECTED (no stop loss)",
                detail="Open position has no stop loss set. This position has unlimited downside risk.",
                evidence=evidence,
                recommended_action="Check order_executor ATR stop calculation. Position must be manually reviewed and a stop loss set immediately.",
                context_links=[{"label": "Book / Positions", "url": "/book"}],
                ask_kiro_prompt=f'Intel finding [C7]: "{row[1]} {row[2]} — UNPROTECTED (no stop loss)."\n\nEvidence: {evidence}\n\nRecommended action: URGENT — set stop loss immediately. Check order_executor ATR stop calculation.',
            ))
        return findings if findings else None

    # ═══════════════════════════════════════════════════════════════════════════
    # Category D — Data Pipeline
    # ═══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _business_days_stale(latest_bar) -> float:
        """Weekday-days elapsed since `latest_bar` (Sat/Sun excluded).

        P1-5: market-hours proxy for data freshness. Raw wall-clock staleness
        reads ~20h for a current 1d bar intraday and ~3 days over a weekend,
        which made D1/D2 fire false P1s for every open position every overnight
        and every Monday. Counting only weekdays after the bar's date ignores
        normal closures while still catching genuine multi-day gaps (e.g.
        ALUMINUM at 162h ≈ 5 business days). Returns a large sentinel if
        latest_bar is None (never synced).
        """
        from datetime import timedelta as _td
        if latest_bar is None:
            return 9999.0
        now = datetime.now()
        if latest_bar >= now:
            return 0.0
        days = 0
        cur = latest_bar.date()
        today = now.date()
        while cur < today:
            cur = cur + _td(days=1)
            if cur.weekday() < 5:  # Mon–Fri
                days += 1
        return float(days)

    def _check_d1_stale_1d_bars(self, lookback_days: int) -> Optional[List[Finding]]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            rows = session.execute(text("""
                SELECT p.symbol,
                       MAX(h.date) as latest_bar,
                       EXTRACT(EPOCH FROM (NOW() - MAX(h.date)))/3600 as stale_hours
                FROM positions p
                LEFT JOIN historical_price_cache h
                    ON h.symbol = p.symbol AND h.interval = '1d'
                WHERE p.closed_at IS NULL AND p.account_type = 'demo'
                GROUP BY p.symbol
                HAVING NOW() - MAX(h.date) > INTERVAL '2 days'
                   OR MAX(h.date) IS NULL
            """)).fetchall()
        finally:
            session.close()

        if not rows:
            return None

        findings = []
        for row in rows:
            # P1-5: skip false positives from weekends/overnight — only flag when
            # the bar is stale by more than 2 BUSINESS days.
            bd_stale = self._business_days_stale(row[1])
            if bd_stale <= 2:
                continue
            stale_h = round(row[2] or 0, 1)
            latest = row[1].strftime("%Y-%m-%d") if row[1] else "never"
            evidence = f"Symbol: {row[0]}\nLatest 1d bar: {latest}\nStaleness: {stale_h}h ({bd_stale:.0f} business days)"
            findings.append(Finding(
                check_id="D1",
                key=f"data_stale:{row[0]}:1d",
                category="D",
                severity="P1",
                title=f"D1: {row[0]} — 1d bars {bd_stale:.0f} business days stale (open position)",
                detail="Signal generation is running on stale 1d data for an open position. Indicators may be wrong.",
                evidence=evidence,
                recommended_action="Check _sync_price_data for this symbol — may be Yahoo ticker mapping issue or DST crash. Run manual full sync.",
                context_links=[{"label": "Guard / System", "url": "/guard/system"}],
                ask_kiro_prompt=f'Intel finding [D1]: "{row[0]} — 1d bars {stale_h:.0f}h stale (open position)."\n\nEvidence: {evidence}\n\nRecommended action: Check _sync_price_data for this symbol.',
            ))
        return findings if findings else None

    def _check_d2_stale_4h_bars(self, lookback_days: int) -> Optional[List[Finding]]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            rows = session.execute(text("""
                SELECT p.symbol,
                       MAX(h.date) as latest_bar,
                       EXTRACT(EPOCH FROM (NOW() - MAX(h.date)))/3600 as stale_hours
                FROM positions p
                JOIN strategies s ON s.id = p.strategy_id
                LEFT JOIN historical_price_cache h
                    ON h.symbol = p.symbol AND h.interval = '4h'
                WHERE p.closed_at IS NULL AND p.account_type = 'demo'
                AND s.strategy_metadata->>'interval' = '4h'
                GROUP BY p.symbol
                HAVING NOW() - MAX(h.date) > INTERVAL '6 hours'
                   OR MAX(h.date) IS NULL
            """)).fetchall()
        finally:
            session.close()

        if not rows:
            return None

        findings = []
        for row in rows:
            # P1-5: 4h bars legitimately age overnight (~17h) and over weekends
            # (~65h). Only flag genuine multi-day gaps (> 2 business days); the
            # raw SQL "> 6 hours" HAVING is just a coarse prefilter.
            bd_stale = self._business_days_stale(row[1])
            if bd_stale <= 2:
                continue
            stale_h = round(row[2] or 0, 1)
            latest = row[1].strftime("%Y-%m-%d %H:%M") if row[1] else "never"
            evidence = f"Symbol: {row[0]}\nLatest 4h bar: {latest}\nStaleness: {stale_h}h ({bd_stale:.0f} business days)"
            findings.append(Finding(
                check_id="D2",
                key=f"data_stale:{row[0]}:4h",
                category="D",
                severity="P1",
                title=f"D2: {row[0]} — 4h bars {bd_stale:.0f} business days stale (4h strategy open)",
                detail="4h strategy has an open position but 4h bars are stale. TSL ratchet and signal generation may be using wrong data.",
                evidence=evidence,
                recommended_action="Check _sync_price_data for this symbol's 4h interval. May need manual sync.",
                context_links=[{"label": "Guard / System", "url": "/guard/system"}],
                ask_kiro_prompt=f'Intel finding [D2]: "{row[0]} — 4h bars {stale_h:.0f}h stale."\n\nEvidence: {evidence}\n\nRecommended action: Check 4h data sync for this symbol.',
            ))
        return findings if findings else None

    def _check_d3_yahoo_delisted(self, lookback_days: int) -> Optional[Finding]:
        matches = self.log_reader.grep_logs(
            "possibly delisted",
            lookback_days,
            ["errors.log", "alphacent.log"],
        )
        if not matches:
            return None

        # Extract unique symbols from log lines
        symbols = set()
        for m in matches:
            text_line = m.get("text", "")
            # Try to extract symbol from log line
            for part in text_line.split():
                if part.isupper() and 2 <= len(part) <= 6 and part.isalpha():
                    symbols.add(part)

        evidence = f"Occurrences: {len(matches)}\nSample symbols: {', '.join(list(symbols)[:10])}\nSample: {matches[0]['text'][:200]}"
        return Finding(
            check_id="D3",
            key="yahoo_delisted",
            category="D",
            severity="P2",
            title=f"D3: Yahoo 'possibly delisted' errors ({len(matches)} occurrences)",
            detail="Yahoo Finance is returning 'possibly delisted' errors for some symbols. Ticker mapping may be wrong.",
            evidence=evidence,
            recommended_action="Check symbol_mapper.py to_yahoo_ticker() — may need explicit override for affected symbols.",
            context_links=[{"label": "Guard / System", "url": "/guard/system"}],
            ask_kiro_prompt=f'Intel finding [D3]: "Yahoo possibly delisted errors ({len(matches)} occurrences)."\n\nEvidence: {evidence}\n\nRecommended action: Check symbol_mapper.py to_yahoo_ticker().',
        )

    def _check_d4_fmp_rate_limit(self, lookback_days: int) -> Optional[Finding]:
        matches = self.log_reader.grep_logs(
            "FMP rate limit",
            lookback_days,
            ["errors.log", "alphacent.log"],
        )
        if not matches:
            return None

        evidence = f"Rate limit hits: {len(matches)}\nSample: {matches[0]['text'][:200]}"
        return Finding(
            check_id="D4",
            key="fmp_rate_limit",
            category="D",
            severity="P1",
            title=f"D4: FMP rate limit hit {len(matches)} times",
            detail="FMP Starter plan rate limit (300 calls/min) is being exceeded. Fundamental data unavailable for part of cycle.",
            evidence=evidence,
            recommended_action="Consider spreading FMP calls across cycle phases or upgrading plan.",
            context_links=[{"label": "Guard / System", "url": "/guard/system"}],
            ask_kiro_prompt=f'Intel finding [D4]: "FMP rate limit hit {len(matches)} times."\n\nEvidence: {evidence}\n\nRecommended action: Spread FMP calls or upgrade plan.',
        )

    def _check_d7_duplicate_price_bars(self, lookback_days: int) -> Optional[Finding]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            rows = session.execute(text("""
                SELECT symbol, interval, DATE(date) as day, COUNT(*) as count
                FROM historical_price_cache
                WHERE interval = '1d'
                GROUP BY symbol, interval, DATE(date)
                HAVING COUNT(*) > 1
                LIMIT 20
            """)).fetchall()
        finally:
            session.close()

        if not rows:
            return None

        evidence = f"Duplicate 1d bar groups: {len(rows)}\nSample: {rows[0][0]} on {rows[0][2]} ({rows[0][3]} rows)"
        return Finding(
            check_id="D7",
            key="data_duplicate:1d",
            category="D",
            severity="P2",
            title=f"D7: {len(rows)} duplicate 1d bar groups in historical_price_cache",
            detail="Duplicate 1d bars exist in the price cache. This can cause indicator miscalculation.",
            evidence=evidence,
            recommended_action="Run: DELETE FROM historical_price_cache WHERE id NOT IN (SELECT MIN(id) FROM historical_price_cache GROUP BY symbol, interval, DATE(date)). Then add upsert logic in _save_historical_to_db.",
            context_links=[{"label": "Guard / System", "url": "/guard/system"}],
            ask_kiro_prompt=f'Intel finding [D7]: "{len(rows)} duplicate 1d bar groups in historical_price_cache."\n\nEvidence: {evidence}\n\nRecommended action: Deduplicate price cache.',
        )

    def _check_d8_mqs_null_snapshots(self, lookback_days: int) -> Optional[Finding]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            row = session.execute(text("""
                SELECT COUNT(*) FROM equity_snapshots
                WHERE market_quality_score IS NULL
                AND created_at > NOW() - INTERVAL '3 days'
            """)).fetchone()
        finally:
            session.close()

        if not row or (row[0] or 0) < 3:
            return None

        evidence = f"NULL MQS snapshots in last 3 days: {row[0]}"
        return Finding(
            check_id="D8",
            key="mqs_null_snapshots",
            category="D",
            severity="P2",
            title=f"D8: {row[0]} equity snapshots with NULL market_quality_score",
            detail="MQS persistence is broken. The _save_hourly_equity_snapshot function is silently failing to compute/save MQS.",
            evidence=evidence,
            recommended_action="Check _save_hourly_equity_snapshot in monitoring_service.py — MQS computation wrapped in except:pass. Fix the silent failure.",
            context_links=[{"label": "Guard / System", "url": "/guard/system"}],
            ask_kiro_prompt=f'Intel finding [D8]: "{row[0]} equity snapshots with NULL MQS."\n\nEvidence: {evidence}\n\nRecommended action: Fix MQS persistence in _save_hourly_equity_snapshot.',
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # Category E — Cycle & Signal Pipeline
    # ═══════════════════════════════════════════════════════════════════════════

    def _check_e1_cycle_duration(self, lookback_days: int) -> Optional[Finding]:
        lines = self.log_reader.read_lines(
            "cycles/cycle_history.log",
            lookback_days,
            pattern="CYCLE COMPLETE in",
        )
        if not lines:
            return None

        durations = []
        for line in lines:
            try:
                # Format: "CYCLE COMPLETE in 342.1s"
                idx = line.index("CYCLE COMPLETE in ")
                rest = line[idx + len("CYCLE COMPLETE in "):]
                secs = float(rest.split("s")[0].strip())
                durations.append(secs)
            except (ValueError, IndexError):
                continue

        if not durations:
            return None

        slow = [d for d in durations if d > 1200]
        if not slow:
            return None

        avg_slow = round(sum(slow) / len(slow))
        evidence = f"Cycles >1200s: {len(slow)} of {len(durations)}\nAvg slow duration: {avg_slow}s\nMax: {max(slow):.0f}s"
        return Finding(
            check_id="E1",
            key="cycle_duration_regression",
            category="E",
            severity="P2",
            title=f"E1: {len(slow)} cycles exceeded 1200s (avg {avg_slow}s)",
            detail="Autonomous cycle is running slower than expected. May indicate WF cache miss rate increasing or new 1h strategies adding load.",
            evidence=evidence,
            recommended_action="Check: (1) WF cache hit rate dropping, (2) new 1h strategies added (large WF windows), (3) DB query performance.",
            context_links=[{"label": "Guard / Sync log", "url": "/guard/sync-log"}],
            ask_kiro_prompt=f'Intel finding [E1]: "{len(slow)} cycles exceeded 1200s (avg {avg_slow}s)."\n\nEvidence: {evidence}\n\nRecommended action: Check WF cache hit rate and DB performance.',
        )

    def _check_e2_wf_cache_hit_rate(self, lookback_days: int) -> Optional[Finding]:
        hit_lines = self.log_reader.read_lines("strategy.log", lookback_days, pattern="WF cache hit")
        miss_lines = self.log_reader.read_lines("strategy.log", lookback_days, pattern="WF window [")

        hits = len(hit_lines)
        misses = len(miss_lines)
        total = hits + misses
        if total < 10:
            return None

        hit_rate = hits / total
        if hit_rate >= 0.40:
            return None

        evidence = f"WF cache hits: {hits}\nWF cache misses: {misses}\nHit rate: {hit_rate*100:.1f}% (threshold: 40%)"
        return Finding(
            check_id="E2",
            key="wf_cache_hit_rate",
            category="E",
            severity="P2",
            title=f"E2: WF cache hit rate {hit_rate*100:.0f}% (below 40%)",
            detail="Walk-forward cache is not effective. Each cache miss triggers a full WF computation, slowing cycles.",
            evidence=evidence,
            recommended_action="Check wf_cache_ttl in autonomous_trading.yaml (should be 1h). Cache may be invalidated too aggressively.",
            context_links=[{"label": "Guard / System", "url": "/guard/system"}],
            ask_kiro_prompt=f'Intel finding [E2]: "WF cache hit rate {hit_rate*100:.0f}% (below 40%)."\n\nEvidence: {evidence}\n\nRecommended action: Check wf_cache_ttl in autonomous_trading.yaml.',
        )

    def _check_e3_low_proposals(self, lookback_days: int) -> Optional[Finding]:
        lines = self.log_reader.read_lines(
            "cycles/cycle_history.log",
            lookback_days,
            pattern="fresh (DSL=",
        )
        if not lines:
            return None

        counts = []
        for line in lines:
            try:
                # Format: "12 fresh (DSL=8, AE=4)"
                count = int(line.strip().split()[0])
                counts.append(count)
            except (ValueError, IndexError):
                continue

        if not counts:
            return None

        low = [c for c in counts if c < 10]
        if len(low) < 3:
            return None

        evidence = f"Cycles with <10 proposals: {len(low)} of {len(counts)}\nMin: {min(counts)}\nAvg: {sum(counts)//len(counts)}"
        return Finding(
            check_id="E3",
            key="proposal_count_low",
            category="E",
            severity="P2",
            title=f"E3: {len(low)} cycles with <10 fresh proposals",
            detail="Template pool may be exhausted or rejection blacklist too aggressive. System is not generating enough new strategy candidates.",
            evidence=evidence,
            recommended_action="Check: (1) .wf_failed_cache.json size, (2) .rejection_blacklist.json, (3) .zero_trade_blacklist.json.",
            context_links=[{"label": "Guard / System", "url": "/guard/system"}],
            ask_kiro_prompt=f'Intel finding [E3]: "{len(low)} cycles with <10 fresh proposals."\n\nEvidence: {evidence}\n\nRecommended action: Check rejection blacklists and WF failed cache.',
        )

    def _check_e4_zero_short_wf_pass(self, lookback_days: int) -> Optional[Finding]:
        lines = self.log_reader.read_lines("strategy.log", lookback_days, pattern="SHORT")
        wf_pass_lines = [l for l in lines if "✓" in l and "SHORT" in l]

        if len(wf_pass_lines) > 0:
            return None

        # Only fire if we have enough data to be meaningful
        total_lines = len(lines)
        if total_lines < 20:
            return None

        evidence = f"SHORT WF passes in last {lookback_days}d: 0\nTotal SHORT-related log lines: {total_lines}"
        return Finding(
            check_id="E4",
            key="short_wf_pass_rate",
            category="E",
            severity="P1",
            title=f"E4: 0 SHORT strategies passed WF in last {lookback_days}d",
            detail="No SHORT strategies are passing walk-forward validation. Either SHORT templates are not being proposed or WF thresholds are too strict.",
            evidence=evidence,
            recommended_action="Check: (1) min_sharpe threshold for SHORTs (+0.3 tightening), (2) trade count requirements vs typical SHORT setup frequency, (3) whether SHORT templates are being proposed.",
            context_links=[{"label": "Strategies", "url": "/strategies"}],
            ask_kiro_prompt=f'Intel finding [E4]: "0 SHORT strategies passed WF in last {lookback_days}d."\n\nEvidence: {evidence}\n\nRecommended action: Check SHORT WF thresholds and proposal pipeline.',
        )

    def _check_e5_gate_loop(self, lookback_days: int) -> Optional[List[Finding]]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            # Fetch all distinct blocking reasons for each strategy so we can
            # inspect the FULL set, not just the lexicographically-largest one.
            # MAX(reason) is wrong here — "Insufficient balance: $0" beats
            # "Pullback gate..." alphabetically, so the old single-reason check
            # silently mis-classified pullback-blocked strategies as structural loops.
            rows = session.execute(text(f"""
                SELECT sd.strategy_id, s.name,
                       SUM(CASE WHEN sd.stage = 'gate_blocked' THEN 1 ELSE 0 END) as blocked,
                       SUM(CASE WHEN sd.stage = 'order_submitted' THEN 1 ELSE 0 END) as submitted,
                       ARRAY_AGG(DISTINCT sd.reason) FILTER (WHERE sd.stage = 'gate_blocked') as all_reasons,
                       COALESCE(s.strategy_metadata->>'interval', '1d') as interval
                FROM signal_decisions sd
                LEFT JOIN strategies s ON s.id = sd.strategy_id
                WHERE sd.timestamp > NOW() - INTERVAL '{lookback_days} days'
                GROUP BY sd.strategy_id, s.name, s.strategy_metadata->>'interval'
                HAVING SUM(CASE WHEN sd.stage = 'gate_blocked' THEN 1 ELSE 0 END) >= 10
                   AND SUM(CASE WHEN sd.stage = 'order_submitted' THEN 1 ELSE 0 END) = 0
            """)).fetchall()
        finally:
            session.close()

        if not rows:
            return None

        # A "permanent loop" means blocked by gates that will NEVER self-resolve.
        # Exclude strategies where ALL blocking reasons are temporary (market-condition
        # gates or transient balance/rate-limiting issues that clear on their own):
        #
        # Temporary (skip if ALL reasons are in this set):
        #   - Pullback gate / Drawdown pause / Market quality gate / Bull market regime gate
        #     → unblock when market recovers
        #   - Insufficient balance: $0 < N
        #     → transient: eToro settlement window depletes reported balance briefly
        #   - Symbol limit: N existing LONG ... (max: N)
        #     → rate-limiting by design — clears when existing positions close
        #   - Low-confidence exit ...
        #     → exit filter, not an entry permanent loop
        #
        # Structural (flag if ANY reason survives after excluding the above):
        #   - Any gate not in the temporary list that blocks every signal
        TEMPORARY_GATE_PREFIXES = (
            "Pullback gate",
            "Drawdown pause",
            "Market quality gate",
            "Bull market regime gate",
            # Insufficient balance at ANY level is transient (demo balance
            # depletes during settlement / full deployment and recovers when
            # positions close). Previously only the "$0" variant was excluded,
            # so balance blocks at $409/$1059/$1432 survived as "structural" and
            # produced false E5 "permanent loop" findings (MCHP, Jun 10). Match
            # both reason-string formats regardless of the dollar amount.
            "Insufficient balance:",       # "Insufficient balance: $409 < $2000"
            "insufficient_balance (",      # "insufficient_balance ($409 < $2000 minimum)"
            "Symbol limit:",               # rate-limiting by design
            "Low-confidence exit",         # exit filter, not entry loop
        )

        findings = []
        for row in rows:
            all_reasons = row[4] or []
            if not isinstance(all_reasons, list):
                all_reasons = [all_reasons] if all_reasons else []

            # Check whether every blocking reason is temporary/expected
            structural_reasons = [
                r for r in all_reasons
                if r and not any(r.startswith(prefix) for prefix in TEMPORARY_GATE_PREFIXES)
            ]

            # If every reason is temporary, skip — this is not a permanent loop
            if not structural_reasons:
                continue

            # Fallback name lookup for strategies not found via LEFT JOIN
            name = row[1]
            if not name:
                try:
                    from sqlalchemy import text as _text
                    sess2 = self.db.get_session()
                    try:
                        nr = sess2.execute(_text("SELECT name FROM strategies WHERE id=:id"), {"id": row[0]}).fetchone()
                        name = nr[0] if nr else row[0]
                    finally:
                        sess2.close()
                except Exception:
                    name = row[0]

            representative_reason = structural_reasons[0]
            evidence = (f"Strategy: {name}\nInterval: {row[5]}\n"
                       f"Gate blocks ({lookback_days}d): {row[2]}\n"
                       f"Orders submitted ({lookback_days}d): {row[3]}\n"
                       f"Structural blocking reason(s): {'; '.join(structural_reasons[:3])}")
            findings.append(Finding(
                check_id="E5",
                key=f"gate_loop:{row[0]}",
                category="E",
                severity="P1",
                title=f"E5: {name} — {row[2]} gate blocks, 0 orders in {lookback_days}d (permanent loop)",
                detail="Strategy is permanently blocked by a runtime gate — signals fire but no orders ever get through. Either the gate logic is wrong for this strategy type, or the strategy should be retired.",
                evidence=evidence,
                recommended_action="Review gate logic vs conviction scorer — they should be consistent. If gate is correct, retire the strategy.",
                context_links=[{"label": "Guard / Gates", "url": "/guard/gates"}, {"label": "Guard / Audit", "url": "/guard/audit"}],
                ask_kiro_prompt=f'Intel finding [E5]: "{name} — {row[2]} gate blocks, 0 orders in {lookback_days}d."\n\nEvidence: {evidence}\n\nRecommended action: Review gate logic for this strategy type.',
            ))
        return findings if findings else None

    def _check_e8_concurrent_cycles(self, lookback_days: int) -> Optional[Finding]:
        lines = self.log_reader.read_lines(
            "alphacent.log",
            lookback_days,
            pattern="Starting autonomous cycle",
        )
        if len(lines) < 2:
            return None

        # Look for two cycle starts without a "DB lock released" between them
        # Simple heuristic: two starts within 60 seconds
        starts = []
        for line in lines:
            ts = self.log_reader._parse_timestamp(line)
            if ts:
                starts.append(ts)

        overlaps = []
        for i in range(1, len(starts)):
            gap = (starts[i] - starts[i - 1]).total_seconds()
            if 0 < gap < 60:
                overlaps.append((starts[i - 1], starts[i]))

        if not overlaps:
            return None

        evidence = f"Potential concurrent cycle starts: {len(overlaps)}\nFirst overlap: {overlaps[0][0]} and {overlaps[0][1]}"
        return Finding(
            check_id="E8",
            key="concurrent_cycles",
            category="E",
            severity="P0",
            title=f"E8: {len(overlaps)} potential concurrent cycle starts detected",
            detail="Two autonomous cycles may have started within 60 seconds of each other. Cycle lock may be broken.",
            evidence=evidence,
            recommended_action="Check _db_cycle_lock in strategies.py — lock must be acquired before cycle starts and released in finally block.",
            context_links=[{"label": "Guard / Sync log", "url": "/guard/sync-log"}],
            ask_kiro_prompt=f'Intel finding [E8]: "{len(overlaps)} potential concurrent cycle starts."\n\nEvidence: {evidence}\n\nRecommended action: Check _db_cycle_lock in strategies.py.',
        )

    # ═══════════════════════════════════════════════════════════════════════════
    # Category F — System Health
    # ═══════════════════════════════════════════════════════════════════════════

    def _check_f1_new_errors(self, lookback_days: int) -> Optional[Finding]:
        lines = self.log_reader.read_lines("errors.log", lookback_days)
        if not lines:
            return None

        # Classify severity
        p0_keywords = ["UniqueViolation", "InFailedSqlTransaction", "duplicate key", "account_type collision"]
        p0_lines = [l for l in lines if any(kw in l for kw in p0_keywords)]
        severity = "P0" if p0_lines else "P1"

        sample = lines[-10:]  # most recent
        evidence = f"New error lines in last {lookback_days}d: {len(lines)}\nP0 errors: {len(p0_lines)}\nRecent:\n" + "\n".join(sample[:5])
        return Finding(
            check_id="F1",
            key="errors_log_new",
            category="F",
            severity=severity,
            title=f"F1: {len(lines)} new errors in errors.log ({len(p0_lines)} P0)",
            detail="New ERROR entries found in errors.log. P0 keywords indicate DB transaction or account scoping issues.",
            evidence=evidence,
            recommended_action="Review errors above. P0 keywords: UniqueViolation, InFailedSqlTransaction, duplicate key, account_type collision.",
            context_links=[{"label": "Guard / Sync log", "url": "/guard/sync-log"}],
            ask_kiro_prompt=f'Intel finding [F1]: "{len(lines)} new errors in errors.log ({len(p0_lines)} P0)."\n\nEvidence: {evidence}\n\nRecommended action: Review and fix errors.',
        )

    def _check_f2_sqlalchemy_failed_transaction(self, lookback_days: int) -> Optional[Finding]:
        matches = self.log_reader.grep_logs(
            "InFailedSqlTransaction",
            lookback_days,
            ["errors.log", "alphacent.log"],
        )
        if not matches:
            return None

        evidence = f"InFailedSqlTransaction occurrences: {len(matches)}\nSample: {matches[0]['text'][:300]}"
        return Finding(
            check_id="F2",
            key="sqlalchemy_failed_transaction",
            category="F",
            severity="P0",
            title=f"F2: SQLAlchemy InFailedSqlTransaction ({len(matches)} occurrences)",
            detail="Transaction not rolled back after error. Subsequent queries in the same session are failing because the transaction is in an error state.",
            evidence=evidence,
            recommended_action="Find the DB session that raised the original error and ensure session.rollback() is called in the except block before any subsequent queries.",
            context_links=[{"label": "Guard / Sync log", "url": "/guard/sync-log"}],
            ask_kiro_prompt=f'Intel finding [F2]: "SQLAlchemy InFailedSqlTransaction ({len(matches)} occurrences)."\n\nEvidence: {evidence}\n\nRecommended action: Add session.rollback() in except blocks.',
        )

    def _check_f3_postgres_idle_connections(self, lookback_days: int) -> Optional[Finding]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            row = session.execute(text("""
                SELECT
                    COUNT(*) FILTER (WHERE state = 'idle') as idle_count,
                    COUNT(*) as total_count
                FROM pg_stat_activity
                WHERE datname = 'alphacent'
            """)).fetchone()
        finally:
            session.close()

        if not row or (row[0] or 0) <= 8:
            return None

        evidence = f"Idle connections: {row[0]}\nTotal connections: {row[1]}"
        return Finding(
            check_id="F3",
            key="postgres_connections",
            category="F",
            severity="P2",
            title=f"F3: {row[0]} idle Postgres connections (>{8} threshold)",
            detail="Connection pool may be leaking. Idle connections accumulate when sessions are not properly closed.",
            evidence=evidence,
            recommended_action="Check that all DB sessions are closed in finally blocks. Consider adding pool_pre_ping=True to engine.",
            context_links=[{"label": "Guard / System", "url": "/guard/system"}],
            ask_kiro_prompt=f'Intel finding [F3]: "{row[0]} idle Postgres connections."\n\nEvidence: {evidence}\n\nRecommended action: Check DB session cleanup.',
        )

    def _check_f5_service_restart(self, lookback_days: int) -> Optional[Finding]:
        matches = self.log_reader.grep_logs(
            "AlphaCent backend starting",
            lookback_days,
            ["alphacent.log"],
        )
        if not matches:
            return None

        evidence = f"Service restarts in last {lookback_days}d: {len(matches)}\nTimestamps: {[m['timestamp'] for m in matches[:5]]}"
        return Finding(
            check_id="F5",
            key="service_restart",
            category="F",
            severity="P1",
            title=f"F5: {len(matches)} service restart(s) detected",
            detail="AlphaCent backend restarted unexpectedly. May indicate crashes, OOM kills, or manual restarts.",
            evidence=evidence,
            recommended_action="Check: (1) errors.log around restart time, (2) systemd journal for OOM killer, (3) cycle_error.log for crash.",
            context_links=[{"label": "Guard / Sync log", "url": "/guard/sync-log"}],
            ask_kiro_prompt=f'Intel finding [F5]: "{len(matches)} service restart(s) detected."\n\nEvidence: {evidence}\n\nRecommended action: Check errors.log and systemd journal.',
        )

    def _check_f7_api_rate_limits(self, lookback_days: int) -> Optional[List[Finding]]:
        providers = {
            "eToro": ["rate limit", "429"],
            "FMP": ["FMP rate limit", "FMP 429"],
            "Yahoo": ["Too Many Requests", "yahoo rate"],
        }
        findings = []
        for provider, patterns in providers.items():
            all_matches = []
            for pat in patterns:
                all_matches.extend(self.log_reader.grep_logs(pat, lookback_days, ["errors.log", "alphacent.log"]))
            if not all_matches:
                continue
            evidence = f"Provider: {provider}\nRate limit hits: {len(all_matches)}\nSample: {all_matches[0]['text'][:200]}"
            findings.append(Finding(
                check_id="F7",
                key=f"api_rate_limit:{provider.lower()}",
                category="F",
                severity="P1",
                title=f"F7: {provider} rate limit hit {len(all_matches)} times",
                detail=f"{provider} API rate limit is being exceeded. Data may be unavailable for part of cycle.",
                evidence=evidence,
                recommended_action=f"Check {provider} call frequency and add backoff. For FMP: 300 calls/min on Starter plan.",
                context_links=[{"label": "Guard / System", "url": "/guard/system"}],
                ask_kiro_prompt=f'Intel finding [F7]: "{provider} rate limit hit {len(all_matches)} times."\n\nEvidence: {evidence}\n\nRecommended action: Add backoff for {provider} API calls.',
            ))
        return findings if findings else None

    # ═══════════════════════════════════════════════════════════════════════════
    # Category G — Alpha & Improvement Opportunities
    # ═══════════════════════════════════════════════════════════════════════════

    def _check_g1_strong_wf_never_activated(self, lookback_days: int) -> Optional[List[Finding]]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            rows = session.execute(text(f"""
                SELECT DISTINCT sd.template_name, sd.symbol,
                       MAX((sd.decision_metadata->>'wf_test_sharpe')::float) as best_sharpe,
                       MAX(sd.reason) as last_reason
                FROM signal_decisions sd
                WHERE sd.stage = 'wf_validated' AND sd.decision = 'accepted'
                AND (sd.decision_metadata->>'wf_test_sharpe')::float > 2.0
                AND sd.timestamp > NOW() - INTERVAL '{lookback_days} days'
                AND sd.template_name IS NOT NULL AND sd.symbol IS NOT NULL
                GROUP BY sd.template_name, sd.symbol
                HAVING (sd.template_name, sd.symbol) NOT IN (
                    SELECT strategy_metadata->>'template_name', symbols->>0
                    FROM strategies WHERE status IN ('BACKTESTED','PAPER','LIVE')
                    AND activated_at > NOW() - INTERVAL '7 days'
                )
                LIMIT 10
            """)).fetchall()
        finally:
            session.close()

        if not rows:
            return None

        findings = []
        for row in rows:
            evidence = f"Template: {row[0]}\nSymbol: {row[1]}\nBest WF Sharpe: {row[2]:.2f}\nLast rejection reason: {row[3]}"
            findings.append(Finding(
                check_id="G1",
                key=f"template_blocked:{row[0]}:{row[1]}",
                category="G",
                severity="opportunity",
                title=f"G1: {row[0]} / {row[1]} — WF Sharpe {row[2]:.2f} but never activated",
                detail="Strong WF edge is not activating. Activation criteria may be blocking a genuinely good strategy.",
                evidence=evidence,
                recommended_action="Check activation criteria rejection reason in signal_decisions (stage=rejected_act). May be avg_loss gate, min_sharpe, or MC bootstrap failing.",
                context_links=[{"label": "Strategies", "url": "/strategies"}, {"label": "Guard / Audit", "url": "/guard/audit"}],
                ask_kiro_prompt=f'Intel finding [G1]: "{row[0]} / {row[1]} — WF Sharpe {row[2]:.2f} but never activated."\n\nEvidence: {evidence}\n\nRecommended action: Check activation criteria rejection reason.',
            ))
        return findings if findings else None

    def _check_g2_underweighted_asset_class(self, lookback_days: int) -> Optional[List[Finding]]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            # Get live WR by asset class from trade_journal
            wr_rows = session.execute(text("""
                SELECT
                    CASE
                        WHEN symbol IN ('BTC','ETH','SOL','ADA','XRP','DOGE','AVAX','LINK','DOT','MATIC') THEN 'crypto'
                        WHEN symbol IN ('EURUSD','GBPUSD','USDJPY','AUDUSD','USDCAD','USDCHF','NZDUSD') THEN 'forex'
                        WHEN symbol IN ('GOLD','SILVER','OIL','NATGAS','COPPER') THEN 'commodity'
                        WHEN symbol IN ('SPX500','NSDQ100','DJ30','FTSE100','GER40') THEN 'index'
                        ELSE 'stock'
                    END as asset_class,
                    COUNT(*) as trades,
                    COUNT(*) FILTER (WHERE pnl > 0) as wins
                FROM trade_journal
                WHERE exit_time IS NOT NULL
                GROUP BY 1
            """)).fetchall()

            # Get strategy count by asset class
            strat_rows = session.execute(text("""
                SELECT
                    CASE
                        WHEN symbols::text LIKE '%BTC%' OR symbols::text LIKE '%ETH%' THEN 'crypto'
                        WHEN symbols::text LIKE '%USD%' AND LENGTH(symbols::text) < 30 THEN 'forex'
                        WHEN symbols::text LIKE '%GOLD%' OR symbols::text LIKE '%OIL%' THEN 'commodity'
                        WHEN symbols::text LIKE '%SPX%' OR symbols::text LIKE '%NSDQ%' THEN 'index'
                        ELSE 'stock'
                    END as asset_class,
                    COUNT(*) as strat_count
                FROM strategies WHERE status IN ('BACKTESTED','PAPER')
                GROUP BY 1
            """)).fetchall()
        finally:
            session.close()

        total_strats = sum(r[1] for r in strat_rows) or 1
        strat_map = {r[0]: r[1] for r in strat_rows}

        findings = []
        for row in wr_rows:
            if row[1] < 10:
                continue
            wr = row[2] / row[1]
            if wr < 0.60:
                continue
            strat_count = strat_map.get(row[0], 0)
            strat_pct = strat_count / total_strats * 100
            if strat_pct >= 15:
                continue

            evidence = f"Asset class: {row[0]}\nLive win rate: {wr*100:.1f}%\nTrades: {row[1]}\nActive strategies: {strat_count} ({strat_pct:.1f}% of total)"
            findings.append(Finding(
                check_id="G2",
                key=f"underweighted_asset_class:{row[0]}",
                category="G",
                severity="opportunity",
                title=f"G2: {row[0]} — {wr*100:.0f}% live WR but only {strat_pct:.0f}% of strategies",
                detail=f"High-performing asset class is underweighted in the strategy library. {row[0]} has {wr*100:.0f}% live win rate but only {strat_pct:.0f}% of active strategies.",
                evidence=evidence,
                recommended_action="Increase proposal quota for this class in strategy_proposer or raise asset tradability score.",
                context_links=[{"label": "Strategies", "url": "/strategies"}],
                ask_kiro_prompt=f'Intel finding [G2]: "{row[0]} — {wr*100:.0f}% live WR but only {strat_pct:.0f}% of strategies."\n\nEvidence: {evidence}\n\nRecommended action: Increase proposal quota for {row[0]}.',
            ))
        return findings if findings else None

    def _check_g3_missed_alpha(self, lookback_days: int) -> Optional[List[Finding]]:
        try:
            from src.analytics.observability import per_symbol_opportunity_cost
            results = per_symbol_opportunity_cost(lookback_days=lookback_days)
        except Exception:
            return None

        if not results:
            return None

        # Top 5 missed alpha symbols
        top = [r for r in results if r.get("opportunity_cost_pct", 0) > 10][:5]
        if not top:
            return None

        findings = []
        for r in top:
            evidence = (
                f"Symbol: {r['symbol']}\n"
                f"Forward return: {r['symbol_fwd_return_pct']:.1f}%\n"
                f"Captured: {r['captured_pct']:.1f}%\n"
                f"Opportunity cost: {r['opportunity_cost_pct']:.1f}%\n"
                f"Trades: {r['trades']}"
            )
            findings.append(Finding(
                check_id="G3",
                key=f"missed_alpha:{r['symbol']}",
                category="G",
                severity="opportunity",
                title=f"G3: {r['symbol']} — {r['opportunity_cost_pct']:.0f}% missed alpha",
                detail=f"{r['symbol']} moved {r['symbol_fwd_return_pct']:.1f}% but we only captured {r['captured_pct']:.1f}%. System is not trading this symbol effectively.",
                evidence=evidence,
                recommended_action="Check rejection blacklist and WF cache for this symbol. May be locked out by performance feedback loop.",
                context_links=[{"label": "Research / Attribution", "url": "/research/attribution"}],
                ask_kiro_prompt=f'Intel finding [G3]: "{r["symbol"]} — {r["opportunity_cost_pct"]:.0f}% missed alpha."\n\nEvidence: {evidence}\n\nRecommended action: Check rejection blacklist and WF cache for {r["symbol"]}.',
            ))
        return findings if findings else None

    def _check_g5_live_sharpe_divergence(self, lookback_days: int) -> Optional[List[Finding]]:
        try:
            from src.analytics.observability import wf_live_divergence
            alerts = wf_live_divergence(min_live_trades=10)
        except Exception:
            return None

        if not alerts:
            return None

        findings = []
        for a in alerts[:5]:  # top 5 divergences
            evidence = (
                f"Strategy: {a['name']}\n"
                f"WF Sharpe: {a['wf_test_sharpe']}\n"
                f"Live Sharpe: {a['live_sharpe']}\n"
                f"Divergence: {a['divergence']}\n"
                f"Live trades: {a['live_trades']}"
            )
            findings.append(Finding(
                check_id="G5",
                key=f"strategy:{a['strategy_id']}",
                category="G",
                severity="P2",
                title=f"G5: {a['name']} — live Sharpe {a['live_sharpe']} vs WF {a['wf_test_sharpe']} (divergence {a['divergence']})",
                detail="Strategy's live performance diverges significantly from WF test Sharpe. Edge may not be translating or regime has changed.",
                evidence=evidence,
                recommended_action="Consider retiring strategy. Check if market regime has changed since WF validation period.",
                context_links=[{"label": "Strategies", "url": "/strategies"}, {"label": "Research / Attribution", "url": "/research/attribution"}],
                ask_kiro_prompt=f'Intel finding [G5]: "{a["name"]} — live Sharpe {a["live_sharpe"]} vs WF {a["wf_test_sharpe"]}."\n\nEvidence: {evidence}\n\nRecommended action: Consider retiring strategy.',
            ))
        return findings if findings else None

    def _check_g7_regime_template_loser(self, lookback_days: int) -> Optional[List[Finding]]:
        try:
            from src.analytics.observability import regime_template_pnl_matrix
            result = regime_template_pnl_matrix(lookback_days=lookback_days)
        except Exception:
            return None

        cells = result.get("cells", [])
        losers = [c for c in cells if c.get("trades", 0) >= 10 and c.get("win_rate", 1) < 0.30]

        if not losers:
            return None

        findings = []
        for c in losers[:5]:
            evidence = (
                f"Regime: {c['regime']}\n"
                f"Template: {c['template']}\n"
                f"Direction: {c['direction']}\n"
                f"Trades: {c['trades']}\n"
                f"Win rate: {c['win_rate']*100:.0f}%\n"
                f"Total P&L: ${c['total_pnl']:.2f}"
            )
            findings.append(Finding(
                check_id="G7",
                key=f"regime_template:{c['regime']}:{c['template']}:{c['direction']}",
                category="G",
                severity="opportunity",
                title=f"G7: {c['template']} {c['direction']} in {c['regime']} — {c['win_rate']*100:.0f}% WR ({c['trades']} trades)",
                detail="This template/regime/direction combination is a systematic loser. Should be suppressed in this regime.",
                evidence=evidence,
                recommended_action="Add to regime suppression list in strategy_proposer.",
                context_links=[{"label": "Research / Regime", "url": "/research/regime"}],
                ask_kiro_prompt=f'Intel finding [G7]: "{c["template"]} {c["direction"]} in {c["regime"]} — {c["win_rate"]*100:.0f}% WR."\n\nEvidence: {evidence}\n\nRecommended action: Add to regime suppression list.',
            ))
        return findings if findings else None

    def _check_g9_extreme_degradation(self, lookback_days: int) -> Optional[List[Finding]]:
        from sqlalchemy import text
        session = self.db.get_session()
        try:
            rows = session.execute(text("""
                SELECT id, name,
                       (strategy_metadata->>'wf_performance_degradation')::float as deg,
                       (strategy_metadata->>'wf_test_sharpe')::float as test_s,
                       (strategy_metadata->>'wf_train_sharpe')::float as train_s,
                       COALESCE((backtest_results->>'total_trades')::int, 0) as trades
                FROM strategies WHERE status IN ('BACKTESTED','PAPER')
                AND (strategy_metadata->>'wf_performance_degradation') IS NOT NULL
                AND (strategy_metadata->>'wf_performance_degradation')::float < -1000
                AND COALESCE((backtest_results->>'total_trades')::int, 0) >= 8
                AND (strategy_metadata->>'wf_train_sharpe')::float > 0
            """)).fetchall()
        finally:
            session.close()

        if not rows:
            return None

        findings = []
        for row in rows:
            evidence = f"Strategy: {row[1]}\nDegradation: {row[2]:.0f}%\nWF test Sharpe: {row[3]:.2f}\nWF train Sharpe: {row[4]:.2f}\nTrades: {row[5]}"
            findings.append(Finding(
                check_id="G9",
                key=f"strategy:{row[0]}",
                category="G",
                severity="P2",
                title=f"G9: {row[1]} — extreme degradation {row[2]:.0f}% (regime luck)",
                detail="Extreme WF performance degradation with sufficient trade count and positive train Sharpe indicates the strategy captured a single regime event. Test Sharpe is 11x+ above train Sharpe.",
                evidence=evidence,
                recommended_action="Consider retiring or requiring re-validation with stricter consistency gate: (test_sharpe - train_sharpe) ≤ 1.5.",
                context_links=[{"label": "Strategies", "url": "/strategies"}],
                ask_kiro_prompt=f'Intel finding [G9]: "{row[1]} — extreme degradation {row[2]:.0f}%."\n\nEvidence: {evidence}\n\nRecommended action: Consider retiring strategy.',
            ))
        return findings if findings else None

    # ═══════════════════════════════════════════════════════════════════════════
    # Category H — Config & Code Integrity
    # ═══════════════════════════════════════════════════════════════════════════

    def _check_h1_config_code_divergence(self, lookback_days: int) -> Optional[Finding]:
        issues = []

        # Check atr_sl_multiplier in YAML vs hardcoded 1.5 in order_executor
        try:
            import yaml
            yaml_path = "/home/ubuntu/alphacent/config/autonomous_trading.yaml"
            if os.path.exists(yaml_path):
                with open(yaml_path) as f:
                    cfg = yaml.safe_load(f)
                yaml_val = cfg.get("risk", {}).get("atr_sl_multiplier")
                if yaml_val is not None and float(yaml_val) != 1.5:
                    issues.append(f"atr_sl_multiplier: YAML={yaml_val}, code=1.5 (order_executor.py:241)")
        except Exception:
            pass

        if not issues:
            return None

        evidence = "\n".join(issues)
        return Finding(
            check_id="H1",
            key="config_code_divergence",
            category="H",
            severity="P2",
            title=f"H1: Config/code divergence detected ({len(issues)} issue(s))",
            detail="Config values in autonomous_trading.yaml do not match hardcoded values in code. Dead config creates false confidence.",
            evidence=evidence,
            recommended_action="Either wire config to code or remove dead config key. atr_sl_multiplier is hardcoded at 1.5 in order_executor.py:241.",
            context_links=[{"label": "Settings", "url": "/settings"}],
            ask_kiro_prompt=f'Intel finding [H1]: "Config/code divergence detected."\n\nEvidence: {evidence}\n\nRecommended action: Wire config to code or remove dead config key.',
        )

    def _check_h3_graduation_min_trades_low(self, lookback_days: int) -> Optional[Finding]:
        try:
            import yaml
            yaml_path = "/home/ubuntu/alphacent/config/autonomous_trading.yaml"
            if not os.path.exists(yaml_path):
                return None
            with open(yaml_path) as f:
                cfg = yaml.safe_load(f)
            val = cfg.get("graduation_gate", {}).get("min_trades")
            if val is None or int(val) >= 20:
                return None
        except Exception:
            return None

        evidence = f"graduation_gate.min_trades: {val} (intended: 20)\nNote: was lowered to {val} to enable GOOGL test graduation."
        return Finding(
            check_id="H3",
            key="graduation_min_trades_low",
            category="H",
            severity="P2",
            title=f"H3: graduation_gate.min_trades={val} (should be 20)",
            detail=f"min_trades was lowered to {val} to enable GOOGL test graduation. Should be raised back to 20 now that live system is stable.",
            evidence=evidence,
            recommended_action="Raise graduation_gate.min_trades back to 20 via Settings UI or direct YAML edit on EC2.",
            context_links=[{"label": "Settings", "url": "/settings"}],
            ask_kiro_prompt=f'Intel finding [H3]: "graduation_gate.min_trades={val} (should be 20)."\n\nEvidence: {evidence}\n\nRecommended action: Raise min_trades to 20 in Settings.',
        )

    def _check_h4_paper_conviction_threshold(self, lookback_days: int) -> Optional[Finding]:
        try:
            import yaml
            yaml_path = "/home/ubuntu/alphacent/config/autonomous_trading.yaml"
            if not os.path.exists(yaml_path):
                return None
            with open(yaml_path) as f:
                cfg = yaml.safe_load(f)
            # Check paper conviction threshold
            val = (
                cfg.get("alpha_edge", {}).get("min_conviction_score")
                or cfg.get("conviction", {}).get("paper_threshold")
            )
            if val is None or int(val) >= 73:
                return None
        except Exception:
            return None

        evidence = f"Paper conviction threshold: {val} (was 73, lowered on 2026-05-14)\nLive threshold: 73 (unchanged)"
        return Finding(
            check_id="H4",
            key="paper_conviction_threshold",
            category="H",
            severity="P2",
            title=f"H4: Paper conviction threshold at {val} (temporarily lowered from 73)",
            detail=f"Paper conviction threshold was lowered to {val} to enable more paper trades. Monitor 70-72 band performance.",
            evidence=evidence,
            recommended_action="Monitor 70-72 band performance. If win rate holds after 15+ trades per strategy, threshold is correctly calibrated. If WR <50%, raise back to 73.",
            context_links=[{"label": "Settings", "url": "/settings"}],
            ask_kiro_prompt=f'Intel finding [H4]: "Paper conviction threshold at {val} (temporarily lowered from 73)."\n\nEvidence: {evidence}\n\nRecommended action: Monitor 70-72 band performance and decide whether to raise back to 73.',
        )
