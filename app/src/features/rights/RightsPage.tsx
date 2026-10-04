import { useMemo, useState } from 'react'
import { Link, useNavigate, useSearch } from '@tanstack/react-router'
import { useQueries } from '@tanstack/react-query'
import { Tab, TabList, TabPanel, Tabs } from 'react-aria-components'
import { CalendarClock, PenLine, ShieldCheck, ShieldX } from 'lucide-react'
import type { AssetListItem, RightsRecord } from '../../api/types'
import { api, ApiError, mediaUrl } from '../../api/client'
import { useAssets, useBulkRights, useVocabularies } from '../../api/queries'
import { Button } from '../../components/Button'
import { Dialog } from '../../components/Dialog'
import { EmptyState } from '../../components/EmptyState'
import { Checkbox, Select } from '../../components/Field'
import { RightsBadge } from '../../components/RightsBadge'
import { toast } from '../../components/Toast'
import { daysUntil, formatDate, plural, shortLabel } from '../../lib/format'
import { COMMON_TERRITORIES, stateFromBadge, type RightsState } from '../../lib/rights'
import { usePrefs, useUi } from '../../lib/store'
import type { RightsTab } from '../../routes/router'
import l from '../library/Library.module.css'
import s from './Rights.module.css'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'

const TABS: { id: RightsTab; label: string; states?: RightsState[] }[] = [
  { id: 'expiring', label: 'Expiring soon', states: ['expiring'] },
  { id: 'restricted', label: 'Restricted', states: ['restricted'] },
  { id: 'blocked', label: 'Blocked', states: ['blocked', 'expired'] },
  { id: 'unknown', label: 'Unknown', states: ['unknown'] },
  { id: 'cleared', label: 'Cleared', states: ['cleared'] },
  { id: 'releases', label: 'Releases' },
  { id: 'policies', label: 'Policies' },
]

/** Rights and governance (system.md §9.6). */
export function RightsPage() {
  const search = useSearch({ from: '/rights' })
  const navigate = useNavigate()
  useDocumentTitle('Rights and governance')
  const assets = useAssets()
  const list = useMemo(() => assets.data?.assets ?? [], [assets.data])
  const counts = useMemo(() => {
    const c: Record<string, number> = {}
    for (const a of list) {
      const st = stateFromBadge(a.rights_badge)
      c[st] = (c[st] ?? 0) + 1
    }
    return c
  }, [list])
  const firstWithItems = TABS.find((t) => t.states?.some((x) => counts[x]))?.id ?? 'unknown'
  const tab = search.tab ?? (counts.expiring ? 'expiring' : firstWithItems)

  return (
    <main id="main" className={l.page}>
      <div className={l.inner}>
        <div className={l.titleRow}>
          <h1>Rights and governance</h1>
        </div>
        <Tabs selectedKey={tab} onSelectionChange={(k) => navigate({ to: '/rights', search: { tab: k as RightsTab } })} className={s.tabs}>
          <TabList aria-label="Rights views" className={s.tabList}>
            {TABS.map((t) => (
              <Tab key={t.id} id={t.id} className={s.tab}>
                {t.label}
                {t.states && <span className={s.tabCount}>{t.states.reduce((n, x) => n + (counts[x] ?? 0), 0)}</span>}
              </Tab>
            ))}
          </TabList>
          {TABS.filter((t) => t.states).map((t) => (
            <TabPanel key={t.id} id={t.id}>
              <AssetRightsTable assets={list.filter((a) => t.states?.includes(stateFromBadge(a.rights_badge)))} tab={t} loading={assets.isLoading} />
            </TabPanel>
          ))}
          <TabPanel id="releases">
            <Releases assets={list} />
          </TabPanel>
          <TabPanel id="policies">
            <Policies />
          </TabPanel>
        </Tabs>
      </div>
    </main>
  )
}

function useRightsFor(assets: AssetListItem[]) {
  return useQueries({
    queries: assets.slice(0, 200).map((a) => ({ queryKey: ['rights', a.uid, null], queryFn: () => api.get<RightsRecord>(`/api/rights/${a.uid}`), staleTime: 30_000 })),
  })
}

