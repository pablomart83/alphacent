import { useEffect, useMemo, useState } from 'react'
import type { SortingState } from '@tanstack/react-table'
import { GraduationCap } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import {
  Badge,
  ConfirmDialog,
  EmptyState,
  ErrorState,
} from '@/components/primitives'
import { ResizablePanelLayout, SectionLabel } from '@/components/layout'
import { classifyError } from '@/lib/errors'
import { api } from '@/services/api'
import { useLiveSummary } from '@/pages/book/useBookData'
import {
  useGraduationQueue,
  useRetireLiveStrategy,
  type LiveStrategyRow,
} from '../useStrategiesData'
import { GraduationQueueTable } from './GraduationQueueTable'
import { GraduationCard } from './GraduationCard'
import { ActiveLiveTable, LiveStrategyDetailPanel } from './ActiveLiveTable'
import { ApproachingGraduationPanel } from './ApproachingGraduationPanel'
import { toast } from 'sonner'
import { notifyError } from '@/lib/errors'

/* Live-trading config shape — mirrors /config/live-trading. */
interface LiveTradingConfigPayload {
  enabled?: boolean
  virtual_balance?: number
  real_investment?: number
  mirror_ratio?: number
  base_risk_pct?: number
  min_order_size?: number
  max_order_size?: number
  symbol_cap_pct?: number
  conviction_threshold?: number
  conviction_threshold_crypto?: number
}

function useLiveTradingConfig() {
  return useQuery<LiveTradingConfigPayload>({
    queryKey: ['live-trading-config'],
    queryFn: () => api.get<LiveTradingConfigPayload>('/config/live-trading'),
    staleTime: 120_000,
  })
}

/**
 * Graduation tab — /strategies/graduation.
 *
 * Left 55% : queue table + active live table + (empty) retired section
 * Right 45%: GraduationCard when a queue row is selected
 */
