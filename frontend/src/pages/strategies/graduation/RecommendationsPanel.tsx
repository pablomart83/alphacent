import { Lightbulb, RefreshCw, Check, X, Undo2 } from 'lucide-react'
import { Button, Badge, Skeleton, EmptyState } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import {
  useRecommendations,
  useRecommendationAction,
  useRecomputeRecommendations,
  type RecommendationRow,
} from '../useStrategiesData'

/**
 * RecommendationsPanel — Tier-1 MAE/MFE → SL/TP improvement recommendations.
 * Proposals only; approving applies via the Path-A rail (live pairs update
 * live_strategies, template/paper scope writes a param override the proposer
 * reads next cycle). LIVE-scoped rows are visibly tagged.
 */

function pct(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return `${(v * 100).toFixed(1)}%`
}

function RecRow({ rec }: { rec: RecommendationRow }) {
  const action = useRecommendationAction()
  const isLive = rec.account_type === 'live'
  const slChanged = rec.proposed_sl !== rec.current_sl
  const tpChanged = rec.proposed_tp !== rec.current_tp
  const pending = rec.status === 'pending'

  return (
    <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2">
      <div className="flex items-center gap-2 mb-1">
        <span className="text-[12px] text-[var(--text-1)] font-medium">{rec.scope_key}</span>
        <Badge variant={rec.scope_type === 'symbol' ? 'info' : 'default'} size="sm">
          {rec.scope_type === 'symbol' ? 'pair' : 'template'}
        </Badge>
        {isLive && <Badge variant="warning" size="sm">LIVE</Badge>}
        <span className="text-[10px] text-[var(--text-3)] ml-auto mono">n={rec.n_trades}</span>
        {!pending && (
          <Badge variant={rec.status === 'applied' ? 'success' : 'default'} size="sm">
            {rec.status}
          </Badge>
        )}
      </div>

      <div className="flex items-center gap-4 text-[11px] mono mb-1">
        <span className={slChanged ? 'text-[var(--text-1)]' : 'text-[var(--text-3)]'}>
          SL {pct(rec.current_sl)} → <strong>{pct(rec.proposed_sl)}</strong>
        </span>
        <span className={tpChanged ? 'text-[var(--text-1)]' : 'text-[var(--text-3)]'}>
          TP {pct(rec.current_tp)} → <strong>{pct(rec.proposed_tp)}</strong>
        </span>
      </div>

      {rec.summary && (
        <div className="text-[10px] text-[var(--text-2)] mb-1.5">{rec.summary}</div>
      )}
      {rec.evidence && (
        <div className="text-[9px] text-[var(--text-3)] mono mb-1.5">
          MAE p80 {pct(rec.evidence.mae_p80)} · winners MAE p75 {pct(rec.evidence.winners_mae_p75)} ·
          MFE p50 {pct(rec.evidence.mfe_p50)} · win {pct(rec.evidence.win_rate)} ·
          exp capture +{pct(rec.evidence.expected_capture_gain)}
        </div>
      )}

      <div className="flex items-center gap-1.5">
        {pending ? (
          <>
            <Button
              size="sm"
              variant="primary"
              disabled={action.isPending}
              onClick={() => action.mutate({ id: rec.id, action: 'approve' })}
            >
              <Check className="h-3 w-3 mr-1" /> Approve
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={action.isPending}
              onClick={() => action.mutate({ id: rec.id, action: 'reject' })}
            >
              <X className="h-3 w-3 mr-1" /> Reject
            </Button>
          </>
        ) : rec.status === 'applied' ? (
          <Button
            size="sm"
            variant="outline"
            disabled={action.isPending}
            onClick={() => action.mutate({ id: rec.id, action: 'revert' })}
          >
            <Undo2 className="h-3 w-3 mr-1" /> Revert
          </Button>
        ) : null}
      </div>
    </div>
  )
}

export function RecommendationsPanel() {
  const query = useRecommendations('pending')
  const recompute = useRecomputeRecommendations()
  const recs = query.data?.recommendations ?? []

  return (
    <section className="px-2 pt-2 pb-2 border-t border-[var(--border-subtle)] flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <Lightbulb className="h-3.5 w-3.5 text-[var(--accent-primary)]" />
        <SectionLabel className="mb-0">SL/TP recommendations</SectionLabel>
        <Badge variant="info" size="sm">{recs.length}</Badge>
        <Button
          size="sm"
          variant="ghost"
          className="ml-auto"
          disabled={recompute.isPending}
          onClick={() => recompute.mutate()}
        >
          <RefreshCw className={`h-3 w-3 mr-1 ${recompute.isPending ? 'animate-spin' : ''}`} />
          Run now
        </Button>
      </div>

      {query.isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : recs.length === 0 ? (
        <EmptyState
          title="No pending recommendations"
          description="The MAE/MFE engine found no material, well-sampled SL/TP changes. Runs daily."
        />
      ) : (
        <div className="flex flex-col gap-1.5">
          {recs.map((rec) => (
            <RecRow key={rec.id} rec={rec} />
          ))}
        </div>
      )}
    </section>
  )
}
