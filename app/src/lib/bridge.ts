/**
 * Capability bridge to the desktop shell (ADR 001). In the browser
 * `window.metachlorian` is undefined and every shell-only feature degrades:
 * drag-out → copy path / download proxy; launch Cutawan → download package.
 */

export interface ShellCapabilities {
  canDragOut?: boolean
  canStartLocalCore?: boolean
  canBrowseMdns?: boolean
  canLaunchCutawan?: boolean
  canRevealInFolder?: boolean
}

export interface MetachlorianBridge {
  capabilities: ShellCapabilities
  /** Core URL when the shell started or connected to one (e.g. http://127.0.0.1:53817). */
  coreUrl?: string
  platform?: 'darwin' | 'win32' | 'linux'
  startDrag?: (paths: string[]) => void
  revealInFolder?: (path: string) => void
  launchCutawan?: (packageDir: string) => Promise<void>
  setNativeTheme?: (theme: 'system' | 'light' | 'dark') => void
}

declare global {
  interface Window {
    metachlorian?: MetachlorianBridge
  }
}

export function bridge(): MetachlorianBridge | undefined {
  return typeof window === 'undefined' ? undefined : window.metachlorian
}

export function can(cap: keyof ShellCapabilities): boolean {
  return Boolean(bridge()?.capabilities?.[cap])
}

export const isMac = typeof navigator !== 'undefined' && /Mac|iPhone|iPad/.test(navigator.platform || navigator.userAgent)

/** Platform modifier label for shortcut hints. */
export const MOD = isMac ? '⌘' : 'Ctrl '
