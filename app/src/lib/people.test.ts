import { describe, expect, it } from 'vitest'
import type { Face, PersonRef } from '../api/types'
import { cleanName, groupFacesByFile, isPersonNote, mergePlan, onlyNames, mergeTarget, peopleInNote, personCounts, personLabel, personPhrases, personSearch } from './people'

const alex: PersonRef = { id: 12, name: 'Alex Rivera', label: 'Alex Rivera' }
const sam: PersonRef = { id: 3, name: 'Sam', label: 'Sam' }
const anon: PersonRef = { id: 40, name: null, label: 'Person 40' }

describe('person filter note', () => {
  const note = 'Only shots where Sam and Alex Rivera can be seen (recognised faces).'
  it('recognises the core note', () => {
    expect(isPersonNote(note)).toBe(true)
    expect(isPersonNote('Nothing in the library is tagged with Paris')).toBe(false)
  })
  it('maps the names to known people in the order given', () => {
    expect(peopleInNote(note, [alex, sam, anon]).map((p) => p.id)).toEqual([3, 12])
  })
  it('matches whole names only, case-insensitively', () => {
    expect(peopleInNote('Only shots where Samantha can be seen (recognised faces).', [sam])).toEqual([])
    expect(peopleInNote('Only shots where SAM can be seen (recognised faces).', [sam])).toEqual([sam])
  })
})

describe('person labels and phrases', () => {
  it('labels known people by name, others as Person N', () => {
    expect(personLabel('12', [alex])).toBe('Alex Rivera')
    expect(personLabel(40, new Map([[40, anon]]))).toBe('Person 40')
    expect(personLabel(7, [])).toBe('Person 7')
  })
  it('indexes names so a chip can find its words', () => {
    expect(personPhrases([alex, anon])).toEqual([{ phrase: 'alex rivera', vocab: 'person', term: '12' }])
  })
  it('tidies names like the core', () => {
    expect(cleanName('  Alex   Rivera ')).toBe('Alex Rivera')
    expect(cleanName('x'.repeat(100))).toHaveLength(80)
  })
  it('counts shots and files', () => {
    expect(personCounts({ faces: 11, shots: 9, files: 1 })).toBe('9 shots · 1 file')
  })
  it('searches by name, or by identity when unnamed', () => {
    expect(personSearch(alex)).toEqual({ q: 'Alex Rivera' })
    expect(personSearch(anon)).toEqual({ req: { person: ['40'] } })
  })
})

const face = (id: number, asset: string, shot: string): Face => ({
  id, t: id, box: [0, 0, 1, 1], score: 0.9, size_px: 100, thumb: `/media/${asset}/faces/${id}.jpg`, confirmed: false,
  shot_uid: shot, shot_number: 1, asset_uid: asset, filename: `${asset}.mp4`,
})

describe('faces by file', () => {
  it('groups in order and counts distinct shots', () => {
    const groups = groupFacesByFile([face(1, 'a', 'a-1'), face(2, 'a', 'a-1'), face(3, 'b', 'b-1'), face(4, 'a', 'a-2')])
    expect(groups.map((g) => [g.asset_uid, g.faces.length, g.shots])).toEqual([['a', 3, 2], ['b', 1, 1]])
  })
})

describe('merging people', () => {
  const p = (id: number, named: boolean, shots: number, faces = shots, name: string | null = named ? `N${id}` : null) => ({ id, named, shots, faces, name })
  it('keeps a named person, then the largest, then the oldest', () => {
    expect(mergeTarget([p(5, false, 9), p(6, true, 1)])?.id).toBe(6)
    expect(mergeTarget([p(5, false, 2), p(6, false, 9)])?.id).toBe(6)
    expect(mergeTarget([p(8, false, 2, 3), p(6, false, 2, 3)])?.id).toBe(6)
    expect(mergeTarget([])).toBeUndefined()
  })
  it('merges everyone else into the target and reports names that would be lost', () => {
    const plan = mergePlan([p(1, true, 2), p(2, false, 3), p(3, true, 1)], 1)
    expect(plan.into?.id).toBe(1)
    expect(plan.from.map((x) => x.id)).toEqual([2, 3])
    expect(plan.dropsNames).toEqual(['N3'])
    expect(plan.keepsName).toBe('N1')
    const unnamedTarget = mergePlan([p(1, false, 2), p(2, true, 3), p(3, true, 1)], 1)
    expect(unnamedTarget.keepsName).toBe('N2')
    expect(unnamedTarget.dropsNames).toEqual(['N3'])
  })
})

describe('name-only queries', () => {
  it('is a person filter when only names (and joining words) remain', () => {
    expect(onlyNames('Alex Rivera', ['Alex Rivera'])).toBe(true)
    expect(onlyNames('sam and alex rivera', ['Alex Rivera', 'Sam'])).toBe(true)
    expect(onlyNames('Alex Rivera at night', ['Alex Rivera'])).toBe(false)
    expect(onlyNames('night', [])).toBe(false)
  })
})
