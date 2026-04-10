import { format, formatDistanceToNow, isToday, isYesterday, parseISO } from 'date-fns';

/**
 * Parse a date string from the backend.
 * Backend stores all timestamps in UTC but without the 'Z' suffix.
 * This function ensures they're correctly interpreted as UTC.
 */
function parseUTC(date: Date | string): Date {
  if (date instanceof Date) return date;
  // If the string has no timezone indicator, treat it as UTC
  const str = date.trim();
  if (!str.endsWith('Z') && !str.includes('+') && !/\d{2}:\d{2}$/.test(str.slice(-6))) {
    return parseISO(str + 'Z');
  }
  return parseISO(str);
}

/**
 * Format date to readable string (local timezone)
 */
export function formatDate(date: Date | string, formatStr: string = 'MMM d, yyyy'): string {
  return format(parseUTC(date), formatStr);
}

/**
 * Format date and time (local timezone)
 */
export function formatDateTime(date: Date | string): string {
  return format(parseUTC(date), 'MMM d, yyyy HH:mm:ss');
}

/**
 * Format time only (local timezone)
 */
export function formatTime(date: Date | string): string {
  return format(parseUTC(date), 'HH:mm:ss');
}

/**
 * Format relative time (e.g., "2 hours ago")
 */
export function formatRelativeTime(date: Date | string): string {
  return formatDistanceToNow(parseUTC(date), { addSuffix: true });
}

/**
 * Format date with smart relative/absolute logic (local timezone)
 */
export function formatSmartDate(date: Date | string): string {
  const dateObj = parseUTC(date);

  if (isToday(dateObj)) {
    return `Today at ${format(dateObj, 'HH:mm')}`;
  }

  if (isYesterday(dateObj)) {
    return `Yesterday at ${format(dateObj, 'HH:mm')}`;
  }

  return format(dateObj, 'MMM d, yyyy HH:mm');
}

/**
 * Parse ISO string to Date (UTC-aware)
 */
export function parseDate(dateString: string): Date {
  return parseUTC(dateString);
}


/**
 * Convert a backend UTC timestamp string to a local Date object.
 * Use this when you need a Date object (e.g., for calculations, sorting).
 * Backend timestamps are UTC but often lack the 'Z' suffix.
 */
export function utcToLocal(date: string | Date | null | undefined): Date {
  if (!date) return new Date();
  if (date instanceof Date) return date;
  const str = date.trim();
  // If no timezone indicator, append Z to force UTC interpretation
  if (!str.endsWith('Z') && !str.includes('+') && !/\d{2}:\d{2}$/.test(str.slice(-6))) {
    return new Date(str + 'Z');
  }
  return new Date(str);
}

/**
 * Format a backend UTC timestamp to a localized display string.
 * Shorthand for the most common use case.
 */
export function formatUTC(date: string | null | undefined, formatStr: string = 'MMM d, yyyy HH:mm:ss'): string {
  if (!date) return '—';
  return format(utcToLocal(date), formatStr);
}
