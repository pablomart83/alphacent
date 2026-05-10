import { useMemo } from 'react'
import { Lightbulb } from 'lucide-react'
import { SectionLabel } from '@/components/layout'
import { Skeleton, EmptyState } from '@/components/primitives'
import { RegimePill } from '@/components/trading/RegimePill'
import { cn } from '@/lib/utils'
import type { CycleRunRow } from '../useStrategiesData'

/**
 * CycleIntelligencePanel — surfaces the "intent" of the last / running
 * cycle: which market regime it ran under, the proposal mix (DSL vs
 * Alpha Edge), and the stage_details breakdown when the backend provides
 * one. Shows at a glance "what did this cycle actually look at?".
 */

interface CycleIntelligencePanelProps {
  lastCycle: CycleRunRow | null
  regime?: string | null
  regimeConfidence?: number | null
  loading?: boolean
  className?: string
}

export function CycleIntelligencePanel({
  lastCycle,
  regime,
  regimeConfidence,
  loading,
  className,
}: CycleIntelligencePanelProps) {
  const mix = useMemo(() => {
    if (!lastCycle) return null
    const total = lastCycle.proposals_generated || 0
    if (total <= 0) return null
    const dsl = lastCycle.proposals_template
    const alphaEdge = lastCycle.proposals_alpha_edge
    const other = Math.max(0, total - dsl - alphaEdge)
    return {
      total,
      dsl,
      alphaEdge,
      other,
    }
  }, [lastCycle])

  const stageHighlights = useMemo(() => {
    const details = lastCycle?.stage_details
    if (!details || typeof details !== 'object') return []
    const entries: Array<{ stage: string; summary: string }> = []
    for (const [stage, payload] of Object.entries(details as Record<string, unknown>)) {
      const summary = summariseStagePayload(payload)
      if (summary) entries.push({ stage, summary })
    }
    return entries.slice(0, 6)
  }, [lastCycle])

  return (
    <section className={cn('flex flex-col gap-2 p-2', className)}>
      <div className="flex items-center gap-2">
        <SectionLabel>Cycle intelligence</SectionLabel>
        <Lightbulb className="h-3 w-3 text-[var(--text-3)]" />
      </div>

      {loading ? (
        <Skeleton className="h-24 w-full" />
      ) : !lastCycle ? (
        <EmptyState title="No cycle yet" description="Intelligence surfaces once a cycle completes." />
      ) : (
        <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 flex flex-col gap-2">
          {regime && (
            <div className="flex items-center gap-2">
              <span className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">
                Regime
              </span>
              <RegimePill
                regime={regime}
                size="sm"
                confidence={regimeConfidence ?? undefined}
                showConfidence={regimeConfidence != null}
              />
            </div>
          )}

          {mix && (
            <div>
              <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)] mb-1">
                Proposal mix
              </div>
              <MixBar
                segments={[
                  { label: 'DSL template', value: mix.dsl, color: 'var(--accent-primary)' },
                  { label: 'Alpha Edge', value: mix.alphaEdge, color: 'var(--accent-secondary)' },
                  { label: 'Other', value: mix.other, color: 'var(--text-3)' },
                ]}
                total={mix.total}
              />
            </div>
          )}

          {stageHighlights.length > 0 && (
            <div>
              <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)] mb-1">
                Stage details
              </div>
              <ul className="space-y-0.5 text-[10px]">
                {stageHighlights.map((h) => (
                  <li key={h.stage} className="flex items-baseline gap-2">
                    <span className="text-[var(--text-3)] uppercase tracking-wider w-[100px] shrink-0 truncate">
                      {h.stage.replace(/_/g, ' ')}
                    </span>
                    <span className="mono text-[var(--text-1)] truncate" title={h.summary}>
                      {h.summary}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </section>
  )
}

function MixBar({
  segments,
  total,
}: {
  segments: Array<{ label: string; value: number; color: string }>
  total: number
}) {
  return (
    <div>
      <div className="h-2 rounded-[1px] bg-[var(--bg-0)] overflow-hidden flex">
        {segments.map((s) => {
          const pct = total > 0 ? (s.value / total) * 100 : 0
          return (
            <div
              key={s.label}
              style={{ width: `${pct}%`, backgroundColor: s.color }}
              title={`${s.label}: ${s.value} (${pct.toFixed(0)}%)`}
            />
          )
        })}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-1">
        {segments.map((s) => {
          const pct = total > 0 ? (s.value / total) * 100 : 0
          return (
            <div key={s.label} className="inline-flex items-center gap-1 text-[10px]">
              <span
                className="h-1.5 w-1.5 rounded-full"
                style={{ backgroundColor: s.color }}
              />
              <span className="text-[var(--text-2)]">{s.label}</span>
              <span className="mono text-[var(--text-1)]">{s.value}</span>
              <span className="text-[var(--text-3)]">({pct.toFixed(0)}%)</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

function summariseStagePayload(payload: unknown): string | null {
  if (payload == null) return null
  if (typeof payload === 'string') return payload.length > 80 ? `${payload.slice(0, 80)}…` : payload
  if (typeof payload === 'number' || typeof payload === 'boolean') return String(payload)
  if (Array.isArray(payload)) return `${payload.length} items`
  if (typeof payload === 'object') {
    const entries = Object.entries(payload as Record<string, unknown>).slice(0, 4)
    const parts = entries
      .map(([k, v]) => {
        if (typeof v === 'number' && Number.isFinite(v)) return `${k}=${v}`
        if (typeof v === 'string' && v.length < 24) return `${k}=${v}`
        return null
      })
      .filter((p): p is string => !!p)
    return parts.length ? parts.join(' · ') : null
  }
  return null
}