function AssetRightsTable({ assets, tab, loading }: { assets: AssetListItem[]; tab: (typeof TABS)[number]; loading: boolean }) {
  const [sel, setSel] = useState<Set<string>>(new Set())
  const [expiryOpen, setExpiryOpen] = useState(false)
  const [expiry, setExpiry] = useState('')
  const bulk = useBulkRights()
  const rights = useRightsFor(assets)
  const { label } = useVocabularies()
  const selected = assets.filter((a) => sel.has(a.uid)).map((a) => a.uid)
  const all = assets.length > 0 && selected.length === assets.length

  const apply = async (rightsPatch: Partial<RightsRecord>, verb: string) => {
    try {
      await bulk.mutateAsync({ assetUids: selected, rights: rightsPatch })
      toast({ title: `${verb} ${plural(selected.length, 'file')}` })
      setSel(new Set())
    } catch (e) {
      toast({ title: "Couldn't update rights", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    }
  }

  if (!loading && !assets.length) {
    return (
      <EmptyState inline title={`Nothing ${tab.id === 'expiring' ? 'expires in the next 30 days' : `is ${tab.label.toLowerCase()}`}`}>
        {tab.id === 'unknown' ? 'Every file has rights recorded.' : 'Files move here when their rights change.'}
      </EmptyState>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      <div className={s.bulk} role="toolbar" aria-label="Bulk actions">
        <span>{selected.length ? <><strong>{selected.length}</strong> selected</> : `${plural(assets.length, 'file')}`}</span>
        <Button variant="secondary" size="sm" icon={ShieldCheck} isDisabled={!selected.length} onPress={() => apply({ status: 'cleared' }, 'Marked cleared:')}>Mark cleared</Button>
        <Button variant="secondary" size="sm" icon={CalendarClock} isDisabled={!selected.length} onPress={() => setExpiryOpen(true)}>Set expiry</Button>
        <Button variant="danger" size="sm" icon={ShieldX} isDisabled={!selected.length} onPress={() => apply({ status: 'not_cleared' }, 'Blocked')}>Block</Button>
        <Button variant="secondary" size="sm" icon={PenLine} isDisabled={!selected.length} onPress={() => useUi.getState().set({ rightsDialog: { assetUids: selected, title: plural(selected.length, 'file') } })}>Edit…</Button>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table className={l.table} data-testid="rights-table">
          <thead>
            <tr>
              <th style={{ inlineSize: 32 }}>
                <Checkbox selection aria-label="Select all" isSelected={all} isIndeterminate={!all && selected.length > 0} onChange={(v) => setSel(v ? new Set(assets.map((a) => a.uid)) : new Set())} />
              </th>
              <th>File</th>
              <th>Status</th>
              <th>Expires</th>
              <th>Uses</th>
              <th>Channels</th>
              <th>Territories</th>
              <th>Updated by</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {assets.map((a, i) => {
              const r = rights[i]?.data
              const d = daysUntil(r?.expires)
              return (
                <tr key={a.uid} className={s.row} data-selected={sel.has(a.uid)}>
                  <td>
                    <Checkbox selection aria-label={`Select ${a.filename}`} isSelected={sel.has(a.uid)} onChange={(v) => { const n = new Set(sel); if (v) n.add(a.uid); else n.delete(a.uid); setSel(n) }} />
                  </td>
                  <td>
                    <span className={s.fileCell}>
                      <img src={mediaUrl(a.poster)} alt="" loading="lazy" />
                      <Link to="/file/$assetId" params={{ assetId: a.uid }}>{a.filename}</Link>
                    </span>
                  </td>
                  <td><RightsBadge state={stateFromBadge(a.rights_badge)} record={r} /></td>
                  <td>{r?.expires ? <>{formatDate(r.expires)} {d !== null && <span className={s.small}>({d < 0 ? `${-d} days ago` : `${d} days`})</span>}</> : <span className={s.small}>Never</span>}</td>
                  <td className={s.small}>{r?.permitted_uses?.length ? r.permitted_uses.map((u) => label('usage', u)).join(', ') : r?.status === 'unknown' ? '—' : 'Any'}</td>
                  <td className={s.small}>{r?.channels?.length ? r.channels.map((u) => label('channel', u)).join(', ') : r?.status === 'unknown' ? '—' : 'Any'}</td>
                  <td className={s.small}>{r?.territories?.length ? r.territories.join(', ') : r?.status === 'unknown' ? '—' : 'Any'}</td>
                  <td className={s.small}>{r?.updated_by || '—'}</td>
                  <td>
                    <Button variant="quiet" size="sm" onPress={() => useUi.getState().set({ rightsDialog: { assetUids: [a.uid], title: a.filename } })} aria-label={`Edit rights for ${a.filename}`} data-testid="edit-rights">
                      Edit
                    </Button>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <Dialog
        isOpen={expiryOpen}
        onOpenChange={setExpiryOpen}
        title={`Set expiry for ${plural(selected.length, 'file')}`}
        size="s"
        footer={
          <>
            <Button variant="secondary" onPress={() => setExpiryOpen(false)}>Cancel</Button>
            <Button variant="primary" isDisabled={!expiry} onPress={() => { apply({ expires: expiry }, 'Expiry set for'); setExpiryOpen(false) }}>Set expiry</Button>
          </>
        }
      >
        <label htmlFor="bulk-exp" style={{ display: 'block', marginBlockEnd: 'var(--space-2)' }}>Licence expires on</label>
        <input id="bulk-exp" type="date" value={expiry} onChange={(e) => setExpiry(e.target.value)} style={{ blockSize: 'var(--control-md)', background: 'var(--bg-raised)', border: 'var(--border-width) solid var(--border-control)', borderRadius: 'var(--radius-sm)', paddingInline: 'var(--space-2)' }} />
      </Dialog>
    </div>
  )
}

function Releases({ assets }: { assets: AssetListItem[] }) {
  const rights = useRightsFor(assets)
  const { label } = useVocabularies()
  return (
    <div style={{ overflowX: 'auto' }}>
      <table className={l.table}>
        <thead>
          <tr>
            <th>File</th>
            <th>Model release</th>
            <th>Property release</th>
            <th>Brand safety</th>
            <th />
          </tr>
        </thead>
        <tbody>
          {assets.map((a, i) => {
            const r = rights[i]?.data
            return (
              <tr key={a.uid}>
                <td><span className={s.fileCell}><img src={mediaUrl(a.poster)} alt="" loading="lazy" /><Link to="/file/$assetId" params={{ assetId: a.uid }}>{a.filename}</Link></span></td>
                <td>{r ? label('release_status', r.model_release) : '—'}</td>
                <td>{r ? label('release_status', r.property_release) : '—'}</td>
                <td>{r ? (r.brand_safety === 'safe' ? 'Brand safe' : r.brand_safety === 'unsafe' ? 'Not brand safe' : 'Not assessed') : '—'}</td>
                <td><Button variant="quiet" size="sm" onPress={() => useUi.getState().set({ rightsDialog: { assetUids: [a.uid], title: a.filename } })}>Edit</Button></td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function Policies() {
  const def = usePrefs((p) => p.defaultUse)
  const set = usePrefs((p) => p.set)
  const { vocabs } = useVocabularies()
  const opt = (v: string) => [{ id: '', label: 'Not set' }, ...(vocabs[v]?.terms ?? []).map((t) => ({ id: t.id, label: shortLabel(t.label) }))]
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
      <p className={s.statement}>
        <strong>Agents only see shots that are cleared.</strong> This can't be changed per token. Restricted, blocked and unknown shots never reach an agent, and agents cannot change rights.
      </p>
      <section style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        <h2 className={l.figureLabel}>Default intended use</h2>
        <p className={l.muted}>Prefills the rights check when you send to Cutawan or check a shot.</p>
        <div className={s.form}>
          <Select label="Usage" options={opt('usage')} selectedKey={def.use ?? ''} onSelectionChange={(k) => set({ defaultUse: { ...def, use: String(k) || undefined } })} />
          <Select label="Channel" options={opt('channel')} selectedKey={def.channel ?? ''} onSelectionChange={(k) => set({ defaultUse: { ...def, channel: String(k) || undefined } })} />
          <Select label="Territory" options={[{ id: '', label: 'Not set' }, ...COMMON_TERRITORIES.map(([c, n]) => ({ id: c, label: `${c} · ${n}` }))]} selectedKey={def.territory ?? ''} onSelectionChange={(k) => set({ defaultUse: { ...def, territory: String(k) || undefined } })} />
        </div>
      </section>
      <section style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
        <h2 className={l.figureLabel}>How verdicts work</h2>
        <ul style={{ listStyle: 'disc', paddingInlineStart: 'var(--space-5)', maxInlineSize: 'var(--measure-prose)', lineHeight: 'var(--leading-md)' }}>
          <li>Unknown rights are never treated as cleared.</li>
          <li>Expired licences, uses, channels or territories outside the grant block a shot.</li>
          <li>People in frame need a model release for commercial, advertising and marketing use.</li>
          <li>Shot overrides inherit anything they leave empty from the file.</li>
        </ul>
      </section>
    </div>
  )
}
