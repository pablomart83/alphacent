import { type FC, type ReactNode } from 'react';
import { Search } from 'lucide-react';
import { Input } from './Input';
import { cn } from '../../lib/utils';

interface FilterBarProps {
  /** Left-side info text (e.g. "127 of 297 symbols") */
  info?: string;
  /** Search input value */
  searchValue?: string;
  /** Search input change handler */
  onSearchChange?: (value: string) => void;
  /** Search placeholder */
  searchPlaceholder?: string;
  /** Additional filter controls (Select dropdowns, buttons) rendered after search */
  children?: ReactNode;
  className?: string;
}

/**
 * Inline filter bar for tab interiors — replaces scattered filter patterns.
 * Renders as a single compact row: info text | search | custom filters.
 *
 * Usage:
 * ```tsx
 * <FilterBar
 *   info={`${filtered.length} of ${total.length}`}
 *   searchValue={search}
 *   onSearchChange={setSearch}
 *   searchPlaceholder="Search symbol..."
 * >
 *   <Select value={filter} onValueChange={setFilter}>...</Select>
 * </FilterBar>
 * ```
 */
export const FilterBar: FC<FilterBarProps> = ({
  info,
  searchValue,
  onSearchChange,
  searchPlaceholder = 'Search...',
  children,
  className,
}) => (
  <div className={cn('flex items-center gap-2 py-1', className)}>
    {info && <span className="text-[10px] text-gray-500 shrink-0">{info}</span>}
    {onSearchChange !== undefined && (
      <div className="relative ml-auto">
        <Search className="absolute left-2 top-1/2 transform -translate-y-1/2 h-3 w-3 text-gray-500" />
        <Input
          placeholder={searchPlaceholder}
          value={searchValue ?? ''}
          onChange={(e) => onSearchChange(e.target.value)}
          className="pl-7 h-7 text-xs w-[150px]"
        />
      </div>
    )}
    {!onSearchChange && <div className="ml-auto" />}
    {children}
  </div>
);
