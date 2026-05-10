import { useState } from 'react'
import { toast } from 'sonner'
import { Rocket } from 'lucide-react'
import {
  Badge,
  Button,
  Input,
  Label,
  Switch,
} from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { classifyError } from '@/lib/errors'
import { useBootstrap, type BootstrapPayload } from '../useStrategiesData'

const AVAILABLE_TYPES = [
  { value: 'momentum', label: 'Momentum' },
  { value: 'mean_reversion', label: 'Mean reversion' },
  { value: 'breakout', label: 'Breakout' },
]

/**
 * BootstrapPanel — kick off a multi-strategy generation cycle.
 */
export function BootstrapPanel() {
  const bootstrap = useBootstrap()
  const [types, setTypes] = useState<string[]>(['momentum', 'breakout'])
  const [autoActivate, setAutoActivate] = useState(false)
  const [minSharpe, setMinSharpe] = useState(1.0)
  const [backtestDays, setBacktestDays] = useState(90)
  const [result, setResult] = useState<BootstrapPayload | null>(null)

  const toggleType = (value: string) => {
    setTypes((cur) =>
      cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value],
    )
  }

  const run = async () => {
    try {
      const res = await bootstrap.mutateAsync({
        strategy_types: types.length ? types : undefined,
        auto_activate: autoActivate,
        min_sharpe: minSharpe,
        backtest_days: backtestDays,
      })
      setResult(res)
      toast.success(res.message)
    } catch (err) {
      const info = classifyError(err, 'bootstrap')
      toast.error(info.title, { description: info.message })
    }
  }

  return (
    <section className="flex flex-col gap-2 p-2 rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)]">
      <SectionLabel>Bootstrap</SectionLabel>

      <div>
        <Label className="text-[10px] uppercase tracking-wider">Strategy types</Label>
        <div className="flex flex-wrap gap-1 mt-1">
          {AVAILABLE_TYPES.map((t) => {
            const selected = types.includes(t.value)
            return (
              <button
                key={t.value}
                type="button"
                onClick={() => toggleType(t.value)}
                className={`h-6 px-2 rounded-[2px] text-[10px] uppercase tracking-wider border transition-colors ${
                  selected
                    ? 'bg-[var(--accent-primary)] text-white border-[var(--accent-primary)]'
                    : 'bg-[var(--bg-0)] text-[var(--text-2)] border-[var(--border-default)] hover:text-[var(--text-0)]'
                }`}
              >
                {t.label}
              </button>
            )
          })}
        </div>
        <div className="text-[9px] text-[var(--text-3)] mt-1">
          Leave empty to let the backend pick.
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <Label className="text-[10px] uppercase tracking-wider">Min Sharpe</Label>
          <Input
            type="number"
            value={minSharpe}
            onChange={(e) => setMinSharpe(Number(e.target.value))}
            min={0}
            max={5}
            step={0.1}
            className="h-7 mono text-[11px] mt-1"
          />
        </div>
        <div>
          <Label className="text-[10px] uppercase tracking-wider">Backtest days</Label>
          <Input
            type="number"
            value={backtestDays}
            onChange={(e) => setBacktestDays(Number(e.target.value))}
            min={30}
            max={365}
            step={10}
            className="h-7 mono text-[11px] mt-1"
          />
        </div>
      </div>

      <label className="inline-flex items-center gap-2 text-[10px] text-[var(--text-2)]">
        <Switch checked={autoActivate} onCheckedChange={setAutoActivate} />
        Auto-activate strategies meeting min Sharpe
      </label>

      <Button
        variant="primary"
        size="sm"
        onClick={run}
        loading={bootstrap.isPending}
        className="gap-1.5 self-start"
      >
        <Rocket className="h-3 w-3" />
        Run bootstrap
      </Button>

      {result && (
        <div className="mt-1 rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-0)] p-2 space-y-1 text-[11px]">
          <div className="flex items-center gap-2">
            <Badge variant={result.success ? 'success' : 'warning'} size="sm">
              {result.success ? 'Complete' : 'Partial'}
            </Badge>
            <span className="text-[var(--text-2)]">{result.message}</span>
          </div>
          {result.strategies.length > 0 && (
            <ul className="space-y-0.5 pt-1 border-t border-[var(--border-subtle)]">
              {result.strategies.map((s) => (
                <li key={s.id} className="flex items-baseline justify-between gap-2">
                  <span
                    className="text-[var(--text-1)] truncate max-w-[260px]"
                    title={s.name}
                  >
                    {s.name}
                  </span>
                  <span className="mono tabular-nums text-[10px] text-[var(--text-3)]">
                    {s.backtest_results
                      ? `Sh ${s.backtest_results.sharpe_ratio.toFixed(2)} · ${s.backtest_results.total_trades}t`
                      : s.status}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <div className="pt-1 border-t border-[var(--border-subtle)]">
            <a
              href="/strategies/library"
              className="text-[var(--accent-primary)] hover:underline text-[10px]"
            >
              Open library →
            </a>
          </div>
        </div>
      )}
    </section>
  )
}
