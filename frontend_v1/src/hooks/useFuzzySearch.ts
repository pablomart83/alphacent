import { useMemo, useCallback } from 'react';
import Fuse from 'fuse.js';

export interface SearchableItem {
  id: string;
  type: 'symbol' | 'strategy' | 'page' | 'action';
  label: string;
  description?: string;
  icon?: string;
  action: () => void;
}

export interface FuzzySearchResult {
  item: SearchableItem;
  score: number;
}

const FUSE_OPTIONS = {
  keys: [
    { name: 'label', weight: 0.7 },
    { name: 'description', weight: 0.3 },
  ],
  threshold: 0.4,
  includeScore: true,
  minMatchCharLength: 1,
  shouldSort: true,
};

/**
 * Fuzzy search hook wrapping fuse.js.
 * Accepts a list of searchable items and returns a search function.
 * Results are grouped by category and scored for relevance.
 */
export function useFuzzySearch(items: SearchableItem[]) {
  const fuse = useMemo(() => new Fuse(items, FUSE_OPTIONS), [items]);

  const search = useCallback(
    (query: string): FuzzySearchResult[] => {
      if (!query.trim()) return [];
      const results = fuse.search(query, { limit: 20 });
      return results.map((r) => ({
        item: r.item,
        score: r.score ?? 1,
      }));
    },
    [fuse],
  );

  /** Group results by type category */
  const searchGrouped = useCallback(
    (query: string) => {
      const results = search(query);
      const groups: Record<string, FuzzySearchResult[]> = {};
      for (const r of results) {
        const key = r.item.type;
        if (!groups[key]) groups[key] = [];
        groups[key].push(r);
      }
      return groups;
    },
    [search],
  );

  return { search, searchGrouped };
}
