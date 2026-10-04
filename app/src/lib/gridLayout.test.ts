import { describe, expect, it } from 'vitest'
import { buildRows, gridGeometry, moveIndex, noStrongMatches, rowOfItem, strongDivider } from './gridLayout'

describe('grid geometry', () => {
  it('fits columns and stretches cards up to 1.35×', () => {
    const g = gridGeometry(1000, 232, 12)
    expect(g.cols).toBe(4)
    expect(g.cardW).toBeLessThanOrEqual(Math.floor(232 * 1.35))
    expect(g.cardW).toBeGreaterThanOrEqual(232)
    expect(g.cardH).toBe(Math.round((g.cardW * 9) / 16) + 44)
    expect(gridGeometry(200, 232, 12).cols).toBe(1)
  })
  it('centres leftover space', () => {
    const g = gridGeometry(2000, 168, 12)
    const used = g.cols * g.cardW + (g.cols - 1) * 12
    expect(Math.abs(2000 - used - 2 * g.pad)).toBeLessThanOrEqual(1)
  })
})

describe('rows and divider', () => {
  const rows = buildRows(10, 4, 5)
  it('inserts the divider and leaves ragged rows', () => {
    expect(rows).toEqual([
      { kind: 'items', start: 0, count: 4 },
      { kind: 'items', start: 4, count: 1 },
      { kind: 'divider' },
      { kind: 'items', start: 5, count: 4 },
      { kind: 'items', start: 9, count: 1 },
    ])
    expect(rowOfItem(rows, 4)).toBe(1)
    expect(rowOfItem(rows, 5)).toBe(3)
    expect(rowOfItem(rows, 9)).toBe(4)
  })
  it('moves across the divider by column', () => {
    expect(moveIndex(rows, 2, 'down', 10)).toBe(4)
    expect(moveIndex(rows, 4, 'down', 10)).toBe(5)
    expect(moveIndex(rows, 7, 'up', 10)).toBe(4)
    expect(moveIndex(rows, 6, 'end', 10)).toBe(8)
    expect(moveIndex(rows, 9, 'right', 10)).toBe(9)
    expect(moveIndex(rows, 0, 'up', 10)).toBe(0)
  })
})

describe('match-strength divider', () => {
  it('sits after the strong results of the whole list', () => {
    expect(strongDivider({ total: 268, strong_count: 35, strictness: 'balanced' })).toBe(35)
    // The divider may lie beyond the loaded page: it is placed in the full (pre-allocated) list.
    const rows = buildRows(268, 4, strongDivider({ total: 268, strong_count: 130, strictness: 'strict' }))
    expect(rows[32]).toEqual({ kind: 'items', start: 128, count: 2 })
    expect(rows[33]).toEqual({ kind: 'divider' })
    expect(rows[34]).toEqual({ kind: 'items', start: 130, count: 4 })
  })
  it('has no divider without a score, or when every or no result is strong', () => {
    expect(strongDivider({ total: 154, strong_count: 154, strictness: null })).toBeNull()
    expect(strongDivider({ total: 40, strong_count: 40, strictness: 'loose' })).toBeNull()
    expect(strongDivider({ total: 40, strong_count: 0, strictness: 'strict' })).toBeNull()
    expect(strongDivider(undefined)).toBeNull()
    expect(strongDivider({ total: 10 })).toBeNull()
  })
  it('reports "no strong matches" only for a scored query with results', () => {
    expect(noStrongMatches({ total: 40, strong_count: 0, strictness: 'strict' })).toBe(true)
    expect(noStrongMatches({ total: 0, strong_count: 0, strictness: 'strict' })).toBe(false)
    expect(noStrongMatches({ total: 40, strong_count: 0, strictness: null })).toBe(false)
    expect(noStrongMatches({ total: 40, strong_count: 3, strictness: 'balanced' })).toBe(false)
  })
})
