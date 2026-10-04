/**
 * Results grid geometry (system.md §2.3): cards stretch up to 1.35 × their
 * minimum width; leftover space goes to the margins (no ragged right edge).
 * A "Weaker matches below" divider row can be inserted at an item index.
 */

export interface GridGeometry {
  cols: number
  cardW: number
  cardH: number
  rowH: number
  pad: number
  gap: number
}

export const STRIP_HEIGHT = 44

export function gridGeometry(width: number, minW: number, gap: number, minPad = 16): GridGeometry {
  const usable = Math.max(minW, width - 2 * minPad)
  const cols = Math.max(1, Math.floor((usable + gap) / (minW + gap)))
  const cardW = Math.floor(Math.min(minW * 1.35, (usable - (cols - 1) * gap) / cols))
  const used = cols * cardW + (cols - 1) * gap
  const pad = Math.max(minPad, Math.floor((width - used) / 2))
  const cardH = Math.round((cardW * 9) / 16) + STRIP_HEIGHT
  return { cols, cardW, cardH, rowH: cardH + gap + 4, pad, gap }
}

export type VRow = { kind: 'items'; start: number; count: number } | { kind: 'divider' }

/** Rows for `total` items in `cols` columns, with an optional divider before item `split`. */
export function buildRows(total: number, cols: number, split: number | null): VRow[] {
  const rows: VRow[] = []
  const push = (from: number, to: number) => {
    for (let i = from; i < to; i += cols) rows.push({ kind: 'items', start: i, count: Math.min(cols, to - i) })
  }
  if (split !== null && split > 0 && split < total) {
    push(0, split)
    rows.push({ kind: 'divider' })
    push(split, total)
  } else push(0, total)
  return rows
}

/** Row index holding item `i`. */
export function rowOfItem(rows: VRow[], i: number): number {
  let lo = 0
  let hi = rows.length - 1
  // rows are ordered by start; dividers carry no items
  while (lo <= hi) {
    const mid = (lo + hi) >> 1
    const r = rows[mid]
    if (r.kind === 'divider') {
      const prev = rows[mid - 1]
      if (prev && prev.kind === 'items' && i < prev.start + prev.count) hi = mid - 1
      else lo = mid + 1
      continue
    }
    if (i < r.start) hi = mid - 1
    else if (i >= r.start + r.count) lo = mid + 1
    else return mid
  }
  return Math.max(0, Math.min(rows.length - 1, lo))
}

/** Item index after moving from `i` by arrow key, respecting the divider's ragged rows. */
export function moveIndex(rows: VRow[], i: number, key: 'up' | 'down' | 'left' | 'right' | 'home' | 'end', total: number): number {
  if (!total) return 0
  const ri = rowOfItem(rows, i)
  const row = rows[ri]
  if (row.kind !== 'items') return i
  const col = i - row.start
  switch (key) {
    case 'left':
      return Math.max(0, i - 1)
    case 'right':
      return Math.min(total - 1, i + 1)
    case 'home':
      return row.start
    case 'end':
      return row.start + row.count - 1
    case 'up':
    case 'down': {
      let r = ri + (key === 'up' ? -1 : 1)
      while (r >= 0 && r < rows.length && rows[r].kind !== 'items') r += key === 'up' ? -1 : 1
      if (r < 0 || r >= rows.length) return i
      const target = rows[r] as Extract<VRow, { kind: 'items' }>
      return target.start + Math.min(col, target.count - 1)
    }
  }
}

/** What the core says about match strength for a result list (POST /api/search, /api/similar). */
export interface StrengthInfo {
  total: number
  strong_count?: number | null
  /** null when the query has nothing to score (a filter-only browse): every result is strong. */
  strictness?: string | null
}

/**
 * Where the "Weaker matches below" divider goes: after the first `strong_count` results of the
 * whole list (the core orders strong matches first). Null when there is no divider: nothing to
 * score, every result is strong, or none is (that case is the "No strong matches" state).
 */
export function strongDivider(info: StrengthInfo | null | undefined): number | null {
  if (!info || !info.strictness || typeof info.strong_count !== 'number') return null
  const n = info.strong_count
  if (n <= 0 || n >= info.total) return null
  return n
}

/** True when a scored query found results but none clears the strictness threshold. */
export function noStrongMatches(info: StrengthInfo | null | undefined): boolean {
  return Boolean(info && info.strictness && info.strong_count === 0 && info.total > 0)
}
