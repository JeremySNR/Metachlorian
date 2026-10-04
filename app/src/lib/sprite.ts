/**
 * Sprite-sheet maths for hover scrubbing and filmstrip thumbnails.
 *
 * The core writes one sprite set per file (asset `media.sprites`): one tile every
 * `interval` seconds, `cols × rows` tiles per sheet (sheets are always full grids),
 * `count` tiles in total. Scrubbing swaps `background-position` on a div through
 * a ref, so a frame change never touches React or decodes video.
 */
import type { Sprites } from '../api/types'

/** Number of scrub positions across a card (system.md §3.6: floor(x / width × 24)). */
export const SCRUB_STEPS = 24

export const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))

/** Tile index for a time in the file. */
export function spriteIndexAt(sp: Sprites, t: number): number {
  const interval = sp.interval > 0 ? sp.interval : 1
  return clamp(Math.floor(t / interval + 1e-6), 0, Math.max(0, sp.count - 1))
}

export interface TileRef {
  sheet: string
  sheetIndex: number
  col: number
  row: number
}

export function spriteTile(sp: Sprites, index: number): TileRef {
  const perSheet = Math.max(1, sp.cols * sp.rows)
  const i = clamp(Math.floor(index), 0, Math.max(0, sp.count - 1))
  const sheetIndex = clamp(Math.floor(i / perSheet), 0, Math.max(0, sp.sheets.length - 1))
  const local = i - sheetIndex * perSheet
  const base = sp.base.endsWith('/') ? sp.base : `${sp.base}/`
  return { sheet: `${base}${sp.sheets[sheetIndex] ?? ''}`, sheetIndex, col: local % sp.cols, row: Math.floor(local / sp.cols) }
}

/** Percentage background geometry that works at any element size. */
export function tileBackground(sp: Sprites, index: number): { image: string; size: string; position: string } {
  const t = spriteTile(sp, index)
  const x = sp.cols > 1 ? (t.col / (sp.cols - 1)) * 100 : 0
  const y = sp.rows > 1 ? (t.row / (sp.rows - 1)) * 100 : 0
  return { image: `url("${t.sheet}")`, size: `${sp.cols * 100}% ${sp.rows * 100}%`, position: `${round(x)}% ${round(y)}%` }
}

const round = (n: number) => Math.round(n * 1000) / 1000

/** Scrub step (0…steps-1) for a pointer fraction across the frame. */
export function scrubStep(fraction: number, steps = SCRUB_STEPS): number {
  return clamp(Math.floor(clamp(fraction, 0, 0.99999) * steps), 0, steps - 1)
}

/** Time inside the shot for a scrub step: the centre of that step's slice. */
export function scrubTime(step: number, start: number, end: number, steps = SCRUB_STEPS): number {
  const dur = Math.max(0, end - start)
  return clamp(start + ((clamp(step, 0, steps - 1) + 0.5) / steps) * dur, start, Math.max(start, end - 1e-3))
}

/** Aspect ratio of a tile (used to letterbox the sprite inside a 16:9 frame). */
export function tileAspect(sp: Sprites): number {
  return sp.tile_h > 0 ? sp.tile_w / sp.tile_h : 16 / 9
}

/** Tiles to draw across a filmstrip segment of `widthPx`, each `tileWidthPx` wide. */
export function filmstripTiles(sp: Sprites, start: number, end: number, widthPx: number, tileWidthPx: number): number[] {
  const n = Math.max(1, Math.min(64, Math.ceil(widthPx / Math.max(8, tileWidthPx))))
  const out: number[] = []
  for (let i = 0; i < n; i++) out.push(spriteIndexAt(sp, start + ((i + 0.5) / n) * (end - start)))
  return out
}
