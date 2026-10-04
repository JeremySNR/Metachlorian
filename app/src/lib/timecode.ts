/**
 * Timecode and duration formatting (system.md §3.7, §8 Formats).
 *
 * SMPTE HH:MM:SS:FF (';' before frames for drop-frame rates), frame counts (#21342)
 * or seconds (14:03.48). Pure functions: no DOM, no React.
 */

export type TimecodeFormat = 'smpte' | 'frames' | 'seconds'

const EPS = 1e-6

/** Integer timecode base for a frame rate (23.976 → 24, 29.97 → 30, 59.94 → 60). */
export function nominalFps(fps: number | null | undefined): number {
  if (!fps || !Number.isFinite(fps) || fps <= 0) return 25
  return Math.max(1, Math.round(fps))
}

/** NTSC rates that use drop-frame timecode. */
export function isDropFrame(fps: number | null | undefined): boolean {
  if (!fps) return false
  return Math.abs(fps - 29.97) < 0.01 || Math.abs(fps - 59.94) < 0.01
}

/** Frame number (0-based) that contains time `seconds`. */
export function secondsToFrames(seconds: number, fps: number | null | undefined): number {
  const rate = fps && fps > 0 ? fps : 25
  return Math.max(0, Math.floor(seconds * rate + EPS))
}

export function framesToSeconds(frames: number, fps: number | null | undefined): number {
  const rate = fps && fps > 0 ? fps : 25
  return frames / rate
}

export interface TimecodeParts {
  h: number
  m: number
  s: number
  f: number
  drop: boolean
}

/** Frame count → SMPTE fields, applying the drop-frame rule for 29.97 / 59.94. */
export function framesToParts(frames: number, fps: number | null | undefined): TimecodeParts {
  const base = nominalFps(fps)
  const drop = isDropFrame(fps)
  let n = Math.max(0, Math.floor(frames))
  if (drop) {
    const dropFrames = base === 60 ? 4 : 2
    const per10 = Math.round((fps as number) * 600)
    const perMin = base * 60 - dropFrames
    const d = Math.floor(n / per10)
    const m = n % per10
    n += dropFrames * 9 * d + (m > dropFrames ? dropFrames * Math.floor((m - dropFrames) / perMin) : 0)
  }
  const f = n % base
  const totalSeconds = Math.floor(n / base)
  return { h: Math.floor(totalSeconds / 3600), m: Math.floor(totalSeconds / 60) % 60, s: totalSeconds % 60, f, drop }
}

const pad = (n: number, w = 2) => String(n).padStart(w, '0')

export function formatTimecode(seconds: number | null | undefined, fps: number | null | undefined, format: TimecodeFormat = 'smpte'): string {
  const t = Math.max(0, seconds ?? 0)
  if (format === 'frames') return `#${secondsToFrames(t, fps)}`
  if (format === 'seconds') {
    const m = Math.floor(t / 60)
    const s = t - m * 60
    return `${pad(m)}:${s.toFixed(2).padStart(5, '0')}`
  }
  const p = framesToParts(secondsToFrames(t, fps), fps)
  const fw = nominalFps(fps) > 99 ? 3 : 2
  return `${pad(p.h)}:${pad(p.m)}:${pad(p.s)}${p.drop ? ';' : ':'}${pad(p.f, fw)}`
}

/**
 * Split a timecode into the leading all-zero groups (rendered in --fg-3) and the
 * significant rest, e.g. "00:00:03:12" → ["00:00:", "03:12"]. Hours always show.
 */
export function splitLeadingZeros(tc: string): [string, string] {
  if (!/^\d{2}:/.test(tc)) return ['', tc]
  let i = 0
  while (tc.startsWith('00', i) && (tc[i + 2] === ':' || tc[i + 2] === ';') && i < tc.length - 5) i += 3
  return [tc.slice(0, i), tc.slice(i)]
}

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

/** Accessible name: "14 minutes, 3 seconds, 12 frames" (hours omitted when zero). */
export function timecodeAriaLabel(seconds: number | null | undefined, fps: number | null | undefined): string {
  const p = framesToParts(secondsToFrames(Math.max(0, seconds ?? 0), fps), fps)
  const parts: string[] = []
  if (p.h) parts.push(plural(p.h, 'hour'))
  if (p.h || p.m) parts.push(plural(p.m, 'minute'))
  parts.push(plural(p.s, 'second'))
  parts.push(plural(p.f, 'frame'))
  return parts.join(', ')
}

