import { useMemo, useState } from 'react'
import { Download } from 'lucide-react'
import { Button, ErrorState, Input, Label } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { classifyError } from '@/lib/errors'
import {
  buildTradeJournalExportUrl,
  useTradeJournal,
  useTradeJournalPatterns,
  type TradeJournalFilters,
} from '../useResearchData'
import { TradeJournalTable } from './TradeJournalTable'
import { MaeMfeScatter } from './MaeMfeScatter'
import { PatternsPanel } from './PatternsPanel'

/**
 * Journal tab — every trade, every pattern, no invented data.
 *   1. Filter bar: symbol, strategy, regime, sector, date range.
 *   2. Virtualised table (DataTable auto-virtualises > 100 rows).
 *   3. MAE / MFE scatter (Visx) — x=MAE %, y=MFE %, colour=P&L sign.
 *   4. Patterns panel: best & worst signals + recommendations.
 *   5. CSV export via direct href — avoids blob churn.
 */
export function JournalTab() {
  const [symbol, setSymbol] = useState('')
  const [regime, setRegime] = useState('')
  const [sector, setSector] = useState('')
  const [startDate, setStartDate] = useState('')
  const [endDate, setEndDate] = useState('')

  const filters: TradeJournalFilters = useMemo(
    () => ({
      symbol: symbol || null,
      regime: regime || null,
      sector: sector || null,
      startDate: startDate || null,
      endDate: endDate || null,
      limit: 500,
    }),
    [symbol, regime, sector, startDate, endDate],
  )

  const journal = useTradeJournal(filters)
  const patterns = useTradeJournalPatterns()

  const exportUrl = buildTradeJournalExportUrl(filters)

  if (journal.isError) {
    const info = classifyError(journal.error, 'trade journal')
    return (
      <ErrorState
        title="Couldn't load trade journal"
        message={info.message}
        onRetry={() => journal.refetch()}
      />
    )
  }

  return (
    <div className="flex flex-col h-full min-h-0 overflow-auto bg-[var(--bg-0)] px-3 py-3 space-y-4">
      <section className="space-y-1.5">
        <SectionLabel
          actions={
            <Button asChild size="sm" variant="secondary">
              <a href={exportUrl} download>
                <Download className="h-3 w-3 mr-1" />
                Export CSV
              </a>
            </Button>
          }
        >
          Filters · {journal.data?.total_count ?? 0} trades
        </SectionLabel>
        <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 grid grid-cols-2 md:grid-cols-5 gap-2">
          <Field label="Symbol">
            <Input
              value={symbol}
              onChange={(e) => setSymbol(e.target.value.toUpperCase())}
              placeholder="e.g. AAPL"
              className="h-7 mono"
            />
          </Field>
          <Field label="Regime">
            <Input
              value={regime}
              onChange={(e) => setRegime(e.target.value)}
              placeholder="trending_up"
              className="h-7 mono"
            />
          </Field>
          <Field label="Sector">
            <Input
              value={sector}
              onChange={(e) => setSector(e.target.value)}
              placeholder="Technology"
              className="h-7 mono"
            />
          </Field>
          <Field label="Start">
            <Input
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              placeholder="YYYY-MM-DD"
              className="h-7 mono"
            />
          </Field>
          <Field label="End">
            <Input
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              placeholder="YYYY-MM-DD"
              className="h-7 mono"
            />
          </Field>
        </div>
      </section>

      <TradeJournalTable trades={journal.data?.trades} loading={journal.isLoading} />
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        <MaeMfeScatter trades={journal.data?.trades} loading={journal.isLoading} />
        <PatternsPanel data={patterns.data} loading={patterns.isLoading} />
      </div>
    </div>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <Label className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">
        {label}
      </Label>
      {children}
    </div>
  )
}
