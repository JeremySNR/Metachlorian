/**
 * URL ⇄ search state. Every search is a shareable URL (ADR 013 §5):
 * /search?q=…&req=…&exc=…&f=…&use=…&ch=…&terr=…&inc=…&similar=…
 */
import type { SearchFilters, SearchRequest, TermMap, Verdict } from '../../api/types'
import type { SearchState } from '../../lib/chips'

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
  similar?: string
  assets?: string
  group?: 'files'
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
  if (raw.group === 'files') p.group = 'files'
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

export function includeFrom(p: SearchParams): Verdict[] {
  if (!p.inc) return DEFAULT_INCLUDE
  if (p.inc === 'all') return ALL_VERDICTS
  const list = p.inc.split(',').filter((v): v is Verdict => (ALL_VERDICTS as string[]).includes(v))
  return list.length ? list : DEFAULT_INCLUDE
}

export function hasUse(p: SearchParams): boolean {
  return Boolean(p.use || p.ch || p.terr)
}

/** The request body the core receives for these params. */
export function toRequest(p: SearchParams): SearchRequest {
  const req: SearchRequest = { q: p.q ?? '' }
  if (p.req) req.require = p.req
  if (p.exc) req.exclude = p.exc
  if (p.f) req.filters = p.f
  if (hasUse(p)) req.intended_use = { use: p.use ?? null, channel: p.ch ?? null, territory: p.terr ?? null, include: includeFrom(p) }
  if (p.similar) req.similar_to = p.similar
  if (p.assets) req.asset_uids = p.assets.split(',')
  return req
}
