/**
 * Search scope: "only footage in this folder" or "only shots in this collection".
 *
 * A scope is sent to the core as `filters.folder` / `filters.collection` (a folder name such as
 * "Disney 2026", a relative path such as "Holidays/Disney 2026", or an absolute path; a collection uid
 * or exact name). It lives in the URL as repeatable `folder=` / `collection=` params. The query text may
 * also carry `folder:"Disney 2026"`; the core strips those words and echoes them in `query.filters`.
 * This module maps both sources to scope chips, labels and the count line, and reads the core's
 * "No folder called …. Closest: …." notes.
 */
import { plural } from './format'

export type ScopeKind = 'folder' | 'collection'
export const SCOPE_KINDS: ScopeKind[] = ['folder', 'collection']

export interface Scope {
  folder: string[]
  collection: string[]
}

export const EMPTY_SCOPE: Scope = { folder: [], collection: [] }

/**
 * A URL or response value as a clean list. The router turns "2026" into a number and repeated keys into
 * an array, and the core echoes a single filter as a string, so accept all of those.
 */
export function scopeList(v: unknown): string[] | undefined {
  const raw = Array.isArray(v) ? v : v === undefined || v === null ? [] : [v]
  const out: string[] = []
  for (const x of raw) {
    if (typeof x !== 'string' && typeof x !== 'number' && typeof x !== 'boolean') continue
    const s = String(x).trim()
    if (s && !out.includes(s)) out.push(s)
  }
  return out.length ? out : undefined
}

export function hasScope(s: Partial<Scope> | null | undefined): boolean {
  return Boolean(s && ((s.folder?.length ?? 0) > 0 || (s.collection?.length ?? 0) > 0))
}

export function mergeScopes(...scopes: (Partial<Scope> | null | undefined)[]): Scope {
  const out: Scope = { folder: [], collection: [] }
  for (const s of scopes) {
    for (const k of SCOPE_KINDS) for (const v of s?.[k] ?? []) if (!out[k].some((x) => same(x, v))) out[k].push(v)
  }
  return out
}

const same = (a: string, b: string) => a.toLowerCase() === b.toLowerCase()

// ---------------------------------------------------------------- folder:"…" written in the query

/** The core's syntax (search/engine.py `_scope_from_text`). */
const TOKEN = /\b(folder|collection)\s*:\s*(?:"([^"]+)"|(\S+))/gi

/** Scopes written in the query text. */
export function scopeTokens(q: string | null | undefined): Scope {
  const out: Scope = { folder: [], collection: [] }
  if (!q || !q.includes(':')) return out
  for (const m of q.matchAll(TOKEN)) {
    const kind = m[1].toLowerCase() as ScopeKind
    const v = (m[2] ?? m[3]).trim()
    if (v && !out[kind].some((x) => same(x, v))) out[kind].push(v)
  }
  return out
}

/** Remove one written scope from the query text; null when the words can't be found. */
export function stripScopeToken(q: string, kind: ScopeKind, value: string): string | null {
  let found = false
  const next = q.replace(TOKEN, (m, k: string, quoted?: string, bare?: string) => {
    if (found || k.toLowerCase() !== kind || !same((quoted ?? bare ?? '').trim(), value)) return m
    found = true
    return ' '
  })
  return found ? next.replace(/\s+/g, ' ').trim() : null
}

