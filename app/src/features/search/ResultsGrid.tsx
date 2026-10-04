import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { useIsFetching } from '@tanstack/react-query'
import { Popover } from 'react-aria-components'
import {
  Copy, ExternalLink, FileVideoCamera, Film, FolderOpen, FolderSearch, Layers, PenLine, Play, Plus, ScanSearch, ShieldCheck,
} from 'lucide-react'
import type { SearchResult } from '../../api/types'
import { mediaUrl } from '../../api/client'
import { queryClient, shotQuery } from '../../api/queries'
import { Menu, MenuItem, MenuSeparator } from '../../components/Menu'
import { RightsBadge } from '../../components/RightsBadge'
import { toast } from '../../components/Toast'
import { Timecode } from '../../components/Timecode'
import { isTyping } from '../../hooks/useHotkeys'
import { bridge, can, MOD } from '../../lib/bridge'
import { buildRows, gridGeometry, moveIndex, rowOfItem, type VRow } from '../../lib/gridLayout'
import { humanise } from '../../lib/format'
import { basename } from '../../lib/scope'
import type { RightsState } from '../../lib/rights'
import { usePrefs, useUi, type ResultsView } from '../../lib/store'
import { formatDuration, formatTimecode, fpsLabel, fpsTitle } from '../../lib/timecode'
import { MatchRail } from './MatchRail'
import { PlaceholderCard, ShotCard, type CardController } from './ShotCard'
import o from '../../components/Overlay.module.css'
import t from '../../styles/type.module.css'
import s from './ResultsGrid.module.css'

const THUMB_MIN = { s: 168, m: 232, l: 320 } as const
const LIST_ROW = 52
const LOG_ROW = 118
const DIVIDER_ROW = 40

export interface ResultsGridProps {
  results: SearchResult[]
  total: number
  hasMore: boolean
  isFetchingMore: boolean
  loadMore: () => void
  split: number | null
  rightsOf: (r: SearchResult) => RightsState
  onOpen: (r: SearchResult, how: 'click' | 'double' | 'enter') => void
  onFocusShot: (r: SearchResult) => void
  onSimilar: (uids: string[]) => void
  onAddToActive: (uids: string[]) => void
  onAddTo: (uids: string[]) => void
  onRights: (uids: string[]) => void
  onEditTags: (r: SearchResult) => void
  onCycleView: () => void
  onToggleGroup: () => void
  activeName: string
  label: string
  /** Query text of the results shown (for ⌘Enter focus). */
  queryText: string
  /** Select every result of the query (pages through the core, not just the loaded rows). */
  onSelectAll?: () => void
  /** Scope search to a result's folder (absolute path). */
  onScopeFolder?: (folder: string) => void
}

/** Match-rail values 0..1: the core's absolute strength, or the score relative to the top when nothing was scored. */
export function railValues(results: { score: number; strength?: number | null }[]): number[] {
  if (results.some((r) => typeof r.strength === 'number')) return results.map((r) => (typeof r.strength === 'number' ? r.strength : 0))
  const top = results[0]?.score || 1
  return results.map((r) => Math.max(0, Math.min(1, r.score / top)))
}

export function shotReference(r: SearchResult): string {
  const inS = r.in ?? r.start
  const outS = r.out ?? r.end
  return `${r.filename} · ${formatTimecode(inS, r.fps)} → ${formatTimecode(outS, r.fps)}`
}

function cssPx(name: string, fallback: number): number {
  const v = parseFloat(getComputedStyle(document.documentElement).getPropertyValue(name))
  return Number.isFinite(v) ? v : fallback
}

/**
 * Virtualised results (TanStack Virtual rows) with a hand-rolled APG grid:
 * roving tabindex, aria-rowcount/rowindex, focused-row pinning (ADR 013 §4 fallback).
 * The scroll height is pre-allocated from the total; unloaded cells are letterbox wells.
 */
