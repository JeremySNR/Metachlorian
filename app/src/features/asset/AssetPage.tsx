import { useRef, useState } from 'react'
import { Link, useNavigate, useParams, useRouter, useSearch } from '@tanstack/react-router'
import { ArrowLeft, ChevronDown, CircleAlert, ImageOff, LoaderCircle, RefreshCw, Search, ShieldCheck } from 'lucide-react'
import type { AssetDoc } from '../../api/types'
import { ApiError, api, mediaUrl } from '../../api/client'
import { queryClient, useAsset, useCorrect, useVocabularies } from '../../api/queries'
import { Button, IconButton } from '../../components/Button'
import { EmptyState, StatusText } from '../../components/EmptyState'
import { HumanMarker } from '../../components/HumanMarker'
import { Ic } from '../../components/Icon'
import { Menu, MenuItem, MenuPopover, MenuTrigger } from '../../components/Menu'
import { RightsBadge } from '../../components/RightsBadge'
import { Timecode } from '../../components/Timecode'
import { toast } from '../../components/Toast'
import { formatBytes, formatDate, formatDateTime, formatNumber, humanise, percent, plural, shortLabel, tidyNumbers } from '../../lib/format'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { stateFromBadge } from '../../lib/rights'
import { formatDuration, formatLength, fpsLabel, fpsTitle } from '../../lib/timecode'
import { useUi } from '../../lib/store'
import { Player, type PlayerHandle } from '../shot/Player'
import { Transcript } from '../shot/ShotPanels'
import { Filmstrip, type FilmstripHandle } from './Filmstrip'
import { CheckRightsNudge, OriginDetails } from './Origin'
import { DecoderLink } from '../ingest/DecoderLink'
import { colourFacts, decodedFromText, decodeErrors, needsDecoder } from '../../lib/formats'
import s from './Asset.module.css'

const STAGE_ORDER = ['raw', 'selects', 'finished']

