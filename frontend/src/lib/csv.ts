/**
 * Minimal CSV export helper. Values are RFC-4180 quoted when they contain
 * quotes, commas, or newlines. Null/undefined rendered as empty string.
 * Triggers a browser download via a hidden `<a>` element.
 */

export type CsvValue = string | number | boolean | null | undefined | Date

export interface CsvColumn<T> {
  header: string
  /** Extract a value from a row. */
  value: (row: T) => CsvValue
}

function escapeCell(raw: CsvValue): string {
  if (raw == null) return ''
  const value =
    raw instanceof Date
      ? raw.toISOString()
      : typeof raw === 'boolean'
        ? raw
          ? 'true'
          : 'false'
        : String(raw)
  if (/[",\r\n]/.test(value)) {
    return `"${value.replace(/"/g, '""')}"`
  }
  return value
}

export function toCsv<T>(rows: T[], columns: CsvColumn<T>[]): string {
  const head = columns.map((c) => escapeCell(c.header)).join(',')
  const body = rows
    .map((row) => columns.map((c) => escapeCell(c.value(row))).join(','))
    .join('\r\n')
  return body ? `${head}\r\n${body}` : head
}

export function downloadCsv<T>(
  filename: string,
  rows: T[],
  columns: CsvColumn<T>[],
): void {
  const csv = toCsv(rows, columns)
  // UTF-8 BOM so Excel opens it without mis-decoding.
  const blob = new Blob([`\uFEFF${csv}`], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename.endsWith('.csv') ? filename : `${filename}.csv`
  a.style.display = 'none'
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  // Revoke on next tick to make sure the download has started
  setTimeout(() => URL.revokeObjectURL(url), 0)
}
