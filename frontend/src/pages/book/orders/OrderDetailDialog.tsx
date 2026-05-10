import {
  Badge,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives'
import { formatCurrency, formatTimestamp } from '@/lib/utils'
import type { OrderRow } from '../useBookData'
import { slippageBps } from './orderColumns'

interface OrderDetailDialogProps {
  order: OrderRow | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

function statusVariant(status: OrderRow['status']) {
  switch (status) {
    case 'FILLED':
      return 'success' as const
    case 'PENDING':
    case 'SUBMITTED':
    case 'PARTIALLY_FILLED':
      return 'warning' as const
    case 'CANCELLED':
      return 'muted' as const
    case 'REJECTED':
    case 'FAILED':
      return 'error' as const
    default:
      return 'default' as const
  }
}

export function OrderDetailDialog({ order, open, onOpenChange }: OrderDetailDialogProps) {
  if (!order) return null
  const bps = slippageBps(order)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>
            <span className="mono">{order.symbol}</span>
            <span className="text-[var(--text-3)] mx-1.5 text-[13px] font-normal">·</span>
            <span className="text-[13px]">{order.side} {order.order_type}</span>
          </DialogTitle>
          <DialogDescription>
            Order {order.id} · {order.strategy_name || 'Manual'}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3 mt-2">
          <div className="flex items-center gap-2">
            <Badge variant={statusVariant(order.status)} size="md">
              {order.status}
            </Badge>
            {order.order_action && (
              <Badge variant="muted" size="md">
                {order.order_action}
              </Badge>
            )}
            {order.etoro_order_id && (
              <span className="ml-auto text-[10px] text-[var(--text-3)] mono">
                eToro #{order.etoro_order_id}
              </span>
            )}
          </div>

          <div className="grid grid-cols-2 gap-2">
            <DetailRow label="Quantity" value={formatCurrency(order.quantity, { precision: 0 })} mono />
            <DetailRow label="Expected" value={order.expected_price != null ? order.expected_price.toString() : '—'} mono />
            <DetailRow label="Filled price" value={order.filled_price != null ? order.filled_price.toString() : '—'} mono />
            <DetailRow label="Filled qty" value={order.filled_quantity != null ? formatCurrency(order.filled_quantity, { precision: 0 }) : '—'} mono />
            <DetailRow
              label="Slippage"
              value={bps != null ? `${bps >= 0 ? '+' : ''}${bps.toFixed(1)} bps` : '—'}
              mono
              colour={
                bps == null
                  ? 'text-[var(--text-3)]'
                  : Math.abs(bps) < 3
                    ? 'text-[var(--text-1)]'
                    : bps > 0
                      ? 'text-[var(--pnl-down)]'
                      : 'text-[var(--pnl-up)]'
              }
            />
            <DetailRow
              label="Fill time"
              value={
                order.fill_time_seconds != null
                  ? order.fill_time_seconds < 60
                    ? `${order.fill_time_seconds.toFixed(1)}s`
                    : `${Math.round(order.fill_time_seconds / 60)}m`
                  : '—'
              }
              mono
            />
            <DetailRow label="Created" value={formatTimestamp(order.created_at, 'long')} />
            <DetailRow label="Filled at" value={formatTimestamp(order.filled_at, 'long')} />
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function DetailRow({
  label,
  value,
  mono,
  colour,
}: {
  label: string
  value: string
  mono?: boolean
  colour?: string
}) {
  return (
    <div className="flex flex-col gap-0.5 rounded-[3px] bg-[var(--bg-2)] border border-[var(--border-subtle)] px-2.5 py-1.5">
      <span className="text-[10px] uppercase tracking-wider text-[var(--text-3)]">{label}</span>
      <span
        className={[
          'text-[12px]',
          mono ? 'mono tabular-nums' : '',
          colour ?? 'text-[var(--text-0)]',
        ].join(' ')}
      >
        {value}
      </span>
    </div>
  )
}
