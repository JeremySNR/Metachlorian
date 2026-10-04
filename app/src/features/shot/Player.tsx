import { forwardRef, useEffect, useImperativeHandle, useRef, useState } from 'react'
import {
  Captions, ChevronsLeft, ChevronsRight, LoaderCircle, Maximize, Pause, Play, SkipBack, SkipForward, Volume2, VolumeX, type LucideIcon,
} from 'lucide-react'
import { IconButton } from '../../components/Button'
import { Ic } from '../../components/Icon'
import { isTyping } from '../../hooks/useHotkeys'
import { useLatest } from '../../hooks/useDebounced'
import { formatDuration, formatTimecode, parseTimecode, splitLeadingZeros, timecodeAriaLabel } from '../../lib/timecode'
import { usePrefs } from '../../lib/store'
import s from './Player.module.css'

export interface PlayerHandle {
  seek: (t: number) => void
  play: () => void
  pause: () => void
  time: () => number
  focus: () => void
}

export interface PlayerProps {
  src: string
  poster?: string
  fps: number | null
  /** Timeline extent in file seconds (the shot, or the whole file). */
  range: [number, number]
  boundaries?: number[]
  startAt?: number
  inPoint: number | null
  outPoint: number | null
  onInOut?: (inPoint: number | null, outPoint: number | null) => void
  onPrevShot?: () => void
  onNextShot?: () => void
  onPrevResult?: () => void
  onNextResult?: () => void
  /** Called on every painted frame / seek; keep it cheap (imperative updates only). */
  onTime?: (t: number) => void
  compact?: boolean
  label: string
  captions?: string
  testId?: string
}

const VOLUME_KEY = 'mc.volume'

/**
 * Player with editor transport (system.md §3.12, keyboard §5.4). Readout and
 * playhead update through refs on every frame, never through React state.
 */