/**
 * Parse what a person types into a timecode field. Accepts HH:MM:SS:FF (or ;FF),
 * MM:SS, SS, decimals (12.5), "1:02.5", frame counts (#123) and bare digit runs
 * typed like an NLE ("140312" → 00:14:03:12). Returns seconds, or null.
 */
export function parseTimecode(input: string, fps: number | null | undefined): number | null {
  const s = input.trim()
  if (!s) return null
  const base = nominalFps(fps)
  if (/^#\d+$/.test(s)) return framesToSeconds(Number(s.slice(1)), fps)
  if (/^\d+(\.\d+)?s?$/.test(s) && (s.includes('.') || s.endsWith('s'))) return Number(s.replace(/s$/, ''))
  if (/^\d{3,8}$/.test(s)) {
    const padded = s.padStart(8, '0')
    return parseTimecode(`${padded.slice(0, 2)}:${padded.slice(2, 4)}:${padded.slice(4, 6)}:${padded.slice(6, 8)}`, fps)
  }
  if (/^\d+$/.test(s)) return Number(s)
  const groups = s.split(/[:;]/)
  if (groups.some((g) => g === '' || !/^\d+(\.\d+)?$/.test(g))) return null
  const nums = groups.map(Number)
  if (nums.length === 4) {
    const [h, m, sec, f] = nums
    if (m > 59 || sec > 59 || f >= base) return null
    if (isDropFrame(fps) && s.includes(';')) {
      // Drop-frame: convert the label back to a frame count.
      const dropFrames = base === 60 ? 4 : 2
      const totalMinutes = 60 * h + m
      const frames = (3600 * h + 60 * m + sec) * base + f - dropFrames * (totalMinutes - Math.floor(totalMinutes / 10))
      return framesToSeconds(frames, fps)
    }
    return framesToSeconds((3600 * h + 60 * m + sec) * base + f, fps)
  }
  if (nums.length === 3) {
    const [h, m, sec] = nums
    return h * 3600 + m * 60 + sec
  }
  if (nums.length === 2) {
    const [m, sec] = nums
    return m * 60 + sec
  }
  return null
}

/** Shot durations: "6s", "4.5s", "1m 12s", "1h 02m" (system.md §8). */
export function formatDuration(seconds: number | null | undefined): string {
  const t = Math.max(0, seconds ?? 0)
  if (t < 10) {
    const r = Math.round(t * 10) / 10
    return `${Number.isInteger(r) ? r.toFixed(0) : r.toFixed(1)}s`
  }
  if (t < 60) return `${Math.round(t)}s`
  if (t < 3600) {
    const m = Math.floor(t / 60)
    const s = Math.round(t - m * 60)
    return s === 60 ? `${m + 1}m` : s ? `${m}m ${s}s` : `${m}m`
  }
  const h = Math.floor(t / 3600)
  const m = Math.round((t - h * 3600) / 60)
  return `${h}h ${pad(m)}m`
}

/** Spoken duration for accessible names: "6 seconds", "1 minute, 12 seconds". */
export function durationAriaLabel(seconds: number | null | undefined): string {
  const t = Math.round(Math.max(0, seconds ?? 0))
  const m = Math.floor(t / 60)
  const s = t % 60
  if (!m) return plural(s, 'second')
  return s ? `${plural(m, 'minute')}, ${plural(s, 'second')}` : plural(m, 'minute')
}

/** File length: "41:12", "1:02:03". */
export function formatLength(seconds: number | null | undefined): string {
  const t = Math.round(Math.max(0, seconds ?? 0))
  const h = Math.floor(t / 3600)
  const m = Math.floor(t / 60) % 60
  const s = t % 60
  return h ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`
}

/** Frame-rate label for the edge strip: 25p, 23.98p, 29.97p, 50p. */
export function fpsLabel(fps: number | null | undefined): string {
  if (!fps || !Number.isFinite(fps)) return ''
  const r = Math.round(fps)
  if (Math.abs(fps - r) < 0.005) return `${r}p`
  return `${(Math.round(fps * 100) / 100).toFixed(2).replace(/0$/, '')}p`
}
