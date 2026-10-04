import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import type { RightsBadge } from '../../api/types'
import { useLibraryStats, useVocabularies } from '../../api/queries'
import { EmptyState } from '../../components/EmptyState'
import { Ic } from '../../components/Icon'
import { RIGHTS_ICON } from '../../components/RightsBadge'
import { Segmented } from '../../components/Segmented'
import { formatBytes, formatNumber, humanise, plural, shortLabel } from '../../lib/format'
import { stateFromBadge, RIGHTS_SHORT } from '../../lib/rights'
import s from './Library.module.css'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'

const COVERAGE: [string, string][] = [
  ['shot_size', 'Shot size'],
  ['camera_movement', 'Movement'],
  ['shot_role', 'Role'],
  ['setting', 'Setting'],
  ['time_of_day', 'Time of day'],
  ['weather', 'Weather'],
  ['season', 'Season'],
  ['pace', 'Pace'],
  ['mood', 'Mood'],
  ['audio_class', 'Audio'],
]

/** Map a count to the neutral sequential ramp (0 = gap, hatched). */
export function rampStep(n: number, max: number): number {
  if (n <= 0) return 0
  if (max <= 1) return 3
  return Math.max(1, Math.min(5, 1 + Math.floor((Math.log(n) / Math.log(max)) * 4.999)))
}

export function LibraryTabs() {
  return (
    <nav className={s.tabs} aria-label="Library">
      <Link to="/library" className={s.tab} activeOptions={{ exact: true }}>
        Overview
      </Link>
      <Link to="/library/folders" className={s.tab}>
        Folders
      </Link>
      <Link to="/library/corrections" className={s.tab}>
        Corrections log
      </Link>
    </nav>
  )
}

