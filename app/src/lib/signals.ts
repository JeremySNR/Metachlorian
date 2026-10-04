/**
 * Shot signals: grouping, labels, value rendering and provenance
 * (records.py field names; system.md §3.10 signal rows).
 */
import type { CorrectionKind, FieldValue, TechnicalSummary } from '../api/types'
import { humanise, percent } from './format'
import { fpsLabel } from './timecode'

export type SignalGroup = 'Camera' | 'Content' | 'People' | 'Audio' | 'Semantic' | 'Quality' | 'Look' | 'Technical'
export const SIGNAL_GROUPS: SignalGroup[] = ['Camera', 'Content', 'People', 'Audio', 'Semantic', 'Quality', 'Look', 'Technical']

/** Field → vocabulary for controlled-term fields (records.py VOCAB_FIELDS). */
export const VOCAB_FIELDS: Record<string, { vocab: string; multi: boolean }> = {
  'camera.movement': { vocab: 'camera_movement', multi: true },
  'camera.shot_size': { vocab: 'shot_size', multi: false },
  'camera.angle': { vocab: 'camera_angle', multi: false },
  'camera.speed_effect': { vocab: 'speed_effect', multi: true },
  'shot.role': { vocab: 'shot_role', multi: true },
  'content.setting': { vocab: 'setting', multi: true },
  'content.time_of_day': { vocab: 'time_of_day', multi: false },
  'content.weather': { vocab: 'weather', multi: true },
  'content.season': { vocab: 'season', multi: false },
  'semantic.mood': { vocab: 'mood', multi: true },
  'pacing.pace': { vocab: 'pace', multi: false },
  'audio.classes': { vocab: 'audio_class', multi: true },
  'quality.flags': { vocab: 'quality_flag', multi: true },
}

type Fmt = 'percent' | 'number' | 'lufs' | 'wpm' | 'score'

interface Meta {
  group: SignalGroup
  label: string
  fmt?: Fmt
}

export const FIELD_META: Record<string, Meta> = {
  'camera.shot_size': { group: 'Camera', label: 'Shot size' },
  'camera.angle': { group: 'Camera', label: 'Angle' },
  'camera.movement': { group: 'Camera', label: 'Movement' },
  'camera.speed_effect': { group: 'Camera', label: 'Speed' },
  'shot.role': { group: 'Camera', label: 'Role' },
  'composition.vertical_crop': { group: 'Camera', label: '9:16 crop' },
  'content.caption': { group: 'Content', label: 'Description' },
  'content.summary': { group: 'Content', label: 'Summary' },
  'content.setting': { group: 'Content', label: 'Setting' },
  'content.time_of_day': { group: 'Content', label: 'Time of day' },
  'content.weather': { group: 'Content', label: 'Weather' },
  'content.season': { group: 'Content', label: 'Season' },
  'content.location': { group: 'Content', label: 'Place' },
  'content.objects': { group: 'Content', label: 'Objects' },
  'content.concepts': { group: 'Content', label: 'Concepts' },
  'content.activities': { group: 'Content', label: 'Activities' },
  'content.ocr_text': { group: 'Content', label: 'Text in frame' },
  'graphics.title': { group: 'Content', label: 'Title card' },
  'graphics.lower_third': { group: 'Content', label: 'Lower third' },
  'graphics.burned_in_captions': { group: 'Content', label: 'Burned-in captions' },
  tags: { group: 'Content', label: 'Tags' },
  'people.count': { group: 'People', label: 'People' },
  'people.peak_count': { group: 'People', label: 'Peak count' },
  'people.faces': { group: 'People', label: 'Faces' },
  'people.talking_to_camera': { group: 'People', label: 'Talking to camera' },
  'people.centred_face': { group: 'People', label: 'Centred face' },
  'audio.classes': { group: 'Audio', label: 'Audio' },
  'audio.events': { group: 'Audio', label: 'Sound events' },
  'audio.has_audio': { group: 'Audio', label: 'Has audio' },
  'audio.speech_ratio': { group: 'Audio', label: 'Speech share', fmt: 'percent' },
  'audio.silence_ratio': { group: 'Audio', label: 'Silence', fmt: 'percent' },
  'audio.words_per_minute': { group: 'Audio', label: 'Speaking rate', fmt: 'wpm' },
  'audio.loudness_lufs': { group: 'Audio', label: 'Loudness', fmt: 'lufs' },
  'audio.language': { group: 'Audio', label: 'Language' },
  'semantic.mood': { group: 'Semantic', label: 'Mood' },
  'semantic.topics': { group: 'Semantic', label: 'Topics' },
  'semantic.suggested_uses': { group: 'Semantic', label: 'Suggested uses' },
  'pacing.pace': { group: 'Semantic', label: 'Pace' },
  'pacing.motion_energy': { group: 'Semantic', label: 'Motion energy', fmt: 'score' },
  'pacing.audio_energy': { group: 'Semantic', label: 'Audio energy', fmt: 'score' },
  'quality.usable': { group: 'Quality', label: 'Usable' },
  'quality.score': { group: 'Quality', label: 'Quality score', fmt: 'score' },
  'quality.flags': { group: 'Quality', label: 'Problems' },
  'quality.sharpness': { group: 'Quality', label: 'Sharpness', fmt: 'score' },
  'quality.exposure': { group: 'Quality', label: 'Exposure', fmt: 'score' },
  'quality.noise': { group: 'Quality', label: 'Noise', fmt: 'score' },
  'quality.stability': { group: 'Quality', label: 'Stability', fmt: 'score' },
  'look.dominant_colours': { group: 'Look', label: 'Colours' },
  'look.log_likeness': { group: 'Look', label: 'Log likeness', fmt: 'score' },
  'quality.contrast': { group: 'Look', label: 'Contrast', fmt: 'score' },
  'quality.saturation': { group: 'Look', label: 'Saturation', fmt: 'score' },
}

