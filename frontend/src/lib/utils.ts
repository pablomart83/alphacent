import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

/**
 * Utility function to merge Tailwind CSS classes
 * Combines clsx for conditional classes and tailwind-merge to handle conflicts
 */
export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * Format currency values
 */
export function formatCurrency(value: number, currency: string = 'USD'): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(value);
}

/**
 * Format percentage values
 */
export function formatPercentage(value: number, decimals: number = 2): string {
  return `${value >= 0 ? '+' : ''}${value.toFixed(decimals)}%`;
}

/**
 * Format large numbers with K, M, B suffixes
 */
export function formatCompactNumber(value: number): string {
  const formatter = new Intl.NumberFormat('en-US', {
    notation: 'compact',
    compactDisplay: 'short',
    maximumFractionDigits: 1,
  });
  return formatter.format(value);
}

/**
 * Format numbers with thousand separators
 */
export function formatNumber(value: number, decimals: number = 2): string {
  return new Intl.NumberFormat('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

/**
 * Clamp a number between min and max
 */
export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

/**
 * Get color class based on value (positive/negative)
 */
export function getValueColor(value: number): string {
  if (value > 0) return 'text-accent-green';
  if (value < 0) return 'text-accent-red';
  return 'text-gray-400';
}

/**
 * Get background color class based on value (positive/negative)
 */
export function getValueBgColor(value: number): string {
  if (value > 0) return 'bg-accent-green/10';
  if (value < 0) return 'bg-accent-red/10';
  return 'bg-gray-800/50';
}

/**
 * Format a timestamp with timezone abbreviation using Intl.DateTimeFormat.
 * Returns e.g. "Jan 15, 2026 14:30 EST" or "Jan 15, 2026 EST".
 */
export function formatTimestamp(
  dateInput: string | Date,
  options?: { includeTime?: boolean; includeSeconds?: boolean }
): string {
  const { includeTime = true, includeSeconds = false } = options ?? {};

  let date: Date;
  try {
    if (dateInput instanceof Date) {
      date = dateInput;
    } else {
      // Backend emits naive UTC ISO strings (no tz suffix). JS Date() would
      // parse those as LOCAL time, causing N-hour drift where N = local UTC
      // offset. Append Z if no timezone indicator present.
      const str = String(dateInput).trim();
      const hasTz = str.endsWith('Z') || str.endsWith('z') || /[+-]\d{2}:?\d{2}$/.test(str);
      date = new Date(hasTz ? str : str + 'Z');
    }
    if (isNaN(date.getTime())) {
      return String(dateInput);
    }
  } catch {
    return String(dateInput);
  }

  const formatOptions: Intl.DateTimeFormatOptions = {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZoneName: 'short',
  };

  if (includeTime) {
    formatOptions.hour = '2-digit';
    formatOptions.minute = '2-digit';
    formatOptions.hour12 = false;
    if (includeSeconds) {
      formatOptions.second = '2-digit';
    }
  }

  return new Intl.DateTimeFormat('en-US', formatOptions).format(date);
}
