import { useMemo, useState, type ReactNode } from 'react'
import { Link } from '@tanstack/react-router'
import { useQueries } from '@tanstack/react-query'
import { ChevronDown, Download, Layers, Plus, ShieldCheck } from 'lucide-react'
import type { IntendedUse, Moment, SearchResult, ShotDoc, TranscriptSegment, Verdict, Vocabulary, WhyItem } from '../../api/types'
import { api, mediaUrl, ApiError } from '../../api/client'
import { checkRights, exportClip, useAddToCollection, useCollections, useSimilar, useVocabularies } from '../../api/queries'
import { buildPhraseIndex, locateTerm } from '../../lib/chips'
import type { Collection } from '../../api/types'
import { Button } from '../../components/Button'
import { ConfidenceMeter } from '../../components/ConfidenceMeter'
import { Select } from '../../components/Field'
import { Menu, MenuItem, MenuPopover, MenuSeparator, MenuTrigger } from '../../components/Menu'
import { RightsFull, RightsBadge } from '../../components/RightsBadge'
import { toast } from '../../components/Toast'
import { Timecode } from '../../components/Timecode'
import { Snippet } from '../search/ResultsGrid'
import { formatDate, humanise, shortLabel } from '../../lib/format'
import { stateFromBadge, stateFromVerdict, describeRights, COMMON_TERRITORIES, type RightsState } from '../../lib/rights'
import { formatDuration, formatTimecode } from '../../lib/timecode'
import { usePrefs, useUi } from '../../lib/store'
import t from '../../styles/type.module.css'
import s from './Shot.module.css'

export function Section({ title, action, children, id }: { title: string; action?: ReactNode; children: ReactNode; id?: string }) {
  return (
    <section className={s.section} aria-labelledby={id ? `${id}-h` : undefined}>
      <div className={s.sectionHead}>
        <h3 className={t.slate} id={id ? `${id}-h` : undefined}>
          {title}
        </h3>
        {action}
      </div>
      {children}
    </section>
  )
}

// ---------------------------------------------------------------- why it matched
const SIGNAL_NAME: Record<string, string> = {
  shot_size: 'shot size',
  camera_movement: 'movement',
  time_of_day: 'time of day',
  shot_role: 'role',
  audio_class: 'audio',
  edit_type: 'edit stage',
}

