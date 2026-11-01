import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { DropZone, FileTrigger } from 'react-aria-components'
import { Check, ChevronRight, CircleAlert, CircleCheck, CircleDashed, CircleX, Cloud, Cpu, FolderOpen, FolderSearch, FolderTree, HardDrive, LoaderCircle, RefreshCw, Trash2, Upload } from 'lucide-react'
import type { QueueJob, SourceScan } from '../../api/types'
import { api, ApiError, upload } from '../../api/client'
import { useAsset, useHealth, useProcessing, useSources, useFolderExclusions } from '../../api/queries'
import { Button } from '../../components/Button'
import { Bar, EmptyState, StatusText } from '../../components/EmptyState'
import { Checkbox, TextField } from '../../components/Field'
import { Ic } from '../../components/Icon'
import { toast } from '../../components/Toast'
import { bridge, can } from '../../lib/bridge'
import { formatDateTime, formatNumber, formatRelative, humanise, plural } from '../../lib/format'
import { formatLength } from '../../lib/timecode'
import l from '../library/Library.module.css'
import s from './Ingest.module.css'
import { STEPS, stepStates, updatingText } from '../../lib/processing'
import { needsDecoder } from '../../lib/formats'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { searchFolder } from '../library/FoldersPage'
import { AddFromLinks, ImportsList } from './Imports'
import { DecoderLink } from './DecoderLink'

const STEP_ICON = { done: Check, active: LoaderCircle, waiting: CircleDashed, failed: CircleX }

