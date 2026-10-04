/**
 * UI state (Zustand). Server state lives in TanStack Query; shareable search
 * state lives in the URL (TanStack Router). This holds per-user preferences
 * (persisted) and transient UI state such as the shot selection.
 */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { IntendedUse, SearchRequest, SearchResponse, SearchResult } from '../api/types'
import type { TimecodeFormat } from './timecode'

export type Theme = 'system' | 'light' | 'dark'
export type Density = 'compact' | 'default' | 'comfortable'
export type MotionPref = 'system' | 'reduced' | 'full'
export type ThumbSize = 's' | 'm' | 'l'
export type ResultsView = 'grid' | 'list' | 'log'
export type Strictness = 'loose' | 'balanced' | 'strict'

export interface Prefs {
  theme: Theme
  density: Density
  motion: MotionPref
  contrast: 'system' | 'more'
  textSize: 100 | 112.5 | 125
  scrub: boolean
  dwellPreview: boolean
  timecodeFormat: TimecodeFormat
  singleKeys: boolean
  railOpen: boolean
  inspectorOpen: boolean
  inspectorPinned: boolean
  railWidth: number
  inspectorWidth: number
  thumbSize: ThumbSize
  view: ResultsView
  strictness: Strictness
  activeCollection: string | null
  defaultUse: { use?: string; channel?: string; territory?: string }
  recentShots: string[]
  set: (p: Partial<Omit<Prefs, 'set'>>) => void
}

export const usePrefs = create<Prefs>()(
  persist(
    (set) => ({
      theme: 'system',
      density: 'default',
      motion: 'system',
      contrast: 'system',
      textSize: 100,
      scrub: true,
      dwellPreview: true,
      timecodeFormat: 'smpte',
      singleKeys: true,
      railOpen: true,
      inspectorOpen: true,
      inspectorPinned: false,
      railWidth: 264,
      inspectorWidth: 384,
      thumbSize: 'm',
      view: 'grid',
      strictness: 'balanced',
      activeCollection: null,
      defaultUse: {},
      recentShots: [],
      set: (p) => set(p),
    }),
    { name: 'mc.prefs', version: 1, partialize: ({ set: _s, ...rest }) => rest },
  ),
)

/** Reflect display prefs on <html> (system.md §1.11). */
export function applyPrefsToDocument(p: Pick<Prefs, 'theme' | 'density' | 'motion' | 'contrast' | 'textSize' | 'scrub'>) {
  const h = document.documentElement
  const setAttr = (k: string, v: string | null) => (v ? h.setAttribute(k, v) : h.removeAttribute(k))
  setAttr('data-theme', p.theme === 'system' ? null : p.theme)
  setAttr('data-density', p.density === 'default' ? null : p.density)
  setAttr('data-motion', p.motion === 'system' ? null : p.motion)
  setAttr('data-contrast', p.contrast === 'more' ? 'more' : null)
  setAttr('data-scrub', p.scrub ? 'on' : 'off')
  h.style.fontSize = p.textSize === 100 ? '' : `${p.textSize}%`
}

export function prefersReducedMotion(): boolean {
  const m = document.documentElement.getAttribute('data-motion')
  if (m === 'reduced') return true
  if (m === 'full') return false
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

// ---------------------------------------------------------------- transient UI state

export interface ExampleSearch {
  name: string
  kind: 'image' | 'clip'
  response: SearchResponse
  /** Kept so the search can re-run when the rights filters change. */
  file?: File
  /** Rights options the response was computed with (JSON of SimilarRights). */
  rightsKey?: string
}

interface UiState {
  selection: Set<string>
  /** Shot shown in the inspector (follows grid focus). */
  inspected: string | null
  /** Ordered result ids of the last search, for [ / ] in Shot detail. */
  resultOrder: string[]
  resultCache: Map<string, SearchResult>
  /** Total results of the last search (the pager in Shot detail counts these, not just the loaded page). */
  resultTotal: number
  /** Request and next-page cursor of the last search, to page on from Shot detail. */
  resultPaging: { req: SearchRequest; next: string | null } | null
  lastQuery: string
  example: ExampleSearch | null
  railDrawer: boolean
  /** ⌘Enter in the search bar: focus the first result once it arrives. */
  focusResultsPending: string | null
  commandOpen: boolean
  shortcutsOpen: boolean
  sendDialog: ({ kind: 'collection'; uid: string } | { kind: 'shots'; uids: string[] }) & { consumer?: 'cutawan' | 'nle'; use?: IntendedUse | null } | null
  rightsDialog: { assetUids: string[]; shotUid?: string; title?: string } | null
  addToDialog: string[] | null
  /** Command menu: "Search in folder…" / "Search in collection…". */
  scopeDialog: 'folder' | 'collection' | null
  /** Command menu: "Import from links…" (a timestamp; Ingest focuses the links field when it is recent). */
  importLinksFocus: number
  setSelection: (s: Set<string>) => void
  toggleSelected: (uid: string) => void
  clearSelection: () => void
  inspect: (uid: string | null) => void
  rememberResults: (results: SearchResult[], query?: string, total?: number, paging?: { req: SearchRequest; next: string | null } | null) => void
  appendResults: (results: SearchResult[], next: string | null) => void
  set: (p: Partial<UiState>) => void
}

export const useUi = create<UiState>()((set, get) => ({
  selection: new Set(),
  inspected: null,
  resultOrder: [],
  resultCache: new Map(),
  resultTotal: 0,
  resultPaging: null,
  lastQuery: '',
  example: null,
  railDrawer: false,
  focusResultsPending: null,
  commandOpen: false,
  shortcutsOpen: false,
  sendDialog: null,
  rightsDialog: null,
  addToDialog: null,
  scopeDialog: null,
  importLinksFocus: 0,
  setSelection: (s) => set({ selection: s }),
  toggleSelected: (uid) => {
    const s = new Set(get().selection)
    if (s.has(uid)) s.delete(uid)
    else s.add(uid)
    set({ selection: s })
  },
  clearSelection: () => set({ selection: new Set() }),
  inspect: (uid) => set({ inspected: uid }),
  rememberResults: (results, query = '', total, paging = null) => {
    const cache = get().resultCache
    for (const r of results) cache.set(r.uid, r)
    set({ resultOrder: results.map((r) => r.uid), lastQuery: query, resultTotal: Math.max(total ?? results.length, results.length), resultPaging: paging })
  },
  appendResults: (results, next) => {
    const cache = get().resultCache
    for (const r of results) cache.set(r.uid, r)
    const seen = new Set(get().resultOrder)
    const paging = get().resultPaging
    set({ resultOrder: [...get().resultOrder, ...results.map((r) => r.uid).filter((u) => !seen.has(u))], resultPaging: paging ? { ...paging, next } : null })
  },
  set: (p) => set(p),
}))

export function rememberRecentShot(uid: string) {
  const p = usePrefs.getState()
  p.set({ recentShots: [uid, ...p.recentShots.filter((x) => x !== uid)].slice(0, 12) })
}
