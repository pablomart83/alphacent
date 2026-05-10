import { useState } from 'react'
import { toast } from 'sonner'
import { Wand2 } from 'lucide-react'
import { Button, Label } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { notifyError } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { useGenerateStrategy, type StrategyRow } from '../useStrategiesData'

/**
 * GenerateStrategyPanel — LLM-backed strategy generation.
 */
export function GenerateStrategyPanel() {
  const generate = useGenerateStrategy()
  const [prompt, setPrompt] = useState('')
  const [result, setResult] = useState<StrategyRow | null>(null)

  const run = async () => {
    const text = prompt.trim()
    if (text.length < 10) {
      toast.error('Prompt must be at least 10 characters')
      return
    }
    try {
      const res = await generate.mutateAsync({ prompt: text })
      setResult(res)
      toast.success('Strategy proposed — see library')
    } catch (err) {
      notifyError(err, 'generate strategy')
    }
  }

  return (
    <section className="flex flex-col gap-2 p-2 rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)]">
      <SectionLabel>Generate strategy</SectionLabel>

      <div>
        <Label htmlFor="gen-prompt" className="text-[10px] uppercase tracking-wider">
          Prompt
        </Label>
        <textarea
          id="gen-prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          rows={4}
          maxLength={1000}
          placeholder="Long-only momentum on NVDA and AMD using 10/30 EMA cross, 6% stop, 15% take, weekly rebalance."
          className={cn(
            'w-full mt-1 rounded-[3px] bg-[var(--bg-0)] border border-[var(--border-default)]',
            'px-2 py-1.5 text-[11px] text-[var(--text-0)]',
            'focus:outline-2 focus:outline-[var(--border-focus)]',
          )}
        />
        <div className="text-[9px] text-[var(--text-3)] text-right mt-0.5">
          {prompt.length} / 1000
        </div>
      </div>

      <Button
        variant="primary"
        size="sm"
        onClick={run}
        loading={generate.isPending}
        disabled={prompt.trim().length < 10}
        className="gap-1.5 self-start"
      >
        <Wand2 className="h-3 w-3" />
        Generate
      </Button>

      {result && (
        <div className="mt-1 rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-0)] p-2 space-y-1 text-[11px]">
          <div>
            <span className="text-[var(--text-0)] font-medium">{result.name}</span>
            <span className="text-[10px] text-[var(--text-3)] ml-2">
              · {result.status}
            </span>
          </div>
          <p className="text-[10px] text-[var(--text-2)] line-clamp-3">
            {result.description}
          </p>
          <div className="text-[10px] text-[var(--text-3)]">
            Symbols: <span className="mono">{result.symbols.join(', ') || '—'}</span>
          </div>
          <div className="pt-1 border-t border-[var(--border-subtle)]">
            <a
              href={`/strategies/library?selected=${result.id}`}
              className="text-[var(--accent-primary)] hover:underline text-[10px]"
            >
              Open in library →
            </a>
          </div>
        </div>
      )}
    </section>
  )
}
