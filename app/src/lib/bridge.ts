/**
 * Capability bridge to the Electron shell (ADR 001; desktop/ preload).
 * In a plain browser `window.metachlorian` is undefined and every shell-only
 * feature degrades: drag-out → copy path / download proxy; open in Cutawan →
 * download the package; choose folder → type a path.
 */

export interface DesktopInfo {
  desktop: boolean
  platform: 'darwin' | 'win32' | 'linux' | string
  mode: 'solo' | 'team'
  baseUrl: string
  version: string
}

export interface MetachlorianBridge {
  desktop: true
  info: () => Promise<DesktopInfo>
  /** Switch between this computer (solo) and a server (team). Relaunches the app. */
  setServer: (mode: 'solo' | 'team', serverUrl?: string) => Promise<{ ok: boolean; error?: string }>
  /** Native drag of real files. Must be called synchronously from dragstart with files already on disk. */
  startDrag: (files: string[], icon?: string) => void
  reveal: (path: string) => void
  openPath: (path: string) => void
  chooseFolder: () => Promise<string | null>
  openInCutawan: (packagePath: string) => Promise<{ ok: boolean; error?: string }>
}

declare global {
  interface Window {
    metachlorian?: MetachlorianBridge
  }
}

export function bridge(): MetachlorianBridge | undefined {
  return typeof window === 'undefined' ? undefined : window.metachlorian
}

export type Capability = 'canDragOut' | 'canRevealInFolder' | 'canChooseFolder' | 'canLaunchCutawan' | 'canSwitchServer'

/** True when the desktop shell provides the feature. */
export function can(cap: Capability): boolean {
  const b = bridge()
  if (!b?.desktop) return false
  switch (cap) {
    case 'canDragOut':
      return typeof b.startDrag === 'function'
    case 'canRevealInFolder':
      return typeof b.reveal === 'function'
    case 'canChooseFolder':
      return typeof b.chooseFolder === 'function'
    case 'canLaunchCutawan':
      return typeof b.openInCutawan === 'function'
    case 'canSwitchServer':
      return typeof b.setServer === 'function'
  }
}

let infoCache: Promise<DesktopInfo | null> | null = null

/** Shell info (platform, solo/team mode, base URL), cached; null in the browser. */
export function desktopInfo(): Promise<DesktopInfo | null> {
  const b = bridge()
  if (!b?.desktop || typeof b.info !== 'function') return Promise.resolve(null)
  infoCache ??= b.info().catch(() => null)
  return infoCache
}

export const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)

/** Platform modifier label for shortcut hints. */
export const MOD = isMac ? '⌘' : 'Ctrl '
