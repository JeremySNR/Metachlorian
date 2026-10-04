import { useEffect, useRef, useState } from 'react'
import { Link } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { DropZone, FileTrigger } from 'react-aria-components'
import { Check, ChevronRight, CircleAlert, CircleCheck, CircleDashed, CircleX, Cloud, Cpu, FolderOpen, HardDrive, LoaderCircle, RefreshCw, Trash2, Upload } from 'lucide-react'
import type { AnalyserInfo, ProcessingAsset, QueueJob } from '../../api/types'
import { api, ApiError, upload } from '../../api/client'
import { useAsset, useHealth, useProcessing, useSources } from '../../api/queries'
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

const STEPS: { label: string; analysers: string[] }[] = [
  { label: 'Probe', analysers: ['technical'] },
  { label: 'Proxies', analysers: ['proxy'] },
  { label: 'Shots', analysers: ['shots', 'keyframes'] },
  { label: 'Vision', analysers: ['embed', 'visual_tags', 'motion', 'quality', 'ocr', 'people', 'caption'] },
  { label: 'Audio', analysers: ['audio', 'speech'] },
  { label: 'Index', analysers: ['fusion', 'rollup', 'text_embed'] },
]

type StepState = 'done' | 'active' | 'waiting' | 'failed'

/** Step states for a queue row from its counts, running and failed jobs (approximate between polls). */
export function stepStates(a: ProcessingAsset, available: AnalyserInfo[], running: QueueJob[], failed: QueueJob[]): StepState[] {
  const order = available.filter((x) => x.available).map((x) => x.name)
  const ready = a.status === 'ready'
  const doneSet = new Set(ready ? order : order.slice(0, a.done))
  const runningSet = new Set(running.filter((j) => j.uid === a.uid).map((j) => j.analyser))
  const failedSet = new Set(failed.filter((j) => j.uid === a.uid).map((j) => j.analyser))
  let activeShown = false
  return STEPS.map((st) => {
    const names = st.analysers.filter((n) => order.includes(n))
    if (names.some((n) => failedSet.has(n))) return 'failed'
    if (names.some((n) => runningSet.has(n))) {
      activeShown = true
      return 'active'
    }
    if (names.every((n) => doneSet.has(n))) return 'done'
    if (!activeShown && !ready && a.running === 0 && a.queued > 0) {
      activeShown = true
      return 'active'
    }
    return 'waiting'
  })
}

const STEP_ICON = { done: Check, active: LoaderCircle, waiting: CircleDashed, failed: CircleX }

/** Ingest and processing (system.md §9.7, §3.23). Polls every 2.5 s while visible. */
export function IngestPage() {
  const proc = useProcessing()
  const sources = useSources()
  const health = useHealth()
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
  const ready = assets.filter((a) => a.status === 'ready').length
  const processing = assets.filter((a) => a.status === 'processing').length
  const remote = health.data?.egress.content_leaves_machine

  useEffect(() => {
    if (!d) return
    const now = Date.now()
    if (now - lastAnnounce.current < 10_000) return
    lastAnnounce.current = now
    const t = window.setTimeout(() => setAnnounce(`Ingest: ${ready} of ${assets.length} files ready`), 0)
    return () => window.clearTimeout(t)
  }, [d, ready, assets.length])

  const addSource = async () => {
    if (!uri.trim()) return
    setAdding(true)
    try {
      const res = await api.post<{ id: number; scan: { added?: number; new?: number } }>('/api/sources', { uri: uri.trim(), watch, scan: true })
      toast({ title: `Added ${uri.trim()}`, description: `Scanning now. ${res.scan && typeof res.scan === 'object' ? 'New files appear in the queue below.' : ''}` })
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
        <span className="visually-hidden" aria-live="polite">{announce}</span>

        <div className={s.summary} data-testid="processing-summary">
          <div className={l.figure}>
            <span className={l.figureLabel}>Ready</span>
            <strong>{formatNumber(ready)}</strong>
            <span className={l.figureSub}>of {plural(assets.length, 'file')}</span>
          </div>
          <div className={l.figure}>
            <span className={l.figureLabel}>Analysing</span>
            <strong>{formatNumber(processing)}</strong>
            <span className={l.figureSub}>{formatNumber(d?.queue.by_status.running ?? 0)} steps running · {formatNumber(d?.queue.by_status.queued ?? 0)} queued</span>
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
            {(sources.data ?? []).map((src) => (
              <div key={src.id} className={s.card}>
                <div className={s.cardHead}>
                  <Ic icon={src.kind === 's3' ? Cloud : HardDrive} />
                  <span className={s.path}>{src.uri}</span>
                </div>
                <div className={s.cardMeta}>
                  <span>{plural(src.assets, 'file')}</span>
                  <span>{src.watch ? 'Watched' : 'Not watched'}</span>
                  <span title={formatDateTime(src.last_scan)}>Scanned {formatRelative(src.last_scan)}</span>
                </div>
                <div className={s.cardActions}>
                  <Button
                    variant="quiet"
                    size="sm"
                    icon={RefreshCw}
                    onPress={async () => {
                      await api.post(`/api/sources/${src.id}/scan`, {})
                      toast({ title: `Rescanned ${src.uri}`, tone: 'info' })
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
          <form
            className={s.addForm}
            onSubmit={(e) => {
              e.preventDefault()
              addSource()
            }}
          >
            <TextField label="Add a folder or S3 location" description="A path on the server running Metachlorian, or s3://bucket/prefix. Files stay where they are; Metachlorian only reads them." value={uri} onChange={setUri} placeholder="/Volumes/Shoot_04 or s3://bucket/footage" mono />
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

        <section className={l.section} aria-labelledby="q-h">
          <div className={l.sectionHead}>
            <h2 id="q-h">Queue</h2>
            <span className={s.pct}>Updates every few seconds</span>
          </div>
          {proc.isError ? (
            <EmptyState inline title="Couldn't read the queue" role="alert">{(proc.error as Error).message}</EmptyState>
          ) : !assets.length && !proc.isLoading ? (
            <EmptyState inline title="Nothing to process">Add a folder or drop files above. Analysis starts straight away.</EmptyState>
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
                    const total = Math.max(1, a.done + a.queued + a.running + a.failed + a.unavailable)
                    const frac = a.status === 'ready' ? 1 : a.done / total
                    const fails = (d?.queue.failed ?? []).filter((j) => j.uid === a.uid)
                    return [
                      <tr key={a.uid}>
                        <td>
                          <button type="button" className={s.rowButton} aria-expanded={open === a.uid} onClick={() => setOpen(open === a.uid ? null : a.uid)}>
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
                          <span style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center' }}>
                            <Bar value={frac} current={a.status === 'processing'} label={`${a.filename} progress`} />
                            <span className={s.pct}>{Math.round(frac * 100)}%</span>
                          </span>
                        </td>
                        <td>
                          {fails.length ? (
                            <StatusText tone="blocked" icon={CircleX}>Failed</StatusText>
                          ) : a.status === 'ready' ? (
                            <Link to="/file/$assetId" params={{ assetId: a.uid }}>
                              <StatusText tone="cleared" icon={CircleCheck}>Ready</StatusText>
                            </Link>
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

function DetailRow({ uid, fails }: { uid: string; fails: QueueJob[] }) {
  const a = useAsset(uid, { refetchInterval: 3000 })
  const qc = useQueryClient()
  return (
    <tr className={s.detail}>
      <td colSpan={5}>
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
            {humanise(f.analyser)} failed: {f.error ?? 'no reason given'}.
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
