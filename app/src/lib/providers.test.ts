import { describe, expect, it } from 'vitest'
import type { OpenRouterModel, Provider } from '../api/types'
import {
  codexState, draftFromSettings, effectiveLlm, endpointBody, endpointDraft, filterModels, formatContext, formatPerMillion, isDirty, isRemote,
  savePlan, switchProvider,
} from './providers'

const providers = [
  { id: 'custom', label: 'Local', hosted: false, base_url: '', default_models: { vlm: '', llm: '' }, concurrency: 1, batch: 1 },
  { id: 'openai', label: 'OpenAI', hosted: true, base_url: 'https://api.openai.com/v1', default_models: { vlm: 'gpt-v', llm: 'gpt-l' }, concurrency: 4, batch: 1 },
  { id: 'codex', label: 'Codex', hosted: true, base_url: '', default_models: { vlm: 'luna', llm: 'luna' }, concurrency: 1, batch: 6 },
] as Provider[]

const blank = { provider: 'custom' as const, base_url: '', model: '' }
const local = { provider: 'custom' as const, base_url: 'http://127.0.0.1:8080/v1', model: 'qwen-vl', local: true }
const loopback = { url: 'http://127.0.0.1:8080/v1', local: true, reason: 'private address' }
const savedLocal = { vlm: blank, llm: blank, allow_remote: false }

describe('drafts', () => {
  it('follows the captions provider unless the summaries differ', () => {
    expect(draftFromSettings(blank, blank).separate).toBe(false)
    expect(draftFromSettings({ provider: 'openai', model: 'gpt-v' }, { provider: 'openai', model: 'gpt-v' }).separate).toBe(false)
    expect(draftFromSettings(local, blank).separate).toBe(true)
  })
  it('copies the captions provider for summaries when they are not separate', () => {
    const d = draftFromSettings({ provider: 'openai', model: 'gpt-v' }, blank)
    expect(effectiveLlm({ ...d, separate: false })).toMatchObject({ provider: 'openai', model: 'gpt-v' })
  })
  it('starts a hosted provider from its suggested model and its own address', () => {
    const ep = switchProvider(endpointDraft(local), 'openai', providers, 'llm')
    expect(ep).toMatchObject({ provider: 'openai', model: 'gpt-l', base_url: '' })
    expect(endpointBody(ep)).toEqual({ provider: 'openai', model: 'gpt-l', base_url: '', concurrency: 0, batch: 0 })
  })
  it('restores the remembered custom endpoint when switching back to Local', () => {
    const remembered = endpointDraft(local)
    const back = switchProvider(switchProvider(remembered, 'codex', providers, 'vlm'), 'custom', providers, 'vlm', remembered)
    expect(back).toMatchObject({ provider: 'custom', base_url: local.base_url, model: 'qwen-vl', local: true })
  })
  it('sends the Codex cap and path only for Codex', () => {
    const ep = { ...switchProvider(endpointDraft(blank), 'codex', providers, 'vlm'), daily_limit: 50 }
    expect(endpointBody(ep)).toMatchObject({ provider: 'codex', daily_limit: 50, codex_path: 'codex' })
    expect(endpointBody(endpointDraft(local))).not.toHaveProperty('daily_limit')
  })
})

