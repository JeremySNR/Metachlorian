/**
 * Query-chip mapping (system.md §3.2–3.3).
 *
 * The core parses the natural-language query into preferences (soft), required
 * and excluded terms (hard), typed filters and an intended use. This module turns
 * the echoed `query` block of a search response into chips, finds the words each
 * inferred chip came from ("From your words 'close-ups'"), and applies chip edits
 * (remove, promote to required, toggle exclude) to the search state. Removing an
 * inferred chip edits the words, because the server re-parses the text each time.
 */
import type { IntendedUse, SearchFilters, SearchResponse, TermMap, WhyItem } from '../api/types'
import { humanise } from './format'

export type ChipKind = 'prefer' | 'require' | 'exclude' | 'filter' | 'use' | 'place' | 'person'
export type FilterGroup =
  | 'duration'
  | 'fps'
  | 'people'
  | 'min_height'
  | 'orientation'
  | 'log'
  | 'hdr'
  | 'usable'
  | 'speech'
  | 'music'
  | 'edit_type'
  | 'captured'
  | 'min_quality'

export interface QueryChip {
  key: string
  kind: ChipKind
  vocab?: string
  term?: string
  filter?: FilterGroup
  slate: string
  label: string
  /** True when it came from the person's words rather than an explicit filter. */
  inferred: boolean
  /** The words it came from, when they can be located in the query text. */
  words?: string
}

/** What the person controls directly (the URL state). */
export interface SearchState {
  q: string
  require: TermMap
  exclude: TermMap
  filters: SearchFilters
  use?: IntendedUse | null
}

export type LabelFn = (vocab: string, term: string) => string

export const VOCAB_SLATE: Record<string, string> = {
  shot_size: 'SHOT SIZE',
  camera_movement: 'MOVEMENT',
  camera_angle: 'ANGLE',
  shot_role: 'ROLE',
  setting: 'SETTING',
  time_of_day: 'TIME OF DAY',
  weather: 'WEATHER',
  season: 'SEASON',
  mood: 'MOOD',
  pace: 'PACE',
  speed_effect: 'SPEED',
  audio_class: 'AUDIO',
  edit_type: 'EDIT STAGE',
  quality_flag: 'QUALITY',
  object: 'OBJECT',
  concept: 'CONCEPT',
  look: 'LOOK',
  resolution: 'RESOLUTION',
  orientation: 'ORIENTATION',
  person: 'PERSON',
}

export const FILTER_SLATE: Record<FilterGroup, string> = {
  duration: 'DURATION',
  fps: 'FPS',
  people: 'PEOPLE',
  min_height: 'RESOLUTION',
  orientation: 'ORIENTATION',
  log: 'LOG',
  hdr: 'HDR',
  usable: 'QUALITY',
  speech: 'SPEECH',
  music: 'MUSIC',
  edit_type: 'EDIT STAGE',
  captured: 'SHOT DATE',
  min_quality: 'QUALITY',
}

/** Which request filter keys each chip group covers. */
export const FILTER_KEYS: Record<FilterGroup, (keyof SearchFilters)[]> = {
  duration: ['min_duration', 'max_duration'],
  fps: ['min_fps', 'max_fps'],
  people: ['min_people', 'max_people'],
  min_height: ['min_height'],
  orientation: ['orientation'],
  log: ['log'],
  hdr: ['hdr'],
  usable: ['usable'],
  speech: ['speech'],
  music: ['music'],
  edit_type: ['edit_type'],
  captured: ['captured_after', 'captured_before'],
  min_quality: ['min_quality'],
}

const HEIGHT_LABEL: Record<number, string> = { 4320: '8K', 3160: '6K', 2160: '4K (UHD)', 1440: '1440p', 1080: '1080p', 720: '720p' }

export function heightLabel(h: number): string {
  return HEIGHT_LABEL[h] ?? `${h}p`
}

const num = (v: number) => (Number.isInteger(v) ? String(v) : String(Math.round(v * 10) / 10))
const has = (v: unknown) => v !== undefined && v !== null && v !== ''

