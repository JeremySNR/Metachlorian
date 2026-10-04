import { useSyncExternalStore } from 'react'

export function useMediaQuery(query: string): boolean {
  return useSyncExternalStore(
    (cb) => {
      const m = window.matchMedia(query)
      m.addEventListener('change', cb)
      return () => m.removeEventListener('change', cb)
    },
    () => window.matchMedia(query).matches,
    () => false,
  )
}

/** Layout tiers from system.md §2.2. */
export type Tier = 'wide' | 'desktop' | 'laptop' | 'tablet' | 'narrow'

export function useTier(): Tier {
  const wide = useMediaQuery('(min-width: 1680px)')
  const desktop = useMediaQuery('(min-width: 1280px)')
  const laptop = useMediaQuery('(min-width: 1024px)')
  const tablet = useMediaQuery('(min-width: 768px)')
  return wide ? 'wide' : desktop ? 'desktop' : laptop ? 'laptop' : tablet ? 'tablet' : 'narrow'
}

export const isOverlayInspector = (t: Tier) => t === 'laptop' || t === 'tablet' || t === 'narrow'
export const isDrawerRail = (t: Tier) => t === 'tablet' || t === 'narrow'
