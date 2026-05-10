import { useEffect, useMemo, useState } from 'react'
import {
  ChevronLeft,
  ChevronRight,
  FileText,
  GraduationCap,
  Gauge,
  LineChart,
  Settings,
  X,
} from 'lucide-react'
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  Skeleton,
  Tabs,
  TabsList,
  TabsTrigger,
  TabsContent,
} from '@/components/primitives'
import { ConvictionBar, type ConvictionComponents } from '@/components/trading/ConvictionBar'
import { RegimePill } from '@/components/trading/RegimePill'
import { PnLNumber } from '@/components/trading/PnLNumber'
import { classifyError } from '@/lib/errors'
import {
  formatCurrency,
  formatPercentage,
  formatTimestamp,
} from '@/lib/utils'
import {
  useStrategy,
  type StrategyRow,
  type WalkForwardResults,
  type StrategyReasoning,
} from '../useStrategiesData'

/* ──────────────────────────────────────────────────────────────────────
 *  Entry point — the right-hand rail inside LibraryTab. Fetches the full
 *  strategy payload (rules, reasoning, walk-forward results) lazily when
 *  a row is selected; the table itself uses slim payloads.
 * ────────────────────────────────────────────────────────────────────── */

type DetailSubTab = 'evidence' | 'reasoning' | 'conviction' | 'live' | 'config'

const SUB_TABS: Array<{ value: DetailSubTab; label: string; icon: React.ComponentType<{ className?: string }> }> = [
  { value: 'evidence', label: 'Evidence', icon: LineChart },
  { value: 'reasoning', label: 'Reasoning', icon: FileText },
  { value: 'conviction', label: 'Conviction', icon: Gauge },
  { value: 'live', label: 'Live', icon: GraduationCap },
  { value: 'config', label: 'Config', icon: Settings },
]

interface StrategyDetailPanelProps {
  strategyId: string
  onClose: () => void
  onAction: (
    action: 'activate' | 'deactivate' | 'retire' | 'delete-permanent' | 'backtest',
    row: StrategyRow,
  ) => void
  /** External subtab binding — allows keyboard [/] cycling from the parent. */
  subTab?: DetailSubTab
  onSubTabChange?: (tab: DetailSubTab) => void
}

