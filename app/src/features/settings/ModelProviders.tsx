import { useMemo, useState, type ReactNode } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  Button as RacButton, Disclosure, DisclosurePanel, Heading, ListBox, ListBoxItem, Radio as RacRadio, RadioGroup as RacRadioGroup,
} from 'react-aria-components'
import { ChevronRight, CircleAlert, CircleCheck, Cloud, HardDrive, KeyRound, LoaderCircle, PlugZap, Terminal, Trash2 } from 'lucide-react'
import type { AdminSettings, EndpointHealth, Provider, ProviderId, ProviderKey, ProvidersResponse, ProviderTest } from '../../api/types'
import { api, ApiError } from '../../api/client'
import {
  checkEndpointLocality, testProvider, useAdminSettings, useEndpointLocality, useHealth, useOpenRouterModels, useProcessing, useProviders, useSetProviderKey,
} from '../../api/queries'
import { useDebounced } from '../../hooks/useDebounced'
import { endpointHost, localityBadge, type Locality } from '../../lib/egress'
import { formatNumber, plural } from '../../lib/format'
import { filesPending } from '../../lib/processing'
import {
  codexState, draftFromSettings, effectiveLlm, filterModels, formatContext, formatPerMillion, isDirty, isEnabled, isHosted, NEVER_SENT, PROVIDER_DESTINATION,
  PROVIDER_NAME, PROVIDER_ORDER, savePlan, SENDS, switchProvider, type AdapterDraft, type EndpointDraft, type Role, type SavePlan,
} from '../../lib/providers'
import { Button } from '../../components/Button'
import { Dialog } from '../../components/Dialog'
import { StatusText } from '../../components/EmptyState'
import { Checkbox, NumberField, Switch, TextField } from '../../components/Field'
import { Ic } from '../../components/Icon'
import { toast } from '../../components/Toast'
import l from '../library/Library.module.css'
import s from './Settings.module.css'

const ROLE_TITLE: Record<Role, string> = { vlm: 'Captions and labels', llm: 'Summaries' }

/** One line per provider in the chooser: what it is and what it costs. */
const BLURB: Record<ProviderId, { what: string; cost: string }> = {
  custom: { what: 'This machine: the CPU tier, or a vision model server you run (llama.cpp, vLLM, Ollama).', cost: 'Free. The CPU tier is the slowest.' },
  openai: { what: 'OpenAI API with your API key.', cost: 'Billed per request to your OpenAI account.' },
  openrouter: { what: 'Many model makers through one OpenRouter key.', cost: 'Billed per request from your OpenRouter credit.' },
  codex: { what: 'Your ChatGPT plan, through the Codex CLI on the server.', cost: 'No API billing; capped requests per day.' },
}

/** Settings → Model adapters: providers for captions and summaries, keys, privacy and status (system.md §3.20, §9.9). */
export function ModelAdapters({ onAdminError }: { onAdminError: (e: unknown) => ReactNode }) {
  const settings = useAdminSettings()
  const providers = useProviders()
  if (settings.isError) return onAdminError(settings.error)
  if (providers.isError) return onAdminError(providers.error)
  const d = settings.data
  const p = providers.data
  if (!d || !p) return <div aria-busy="true" />
  // Remount the editor whenever the saved endpoints change, so the draft starts from what is saved.
  const savedKey = JSON.stringify([d.settings.vlm, d.settings.llm, d.settings.allow_remote])
  return (
    <section className={s.stack} data-testid="model-adapters">
      <AdapterStatus settings={d} providers={p} />
      <Editor key={savedKey} settings={d} providers={p} />
      <BundledModels models={d.models} />
    </section>
  )
}

// ---------------------------------------------------------------- status

function healthText(h: EndpointHealth | null | undefined, ep: { provider: ProviderId }): { tone: 'cleared' | 'caution' | 'blocked' | 'neutral'; text: string } {
  if (!h) return { tone: 'neutral', text: 'Not configured' }
  if (h.ok) return { tone: 'cleared', text: ep.provider === 'codex' ? 'Signed in' : 'Reachable' }
  if (h.reason === 'not configured') return { tone: 'neutral', text: 'Not configured' }
  if (h.reason === 'no API key') return { tone: 'caution', text: 'No API key saved' }
  return { tone: 'blocked', text: h.reason ? capitalise(h.reason) : `Unreachable${h.status ? ` (HTTP ${h.status})` : ''}` }
}

const capitalise = (t: string) => t.charAt(0).toUpperCase() + t.slice(1)

