import { useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { useNavigate, useSearch } from '@tanstack/react-router'
import { Camera, Check, Download, FolderPlus, RefreshCw, Search, X } from 'lucide-react'
import { api } from '../../api/client'
import { useMe } from '../../api/queries'
import { photoRequestKey, usePhotoJobs, usePhotoSearch, usePhotoStatus, type PhotoContext, type PhotoJob, type PhotoSession } from '../../api/photos'
import { Button, IconButton } from '../../components/Button'
import { Checkbox, TextField } from '../../components/Field'
import { Ic } from '../../components/Icon'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { PhotoImage, PhotoInspector } from './PhotoInspector'
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
  const [folder, setFolder] = useState('')
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
  const [connectorPath, setConnectorPath] = useState('')
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
  const count = Object.values(status.data?.counts ?? {}).reduce((sum, n) => sum + n, 0)

  const action = async (task: () => Promise<unknown>, success: string) => {
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
    for (const uid of ids) revisions[uid] = (await api.get<PhotoContext>(`/api/photos/${uid}/context`)).revision
    await enqueue('/api/photos/edits', { photo_ids: ids, expected_revisions: revisions, brief: 'Natural family and travel edits', creative: false })
  }, 'Preparing virtual copies. Follow the job below, or continue editing through your agent.')

  return <main className={s.page} id="main">
    <div className={s.inner}>
      <header className={s.header}><div><p className={s.eyebrow}>METACHLORIAN / PHOTOS</p><h1>The moments worth keeping.</h1><p className={s.muted}>Find your photographs, compare the moments and finish them in Lightroom.</p></div><Ic icon={Camera} size={24} /></header>
      {status.error ? <p role="alert">{status.error.message}</p> : null}
      {status.isPending ? <p role="status">Loading your photo library…</p> : null}
      {status.data && !enabled ? <section className={s.panel}>
        <h2>Your photo library, in place.</h2><p>Connect a Lightroom Classic catalogue or add a folder. Originals stay where they are. Temporary previews have a storage limit, and edits are saved as virtual copies.</p>
        <p className={s.muted}>This is a preview feature. Lightroom editing targets version 15.6; platform certification is still in progress.</p>
        <Button variant="primary" isDisabled={!canAdmin || busy} busy={busy} onPress={() => void action(() => api.put('/api/admin/settings', { photos_enabled: true }), 'Photos enabled.')}>Enable Photos</Button>
      </section> : null}
      {enabled ? <>
        <div className={s.stats}>
          <div><strong>{count.toLocaleString()}</strong><span>photographs indexed</span></div>
          <div><strong>{status.data?.lightroom.connected ? 'Connected' : 'Offline'}</strong><span>{status.data?.lightroom.catalog?.name ?? 'Lightroom Classic'}</span></div>
          <div><strong>{bytes(status.data?.cache.bytes ?? 0)}</strong><span>of {bytes(status.data?.cache.budget_bytes ?? 0)} preview cache</span></div>
        </div>
        <details className={s.panel} open={count === 0 ? true : undefined}>
          <summary>Sources and Lightroom setup</summary>
          <div className={s.setup}>
            <div><h3>Lightroom Classic</h3><p>Reuse your catalogue and Smart Previews. Enable the connector once in Lightroom’s Plug-in Manager.</p>
              <div className={s.actions}>
                <Button icon={Download} isDisabled={!canAdmin || busy} onPress={() => void action(async () => {
                  const result = await api.post<{ path: string }>('/api/photos/connector/install'); setConnectorPath(result.path)
                }, 'Connector copied. Add the folder below in Lightroom’s Plug-in Manager.')}>Install connector files</Button>
                <Button icon={RefreshCw} isDisabled={!canIngest || !status.data?.lightroom.connected || busy} onPress={() => void action(() => enqueue('/api/photos/sources/lightroom'), 'Catalogue synchronisation queued.')}>Sync catalogue</Button>
              </div>
              {connectorPath ? <p className={s.path}>{connectorPath}</p> : null}
            </div>
            <div><h3>Photo folder</h3><p>Index JPEG, HEIC, RAW and other photographs without copying them.</p>
              <TextField label="Folder on this computer" value={folder} onChange={setFolder} placeholder="/Pictures/Family or C:\Pictures\Family" />
              <Button icon={FolderPlus} isDisabled={!canIngest || !folder.trim() || busy} onPress={() => void action(() => enqueue('/api/photos/sources/folder', { path: folder }), 'Folder indexing queued.')}>Index folder</Button>
            </div>
          </div>
          <p className={s.muted}>Only selected previews go to your connected agent. Photo indexing runs locally. Models and Lightroom’s own previews use separate storage.</p>
          <details><summary>Use with Codex or another agent</summary><p>Connect the agent to this app’s MCP endpoint and grant photo editing and collection permissions. Try: “Find the best 20 photos from our holiday, include varied moments, and edit them naturally in Lightroom.”</p>
            <code>{`${window.location.origin}/mcp`}</code><p className={s.muted}>Create the agent token in Settings → Agents. Visual models can be installed with <code>metachlorian models fetch --pack photos</code>.</p></details>
        </details>
        {canAdmin && status.data?.models.some((m) => m.name !== 'face-landmarker' && !m.installed) ? <section className={s.panel}><h2>Search what is in your photographs</h2><p>Install local visual search and face models. Downloads are shared with the video library.</p><Button icon={Download} isDisabled={busy || jobs.data?.jobs.some((j) => j.kind === 'models' && ['queued', 'running'].includes(j.status))} onPress={() => void action(() => enqueue('/api/photos/models/install'), 'Photo models queued for download.')}>Install photo models ({Math.round(status.data.models.filter((m) => m.name !== 'face-landmarker' && !m.installed).reduce((sum, m) => sum + m.size_mb, 0))} MB)</Button></section> : null}
        <form className={s.search} onSubmit={(event) => { event.preventDefault(); setQuery(draft); setFilters({ ...(person.trim() ? { person: person.trim() } : {}), ...(dateFrom ? { date_from: dateFrom } : {}), ...(dateTo ? { date_to: `${dateTo}T23:59:59` } : {}) }); setSelected(new Set()); setCompare(false) }}>
          <TextField label="Find photographs" value={draft} onChange={setDraft} placeholder="Family at the beach, quiet moments, portraits in evening light…" />
          <div className={s.filters}><TextField label="Person" value={person} onChange={setPerson} placeholder="A name you’ve added" /><label>From<input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} /></label><label>To<input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} /></label><Button type="submit" variant="primary" icon={Search}>Find photos</Button></div>
        </form>
        <div className={s.row}><Checkbox isSelected={diverse} onChange={setDiverse}>Show different moments</Checkbox><span className={s.muted}>{search.data?.pages[0]?.total.toLocaleString() ?? 0} results</span>
          {route.person_id || route.photo_collection ? <Button size="sm" onPress={() => void navigate({ to: '/photos', search: {} })}>Clear {route.person_id ? 'person' : 'collection'} filter</Button> : null}
          {filters.burst_id ? <Button size="sm" onPress={() => setFilters({})}>Leave burst comparison</Button> : null}
          {selected.size ? <><span>{selected.size} selected</span><Button size="sm" isDisabled={selected.size > 4} onPress={() => setCompare(!compare)}>{compare ? 'Show library' : 'Compare up to four'}</Button><Button size="sm" isDisabled={!canEdit || busy || !status.data?.lightroom.connected} onPress={() => void prepare()}>Prepare virtual copies</Button><Button size="sm" onPress={() => { setSelected(new Set()); setCompare(false) }}>Clear selection</Button></> : null}
        </div>
        {search.error ? <p role="alert">{search.error.message}</p> : null}
        {search.isPending ? <p role="status">Finding photographs…</p> : null}
        {search.data?.pages[0]?.semantic_available === false && query ? <p className={s.muted}>Searching metadata. Install the visual model pack to search image content too.</p> : null}
        {!search.isPending && !items.length ? <section className={s.empty}><h2>{count ? 'No matching photographs yet.' : 'Start with a catalogue or folder.'}</h2><p>{count ? 'Try a broader description, another date range or a person you have named.' : 'Metadata appears first. Image understanding continues in the background.'}</p></section> : null}
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
        {review ? <section className={s.panel} aria-label="Review Lightroom edit"><div className={s.row}><h2>Review this edit</h2><IconButton icon={X} label="Close edit review" onPress={() => setReview(null)} /></div>
          <div className={s.comparisonGrid}>
            {review.source_photo_id ? <figure><PhotoImage uid={review.source_photo_id} label="Source photograph" edge={1600} /><figcaption>Source photograph</figcaption></figure> : null}
            <figure><PhotoImage key={`${review.photo_id}-${review.revision}`} uid={review.photo_id} revision={review.revision} label="Rendered Lightroom edit" edge={1600} /><figcaption>Rendered virtual copy</figcaption></figure>
          </div><p className={s.muted}>Check skin colour, detail, framing and consistency with the other photographs before saving.</p><TextField label="Lightroom collection" value={collection} onChange={setCollection} />
          <Button icon={Check} variant="primary" isDisabled={!canEdit || !scopes.includes('collections:write') || !collection.trim() || busy} onPress={() => void action(async () => {
            await enqueue('/api/photos/edits/finish', { selections: [{ session_id: review.session_id, reviewed_revision: review.revision }], collection }); setReview(null)
          }, 'Saving the reviewed virtual copy to Lightroom.')}>Save reviewed copy</Button>
        </section> : null}
        {jobs.data?.jobs.length ? <section className={s.panel}><div className={s.row}><h2>Activity</h2><Button size="sm" isDisabled={!canIngest || busy} onPress={() => void action(() => enqueue('/api/photos/analyse'), 'Image analysis queued.')}>Refresh analysis</Button></div>
          {jobs.data.jobs.slice(0, 12).map((job) => <PhotoJobRow key={job.uid} job={job} canManage={job.kind === 'models' ? canAdmin : ['begin','apply','finish','restore'].includes(job.kind) ? canEdit : canIngest} onReview={setReview} onAction={(command) => void action(() => api.post(`/api/photos/jobs/${job.uid}/${command}`), command === 'resume' ? 'Job resumed.' : 'Stopping at the next safe point.')} />)}
        </section> : null}
      </> : null}
      {message ? <p role="status" className={s.notice}>{message}</p> : null}
      {error ? <p role="alert" className={s.notice}>{error}</p> : null}
    </div>
  </main>
}

