import { useNavigate } from 'react-router-dom'
import { AlertTriangle, ChevronRight } from 'lucide-react'
import { StatTile } from '@/components/primitives'
import { PanelHeader, SectionLabel } from '@/components/layout'
import { SignalFeed } from '@/components/trading/SignalFeed'
import { OrderFillsTicker } from '@/components/trading/OrderFillsTicker'
import { cn, formatAge } from '@/lib/utils'
import {
  useIntelSummary,
  useIntelFindings,
  severityColor,
  severityBg,
} from '@/pages/intel/useIntelData'
import { useRiskMetrics, riskScoreColor } from '@/pages/guard/useGuardData'

/**
 * "What needs a human now" — the cross-stage attention rail. Aggregates the
 * highest-severity Intel findings, live risk-limit reasons, and (below the
 * fold) the real-time signal + fill feeds. Self-contained: every hook here is
 * shared/deduped with the Intel and Guard pages.
 */
export function AttentionRail({ className, showFeeds = true }: { className?: string; showFeeds?: boolean }) {
  const navigate = useNavigate()
  const summary = useIntelSummary()
  const findings = useIntelFindings({ status: 'open' })
  const liveRisk = useRiskMetrics('LIVE')

  const s = summary.data
  const priority = (findings.data ?? [])
    .filter((f) => f.severity === 'P0' || f.severity === 'P1')
    .sort((a, b) => (a.severity === 'P0' ? -1 : 1) - (b.severity === 'P0' ? -1 : 1))
    .slice(0, 6)

  const riskReasons = liveRisk.data?.risk_reasons ?? []
  const riskScore = liveRisk.data?.risk_score

  return (
    <div className={cn('flex h-full min-h-0 flex-col bg-[var(--bg-0)]', className)}>
      <div className="flex items-center gap-1.5 px-3 py-2 border-b border-[var(--border-default)]">
        <AlertTriangle className="h-3.5 w-3.5 text-[var(--status-warning)]" />
        <span className="text-[11px] font-semibold uppercase tracking-wider text-[var(--text-1)]">
          Needs attention
        </span>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto">
        {/* Severity summary */}
        <div className="grid grid-cols-3 gap-2 p-2">
          <StatTile
            layout="value-top"
            size="lg"
            label="P0"
            value={s?.p0_open ?? 0}
            valueColor="var(--pnl-down)"
            bg={(s?.p0_open ?? 0) > 0 ? 'rgba(239,68,68,0.10)' : undefined}
            pulseValue={(s?.p0_open ?? 0) > 0}
            onClick={() => navigate('/intel')}
          />
          <StatTile
            layout="value-top"
            size="lg"
            label="P1"
            value={s?.p1_open ?? 0}
            valueColor="var(--status-warning)"
            bg={(s?.p1_open ?? 0) > 0 ? 'rgba(245,158,11,0.10)' : undefined}
            onClick={() => navigate('/intel')}
          />
          <StatTile
            layout="value-top"
            size="lg"
            label="Opps"
            value={s?.opportunities_open ?? 0}
            valueColor="var(--accent-primary)"
            onClick={() => navigate('/intel')}
          />
        </div>

        {/* Live risk breaches */}
        {riskScore && riskScore !== 'safe' && riskReasons.length > 0 && (
          <div className="px-2 pb-2">
            <SectionLabel>Live risk</SectionLabel>
            <div
              className="rounded-[3px] border p-2 space-y-1"
              style={{
                borderColor: `color-mix(in oklab, ${riskScoreColor(riskScore)} 40%, transparent)`,
                background: `color-mix(in oklab, ${riskScoreColor(riskScore)} 6%, var(--bg-1))`,
              }}
            >
              {riskReasons.slice(0, 4).map((reason, i) => (
                <div key={i} className="flex items-start gap-1.5 text-[10px] text-[var(--text-1)]">
                  <span className="mt-[3px] h-1.5 w-1.5 shrink-0 rounded-full" style={{ background: riskScoreColor(riskScore) }} />
                  <span>{reason}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Priority findings */}
        <div className="px-2 pb-2">
          <SectionLabel>Top findings</SectionLabel>
          {findings.isLoading ? (
            <div className="h-16 animate-pulse rounded-[3px] bg-[var(--bg-1)]" />
          ) : priority.length === 0 ? (
            <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 text-[10px] text-[var(--text-3)]">
              No P0/P1 findings open. System calm.
            </div>
          ) : (
            <div className="space-y-1">
              {priority.map((f) => (
                <button
                  key={f.id}
                  type="button"
                  onClick={() => navigate('/intel')}
                  className="flex w-full items-start gap-2 rounded-[3px] border border-[var(--border-subtle)] p-2 text-left hover:bg-[var(--bg-hover)] transition-colors"
                  style={{ background: severityBg(f.severity) }}
                >
                  <span
                    className="mt-0.5 rounded-[2px] px-1 text-[9px] font-bold"
                    style={{ color: severityColor(f.severity), background: 'var(--bg-0)' }}
                  >
                    {f.severity}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-[11px] text-[var(--text-0)]">{f.title}</span>
                    <span className="text-[9px] text-[var(--text-3)] mono">
                      {formatAge(f.last_seen ?? f.first_seen)}
                      {f.occurrence_count > 1 && ` · ×${f.occurrence_count}`}
                    </span>
                  </span>
                  <ChevronRight className="h-3 w-3 shrink-0 text-[var(--text-3)]" />
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Live activity feeds (follow the active account toggle) */}
        {showFeeds && (
          <div className="border-t border-[var(--border-subtle)]">
            <div className="h-[240px]">
              <PanelHeader title="Signals">
                <SignalFeed />
              </PanelHeader>
            </div>
            <div className="h-[240px] border-t border-[var(--border-subtle)]">
              <PanelHeader title="Fills · slippage">
                <OrderFillsTicker />
              </PanelHeader>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