/** Human label for one filter group, or null when the group is not set. */
export function filterLabel(group: FilterGroup, f: SearchFilters, label?: LabelFn): string | null {
  switch (group) {
    case 'duration': {
      const lo = f.min_duration
      const hi = f.max_duration
      if (has(lo) && has(hi)) return `${num(lo as number)}s – ${num(hi as number)}s`
      if (has(lo)) return `${num(lo as number)}s or longer`
      if (has(hi)) return `Up to ${num(hi as number)}s`
      return null
    }
    case 'fps': {
      const lo = f.min_fps
      const hi = f.max_fps
      if (has(lo) && has(hi)) return `${Math.ceil(lo as number)}–${Math.floor(hi as number)} fps`
      if (has(lo)) return `${Math.ceil(lo as number)} fps or more`
      if (has(hi)) return `Up to ${Math.floor(hi as number)} fps`
      return null
    }
    case 'people': {
      const lo = f.min_people
      const hi = f.max_people
      if (hi === 0) return 'No people'
      if (lo === 1 && hi === 1) return 'One person'
      if (has(lo) && has(hi)) return `${lo}–${hi} people`
      if (has(lo)) return `${lo} or more ${lo === 1 ? 'person' : 'people'}`
      if (has(hi)) return `Up to ${hi} people`
      return null
    }
    case 'min_height':
      return has(f.min_height) ? `${heightLabel(f.min_height as number)} or higher` : null
    case 'orientation':
      return f.orientation ? humanise(f.orientation) : null
    case 'log':
      return has(f.log) ? (f.log ? 'Log profile' : 'Not log') : null
    case 'hdr':
      return has(f.hdr) ? (f.hdr ? 'HDR' : 'SDR') : null
    case 'usable':
      return has(f.usable) ? (f.usable ? 'Usable only' : 'Unusable only') : null
    case 'speech':
      return has(f.speech) ? (f.speech ? 'With speech' : 'No speech') : null
    case 'music':
      return has(f.music) ? (f.music ? 'With music' : 'No music') : null
    case 'edit_type': {
      const v = f.edit_type
      if (!v || (Array.isArray(v) && !v.length)) return null
      const list = Array.isArray(v) ? v : [v]
      return list.map((t) => (label ? label('edit_type', t) : humanise(t))).join(', ')
    }
    case 'captured': {
      const a = f.captured_after
      const b = f.captured_before
      if (a && b) return `${a} – ${b}`
      if (a) return `After ${a}`
      if (b) return `Before ${b}`
      return null
    }
    case 'min_quality':
      return has(f.min_quality) ? `Score ${f.min_quality} or more` : null
  }
}

export function intendedUseLabel(use: IntendedUse | null | undefined, label?: LabelFn): string | null {
  if (!use) return null
  const parts: string[] = []
  if (use.use) parts.push(label ? label('usage', use.use) : humanise(use.use))
  if (use.channel) parts.push(label ? label('channel', use.channel) : humanise(use.channel))
  if (use.territory) parts.push(use.territory.toUpperCase())
  return parts.length ? parts.join(' · ') : null
}

// ---------------------------------------------------------------- phrase index

