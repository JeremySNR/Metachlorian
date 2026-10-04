import { ChevronDown, Download, Layers, Plus, ScanSearch, Send, ShieldCheck } from 'lucide-react'
import { Button } from '../../components/Button'
import { Menu, MenuItem, MenuPopover, MenuTrigger } from '../../components/Menu'
import { MOD } from '../../lib/bridge'
import { comboText } from '../../lib/keys'
import { formatNumber } from '../../lib/format'
import { useUi } from '../../lib/store'
import s from './SelectionBar.module.css'

interface Props {
  total: number
  loaded: number
  selectingAll?: boolean
  activeName: string
  onSelectAll: () => void
  onAddToActive: () => void
  onAddTo: () => void
  onSimilar: () => void
  onRights: () => void
  onExport: (format: 'otio' | 'fcpxml' | 'edl') => void
  onSend: () => void
}

/** Selection bar (system.md §3.14): appears with ≥ 1 selected shot. */
export function SelectionBar(p: Props) {
  const selection = useUi((u) => u.selection)
  const clear = useUi((u) => u.clearSelection)
  const n = selection.size
  if (!n) return null
  return (
    <div className={s.bar} role="region" aria-label="Selection" data-testid="selection-bar">
      <span className={s.count} aria-live="polite">
        <b>{formatNumber(n)}</b> selected
      </span>
      {p.total > n && (
        <Button variant="quiet" size="sm" onPress={p.onSelectAll} busy={p.selectingAll} className={s.hideNarrow} data-testid="select-all">
          {`Select all ${formatNumber(p.total)}`}
        </Button>
      )}
      <Button variant="quiet" size="sm" shortcut="Esc" onPress={clear}>
        Clear
      </Button>
      <span className={s.spacer} />
      <div className={s.actions}>
        <Button variant="secondary" icon={Plus} shortcut="B" onPress={p.onAddToActive}>
          {`Add to ${p.activeName}`}
        </Button>
        <Button variant="secondary" icon={Layers} shortcut="A" onPress={p.onAddTo} className={s.hideNarrow}>
          Add to…
        </Button>
        <Button variant="secondary" icon={ScanSearch} shortcut="S" onPress={p.onSimilar}>
          Find similar
        </Button>
        <Button variant="secondary" icon={ShieldCheck} shortcut="R" onPress={p.onRights} className={s.hideNarrow}>
          Rights…
        </Button>
        <MenuTrigger>
          <Button variant="secondary" icon={Download} iconEnd={ChevronDown} shortcut={`${MOD}E`}>
            Export
          </Button>
          <MenuPopover placement="top end">
            <Menu aria-label="Export timeline" onAction={(k) => p.onExport(k as 'otio' | 'fcpxml' | 'edl')}>
              <MenuItem id="otio">OpenTimelineIO (.otio)</MenuItem>
              <MenuItem id="fcpxml">FCPXML 1.10</MenuItem>
              <MenuItem id="edl">CMX 3600 EDL</MenuItem>
            </Menu>
          </MenuPopover>
        </MenuTrigger>
        <Button variant="primary" icon={Send} shortcut={comboText('Mod+Shift+E')} onPress={p.onSend}>
          Send to Cutawan
        </Button>
      </div>
    </div>
  )
}
