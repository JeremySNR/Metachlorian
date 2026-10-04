import { useRef, useState } from 'react'
import { Link, useNavigate } from '@tanstack/react-router'
import { Maximize2, PanelRightClose, ScanSearch, X } from 'lucide-react'
import type { IntendedUse, SearchResult } from '../../api/types'
import { mediaUrl } from '../../api/client'
import { useShot, useVocabularies } from '../../api/queries'
import { Button, IconButton } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { RightsBadge } from '../../components/RightsBadge'
import { Timecode, TimecodeRange } from '../../components/Timecode'
import { MOD } from '../../lib/bridge'
import { humanise } from '../../lib/format'
import { Player, type PlayerHandle } from './Player'
import { SignalTable } from './SignalTable'
import { AddToCollectionButton, BlockedNote, ExportMenu, InCollections, RightsBlock, Section, shotRightsState, WhyMatched } from './ShotPanels'
import { techSummary } from './techSummary'
import { ShotPeople } from '../people/ShotPeople'
import { FolderCrumbs } from '../search/FolderCrumbs'
import { dirname } from '../../lib/folders'
import t from '../../styles/type.module.css'
import s from './Shot.module.css'

interface Props {
  uid: string | null
  result?: SearchResult
  intended?: IntendedUse | null
  query?: string
  onClose?: () => void
  onCollapse?: () => void
  editField?: string | null
  /** Search scope to keep when finding similar shots. */
  keep?: { folder?: string[]; collection?: string[] }
}

/** Right-hand inspector (system.md §2.1, §9.1): follows grid focus; Enter opens Shot detail. */
export function Inspector({ uid, result, intended, query, onClose, onCollapse, editField, keep }: Props) {
  const shot = useShot(uid, intended)
  const { vocabs, label } = useVocabularies()
  const navigate = useNavigate()
  const player = useRef<PlayerHandle>(null)
  const [inOut, setInOut] = useState<{ uid: string | null; i: number | null; o: number | null }>({ uid: null, i: null, o: null })
  const d = shot.data
  const io = inOut.uid === uid ? inOut : { uid, i: null, o: null }

  if (!uid) {
    return (
      <div className={s.panel}>
        <div className={s.panelHead}>
          <h2 className={t.slate}>Shot</h2>
          {onCollapse && <IconButton icon={PanelRightClose} label="Collapse inspector" shortcut={`${MOD}I`} size="sm" onPress={onCollapse} />}
        </div>
        <EmptyState inline title="No shot selected">
          Move through the results with the arrow keys or hover a card. The shot you focus appears here.
        </EmptyState>
      </div>
    )
  }

  const fps = d?.technical.fps ?? result?.fps ?? null
  const start = d?.start ?? result?.start ?? 0
  const end = d?.end ?? result?.end ?? 0
  const state = d ? shotRightsState(d) : 'unknown'
  const edit = d && typeof d.edit_type === 'object' && d.edit_type ? d.edit_type.term : (d?.edit_type as string | null)

  return (
    <div className={s.panel} aria-busy={shot.isFetching || undefined}>
      <div className={s.panelHead}>
        <h2>
          <span className={t.slate}>Shot {d ? d.idx + 1 : ''}</span>
          <Timecode seconds={result?.in ?? start} fps={fps} size="sm" />
        </h2>
        {d && <RightsBadge state={state} record={d.rights} reasons={d.rights_check?.reasons} />}
        <IconButton icon={Maximize2} label="Open shot detail" shortcut="Enter" size="sm" onPress={() => navigate({ to: '/shot/$shotId', params: { shotId: uid } })} />
        {onClose && <IconButton icon={X} label="Close" shortcut="Esc" size="sm" onPress={onClose} />}
        {onCollapse && <IconButton icon={PanelRightClose} label="Collapse inspector" shortcut={`${MOD}I`} size="sm" onPress={onCollapse} />}
      </div>
      {(d || result) && (
        <div className={s.panelSub}>
          {d ? (
            <Link to="/file/$assetId" params={{ assetId: d.asset_uid }} search={{ shot: d.uid }} className={s.fileLink} title={d.path}>
              {d.filename}
            </Link>
          ) : (
            <span className={s.fileLink}>{result?.filename}</span>
          )}
          {edit && <span className={t.slate}>{humanise(edit)}</span>}
          <FolderCrumbs folder={result?.folder ?? (d ? dirname(d.path) : null)} className={s.subCrumbs} />
        </div>
      )}
      <div className={s.scroll} data-testid="inspector">
        {d || result ? (
          <Player
            key={uid}
            ref={player}
            compact
            src={mediaUrl(d?.media.proxy ?? result?.proxy) as string}
            poster={mediaUrl(d?.media.poster ?? result?.poster)}
            fps={fps}
            range={[start, end]}
            startAt={result?.in ?? start}
            inPoint={io.i}
            outPoint={io.o}
            onInOut={(i, o) => setInOut({ uid, i, o })}
            label={`${d?.filename ?? result?.filename ?? ''}, shot ${(d?.idx ?? result?.idx ?? 0) + 1}`}
            testId="inspector-player"
          />
        ) : null}
        {shot.isError && !d && (
          <EmptyState inline title="Couldn't load this shot" role="alert">
            {(shot.error as Error)?.message}
          </EmptyState>
        )}
        {d && (
          <>
            <div className={s.section}>
              <p className={s.desc}>{d.summary.caption || d.summary.summary || 'No description yet.'}</p>
              <TimecodeRange inS={start} outS={end} fps={fps} copyable />
              <div className={s.techLine}>{techSummary(d)}</div>
            </div>
            <BlockedNote state={state} />
            <div className={s.actions}>
              <AddToCollectionButton uids={[uid]} inPoint={io.i} outPoint={io.o} />
              <Button variant="secondary" icon={ScanSearch} shortcut="S" onPress={() => navigate({ to: '/search', search: { similar: uid, ...keep } })}>
                Find similar
              </Button>
              <ExportMenu shot={d} inPoint={io.i} outPoint={io.o} state={state} />
            </div>
            <Section title="Rights" id="rights">
              <RightsBlock shot={d} vocabs={vocabs} intended={intended} />
            </Section>
            {(d.people_identities || Array.isArray(result?.identities)) && (
              <Section title="People" id="people">
                <ShotPeople people={d.people_identities ?? result?.identities} />
              </Section>
            )}
            {result && (
              <Section title="Why it matched" id="why">
                <WhyMatched why={result.why} label={label} query={query} />
              </Section>
            )}
            <Section title="Signals" id="signals" action={<span className={t.slate}>E edits</span>}>
              <SignalTable shot={d} vocabs={vocabs} label={label} editField={editField} collapsible />
            </Section>
            <Section title="In collections" id="cols">
              <InCollections uid={uid} />
            </Section>
            <Section title="File" id="file">
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
          </>
        )}
      </div>
    </div>
  )
}