function AdapterStatus({ settings, providers }: { settings: AdminSettings; providers: ProvidersResponse }) {
  const proc = useProcessing()
  const health = useHealth()
  const qc = useQueryClient()
  const [pausing, setPausing] = useState(false)
  const st = settings.settings
  const leaves = settings.egress.adapters.some((a) => a.active)
  const hostedConfigured = settings.egress.adapters.length > 0
  const caption = proc.data?.analysers.find((a) => a.name === 'caption')
  const queuedCaptions = proc.data ? filesPending(proc.data.assets, 'caption') : null
  const queuedSummaries = proc.data ? proc.data.assets.filter((a) => a.pending.includes('fusion') || a.pending.includes('rollup')).length : null
  const codex = providers.providers.find((x) => x.id === 'codex')
  const usesCodex = st.vlm.provider === 'codex' || st.llm.provider === 'codex'
  const row = (role: Role) => {
    const ep = st[role]
    const h = healthText(role === 'vlm' ? settings.vlm_health : settings.llm_health, ep)
    const enabled = ep.provider === 'codex' ? Boolean(ep.model) : Boolean((ep.base_url || isHosted(ep.provider)) && ep.model)
    const where = !enabled ? (role === 'vlm' ? 'CPU tier (no vision language model)' : 'Rules only (no language model)') : `${PROVIDER_NAME[ep.provider]} · ${ep.model}`
    return (
      <>
        <dt>{ROLE_TITLE[role]}</dt>
        <dd data-testid={`status-${role}`}>
          <span>{where}</span>
          {enabled && <StatusText tone={h.tone} icon={h.tone === 'cleared' ? CircleCheck : h.tone === 'neutral' ? undefined : CircleAlert}>{h.text}</StatusText>}
          {enabled && isHosted(ep.provider) && !st.allow_remote && <StatusText tone="caution">Paused: hosted providers are off</StatusText>}
        </dd>
      </>
    )
  }
  const pause = async (on: boolean) => {
    setPausing(true)
    try {
      await api.put('/api/admin/settings', { allow_remote: on })
      for (const k of [['admin', 'settings'], ['admin', 'providers'], ['health'], ['processing']]) qc.invalidateQueries({ queryKey: k })
      toast({ title: on ? 'Hosted providers are on again' : 'Hosted providers paused', description: on ? undefined : 'Hosted models will receive no content until you turn them back on.', tone: 'info' })
    } catch (e) {
      toast({ title: "Couldn't change hosted providers", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    } finally {
      setPausing(false)
    }
  }
  return (
    <div className={s.statusBlock} aria-busy={proc.isFetching && !proc.data ? true : undefined}>
      <div className={s.statusHead}>
        <h2>Status</h2>
        {leaves ? <StatusText tone="caution" icon={Cloud} filled>Leaves this machine</StatusText> : <StatusText tone="neutral" icon={HardDrive}>Model analysis stays here</StatusText>}
      </div>
      <dl className={s.statusList}>
        {row('vlm')}
        {row('llm')}
        <dt>Queue</dt>
        <dd data-testid="status-queue">
          {queuedCaptions === null ? 'Checking…' : queuedCaptions ? `${plural(queuedCaptions, 'file')} waiting for captions` : 'No files waiting for captions'}
          {queuedSummaries ? ` · ${plural(queuedSummaries, 'file')} waiting for summaries` : ''}
          {caption && !caption.available && caption.reason ? <span className={s.statusNote}>{caption.reason}</span> : null}
        </dd>
        {usesCodex && codex && (
          <>
            <dt>ChatGPT today</dt>
            <dd>
              {codex.remaining_today !== null && codex.remaining_today !== undefined
                ? `${formatNumber(codex.remaining_today)} of ${formatNumber(codex.daily_limit ?? 0)} requests left (resets at midnight UTC)`
                : `Up to ${formatNumber(codex.daily_limit ?? 0)} requests a day`}
            </dd>
          </>
        )}
      </dl>
      {hostedConfigured && (
        <Switch isSelected={st.allow_remote} isDisabled={pausing} onChange={pause}>
          {st.allow_remote ? 'Hosted providers on: content is sent' : 'Hosted providers paused: nothing is sent'}
        </Switch>
      )}
      {health.data && !health.data.vlm && !hostedConfigured && (
        <p className={s.muted}>
          With no vision language model, Metachlorian uses its CPU tier: local SigLIP labels, motion, audio, speech and on-screen text. Descriptions are
          assembled from those signals.
        </p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------- editor

interface EditorProps {
  settings: AdminSettings
  providers: ProvidersResponse
}

function Editor({ settings, providers }: EditorProps) {
  const qc = useQueryClient()
  const st = settings.settings
  const saved = { vlm: st.vlm, llm: st.llm, allow_remote: st.allow_remote }
  const [draft, setDraft] = useState<AdapterDraft>(() => draftFromSettings(st.vlm, st.llm))
  const [confirm, setConfirm] = useState<SavePlan | null>(null)
  const [busy, setBusy] = useState(false)
  // The custom endpoint typed here survives a trip to a hosted provider and back (until saved).
  const [remembered, setRemembered] = useState<Partial<Record<Role, EndpointDraft>>>({})
  const list = providers.providers
  const dirty = isDirty(draft, saved) || draft.separate !== draftFromSettings(st.vlm, st.llm).separate

  const setRole = (role: Role, ep: EndpointDraft) => setDraft((d) => ({ ...d, [role]: ep }))
  const choose = (role: Role, to: ProviderId) => {
    const cur = draft[role]
    const memory = cur.provider === 'custom' ? { ...remembered, [role]: cur } : remembered
    if (cur.provider === 'custom') setRemembered(memory)
    setRole(role, switchProvider(cur, to, list, role, memory[role]))
  }

  const localities = async (): Promise<Partial<Record<Role, Locality | null>>> => {
    const out: Partial<Record<Role, Locality | null>> = {}
    const llm = effectiveLlm(draft)
    for (const [role, ep] of [['vlm', draft.vlm], ['llm', llm]] as const) {
      if (ep.provider === 'custom' && ep.base_url.trim()) out[role] = await checkEndpointLocality(ep.base_url).catch(() => null)
    }
    return out
  }

  const write = async (plan: SavePlan) => {
    setBusy(true)
    try {
      await api.put('/api/admin/settings', plan.body)
      const llm = effectiveLlm(draft)
      const what = draft.vlm.provider === llm.provider ? PROVIDER_NAME[draft.vlm.provider] : `${PROVIDER_NAME[draft.vlm.provider]} and ${PROVIDER_NAME[llm.provider]}`
      toast({
        title: `Model adapters saved: ${what}`,
        description: isEnabled(draft.vlm) ? 'New and unfinished files are queued for analysis now. The status above follows the queue.' : 'Captions come from the CPU tier.',
      })
      for (const k of [['admin', 'settings'], ['admin', 'providers'], ['health'], ['processing'], ['stats']]) qc.invalidateQueries({ queryKey: k })
    } catch (e) {
      toast({ title: "Couldn't save the model adapters", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const save = async () => {
    const plan = savePlan(draft, saved, await localities())
    if (plan.confirm) setConfirm(plan)
    else await write(plan)
  }

  return (
    <div className={s.stack}>
      <div className={s.group}>
        <h2>{ROLE_TITLE.vlm}</h2>
        <p className={s.muted}>
          A vision language model looks at sampled frames and writes the description, shot size, angle, setting and roles for every shot. Hosted providers
          are much faster than the CPU tier on this machine.
        </p>
        <ProviderChooser role="vlm" value={draft.vlm.provider} providers={list} onChange={(v) => choose('vlm', v)} />
        <ProviderDetails role="vlm" ep={draft.vlm} providers={list} onChange={(ep) => setRole('vlm', ep)} />
      </div>

      <div className={s.group}>
        <h2>{ROLE_TITLE.llm}</h2>
        <p className={s.muted}>The language model writes file summaries and finishes each shot's log (roles, pace, mood, topics) from text Metachlorian already has.</p>
        <Checkbox
          isSelected={draft.separate}
          onChange={(v) => setDraft((d) => ({ ...d, separate: v, llm: v ? (d.llm.provider === d.vlm.provider && !d.separate ? { ...d.vlm } : d.llm) : d.llm }))}
        >
          Use a different provider for summaries
        </Checkbox>
        {draft.separate ? (
          <>
            <ProviderChooser role="llm" value={draft.llm.provider} providers={list} onChange={(v) => choose('llm', v)} />
            <ProviderDetails role="llm" ep={draft.llm} providers={list} onChange={(ep) => setRole('llm', ep)} />
          </>
        ) : (
          <p className={s.followLine} data-testid="llm-follows">
            Summaries use the same provider:{' '}
            <strong>{isEnabled(draft.vlm) ? `${PROVIDER_NAME[draft.vlm.provider]} · ${draft.vlm.model}` : draft.vlm.provider === 'custom' ? 'none (rules only, on this machine)' : PROVIDER_NAME[draft.vlm.provider]}</strong>.
          </p>
        )}
      </div>

      <div className={s.saveBar}>
        <Button variant="primary" busy={busy} isDisabled={!dirty} disabledReason={!dirty ? 'Nothing has changed' : undefined} onPress={save}>
          Save model settings
        </Button>
        {dirty && (
          <Button variant="quiet" onPress={() => setDraft(draftFromSettings(st.vlm, st.llm))}>
            Discard changes
          </Button>
        )}
      </div>

      <ConfirmEgress plan={confirm} busy={busy} onCancel={() => setConfirm(null)} onConfirm={async () => { if (confirm) await write(confirm); setConfirm(null) }} />
    </div>
  )
}

// ---------------------------------------------------------------- chooser

function LeavesChip({ hosted }: { hosted: boolean }) {
  return hosted ? <StatusText tone="caution" icon={Cloud} filled>Leaves this machine</StatusText> : <StatusText tone="neutral" icon={HardDrive}>Local</StatusText>
}

function ProviderChooser({ role, value, providers, onChange }: { role: Role; value: ProviderId; providers: Provider[]; onChange: (v: ProviderId) => void }) {
  const byId = new Map(providers.map((p) => [p.id, p]))
  return (
    <RacRadioGroup value={value} onChange={(v) => onChange(v as ProviderId)} className={s.chooser} aria-label={`Provider for ${ROLE_TITLE[role].toLowerCase()}`}>
      {PROVIDER_ORDER.filter((id) => byId.has(id)).map((id) => {
        const p = byId.get(id) as Provider
        return (
          <RacRadio key={id} value={id} className={s.providerCard} data-testid={`provider-${role}-${id}`}>
            <span className={s.dot} aria-hidden="true" />
            <span className={s.providerText}>
              <span className={s.providerName}>{PROVIDER_NAME[id]}</span>
              <span className={s.providerBlurb}>
                {BLURB[id].what} {id === 'codex' && p.daily_limit ? `${BLURB[id].cost.replace('capped requests per day', `up to ${formatNumber(p.daily_limit)} requests a day`)}` : BLURB[id].cost}
              </span>
            </span>
            <LeavesChip hosted={p.hosted} />
          </RacRadio>
        )
      })}
    </RacRadioGroup>
  )
}

// ---------------------------------------------------------------- per-provider details

function ProviderDetails({ role, ep, providers, onChange }: { role: Role; ep: EndpointDraft; providers: Provider[]; onChange: (ep: EndpointDraft) => void }) {
  const p = providers.find((x) => x.id === ep.provider)
  if (!p) return null
  return (
    <div className={s.adapter} data-testid={`details-${role}`}>
      <Unlocks role={role} provider={p} ep={ep} />
      {ep.provider === 'custom' && <CustomEndpoint ep={ep} onChange={onChange} role={role} />}
      {(ep.provider === 'openai' || ep.provider === 'openrouter') && p.key && <KeyField provider={p} keyStatus={p.key} model={ep.model} />}
      {ep.provider === 'openai' && (
        <div className={s.form}>
          <TextField label="Model" value={ep.model} onChange={(v) => onChange({ ...ep, model: v })} mono description={`Suggested: ${p.default_models[role]}`} />
        </div>
      )}
      {ep.provider === 'openrouter' && <OpenRouterModels role={role} ep={ep} provider={p} onChange={onChange} />}
      {ep.provider === 'codex' && <CodexSetup provider={p} ep={ep} onChange={onChange} />}
      {isHosted(ep.provider) && <Privacy role={role} provider={ep.provider} />}
      {isHosted(ep.provider) && <Advanced ep={ep} provider={p} onChange={onChange} />}
    </div>
  )
}

function Unlocks({ role, provider, ep }: { role: Role; provider: Provider; ep: EndpointDraft }) {
  const hosted = provider.hosted
  const cpu = ep.provider === 'custom' && !ep.base_url.trim()
  const unlocks =
    role === 'vlm'
      ? cpu
        ? 'Labels from the CPU tier (SigLIP) and descriptions assembled from them. Point it at your own vision model server for written captions.'
        : 'Dense captions for every shot, better shot size, angle and roles, and what text and logos are on screen.'
      : cpu
        ? 'Roles, pace and summaries from rules only. Add a language model for written summaries.'
        : 'Written file summaries and a finished log per shot: roles, pace, mood and topics.'
  const speed = hosted
    ? provider.id === 'codex'
      ? `${provider.batch} shots per request, one request at a time. Faster than the CPU tier, slower than an API key.`
      : `${provider.concurrency} requests at a time. Much faster than the CPU tier.`
    : cpu
      ? 'The slowest option: everything runs on this machine’s CPU.'
      : 'As fast as your server.'
  const cost =
    provider.id === 'openai'
      ? 'Billed per request to your OpenAI API account. No ChatGPT plan needed.'
      : provider.id === 'openrouter'
        ? 'Billed per request from your OpenRouter credit. Prices per model are listed below.'
        : provider.id === 'codex'
          ? `No API billing: uses your ChatGPT plan. Metachlorian caps it at ${formatNumber(ep.daily_limit || provider.daily_limit || 0)} requests a day${provider.remaining_today != null ? ` (${formatNumber(provider.remaining_today)} left today)` : ''}.`
          : 'Free. Runs on hardware you control.'
  return (
    <dl className={s.unlocks}>
      <dt>Unlocks</dt>
      <dd>{unlocks}</dd>
      <dt>Speed</dt>
      <dd>{speed}</dd>
      <dt>Cost</dt>
      <dd>{cost}</dd>
    </dl>
  )
}

/** What leaves this machine, exactly, and what never does (§3.20). */
function Privacy({ role, provider }: { role: Role; provider: Exclude<ProviderId, 'custom'> }) {
  return (
    <div className={s.privacy} data-testid={`privacy-${role}`}>
      <div className={s.privacyHead}>
        <StatusText tone="caution" icon={Cloud} filled>Leaves this machine</StatusText>
        <span>Sent to {PROVIDER_DESTINATION[provider]}, during analysis of each new or re-analysed file.</span>
      </div>
      <div className={s.privacyCols}>
        <div>
          <span className={l.figureLabel}>Sent</span>
          <ul>
            {SENDS[role].map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
        </div>
        <div>
          <span className={l.figureLabel}>Never sent</span>
          <ul>
            {NEVER_SENT.map((x) => (
              <li key={x}>{x}</li>
            ))}
          </ul>
        </div>
      </div>
      {role === 'vlm' && <p className={s.statusNote}>Frames can show people. Face identity runs only on this machine and its data is never sent.</p>}
    </div>
  )
}

function CustomEndpoint({ ep, onChange, role }: { ep: EndpointDraft; onChange: (ep: EndpointDraft) => void; role: Role }) {
  // "Runs on this machine or our own network" is a declaration only; it starts off for a new endpoint
  // and never makes a public host local. The badge shows the core's classification of the host.
  const url = useDebounced(ep.base_url, 400)
  const loc = useEndpointLocality(url)
  const settings = useAdminSettings()
  const badge = localityBadge({ baseUrl: ep.base_url, locality: url === ep.base_url ? loc.data : null, error: loc.isError, allowRemote: Boolean(settings.data?.settings.allow_remote) })
  const leaves = badge.tone === 'caution'
  return (
    <>
      <div className={s.adapterHead}>
        <h3>{role === 'vlm' ? 'Your own vision model server' : 'Your own language model server'}</h3>
        <span data-testid="locality-badge" data-state={badge.state} aria-live="polite">
          {badge.state === 'unset' ? (
            <StatusText tone="neutral" icon={HardDrive}>CPU tier on this machine</StatusText>
          ) : leaves ? (
            <StatusText tone="caution" icon={Cloud} filled>{badge.state === 'refused' ? 'Leaves this machine' : badge.label}</StatusText>
          ) : (
            <StatusText tone="neutral" icon={badge.state === 'local' ? HardDrive : undefined}>{badge.label}</StatusText>
          )}
        </span>
      </div>
      {badge.detail && <p className={s.muted} style={{ fontSize: 'var(--text-sm)' }}>{badge.detail.replace(' Hosted adapters are off, so it will not be used.', ' Saving asks before anything is sent there.')}</p>}
      <div className={s.form}>
        <TextField label="Endpoint (OpenAI-compatible)" value={ep.base_url} onChange={(v) => onChange({ ...ep, base_url: v })} placeholder="http://127.0.0.1:8080/v1" mono className={s.formWide} description="Leave empty to use the CPU tier." />
        <TextField label="Model" value={ep.model} onChange={(v) => onChange({ ...ep, model: v })} mono />
        <TextField label="API key environment variable" value={ep.api_key_env} onChange={(v) => onChange({ ...ep, api_key_env: v })} mono placeholder="OPENAI_API_KEY" />
        <Switch isSelected={ep.local} onChange={(v) => onChange({ ...ep, local: v })} className={s.formWide}>
          Runs on this machine or our own network
        </Switch>
        <p className={`${s.muted} ${s.formWide}`} style={{ fontSize: 'var(--text-xs)' }}>
          Metachlorian decides locality from the address itself; this switch can't make a public host count as local.
        </p>
      </div>
      {leaves && ep.base_url.trim() && <p className={s.statusNote}>Sends to {endpointHost(ep.base_url)}: {SENDS[role].join('; ').toLowerCase()}. Face data is never sent.</p>}
    </>
  )
}

function testText(t: ProviderTest, provider: ProviderId): { ok: boolean; text: string } {
  if (t.ok) {
    if (provider === 'codex') return { ok: true, text: `Codex is installed${t.path ? ` (${t.path})` : ''} and signed in with ChatGPT.` }
    const extra = [t.free_tier ? 'free tier' : null, t.limit_remaining !== null && t.limit_remaining !== undefined ? `$${t.limit_remaining.toFixed(2)} credit left` : null].filter(Boolean)
    return { ok: true, text: `${PROVIDER_NAME[provider]} accepted the key${extra.length ? ` (${extra.join(', ')})` : ''}.` }
  }
  const reason = t.reason ?? (t.status ? `HTTP ${t.status}` : 'no answer')
  return { ok: false, text: reason === 'no API key' ? 'No key is saved yet.' : `Test failed: ${reason}.` }
}

/** Write-only key entry: never displayed or prefilled; the masked form says a key is there and where it came from. */
function KeyField({ provider, keyStatus, model }: { provider: Provider; keyStatus: ProviderKey; model: string }) {
  const [value, setValue] = useState('')
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null)
  const [testing, setTesting] = useState(false)
  const setKey = useSetProviderKey()
  const name = PROVIDER_NAME[provider.id]
  const save = async (v: string) => {
    try {
      const r = await setKey.mutateAsync({ name: keyStatus.name, value: v })
      setValue('')
      setResult(null)
      toast({ title: v ? `Saved the ${name} key` : `Removed the ${name} key`, description: v ? `Stored as ${r.masked}. It is never shown again.` : r.present ? 'A key from the server’s environment is still in use.' : undefined, tone: v ? 'success' : 'info' })
    } catch (e) {
      toast({ title: `Couldn't ${v ? 'save' : 'remove'} the key`, description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    }
  }
  const test = async () => {
    setTesting(true)
    try {
      setResult(testText(await testProvider({ provider: provider.id, model: model || undefined }), provider.id))
    } catch (e) {
      setResult({ ok: false, text: `Test failed: ${e instanceof ApiError ? e.detail : String(e)}.` })
    } finally {
      setTesting(false)
    }
  }
  return (
    <div className={s.keyBlock} data-testid={`key-${provider.id}`}>
      <div className={s.keyState} data-testid="key-state">
        {keyStatus.present ? (
          <>
            <StatusText tone="cleared" icon={KeyRound}>Key saved</StatusText>
            <code className={s.masked}>{keyStatus.masked}</code>
            <span className={s.muted}>{keyStatus.from === 'environment' ? 'from the server’s environment' : 'stored in this library'}</span>
          </>
        ) : (
          <StatusText tone="neutral" icon={KeyRound}>No {name} key yet</StatusText>
        )}
      </div>
      <form
        className={s.keyForm}
        onSubmit={(e) => {
          e.preventDefault()
          if (value.trim()) save(value.trim())
        }}
      >
        <TextField
          label={`${name} API key`}
          type="password"
          autoComplete="new-password"
          spellCheck="false"
          value={value}
          onChange={setValue}
          mono
          placeholder={keyStatus.present ? 'Paste a new key to replace it' : provider.id === 'openai' ? 'sk-…' : 'sk-or-…'}
          description="Write-only: kept on the server and never shown again."
          className={s.keyInput}
        />
        <div className={s.keyActions}>
          <Button type="submit" variant="secondary" isDisabled={!value.trim()} busy={setKey.isPending && Boolean(value)}>
            Save key
          </Button>
          {keyStatus.present && keyStatus.from === 'stored' && (
            <Button variant="quiet" icon={Trash2} onPress={() => save('')}>
              Remove key
            </Button>
          )}
          <Button variant="quiet" icon={PlugZap} busy={testing} isDisabled={!keyStatus.present} disabledReason={!keyStatus.present ? 'Save a key first' : undefined} onPress={test}>
            Test
          </Button>
        </div>
      </form>
      {result && (
        <p role="status" className={s.testResult}>
          <StatusText tone={result.ok ? 'cleared' : 'blocked'} icon={result.ok ? CircleCheck : CircleAlert}>{result.text}</StatusText>
        </p>
      )}
      <p className={s.statusNote}>Test checks the saved key {provider.id === 'openrouter' ? 'and your credit ' : ''}without spending a model request.</p>
    </div>
  )
}

function OpenRouterModels({ role, ep, provider, onChange }: { role: Role; ep: EndpointDraft; provider: Provider; onChange: (ep: EndpointDraft) => void }) {
  const [visionOnly, setVisionOnly] = useState(role === 'vlm')
  const [q, setQ] = useState('')
  const models = useOpenRouterModels(true, visionOnly)
  const shown = useMemo(() => filterModels(models.data ?? [], { q, vision: visionOnly }), [models.data, q, visionOnly])
  const current = models.data?.find((m) => m.id === ep.model)
  return (
    <div className={s.group} style={{ gap: 'var(--space-2)' }}>
      <div className={s.form}>
        <TextField label="Model" value={ep.model} onChange={(v) => onChange({ ...ep, model: v })} mono description={`Suggested: ${provider.default_models[role]}`} />
      </div>
      {models.isError ? (
        <p className={s.statusNote} role="status" data-testid="openrouter-offline">
          Couldn't load OpenRouter's model list ({models.error instanceof ApiError ? models.error.detail : 'no connection'}). Type a model ID above, for example{' '}
          <code>{provider.default_models[role]}</code>. {role === 'vlm' ? 'Captions need a model that reads images.' : ''}
        </p>
      ) : (
        <>
          <div className={s.pickerTools}>
            <TextField aria-label="Filter models" placeholder="Filter models, e.g. gemini or mini" value={q} onChange={setQ} className={s.pickerFilter} />
            <Switch isSelected={visionOnly} onChange={setVisionOnly}>
              Reads images
            </Switch>
          </div>
          {role === 'vlm' && current && !current.vision && <StatusText tone="caution" icon={CircleAlert}>{current.id} doesn't read images, so it can't write captions.</StatusText>}
          <ListBox
            aria-label="OpenRouter models"
            selectionMode="single"
            selectedKeys={ep.model ? [ep.model] : []}
            onSelectionChange={(keys) => {
              const k = [...(keys as Set<string>)][0]
              if (k) onChange({ ...ep, model: String(k) })
            }}
            className={s.picker}
            renderEmptyState={() => <div className={s.pickerEmpty}>{models.isLoading ? 'Loading models…' : 'No models match.'}</div>}
            items={shown}
          >
            {(m) => (
              <ListBoxItem id={m.id} textValue={m.id} className={s.pickerRow}>
                <span className={s.pickerName}>
                  <span>{m.name}</span>
                  <code>{m.id}</code>
                </span>
                <span className={s.pickerPrice} aria-label={`Input ${formatPerMillion(m.input_per_m)} per million tokens`}>
                  {formatPerMillion(m.input_per_m)}
                </span>
                <span className={s.pickerPrice} aria-label={`Output ${formatPerMillion(m.output_per_m)} per million tokens`}>
                  {formatPerMillion(m.output_per_m)}
                </span>
                <span className={s.pickerMeta}>{formatContext(m.context)}</span>
                <span className={s.pickerMeta}>{m.structured ? 'JSON' : '—'}</span>
              </ListBoxItem>
            )}
          </ListBox>
          <p className={s.statusNote}>Prices are US dollars per million tokens (input · output), from OpenRouter. JSON: supports structured output, which captions need.</p>
        </>
      )}
    </div>
  )
}

function CodexSetup({ provider, ep, onChange }: { provider: Provider; ep: EndpointDraft; onChange: (ep: EndpointDraft) => void }) {
  const [checked, setChecked] = useState<ProviderTest | null>(null)
  const [busy, setBusy] = useState(false)
  const status = checked ?? provider.status
  const state = codexState(status ?? null)
  const recheck = async () => {
    setBusy(true)
    try {
      setChecked(await testProvider({ provider: 'codex', codex_path: ep.codex_path || undefined }))
    } catch (e) {
      setChecked({ ok: false, installed: false, reason: e instanceof ApiError ? e.detail : String(e) })
    } finally {
      setBusy(false)
    }
  }
  const step = (done: boolean, children: ReactNode) => (
    <li className={s.step} data-done={done || undefined}>
      <Ic icon={done ? CircleCheck : Terminal} size={16} />
      <span>{children}</span>
    </li>
  )
  return (
    <div className={s.group} style={{ gap: 'var(--space-2)' }} data-testid="codex-setup">
      <div className={s.keyState} role="status">
        {state === 'ready' ? (
          <StatusText tone="cleared" icon={CircleCheck}>Installed and signed in{status?.path ? ` · ${status.path}` : ''}</StatusText>
        ) : state === 'signed-out' ? (
          <StatusText tone="caution" icon={CircleAlert}>Installed, not signed in</StatusText>
        ) : state === 'missing' ? (
          <StatusText tone="caution" icon={CircleAlert}>Codex CLI not found on the server</StatusText>
        ) : (
          <StatusText tone="neutral">Not checked yet</StatusText>
        )}
      </div>
      <ol className={s.steps}>
        {step(state === 'ready' || state === 'signed-out', <>On the server machine, install the Codex CLI: <code>npm i -g @openai/codex</code></>)}
        {step(state === 'ready', <>Sign in with your ChatGPT account: <code>codex login</code></>)}
        {step(false, <>Check again here, then save.</>)}
      </ol>
      <p className={s.statusNote}>
        Metachlorian never reads your login tokens. It runs <code>codex login status</code> to check, and <code>codex exec</code> read-only, with no tools, to
        caption.
      </p>
      <div className={s.form}>
        <TextField label="Codex CLI path" value={ep.codex_path} onChange={(v) => onChange({ ...ep, codex_path: v })} mono description="“codex” finds it on the server’s PATH." />
        <TextField label="Model" value={ep.model} onChange={(v) => onChange({ ...ep, model: v })} mono description={`Suggested: ${provider.default_models.vlm}`} />
        <NumberField
          label="Requests per day"
          minValue={0}
          value={ep.daily_limit}
          onChange={(v) => onChange({ ...ep, daily_limit: Number.isFinite(v) ? v : 0 })}
          description={`0 uses the default (${formatNumber(provider.daily_limit ?? 0)}). Protects your ChatGPT plan's limits.`}
        />
      </div>
      <div>
        <Button variant="secondary" icon={busy ? LoaderCircle : PlugZap} busy={busy} onPress={recheck}>
          Check again
        </Button>
      </div>
      {checked && !checked.ok && checked.reason && <p className={s.statusNote}>{checked.reason}</p>}
    </div>
  )
}

function Advanced({ ep, provider, onChange }: { ep: EndpointDraft; provider: Provider; onChange: (ep: EndpointDraft) => void }) {
  return (
    <Disclosure className={s.advanced}>
      <Heading level={4} className={s.advancedHead}>
        <RacButton slot="trigger" className={s.advancedButton}>
          <Ic icon={ChevronRight} size={14} className={s.chev} />
          Advanced
        </RacButton>
      </Heading>
      <DisclosurePanel>
        <div className={s.form} style={{ paddingBlockStart: 'var(--space-3)' }}>
          <NumberField label="Requests at a time" minValue={0} maxValue={16} value={ep.concurrency} onChange={(v) => onChange({ ...ep, concurrency: Number.isFinite(v) ? v : 0 })} description={`0 uses the default (${provider.concurrency}).`} />
          <NumberField label="Shots per request" minValue={0} maxValue={8} value={ep.batch} onChange={(v) => onChange({ ...ep, batch: Number.isFinite(v) ? v : 0 })} description={`0 uses the default (${provider.batch}).`} />
        </div>
      </DisclosurePanel>
    </Disclosure>
  )
}

// ---------------------------------------------------------------- confirmation (§3.20)

function ConfirmEgress({ plan, busy, onCancel, onConfirm }: { plan: SavePlan | null; busy: boolean; onCancel: () => void; onConfirm: () => void }) {
  const frames = plan?.remote.some((r) => r.role === 'vlm')
  const dests = [...new Set(plan?.remote.map((r) => r.to) ?? [])]
  return (
    <Dialog
      isOpen={Boolean(plan)}
      onOpenChange={(o) => !o && onCancel()}
      title="Content will leave this machine"
      size="m"
      role="alertdialog"
      footer={
        <>
          <Button variant="secondary" autoFocus onPress={onCancel}>
            Cancel
          </Button>
          <Button variant="dangerFilled" busy={busy} onPress={onConfirm}>
            {frames ? 'Turn on and send frames' : 'Turn on and send text'}
          </Button>
        </>
      }
    >
      <div className={s.group} data-testid="egress-confirm">
        <p>
          <strong>
            {frames ? 'Frames and text from your footage' : 'Text from your analysis'} will be sent to {dests.join(' and ')}.
          </strong>{' '}
          This happens during analysis of every new file, and for files re-analysed now. Footage files themselves are not uploaded.
        </p>
        {plan?.remote.map((r) => (
          <div key={r.role}>
            <span className={l.figureLabel}>
              {ROLE_TITLE[r.role]} · {r.ep.provider === 'custom' ? endpointHost(r.ep.base_url) : PROVIDER_NAME[r.ep.provider]}
            </span>
            <ul className={s.confirmList}>
              {SENDS[r.role].map((x) => (
                <li key={x}>{x}</li>
              ))}
            </ul>
          </div>
        ))}
        <p className={s.muted}>
          Never sent: {NEVER_SENT.join(', ').toLowerCase()}. You can pause hosted providers at any time; the top bar shows <em>Leaves this machine</em> while they
          are on.
        </p>
      </div>
    </Dialog>
  )
}

// ---------------------------------------------------------------- bundled models

function BundledModels({ models }: { models: AdminSettings['models'] }) {
  return (
    <div className={s.group}>
      <h2>Bundled models</h2>
      <table className={l.table}>
        <thead>
          <tr>
            <th>Model</th>
            <th>Purpose</th>
            <th>Licence</th>
            <th className={l.num}>Size</th>
            <th>Runs</th>
          </tr>
        </thead>
        <tbody>
          {models.map((m) => (
            <tr key={m.name}>
              <td style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>{m.name}</td>
              <td>{m.purpose}</td>
              <td>{m.licence}</td>
              <td className={l.num}>{formatNumber(m.size_mb)} MB</td>
              <td>{m.installed ? <StatusText tone="neutral" icon={HardDrive}>Local</StatusText> : <StatusText tone="caution">Not installed</StatusText>}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

