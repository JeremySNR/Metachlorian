import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from '@tanstack/react-router'
import { GridList, GridListItem, useDragAndDrop, type Key } from 'react-aria-components'
import { ArrowDown, ArrowUp, Download, Ellipsis, Film, GripVertical, Layers, PenLine, Plus, Scissors, Search, Send, Trash2 } from 'lucide-react'
import type { Collection, CollectionItem } from '../../api/types'
import { ApiError, mediaUrl } from '../../api/client'
import {
  useAddToCollection, useCollection, useCollections, useCreateCollection, useDeleteCollection, useRemoveItem, useReorderCollection,
  useRightsCheck, useUpdateCollection, useUpdateItem, verdictCounts,
} from '../../api/queries'
import { Button, IconButton } from '../../components/Button'
import { Dialog } from '../../components/Dialog'
import { EmptyState } from '../../components/EmptyState'
import { TextField } from '../../components/Field'
import { Ic } from '../../components/Icon'
import { Menu, MenuItem, MenuPopover, MenuSeparator, MenuTrigger } from '../../components/Menu'
import { RightsBadge } from '../../components/RightsBadge'
import { toast } from '../../components/Toast'
import { MOD } from '../../lib/bridge'
import { comboText } from '../../lib/keys'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { formatDateTime, plural } from '../../lib/format'
import { stateFromBadge } from '../../lib/rights'
import { usePrefs, useUi } from '../../lib/store'
import { formatDuration, formatLength, formatTimecode, parseTimecode } from '../../lib/timecode'
import { isMod, isTyping, useDocumentKeys } from '../../hooks/useHotkeys'
import { SHOT_MIME } from '../search/ShotCard'
import t from '../../styles/type.module.css'
import s from './Collections.module.css'

/** Collections and selects (system.md §9.4): a static, ordered set of shots with handoff. */
export function CollectionsPage() {
  const params = useParams({ strict: false }) as { collectionId?: string }
  const navigate = useNavigate()
  const cols = useCollections()
  const active = usePrefs((p) => p.activeCollection)
  const uid = params.collectionId ?? cols.data?.[0]?.uid ?? null
  const col = useCollection(uid)
  const create = useCreateCollection()
  const add = useAddToCollection()
  const [name, setName] = useState('')
  const [dropOn, setDropOn] = useState<string | null>(null)
  useDocumentTitle(col.data?.name, 'Collections')

  const makeCollection = async () => {
    if (!name.trim()) return
    const c = await create.mutateAsync({ name: name.trim() })
    setName('')
    usePrefs.getState().set({ activeCollection: c.uid })
    navigate({ to: '/collections/$collectionId', params: { collectionId: c.uid } })
  }

  const dropShots = async (e: React.DragEvent, target: string, label: string) => {
    const raw = e.dataTransfer.getData(SHOT_MIME)
    setDropOn(null)
    if (!raw) return
    e.preventDefault()
    const uids: string[] = JSON.parse(raw)
    await add.mutateAsync({ uid: target, shot_uids: uids })
    toast({ title: `Added ${plural(uids.length, 'shot')} to ${label}` })
  }

  return (
    <div className={s.page}>
      <nav className={s.side} aria-label="Collections">
        <div className={s.sideHead}>
          <h2 className={t.slate}>Collections</h2>
        </div>
        <div className={s.list} role="list">
          {(cols.data ?? []).map((c) => (
            <Link
              key={c.uid}
              to="/collections/$collectionId"
              params={{ collectionId: c.uid }}
              role="listitem"
              className={s.colItem}
              data-status={c.uid === uid ? 'active' : undefined}
              data-drop={dropOn === c.uid || undefined}
              onDragOver={(e) => {
                if (e.dataTransfer.types.includes(SHOT_MIME)) {
                  e.preventDefault()
                  setDropOn(c.uid)
                }
              }}
              onDragLeave={() => setDropOn(null)}
              onDrop={(e) => dropShots(e, c.uid, c.name)}
            >
              <Ic icon={Layers} />
              <span className={s.colName}>{c.name}</span>
              <span className={s.colCount}>{c.uid === active ? <span className={s.activeMark}>B · </span> : null}{c.items}</span>
            </Link>
          ))}
          {cols.data && !cols.data.length && <p style={{ padding: 'var(--space-3)', color: 'var(--fg-2)' }}>No collections yet.</p>}
        </div>
        <form
          className={s.newForm}
          onSubmit={(e) => {
            e.preventDefault()
            makeCollection()
          }}
        >
          <TextField aria-label="New collection name" placeholder="New collection" value={name} onChange={setName} />
          <IconButton icon={Plus} label="Create collection" type="submit" variant="secondary" isDisabled={!name.trim()} />
        </form>
      </nav>
      {col.data ? (
        <CollectionView key={col.data.uid} col={col.data} />
      ) : col.isError ? (
        <main id="main" className={s.main}>
          <h1 className="visually-hidden">Collections</h1>
          <EmptyState title="There's no collection here" role="alert" actions={<Button onPress={() => navigate({ to: '/collections' })}>All collections</Button>}>
            It may have been deleted, or the link is mistyped.
          </EmptyState>
        </main>
      ) : cols.data && !cols.data.length ? (
        <main id="main" className={s.main}>
          <h1 className="visually-hidden">Collections</h1>
          <EmptyState icon={Layers} title="No collections yet" actions={<Button variant="primary" onPress={() => navigate({ to: '/search' })}>Find shots</Button>}>
            Select shots in search and press <strong>B</strong> to start Selects, or create a collection on the left.
          </EmptyState>
        </main>
      ) : (
        <main id="main" className={s.main} aria-busy="true">
          <h1 className="visually-hidden">Collections</h1>
        </main>
      )}
    </div>
  )
}

