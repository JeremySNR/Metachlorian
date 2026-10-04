import { useState } from 'react'
import { Dialog } from '../../components/Dialog'
import { TextField } from '../../components/Field'
import { MOD } from '../../lib/bridge'
import { useUi } from '../../lib/store'
import t from '../../styles/type.module.css'
import s from './AppShell.module.css'

const M = MOD.trim()
export const SHORTCUTS: { surface: string; rows: [string[], string][] }[] = [
  {
    surface: 'Global',
    rows: [
      [[`${M}K`], 'Command menu'],
      [['/', `${M}F`], 'Focus search'],
      [[`${M}1…5`], 'Search · Library · Collections · Ingest · Rights'],
      [[`${M},`], 'Settings'],
      [[`${M}\\`], 'Toggle filter rail'],
      [[`${M}I`], 'Toggle inspector'],
      [['F6', '⇧F6'], 'Next / previous region'],
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
      [[`${M}Enter`], 'Run the search and focus the first result'],
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
      [['⌥←', '⌥→'], 'Step the scrub frame'],
      [['J', 'K', 'L'], 'Shuttle the preview'],
      [['Enter'], 'Open Shot detail'],
      [['X', `${M}Space`], 'Toggle selection'],
      [['⇧X'], 'Toggle selection and move on'],
      [['⇧ + arrows'], 'Extend selection'],
      [[`${M}A`], 'Select all results'],
      [['B'], 'Add to the active collection'],
      [['A'], 'Add to…'],
      [['S'], 'Find similar'],
      [['E'], 'Edit tags'],
      [['R'], 'Rights for the selection'],
      [['V'], 'Cycle view: grid, list, log'],
      [['G'], 'Toggle shots / files grouping'],
      [[`${M}C`], 'Copy shot reference'],
      [['⇧F10'], 'Context menu'],
    ],
  },
  {
    surface: 'Player',
    rows: [
      [['Space'], 'Play / pause'],
      [['⇧Space'], 'Play from in to out'],
      [['J', 'K', 'L'], 'Reverse / stop / forward (repeat for faster)'],
      [['←', '→'], 'Back / forward one frame'],
      [['⇧←', '⇧→'], 'Back / forward one second'],
      [['↑', '↓'], 'Previous / next shot'],
      [['I', 'O'], 'Set in / out'],
      [['⇧I', '⇧O'], 'Go to in / out'],
      [['⌥X'], 'Clear in and out'],
      [['M', 'F'], 'Mute / full screen'],
      [['[', ']'], 'Previous / next result'],
    ],
  },
  {
    surface: 'Timeline and signals',
    rows: [
      [['+', '-'], 'Zoom in / out'],
      [['⇧Z'], 'Fit'],
      [['Enter'], 'Open the shot under the playhead'],
      [['E'], 'Edit a signal'],
      [['Delete'], 'Remove a value'],
    ],
  },
  {
    surface: 'Collections',
    rows: [
      [['⌥↑', '⌥↓'], 'Move the shot earlier / later'],
      [['Delete'], 'Remove from the collection'],
      [[`${M}⇧E`], 'Send to Cutawan'],
    ],
  },
]

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
          const rows = sec.rows.filter(([k, d]) => !f || d.toLowerCase().includes(f) || k.join(' ').toLowerCase().includes(f))
          if (!rows.length) return null
          return (
            <section key={sec.surface}>
              <h3 className={t.slate}>{sec.surface}</h3>
              <table>
                <tbody>
                  {rows.map(([keys, desc]) => (
                    <tr key={desc}>
                      <td>
                        {keys.map((k) => (
                          <kbd key={k}>{k}</kbd>
                        ))}
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
