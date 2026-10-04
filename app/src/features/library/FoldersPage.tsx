import { useMemo, useState } from 'react'
import { Link, useNavigate, useSearch } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { Button as RacButton } from 'react-aria-components'
import { ChevronDown, ChevronRight, Folder, FolderSearch, ListVideo } from 'lucide-react'
import type { Folder as FolderT } from '../../api/types'
import { folderAssetsQuery, useFolders, useVocabularies } from '../../api/queries'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { TextField } from '../../components/Field'
import { Ic } from '../../components/Icon'
import { RightsBadge } from '../../components/RightsBadge'
import { useDebounced } from '../../hooks/useDebounced'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { buildFolderTree, editStageCounts, formatDateRange, formatHours, type FolderNode } from '../../lib/folders'
import { formatDate, formatNumber, plural } from '../../lib/format'
import { stateFromBadge } from '../../lib/rights'
import { formatLength } from '../../lib/timecode'
import { LibraryTabs } from './LibraryPage'
import l from './Library.module.css'
import s from './Folders.module.css'

/** Ancestors of a path that are listed folders, so a deep-linked folder is visible. */
function ancestorsOf(path: string, folders: readonly FolderT[]): string[] {
  return folders.filter((f) => path !== f.path && path.startsWith(`${f.path}/`)).map((f) => f.path)
}

/** Open search scoped to a folder, with the search box focused for the words. */
export function searchFolder(navigate: ReturnType<typeof useNavigate>, path: string) {
  navigate({ to: '/search', search: { folder: [path] } })
  window.setTimeout(() => window.dispatchEvent(new Event('mc:focus-search')), 60)
}

/**
 * Library → Folders: every folder that holds footage (from the watched folders), with files, length,
 * shoot dates and edit stages; search inside one, or list its files (system.md §9.5, folder scope).
 */
export function FoldersPage() {
  useDocumentTitle('Folders', 'Library')
  const params = useSearch({ from: '/library/folders' })
  const navigate = useNavigate({ from: '/library/folders' })
  const [find, setFind] = useState(params.q ?? '')
  const q = useDebounced(find.trim(), 200)
  const all = useFolders()
  const found = useFolders(q, { enabled: Boolean(q) })
  const list = useMemo(() => (q ? found.data?.folders : all.data?.folders) ?? [], [q, found.data, all.data])
  const tree = useMemo(() => buildFolderTree(list), [list])
  const [expanded, setExpanded] = useState<Set<string> | null>(null)
  const open = params.open ?? null
  const defaultExpanded = useMemo(
    () => new Set([...list.filter((f) => f.depth === 0).map((f) => f.path), ...(open ? ancestorsOf(open, list) : [])]),
    [list, open],
  )
  const exp = q ? new Set(list.map((f) => f.path)) : (expanded ?? defaultExpanded)
  const toggle = (path: string) => {
    const next = new Set(exp)
    if (next.has(path)) next.delete(path)
    else next.add(path)
    setExpanded(next)
  }
  const setOpen = (path: string | null) => navigate({ search: (prev) => ({ ...prev, open: path ?? undefined }), replace: true })
  const total = q ? found.data?.total : all.data?.total
  const error = (q ? found : all).error

  return (
    <main id="main" className={l.page} aria-busy={all.isLoading || undefined}>
      <div className={l.inner}>
        <div className={l.titleRow}>
          <h1>Library</h1>
          <LibraryTabs />
        </div>
        <section className={l.section} aria-labelledby="folders-h">
          <div className={l.sectionHead}>
            <h2 id="folders-h">Folders</h2>
          </div>
          <p className={s.intro}>
            Every folder that holds footage, from the folders you watch. Counts include subfolders. Search inside one to keep words, filters and similar shots to that folder. Agents can do the same with <code>list_folders</code> and <code>search_shots(folder=…)</code>.
          </p>
          <div className={s.toolbar}>
            <TextField
              aria-label="Find a folder"
              placeholder="Find a folder by name or path"
              value={find}
              onChange={(v) => {
                setFind(v)
                navigate({ search: (prev) => ({ ...prev, q: v.trim() || undefined }), replace: true })
              }}
              className={s.find}
            />
            <span className={s.count} role="status">
              {total === undefined ? '' : q ? `${plural(total, 'folder')} match “${q}”` : plural(total, 'folder')}
            </span>
          </div>
          {error ? (
            <EmptyState title="Couldn't load the folders" role="alert">
              {(error as Error).message}
            </EmptyState>
          ) : !list.length && !all.isLoading ? (
            <EmptyState icon={Folder} title={q ? `No folder matches “${q}”` : 'No folders yet'} actions={q ? undefined : <Button onPress={() => navigate({ to: '/ingest' })}>Add a folder</Button>}>
              {q ? 'Try part of the name, or a parent folder.' : 'Add a folder in Ingest; its folders appear here as files are found.'}
            </EmptyState>
          ) : (
            <FolderList nodes={tree} expanded={exp} onToggle={toggle} open={open} onOpen={setOpen} flat={Boolean(q)} level={1} />
          )}
        </section>
      </div>
    </main>
  )
}

function FolderList({ nodes, expanded, onToggle, open, onOpen, flat, level }: { nodes: FolderNode<FolderT>[]; expanded: Set<string>; onToggle: (p: string) => void; open: string | null; onOpen: (p: string | null) => void; flat: boolean; level: number }) {
  return (
    <ul className={level > 1 ? `${s.list} ${s.nested}` : s.list} data-testid={level === 1 ? 'folder-list' : undefined}>
      {nodes.map((n) => (
        <li key={n.folder.path}>
          <FolderRow folder={n.folder} hasChildren={!flat && n.children.length > 0} expanded={expanded.has(n.folder.path)} onToggle={() => onToggle(n.folder.path)} open={open === n.folder.path} onOpen={(o) => onOpen(o ? n.folder.path : null)} flat={flat} />
          {!flat && n.children.length > 0 && expanded.has(n.folder.path) && <FolderList nodes={n.children} expanded={expanded} onToggle={onToggle} open={open} onOpen={onOpen} flat={flat} level={level + 1} />}
        </li>
      ))}
    </ul>
  )
}

