import { useState } from 'react'
import { Copy } from 'lucide-react'
import type { Photo } from '../../api/photos'
import { Button } from '../../components/Button'
import { Checkbox, TextField } from '../../components/Field'
import { PhotoImage } from './PhotoInspector'
import s from './Photos.module.css'

const ideas = [
  ['Natural', 'Keep the moment natural. Balance light and colour, preserve believable skin tones, and refine the framing.'],
  ['Warm film', 'Create a warm Kodak Gold-inspired look with gentle contrast and grain. Preserve believable skin tones and the feeling of the moment.'],
  ['Black & white', 'Create an expressive black-and-white edit with thoughtful contrast, preserved highlight detail and strong framing.'],
] as const

export function PhotoEditBrief({ photos, brief, onBrief, creative, onCreative, editBlocked, busy, error, onPrepare, onSetup }: {
  photos: Photo[]; brief: string; onBrief: (value: string) => void; creative: boolean; onCreative: (value: boolean) => void
  editBlocked?: string; busy: boolean; error: string; onPrepare: () => void; onSetup: () => void
}) {
  const [copied, setCopied] = useState(false)
  const [copyError, setCopyError] = useState('')
  const copy = async () => {
    setCopied(false); setCopyError('')
    try {
      await navigator.clipboard.writeText(`Use these Metachlorian photos: ${photos.map(photo => `${photo.filename} (${photo.uid})`).join(', ')}. ${brief}\n${creative ? 'Creative changes are welcome.' : 'Keep the edit natural.'} Check Lightroom readiness, work on virtual copies and review Lightroom renders before saving. Report any blocked steps.`)
      setCopied(true)
    } catch { setCopyError('Could not copy the brief. Check clipboard access in your browser and try again.') }
  }
  return <div className={s.dialogContent}>
    <p>{photos.length} {photos.length === 1 ? 'photograph' : 'photographs'} selected. Describe the result you want, then give the brief to Codex or your preferred agent.</p>
    <div className={s.briefPhotos}>{photos.slice(0, 6).map(photo => <figure key={photo.uid}><PhotoImage uid={photo.uid} edge={300} label={photo.filename} retry={false} /><figcaption>{photo.filename}</figcaption></figure>)}{photos.length > 6 ? <span>+{photos.length - 6} more</span> : null}</div>
    <div className={s.actions} aria-label="Brief starting points">{ideas.map(([label, text]) => <Button key={label} size="sm" onPress={() => { onBrief(text); onCreative(label !== 'Natural'); setCopied(false) }}>{label}</Button>)}</div>
    <TextField multiline label="Edit brief" value={brief} onChange={value => { onBrief(value); setCopied(false) }} description="These starting points describe a look; no adjustments are applied here." />
    <Checkbox isSelected={creative} onChange={value => { onCreative(value); setCopied(false) }}>Allow a creative look and bolder framing</Checkbox>
    <div className={s.actions}><Button variant="primary" icon={Copy} isDisabled={!brief.trim()} onPress={() => void copy()}>Copy brief for agent</Button><Button variant="quiet" onPress={onSetup}>Agent setup</Button></div>
    {copied ? <p role="status">Brief and photo references copied. Paste them into your connected agent to start the edit.</p> : null}
    {copyError ? <p role="alert">{copyError}</p> : null}
    {editBlocked ? <p className={s.hint}>Lightroom editing needs attention: {editBlocked}</p> : null}
    <details className={s.advanced}><summary>Prepare virtual copies yourself</summary><p>This creates recoverable copies in Lightroom for your agent to edit. It does not apply the brief automatically.</p><Button isDisabled={Boolean(editBlocked) || busy || !brief.trim()} disabledReason={editBlocked} busy={busy} onPress={onPrepare}>Prepare virtual copies</Button>{error ? <p role="alert">{error}</p> : null}</details>
  </div>
}