function CollectionView({ col }: { col: Collection }) {
  const navigate = useNavigate()
  const update = useUpdateCollection()
  const reorder = useReorderCollection()
  const remove = useRemoveItem()
  const del = useDeleteCollection()
  const add = useAddToCollection()
  const updateItem = useUpdateItem()
  const [editingName, setEditingName] = useState(false)
  const [nameDraft, setNameDraft] = useState(col.name)
  const [brief, setBrief] = useState(col.brief || col.description)
  const [trim, setTrim] = useState<CollectionItem | null>(null)
  const [noteItem, setNoteItem] = useState<CollectionItem | null>(null)
  const [selected, setSelected] = useState<Set<Key>>(new Set())
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [drop, setDrop] = useState(false)
  const items = col.items
  const isActive = usePrefs((p) => p.activeCollection) === col.uid
  const check = useRightsCheck(items.length ? { shot_uids: items.map((i) => i.shot.uid) } : null)
  const counts = verdictCounts(check.data)
  const total = items.reduce((sum, i) => sum + ((i.out ?? i.shot.end) - (i.in ?? i.shot.start)), 0)

  const order = (ids: number[]) => reorder.mutate({ uid: col.uid, order: ids })
  const move = (itemId: number, delta: number) => {
    const ids = items.map((i) => i.item_id)
    const i = ids.indexOf(itemId)
    const j = i + delta
    if (i < 0 || j < 0 || j >= ids.length) return
    ;[ids[i], ids[j]] = [ids[j], ids[i]]
    order(ids)
  }

  const removeItem = async (it: CollectionItem) => {
    const before = items.map((i) => i.item_id)
    await remove.mutateAsync({ uid: col.uid, itemId: it.item_id })
    toast({
      title: `Removed from ${col.name}`,
      action: {
        label: 'Undo',
        onAction: async () => {
          const res = await add.mutateAsync({ uid: col.uid, shot_uids: [it.shot.uid], in: it.in, out: it.out, note: it.note })
          const added = res.items[res.items.length - 1]
          order(before.map((id) => (id === it.item_id ? added.item_id : id)))
        },
      },
    })
  }

  const { dragAndDropHooks } = useDragAndDrop({
    getItems: (keys) => [...keys].map((k) => ({ 'text/plain': String(k) })),
    onReorder(e) {
      const ids = items.map((i) => i.item_id)
      const moving = [...e.keys].map(Number)
      const rest = ids.filter((id) => !moving.includes(id))
      const target = Number(e.target.key)
      let at = rest.indexOf(target)
      if (e.target.dropPosition === 'after') at += 1
      rest.splice(at, 0, ...moving)
      order(rest)
    },
  })

  useDocumentKeys((e) => {
    if (isTyping(e.target) || document.querySelector('[role="dialog"]')) return
    if (isMod(e) && e.shiftKey && e.key.toLowerCase() === 'e' && items.length) {
      e.preventDefault()
      useUi.getState().set({ sendDialog: { kind: 'collection', uid: col.uid, consumer: 'cutawan' } })
    } else if (isMod(e) && !e.shiftKey && e.key.toLowerCase() === 'e' && items.length) {
      e.preventDefault()
      useUi.getState().set({ sendDialog: { kind: 'collection', uid: col.uid, consumer: 'nle' } })
    }
  })

  const saveName = () => {
    setEditingName(false)
    if (nameDraft.trim() && nameDraft !== col.name) update.mutate({ uid: col.uid, name: nameDraft.trim() })
  }

  const byId = useMemo(() => new Map(items.map((i) => [i.item_id, i])), [items])

  return (
    <main
      id="main"
      className={s.main}
      data-drop={drop || undefined}
      onDragOver={(e) => {
        if (e.dataTransfer.types.includes(SHOT_MIME)) {
          e.preventDefault()
          setDrop(true)
        }
      }}
      onDragLeave={(e) => e.currentTarget === e.target && setDrop(false)}
      onDrop={async (e) => {
        const raw = e.dataTransfer.getData(SHOT_MIME)
        setDrop(false)
        if (!raw) return
        e.preventDefault()
        const uids: string[] = JSON.parse(raw)
        await add.mutateAsync({ uid: col.uid, shot_uids: uids })
        toast({ title: `Added ${plural(uids.length, 'shot')} to ${col.name}` })
      }}
    >
      <div className={s.head}>
        <div className={s.titleRow}>
          <h1>
            {editingName ? (
              <input
                className={s.titleInput}
                aria-label="Collection name"
                value={nameDraft}
                autoFocus
                onChange={(e) => setNameDraft(e.target.value)}
                onBlur={saveName}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') saveName()
                  if (e.key === 'Escape') {
                    setNameDraft(col.name)
                    setEditingName(false)
                  }
                }}
              />
            ) : (
              <button type="button" className={s.titleButton} onClick={() => setEditingName(true)} aria-label={`${col.name}. Rename`}>
                {col.name}
              </button>
            )}
          </h1>
          {!isActive && (
            <Button variant="quiet" size="sm" onPress={() => usePrefs.getState().set({ activeCollection: col.uid })}>
              Make active (B adds here)
            </Button>
          )}
          <Button
            variant="secondary"
            icon={Search}
            isDisabled={!items.length}
            data-testid="search-in-collection"
            onPress={() => {
              navigate({ to: '/search', search: { collection: [col.uid] } })
              window.setTimeout(() => window.dispatchEvent(new Event('mc:focus-search')), 60)
            }}
          >
            Search in this collection
          </Button>
          <Button variant="secondary" icon={Download} shortcut={`${MOD}E`} isDisabled={!items.length} onPress={() => useUi.getState().set({ sendDialog: { kind: 'collection', uid: col.uid, consumer: 'nle' } })} data-testid="export-timeline">
            Export timeline
          </Button>
          <Button variant="primary" icon={Send} shortcut={comboText('Mod+Shift+E')} isDisabled={!items.length} onPress={() => useUi.getState().set({ sendDialog: { kind: 'collection', uid: col.uid, consumer: 'cutawan' } })} data-testid="send-to-cutawan">
            Send to Cutawan
          </Button>
          <MenuTrigger>
            <IconButton icon={Ellipsis} label="More collection actions" />
            <MenuPopover placement="bottom end">
              <Menu aria-label="Collection actions">
                <MenuItem icon={PenLine} onAction={() => setEditingName(true)}>Rename</MenuItem>
                <MenuSeparator />
                <MenuItem icon={Trash2} danger onAction={() => setConfirmDelete(true)}>Delete collection…</MenuItem>
              </Menu>
            </MenuPopover>
          </MenuTrigger>
        </div>
        <div className={s.facts}>
          <span>
            <strong>{plural(items.length, 'shot')}</strong> · {formatLength(total)}
          </span>
          {items.length > 0 && (
            <span data-testid="collection-rights">
              {counts.allowed} cleared · {counts.restricted} restricted · {counts.blocked} blocked · {counts.unknown} unknown
            </span>
          )}
          <span>Updated {formatDateTime(col.updated_at)}</span>
        </div>
        <div className={s.brief}>
          <TextField
            aria-label="Brief or note"
            placeholder="Add a brief: what this is for, the story, the audience"
            value={brief}
            onChange={setBrief}
            multiline
            onBlur={() => brief !== (col.brief || col.description) && update.mutate({ uid: col.uid, brief })}
          />
        </div>
      </div>
      {items.length ? (
        <div
          onKeyDownCapture={(e) => {
            const key = (document.activeElement as HTMLElement | null)?.closest('[data-key]')?.getAttribute('data-key')
            const it = key ? byId.get(Number(key)) : undefined
            if (!it) return
            if (e.altKey && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
              e.preventDefault()
              e.stopPropagation()
              move(it.item_id, e.key === 'ArrowUp' ? -1 : 1)
            } else if (e.key === 'Delete' || e.key === 'Backspace') {
              e.preventDefault()
              removeItem(it)
            }
          }}
        >
        <GridList
          aria-label={`Shots in ${col.name}`}
          className={s.items}
          items={items}
          dragAndDropHooks={dragAndDropHooks}
          selectionMode="multiple"
          selectionBehavior="replace"
          selectedKeys={selected}
          onSelectionChange={(k) => setSelected(k === 'all' ? new Set(items.map((i) => i.item_id)) : k)}
          onAction={(key) => navigate({ to: '/shot/$shotId', params: { shotId: byId.get(Number(key))?.shot.uid ?? '' } })}
          data-testid="collection-items"
        >
          {(it) => {
            const sh = it.shot
            const inS = it.in ?? sh.start
            const outS = it.out ?? sh.end
            const trimmed = it.in !== null || it.out !== null
            const pos = items.indexOf(it)
            return (
              <GridListItem id={it.item_id} textValue={`${pos + 1}. ${sh.caption ?? sh.filename}`} className={s.item}>
                <button slot="drag" className={s.handle} aria-label="Drag to reorder">
                  <Ic icon={GripVertical} />
                </button>
                <span className={s.pos}>{pos + 1}</span>
                {sh.thumb ? <img className={s.thumb} src={mediaUrl(sh.thumb)} alt="" loading="lazy" /> : <span className={s.thumb} />}
                <span className={s.itemText}>
                  <span className={s.itemTitle}>{sh.caption || `${sh.filename} · shot ${sh.idx + 1}`}</span>
                  <span className={s.itemMeta}>
                    <span className={trimmed ? s.trimmed : undefined}>
                      {formatTimecode(inS, sh.fps)} → {formatTimecode(outS, sh.fps)}
                    </span>
                    <span>{formatDuration(outS - inS)}</span>
                    {trimmed && <span>trimmed</span>}
                    <span className={s.hideSmall}>{sh.filename}</span>
                  </span>
                  {it.note && <span className={s.note}>{it.note}</span>}
                </span>
                <RightsBadge state={stateFromBadge(it.rights_badge)} />
                <span className={s.hideSmall} />
                <MenuTrigger>
                  <IconButton icon={Ellipsis} label="Shot actions" size="sm" />
                  <MenuPopover placement="bottom end">
                    <Menu aria-label="Shot actions">
                      <MenuItem icon={Film} onAction={() => navigate({ to: '/shot/$shotId', params: { shotId: sh.uid } })}>Open</MenuItem>
                      <MenuItem icon={Scissors} onAction={() => setTrim(it)}>Trim in and out…</MenuItem>
                      <MenuItem icon={PenLine} onAction={() => setNoteItem(it)}>Edit note…</MenuItem>
                      <MenuSeparator />
                      <MenuItem icon={ArrowUp} shortcut={comboText('Alt+↑')} isDisabled={pos === 0} onAction={() => move(it.item_id, -1)}>Move up</MenuItem>
                      <MenuItem icon={ArrowDown} shortcut={comboText('Alt+↓')} isDisabled={pos === items.length - 1} onAction={() => move(it.item_id, 1)}>Move down</MenuItem>
                      <MenuSeparator />
                      <MenuItem icon={Trash2} danger shortcut="Delete" onAction={() => removeItem(it)}>Remove from collection</MenuItem>
                    </Menu>
                  </MenuPopover>
                </MenuTrigger>
              </GridListItem>
            )
          }}
        </GridList>
        </div>
      ) : (
        <EmptyState icon={Layers} title={`Nothing in ${col.name} yet`} actions={<Button onPress={() => navigate({ to: '/search' })}>Find shots</Button>}>
          Select shots and press <strong>B</strong> to add them here, or drag shots onto this page.
        </EmptyState>
      )}
      {trim && <TrimDialog item={trim} onClose={() => setTrim(null)} onSave={(i, o) => updateItem.mutateAsync({ uid: col.uid, itemId: trim.item_id, in: i, out: o }).then(() => toast({ title: 'Trim saved' }))} />}
      {noteItem && <NoteDialog item={noteItem} onClose={() => setNoteItem(null)} onSave={(note) => updateItem.mutateAsync({ uid: col.uid, itemId: noteItem.item_id, note })} />}
      <Dialog
        isOpen={confirmDelete}
        onOpenChange={setConfirmDelete}
        title={`Delete ${col.name}?`}
        size="s"
        role="alertdialog"
        footer={
          <>
            <Button variant="secondary" autoFocus onPress={() => setConfirmDelete(false)}>Cancel</Button>
            <Button
              variant="dangerFilled"
              onPress={async () => {
                try {
                  await del.mutateAsync(col.uid)
                  setConfirmDelete(false)
                  navigate({ to: '/collections' })
                } catch (e) {
                  toast({ title: "Couldn't delete", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
                }
              }}
            >
              Delete collection
            </Button>
          </>
        }
      >
        The {plural(items.length, 'shot')} stay in the library. Only this collection goes.
      </Dialog>
    </main>
  )
}

