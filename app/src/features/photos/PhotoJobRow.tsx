import type { PhotoJob, PhotoSession } from '../../api/photos'
import { Button } from '../../components/Button'
import s from './Photos.module.css'

const bytes = (n: number) => `${(n / 1024 ** 2).toFixed(1)} MiB`
const labels: Record<string, string> = { folder: 'Folder indexing', catalog: 'Lightroom catalogue', analyse: 'Image analysis', begin: 'Prepare virtual copies', apply: 'Render edit', finish: 'Save selection', restore: 'Restore candidate', models: 'Download photo models' }

export function PhotoJobRow({ job, canManage, onReview, onAction }: { job: PhotoJob; canManage: boolean; onReview: (session: PhotoSession) => void; onAction: (command: 'resume' | 'cancel') => void }) {
  const result = job.result
  const sessions = result.sessions ?? (result.session_id && result.photo_id && result.revision ? [{ session_id: result.session_id, photo_id: result.photo_id, source_photo_id: result.source_photo_id, revision: result.revision }] : [])
  return <div className={s.job}><div className={s.row}><strong>{labels[job.kind] ?? job.kind}</strong><span className={s.badge}>{job.status === 'done' && sessions.length ? job.kind === 'begin' ? 'Copies ready for agent' : 'Ready for review' : job.status}</span>
    {result.processed !== undefined ? <span className={s.muted}>{result.processed.toLocaleString()}{result.total ? ` / ${result.total.toLocaleString()}` : ''} photographs</span> : null}
    {result.current_model ? <span className={s.muted}>{result.current_model}{result.downloaded_bytes ? ` · ${bytes(result.downloaded_bytes)}${result.total_bytes ? ` / ${bytes(result.total_bytes)}` : ''}` : ''}</span> : null}
    {canManage && ['waiting', 'failed', 'cancelled'].includes(job.status) ? <Button size="sm" onPress={() => onAction('resume')}>Resume</Button> : null}
    {canManage && ['queued', 'running', 'waiting'].includes(job.status) ? <Button size="sm" onPress={() => onAction('cancel')}>Stop</Button> : null}
    {job.status === 'done' ? sessions.map((session, i) => <Button size="sm" key={session.session_id} onPress={() => onReview(session)}>{job.kind === 'begin' ? 'View copy' : 'Review edit'}{sessions.length > 1 ? ` ${i + 1}` : ''}</Button>) : null}
  </div>{job.kind === 'begin' && job.status === 'done' ? <p className={s.muted}>Virtual copies created. Ask your agent to apply the brief and review the rendered result.</p> : null}{job.error ? <p className={s.muted}>{job.error}</p> : null}{result.accepted ? <p>{result.accepted.length} photographs saved to {result.collection} in Lightroom.</p> : null}</div>
}
