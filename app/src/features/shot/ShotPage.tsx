import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams, useRouter } from '@tanstack/react-router'
import { ArrowLeft, ChevronLeft, ChevronRight, ScanSearch } from 'lucide-react'
import { api, ApiError, mediaUrl } from '../../api/client'
import type { SearchResponse } from '../../api/types'
import { toast } from '../../components/Toast'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
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
import { OriginDetails } from '../asset/Origin'
import { AddToCollectionButton, BlockedNote, ExportMenu, InCollections, Moments, RightsBlock, Section, shotRightsState, SimilarStrip, Transcript, WhyMatched } from './ShotPanels'
import { techSummary } from './techSummary'
import { ShotPeople } from '../people/ShotPeople'
import { FolderCrumbs } from '../search/FolderCrumbs'
import { dirname } from '../../lib/folders'
import { hasScope, mergeScopes, scopeList, scopeTokens } from '../../lib/scope'
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
  const resultTotal = useUi((u) => u.resultTotal)
  const paging = useUi((u) => u.resultPaging)
  const [loadingMore, setLoadingMore] = useState(false)
  const d = shot.data
  useDocumentTitle(d ? `Shot ${d.idx + 1}` : 'Shot', d?.filename)
  const inOut = io.uid === shotId ? io : { uid: shotId, i: null, o: null }
  // Similar shots stay inside the last search's folder or collection (chosen, or written as folder:"…").
  const lastScope = mergeScopes({ folder: scopeList(paging?.req.filters?.folder), collection: scopeList(paging?.req.filters?.collection) }, scopeTokens(paging?.req.q))
  const scoped = hasScope(lastScope)
  const scopeParams = scoped ? { folder: lastScope.folder.length ? lastScope.folder : undefined, collection: lastScope.collection.length ? lastScope.collection : undefined } : {}

  useEffect(() => {
    rememberRecentShot(shotId)
    requestAnimationFrame(() => player.current?.focus())
  }, [shotId])

  const pos = order.indexOf(shotId)
  const prevResult = pos > 0 ? order[pos - 1] : undefined
  const nextResult = pos >= 0 && pos < order.length - 1 ? order[pos + 1] : undefined
  // The pager counts every result of the search; past the loaded page it fetches the next one.
  const canLoadMore = pos >= 0 && pos === order.length - 1 && Boolean(paging?.next)
  const goShot = (uid?: string) => uid && navigate({ to: '/shot/$shotId', params: { shotId: uid }, replace: true })
  const loadNext = async () => {
    if (!paging?.next || loadingMore) return
    setLoadingMore(true)
    try {
      const page = await api.post<SearchResponse>('/api/search', { ...paging.req, cursor: paging.next })
      useUi.getState().appendResults(page.results, page.next_cursor)
      if (page.results[0]) goShot(page.results[0].uid)
    } catch (e) {
      toast({ title: "Couldn't load more results", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    } finally {
      setLoadingMore(false)
    }
  }
  const goNext = () => (nextResult ? goShot(nextResult) : canLoadMore ? loadNext() : undefined)

  useDocumentKeys((e) => {
    if (isTyping(e.target) || e.metaKey || e.ctrlKey || e.altKey || !usePrefs.getState().singleKeys) return
    if ((e.target as HTMLElement).closest('[data-testid="signals"], [role="group"]')) return
    if (e.key === '[') goShot(prevResult)
    else if (e.key === ']') goNext()
    else if (e.key.toLowerCase() === 's' && d) navigate({ to: '/search', search: { similar: d.uid, ...scopeParams } })
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
  const iu = paging?.req.intended_use
  const similarRights = { use: iu?.use ?? null, channel: iu?.channel ?? null, territory: iu?.territory ?? null, include: iu?.include ?? null, hideBlocked: paging?.req.hide_blocked ?? true, ...(scoped ? { scope: lastScope } : {}) }
  const similarSearch = { similar: d.uid, ...scopeParams }
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
            <span className={t.slate} aria-label={`Result ${pos + 1} of ${Math.max(resultTotal, order.length)}`}>
              {pos + 1} / {Math.max(resultTotal, order.length)}
            </span>
            <IconButton icon={ChevronRight} label="Next result" shortcut="]" isDisabled={(!nextResult && !canLoadMore) || loadingMore} onPress={goNext} />
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
            onNextResult={nextResult || canLoadMore ? goNext : undefined}
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
          title={scoped ? 'Similar shots in this search scope' : 'Similar shots'}
          id="sim"
          action={
            <Button variant="quiet" size="sm" icon={ScanSearch} shortcut="S" onPress={() => navigate({ to: '/search', search: similarSearch })}>
              See all
            </Button>
          }
        >
          <SimilarStrip uid={d.uid} limit={8} rights={similarRights} />
        </Section>
      </main>
      <aside className={s.right} aria-label="Shot details">
        <div className={s.section}>
          <p className={s.desc}>{d.summary.caption || d.summary.summary || 'No description yet.'}</p>
          <TimecodeRange inS={d.start} outS={d.end} fps={fps} copyable />
          <div className={s.techLine}>{techSummary(d)}</div>
        </div>
        <BlockedNote state={state} />
        <div className={s.actions}>
          <AddToCollectionButton uids={[d.uid]} inPoint={inOut.i} outPoint={inOut.o} />
          <ExportMenu shot={d} inPoint={inOut.i} outPoint={inOut.o} state={state} />
        </div>
        <Section title="Rights" id="r2">
          <RightsBlock shot={d} vocabs={vocabs} />
        </Section>
        {d.origin && (
          <Section title="From the web" id="o2">
            <OriginDetails origin={d.origin} />
          </Section>
        )}
        {d.people_identities && (
          <Section title="People" id="p2">
            <ShotPeople people={d.people_identities} />
          </Section>
        )}
        <Section title="Signals" id="sig2" action={<span className={t.slate}>E edits</span>}>
          <SignalTable shot={d} vocabs={vocabs} label={label} collapsible />
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
            <dt>Folder</dt>
            <dd>
              {(d.folders?.length ? d.folders : [dirname(d.path)]).map((f) => (
                <FolderCrumbs key={f} folder={f} />
              ))}
            </dd>
            <dt>Path</dt>
            <dd style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>{d.path}</dd>
          </dl>
        </Section>
      </aside>
    </div>
  )
}
