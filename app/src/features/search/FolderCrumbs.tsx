import { Link, useRouterState } from '@tanstack/react-router'
import { Folder } from 'lucide-react'
import { useFolders } from '../../api/queries'
import { Ic } from '../../components/Icon'
import { folderCrumbs } from '../../lib/folders'
import type { SearchParams } from './searchParams'
import c from './FolderCrumbs.module.css'

/**
 * A file's folder as a breadcrumb from its watched folder: "sample › day 2". Each part is a link that
 * scopes search to that folder (its absolute path, so the match is exact). On the search page the words
 * and filters are kept; elsewhere it starts a new search of the whole folder.
 */
export function FolderCrumbs({ folder, className }: { folder: string | null | undefined; className?: string }) {
  const folders = useFolders()
  const onSearch = useRouterState({ select: (st) => st.location.pathname === '/search' })
  if (!folder) return null
  const crumbs = folderCrumbs(folder, folders.data?.folders ?? [])
  if (!crumbs.length) return null
  return (
    <nav aria-label="Folder" className={[c.crumbs, className].filter(Boolean).join(' ')} data-testid="folder-crumbs">
      <Ic icon={Folder} size={14} className={c.icon} />
      <ol>
        {crumbs.map((cr, i) => (
          <li key={cr.path}>
            {i > 0 && <span aria-hidden="true" className={c.sep}>›</span>}
            <Link
              to="/search"
              search={(prev: SearchParams) => ({ ...(onSearch ? prev : {}), folder: [cr.path], collection: undefined })}
              className={c.crumb}
              title={`Search in ${cr.path}`}
              aria-label={`${cr.name}: search in this folder`}
            >
              {cr.name}
            </Link>
          </li>
        ))}
      </ol>
    </nav>
  )
}
