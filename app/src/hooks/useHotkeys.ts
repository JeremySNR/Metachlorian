import { useEffect } from 'react'
import { usePrefs } from '../lib/store'
import { useLatest } from './useDebounced'

/** True when focus is in a text-entry control (single-key shortcuts never fire there, WCAG 2.1.4). */
export function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null
  if (!el) return false
  const tag = el.tagName
  if (tag === 'TEXTAREA' || el.isContentEditable) return true
  if (tag === 'INPUT') {
    const type = (el as HTMLInputElement).type
    return !['checkbox', 'radio', 'button', 'range', 'submit'].includes(type)
  }
  return el.getAttribute('role') === 'combobox' || el.getAttribute('role') === 'searchbox'
}

export const isMod = (e: KeyboardEvent | React.KeyboardEvent) => e.metaKey || e.ctrlKey

/** Single-key shortcuts are on unless switched off in Settings → Keyboard. */
export function singleKeysOn(): boolean {
  return usePrefs.getState().singleKeys
}

/** Document-level key handler, kept current without re-binding. */
export function useDocumentKeys(handler: (e: KeyboardEvent) => void, enabled = true) {
  const ref = useLatest(handler)
  useEffect(() => {
    if (!enabled) return
    const h = (e: KeyboardEvent) => ref.current(e)
    document.addEventListener('keydown', h)
    return () => document.removeEventListener('keydown', h)
  }, [enabled, ref])
}
