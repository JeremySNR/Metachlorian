import { useNavigate, useRouterState } from '@tanstack/react-router'
import { AddToDialog } from '../collections/AddToDialog'
import { SendDialog } from '../collections/SendDialog'
import { RightsEditor } from '../rights/RightsEditor'
import { ScopeDialog } from '../search/ScopePicker'
import { scopeOf, validateSearch, withScope, type SearchParams } from '../search/searchParams'
import { useUi } from '../../lib/store'

/** Dialogs any surface can open through the UI store. */
export function GlobalDialogs() {
  return (
    <>
      <AddToDialog />
      <SendDialog />
      <RightsEditor />
      <ScopeCommandDialog />
    </>
  )
}

/** Command menu → "Search in folder…" / "Search in collection…": choose, then search there with the words focused. */
function ScopeCommandDialog() {
  const mode = useUi((u) => u.scopeDialog)
  const navigate = useNavigate()
  const location = useRouterState({ select: (st) => st.location })
  const current = validateSearch(location.pathname === '/search' ? (location.search as Record<string, unknown>) : {})
  return (
    <ScopeDialog
      mode={mode}
      value={scopeOf(current)}
      onClose={() => useUi.getState().set({ scopeDialog: null })}
      onChoose={(scope) => {
        navigate({ to: '/search', search: (prev: SearchParams) => withScope(location.pathname === '/search' ? prev : {}, scope) })
        window.setTimeout(() => window.dispatchEvent(new Event('mc:focus-search')), 80)
      }}
    />
  )
}