function PhotoJobRow({ job, canManage, onReview, onAction }: { job: PhotoJob; canManage: boolean; onReview: (session: PhotoSession) => void; onAction: (command: 'resume' | 'cancel') => void }) {
  const result = job.result
  const sessions = result.sessions ?? (result.session_id && result.photo_id && result.revision ? [{ session_id: result.session_id, photo_id: result.photo_id, revision: result.revision }] : [])
  return <div className={s.job}><div className={s.row}><strong>{labels[job.kind] ?? job.kind}</strong><span className={s.badge}>{job.status === 'done' && sessions.length ? 'Ready for review' : job.status}</span>
    {result.processed !== undefined ? <span className={s.muted}>{result.processed.toLocaleString()}{result.total ? ` / ${result.total.toLocaleString()}` : ''} photographs</span> : null}
    {result.current_model ? <span className={s.muted}>{result.current_model}{result.downloaded_bytes ? ` · ${bytes(result.downloaded_bytes)}${result.total_bytes ? ` / ${bytes(result.total_bytes)}` : ''}` : ''}</span> : null}
    {canManage && ['waiting', 'failed', 'cancelled'].includes(job.status) ? <Button size="sm" onPress={() => onAction('resume')}>Resume</Button> : null}
    {canManage && ['queued', 'running', 'waiting'].includes(job.status) ? <Button size="sm" onPress={() => onAction('cancel')}>Stop</Button> : null}
    {job.status === 'done' ? sessions.map((session, i) => <Button size="sm" key={session.session_id} onPress={() => onReview(session)}>Review{sessions.length > 1 ? ` ${i + 1}` : ''}</Button>) : null}
  </div>{job.error ? <p className={s.muted}>{job.error}</p> : null}{result.accepted ? <p>{result.accepted.length} photographs saved to {result.collection} in Lightroom.</p> : null}</div>
}
