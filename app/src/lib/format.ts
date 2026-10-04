/** British English number, size and date formatting (system.md §8). */

const nf = new Intl.NumberFormat('en-GB')

export function formatNumber(n: number | null | undefined): string {
  return n === null || n === undefined || !Number.isFinite(n) ? '—' : nf.format(n)
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${formatNumber(n)} ${n === 1 ? one : many}`
}

/** Decimal units with a space: "1.2 GB". */
export function formatBytes(bytes: number | null | undefined): string {
  if (!bytes || bytes < 0) return '0 B'
  const units = ['B', 'kB', 'MB', 'GB', 'TB', 'PB']
  let i = 0
  let v = bytes
  while (v >= 1000 && i < units.length - 1) {
    v /= 1000
    i++
  }
  return `${v >= 100 || i === 0 ? Math.round(v) : v.toFixed(1)} ${units[i]}`
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function toDate(v: number | string | Date | null | undefined): Date | null {
  if (v === null || v === undefined || v === '') return null
  if (v instanceof Date) return v
  if (typeof v === 'number') return new Date(v < 1e12 ? v * 1000 : v)
  const d = new Date(v.length === 10 ? `${v}T00:00:00` : v)
  return Number.isNaN(d.getTime()) ? null : d
}

/** "4 Oct 2026" */
export function formatDate(v: number | string | Date | null | undefined): string {
  const d = toDate(v)
  return d ? `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}` : '—'
}

/** "4 Oct" */
export function formatDayMonth(v: number | string | Date | null | undefined): string {
  const d = toDate(v)
  return d ? `${d.getDate()} ${MONTHS[d.getMonth()]}` : '—'
}

/** "4 Oct 2026, 14:05" (24-hour) */
export function formatDateTime(v: number | string | Date | null | undefined): string {
  const d = toDate(v)
  if (!d) return '—'
  return `${formatDate(d)}, ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** Relative only under 7 days ("2 days ago"), absolute otherwise. */
export function formatRelative(v: number | string | Date | null | undefined, now = Date.now()): string {
  const d = toDate(v)
  if (!d) return '—'
  const s = Math.round((now - d.getTime()) / 1000)
  if (s < 0 || s > 7 * 86400) return formatDate(d)
  if (s < 45) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) {
    const h = Math.round(s / 3600)
    return `${h} hour${h === 1 ? '' : 's'} ago`
  }
  const days = Math.round(s / 86400)
  return `${days} day${days === 1 ? '' : 's'} ago`
}

/** Days from today to an ISO date (negative when past). */
export function daysUntil(iso: string | null | undefined, now = new Date()): number | null {
  const d = toDate(iso ?? null)
  if (!d) return null
  const a = Date.UTC(now.getFullYear(), now.getMonth(), now.getDate())
  const b = Date.UTC(d.getFullYear(), d.getMonth(), d.getDate())
  return Math.round((b - a) / 86400000)
}

/** "close_up" → "Close up" (fallback when no vocabulary label is known). */
export function humanise(term: string | null | undefined): string {
  if (!term) return ''
  const s = term.replace(/[_-]+/g, ' ').trim()
  return s.charAt(0).toUpperCase() + s.slice(1)
}

/** "Close-up (CU)" → "Close-up": vocabulary labels without the abbreviation. */
export function shortLabel(label: string): string {
  return label.replace(/\s*\([^)]*\)\s*$/, '').trim() || label
}

export function percent(v: number | null | undefined, digits = 0): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—'
  return `${(v * 100).toFixed(digits)}%`
}

export function resolutionLabel(width?: number | null, height?: number | null): string {
  if (!width || !height) return ''
  return `${width}×${height}`
}

/** Aspect label for non-16:9 frames: 9:16, 2.39:1, 4:3, 1:1. */
export function aspectLabel(ratio: number | null | undefined): string | null {
  if (!ratio || !Number.isFinite(ratio)) return null
  const known: [number, string][] = [
    [16 / 9, '16:9'],
    [9 / 16, '9:16'],
    [1, '1:1'],
    [4 / 5, '4:5'],
    [4 / 3, '4:3'],
    [3 / 4, '3:4'],
    [2.39, '2.39:1'],
    [2.35, '2.35:1'],
    [1.85, '1.85:1'],
    [2, '2:1'],
    [21 / 9, '21:9'],
  ]
  let best = known[0]
  for (const k of known) if (Math.abs(k[0] - ratio) < Math.abs(best[0] - ratio)) best = k
  if (Math.abs(best[0] - ratio) / ratio > 0.03) return `${ratio.toFixed(2)}:1`
  return best[1]
}
