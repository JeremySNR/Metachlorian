import { describe, expect, it } from 'vitest'
import { buildRows, gridGeometry, moveIndex, rowOfItem, weakSplit } from './gridLayout'

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
  it('finds the weak split', () => {
    expect(weakSplit([1, 0.9, 0.6, 0.4], 0.5, 4)).toBe(3)
    expect(weakSplit([1, 0.9], 0.5, 10)).toBeNull()
  })
})