export function StrategyDetailPanel({
  strategyId,
  onClose,
  onAction,
  subTab,
  onSubTabChange,
}: StrategyDetailPanelProps) {
  const query = useStrategy(strategyId)
  const [internalSub, setInternalSub] = useState<DetailSubTab>('evidence')
  const activeSub = subTab ?? internalSub
  const setSub = onSubTabChange ?? setInternalSub

  // When the strategy id changes, reset to the default tab unless controlled.
  useEffect(() => {
    if (!onSubTabChange) setInternalSub('evidence')
  }, [strategyId, onSubTabChange])

  if (query.isLoading) {
    return (
      <div className="flex flex-col h-full bg-[var(--bg-1)]">
        <div className="px-3 py-2 border-b border-[var(--border-subtle)]">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-3 w-24 mt-1" />
        </div>
        <div className="p-3 space-y-2">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-32 w-full" />
        </div>
      </div>
    )
  }

  if (query.isError) {
    const info = classifyError(query.error, 'strategy detail')
    return (
      <div className="flex flex-col h-full bg-[var(--bg-1)]">
        <DetailHeader onClose={onClose} title="Strategy detail" />
        <ErrorState title="Couldn't load strategy" message={info.message} onRetry={() => query.refetch()} />
      </div>
    )
  }

  const strategy = query.data
  if (!strategy) {
    return (
      <div className="flex flex-col h-full bg-[var(--bg-1)]">
        <DetailHeader onClose={onClose} title="Strategy detail" />
        <EmptyState title="Strategy not found" description="This strategy may have been retired. Refresh the library." />
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full min-h-0 bg-[var(--bg-1)] border-l border-[var(--border-subtle)]">
      <DetailHeaderWithStrategy
        strategy={strategy}
        onClose={onClose}
        onAction={onAction}
      />

      <Tabs
        value={activeSub}
        onValueChange={(v) => setSub(v as DetailSubTab)}
        className="flex flex-col flex-1 min-h-0"
      >
        <TabsList
          variant="pills"
          className="shrink-0 mx-3 my-2 overflow-x-auto flex-nowrap"
        >
          {SUB_TABS.map((t) => (
            <TabsTrigger key={t.value} value={t.value} variant="pills">
              <t.icon className="h-3 w-3" />
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
        <div className="flex-1 min-h-0 overflow-auto">
          <TabsContent value="evidence" className="m-0 p-3 data-[state=inactive]:hidden">
            <EvidenceTab strategy={strategy} />
          </TabsContent>
          <TabsContent value="reasoning" className="m-0 p-3 data-[state=inactive]:hidden">
            <ReasoningTab strategy={strategy} />
          </TabsContent>
          <TabsContent value="conviction" className="m-0 p-3 data-[state=inactive]:hidden">
            <ConvictionTab strategy={strategy} />
          </TabsContent>
          <TabsContent value="live" className="m-0 p-3 data-[state=inactive]:hidden">
            <LiveTab strategy={strategy} />
          </TabsContent>
          <TabsContent value="config" className="m-0 p-3 data-[state=inactive]:hidden">
            <ConfigTab strategy={strategy} />
          </TabsContent>
        </div>
      </Tabs>
    </div>
  )
}

/* ─────────────────────────── header ─────────────────────────── */

function DetailHeader({ title, onClose }: { title: string; onClose: () => void }) {
  return (
    <div className="shrink-0 px-3 py-2 border-b border-[var(--border-subtle)] flex items-center gap-2">
      <h2 className="text-[13px] font-semibold text-[var(--text-0)] truncate">{title}</h2>
      <Button
        variant="ghost"
        size="icon-sm"
        onClick={onClose}
        aria-label="Close detail panel"
        className="ml-auto"
      >
        <X className="h-3.5 w-3.5" />
      </Button>
    </div>
  )
}

function DetailHeaderWithStrategy({
  strategy,
  onClose,
  onAction,
}: {
  strategy: StrategyRow
  onClose: () => void
  onAction: StrategyDetailPanelProps['onAction']
}) {
  const conviction = strategy.metadata?.conviction_score
  const status = strategy.status
  const statusVariant =
    status === 'LIVE'
      ? 'live'
      : status === 'PAPER' || status === 'DEMO'
        ? 'paper'
        : status === 'BACKTESTED'
          ? 'backtested'
          : status === 'RETIRED'
            ? 'retired'
            : 'info'
  return (
    <div className="shrink-0 px-3 py-2 border-b border-[var(--border-subtle)]">
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 mb-1 flex-wrap">
            <Badge variant={statusVariant} size="sm">
              {status === 'DEMO' ? 'PAPER' : status}
            </Badge>
            {strategy.strategy_category && (
              <Badge variant="muted" size="sm">
                {strategy.strategy_category.replace(/_/g, ' ')}
              </Badge>
            )}
            {strategy.market_regime && (
              <RegimePill regime={strategy.market_regime} size="sm" showConfidence={false} />
            )}
          </div>
          <h2
            className="text-[13px] font-semibold text-[var(--text-0)] leading-tight truncate"
            title={strategy.name}
          >
            {strategy.name}
          </h2>
          <div className="text-[10px] text-[var(--text-3)] mt-0.5 truncate" title={strategy.description}>
            {strategy.template_name && <span className="mono">{strategy.template_name}</span>}
            {strategy.template_name && ' · '}
            <span>
              Created {formatTimestamp(strategy.created_at, 'date')}
            </span>
            {strategy.activated_at && <> · Activated {formatTimestamp(strategy.activated_at, 'date')}</>}
          </div>
        </div>
        {conviction != null && (
          <div className="flex flex-col items-end shrink-0 px-2 py-1 rounded-[3px] bg-[var(--bg-2)] border border-[var(--border-subtle)]">
            <div className="text-[9px] uppercase tracking-wide text-[var(--text-3)]">
              Conviction
            </div>
            <div className="mono tabular-nums text-[18px] font-semibold text-[var(--text-0)]">
              {conviction.toFixed(0)}
            </div>
          </div>
        )}
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={onClose}
          aria-label="Close detail panel"
        >
          <X className="h-3.5 w-3.5" />
        </Button>
      </div>

      {/* Action bar */}
      <div className="flex items-center gap-1 mt-2 flex-wrap">
        {status === 'BACKTESTED' && (
          <Button variant="primary" size="sm" onClick={() => onAction('activate', strategy)}>
            Activate
          </Button>
        )}
        {(status === 'PAPER' || status === 'LIVE' || status === 'DEMO') && (
          <Button variant="secondary" size="sm" onClick={() => onAction('deactivate', strategy)}>
            Deactivate
          </Button>
        )}
        {status === 'PROPOSED' && (
          <Button variant="primary" size="sm" onClick={() => onAction('backtest', strategy)}>
            Run backtest
          </Button>
        )}
        {status !== 'RETIRED' && (
          <Button variant="ghost" size="sm" onClick={() => onAction('retire', strategy)}>
            Retire
          </Button>
        )}
        {status === 'RETIRED' && (
          <Button
            variant="destructive"
            size="sm"
            onClick={() => onAction('delete-permanent', strategy)}
          >
            Permanently delete
          </Button>
        )}
      </div>
    </div>
  )
}

/* ─────────────────────────── Evidence tab ─────────────────────────── */

function EvidenceTab({ strategy }: { strategy: StrategyRow }) {
  const wf = strategy.walk_forward_results ?? null
  const regimeDist = useMemo(() => buildRegimeDistribution(wf), [wf])
  const pm = strategy.performance_metrics

  return (
    <div className="flex flex-col gap-3">
      {/* Headline backtest metrics */}
      <section>
        <SectionLabel>Backtest summary</SectionLabel>
        <div className="grid grid-cols-3 gap-2">
          <MetricTile
            label="Sharpe"
            value={pm?.sharpe_ratio?.toFixed(2) ?? '—'}
            color={sharpeColor(pm?.sharpe_ratio)}
          />
          <MetricTile
            label="Return"
            value={
              pm?.total_return != null
                ? formatPercentage(pm.total_return * 100, { precision: 1, signed: true })
                : '—'
            }
            color={pnlColor(pm?.total_return)}
          />
          <MetricTile
            label="Max DD"
            value={pm?.max_drawdown != null ? `${(pm.max_drawdown * 100).toFixed(1)}%` : '—'}
            color="var(--pnl-down)"
          />
          <MetricTile
            label="Win rate"
            value={pm?.win_rate != null ? `${(pm.win_rate * 100).toFixed(0)}%` : '—'}
            color="var(--text-1)"
          />
          <MetricTile label="Trades" value={String(pm?.total_trades ?? 0)} color="var(--text-1)" />
          <MetricTile
            label="Sortino"
            value={pm?.sortino_ratio?.toFixed(2) ?? '—'}
            color="var(--text-1)"
          />
        </div>
      </section>

      {/* Walk-forward */}
      <section>
        <SectionLabel>Walk-forward</SectionLabel>
        {wf ? (
          <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-2)] overflow-hidden">
            <table className="w-full text-[11px]">
              <thead className="text-[9px] uppercase tracking-wide text-[var(--text-3)]">
                <tr className="border-b border-[var(--border-subtle)]">
                  <th className="text-left px-2 py-1 font-medium">Metric</th>
                  <th className="text-right px-2 py-1 font-medium">Train</th>
                  <th className="text-right px-2 py-1 font-medium">Test</th>
                  <th className="text-right px-2 py-1 font-medium">Δ</th>
                </tr>
              </thead>
              <tbody className="mono">
                <WFRow label="Sharpe" train={wf.train_sharpe} test={wf.test_sharpe} fmt={(v) => v.toFixed(2)} />
                <WFRow
                  label="Return"
                  train={wf.train_return}
                  test={wf.test_return}
                  fmt={(v) => `${(v * 100).toFixed(1)}%`}
                />
                <WFRow
                  label="Max DD"
                  train={wf.train_max_drawdown}
                  test={wf.test_max_drawdown}
                  fmt={(v) => `${(v * 100).toFixed(1)}%`}
                  invertDelta
                />
                <WFRow
                  label="Win rate"
                  train={wf.train_win_rate}
                  test={wf.test_win_rate}
                  fmt={(v) => `${(v * 100).toFixed(0)}%`}
                />
                <WFRow
                  label="Trades"
                  train={wf.train_trades}
                  test={wf.test_trades}
                  fmt={(v) => String(Math.round(v))}
                />
              </tbody>
            </table>
            {typeof wf.consistency_score === 'number' && (
              <div className="px-2 py-1.5 border-t border-[var(--border-subtle)] flex items-center gap-2">
                <span className="text-[10px] uppercase tracking-wide text-[var(--text-3)]">
                  Consistency
                </span>
                <div className="flex-1 h-1 rounded-[1px] bg-[var(--bg-0)] overflow-hidden">
                  <div
                    className="h-full"
                    style={{
                      width: `${Math.min(100, Math.max(0, wf.consistency_score))}%`,
                      backgroundColor: consistencyColor(wf.consistency_score),
                    }}
                  />
                </div>
                <span className="mono tabular-nums text-[11px] text-[var(--text-1)]">
                  {wf.consistency_score.toFixed(0)}
                </span>
              </div>
            )}
          </div>
        ) : (
          <EmptyState title="No walk-forward data" description="This strategy hasn't been validated via walk-forward yet." className="py-4" />
        )}
      </section>

      {/* Monte Carlo */}
      {wf?.bootstrap && (
        <section>
          <SectionLabel>Monte Carlo bootstrap</SectionLabel>
          <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-2)] px-2 py-1.5">
            <div className="grid grid-cols-3 gap-2 mb-2">
              <BootstrapTile label="p5" value={wf.bootstrap.p5} />
              <BootstrapTile label="p50" value={wf.bootstrap.p50} />
              <BootstrapTile label="p95" value={wf.bootstrap.p95} />
            </div>
            {wf.bootstrap.p5 != null && wf.bootstrap.p95 != null && (
              <BootstrapRibbon
                p5={wf.bootstrap.p5}
                p50={wf.bootstrap.p50 ?? (wf.bootstrap.p5 + wf.bootstrap.p95) / 2}
                p95={wf.bootstrap.p95}
              />
            )}
            <div className="text-[10px] text-[var(--text-3)] mt-1.5">
              {wf.bootstrap.samples ? `${wf.bootstrap.samples.toLocaleString('en-US')} resamples` : 'Confidence band from resampled trade P&L'}
            </div>
          </div>
        </section>
      )}

      {/* Regime distribution */}
      {regimeDist.length > 0 && (
        <section>
          <SectionLabel>Trades by regime</SectionLabel>
          <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-2)] p-2">
            <div className="flex flex-col gap-1">
              {regimeDist.map((r) => (
                <div key={r.regime} className="flex items-center gap-2 text-[11px]">
                  <span className="w-[120px] text-[var(--text-2)] truncate" title={r.regime}>
                    {r.regime.replace(/_/g, ' ')}
                  </span>
                  <div className="flex-1 h-1.5 rounded-[1px] bg-[var(--bg-0)] overflow-hidden">
                    <div
                      className="h-full"
                      style={{
                        width: `${r.percent * 100}%`,
                        backgroundColor: r.netPnl >= 0 ? 'var(--pnl-up)' : 'var(--pnl-down)',
                      }}
                    />
                  </div>
                  <span className="mono tabular-nums w-[40px] text-right text-[var(--text-1)]">
                    {r.count}
                  </span>
                  <span className="mono tabular-nums w-[80px] text-right">
                    <PnLNumber value={r.netPnl} format="currency" precision={0} size="sm" />
                  </span>
                </div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* Transaction cost reminder */}
      {strategy.requires_fundamental_data && (
        <div className="rounded-[3px] border border-[var(--status-warning)]/30 bg-[color-mix(in_oklab,var(--status-warning)_10%,transparent)] px-2 py-1.5 text-[10px] text-[var(--status-warning)]">
          Requires fundamental data — signals may be gated by FMP data freshness.
        </div>
      )}
    </div>
  )
}

interface RegimeBucket {
  regime: string
  count: number
  percent: number
  netPnl: number
}

function buildRegimeDistribution(wf: WalkForwardResults | null): RegimeBucket[] {
  if (!wf?.trades || wf.trades.length === 0) return []
  const buckets = new Map<string, { count: number; netPnl: number }>()
  for (const t of wf.trades) {
    const regime = (t.regime || 'unknown').toLowerCase()
    const bucket = buckets.get(regime) ?? { count: 0, netPnl: 0 }
    bucket.count += 1
    bucket.netPnl += typeof t.pnl === 'number' ? t.pnl : 0
    buckets.set(regime, bucket)
  }
  const total = Array.from(buckets.values()).reduce((acc, b) => acc + b.count, 0)
  return Array.from(buckets.entries())
    .map(([regime, b]) => ({
      regime,
      count: b.count,
      percent: total > 0 ? b.count / total : 0,
      netPnl: b.netPnl,
    }))
    .sort((a, b) => b.count - a.count)
}

/* ─────────────────────────── Reasoning tab ─────────────────────────── */

function ReasoningTab({ strategy }: { strategy: StrategyRow }) {
  const r: StrategyReasoning | null = strategy.reasoning ?? null

  if (!r || (typeof r === 'object' && Object.keys(r).length === 0)) {
    return (
      <EmptyState
        title="No reasoning recorded"
        description="This strategy was not generated with an explicit hypothesis — the reasoning block is empty."
      />
    )
  }

  const hypothesis = r.hypothesis
  const alphaSources = normaliseAlphaSources(r.alpha_sources)
  const marketAssumptions = Array.isArray(r.market_assumptions) ? r.market_assumptions : []
  const signalLogic = typeof r.signal_logic === 'string' ? r.signal_logic : ''

  return (
    <div className="flex flex-col gap-3">
      {hypothesis && (
        <section>
          <SectionLabel>Hypothesis</SectionLabel>
          <p className="text-[12px] leading-relaxed text-[var(--text-1)] whitespace-pre-wrap">{hypothesis}</p>
        </section>
      )}

      {alphaSources.length > 0 && (
        <section>
          <SectionLabel>Alpha sources</SectionLabel>
          <div className="flex flex-col gap-1.5">
            {alphaSources.map((src, i) => {
              const weight = src.weight ?? 0
              return (
                <div key={`${src.source}-${i}`} className="flex items-center gap-2 text-[11px]">
                  <span className="w-[200px] text-[var(--text-1)] truncate" title={src.source}>
                    {src.source}
                  </span>
                  <div className="flex-1 h-1.5 rounded-[1px] bg-[var(--bg-2)] overflow-hidden">
                    <div
                      className="h-full bg-[var(--accent-primary)]"
                      style={{ width: `${Math.min(100, Math.max(0, weight * 100))}%` }}
                    />
                  </div>
                  <span className="mono tabular-nums w-[40px] text-right text-[var(--text-1)]">
                    {(weight * 100).toFixed(0)}%
                  </span>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {marketAssumptions.length > 0 && (
        <section>
          <SectionLabel>Market assumptions</SectionLabel>
          <ul className="list-disc list-inside space-y-1 text-[12px] text-[var(--text-1)]">
            {marketAssumptions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </section>
      )}

      {signalLogic && (
        <section>
          <SectionLabel>Signal logic</SectionLabel>
          <pre className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-2)] p-2 text-[11px] text-[var(--text-1)] overflow-x-auto mono whitespace-pre-wrap">
            {signalLogic}
          </pre>
        </section>
      )}

      {strategy.entry_rules && strategy.entry_rules.length > 0 && (
        <section>
          <SectionLabel>Entry rules</SectionLabel>
          <ul className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-2)] divide-y divide-[var(--border-subtle)]">
            {strategy.entry_rules.map((rule, i) => (
              <li key={i} className="px-2 py-1 mono text-[11px] text-[var(--text-1)]">
                {rule}
              </li>
            ))}
          </ul>
        </section>
      )}

      {strategy.exit_rules && strategy.exit_rules.length > 0 && (
        <section>
          <SectionLabel>Exit rules</SectionLabel>
          <ul className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-2)] divide-y divide-[var(--border-subtle)]">
            {strategy.exit_rules.map((rule, i) => (
              <li key={i} className="px-2 py-1 mono text-[11px] text-[var(--text-1)]">
                {rule}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  )
}

function normaliseAlphaSources(
  raw: StrategyReasoning['alpha_sources'],
): Array<{ source: string; weight?: number | null }> {
  if (!Array.isArray(raw)) return []
  return raw
    .map((entry) => {
      if (typeof entry === 'string') return { source: entry, weight: null }
      if (entry && typeof entry === 'object' && 'source' in entry) {
        return { source: String(entry.source), weight: entry.weight ?? null }
      }
      return null
    })
    .filter((e): e is { source: string; weight: number | null } => !!e)
}

/* ─────────────────────────── Conviction tab ─────────────────────────── */

function ConvictionTab({ strategy }: { strategy: StrategyRow }) {
  const score = strategy.metadata?.conviction_score
  const breakdown = strategy.metadata?.conviction_score_breakdown
  const isCrypto = (strategy.metadata?.asset_class || '').toLowerCase() === 'crypto'

  if (score == null) {
    return (
      <EmptyState
        title="No conviction score"
        description="Conviction scoring runs during the autonomous cycle — this strategy hasn't been scored yet."
      />
    )
  }

  const demoThreshold = 65
  const liveThreshold = isCrypto ? 68 : 74

  const components: ConvictionComponents | undefined = breakdown
    ? {
        wf_edge: breakdown.wf_edge ?? undefined,
        signal_quality: breakdown.signal_quality ?? undefined,
        regime_fit: breakdown.regime_fit ?? undefined,
        asset_tradability: breakdown.asset_tradability ?? undefined,
        fundamental: breakdown.fundamental ?? undefined,
        carry: breakdown.carry ?? undefined,
        crypto_cycle: breakdown.crypto_cycle ?? undefined,
        sentiment: breakdown.sentiment ?? undefined,
        factor: breakdown.factor ?? undefined,
      }
    : undefined

  return (
    <div className="flex flex-col gap-3">
      <section>
        <SectionLabel>Score</SectionLabel>
        <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-2)] p-3">
          <ConvictionBar
            score={score}
            components={components}
            size="large"
            threshold={liveThreshold}
            showValue
          />
          <div className="flex items-center gap-3 mt-2 text-[10px] text-[var(--text-3)]">
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-[1px] bg-[var(--text-3)]" />
              DEMO threshold {demoThreshold}
            </span>
            <span className="inline-flex items-center gap-1">
              <span className="h-2 w-[1px] bg-[var(--text-0)]" />
              LIVE threshold {liveThreshold}
              {isCrypto ? ' (crypto)' : ' (equity)'}
            </span>
          </div>
        </div>
      </section>

      {components && (
        <section>
          <SectionLabel>Breakdown</SectionLabel>
          <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-2)] overflow-hidden">
            <ComponentRow label="WF edge" value={components.wf_edge} max={40} color="var(--pnl-up)" />
            <ComponentRow label="Signal quality" value={components.signal_quality} max={25} color="var(--accent-primary)" />
            <ComponentRow label="Regime fit" value={components.regime_fit} max={20} color="var(--regime-up)" />
            <ComponentRow label="Asset tradability" value={components.asset_tradability} max={15} color="var(--accent-ticker)" />
            <ComponentRow label="Fundamental" value={components.fundamental} max={15} signed color="var(--accent-secondary)" />
            <ComponentRow label="Carry" value={components.carry} max={5} signed color="var(--status-warning)" />
            <ComponentRow label="Crypto cycle" value={components.crypto_cycle} max={5} signed color="var(--regime-vol)" />
            <ComponentRow label="Sentiment" value={components.sentiment} max={1} signed color="var(--text-2)" />
            <ComponentRow label="Factor" value={components.factor} max={6} signed color="var(--pnl-up-flash)" />
          </div>
        </section>
      )}

      {!components && (
        <div className="text-[11px] text-[var(--text-3)] rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-2)] p-2">
          Component breakdown not available — only the aggregate score was persisted.
        </div>
      )}
    </div>
  )
}

/* ─────────────────────────── Live tab ─────────────────────────── */

function LiveTab({ strategy }: { strategy: StrategyRow }) {
  const isLive = strategy.status === 'LIVE'
  const livePnl = strategy.metadata?.live_pnl ?? null
  const liveTrades = strategy.metadata?.live_trades ?? 0

  if (!isLive) {
    return (
      <EmptyState
        title="Not live-authorised"
        description="This strategy runs in paper mode only. Graduate a (template, symbol) pair via the Graduation tab to enable live fills."
      />
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <section>
        <SectionLabel>Live performance</SectionLabel>
        <div className="grid grid-cols-3 gap-2">
          <MetricTile
            label="Live P&L"
            value={formatCurrency(livePnl, { signed: true, precision: 0 })}
            color={pnlColor(livePnl)}
          />
          <MetricTile label="Live trades" value={String(liveTrades)} color="var(--text-1)" />
          <MetricTile
            label="vs Backtest"
            value={
              strategy.performance_metrics?.total_return != null
                ? formatPercentage(strategy.performance_metrics.total_return * 100, {
                    precision: 1,
                    signed: true,
                  })
                : '—'
            }
            color={pnlColor(strategy.performance_metrics?.total_return)}
          />
        </div>
      </section>

      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-2)] px-2 py-3 text-[11px] text-[var(--text-2)]">
        Per-trade MAE/MFE journal lands in Sprint 11 (Research → Journal). The Book → Live surface shows divergence vs paper Sharpe today.
      </div>
    </div>
  )
}

/* ─────────────────────────── Config tab ─────────────────────────── */

function ConfigTab({ strategy }: { strategy: StrategyRow }) {
  const risk = strategy.risk_params || {}
  const rows: Array<{ label: string; value: string }> = [
    { label: 'Allocation', value: `${(strategy.allocation_percent ?? 0).toFixed(2)}%` },
    {
      label: 'Allocated capital',
      value: strategy.allocated_capital != null
        ? formatCurrency(strategy.allocated_capital, { precision: 0 })
        : '—',
    },
    {
      label: 'Deployed capital',
      value:
        strategy.deployed_capital != null
          ? formatCurrency(strategy.deployed_capital, { precision: 0 })
          : '—',
    },
    ...Object.entries(risk).map(([k, v]) => ({
      label: k.replace(/_/g, ' '),
      value: formatRiskParam(k, Number(v)),
    })),
    { label: 'Source', value: strategy.source ?? strategy.metadata?.source ?? '—' },
    { label: 'Template', value: strategy.template_name ?? strategy.metadata?.template_name ?? '—' },
    {
      label: 'Regime',
      value:
        strategy.market_regime ??
        strategy.metadata?.market_regime ??
        strategy.metadata?.activation_regime ??
        '—',
    },
    { label: 'Interval', value: strategy.metadata?.interval ?? '—' },
    { label: 'Direction', value: strategy.metadata?.direction ?? '—' },
    { label: 'Strategy type', value: strategy.strategy_type ?? '—' },
    {
      label: 'Activated',
      value: strategy.activated_at ? formatTimestamp(strategy.activated_at) : '—',
    },
    {
      label: 'Retired',
      value: strategy.retired_at ? formatTimestamp(strategy.retired_at) : '—',
    },
  ]

  return (
    <div className="flex flex-col gap-3">
      <section>
        <SectionLabel>Configuration</SectionLabel>
        <dl className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-2)] divide-y divide-[var(--border-subtle)]">
          {rows.map((r) => (
            <div key={r.label} className="flex items-center gap-2 px-2 py-1 text-[11px]">
              <dt className="w-[160px] text-[var(--text-3)] uppercase tracking-wide text-[10px]">
                {r.label}
              </dt>
              <dd className="flex-1 mono text-[var(--text-1)] truncate" title={r.value}>
                {r.value}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      <section>
        <SectionLabel>Symbols ({strategy.symbols?.length ?? 0})</SectionLabel>
        <div className="flex flex-wrap gap-1">
          {(strategy.symbols ?? []).map((s) => (
            <span
              key={s}
              className="inline-flex items-center px-1.5 py-0.5 rounded-[2px] mono text-[10px] bg-[var(--bg-2)] text-[var(--text-1)] border border-[var(--border-subtle)]"
            >
              {s}
            </span>
          ))}
        </div>
      </section>

      <div className="text-[10px] text-[var(--text-3)]">
        Allocation and risk params are read-only for autonomous strategies. Modify via Settings → Autonomous or re-propose the strategy.
      </div>
    </div>
  )
}

function formatRiskParam(key: string, value: number): string {
  if (!Number.isFinite(value)) return '—'
  const lower = key.toLowerCase()
  if (lower.includes('pct') || lower.includes('percent') || lower === 'sl' || lower === 'tp') {
    return `${(value * 100).toFixed(2)}%`
  }
  if (Math.abs(value) < 1) return value.toFixed(4)
  return value.toFixed(2)
}

/* ─────────────────────────── Shared pieces ─────────────────────────── */

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)] mb-1.5">
      {children}
    </div>
  )
}

