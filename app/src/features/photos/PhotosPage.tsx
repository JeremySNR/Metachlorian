import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { Check, Copy, Download, RefreshCw, Search, Settings2, X } from 'lucide-react'
import { api } from '../../api/client'
import { useMe } from '../../api/queries'
import { photoRequestKey, usePhotoJobs, usePhotoSearch, usePhotoStatus, type PhotoContext, type PhotoJob, type PhotoSession, type PhotoStatus } from '../../api/photos'
import { Button, IconButton } from '../../components/Button'
import { Checkbox, TextField } from '../../components/Field'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { PhotoImage, PhotoInspector } from './PhotoInspector'
import { PhotosSetup } from './PhotosSetup'
import s from './Photos.module.css'

const bytes = (n: number) => `${(n / 1024 ** 2).toFixed(1)} MiB`
const labels: Record<string, string> = { folder: 'Folder indexing', catalog: 'Lightroom catalogue', analyse: 'Image understanding', begin: 'Prepare virtual copies', apply: 'Render edit', finish: 'Save selection', restore: 'Restore candidate', models: 'Download photo models' }

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
  const [view, setView] = useState<'library' | 'activity'>('library')
  const [brief, setBrief] = useState('Natural family and travel edits, with warm skin tones and thoughtful framing')
  const [creative, setCreative] = useState(false)
  const [person, setPerson] = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [filters, setFilters] = useState<Record<string, string | number | boolean>>({})
  const [diverse, setDiverse] = useState(true)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [inspected, setInspected] = useState<string | null>(null)
  const [compare, setCompare] = useState(false)
  const [review, setReview] = useState<PhotoSession | null>(null)
  const [collection, setCollection] = useState('Family favourites')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [error, setError] = useState('')
  const requests = useRef(new Map<string, string>())
  const enqueue = async (path: string, body: Record<string, unknown> = {}) => {
    const signature = JSON.stringify([path, body])
    const key = requests.current.get(signature) ?? photoRequestKey()
    requests.current.set(signature, key)
    const result = await api.post(path, { ...body, idempotency_key: key })
    requests.current.delete(signature)
    return result
  }
  const search = usePhotoSearch(query, { ...(route.person_id ? { person_id: route.person_id } : {}), ...(route.photo_collection ? { collection: route.photo_collection } : {}), ...filters }, diverse, enabled)
  const items = search.data?.pages.flatMap((page) => page.results) ?? []
  const scopes = me.data?.scopes ?? []
  const canIngest = scopes.includes('ingest:write')
  const canEdit = scopes.includes('photos:edit')
  const canAdmin = scopes.includes('admin')
  const count = status.data?.coverage.total ?? 0
  const connection = status.data?.lightroom
  const showSetup = setupOpen ?? (count === 0 || !connection?.connected)
  const activeJobs = jobs.data?.jobs.filter((job) => ['queued', 'running', 'waiting'].includes(job.status)).length ?? 0
  const editBlocked = !canEdit ? 'Your account needs photos:edit.' : !connection?.can_edit ? connection?.message ?? 'Connect Lightroom to prepare virtual copies.' : undefined

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
  const toggle = (uid: string) => setSelected((old) => {
    const next = new Set(old)
    if (next.has(uid)) next.delete(uid)
    else if (next.size < 100) next.add(uid)
    return next
  })
  const prepare = () => action(async () => {
    const ids = [...selected]
    // Lightroom serialises context reads. Sequential batches avoid flooding
    // the local connector when a large selection is prepared.
    const revisions: Record<string, string> = {}
    for (const uid of ids) {
      const context = await api.get<PhotoContext>(`/api/photos/${uid}/context`)
      if (context.workflow.state === 'blocked') throw new Error(context.capabilities.reason || context.workflow.reason || 'Lightroom editing is unavailable for this photo.')
      revisions[uid] = context.revision
    }
    await enqueue('/api/photos/edits', { photo_ids: ids, expected_revisions: revisions, brief, creative })
    setView('activity')
  }, 'Preparing virtual copies. Your agent can now use the saved brief to edit them. Preparing copies does not apply a look.')
  const checkConnection = () => void action(async () => {
    const result = await api.post<PhotoStatus>('/api/photos/connector/check')
    qc.setQueryData(['photos', 'status'], result)
    if (!result.lightroom.connected || result.lightroom.busy) throw new Error(result.lightroom.message)
    await qc.invalidateQueries({ queryKey: ['photos', 'preview'] })
  }, 'Lightroom answered. Connection details are shown above.')

  return <main className={s.page} id="main">
    <div className={s.inner}>
      <header className={s.header}><div><p className={s.eyebrow}>YOUR LIBRARY, IN PLACE</p><h1>Photos</h1><p className={s.muted}>Find the moment. Give it the edit it deserves.</p></div>{enabled ? <Button icon={Settings2} onPress={() => setSetupOpen(!showSetup)}>{showSetup ? 'Hide setup' : 'Photo setup'}</Button> : null}</header>
      {status.error ? <p role="alert">{status.error.message}</p> : null}
      {status.isPending ? <p role="status">Loading your photo library…</p> : null}
      {status.data && !enabled ? <section className={s.panel}>
        <h2>Your photo library, in place.</h2><p>Connect a Lightroom Classic catalogue or add a folder. Originals stay where they are. Temporary previews have a storage limit, and edits are saved as virtual copies.</p>
        <p className={s.muted}>Bring your own agent, such as Codex. Metachlorian helps it find, inspect and edit photos through Lightroom Classic. Start with the guided setup below.</p>
        <Button variant="primary" isDisabled={!canAdmin || busy} busy={busy} onPress={() => void action(() => api.put('/api/admin/settings', { photos_enabled: true }), 'Photos enabled.')}>Enable Photos</Button>
      </section> : null}
      {enabled ? <>
        <section className={s.connection} aria-label="Lightroom connection" data-ready={connection?.can_edit || undefined}>
          <div className={s.grow}><div className={s.row}><span className={s.statusDot} /><strong>{connection?.label}</strong>{connection?.connected ? <span className={s.badge}>Classic {connection.catalog?.version} · {connection.catalog?.name}</span> : null}</div><p>{connection?.message}</p>{connection?.checked_at ? <span className={s.muted}>Last checked {new Date(connection.checked_at * 1000).toLocaleTimeString()}</span> : null}</div>
          <div className={s.actions}><Button icon={RefreshCw} size="sm" busy={busy} isDisabled={busy} onPress={checkConnection}>Check connection</Button>{!showSetup ? <Button size="sm" onPress={() => setSetupOpen(true)}>{connection?.can_edit ? 'Agent & sources' : 'Finish setup'}</Button> : null}</div>
        </section>
        {showSetup && status.data ? <PhotosSetup status={status.data} canAdmin={canAdmin} canIngest={canIngest} busy={busy} action={action} enqueue={enqueue} onCheck={checkConnection} onClose={() => setSetupOpen(false)} /> : null}
        <div className={s.libraryBar}><nav className={s.views} aria-label="Photo views"><button aria-pressed={view === 'library'} onClick={() => setView('library')}>Library <span>{count.toLocaleString()}</span></button><button aria-pressed={view === 'activity'} onClick={() => setView('activity')}>Activity {activeJobs ? <span>{activeJobs}</span> : null}</button></nav><span className={s.muted}>{status.data?.coverage.analysed.toLocaleString()} analysed · {bytes(status.data?.cache.bytes ?? 0)} / {bytes(status.data?.cache.budget_bytes ?? 0)} preview cache</span></div>
        {view === 'library' ? <>
        {status.data?.coverage.needs_attention ? <section className={s.modelNotice}><div className={s.grow}><h2>{status.data.coverage.needs_attention.toLocaleString()} photos need a preview</h2><p>Analysis could not read these images. Connect Lightroom or reconnect their originals, then retry. Open a photograph to see its preview error.</p></div><Button size="sm" isDisabled={!canIngest || busy} onPress={() => void action(() => enqueue('/api/photos/analyse'), 'Image analysis queued. Follow progress in Activity.')}>Retry photo analysis</Button></section> : null}
        {canAdmin && status.data?.models.some((m) => m.name !== 'face-landmarker' && !m.installed) ? <section className={s.modelNotice}><div className={s.grow}><h2>Add visual search</h2><p>Find subjects and moments by what is in the image. Local models are shared with your video library; downloads use separate storage.</p></div><Button icon={Download} size="sm" isDisabled={busy || jobs.data?.jobs.some((j) => j.kind === 'models' && ['queued', 'running'].includes(j.status))} onPress={() => void action(() => enqueue('/api/photos/models/install'), 'Photo models queued for download. Follow progress in Activity.')}>Install photo models ({Math.round(status.data.models.filter((m) => m.name !== 'face-landmarker' && !m.installed).reduce((sum, m) => sum + m.size_mb, 0))} MB)</Button></section> : null}
        <form className={s.search} onSubmit={(event) => { event.preventDefault(); setQuery(draft); setFilters({ ...(person.trim() ? { person: person.trim() } : {}), ...(dateFrom ? { date_from: dateFrom } : {}), ...(dateTo ? { date_to: `${dateTo}T23:59:59` } : {}) }); setSelected(new Set()); setCompare(false); setInspected(null) }}>
          <div className={s.searchMain}><TextField label="Find photographs" value={draft} onChange={setDraft} placeholder="Family at the beach, quiet moments, portraits in evening light…" /><Button type="submit" variant="primary" icon={Search}>Find photos</Button></div>
          <details className={s.advanced}><summary>Refine by person or date</summary><div className={s.filters}><TextField label="Person" value={person} onChange={setPerson} placeholder="A name you’ve added" /><label>From<input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></label><label>To<input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></label></div></details>
        </form>
        <div className={s.row}><Checkbox isSelected={diverse} onChange={setDiverse}>Show different moments</Checkbox><span className={s.muted}>{search.data?.pages[0]?.total.toLocaleString() ?? 0} results</span>
          {route.person_id || route.photo_collection ? <Button size="sm" onPress={() => void navigate({ to: '/photos', search: {} })}>Clear {route.person_id ? 'person' : 'collection'} filter</Button> : null}
          {filters.burst_id ? <Button size="sm" onPress={() => setFilters({})}>Leave burst comparison</Button> : null}
          {selected.size ? <><span>{selected.size} selected</span><Button size="sm" isDisabled={selected.size > 4} onPress={() => setCompare(!compare)}>{compare ? 'Show library' : 'Compare up to four'}</Button><Button size="sm" onPress={() => { setSelected(new Set()); setCompare(false); setInspected(null) }}>Clear selection</Button></> : null}
        </div>
        {selected.size ? <section className={s.selection} aria-label="Selected photographs"><div className={s.grow}><TextField label="Edit brief" value={brief} onChange={setBrief} /><p className={s.muted}>Ask your agent to edit these photos, or prepare virtual copies for it to work on. Originals stay untouched.</p><Checkbox isSelected={creative} onChange={setCreative}>Allow a creative look and bolder framing</Checkbox></div><div className={s.actions}><Button size="sm" icon={Copy} onPress={() => void action(() => navigator.clipboard.writeText(`Use Metachlorian photo IDs ${[...selected].join(', ')}. ${brief}. ${creative ? 'A creative look is welcome.' : 'Keep the edit natural.'} Work on virtual copies and review Lightroom renders.`), 'Selection and brief copied for your agent.')}>Copy brief for agent</Button><Button size="sm" isDisabled={Boolean(editBlocked) || busy} disabledReason={editBlocked} onPress={() => void prepare()}>Prepare virtual copies</Button></div></section> : null}
        {search.error ? <p role="alert">{search.error.message}</p> : null}
        {search.isPending ? <p role="status">Finding photographs…</p> : null}
        {search.data?.pages[0]?.semantic_available === false && query ? <p className={s.muted}>Searching metadata. Install the visual model pack to search image content too.</p> : null}
        {!search.isPending && !items.length ? <section className={s.empty}><h2>{count ? 'No matching photographs yet.' : 'Your next favourite is in here.'}</h2><p>{count ? 'Try a broader description, another date range or a person you have named.' : 'Choose a catalogue or folder in Photo setup. Metadata appears first, then image understanding.'}</p>{!count ? <Button onPress={() => setSetupOpen(true)}>Choose photo source</Button> : null}</section> : null}
        <div className={s.workspace}>
          <div className={compare ? s.comparisonGrid : s.grid}>
            {items.filter((photo) => !compare || selected.has(photo.uid)).map((photo) => <article className={s.card} data-selected={selected.has(photo.uid) || undefined} key={photo.uid}>
              <button className={s.imageButton} onClick={() => setInspected(photo.uid)} aria-label={`Inspect ${photo.filename}`}><PhotoImage key={`${photo.uid}-${photo.revision}`} uid={photo.uid} label={photo.filename} edge={compare ? 1600 : 600} retry={false} /></button>
              <div className={s.cardInfo}><Checkbox isSelected={selected.has(photo.uid)} onChange={() => toggle(photo.uid)} aria-label={`Select ${photo.filename}`} /><div><strong>{photo.filename}</strong><span>{photo.copy_name || photo.capture_time?.slice(0, 10) || 'Capture date unknown'}</span></div><span className={s.badge}>{photo.availability === 'original' ? 'Original' : photo.availability.replaceAll('_', ' ')}</span></div>
            </article>)}
          </div>
          {inspected ? <PhotoInspector key={inspected} uid={inspected} canName={scopes.includes('tags:write') && me.data?.role !== 'agent'} onClose={() => setInspected(null)} onBurst={(id) => { setFilters({ burst_id: id }); setDiverse(false); setInspected(null); setQuery('') }} /> : null}
        </div>
        {search.hasNextPage && !compare ? <Button isDisabled={search.isFetchingNextPage} onPress={() => void search.fetchNextPage()}>Load more photographs</Button> : null}
        </> : null}
        {view === 'activity' && review ? <section className={s.panel} aria-label="Review Lightroom edit"><div className={s.row}><h2>Review this edit</h2><IconButton icon={X} label="Close edit review" onPress={() => setReview(null)} /></div>
          <div className={s.comparisonGrid}>
            {review.source_photo_id ? <figure><PhotoImage uid={review.source_photo_id} label="Source photograph" edge={1600} /><figcaption>Source photograph</figcaption></figure> : null}
            <figure><PhotoImage key={`${review.photo_id}-${review.revision}`} uid={review.photo_id} revision={review.revision} label="Rendered Lightroom edit" edge={1600} /><figcaption>Rendered virtual copy</figcaption></figure>
          </div><p className={s.muted}>Check skin colour, detail, framing and consistency with the other photographs before saving.</p><TextField label="Lightroom collection" value={collection} onChange={setCollection} />
          <Button icon={Check} variant="primary" isDisabled={!canEdit || !scopes.includes('collections:write') || !collection.trim() || busy} onPress={() => void action(async () => {
            await enqueue('/api/photos/edits/finish', { selections: [{ session_id: review.session_id, reviewed_revision: review.revision }], collection }); setReview(null)
          }, 'Saving the reviewed virtual copy to Lightroom.')}>Save reviewed copy</Button>
        </section> : null}
        {view === 'activity' ? <section className={s.panel}><div className={s.row}><h2>Activity</h2><Button size="sm" isDisabled={!canIngest || busy} onPress={() => void action(() => enqueue('/api/photos/analyse'), 'Image analysis queued.')}>Refresh analysis</Button></div>
          {jobs.error ? <p role="alert">{jobs.error.message}</p> : null}
          {!jobs.data?.jobs.length ? <p className={s.muted}>Indexing, agent edits and saved selections will appear here.</p> : null}
          {jobs.data?.jobs.slice(0, 30).map((job) => <PhotoJobRow key={job.uid} job={job} canManage={job.kind === 'models' ? canAdmin : ['begin','apply','finish','restore'].includes(job.kind) ? canEdit : canIngest} onReview={setReview} onAction={(command) => void action(() => api.post(`/api/photos/jobs/${job.uid}/${command}`), command === 'resume' ? 'Job resumed.' : 'Stopping at the next safe point.')} />)}
        </section> : null}
      </> : null}
      {message ? <div role="status" className={s.notice}><span>{message}</span><IconButton icon={X} label="Dismiss notification" onPress={() => setMessage('')} /></div> : null}
      {error ? <div role="alert" className={s.notice}><span>{error}</span><IconButton icon={X} label="Dismiss error" onPress={() => setError('')} /></div> : null}
    </div>
  </main>
}

