import { memo, useEffect, useRef } from 'react'
import { Check, Ellipsis, LoaderCircle, PenLine, Play, Plus, ScanSearch } from 'lucide-react'
import type { SearchResult, Sprites } from '../../api/types'
import { ensureSprites, queryClient, shotQuery } from '../../api/queries'
import { mediaUrl } from '../../api/client'
import { Ic } from '../../components/Icon'
import { RightsGlyph } from '../../components/RightsBadge'
import { aspectLabel } from '../../lib/format'
import { previewPool, type PreviewHandle } from '../../lib/previewPool'
import { describeRights, type RightsState } from '../../lib/rights'
import { SCRUB_STEPS, scrubStep, scrubTime, spriteIndexAt, tileAspect, tileBackground } from '../../lib/sprite'
import { prefersReducedMotion, usePrefs } from '../../lib/store'
import { durationAriaLabel, formatDuration, formatTimecode, fpsLabel, fpsTitle, splitLeadingZeros, timecodeAriaLabel } from '../../lib/timecode'
import { preferenceMatch } from '../../lib/chips'
import { can, bridge } from '../../lib/bridge'
import { dragFiles, prepareDrag } from '../../lib/dragOut'
import s from './ResultsGrid.module.css'

export interface CardController {
  togglePreview: (startedAt?: number) => void
  stopPreview: () => void
  isPreviewing: () => boolean
  stepScrub: (delta: number) => void
  shuttle: (key: 'j' | 'k' | 'l') => void
}

export interface ShotCardProps {
  r: SearchResult
  index: number
  colIndex: number
  focused: boolean
  selected: boolean
  rights: RightsState
  onFocusIndex: (i: number) => void
  onActivate: (i: number, how: 'click' | 'double') => void
  onToggleSelect: (i: number, mode: 'toggle' | 'range') => void
  onMenu: (i: number, anchor: HTMLElement) => void
  onSimilar: (uid: string) => void
  onAdd: (uid: string) => void
  dragUids: (uid: string) => string[]
  register: (i: number, c: CardController | null) => void
}

export const SHOT_MIME = 'application/x-metachlorian-shots'

const HOVER_INTENT = 150
const DWELL = 400

/**
 * "Close-up, hands at a food stall. Starts 1 minute, 6 seconds, 5 frames, 4 seconds long.
 * Restricted: credit required. Matches 2 of 3 preferences."
 */
export function shotAccessibleName(r: SearchResult, rights: RightsState): string {
  const desc = r.caption || r.summary || `${r.filename}, shot ${r.idx + 1}`
  const inS = r.in ?? r.start
  const outS = r.out ?? r.end
  const d = describeRights(rights, null, r.rights?.reasons)
  const pm = preferenceMatch(r.why)
  const prefs = pm && pm.total > 1 ? ` Matches ${pm.matched} of ${pm.total} preferences.` : ''
  return `${desc.replace(/\.$/, '')}. Starts ${timecodeAriaLabel(inS, r.fps)}, ${durationAriaLabel(outS - inS)} long. ${d.long.replace(/\.$/, '')}.${prefs}`
}

function aspectFromResolution(res: string | null): number | null {
  const m = res ? /^(\d+)x(\d+)$/.exec(res) : null
  return m ? Number(m[1]) / Number(m[2]) : null
}

/**
 * Shot card with sprite scrubbing and pooled video preview (system.md §3.6).
 * Per-frame work (sprite position, scrub bar) goes through refs, never React state.
 */
