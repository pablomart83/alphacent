import { useState } from 'react'
import { Sparkles } from 'lucide-react'
import { Button, Label } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { notifyError } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { useVibeCodeTranslate } from '../useStrategiesData'

/**
 * VibeCodePanel — natural-language → structured trading command.
 */
export function VibeCodePanel() {
  const translate = useVibeCodeTranslate()
  const [input, setInput] = useState('')
  const [result, setResult] = useState<Awaited<
    ReturnType<typeof translate.mutateAsync>
  > | null>(null)

  const run = async () => {
    const text = input.trim()
    if (!text) return
    try {
      const res = await translate.mutateAsync({ naturalLanguage: text })
      setResult(res)
    } catch (err) {
      notifyError(err, 'vibe code translate')
    }
  }

  return (
    <section className="flex flex-col gap-2 p-2 rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)]">
      <SectionLabel>Vibe-code translator</SectionLabel>

      <div>
        <Label htmlFor="vibe-input" className="text-[10px] uppercase tracking-wider">
          Describe the trade
        </Label>
        <textarea
          id="vibe-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          rows={3}
          placeholder='"buy $2000 of AAPL at market because earnings beat"'
          className={cn(
            'w-full mt-1 rounded-[3px] bg-[var(--bg-0)] border border-[var(--border-default)]',
            'px-2 py-1.5 text-[11px] text-[var(--text-0)]',
            'focus:outline-2 focus:outline-[var(--border-focus)]',
          )}
        />
      </div>

      <Button
        variant="primary"
        size="sm"
        onClick={run}
        loading={translate.isPending}
        disabled={!input.trim()}
        className="gap-1.5 self-start"
      >
        <Sparkles className="h-3 w-3" />
        Translate
      </Button>

      {result && (
        <div className="mt-1 rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-0)] p-2 space-y-1 text-[11px]">
          <Row label="Action" value={<span className="mono uppercase">{result.action}</span>} />
          <Row label="Symbol" value={<span className="mono">{result.symbol}</span>} />
          {result.quantity != null && (
            <Row label="Quantity" value={<span className="mono tabular-nums">{result.quantity}</span>} />
          )}
          {result.price != null && (
            <Row label="Price" value={<span className="mono tabular-nums">${result.price.toFixed(2)}</span>} />
          )}
          <Row
            label="Reason"
            value={<span className="text-[var(--text-2)]">{result.reason}</span>}
          />
          <div className="text-[9px] text-[var(--text-3)] italic pt-1 border-t border-[var(--border-subtle)]">
            Preview only. To fire, wire this command through the manual-order flow.
          </div>
        </div>
      )}
    </section>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-2">
      <span className="text-[9px] uppercase tracking-wider text-[var(--text-3)] w-16 shrink-0">
        {label}
      </span>
      <span>{value}</span>
    </div>
  )
}