/** Ingest and processing (system.md §9.7, §3.23). Polls every 2.5 s while visible. */
export function IngestPage() {
  const [offset, setOffset] = useState(0)
  const [fileQuery, setFileQuery] = useState('')
  const proc = useProcessing(true, { offset, q: fileQuery })
  useDocumentTitle('Ingest and processing')
  const sources = useSources()
  const exclusions = useFolderExclusions()
  const health = useHealth()
  const navigate = useNavigate()
  const qc = useQueryClient()
  const [uri, setUri] = useState('')
  const [watch, setWatch] = useState(true)
  const [adding, setAdding] = useState(false)
  const [uploads, setUploads] = useState<{ name: string; progress: number; state: 'uploading' | 'done' | 'failed'; error?: string }[]>([])
  const [open, setOpen] = useState<string | null>(null)
  const [announce, setAnnounce] = useState('')
  const lastAnnounce = useRef(0)
  const d = proc.data
  const assets = d?.assets ?? []
  const counts = d?.asset_counts ?? {}
  const total = Object.values(counts).reduce((sum, count) => sum + count, 0)
  const ready = (counts.ready ?? 0) + (counts.updating ?? 0)
  const processing = total - ready
  const updating = counts.updating ?? 0
  // Magenta marks only the current item (§0 rule 2): the first row with a running step.
  const currentUid = assets.find((a) => a.running > 0)?.uid
  const remote = health.data?.egress.content_leaves_machine

  useEffect(() => {
    if (!d) return
    const now = Date.now()
    if (now - lastAnnounce.current < 10_000) return
    lastAnnounce.current = now
    const t = window.setTimeout(() => setAnnounce(`Ingest: ${ready} of ${total} files searchable`), 0)
    return () => window.clearTimeout(t)
  }, [d, ready, total])

  const addSource = async () => {
    if (!uri.trim()) return
    setAdding(true)
    try {
      await api.post('/api/sources', { uri: uri.trim(), watch, scan: true })
      toast({ title: `Added ${uri.trim()}`, description: 'Scan requested, including all subfolders. Follow its progress below.' })
      setUri('')
      qc.invalidateQueries({ queryKey: ['sources'] })
      qc.invalidateQueries({ queryKey: ['processing'] })
    } catch (e) {
      toast({ title: "Couldn't add that source", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    } finally {
      setAdding(false)
    }
  }

  const uploadFiles = async (files: File[]) => {
    for (const f of files) {
      setUploads((u) => [...u, { name: f.name, progress: 0, state: 'uploading' }])
      const form = new FormData()
      form.append('file', f)
      try {
        await upload<{ outcome: string }>('/api/upload', form, (p) => setUploads((u) => u.map((x) => (x.name === f.name ? { ...x, progress: p } : x))))
        setUploads((u) => u.map((x) => (x.name === f.name ? { ...x, progress: 1, state: 'done' } : x)))
        qc.invalidateQueries({ queryKey: ['processing'] })
      } catch (e) {
        setUploads((u) => u.map((x) => (x.name === f.name ? { ...x, state: 'failed', error: e instanceof ApiError ? e.detail : String(e) } : x)))
      }
    }
  }

  const retryAll = async () => {
    const r = await api.post<{ enqueued: number }>('/api/processing/retry', {})
    toast({ title: `Retrying failed steps`, description: `${r.enqueued} queued`, tone: 'info' })
    qc.invalidateQueries({ queryKey: ['processing'] })
  }

  return (
    <main id="main" className={l.page}>
      <div className={l.inner}>
        <div className={l.titleRow}>
          <h1>Ingest and processing</h1>
          <StatusText tone={remote ? 'caution' : 'neutral'} icon={remote ? Cloud : HardDrive} filled={remote}>
            {remote ? 'Leaves this machine' : 'Local analysis'}
          </StatusText>
        </div>
        {d?.library_path && <p className={s.path}>Current library: {d.library_path}</p>}
        <span className="visually-hidden" aria-live="polite">{announce}</span>

        <div className={s.summary} data-testid="processing-summary">
          <div className={l.figure}>
            <span className={l.figureLabel}>Searchable</span>
            <strong>{formatNumber(ready)}</strong>
            <span className={l.figureSub}>of {plural(total, 'file')}{updating ? ` · ${formatNumber(updating)} updating` : ''}</span>
          </div>
          <div className={l.figure}>
            <span className={l.figureLabel}>Not yet searchable</span>
            <strong>{formatNumber(processing)}</strong>
            <span className={l.figureSub}>{plural(d?.queue.by_status.running ?? 0, 'step')} running · {formatNumber(d?.queue.by_status.queued ?? 0)} queued</span>
          </div>
          <div className={l.figure}>
            <span className={l.figureLabel}>Failed steps</span>
            <strong>{formatNumber(d?.queue.by_status.failed ?? 0)}</strong>
            <span className={l.figureSub}>{d?.queue.failed.length ? <Button variant="quiet" size="sm" icon={RefreshCw} onPress={retryAll}>Retry all</Button> : 'None'}</span>
          </div>
          <div className={l.figure}>
            <span className={l.figureLabel}>Throughput</span>
            <strong>{d?.throughput.ratio ? `${d.throughput.ratio.toFixed(2)}×` : '—'}</strong>
            <span className={l.figureSub}>{d?.throughput.ratio ? `${d.throughput.footage_hours.toFixed(2)} h of footage in ${d.throughput.wall_hours.toFixed(2)} h` : 'Measured once files finish'}</span>
          </div>
        </div>

        <section className={l.section} aria-labelledby="src-h">
          <div className={l.sectionHead}>
            <h2 id="src-h">Watched folders and sources</h2>
          </div>
          <div className={s.sources}>
            {[...(sources.data ?? [])].sort((a, b) => Number(['queued', 'discovering', 'registering'].includes(b.scan?.state ?? '')) - Number(['queued', 'discovering', 'registering'].includes(a.scan?.state ?? '')) || b.id - a.id).map((src) => (
              <div key={src.id} className={s.card}>
                <div className={s.cardHead}>
                  <Ic icon={src.kind === 's3' ? Cloud : HardDrive} />
                  <span className={s.path}>{src.uri}</span>
                </div>
                <div className={s.cardMeta}>
                  <span>{plural(src.assets, 'file')}</span>
                  <span>{src.watch ? 'Watched' : 'Not watched'}</span>
                  <span title={formatDateTime(src.last_scan)}>{src.last_scan ? `Last scan ${formatRelative(src.last_scan)}` : 'No completed scan yet'}</span>
                </div>
                <ScanProgress scan={src.scan} />
                <div className={s.cardActions}>
                  {src.kind !== 's3' && src.assets > 0 && (
                    <>
                      <Button variant="secondary" size="sm" icon={FolderSearch} onPress={() => searchFolder(navigate, src.uri.replace(/\/+$/, ''))} aria-label={`Search this folder: ${src.uri}`}>
                        Search this folder
                      </Button>
                      <Button variant="quiet" size="sm" icon={FolderTree} onPress={() => navigate({ to: '/library/folders', search: { open: src.uri.replace(/\/+$/, '') } })} aria-label={`Show files in ${src.uri}`}>
                        Show files
                      </Button>
                    </>
                  )}
                  <Button
                    variant="quiet"
                    size="sm"
                    icon={RefreshCw}
                    isDisabled={['queued', 'discovering', 'registering'].includes(src.scan?.state ?? '')}
                    onPress={async () => {
                      try {
                        await api.post(`/api/sources/${src.id}/scan`, {})
                        toast({ title: `Scan requested for ${src.uri}`, tone: 'info' })
                      } catch (e) {
                        toast({ title: 'Could not start scan', description: String(e), tone: 'error' })
                      }
                      qc.invalidateQueries({ queryKey: ['processing'] })
                      qc.invalidateQueries({ queryKey: ['sources'] })
                    }}
                  >
                    Rescan
                  </Button>
                  {can('canRevealInFolder') && (
                    <Button variant="quiet" size="sm" icon={FolderOpen} onPress={() => bridge()?.openPath(src.uri)}>
                      Open
                    </Button>
                  )}
                  <Button
                    variant="quiet"
                    size="sm"
                    icon={Trash2}
                    isDisabled={['queued', 'discovering', 'registering'].includes(src.scan?.state ?? '')}
                    onPress={async () => {
                      await api.del(`/api/sources/${src.id}`)
                      toast({ title: `Stopped watching ${src.uri}`, description: 'Files already in the library stay.', tone: 'info' })
                      qc.invalidateQueries({ queryKey: ['sources'] })
                    }}
                  >
                    Remove
                  </Button>
                </div>
              </div>
            ))}
          </div>
          {!!exclusions.data?.length && <div>
            <h3>Excluded folders</h3>
            <p>These folders and their subfolders are skipped by every scan. Original files stay on disk.</p>
            <ul>{exclusions.data.map((folder) => <li key={folder} className={s.path}>{folder}</li>)}</ul>
          </div>}
          <form
            className={s.addForm}
            onSubmit={(e) => {
              e.preventDefault()
              addSource()
            }}
          >
            <TextField label="Add a folder or S3 location" description="Scans all subfolders for videos, skips duplicate content, and starts analysis as files are registered. Originals stay where they are. Use a path on this server or s3://bucket/prefix." value={uri} onChange={setUri} placeholder="D:\Photos and Videos or s3://bucket/footage" mono />
            {can('canChooseFolder') && (
              <Button
                variant="secondary"
                icon={FolderOpen}
                onPress={async () => {
                  const p = await bridge()?.chooseFolder()
                  if (p) setUri(p)
                }}
              >
                Choose folder…
              </Button>
            )}
            <Checkbox isSelected={watch} onChange={setWatch}>
              Watch for new files
            </Checkbox>
            <Button type="submit" variant="primary" busy={adding} isDisabled={!uri.trim()}>
              Add and scan
            </Button>
          </form>
          <DropZone
            className={s.drop}
            getDropOperation={() => 'copy'}
            onDrop={async (e) => {
              const files = await Promise.all(e.items.filter((i) => i.kind === 'file').map((i) => (i as { getFile: () => Promise<File> }).getFile()))
              uploadFiles(files)
            }}
            aria-label="Drop video files to upload"
          >
            <Ic icon={Upload} size={20} />
            <span>Drop files to add them, or</span>
            <FileTrigger allowsMultiple acceptedFileTypes={['video/*', '.mov', '.mxf', '.mkv']} onSelect={(fl) => fl && uploadFiles(Array.from(fl))}>
              <Button variant="secondary" size="sm">Choose files…</Button>
            </FileTrigger>
            {uploads.length > 0 && (
              <div className={s.uploads}>
                {uploads.map((u) => (
                  <div key={u.name} className={s.upload}>
                    <span>{u.name}</span>
                    <Bar value={u.progress} current={u.state === 'uploading'} label={`Uploading ${u.name}`} />
                    <span className={s.pct}>{u.state === 'failed' ? <StatusText tone="blocked" icon={CircleAlert}>Failed</StatusText> : u.state === 'done' ? 'Added' : `${Math.round(u.progress * 100)}%`}</span>
                  </div>
                ))}
              </div>
            )}
          </DropZone>
        </section>

        <section className={l.section} aria-labelledby="links-h">
          <div className={l.sectionHead}>
            <h2 id="links-h">Add from links</h2>
            <Link to="/settings/$section" params={{ section: 'imports' }}>Import settings</Link>
          </div>
          <AddFromLinks />
        </section>

        <ImportsList />

        <section className={l.section} aria-labelledby="q-h">
          {(d?.queue.running ?? []).map((job) => <p key={job.id} className={s.activity}><Ic icon={LoaderCircle} className="mc-spin" /> <strong>{job.filename}</strong> · {humanise(job.analyser)} running</p>)}
          <div className={l.sectionHead}>
            <h2 id="q-h">Queue and file history</h2>
            <span className={s.pct}>Updates every few seconds</span>
          </div>
          <TextField label="Find an ingested file" description="Includes completed files and earlier imports. Search by filename or folder path." value={fileQuery} onChange={(value) => { setFileQuery(value); setOffset(0) }} />
          {proc.isError ? (
            <EmptyState inline title="Couldn't read the queue" role="alert">{(proc.error as Error).message}</EmptyState>
          ) : !assets.length && !proc.isLoading ? (
            <EmptyState inline title={fileQuery ? 'No matching files' : 'Nothing to process'}>{fileQuery ? 'Try another filename or folder path.' : 'Add a folder or drop files above. Analysis starts as files are registered.'}</EmptyState>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table className={l.table} data-testid="queue-table">
                <thead>
                  <tr>
                    <th>File</th>
                    <th className={l.num}>Length</th>
                    <th>Steps</th>
                    <th>Progress</th>
                    <th>State</th>
                  </tr>
                </thead>
                <tbody>
                  {assets.map((a) => {
                    const steps = stepStates(a, d?.analysers ?? [], d?.queue.running ?? [], d?.queue.failed ?? [])
                    const total = Math.max(1, d?.analysers.length ?? 0, a.done + a.queued + a.running + a.failed + a.unavailable)
                    const isUpdating = a.status === 'updating'
                    const completed = a.steps ? Object.values(a.steps).filter((state) => state === 'done' || state === 'unavailable').length : a.done + a.unavailable
                    const frac = a.status === 'ready' && !a.failed ? 1 : completed / total
                    const fails = (d?.queue.failed ?? []).filter((j) => j.uid === a.uid)
                    const left = a.queued + a.running
                    return [
                      <tr key={a.uid}>
                        <td>
                          <button type="button" className={s.rowButton} title={a.path} aria-expanded={open === a.uid} onClick={() => setOpen(open === a.uid ? null : a.uid)}>
                            <Ic icon={ChevronRight} size={14} style={{ transform: open === a.uid ? 'rotate(90deg)' : undefined }} />
                            <span>{a.filename}</span>
                          </button>
                        </td>
                        <td className={l.num}>{formatLength(a.duration)}</td>
                        <td>
                          <span className={s.steps}>
                            {STEPS.map((st, i) => (
                              <span key={st.label} className={`${s.step} ${s[steps[i]]}`} aria-label={`${st.label}: ${steps[i]}`}>
                                <Ic icon={STEP_ICON[steps[i]]} size={14} className={steps[i] === 'active' ? 'mc-spin' : undefined} />
                                <span className={s.stepLabel}>{st.label}</span>
                              </span>
                            ))}
                          </span>
                        </td>
                        <td style={{ minInlineSize: 120 }}>
                          {isUpdating ? (
                            <span className={s.pct}>Searchable · {plural(left, 'step')} left</span>
                          ) : (
                            <span style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
                              <Bar value={frac} current={a.uid === currentUid} label={`${a.filename} progress`} />
                              <span className={s.pct}>{Math.round(frac * 100)}%</span>
                            </span>
                          )}
                        </td>
                        <td>
                          {a.status === 'missing' ? <StatusText tone="caution" icon={CircleAlert}>Source file missing</StatusText> : fails.length || a.failed || a.status === 'error' ? (
                            <span className={s.stateCell}>
                              <StatusText tone="blocked" icon={CircleX}>Failed</StatusText>
                              <DecoderLink error={fails.find((f) => needsDecoder(f.error))?.error} className={s.decoderLink} />
                            </span>
                          ) : a.status === 'ready' ? (
                            <Link to="/file/$assetId" params={{ assetId: a.uid }}>
                              <StatusText tone="cleared" icon={CircleCheck}>Ready</StatusText>
                            </Link>
                          ) : isUpdating ? (
                            <StatusText tone="info" icon={RefreshCw}>{updatingText(a)}</StatusText>
                          ) : (
                            <StatusText tone="info" icon={LoaderCircle}>{a.running ? 'Analysing' : 'Queued'}</StatusText>
                          )}
                        </td>
                      </tr>,
                      open === a.uid ? <DetailRow key={`${a.uid}-d`} uid={a.uid} fails={fails} /> : null,
                    ]
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <div className={s.pagination} aria-label="File history pages">
          <span className={s.pct}>{formatNumber(assets.length ? offset + 1 : 0)}–{formatNumber(offset + assets.length)} of {formatNumber(d?.total ?? total)} files · newest added first</span>
          <Button variant="secondary" size="sm" isDisabled={offset === 0 || proc.isFetching} onPress={() => setOffset(Math.max(0, offset - 200))}>Previous</Button>
          <Button variant="secondary" size="sm" isDisabled={offset + assets.length >= (d?.total ?? total) || proc.isFetching} onPress={() => setOffset(offset + 200)}>Next</Button>
        </div>

        <section className={l.section} aria-labelledby="an-h">
          <div className={l.sectionHead}>
            <h2 id="an-h">Analysers</h2>
            <Link to="/settings/$section" params={{ section: 'adapters' }}>Model adapters</Link>
          </div>
          <div className={s.analysers}>
            {(d?.analysers ?? []).map((a) => {
              const counts = d?.queue.by_analyser[a.name] ?? {}
              return (
                <div key={a.name} className={s.analyser}>
                  <Ic icon={a.available ? Cpu : CircleDashed} className={a.available ? s.ok : s.na} />
                  <div>
                    <strong>{humanise(a.name)}</strong>{' '}
                    <span className={s.pct}>
                      {Object.entries(counts).map(([k, v]) => `${v} ${k}`).join(' · ')}
                    </span>
                    <p>{a.available ? a.description : <>Not available: {a.reason}</>}</p>
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      </div>
    </main>
  )
}

function ScanProgress({ scan }: { scan?: SourceScan }) {
  if (!scan?.state) return null
  const active = ['queued', 'discovering', 'registering'].includes(scan.state)
  const problem = scan.state === 'failed' || scan.state === 'completed_with_errors'
  const labels = { queued: 'Waiting to scan', discovering: 'Finding videos in all subfolders', registering: 'Registering videos and queuing analysis', completed: 'Scan complete', completed_with_errors: 'Scan finished — some paths could not be read', failed: 'Scan failed' }
  const found = scan.found ?? 0
  const processed = scan.processed ?? 0
  return <div className={s.scanProgress}>
    <StatusText tone={problem ? 'caution' : active ? 'info' : 'cleared'} icon={active ? LoaderCircle : problem ? CircleAlert : CircleCheck}>{labels[scan.state]}</StatusText>
    <span>{formatNumber(scan.directories ?? 0)} folders checked · {formatNumber(found)} videos found{scan.state === 'discovering' ? ' so far' : ''}</span>
    {scan.state !== 'queued' && scan.state !== 'discovering' && <>
      <Bar value={found ? processed / found : 0} current={active} label="Videos checked" />
      <span>{formatNumber(processed)} of {formatNumber(found)} videos checked · {formatNumber(scan.added ?? 0)} new · {formatNumber(scan.changed ?? 0)} changed · {formatNumber(scan.unchanged ?? 0)} already known · {formatNumber(scan.duplicates ?? 0)} duplicate locations · {formatNumber(scan.missing ?? 0)} missing</span>
    </>}
    {scan.current_path && <span className={s.path}>{scan.current_path}</span>}
    {active && (scan.file_bytes ?? 0) > 0 && <span>Reading file: {Math.min(100, Math.round(100 * (scan.bytes_read ?? 0) / scan.file_bytes!))}%</span>}
    {scan.updated_at && <span>Updated {formatRelative(scan.updated_at)}</span>}
    {!active && !problem && <span>Folder scan finished. Video analysis progress is shown below.</span>}
    {!!scan.errors && <details><summary>{plural(scan.errors, 'scan error')} — show details</summary>{(scan.issues ?? []).map((issue, i) => <p className={s.path} key={i}>{issue}</p>)}<p>Reconnect unavailable drives or fix access, then rescan. Up to 20 errors shown.</p></details>}
  </div>
}

function DetailRow({ uid, fails }: { uid: string; fails: QueueJob[] }) {
  const a = useAsset(uid, { refetchInterval: 3000 })
  const qc = useQueryClient()
  return (
    <tr className={s.detail}>
      <td colSpan={5}>
        {a.data?.path && <p className={s.path}>{a.data.path}</p>}
        <div className={s.detailRuns}>
          {(a.data?.processing ?? []).map((r) => (
            <StatusText key={r.analyser} tone={r.status === 'done' ? 'neutral' : r.status === 'failed' ? 'blocked' : r.status === 'unavailable' ? 'caution' : 'info'}>
              {humanise(r.analyser)} · {r.status === 'done' ? `${(r.seconds ?? 0).toFixed(1)} s` : r.status}
            </StatusText>
          ))}
          {(a.data?.jobs ?? []).map((j) => (
            <StatusText key={`j-${j.analyser}`} tone={j.status === 'failed' ? 'blocked' : 'info'} icon={j.status === 'running' ? LoaderCircle : undefined}>
              {humanise(j.analyser)} · {j.status}
            </StatusText>
          ))}
        </div>
        {fails.map((f) => (
          <p key={f.id} className={s.failure}>
            {humanise(f.analyser)} failed: {f.error ?? 'no reason given'}{f.error && /[.!?]$/.test(f.error) ? '' : '.'}{' '}
            <DecoderLink error={f.error} className={s.decoderLink} />
          </p>
        ))}
        <div style={{ display: 'flex', gap: 'var(--space-2)', paddingBlockEnd: 'var(--space-2)' }}>
          <Button
            variant="secondary"
            size="sm"
            icon={RefreshCw}
            onPress={async () => {
              await api.post(`/api/assets/${uid}/reprocess`, {})
              toast({ title: 'Re-analysis queued', tone: 'info' })
              qc.invalidateQueries({ queryKey: ['processing'] })
            }}
          >
            {fails.length ? 'Retry' : 'Re-analyse'}
          </Button>
          <Link to="/file/$assetId" params={{ assetId: uid }}>Open file</Link>
        </div>
      </td>
    </tr>
  )
}
