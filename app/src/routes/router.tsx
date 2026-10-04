import { createRootRoute, createRoute, createRouter, lazyRouteComponent, redirect } from '@tanstack/react-router'
import { AppShell } from '../features/shell/AppShell'
import { SearchPage } from '../features/search/SearchPage'
import { validateSearch } from '../features/search/searchParams'
import { NotFound } from '../features/shell/NotFound'

const rootRoute = createRootRoute({ component: AppShell, notFoundComponent: () => <NotFound /> })

const indexRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/',
  beforeLoad: () => {
    throw redirect({ to: '/search' })
  },
})

export const searchRoute = createRoute({ getParentRoute: () => rootRoute, path: '/search', validateSearch, component: SearchPage })

export const shotRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/shot/$shotId',
  validateSearch: (raw: Record<string, unknown>): { from?: string } => (typeof raw.from === 'string' ? { from: raw.from } : {}),
  component: lazyRouteComponent(() => import('../features/shot/ShotPage'), 'ShotPage'),
})

export const fileRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/file/$assetId',
  validateSearch: (raw: Record<string, unknown>): { t?: number; shot?: string } => ({
    ...(typeof raw.t === 'number' ? { t: raw.t } : {}),
    ...(typeof raw.shot === 'string' ? { shot: raw.shot } : {}),
  }),
  component: lazyRouteComponent(() => import('../features/asset/AssetPage'), 'AssetPage'),
})

const collectionsComponent = lazyRouteComponent(() => import('../features/collections/CollectionsPage'), 'CollectionsPage')
export const collectionsRoute = createRoute({ getParentRoute: () => rootRoute, path: '/collections', component: collectionsComponent })
export const collectionRoute = createRoute({ getParentRoute: () => rootRoute, path: '/collections/$collectionId', component: collectionsComponent })

export const libraryRoute = createRoute({ getParentRoute: () => rootRoute, path: '/library', component: lazyRouteComponent(() => import('../features/library/LibraryPage'), 'LibraryPage') })
export const correctionsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/library/corrections',
  component: lazyRouteComponent(() => import('../features/corrections/CorrectionsPage'), 'CorrectionsPage'),
})

export type RightsTab = 'expiring' | 'restricted' | 'blocked' | 'unknown' | 'cleared' | 'releases' | 'policies'
const RIGHTS_TABS: RightsTab[] = ['expiring', 'restricted', 'blocked', 'unknown', 'cleared', 'releases', 'policies']
export const rightsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/rights',
  validateSearch: (raw: Record<string, unknown>): { tab?: RightsTab; asset?: string } => ({
    ...(RIGHTS_TABS.includes(raw.tab as RightsTab) ? { tab: raw.tab as RightsTab } : {}),
    ...(typeof raw.asset === 'string' ? { asset: raw.asset } : {}),
  }),
  component: lazyRouteComponent(() => import('../features/rights/RightsPage'), 'RightsPage'),
})

const peopleComponent = lazyRouteComponent(() => import('../features/people/PeoplePage'), 'PeoplePage')
export const peopleRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/people',
  validateSearch: (raw: Record<string, unknown>): { q?: string } => (typeof raw.q === 'string' && raw.q.trim() ? { q: raw.q } : {}),
  component: peopleComponent,
})
export const personRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/people/$personId',
  component: lazyRouteComponent(() => import('../features/people/PersonPage'), 'PersonPage'),
})

export const ingestRoute = createRoute({ getParentRoute: () => rootRoute, path: '/ingest', component: lazyRouteComponent(() => import('../features/ingest/IngestPage'), 'IngestPage') })

const settingsIndex = createRoute({
  getParentRoute: () => rootRoute,
  path: '/settings',
  beforeLoad: () => {
    throw redirect({ to: '/settings/$section', params: { section: 'appearance' } })
  },
})
export const settingsRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: '/settings/$section',
  component: lazyRouteComponent(() => import('../features/settings/SettingsPage'), 'SettingsPage'),
})

const routeTree = rootRoute.addChildren([
  indexRoute, searchRoute, shotRoute, fileRoute, collectionsRoute, collectionRoute, libraryRoute, correctionsRoute, rightsRoute, peopleRoute, personRoute, ingestRoute, settingsIndex, settingsRoute,
])

export const router = createRouter({ routeTree, defaultPreload: 'intent', scrollRestoration: false })

declare module '@tanstack/react-router' {
  interface Register {
    router: typeof router
  }
}
