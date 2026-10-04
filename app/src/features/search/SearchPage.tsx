import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearch as useRouteSearch } from '@tanstack/react-router'
import { useQueries, useQuery } from '@tanstack/react-query'
import { CircleAlert, FolderPlus, Info, LayoutGrid, ListVideo, PanelLeftOpen, PanelRightOpen, Rows3, SlidersHorizontal, TriangleAlert } from 'lucide-react'
import type { SearchRequest, SearchResponse, SearchResult } from '../../api/types'
import { api, ApiError } from '../../api/client'
import {
  buildPackage, useAddToCollection, useCollections, useCreateCollection, useLibraryStats, useSearch, useShot, useVocabularies,
} from '../../api/queries'
import { Button, IconButton } from '../../components/Button'
import { Sheet } from '../../components/Dialog'
import { EmptyState } from '../../components/EmptyState'
import { Segmented } from '../../components/Segmented'
import { toast } from '../../components/Toast'
import { isDrawerRail, isOverlayInspector, useTier } from '../../hooks/useMediaQuery'
import { isMod, isTyping, useDocumentKeys } from '../../hooks/useHotkeys'
import { useDebounced } from '../../hooks/useDebounced'
import { activeFilterCount, buildPhraseIndex, chipsFromQuery, removeChip, type SearchState } from '../../lib/chips'
import { MOD } from '../../lib/bridge'
import { weakSplit } from '../../lib/gridLayout'
import { formatNumber, plural } from '../../lib/format'
import { stateFromBadge, stateFromVerdict } from '../../lib/rights'
import { usePrefs, useUi, type ResultsView, type Strictness, type ThumbSize } from '../../lib/store'
import { Inspector } from '../shot/Inspector'
import { ChipRow, type ExtraChip } from './ChipRow'
import { FilterRail } from './FilterRail'
import { FilesView } from './FilesView'
import { ResultsGrid } from './ResultsGrid'
import { SelectionBar } from './SelectionBar'
import { fromState, toRequest, toState, type SearchParams } from './searchParams'
import s from './SearchPage.module.css'

const STRICT_RATIO: Record<Strictness, number> = { loose: 0.25, balanced: 0.5, strict: 0.7 }

export function rightsOf(r: SearchResult) {
  return r.rights ? stateFromVerdict(r.rights.verdict, r.rights.reasons) : stateFromBadge(r.rights_badge)
}

