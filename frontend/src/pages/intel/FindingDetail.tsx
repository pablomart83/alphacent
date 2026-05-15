import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CheckCircle, ExternalLink, MessageSquare, XCircle } from 'lucide-react'
import { Button } from '@/components/primitives'
import { cn } from '@/lib/utils'
import type { IntelFinding } from './useIntelData'
import {
  categoryLabel,
  formatAge,
  severityBg,
  severityColor,
  useDismissFinding,
  useResolveFinding,
} from './useIntelData'

interface Props {
  finding: IntelFinding | undefined
  loading: boolean
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
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-8 rounded bg-[var(--bg-1)] animate-pulse" />
        ))}
      </div>
    )
  }

  if (!finding) {
    return (
      <div className="flex items-center justify-center h-full text-[11px] text-[var(--text-3)]">
        Select a finding to view details
      </div>
    )
  }

  const handleAskKiro = () => {
    navigator.clipboard.writeText(finding.ask_kiro_prompt).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  const handleDismiss = () => {
    if (!showDismissInput) {
      setShowDismissInput(true)
      return
    }
    dismiss.mutate({ id: finding.id, reason: dismissReason })
    setShowDismissInput(false)
    setDismissReason('')
  }

  const handleResolve = () => {
    resolve.mutate(finding.id)
  }

  const isOpen = finding.status === 'open'

  return (
    <div className="flex flex-col h-full min-h-0 overflow-y-auto">
      {/* Header */}
      <div
        className="shrink-0 px-4 py-3 border-b border-[var(--border-subtle)]"
        style={{ background: severityBg(finding.severity) }}
      >
        <div className="flex items-center gap-2 mb-1">
          <span
            className="text-[10px] font-bold mono px-1.5 py-0.5 rounded"
            style={{
              color: severityColor(finding.severity),
              background: `${severityColor(finding.severity)}25`,
            }}
          >
            {finding.severity}
          </span>
          <span className="text-[10px] text-[var(--text-3)]">{finding.check_id}</span>
          <span className="text-[10px] text-[var(--text-3)]">·</span>
          <span className="text-[10px] text-[var(--text-3)]">{categoryLabel(finding.category)}</span>
          {finding.status !== 'open' && (
            <span
              className={cn(
                'text-[9px] font-medium px-1.5 py-0.5 rounded ml-auto',
                finding.status === 'resolved'
                  ? 'bg-[rgba(34,197,94,0.15)] text-[var(--pnl-up)]'
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
        <p className="text-[10px] text-[var(--text-3)] mt-1">
          First seen {formatAge(finding.first_seen)} · Last seen {formatAge(finding.last_seen)}
          {finding.occurrence_count > 1 && ` · ${finding.occurrence_count} occurrences`}
        </p>
      </div>

      {/* Body */}
      <div className="flex-1 px-4 py-3 space-y-4 text-[11px]">
        {/* Root cause */}
        <section>
          <h3 className="text-[9px] font-semibold uppercase tracking-widest text-[var(--text-3)] mb-1.5">
            Root Cause
          </h3>
          <p className="text-[var(--text-1)] leading-relaxed">{finding.detail}</p>
        </section>

        {/* Evidence */}
        <section>
          <h3 className="text-[9px] font-semibold uppercase tracking-widest text-[var(--text-3)] mb-1.5">
            Evidence
          </h3>
          <pre className="text-[10px] font-mono bg-[var(--bg-1)] border border-[var(--border-subtle)] rounded p-2.5 whitespace-pre-wrap break-words text-[var(--text-1)] leading-relaxed">
            {finding.evidence}
          </pre>
        </section>

        {/* Recommended action */}
        <section>
          <h3 className="text-[9px] font-semibold uppercase tracking-widest text-[var(--text-3)] mb-1.5">
            Recommended Action
          </h3>
          <p className="text-[var(--text-1)] leading-relaxed">{finding.recommended_action}</p>
        </section>

        {/* Context links */}
        {finding.context_links && finding.context_links.length > 0 && (
          <section>
            <h3 className="text-[9px] font-semibold uppercase tracking-widest text-[var(--text-3)] mb-1.5">
              Context
            </h3>
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
          </section>
        )}

        {/* Dismissed reason */}
        {finding.status === 'dismissed' && finding.dismissed_reason && (
          <section>
            <h3 className="text-[9px] font-semibold uppercase tracking-widest text-[var(--text-3)] mb-1.5">
              Dismissed Reason
            </h3>
            <p className="text-[var(--text-2)] italic">{finding.dismissed_reason}</p>
          </section>
        )}
      </div>

      {/* Actions */}
      <div className="shrink-0 px-4 py-3 border-t border-[var(--border-subtle)] space-y-2">
        {showDismissInput && (
          <div className="flex gap-2">
            <input
              type="text"
              value={dismissReason}
              onChange={(e) => setDismissReason(e.target.value)}
              placeholder="Reason for dismissing (optional)"
              className="flex-1 text-[11px] bg-[var(--bg-1)] border border-[var(--border-subtle)] rounded px-2 py-1 text-[var(--text-1)] focus:outline-none focus:border-[var(--border-focus)]"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleDismiss()
                if (e.key === 'Escape') {
                  setShowDismissInput(false)
                  setDismissReason('')
                }
              }}
            />
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setShowDismissInput(false)
                setDismissReason('')
              }}
            >
              Cancel
            </Button>
          </div>
        )}

        <div className="flex gap-2">
          {isOpen && (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleDismiss}
              disabled={dismiss.isPending}
              className="text-[var(--text-2)]"
            >
              <XCircle className="h-3.5 w-3.5 mr-1" />
              {showDismissInput ? 'Confirm dismiss' : 'Dismiss'}
            </Button>
          )}

          {(isOpen || finding.status === 'dismissed') && (
            <Button
              variant="ghost"
              size="sm"
              onClick={handleResolve}
              disabled={resolve.isPending}
              className="text-[var(--pnl-up)]"
            >
              <CheckCircle className="h-3.5 w-3.5 mr-1" />
              Mark resolved
            </Button>
          )}

          <Button
            variant="ghost"
            size="sm"
            onClick={handleAskKiro}
            className="ml-auto text-[var(--accent-primary)]"
            title="Copy pre-filled prompt to clipboard"
          >
            <MessageSquare className="h-3.5 w-3.5 mr-1" />
            {copied ? 'Copied!' : 'Ask Kiro →'}
          </Button>
        </div>
      </div>
    </div>
  )
}
