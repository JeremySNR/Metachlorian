import { useEffect, useState, type ReactNode } from 'react'
import { Link, useParams } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { Bot, Cloud, Copy, HardDrive, KeyRound, Plus, ScanFace, Trash2 } from 'lucide-react'
import type { Scope } from '../../api/types'
import { api, ApiError } from '../../api/client'
import { useAdminSettings, useAudit, useHealth, useMe, usePeople, useTokens, useUsers } from '../../api/queries'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { ModelAdapters } from './ModelProviders'
import { ImportSettings } from './ImportSettings'
import { FormatsSettings } from './Formats'
import { Button } from '../../components/Button'
import { Dialog } from '../../components/Dialog'
import { EmptyState, StatusText } from '../../components/EmptyState'
import { Checkbox, NumberField, Radio, RadioGroup, Select, Switch, TextField } from '../../components/Field'
import { Segmented } from '../../components/Segmented'
import { toast } from '../../components/Toast'
import { bridge, can, desktopInfo, type DesktopInfo } from '../../lib/bridge'
import { formatDateTime, formatRelative, humanise, plural } from '../../lib/format'
import { usePrefs, type Density, type MotionPref, type Theme } from '../../lib/store'
import { Keys, SHORTCUTS } from '../shell/ShortcutsDialog'
import l from '../library/Library.module.css'
import s from './Settings.module.css'

const SECTIONS: { id: string; label: string; admin?: boolean; desktop?: boolean }[] = [
  { id: 'appearance', label: 'Appearance' },
  { id: 'playback', label: 'Playback' },
  { id: 'keyboard', label: 'Keyboard' },
  { id: 'connection', label: 'Connection', desktop: true },
  { id: 'users', label: 'Users and roles', admin: true },
  { id: 'tokens', label: 'API tokens for agents', admin: true },
  { id: 'adapters', label: 'Model adapters', admin: true },
  { id: 'privacy', label: 'Privacy and analysis', admin: true },
  { id: 'imports', label: 'Imports' },
  { id: 'formats', label: 'Formats' },
  { id: 'audit', label: 'Audit log', admin: true },
  { id: 'storage', label: 'Storage and proxies', admin: true },
  { id: 'about', label: 'About' },
]

/** Settings and admin (system.md §9.9). */
export function SettingsPage() {
  const { section } = useParams({ from: '/settings/$section' })
  const me = useMe()
  const isAdmin = me.data?.scopes.includes('admin')
  const desktop = Boolean(bridge()?.desktop)
  const visible = SECTIONS.filter((x) => (!x.desktop || desktop) && (!x.admin || isAdmin !== false))
  const current = visible.find((x) => x.id === section)
  useDocumentTitle(current?.label ?? 'Not found', 'Settings')
  return (
    <div className={s.page}>
      <nav className={s.nav} aria-label="Settings sections">
        <span className={s.navHead}>Settings</span>
        {visible.map((x) => (
          <Link key={x.id} to="/settings/$section" params={{ section: x.id }} className={s.navLink}>
            {x.label}
          </Link>
        ))}
      </nav>
      <main id="main" className={s.main}>
        <div className={s.inner}>
          <h1>{current ? current.label : 'Not found'}</h1>
          {!current && (
            <EmptyState inline title="There's no settings section here">
              {isAdmin === false && SECTIONS.some((x) => x.id === section) ? 'Only admins can see this section.' : 'Pick a section from the list.'}
            </EmptyState>
          )}
          {!current ? null : current.id === 'appearance' && <Appearance />}
          {current?.id === 'playback' && <Playback />}
          {current?.id === 'keyboard' && <Keyboard />}
          {current?.id === 'connection' && <Connection />}
          {current?.id === 'users' && <Users />}
          {current?.id === 'tokens' && <Tokens />}
          {current?.id === 'adapters' && <ModelAdapters onAdminError={(e) => <AdminOnly error={e} />} />}
          {current?.id === 'privacy' && <PrivacySettings />}
          {current?.id === 'imports' && <ImportSettings />}
          {current?.id === 'formats' && <FormatsSettings />}
          {current?.id === 'audit' && <Audit />}
          {current?.id === 'storage' && <Storage />}
          {current?.id === 'about' && <About />}
        </div>
      </main>
    </div>
  )
}

