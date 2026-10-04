import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearch as useRouteSearch } from '@tanstack/react-router'
import { useQueries, useQuery } from '@tanstack/react-query'
import { CircleAlert, FolderPlus, Info, LayoutGrid, ListVideo, PanelLeftOpen, PanelRightOpen, Rows3, SearchX, SlidersHorizontal, TriangleAlert } from 'lucide-react'
import type { PersonRef, SearchRequest, SearchResponse, SearchResult, Strictness } from '../../api/types'
import { api, ApiError } from '../../api/client'
import {
  buildPackage, PAGE_SIZE, searchByExample, useAddToCollection, useCollections, useCreateCollection, useLibraryStats, useNamedPeople, useSearch, useShot, useVocabularies,
} from '../../api/queries'
import { Button, IconButton } from '../../components/Button'
import { Sheet } from '../../components/Dialog'
import { EmptyState } from '../../components/EmptyState'
import { Segmented } from '../../components/Segmented'
import { toast } from '../../components/Toast'
import { isDrawerRail, isOverlayInspector, useTier } from '../../hooks/useMediaQuery'
import { isMod, isTyping, useDocumentKeys } from '../../hooks/useHotkeys'
import { useDebounced } from '../../hooks/useDebounced'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { activeFilterCount, buildPhraseIndex, chipsFromQuery, removeChip, type QueryChip, type SearchState } from '../../lib/chips'
import { MOD } from '../../lib/bridge'
import { noStrongMatches, strongDivider } from '../../lib/gridLayout'
import { formatNumber, plural } from '../../lib/format'
import { isPersonNote, onlyNames, personLabel, personPhrases, PERSON_VOCAB } from '../../lib/people'
import { stateFromBadge, stateFromVerdict } from '../../lib/rights'
import { usePrefs, useUi, type ResultsView, type ThumbSize } from '../../lib/store'
import { Inspector } from '../shot/Inspector'
import { ChipRow, type ExtraChip } from './ChipRow'
import { FilterRail } from './FilterRail'
import { FilesView } from './FilesView'
import { ResultsGrid } from './ResultsGrid'
import { SelectionBar } from './SelectionBar'
import { fromState, showsBlocked, similarRightsOf, strictnessOf, toRequest, toState, withBlocked, type SearchParams } from './searchParams'
import s from './SearchPage.module.css'

const STRICT_LABEL: Record<Strictness, string> = { loose: 'loose', balanced: 'balanced', strict: 'strict' }

/** Error copy that fits the failure (§3.16): offline, unreachable, server error, or the core's own message. */
export function searchErrorText(err: unknown): string {
  if (err instanceof ApiError) {
    if (err.status === 0) return err.detail
    if (err.status >= 500) return `The search service hit an error (HTTP ${err.status}). Try again; if it keeps failing, check the core's log.`
    return err.detail || `The search was refused (HTTP ${err.status}).`
  }
  return "The search didn't complete."
}