const SOURCE_LABEL: Record<string, string> = {
  visual_tags: 'Vision model',
  embed: 'Vision model',
  caption: 'Vision model',
  vlm: 'Vision model',
  motion: 'Motion analysis',
  people: 'Person detector',
  audio: 'Audio',
  speech: 'Transcript',
  ocr: 'On-screen text',
  quality: 'Image analysis',
  technical: 'Camera metadata',
  fusion_rules: 'Rules',
  shots: 'Shot detection',
  human: 'Human',
  fusion: 'Combined',
  llm: 'Language model',
}

export function sourceLabel(fv: FieldValue): string {
  if (fv.corrected || fv.source === 'human') return 'Human'
  if (fv.source !== 'fusion') return SOURCE_LABEL[fv.source] ?? humanise(fv.source)
  const v = fv.value as unknown
  const first = Array.isArray(v) ? v[0] : v
  const srcs: string[] = (first && typeof first === 'object' && Array.isArray((first as { sources?: string[] }).sources) ? (first as { sources: string[] }).sources : []) ?? []
  const labels = [...new Set(srcs.map((x) => SOURCE_LABEL[x] ?? humanise(x)))]
  return labels.length ? labels.slice(0, 2).join(' + ') : 'Combined'
}

export interface TermItem {
  term: string
  confidence: number | null
}

export type Rendered =
  | { kind: 'terms'; items: TermItem[] }
  | { kind: 'text'; text: string }
  | { kind: 'colours'; colours: { hex: string; share?: number }[] }
  | { kind: 'empty' }

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)

function fmtNumber(n: number, fmt?: Fmt): string {
  switch (fmt) {
    case 'percent':
      return percent(n)
    case 'lufs':
      return `${n.toFixed(1)} LUFS`
    case 'wpm':
      return `${Math.round(n)} words/min`
    case 'score':
      return n.toFixed(2)
    default:
      return Number.isInteger(n) ? String(n) : n.toFixed(2)
  }
}

