import { useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowLeft } from 'lucide-react'
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/primitives'
import { api } from '@/services/api'
import { notifyError } from '@/lib/errors'
import { formatCurrency } from '@/lib/utils'
import { toast } from 'sonner'
import { useTradingMode } from '@/stores'
import {
  usePlaceOrder,
  type OrderSide,
  type OrderType,
  type PlaceOrderBody,
} from '../useBookData'

interface SlimStrategyRow {
  id: string
  name: string
  status: string
  symbols: string[]
}

interface SlimStrategiesPayload {
  strategies: SlimStrategyRow[]
  total_count: number
}

interface PlaceOrderDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

type Step = 'fill' | 'review'

interface FormState {
  strategyId: string
  symbol: string
  side: OrderSide
  orderType: OrderType
  quantity: string
  price: string
  stopPrice: string
}

const INITIAL: FormState = {
  strategyId: '',
  symbol: '',
  side: 'BUY',
  orderType: 'MARKET',
  quantity: '',
  price: '',
  stopPrice: '',
}

export function PlaceOrderDialog({ open, onOpenChange }: PlaceOrderDialogProps) {
  const mode = useTradingMode((s) => s.mode)
  const [step, setStep] = useState<Step>('fill')
  const [form, setForm] = useState<FormState>(INITIAL)

  const strategiesQuery = useQuery<SlimStrategiesPayload>({
    queryKey: ['strategies', mode, { slim: true }],
    queryFn: () =>
      api.get<SlimStrategiesPayload>('/strategies', { mode, slim: true }),
    enabled: open,
    staleTime: 60_000,
  })

  const placeMutation = usePlaceOrder()

  const strategyOptions = useMemo(() => {
    return (strategiesQuery.data?.strategies ?? [])
      .filter((s) => s.status === 'PAPER' || s.status === 'LIVE' || s.status === 'BACKTESTED')
      .sort((a, b) => a.name.localeCompare(b.name))
  }, [strategiesQuery.data])

  const quantityNum = Number(form.quantity)
  const priceNum = Number(form.price)
  const stopNum = Number(form.stopPrice)

  const errors: string[] = useMemo(() => {
    const errs: string[] = []
    if (!form.strategyId) errs.push('Pick a strategy.')
    if (!form.symbol.trim()) errs.push('Enter a symbol.')
    if (!Number.isFinite(quantityNum) || quantityNum <= 0) errs.push('Quantity must be positive.')
    if (form.orderType === 'LIMIT' && (!Number.isFinite(priceNum) || priceNum <= 0)) {
      errs.push('Limit price required for LIMIT orders.')
    }
    if (form.orderType === 'STOP_LOSS' && (!Number.isFinite(stopNum) || stopNum <= 0)) {
      errs.push('Stop price required for STOP_LOSS orders.')
    }
    return errs
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form.strategyId, form.symbol, quantityNum, priceNum, stopNum, form.orderType])

  const canProceed = errors.length === 0

  const reset = () => {
    setForm(INITIAL)
    setStep('fill')
  }

  const handleClose = (o: boolean) => {
    if (!o) reset()
    onOpenChange(o)
  }

  const handleSubmit = async () => {
    const body: PlaceOrderBody = {
      strategy_id: form.strategyId,
      symbol: form.symbol.trim().toUpperCase(),
      side: form.side,
      order_type: form.orderType,
      quantity: quantityNum,
    }
    if (form.orderType === 'LIMIT') body.price = priceNum
    if (form.orderType === 'STOP_LOSS') body.stop_price = stopNum

    try {
      const res = await placeMutation.mutateAsync({ body, mode })
      toast.success(res.message || `Submitted ${form.side} ${form.symbol}`)
      handleClose(false)
    } catch (e) {
      notifyError(e, 'place order')
    }
  }

  const selectedStrategy = strategyOptions.find((s) => s.id === form.strategyId)

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[500px]">
        <DialogHeader>
          <DialogTitle>
            {step === 'fill' ? 'Manual order' : 'Review and submit'}
          </DialogTitle>
          <DialogDescription>
            {step === 'fill'
              ? `Routes through ${mode} account. Backend enforces risk caps.`
              : 'Double-check everything. Submits a live order via eToro.'}
          </DialogDescription>
        </DialogHeader>

        {step === 'fill' ? (
          <div className="flex flex-col gap-3 mt-1">
            <div className="flex flex-col gap-1.5">
              <Label>Strategy</Label>
              <Select
                value={form.strategyId}
                onValueChange={(v) => setForm((f) => ({ ...f, strategyId: v }))}
              >
                <SelectTrigger size="sm">
                  <SelectValue placeholder="Select strategy…" />
                </SelectTrigger>
                <SelectContent>
                  {strategyOptions.length === 0 ? (
                    <SelectItem value="__none" disabled>
                      No eligible strategies
                    </SelectItem>
                  ) : (
                    strategyOptions.map((s) => (
                      <SelectItem key={s.id} value={s.id}>
                        <span className="truncate max-w-[360px]">
                          {s.name} · {s.status}
                        </span>
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="flex flex-col gap-1.5">
                <Label>Symbol</Label>
                <Input
                  value={form.symbol}
                  onChange={(e) => setForm((f) => ({ ...f, symbol: e.target.value }))}
                  placeholder="AAPL / BTC / EURUSD"
                  className="mono uppercase"
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Side</Label>
                <Select
                  value={form.side}
                  onValueChange={(v) => setForm((f) => ({ ...f, side: v as OrderSide }))}
                >
                  <SelectTrigger size="sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="BUY">Buy (long)</SelectItem>
                    <SelectItem value="SELL">Sell (short)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="flex flex-col gap-1.5">
                <Label>Order type</Label>
                <Select
                  value={form.orderType}
                  onValueChange={(v) => setForm((f) => ({ ...f, orderType: v as OrderType }))}
                >
                  <SelectTrigger size="sm">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="MARKET">Market</SelectItem>
                    <SelectItem value="LIMIT">Limit</SelectItem>
                    <SelectItem value="STOP_LOSS">Stop</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>Quantity ($ invested)</Label>
                <Input
                  type="number"
                  inputMode="decimal"
                  min={1}
                  step="any"
                  value={form.quantity}
                  onChange={(e) => setForm((f) => ({ ...f, quantity: e.target.value }))}
                  placeholder="2000"
                  className="mono"
                />
              </div>
            </div>

            {(form.orderType === 'LIMIT' || form.orderType === 'STOP_LOSS') && (
              <div className="grid grid-cols-2 gap-2">
                {form.orderType === 'LIMIT' && (
                  <div className="flex flex-col gap-1.5">
                    <Label>Limit price</Label>
                    <Input
                      type="number"
                      step="any"
                      inputMode="decimal"
                      value={form.price}
                      onChange={(e) => setForm((f) => ({ ...f, price: e.target.value }))}
                      className="mono"
                    />
                  </div>
                )}
                {form.orderType === 'STOP_LOSS' && (
                  <div className="flex flex-col gap-1.5">
                    <Label>Stop price</Label>
                    <Input
                      type="number"
                      step="any"
                      inputMode="decimal"
                      value={form.stopPrice}
                      onChange={(e) => setForm((f) => ({ ...f, stopPrice: e.target.value }))}
                      className="mono"
                    />
                  </div>
                )}
              </div>
            )}

            {errors.length > 0 && (
              <ul className="flex flex-col gap-0.5 text-[10px] text-[var(--status-warning)]">
                {errors.map((e) => (
                  <li key={e}>· {e}</li>
                ))}
              </ul>
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-2 mt-1">
            <ReviewLine label="Account" value={mode} />
            <ReviewLine label="Strategy" value={selectedStrategy?.name ?? form.strategyId} />
            <ReviewLine label="Symbol" value={form.symbol.toUpperCase()} mono />
            <ReviewLine label="Side" value={form.side} />
            <ReviewLine label="Type" value={form.orderType} />
            <ReviewLine label="Quantity" value={formatCurrency(quantityNum, { precision: 0 })} mono />
            {form.orderType === 'LIMIT' && (
              <ReviewLine label="Limit price" value={String(priceNum)} mono />
            )}
            {form.orderType === 'STOP_LOSS' && (
              <ReviewLine label="Stop price" value={String(stopNum)} mono />
            )}
            <div className="mt-2 rounded-[3px] border border-[var(--status-warning)]/40 bg-[var(--status-warning-bg)] px-2.5 py-2 text-[11px] leading-[16px] text-[var(--status-warning)]">
              This submits an order via eToro. Cap rules still apply server-side —
              expect a 400 if risk validation rejects it.
            </div>
          </div>
        )}

        <DialogFooter className="mt-4">
          {step === 'review' ? (
            <Button variant="ghost" onClick={() => setStep('fill')} className="gap-1">
              <ArrowLeft className="h-3 w-3" />
              Back
            </Button>
          ) : (
            <Button variant="ghost" onClick={() => handleClose(false)}>
              Cancel
            </Button>
          )}
          {step === 'fill' ? (
            <Button
              variant="primary"
              onClick={() => setStep('review')}
              disabled={!canProceed}
            >
              Review
            </Button>
          ) : (
            <Button
              variant="primary"
              onClick={handleSubmit}
              loading={placeMutation.isPending}
            >
              Submit {form.side}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function ReviewLine({
  label,
  value,
  mono,
}: {
  label: string
  value: string
  mono?: boolean
}) {
  return (
    <div className="flex items-center justify-between px-2.5 py-1.5 rounded-[3px] bg-[var(--bg-2)] border border-[var(--border-subtle)]">
      <span className="text-[10px] uppercase tracking-wider text-[var(--text-3)]">{label}</span>
      <span className={`text-[12px] text-[var(--text-0)] ${mono ? 'mono tabular-nums' : ''}`}>
        {value}
      </span>
    </div>
  )
}
