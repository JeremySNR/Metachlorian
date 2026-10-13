import brandMark from '../../assets/metachlorian-mark.svg'
import { useEffect, useState } from 'react'
import { Link, Outlet, useNavigate } from '@tanstack/react-router'
import { TooltipTrigger, Focusable } from 'react-aria-components'
import { CircleHelp, Globe, HardDrive, Layers, Library, Menu as MenuIcon, ScanFace, Search, Settings, ShieldCheck, type LucideIcon } from 'lucide-react'
import { IconButton } from '../../components/Button'
import { Menu, MenuItem, MenuPopover, MenuSeparator, MenuTrigger } from '../../components/Menu'
import { useMediaQuery } from '../../hooks/useMediaQuery'
import { Ic } from '../../components/Icon'
import { Toaster, toast } from '../../components/Toast'
import { Tooltip } from '../../components/Tooltip'
import { isTyping, isMod, useDocumentKeys } from '../../hooks/useHotkeys'
import { desktopInfo } from '../../lib/bridge'
import { comboText } from '../../lib/keys'
import { usePrefs, useUi } from '../../lib/store'
import { useAddToCollection, useCollections, useCreateCollection } from '../../api/queries'
import { SearchBar } from '../search/SearchBar'
import { CommandMenu } from './CommandMenu'
import { EgressIndicator } from './EgressIndicator'
import { ShortcutsDialog } from './ShortcutsDialog'
import { GlobalDialogs } from './GlobalDialogs'
import s from './AppShell.module.css'

const NAV: { to: '/library' | '/collections' | '/ingest' | '/rights' | '/people' | '/community'; label: string; icon: LucideIcon; key: string }[] = [
  { to: '/library', label: 'Library', icon: Library, key: '2' },
  { to: '/collections', label: 'Collections', icon: Layers, key: '3' },
  { to: '/ingest', label: 'Ingest', icon: HardDrive, key: '4' },
  { to: '/rights', label: 'Rights', icon: ShieldCheck, key: '5' },
  { to: '/people', label: 'People', icon: ScanFace, key: '6' },
  { to: '/community', label: 'Community', icon: Globe, key: '7' },
]

/** ⌘1…⌘7, in top-bar order (system.md §5.1). */
export const SECTION_KEYS = ['/search', '/library', '/collections', '/ingest', '/rights', '/people', '/community'] as const

const SHOT_MIME = 'application/x-metachlorian-shots'

/** Landmarks cycled by F6 / Shift+F6 (system.md §2.1). */
function cycleLandmark(back: boolean) {
  const marks = Array.from(document.querySelectorAll<HTMLElement>('header, nav, search, [role="search"], aside, main, [role="region"][aria-label="Selection"], [aria-label="Notifications"]')).filter(
    (el) => el.offsetParent !== null || el.getClientRects().length > 0,
  )
  if (!marks.length) return
  const current = marks.findIndex((m) => m.contains(document.activeElement))
  const next = marks[(current + (back ? -1 : 1) + marks.length) % marks.length]
  const target = next.querySelector<HTMLElement>('[tabindex="0"], input, button, a[href], [tabindex]:not([tabindex="-1"])') ?? next
  if (!target.hasAttribute('tabindex') && target === next) next.tabIndex = -1
  target.focus()
}

