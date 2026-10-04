/**
 * URL ⇄ search state. Every search is a shareable URL (ADR 013 §5):
 * /search?q=…&req=…&exc=…&f=…&use=…&ch=…&terr=…&inc=…&blocked=show&strict=…&similar=…&folder=…&collection=…
 * (folder and collection repeat: folder=a&folder=b).
 */
import { defaultStringifySearch } from '@tanstack/react-router'
import type { SearchFilters, SearchRequest, Strictness, TermMap, Verdict } from '../../api/types'
import type { SearchState } from '../../lib/chips'
import { hasScope, mergeScopes, SCOPE_KINDS, scopeList, scopeTokens, stripScopeToken, type Scope, type ScopeKind } from '../../lib/scope'

export interface SearchParams {
  q?: string
  req?: TermMap
  exc?: TermMap
  f?: SearchFilters
  use?: string
  ch?: string
  terr?: string
  /** Rights verdicts to include when an intended use is set: "all" or a comma list. */
  inc?: string
  /** "show": include shots blocked for every use (not cleared or expired). Hidden by default. */
  blocked?: 'show'
  /** Where strong matches end; absent = balanced. */
  strict?: 'loose' | 'strict'
  similar?: string
  assets?: string
  group?: 'files'
  /** Search scope: only footage in these folders (name, relative or absolute path). */
  folder?: string[]
  /** Search scope: only shots in these collections (uid or name). */
  collection?: string[]
}

const isObj = (v: unknown): v is Record<string, unknown> => typeof v === 'object' && v !== null && !Array.isArray(v)
const str = (v: unknown) => (typeof v === 'string' && v.trim() ? v : undefined)

function termMap(v: unknown): TermMap | undefined {
  if (!isObj(v)) return undefined
  const out: TermMap = {}
  for (const [k, terms] of Object.entries(v)) {
    if (Array.isArray(terms)) {
      const t = terms.filter((x): x is string => typeof x === 'string')
      if (t.length) out[k] = t
    }
  }
  return Object.keys(out).length ? out : undefined
}

const FILTER_NUM = ['min_duration', 'max_duration', 'min_fps', 'max_fps', 'min_people', 'max_people', 'min_quality', 'min_height'] as const
const FILTER_BOOL = ['log', 'hdr', 'usable', 'speech', 'music'] as const

function filters(v: unknown): SearchFilters | undefined {
  if (!isObj(v)) return undefined
  const out: SearchFilters = {}
  for (const k of FILTER_NUM) if (typeof v[k] === 'number' && Number.isFinite(v[k])) out[k] = v[k] as number
  for (const k of FILTER_BOOL) if (typeof v[k] === 'boolean') out[k] = v[k] as boolean
  if (v.orientation === 'vertical' || v.orientation === 'horizontal' || v.orientation === 'square') out.orientation = v.orientation
  if (Array.isArray(v.edit_type)) {
    const e = v.edit_type.filter((x): x is string => typeof x === 'string')
    if (e.length) out.edit_type = e
  }
  if (typeof v.captured_after === 'string') out.captured_after = v.captured_after
  if (typeof v.captured_before === 'string') out.captured_before = v.captured_before
  return Object.keys(out).length ? out : undefined
}

export function validateSearch(raw: Record<string, unknown>): SearchParams {
  const p: SearchParams = {}
  const q = typeof raw.q === 'string' ? raw.q : typeof raw.q === 'number' ? String(raw.q) : undefined
  if (q) p.q = q
  const req = termMap(raw.req)
  if (req) p.req = req
  const exc = termMap(raw.exc)
  if (exc) p.exc = exc
  const f = filters(raw.f)
  if (f) p.f = f
  for (const k of ['use', 'ch', 'terr', 'inc', 'similar', 'assets'] as const) {
    const v = str(raw[k])
    if (v) p[k] = v
  }
  for (const k of SCOPE_KINDS) {
    const v = scopeList(raw[k])
    if (v) p[k] = v
  }
  if (raw.group === 'files') p.group = 'files'
  if (raw.blocked === 'show') p.blocked = 'show'
  if (raw.strict === 'loose' || raw.strict === 'strict') p.strict = raw.strict
  return p
}

export function toState(p: SearchParams): SearchState {
  return {
    q: p.q ?? '',
    require: p.req ?? {},
    exclude: p.exc ?? {},
    filters: p.f ?? {},
    use: p.use || p.ch || p.terr ? { use: p.use ?? null, channel: p.ch ?? null, territory: p.terr ?? null } : null,
  }
}

const clean = <T extends object>(o: T | undefined): T | undefined => (o && Object.keys(o).length ? o : undefined)

export function fromState(s: SearchState, prev: SearchParams = {}): SearchParams {
  return {
    ...prev,
    q: s.q.trim() ? s.q : undefined,
    req: clean(s.require),
    exc: clean(s.exclude),
    f: clean(Object.fromEntries(Object.entries(s.filters).filter(([, v]) => v !== null && v !== undefined && !(Array.isArray(v) && !v.length))) as SearchFilters),
    use: s.use?.use ?? undefined,
    ch: s.use?.channel ?? undefined,
    terr: s.use?.territory ?? undefined,
  }
}

export const ALL_VERDICTS: Verdict[] = ['allowed', 'restricted', 'unknown', 'blocked']
export const DEFAULT_INCLUDE: Verdict[] = ['allowed', 'restricted', 'unknown']

/** Blocked footage is shown only when asked (blocked=show, or the older inc=all / inc=…,blocked). */
export function showsBlocked(p: SearchParams): boolean {
  return p.blocked === 'show' || p.inc === 'all' || Boolean(p.inc?.split(',').includes('blocked'))
}