/** The core's normalisation (vocab/__init__.py norm). */
export function norm(s: string): string {
  return s
    .toLowerCase()
    .replace(/[-_]/g, ' ')
    .replace(/’/g, "'")
    .replace(/[^\p{L}\p{N}_' ]/gu, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

export interface PhraseEntry {
  phrase: string
  vocab: string
  term: string
}

/** Extra phrases the parser knows that the vocabularies do not carry (parse.py EXTRA). */
const EXTRA: Record<string, [string, string]> = {
  drone: ['camera_movement', 'aerial'],
  'drone shot': ['camera_movement', 'aerial'],
  aerial: ['camera_movement', 'aerial'],
  wide: ['shot_size', 'long_shot'],
  'wide shot': ['shot_size', 'long_shot'],
  wides: ['shot_size', 'long_shot'],
  'close up': ['shot_size', 'close_up'],
  'close ups': ['shot_size', 'close_up'],
  closeup: ['shot_size', 'close_up'],
  closeups: ['shot_size', 'close_up'],
  cu: ['shot_size', 'close_up'],
  ecu: ['shot_size', 'extreme_close_up'],
  coastline: ['setting', 'coast'],
  coast: ['setting', 'coast'],
  beach: ['setting', 'coast'],
  seaside: ['setting', 'coast'],
  street: ['setting', 'street'],
  city: ['setting', 'urban'],
  indoors: ['setting', 'interior'],
  outdoors: ['setting', 'exterior'],
  night: ['time_of_day', 'night'],
  nighttime: ['time_of_day', 'night'],
  sunset: ['time_of_day', 'sunset'],
  slow: ['pace', 'slow'],
  calm: ['pace', 'slow'],
  fast: ['pace', 'fast'],
  busy: ['pace', 'fast'],
  interview: ['shot_role', 'interview'],
  interviews: ['shot_role', 'interview'],
  cutaway: ['shot_role', 'cutaway'],
  cutaways: ['shot_role', 'cutaway'],
  'b roll': ['shot_role', 'b_roll'],
  broll: ['shot_role', 'b_roll'],
  establishing: ['shot_role', 'establishing'],
  'piece to camera': ['shot_role', 'piece_to_camera'],
  ptc: ['shot_role', 'piece_to_camera'],
  raw: ['edit_type', 'raw'],
  'raw footage': ['edit_type', 'raw'],
  rushes: ['edit_type', 'raw'],
  selects: ['edit_type', 'selects'],
  finished: ['edit_type', 'finished'],
  'finished edit': ['edit_type', 'finished'],
  'final edit': ['edit_type', 'finished'],
  'slow motion': ['speed_effect', 'slow_motion'],
  slowmo: ['speed_effect', 'slow_motion'],
  'slo mo': ['speed_effect', 'slow_motion'],
  timelapse: ['speed_effect', 'time_lapse'],
  'time lapse': ['speed_effect', 'time_lapse'],
  hyperlapse: ['speed_effect', 'hyperlapse'],
  'golden hour': ['time_of_day', 'golden_hour'],
}

export interface VocabLike {
  terms: { id: string; label: string; synonyms?: string[] }[]
}

export function buildPhraseIndex(vocabs: Record<string, VocabLike | undefined>): PhraseEntry[] {
  const seen = new Set<string>()
  const out: PhraseEntry[] = []
  const add = (phrase: string, vocab: string, term: string) => {
    const p = norm(phrase)
    const k = `${p}|${vocab}|${term}`
    if (p.length < 2 || seen.has(k)) return
    seen.add(k)
    out.push({ phrase: p, vocab, term })
  }
  for (const [vocab, v] of Object.entries(vocabs)) {
    if (!v) continue
    for (const t of v.terms) {
      add(t.id, vocab, t.id)
      add(t.label, vocab, t.id)
      add(t.label.replace(/\s*\([^)]*\)/g, ''), vocab, t.id)
      const abbr = /\(([^)]+)\)/.exec(t.label)?.[1]
      if (abbr) add(abbr, vocab, t.id)
      for (const s of t.synonyms ?? []) add(s, vocab, t.id)
    }
  }
  for (const [phrase, [vocab, term]] of Object.entries(EXTRA)) add(phrase, vocab, term)
  out.sort((a, b) => b.phrase.length - a.phrase.length)
  return out
}

export interface Span {
  start: number
  end: number
  text: string
}

/** Normalise `q` while remembering where each normalised character came from. */
function normWithMap(q: string): { s: string; map: number[] } {
  let s = ''
  const map: number[] = []
  let lastSpace = true
  for (let i = 0; i < q.length; i++) {
    let c = q[i].toLowerCase()
    if (c === '’') c = "'"
    if (/[\p{L}\p{N}']/u.test(c)) {
      s += c
      map.push(i)
      lastSpace = false
    } else if (!lastSpace) {
      s += ' '
      map.push(i)
      lastSpace = true
    }
  }
  return { s, map }
}

function findPhrase(q: string, phrase: string): Span | null {
  const { s, map } = normWithMap(q)
  const hay = ` ${s} `
  for (const candidate of [phrase, `${phrase}s`, `${phrase}es`]) {
    const needle = ` ${candidate} `
    const at = hay.indexOf(needle)
    if (at >= 0) {
      const startN = at // index in s of the first char (hay has a leading space)
      const endN = startN + candidate.length - 1
      const start = map[startN]
      const end = map[endN] + 1
      return { start, end, text: q.slice(start, end) }
    }
  }
  return null
}

/** Locate the words in `q` that map to (vocab, term), longest phrase first. */
export function locateTerm(q: string, index: PhraseEntry[], vocab: string, term: string): Span | null {
  for (const e of index) {
    if (e.vocab !== vocab || e.term !== term) continue
    const sp = findPhrase(q, e.phrase)
    if (sp) return sp
  }
  return null
}

// Technical filter patterns (ported from search/parse.py) for locating and removing words.
const NUM = String.raw`(\d+(?:\.\d+)?)`
const UNIT = String.raw`\s*(?:s|sec|secs|seconds?)\b`
const FILTER_PATTERNS: Record<FilterGroup, RegExp[]> = {
  duration: [
    new RegExp(String.raw`\b(?:at least|min(?:imum)?|longer than|more than|over|>=?)\s*${NUM}${UNIT}`, 'gi'),
    new RegExp(String.raw`\b${NUM}${UNIT.replace(/\\b$/, '')}\s*(?:\+|or (?:more|longer)|plus)`, 'gi'),
    new RegExp(String.raw`\b(?:at most|max(?:imum)?|shorter than|less than|under|<=?)\s*${NUM}${UNIT}`, 'gi'),
    new RegExp(String.raw`\b${NUM}\s*(?:-|to)\s*${NUM}${UNIT}`, 'gi'),
  ],
  min_height: [/\b(8k|4320p|6k|4k|uhd|2160p|2\.7k|1440p|qhd|1080p?|full hd|fhd|720p|hd)\b/gi],
  fps: [new RegExp(String.raw`\b${NUM}\s*(?:fps|p(?=\b)|frames per second)`, 'gi')],
  orientation: [/\b(vertical|portrait|9[:x]16|horizontal|landscape|16[:x]9)\b/gi],
  log: [/\b(log|flat profile|s-?log\d?|v-?log|c-?log|apple log|ungraded)\b/gi],
  hdr: [/\bhdr\b/gi],
  usable: [/\b(usable|good quality|sharp)\b/gi],
  speech: [/\b(with speech|talking|dialogue|speaking|no speech|without speech|no dialogue|no talking|silent)\b/gi],
  music: [/\b(no music|without music|with music)\b/gi],
  people: [
    /\b(no|without|zero|empty of) (people|person|persons|humans|crowds?)\b|\b(nobody|no one|empty|deserted|unpeopled)\b/gi,
    /\b(one|single|a single|1|lone|solo) (person|man|woman|people|presenter|subject)\b/gi,
    /\b(with|including|showing) (people|a person|someone|crowds?)\b/gi,
  ],
  edit_type: [],
  captured: [],
  min_quality: [],
}

export function locateFilter(q: string, group: FilterGroup): Span | null {
  for (const rx of FILTER_PATTERNS[group]) {
    rx.lastIndex = 0
    const m = rx.exec(q)
    if (m) return { start: m.index, end: m.index + m[0].length, text: m[0] }
  }
  return null
}

/** Remove a span from the text and tidy the punctuation left behind. */
export function removeSpan(q: string, span: Span): string {
  return tidy(q.slice(0, span.start) + ' ' + q.slice(span.end))
}

export function tidy(q: string): string {
  return q
    .replace(/\s+/g, ' ')
    .replace(/\s+([,.;])/g, '$1')
    .replace(/([,;])(\s*[,;])+/g, '$1')
    .replace(/^[\s,;.]+|[\s,;]+$/g, '')
    .replace(/\b(and|or|with|in|at|of)\s*$/i, '')
    .replace(/^(and|or)\b\s*/i, '')
    .replace(/\s+/g, ' ')
    .replace(/[\s,;]+$/g, '')
    .trim()
}

// ---------------------------------------------------------------- chips from a response

const listHas = (m: TermMap | undefined, vocab: string, term: string) => Boolean(m?.[vocab]?.includes(term))

export function chipsFromQuery(query: SearchResponse['query'], state: SearchState, label: LabelFn, index: PhraseEntry[] = []): QueryChip[] {
  const chips: QueryChip[] = []
  const parsed = query.parsed
  const q = state.q
  const words = (vocab: string, term: string) => locateTerm(q, index, vocab, term)?.text
  for (const [vocab, terms] of Object.entries(query.require ?? {})) {
    for (const term of terms) {
      if (vocab === 'person') {
        // A recognised person (face identity): from a known name in the words, or an explicit filter. Always hard.
        chips.push({ key: `person:${term}`, kind: 'person', vocab, term, slate: 'PERSON', label: label(vocab, term), inferred: !listHas(state.require, vocab, term), words: words(vocab, term) })
        continue
      }
      chips.push({ key: `require:${vocab}:${term}`, kind: 'require', vocab, term, slate: VOCAB_SLATE[vocab] ?? vocab.toUpperCase(), label: label(vocab, term), inferred: !listHas(state.require, vocab, term), words: words(vocab, term) })
    }
  }
  for (const [vocab, terms] of Object.entries(query.prefer ?? {})) {
    for (const term of terms) {
      if (listHas(query.require, vocab, term)) continue
      chips.push({ key: `prefer:${vocab}:${term}`, kind: 'prefer', vocab, term, slate: VOCAB_SLATE[vocab] ?? vocab.toUpperCase(), label: label(vocab, term), inferred: true, words: words(vocab, term) })
    }
  }
  for (const [vocab, terms] of Object.entries(query.exclude ?? {})) {
    for (const term of terms) {
      chips.push({ key: `exclude:${vocab}:${term}`, kind: 'exclude', vocab, term, slate: `NOT ${VOCAB_SLATE[vocab] ?? vocab.toUpperCase()}`, label: label(vocab, term), inferred: !listHas(state.exclude, vocab, term), words: words(vocab, term) })
    }
  }
  const f = query.filters ?? {}
  for (const group of Object.keys(FILTER_KEYS) as FilterGroup[]) {
    const text = filterLabel(group, f, label)
    if (!text) continue
    const keys = FILTER_KEYS[group]
    const explicit = keys.some((k) => has(state.filters?.[k]))
    const fromWords = keys.some((k) => has(parsed?.filters?.[k]))
    chips.push({ key: `filter:${group}`, kind: 'filter', filter: group, slate: FILTER_SLATE[group], label: text, inferred: fromWords && !explicit, words: fromWords ? locateFilter(q, group)?.text : undefined })
  }
  for (const place of parsed?.place ?? []) {
    chips.push({ key: `place:${place}`, kind: 'place', slate: 'PLACE', label: place, inferred: true, words: place })
  }
  const ul = intendedUseLabel(query.intended_use, label)
  if (ul) chips.push({ key: 'use', kind: 'use', slate: 'RIGHTS', label: ul, inferred: !state.use })
  return chips
}

// ---------------------------------------------------------------- chip edits

const without = (m: TermMap | undefined, vocab: string, term: string): TermMap => {
  const out: TermMap = {}
  for (const [k, v] of Object.entries(m ?? {})) {
    const rest = k === vocab ? v.filter((t) => t !== term) : v
    if (rest.length) out[k] = rest
  }
  return out
}

const withTerm = (m: TermMap | undefined, vocab: string, term: string): TermMap => {
  const cur = m?.[vocab] ?? []
  return { ...(m ?? {}), [vocab]: cur.includes(term) ? cur : [...cur, term] }
}

const NEGATION = /\b(?:no|not|without|exclude|excluding|except)\s+(?:at\s+|in\s+|the\s+)?$/i

/** Remove the words behind an inferred term chip (and a preceding negation for exclusions). */
function removeTermWords(q: string, index: PhraseEntry[], vocab: string, term: string, negated: boolean): string | null {
  const sp = locateTerm(q, index, vocab, term)
  if (!sp) return null
  let start = sp.start
  if (negated) {
    const m = NEGATION.exec(q.slice(0, sp.start))
    if (m) start = sp.start - m[0].length
  }
  return removeSpan(q, { ...sp, start })
}

/**
 * Apply "remove" to a chip. Returns the new state, or null when an inferred chip's
 * words could not be found (the caller then explains rather than silently failing).
 */
export function removeChip(state: SearchState, chip: QueryChip, index: PhraseEntry[]): SearchState | null {
  const next: SearchState = { ...state, require: { ...state.require }, exclude: { ...state.exclude }, filters: { ...state.filters } }
  switch (chip.kind) {
    case 'require':
    case 'prefer': {
      const vocab = chip.vocab as string
      const term = chip.term as string
      next.require = without(state.require, vocab, term)
      const explicit = listHas(state.require, vocab, term)
      const q = removeTermWords(state.q, index, vocab, term, false)
      if (q !== null) next.q = q
      else if (!explicit) return null
      return next
    }
    case 'exclude': {
      const vocab = chip.vocab as string
      const term = chip.term as string
      if (listHas(state.exclude, vocab, term)) {
        next.exclude = without(state.exclude, vocab, term)
        return next
      }
      const q = removeTermWords(state.q, index, vocab, term, true)
      if (q === null) return null
      next.q = q
      return next
    }
    case 'person': {
      // Drop the explicit filter and the name in the words; the core re-reads names from the text.
      const term = chip.term as string
      const explicit = listHas(state.require, 'person', term)
      next.require = without(state.require, 'person', term)
      const q = removeTermWords(state.q, index, 'person', term, false)
      if (q !== null) next.q = q
      else if (!explicit) return null
      return next
    }
    case 'filter': {
      const group = chip.filter as FilterGroup
      let changed = false
      for (const k of FILTER_KEYS[group]) {
        if (has(next.filters[k])) {
          delete next.filters[k]
          changed = true
        }
      }
      let q = state.q
      for (let i = 0; i < 4; i++) {
        const sp = locateFilter(q, group)
        if (!sp) break
        q = removeSpan(q, sp)
        changed = true
      }
      next.q = q
      return changed ? next : null
    }
    case 'place': {
      const sp = findPhraseExact(state.q, chip.label)
      if (!sp) return null
      const m = /\b(?:from|in|at|of)\s+$/i.exec(state.q.slice(0, sp.start))
      next.q = removeSpan(state.q, { ...sp, start: m ? sp.start - m[0].length : sp.start })
      return next
    }
    case 'use': {
      next.use = null
      const m = /\b(?:cleared|licensed|allowed|ok|approved|safe|can use|able to use|we can use|permitted)\b.*?\b(?:for|on|in)\b\s+[a-z][a-z ]{2,40}/i.exec(state.q)
      if (m) next.q = removeSpan(state.q, { start: m.index, end: m.index + m[0].length, text: m[0] })
      return next
    }
  }
}

function findPhraseExact(q: string, text: string): Span | null {
  const at = q.indexOf(text)
  return at >= 0 ? { start: at, end: at + text.length, text } : null
}

/** Promote a preference to a hard requirement (the words stay). */
export function promoteChip(state: SearchState, chip: QueryChip): SearchState {
  if (!chip.vocab || !chip.term || chip.kind === 'person') return state
  return { ...state, require: withTerm(state.require, chip.vocab, chip.term) }
}

/** Demote a requirement back to a preference (only meaningful when the words remain). */
export function demoteChip(state: SearchState, chip: QueryChip): SearchState {
  if (!chip.vocab || !chip.term || chip.kind === 'person') return state
  return { ...state, require: without(state.require, chip.vocab, chip.term) }
}

/** Alt+click / Alt+Enter: a preference or requirement becomes an exclusion, and back. */
export function toggleExcludeChip(state: SearchState, chip: QueryChip, index: PhraseEntry[]): SearchState | null {
  if (!chip.vocab || !chip.term || chip.kind === 'person') return null
  const vocab = chip.vocab
  const term = chip.term
  if (chip.kind === 'exclude') {
    const removed = removeChip(state, chip, index)
    if (!removed) return null
    return { ...removed, require: withTerm(removed.require, vocab, term) }
  }
  const removed = removeChip(state, chip, index) ?? { ...state, require: without(state.require, vocab, term) }
  return { ...removed, exclude: withTerm(removed.exclude, vocab, term) }
}

/** True when the state has anything beyond free text. */
export function hasConstraints(state: SearchState): boolean {
  return (
    Object.values(state.require ?? {}).some((v) => v.length) ||
    Object.values(state.exclude ?? {}).some((v) => v.length) ||
    Object.values(state.filters ?? {}).some(has) ||
    Boolean(state.use && (state.use.use || state.use.channel || state.use.territory))
  )
}

/** Count of active filters for the rail header (--key count). */
export function activeFilterCount(state: SearchState): number {
  let n = 0
  for (const v of Object.values(state.require ?? {})) n += v.length
  for (const v of Object.values(state.exclude ?? {})) n += v.length
  const f = state.filters ?? {}
  for (const g of Object.keys(FILTER_KEYS) as FilterGroup[]) if (FILTER_KEYS[g].some((k) => has(f[k]))) n++
  if (state.use && (state.use.use || state.use.channel || state.use.territory)) n++
  return n
}

// ---------------------------------------------------------------- why it matched

/** Preferences the result has, out of those the query asked for ("3 of 5 preferences"). */
export function preferenceMatch(why: readonly Pick<WhyItem, 'signal' | 'term' | 'missing'>[] | undefined): { matched: number; total: number } | null {
  const prefs = (why ?? []).filter((w) => w.term)
  if (!prefs.length) return null
  return { matched: prefs.filter((w) => !w.missing).length, total: prefs.length }
}

function parseFilterValue(v: string): unknown {
  const t = v.trim()
  if (t === 'True' || t === 'true') return true
  if (t === 'False' || t === 'false') return false
  if (/^-?\d+(\.\d+)?$/.test(t)) return Number(t)
  if (t.startsWith('[')) {
    try {
      return JSON.parse(t.replace(/'/g, '"'))
    } catch {
      return t
    }
  }
  return t
}

/**
 * "Matches your filters" lines from a result's `why` (signal "filter", detail "min height: 1080"):
 * grouped like the filter chips ("1080p or higher", "2s – 10s", "Not log"), never raw keys.
 */
export function whyFilterLabels(why: { signal: string; detail: string; filter?: string }[] | undefined, label?: LabelFn): string[] {
  const f: Record<string, unknown> = {}
  const unknown: string[] = []
  for (const w of why ?? []) {
    if (w.signal !== 'filter') continue
    const key = w.filter ?? w.detail.split(':')[0].trim().replace(/\s+/g, '_')
    const raw = w.detail.includes(':') ? w.detail.slice(w.detail.indexOf(':') + 1) : ''
    if (Object.values(FILTER_KEYS).some((keys) => (keys as string[]).includes(key))) f[key] = parseFilterValue(raw)
    else unknown.push(humanise(w.detail.replace(/:\s*/, ': ')))
  }
  const out: string[] = []
  for (const group of Object.keys(FILTER_KEYS) as FilterGroup[]) {
    const text = filterLabel(group, f as SearchFilters, label)
    if (text) out.push(text)
  }
  return [...out, ...unknown]
}
