import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { api } from '../../api/client'
import { photoPreview, usePhoto } from '../../api/photos'
import { Button, IconButton } from '../../components/Button'
import { TextField } from '../../components/Field'
import s from './Photos.module.css'

export function PhotoInspector({ uid, canName, onClose, onBurst }: { uid: string; canName: boolean; onClose: () => void; onBurst: (id: string) => void }) {
  const detail = usePhoto(uid)
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [detailFace, setDetailFace] = useState<number | null>(null)
  const photo = detail.data
  const face = photo?.faces.find((f) => f.id === detailFace)
  const nameFace = async (faceId: number) => {
    try {
      await api.post(`/api/photos/faces/${faceId}/name`, { name })
      setName('')
      await qc.invalidateQueries({ queryKey: ['photos', 'detail', uid] })
    } catch (e) { setError((e as Error).message) }
  }
  const separateFace = async (faceId: number) => {
    try {
      await api.post(`/api/photos/faces/${faceId}/move`, { identity_id: null })
      await qc.invalidateQueries({ queryKey: ['photos', 'detail', uid] })
      await qc.invalidateQueries({ queryKey: ['people'] })
    } catch (e) { setError((e as Error).message) }
  }
  return <aside className={s.inspector} aria-label="Photograph details">
    <div className={s.row}><h2>{photo?.filename ?? 'Photograph'}</h2><IconButton icon={X} label="Close photograph details" onPress={onClose} /></div>
    {detail.isPending ? <p role="status">Loading photograph…</p> : null}
    {detail.error ? <p role="alert">{detail.error.message}</p> : null}
    {photo ? <>
      <PhotoImage key={`${uid}-${detailFace}`} uid={uid} label={face ? 'Original face detail' : photo.filename} edge={1600} region={face?.box} native={Boolean(face)} />
      {face ? <Button size="sm" onPress={() => setDetailFace(null)}>Show full photograph</Button> : null}
      <dl className={s.facts}>
        <dt>Captured</dt><dd>{photo.capture_time?.replace('T', ' ') ?? 'Unknown'}</dd>
        <dt>Dimensions</dt><dd>{photo.width && photo.height ? `${photo.width} × ${photo.height}` : 'Unknown'}</dd>
        <dt>Available</dt><dd>{photo.availability.replaceAll('_', ' ')}</dd>
        <dt>Rating</dt><dd>{photo.rating ? `${photo.rating} / 5` : 'Unrated'}</dd>
      </dl>
      {photo.keywords.length ? <p className={s.muted}>{photo.keywords.join(' · ')}</p> : null}
      {photo.burst_id ? <Button size="sm" onPress={() => onBurst(photo.burst_id!)}>Compare this burst</Button> : null}
      <h3>What we can judge</h3>
      <ul className={s.notes}>{(photo.evidence.uncertainty ?? ['Analysis is still pending.']).map((note) => <li key={note}>{note}</li>)}</ul>
      {photo.faces.length ? <><h3>People</h3><p className={s.muted}>Name a person once to find them again. Face matching stays on this computer.</p>
        {canName ? <TextField label="Person’s name" value={name} onChange={setName} /> : null}
        {photo.faces.map((f, i) => <div className={s.row} key={f.id}><span>{f.name ?? `Person ${i + 1}`}</span>
          <Button size="sm" isDisabled={f.stale} onPress={() => setDetailFace(f.id)}>{f.stale ? 'Refresh analysis for current detail' : 'Inspect detail'}</Button>
          {canName && f.identity_id ? <Button size="sm" isDisabled={!name.trim()} onPress={() => void nameFace(f.id)}>Name</Button> : null}
          {canName && f.name ? <Button size="sm" onPress={() => void separateFace(f.id)}>Not this person</Button> : null}
        </div>)}
      </> : null}
      <details><summary>Capture metadata</summary><dl className={s.facts}>{Object.entries(photo.metadata).filter(([key, value]) => !key.startsWith('_') && value != null && typeof value !== 'object').map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}</dl></details>
    </> : null}
    {error ? <p role="alert">{error}</p> : null}
  </aside>
}

export function PhotoImage({ uid, label, edge = 600, revision, region, native = false, retry = true }: {
  uid: string; label: string; edge?: number; revision?: string; region?: number[]; native?: boolean; retry?: boolean
}) {
  const [failed, setFailed] = useState(false)
  return <div className={s.image}>
    {failed ? <div><p>Preview unavailable. Open Lightroom or reconnect the original.</p>{retry ? <Button size="sm" onPress={() => setFailed(false)}>Retry preview</Button> : null}</div> :
      <img src={photoPreview(uid, edge, revision, region, native)} alt={label} loading="lazy" decoding="async" onError={() => setFailed(true)} />}
  </div>
}
