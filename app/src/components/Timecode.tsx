import { Button as RacButton } from 'react-aria-components'
import { formatDuration, formatTimecode, splitLeadingZeros, timecodeAriaLabel, durationAriaLabel } from '../lib/timecode'
import { usePrefs } from '../lib/store'
import { toast } from './Toast'
import s from './Data.module.css'

interface Props {
  seconds: number | null | undefined
  fps: number | null | undefined
  size?: 'xs' | 'sm' | 'xl'
  /** Standalone timecodes copy on click (not inside cards). */
  copyable?: boolean
  className?: string
}

/** Timecode with dimmed leading zero groups and a spoken accessible name (§3.7). */
export function Timecode({ seconds, fps, size = 'sm', copyable, className }: Props) {
  const format = usePrefs((p) => p.timecodeFormat)
  const tc = formatTimecode(seconds ?? 0, fps, format)
  const [dim, rest] = splitLeadingZeros(tc)
  const label = timecodeAriaLabel(seconds ?? 0, fps)
  const inner = (
    <>
      <span aria-hidden="true">
        {dim && <span className={s.dim}>{dim}</span>}
        {rest}
      </span>
    </>
  )
  const cls = [s.tc, s[`tc-${size}`], className].filter(Boolean).join(' ')
  if (copyable) {
    return (
      <RacButton
        className={`${cls} ${s.tcButton}`}
        aria-label={`${label}. Copy timecode`}
        onPress={() => {
          navigator.clipboard?.writeText(tc).catch(() => undefined)
          toast({ title: `Copied ${tc}`, tone: 'info' })
        }}
      >
        {inner}
      </RacButton>
    )
  }
  return (
    <span className={cls} role="text" aria-label={label}>
      {inner}
    </span>
  )
}

/** "00:14:03:12 → 00:14:09:12 (6s)" */
export function TimecodeRange({ inS, outS, fps, size = 'sm', showDuration = true, copyable }: { inS: number; outS: number; fps: number | null | undefined; size?: 'xs' | 'sm'; showDuration?: boolean; copyable?: boolean }) {
  return (
    <span className={s.range}>
      <Timecode seconds={inS} fps={fps} size={size} copyable={copyable} />
      <span className={s.arrow} aria-hidden="true">→</span>
      <span className="visually-hidden">to</span>
      <Timecode seconds={outS} fps={fps} size={size} copyable={copyable} />
      {showDuration && (
        <span className={s.rangeDur} aria-label={durationAriaLabel(outS - inS)}>
          ({formatDuration(outS - inS)})
        </span>
      )}
    </span>
  )
}