export const Player = forwardRef<PlayerHandle, PlayerProps>(function Player(props, ref) {
  const { src, poster, fps, range, boundaries = [], startAt, inPoint, outPoint, onInOut, compact, label, testId } = props
  const videoRef = useRef<HTMLVideoElement>(null)
  const rootRef = useRef<HTMLDivElement>(null)
  const readoutRef = useRef<HTMLSpanElement>(null)
  const headRef = useRef<HTMLDivElement>(null)
  const timelineRef = useRef<HTMLDivElement>(null)
  const [playing, setPlaying] = useState(false)
  const [muted, setMuted] = useState(false)
  const [rate, setRate] = useState(1)
  const [editing, setEditing] = useState<string | null>(null)
  const [waiting, setWaiting] = useState(false)
  const reverse = useRef(0)
  const shuttle = useRef(0)
  const playRange = useRef<[number, number] | null>(null)
  const format = usePrefs((p) => p.timecodeFormat)
  const [a, b] = range
  const span = Math.max(0.001, b - a)
  const latest = useLatest(props)

  const paint = (t: number) => {
    const tc = formatTimecode(t, fps, format)
    const [dim, rest] = splitLeadingZeros(tc)
    if (readoutRef.current) readoutRef.current.innerHTML = `${dim ? `<span class="${s.dim}">${dim}</span>` : ''}${rest}`
    if (headRef.current) headRef.current.style.insetInlineStart = `${Math.max(0, Math.min(100, ((t - a) / span) * 100))}%`
    if (timelineRef.current) {
      timelineRef.current.setAttribute('aria-valuenow', String(Math.round(t * 100) / 100))
      timelineRef.current.setAttribute('aria-valuetext', timecodeAriaLabel(t, fps))
    }
    latest.current.onTime?.(t)
  }

  const seek = (t: number) => {
    const v = videoRef.current
    if (!v) return
    const c = Math.max(0, Math.min(v.duration || b, t))
    v.currentTime = c
    paint(c)
  }

  const stopReverse = () => {
    window.clearInterval(reverse.current)
    reverse.current = 0
  }

  const play = (from?: number) => {
    const v = videoRef.current
    if (!v) return
    stopReverse()
    if (from !== undefined) v.currentTime = from
    v.playbackRate = 1
    shuttle.current = 0
    setRate(1)
    v.play().catch(() => undefined)
  }

  const pause = () => {
    stopReverse()
    shuttle.current = 0
    videoRef.current?.pause()
    playRange.current = null
  }

  useImperativeHandle(ref, () => ({ seek, play: () => play(), pause, time: () => videoRef.current?.currentTime ?? 0, focus: () => rootRef.current?.focus() }))

  // Restore volume; start at the in-point.
  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    const vol = Number(localStorage.getItem(VOLUME_KEY) ?? '1')
    v.volume = Number.isFinite(vol) ? Math.max(0, Math.min(1, vol)) : 1
    const t0 = performance.now()
    const onMeta = () => {
      const target = startAt ?? a
      if (Math.abs(v.currentTime - target) > 0.05) v.currentTime = target
      paint(target)
    }
    const onFirst = () => {
      if (import.meta.env.DEV) console.debug(`[player] first frame ${Math.round(performance.now() - t0)} ms`)
    }
    v.addEventListener('loadedmetadata', onMeta, { once: true })
    v.addEventListener('loadeddata', onFirst, { once: true })
    paint(startAt ?? a)
    return () => {
      v.removeEventListener('loadedmetadata', onMeta)
      v.removeEventListener('loadeddata', onFirst)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src, a, startAt])

  // Frame-accurate readout while playing.
  useEffect(() => {
    const v = videoRef.current
    if (!v) return
    let handle = 0
    let raf = 0
    const tick = () => {
      paint(v.currentTime)
      const pr = playRange.current
      if (pr && v.currentTime >= pr[1]) {
        v.pause()
        v.currentTime = pr[1]
        playRange.current = null
      }
      if (!v.paused) schedule()
    }
    const schedule = () => {
      if ('requestVideoFrameCallback' in v) handle = v.requestVideoFrameCallback(tick)
      else raf = requestAnimationFrame(tick)
    }
    const onPlay = () => {
      setPlaying(true)
      schedule()
    }
    const onPause = () => {
      setPlaying(false)
      paint(v.currentTime)
    }
    const onSeeked = () => paint(v.currentTime)
    const onWaiting = () => setWaiting(true)
    const onPlaying = () => setWaiting(false)
    v.addEventListener('play', onPlay)
    v.addEventListener('pause', onPause)
    v.addEventListener('seeked', onSeeked)
    v.addEventListener('waiting', onWaiting)
    v.addEventListener('playing', onPlaying)
    v.addEventListener('canplay', onPlaying)
    return () => {
      v.removeEventListener('play', onPlay)
      v.removeEventListener('pause', onPause)
      v.removeEventListener('seeked', onSeeked)
      v.removeEventListener('waiting', onWaiting)
      v.removeEventListener('playing', onPlaying)
      v.removeEventListener('canplay', onPlaying)
      if ('cancelVideoFrameCallback' in v && handle) v.cancelVideoFrameCallback(handle)
      cancelAnimationFrame(raf)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src, fps, format, a, b])

  useEffect(() => () => stopReverse(), [])

  const frame = 1 / (fps || 25)

  const jkl = (key: 'j' | 'k' | 'l') => {
    const v = videoRef.current
    if (!v) return
    if (key === 'k') {
      pause()
      setRate(1)
      return
    }
    const dir = key === 'l' ? 1 : -1
    const cur = shuttle.current
    const next = Math.sign(cur) === dir ? Math.min(8, Math.abs(cur) * 2) * dir : dir
    shuttle.current = next
    setRate(Math.abs(next))
    stopReverse()
    if (next > 0) {
      v.playbackRate = next
      v.play().catch(() => undefined)
    } else {
      v.pause()
      const step = 1 / 20
      reverse.current = window.setInterval(() => {
        const t = v.currentTime + next * step
        if (t <= 0) {
          stopReverse()
          v.currentTime = 0
        } else v.currentTime = t
        paint(v.currentTime)
      }, step * 1000)
    }
  }

  const setIn = (t: number | null) => onInOut?.(t, outPoint !== null && t !== null && t >= outPoint ? null : outPoint)
  const setOut = (t: number | null) => onInOut?.(inPoint !== null && t !== null && t <= inPoint ? null : inPoint, t)

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (isTyping(e.target)) return
    const v = videoRef.current
    if (!v) return
    const p = latest.current
    const mod = e.metaKey || e.ctrlKey
    const single = usePrefs.getState().singleKeys && !mod
    const k = e.key
    const handled = () => e.preventDefault()
    if (k === ' ') {
      handled()
      if (e.shiftKey) {
        const i = inPoint ?? a
        const o = outPoint ?? b
        playRange.current = [i, o]
        play(i)
        playRange.current = [i, o]
      } else if (v.paused && !reverse.current) play()
      else pause()
      return
    }
    if (k === 'ArrowLeft' || k === 'ArrowRight') {
      handled()
      pause()
      seek(v.currentTime + (k === 'ArrowLeft' ? -1 : 1) * (e.shiftKey ? 1 : frame))
      return
    }
    if (k === 'ArrowUp' && p.onPrevShot) return handled(), p.onPrevShot()
    if (k === 'ArrowDown' && p.onNextShot) return handled(), p.onNextShot()
    if (k === 'Home') return handled(), seek(a)
    if (k === 'End') return handled(), seek(b)
    if (!single) return
    switch (k.toLowerCase()) {
      case 'j':
      case 'k':
      case 'l':
        handled()
        jkl(k.toLowerCase() as 'j' | 'k' | 'l')
        return
      case 'i':
        handled()
        if (e.altKey) setIn(null)
        else if (e.shiftKey) seek(inPoint ?? a)
        else setIn(v.currentTime)
        return
      case 'o':
        handled()
        if (e.altKey) setOut(null)
        else if (e.shiftKey) seek(outPoint ?? b)
        else setOut(v.currentTime)
        return
      case 'x':
        if (e.altKey) {
          handled()
          onInOut?.(null, null)
        }
        return
      case 'm':
        handled()
        v.muted = !v.muted
        setMuted(v.muted)
        return
      case 'f':
        handled()
        rootRef.current?.requestFullscreen?.().catch(() => undefined)
        return
      case 't':
        handled()
        setEditing(formatTimecode(v.currentTime, fps))
        return
      case '[':
        if (p.onPrevResult) {
          handled()
          p.onPrevResult()
        }
        return
      case ']':
        if (p.onNextResult) {
          handled()
          p.onNextResult()
        }
        return
    }
    if (/^\d$/.test(k) && !e.altKey) {
      handled()
      setEditing(k)
    }
  }

  // Timeline pointer: click seeks, drag scrubs.
  const scrubTo = (clientX: number) => {
    const el = timelineRef.current
    if (!el) return
    const r = el.getBoundingClientRect()
    const f = Math.max(0, Math.min(1, (clientX - r.left) / r.width))
    const v = videoRef.current
    const t = a + f * span
    if (v && 'fastSeek' in v && typeof v.fastSeek === 'function') {
      v.fastSeek(t)
      paint(t)
    } else seek(t)
  }

  const inPct = inPoint !== null ? ((inPoint - a) / span) * 100 : null
  const outPct = outPoint !== null ? ((outPoint - a) / span) * 100 : null

  return (
    <div ref={rootRef} className={`${s.player} ${compact ? s.compact : ''} ${waiting ? s.waiting : ''}`} tabIndex={0} role="group" aria-label={`Player, ${label}. Space plays, J K L shuttle, I and O mark in and out.`} onKeyDown={onKeyDown} data-testid={testId}>
      <div className={s.well}>
        <video
          ref={videoRef}
          className={s.video}
          src={`${src}#t=${(startAt ?? a).toFixed(3)}`}
          poster={poster}
          preload="auto"
          playsInline
          muted={muted}
          onClick={() => (videoRef.current?.paused ? play() : pause())}
          onVolumeChange={(e) => {
            localStorage.setItem(VOLUME_KEY, String(e.currentTarget.volume))
            setMuted(e.currentTarget.muted)
          }}
          aria-label={label}
        >
          {props.captions && <track kind="captions" src={props.captions} srcLang="en" label="Transcript" />}
        </video>
        <span className={s.bufferChip} aria-hidden="true">
          <Ic icon={LoaderCircle} size={16} className="mc-spin" />
        </span>
      </div>
      <div
        ref={timelineRef}
        className={s.timeline}
        role="slider"
        tabIndex={-1}
        aria-label="Playhead"
        aria-valuemin={Math.round(a * 100) / 100}
        aria-valuemax={Math.round(b * 100) / 100}
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId)
          pause()
          scrubTo(e.clientX)
        }}
        onPointerMove={(e) => e.buttons === 1 && scrubTo(e.clientX)}
        onPointerUp={(e) => {
          const el = timelineRef.current
          if (!el) return
          const r = el.getBoundingClientRect()
          seek(a + Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * span)
        }}
      >
        <div className={s.track} />
        {boundaries
          .filter((x) => x > a && x < b)
          .map((x) => (
            <div key={x} className={s.boundary} style={{ insetInlineStart: `${((x - a) / span) * 100}%` }} />
          ))}
        {(inPct !== null || outPct !== null) && <div className={s.rangeTint} style={{ insetInlineStart: `${inPct ?? 0}%`, insetInlineEnd: `${100 - (outPct ?? 100)}%` }} />}
        <div ref={headRef} className={s.playhead} />
      </div>
      <div className={s.transport}>
        {editing !== null ? (
          <input
            className={s.readoutInput}
            autoFocus
            aria-label="Go to timecode"
            value={editing}
            onChange={(e) => setEditing(e.target.value)}
            onKeyDown={(e) => {
              e.stopPropagation()
              if (e.key === 'Enter') {
                const t = parseTimecode(editing, fps)
                if (t !== null) seek(t)
                setEditing(null)
                rootRef.current?.focus()
              } else if (e.key === 'Escape') {
                setEditing(null)
                rootRef.current?.focus()
              }
            }}
            onBlur={() => setEditing(null)}
          />
        ) : (
          <button type="button" className={s.readout} aria-label="Current timecode. Press to type a timecode" onClick={() => setEditing(formatTimecode(videoRef.current?.currentTime ?? 0, fps))}>
            <span ref={readoutRef} aria-hidden="true" />
          </button>
        )}
        <div className={s.center}>
          {props.onPrevShot && <IconButton icon={SkipBack} label="Previous shot" shortcut="↑" size="sm" onPress={props.onPrevShot} />}
          <IconButton icon={ChevronsLeft} label="Reverse (J)" shortcut="J" size="sm" onPress={() => jkl('j')} />
          <IconButton icon={playing ? Pause : Play} label={playing ? 'Pause' : 'Play'} shortcut="Space" onPress={() => (playing ? pause() : play())} data-testid="player-play" />
          <IconButton icon={ChevronsRight} label="Forward (L)" shortcut="L" size="sm" onPress={() => jkl('l')} />
          {props.onNextShot && <IconButton icon={SkipForward} label="Next shot" shortcut="↓" size="sm" onPress={props.onNextShot} />}
          {rate !== 1 && <span className={s.rate}>{rate}×</span>}
        </div>
        <div className={s.right}>
          {onInOut && (
            <>
              <IconButton icon={BracketIn as unknown as LucideIcon} label="Mark in" shortcut="I" size="sm" onPress={() => setIn(videoRef.current?.currentTime ?? a)} />
              <IconButton icon={BracketOut as unknown as LucideIcon} label="Mark out" shortcut="O" size="sm" onPress={() => setOut(videoRef.current?.currentTime ?? b)} />
            </>
          )}
          {props.captions && !compact && <IconButton icon={Captions} label="Captions" shortcut="C" size="sm" className={s.hideSmall} />}
          <IconButton icon={muted ? VolumeX : Volume2} label={muted ? 'Unmute' : 'Mute'} shortcut="M" size="sm" onPress={() => { const v = videoRef.current; if (v) { v.muted = !v.muted; setMuted(v.muted) } }} />
          {!compact && <IconButton icon={Maximize} label="Full screen" shortcut="F" size="sm" onPress={() => rootRef.current?.requestFullscreen?.().catch(() => undefined)} />}
        </div>
      </div>
      {onInOut && (inPoint !== null || outPoint !== null) && (
        <div className={s.inout}>
          <span><b>IN</b>{inPoint !== null ? formatTimecode(inPoint, fps, format) : '—'}</span>
          <span><b>OUT</b>{outPoint !== null ? formatTimecode(outPoint, fps, format) : '—'}</span>
          {inPoint !== null && outPoint !== null && <span><b>DUR</b>{formatDuration(outPoint - inPoint)}</span>}
        </div>
      )}
    </div>
  )
})

/** Lucide has no bracket icons; these follow its 24-unit grid and stroke. */
function BracketIn(props: React.SVGProps<SVGSVGElement> & { size?: number }) {
  const { size = 16, ...rest } = props
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" className="lucide" {...rest}>
      <path d="M10 4H6v16h4" />
      <path d="M14 12h5M16 9l3 3-3 3" />
    </svg>
  )
}

function BracketOut(props: React.SVGProps<SVGSVGElement> & { size?: number }) {
  const { size = 16, ...rest } = props
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" className="lucide" {...rest}>
      <path d="M14 4h4v16h-4" />
      <path d="M5 12h5M8 9l-3 3 3 3" />
    </svg>
  )
}
