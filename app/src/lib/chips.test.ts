import { describe, expect, it } from 'vitest'
import type { SearchResponse } from '../api/types'
import {
  activeFilterCount, buildPhraseIndex, chipsFromQuery, filterLabel, locateFilter, locateTerm, norm, promoteChip,
  preferenceMatch, removeChip, tidy, toggleExcludeChip, whyFilterLabels, type SearchState,
} from './chips'

const vocabs = {
  shot_size: { terms: [{ id: 'close_up', label: 'Close-up (CU)', synonyms: ['closeup', 'tight shot'] }, { id: 'long_shot', label: 'Long shot (LS)', synonyms: ['wide shot'] }] },
  camera_movement: { terms: [{ id: 'handheld', label: 'Handheld', synonyms: ['hand held', 'handheld camera'] }] },
  setting: { terms: [{ id: 'street', label: 'Street', synonyms: [] }] },
  time_of_day: { terms: [{ id: 'night', label: 'Night', synonyms: ['nighttime', 'after dark'] }] },
  pace: { terms: [{ id: 'fast', label: 'Fast', synonyms: ['busy', 'energetic'] }] },
}
const index = buildPhraseIndex(vocabs)
const label = (v: string, t: string) => (vocabs as Record<string, { terms: { id: string; label: string }[] }>)[v]?.terms.find((x) => x.id === t)?.label.replace(/\s*\(.*\)$/, '') ?? t

const q = 'handheld street food close-ups, busy, night'
const query = (over: Partial<SearchResponse['query']> = {}): SearchResponse['query'] => ({
  text: q,
  parsed: { text: q, semantic: q, keywords: ['food'], prefer: { shot_size: ['close_up'], camera_movement: ['handheld'], setting: ['street'], time_of_day: ['night'], pace: ['fast'] }, require: {}, exclude: {}, filters: {}, rights: {}, place: [], notes: [], limit: null, prefer_people: 4, context: '' },
  filters: {}, require: {}, exclude: {}, prefer: { shot_size: ['close_up'], camera_movement: ['handheld'], setting: ['street'], time_of_day: ['night'], pace: ['fast'] }, intended_use: null, limit: 120,
  ...over,
})
const state: SearchState = { q, require: {}, exclude: {}, filters: {} }

describe('phrase index', () => {
  it('normalises like the core', () => {
    expect(norm('Close-up (CU)')).toBe('close up cu')
    expect(norm('Night’s')).toBe("night's")
  })
  it('locates the words behind a term, including plurals', () => {
    expect(locateTerm(q, index, 'shot_size', 'close_up')?.text).toBe('close-ups')
    expect(locateTerm(q, index, 'pace', 'fast')?.text).toBe('busy')
    expect(locateTerm(q, index, 'camera_movement', 'handheld')?.text).toBe('handheld')
    expect(locateTerm('Night market', index, 'time_of_day', 'night')?.text).toBe('Night')
    expect(locateTerm(q, index, 'shot_size', 'long_shot')).toBeNull()
  })
})

describe('chips from a search response', () => {
  it('maps parsed preferences to inferred chips with their words', () => {
    const chips = chipsFromQuery(query(), state, label, index)
    expect(chips.map((c) => c.key)).toEqual([
      'prefer:shot_size:close_up', 'prefer:camera_movement:handheld', 'prefer:setting:street', 'prefer:time_of_day:night', 'prefer:pace:fast',
    ])
    const cu = chips[0]
    expect(cu).toMatchObject({ slate: 'SHOT SIZE', label: 'Close-up', inferred: true, words: 'close-ups' })
  })

  it('shows required terms once and marks explicit ones as not inferred', () => {
    const s = { ...state, require: { shot_size: ['close_up'] } }
    const chips = chipsFromQuery(query({ require: { shot_size: ['close_up'] } }), s, label, index)
    expect(chips.filter((c) => c.term === 'close_up')).toHaveLength(1)
    expect(chips[0]).toMatchObject({ kind: 'require', inferred: false })
  })

  it('groups technical filters and intended use', () => {
    const chips = chipsFromQuery(
      query({ filters: { min_fps: 49.5, min_height: 2160, min_duration: 2, max_duration: 10, log: true }, intended_use: { use: 'marketing', channel: 'organic_social', territory: 'gb' } }),
      { ...state, q: 'drone 4k 50fps log', filters: { min_duration: 2, max_duration: 10 } },
      label,
      index,
    )
    const byKey = Object.fromEntries(chips.map((c) => [c.key, c]))
    expect(byKey['filter:fps']).toMatchObject({ label: '50 fps or more', slate: 'FPS' })
    expect(byKey['filter:min_height']).toMatchObject({ label: '4K (UHD) or higher' })
    expect(byKey['filter:duration']).toMatchObject({ label: '2s – 10s', inferred: false })
    expect(byKey['filter:log']).toMatchObject({ label: 'Log profile' })
    expect(byKey.use).toMatchObject({ slate: 'RIGHTS', label: 'marketing · organic_social · GB' })
  })

  it('labels people and edit stage filters', () => {
    expect(filterLabel('people', { max_people: 0 })).toBe('No people')
    expect(filterLabel('people', { min_people: 1, max_people: 1 })).toBe('One person')
    expect(filterLabel('edit_type', { edit_type: ['raw', 'selects'] })).toBe('Raw, Selects')
    expect(filterLabel('duration', {})).toBeNull()
  })
})