function TrimDialog({ item, onClose, onSave }: { item: CollectionItem; onClose: () => void; onSave: (i: number | null, o: number | null) => Promise<unknown> }) {
  const sh = item.shot
  const [inT, setIn] = useState(formatTimecode(item.in ?? sh.start, sh.fps))
  const [outT, setOut] = useState(formatTimecode(item.out ?? sh.end, sh.fps))
  const i = parseTimecode(inT, sh.fps)
  const o = parseTimecode(outT, sh.fps)
  const valid = i !== null && o !== null && i >= sh.start - 0.001 && o <= sh.end + 0.001 && i < o
  return (
    <Dialog
      isOpen
      onOpenChange={(open) => !open && onClose()}
      title="Trim in and out"
      size="s"
      footer={
        <>
          <Button variant="quiet" onPress={() => onSave(null, null).then(onClose)}>Reset to shot</Button>
          <Button variant="secondary" onPress={onClose}>Cancel</Button>
          <Button variant="primary" isDisabled={!valid} onPress={() => onSave(i, o).then(onClose)}>Save trim</Button>
        </>
      }
    >
      <p style={{ marginBlockEnd: 'var(--space-3)', color: 'var(--fg-2)' }}>
        The shot runs {formatTimecode(sh.start, sh.fps)} → {formatTimecode(sh.end, sh.fps)}. In and out must stay inside it.
      </p>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 'var(--space-3)' }}>
        <TextField label="In" value={inT} onChange={setIn} mono isInvalid={i === null} />
        <TextField label="Out" value={outT} onChange={setOut} mono isInvalid={o === null} />
      </div>
      {i !== null && o !== null && <p style={{ marginBlockStart: 'var(--space-2)', fontFamily: 'var(--font-mono)', fontSize: 'var(--text-xs)' }}>{valid ? `Duration ${formatDuration(o - i)}` : 'Out must come after in, inside the shot.'}</p>}
    </Dialog>
  )
}

function NoteDialog({ item, onClose, onSave }: { item: CollectionItem; onClose: () => void; onSave: (note: string) => Promise<unknown> }) {
  const [note, setNote] = useState(item.note)
  return (
    <Dialog
      isOpen
      onOpenChange={(open) => !open && onClose()}
      title="Note for this shot"
      size="m"
      footer={
        <>
          <Button variant="secondary" onPress={onClose}>Cancel</Button>
          <Button variant="primary" onPress={() => onSave(note).then(onClose)}>Save note</Button>
        </>
      }
    >
      <TextField aria-label="Note" value={note} onChange={setNote} multiline autoFocus placeholder="e.g. Use the steam rising at the end" />
    </Dialog>
  )
}