function MetricTile({
  label,
  value,
  color,
}: {
  label: string
  value: string
  color: string
}) {
  return (
    <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-2)] px-2 py-1.5">
      <div className="text-[9px] uppercase tracking-wide text-[var(--text-3)]">{label}</div>
      <div className="mono tabular-nums text-[14px] font-semibold mt-0.5" style={{ color }}>
        {value}
      </div>
    </div>
  )
}

function WFRow({
  label,
  train,
  test,
  fmt,
  invertDelta,
}: {
  label: string
  train: number | null | undefined
  test: number | null | undefined
  fmt: (v: number) => string
  invertDelta?: boolean
}) {
  const delta =
    typeof train === 'number' && typeof test === 'number' ? test - train : null
  const deltaPositive = delta != null && (invertDelta ? delta < 0 : delta > 0)
  const deltaNegative = delta != null && (invertDelta ? delta > 0 : delta < 0)
  return (
    <tr className="border-b border-[var(--border-subtle)] last:border-b-0">
      <td className="px-2 py-1 text-[var(--text-2)]">{label}</td>
      <td className="px-2 py-1 text-right tabular-nums text-[var(--text-1)]">
        {typeof train === 'number' ? fmt(train) : '—'}
      </td>
      <td className="px-2 py-1 text-right tabular-nums text-[var(--text-0)]">
        {typeof test === 'number' ? fmt(test) : '—'}
      </td>
      <td
        className="px-2 py-1 text-right tabular-nums"
        style={{
          color: deltaPositive
            ? 'var(--pnl-up)'
            : deltaNegative
              ? 'var(--pnl-down)'
              : 'var(--text-3)',
        }}
      >
        {delta != null ? fmt(delta) : '—'}
      </td>
    </tr>
  )
}