function FolderRow({ folder: f, hasChildren, expanded, onToggle, open, onOpen, flat }: { folder: FolderT; hasChildren: boolean; expanded: boolean; onToggle: () => void; open: boolean; onOpen: (open: boolean) => void; flat: boolean }) {
  const navigate = useNavigate()
  const { label } = useVocabularies()
  // The file list loads only when the folder is opened; the edit-stage summary comes with the folder.
  const files = useQuery({ ...folderAssetsQuery(f.path), enabled: open })
  const stages = f.edit_types
    ? Object.entries(f.edit_types).map(([term, count]) => ({ term: term === 'unclassified' ? null : term, count }))
    : files.data
      ? editStageCounts(files.data.assets)
      : []
  const id = `files-${f.path.replace(/[^a-z0-9]+/gi, '-')}`
  const dates = formatDateRange(f.captured_from, f.captured_to)
  return (
    <div className={`${s.row} ${open ? s.rowOpen : ''}`} data-testid="folder-row" data-path={f.path}>
      <div className={s.name}>
        {hasChildren ? (
          <RacButton className={s.chev} onPress={onToggle} aria-expanded={expanded} aria-label={`${expanded ? 'Hide' : 'Show'} folders in ${f.name}`}>
            <Ic icon={expanded ? ChevronDown : ChevronRight} size={14} />
          </RacButton>
        ) : (
          <span className={s.chevSpace} />
        )}
        <Ic icon={Folder} size={16} className={s.icon} />
        <div className={s.nameText}>
          <h3>{f.name}</h3>
          <span className={s.path} title={f.path}>
            {flat || f.depth > 0 ? f.relative : f.path}
          </span>
        </div>
      </div>
      <dl className={s.facts}>
        <div>
          <dt>Files</dt>
          <dd>{formatNumber(f.files)}</dd>
        </div>
        <div>
          <dt>Shots</dt>
          <dd>{formatNumber(f.shots)}</dd>
        </div>
        <div>
          <dt>Length</dt>
          <dd>{formatHours(f.hours)}</dd>
        </div>
        <div>
          <dt>Shot</dt>
          <dd>{dates || 'Date unknown'}</dd>
        </div>
        <div>
          <dt>Edit stage</dt>
          <dd data-testid="folder-stages">
            {!f.edit_types && files.isLoading
              ? '…'
              : stages.length
                ? stages.map((x) => `${x.term ? label('edit_type', x.term) : 'Not classified'} ${formatNumber(x.count)}`).join(' · ')
                : '—'}
            {!f.edit_types && files.data && files.data.total > files.data.assets.length ? ` (first ${formatNumber(files.data.assets.length)} files)` : ''}
          </dd>
        </div>
      </dl>
      <div className={s.actions}>
        <Button variant="secondary" size="sm" icon={FolderSearch} onPress={() => searchFolder(navigate, f.path)} aria-label={`Search this folder: ${f.name}`}>
          Search this folder
        </Button>
        <Button variant="quiet" size="sm" icon={open ? ChevronDown : ListVideo} onPress={() => onOpen(!open)} aria-expanded={open} aria-controls={open ? id : undefined} aria-label={`${open ? 'Hide' : 'Show'} files in ${f.name}`}>
          {open ? 'Hide files' : 'Show files'}
        </Button>
      </div>
      {open && (
        <div id={id} className={s.files} role="region" aria-label={`Files in ${f.name}`} data-testid="folder-files">
          {files.isLoading ? (
            <p className={s.muted}>Loading files…</p>
          ) : files.isError ? (
            <p className={s.muted} role="alert">{`Couldn't load the files: ${(files.error as Error).message}`}</p>
          ) : (
            <>
              <table className={l.table}>
                <thead>
                  <tr>
                    <th>File</th>
                    <th className={s.hideNarrow}>Shot</th>
                    <th className={l.num}>Length</th>
                    <th className={s.hideNarrow}>Edit stage</th>
                    <th>Rights</th>
                  </tr>
                </thead>
                <tbody>
                  {(files.data?.assets ?? []).map((a) => (
                    <tr key={a.uid}>
                      <td className={s.fileCell}>
                        <Link to="/file/$assetId" params={{ assetId: a.uid }} title={a.path}>
                          {a.filename}
                        </Link>
                        {f.path !== a.path.slice(0, a.path.lastIndexOf('/')) && <span className={s.sub}>{a.path.slice(f.path.length + 1, a.path.lastIndexOf('/'))}</span>}
                      </td>
                      <td className={s.hideNarrow}>{a.captured ? formatDate(a.captured) : '—'}</td>
                      <td className={l.num}>{formatLength(a.duration)}</td>
                      <td className={s.hideNarrow}>{a.edit_type ? label('edit_type', typeof a.edit_type === 'string' ? a.edit_type : a.edit_type.term) : 'Not classified'}</td>
                      <td>
                        <RightsBadge state={stateFromBadge(a.rights_badge)} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {files.data && files.data.total > files.data.assets.length && <p className={s.muted}>{`Showing the first ${formatNumber(files.data.assets.length)} of ${plural(files.data.total, 'file')}.`}</p>}
            </>
          )}
        </div>
      )}
    </div>
  )
}