/** Library overview (system.md §9.5): what exists, coverage and gaps. */
export function LibraryPage() {
  const stats = useLibraryStats({ refetchInterval: 15_000 })
  useDocumentTitle('Library')
  const { label } = useVocabularies()
  const [view, setView] = useState<'matrix' | 'table'>(() => (window.matchMedia?.('(prefers-contrast: more)').matches ? 'table' : 'matrix'))
  const d = stats.data

  if (stats.isError) {
    return (
      <main id="main" className={s.page}>
        <EmptyState title="Couldn't load the library overview" role="alert">
          {(stats.error as Error).message}
        </EmptyState>
      </main>
    )
  }

  const processing = d?.status?.processing ?? 0
  const updating = d?.status?.updating ?? 0
  const ready = (d?.status?.ready ?? 0) + updating
  const edit = Object.entries(d?.edit_types ?? {}).sort((a, b) => b[1] - a[1])
  const editMax = Math.max(1, ...edit.map(([, n]) => n))
  const rights = Object.entries(d?.rights ?? {}) as [RightsBadge, number][]
  const rightsTotal = rights.reduce((a, [, n]) => a + n, 0) || 1
  const order: RightsBadge[] = ['cleared', 'expiring', 'restricted', 'expired', 'not_cleared', 'unknown']
  rights.sort((a, b) => order.indexOf(a[0]) - order.indexOf(b[0]))

  return (
    <main id="main" className={s.page} aria-busy={stats.isLoading || undefined}>
      <div className={s.inner}>
        <div className={s.titleRow}>
          <h1>Library</h1>
          <LibraryTabs />
        </div>

        <div className={s.figures} data-testid="library-figures">
          <div className={s.figure}>
            <span className={s.figureLabel}>Files</span>
            <strong>{formatNumber(d?.assets)}</strong>
            <span className={s.figureSub}>{processing
                ? `${formatNumber(ready)} analysed · ${formatNumber(processing)} in progress`
                : updating
                  ? `All analysed · ${formatNumber(updating)} updating to newer analysers`
                  : 'All analysed'}</span>
          </div>
          <div className={s.figure}>
            <span className={s.figureLabel}>Shots</span>
            <strong>{formatNumber(d?.shots)}</strong>
            <span className={s.figureSub}>Searchable now</span>
          </div>
          <div className={s.figure}>
            <span className={s.figureLabel}>Hours</span>
            <strong>{d ? d.hours.toFixed(d.hours < 10 ? 1 : 0) : '—'}</strong>
            <span className={s.figureSub}>{formatBytes(d?.bytes)} of source media</span>
          </div>
          <div className={s.figure}>
            <span className={s.figureLabel}>Throughput</span>
            <strong>{d?.throughput.ratio ? `${d.throughput.ratio.toFixed(1)}×` : '—'}</strong>
            <span className={s.figureSub}>{d?.throughput.ratio ? 'Hours of new footage analysed per hour of work' : 'Shown after new footage is analysed'}</span>
          </div>
        </div>

        <div className={s.two}>
          <section className={s.section} aria-labelledby="stages-h">
            <div className={s.sectionHead}>
              <h2 id="stages-h">Edit stage</h2>
            </div>
            {edit.length ? (
              edit.map(([term, n]) => (
                <Link key={term} to="/search" search={{ f: { edit_type: [term] } }} className={s.barRow} aria-label={`${label('edit_type', term)}: ${plural(n, 'file')}. Search these`}>
                  <span>{label('edit_type', term)}</span>
                  <span className={s.barTrack} aria-hidden="true">
                    <span className={s.barFill} style={{ display: 'block', inlineSize: `${(n / editMax) * 100}%` }} />
                  </span>
                  <span className={s.barValue}>{formatNumber(n)}</span>
                </Link>
              ))
            ) : (
              <p className={s.muted}>Files are classified as raw, selects or finished once their shots and audio are analysed.</p>
            )}
          </section>

          <section className={s.section} aria-labelledby="rights-h">
            <div className={s.sectionHead}>
              <h2 id="rights-h">Rights</h2>
              <Link to="/rights">Rights and governance</Link>
            </div>
            <div className={s.stack} role="img" aria-label={rights.map(([b, n]) => `${RIGHTS_SHORT[stateFromBadge(b)]} ${n}`).join(', ')}>
              {rights.map(([b, n]) => (
                <span key={b} className={`${s.seg} ${s[`seg-${b}`]}`} style={{ flex: n / rightsTotal }} title={`${RIGHTS_SHORT[stateFromBadge(b)]}: ${n}`} />
              ))}
            </div>
            <div className={s.legend}>
              {rights.map(([b, n]) => {
                const st = stateFromBadge(b)
                const tab = st === 'blocked' || st === 'expired' ? 'blocked' : st === 'expiring' ? 'expiring' : st === 'restricted' ? 'restricted' : st === 'unknown' ? 'unknown' : 'cleared'
                return (
                  <Link key={b} to="/rights" search={{ tab }}>
                    <Ic icon={RIGHTS_ICON[st]} size={14} style={{ color: `var(--status-${st === 'cleared' ? 'cleared' : st === 'unknown' ? 'info' : st === 'restricted' || st === 'expiring' ? 'caution' : 'blocked'})` }} />
                    {b === 'not_cleared' ? 'Blocked' : RIGHTS_SHORT[st]} <b>{formatNumber(n)}</b>
                  </Link>
                )
              })}
            </div>
            <p className={s.muted} style={{ fontSize: 'var(--text-sm)' }}>
              Files with unknown rights are never treated as cleared, and agents never see them.
            </p>
          </section>
        </div>

        <section className={s.section} aria-labelledby="cov-h">
          <div className={s.sectionHead}>
            <h2 id="cov-h">Coverage</h2>
            <Segmented label="Coverage view" value={view} onChange={setView} segments={[{ id: 'matrix', label: 'Matrix' }, { id: 'table', label: 'Table' }]} />
          </div>
          {view === 'matrix' ? (
            <div className={s.matrix} data-testid="coverage">
              {COVERAGE.map(([vocab, title]) => {
                const cells = d?.facets?.[vocab] ?? []
                if (!cells.length) return null
                const max = Math.max(1, ...cells.map((c) => c.count))
                return (
                  <div key={vocab} className={s.mRow}>
                    <span className={s.mLabel}>{title}</span>
                    <div className={s.cells}>
                      {cells.map((c) => {
                        const step = rampStep(c.count, max)
                        return (
                          <Link
                            key={c.term}
                            to="/search"
                            search={{ req: { [vocab]: [c.term] } }}
                            className={`${s.cell} ${s[`v${step}`]}`}
                            aria-label={`${title} ${shortLabel(c.label)}: ${c.count ? plural(c.count, 'shot') : 'gap, no shots'}`}
                            title={`${shortLabel(c.label)}: ${c.count ? plural(c.count, 'shot') : 'gap'}`}
                          >
                            <span>{shortLabel(c.label)}</span>
                            <span className={s.n}>{c.count ? formatNumber(c.count) : 'gap'}</span>
                          </Link>
                        )
                      })}
                    </div>
                  </div>
                )
              })}
              <div className={s.scale} aria-hidden="true">
                <span className={`${s.sw} ${s.v0}`} /> gap
                {[1, 2, 3, 4, 5].map((v) => (
                  <span key={v} className={`${s.sw} ${s[`v${v}`]}`} />
                ))}
                more shots (log scale)
              </div>
            </div>
          ) : (
            <table className={s.table}>
              <thead>
                <tr>
                  <th>Facet</th>
                  <th>Value</th>
                  <th className={s.num}>Shots</th>
                </tr>
              </thead>
              <tbody>
                {COVERAGE.flatMap(([vocab, title]) =>
                  (d?.facets?.[vocab] ?? []).map((c) => (
                    <tr key={`${vocab}-${c.term}`}>
                      <td>{title}</td>
                      <td>
                        <Link to="/search" search={{ req: { [vocab]: [c.term] } }}>
                          {shortLabel(c.label)}
                        </Link>
                      </td>
                      <td className={s.num}>{c.count ? formatNumber(c.count) : 'Gap'}</td>
                    </tr>
                  )),
                )}
              </tbody>
            </table>
          )}
        </section>

        <div className={s.two}>
          <section className={s.section} aria-labelledby="gaps-h">
            <div className={s.sectionHead}>
              <h2 id="gaps-h">Biggest gaps</h2>
            </div>
            {d?.gaps?.length ? (
              <div className={s.gaps}>
                {d.gaps.slice(0, 24).map((g) => (
                  <span key={`${g.vocab}-${g.term}`} className={s.gap}>
                    <span>{humanise(g.vocab)}</span>
                    {shortLabel(g.label)}
                  </span>
                ))}
              </div>
            ) : (
              <p className={s.muted}>No gaps in the main facets.</p>
            )}
            <p className={s.muted} style={{ fontSize: 'var(--text-sm)' }}>
              Values nothing in the library has been confidently tagged with. Shoot or source these to fill them.
            </p>
          </section>
          <section className={s.section} aria-labelledby="topics-h">
            <div className={s.sectionHead}>
              <h2 id="topics-h">Topics and places</h2>
            </div>
            {d && (d.topics.length || d.places.length) ? (
              <div className={s.list}>
                {[...d.places.map(([p, n]) => ['Place', p, n] as const), ...d.topics.map(([p, n]) => ['Topic', p, n] as const)].slice(0, 16).map(([k, v, n]) => (
                  <Link key={`${k}${v}`} to="/search" search={{ q: v }} className={s.barRow}>
                    <span>{v}</span>
                    <span className={s.muted} style={{ fontSize: 'var(--text-xs)' }}>{k}</span>
                    <span className={s.barValue}>{n}</span>
                  </Link>
                ))}
              </div>
            ) : (
              <p className={s.muted}>Topics and places appear when transcripts, on-screen text and location metadata have been analysed.</p>
            )}
          </section>
        </div>
      </div>
    </main>
  )
}
