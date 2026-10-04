/**
 * Pool of preview <video> elements (ADR 013 §6, system.md §6).
 *
 * Cards never own a <video>. On hover intent (150 ms) or focus rest a pooled
 * element is warmed with the proxy (`preload="auto"`, seeked to the in-point);
 * on dwell or Space it is moved into the card's frame and played muted, looping
 * the shot at most three times. Elements keep their buffered proxy between uses,
 * so moving between shots of the same file is a seek, not a reload. Idle
 * elements drop their `src` after a while to release decoders.
 */

const POOL_SIZE = 4
const IDLE_RELEASE_MS = 30_000
const MAX_LOOPS = 3

interface Slot {
  el: HTMLVideoElement
  base: string | null
  owner: HTMLElement | null
  lastUsed: number
  idleTimer: number | undefined
}

export interface PreviewHandle {
  readonly el: HTMLVideoElement
  stop(): void
  isPlaying(): boolean
  toggle(): void
  setRate(rate: number): void
  seek(t: number): void
}

interface PerfLog {
  previewStarts: number[]
  last?: number
}

declare global {
  interface Window {
    __mcPerf?: PerfLog
  }
}

function perf(): PerfLog {
  if (!window.__mcPerf) window.__mcPerf = { previewStarts: [] }
  return window.__mcPerf
}

/** Record a preview start time (ms from intent to first painted frame). */
export function logPreviewStart(ms: number) {
  const p = perf()
  p.previewStarts.push(Math.round(ms))
  p.last = Math.round(ms)
  if (import.meta.env.DEV) console.debug(`[preview] first frame in ${Math.round(ms)} ms`)
}

const fragment = (inS: number, outS?: number) => `#t=${inS.toFixed(3)}${outS !== undefined ? `,${outS.toFixed(3)}` : ''}`

class PreviewPool {
  private slots: Slot[] = []
  private holder: HTMLDivElement | null = null
  private active: { slot: Slot; stop: () => void } | null = null

  private ensure() {
    if (this.slots.length || typeof document === 'undefined') return
    this.holder = document.createElement('div')
    this.holder.setAttribute('aria-hidden', 'true')
    this.holder.style.cssText = 'position:fixed;inline-size:1px;block-size:1px;overflow:hidden;opacity:0;pointer-events:none;inset-block-start:0;inset-inline-start:0'
    document.body.appendChild(this.holder)
    for (let i = 0; i < POOL_SIZE; i++) {
      const el = document.createElement('video')
      el.muted = true
      el.defaultMuted = true
      el.playsInline = true
      el.preload = 'auto'
      el.disablePictureInPicture = true
      el.setAttribute('muted', '')
      el.setAttribute('playsinline', '')
      el.setAttribute('aria-hidden', 'true')
      el.tabIndex = -1
      this.holder.appendChild(el)
      this.slots.push({ el, base: null, owner: null, lastUsed: 0, idleTimer: undefined })
    }
  }

  private pick(base: string): Slot {
    this.ensure()
    const free = this.slots.filter((s) => !s.owner)
    const pool = free.length ? free : this.slots
    return pool.find((s) => s.base === base) ?? pool.slice().sort((a, b) => a.lastUsed - b.lastUsed)[0]
  }

  private load(slot: Slot, base: string, inS: number, outS?: number) {
    window.clearTimeout(slot.idleTimer)
    slot.lastUsed = performance.now()
    if (slot.base !== base) {
      slot.base = base
      slot.el.src = base + fragment(inS, outS)
    } else if (Math.abs(slot.el.currentTime - inS) > 0.04) {
      if (slot.el.readyState >= 1) slot.el.currentTime = inS
    }
  }

  private scheduleIdle(slot: Slot) {
    window.clearTimeout(slot.idleTimer)
    slot.idleTimer = window.setTimeout(() => {
      if (slot.owner) return
      slot.el.removeAttribute('src')
      slot.el.load()
      slot.base = null
    }, IDLE_RELEASE_MS)
  }