/** Normalise a field value for display. */
export function renderValue(field: string, value: unknown): Rendered {
  const meta = FIELD_META[field]
  if (value === null || value === undefined || value === '') return { kind: 'empty' }
  if (Array.isArray(value)) {
    if (!value.length) return { kind: 'empty' }
    if (value.every((x) => isObj(x) && 'hex' in x)) return { kind: 'colours', colours: value as { hex: string; share?: number }[] }
    if (value.every((x) => isObj(x) && 'term' in x)) return { kind: 'terms', items: value.map((x) => ({ term: String((x as { term: unknown }).term), confidence: ((x as { confidence?: number }).confidence ?? null) as number | null })) }
    if (value.every((x) => isObj(x) && 'label' in x)) return { kind: 'text', text: value.slice(0, 4).map((x) => `${(x as { label: string }).label}${'p' in (x as object) ? ` ${percent((x as { p: number }).p)}` : ''}`).join(', ') }
    if (value.every((x) => typeof x === 'string')) return { kind: 'terms', items: value.map((x) => ({ term: String(x), confidence: null })) }
    return { kind: 'text', text: value.map((x) => (typeof x === 'object' ? JSON.stringify(x) : String(x))).join(', ') }
  }
  if (isObj(value)) {
    if ('term' in value) return { kind: 'terms', items: [{ term: String(value.term), confidence: (value.confidence as number) ?? null }] }
    if ('value' in value) return renderValue(field, value.value)
    if (field === 'composition.vertical_crop' && 'safe' in value) return { kind: 'text', text: value.safe ? 'Safe crop available' : 'No safe crop' }
    if ('bars_vertical' in value) return { kind: 'text', text: (value.bars_vertical as number) > 0.02 || (value.bars_horizontal as number) > 0.02 ? 'Bars present' : 'None' }
    return { kind: 'text', text: Object.entries(value).slice(0, 4).map(([k, v]) => `${humanise(k)} ${typeof v === 'number' ? fmtNumber(v) : String(v)}`).join(', ') }
  }
  if (typeof value === 'boolean') return { kind: 'text', text: value ? 'Yes' : 'No' }
  if (typeof value === 'number') return { kind: 'text', text: fmtNumber(value, meta?.fmt) }
  return { kind: 'text', text: String(value) }
}

/** Plain text for a value (tooltips: "Model said: Calm (0.62)"). */
export function valueText(field: string, value: unknown, label: (vocab: string, term: string) => string): string {
  const r = renderValue(field, value)
  const vocab = VOCAB_FIELDS[field]?.vocab
  switch (r.kind) {
    case 'terms':
      return r.items.map((i) => `${vocab ? label(vocab, i.term) : humanise(i.term)}${i.confidence !== null && i.confidence < 1 ? ` (${i.confidence.toFixed(2)})` : ''}`).join(', ')
    case 'text':
      return r.text
    case 'colours':
      return r.colours.map((c) => c.hex).join(', ')
    default:
      return 'nothing'
  }
}

/** Term ids of a value (for confirm/compare). */
export function termIds(value: unknown): string[] {
  const r = renderValue('', value)
  return r.kind === 'terms' ? r.items.map((i) => i.term) : []
}

export interface SignalRow {
  field: string
  label: string
  group: SignalGroup
  fv: FieldValue
  kind?: CorrectionKind
}

/** Rows grouped for display, skipping raw/internal measurements. */
export function signalRows(fields: Record<string, FieldValue>, correctable: Record<string, CorrectionKind> = {}): Map<SignalGroup, SignalRow[]> {
  const out = new Map<SignalGroup, SignalRow[]>()
  for (const g of SIGNAL_GROUPS) out.set(g, [])
  for (const [field, meta] of Object.entries(FIELD_META)) {
    const fv = fields[field]
    if (!fv) continue
    const r = renderValue(field, fv.value)
    if (r.kind === 'empty' && !correctable[field]) continue
    out.get(meta.group)?.push({ field, label: meta.label, group: meta.group, fv, kind: correctable[field] })
  }
  return out
}

/** Technical rows from the shot's technical block (source: camera metadata). */
export function technicalRows(t: TechnicalSummary | undefined): [string, string][] {
  if (!t) return []
  const rows: [string, string | null | undefined][] = [
    ['Resolution', t.width && t.height ? `${t.width}×${t.height}` : null],
    ['Frame rate', t.fps ? fpsLabel(t.fps) : null],
    ['Codec', t.video_codec ? t.video_codec.toUpperCase() : null],
    ['Bit depth', t.bit_depth ? `${t.bit_depth}-bit` : null],
    ['Colour', t.hdr ? `HDR${t.hdr_format ? ` (${t.hdr_format})` : ''}` : t.color_transfer ? `SDR · ${t.color_transfer}` : 'SDR'],
    ['Log', t.log_profile ? `Yes (${percent(t.log_confidence ?? 0)})` : 'No'],
    ['Orientation', t.orientation ? humanise(t.orientation) : null],
    ['Camera', [t.camera_make, t.camera_model].filter(Boolean).join(' ') || null],
    ['Lens', t.lens],
    ['Shot on', t.capture_date ? t.capture_date.slice(0, 10) : null],
    ['Audio', t.audio_channels ? `${t.audio_channels} channel${t.audio_channels === 1 ? '' : 's'}` : null],
  ]
  return rows.filter((r): r is [string, string] => Boolean(r[1]))
}