describe('chip edits', () => {
  const chips = chipsFromQuery(query(), state, label, index)
  it('removing an inferred chip removes its words', () => {
    expect(removeChip(state, chips[0], index)?.q).toBe('handheld street food, busy, night')
    expect(removeChip(state, chips[4], index)?.q).toBe('handheld street food close-ups, night')
    expect(removeChip(state, chips[3], index)?.q).toBe('handheld street food close-ups, busy')
  })
  it('promotes a preference to a requirement', () => {
    const s = promoteChip(state, chips[0])
    expect(s.require).toEqual({ shot_size: ['close_up'] })
    expect(s.q).toBe(q)
  })
  it('toggles exclusion', () => {
    const s = toggleExcludeChip(state, chips[3], index)
    expect(s?.exclude).toEqual({ time_of_day: ['night'] })
    expect(s?.q).toBe('handheld street food close-ups, busy')
  })
  it('removes a parsed negation with its words', () => {
    const qq = 'street food, not at night'
    const ex = { key: 'exclude:time_of_day:night', kind: 'exclude' as const, vocab: 'time_of_day', term: 'night', slate: '', label: '', inferred: true }
    expect(removeChip({ ...state, q: qq }, ex, index)?.q).toBe('street food')
  })
  it('removes technical filter words and explicit filters', () => {
    const s: SearchState = { q: 'drone 4k 50fps sunset', require: {}, exclude: {}, filters: {} }
    expect(locateFilter(s.q, 'fps')?.text).toBe('50fps')
    const fps = { key: 'filter:fps', kind: 'filter' as const, filter: 'fps' as const, slate: '', label: '', inferred: true }
    expect(removeChip(s, fps, index)?.q).toBe('drone 4k sunset')
    const res = { ...fps, key: 'filter:min_height', filter: 'min_height' as const }
    expect(removeChip(s, res, index)?.q).toBe('drone 50fps sunset')
    const dur = { ...fps, key: 'filter:duration', filter: 'duration' as const, inferred: false }
    expect(removeChip({ ...s, filters: { min_duration: 2 } }, dur, index)?.filters).toEqual({})
  })
  it('returns null when an inferred chip cannot be traced to words', () => {
    const ghost = { key: 'prefer:shot_size:long_shot', kind: 'prefer' as const, vocab: 'shot_size', term: 'long_shot', slate: '', label: '', inferred: true }
    expect(removeChip(state, ghost, index)).toBeNull()
  })
  it('tidies punctuation', () => {
    expect(tidy(' , a ,, b , ')).toBe('a, b')
    expect(tidy('street food and')).toBe('street food')
  })
  it('counts active filters', () => {
    expect(activeFilterCount({ q: '', require: { a: ['x', 'y'] }, exclude: { b: ['z'] }, filters: { min_fps: 50, max_fps: 60, log: true }, use: { use: 'marketing' } })).toBe(6)
  })
})

describe('why it matched', () => {
  it('counts preferences matched', () => {
    const why = [
      { signal: 'visual similarity', detail: 'x' },
      { signal: 'time_of_day', detail: 'Night', term: 'night' },
      { signal: 'shot_size', detail: 'not labelled', term: 'close_up', missing: true },
      { signal: 'setting', detail: 'Street', term: 'street' },
    ]
    expect(preferenceMatch(why)).toEqual({ matched: 2, total: 3 })
    const kw = [{ signal: 'keywords', detail: 'x' }]
    expect(preferenceMatch(kw)).toBeNull()
  })
  it('writes filter matches as people would', () => {
    const why = [
      { signal: 'filter', detail: 'min height: 1080', filter: 'min_height' },
      { signal: 'filter', detail: 'min fps: 25', filter: 'min_fps' },
      { signal: 'filter', detail: 'orientation: horizontal', filter: 'orientation' },
      { signal: 'filter', detail: 'log: False', filter: 'log' },
      { signal: 'filter', detail: 'min duration: 2', filter: 'min_duration' },
      { signal: 'filter', detail: 'max duration: 10', filter: 'max_duration' },
      { signal: 'setting', detail: 'Street', term: 'street' },
    ]
    expect(whyFilterLabels(why)).toEqual(['2s – 10s', '25 fps or more', '1080p or higher', 'Horizontal', 'Not log'])
  })
})
