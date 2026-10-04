/**
 * Model providers for the vision-language model (captions) and the language model (summaries).
 * Pure: drafts from /api/admin/settings, the body PUT /api/admin/settings receives, and when the
 * §3.20 "content leaves this machine" confirmation is needed. Keys never pass through here.
 */
import type { CodexStatus, ModelEndpoint, OpenRouterModel, Provider, ProviderId } from '../api/types'
import { endpointHost, type Locality } from './egress'

export type Role = 'vlm' | 'llm'

export const PROVIDER_ORDER: ProviderId[] = ['custom', 'openai', 'openrouter', 'codex']

/** Short names for the chooser and messages. */
export const PROVIDER_NAME: Record<ProviderId, string> = {
  custom: 'Local',
  openai: 'OpenAI',
  openrouter: 'OpenRouter',
  codex: 'ChatGPT via Codex',
}

/** Where a hosted provider sends content, for the confirmation and the egress popover. */
export const PROVIDER_DESTINATION: Record<Exclude<ProviderId, 'custom'>, string> = {
  openai: 'OpenAI (api.openai.com)',
  openrouter: 'OpenRouter (openrouter.ai) and the model maker it routes to',
  codex: 'OpenAI, through the Codex CLI and your ChatGPT account',
}

/** What each role sends to a provider that is not on this machine (core: analysers/caption.py, fusion.py, rollup.py). */
export const SENDS: Record<Role, string[]> = {
  vlm: [
    'Sampled keyframes: four frames per shot, as one contact-sheet image',
    'Up to 300 characters of transcript and 200 of on-screen text per shot',
    'Measured facts: duration, camera movement and the person count',
  ],
  llm: ['Text only: captions, labels, and short transcript and on-screen text snippets'],
}

/** Never sent to any model provider. */
export const NEVER_SENT = ['Footage files and audio', 'Face crops and face embeddings', 'Names you give people']

export interface EndpointDraft {
  provider: ProviderId
  model: string
  base_url: string
  api_key_env: string
  local: boolean
  codex_path: string
  concurrency: number
  batch: number
  daily_limit: number
}

export interface AdapterDraft {
  vlm: EndpointDraft
  /** Used only when `separate` is on; otherwise the language model follows the captions provider. */
  llm: EndpointDraft
  separate: boolean
}

export const isHosted = (id: ProviderId) => id !== 'custom'

export function endpointDraft(ep: Partial<ModelEndpoint>): EndpointDraft {
  return {
    provider: ep.provider ?? 'custom',
    model: ep.model ?? '',
    base_url: ep.base_url ?? '',
    api_key_env: ep.api_key_env ?? '',
    // A new custom endpoint starts undeclared; the core decides locality from the host anyway.
    local: ep.base_url ? (ep.local ?? false) : false,
    codex_path: ep.codex_path || 'codex',
    concurrency: ep.concurrency ?? 0,
    batch: ep.batch ?? 0,
    daily_limit: ep.daily_limit ?? 0,
  }
}

/** Same provider, model and address for both: the summaries follow the captions provider. */
export function draftFromSettings(vlm: Partial<ModelEndpoint>, llm: Partial<ModelEndpoint>): AdapterDraft {
  const v = endpointDraft(vlm)
  const l = endpointDraft(llm)
  const same = v.provider === l.provider && v.model === l.model && v.base_url.trim() === l.base_url.trim()
  return { vlm: v, llm: l, separate: !same }
}

/** The language model actually saved: its own draft, or a copy of the captions provider. */
export function effectiveLlm(d: AdapterDraft): EndpointDraft {
  return d.separate ? d.llm : { ...d.vlm }
}

/**
 * Switch an endpoint to another provider. Hosted providers start from their suggested model and the
 * provider's own address; going back to Local restores the custom endpoint remembered for this session.
 */
export function switchProvider(ep: EndpointDraft, to: ProviderId, providers: readonly Provider[], role: Role, rememberedCustom?: EndpointDraft | null): EndpointDraft {
  if (ep.provider === to) return ep
  if (to === 'custom') {
    const r = rememberedCustom
    return { ...ep, provider: 'custom', model: r?.model ?? '', base_url: r?.base_url ?? '', api_key_env: r?.api_key_env ?? '', local: r?.local ?? false, concurrency: 0, batch: 0, daily_limit: 0 }
  }
  const p = providers.find((x) => x.id === to)
  return { ...ep, provider: to, model: p?.default_models[role] ?? '', base_url: '', api_key_env: '', concurrency: 0, batch: 0, daily_limit: 0 }
}

/** Fields PUT /api/admin/settings takes for one endpoint. Hosted providers use their own address. */
export function endpointBody(ep: EndpointDraft): Partial<ModelEndpoint> {
  const common = { provider: ep.provider, model: ep.model.trim(), concurrency: ep.concurrency, batch: ep.batch }
  if (ep.provider === 'custom') return { ...common, base_url: ep.base_url.trim(), api_key_env: ep.api_key_env.trim(), local: ep.local }
  if (ep.provider === 'codex') return { ...common, base_url: '', daily_limit: ep.daily_limit, codex_path: ep.codex_path.trim() || 'codex' }
  return { ...common, base_url: '' }
}

