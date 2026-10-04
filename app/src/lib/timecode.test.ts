import { describe, expect, it } from 'vitest'
import {
  durationAriaLabel, formatDuration, formatLength, formatTimecode, fpsLabel, fpsTitle, framesToParts, isDropFrame,
  nominalFps, parseTimecode, snapFps, splitLeadingZeros, timecodeAriaLabel,
} from './timecode'

describe('timecode', () => {
  it('formats SMPTE at integer rates', () => {
    expect(formatTimecode(843.48, 25)).toBe('00:14:03:12')
    expect(formatTimecode(0, 25)).toBe('00:00:00:00')
    expect(formatTimecode(3600 + 61.5, 50)).toBe('01:01:01:25')
  })

  it('uses the nominal base for 23.976 non-drop', () => {
    expect(nominalFps(23.976)).toBe(24)
    expect(isDropFrame(23.976)).toBe(false)
    // frame 24 at 23.976 is labelled 00:00:01:00
    expect(formatTimecode(24 / 23.976, 23.976)).toBe('00:00:01:00')
  })

  it('applies drop-frame at 29.97 with a semicolon', () => {
    expect(isDropFrame(29.97)).toBe(true)
    // Frame 1800 at 29.97 DF is 00:01:00;02 (frames 0 and 1 of minute 1 are dropped)
    const p = framesToParts(1800, 29.97)
    expect([p.m, p.s, p.f]).toEqual([1, 0, 2])
    expect(formatTimecode(1800 / 29.97, 29.97)).toBe('00:01:00;02')
    // Every tenth minute keeps its frames: frame 17982 is 00:10:00;00
    expect(formatTimecode(17982 / 29.97, 29.97)).toBe('00:10:00;00')
  })

  it('formats frames and seconds modes', () => {
    expect(formatTimecode(10, 25, 'frames')).toBe('#250')
    expect(formatTimecode(843.48, 25, 'seconds')).toBe('14:03.48')
  })

  it('splits leading zero groups for dimming', () => {
    expect(splitLeadingZeros('00:14:03:12')).toEqual(['00:', '14:03:12'])
    expect(splitLeadingZeros('00:00:03:12')).toEqual(['00:00:', '03:12'])
    expect(splitLeadingZeros('00:00:00:12')).toEqual(['00:00:', '00:12'])
    expect(splitLeadingZeros('01:00:00:00')).toEqual(['', '01:00:00:00'])
    expect(splitLeadingZeros('#123')).toEqual(['', '#123'])
  })

  it('gives a spoken accessible name', () => {
    expect(timecodeAriaLabel(843.48, 25)).toBe('14 minutes, 3 seconds, 12 frames')
    expect(timecodeAriaLabel(1 + 1 / 25, 25)).toBe('1 second, 1 frame')
    expect(timecodeAriaLabel(3661, 25)).toBe('1 hour, 1 minute, 1 second, 0 frames')
  })

  it('parses what people type', () => {
    expect(parseTimecode('00:14:03:12', 25)).toBeCloseTo(843.48, 3)
    expect(parseTimecode('140312', 25)).toBeCloseTo(843.48, 3)
    expect(parseTimecode('1:02.5', 25)).toBeCloseTo(62.5, 3)
    expect(parseTimecode('#250', 25)).toBe(10)
    expect(parseTimecode('12.5', 25)).toBe(12.5)
    expect(parseTimecode('00:01:00;02', 29.97)).toBeCloseTo(1800 / 29.97, 4)
    expect(parseTimecode('00:00:00:30', 25)).toBeNull()
    expect(parseTimecode('abc', 25)).toBeNull()
  })

  it('round-trips SMPTE', () => {
    for (const fps of [24, 25, 30, 50, 23.976, 29.97, 59.94]) {
      for (const t of [0, 1.5, 59.9, 61, 600.2, 3725.3]) {
        const tc = formatTimecode(t, fps)
        const back = parseTimecode(tc, fps) as number
        expect(formatTimecode(back + 1e-4, fps)).toBe(tc)
      }
    }
  })

  it('formats durations, lengths and frame rates', () => {
    expect(formatDuration(6)).toBe('6s')
    expect(formatDuration(4.463)).toBe('4.5s')
    expect(formatDuration(72)).toBe('1m 12s')
    expect(formatDuration(3720)).toBe('1h 02m')
    expect(durationAriaLabel(6)).toBe('6 seconds')
    expect(durationAriaLabel(72)).toBe('1 minute, 12 seconds')
    expect(formatLength(2472)).toBe('41:12')
    expect(formatLength(3723)).toBe('1:02:03')
    expect(fpsLabel(25)).toBe('25p')
    expect(fpsLabel(23.976)).toBe('23.98p')
    expect(fpsLabel(29.97)).toBe('29.97p')
    expect(fpsLabel(59.94)).toBe('59.94p')
  })
})

describe('frame-rate snapping (±0.1%)', () => {
  it('snaps measured averages to the nearest standard rate', () => {
    expect(fpsLabel(59.981)).toBe('60p')
    expect(fpsLabel(30.017)).toBe('30p')
    expect(fpsLabel(29.95)).toBe('29.97p')
    expect(fpsLabel(29.944)).toBe('29.97p')
    expect(fpsLabel(23.999)).toBe('24p')
    expect(fpsLabel(59.97)).toBe('59.94p')
    expect(fpsLabel(119.9)).toBe('119.88p')
    expect(snapFps(59.981)).toMatchObject({ snapped: true, exact: 59.981 })
    expect(snapFps(59.981)?.fps).toBeCloseTo(60)
  })
  it('leaves rates outside the tolerance as measured', () => {
    // 24.03 is 0.125% off 24 and 29.93 is 0.13% off 29.97: shown as measured.
    expect(fpsLabel(24.03)).toBe('24.03p')
    expect(fpsLabel(29.93)).toBe('29.93p')
    expect(fpsLabel(12)).toBe('12p')
    expect(snapFps(24.03)).toMatchObject({ snapped: false })
    expect(snapFps(null)).toBeNull()
    expect(fpsLabel(0)).toBe('')
  })
  it('explains a snapped value in the tooltip', () => {
    expect(fpsTitle(59.981)).toBe('Measured 59.981 fps, shown as 60')
    expect(fpsTitle(25)).toBe('25 fps')
    expect(fpsTitle(null)).toBeUndefined()
  })
})