/** Verdicts for the intended use; "blocked" follows the Hide blocked switch. */
export function includeFrom(p: SearchParams): Verdict[] {
  let list: Verdict[] = DEFAULT_INCLUDE
  if (p.inc === 'all') list = ALL_VERDICTS
  else if (p.inc) {
    const parsed = p.inc.split(',').filter((v): v is Verdict => (ALL_VERDICTS as string[]).includes(v))
    if (parsed.length) list = parsed
  }
  list = list.filter((v) => v !== 'blocked')
  return showsBlocked(p) ? [...list, 'blocked'] : list
}

/** Turn Hide blocked on or off (system.md §3.4: on by default, whatever the intended use). */
export function withBlocked(p: SearchParams, show: boolean): SearchParams {
  const inc = p.inc === 'all' ? undefined : p.inc?.split(',').filter((v) => v !== 'blocked').join(',') || undefined
  return { ...p, inc: inc === DEFAULT_INCLUDE.join(',') ? undefined : inc, blocked: show ? 'show' : undefined }
}

export function strictnessOf(p: SearchParams): Strictness {
  return p.strict ?? 'balanced'
}

export function hasUse(p: SearchParams): boolean {
  return Boolean(p.use || p.ch || p.terr)
}

/** The request body the core receives for these params. */
export function toRequest(p: SearchParams): SearchRequest {
  const req: SearchRequest = { q: p.q ?? '' }
  if (p.req) req.require = p.req
  if (p.exc) req.exclude = p.exc
  if (p.f || hasScope(scopeOf(p))) req.filters = { ...(p.f ?? {}), ...(p.folder?.length ? { folder: p.folder } : {}), ...(p.collection?.length ? { collection: p.collection } : {}) }
  if (hasUse(p)) req.intended_use = { use: p.use ?? null, channel: p.ch ?? null, territory: p.terr ?? null, include: includeFrom(p) }
  req.hide_blocked = !showsBlocked(p)
  if (p.strict) req.strictness = p.strict
  if (p.similar) req.similar_to = p.similar
  if (p.assets) req.asset_uids = p.assets.split(',')
  return req
}

/**
 * Rights and scope for similar-shot searches (GET /api/shots/{uid}/similar, POST /api/similar): the same
 * verdicts and Hide blocked as search, inside the same folder or collection (chosen or written in the words).
 */
export function similarRightsOf(p: SearchParams): { use: string | null; channel: string | null; territory: string | null; include: Verdict[] | null; hideBlocked: boolean; scope?: Scope } {
  const scope = effectiveScope(p)
  return { use: p.use ?? null, channel: p.ch ?? null, territory: p.terr ?? null, include: hasUse(p) ? includeFrom(p) : null, hideBlocked: !showsBlocked(p), ...(hasScope(scope) ? { scope } : {}) }
}

// ---------------------------------------------------------------- scope

/** The scope chosen in the scope control (URL folder= / collection=). */
export function scopeOf(p: SearchParams): Scope {
  // Tolerates raw router search (a single folder= parses as a string, a number-like name as a number).
  return { folder: scopeList(p.folder) ?? [], collection: scopeList(p.collection) ?? [] }
}

/** Chosen scope plus any folder:"…" / collection:"…" written in the words. */
export function effectiveScope(p: SearchParams): Scope {
  return mergeScopes(scopeOf(p), scopeTokens(p.q))
}

/** Replace the chosen scope (Everything = empty). Written scopes stay in the words. */
export function withScope(p: SearchParams, scope: Partial<Scope>): SearchParams {
  return { ...p, folder: scope.folder?.length ? scope.folder : undefined, collection: scope.collection?.length ? scope.collection : undefined }
}

/** Params that keep only the scope (and the rights choices) for a new similar search. */
export function keepScope(p: SearchParams): Pick<SearchParams, 'folder' | 'collection'> {
  return { folder: p.folder, collection: p.collection }
}

/** Remove one scope value, from the URL or from the words. Null when it is in neither. */
export function withoutScope(p: SearchParams, kind: ScopeKind, value: string): SearchParams | null {
  const list = p[kind] ?? []
  const lower = value.toLowerCase()
  if (list.some((v) => v.toLowerCase() === lower)) {
    const rest = list.filter((v) => v.toLowerCase() !== lower)
    return { ...p, [kind]: rest.length ? rest : undefined }
  }
  const q = p.q ? stripScopeToken(p.q, kind, value) : null
  return q === null ? null : { ...p, q: q || undefined }
}

/** The one-click fix for "No folder called x. Closest: y.": search y instead (the chosen scope takes it). */
export function withScopeFix(p: SearchParams, kind: ScopeKind, missing: string, replacement: string): SearchParams {
  const base = withoutScope(p, kind, missing) ?? p
  const list = (base[kind] ?? []).filter((v) => v.toLowerCase() !== replacement.toLowerCase())
  return { ...base, [kind]: [...list, replacement] }
}

/**
 * Router search serialiser: the default (JSON for objects), except the scope lists, which repeat
 * (folder=a&folder=b) so links stay readable. The default parser reads repeated keys back as a list.
 */
export function stringifySearch(search: Record<string, unknown>): string {
  const rest: Record<string, unknown> = { ...search }
  const repeat: [string, string][] = []
  for (const k of SCOPE_KINDS) {
    const v = rest[k]
    if (Array.isArray(v) && v.every((x) => typeof x === 'string')) {
      for (const x of v) repeat.push([k, x])
      delete rest[k]
    }
  }
  const base = defaultStringifySearch(rest)
  if (!repeat.length) return base
  const out = new URLSearchParams(base.slice(1))
  for (const [k, v] of repeat) out.append(k, v)
  return `?${out.toString()}`
}
