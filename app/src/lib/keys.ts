/**
 * Keyboard-shortcut labels (system.md §5): one key per <kbd>, written for the platform.
 * Combos are written with "+" and the tokens Mod, Shift and Alt: "Mod+Shift+E".
 * macOS shows glyphs with no separator (⌘⇧E); Windows and Linux show words (Ctrl+Shift+E).
 */
import { isMac } from './bridge'

const MAC: Record<string, string> = { Mod: '⌘', Shift: '⇧', Alt: '⌥', Ctrl: '⌃', Enter: '↩' }
const PC: Record<string, string> = { Mod: 'Ctrl', Shift: 'Shift', Alt: 'Alt', Ctrl: 'Ctrl' }

/** The keys of a combo as they are printed on this platform: "Mod+K" → ["Ctrl", "K"] or ["⌘", "K"]. */
export function keyTokens(combo: string, mac = isMac): string[] {
  const map = mac ? MAC : PC
  return combo.split(/\+(?!$)/).map((k) => map[k] ?? k)
}

/** A combo as one string for compact hints: "⌘⇧E" on macOS, "Ctrl+Shift+E" elsewhere. */
export function comboText(combo: string, mac = isMac): string {
  return keyTokens(combo, mac).join(mac ? '' : '+')
}