function Row({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <div className={s.row}>
      <span className={s.rowLabel}>
        <span>{label}</span>
        {hint && <span>{hint}</span>}
      </span>
      <div>{children}</div>
    </div>
  )
}

function Appearance() {
  const p = usePrefs()
  return (
    <section className={s.group}>
      <Row label="Theme" hint="System follows your operating system.">
        <Segmented<Theme> label="Theme" value={p.theme} onChange={(v) => p.set({ theme: v })} segments={[{ id: 'system', label: 'System' }, { id: 'light', label: 'Light' }, { id: 'dark', label: 'Dark' }]} />
      </Row>
      <Row label="Density">
        <Segmented<Density> label="Density" value={p.density} onChange={(v) => p.set({ density: v })} segments={[{ id: 'compact', label: 'Compact' }, { id: 'default', label: 'Default' }, { id: 'comfortable', label: 'Comfortable' }]} />
      </Row>
      <Row label="Text size">
        <Segmented label="Text size" value={String(p.textSize) as '100' | '112.5' | '125'} onChange={(v) => p.set({ textSize: Number(v) as 100 | 112.5 | 125 })} segments={[{ id: '100', label: '100%' }, { id: '112.5', label: '112.5%' }, { id: '125', label: '125%' }]} />
      </Row>
      <Row label="Motion" hint="Reduced removes transitions and hover playback.">
        <Segmented<MotionPref> label="Motion" value={p.motion} onChange={(v) => p.set({ motion: v })} segments={[{ id: 'system', label: 'System' }, { id: 'reduced', label: 'Reduced' }, { id: 'full', label: 'Full' }]} />
      </Row>
      <Row label="Contrast">
        <Segmented label="Contrast" value={p.contrast} onChange={(v) => p.set({ contrast: v })} segments={[{ id: 'system', label: 'System' }, { id: 'more', label: 'More' }]} />
      </Row>
    </section>
  )
}

function Playback() {
  const p = usePrefs()
  return (
    <section className={s.group}>
      <Row label="Scrub on hover" hint="Moving the pointer across a thumbnail steps through the shot.">
        <Switch isSelected={p.scrub} onChange={(v) => p.set({ scrub: v })}>{p.scrub ? 'On' : 'Off'}</Switch>
      </Row>
      <Row label="Play when the pointer rests" hint="Muted, after 0.4 s, never under reduced motion.">
        <Switch isSelected={p.dwellPreview} onChange={(v) => p.set({ dwellPreview: v })}>{p.dwellPreview ? 'On' : 'Off'}</Switch>
      </Row>
      <Row label="Timecode">
        <Select aria-label="Timecode format" options={[{ id: 'smpte', label: 'SMPTE (00:14:03:12)' }, { id: 'frames', label: 'Frames (#21342)' }, { id: 'seconds', label: 'Seconds (14:03.48)' }]} selectedKey={p.timecodeFormat} onSelectionChange={(k) => p.set({ timecodeFormat: k as 'smpte' })} />
      </Row>
    </section>
  )
}