/** Write a scope into query text, quoting when needed: folder:"Disney 2026". */
export function scopeToken(kind: ScopeKind, value: string): string {
  return /[\s"]/.test(value) ? `${kind}:"${value.replace(/"/g, '')}"` : `${kind}:${value}`
}

// ---------------------------------------------------------------- chips

export interface ScopeChip {
  key: string
  kind: ScopeKind
  value: string
  /** Written in the query text (removing it edits the words) rather than chosen in the scope control. */
  typed: boolean
}

/** Scope chips: chosen scopes first, then ones the core read from the words (`query.filters`). */
export function scopeChips(chosen: Partial<Scope>, echoed?: { folder?: unknown; collection?: unknown } | null): ScopeChip[] {
  const out: ScopeChip[] = []
  for (const kind of SCOPE_KINDS) {
    const urlValues = chosen[kind] ?? []
    for (const value of urlValues) out.push({ key: `scope:${kind}:${value}`, kind, value, typed: false })
    for (const value of scopeList(echoed?.[kind]) ?? []) {
      if (!urlValues.some((x) => same(x, value)) && !out.some((c) => c.kind === kind && same(c.value, value))) out.push({ key: `scope:${kind}:${value}`, kind, value, typed: true })
    }
  }
  return out
}

/** Scope as the person sees it: chosen plus written (from the core's echo when there is one). */
export function chipsToScope(chips: ScopeChip[]): Scope {
  const out: Scope = { folder: [], collection: [] }
  for (const c of chips) out[c.kind].push(c.value)
  return out
}

// ---------------------------------------------------------------- labels

export interface FolderRef {
  path: string
  name: string
  relative: string
}

export interface CollectionRef {
  uid: string
  name: string
}

/** Last path segment ("Holidays/Disney 2026/" → "Disney 2026"). */
export function basename(p: string): string {
  const parts = p.replace(/\\/g, '/').replace(/\/+$/, '').split('/')
  return parts[parts.length - 1] || p
}

/** A folder scope value as a name: the folder's own name when it is known, else its last segment. */
export function folderLabel(value: string, folders: readonly FolderRef[] = []): string {
  const v = value.replace(/\\/g, '/').replace(/\/+$/, '')
  const hit = folders.find((f) => f.path === v) ?? folders.find((f) => same(f.relative, v))
  return hit ? hit.name : basename(v)
}

/** A collection scope value (uid or name) as its name. */
export function collectionLabel(value: string, collections: readonly CollectionRef[] = []): string {
  return (collections.find((c) => c.uid === value) ?? collections.find((c) => same(c.name, value)))?.name ?? value
}

/** Chip text: "In Disney 2026" / "In collection: Kids on rides". */
export function scopeChipText(kind: ScopeKind, name: string): { lead: string; name: string } {
  return kind === 'folder' ? { lead: 'In', name } : { lead: 'In collection:', name }
}

function joinNames(names: string[], one: string, many: string): string {
  if (names.length === 1) return one === 'folder' ? names[0] : `${one} ${names[0]}`
  if (names.length === 2) return one === 'folder' ? `${names[0]} and ${names[1]}` : `${many} ${names[0]} and ${names[1]}`
  return plural(names.length, one, many)
}

/** The count line's scope: "in Disney 2026", "in collection Kids on rides", "in sample and extra", "in 3 folders". */
export function scopePhrase(scope: Scope, folderName: (v: string) => string, collectionName: (v: string) => string): string | null {
  const parts: string[] = []
  if (scope.folder.length) parts.push(joinNames(scope.folder.map(folderName), 'folder', 'folders'))
  if (scope.collection.length) parts.push(joinNames(scope.collection.map(collectionName), 'collection', 'collections'))
  return parts.length ? `in ${parts.join(', ')}` : null
}

// ---------------------------------------------------------------- the core's notes

export interface ScopeNote {
  kind: ScopeKind
  missing: string
  closest: string[]
}

const NOTE = /^No (folder|collection) called "(.+)"\.(?: Closest: (.+)\.)?$/

/** `No folder called "Disney 2025". Closest: Videos/Holidays/Disney 2026.` → parts; null for other notes. */
export function parseScopeNote(note: string): ScopeNote | null {
  const m = NOTE.exec(note.trim())
  if (!m) return null
  return { kind: m[1] as ScopeKind, missing: m[2], closest: m[3] ? m[3].split(', ').map((x) => x.trim()).filter(Boolean) : [] }
}

/** Query string for the similar-shot endpoints: repeated folder= and collection= params. */
export function scopeQueryParams(scope: Partial<Scope> | null | undefined): [string, string][] {
  const out: [string, string][] = []
  for (const k of SCOPE_KINDS) for (const v of scope?.[k] ?? []) out.push([k, v])
  return out
}