/** Asset view (system.md §9.3, directions A3): one file's shot structure. */
export function AssetPage() {
  const { assetId } = useParams({ from: '/file/$assetId' })
  const search = useSearch({ from: '/file/$assetId' })
  const router = useRouter()
  const navigate = useNavigate()
  const processing = (a?: AssetDoc) => a?.status === 'processing'
  const asset = useAsset(assetId, { refetchInterval: 5000 })
  const a = asset.data
  const { label, vocabs } = useVocabularies()
  const correct = useCorrect()
  const player = useRef<PlayerHandle>(null)
  const strip = useRef<FilmstripHandle>(null)
  const [current, setCurrent] = useState(-1)
  const [io, setIo] = useState<{ i: number | null; o: number | null }>({ i: null, o: null })
  const cache = useUi((u) => u.resultCache)
  const order = useUi((u) => u.resultOrder)
  useDocumentTitle(asset.data?.filename ?? 'File')

  if (asset.isError && !a) {
    return (
      <EmptyState title="Couldn't open this file" role="alert" actions={<Button onPress={() => navigate({ to: '/library' })}>Library overview</Button>}>
        {(asset.error as Error).message}
      </EmptyState>
    )
  }
  if (!a) return <div className={s.page} aria-busy="true" />

  const st = a.structure ?? {}
  const edit = a.edit_type ?? st.edit_type
  const editCorrected = a.fields['structure.edit_type']?.corrected
  const shots = a.shots ?? []
  const startShot = search.shot ? shots.find((x) => x.uid === search.shot) : undefined
  const matches = order
    .map((u) => cache.get(u))
    .filter((r) => r && r.asset_uid === a.uid)
    .map((r) => ({ start: r!.in ?? r!.start, end: r!.out ?? r!.end, uid: r!.uid }))
  const rightsState = stateFromBadge(a.rights.badge)
  const hatch = rightsState === 'restricted' || rightsState === 'expiring' ? 'restricted' : rightsState === 'blocked' || rightsState === 'expired' ? 'blocked' : null
  const tech = a.technical as Record<string, string | number | boolean | null>
  const scores = edit?.scores ?? {}
  const maxScore = Math.max(0.001, ...Object.values(scores))
  // Evidence as a share of the total, not raw rule scores.
  const scoreSum = Math.max(0.001, Object.values(scores).reduce((x, y) => x + y, 0))
  const failed = a.processing.filter((p) => p.status === 'failed')
  const techFail = failed.find((p) => p.analyser === 'technical')
  const colour = colourFacts(tech)
  const decoded = decodedFromText(tech)
  const damaged = decodeErrors(a.fields)
  const pendingJobs = a.jobs.filter((j) => j.status !== 'failed')

  const setStage = async (term: string) => {
    try {
      await correct.mutateAsync({ field: 'structure.edit_type', op: 'set', value: term, asset_uid: a.uid })
      toast({ title: `Edit stage set to ${label('edit_type', term)}`, description: 'This stays as you set it, even if the file is re-analysed.' })
    } catch (e) {
      toast({ title: "Couldn't change the edit stage", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    }
  }

  const reprocess = async () => {
    try {
      const r = await api.post<{ enqueued: number }>(`/api/assets/${a.uid}/reprocess`, {})
      toast({ title: `Re-analysing ${a.filename}`, description: `${r.enqueued} steps queued. Your corrections are kept.`, tone: 'info' })
      queryClient.invalidateQueries({ queryKey: ['asset', a.uid] })
    } catch (e) {
      toast({ title: "Couldn't re-analyse", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    }
  }

  const stats: [string, string][] = [
    ['Shots', formatNumber(st.shot_count ?? shots.length)],
    ['Length', formatLength(a.duration)],
    ['Cuts / min', st.cuts_per_minute !== undefined ? st.cuts_per_minute.toFixed(1) : '—'],
    ['Avg shot', st.avg_shot_length !== undefined ? formatDuration(st.avg_shot_length) : '—'],
    ['Median shot', st.median_shot_length !== undefined ? formatDuration(st.median_shot_length) : '—'],
    ['Single take', st.single_take === undefined ? '—' : st.single_take ? 'Yes' : 'No'],
    ['Titles', st.titles === undefined ? '—' : st.titles ? 'Yes' : 'No'],
    ['Lower thirds', st.lower_thirds === undefined ? '—' : st.lower_thirds ? 'Yes' : 'No'],
    ['Music bed', st.music_bed === undefined ? '—' : st.music_bed ? `Yes (${percent(st.music_share)})` : 'No'],
    ['Speech', st.speech_share !== undefined ? percent(st.speech_share) : '—'],
    ['Loudness', st.integrated_lufs !== undefined && st.integrated_lufs !== null ? `${st.integrated_lufs.toFixed(1)} LUFS` : '—'],
    ['Transitions', st.transitions ? Object.entries(st.transitions).map(([k, v]) => `${v} ${k}${v === 1 ? '' : 's'}`).join(', ') : '—'],
  ]

  return (
    <div className={s.page}>
      <div className={s.head}>
        <IconButton icon={ArrowLeft} label="Back" onPress={() => router.history.back()} />
        <h1>{a.filename}</h1>
        <MenuTrigger>
          <Button variant="secondary" size="sm" iconEnd={ChevronDown} aria-label={`Edit stage: ${edit ? label('edit_type', edit.term) : 'not classified'}. Change`} data-testid="edit-stage">
            {edit ? label('edit_type', edit.term) : 'Edit stage'}
          </Button>
          <MenuPopover>
            <Menu aria-label="Set edit stage" onAction={(k) => setStage(String(k))}>
              {(vocabs.edit_type?.terms ?? []).map((t) => (
                <MenuItem key={t.id} id={t.id} checked={edit?.term === t.id}>
                  {shortLabel(t.label)}
                </MenuItem>
              ))}
            </Menu>
          </MenuPopover>
        </MenuTrigger>
        <span className={s.meta}>
          {plural2(st.shot_count ?? shots.length)} · {formatLength(a.duration)}
        </span>
        <RightsBadge state={rightsState} record={a.rights} />
        <Button variant="quiet" size="sm" icon={ShieldCheck} onPress={() => useUi.getState().set({ rightsDialog: { assetUids: [a.uid], title: a.filename } })}>
          Rights…
        </Button>
        <Button variant="quiet" size="sm" icon={Search} onPress={() => navigate({ to: '/search', search: { assets: a.uid } })}>
          Search this file
        </Button>
      </div>

      <div className={s.top}>
        {a.media.proxy ? (
          <Player
            ref={player}
            src={mediaUrl(a.media.proxy) as string}
            poster={mediaUrl(a.media.poster)}
            fps={a.fps}
            range={[0, a.duration]}
            boundaries={shots.map((x) => x.start)}
            startAt={startShot?.start ?? search.t ?? 0}
            inPoint={io.i}
            outPoint={io.o}
            onInOut={(i, o) => setIo({ i, o })}
            onTime={(t) => strip.current?.setTime(t)}
            onPrevShot={() => {
              const t = player.current?.time() ?? 0
              const prev = [...shots].reverse().find((x) => x.start < t - 0.1)
              player.current?.seek(prev?.start ?? 0)
            }}
            onNextShot={() => {
              const t = player.current?.time() ?? 0
              const next = shots.find((x) => x.start > t + 0.01)
              if (next) player.current?.seek(next.start)
            }}
            label={a.filename}
            testId="asset-player"
          />
        ) : techFail ? (
          <EmptyState inline icon={CircleAlert} title="Metachlorian can't read this file yet" role="alert" actions={<DecoderLink error={techFail.error} className={s.actionLink} />}>
            {techFail.error}
          </EmptyState>
        ) : (
          <EmptyState inline icon={LoaderCircle} title="Preparing a proxy">
            The proxy appears here as soon as it has been made. Analysis continues in the background.
          </EmptyState>
        )}
        <div className={s.side}>
          <div className={s.block}>
            <span className={s.blockHead}>Edit stage</span>
            {edit ? (
              <div className={s.block} data-testid="edit-type">
                <p>
                  <strong>{label('edit_type', edit.term)}</strong>{' '}
                  {editCorrected ? <HumanMarker by={a.fields['structure.edit_type']?.corrected_by} at={a.fields['structure.edit_type']?.corrected_at} /> : <span className={s.meta}>confidence {percent(edit.confidence)}</span>}
                </p>
                {STAGE_ORDER.filter((k) => k in scores).map((k) => (
                  <div key={k} className={`${s.stage} ${edit.term === k ? s.win : ''}`}>
                    <span>{label('edit_type', k)}</span>
                    <span className={s.bar} role="img" aria-label={`${label('edit_type', k)}: ${percent(scores[k] / scoreSum)} of the evidence`}>
                      <span className={s.fill} style={{ display: 'block', inlineSize: `${(scores[k] / maxScore) * 100}%` }} />
                    </span>
                    <span className={s.stageScore} title={`Rule score ${scores[k].toFixed(1)}`}>{percent(scores[k] / scoreSum)}</span>
                  </div>
                ))}
                <p className={s.meta} style={{ whiteSpace: 'normal' }}>
                  Evidence: {[st.single_take ? 'one continuous take' : st.cuts_per_minute !== undefined ? `${st.cuts_per_minute.toFixed(1)} cuts per minute` : null, st.titles ? 'titles' : null, st.lower_thirds ? 'lower thirds' : null, st.music_bed ? 'music bed' : null, st.loudness_normalised ? 'loudness normalised' : null, st.starts_or_ends_black ? 'starts or ends on black' : null].filter(Boolean).join(', ') || 'still being gathered'}
                </p>
              </div>
            ) : (
              <StatusText tone="info" icon={LoaderCircle}>
                Classified once shots and audio are analysed
              </StatusText>
            )}
          </div>
          <div className={s.block}>
            <span className={s.blockHead}>Summary</span>
            <p>{tidyNumbers(st.summary?.story || st.summary?.text || 'No summary yet.')}</p>
          </div>
          {a.origin && (
            <section className={s.block} aria-labelledby="origin-h">
              <h2 className={s.blockHead} id="origin-h">From the web</h2>
              <OriginDetails origin={a.origin} />
              {a.rights.status === 'unknown' && <CheckRightsNudge onCheck={() => useUi.getState().set({ rightsDialog: { assetUids: [a.uid], title: a.filename } })} />}
            </section>
          )}
          {damaged > 0 && (
            <div className={s.notice} role="note" data-testid="damaged-picture">
              <StatusText tone="caution" icon={ImageOff}>Damaged picture</StatusText>
              <p>
                Part of this file couldn't be decoded ({damaged} {damaged === 1 ? 'error' : 'errors'}), usually an interrupted recording or a bad card copy.
                The preview shows what could be read; copy the file from the card again if you can.
              </p>
            </div>
          )}
          <dl className={s.kv}>
            <dt>Path</dt>
            <dd className={s.mono}>{a.path}</dd>
            <dt>Video</dt>
            <dd className={s.mono}>
              <span title={fpsTitle(a.fps)}>{[a.width && a.height ? `${a.width}×${a.height}` : null, fpsLabel(a.fps), String(tech.video_codec ?? '').toUpperCase(), tech.bit_depth ? `${tech.bit_depth}-bit` : null, tech.hdr ? 'HDR' : 'SDR', tech.chroma].filter(Boolean).join(' · ')}</span>
            </dd>
            {colour.colour && (
              <>
                <dt>Colour</dt>
                <dd>{colour.colour}</dd>
              </>
            )}
            {colour.hdr && (
              <>
                <dt>HDR</dt>
                <dd>{colour.hdr}</dd>
              </>
            )}
            {decoded && (
              <>
                <dt>Decoded</dt>
                <dd data-testid="decoded-from">
                  Decoded from {decoded.format}
                  {decoded.decoder ? (
                    <>
                      {' '}with <code className={s.mono}>{decoded.decoder}</code>
                    </>
                  ) : null}
                </dd>
              </>
            )}
            <dt>Audio</dt>
            <dd className={s.mono}>{tech.audio_codec ? `${String(tech.audio_codec).toUpperCase()} · ${tech.audio_channels ?? '?'} ch · ${tech.audio_sample_rate ?? '?'} Hz` : 'None'}</dd>
            <dt>Size</dt>
            <dd className={s.mono}>{formatBytes(a.size)}</dd>
            <dt>Shot on</dt>
            <dd>{tech.capture_date ? formatDate(String(tech.capture_date).slice(0, 10)) : 'Unknown'}{tech.camera_model ? ` · ${tech.camera_make ?? ''} ${tech.camera_model}` : ''}</dd>
            <dt>Ingested</dt>
            <dd>{formatDateTime(a.created_at)}</dd>
            <dt>Processing</dt>
            <dd>
              {processing(a) ? (
                <StatusText tone="info" icon={LoaderCircle}>
                  Analysing · {plural(pendingJobs.length, 'step')} left
                </StatusText>
              ) : a.status === 'updating' ? (
                <StatusText tone="info" icon={RefreshCw}>
                  Searchable · updating {plural(pendingJobs.length, 'step')}
                </StatusText>
              ) : failed.length ? (
                <>
                  <StatusText tone="blocked">{plural(failed.length, 'step')} failed</StatusText> <DecoderLink error={techFail?.error} className={s.actionLink} />
                </>
              ) : (
                <StatusText tone="cleared">Analysed</StatusText>
              )}{' '}
              <Button variant="quiet" size="sm" icon={RefreshCw} onPress={reprocess}>
                Re-analyse
              </Button>
            </dd>
          </dl>
        </div>
      </div>

      {shots.length > 0 && a.duration > 0 && (
        <Filmstrip
          ref={strip}
          filename={a.filename}
          duration={a.duration}
          fps={a.fps}
          shots={shots}
          sprites={a.media.sprites}
          matches={matches}
          rightsHatch={hatch}
          inOut={io.i !== null && io.o !== null ? [io.i, io.o] : null}
          onSeek={(t) => player.current?.seek(t)}
          onOpenShot={(uid) => navigate({ to: '/shot/$shotId', params: { shotId: uid } })}
          onShotChange={setCurrent}
        />
      )}

      <div className={s.section}>
        <span className={s.blockHead}>Structure</span>
        <div className={s.stats}>
          {stats.map(([k, v]) => (
            <div key={k} className={s.stat}>
              <span className={s.statLabel}>{k}</span>
              <span className={s.statValue}>{v}</span>
            </div>
          ))}
          {st.roles && (
            <div className={s.stat} style={{ gridColumn: 'span 2' }}>
              <span className={s.statLabel}>Roles</span>
              <span>{Object.entries(st.roles).sort((x, y) => y[1] - x[1]).map(([k, v]) => `${label('shot_role', k)} ${v}`).join(' · ')}</span>
            </div>
          )}
        </div>
      </div>

      <div className={s.section}>
        <span className={s.blockHead}>Shots</span>
        {shots.length ? (
          <div className={s.tableWrap}>
            <table className={s.table} aria-label={`Shots in ${a.filename}`}>
              <thead>
                <tr>
                  <th className={s.num}>#</th>
                  <th />
                  <th>In</th>
                  <th>Out</th>
                  <th className={s.num}>Dur</th>
                  <th>Shot size</th>
                  <th>Movement</th>
                  <th>Time</th>
                  <th>Role</th>
                  <th>Description</th>
                </tr>
              </thead>
              <tbody>
                {shots.map((x, i) => (
                  <tr
                    key={x.uid}
                    data-current={i === current}
                    tabIndex={0}
                    onClick={() => player.current?.seek(x.start)}
                    onDoubleClick={() => navigate({ to: '/shot/$shotId', params: { shotId: x.uid } })}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter') navigate({ to: '/shot/$shotId', params: { shotId: x.uid } })
                      if (e.key === ' ') {
                        e.preventDefault()
                        player.current?.seek(x.start)
                      }
                    }}
                    aria-label={`Shot ${x.idx + 1}`}
                  >
                    <td className={s.num}>{x.idx + 1}</td>
                    <td>{x.thumb ? <img className={s.thumb} src={mediaUrl(x.thumb)} alt="" loading="lazy" /> : null}</td>
                    <td><Timecode seconds={x.start} fps={a.fps} size="xs" /></td>
                    <td><Timecode seconds={x.end} fps={a.fps} size="xs" /></td>
                    <td className={s.num}>{formatDuration(x.duration)}</td>
                    <td>{x.shot_size ? label('shot_size', x.shot_size) : '—'}</td>
                    <td>{x.camera_movement?.length ? x.camera_movement.slice(0, 2).map((m) => label('camera_movement', m.term)).join(', ') : '—'}</td>
                    <td>{x.time_of_day ? label('time_of_day', x.time_of_day) : '—'}</td>
                    <td>{x.role?.length ? label('shot_role', x.role[0].term) : '—'}</td>
                    <td className={s.ellip}>
                      {x.caption ?? ''}
                      {x.corrected?.length ? ' ✎' : ''}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <StatusText tone="info" icon={LoaderCircle}>
            Shots appear once shot detection has run.
          </StatusText>
        )}
      </div>

      <div className={s.cols}>
        <div className={s.block}>
          <span className={s.blockHead}>Transcript</span>
          <Transcript segments={a.transcript} fps={a.fps} onSeek={(t) => player.current?.seek(t)} />
        </div>
        <div className={s.block}>
          <span className={s.blockHead}>Processing</span>
          <div className={s.runs}>
            {a.processing.map((p) => (
              <StatusText key={p.analyser} tone={p.status === 'done' ? 'neutral' : p.status === 'failed' ? 'blocked' : p.status === 'unavailable' ? 'caution' : 'info'}>
                {p.analyser} {p.status === 'done' ? `· ${(p.seconds ?? 0).toFixed(1)} s` : `· ${p.status}`}
              </StatusText>
            ))}
            {pendingJobs.map((j) => (
              <StatusText key={j.analyser} tone="info" icon={LoaderCircle}>
                {j.analyser} · {j.status}
              </StatusText>
            ))}
          </div>
          {failed.map((f) => (
            <p key={f.analyser} style={{ color: 'var(--status-blocked)', fontSize: 'var(--text-sm)' }}>
              <Ic icon={RefreshCw} size={14} /> {humanise(f.analyser)} failed: {f.error}{' '}
              {needsDecoder(f.error) && <DecoderLink error={f.error} className={s.actionLink} />}
            </p>
          ))}
          <p className={s.meta}>
            <Link to="/ingest">Ingest and processing</Link>
          </p>
        </div>
      </div>
    </div>
  )
}

function plural2(n: number) {
  return `${formatNumber(n)} shot${n === 1 ? '' : 's'}`
}
