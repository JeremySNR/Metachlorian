import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useRouter } from '@tanstack/react-router'
import { ArrowLeft, ChevronLeft, ChevronRight, ScanSearch } from 'lucide-react'
import { mediaUrl } from '../../api/client'
import { useShot, useVocabularies } from '../../api/queries'
import { Button, IconButton } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { RightsBadge } from '../../components/RightsBadge'
import { TimecodeRange } from '../../components/Timecode'
import { useDocumentKeys, isTyping } from '../../hooks/useHotkeys'
import { humanise } from '../../lib/format'
import { rememberRecentShot, usePrefs, useUi } from '../../lib/store'
import { Player, type PlayerHandle } from './Player'
import { SignalTable } from './SignalTable'
import { AddToCollectionButton, ExportMenu, InCollections, Moments, RightsBlock, Section, shotRightsState, SimilarStrip, Transcript, WhyMatched } from './ShotPanels'
import { techSummary } from './techSummary'
import t from '../../styles/type.module.css'
import s from './Shot.module.css'

/** Shot detail (system.md §9.2, directions A2). */
export function ShotPage() {
  const { shotId } = useParams({ from: '/shot/$shotId' })
  const navigate = useNavigate()
  const router = useRouter()
  const shot = useShot(shotId)
  const { vocabs, label } = useVocabularies()
  const player = useRef<PlayerHandle>(null)
  const [io, setIo] = useState<{ uid: string; i: number | null; o: number | null }>({ uid: shotId, i: null, o: null })
  const [now, setNow] = useState(0)
  const order = useUi((u) => u.resultOrder)
  const result = useUi((u) => u.resultCache.get(shotId))
  const lastQuery = useUi((u) => u.lastQuery)
  const d = shot.data
  const inOut = io.uid === shotId ? io : { uid: shotId, i: null, o: null }

  useEffect(() => {
    rememberRecentShot(shotId)
    requestAnimationFrame(() => player.current?.focus())
  }, [shotId])

  const pos = order.indexOf(shotId)
  const prevResult = pos > 0 ? order[pos - 1] : undefined
  const nextResult = pos >= 0 && pos < order.length - 1 ? order[pos + 1] : undefined
  const goShot = (uid?: string) => uid && navigate({ to: '/shot/$shotId', params: { shotId: uid }, replace: true })

  useDocumentKeys((e) => {
    if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey || !usePrefs.getState().singleKeys) return
    if ((e.target as HTMLElement).closest('[data-testid="signals"], [role="group"]')) return
    if (e.key === '[') goShot(prevResult)
    else if (e.key === ']') goShot(nextResult)
    else if (e.key.toLowerCase() === 's' && d) navigate({ to: '/search', search: { similar: d.uid } })
    else if (e.key === 'Escape' && !document.querySelector('[role="dialog"]')) router.history.back()
  })

  if (shot.isError && !d) {
    return (
      <EmptyState title="Couldn't open this shot" role="alert" actions={<Button onPress={() => navigate({ to: '/search' })}>Back to search</Button>}>
        {(shot.error as Error).message}. It may have been re-segmented; search again to find it.
      </EmptyState>
    )
  }
  if (!d) return <div className={s.page} aria-busy="true" />

  const fps = d.technical.fps
  const state = shotRightsState(d)
  const edit = typeof d.edit_type === 'object' && d.edit_type ? d.edit_type.term : (d.edit_type as string | null)
  const shotCount = undefined as number | undefined

  return (
    <div className={s.page}>
      <div className={s.pageHead}>
        <IconButton icon={ArrowLeft} label="Back" shortcut="Esc" onPress={() => router.history.back()} />
        <div className={s.crumbs}>
          <Link to="/file/$assetId" params={{ assetId: d.asset_uid }} search={{ shot: d.uid }} className={t.ui} style={{ color: 'var(--fg-2)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {d.filename}
          </Link>
          <span className={s.sep} aria-hidden="true">›</span>
          <h1>
            Shot {d.idx + 1}
            {shotCount ? ` of ${shotCount}` : ''}
          </h1>
        </div>
        {edit && <span className={t.slate}>{humanise(edit)}</span>}
        <RightsBadge state={state} record={d.rights} reasons={d.rights_check?.reasons} />
        {order.length > 0 && pos >= 0 && (
          <>
            <IconButton icon={ChevronLeft} label="Previous result" shortcut="[" isDisabled={!prevResult} onPress={() => goShot(prevResult)} />
            <span className={t.slate}>
              {pos + 1} / {order.length}
            </span>
            <IconButton icon={ChevronRight} label="Next result" shortcut="]" isDisabled={!nextResult} onPress={() => goShot(nextResult)} />
          </>
        )}
      </div>
      <main className={s.left} id="main" aria-label="Shot">
        <div className={s.playerWrap}>
          <Player
            key={d.uid}
            ref={player}
            src={mediaUrl(d.media.proxy) as string}
            poster={mediaUrl(d.media.poster)}
            fps={fps}
            range={[d.start, d.end]}
            startAt={result?.in ?? d.start}
            inPoint={inOut.i}
            outPoint={inOut.o}
            onInOut={(i, o) => setIo({ uid: d.uid, i, o })}
            onPrevShot={d.neighbours.previous ? () => goShot(d.neighbours.previous) : undefined}
            onNextShot={d.neighbours.next ? () => goShot(d.neighbours.next) : undefined}
            onPrevResult={prevResult ? () => goShot(prevResult) : undefined}
            onNextResult={nextResult ? () => goShot(nextResult) : undefined}
            onTime={(tt) => {
              if (Math.abs(tt - now) > 0.2) setNow(tt)
            }}
            label={`${d.filename}, shot ${d.idx + 1}`}
            testId="shot-player"
          />
        </div>
        <Section title="Why it matched" id="why2">
          <WhyMatched why={result?.why ?? []} label={label} query={lastQuery} />
        </Section>
        <Section title="Transcript" id="tr">
          <Transcript segments={d.transcript} fps={fps} onSeek={(tt) => player.current?.seek(tt)} current={now} />
        </Section>
        <Section title="Moments" id="mo">
          <Moments moments={d.moments} fps={fps} onSeek={(tt) => player.current?.seek(tt)} />
        </Section>
        <Section
          title="Similar shots"
          id="sim"
          action={
            <Button variant="quiet" size="sm" icon={ScanSearch} shortcut="S" onPress={() => navigate({ to: '/search', search: { similar: d.uid } })}>
              See all
            </Button>
          }
        >
          <SimilarStrip uid={d.uid} limit={8} />
        </Section>
      </main>
      <aside className={s.right} aria-label="Shot details">
        <div className={s.section}>
          <p className={s.desc}>{d.summary.caption || d.summary.summary || 'No description yet.'}</p>
          <TimecodeRange inS={d.start} outS={d.end} fps={fps} copyable />
          <div className={s.techLine}>{techSummary(d)}</div>
        </div>
        <div className={s.actions}>
          <AddToCollectionButton uids={[d.uid]} inPoint={inOut.i} outPoint={inOut.o} />
          <ExportMenu shot={d} inPoint={inOut.i} outPoint={inOut.o} state={state} />
        </div>
        <Section title="Signals" id="sig2" action={<span className={t.slate}>E edits</span>}>
          <SignalTable shot={d} vocabs={vocabs} label={label} />
        </Section>
        <Section title="Rights" id="r2">
          <RightsBlock shot={d} vocabs={vocabs} />
        </Section>
        <Section title="In collections" id="c2">
          <InCollections uid={d.uid} />
        </Section>
        <Section title="File" id="f2">
          <dl className={s.kv}>
            <dt>Name</dt>
            <dd>
              <Link to="/file/$assetId" params={{ assetId: d.asset_uid }} search={{ shot: d.uid }}>
                {d.filename}
              </Link>
            </dd>
            <dt>Edit stage</dt>
            <dd>{edit ? humanise(edit) : 'Not classified yet'}</dd>
            <dt>Path</dt>
            <dd style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>{d.path}</dd>
          </dl>
        </Section>
      </aside>
    </div>
  )
}
