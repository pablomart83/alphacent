import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import { Play } from 'lucide-react'
import {
  Button,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { PnLNumber } from '@/components/trading/PnLNumber'
import { notifyError } from '@/lib/errors'
import { formatTimestamp } from '@/lib/utils'
import {
  useStrategies,
  useStrategyBacktest,
  type BacktestResultsPayload,
} from '../useStrategiesData'

/**
 * BacktestRunnerPanel — select a library strategy, choose a date range, run.
 * Results render as a KPI grid. Progress bar hook is reserved for the WS
 * `backtest_progress` event (Sprint 11 adds the live stream overlay).
 */
export function BacktestRunnerPanel() {
  const strategies = useStrategies({ slim: true, include_retired: false })
  const backtest = useStrategyBacktest()

  const [strategyId, setStrategyId] = useState<string>('')
  const [startDate, setStartDate] = useState<string>('')
  const [endDate, setEndDate] = useState<string>('')
  const [results, setResults] = useState<BacktestResultsPayload | null>(null)

  const options = useMemo(() => {
    const rows = strategies.data?.strategies ?? []
    return rows.map((s) => ({ value: s.id, label: s.name }))
  }, [strategies.data])

  const run = async () => {
    if (!strategyId) {
      toast.error('Select a strategy first')
      return
    }
    try {
      const res = await backtest.mutateAsync({
        strategyId,
        start_date: startDate || undefined,
        end_date: endDate || undefined,
      })
      setResults(res)
      toast.success('Backtest complete')
    } catch (err) {
      notifyError(err, 'backtest')
    }
  }

  return (
    <section className="flex flex-col gap-2 p-2 rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)]">
      <SectionLabel>Backtest runner</SectionLabel>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <div>
          <Label className="text-[10px] uppercase tracking-wider">Strategy</Label>
          <Select value={strategyId} onValueChange={setStrategyId}>
            <SelectTrigger size="sm" className="w-full mt-1">
              <SelectValue placeholder="Choose a strategy" />
            </SelectTrigger>
            <SelectContent>
              {options.length === 0 ? (
                <SelectItem value="__none__" disabled>
                  Strategies loading…
                </SelectItem>
              ) : (
                options.map((o) => (
                  <SelectItem key={o.value} value={o.value}>
                    {o.label}
                  </SelectItem>
                ))
              )}
            </SelectContent>
          </Select>
        </div>
        <div />

        <div>
          <Label htmlFor="bt-start" className="text-[10px] uppercase tracking-wider">
            Start date
          </Label>
          <Input
            id="bt-start"
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="h-7 mt-1 text-[11px]"
          />
        </div>
        <div>
          <Label htmlFor="bt-end" className="text-[10px] uppercase tracking-wider">
            End date
          </Label>
          <Input
            id="bt-end"
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="h-7 mt-1 text-[11px]"
          />
        </div>
      </div>

      <Button
        variant="primary"
        size="sm"
        onClick={run}
        loading={backtest.isPending}
        disabled={!strategyId}
        className="gap-1.5 self-start"
      >
        <Play className="h-3 w-3" />
        Run backtest
      </Button>

      {results && <BacktestResults results={results} />}
    </section>
  )
}

function BacktestResults({ results }: { results: BacktestResultsPayload }) {
  const {
    total_return,
    sharpe_ratio,
    sortino_ratio,
    max_drawdown,
    win_rate,
    total_trades,
    avg_win,
    avg_loss,
    backtest_period,
    gross_return,
    net_return,
    total_transaction_costs,
  } = results

  return (
    <div className="mt-2 space-y-2">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Kpi label="Total return" value={<PnLNumber value={total_return * 100} format="percentage" precision={2} size="sm" showSign />} />
        <Kpi label="Sharpe" value={sharpe_ratio.toFixed(2)} />
        <Kpi label="Sortino" value={sortino_ratio.toFixed(2)} />
        <Kpi label="Max DD" value={`${(max_drawdown * 100).toFixed(1)}%`} negative />
        <Kpi label="Win rate" value={`${(win_rate * 100).toFixed(0)}%`} />
        <Kpi label="Trades" value={String(total_trades)} />
        <Kpi label="Avg win" value={`$${avg_win.toFixed(0)}`} positive />
        <Kpi label="Avg loss" value={`$${avg_loss.toFixed(0)}`} negative />
      </div>
      {(gross_return != null || net_return != null) && (
        <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-0)] p-2 text-[10px] text-[var(--text-2)] space-y-0.5">
          {gross_return != null && (
            <div>
              Gross: <span className="mono">{(gross_return * 100).toFixed(2)}%</span>
            </div>
          )}
          {net_return != null && (
            <div>
              Net: <span className="mono">{(net_return * 100).toFixed(2)}%</span>
            </div>
          )}
          {total_transaction_costs != null && (
            <div>
              Transaction costs:{' '}
              <span className="mono text-[var(--pnl-down)]">
                ${total_transaction_costs.toFixed(2)}
              </span>
            </div>
          )}
        </div>
      )}
      {backtest_period && (
        <div className="text-[10px] text-[var(--text-3)]">
          Period: {formatTimestamp(backtest_period.start, 'short')} →{' '}
          {formatTimestamp(backtest_period.end, 'short')}
        </div>
      )}
    </div>
  )
}

function Kpi({
  label,
  value,
  positive,
  negative,
}: {
  label: string
  value: React.ReactNode
  positive?: boolean
  negative?: boolean
}) {
  return (
    <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-0)] p-1.5">
      <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">
        {label}
      </div>
      <div
        className="mono tabular-nums text-[13px] mt-0.5"
        style={{
          color: positive
            ? 'var(--pnl-up)'
            : negative
              ? 'var(--pnl-down)'
              : 'var(--text-0)',
        }}
      >
        {value}
      </div>
    </div>
  )
}