function BootstrapTile({ label, value }: { label: string; value: number | null | undefined }) {
  return (
    <div className="rounded-[2px] bg-[var(--bg-1)] px-2 py-1 text-center">
      <div className="text-[9px] uppercase tracking-wide text-[var(--text-3)]">{label}</div>
      <div className="mono tabular-nums text-[12px] font-semibold text-[var(--text-0)] mt-0.5">
        {typeof value === 'number' ? value.toFixed(2) : '—'}
      </div>
    </div>
  )
}

function BootstrapRibbon({ p5, p50, p95 }: { p5: number; p50: number; p95: number }) {
  const min = Math.min(p5, 0)
  const max = Math.max(p95, 0)
  const range = max - min || 1
  const start = ((p5 - min) / range) * 100
  const end = ((p95 - min) / range) * 100
  const median = ((p50 - min) / range) * 100
  return (
    <div className="relative h-2 rounded-[1px] bg-[var(--bg-1)] overflow-hidden">
      <div
        className="absolute inset-y-0 bg-[color-mix(in_oklab,var(--accent-primary)_30%,transparent)]"
        style={{ left: `${start}%`, width: `${Math.max(0.5, end - start)}%` }}
      />
      <div
        className="absolute inset-y-0 w-[1px] bg-[var(--text-0)]"
        style={{ left: `${median}%` }}
      />
    </div>
  )
}

