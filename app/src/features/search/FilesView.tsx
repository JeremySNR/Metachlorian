import { Link } from '@tanstack/react-router'
import type { SearchResult } from '../../api/types'
import { mediaUrl } from '../../api/client'
import { Timecode } from '../../components/Timecode'
import { humanise } from '../../lib/format'
import { useUi } from '../../lib/store'
import { FolderCrumbs } from './FolderCrumbs'
import t from '../../styles/type.module.css'
import s from './ResultsGrid.module.css'

/** "Files" grouping: one contact-sheet strip per file, matching shots in order (Light Table borrowing). */
export function FilesView({ results, onOpen }: { results: SearchResult[]; onOpen: (r: SearchResult) => void }) {
  const inspected = useUi((u) => u.inspected)
  const groups = new Map<string, SearchResult[]>()
  for (const r of results) {
    const g = groups.get(r.asset_uid) ?? []
    g.push(r)
    groups.set(r.asset_uid, g)
  }
  return (
    <div className={s.files} style={{ overflowY: 'auto', flex: 1 }}>
      {[...groups.entries()].map(([asset, shots]) => {
        const sorted = [...shots].sort((a, b) => a.start - b.start)
        return (
          <section key={asset} className={s.fileGroup} aria-label={shots[0].filename}>
            <div className={s.fileHead}>
              <Link to="/file/$assetId" params={{ assetId: asset }} className={s.fileName}>
                {shots[0].filename}
              </Link>
              <span className={t.slate}>{humanise(shots[0].edit_type) || 'Edit stage unknown'}</span>
              <span className={t.slate}>
                {shots.length} matching shot{shots.length === 1 ? '' : 's'}
              </span>
              <FolderCrumbs folder={shots[0].folder} />
            </div>
            <div className={s.fileStrip}>
              {sorted.map((r) => (
                <button key={r.uid} type="button" className={s.mini} aria-pressed={inspected === r.uid} onClick={() => onOpen(r)} aria-label={`${r.caption ?? 'Shot'} at ${r.start.toFixed(1)} seconds`}>
                  {r.thumb ? <img src={mediaUrl(r.thumb)} alt="" loading="lazy" decoding="async" /> : <span />}
                  <Timecode seconds={r.in ?? r.start} fps={r.fps} size="xs" />
                </button>
              ))}
            </div>
          </section>
        )
      })}
    </div>
  )
}
