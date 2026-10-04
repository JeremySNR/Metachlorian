import { useCallback, useId, useMemo, useState } from 'react'
import {
  Button as RacButton, Collection, Dialog as RacDialog, DialogTrigger, Input, ListBox, ListBoxItem, Popover, SearchField, Tree, TreeItem, TreeItemContent, type Key,
} from 'react-aria-components'
import { Check, ChevronDown, ChevronRight, Folder, Layers, Library, Search, X } from 'lucide-react'
import type { CollectionSummary, Folder as FolderT } from '../../api/types'
import { useCollections, useFolders } from '../../api/queries'
import { Button, IconButton } from '../../components/Button'
import { Dialog } from '../../components/Dialog'
import { Ic } from '../../components/Icon'
import { Segmented } from '../../components/Segmented'
import { useDebounced } from '../../hooks/useDebounced'
import { buildFolderTree, formatDateRange, formatHours, type FolderNode } from '../../lib/folders'
import { formatNumber, plural } from '../../lib/format'
import { collectionLabel, EMPTY_SCOPE, folderLabel, hasScope, scopeChipText, type Scope } from '../../lib/scope'
import s from './ScopePicker.module.css'

export type ScopeMode = 'all' | 'folder' | 'collection'

/** Folder and collection names for scope values (uids and paths read as names). */
export function useScopeLabels() {
  const folders = useFolders()
  const collections = useCollections()
  const list = folders.data?.folders
  const cols = collections.data
  const folderName = useCallback((v: string) => folderLabel(v, list ?? []), [list])
  const collectionName = useCallback((v: string) => collectionLabel(v, cols ?? []), [cols])
  return { folderName, collectionName, folders: list ?? [], collections: cols ?? [] }
}

/** "Everything", "In sample", "In collection: Kids on rides", "In 2 folders". */
export function scopeSummary(scope: Scope, folderName: (v: string) => string, collectionName: (v: string) => string): string {
  const n = scope.folder.length + scope.collection.length
  if (!n) return 'Everything'
  if (n > 1) {
    const parts = [scope.folder.length ? plural(scope.folder.length, 'folder') : '', scope.collection.length ? plural(scope.collection.length, 'collection') : ''].filter(Boolean)
    return `In ${parts.join(' and ')}`
  }
  if (scope.folder.length) return `${scopeChipText('folder', '').lead} ${folderName(scope.folder[0])}`
  return `${scopeChipText('collection', '').lead} ${collectionName(scope.collection[0])}`
}

/** One line of folder facts: "7 files · 3–14 Aug 2026 · 8 min". */
export function folderFacts(f: Pick<FolderT, 'files' | 'captured_from' | 'captured_to' | 'hours'>): string {
  return [plural(f.files, 'file'), formatDateRange(f.captured_from, f.captured_to), formatHours(f.hours)].filter(Boolean).join(' · ')
}

/**
 * Choose where search looks: everything, a folder (searchable tree from /api/folders) or a collection.
 * Choosing calls `onChoose` with the new scope (one folder or one collection; Everything = empty).
 */
export function ScopePanel({ value, onChoose, initialMode, autoFocus = true }: { value: Scope; onChoose: (scope: Scope) => void; initialMode?: ScopeMode; autoFocus?: boolean }) {
  const [mode, setMode] = useState<ScopeMode>(initialMode ?? (value.collection.length ? 'collection' : value.folder.length ? 'folder' : 'folder'))
  return (
    <div className={s.panel}>
      <Segmented
        label="Search in"
        value={mode}
        onChange={setMode}
        segments={[
          { id: 'all', label: 'Everything' },
          { id: 'folder', label: 'A folder' },
          { id: 'collection', label: 'A collection' },
        ]}
      />
      {mode === 'all' ? (
        <div className={s.everything}>
          <p>Search every file in the library.</p>
          <Button variant="secondary" icon={Library} onPress={() => onChoose(EMPTY_SCOPE)} autoFocus={autoFocus}>
            Search everything
          </Button>
        </div>
      ) : mode === 'folder' ? (
        <FolderChooser selected={value.folder} onChoose={(path) => onChoose({ folder: [path], collection: [] })} autoFocus={autoFocus} />
      ) : (
        <CollectionChooser selected={value.collection} onChoose={(uid) => onChoose({ folder: [], collection: [uid] })} autoFocus={autoFocus} />
      )}
    </div>
  )
}

