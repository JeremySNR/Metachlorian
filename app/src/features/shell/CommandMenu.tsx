import { useMemo, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { Autocomplete, Input, Menu, MenuItem, MenuSection, Header, SearchField, type Key } from 'react-aria-components'
import {
  Clapperboard, Film, FolderSearch, FolderTree, HardDrive, Keyboard, Layers, Library, ListChecks, Moon, PanelLeft, PanelRight, ScanFace, Search, Settings, ShieldCheck, Sun, SunMoon, type LucideIcon,
} from 'lucide-react'
import { useCollections } from '../../api/queries'
import { Dialog } from '../../components/Dialog'
import { Ic } from '../../components/Icon'
import { MOD } from '../../lib/bridge'
import { usePrefs, useUi } from '../../lib/store'
import t from '../../styles/type.module.css'
import s from './AppShell.module.css'

interface Cmd {
  id: string
  label: string
  icon: LucideIcon
  meta?: string
  run: () => void
}

/** Subsequence fuzzy match: "clct" matches "Collections". */
export function fuzzy(text: string, query: string): boolean {
  const q = query.toLowerCase().replace(/\s+/g, '')
  if (!q) return true
  const h = text.toLowerCase()
  if (h.includes(query.toLowerCase().trim())) return true
  let i = 0
  for (const c of h) if (c === q[i]) i++
  return i === q.length
}

/** ⌘K: every action is reachable here (system.md §3.24). */
export function CommandMenu() {
  const open = useUi((u) => u.commandOpen)
  const set = useUi((u) => u.set)
  const navigate = useNavigate()
  const collections = useCollections()
  const recent = usePrefs((p) => p.recentShots)
  const [query, setQuery] = useState('')
  const close = () => {
    set({ commandOpen: false })
    setQuery('')
  }

  const sections = useMemo(() => {
    const p = usePrefs.getState()
    const actions: Cmd[] = [
      { id: 'focus-search', label: 'Search shots', icon: Search, meta: '/', run: () => window.setTimeout(() => window.dispatchEvent(new Event('mc:focus-search')), 30) },
      { id: 'scope-folder', label: 'Search in folder…', icon: FolderSearch, run: () => set({ scopeDialog: 'folder' }) },
      { id: 'scope-collection', label: 'Search in collection…', icon: Layers, run: () => set({ scopeDialog: 'collection' }) },
      { id: 'toggle-rail', label: 'Toggle filter rail', icon: PanelLeft, meta: `${MOD}\\`, run: () => p.set({ railOpen: !usePrefs.getState().railOpen }) },
      { id: 'toggle-inspector', label: 'Toggle inspector', icon: PanelRight, meta: `${MOD}I`, run: () => p.set({ inspectorOpen: !usePrefs.getState().inspectorOpen }) },
      { id: 'theme-dark', label: 'Theme: dark', icon: Moon, run: () => p.set({ theme: 'dark' }) },
      { id: 'theme-light', label: 'Theme: light', icon: Sun, run: () => p.set({ theme: 'light' }) },
      { id: 'theme-system', label: 'Theme: follow system', icon: SunMoon, run: () => p.set({ theme: 'system' }) },
      { id: 'shortcuts', label: 'Keyboard shortcuts', icon: Keyboard, meta: '?', run: () => set({ shortcutsOpen: true }) },
    ]
    const go: Cmd[] = [
      { id: 'go-search', label: 'Go to Search', icon: Search, meta: `${MOD}1`, run: () => navigate({ to: '/search' }) },
      { id: 'go-library', label: 'Go to Library overview', icon: Library, meta: `${MOD}2`, run: () => navigate({ to: '/library' }) },
      { id: 'go-collections', label: 'Go to Collections', icon: Layers, meta: `${MOD}3`, run: () => navigate({ to: '/collections' }) },
      { id: 'go-ingest', label: 'Go to Ingest and processing', icon: HardDrive, meta: `${MOD}4`, run: () => navigate({ to: '/ingest' }) },
      { id: 'go-rights', label: 'Go to Rights and governance', icon: ShieldCheck, meta: `${MOD}5`, run: () => navigate({ to: '/rights' }) },
      { id: 'go-people', label: 'Go to People', icon: ScanFace, meta: `${MOD}6`, run: () => navigate({ to: '/people' }) },
      { id: 'go-folders', label: 'Go to Library folders', icon: FolderTree, run: () => navigate({ to: '/library/folders' }) },
      { id: 'go-corrections', label: 'Go to Corrections log', icon: ListChecks, run: () => navigate({ to: '/library/corrections' }) },
      { id: 'go-settings', label: 'Go to Settings', icon: Settings, meta: `${MOD},`, run: () => navigate({ to: '/settings/$section', params: { section: 'appearance' } }) },
      { id: 'go-tokens', label: 'Settings: API tokens for agents', icon: Settings, run: () => navigate({ to: '/settings/$section', params: { section: 'tokens' } }) },
      { id: 'go-adapters', label: 'Settings: model adapters', icon: Settings, run: () => navigate({ to: '/settings/$section', params: { section: 'adapters' } }) },
      { id: 'go-privacy', label: 'Settings: privacy and analysis (face recognition)', icon: Settings, run: () => navigate({ to: '/settings/$section', params: { section: 'privacy' } }) },
    ]
    const cols: Cmd[] = (collections.data ?? []).map((c) => ({ id: `col-${c.uid}`, label: c.name, icon: Layers, meta: `${c.items} shots`, run: () => navigate({ to: '/collections/$collectionId', params: { collectionId: c.uid } }) }))
    const shots: Cmd[] = recent.slice(0, 6).map((uid) => {
      const r = useUi.getState().resultCache.get(uid)
      return { id: `shot-${uid}`, label: r ? `${r.filename} · shot ${r.idx + 1}` : `Shot ${uid}`, icon: r ? Film : Clapperboard, run: () => navigate({ to: '/shot/$shotId', params: { shotId: uid } }) }
    })
    return [
      { name: 'Actions', items: actions },
      { name: 'Go to', items: go },
      { name: 'Collections', items: cols },
      { name: 'Recent shots', items: shots },
    ].filter((sec) => sec.items.length)
  }, [collections.data, recent, navigate, set])

  const all = new Map(sections.flatMap((sec) => sec.items.map((i) => [i.id, i] as const)))
  const visible = sections.map((sec) => ({ ...sec, items: sec.items.filter((i) => fuzzy(i.label, query)) })).filter((sec) => sec.items.length)

  return (
    <Dialog isOpen={open} onOpenChange={(o) => (o ? set({ commandOpen: true }) : close())} title="Command menu" size="m" top bare aria-label="Command menu">
      <div className={s.command}>
        <Autocomplete inputValue={query} onInputChange={setQuery}>
          <SearchField aria-label="Type a command or search" autoFocus className={s.commandInput}>
            <Ic icon={Search} />
            <Input placeholder="Type a command, page or collection" />
          </SearchField>
          <Menu
            className={s.commandList}
            aria-label="Commands"
            onAction={(key: Key) => {
              const cmd = all.get(String(key))
              close()
              cmd?.run()
            }}
            renderEmptyState={() => <div className={s.commandEmpty}>Nothing matches “{query}”.</div>}
          >
            {visible.map((sec) => (
              <MenuSection key={sec.name} id={sec.name}>
                <Header className={t.slate} style={{ padding: 'var(--space-2) var(--space-3) var(--space-1)' }}>
                  {sec.name}
                </Header>
                {sec.items.map((i) => (
                  <MenuItem key={i.id} id={i.id} textValue={i.label} className={s.commandItem}>
                    <Ic icon={i.icon} />
                    <span>{i.label}</span>
                    {i.meta && <span className={s.meta}>{i.meta}</span>}
                  </MenuItem>
                ))}
              </MenuSection>
            ))}
          </Menu>
        </Autocomplete>
      </div>
    </Dialog>
  )
}
