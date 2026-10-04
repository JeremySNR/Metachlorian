import { useState } from 'react'
import { Dialog } from '../../components/Dialog'
import { TextField } from '../../components/Field'
import { isMac } from '../../lib/bridge'
import { comboText, keyTokens } from '../../lib/keys'
import { useUi } from '../../lib/store'
import t from '../../styles/type.module.css'
import s from './AppShell.module.css'

/** Combos use lib/keys.ts notation (Mod+K, Shift+F6); each row lists alternatives. */
export const SHORTCUTS: { surface: string; rows: [string[], string][] }[] = [
  {
    surface: 'Global',
    rows: [
      [['Mod+K'], 'Command menu'],
      [['/', 'Mod+F'], 'Focus search'],
      [['Mod+1…5'], 'Search · Library · Collections · Ingest · Rights'],
      [['Mod+,'], 'Settings'],
      [['Mod+\\'], 'Toggle filter rail'],
      [['Mod+I'], 'Toggle inspector'],
      [['F6', 'Shift+F6'], 'Next / previous region'],
      [['?'], 'Keyboard shortcuts'],
      [['Esc'], 'Close the topmost layer, stop preview, clear selection'],
    ],
  },
  {
    surface: 'Search bar',
    rows: [
      [['↓', '↑'], 'Move through suggestions'],
      [['Tab'], 'Accept the suggestion as a chip'],
      [['Enter'], 'Run the search'],
      [['Mod+Enter'], 'Run the search and focus the first result'],
      [['Backspace'], 'At the start: focus the last chip'],
      [['Esc'], 'Close suggestions, clear text, leave the field'],
    ],
  },
  {
    surface: 'Results grid',
    rows: [
      [['←', '→', '↑', '↓'], 'Move focus'],
      [['Home', 'End'], 'Row start / end'],
      [['PageUp', 'PageDown'], 'Page'],
      [['Space'], 'Play or stop the inline preview'],
      [['Alt+←', 'Alt+→'], 'Step the scrub frame'],
      [['J', 'K', 'L'], 'Shuttle the preview'],
      [['Enter'], 'Open Shot detail'],
      [['X', 'Mod+Space'], 'Toggle selection'],
      [['Shift+X'], 'Toggle selection and move on'],
      [['Shift+arrows'], 'Extend selection'],
      [['Mod+A'], 'Select all results'],
      [['B'], 'Add to the active collection'],
      [['A'], 'Add to…'],
      [['S'], 'Find similar'],
      [['E'], 'Edit tags'],
      [['R'], 'Rights for the selection'],
      [['V'], 'Cycle view: grid, list, log'],
      [['G'], 'Toggle shots / files grouping'],
      [['Mod+C'], 'Copy shot reference'],
      [['Shift+F10'], 'Context menu'],
    ],
  },
  {
    surface: 'Player',
    rows: [
      [['Space'], 'Play / pause'],
      [['Shift+Space'], 'Play from in to out'],
      [['J', 'K', 'L'], 'Reverse / stop / forward (repeat for faster)'],
      [['←', '→'], 'Back / forward one frame'],
      [['Shift+←', 'Shift+→'], 'Back / forward one second'],
      [['↑', '↓'], 'Previous / next shot'],
      [['I', 'O'], 'Set in / out'],
      [['Shift+I', 'Shift+O'], 'Go to in / out'],
      [['Alt+X'], 'Clear in and out'],
      [['M', 'F'], 'Mute / full screen'],
      [['[', ']'], 'Previous / next result'],
    ],
  },
  {
    surface: 'Timeline and signals',
    rows: [
      [['+', '-'], 'Zoom in / out'],
      [['Shift+Z'], 'Fit'],
      [['Enter'], 'Open the shot under the playhead'],
      [['E'], 'Edit a signal'],
      [['Delete'], 'Remove a value'],
    ],
  },
  {
    surface: 'Collections',
    rows: [
      [['Alt+↑', 'Alt+↓'], 'Move the shot earlier / later'],
      [['Delete'], 'Remove from the collection'],
      [['Mod+Shift+E'], 'Send to Cutawan'],
    ],
  },
]

/** Alternatives for one action, one <kbd> per key ("Ctrl" "K", or "⌘" "K" on macOS). */
export function Keys({ combos }: { combos: string[] }) {
  return (
    <span className={s.keys} aria-label={combos.map((c) => comboText(c)).join(' or ')}>
      {combos.map((c, i) => (
        <span key={c} className={s.combo} aria-hidden="true">
          {i > 0 && <span className={s.or}>or</span>}
          {keyTokens(c).map((k, j) => (
            <span key={j} className={s.combo}>
              {j > 0 && !isMac && <span className={s.plus}>+</span>}
              <kbd>{k}</kbd>
            </span>
          ))}
        </span>
      ))}
    </span>
  )
}

export function ShortcutsDialog() {
  const open = useUi((u) => u.shortcutsOpen)
  const set = useUi((u) => u.set)
  const [filter, setFilter] = useState('')
  const f = filter.toLowerCase()
  return (
    <Dialog isOpen={open} onOpenChange={(o) => set({ shortcutsOpen: o })} title="Keyboard shortcuts" size="l">
      <TextField aria-label="Filter shortcuts" placeholder="Filter shortcuts" value={filter} onChange={setFilter} className={undefined} />
      <div className={s.shortcuts} style={{ marginBlockStart: 'var(--space-4)' }}>
        {SHORTCUTS.map((sec) => {
          const rows = sec.rows.filter(([k, d]) => !f || d.toLowerCase().includes(f) || k.map((c) => comboText(c)).join(' ').toLowerCase().includes(f))
          if (!rows.length) return null
          return (
            <section key={sec.surface}>
              <h3 className={t.slate}>{sec.surface}</h3>
              <table>
                <tbody>
                  {rows.map(([keys, desc]) => (
                    <tr key={desc}>
                      <td>
                        <Keys combos={keys} />
                      </td>
                      <td>{desc}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          )
        })}
      </div>
    </Dialog>
  )
}
