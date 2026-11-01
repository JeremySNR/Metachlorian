import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { Check, FolderPlus, Grid2X2, Grid3X3, Info, Search, Settings2, SlidersHorizontal, Sparkles, X } from 'lucide-react'
import { api } from '../../api/client'
import { useMe } from '../../api/queries'
import { photoRequestKey, usePhotoJobs, usePhotoSearch, usePhotoStatus, type Photo, type PhotoContext, type PhotoSession, type PhotoStatus } from '../../api/photos'
import { Button, IconButton } from '../../components/Button'
import { Dialog } from '../../components/Dialog'
import { Checkbox, TextField } from '../../components/Field'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { PhotoImage, PhotoInspector, type PhotoInspectorTab } from './PhotoInspector'
import { PhotosSetup, type PhotoSetupStep } from './PhotosSetup'
import { PhotoLibraryDetails } from './PhotoLibraryDetails'
import { PhotoEditBrief } from './PhotoEditBrief'
import { PhotoJobRow } from './PhotoJobRow'
import s from './Photos.module.css'

const editKinds = new Set(['begin', 'apply', 'finish', 'restore'])

export function PhotosPage() {
  useDocumentTitle('Photos')
  const route = useSearch({ from: '/photos' })
  const navigate = useNavigate()
  const status = usePhotoStatus()
  const me = useMe()
  const qc = useQueryClient()
  const enabled = Boolean(status.data?.enabled)
  const jobs = usePhotoJobs(enabled)
  const [draft, setDraft] = useState('')
  const [query, setQuery] = useState('')
  const [setupOpen, setSetupOpen] = useState<boolean | null>(null)
  const [setupStep, setSetupStep] = useState<PhotoSetupStep>('source')
  const [libraryDetails, setLibraryDetails] = useState(false)
  const [briefOpen, setBriefOpen] = useState(false)
  const [view, setView] = useState<'library' | 'edits' | 'activity'>('library')
  const [brief, setBrief] = useState('Natural family and travel edits, with warm skin tones and thoughtful framing')
  const [creative, setCreative] = useState(false)
  const [person, setPerson] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [filtersOpen, setFiltersOpen] = useState(false)
  const [filters, setFilters] = useState<Record<string, string | number | boolean>>({})
  const [diverse, setDiverse] = useState(true)
  const [selected, setSelected] = useState<Map<string, Photo>>(new Map())
  const [inspected, setInspected] = useState<string | null>(null)
  const [inspectorTab, setInspectorTab] = useState<PhotoInspectorTab>('overview')
  const [compare, setCompare] = useState(false)
  const [largeThumbnails, setLargeThumbnails] = useState(false)
  const [review, setReview] = useState<PhotoSession | null>(null)
  const [collection, setCollection] = useState('Family favourites')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const photoTrigger = useRef<HTMLButtonElement | null>(null)
  const requests = useRef(new Map<string, string>())
  const scrollPane = useRef<HTMLDivElement | null>(null)
  const searchForm = useRef<HTMLFormElement | null>(null)
  useEffect(() => {
    const focus = () => {
      if (document.querySelector('[role="dialog"]')) return
      setView('library')
      requestAnimationFrame(() => {
        const input = searchForm.current?.querySelector('input')
        input?.focus(); input?.select()
      })
    }
    window.addEventListener('mc:focus-search', focus)
    return () => window.removeEventListener('mc:focus-search', focus)
  }, [])
  const enqueue = async (path: string, body: Record<string, unknown> = {}) => {
    const signature = JSON.stringify([path, body])
    const key = requests.current.get(signature) ?? photoRequestKey()
    requests.current.set(signature, key)
    const result = await api.post(path, { ...body, idempotency_key: key })
    requests.current.delete(signature)
    return result
  }
  const search = usePhotoSearch(query, {
    ...(route.person_id ? { person_id: route.person_id } : {}),
    ...(route.photo_collection ? { collection: route.photo_collection } : {}), ...filters,
  }, diverse, enabled)
  const items = search.data?.pages.flatMap(page => page.results) ?? []
  const visible = compare ? [...selected.values()] : items
  const inspectedIndex = visible.findIndex(photo => photo.uid === inspected)
  const scopes = me.data?.scopes ?? []
  const canIngest = scopes.includes('ingest:write')
  const canEdit = scopes.includes('photos:edit')
  const canAdmin = scopes.includes('admin')
  const count = status.data?.coverage.total ?? 0
  const connection = status.data?.lightroom
  const showSetup = setupOpen ?? (count === 0)
  const resultCount = search.data?.pages[0]?.total ?? 0
  const visualSearch = status.data?.models.some(model => model.name === 'siglip-base-multilingual' && model.installed)
  const activeJobs = jobs.data?.jobs.filter(job => ['queued', 'running', 'waiting'].includes(job.status)).length ?? 0
  const displayedJobs = jobs.data?.jobs.filter(job => view !== 'edits' || editKinds.has(job.kind)) ?? []
  const editBlocked = !canEdit ? 'Your account needs photos:edit.' : !connection?.can_edit ? connection?.message ?? 'Connect Lightroom to prepare virtual copies.' : undefined
  const hasFilters = Boolean(query || Object.keys(filters).length || route.person_id || route.photo_collection)

  const action = async (task: () => Promise<unknown>, success: string) => {
    if (showSetup) setSetupOpen(true)
    setBusy(true); setError(''); setMessage('')
    try {
      await task()
      setMessage(success)
      await qc.invalidateQueries({ queryKey: ['photos'] })
    } catch (e) { setError((e as Error).message) }
    finally { setBusy(false) }
  }
  const openSetup = (step: PhotoSetupStep) => {
    setSetupStep(step); setSetupOpen(true); setLibraryDetails(false); setBriefOpen(false)
    setError(''); setMessage('')
  }
  const switchView = (next: typeof view) => { setView(next); scrollPane.current?.scrollTo({ top: 0 }) }
  const toggle = (photo: Photo) => setSelected(old => {
    const next = new Map(old)
    if (next.has(photo.uid)) next.delete(photo.uid)
    else if (next.size < 100) next.set(photo.uid, photo)
    return next
  })
  const clearSelection = () => { setSelected(new Map()); setCompare(false) }
  const resetSearch = () => {
    setDraft(''); setQuery(''); setPerson(''); setDateFrom(''); setDateTo(''); setFilters({}); setInspected(null)
    clearSelection()
    void navigate({ to: '/photos', search: {} })
  }
  const prepare = () => action(async () => {
    const ids = [...selected.keys()]
    const revisions: Record<string, string> = {}
    for (const uid of ids) {
      const context = await api.get<PhotoContext>(`/api/photos/${uid}/context`)
      if (context.workflow.state === 'blocked') throw new Error(context.capabilities.reason || context.workflow.reason || 'Lightroom editing is unavailable for this photo.')
      revisions[uid] = context.revision
    }
    await enqueue('/api/photos/edits', { photo_ids: ids, expected_revisions: revisions, brief, creative })
    setBriefOpen(false); switchView('edits')
  }, 'Preparing virtual copies. Ask your agent to apply the brief and review the results.')
  const checkConnection = () => void action(async () => {
    const result = await api.post<PhotoStatus>('/api/photos/connector/check')
    qc.setQueryData(['photos', 'status'], result)
    if (!result.lightroom.connected || result.lightroom.busy) throw new Error(result.lightroom.message)
    await qc.invalidateQueries({ queryKey: ['photos', 'preview'] })
  }, 'Lightroom answered. Its catalogue and version are shown in setup.')
  const reviewEdit = (session: PhotoSession) => { setReview(session); switchView('edits') }
  const setupContent = status.data ? <PhotosSetup status={status.data} step={setupStep} onStepChange={setSetupStep} embedded={count > 0} canAdmin={canAdmin} canIngest={canIngest} busy={busy} action={action} enqueue={enqueue} onCheck={checkConnection} onClose={() => setSetupOpen(false)} /> : null
  const feedback = <>{error ? <div role="alert" className={s.feedback}><span>{error}</span><IconButton icon={X} label="Dismiss error" onPress={() => setError('')} /></div> : message ? <div role="status" className={s.feedback}><span>{message}</span><IconButton icon={X} label="Dismiss notification" onPress={() => setMessage('')} /></div> : null}</>

  return <main className={s.page} id="main">
    <div className={s.libraryPane}>
      <header className={s.libraryHeader}>
        <div className={s.row}><h1>Photos</h1>{enabled ? <span className={s.muted}>{count.toLocaleString()} in your library</span> : null}</div>
        {enabled ? <div className={s.actions}><Button size="sm" icon={FolderPlus} onPress={() => openSetup('source')}>Add photos</Button><Button size="sm" variant="quiet" icon={Settings2} onPress={() => openSetup('connect')}>Setup & agent</Button></div> : null}
      </header>
      {enabled ? <>
        <section className={s.connectionSummary} aria-label="Lightroom connection" data-ready={connection?.can_edit || undefined}>
          <button onClick={() => openSetup('connect')} className={s.connectionButton}><span className={s.statusDot} />{connection?.busy ? 'Lightroom is working' : connection?.can_edit ? 'Lightroom ready' : connection?.connected ? 'Lightroom needs attention' : 'Connect Lightroom to edit'}</button>
          <Button size="sm" variant="quiet" icon={Info} onPress={() => { setLibraryDetails(true); setError(''); setMessage('') }}>{status.data?.coverage.needs_attention ? `${status.data.coverage.needs_attention} previews need attention` : visualSearch ? 'Visual search available' : 'Metadata search'} · Library details</Button>
        </section>
        <nav className={`${s.views} ${s.libraryNavigation}`} aria-label="Photo views">
          <button aria-pressed={view === 'library'} onClick={() => switchView('library')}>Library</button>
          <button aria-pressed={view === 'edits'} onClick={() => switchView('edits')}>Edits</button>
          <button aria-pressed={view === 'activity'} onClick={() => switchView('activity')}>Activity {activeJobs ? <span>{activeJobs}</span> : null}</button>
        </nav>
      </> : null}
      <div className={s.inner} ref={scrollPane} data-testid="photo-library-scroll">
        {status.error ? <p role="alert">{status.error.message}</p> : null}
        {status.isPending ? <p role="status">Loading your photo library…</p> : null}
        {status.data && !enabled ? <section className={s.panel}><h2>Bring your photographs into view.</h2><p>Browse a folder or connect Lightroom Classic, compare your favourites, and give your agent a brief for the edit. Originals stay where they are.</p><Button variant="primary" isDisabled={!canAdmin || busy} busy={busy} onPress={() => void action(() => api.put('/api/admin/settings', { photos_enabled: true }), 'Photos enabled.')}>Enable Photos</Button></section> : null}
        {enabled && count === 0 && showSetup ? setupContent : null}
        {enabled && view === 'library' && (count > 0 || !showSetup) ? <>
          <form ref={searchForm} className={s.search} role="search" aria-label="Search photographs" onSubmit={event => {
            event.preventDefault(); setQuery(draft)
            setFilters({ ...(person.trim() ? { person: person.trim() } : {}), ...(dateFrom ? { date_from: dateFrom } : {}), ...(dateTo ? { date_to: `${dateTo}T23:59:59` } : {}) })
            clearSelection(); setInspected(null)
          }}>
            <div className={s.searchMain}><TextField label="Find photographs" value={draft} onChange={setDraft} placeholder={visualSearch ? 'Family at the beach, portraits in evening light…' : 'Search filenames, keywords or camera details…'} /><Button type="submit" variant="primary" icon={Search}>Find photos</Button></div>
            <div className={s.browseToolbar}>
              <div className={s.row}><Button size="sm" variant="quiet" icon={SlidersHorizontal} aria-expanded={filtersOpen} onPress={() => setFiltersOpen(!filtersOpen)}>Filters{Object.keys(filters).length ? ` (${Object.keys(filters).length})` : ''}</Button><Checkbox isSelected={diverse} onChange={setDiverse}>Show different moments</Checkbox>{hasFilters ? <Button size="sm" variant="quiet" onPress={resetSearch}>Clear search & filters</Button> : null}</div>
              <div className={s.row}><span className={s.muted}>{compare ? `${selected.size} comparing` : `${resultCount.toLocaleString()} ${resultCount === 1 ? 'result' : 'results'}`}</span><IconButton icon={Grid3X3} label="Small thumbnails" aria-pressed={!largeThumbnails} onPress={() => setLargeThumbnails(false)} /><IconButton icon={Grid2X2} label="Large thumbnails" aria-pressed={largeThumbnails} onPress={() => setLargeThumbnails(true)} /></div>
            </div>
            {filtersOpen ? <div className={s.filters}><TextField label="Person" value={person} onChange={setPerson} placeholder="A name you’ve added" /><label>From<input type="date" value={dateFrom} onChange={e => setDateFrom(e.target.value)} /></label><label>To<input type="date" value={dateTo} onChange={e => setDateTo(e.target.value)} /></label><Button type="submit" size="sm">Apply filters</Button></div> : null}
          </form>
          {route.person_id || route.photo_collection ? <p className={s.filterNote}>Showing {route.person_id ? 'one person' : `collection “${route.photo_collection}”`}. <button onClick={() => void navigate({ to: '/photos', search: {} })}>Show all photos</button></p> : null}
          {filters.burst_id ? <p className={s.filterNote}>Showing this burst. <button onClick={() => { setFilters({}); setDiverse(true) }}>Show all moments</button></p> : null}
          {search.error ? <p role="alert">{search.error.message}</p> : null}
          {search.isPending ? <p role="status">Finding photographs…</p> : null}
          {search.data?.pages[0]?.semantic_available === false && query ? <p className={s.muted}>Results match metadata. Open Library details to enable searching image content.</p> : null}
          {compare ? <strong>Compare your selection</strong> : null}
          {!search.isPending && !visible.length ? <section className={s.empty}><h2>{count ? 'No matching photographs' : 'Add your first photographs'}</h2><p>{count ? 'Try fewer filters or a broader search.' : 'Choose a folder or your Lightroom catalogue. Your originals stay in place.'}</p><Button onPress={() => count ? resetSearch() : openSetup('source')}>{count ? 'Reset search' : 'Choose photo source'}</Button></section> : null}
          <div className={compare ? s.comparisonGrid : s.grid} data-size={largeThumbnails ? 'large' : 'small'}>
            {visible.map(photo => <article className={s.card} data-selected={selected.has(photo.uid) || undefined} data-inspected={inspected === photo.uid || undefined} key={photo.uid}>
              <button className={s.imageButton} onClick={event => { photoTrigger.current = event.currentTarget; setInspected(photo.uid) }} aria-label={`Inspect ${photo.filename}`}><PhotoImage key={`${photo.uid}-${photo.revision}`} uid={photo.uid} label={photo.filename} edge={compare || largeThumbnails ? 1600 : 600} retry={false} /></button>
              <div className={s.cardInfo}><Checkbox isSelected={selected.has(photo.uid)} onChange={() => toggle(photo)} aria-label={`Select ${photo.filename}`} /><div><strong>{photo.filename}</strong><span>{photo.copy_name || photo.capture_time?.slice(0, 10) || 'Date unknown'}</span></div>{photo.is_virtual || photo.availability !== 'original' ? <span className={s.badge}>{photo.is_virtual ? 'Virtual copy' : photo.availability.replaceAll('_', ' ')}</span> : null}</div>
            </article>)}
          </div>
          {search.hasNextPage && !compare ? <Button isDisabled={search.isFetchingNextPage} onPress={() => void search.fetchNextPage()}>Load more photographs</Button> : null}
        </> : null}
        {enabled && view === 'edits' && review ? <section className={s.panel} aria-label="Review Lightroom edit">
          <div className={s.row}><h2 className={s.grow}>Review this copy</h2><IconButton icon={X} label="Close edit review" onPress={() => setReview(null)} /></div>
          <div className={s.comparisonGrid}>{review.source_photo_id ? <figure><PhotoImage uid={review.source_photo_id} label="Source photograph" edge={1600} /><figcaption>Source photograph</figcaption></figure> : null}<figure><PhotoImage key={`${review.photo_id}-${review.revision}`} uid={review.photo_id} revision={review.revision} label="Rendered Lightroom edit" edge={1600} /><figcaption>Rendered virtual copy</figcaption></figure></div>
          <p className={s.muted}>Check skin colour, detail and framing before saving. If the copy has changed, open the latest edit from the list below.</p>
          <TextField label="Lightroom collection" value={collection} onChange={setCollection} />
          <Button icon={Check} variant="primary" isDisabled={Boolean(editBlocked) || !scopes.includes('collections:write') || !collection.trim() || busy} disabledReason={editBlocked || (!scopes.includes('collections:write') ? 'Your account needs collections:write to save a collection.' : undefined)} onPress={() => void action(async () => {
            await enqueue('/api/photos/edits/finish', { selections: [{ session_id: review.session_id, reviewed_revision: review.revision }], collection }); setReview(null)
          }, 'Saving the reviewed copy to Lightroom.')}>Save reviewed copy</Button>
        </section> : null}
        {enabled && view !== 'library' ? <section className={s.panel}>
          <div><h2>{view === 'edits' ? 'Your Lightroom edits' : 'Library activity'}</h2><p className={s.muted}>{view === 'edits' ? 'Prepared copies and edits made through Metachlorian. Open a copy to review its Lightroom rendition.' : 'Follow indexing, analysis, model downloads and editing jobs.'}</p></div>
          {jobs.error ? <p role="alert">{jobs.error.message}</p> : null}
          {!displayedJobs.length ? <div className={s.empty}><h3>{view === 'edits' ? 'Start with a few favourites' : 'No activity yet'}</h3><p>{view === 'edits' ? 'Select photographs in the Library, create an edit brief and give it to your connected agent.' : 'Jobs appear here when you add photos or ask your agent to edit.'}</p><Button onPress={() => switchView('library')}>Browse photos</Button></div> : null}
          {displayedJobs.map(job => <PhotoJobRow key={job.uid} job={job} canManage={job.kind === 'models' ? canAdmin : editKinds.has(job.kind) ? canEdit : canIngest} onReview={reviewEdit} onAction={command => void action(() => api.post(`/api/photos/jobs/${job.uid}/${command}`), command === 'resume' ? 'Job resumed.' : 'Stopping at the next safe point.')} />)}
        </section> : null}
      </div>
      {selected.size && view === 'library' ? <section className={s.selectionBar} aria-label="Selected photographs">
        <div className={s.row}><strong>{selected.size} selected</strong><Button size="sm" isDisabled={selected.size < 2 || selected.size > 4} disabledReason={selected.size < 2 || selected.size > 4 ? 'Select two to four photographs to compare.' : undefined} onPress={() => { setCompare(!compare); setInspected(null); scrollPane.current?.scrollTo({ top: 0 }) }}>{compare ? 'Back to library' : 'Compare'}</Button></div>
        <div className={s.actions}><Button size="sm" variant="primary" icon={Sparkles} onPress={() => { setBriefOpen(true); setError(''); setMessage('') }}>Create edit brief</Button><IconButton icon={X} label="Clear selection" onPress={clearSelection} /></div>
      </section> : null}
      {!briefOpen && !libraryDetails && !(showSetup && count > 0) ? feedback : null}
    </div>
    {inspected && inspectedIndex >= 0 && view === 'library' ? <PhotoInspector key={inspected} uid={inspected} tab={inspectorTab} onTabChange={setInspectorTab} position={`${inspectedIndex + 1} of ${visible.length} ${compare ? 'selected' : 'loaded'} photos`} onPrevious={inspectedIndex > 0 ? () => setInspected(visible[inspectedIndex - 1].uid) : undefined} onNext={inspectedIndex < visible.length - 1 ? () => setInspected(visible[inspectedIndex + 1].uid) : undefined} canName={scopes.includes('tags:write') && me.data?.role !== 'agent'} onClose={() => { setInspected(null); photoTrigger.current?.focus() }} onBurst={id => { setFilters({ burst_id: id }); setDiverse(false); setInspected(null); setQuery(''); setCompare(false); clearSelection() }} /> : null}
    <Dialog isOpen={enabled && count > 0 && showSetup} onOpenChange={setSetupOpen} title="Photo setup" size="l">{setupContent}{feedback}</Dialog>
    <Dialog isOpen={libraryDetails} onOpenChange={setLibraryDetails} title="Library details" size="m">{status.data ? <PhotoLibraryDetails status={status.data} canIngest={canIngest} canAdmin={canAdmin} busy={busy} downloading={Boolean(jobs.data?.jobs.some(job => job.kind === 'models' && ['queued', 'running'].includes(job.status)))} onAnalyse={() => void action(() => enqueue('/api/photos/analyse'), 'Image analysis queued. Follow progress in Activity.')} onModels={() => void action(() => enqueue('/api/photos/models/install'), 'Photo models queued. Follow progress in Activity.')} /> : null}{feedback}</Dialog>
    <Dialog isOpen={briefOpen} onOpenChange={setBriefOpen} title="Create an edit brief" size="m"><PhotoEditBrief photos={[...selected.values()]} brief={brief} onBrief={setBrief} creative={creative} onCreative={setCreative} editBlocked={editBlocked} busy={busy} error={error} onPrepare={() => void prepare()} onSetup={() => openSetup('agent')} /></Dialog>
  </main>
}