function PhotoJobRow({ job, canManage, onReview, onAction }: { job: PhotoJob; canManage: boolean; onReview: (session: PhotoSession) => void; onAction: (command: 'resume' | 'cancel') => void }) {
  const result = job.result
  const sessions = result.sessions ?? (result.session_id && result.photo_id && result.revision ? [{ session_id: result.session_id, photo_id: result.photo_id, revision: result.revision }] : [])
  return <div className={s.job}><div className={s.row}><strong>{labels[job.kind] ?? job.kind}</strong><span className={s.badge}>{job.status === 'done' && sessions.length ? job.kind === 'begin' ? 'Copies ready for agent' : 'Ready for review' : job.status}</span>
    {result.processed !== undefined ? <span className={s.muted}>{result.processed.toLocaleString()}{result.total ? ` / ${result.total.toLocaleString()}` : ''} photographs</span> : null}
    {result.current_model ? <span className={s.muted}>{result.current_model}{result.downloaded_bytes ? ` · ${bytes(result.downloaded_bytes)}${result.total_bytes ? ` / ${bytes(result.total_bytes)}` : ''}` : ''}</span> : null}
    {canManage && ['waiting', 'failed', 'cancelled'].includes(job.status) ? <Button size="sm" onPress={() => onAction('resume')}>Resume</Button> : null}
    {canManage && ['queued', 'running', 'waiting'].includes(job.status) ? <Button size="sm" onPress={() => onAction('cancel')}>Stop</Button> : null}
    {job.status === 'done' ? sessions.map((session, i) => <Button size="sm" key={session.session_id} onPress={() => onReview(session)}>{job.kind === 'begin' ? 'View copy' : 'Review edit'}{sessions.length > 1 ? ` ${i + 1}` : ''}</Button>) : null}
  </div>{job.kind === 'begin' && job.status === 'done' ? <p className={s.muted}>Virtual copies created. Ask your agent to apply the brief and review the rendered result.</p> : null}{job.error ? <p className={s.muted}>{job.error}</p> : null}{result.accepted ? <p>{result.accepted.length} photographs saved to {result.collection} in Lightroom.</p> : null}</div>
}
