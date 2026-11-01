import { Download, RefreshCw } from 'lucide-react'
import { Button } from '../../components/Button'
import type { PhotoStatus } from '../../api/photos'
import s from './Photos.module.css'

const bytes = (value: number) => `${(value / 1024 ** 2).toFixed(1)} MiB`

export function PhotoLibraryDetails({ status, canIngest, canAdmin, busy, downloading, onAnalyse, onModels }: {
  status: PhotoStatus; canIngest: boolean; canAdmin: boolean; busy: boolean; downloading: boolean
  onAnalyse: () => void; onModels: () => void
}) {
  const missing = status.models.filter(model => model.name !== 'face-landmarker' && !model.installed)
  return <div className={s.dialogContent}>
    <section className={s.analysisSection}>
      <h3>Image understanding</h3>
      <p>{status.coverage.analysed.toLocaleString()} of {status.coverage.total.toLocaleString()} photos analysed</p>
      <progress aria-label="Photo analysis progress" value={status.coverage.analysed} max={Math.max(1, status.coverage.total)} />
      <p>Analysis measures available previews. Open a photo’s Analysis view to see the measurements and models used.</p>
      {status.coverage.needs_attention ? <p className={s.hint}>{status.coverage.needs_attention.toLocaleString()} photos need a preview. Connect Lightroom or reconnect their originals, then retry analysis.</p> : null}
      <Button size="sm" icon={RefreshCw} isDisabled={!canIngest || busy} disabledReason={!canIngest ? 'Your account needs ingest:write to run analysis.' : undefined} onPress={onAnalyse}>Refresh analysis</Button>
    </section>
    <section className={s.analysisSection}>
      <h3>{missing.length ? 'Add visual search and face tools' : 'Photo models are installed'}</h3>
      <p>Local models let you search image content and find people. They are shared with your video library.</p>
      {missing.length ? <><p>{Math.round(missing.reduce((sum, model) => sum + model.size_mb, 0))} MB to download. You can browse and search metadata without these models.</p><Button icon={Download} size="sm" isDisabled={!canAdmin || busy || downloading} disabledReason={!canAdmin ? 'An administrator can install photo models.' : undefined} onPress={onModels}>{downloading ? 'Downloading photo models…' : 'Install photo models'}</Button></> : null}
    </section>
    <section className={s.analysisSection}>
      <h3>Storage</h3>
      <dl className={s.facts}><dt>Temporary previews</dt><dd>{bytes(status.cache.bytes)} / {bytes(status.cache.budget_bytes)}</dd><dt>Shared library database</dt><dd>{bytes(status.database_bytes)}</dd></dl>
      <p>Originals stay in place. Older previews are removed as the cache fills. Model downloads and Lightroom’s own catalogue and previews use separate storage.</p>
    </section>
  </div>
}