export function ResultsGrid(props: ResultsGridProps) {
  const { results, total, hasMore, isFetchingMore, loadMore, split, rightsOf, onOpen, onFocusShot } = props
  const view = usePrefs((p) => p.view)
  const thumbSize = usePrefs((p) => p.thumbSize)
  const density = usePrefs((p) => p.density)
  const selection = useUi((u) => u.selection)
  const scrollerRef = useRef<HTMLDivElement>(null)
  const gridRef = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  const [focusIndex, setFocusIndex] = useState(0)
  const anchor = useRef(0)
  const controllers = useRef(new Map<number, CardController>())
  const [menu, setMenu] = useState<{ index: number } | null>(null)
  const menuAnchor = useRef<HTMLElement | null>(null)

  useLayoutEffect(() => {
    const el = scrollerRef.current
    if (!el) return
    const ro = new ResizeObserver(() => setWidth(el.clientWidth))
    ro.observe(el)
    setWidth(el.clientWidth)
    return () => ro.disconnect()
  }, [])

  const gap = useMemo(() => cssPx('--thumb-gap', 12), [density]) // eslint-disable-line react-hooks/exhaustive-deps
  const geo = useMemo(() => gridGeometry(width || 800, THUMB_MIN[thumbSize], gap), [width, thumbSize, gap])
  const cols = view === 'grid' ? geo.cols : 1
  const rowH = view === 'grid' ? geo.rowH : view === 'list' ? LIST_ROW : LOG_ROW
  const rows = useMemo(() => buildRows(total, cols, split), [total, cols, split])
  // Screen readers count rows of shots, not the divider ("Row 2 of 30").
  const rowNumbers = useMemo(() => {
    let n = 0
    return rows.map((r) => (r.kind === 'items' ? ++n : 0))
  }, [rows])
  const itemRows = rowNumbers.reduce((a, b) => Math.max(a, b), 0)

  const virtualizer = useVirtualizer({
    count: rows.length,
    getScrollElement: () => scrollerRef.current,
    estimateSize: (i) => (rows[i]?.kind === 'divider' ? DIVIDER_ROW : rowH),
    overscan: 2,
    paddingStart: view === 'grid' ? 4 : 0,
    paddingEnd: 24,
  })

  useEffect(() => {
    virtualizer.measure()
  }, [rowH, cols, rows.length, view, virtualizer])

  const items = virtualizer.getVirtualItems()

  // Infinite loading: fetch the next page as the viewport nears the loaded edge.
  const lastRow = items.length ? rows[items[items.length - 1].index] : undefined
  const lastVisibleItem = lastRow && lastRow.kind === 'items' ? lastRow.start + lastRow.count : 0
  useEffect(() => {
    if (hasMore && !isFetchingMore && lastVisibleItem >= results.length - cols * 2) loadMore()
  }, [lastVisibleItem, results.length, hasMore, isFetchingMore, loadMore, cols])

  // Keep the focus index valid when results change.
  useEffect(() => {
    if (focusIndex >= Math.max(1, total)) setFocusIndex(0)
  }, [total, focusIndex])

  // Inspector follows grid focus after 150 ms.
  const focused = results[focusIndex]
  useEffect(() => {
    if (!focused) return
    const t0 = window.setTimeout(() => onFocusShot(focused), 150)
    return () => window.clearTimeout(t0)
  }, [focused, onFocusShot])

  const focusItem = (i: number, scroll = true) => {
    const idx = Math.max(0, Math.min(Math.max(0, total - 1), i))
    setFocusIndex(idx)
    if (scroll) virtualizer.scrollToIndex(rowOfItem(rows, idx), { align: 'auto' })
    requestAnimationFrame(() => {
      const el = gridRef.current?.querySelector<HTMLElement>(`[data-index="${idx}"]`)
      if (el) el.focus({ preventScroll: false })
      else
        window.setTimeout(() => {
          gridRef.current?.querySelector<HTMLElement>(`[data-index="${idx}"]`)?.focus()
        }, 60)
    })
    return idx
  }

  const focusPending = useUi((u) => u.focusResultsPending)
  const fetching = useIsFetching({ queryKey: ['search'] }) > 0
  useEffect(() => {
    if (focusPending !== null && focusPending === props.queryText && results.length && !fetching) {
      useUi.getState().set({ focusResultsPending: null })
      focusItem(0)
    }
  })

  const ui = useUi.getState
  const targetUids = (r?: SearchResult) => {
    const sel = ui().selection
    if (sel.size && (!r || sel.has(r.uid))) return [...sel]
    return r ? [r.uid] : []
  }

  const selectRange = (from: number, to: number) => {
    const next = new Set(ui().selection)
    const [a, b] = from < to ? [from, to] : [to, from]
    for (let i = a; i <= b; i++) if (results[i]) next.add(results[i].uid)
    ui().setSelection(next)
  }

  const toggleAt = (i: number, mode: 'toggle' | 'range') => {
    const r = results[i]
    if (!r) return
    if (mode === 'range') selectRange(anchor.current, i)
    else {
      ui().toggleSelected(r.uid)
      anchor.current = i
    }
  }

  const copy = (text: string, msg: string) => {
    navigator.clipboard?.writeText(text).catch(() => undefined)
    toast({ title: msg, tone: 'info' })
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (isTyping(e.target)) return
    const mod = e.metaKey || e.ctrlKey
    const single = usePrefs.getState().singleKeys && !mod && !e.altKey
    const r = results[focusIndex]
    const ctrl = controllers.current.get(focusIndex)
    const go = (to: number) => {
      e.preventDefault()
      const prev = focusIndex
      const idx = focusItem(to)
      if (e.shiftKey && !single) selectRange(prev, idx)
      else if (e.shiftKey) selectRange(anchor.current, idx)
      else anchor.current = idx
    }
    const pageRows = Math.max(1, Math.floor((scrollerRef.current?.clientHeight ?? 600) / rowH))
    const k = e.key
    if (k === 'ArrowLeft' || k === 'ArrowRight') {
      if (e.altKey) {
        e.preventDefault()
        ctrl?.stepScrub(k === 'ArrowLeft' ? -1 : 1)
        return
      }
      return go(moveIndex(rows, focusIndex, k === 'ArrowLeft' ? 'left' : 'right', total))
    }
    if (k === 'ArrowUp' || k === 'ArrowDown') return go(moveIndex(rows, focusIndex, k === 'ArrowUp' ? 'up' : 'down', total))
    if (k === 'Home') return go(mod ? 0 : moveIndex(rows, focusIndex, 'home', total))
    if (k === 'End') return go(mod ? Math.max(0, (hasMore ? results.length : total) - 1) : moveIndex(rows, focusIndex, 'end', total))
    if (k === 'PageDown') return go(Math.min(total - 1, focusIndex + pageRows * cols))
    if (k === 'PageUp') return go(Math.max(0, focusIndex - pageRows * cols))
    if (k === ' ' || k === 'Spacebar') {
      e.preventDefault()
      if (mod) toggleAt(focusIndex, 'toggle')
      else ctrl?.togglePreview(performance.now())
      return
    }
    if (k === 'Enter' && r) {
      e.preventDefault()
      onOpen(r, 'enter')
      return
    }
    if (k === 'Escape') {
      if (ctrl?.isPreviewing()) {
        e.preventDefault()
        ctrl.stopPreview()
      } else if (ui().selection.size) {
        e.preventDefault()
        ui().clearSelection()
      }
      return
    }
    if ((k === 'F10' && e.shiftKey) || k === 'ContextMenu') {
      e.preventDefault()
      const el = gridRef.current?.querySelector<HTMLElement>(`[data-index="${focusIndex}"]`)
      if (el) {
        menuAnchor.current = el
        setMenu({ index: focusIndex })
      }
      return
    }
    if (mod && k.toLowerCase() === 'a') {
      e.preventDefault()
      if (e.shiftKey) ui().clearSelection()
      else if (props.onSelectAll) props.onSelectAll()
      else ui().setSelection(new Set(results.map((x) => x.uid)))
      return
    }
    if (mod && k.toLowerCase() === 'c' && r) {
      e.preventDefault()
      const uids = targetUids(r)
      copy(uids.map((u) => results.find((x) => x.uid === u)).filter(Boolean).map((x) => shotReference(x as SearchResult)).join('\n'), uids.length > 1 ? `Copied ${uids.length} shot references` : 'Copied shot reference')
      return
    }
    if (!usePrefs.getState().singleKeys || mod || e.altKey || !r) return
    switch (k.toLowerCase()) {
      case 'x':
        e.preventDefault()
        toggleAt(focusIndex, 'toggle')
        if (e.shiftKey) focusItem(focusIndex + 1)
        return
      case 'j':
      case 'k':
      case 'l':
        e.preventDefault()
        ctrl?.shuttle(k.toLowerCase() as 'j' | 'k' | 'l')
        return
      case 'b':
        e.preventDefault()
        props.onAddToActive(e.shiftKey ? [r.uid] : targetUids(r))
        if (e.shiftKey) focusItem(focusIndex + 1)
        return
      case 'a':
        e.preventDefault()
        props.onAddTo(targetUids(r))
        return
      case 's':
        e.preventDefault()
        props.onSimilar(targetUids(r))
        return
      case 'r':
        e.preventDefault()
        props.onRights(targetUids(r))
        return
      case 'e':
        e.preventDefault()
        props.onEditTags(r)
        return
      case 'v':
        e.preventDefault()
        props.onCycleView()
        return
      case 'g':
        e.preventDefault()
        props.onToggleGroup()
        return
    }
  }

  const register = (i: number, c: CardController | null) => {
    if (c) controllers.current.set(i, c)
    else controllers.current.delete(i)
  }

  // Stable callbacks so memoised cards skip re-rendering while the grid scrolls.
  const latest = useRef({ toggleAt, register, results, onOpen, props, targetUids })
  latest.current = { toggleAt, register, results, onOpen, props, targetUids }
  const stable = useMemo(
    () => ({
      onFocusIndex: (idx: number) => setFocusIndex(idx),
      onActivate: (idx: number, how: 'click' | 'double') => {
        setFocusIndex(idx)
        anchor.current = idx
        const rr = latest.current.results[idx]
        if (rr) latest.current.onOpen(rr, how)
      },
      onToggleSelect: (i: number, mode: 'toggle' | 'range') => latest.current.toggleAt(i, mode),
      onMenu: (idx: number, el: HTMLElement) => {
        menuAnchor.current = el
        setFocusIndex(idx)
        setMenu({ index: idx })
      },
      onSimilar: (uid: string) => latest.current.props.onSimilar([uid]),
      onAdd: (uid: string) => latest.current.props.onAddToActive([uid]),
      dragUids: (uid: string) => latest.current.targetUids(latest.current.results.find((x) => x.uid === uid)),
      register: (i: number, c: CardController | null) => latest.current.register(i, c),
    }),
    [],
  )

  const menuResult = menu ? results[menu.index] : undefined
  const totalSize = virtualizer.getTotalSize()

  return (
    <div className={s.wrap}>
      <div ref={scrollerRef} className={s.scroller} data-testid="results-scroller">
        {view === 'list' && <ListHeader />}
        <div
          ref={gridRef}
          role="grid"
          id="results"
          aria-label={props.label}
          aria-rowcount={itemRows}
          aria-colcount={cols}
          aria-multiselectable="true"
          aria-description="Space previews, X selects, Enter opens."
          className={s.grid}
          style={{ blockSize: totalSize, ['--gap' as string]: `${geo.gap}px`, ['--pad' as string]: `${geo.pad}px`, ['--card-w' as string]: `${geo.cardW}px` }}
          onKeyDown={onKeyDown}
          data-testid="results-grid"
        >
          {items.map((vi) => {
            const row = rows[vi.index] as VRow
            if (row.kind === 'divider') {
              return (
                <div key={`d${vi.index}`} role="presentation" aria-hidden="true" className={s.divider} style={{ transform: `translateY(${vi.start}px)`, blockSize: vi.size }}>
                  <span className={t.slate}>Weaker matches below</span>
                </div>
              )
            }
            const cells = []
            for (let c = 0; c < row.count; c++) {
              const i = row.start + c
              const r = results[i]
              const focusedCell = i === focusIndex
              if (!r) {
                cells.push(view === 'grid' ? <PlaceholderCard key={`p${i}`} index={i} colIndex={c} focused={focusedCell} /> : <div key={`p${i}`} role="gridcell" aria-busy="true" aria-label={`Loading shot ${i + 1}`} data-index={i} tabIndex={focusedCell ? 0 : -1} className={`${s.item} ${view === 'list' ? s.listItem : s.logItem}`} />)
                continue
              }
              const common = {
                r,
                index: i,
                focused: focusedCell,
                selected: selection.has(r.uid),
                rights: rightsOf(r),
                onFocusIndex: stable.onFocusIndex,
                onActivate: stable.onActivate,
              }
              if (view === 'grid') {
                cells.push(
                  <ShotCard
                    key={r.uid}
                    {...common}
                    colIndex={c}
                    onToggleSelect={stable.onToggleSelect}
                    onMenu={stable.onMenu}
                    onSimilar={stable.onSimilar}
                    onAdd={stable.onAdd}
                    dragUids={stable.dragUids}
                    register={stable.register}
                  />,
                )
              } else cells.push(<ListItem key={r.uid} {...common} view={view} onToggleSelect={stable.onToggleSelect} />)
            }
            return (
              <div
                key={`r${vi.index}`}
                role="row"
                aria-rowindex={rowNumbers[vi.index]}
                aria-label={`Row ${rowNumbers[vi.index]} of ${itemRows}`}
                className={view === 'grid' ? s.row : s.listRow}
                style={{ transform: `translateY(${vi.start}px)`, blockSize: view === 'grid' ? geo.cardH : vi.size }}
              >
                {cells}
              </div>
            )
          })}
        </div>
      </div>
      {view === 'grid' && <MatchRail scroller={scrollerRef} values={railValues(results)} total={total} split={split} gridId="results" />}
      <Popover
        triggerRef={menuAnchor as React.RefObject<HTMLElement>}
        isOpen={Boolean(menu && menuResult)}
        onOpenChange={(open) => {
          if (!open) {
            setMenu(null)
            requestAnimationFrame(() => gridRef.current?.querySelector<HTMLElement>(`[data-index="${focusIndex}"]`)?.focus())
          }
        }}
        placement="bottom start"
        offset={-40}
        crossOffset={16}
        className={o.popover}
      >
        {menuResult && (
          <Menu aria-label="Shot actions" autoFocus="first" onClose={() => setMenu(null)}>
            <MenuItem icon={Film} shortcut="Enter" onAction={() => onOpen(menuResult, 'enter')}>Open</MenuItem>
            <MenuItem icon={FileVideoCamera} onAction={() => window.dispatchEvent(new CustomEvent('mc:open-file', { detail: menuResult }))}>Open file</MenuItem>
            <MenuItem icon={Play} shortcut="Space" onAction={() => controllers.current.get(menu?.index ?? -1)?.togglePreview(performance.now())}>Preview</MenuItem>
            <MenuItem icon={ScanSearch} shortcut="S" onAction={() => props.onSimilar(targetUids(menuResult))}>Find similar</MenuItem>
            {menuResult.folder && props.onScopeFolder && (
              <MenuItem icon={FolderSearch} onAction={() => props.onScopeFolder?.(menuResult.folder as string)}>{`Search in folder ${basename(menuResult.folder)}`}</MenuItem>
            )}
            <MenuSeparator />
            <MenuItem icon={Plus} shortcut="B" onAction={() => props.onAddToActive(targetUids(menuResult))}>{`Add to ${props.activeName}`}</MenuItem>
            <MenuItem icon={Layers} shortcut="A" onAction={() => props.onAddTo(targetUids(menuResult))}>Add to…</MenuItem>
            <MenuSeparator />
            <MenuItem icon={Copy} onAction={() => copy(formatTimecode(menuResult.in ?? menuResult.start, menuResult.fps), `Copied ${formatTimecode(menuResult.in ?? menuResult.start, menuResult.fps)}`)}>Copy timecode</MenuItem>
            <MenuItem icon={Copy} shortcut={`${MOD}C`} onAction={() => copy(shotReference(menuResult), 'Copied shot reference')}>Copy shot reference</MenuItem>
            <MenuItem icon={PenLine} shortcut="E" onAction={() => props.onEditTags(menuResult)}>Edit tags</MenuItem>
            <MenuItem icon={ShieldCheck} shortcut="R" onAction={() => props.onRights(targetUids(menuResult))}>Rights…</MenuItem>
            {can('canRevealInFolder') ? (
              <MenuItem icon={FolderOpen} onAction={() => queryClient.fetchQuery(shotQuery(menuResult.uid)).then((d) => bridge()?.reveal(d.path))}>Reveal in folder</MenuItem>
            ) : (
              <MenuItem icon={ExternalLink} onAction={() => window.open(mediaUrl(menuResult.proxy), '_blank', 'noopener')}>Download proxy</MenuItem>
            )}
          </Menu>
        )}
      </Popover>
    </div>
  )
}

