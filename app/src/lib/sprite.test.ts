import { describe, expect, it } from 'vitest'
import type { Sprites } from '../api/types'
import { filmstripTiles, scrubStep, scrubTime, spriteIndexAt, spriteTile, tileAspect, tileBackground } from './sprite'

const sp: Sprites = { interval: 1, tile_w: 192, tile_h: 82, cols: 10, rows: 10, count: 230, sheets: ['sprite_001.jpg', 'sprite_002.jpg', 'sprite_003.jpg'], base: '/media/a/sprites/' }

describe('sprite tile maths', () => {
  it('maps time to tile index, clamped', () => {
    expect(spriteIndexAt(sp, 0)).toBe(0)
    expect(spriteIndexAt(sp, 12.7)).toBe(12)
    expect(spriteIndexAt(sp, -3)).toBe(0)
    expect(spriteIndexAt(sp, 9999)).toBe(229)
    expect(spriteIndexAt({ ...sp, interval: 2 }, 12.7)).toBe(6)
  })

  it('finds sheet, column and row', () => {
    expect(spriteTile(sp, 0)).toMatchObject({ sheetIndex: 0, col: 0, row: 0, sheet: '/media/a/sprites/sprite_001.jpg' })
    expect(spriteTile(sp, 37)).toMatchObject({ sheetIndex: 0, col: 7, row: 3 })
    expect(spriteTile(sp, 100)).toMatchObject({ sheetIndex: 1, col: 0, row: 0, sheet: '/media/a/sprites/sprite_002.jpg' })
    expect(spriteTile(sp, 229)).toMatchObject({ sheetIndex: 2, col: 9, row: 2 })
  })

  it('produces percentage background geometry', () => {
    const bg = tileBackground(sp, 37)
    expect(bg.size).toBe('1000% 1000%')
    expect(bg.position).toBe('77.778% 33.333%')
    expect(bg.image).toBe('url("/media/a/sprites/sprite_001.jpg")')
    expect(tileBackground(sp, 99).position).toBe('100% 100%')
  })

  it('handles a base without a trailing slash and single-column sheets', () => {
    expect(spriteTile({ ...sp, base: '/m/s' }, 0).sheet).toBe('/m/s/sprite_001.jpg')
    expect(tileBackground({ ...sp, cols: 1, rows: 1, count: 1 }, 0).position).toBe('0% 0%')
  })

  it('maps pointer fraction to 24 scrub steps and times inside the shot', () => {
    expect(scrubStep(0)).toBe(0)
    expect(scrubStep(0.5)).toBe(12)
    expect(scrubStep(1)).toBe(23)
    expect(scrubStep(-1)).toBe(0)
    expect(scrubTime(0, 10, 22)).toBeCloseTo(10.25, 5)
    expect(scrubTime(23, 10, 22)).toBeCloseTo(21.75, 5)
    expect(scrubTime(12, 10, 10)).toBe(10)
  })

  it('computes tile aspect and filmstrip tiles', () => {
    expect(tileAspect(sp)).toBeCloseTo(192 / 82)
    expect(filmstripTiles(sp, 0, 10, 100, 50)).toEqual([2, 7])
    expect(filmstripTiles(sp, 0, 10, 10, 50)).toEqual([5])
  })
})