/** Search surface (system.md §9.1, directions A1). */
export function SearchPage() {
  const params = useRouteSearch({ from: '/search' }) as SearchParams
  const navigate = useNavigate({ from: '/search' })
  const tier = useTier()
  const prefs = usePrefs()
  const example = useUi((u) => u.example)
  const inspected = useUi((u) => u.inspected)
  const selection = useUi((u) => u.selection)
  const setUi = useUi((u) => u.set)
  const railDrawer = useUi((u) => u.railDrawer)
  const { vocabs, label } = useVocabularies()
  const [sheetUid, setSheetUid] = useState<string | null>(null)
  const [editField, setEditField] = useState<string | null>(null)
  const [staged, setStaged] = useState<SearchParams | null>(null)
  const collections = useCollections()
  const addTo = useAddToCollection()
  const createCol = useCreateCollection()

  // Back/forward to a text or similar search leaves query-by-example mode.
  useEffect(() => {
    if (useUi.getState().example && (params.q || params.similar || params.req || params.f)) useUi.getState().set({ example: null })
  }, [params])

  const req = useMemo(() => toRequest(params), [params])
  const search = useSearch(example ? null : req)
  const pages = useMemo(() => search.data?.pages ?? [], [search.data])
  const first: SearchResponse | undefined = example ? example.response : pages[0]
  const results = useMemo(() => (example ? example.response.results : pages.flatMap((p) => p.results)), [example, pages])
  const total = example ? results.length : (first?.total ?? 0)
  const state = toState(params)

  const stats = useLibraryStats({ refetchInterval: 10_000 })
  const processing = stats.data?.status?.processing ?? 0
  const [seen, setSeen] = useState<{ at: number; shots: number | null }>({ at: 0, shots: null })
  if (search.isSuccess && stats.data && seen.at !== search.dataUpdatedAt) setSeen({ at: search.dataUpdatedAt, shots: stats.data.shots })
  const shotsAtSearch = seen.shots
  const setShotsAtSearch = (n: number | null) => setSeen({ at: search.dataUpdatedAt, shots: n })
  const newShots = stats.data && shotsAtSearch !== null ? stats.data.shots - shotsAtSearch : 0

  useEffect(() => {
    if (results.length) useUi.getState().rememberResults(results, params.q ?? '')
  }, [results, params.q])

  const setParams = useCallback((p: SearchParams, replace = true) => navigate({ search: p, replace }), [navigate])
  const setState = (st: SearchState) => setParams(fromState(st, params), false)

  const hasQuery = Boolean(params.q?.trim() || params.similar || example)
  const split = hasQuery ? weakSplit(results.map((r) => r.score), STRICT_RATIO[prefs.strictness], total) : null

  const overlay = isOverlayInspector(tier)
  const drawer = isDrawerRail(tier)
  const byUid = useMemo(() => new Map(results.map((r) => [r.uid, r])), [results])

  const onFocusShot = useCallback((r: SearchResult) => {
    if (useUi.getState().inspected !== r.uid) useUi.getState().inspect(r.uid)
  }, [])

  const onOpen = (r: SearchResult, how: 'click' | 'double' | 'enter') => {
    useUi.getState().inspect(r.uid)
    if (how === 'double' || (how === 'enter' && !overlay)) {
      navigate({ to: '/shot/$shotId', params: { shotId: r.uid } })
      return
    }
    if (overlay && (how === 'enter' || how === 'click')) setSheetUid(r.uid)
  }

  const activeCol = collections.data?.find((c) => c.uid === prefs.activeCollection) ?? collections.data?.find((c) => c.name === 'Selects') ?? collections.data?.[0]
  const activeName = activeCol?.name ?? 'Selects'

  const addToActive = async (uids: string[]) => {
    if (!uids.length) return
    try {
      if (activeCol) {
        await addTo.mutateAsync({ uid: activeCol.uid, shot_uids: uids })
        toast({ title: `Added ${plural(uids.length, 'shot')} to ${activeCol.name}` })
      } else {
        const c = await createCol.mutateAsync({ name: 'Selects', shot_uids: uids })
        usePrefs.getState().set({ activeCollection: c.uid })
        toast({ title: `Created Selects with ${plural(uids.length, 'shot')}` })
      }
    } catch (e) {
      toast({ title: "Couldn't add to the collection", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    }
  }

  const similar = (uids: string[]) => {
    if (!uids.length) return
    useUi.getState().set({ example: null, selection: new Set() })
    navigate({ search: { similar: uids[0] } })
  }

  const rights = (uids: string[]) => {
    const assets = [...new Set(uids.map((u) => byUid.get(u)?.asset_uid).filter(Boolean) as string[])]
    if (!assets.length) return
    const one = uids.length === 1 ? byUid.get(uids[0]) : undefined
    setUi({ rightsDialog: { assetUids: assets, shotUid: one?.uid, title: one ? `${one.filename} · shot ${one.idx + 1}` : `${plural(assets.length, 'file')}` } })
  }

  const exportTimeline = async (uids: string[]) => {
    try {
      const res = await buildPackage(
        uids.map((u) => ({ shot_uid: u })),
        { name: `Export · ${new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })}`, target: { consumer: 'nle' }, media_policy: 'none', zip: true },
      )
      toast({ title: 'Timeline ready: OTIO, FCPXML 1.10 and CMX 3600 EDL', description: res.path.split('/').pop(), action: { label: 'Download', onAction: () => window.open(res.download, '_blank', 'noopener') } })
    } catch (e) {
      toast({ title: "Couldn't export the timeline", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    }
  }

  const selected = [...selection]

  useDocumentKeys((e) => {
    if (isTyping(e.target)) return
    if (isMod(e) && e.key.toLowerCase() === 'e' && selection.size) {
      e.preventDefault()
      if (e.shiftKey) setUi({ sendDialog: { kind: 'shots', uids: selected } })
      else exportTimeline(selected)
    }
    if (isMod(e) && (e.key === '=' || e.key === '-' || e.key === '0')) {
      e.preventDefault()
      const order: ThumbSize[] = ['s', 'm', 'l']
      const i = order.indexOf(prefs.thumbSize)
      prefs.set({ thumbSize: e.key === '0' ? 'm' : order[Math.max(0, Math.min(2, i + (e.key === '=' ? 1 : -1)))] })
    }
  })

  // Similar-to label and query-by-example chips.
  const similarShot = useShot(params.similar)
  const extra: ExtraChip[] = []
  if (example) extra.push({ key: 'example', slate: example.kind === 'image' ? 'SIMILAR TO IMAGE' : 'SIMILAR TO CLIP', label: example.name, onRemove: () => setUi({ example: null }) })
  if (params.similar)
    extra.push({
      key: 'similar',
      slate: 'SIMILAR TO',
      label: similarShot.data ? `${similarShot.data.filename} · shot ${similarShot.data.idx + 1}` : 'Shot',
      onRemove: () => setParams({ ...params, similar: undefined }, false),
    })

  // No results: what removing each chip would show (§3.16).
  const index = useMemo(() => buildPhraseIndex(vocabs), [vocabs])
  const noResults = search.isSuccess && !example && total === 0
  const chips = useMemo(() => (noResults && first ? chipsFromQuery(first.query, state, label, index).slice(0, 4) : []), [noResults, first, state, label, index])
  const suggestions = useQueries({
    queries: chips.map((c) => {
      const next = removeChip(state, c, index)
      const body: SearchRequest | null = next ? { ...toRequest(fromState(next, params)), limit: 1, facets: false } : null
      return { queryKey: ['search-count', body], queryFn: () => api.post<SearchResponse>('/api/search', { ...body }), enabled: Boolean(body), staleTime: 60_000 }
    }),
  })

  // Tablet drawer: count for staged filters.
  const stagedCount = useQuery({
    queryKey: ['search-count', staged ? toRequest(staged) : null],
    queryFn: () => api.post<SearchResponse>('/api/search', { ...toRequest(staged as SearchParams), limit: 1, facets: false }),
    enabled: Boolean(staged),
  })
  const stagedDebounced = useDebounced(stagedCount.data?.total, 100)

  const files = new Set(results.map((r) => r.asset_uid)).size
  const secs = first?.timings_ms?.total ? (first.timings_ms.total / 1000).toFixed(1) : null
  const countText = example
    ? `${plural(total, 'similar shot')} to ${example.name}`
    : search.isLoading && !first
      ? 'Searching…'
      : `${plural(total, 'shot')}${total && results.length >= total ? ` in ${plural(files, 'file')}` : ''}${secs ? ` · ${secs} s` : ''}`

  const rail = (
    <FilterRail
      params={staged ?? params}
      facets={first?.facets ?? {}}
      excludedByRights={first?.excluded_by_rights ?? 0}
      vocabs={vocabs}
      label={label}
      onChange={(p) => (drawer ? setStaged(p) : setParams(p, false))}
      onCollapse={drawer ? undefined : () => prefs.set({ railOpen: false })}
      drawer={drawer}
    />
  )

  const inspectedResult = inspected ? byUid.get(inspected) : undefined
  const inspector = (
    <Inspector
      uid={overlay ? sheetUid : inspected}
      result={overlay ? (sheetUid ? byUid.get(sheetUid) : undefined) : inspectedResult}
      intended={req.intended_use}
      query={params.q}
      editField={editField}
      onClose={overlay ? () => setSheetUid(null) : undefined}
      onCollapse={overlay ? undefined : () => prefs.set({ inspectorOpen: false })}
    />
  )

  const active = activeFilterCount(state)
  const firstRun = stats.data && stats.data.assets === 0

  let body
  if (firstRun) {
    body = (
      <EmptyState icon={FolderPlus} title="Add your first footage" actions={<><Button variant="primary" onPress={() => navigate({ to: '/ingest' })}>Add a folder</Button><Button variant="quiet" onPress={() => navigate({ to: '/library' })}>Read how indexing works</Button></>}>
        Point Metachlorian at a folder. Files stay where they are, and we only read them.
      </EmptyState>
    )
  } else if (search.isError && !first) {
    const err = search.error
    body = (
      <EmptyState icon={CircleAlert} title="Search didn't work" role="alert" actions={<Button onPress={() => search.refetch()}>Try again</Button>}>
        <p>{err instanceof ApiError && err.status === 0 ? err.detail : "The search service didn't respond."}</p>
        <details style={{ marginBlockStart: 'var(--space-2)' }}>
          <summary>Details</summary>
          <code style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>
            {err instanceof ApiError ? `${err.id}: ${err.detail}` : String(err)}
          </code>
        </details>
      </EmptyState>
    )
  } else if (noResults) {
    const sugg = chips
      .map((c, i) => ({ c, n: suggestions[i]?.data?.total }))
      .filter((x) => x.n)
      .sort((a, b) => (b.n ?? 0) - (a.n ?? 0))
    body = (
      <EmptyState
        title={params.q ? `No shots match “${params.q}”` : active ? `Your filters hide all the shots` : 'No shots yet'}
        actions={
          <>
            {sugg.map(({ c, n }) => (
              <Button key={c.key} variant="secondary" onPress={() => { const next = removeChip(state, c, index); if (next) setState(next) }}>
                {`Remove ${c.label.toLowerCase()} (${formatNumber(n ?? 0)})`}
              </Button>
            ))}
            {active > 0 && <Button variant="quiet" onPress={() => setParams({ q: params.q })}>Clear all filters</Button>}
          </>
        }
      >
        {sugg.length ? (
          <p>
            {sugg.slice(0, 2).map(({ c, n }, i) => (
              <span key={c.key}>
                {i ? ' ' : ''}Removing <strong>{c.label.toLowerCase()}</strong> would show {plural(n ?? 0, 'shot')}.
              </span>
            ))}
          </p>
        ) : processing ? (
          <p>{processing} files are still being analysed. Shots appear here as soon as each file is ready.</p>
        ) : (
          <p>Try fewer words, or describe what is in the frame rather than where it was used.</p>
        )}
      </EmptyState>
    )
  } else if (params.group === 'files' && !example) {
    body = <FilesView results={results} onOpen={(r) => onOpen(r, 'click')} />
  } else {
    body = (
      <ResultsGrid
        results={results}
        total={total}
        hasMore={Boolean(search.hasNextPage) && !example}
        isFetchingMore={search.isFetchingNextPage}
        loadMore={() => search.fetchNextPage()}
        split={split}
        rightsOf={rightsOf}
        onOpen={onOpen}
        onFocusShot={onFocusShot}
        onSimilar={similar}
        onAddToActive={addToActive}
        onAddTo={(uids) => setUi({ addToDialog: uids })}
        onRights={rights}
        onEditTags={(r) => {
          useUi.getState().inspect(r.uid)
          setEditField('camera.shot_size')
          window.setTimeout(() => setEditField(null), 50)
          if (overlay) setSheetUid(r.uid)
          else prefs.set({ inspectorOpen: true })
        }}
        onCycleView={() => {
          const order: ResultsView[] = ['grid', 'list', 'log']
          prefs.set({ view: order[(order.indexOf(prefs.view) + 1) % 3] })
        }}
        onToggleGroup={() => setParams({ ...params, group: params.group === 'files' ? undefined : 'files' })}
        activeName={activeName}
        queryText={first?.query.text ?? ''}
        label={params.q ? `Results for ${params.q}` : 'All shots'}
      />
    )
  }

  const railCollapsed = !drawer && !prefs.railOpen
  return (
    <div className={s.page} style={{ ['--rail-w' as string]: `${prefs.railWidth}px`, ['--insp-w' as string]: `${prefs.inspectorWidth}px` }}>
      {!drawer &&
        (railCollapsed ? (
          <aside aria-label="Filters" className={`${s.rail} ${s.railCollapsed}`}>
            <IconButton icon={PanelLeftOpen} label="Show filters" shortcut={`${MOD}\\`} onPress={() => prefs.set({ railOpen: true })} placement="end" />
            {active > 0 && <span className={s.railCount}>{active}</span>}
          </aside>
        ) : (
          <aside aria-label="Filters" className={s.rail}>
            {rail}
          </aside>
        ))}
      <main id="main" className={s.main} aria-busy={search.isFetching || undefined} tabIndex={-1}>
        <ChipRow query={first?.query} state={state} vocabs={vocabs} label={label} onChange={setState} extra={extra} />
        <div className={s.header}>
          {drawer && (
            <Button variant="secondary" size="sm" icon={SlidersHorizontal} onPress={() => { setStaged(params); setUi({ railDrawer: true }) }}>
              {active ? `Filters · ${active}` : 'Filters'}
            </Button>
          )}
          <p className={s.count} role="status" data-testid="result-count">
            {countText}
          </p>
          <div className={s.headerControls}>
            {!example && (
              <Segmented
                label="Group results"
                value={params.group === 'files' ? 'files' : 'shots'}
                onChange={(v) => setParams({ ...params, group: v === 'files' ? 'files' : undefined })}
                segments={[{ id: 'shots', label: 'Shots' }, { id: 'files', label: 'Files' }]}
              />
            )}
            <Segmented
              label="View"
              value={prefs.view}
              onChange={(v) => prefs.set({ view: v })}
              segments={[
                { id: 'grid', label: 'Grid view', icon: LayoutGrid, iconOnly: true },
                { id: 'list', label: 'List view', icon: Rows3, iconOnly: true },
                { id: 'log', label: 'Log view', icon: ListVideo, iconOnly: true },
              ]}
            />
            {prefs.view === 'grid' && (
              <Segmented
                className={s.hideNarrow}
                label="Thumbnail size"
                value={prefs.thumbSize}
                onChange={(v) => prefs.set({ thumbSize: v })}
                segments={[{ id: 's', label: 'S' }, { id: 'm', label: 'M' }, { id: 'l', label: 'L' }]}
              />
            )}
            {hasQuery && (
              <Segmented
                className={s.hideNarrow}
                label="Match strictness"
                value={prefs.strictness}
                onChange={(v) => prefs.set({ strictness: v })}
                segments={[{ id: 'loose', label: 'Loose' }, { id: 'balanced', label: 'Balanced' }, { id: 'strict', label: 'Strict' }]}
              />
            )}
            {!overlay && !prefs.inspectorOpen && <IconButton icon={PanelRightOpen} label="Show inspector" shortcut={`${MOD}I`} onPress={() => prefs.set({ inspectorOpen: true })} />}
          </div>
        </div>
        {processing > 0 && !firstRun && (
          <div className={s.notice} role="status">
            <Info size={16} strokeWidth={1.75} aria-hidden="true" />
            <span className={s.noticeText}>
              <span>Results will improve as analysis finishes</span>
              <span>
                {formatNumber((stats.data?.assets ?? 0) - processing)} of {formatNumber(stats.data?.assets ?? 0)} files analysed. Shots from the rest appear automatically.
              </span>
            </span>
            {newShots > 0 && (
              <Button variant="quiet" size="sm" onPress={() => { search.refetch(); setShotsAtSearch(stats.data?.shots ?? null) }}>
                {`Show ${plural(newShots, 'new shot')}`}
              </Button>
            )}
          </div>
        )}
        {first?.notes?.map((n) => (
          <div key={n} className={`${s.notice} ${s.noticeCaution}`}>
            <TriangleAlert size={16} strokeWidth={1.75} aria-hidden="true" />
            <span className={s.noticeText}>
              <span>{n}</span>
            </span>
          </div>
        ))}
        {body}
      </main>
      {!overlay && prefs.inspectorOpen && (
        <aside aria-label="Shot details" className={s.inspector}>
          {inspector}
        </aside>
      )}
      {overlay && (
        <Sheet isOpen={Boolean(sheetUid)} onOpenChange={(o) => !o && setSheetUid(null)} side="right" label="Shot details">
          {inspector}
        </Sheet>
      )}
      {drawer && (
        <Sheet isOpen={railDrawer} onOpenChange={(o) => { setUi({ railDrawer: o }); if (!o) setStaged(null) }} side="left" label="Filters">
          <div style={{ display: 'flex', flexDirection: 'column', blockSize: '100%' }}>
            <div style={{ flex: 1, minBlockSize: 0, display: 'flex' }}>{rail}</div>
            <div className={s.drawerFooter}>
              <Button variant="primary" onPress={() => { if (staged) setParams(staged, false); setStaged(null); setUi({ railDrawer: false }) }}>
                {stagedDebounced !== undefined ? `Show ${plural(stagedDebounced, 'shot')}` : 'Show results'}
              </Button>
              <Button variant="secondary" onPress={() => setStaged({ q: params.q })}>
                Reset
              </Button>
            </div>
          </div>
        </Sheet>
      )}
      <div className={s.selection}>
        <SelectionBar
          total={total}
          loaded={results.length}
          activeName={activeName}
          onSelectAll={() => useUi.getState().setSelection(new Set(results.map((r) => r.uid)))}
          onAddToActive={() => addToActive(selected)}
          onAddTo={() => setUi({ addToDialog: selected })}
          onSimilar={() => similar(selected)}
          onRights={() => rights(selected)}
          onExport={() => exportTimeline(selected)}
          onSend={() => setUi({ sendDialog: { kind: 'shots', uids: selected } })}
        />
      </div>
    </div>
  )
}