function ListHeader() {
  return (
    <div className={s.listHeader} aria-hidden="true">
      <div className={`${s.item} ${s.listItem}`}>
        <span />
        <span className={t.slate}>In → out</span>
        <span className={t.slate}>Dur</span>
        <span className={t.slate}>Description</span>
        <span className={`${t.slate} ${s.wideOnly}`}>File</span>
        <span className={`${t.slate} ${s.wideOnly}`}>Edit stage</span>
        <span className={`${t.slate} ${s.wideOnly}`}>FPS</span>
        <span className={`${t.slate} ${s.wideOnly}`}>Resolution</span>
        <span className={t.slate}>Rights</span>
      </div>
    </div>
  )
}

interface ListItemProps {
  r: SearchResult
  index: number
  focused: boolean
  selected: boolean
  rights: RightsState
  view: ResultsView
  onFocusIndex: (i: number) => void
  onActivate: (i: number, how: 'click' | 'double') => void
  onToggleSelect: (i: number, mode: 'toggle' | 'range') => void
}

function ListItem({ r, index, focused, selected, rights, view, onFocusIndex, onActivate, onToggleSelect }: ListItemProps) {
  const inS = r.in ?? r.start
  const outS = r.out ?? r.end
  const desc = r.caption || r.summary || r.filename
  const handlers = {
    role: 'gridcell' as const,
    'aria-selected': selected,
    tabIndex: focused ? 0 : -1,
    'data-index': index,
    'data-uid': r.uid,
    onFocus: (e: React.FocusEvent) => e.target === e.currentTarget && onFocusIndex(index),
    onClick: (e: React.MouseEvent) => {
      if (e.metaKey || e.ctrlKey) onToggleSelect(index, 'toggle')
      else if (e.shiftKey) onToggleSelect(index, 'range')
      else onActivate(index, 'click')
    },
    onDoubleClick: () => onActivate(index, 'double'),
  }
  if (view === 'list') {
    return (
      <div {...handlers} aria-label={`${desc}. ${r.filename}${r.folder ? `, in ${basename(r.folder)}` : ''}`} className={`${s.item} ${s.listItem}`}>
        {r.thumb ? <img className={s.thumbSm} src={mediaUrl(r.thumb)} alt="" loading="lazy" decoding="async" /> : <span className={s.thumbSm} />}
        <span className={s.cellMono}>
          <Timecode seconds={inS} fps={r.fps} size="xs" /> → <Timecode seconds={outS} fps={r.fps} size="xs" />
        </span>
        <span className={s.cellMono}>{formatDuration(outS - inS)}</span>
        <span className={s.cellText}>{desc}</span>
        <span className={`${s.cellText} ${s.wideOnly}`} style={{ color: 'var(--fg-2)' }} title={r.folder ? `${r.folder}/${r.filename}` : r.filename}>
          {r.folder ? `${basename(r.folder)} › ${r.filename}` : r.filename}
        </span>
        <span className={`${s.cellText} ${s.wideOnly}`} style={{ color: 'var(--fg-2)' }}>{humanise(r.edit_type)}</span>
        <span className={`${s.cellMono} ${s.wideOnly}`} title={fpsTitle(r.fps)}>{fpsLabel(r.fps)}</span>
        <span className={`${s.cellMono} ${s.wideOnly}`}>{r.resolution?.replace('x', '×')}</span>
        <span>
          <RightsBadge state={rights} reasons={r.rights?.reasons} />
        </span>
      </div>
    )
  }
  const snippet = r.why.find((w) => w.snippet)?.snippet
  return (
    <div {...handlers} aria-label={`${desc}. ${r.filename}${r.folder ? `, in ${basename(r.folder)}` : ''}`} className={`${s.item} ${s.logItem}`}>
      {r.thumb ? <img className={s.thumbLog} src={mediaUrl(r.thumb)} alt="" loading="lazy" decoding="async" /> : <span className={s.thumbLog} />}
      <div className={s.logBody}>
        <span className={s.cellMono}>
          <Timecode seconds={inS} fps={r.fps} size="xs" /> → <Timecode seconds={outS} fps={r.fps} size="xs" /> · {formatDuration(outS - inS)} · {r.folder ? `${basename(r.folder)} › ` : ''}{r.filename}
        </span>
        <span className={s.logText}>{desc}</span>
        {snippet && <Snippet text={snippet} />}
        <span className={s.logSignals}>
          {r.shot_size && <span>{humanise(r.shot_size)}</span>}
          {r.camera_movement.slice(0, 2).map((m) => (
            <span key={m.term}>{humanise(m.term)}</span>
          ))}
          {r.time_of_day && <span>{humanise(r.time_of_day)}</span>}
          {r.pace && <span>{humanise(r.pace)} pace</span>}
        </span>
      </div>
      <RightsBadge state={rights} reasons={r.rights?.reasons} />
    </div>
  )
}

/** Render the core's [match] snippet markers as <mark>. */
export function Snippet({ text, className }: { text: string; className?: string }) {
  const parts = text.split(/(\[[^\]]+\])/g)
  return (
    <span className={className ?? s.logExcerpt}>
      {parts.map((p, i) => (p.startsWith('[') && p.endsWith(']') ? <mark key={i}>{p.slice(1, -1)}</mark> : <span key={i}>{p}</span>))}
    </span>
  )
}