function ComponentRow({
  label,
  value,
  max,
  color,
  signed,
}: {
  label: string
  value: number | null | undefined
  max: number
  color: string
  signed?: boolean
}) {
  if (value == null || !Number.isFinite(value)) {
    return (
      <div className="flex items-center gap-2 px-2 py-1 text-[11px]">
        <span className="w-[120px] text-[var(--text-2)]">{label}</span>
        <span className="flex-1 text-[var(--text-3)] text-[10px]">—</span>
      </div>
    )
  }
  const pct = signed ? Math.abs(value / max) : value / max
  const isNegative = value < 0
  return (
    <div className="flex items-center gap-2 px-2 py-1 text-[11px] border-b border-[var(--border-subtle)] last:border-b-0">
      <span className="w-[130px] text-[var(--text-2)] truncate" title={label}>
        {label}
      </span>
      <div className="flex-1 h-1.5 rounded-[1px] bg-[var(--bg-0)] overflow-hidden">
        <div
          className="h-full"
          style={{
            width: `${Math.min(100, Math.max(0, pct * 100))}%`,
            backgroundColor: isNegative ? 'var(--pnl-down)' : color,
          }}
        />
      </div>
      <span className="mono tabular-nums w-[64px] text-right text-[var(--text-1)]">
        {signed && value > 0 ? '+' : ''}
        {value.toFixed(1)} / {max}
      </span>
    </div>
  )
}