export function GraduationTab() {
  const queueQuery = useGraduationQueue()
  const liveSummary = useLiveSummary()
  const liveConfig = useLiveTradingConfig()
  const retire = useRetireLiveStrategy()

  const [sorting, setSorting] = useState<SortingState>([
    { id: 'qualification_ratio', desc: true },
  ])
  const [selectedKey, setSelectedKey] = useState<string | null>(null)
  // Selected live strategy for the side panel (independent of queue selection)
  const [selectedLive, setSelectedLive] = useState<LiveStrategyRow | null>(null)
  const [confirmRetireLive, setConfirmRetireLive] = useState<LiveStrategyRow | null>(null)

  const queue = queueQuery.data?.queue ?? []
  const selectedRow = useMemo(
    () => queue.find((r) => `${r.strategy_id}::${r.symbol}` === selectedKey) ?? null,
    [queue, selectedKey],
  )

  // When a queue row is selected, clear the live selection and vice versa
  const handleQueueSelect = (row: typeof selectedRow) => {
    setSelectedKey(row ? `${row.strategy_id}::${row.symbol}` : null)
    setSelectedLive(null)
  }
  const handleLiveSelect = (row: LiveStrategyRow | null) => {
    setSelectedLive(row)
    setSelectedKey(null)
  }

  const handleRetireLive = async () => {
    if (!confirmRetireLive) return
    try {
      await retire.mutateAsync({ liveId: confirmRetireLive.id })
      toast.success(
        `Retired ${confirmRetireLive.template_name ?? confirmRetireLive.strategy_id} × ${confirmRetireLive.symbol}`,
      )
      if (selectedLive?.id === confirmRetireLive.id) setSelectedLive(null)
      setConfirmRetireLive(null)
    } catch (err) {
      notifyError(err, 'retire live')
    }
  }

  /* Keyboard: j/k navigation over queue, Enter opens, Esc closes. */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      if (
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable)
      )
        return
      if (e.metaKey || e.ctrlKey || e.altKey) return

      if (e.key === 'Escape') {
        if (selectedKey) setSelectedKey(null)
        if (selectedLive) setSelectedLive(null)
        return
      }

      if (queue.length === 0) return

      if (e.key.toLowerCase() === 'j' || e.key.toLowerCase() === 'k') {
        e.preventDefault()
        const currentIdx = selectedKey
          ? queue.findIndex((r) => `${r.strategy_id}::${r.symbol}` === selectedKey)
          : -1
        const nextIdx =
          e.key.toLowerCase() === 'j'
            ? Math.min(queue.length - 1, currentIdx + 1)
            : Math.max(0, currentIdx - 1)
        const nextRow = queue[nextIdx]
        if (nextRow) handleQueueSelect(nextRow)
        return
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queue, selectedKey, selectedLive])

  if (queueQuery.isError) {
    const info = classifyError(queueQuery.error, 'graduation queue')
    return (
      <ErrorState
        title="Couldn't load graduation queue"
        message={info.message}
        onRetry={() => queueQuery.refetch()}
      />
    )
  }

  const cfg = liveConfig.data
  const mirrorRatio =
    liveSummary.data?.mirror_ratio ?? cfg?.mirror_ratio ?? 0.1

  const left = (
    <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)] overflow-auto">
      <section className="px-2 pt-2 pb-1">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <GraduationCap className="h-3.5 w-3.5 text-[var(--accent-primary)]" />
            <SectionLabel className="mb-0">Graduation queue</SectionLabel>
            <Badge variant="info" size="sm">
              {queue.length}
            </Badge>
          </div>
          <div className="text-[10px] text-[var(--text-3)]">
            ≥ 15 trades (4H) · Sharpe 60–200% of WF · Win ≥ 55% · avg P&L/trade {'>'} 0
          </div>
        </div>
      </section>

      <div className="px-2 pb-2">
        <GraduationQueueTable
          queue={queue}
          loading={queueQuery.isLoading}
          selectedKey={selectedKey}
          onSelect={(row) => handleQueueSelect(row)}
          sorting={sorting}
          onSortingChange={setSorting}
        />
      </div>

      <ActiveLiveTable
        selectedId={selectedLive?.id ?? null}
        onSelect={handleLiveSelect}
      />

      <div className="px-2 pb-2">
        <ApproachingGraduationPanel />
      </div>

      <RetiredSection />
    </div>
  )

  // Right panel: live detail takes priority over queue card when both could show
  const right = selectedLive ? (
    <LiveStrategyDetailPanel
      row={selectedLive}
      onClose={() => setSelectedLive(null)}
      onRetire={() => setConfirmRetireLive(selectedLive)}
    />
  ) : selectedRow ? (
    <GraduationCard
      row={selectedRow}
      onClose={() => setSelectedKey(null)}
      mirrorRatio={mirrorRatio}
      defaults={{
        position_size:
          cfg?.min_order_size != null && cfg?.max_order_size != null
            ? (cfg.min_order_size + cfg.max_order_size) / 2
            : 500,
        sl_pct_equity: 0.06,
        sl_pct_crypto: 0.08,
        tp_pct_equity: 0.15,
        tp_pct_crypto: 0.2,
        conviction_threshold_equity: cfg?.conviction_threshold ?? 74,
        conviction_threshold_crypto: cfg?.conviction_threshold_crypto ?? 68,
        symbol_cap_pct: cfg?.symbol_cap_pct ?? 0.2,
        min_order_size: cfg?.min_order_size ?? 200,
        max_order_size: cfg?.max_order_size ?? 1500,
      }}
    />
  ) : (
    <div className="flex h-full items-center justify-center bg-[var(--bg-0)]">
      <EmptyState
        title="Select a candidate"
        description="Click a queue row to review and approve, or a live authorisation to inspect its history."
      />
    </div>
  )

  const hasRightPanel = !!(selectedRow || selectedLive)

  return (
    <>
      {hasRightPanel ? (
        <ResizablePanelLayout
          layoutId="strategies.graduation"
          panels={[
            { id: 'grad-queue', defaultSize: 55, minSize: 40, content: left },
            { id: 'grad-card', defaultSize: 45, minSize: 30, maxSize: 70, content: right },
          ]}
        />
      ) : (
        left
      )}

      <ConfirmDialog
        open={!!confirmRetireLive}
        onOpenChange={(o) => !o && setConfirmRetireLive(null)}
        title="Retire live authorisation"
        description={
          confirmRetireLive
            ? `Retire ${confirmRetireLive.template_name ?? confirmRetireLive.strategy_id} × ${confirmRetireLive.symbol}? Future signals stop firing live orders. Open live positions are NOT closed automatically.`
            : ''
        }
        confirmLabel="Retire"
        confirmVariant="destructive"
        isLoading={retire.isPending}
        onConfirm={handleRetireLive}
      />
    </>
  )
}

/**
 * RetiredSection — placeholder for the 14-day cooldown countdown on retired
 * authorisations. Today's `GET /strategies/live` returns only retired_at IS
 * NULL rows, so rendering retirees requires either a new endpoint flag or
 * a trade_journal query. We surface the architectural shape and mark the
 * gap honestly instead of rendering a misleading empty panel.
 */
function RetiredSection() {
  return (
    <section className="flex flex-col gap-2 p-2 border-t border-[var(--border-subtle)]">
      <div className="flex items-center justify-between gap-2">
        <SectionLabel className="mb-0">Retired authorisations</SectionLabel>
      </div>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 text-[10px] text-[var(--text-3)] leading-relaxed">
        The 14-day re-graduation cooldown list requires a backend extension to{' '}
        <span className="mono">/strategies/live</span> or a new{' '}
        <span className="mono">/strategies/live?include_retired=true</span> query param.
        Rather than invent entries, this section renders empty until the backend surfaces
        retired rows. Raise before Sprint 8 if the CIO needs the countdown.
      </div>
    </section>
  )
}
