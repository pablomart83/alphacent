import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CheckCircle, Copy, ExternalLink, XCircle } from 'lucide-react'
import { Button } from '@/components/primitives'
import { cn } from '@/lib/utils'
import type { IntelFinding } from './useIntelData'
import {
  categoryLabel,
  formatAge,
  severityColor,
  useDismissFinding,
  useResolveFinding,
} from './useIntelData'

interface Props {
  finding: IntelFinding | undefined
  loading: boolean
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="text-[8px] font-semibold uppercase tracking-widest text-[var(--text-3)] mb-1.5">
        {title}
      </h3>
      {children}
    </section>
  )
}

export function FindingDetail({ finding, loading }: Props) {
  const navigate = useNavigate()
  const dismiss = useDismissFinding()
  const resolve = useResolveFinding()
  const [dismissReason, setDismissReason] = useState('')
  const [showDismissInput, setShowDismissInput] = useState(false)
  const [copied, setCopied] = useState(false)

  if (loading) {
    return (
      <div className="p-4 space-y-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-6 rounded bg-[var(--bg-1)] animate-pulse" style={{ width: `${70 + i * 5}%` }} />
        ))}
      </div>
    )
  }

  if (!finding) return null

  const handleAskKiro = () => {
    navigator.clipboard.writeText(finding.ask_kiro_prompt).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  const handleDismiss = () => {
    if (!showDismissInput) { setShowDismissInput(true); return }
    dismiss.mutate({ id: finding.id, reason: dismissReason })
    setShowDismissInput(false)
    setDismissReason('')
  }

  const handleResolve = () => resolve.mutate(finding.id)
  const isOpen = finding.status === 'open'
  const color = severityColor(finding.severity)

  return (
    <div className="flex flex-col h-full min-h-0">

      {/* Header — subtle left border accent instead of heavy background */}
      <div
        className="shrink-0 px-4 py-3 border-b border-[var(--border-subtle)] border-l-4"
        style={{ borderLeftColor: color }}
      >
        <div className="flex items-center gap-2 mb-1">
          <span
            className="text-[9px] font-bold mono px-1.5 py-0.5 rounded"
            style={{ color, background: `${color}18` }}
          >
            {finding.severity}
          </span>
          <span className="text-[9px] text-[var(--text-3)]">{finding.check_id}</span>
          <span className="text-[9px] text-[var(--text-3)]">·</span>
          <span className="text-[9px] text-[var(--text-3)]">{categoryLabel(finding.category)}</span>

          {finding.status !== 'open' && (
            <span
              className={cn(
                'text-[8px] font-medium px-1.5 py-0.5 rounded ml-auto',
                finding.status === 'resolved'
                  ? 'bg-[rgba(34,197,94,0.12)] text-[var(--pnl-up)]'
                  : 'bg-[var(--bg-2)] text-[var(--text-3)]',
              )}
            >
              {finding.status}
            </span>
          )}
        </div>

        <h2 className="text-[13px] font-semibold text-[var(--text-0)] leading-snug">
          {finding.title.replace(/^[A-H]\d+:\s*/, '')}
        </h2>

        <div className="flex items-center gap-3 mt-1">
          <span className="text-[9px] text-[var(--text-3)]">
            First seen {formatAge(finding.first_seen)}
          </span>
          <span className="text-[9px] text-[var(--text-3)]">
            Last seen {formatAge(finding.last_seen)}
          </span>
          {finding.occurrence_count > 1 && (
            <span className="text-[9px] text-[var(--text-3)]">
              {finding.occurrence_count} occurrences
            </span>
          )}
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 min-h-0 overflow-y-auto px-4 py-3 space-y-4 text-[11px]">

        <Section title="Root Cause">
          <p className="text-[var(--text-1)] leading-relaxed">{finding.detail}</p>
        </Section>

        <Section title="Evidence">
          <pre className="text-[10px] font-mono bg-[var(--bg-1)] border border-[var(--border-subtle)] rounded p-2.5 whitespace-pre-wrap break-words text-[var(--text-1)] leading-relaxed">
            {finding.evidence}
          </pre>
        </Section>

        <Section title="Recommended Action">
          <p className="text-[var(--text-1)] leading-relaxed">{finding.recommended_action}</p>
        </Section>

        {finding.context_links && finding.context_links.length > 0 && (
          <Section title="Context">
            <div className="flex flex-wrap gap-2">
              {finding.context_links.map((link) => (
                <button
                  key={link.url}
                  type="button"
                  onClick={() => navigate(link.url)}
                  className="inline-flex items-center gap-1 text-[10px] text-[var(--accent-primary)] hover:underline"
                >
                  <ExternalLink className="h-3 w-3" />
                  {link.label}
                </button>
              ))}
            </div>
          </Section>
        )}

        {finding.status === 'dismissed' && finding.dismissed_reason && (
          <Section title="Dismissed Reason">
            <p className="text-[var(--text-2)] italic text-[10px]">{finding.dismissed_reason}</p>
          </Section>
        )}
      </div>

      {/* Action bar */}
      <div className="shrink-0 px-4 py-2.5 border-t border-[var(--border-subtle)] bg-[var(--bg-0)]">
        {showDismissInput && (
          <div className="flex gap-2 mb-2">
            <input
              type="text"
              value={dismissReason}
              onChange={(e) => setDismissReason(e.target.value)}
              placeholder="Reason (optional)"
              className="flex-1 text-[10px] bg-[var(--bg-1)] border border-[var(--border-subtle)] rounded px-2 py-1 text-[var(--text-1)] focus:outline-none focus:border-[var(--border-focus)]"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleDismiss()
                if (e.key === 'Escape') { setShowDismissInput(false); setDismissReason('') }
              }}
            />
            <Button
              variant="ghost"
              size="sm"
              onClick={() => { setShowDismissInput(false); setDismissReason('') }}
              className="h-6 text-[10px]"
            >
              Cancel
            </Button>
          </div>
        )}

        <div className="flex items-center gap-2">
          {isOpen && (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleDismiss}
              disabled={dismiss.isPending}
              className="h-6 text-[10px] text-[var(--text-2)] gap-1"
            >
              <XCircle className="h-3 w-3" />
              {showDismissInput ? 'Confirm' : 'Dismiss'}
            </Button>
          )}

          {(isOpen || finding.status === 'dismissed') && (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleResolve}
              disabled={resolve.isPending}
              className="h-6 text-[10px] text-[var(--pnl-up)] gap-1"
            >
              <CheckCircle className="h-3 w-3" />
              Resolved
            </Button>
          )}

          <Button
            variant="ghost"
            size="sm"
            onClick={handleAskKiro}
            className="h-6 text-[10px] text-[var(--accent-primary)] gap-1 ml-auto"
            title="Copy pre-filled prompt to clipboard"
          >
            <Copy className="h-3 w-3" />
            {copied ? 'Copied!' : 'Ask Kiro →'}
          </Button>
        </div>
      </div>
    </div>
  )
}
