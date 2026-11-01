import { useQuery } from '@tanstack/react-query'
import { Link } from '@tanstack/react-router'
import { api } from '../../api/client'
import { formatNumber, humanise } from '../../lib/format'
import s from './Library.module.css'

interface ReadinessReport {
  state: 'empty' | 'attention' | 'processing' | 'available'
  files: { total: number; searchable: number; unindexed: number; partially_indexed: number; previews_ready: number; index_failed: number; capture_date_unknown: number }
  shots: { active: number; indexed: number; missing_from_index: number }
  failed_analysis_files: number
  limited_analysis_files: number
  analysis: Record<string, Record<string, number>>
  index_issues: { asset_uid: string; filename: string; status: string; error: string }[]
}

/** Separate search coverage from analysis success; a completed queue is not a quality score. */
export function Readiness() {
  const report = useQuery({ queryKey: ['library-readiness'], queryFn: ({ signal }) => api.get<ReadinessReport>('/api/library/readiness', signal), refetchInterval: 15_000 })
  const d = report.data
  return <section className={s.section} aria-labelledby="readiness-title">
    <div className={s.sectionHead}>
      <h2 id="readiness-title">Search and analysis readiness</h2>
      <Link to="/ingest">Processing and errors</Link>
    </div>
    {report.isError ? <p role="alert">Couldn’t check readiness. <button type="button" onClick={() => report.refetch()}>Retry</button></p>
      : !d ? <p>Checking library…</p> : <>
        <p><strong>{formatNumber(d.files.searchable)} of {formatNumber(d.files.total)} files searchable</strong>
          {' · '}{formatNumber(d.files.previews_ready)} previews ready
          {' · '}{d.state === 'attention' ? 'Needs attention' : d.state === 'processing' ? 'Processing continues' : d.state === 'empty' ? 'Library empty' : 'Search available'}</p>
        <p className={s.muted}>Searchable means at least one shot is indexed. Captions, transcripts and other analysis may still be incomplete.</p>
        <ul>
          <li>{formatNumber(d.files.unindexed)} files not yet searchable; {formatNumber(d.shots.missing_from_index)} detected shots missing from search.</li>
          <li>{formatNumber(d.failed_analysis_files)} files have failed analysis; {formatNumber(d.limited_analysis_files)} have unavailable analysis steps.</li>
          <li>{formatNumber(d.files.capture_date_unknown)} files have no valid recording date. File modification dates are not treated as shoot dates.</li>
        </ul>
        {!!d.index_issues.length && <p>Indexing needs attention: {d.index_issues.slice(0, 5).map((issue, i) => <span key={issue.asset_uid}>
          {i > 0 ? ', ' : ''}<Link to="/file/$assetId" params={{ assetId: issue.asset_uid }}>{issue.filename}</Link>
        </span>)}. Interrupted indexing retries automatically.</p>}
        <details>
          <summary>Analysis coverage by step</summary>
          <p className={s.muted}>Unavailable may mean an optional model is disabled. Completed steps do not guarantee accurate results; review important shots and their evidence.</p>
          <table className={s.readinessTable}>
            <thead><tr><th scope="col">Step</th><th scope="col">Completed</th><th scope="col">Failed</th><th scope="col">Unavailable</th></tr></thead>
            <tbody>{Object.entries(d.analysis).map(([name, counts]) => <tr key={name}>
              <th scope="row">{humanise(name)}</th><td>{formatNumber(counts.done ?? 0)}</td><td>{formatNumber(counts.failed ?? 0)}</td><td>{formatNumber(counts.unavailable ?? 0)}</td>
            </tr>)}</tbody>
          </table>
        </details>
      </>}
  </section>
}