export const ShotCard = memo(function ShotCard({ r, index, colIndex, focused, selected, rights, onFocusIndex, onActivate, onToggleSelect, onMenu, onSimilar, onAdd, dragUids, register }: ShotCardProps) {
  const cardRef = useRef<HTMLDivElement>(null)
  const innerRef = useRef<HTMLDivElement>(null)
  const spriteRef = useRef<HTMLDivElement>(null)
  const fillRef = useRef<HTMLDivElement>(null)
  const st = useRef({
    x0: -1,
    scrubbing: false,
    step: -1,
    sprites: undefined as Sprites | null | undefined,
    intent: 0,
    dwell: 0,
    preview: null as PreviewHandle | null,
    rate: 0,
  })

  const inS = r.in ?? r.start
  const outS = r.out ?? r.end
  const proxy = mediaUrl(r.proxy) as string

  const applySprite = (step: number) => {
    const sp = st.current.sprites
    const el = spriteRef.current
    if (!sp || !el) return
    const t = scrubTime(step, inS, outS)
    const bg = tileBackground(sp, spriteIndexAt(sp, t))
    if (el.dataset.sheet !== bg.image) {
      el.style.backgroundImage = bg.image
      el.style.backgroundSize = bg.size
      el.dataset.sheet = bg.image
      const ta = tileAspect(sp)
      const fa = 16 / 9
      el.style.inlineSize = ta >= fa ? '100%' : `${(ta / fa) * 100}%`
      el.style.blockSize = ta >= fa ? `${(fa / ta) * 100}%` : '100%'
    }
    el.style.backgroundPosition = bg.position
    if (fillRef.current) fillRef.current.style.inlineSize = `${((step + 1) / SCRUB_STEPS) * 100}%`
  }

  const loadSprites = () => {
    if (st.current.sprites !== undefined) return Promise.resolve(st.current.sprites)
    return ensureSprites(r.asset_uid)
      .then((sp) => {
        st.current.sprites = sp
        return sp
      })
      .catch(() => {
        st.current.sprites = null
        return null
      })
  }

  const stopPreview = () => {
    st.current.preview?.stop()
    st.current.preview = null
    st.current.rate = 0
  }

  const startPreview = (from: number, startedAt = performance.now()) => {
    const inner = innerRef.current
    if (!inner || !proxy) return
    stopPreview()
    st.current.preview = previewPool.play(inner, proxy, Math.min(from, outS - 0.05), outS, {
      className: s.video,
      startedAt,
      onEnd: () => undefined,
    })
    if (cardRef.current) cardRef.current.dataset.previewing = 'loading'
    const handle = st.current.preview
    const el = handle.el
    const done = () => {
      if (cardRef.current && st.current.preview === handle) cardRef.current.dataset.previewing = 'playing'
    }
    el.addEventListener('error', () => {
      if (cardRef.current && st.current.preview === handle) delete cardRef.current.dataset.previewing
    }, { once: true })
    if (el.error && cardRef.current) delete cardRef.current.dataset.previewing
    if ('requestVideoFrameCallback' in el) el.requestVideoFrameCallback(done)
    else (el as HTMLVideoElement).addEventListener('playing', done, { once: true })
  }

  const endScrub = () => {
    st.current.scrubbing = false
    st.current.step = -1
    cardRef.current?.classList.remove(s.scrubbing)
  }

  const clearPreviewState = () => {
    stopPreview()
    if (cardRef.current) delete cardRef.current.dataset.previewing
  }

  useEffect(() => {
    const ctrl: CardController = {
      togglePreview: (startedAt) => {
        if (st.current.preview?.isPlaying()) {
          clearPreviewState()
          return
        }
        const from = st.current.step >= 0 ? scrubTime(st.current.step, inS, outS) : inS
        endScrub()
        startPreview(from, startedAt)
      },
      stopPreview: clearPreviewState,
      isPreviewing: () => Boolean(st.current.preview),
      stepScrub: (delta) => {
        loadSprites().then((sp) => {
          if (!sp) return
          clearPreviewState()
          const next = Math.max(0, Math.min(SCRUB_STEPS - 1, (st.current.step < 0 ? -1 : st.current.step) + delta))
          st.current.step = next
          st.current.scrubbing = true
          cardRef.current?.classList.add(s.scrubbing)
          applySprite(next)
        })
      },
      shuttle: (key) => {
        if (key === 'k') {
          st.current.rate = 0
          st.current.preview?.setRate(0)
          return
        }
        const dir = key === 'l' ? 1 : -1
        const cur = st.current.rate
        const next = Math.sign(cur) === dir ? Math.min(8, Math.abs(cur) * 2) * dir : dir
        if (!st.current.preview) startPreview(inS)
        st.current.rate = next
        st.current.preview?.setRate(next)
      },
    }
    register(index, ctrl)
    return () => register(index, null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [index, r.uid])

  useEffect(
    () => () => {
      window.clearTimeout(st.current.intent)
      window.clearTimeout(st.current.dwell)
      st.current.preview?.stop()
    },
    [],
  )

  const scrubOn = () => document.documentElement.dataset.scrub !== 'off'

  const onPointerEnter = (e: React.PointerEvent) => {
    if (e.pointerType !== 'mouse') return
    st.current.x0 = e.clientX
    window.clearTimeout(st.current.intent)
    st.current.intent = window.setTimeout(() => {
      // Hover intent: warm the preview and the shot record.
      previewPool.warm(proxy, inS, outS)
      queryClient.prefetchQuery(shotQuery(r.uid))
      loadSprites()
      prepareDrag(r.uid)
    }, HOVER_INTENT)
  }

  const onPointerMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (e.pointerType !== 'mouse' || !scrubOn()) return
    if (!st.current.scrubbing) {
      if (st.current.x0 < 0) st.current.x0 = e.clientX
      if (Math.abs(e.clientX - st.current.x0) < 4) return
      st.current.scrubbing = true
      cardRef.current?.classList.add(s.scrubbing)
      loadSprites().then(() => st.current.scrubbing && st.current.step >= 0 && applySprite(st.current.step))
    }
    if (st.current.preview) clearPreviewState()
    const rect = e.currentTarget.getBoundingClientRect()
    const step = scrubStep((e.clientX - rect.left) / rect.width)
    if (step !== st.current.step) {
      st.current.step = step
      applySprite(step)
    }
    // Dwell: a resting pointer plays the preview in place.
    window.clearTimeout(st.current.dwell)
    if (usePrefs.getState().dwellPreview && !prefersReducedMotion()) {
      st.current.dwell = window.setTimeout(() => {
        const t = scrubTime(st.current.step, inS, outS)
        endScrub()
        startPreview(t, performance.now() - 0)
      }, DWELL)
    }
  }

  const onPointerLeave = () => {
    window.clearTimeout(st.current.intent)
    window.clearTimeout(st.current.dwell)
    st.current.x0 = -1
    endScrub()
    clearPreviewState()
  }

  const name = shotAccessibleName(r, rights)
  const tc = formatTimecode(inS, r.fps, usePrefs.getState().timecodeFormat)
  const [dim, rest] = splitLeadingZeros(tc)
  const ar = aspectFromResolution(r.resolution)
  const arLabel = ar && Math.abs(ar - 16 / 9) > 0.03 ? aspectLabel(ar) : null
  const blocked = rights === 'blocked' || rights === 'expired'
  const pm = preferenceMatch(r.why)

  return (
    <div
      ref={cardRef}
      role="gridcell"
      aria-colindex={colIndex + 1}
      aria-selected={selected}
      aria-label={name}
      tabIndex={focused ? 0 : -1}
      data-index={index}
      data-uid={r.uid}
      className={`${s.card} ${blocked ? s.blocked : ''}`}
      draggable
      onDragStart={(e) => {
        const uids = dragUids(r.uid)
        e.dataTransfer.setData(SHOT_MIME, JSON.stringify(uids))
        e.dataTransfer.setData('text/plain', `${r.filename} · ${formatTimecode(inS, r.fps)} → ${formatTimecode(outS, r.fps)}`)
        e.dataTransfer.effectAllowed = 'copy'
        if (can('canDragOut')) {
          const files = dragFiles(uids)
          if (files.length) {
            e.preventDefault()
            bridge()?.startDrag(files)
          }
        }
      }}
      onFocus={(e) => {
        if (e.target === e.currentTarget) onFocusIndex(index)
      }}
      onMouseDown={(e) => {
        if (e.button !== 0) return
        if ((e.target as HTMLElement).closest('button')) return
        if (e.metaKey || e.ctrlKey) onToggleSelect(index, 'toggle')
        else if (e.shiftKey) onToggleSelect(index, 'range')
      }}
      onClick={(e) => {
        if ((e.target as HTMLElement).closest('button') || e.metaKey || e.ctrlKey || e.shiftKey) return
        onActivate(index, 'click')
      }}
      onDoubleClick={() => onActivate(index, 'double')}
      onContextMenu={(e) => {
        e.preventDefault()
        onMenu(index, cardRef.current as HTMLElement)
      }}
    >
      <div className={s.frame} onPointerEnter={onPointerEnter} onPointerMove={onPointerMove} onPointerLeave={onPointerLeave}>
        <div className={s.frameInner} ref={innerRef}>
          {r.thumb && <img className={s.poster} src={mediaUrl(r.thumb)} alt="" loading="lazy" decoding="async" draggable={false} />}
          <div className={s.sprite} ref={spriteRef} />
          <div className={s.scrub}>
            <div className={s.scrubFill} ref={fillRef} />
          </div>
        </div>
        <div className={`${s.overlay} ${s.tl}`}>
          <button type="button" tabIndex={-1} className={s.check} aria-label={selected ? 'Deselect shot' : 'Select shot'} aria-pressed={selected} onClick={() => onToggleSelect(index, 'toggle')}>
            {selected && <Ic icon={Check} size={14} />}
          </button>
        </div>
        <div className={`${s.overlay} ${s.tr}`}>
          <button type="button" tabIndex={-1} className={s.scrimBtn} aria-label="Find similar" title="Find similar (S)" onClick={() => onSimilar(r.uid)}>
            <Ic icon={ScanSearch} size={14} />
          </button>
          <button type="button" tabIndex={-1} className={s.scrimBtn} aria-label="Add to active collection" title="Add to active collection (B)" onClick={() => onAdd(r.uid)}>
            <Ic icon={Plus} size={14} />
          </button>
          <button type="button" tabIndex={-1} className={s.scrimBtn} aria-label="More actions" title="More (Shift+F10)" onClick={(e) => onMenu(index, e.currentTarget.closest('[role=gridcell]') as HTMLElement)}>
            <Ic icon={Ellipsis} size={14} />
          </button>
        </div>
        <button type="button" tabIndex={-1} className={s.playBtn} aria-label="Play preview" onClick={() => startPreview(inS)}>
          <Ic icon={Play} size={20} />
        </button>
        {arLabel && <span className={`${s.badge} ${s.bl}`}>{arLabel}</span>}
        {r.corrected?.length > 0 && (
          <span className={`${s.badge} ${s.br}`} title="Human-edited">
            <Ic icon={PenLine} size={12} />
          </span>
        )}
        {blocked && <span className={`${s.badge} ${s.center}`}>{rights === 'expired' ? 'Expired' : 'Blocked'}</span>}
        <span className={`${s.badge} ${s.center} ${s.loadingChip}`} aria-hidden="true">
          <Ic icon={LoaderCircle} size={12} className="mc-spin" />
        </span>
      </div>
      <div className={s.strip} aria-hidden="true">
        <span className={s.stripLine}>
          <span>
            {dim && <span style={{ color: 'var(--fg-3)' }}>{dim}</span>}
            <span style={{ color: 'var(--fg-1)' }}>{rest}</span>
          </span>
        </span>
        <span className={s.stripMeta}>
          <span>{formatDuration(outS - inS)}</span>
          {r.fps ? <span title={fpsTitle(r.fps)}>· {fpsLabel(r.fps)}</span> : null}
          <RightsGlyph state={rights} reasons={r.rights?.reasons} />
        </span>
        <span className={s.titleLine}>
          {pm && pm.total > 1 && (
            <span className={s.prefCue} title={`Matches ${pm.matched} of ${pm.total} preferences`}>
              {pm.matched}/{pm.total}
            </span>
          )}
          <span className={s.title}>{r.caption || r.summary || r.filename}</span>
        </span>
      </div>
    </div>
  )
})

export function PlaceholderCard({ index, colIndex, focused }: { index: number; colIndex: number; focused: boolean }) {
  return (
    <div role="gridcell" aria-colindex={colIndex + 1} aria-label={`Loading shot ${index + 1}`} aria-busy="true" tabIndex={focused ? 0 : -1} data-index={index} className={`${s.card} ${s.placeholder}`}>
      <div className={s.frame} />
      <div className={s.strip} aria-hidden="true">
        <span />
      </div>
    </div>
  )
}