/** Configured enough to be used (the core's ModelEndpoint.enabled). */
export function isEnabled(ep: EndpointDraft): boolean {
  if (ep.provider === 'codex') return Boolean(ep.model.trim())
  if (ep.provider === 'custom') return Boolean(ep.base_url.trim() && ep.model.trim())
  return Boolean(ep.model.trim())
}

/**
 * Content leaves the machine: any enabled hosted provider, or an enabled custom endpoint that is not
 * both declared local and classified local by the core (config.py ModelEndpoint.is_local).
 */
export function isRemote(ep: EndpointDraft, locality?: Locality | null): boolean {
  if (!isEnabled(ep)) return false
  if (isHosted(ep.provider)) return true
  const fresh = locality && locality.url.trim() === ep.base_url.trim() ? locality : null
  return !(ep.local && fresh?.local)
}

/** "OpenAI (api.openai.com)" or the custom endpoint's host. */
export function destination(ep: EndpointDraft): string {
  return ep.provider === 'custom' ? endpointHost(ep.base_url) : PROVIDER_DESTINATION[ep.provider]
}

export interface SavedAdapters {
  vlm: Partial<ModelEndpoint>
  llm: Partial<ModelEndpoint>
  allow_remote: boolean
}

type Localities = Partial<Record<Role, Locality | null>>

/** Where content would go, per role, for the endpoints that leave the machine. */
export function remoteDestinations(vlm: EndpointDraft, llm: EndpointDraft, loc: Localities = {}): { role: Role; ep: EndpointDraft; to: string }[] {
  const out: { role: Role; ep: EndpointDraft; to: string }[] = []
  if (isRemote(vlm, loc.vlm)) out.push({ role: 'vlm', ep: vlm, to: destination(vlm) })
  if (isRemote(llm, loc.llm)) out.push({ role: 'llm', ep: llm, to: destination(llm) })
  return out
}

export interface SavePlan {
  body: { vlm: Partial<ModelEndpoint>; llm: Partial<ModelEndpoint>; allow_remote: boolean }
  /** Ask first (§3.20): something new would leave this machine. */
  confirm: boolean
  /** What leaves, for the confirmation. */
  remote: { role: Role; ep: EndpointDraft; to: string }[]
}

/**
 * What saving this draft does. Hosted providers need allow_remote; when nothing remote remains it is
 * switched off. The confirmation is asked whenever content would start going somewhere it doesn't
 * already go (hosted adapters were off, or a new destination or role).
 */
export function savePlan(draft: AdapterDraft, saved: SavedAdapters, loc: Localities = {}): SavePlan {
  const vlm = draft.vlm
  const llm = effectiveLlm(draft)
  const remote = remoteDestinations(vlm, llm, loc)
  const before = saved.allow_remote ? remoteDestinations(endpointDraft(saved.vlm), endpointDraft(saved.llm), loc) : []
  const known = new Set(before.map((r) => `${r.role}|${r.ep.provider}|${r.to}`))
  const confirm = remote.some((r) => !known.has(`${r.role}|${r.ep.provider}|${r.to}`))
  return { body: { vlm: endpointBody(vlm), llm: endpointBody(llm), allow_remote: remote.length > 0 }, confirm, remote }
}

/** True when the draft differs from what is saved (the Save button's state). */
export function isDirty(draft: AdapterDraft, saved: SavedAdapters): boolean {
  const a = JSON.stringify([endpointBody(draft.vlm), endpointBody(effectiveLlm(draft))])
  const b = JSON.stringify([endpointBody(endpointDraft(saved.vlm)), endpointBody(endpointDraft(saved.llm))])
  return a !== b
}

export type CodexState = 'unknown' | 'missing' | 'signed-out' | 'ready'

export function codexState(status: (Pick<CodexStatus, 'ok'> & { installed?: boolean }) | null | undefined): CodexState {
  if (!status) return 'unknown'
  if (status.ok) return 'ready'
  if (status.installed === false) return 'missing'
  return status.installed ? 'signed-out' : 'unknown'
}

/** "$0.15" per million tokens, "Free", or "—" when unknown. */
export function formatPerMillion(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v)) return '—'
  if (v === 0) return 'Free'
  return `$${v < 1 ? v.toFixed(v < 0.1 ? 3 : 2) : v.toFixed(2)}`
}

/** "128k" context length. */
export function formatContext(n: number | null | undefined): string {
  if (!n) return '—'
  return n >= 1_000_000 ? `${Math.round(n / 100_000) / 10}M` : `${Math.round(n / 1000)}k`
}

/**
 * OpenRouter models for the picker: vision-capable only when asked, matching the filter text, with
 * structured-output models first (captions need JSON output), then cheapest input.
 */
export function filterModels(models: readonly OpenRouterModel[], opts: { q?: string; vision?: boolean; limit?: number } = {}): OpenRouterModel[] {
  const q = (opts.q ?? '').trim().toLowerCase()
  return models
    .filter((m) => (!opts.vision || m.vision) && (!q || m.id.toLowerCase().includes(q) || (m.name ?? '').toLowerCase().includes(q)))
    .sort((a, b) => Number(b.structured) - Number(a.structured) || (a.input_per_m ?? Infinity) - (b.input_per_m ?? Infinity) || a.id.localeCompare(b.id))
    .slice(0, opts.limit ?? 60)
}