export function WhyMatched({ why, label, query }: { why: WhyItem[]; label: (v: string, t: string) => string; query?: string }) {
  const { vocabs } = useVocabularies()
  const index = useMemo(() => buildPhraseIndex(vocabs), [vocabs])
  const words = (vocab: string, term?: string) => (query && term ? locateTerm(query, index, vocab, term)?.text : undefined)
  if (!why.length) return <p className={s.empty}>Open this shot from a search to see why it matched.</p>
  return (
    <div className={s.why} data-testid="why">
      {query && (
        <p style={{ color: 'var(--fg-2)', fontSize: 'var(--text-sm)' }}>
          For “{query}”
        </p>
      )}
      {why.map((w, i) => {
        const field = SIGNAL_NAME[w.signal] ?? w.signal.replace(/_/g, ' ')
        const isVocab = Boolean(w.term)
        const value = w.term ? label(w.signal, w.term) : null
        const from = words(w.signal, w.term)
        return (
          <div key={i} className={s.whyRow}>
            <span className={w.missing ? s.whyMissing : s.whyText}>
              {from && <span style={{ color: 'var(--fg-2)' }}>“{from}” → </span>}
              {isVocab ? (
                w.missing ? (
                  <>
                    <em>{field}:</em> not labelled {value}
                  </>
                ) : (
                  <>
                    <em>{field}:</em> {value} {w.source === 'human' ? <em>(corrected by a person)</em> : null}
                  </>
                )
              ) : w.signal === 'keywords' ? (
                <>
                  <em>words:</em> {w.detail.replace('words matched in the ', 'matched in the ')}
                  {w.snippet && (
                    <>
                      <br />
                      <Snippet text={w.snippet} className={s.whyText} />
                    </>
                  )}
                </>
              ) : w.signal === 'visual similarity' ? (
                <>
                  <em>looks like:</em> the description, visual match {(w.detail.match(/rank (\d+)/) ?? [])[1] ? `#${(w.detail.match(/rank (\d+)/) ?? [])[1]}` : ''}
                </>
              ) : w.signal === 'similar shot' ? (
                <>
                  <em>looks like:</em> the example shot
                </>
              ) : (
                <>
                  <em>{w.signal}:</em> {w.detail}
                </>
              )}
            </span>
            {w.source === 'human' ? (
              <span className={t.slate}>Human</span>
            ) : typeof w.confidence === 'number' ? (
              <ConfidenceMeter value={w.confidence} label={field} />
            ) : typeof w.score === 'number' && w.signal !== 'keywords' ? (
              <span className={t.slate}>Vision model</span>
            ) : null}
          </div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------- rights
export function shotRightsState(shot: ShotDoc): RightsState {
  if (shot.rights_check) return stateFromVerdict(shot.rights_check.verdict, shot.rights_check.reasons, shot.rights.expires)
  return stateFromBadge(shot.rights.badge)
}

export function RightsBlock({ shot, vocabs, intended }: { shot: ShotDoc; vocabs: Record<string, Vocabulary>; intended?: IntendedUse | null }) {
  const r = shot.rights
  const state = shotRightsState(shot)
  const lbl = (v: string, x: string) => shortLabel(vocabs[v]?.terms.find((y) => y.id === x)?.label ?? humanise(x))
  const lines: ReactNode[] = []
  if (r.level === 'shot') lines.push('Shot override (other shots follow the file)')
  if (r.licence || r.owner) lines.push([r.licence, r.owner].filter(Boolean).join(' · '))
  if (r.permitted_uses?.length) lines.push(`Uses: ${r.permitted_uses.map((u) => lbl('usage', u)).join(', ')}`)
  if (r.channels?.length) lines.push(`Channels: ${r.channels.map((c) => lbl('channel', c)).join(', ')}`)
  if (r.territories?.length) lines.push(`Territories: ${r.territories.join(', ')}${r.excluded_territories?.length ? ` (not ${r.excluded_territories.join(', ')})` : ''}`)
  if (r.status !== 'unknown') lines.push(`Expires ${r.expires ? formatDate(r.expires) : 'never'}`)
  if (r.status !== 'unknown') lines.push(`Model release: ${lbl('release_status', r.model_release)} · Property release: ${lbl('release_status', r.property_release)}`)
  if (r.attribution) lines.push(`Credit: ${r.attribution}`)
  if (shot.rights_check && intended) lines.unshift(`For ${[intended.use, intended.channel, intended.territory].filter(Boolean).join(' · ')}: ${shot.rights_check.reasons.join(' ')}`)
  return (
    <div className={s.section}>
      <RightsFull
        state={state}
        record={r}
        reasons={shot.rights_check?.reasons}
        lines={lines}
        action={
          <Button variant="quiet" size="sm" shortcut="R" onPress={() => useUi.getState().set({ rightsDialog: { assetUids: [shot.asset_uid], shotUid: shot.uid, title: `${shot.filename} · shot ${shot.idx + 1}` } })}>
            Change
          </Button>
        }
      />
      <RightsCheck shot={shot} vocabs={vocabs} />
    </div>
  )
}

function RightsCheck({ shot, vocabs }: { shot: ShotDoc; vocabs: Record<string, Vocabulary> }) {
  const def = usePrefs.getState().defaultUse
  const [use, setUse] = useState(def.use ?? '')
  const [channel, setChannel] = useState(def.channel ?? '')
  const [territory, setTerritory] = useState(def.territory ?? '')
  const [result, setResult] = useState<{ verdict: Verdict; reasons: string[] } | null>(null)
  const [open, setOpen] = useState(false)
  const run = async () => {
    try {
      const res = await checkRights({ shot_uids: [shot.uid], use: use || null, channel: channel || null, territory: territory || null })
      setResult({ verdict: res.verdict, reasons: res.items[0]?.reasons ?? [] })
    } catch (e) {
      toast({ title: "Couldn't check rights", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    }
  }
  if (!open)
    return (
      <Button variant="quiet" size="sm" icon={ShieldCheck} onPress={() => setOpen(true)} className={undefined}>
        Check a use
      </Button>
    )
  const st = result ? stateFromVerdict(result.verdict, result.reasons, shot.rights.expires) : null
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
      <Select label="Use" slateLabel options={[{ id: '', label: 'Any use' }, ...(vocabs.usage?.terms ?? []).map((x) => ({ id: x.id, label: shortLabel(x.label) }))]} selectedKey={use} onSelectionChange={(k) => setUse(String(k))} />
      <Select label="Channel" slateLabel options={[{ id: '', label: 'Any channel' }, ...(vocabs.channel?.terms ?? []).map((x) => ({ id: x.id, label: shortLabel(x.label) }))]} selectedKey={channel} onSelectionChange={(k) => setChannel(String(k))} />
      <Select label="Territory" slateLabel options={[{ id: '', label: 'Any territory' }, ...COMMON_TERRITORIES.map(([c, n]) => ({ id: c, label: `${c} · ${n}` }))]} selectedKey={territory} onSelectionChange={(k) => setTerritory(String(k))} />
      <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center', flexWrap: 'wrap' }}>
        <Button variant="secondary" size="sm" onPress={run}>
          Check
        </Button>
        {st && <RightsBadge state={st} reasons={result?.reasons} />}
      </div>
      {result && <p style={{ fontSize: 'var(--text-xs)', color: 'var(--fg-2)' }} role="status">{result.reasons.join(' ')}</p>}
    </div>
  )
}

// ---------------------------------------------------------------- transcript and moments
export function Transcript({ segments, fps, onSeek, current }: { segments: TranscriptSegment[]; fps: number | null; onSeek: (t: number) => void; current?: number }) {
  if (!segments.length) return <p className={s.empty}>No speech in this shot.</p>
  return (
    <div className={s.transcript} data-testid="transcript">
      {segments.map((seg, i) => (
        <div key={i} className={s.seg}>
          <button type="button" className={s.segTime} onClick={() => onSeek(seg.start)} aria-label={`Play from ${formatTimecode(seg.start, fps)}`}>
            {formatTimecode(seg.start, fps).slice(3)}
          </button>
          <p>
            {seg.words?.length
              ? seg.words.map((w, k) => {
                  const st = w.s ?? w.start ?? seg.start
                  const en = w.e ?? w.end ?? seg.end
                  return (
                    <span key={k}>
                      <button type="button" className={s.word} data-current={current !== undefined && current >= st && current < en ? 'true' : undefined} onClick={() => onSeek(st)} title={formatTimecode(st, fps)}>
                        {w.w ?? w.word ?? w.text}
                      </button>{' '}
                    </span>
                  )
                })
              : seg.text}
          </p>
        </div>
      ))}
    </div>
  )
}

const MOMENT_LABEL: Record<string, string> = { speech: 'Speech', text: 'Text', face: 'Face', faces: 'Faces', sound: 'Sound', event: 'Sound', person: 'Person' }

export function Moments({ moments, fps, onSeek }: { moments: Moment[]; fps: number | null; onSeek: (t: number) => void }) {
  const grouped = useMemo(() => {
    const out: Moment[] = []
    for (const m of moments) {
      const prev = out[out.length - 1]
      if (prev && prev.kind === m.kind && m.kind === 'text' && Math.abs(prev.start - m.start) < 0.05) {
        prev.text = `${prev.text ?? ''} ${m.text ?? ''}`.trim()
        continue
      }
      out.push({ ...m })
    }
    return out
  }, [moments])
  if (!grouped.length) return <p className={s.empty}>No moments found.</p>
  return (
    <div className={s.moments}>
      {grouped.slice(0, 40).map((m, i) => (
        <button key={i} type="button" className={s.moment} onClick={() => onSeek(m.start)}>
          <span className={s.momentKind}>{MOMENT_LABEL[m.kind] ?? humanise(m.kind)}</span>
          <span style={{ minInlineSize: 0, overflowWrap: 'anywhere' }}>{m.text || humanise(m.kind)}</span>
          <Timecode seconds={m.start} fps={fps} size="xs" />
        </button>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------- similar shots
export function SimilarStrip({ uid, limit = 8 }: { uid: string; limit?: number }) {
  const q = useSimilar(uid, limit)
  if (q.isLoading) return <div className={s.similar}>{Array.from({ length: Math.min(limit, 4) }, (_, i) => <span key={i} className={s.simWell} />)}</div>
  const results = q.data?.results ?? []
  if (!results.length) return <p className={s.empty}>{q.isError ? "Couldn't load similar shots." : 'Nothing visually similar yet.'}</p>
  return (
    <div className={s.similar} data-testid="similar">
      {results.slice(0, limit).map((r: SearchResult) => (
        <Link key={r.uid} to="/shot/$shotId" params={{ shotId: r.uid }} className={s.simCard} aria-label={`${r.caption ?? r.filename}, ${formatDuration(r.duration)}`}>
          {r.thumb ? <img src={mediaUrl(r.thumb)} alt="" loading="lazy" decoding="async" /> : <span className={s.simWell} />}
          <span className={s.simMeta}>
            <Timecode seconds={r.start} fps={r.fps} size="xs" />
            <span>{formatDuration(r.duration)}</span>
          </span>
          <span className={s.simTitle}>{r.caption ?? r.filename}</span>
        </Link>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------- collections
export function InCollections({ uid }: { uid: string }) {
  const cols = useCollections()
  const details = useQueries({
    queries: (cols.data ?? []).slice(0, 30).map((c) => ({ queryKey: ['collection', c.uid], queryFn: () => api.get<Collection>(`/api/collections/${c.uid}`), staleTime: 30_000 })),
  })
  const inIt = details.map((d) => d.data).filter((c): c is Collection => Boolean(c && c.items.some((i) => i.shot.uid === uid)))
  return (
    <div className={s.chips}>
      {inIt.length ? (
        inIt.map((c) => (
          <Link key={c.uid} to="/collections/$collectionId" params={{ collectionId: c.uid }} className={s.colChip}>
            <Layers size={14} strokeWidth={2} aria-hidden="true" />
            {c.name}
          </Link>
        ))
      ) : (
        <span className={s.empty}>Not in a collection yet.</span>
      )}
    </div>
  )
}

export function AddToCollectionButton({ uids, inPoint, outPoint }: { uids: string[]; inPoint?: number | null; outPoint?: number | null }) {
  const cols = useCollections()
  const add = useAddToCollection()
  const active = usePrefs((p) => p.activeCollection)
  const target = cols.data?.find((c) => c.uid === active) ?? cols.data?.[0]
  const addTo = async (uid: string, name: string) => {
    try {
      await add.mutateAsync({ uid, shot_uids: uids, in: inPoint ?? null, out: outPoint ?? null })
      usePrefs.getState().set({ activeCollection: uid })
      toast({ title: `Added to ${name}${inPoint != null || outPoint != null ? ' with your in and out points' : ''}` })
    } catch (e) {
      toast({ title: "Couldn't add to the collection", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    }
  }
  return (
    <div style={{ display: 'flex', gap: 'var(--space-1)' }}>
      {target && (
        <Button variant="secondary" icon={Plus} shortcut="B" busy={add.isPending} onPress={() => addTo(target.uid, target.name)}>
          {`Add to ${target.name}`}
        </Button>
      )}
      <Button variant="secondary" iconEnd={ChevronDown} onPress={() => useUi.getState().set({ addToDialog: uids })} aria-label="Add to another collection">
        {target ? 'Add to…' : 'Add to collection…'}
      </Button>
    </div>
  )
}

// ---------------------------------------------------------------- export
const EXPORTS: { mode: 'proxy' | 'file' | 'otio' | 'fcpxml' | 'edl' | 'reference'; label: string }[] = [
  { mode: 'proxy', label: 'Proxy clip (MP4)' },
  { mode: 'file', label: 'Trimmed original' },
  { mode: 'otio', label: 'OpenTimelineIO (.otio)' },
  { mode: 'fcpxml', label: 'FCPXML 1.10' },
  { mode: 'edl', label: 'CMX 3600 EDL' },
  { mode: 'reference', label: 'Copy reference (JSON)' },
]

export function ExportMenu({ shot, inPoint, outPoint, state }: { shot: ShotDoc; inPoint: number | null; outPoint: number | null; state: RightsState }) {
  const [busy, setBusy] = useState(false)
  const run = async (mode: (typeof EXPORTS)[number]['mode']) => {
    setBusy(true)
    try {
      const res = await exportClip({ shot_uid: shot.uid, in: inPoint, out: outPoint, mode })
      if (mode === 'reference') {
        await navigator.clipboard?.writeText(JSON.stringify(res.reference, null, 2)).catch(() => undefined)
        toast({ title: 'Copied the shot reference', tone: 'info' })
      } else if (res.download) {
        const a = document.createElement('a')
        a.href = mediaUrl(res.download) as string
        a.download = ''
        document.body.appendChild(a)
        a.click()
        a.remove()
        toast({ title: 'Export ready', description: res.file?.split('/').pop() })
      }
    } catch (e) {
      toast({ title: "Couldn't export", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    } finally {
      setBusy(false)
    }
  }
  const warn = state === 'blocked' || state === 'expired' || state === 'unknown'
  return (
    <MenuTrigger>
      <Button variant="secondary" icon={Download} iconEnd={ChevronDown} busy={busy} data-testid="export-clip">
        Export clip
      </Button>
      <MenuPopover placement="bottom end">
        <Menu aria-label="Export clip" onAction={(k) => run(k as (typeof EXPORTS)[number]['mode'])}>
          {EXPORTS.map((x, i) => [
            i === 2 || i === 5 ? <MenuSeparator key={`sep${i}`} /> : null,
            <MenuItem key={x.mode} id={x.mode}>
              {x.label}
            </MenuItem>,
          ])}
        </Menu>
        {warn && <p style={{ padding: 'var(--space-2) var(--space-3)', fontSize: 'var(--text-xs)', color: 'var(--status-caution)', maxInlineSize: 280 }}>{describeRights(state).long}. Check before using it.</p>}
      </MenuPopover>
    </MenuTrigger>
  )
}