function pnlColor(v: number | null | undefined): string {
  if (v == null) return 'var(--text-3)'
  if (v > 0) return 'var(--pnl-up)'
  if (v < 0) return 'var(--pnl-down)'
  return 'var(--pnl-flat)'
}

function sharpeColor(v: number | null | undefined): string {
  if (v == null) return 'var(--text-3)'
  if (v >= 1.5) return 'var(--pnl-up)'
  if (v >= 1.0) return 'var(--text-0)'
  if (v >= 0.5) return 'var(--status-warning)'
  return 'var(--pnl-down)'
}

function consistencyColor(v: number): string {
  if (v >= 70) return 'var(--pnl-up)'
  if (v >= 50) return 'var(--accent-primary)'
  if (v >= 30) return 'var(--status-warning)'
  return 'var(--pnl-down)'
}

/* Small helpers exposed for keyboard cycling in LibraryTab */
export const SUB_TAB_ORDER: DetailSubTab[] = SUB_TABS.map((t) => t.value)

export function nextSubTab(current: DetailSubTab, direction: 1 | -1): DetailSubTab {
  const idx = SUB_TAB_ORDER.indexOf(current)
  const next = (idx + direction + SUB_TAB_ORDER.length) % SUB_TAB_ORDER.length
  return SUB_TAB_ORDER[next]
}

export type { DetailSubTab }

/* Icons re-exported for convenience (ChevronLeft/Right unused today; kept for future breadcrumbs). */
export { ChevronLeft as _DetailLeftIcon, ChevronRight as _DetailRightIcon }