function FinderField({ label, value, onChange, autoFocus }: { label: string; value: string; onChange: (v: string) => void; autoFocus?: boolean }) {
  return (
    <SearchField aria-label={label} value={value} onChange={onChange} className={s.find} autoFocus={autoFocus}>
      <Ic icon={Search} size={14} />
      <Input placeholder={label} className={s.findInput} />
      {value && (
        <RacButton className={s.findClear} aria-label="Clear">
          <Ic icon={X} size={14} />
        </RacButton>
      )}
    </SearchField>
  )
}

function FolderChooser({ selected, onChoose, autoFocus }: { selected: string[]; onChoose: (path: string) => void; autoFocus?: boolean }) {
  const [find, setFind] = useState('')
  const q = useDebounced(find.trim(), 150)
  const all = useFolders()
  const found = useFolders(q, { enabled: Boolean(q) })
  const list = q ? found.data?.folders : all.data?.folders
  const tree = useMemo(() => buildFolderTree(list ?? []), [list])
  // Source roots start open, so the first level of folders is visible.
  const [expanded, setExpanded] = useState<Set<Key> | null>(null)
  const expandedKeys = expanded ?? new Set<Key>((all.data?.folders ?? []).filter((f) => f.depth === 0 && f.subfolders > 0).map((f) => f.path))
  const sel = new Set(selected)
  const byPath = useMemo(() => new Map((list ?? []).map((f) => [f.path, f])), [list])
  const loading = (q ? found.isLoading : all.isLoading) && !list
  const total = q ? found.data?.total : all.data?.total

  const renderNode = (n: FolderNode<FolderT>) => (
    <TreeItem key={n.folder.path} id={n.folder.path} textValue={n.folder.name} className={s.treeItem} aria-label={`${n.folder.name}, ${folderFacts(n.folder)}`}>
      <TreeItemContent>
        {({ hasChildItems, isExpanded, level }) => (
          <div className={s.treeRow} style={{ paddingInlineStart: `calc(${level - 1} * var(--space-4))` }}>
            {hasChildItems ? (
              <RacButton slot="chevron" className={s.chev} aria-label={isExpanded ? 'Collapse' : 'Expand'}>
                <Ic icon={isExpanded ? ChevronDown : ChevronRight} size={14} />
              </RacButton>
            ) : (
              <span className={s.chevSpace} />
            )}
            <Ic icon={Folder} size={16} className={s.rowIcon} />
            <span className={s.rowText}>
              <span className={s.rowName}>{n.folder.name}</span>
              <span className={s.rowMeta}>{q && n.folder.depth > 0 ? `${n.folder.relative} · ` : ''}{folderFacts(n.folder)}</span>
            </span>
            {sel.has(n.folder.path) && <Ic icon={Check} size={16} className={s.rowCheck} />}
          </div>
        )}
      </TreeItemContent>
      {n.children.length > 0 && <Collection items={n.children}>{renderNode}</Collection>}
    </TreeItem>
  )

  return (
    <div className={s.chooser}>
      <FinderField label="Find a folder" value={find} onChange={setFind} autoFocus={autoFocus} />
      <Tree
        aria-label="Folders"
        className={s.tree}
        items={q ? (list ?? []).map((folder) => ({ folder, children: [] })) : tree}
        dependencies={[selected, q]}
        expandedKeys={q ? new Set<Key>() : expandedKeys}
        onExpandedChange={(keys) => setExpanded(new Set(keys))}
        onAction={(key) => byPath.get(String(key)) && onChoose(String(key))}
        renderEmptyState={() => <p className={s.empty}>{loading ? 'Loading folders…' : q ? `No folder matches “${q}”.` : 'No folders yet. Add one in Ingest.'}</p>}
      >
        {(n: FolderNode<FolderT>) => renderNode(n)}
      </Tree>
      {total !== undefined && list && total > list.length && <p className={s.more}>{`Showing ${formatNumber(list.length)} of ${formatNumber(total)} folders. Type to find others.`}</p>}
    </div>
  )
}