export function AppShell() {
  const navigate = useNavigate()
  const set = useUi((u) => u.set)
  const [dropTarget, setDropTarget] = useState(false)
  const collections = useCollections()
  const add = useAddToCollection()
  const create = useCreateCollection()
  // Below 480 px the section links fold into a menu and search takes its own row (WCAG 1.4.10 reflow).
  const compactNav = useMediaQuery('(max-width: 479.98px)')

  useEffect(() => {
    desktopInfo().then((info) => {
      if (!info) return
      document.documentElement.dataset.shell = ''
      document.documentElement.dataset.platform = info.platform
    })
  }, [])

  useDocumentKeys((e) => {
    const typing = isTyping(e.target)
    const ui = useUi.getState()
    if (isMod(e) && e.key.toLowerCase() === 'k') {
      e.preventDefault()
      set({ commandOpen: !ui.commandOpen })
      return
    }
    if (e.key === 'F6') {
      e.preventDefault()
      cycleLandmark(e.shiftKey)
      return
    }
    if (isMod(e) && e.key.toLowerCase() === 'f') {
      e.preventDefault()
      window.dispatchEvent(new Event('mc:focus-search'))
      return
    }
    if (isMod(e) && !e.shiftKey && !e.altKey && /^[1-6]$/.test(e.key)) {
      e.preventDefault()
      const to = SECTION_KEYS[Number(e.key) - 1] as '/search'
      navigate({ to })
      return
    }
    if (isMod(e) && e.key === ',') {
      e.preventDefault()
      navigate({ to: '/settings/$section', params: { section: 'appearance' } })
      return
    }
    if (isMod(e) && e.key === '\\') {
      e.preventDefault()
      const p = usePrefs.getState()
      p.set({ railOpen: !p.railOpen })
      return
    }
    if (isMod(e) && e.key.toLowerCase() === 'i' && !typing) {
      e.preventDefault()
      const p = usePrefs.getState()
      p.set({ inspectorOpen: !p.inspectorOpen })
      return
    }
    if (isMod(e) && e.key === '/') {
      e.preventDefault()
      set({ shortcutsOpen: true })
      return
    }
    if (typing || e.metaKey || e.ctrlKey || e.altKey) return
    if (!usePrefs.getState().singleKeys) return
    if (e.key === '/') {
      e.preventDefault()
      window.dispatchEvent(new Event('mc:focus-search'))
    } else if (e.key === '?') {
      e.preventDefault()
      set({ shortcutsOpen: true })
    }
  })

  const dropShots = async (e: React.DragEvent) => {
    const raw = e.dataTransfer.getData(SHOT_MIME)
    setDropTarget(false)
    if (!raw) return
    e.preventDefault()
    const uids: string[] = JSON.parse(raw)
    const active = usePrefs.getState().activeCollection
    const target = collections.data?.find((c) => c.uid === active) ?? collections.data?.find((c) => c.name === 'Selects') ?? collections.data?.[0]
    if (target) {
      await add.mutateAsync({ uid: target.uid, shot_uids: uids })
      toast({ title: `Added ${uids.length} shot${uids.length === 1 ? '' : 's'} to ${target.name}` })
    } else {
      const c = await create.mutateAsync({ name: 'Selects', shot_uids: uids })
      usePrefs.getState().set({ activeCollection: c.uid })
      toast({ title: `Created Selects with ${uids.length} shot${uids.length === 1 ? '' : 's'}` })
    }
  }

  return (
    <div className={s.shell}>
      <a className={s.skip} href="#main">
        Skip to main content
      </a>
      <header className={s.topbar}>
        <Link to="/search" className={s.brand} aria-label="Metachlorian, go to search">
          <img className={s.mark} src={brandMark} alt="" aria-hidden="true" />
          <span className={s.wordmark}>Metachlorian</span>
        </Link>
        {compactNav ? (
          <nav className={s.nav} aria-label="Sections">
            <MenuTrigger>
              <IconButton icon={MenuIcon} label="Sections" tooltip={false} />
              <MenuPopover placement="bottom start">
                <Menu aria-label="Go to" onAction={(k) => navigate({ to: String(k) as '/search' })}>
                  <MenuItem id="/search" icon={Search}>Search</MenuItem>
                  {NAV.map((n) => (
                    <MenuItem key={n.to} id={n.to} icon={n.icon} shortcut={comboText(`Mod+${n.key}`)}>
                      {n.label}
                    </MenuItem>
                  ))}
                  <MenuSeparator />
                  <MenuItem id="/settings" icon={Settings}>Settings</MenuItem>
                </Menu>
              </MenuPopover>
            </MenuTrigger>
          </nav>
        ) : (
        <nav className={s.nav} aria-label="Sections">
          {NAV.map((n) => (
            <TooltipTrigger key={n.to} delay={500}>
              <Focusable>
                <Link
                  to={n.to}
                  className={s.navLink}
                  aria-label={n.label}
                  data-drop-target={n.to === '/collections' && dropTarget ? 'true' : undefined}
                  onDragOver={n.to === '/collections' ? (e) => { if (e.dataTransfer.types.includes(SHOT_MIME)) { e.preventDefault(); setDropTarget(true) } } : undefined}
                  onDragLeave={n.to === '/collections' ? () => setDropTarget(false) : undefined}
                  onDrop={n.to === '/collections' ? dropShots : undefined}
                >
                  <Ic icon={n.icon} />
                  <span className={s.navLabel}>{n.label}</span>
                </Link>
              </Focusable>
              <Tooltip>
                {n.label}
                <kbd>{comboText(`Mod+${n.key}`)}</kbd>
              </Tooltip>
            </TooltipTrigger>
          ))}
        </nav>
        )}
        <div className={s.searchSlot}>
          <SearchBar />
        </div>
        <div className={s.end}>
          <EgressIndicator />
          <IconButton icon={CircleHelp} label="Keyboard shortcuts" shortcut="?" onPress={() => set({ shortcutsOpen: true })} />
          <Link to="/settings/$section" params={{ section: 'appearance' }} aria-label="Settings" className={s.navLink} style={{ marginBlock: 0, blockSize: 'var(--control-md)' }}>
            <Ic icon={Settings} />
          </Link>
        </div>
      </header>
      <div className={s.body}>
        <Outlet />
      </div>
      <Toaster />
      <CommandMenu />
      <ShortcutsDialog />
      <GlobalDialogs />
    </div>
  )
}

export { SHOT_MIME }
