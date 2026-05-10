import { useCallback, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { Search } from 'lucide-react'
import {
  Button,
  ErrorState,
  Input,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/primitives'
import { FilterBar } from '@/components/layout'
import { classifyError } from '@/lib/errors'
import {
  useBulkToggleTemplates,
  useTemplateRankings,
  useTemplates,
  useToggleTemplate,
} from '../useStrategiesData'
import { TemplatesGrid } from './TemplatesGrid'
import { TemplateRankingsTable } from './TemplateRankingsTable'

/**
 * Templates tab — /strategies/templates.
 * Grid of templates with toggle + rule preview; ranking leaderboard below.
 */
export function TemplatesTab() {
  const templatesQuery = useTemplates()
  const rankingsQuery = useTemplateRankings()
  const toggleOne = useToggleTemplate()
  const bulkToggle = useBulkToggleTemplates()

  const [search, setSearch] = useState('')
  const [direction, setDirection] = useState<'all' | 'long' | 'short' | 'any'>(
    'all',
  )
  const [assetClass, setAssetClass] = useState<string>('all')
  const [enabledFilter, setEnabledFilter] = useState<'all' | 'enabled' | 'disabled'>(
    'all',
  )
  const [selected, setSelected] = useState<Set<string>>(() => new Set())
  const [pendingToggleName, setPendingToggleName] = useState<string | null>(null)

  const templates = templatesQuery.data?.templates ?? []

  const assetClassOptions = useMemo(() => {
    const classes = new Set<string>()
    templates.forEach((t) => (t.asset_classes ?? []).forEach((c) => classes.add(c)))
    return Array.from(classes).sort()
  }, [templates])

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase()
    return templates.filter((t) => {
      if (q) {
        const hay = `${t.name} ${t.description}`.toLowerCase()
        if (!hay.includes(q)) return false
      }
      if (direction !== 'all') {
        const d = (t.direction ?? '').toLowerCase()
        if (direction === 'any') {
          if (d !== 'any' && d !== 'both') return false
        } else if (d !== direction) return false
      }
      if (assetClass !== 'all') {
        if (!(t.asset_classes ?? []).includes(assetClass)) return false
      }
      if (enabledFilter === 'enabled' && !t.enabled) return false
      if (enabledFilter === 'disabled' && t.enabled) return false
      return true
    })
  }, [templates, search, direction, assetClass, enabledFilter])

  const toggleSelection = useCallback((name: string, checked: boolean) => {
    setSelected((cur) => {
      const next = new Set(cur)
      if (checked) next.add(name)
      else next.delete(name)
      return next
    })
  }, [])

  const clearSelection = () => setSelected(new Set())

  const handleToggleOne = async (name: string, enabled: boolean) => {
    setPendingToggleName(name)
    try {
      await toggleOne.mutateAsync({ name, enabled })
      toast.success(`${enabled ? 'Enabled' : 'Disabled'} ${name}`)
    } catch (err) {
      const info = classifyError(err, 'toggle template')
      toast.error(info.title, { description: info.message })
    } finally {
      setPendingToggleName(null)
    }
  }

  const handleBulk = async (enabled: boolean) => {
    if (selected.size === 0) return
    try {
      const names = Array.from(selected)
      await bulkToggle.mutateAsync({ names, enabled })
      toast.success(
        `${enabled ? 'Enabled' : 'Disabled'} ${names.length} template${names.length === 1 ? '' : 's'}`,
      )
      clearSelection()
    } catch (err) {
      const info = classifyError(err, 'bulk toggle')
      toast.error(info.title, { description: info.message })
    }
  }

  if (templatesQuery.isError) {
    const info = classifyError(templatesQuery.error, 'templates')
    return (
      <ErrorState
        title="Couldn't load templates"
        message={info.message}
        onRetry={() => templatesQuery.refetch()}
      />
    )
  }

  return (
    <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)] overflow-auto">
      <FilterBar>
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-[var(--text-3)] pointer-events-none" />
          <Input
            data-templates-search
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search templates…"
            className="h-7 pl-7 w-[220px] text-[11px]"
          />
        </div>
        <Select value={direction} onValueChange={(v) => setDirection(v as typeof direction)}>
          <SelectTrigger size="sm" className="w-[110px]">
            <SelectValue placeholder="Direction" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Any dir</SelectItem>
            <SelectItem value="long">Long</SelectItem>
            <SelectItem value="short">Short</SelectItem>
            <SelectItem value="any">Bi-directional</SelectItem>
          </SelectContent>
        </Select>
        <Select value={assetClass} onValueChange={setAssetClass}>
          <SelectTrigger size="sm" className="w-[130px]">
            <SelectValue placeholder="Asset class" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All classes</SelectItem>
            {assetClassOptions.map((c) => (
              <SelectItem key={c} value={c}>
                {c}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={enabledFilter}
          onValueChange={(v) => setEnabledFilter(v as typeof enabledFilter)}
        >
          <SelectTrigger size="sm" className="w-[110px]">
            <SelectValue placeholder="Enabled" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All states</SelectItem>
            <SelectItem value="enabled">Enabled</SelectItem>
            <SelectItem value="disabled">Disabled</SelectItem>
          </SelectContent>
        </Select>
        <div className="ml-auto flex items-center gap-2 text-[10px] text-[var(--text-3)]">
          {filtered.length} of {templates.length}
        </div>
      </FilterBar>

      {selected.size > 0 && (
        <div className="flex items-center justify-between gap-2 py-1.5 px-2 bg-[var(--bg-1)] border-b border-[var(--border-subtle)]">
          <span className="text-[11px] text-[var(--text-1)]">
            {selected.size} selected
          </span>
          <div className="flex items-center gap-1.5">
            <Button
              size="sm"
              variant="ghost"
              onClick={clearSelection}
              disabled={bulkToggle.isPending}
            >
              Clear
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => handleBulk(false)}
              loading={bulkToggle.isPending}
            >
              Disable selected
            </Button>
            <Button
              size="sm"
              variant="primary"
              onClick={() => handleBulk(true)}
              loading={bulkToggle.isPending}
            >
              Enable selected
            </Button>
          </div>
        </div>
      )}

      <TemplatesGrid
        templates={filtered}
        loading={templatesQuery.isLoading}
        selected={selected}
        onToggleSelection={toggleSelection}
        onToggleEnabled={handleToggleOne}
        pendingToggleName={pendingToggleName}
      />

      <TemplateRankingsTable
        rankings={rankingsQuery.data?.rankings ?? []}
        templates={templates}
        loading={rankingsQuery.isLoading}
      />
    </div>
  )
}