function CollectionChooser({ selected, onChoose, autoFocus }: { selected: string[]; onChoose: (uid: string) => void; autoFocus?: boolean }) {
  const [find, setFind] = useState('')
  const cols = useCollections()
  const list = (cols.data ?? []).filter((c) => !find.trim() || c.name.toLowerCase().includes(find.trim().toLowerCase()))
  const sel = new Set(selected)
  return (
    <div className={s.chooser}>
      <FinderField label="Find a collection" value={find} onChange={setFind} autoFocus={autoFocus} />
      <ListBox
        aria-label="Collections"
        className={s.tree}
        items={list}
        onAction={(key) => onChoose(String(key))}
        renderEmptyState={() => <p className={s.empty}>{cols.isLoading ? 'Loading collections…' : find.trim() ? `No collection matches “${find.trim()}”.` : 'No collections yet.'}</p>}
      >
        {(c: CollectionSummary) => (
          <ListBoxItem id={c.uid} textValue={c.name} className={s.treeItem} aria-label={`${c.name}, ${plural(c.items, 'shot')}`}>
            <div className={s.treeRow}>
              <Ic icon={Layers} size={16} className={s.rowIcon} />
              <span className={s.rowText}>
                <span className={s.rowName}>{c.name}</span>
                <span className={s.rowMeta}>{plural(c.items, 'shot')}</span>
              </span>
              {(sel.has(c.uid) || [...sel].some((v) => v.toLowerCase() === c.name.toLowerCase())) && <Ic icon={Check} size={16} className={s.rowCheck} />}
            </div>
          </ListBoxItem>
        )}
      </ListBox>
    </div>
  )
}

/** The rail's Scope control (top of the filter rail and the tablet drawer). */
export function ScopeControl({ value, onChange, fromWords = [] }: { value: Scope; onChange: (scope: Scope) => void; fromWords?: string[] }) {
  const { folderName, collectionName } = useScopeLabels()
  const [open, setOpen] = useState(false)
  const scoped = hasScope(value)
  const summary = scopeSummary(value, folderName, collectionName)
  const icon = value.collection.length && !value.folder.length ? Layers : scoped ? Folder : Library
  const id = useId()
  return (
    <div className={s.control} data-testid="scope-control">
      <span className={s.controlLabel} id={`${id}-label`}>
        Scope
      </span>
      <div className={s.controlRow}>
        <DialogTrigger isOpen={open} onOpenChange={setOpen}>
          <RacButton className={`${s.trigger} ${scoped ? s.triggerScoped : ''}`} aria-labelledby={`${id}-label ${id}-value`} data-testid="scope-trigger">
            <Ic icon={icon} size={16} />
            <span id={`${id}-value`} className={s.triggerText} title={[...value.folder, ...value.collection].join(', ') || undefined}>
              {summary}
            </span>
            <Ic icon={ChevronDown} size={14} />
          </RacButton>
          <Popover className={s.popover} placement="bottom start" offset={4}>
            <RacDialog aria-label="Search scope" className={s.dialog}>
              <ScopePanel
                value={value}
                onChoose={(next) => {
                  setOpen(false)
                  onChange(next)
                }}
              />
            </RacDialog>
          </Popover>
        </DialogTrigger>
        {scoped && <IconButton icon={X} label="Search everything" size="sm" onPress={() => onChange(EMPTY_SCOPE)} />}
      </div>
      {fromWords.length > 0 && <p className={s.fromWords}>{`From your words: ${fromWords.join(', ')}. Edit the search text to change it.`}</p>}
    </div>
  )
}

/** Command menu: "Search in folder…" / "Search in collection…". */
export function ScopeDialog({ mode, onClose, onChoose, value }: { mode: 'folder' | 'collection' | null; onClose: () => void; onChoose: (scope: Scope) => void; value: Scope }) {
  return (
    <Dialog isOpen={Boolean(mode)} onOpenChange={(o) => !o && onClose()} title={mode === 'collection' ? 'Search in a collection' : 'Search in a folder'} size="m">
      {mode && (
        <ScopePanel
          key={mode}
          value={value}
          initialMode={mode}
          onChoose={(next) => {
            onClose()
            onChoose(next)
          }}
        />
      )}
    </Dialog>
  )
}