  /** Hover intent / focus rest: start fetching the proxy at the in-point. */
  warm(base: string, inS: number, outS?: number) {
    if (!base) return
    const slot = this.pick(base)
    if (slot.owner) return
    this.load(slot, base, inS, outS)
    this.scheduleIdle(slot)
  }

  /** Stop whatever preview is playing. */
  stopActive() {
    this.active?.stop()
  }

  /**
   * Play the shot in place inside `container`. `startedAt` is the intent time
   * (keydown or dwell end) used to measure start latency.
   */
  play(container: HTMLElement, base: string, inS: number, outS: number, opts: { className?: string; startedAt?: number; rate?: number; onEnd?: () => void } = {}): PreviewHandle {
    this.active?.stop()
    const slot = this.pick(base)
    if (slot.owner && slot.owner !== container) this.detach(slot)
    const el = slot.el
    slot.owner = container
    this.load(slot, base, inS, outS)
    el.className = opts.className ?? ''
    el.removeAttribute('aria-hidden')
    el.setAttribute('aria-hidden', 'true')
    container.appendChild(el)
    const t0 = opts.startedAt ?? performance.now()
    let loops = 0
    let stopped = false
    let measured = false
    let reverseTimer = 0

    const onTime = () => {
      if (el.currentTime >= outS - 0.03) {
        loops++
        if (loops >= MAX_LOOPS) {
          el.pause()
          opts.onEnd?.()
        } else el.currentTime = inS
      }
    }
    const markFirstFrame = () => {
      if (measured || stopped) return
      measured = true
      logPreviewStart(performance.now() - t0)
      container.dataset.previewing = 'playing'
    }
    const startPlayback = () => {
      if (stopped) return
      if (Math.abs(el.currentTime - inS) > 0.04) el.currentTime = inS
      el.playbackRate = opts.rate ?? 1
      const p = el.play()
      if (p) p.catch(() => undefined)
      if ('requestVideoFrameCallback' in el) el.requestVideoFrameCallback(() => markFirstFrame())
      else el.addEventListener('playing', markFirstFrame, { once: true })
    }
    el.addEventListener('timeupdate', onTime)
    container.dataset.previewing = 'loading'
    if (el.readyState >= 1) startPlayback()
    else el.addEventListener('loadedmetadata', startPlayback, { once: true })

    const stopReverse = () => {
      window.clearInterval(reverseTimer)
      reverseTimer = 0
    }
    const stop = () => {
      if (stopped) return
      stopped = true
      stopReverse()
      el.removeEventListener('timeupdate', onTime)
      el.removeEventListener('loadedmetadata', startPlayback)
      el.pause()
      delete container.dataset.previewing
      this.detach(slot)
      if (this.active?.slot === slot) this.active = null
    }
    this.active = { slot, stop }
    return {
      el,
      stop,
      isPlaying: () => !stopped && (!el.paused || reverseTimer !== 0),
      toggle: () => {
        if (stopped) return
        stopReverse()
        if (el.paused) {
          loops = 0
          el.play().catch(() => undefined)
        } else el.pause()
      },
      setRate: (rate: number) => {
        if (stopped) return
        stopReverse()
        if (rate === 0) {
          el.pause()
          return
        }
        if (rate > 0) {
          el.playbackRate = rate
          el.play().catch(() => undefined)
          return
        }
        // Reverse shuttle: the platform cannot play backwards, so step back.
        el.pause()
        const step = 1 / 15
        reverseTimer = window.setInterval(() => {
          const t = el.currentTime + rate * step
          el.currentTime = t <= inS ? outS - 0.05 : t
        }, step * 1000)
      },
      seek: (t: number) => {
        if (!stopped) el.currentTime = Math.min(outS, Math.max(inS, t))
      },
    }
  }

  private detach(slot: Slot) {
    slot.owner = null
    slot.lastUsed = performance.now()
    if (this.holder && slot.el.parentElement !== this.holder) this.holder.appendChild(slot.el)
    this.scheduleIdle(slot)
  }

  /** For tests and diagnostics: how many <video> elements exist in the pool. */
  size() {
    return this.slots.length
  }
}

export const previewPool = new PreviewPool()
