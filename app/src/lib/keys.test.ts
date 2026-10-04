import { describe, expect, it } from 'vitest'
import { comboText, keyTokens } from './keys'

describe('shortcut labels', () => {
  it('splits a combo into one key each', () => {
    expect(keyTokens('Mod+K', false)).toEqual(['Ctrl', 'K'])
    expect(keyTokens('Mod+K', true)).toEqual(['⌘', 'K'])
    expect(keyTokens('Shift+F6', false)).toEqual(['Shift', 'F6'])
    expect(keyTokens('Alt+←', true)).toEqual(['⌥', '←'])
    expect(keyTokens('+', false)).toEqual(['+'])
    expect(keyTokens('?', false)).toEqual(['?'])
  })
  it('never mixes Mac glyphs with PC words', () => {
    expect(comboText('Mod+Shift+E', false)).toBe('Ctrl+Shift+E')
    expect(comboText('Mod+Shift+E', true)).toBe('⌘⇧E')
    expect(comboText('Mod+\\', false)).toBe('Ctrl+\\')
  })
})
