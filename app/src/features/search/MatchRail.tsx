import { useEffect, useRef, useState } from 'react'
import s from './ResultsGrid.module.css'

/**
 * Match-strength rail (system.md §3.22): a sparkline of match strength (absolute, 0..1) down the result
 * list, a tick at the "Weaker matches below" divider and a viewport thumb.
 * Click or drag to jump; PageUp/PageDown on the grid are the keyboard route.
 */
export function MatchRail({ scroller, values, total, split, gridId }: { scroller: React.RefObject<HTMLDivElement | null>; values: number[]; total: number; split: number | null; gridId: string }) {
  const [view, setView] = useState({ top: 0, height: 1 })
  const railRef = useRef<HTMLDivElement>(null)
  const dragging = useRef(false)

  useEffect(() => {
    const el = scroller.current
    if (!el) return
    const update = () => {
      const h = el.scrollHeight || 1
      setView({ top: el.scrollTop / h, height: Math.min(1, el.clientHeight / h) })
    }
    update()
    el.addEventListener('scroll', update, { passive: true })
    const ro = new ResizeObserver(update)
    ro.observe(el)
    return () => {
      el.removeEventListener('scroll', update)
      ro.disconnect()
    }
  }, [scroller, total])

  if (total < 2) return null
  const n = Math.max(total, 1)
  const step = Math.max(1, Math.ceil(values.length / 200))
  const pts: string[] = []
  for (let i = 0; i < values.length; i += step) {
    const x = 2 + Math.max(0, Math.min(1, values[i])) * 8
    pts.push(`${x.toFixed(1)},${((i / n) * 1000).toFixed(1)}`)
  }

  const jump = (clientY: number, smooth: boolean) => {
    const el = scroller.current
    const rail = railRef.current
    if (!el || !rail) return
    const rect = rail.getBoundingClientRect()
    const f = Math.max(0, Math.min(1, (clientY - rect.top) / rect.height))
    const reduced = document.documentElement.dataset.motion === 'reduced' || window.matchMedia('(prefers-reduced-motion: reduce)').matches
    el.scrollTo({ top: f * el.scrollHeight - el.clientHeight / 2, behavior: smooth && !reduced ? 'smooth' : 'auto' })
  }

  return (
    <div
      ref={railRef}
      className={s.matchRail}
      role="scrollbar"
      aria-label="Match strength"
      aria-controls={gridId}
      aria-orientation="vertical"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(view.top * 100)}
      onPointerDown={(e) => {
        dragging.current = true
        e.currentTarget.setPointerCapture(e.pointerId)
        jump(e.clientY, true)
      }}
      onPointerMove={(e) => dragging.current && jump(e.clientY, false)}
      onPointerUp={() => (dragging.current = false)}
    >
      <svg viewBox="0 0 12 1000" preserveAspectRatio="none" aria-hidden="true">
        {pts.length > 1 && <polyline points={pts.join(' ')} fill="none" stroke="var(--viz-3)" strokeWidth="1.5" vectorEffect="non-scaling-stroke" />}
        {split !== null && <line x1="0" x2="12" y1={(split / n) * 1000} y2={(split / n) * 1000} stroke="var(--fg-2)" strokeWidth="1" vectorEffect="non-scaling-stroke" />}
      </svg>
      <div className={s.matchThumb} style={{ insetBlockStart: `${view.top * 100}%`, blockSize: `${Math.max(2, view.height * 100)}%` }} />
    </div>
  )
}
