import { useNavigate } from '@tanstack/react-router'
import { CircleAlert } from 'lucide-react'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'

/** Unknown routes get a real "not found" page instead of whatever section happened to match. */
export function NotFound({ what = 'page' }: { what?: string }) {
  const navigate = useNavigate()
  useDocumentTitle('Not found')
  return (
    <main id="main" style={{ flex: 1, minBlockSize: 0, overflow: 'auto' }}>
      <h1 className="visually-hidden">Not found</h1>
      <EmptyState
        icon={CircleAlert}
        title={`There's no ${what} here`}
        actions={
          <>
            <Button variant="secondary" onPress={() => navigate({ to: '/search' })}>
              Go to search
            </Button>
            <Button variant="quiet" onPress={() => navigate({ to: '/library' })}>
              Library overview
            </Button>
          </>
        }
      >
        The address may be mistyped, or the item was removed.
      </EmptyState>
    </main>
  )
}
