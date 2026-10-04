import { forwardRef, useEffect, useImperativeHandle, useLayoutEffect, useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { Maximize, ZoomIn, ZoomOut } from 'lucide-react'
import type { AssetShot, Sprites } from '../../api/types'
import { IconButton } from '../../components/Button'
import { filmstripTiles, tileAspect, tileBackground } from '../../lib/sprite'
import { formatLength, formatTimecode, timecodeAriaLabel } from '../../lib/timecode'
import { humanise } from '../../lib/format'
import s from './Asset.module.css'

export interface FilmstripHandle {
  setTime: (t: number) => void
}

interface Props {
  filename: string
  duration: number
  fps: number | null
  shots: AssetShot[]
  sprites: Sprites | null
  matches: { start: number; end: number; uid: string }[]
  rightsHatch: 'restricted' | 'blocked' | null
  inOut?: [number, number] | null
  onSeek: (t: number) => void
  onOpenShot: (uid: string) => void
  onShotChange?: (index: number) => void
}

const SHOT_H = 48

/**
 * Filmstrip / timeline (system.md §3.11): matches lane, shot thumbnails from the
 * file's sprite sheet (virtualised horizontally with TanStack Virtual), rights
 * hatching, ruler and a Key playhead. The playhead is a slider; lanes are aria-hidden.
 */
export const Filmstrip = forwardRef<FilmstripHandle, Props>(function Filmstrip({ filename, duration, fps, shots, sprites, matches, rightsHatch, inOut, onSeek, onOpenShot, onShotChange }, ref) {
  const trackRef = useRef<HTMLDivElement>(null)
  const headRef = useRef<HTMLDivElement>(null)
  const readoutRef = useRef<HTMLSpanElement>(null)
  const liveRef = useRef<HTMLSpanElement>(null)
  const [width, setWidth] = useState(800)
  const [zoom, setZoom] = useState(1)
  const timeRef = useRef(0)
  const lastShot = useRef(-1)
  const lastAnnounce = useRef(0)
  const dur = Math.max(0.001, duration)
  const pps = (width * zoom) / dur
  const total = Math.max(width, Math.round(dur * pps))

  useLayoutEffect(() => {
    const el = trackRef.current
    if (!el) return
    const ro = new ResizeObserver(() => setWidth(el.clientWidth))
    ro.observe(el)
    setWidth(el.clientWidth)
    return () => ro.disconnect()
  }, [])

  const shotIndexAt = (t: number) => {
    let lo = 0
    let hi = shots.length - 1
    while (lo <= hi) {
      const m = (lo + hi) >> 1
      if (t < shots[m].start) hi = m - 1
      else if (t >= shots[m].end) lo = m + 1
      else return m
    }
    return -1
  }

  const setTime = (t: number) => {
    timeRef.current = t
    const x = t * pps
    if (headRef.current) {
      headRef.current.style.insetInlineStart = `${x}px`
      headRef.current.parentElement?.setAttribute('aria-valuenow', String(Math.round(t * 100) / 100))
    }
    if (readoutRef.current) readoutRef.current.textContent = formatTimecode(t, fps)
    const i = shotIndexAt(t)
    const track = trackRef.current
    if (track && zoom > 1 && (x < track.scrollLeft || x > track.scrollLeft + track.clientWidth)) track.scrollLeft = x - track.clientWidth / 3
    if (i !== lastShot.current) {
      lastShot.current = i
      onShotChange?.(i)
      const now = performance.now()
      if (i >= 0 && liveRef.current && now - lastAnnounce.current > 500) {
        lastAnnounce.current = now
        const sh = shots[i]
        liveRef.current.textContent = `Shot ${i + 1} of ${shots.length}${sh.shot_size ? `, ${humanise(sh.shot_size)}` : ''}`
      }
    }
    const slider = trackRef.current?.querySelector('[role=slider]')
    slider?.setAttribute('aria-valuetext', `${formatTimecode(t, fps)}, shot ${i + 1} of ${shots.length}`)
  }

  useImperativeHandle(ref, () => ({ setTime }))
  useEffect(() => setTime(timeRef.current))

  const virt = useVirtualizer({
    horizontal: true,
    count: shots.length,
    getScrollElement: () => trackRef.current,
    estimateSize: (i) => Math.max(1, (shots[i].end - shots[i].start) * pps),
    overscan: 4,
  })
  useEffect(() => virt.measure(), [pps, shots.length, virt])

  const tAt = (clientX: number) => {
    const el = trackRef.current
    if (!el) return 0
    const r = el.getBoundingClientRect()
    return Math.max(0, Math.min(dur, (clientX - r.left + el.scrollLeft) / pps))
  }

  const ta = sprites ? tileAspect(sprites) : 16 / 9
  const tileW = SHOT_H * ta
  const tickEvery = [1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800].find((x) => x * pps >= 72) ?? 3600
  const ticks: number[] = []
  for (let t = 0; t <= dur; t += tickEvery) ticks.push(t)

  const onKey = (e: React.KeyboardEvent) => {
    const frame = 1 / (fps || 25)
    const t = timeRef.current
    const k = e.key
    const go = (x: number) => {
      e.preventDefault()
      onSeek(Math.max(0, Math.min(dur, x)))
    }
    if (k === 'ArrowLeft') return go(t - (e.shiftKey ? 1 : frame))
    if (k === 'ArrowRight') return go(t + (e.shiftKey ? 1 : frame))
    if (k === 'ArrowUp') {
      const i = shotIndexAt(t)
      return go(shots[Math.max(0, i - (t - (shots[i]?.start ?? 0) < 0.1 ? 1 : 0))]?.start ?? 0)
    }
    if (k === 'ArrowDown') {
      const i = shotIndexAt(t)
      return go(shots[Math.min(shots.length - 1, i + 1)]?.start ?? t)
    }
    if (k === 'Home') return go(0)
    if (k === 'End') return go(dur)
    if (k === '+' || k === '=') return (e.preventDefault(), setZoom((z) => Math.min(64, z * 2)))
    if (k === '-') return (e.preventDefault(), setZoom((z) => Math.max(1, z / 2)))
    if (k === 'Z' && e.shiftKey) return (e.preventDefault(), setZoom(1))
    if (k === 'Enter') {
      const i = shotIndexAt(t)
      if (i >= 0) {
        e.preventDefault()
        onOpenShot(shots[i].uid)
      }
    }
  }

  return (
    <div className={s.filmstrip} role="group" aria-label={`Timeline, ${filename}`}>
      <div className={s.stripTools}>
        <span className={s.readout} ref={readoutRef} aria-hidden="true" />
        <span className="visually-hidden" aria-live="polite" ref={liveRef} />
        <IconButton icon={ZoomOut} label="Zoom out" shortcut="-" size="sm" isDisabled={zoom <= 1} onPress={() => setZoom((z) => Math.max(1, z / 2))} />
        <span className={s.meta}>{zoom}×</span>
        <IconButton icon={ZoomIn} label="Zoom in" shortcut="+" size="sm" isDisabled={zoom >= 64} onPress={() => setZoom((z) => Math.min(64, z * 2))} />
        <IconButton icon={Maximize} label="Fit" shortcut="⇧Z" size="sm" onPress={() => setZoom(1)} />
      </div>
      <div className={s.lanes}>
        <div className={s.laneLabels} aria-hidden="true">
          <span>MATCHES</span>
          <span>SHOTS</span>
          <span>RIGHTS</span>
          <span />
        </div>
        <div
          ref={trackRef}
          className={s.track}
          onPointerDown={(e) => {
            if (e.button !== 0) return
            e.currentTarget.setPointerCapture(e.pointerId)
            onSeek(tAt(e.clientX))
          }}
          onPointerMove={(e) => e.buttons === 1 && onSeek(tAt(e.clientX))}
          onDoubleClick={(e) => {
            const i = shotIndexAt(tAt(e.clientX))
            if (i >= 0) onOpenShot(shots[i].uid)
          }}
          onWheel={(e) => {
            if (e.ctrlKey || e.metaKey) {
              e.preventDefault()
              setZoom((z) => Math.max(1, Math.min(64, z * (e.deltaY < 0 ? 1.25 : 0.8))))
            }
          }}
        >
          <div className={s.inner} style={{ inlineSize: total }}>
            <div className={s.matchLane} aria-hidden="true">
              {matches.map((m, i) => (
                <div key={i} className={s.match} style={{ insetInlineStart: m.start * pps, inlineSize: Math.max(2, (m.end - m.start) * pps) }} />
              ))}
            </div>
            <div className={s.shotLane} aria-hidden="true">
              {virt.getVirtualItems().map((vi) => {
                const sh = shots[vi.index]
                const w = Math.max(1, (sh.end - sh.start) * pps)
                const tiles = sprites ? filmstripTiles(sprites, sh.start, sh.end, w, tileW) : []
                return (
                  <div key={sh.uid} className={s.shot} style={{ insetInlineStart: sh.start * pps, inlineSize: w }} title={`Shot ${sh.idx + 1} · ${formatTimecode(sh.start, fps)}`}>
                    {sprites &&
                      tiles.map((ti, k) => {
                        const bg = tileBackground(sprites, ti)
                        return <div key={k} className={s.tile} style={{ inlineSize: tileW, backgroundImage: bg.image, backgroundSize: bg.size, backgroundPosition: bg.position }} />
                      })}
                  </div>
                )
              })}
            </div>
            <div className={s.rightsLane} aria-hidden="true">
              {rightsHatch && <div className={`${s.hatch} ${rightsHatch === 'blocked' ? s.hatchBlocked : ''}`} style={{ insetInlineStart: 0, inlineSize: total }} />}
            </div>
            <div className={s.ruler} aria-hidden="true">
              {ticks.map((t) => (
                <span key={t} className={s.tick} style={{ insetInlineStart: t * pps }}>
                  {formatLength(t)}
                </span>
              ))}
            </div>
            {inOut && <div className={s.range} style={{ insetInlineStart: inOut[0] * pps, inlineSize: Math.max(2, (inOut[1] - inOut[0]) * pps) }} />}
            <div
              role="slider"
              tabIndex={0}
              aria-label="Playhead"
              aria-valuemin={0}
              aria-valuemax={Math.round(dur * 100) / 100}
              aria-valuetext={timecodeAriaLabel(0, fps)}
              onKeyDown={onKey}
              style={{ position: 'absolute', inset: 0, outline: 'none' }}
              data-testid="filmstrip"
            >
              <div ref={headRef} className={s.playhead} />
            </div>
          </div>
        </div>
      </div>
    </div>
  )
})