describe('leaving the machine', () => {
  it('counts every hosted provider as remote, and a custom endpoint unless declared and classified local', () => {
    expect(isRemote(endpointDraft({ provider: 'openai', model: 'gpt-v' }))).toBe(true)
    expect(isRemote(endpointDraft(local), loopback)).toBe(false)
    expect(isRemote(endpointDraft({ ...local, local: false }), loopback)).toBe(true)
    expect(isRemote(endpointDraft(local), null)).toBe(true)
    expect(isRemote(endpointDraft(blank))).toBe(false)
  })
  it('asks first and turns hosted adapters on when choosing a hosted provider', () => {
    const d = draftFromSettings(blank, blank)
    const plan = savePlan({ ...d, vlm: switchProvider(d.vlm, 'openai', providers, 'vlm') }, savedLocal)
    expect(plan.confirm).toBe(true)
    expect(plan.body.allow_remote).toBe(true)
    expect(plan.body.llm).toMatchObject({ provider: 'openai' })
    expect(plan.remote.map((r) => r.role)).toEqual(['vlm', 'llm'])
  })
  it('does not ask again for what already leaves', () => {
    const saved = { vlm: { provider: 'openai' as const, model: 'gpt-v' }, llm: { provider: 'openai' as const, model: 'gpt-v' }, allow_remote: true }
    const d = draftFromSettings(saved.vlm, saved.llm)
    expect(savePlan({ ...d, vlm: { ...d.vlm, model: 'gpt-other' } }, saved).confirm).toBe(false)
    expect(savePlan(d, { ...saved, allow_remote: false }).confirm).toBe(true)
    expect(savePlan({ ...d, vlm: switchProvider(d.vlm, 'codex', providers, 'vlm') }, saved).confirm).toBe(true)
  })
  it('switches hosted adapters off when going back to Local', () => {
    const saved = { vlm: { provider: 'openai' as const, model: 'gpt-v' }, llm: { provider: 'openai' as const, model: 'gpt-v' }, allow_remote: true }
    const d = draftFromSettings(saved.vlm, saved.llm)
    const plan = savePlan({ ...d, vlm: switchProvider(d.vlm, 'custom', providers, 'vlm') }, saved)
    expect(plan).toMatchObject({ confirm: false, body: { allow_remote: false, vlm: { provider: 'custom', base_url: '' } } })
  })
  it('keeps hosted adapters on while the summaries still use one', () => {
    const d = { vlm: endpointDraft(local), llm: endpointDraft({ provider: 'openai', model: 'gpt-l' }), separate: true }
    const plan = savePlan(d, savedLocal, { vlm: loopback })
    expect(plan.body.allow_remote).toBe(true)
    expect(plan.remote.map((r) => r.role)).toEqual(['llm'])
  })
  it('knows when the draft changed', () => {
    const d = draftFromSettings(blank, blank)
    expect(isDirty(d, savedLocal)).toBe(false)
    expect(isDirty({ ...d, vlm: { ...d.vlm, model: 'x' } }, savedLocal)).toBe(true)
  })
})

describe('provider details', () => {
  it('reads the Codex setup state', () => {
    expect(codexState(undefined)).toBe('unknown')
    expect(codexState({ ok: false, installed: false })).toBe('missing')
    expect(codexState({ ok: false, installed: true })).toBe('signed-out')
    expect(codexState({ ok: true, installed: true })).toBe('ready')
  })
  it('formats prices and context', () => {
    expect(formatPerMillion(0.15)).toBe('$0.15')
    expect(formatPerMillion(0.075)).toBe('$0.075')
    expect(formatPerMillion(0)).toBe('Free')
    expect(formatPerMillion(null)).toBe('—')
    expect(formatContext(128000)).toBe('128k')
    expect(formatContext(1048576)).toBe('1M')
  })
  it('filters the OpenRouter catalogue to vision models, structured output and cheapest first', () => {
    const m = (id: string, vision: boolean, input: number | null, structured = true): OpenRouterModel => ({ id, name: id, vision, context: 1, input_per_m: input, output_per_m: 1, structured })
    const list = [m('a/text', false, 0.1), m('b/vision-dear', true, 5), m('c/vision-cheap', true, 0.2), m('d/vision-loose', true, 0.01, false)]
    expect(filterModels(list, { vision: true }).map((x) => x.id)).toEqual(['c/vision-cheap', 'b/vision-dear', 'd/vision-loose'])
    expect(filterModels(list, { q: 'dear' }).map((x) => x.id)).toEqual(['b/vision-dear'])
  })
})