function Keyboard() {
  const p = usePrefs()
  return (
    <section className={s.group}>
      <Row label="Single-key shortcuts" hint="Space, J K L, I O, B and friends. Off: everything stays in the command menu.">
        <Switch isSelected={p.singleKeys} onChange={(v) => p.set({ singleKeys: v })}>{p.singleKeys ? 'On' : 'Off'}</Switch>
      </Row>
      {SHORTCUTS.map((sec) => (
        <div key={sec.surface} className={s.group}>
          <h2>{sec.surface}</h2>
          <table className={l.table}>
            <tbody>
              {sec.rows.map(([keys, desc]) => (
                <tr key={desc}>
                  <td style={{ inlineSize: 220 }}><Keys combos={keys} /></td>
                  <td>{desc}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </section>
  )
}

function Connection() {
  const [info, setInfo] = useState<DesktopInfo | null>(null)
  const [mode, setMode] = useState<'solo' | 'team'>('solo')
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    desktopInfo().then((i) => {
      setInfo(i)
      if (i) {
        setMode(i.mode)
        if (i.mode === 'team') setUrl(i.baseUrl)
      }
    })
  }, [])
  if (!can('canSwitchServer')) return <EmptyState inline title="Only in the desktop app">In a browser, Metachlorian always talks to the server that served this page.</EmptyState>
  const apply = async () => {
    setBusy(true)
    const r = await bridge()?.setServer(mode, mode === 'team' ? url.trim() : undefined)
    setBusy(false)
    if (r && !r.ok) toast({ title: "Couldn't connect", description: r.error, tone: 'error' })
  }
  return (
    <section className={s.group}>
      <p className={s.muted}>Currently {info?.mode === 'team' ? `connected to ${info.baseUrl}` : 'running on this computer'}{info?.version ? ` · app ${info.version}` : ''}.</p>
      <RadioGroup label="Library" value={mode} onChange={(v) => setMode(v as 'solo' | 'team')}>
        <Radio value="solo" description="Metachlorian runs on this computer. Footage and analysis stay here.">This computer</Radio>
        <Radio value="team" description="Connect to a shared Metachlorian server on your network.">A server</Radio>
      </RadioGroup>
      {mode === 'team' && <TextField label="Server address" value={url} onChange={setUrl} placeholder="https://metachlorian.studio.lan" mono />}
      <div>
        <Button variant="primary" busy={busy} isDisabled={mode === 'team' && !url.trim()} onPress={apply}>
          Test and switch
        </Button>
      </div>
      <p className={s.muted} style={{ fontSize: 'var(--text-sm)' }}>The app restarts to switch libraries.</p>
    </section>
  )
}

function Users() {
  const users = useUsers()
  const qc = useQueryClient()
  const [name, setName] = useState('')
  const [role, setRole] = useState('editor')
  const [password, setPassword] = useState('')
  const roles = ['admin', 'editor', 'viewer', 'agent']
  if (users.isError) return <AdminOnly error={users.error} />
  const create = async () => {
    try {
      await api.post('/api/admin/users', { username: name.trim(), role, password: password || undefined })
      toast({ title: `Added ${name.trim()}` })
      setName('')
      setPassword('')
      qc.invalidateQueries({ queryKey: ['admin', 'users'] })
    } catch (e) {
      toast({ title: "Couldn't add the user", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    }
  }
  const patch = async (id: number, body: Record<string, unknown>) => {
    await api.patch(`/api/admin/users/${id}`, body)
    qc.invalidateQueries({ queryKey: ['admin', 'users'] })
  }
  return (
    <section className={s.group}>
      <table className={l.table}>
        <thead>
          <tr>
            <th>User</th>
            <th>Role</th>
            <th>Created</th>
            <th>State</th>
          </tr>
        </thead>
        <tbody>
          {(users.data ?? []).length === 0 && (
            <tr>
              <td colSpan={4} className={s.muted}>No users yet. In solo mode you are the local admin.</td>
            </tr>
          )}
          {(users.data ?? []).map((u) => (
            <tr key={u.id}>
              <td>{u.role === 'agent' && <Bot size={14} strokeWidth={2} aria-hidden="true" style={{ display: 'inline', marginInlineEnd: 6, verticalAlign: '-2px' }} />}{u.display_name || u.username}</td>
              <td style={{ inlineSize: 180 }}>
                <Select aria-label={`Role for ${u.username}`} options={roles.map((r) => ({ id: r, label: humanise(r) }))} selectedKey={u.role} onSelectionChange={(k) => patch(u.id, { role: k })} />
              </td>
              <td>{formatDateTime(u.created_at)}</td>
              <td>
                <Switch isSelected={!u.disabled} onChange={(v) => patch(u.id, { disabled: !v })}>{u.disabled ? 'Disabled' : 'Active'}</Switch>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <h2>Add a user</h2>
      <form className={s.form} onSubmit={(e) => { e.preventDefault(); create() }}>
        <TextField label="Username" value={name} onChange={setName} />
        <Select label="Role" options={roles.filter((r) => r !== 'agent').map((r) => ({ id: r, label: humanise(r) }))} selectedKey={role} onSelectionChange={(k) => setRole(String(k))} />
        <TextField label="Password" type="password" description="At least 10 characters. Needed for team mode." value={password} onChange={setPassword} className={s.formWide} />
        <div><Button type="submit" variant="secondary" icon={Plus} isDisabled={!name.trim()}>Add user</Button></div>
      </form>
    </section>
  )
}

function mcpSnippets(token: string, dataDir: string) {
  const origin = window.location.origin
  const stdio = JSON.stringify({ mcpServers: { metachlorian: { command: 'metachlorian', args: ['--data', dataDir, 'mcp'], env: { METACHLORIAN_TOKEN: token } } } }, null, 2)
  const http = JSON.stringify({ mcpServers: { metachlorian: { type: 'http', url: `${origin}/mcp`, headers: { Authorization: `Bearer ${token}` } } } }, null, 2)
  const cli = `claude mcp add --transport http metachlorian ${origin}/mcp --header "Authorization: Bearer ${token}"`
  return { stdio, http, cli }
}

function CodeBlock({ title, code }: { title: string; code: string }) {
  return (
    <div className={s.group} style={{ gap: 'var(--space-1_5)' }}>
      <div className={s.codeHead}>
        <span className={l.figureLabel}>{title}</span>
        <Button variant="quiet" size="sm" icon={Copy} onPress={() => { navigator.clipboard?.writeText(code); toast({ title: `Copied ${title.toLowerCase()}`, tone: 'info' }) }}>Copy</Button>
      </div>
      <pre className={s.code}>{code}</pre>
    </div>
  )
}

function Tokens() {
  const tokens = useTokens()
  const settings = useAdminSettings()
  const qc = useQueryClient()
  const [open, setOpen] = useState(false)
  const [name, setName] = useState('Claude Desktop')
  const [username, setUsername] = useState('agent')
  const [scopes, setScopes] = useState<Scope[]>(['library:read'])
  const [ttl, setTtl] = useState(90)
  const [created, setCreated] = useState<string | null>(null)
  if (tokens.isError) return <AdminOnly error={tokens.error} />
  const create = async () => {
    try {
      const r = await api.post<{ token: string }>('/api/admin/tokens', { name, username, scopes, ttl_days: ttl })
      setCreated(r.token)
      qc.invalidateQueries({ queryKey: ['admin', 'tokens'] })
    } catch (e) {
      toast({ title: "Couldn't create the token", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    }
  }
  const snippets = mcpSnippets(created ?? '<token>', settings.data?.settings.data_dir ?? '~/.local/share/metachlorian')
  const allScopes = tokens.data?.scopes ?? ({} as Record<Scope, string>)
  return (
    <section className={s.group}>
      <p className={s.muted}>Agents connect over MCP with a token. <strong>Agents using a token only ever see cleared shots</strong>, whatever its scopes.</p>
      <div><Button variant="primary" icon={KeyRound} onPress={() => { setCreated(null); setOpen(true) }}>Create token</Button></div>
      <table className={l.table} data-testid="tokens-table">
        <thead>
          <tr>
            <th>Name</th>
            <th>Agent</th>
            <th>Scopes</th>
            <th>Created</th>
            <th>Last used</th>
            <th>Expires</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {(tokens.data?.tokens ?? []).length === 0 && <tr><td colSpan={7} className={s.muted}>No tokens yet.</td></tr>}
          {(tokens.data?.tokens ?? []).map((t) => (
            <tr key={t.id} style={t.revoked ? { color: 'var(--fg-3)' } : undefined}>
              <td>{t.name} <span className={s.scopeDesc}>{t.prefix}…</span></td>
              <td><Bot size={14} strokeWidth={2} aria-hidden="true" style={{ display: 'inline', marginInlineEnd: 6, verticalAlign: '-2px' }} />{t.username}</td>
              <td style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>{t.scopes.join(', ')}</td>
              <td>{formatRelative(t.created_at)}</td>
              <td>{t.last_used ? formatRelative(t.last_used) : 'Never'}</td>
              <td>{t.expires_at ? formatDateTime(t.expires_at) : 'Never'}</td>
              <td>
                {t.revoked ? 'Revoked' : (
                  <Button variant="quiet" size="sm" icon={Trash2} onPress={async () => { await api.del(`/api/admin/tokens/${t.id}`); toast({ title: `Revoked ${t.name}`, tone: 'info' }); qc.invalidateQueries({ queryKey: ['admin', 'tokens'] }) }}>Revoke</Button>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      <h2>Connect an agent</h2>
      <CodeBlock title="Local agents (stdio)" code={snippets.stdio} />
      <CodeBlock title="Remote agents (HTTP)" code={snippets.http} />
      <Dialog
        isOpen={open}
        onOpenChange={setOpen}
        title={created ? 'Token created' : 'Create an API token'}
        size="m"
        footer={created ? <Button variant="primary" onPress={() => setOpen(false)}>Done</Button> : <><Button variant="secondary" onPress={() => setOpen(false)}>Cancel</Button><Button variant="primary" isDisabled={!name.trim() || !username.trim() || !scopes.length} onPress={create}>Create token</Button></>}
      >
        {created ? (
          <div className={s.group} data-testid="new-token">
            <p>Copy it now. It is shown once and can't be retrieved later.</p>
            <div className={s.token}>{created}</div>
            <div><Button variant="secondary" icon={Copy} onPress={() => { navigator.clipboard?.writeText(created); toast({ title: 'Copied the token', tone: 'info' }) }}>Copy token</Button></div>
            <p className={s.muted}>Agents using this token only see cleared shots.</p>
            <CodeBlock title="Claude Code" code={snippets.cli} />
            <CodeBlock title="MCP config (stdio)" code={snippets.stdio} />
            <CodeBlock title="MCP config (HTTP)" code={snippets.http} />
          </div>
        ) : (
          <div className={s.group}>
            <div className={s.form}>
              <TextField label="Name" value={name} onChange={setName} />
              <TextField label="Agent username" value={username} onChange={setUsername} mono />
              <NumberField label="Expires after (days)" description="0 never expires" minValue={0} value={ttl} onChange={setTtl} />
            </div>
            <span className={l.figureLabel}>Scopes</span>
            <div className={s.scopes}>
              {(Object.keys(allScopes) as Scope[]).map((sc) => (
                <Checkbox key={sc} isSelected={scopes.includes(sc)} onChange={(v) => setScopes(v ? [...scopes, sc] : scopes.filter((x) => x !== sc))}>
                  <span>
                    <span style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>{sc}</span>
                    <br />
                    <span className={s.scopeDesc}>{allScopes[sc]}</span>
                  </span>
                </Checkbox>
              ))}
            </div>
          </div>
        )}
      </Dialog>
    </section>
  )
}

/** Face identity on or off, and where analysis content goes (system.md §3.20). */
function PrivacySettings() {
  const settings = useAdminSettings()
  const health = useHealth()
  const people = usePeople({ limit: 1 })
  const qc = useQueryClient()
  const [busy, setBusy] = useState(false)
  if (settings.isError) return <AdminOnly error={settings.error} />
  const st = settings.data?.settings
  if (!st) return <div aria-busy="true" />
  const setFaces = async (on: boolean) => {
    setBusy(true)
    try {
      await api.put('/api/admin/settings', { face_identity: on })
      for (const k of [['admin', 'settings'], ['people'], ['processing']]) qc.invalidateQueries({ queryKey: k })
      toast({
        title: on ? 'Face recognition is on' : 'Face recognition is off',
        description: on ? 'Files are queued to find faces; people appear as analysis finishes.' : 'No new faces are matched. People already found stay until you forget them.',
        tone: 'info',
      })
    } catch (e) {
      toast({ title: "Couldn't change face recognition", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    } finally {
      setBusy(false)
    }
  }
  const remote = health.data?.egress.content_leaves_machine
  const known = people.data?.total ?? 0
  return (
    <section className={s.group}>
      <div className={s.group}>
        <h2>Face identity</h2>
        <Row label="Face recognition" hint="Finds faces, groups them into people you can name, and lets search filter by person.">
          <Switch isSelected={st.face_identity} isDisabled={busy} onChange={setFaces}>
            {st.face_identity ? 'On' : 'Off'}
          </Switch>
        </Row>
        <ul className={s.facts}>
          <li>Runs only on this machine, with bundled models (YuNet to find faces, SFace to compare them).</li>
          <li>Face crops and face embeddings stay in this library. They are never sent to a model provider, hosted or not.</li>
          <li>Names are yours: only editors can name or merge people, and agents can't.</li>
          <li>An admin can forget a person on their page, which deletes their face crops and embeddings.</li>
        </ul>
        <div>
          <Link to="/people" className={s.inlineLink}>
            <ScanFace size={16} strokeWidth={1.75} aria-hidden="true" />
            {known ? `People · ${plural(known, 'person', 'people')} found` : 'People'}
          </Link>
        </div>
      </div>
      <div className={s.group}>
        <h2>Model providers</h2>
        <Row label="Where analysis runs" hint="Captions and summaries can use a hosted provider; everything else runs here.">
          {remote ? <StatusText tone="caution" icon={Cloud} filled>Leaves this machine</StatusText> : <StatusText tone="neutral" icon={HardDrive}>Local: nothing leaves this machine</StatusText>}
        </Row>
        <div>
          <Link to="/settings/$section" params={{ section: 'adapters' }} className={s.inlineLink}>
            Model adapters
          </Link>
        </div>
      </div>
    </section>
  )
}

function Audit() {
  const [agents, setAgents] = useState(false)
  const audit = useAudit(agents)
  if (audit.isError) return <AdminOnly error={audit.error} />
  return (
    <section className={s.group}>
      <Switch isSelected={agents} onChange={setAgents}>Agents only</Switch>
      <table className={l.table} data-testid="audit-table">
        <thead>
          <tr>
            <th>When</th>
            <th>Who</th>
            <th>Via</th>
            <th>Action</th>
            <th>Target</th>
          </tr>
        </thead>
        <tbody>
          {(audit.data ?? []).map((e) => (
            <tr key={e.id}>
              <td title={formatDateTime(e.at)}>{formatRelative(e.at)}</td>
              <td>{e.role === 'agent' && <Bot size={14} strokeWidth={2} aria-hidden="true" style={{ display: 'inline', marginInlineEnd: 6, verticalAlign: '-2px' }} />}{e.actor}</td>
              <td>{e.via}</td>
              <td>{humanise(e.action)}{e.ok ? '' : ' (refused)'}</td>
              <td style={{ maxInlineSize: 320, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>{e.target}</td>
            </tr>
          ))}
          {audit.data?.length === 0 && <tr><td colSpan={5} className={s.muted}>Nothing logged yet.</td></tr>}
        </tbody>
      </table>
    </section>
  )
}

function Storage() {
  const settings = useAdminSettings()
  if (settings.isError) return <AdminOnly error={settings.error} />
  const st = settings.data?.settings
  if (!st) return null
  return (
    <section className={s.group}>
      <Row label="Library data"><code>{st.data_dir}</code></Row>
      <Row label="Models"><code>{st.models_dir}</code></Row>
      <Row label="Proxy height">{st.proxy_height} px · CRF {st.proxy_crf}</Row>
      <Row label="Sprite interval">One frame every {st.sprite_interval} s</Row>
      <Row label="Longest segment">{st.max_segment_s} s (long takes are split)</Row>
      <Row label="Workers">{st.workers}</Row>
      <Row label="Authentication">{st.require_auth ? 'Required (team mode)' : 'Solo mode: this machine only'}</Row>
    </section>
  )
}

function About() {
  const h = useHealth()
  return (
    <section className={s.group}>
      <Row label="Version">{h.data?.version ?? '—'}</Row>
      <Row label="Where content goes">{h.data?.egress.content_leaves_machine ? 'Some content leaves this machine' : 'Everything stays on this machine'}</Row>
      <Row label="Licence">Apache-2.0. Fonts: Instrument Sans and JetBrains Mono (OFL-1.1). Icons: Lucide (ISC).</Row>
    </section>
  )
}

function AdminOnly({ error }: { error: unknown }) {
  return (
    <EmptyState inline title={error instanceof ApiError && error.status === 403 ? 'Only admins can see this' : "Couldn't load this section"} role="alert">
      {error instanceof ApiError && error.status === 403 ? 'Ask an admin to give you access.' : String((error as Error)?.message ?? error)}
    </EmptyState>
  )
}
