import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import type { ColumnDef, SortingState } from '@tanstack/react-table'
import {
  AlertTriangle,
  Bell,
  CheckCheck,
  Inbox,
  Settings as SettingsIcon,
  Trash2,
} from 'lucide-react'
import {
  Badge,
  Button,
  ConfirmDialog,
  DataTable,
  EmptyState,
  ErrorState,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Switch,
} from '@/components/primitives'
import { FilterBar, SectionLabel } from '@/components/layout'
import { classifyError, notifyError } from '@/lib/errors'
import { formatAge, formatTimestamp } from '@/lib/utils'
import {
  useAcknowledgeAlert,
  useAlertHistory,
  useClearAlertHistory,
  useMarkAlertRead,
  useMarkAllAlertsRead,
  type AlertHistoryRow,
  type AlertSeverity,
} from '../useGuardData'
import { AlertPreferencesDialog } from './AlertPreferencesDialog'

const SEVERITY_VARIANT: Record<string, 'info' | 'warning' | 'error'> = {
  info: 'info',
  warning: 'warning',
  critical: 'error',
  danger: 'error',
  error: 'error',
}

export function AlertsTab() {
  const [severity, setSeverity] = useState<AlertSeverity | 'all'>('all')
  const [unreadOnly, setUnreadOnly] = useState(false)
  const [prefsOpen, setPrefsOpen] = useState(false)
  const [clearOpen, setClearOpen] = useState(false)
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'created_at', desc: true },
  ])

  const history = useAlertHistory({
    severity: severity === 'all' ? null : severity,
    unread_only: unreadOnly,
    limit: 200,
  })
  const markRead = useMarkAlertRead()
  const markAllRead = useMarkAllAlertsRead()
  const ack = useAcknowledgeAlert()
  const clear = useClearAlertHistory()

  const rows = history.data?.data.alerts ?? []
  const unread = history.data?.data.unread_count ?? 0

  const columns = useMemo<ColumnDef<AlertHistoryRow>[]>(
    () => [
      {
        id: 'read',
        header: () => '',
        size: 32,
        enableSorting: false,
        cell: ({ row }) =>
          row.original.read ? (
            <span className="h-1.5 w-1.5 inline-block" />
          ) : (
            <span
              className="inline-block h-1.5 w-1.5 rounded-full"
              style={{ backgroundColor: 'var(--accent-primary)' }}
              title="Unread"
            />
          ),
      },
      {
        id: 'severity',
        header: () => 'Severity',
        accessorKey: 'severity',
        size: 90,
        cell: ({ row }) => (
          <Badge
            variant={SEVERITY_VARIANT[row.original.severity] ?? 'muted'}
            size="sm"
          >
            {row.original.severity}
          </Badge>
        ),
      },
      {
        id: 'alert_type',
        header: () => 'Type',
        accessorKey: 'alert_type',
        size: 140,
        cell: ({ row }) => (
          <span className="text-[10px] text-[var(--text-2)] mono">
            {row.original.alert_type}
          </span>
        ),
      },
      {
        id: 'title',
        header: () => 'Title',
        accessorKey: 'title',
        size: 260,
        cell: ({ row }) => (
          <span
            className="text-[var(--text-0)] font-medium truncate block max-w-[240px]"
            title={row.original.title}
          >
            {row.original.title}
          </span>
        ),
      },
      {
        id: 'message',
        header: () => 'Message',
        accessorKey: 'message',
        size: 320,
        cell: ({ row }) => (
          <span
            className="text-[10px] text-[var(--text-2)] truncate block max-w-[300px]"
            title={row.original.message}
          >
            {row.original.message}
          </span>
        ),
      },
      {
        id: 'created_at',
        header: () => 'When',
        accessorKey: 'created_at',
        size: 140,
        cell: ({ row }) => (
          <div className="flex items-baseline gap-1.5">
            <span className="mono tabular-nums text-[10px] text-[var(--text-1)]">
              {formatAge(row.original.created_at) || '—'}
            </span>
            <span className="text-[9px] text-[var(--text-3)] truncate">
              {formatTimestamp(row.original.created_at, 'short') || ''}
            </span>
          </div>
        ),
      },
      {
        id: 'actions',
        header: () => '',
        size: 200,
        enableSorting: false,
        cell: ({ row }) => {
          const r = row.original
          return (
            <div className="flex items-center justify-end gap-1" onClick={(e) => e.stopPropagation()}>
              {r.severity === 'critical' && !r.acknowledged && (
                <Button
                  size="sm"
                  variant="primary"
                  onClick={async () => {
                    try {
                      await ack.mutateAsync(r.id)
                      toast.success('Acknowledged')
                    } catch (err) {
                      notifyError(err, 'acknowledge')
                    }
                  }}
                >
                  Acknowledge
                </Button>
              )}
              {!r.read && (
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={async () => {
                    try {
                      await markRead.mutateAsync(r.id)
                    } catch (err) {
                      notifyError(err, 'mark read')
                    }
                  }}
                >
                  Mark read
                </Button>
              )}
            </div>
          )
        },
      },
    ],
    [ack, markRead],
  )

  if (history.isError) {
    const info = classifyError(history.error, 'alerts history')
    return (
      <ErrorState
        title="Couldn't load alerts"
        message={info.message}
        onRetry={() => history.refetch()}
      />
    )
  }

  return (
    <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)]">
      <FilterBar>
        <Select
          value={severity as string}
          onValueChange={(v) => setSeverity(v as AlertSeverity | 'all')}
        >
          <SelectTrigger size="sm" className="w-[130px]">
            <SelectValue placeholder="Severity" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All severities</SelectItem>
            <SelectItem value="info">Info</SelectItem>
            <SelectItem value="warning">Warning</SelectItem>
            <SelectItem value="critical">Critical</SelectItem>
          </SelectContent>
        </Select>
        <label className="inline-flex items-center gap-1.5 text-[10px] text-[var(--text-2)]">
          <Switch checked={unreadOnly} onCheckedChange={setUnreadOnly} />
          Unread only
        </label>

        <div className="ml-auto flex items-center gap-2">
          <div className="text-[10px] text-[var(--text-3)]">
            {rows.length} shown · {unread} unread
          </div>
          <Button
            size="sm"
            variant="secondary"
            onClick={async () => {
              try {
                await markAllRead.mutateAsync()
                toast.success('All alerts marked read')
              } catch (err) {
                notifyError(err, 'mark all read')
              }
            }}
            loading={markAllRead.isPending}
            disabled={unread === 0}
            className="gap-1.5"
          >
            <CheckCheck className="h-3.5 w-3.5" />
            Mark all read
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setClearOpen(true)}
            disabled={rows.length === 0}
            className="gap-1.5"
          >
            <Trash2 className="h-3.5 w-3.5" />
            Clear all
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setPrefsOpen(true)}
            className="gap-1.5"
          >
            <SettingsIcon className="h-3.5 w-3.5" />
            Preferences
          </Button>
        </div>
      </FilterBar>

      <div className="flex-1 min-h-0 overflow-auto px-3 py-3">
        <div className="flex items-center gap-2 mb-2">
          <Bell className="h-3.5 w-3.5 text-[var(--text-3)]" />
          <SectionLabel className="mb-0">Alert history</SectionLabel>
        </div>

        {rows.length === 0 && !history.isLoading ? (
          <EmptyState
            icon={Inbox}
            title="No alerts"
            description="Historical risk, monitoring, and autonomous alerts show up here once triggered."
          />
        ) : (
          <DataTable
            data={rows}
            columns={columns}
            rowKey={(r) => String(r.id)}
            loading={history.isLoading}
            sorting={{ state: sorting, onChange: setSorting }}
            density="compact"
          />
        )}

        {rows.some((r) => r.severity === 'critical' && !r.acknowledged) && (
          <div className="flex items-center gap-2 mt-3 rounded-[3px] border border-[var(--pnl-down)] bg-[color-mix(in_oklab,var(--pnl-down)_6%,transparent)] p-2 text-[10px] text-[var(--pnl-down)]">
            <AlertTriangle className="h-3.5 w-3.5" />
            Critical alerts require acknowledgement — review before they roll off retention.
          </div>
        )}
      </div>

      <AlertPreferencesDialog open={prefsOpen} onOpenChange={setPrefsOpen} />

      <ConfirmDialog
        open={clearOpen}
        onOpenChange={setClearOpen}
        title="Clear all alerts"
        description="Removes every alert from history, including unacknowledged critical alerts. This cannot be undone."
        confirmLabel="Clear all"
        confirmVariant="destructive"
        isLoading={clear.isPending}
        onConfirm={async () => {
          try {
            await clear.mutateAsync()
            toast.success('Alert history cleared')
            setClearOpen(false)
          } catch (err) {
            notifyError(err, 'clear alerts')
          }
        }}
      />
    </div>
  )
}