/** A chip's value as it reads mid-sentence ("Removing night…"); names keep their capitals. */
const chipWord = (c: QueryChip) => (c.kind === 'person' ? c.label : c.label.toLowerCase())

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
  const strictness = strictnessOf(params)

  // Query by example follows the rights filters too: re-run it when they change.
  const rightsKey = JSON.stringify(similarRightsOf(params))
  const exampleFile = example?.file
  useEffect(() => {
    const ex = useUi.getState().example
    if (!ex?.file || ex.rightsKey === rightsKey) return
    let live = true
    searchByExample(ex.file, 120, JSON.parse(rightsKey))
      .then((response) => {
        if (live && useUi.getState().example?.file === ex.file) useUi.getState().set({ example: { ...ex, response, rightsKey } })
      })
      .catch((e) => toast({ title: "Couldn't refresh the example search", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' }))
    return () => {
      live = false
    }
  }, [rightsKey, exampleFile])
  const pages = useMemo(() => search.data?.pages ?? [], [search.data])
  const first: SearchResponse | undefined = example ? example.response : pages[0]
  const results = useMemo(() => (example ? example.response.results : pages.flatMap((p) => p.results)), [example, pages])
  const total = example ? results.length : (first?.total ?? 0)
  const state = toState(params)

  // People (face identity): PERSON chips name the identities the core filtered by, from named people and the results.
  const namedPeople = useNamedPeople()
  const peopleById = useMemo(() => {
    const m = new Map<number, PersonRef>()
    for (const r of results) if (Array.isArray(r.people)) for (const p of r.people) m.set(p.id, p)
    for (const p of namedPeople.data?.people ?? []) m.set(p.id, p)
    return m
  }, [results, namedPeople.data])
  const personPhraseList = useMemo(() => personPhrases(namedPeople.data?.people ?? []), [namedPeople.data])
  const chipLabel = useCallback((vocab: string, term: string) => (vocab === PERSON_VOCAB ? personLabel(term, peopleById) : label(vocab, term)), [label, peopleById])
  const personChips = (first?.query.require?.[PERSON_VOCAB]?.length ?? 0) > 0

  const stats = useLibraryStats({ refetchInterval: 10_000 })
  const processing = stats.data?.status?.processing ?? 0
  const [seen, setSeen] = useState<{ at: number; shots: number | null }>({ at: 0, shots: null })
  if (search.isSuccess && stats.data && seen.at !== search.dataUpdatedAt) setSeen({ at: search.dataUpdatedAt, shots: stats.data.shots })
  const shotsAtSearch = seen.shots
  const setShotsAtSearch = (n: number | null) => setSeen({ at: search.dataUpdatedAt, shots: n })
  const newShots = stats.data && shotsAtSearch !== null ? stats.data.shots - shotsAtSearch : 0

  const lastNext = example ? null : (pages[pages.length - 1]?.next_cursor ?? null)
  useEffect(() => {
    if (results.length) useUi.getState().rememberResults(results, params.q ?? '', total, example ? null : { req: { ...req, limit: PAGE_SIZE, facets: false }, next: lastNext })
  }, [results, params.q, total, req, lastNext, example])

  const setParams = useCallback((p: SearchParams, replace = true) => navigate({ search: p, replace }), [navigate])
  const setState = (st: SearchState) => setParams(fromState(st, params), false)

  const hasQuery = Boolean(params.q?.trim() || params.similar || example)
  // The core orders strong matches first; the divider sits after the first strong_count of the whole list.
  // A query that is only known names is a person filter (the core doesn't score it): no strong/weak split.
  const personNames = (first?.query.require?.[PERSON_VOCAB] ?? []).map((id) => personLabel(id, peopleById))
  const nameOnly = !example && onlyNames(params.q ?? '', personNames)
  const strength = first && !nameOnly ? { total, strong_count: first.strong_count, strictness: first.strictness } : null
  const split = strongDivider(strength)
  const noStrong = !search.isError && noStrongMatches(strength)
  const scored = Boolean(first?.strictness) && !nameOnly

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

  // Select all: every result of the query, paging through next_cursor (not just the loaded page).
  const [selectingAll, setSelectingAll] = useState(false)
  const selectAll = async () => {
    if (example || results.length >= total) {
      useUi.getState().setSelection(new Set(results.map((r) => r.uid)))
      return
    }
    setSelectingAll(true)
    try {
      const uids = results.map((r) => r.uid)
      let cursor = lastNext
      let guard = 0
      while (cursor && guard++ < 40) {
        const page = await api.post<SearchResponse>('/api/search', { ...req, cursor, limit: 500, facets: false })
        for (const r of page.results) {
          uids.push(r.uid)
          useUi.getState().resultCache.set(r.uid, r)
        }
        cursor = page.next_cursor
      }
      useUi.getState().setSelection(new Set(uids))
    } catch (e) {
      toast({ title: "Couldn't select every result", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    } finally {
      setSelectingAll(false)
    }
  }
  const openSend = () => setUi({ sendDialog: { kind: 'shots', uids: [...useUi.getState().selection], use: state.use ?? null } })

  useDocumentKeys((e) => {
    if (isTyping(e.target)) return
    if (isMod(e) && e.key.toLowerCase() === 'e' && selection.size) {
      e.preventDefault()
      if (e.shiftKey) openSend()
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
  const index = useMemo(() => [...buildPhraseIndex(vocabs), ...personPhraseList].sort((a, b) => b.phrase.length - a.phrase.length), [vocabs, personPhraseList])
  const noResults = search.isSuccess && !example && total === 0
  const wantSuggestions = (noResults || noStrong) && !example
  const chips = useMemo(() => (wantSuggestions && first ? chipsFromQuery(first.query, state, chipLabel, index).slice(0, 4) : []), [wantSuggestions, first, state, chipLabel, index])
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
  const hiddenByRights = first?.excluded_by_rights ?? 0
  const strongText = scored && typeof first?.strong_count === 'number' ? `${formatNumber(first.strong_count)} strong (${STRICT_LABEL[strictness]})` : null
  const rightsText = hiddenByRights > 0 ? `${plural(hiddenByRights, 'shot')} hidden by rights` : null
  const countText =
    search.isError && !first
      ? ''
      : example
        ? [`${plural(total, 'similar shot')} to ${example.name}`, strongText, rightsText].filter(Boolean).join(' · ')
        : search.isLoading && !first
          ? 'Searching…'
          : [`${plural(total, 'shot')}${total && results.length >= total ? ` in ${plural(files, 'file')}` : ''}`, strongText, rightsText, secs ? `${secs} s` : null].filter(Boolean).join(' · ')
  useDocumentTitle(params.q ? `“${params.q}”` : example ? `Similar to ${example.name}` : params.similar ? 'Similar shots' : null, 'Search')

  const rail = (
    <FilterRail
      params={staged ?? params}
      facets={first?.facets ?? {}}
      excludedByRights={first?.excluded_by_rights ?? 0}
      vocabs={vocabs}
      label={label}
      onChange={(p) => (drawer ? setStaged(p) : setParams(p, false))}
      onCollapse={drawer ? undefined : () => prefs.set({ railOpen: false })}
      onClose={drawer ? () => { setUi({ railDrawer: false }); setStaged(null) } : undefined}
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
        <p>{searchErrorText(err)}</p>
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
                {`Remove ${chipWord(c)} (${formatNumber(n ?? 0)})`}
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
                {i ? ' ' : ''}Removing <strong>{chipWord(c)}</strong> would show {plural(n ?? 0, 'shot')}.
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
    const sugg = chips
      .map((c, i) => ({ c, n: noStrong ? suggestions[i]?.data?.strong_count : suggestions[i]?.data?.total }))
      .filter((x) => x.n)
      .sort((a, b) => (b.n ?? 0) - (a.n ?? 0))
    const noStrongNotice = noStrong ? (
      <div className={s.noStrong} role="status" data-testid="no-strong-matches">
        <SearchX size={20} strokeWidth={1.75} aria-hidden="true" className={s.noStrongIcon} />
        <div className={s.noStrongBody}>
          <h2>{params.q ? `No strong matches for “${params.q}”` : 'No strong matches'}</h2>
          <p>
            {sugg.length
              ? sugg.slice(0, 2).map(({ c, n }, i) => (
                  <span key={c.key}>
                    {i ? ' ' : ''}Removing <strong>{chipWord(c)}</strong> would give {plural(n ?? 0, 'strong match', 'strong matches')}.
                  </span>
                ))
              : `Nothing clears the ${STRICT_LABEL[strictness]} threshold. The ${plural(total, 'weaker match', 'weaker matches')} below may still be useful.`}
          </p>
          <div className={s.noStrongActions}>
            {sugg.map(({ c, n }) => (
              <Button key={c.key} variant="secondary" size="sm" onPress={() => { const next = removeChip(state, c, index); if (next) setState(next) }}>
                {`Remove ${chipWord(c)} (${formatNumber(n ?? 0)})`}
              </Button>
            ))}
            {strictness !== 'loose' && (
              <Button variant="quiet" size="sm" onPress={() => setParams({ ...params, strict: 'loose' })}>
                Match loosely
              </Button>
            )}
          </div>
        </div>
      </div>
    ) : null
    body = (
      <>
      {noStrongNotice}
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
        onSelectAll={selectAll}
      />
      </>
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
        <h1 className="visually-hidden">{params.q ? `Search results for ${params.q}` : example ? `Shots similar to ${example.name}` : 'Search'}</h1>
        <ChipRow
          query={first?.query}
          state={state}
          vocabs={vocabs}
          label={chipLabel}
          onChange={setState}
          extra={extra}
          phrases={personPhraseList}
          onOpenPerson={(id) => navigate({ to: '/people/$personId', params: { personId: id } })}
        />
        <div className={s.header}>
          {drawer && (
            <Button variant="secondary" size="sm" icon={SlidersHorizontal} onPress={() => { setStaged(params); setUi({ railDrawer: true }) }}>
              {active ? `Filters · ${active}` : 'Filters'}
            </Button>
          )}
          <p className={s.count} role="status" data-testid="result-count">
            {countText}
          </p>
          {(first?.hidden_blocked ?? 0) > 0 && !showsBlocked(params) && (
            <Button variant="quiet" size="sm" className={s.hideNarrow} onPress={() => setParams(withBlocked(params, true), false)}>
              {`Show ${plural(first?.hidden_blocked ?? 0, 'blocked shot')}`}
            </Button>
          )}
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
                value={strictness}
                onChange={(v) => setParams({ ...params, strict: v === 'balanced' ? undefined : v })}
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
        {/* The person filter note is the PERSON chip above; other notes are cautions. */}
        {first?.notes?.filter((n) => !(personChips && isPersonNote(n))).map((n) => (
          <div key={n} className={`${s.notice} ${isPersonNote(n) ? '' : s.noticeCaution}`}>
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
          selectingAll={selectingAll}
          activeName={activeName}
          onSelectAll={selectAll}
          onAddToActive={() => addToActive(selected)}
          onAddTo={() => setUi({ addToDialog: selected })}
          onSimilar={() => similar(selected)}
          onRights={() => rights(selected)}
          onExport={() => exportTimeline(selected)}
          onSend={openSend}
        />
      </div>
    </div>
  )
}
