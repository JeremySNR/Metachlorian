/**
 * Face identity (People). Pure helpers over /api/people and the search response:
 * the person chip the core's name filter implies, grouping a person's faces by file,
 * and which person a merge keeps. Face data stays in this library; nothing here sends it anywhere.
 */
import type { Face, PersonRef, PersonSummary } from '../api/types'
import { norm, type PhraseEntry } from './chips'
import { plural } from './format'

/** Vocabulary key the core uses for identities in `require` ({"person": ["12"]}). */
export const PERSON_VOCAB = 'person'

/** The core's note when a known name in the query became a hard filter (search/engine.py). */
const PERSON_NOTE = /^Only shots where (.+) can be seen \(recognised faces\)\.$/

export function isPersonNote(note: string): boolean {
  return PERSON_NOTE.test(note.trim())
}

/**
 * The named people a person-filter note is about, in the order the note names them.
 * Names are matched against the people the library knows (the note title-cases them).
 */
export function peopleInNote(note: string, people: readonly PersonRef[]): PersonRef[] {
  const m = PERSON_NOTE.exec(note.trim())
  if (!m) return []
  const text = ` ${norm(m[1])} `
  return people
    .filter((p) => p.name && text.includes(` ${norm(p.name)} `))
    .map((p) => ({ p, at: text.indexOf(` ${norm(p.name as string)} `) }))
    .sort((a, b) => a.at - b.at)
    .map((x) => x.p)
}

/** Phrases for the chip index, so a person chip can find (and remove) the name in the query text. */
export function personPhrases(people: readonly PersonRef[]): PhraseEntry[] {
  return people
    .filter((p) => p.name && norm(p.name).length >= 2)
    .map((p) => ({ phrase: norm(p.name as string), vocab: PERSON_VOCAB, term: String(p.id) }))
}

/** "Alex Rivera", or "Person 12" when unnamed or unknown. */
export function personLabel(id: string | number, people: ReadonlyMap<number, PersonRef> | readonly PersonRef[]): string {
  const n = Number(id)
  const found = people instanceof Map ? people.get(n) : (people as readonly PersonRef[]).find((p) => p.id === n)
  return found?.name || found?.label || `Person ${id}`
}

/** "9 shots · 2 files" (faces only when they differ from shots). */
export function personCounts(p: Pick<PersonSummary, 'faces' | 'shots' | 'files'>): string {
  const parts = [plural(p.shots, 'shot'), plural(p.files, 'file')]
  return parts.join(' · ')
}

/** Tidy a typed name the way the core stores it: single spaces, at most 80 characters. */
export function cleanName(name: string): string {
  return name.split(/\s+/).filter(Boolean).join(' ').slice(0, 80)
}

export interface FaceGroup {
  asset_uid: string
  filename: string
  faces: Face[]
  /** Distinct shots in this file. */
  shots: number
}

/** A person's faces grouped by file, in the order the core returns them (file name, then time). */
export function groupFacesByFile(faces: readonly Face[]): FaceGroup[] {
  const out = new Map<string, FaceGroup>()
  for (const f of faces) {
    let g = out.get(f.asset_uid)
    if (!g) {
      g = { asset_uid: f.asset_uid, filename: f.filename, faces: [], shots: 0 }
      out.set(f.asset_uid, g)
    }
    g.faces.push(f)
  }
  for (const g of out.values()) g.shots = new Set(g.faces.map((f) => f.shot_uid)).size
  return [...out.values()]
}

/**
 * Which person a merge keeps: a named one first (their name survives), then the one in the most
 * shots, then the most faces, then the oldest (lowest id), so the result is predictable.
 */
export function mergeTarget<T extends Pick<PersonSummary, 'id' | 'named' | 'shots' | 'faces'>>(people: readonly T[]): T | undefined {
  return [...people].sort((a, b) => Number(b.named) - Number(a.named) || b.shots - a.shots || b.faces - a.faces || a.id - b.id)[0]
}

/**
 * Merge order: every other selected person goes into `intoId`, in the order given. The core keeps the
 * target's name, or takes the first merged name when the target has none; any other name is lost,
 * so the dialog says which.
 */
export function mergePlan<T extends Pick<PersonSummary, 'id' | 'named' | 'name'>>(selected: readonly T[], intoId: number): { into: T | undefined; from: T[]; keepsName: string | null; dropsNames: string[] } {
  const into = selected.find((p) => p.id === intoId)
  const from = selected.filter((p) => p.id !== intoId)
  const named = from.filter((p) => p.named && p.name)
  const keepsName = (into?.named && into.name) || named[0]?.name || null
  const dropsNames = named.map((p) => p.name as string).filter((n) => n !== keepsName)
  return { into, from, keepsName, dropsNames }
}

/** Named people first (A–Z), then unnamed by size: the order the People page lists them in. */
export function splitPeople<T extends Pick<PersonSummary, 'named'>>(people: readonly T[]): { named: T[]; unnamed: T[] } {
  return { named: people.filter((p) => p.named), unnamed: people.filter((p) => !p.named) }
}

/** Search for a person: by name when named (the core turns a known name into a hard filter), else by identity. */
export function personSearch(p: PersonRef): { q?: string; req?: Record<string, string[]> } {
  return p.name ? { q: p.name } : { req: { [PERSON_VOCAB]: [String(p.id)] } }
}

/**
 * True when the query is nothing but the names the core filtered by ("Alex Rivera", "Sam and Alex").
 * Such a search is a person filter, not a scored description, so it has no strong/weak split.
 */
export function onlyNames(q: string, names: readonly string[]): boolean {
  if (!names.length) return false
  let rest = ` ${norm(q)} `
  for (const n of [...names].sort((a, b) => b.length - a.length)) rest = rest.split(` ${norm(n)} `).join('  ')
  return rest.split(' ').every((w) => !w || ['and', 'or', 'with', 'plus'].includes(w))
}
