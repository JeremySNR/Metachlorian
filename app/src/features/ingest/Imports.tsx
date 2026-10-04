import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { Form } from 'react-aria-components'
import {
  ChevronRight, CircleCheck, CircleSlash, CircleX, Clock, CopyCheck, ExternalLink, FileVideo, FolderSearch, Link2, ListVideo, LoaderCircle, RotateCcw, Trash2, X,
  type LucideIcon,
} from 'lucide-react'
import type { ImportList, ImportRow, ImportStatus } from '../../api/types'
import { api, ApiError } from '../../api/client'
import { useFolders, useHealth, useImports, useImportTool, useMe } from '../../api/queries'
import { Button, buttonClass } from '../../components/Button'
import { Bar, StatusText } from '../../components/EmptyState'
import { Checkbox, ComboBox, Select, TextField } from '../../components/Field'
import { Ic } from '../../components/Icon'
import { toast } from '../../components/Toast'
import { formatDate, plural, sentence } from '../../lib/format'
import {
  completions, destination, groupImports, importFolderOptions, importsRootFrom, isActive, linksHint, parseLinks, playlistSummary, QUALITIES, qualityLabel, siteName,
  statusWords, tally,
} from '../../lib/imports'
import { formatLength } from '../../lib/timecode'
import { useUi } from '../../lib/store'
import { searchFolder } from '../library/FoldersPage'
import l from '../library/Library.module.css'
import s from './Imports.module.css'

const LIST_LIMIT = 200

const STATUS_ICON: Record<ImportStatus, LucideIcon> = {
  queued: Clock,
  probing: LoaderCircle,
  downloading: LoaderCircle,
  done: CircleCheck,
  duplicate: CopyCheck,
  failed: CircleX,
  cancelled: CircleSlash,
  expanded: ListVideo,
}

/** Ingest → Add from links: paste links, choose a folder and a quality cap (docs/guides/importing-from-the-web.md). */
export function AddFromLinks() {
  const me = useMe()
  const health = useHealth()
  const tool = useImportTool()
  const folders = useFolders()
  const qc = useQueryClient()
  const focusAt = useUi((u) => u.importLinksFocus)
  const wrap = useRef<HTMLDivElement>(null)
  const [text, setText] = useState('')
  const [folder, setFolder] = useState('')
  const [quality, setQuality] = useState<number | null>(null)
  const [playlist, setPlaylist] = useState(false)
  const [busy, setBusy] = useState(false)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [done, setDone] = useState('')
  const parsed = useMemo(() => parseLinks(text), [text])
  const folderOptions = useMemo(() => importFolderOptions(folders.data?.folders ?? []).map((f) => ({ id: f, label: f })), [folders.data])
  const maxHeight = quality ?? tool.data?.max_height ?? null
  const canWrite = me.data ? me.data.scopes.includes('ingest:write') : true

  // ⌘K → Import from links… lands here with the links field focused.
  useEffect(() => {
    if (!focusAt || Date.now() - focusAt > 5000) return
    const t = window.setTimeout(() => {
      const el = wrap.current?.querySelector('textarea')
      el?.scrollIntoView({ block: 'center' })
      el?.focus()
    }, 60)
    return () => window.clearTimeout(t)
  }, [focusAt])

  const submit = async () => {
    setErrors({})
    setDone('')
    if (!parsed.links.length) {
      setErrors({ links: 'Paste at least one link.' })
      return
    }
    setBusy(true)
    try {
      const res = await api.post<{ imports: ImportRow[] }>('/api/imports', { urls: parsed.links, folder: folder.trim(), playlist, ...(maxHeight ? { max_height: maxHeight } : {}) })
      // Seed the list so the new rows show (and are announced when they finish) before the next poll.
      qc.setQueryData<ImportList>(['imports', LIST_LIMIT], (old) =>
        old ? { ...old, imports: [...res.imports, ...old.imports.filter((r) => !res.imports.some((n) => n.id === r.id))] } : old,
      )
      qc.invalidateQueries({ queryKey: ['imports', LIST_LIMIT], exact: true })
      setText('')
      setDone(`${plural(res.imports.length, 'link')} added. Progress is in Imports below.`)
    } catch (e) {
      const msg = e instanceof ApiError ? (e.status === 403 ? "Your role can't import videos. Ask an editor or an admin." : sentence(e.detail)) : String(e)
      setErrors(/max_height/.test(msg) ? { quality: msg } : { links: msg })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Form
      className={s.form}
      validationBehavior="aria"
      validationErrors={errors}
      onSubmit={(e) => {
        e.preventDefault()
        submit()
      }}
      data-testid="add-from-links"
    >
      <p className={s.hint}>
        {health.data?.egress.community?.enabled === false
          ? 'Community sharing is off. No community metadata is shared.'
          : 'Public YouTube imports contribute machine analysis to the community index. Private, unlisted and local footage is excluded.'}
        {' '}<Link to="/settings/$section" params={{ section: 'community' }}>Community sharing settings</Link>
      </p>
      <div ref={wrap} className={s.links}>
        <TextField
          name="links"
          label="Links"
          multiline
          mono
          value={text}
          onChange={(v) => {
            setText(v)
            if (done) setDone('')
          }}
          placeholder={'https://www.youtube.com/watch?v=…\nhttps://vimeo.com/…'}
          description={linksHint(parsed)}
          isDisabled={!canWrite}
        />
      </div>
      <div className={s.options}>
        <ComboBox
          name="folder"
          label="Folder"
          description="Under imports/ in the library. Empty: the site's name (YouTube, Vimeo…)."
          placeholder="e.g. Disney 2026"
          options={folderOptions}
          allowsCustomValue
          inputValue={folder}
          onInputChange={setFolder}
          onSelectionChange={(k) => k !== null && setFolder(String(k))}
          isDisabled={!canWrite}
          className={s.folder}
        />
        <Select
          name="quality"
          label="Quality"
          description={tool.data ? `The highest it downloads. Default ${qualityLabel(tool.data.max_height)}.` : 'The highest it downloads.'}
          options={QUALITIES.map((h) => ({ id: String(h), label: qualityLabel(h) }))}
          selectedKey={maxHeight ? String(maxHeight) : null}
          placeholder="The library's default"
          onSelectionChange={(k) => setQuality(Number(k))}
          isDisabled={!canWrite}
          className={s.quality}
        />
      </div>
      <Checkbox isSelected={playlist} onChange={setPlaylist} isDisabled={!canWrite}>
        Import every video of a playlist or channel
      </Checkbox>
      <div className={s.submitRow}>
        <Button type="submit" variant="secondary" icon={Link2} busy={busy} isDisabled={!canWrite || !parsed.links.length} disabledReason={canWrite ? 'Paste at least one link first' : "Your role can't import videos"}>
          Import
        </Button>
        <span role="status" className={s.done}>{done}</span>
      </div>
      <p className={s.note}>
        Only import videos you have the right to use, and check the site's terms. Imported files start with rights <strong>unknown</strong>: agents don't see
        them until someone checks the rights and marks them cleared.{' '}
        {canWrite ? (
          <>
            Private or members-only videos need a login: <Link to="/settings/$section" params={{ section: 'imports' }}>Settings → Imports</Link>.
          </>
        ) : (
          "Your role can't import videos. Ask an editor or an admin."
        )}
      </p>
    </Form>
  )
}

/** Ingest → Imports: live progress of web-link imports, playlists grouped with their videos (polls every 1.5 s while active). */
export function ImportsList() {
  const q = useImports(LIST_LIMIT)
  const qc = useQueryClient()
  const rows = useMemo(() => q.data?.imports ?? [], [q.data])
  const groups = useMemo(() => groupImports(rows), [rows])
  const root = useMemo(() => importsRootFrom(rows), [rows])
  const prev = useRef<Map<number, ImportStatus> | null>(null)
  const [announce, setAnnounce] = useState('')
  // Magenta marks only the current item (system.md §0 rule 2): the first row downloading.
  const currentId = rows.find((r) => r.status === 'downloading')?.id
  const t = tally(rows)

  useEffect(() => {
    if (!q.data) return
    const before = prev.current
    prev.current = new Map(q.data.imports.map((r) => [r.id, r.status]))
    if (!before) return
    const msgs = completions(before, q.data.imports)
    if (!msgs.length) return
    for (const k of ['processing', 'folders', 'assets', 'stats', 'sources']) qc.invalidateQueries({ queryKey: [k] })
    const timer = window.setTimeout(() => setAnnounce(msgs.join(' ')), 0)
    return () => window.clearTimeout(timer)
  }, [q.data, qc])

  const act = async (row: ImportRow, action: 'cancel' | 'retry' | 'remove') => {
    try {
      if (action === 'remove') await api.del(`/api/imports/${row.id}`)
      else await api.post(`/api/imports/${row.id}/${action}`, {})
    } catch (e) {
      toast({ title: action === 'remove' ? "Couldn't remove it from the list" : action === 'retry' ? "Couldn't retry" : "Couldn't cancel", description: e instanceof ApiError ? sentence(e.detail) : String(e), tone: 'error' })
    }
    qc.invalidateQueries({ queryKey: ['imports', LIST_LIMIT], exact: true })
  }

  // The section shows once something was imported (or the list can't be read).
  if (!rows.length && !q.isError) return null

  const summary = [t.active ? `${t.active} importing` : null, t.done ? `${t.done} imported` : null, t.duplicate ? `${t.duplicate} already in the library` : null, t.failed ? `${t.failed} failed` : null]
    .filter(Boolean)
    .join(' · ')

  return (
    <section className={l.section} aria-labelledby="imp-h" data-testid="imports">
      <div className={l.sectionHead}>
        <h2 id="imp-h">Imports</h2>
        <span className={s.count}>{summary}</span>
      </div>
      <span className="visually-hidden" aria-live="polite" role="status" data-testid="imports-announce">
        {announce}
      </span>
      {q.isError ? (
        <p className={s.error} role="alert">Couldn't read the imports: {(q.error as Error).message}</p>
      ) : (
        <>
          <p className={s.hint}>Removing a row from this list keeps the file in the library.</p>
          <ul className={s.list} aria-label="Imports from links">
            {groups.map((g) => (
              <ImportItem key={g.row.id} row={g.row} kids={g.children} root={root} currentId={currentId} act={act} />
            ))}
          </ul>
        </>
      )}
    </section>
  )
}

function nameOf(row: ImportRow) {
  return row.title || row.url
}

function ImportItem({ row, kids, root, currentId, act, nested }: { row: ImportRow; kids: ImportRow[]; root: string | null; currentId?: number; act: (r: ImportRow, a: 'cancel' | 'retry' | 'remove') => Promise<void>; nested?: boolean }) {
  const navigate = useNavigate()
  const [open, setOpen] = useState(kids.length <= 8)
  const words = statusWords(row, kids)
  const active = isActive(row.status)
  const isPlaylist = row.status === 'expanded'
  const name = nameOf(row)
  const dest = destination(row, root) ?? (isPlaylist ? destination(kids.find((k) => k.path) ?? row, root) : null)
  // An imported file's folder (absolute) for "Search this folder".
  const landed = (row.path ? row : kids.find((k) => k.status === 'done' && k.path))?.path ?? null
  const folderAbs = landed ? landed.replace(/\\/g, '/').replace(/\/[^/]*$/, '') : null
  const folderName = dest ?? folderAbs?.split('/').pop() ?? ''
  const kidsActive = kids.filter((k) => isActive(k.status))
  const kidsFailed = kids.filter((k) => k.status === 'failed' || k.status === 'cancelled')
  const uploaded = typeof row.info.upload_date === 'string' && /^\d{8}$/.test(row.info.upload_date) ? `${row.info.upload_date.slice(0, 4)}-${row.info.upload_date.slice(4, 6)}-${row.info.upload_date.slice(6)}` : null
  const meta = [
    isPlaylist ? playlistSummary(kids) : null,
    row.site ? siteName(row.site) : null,
    row.uploader,
    row.duration ? formatLength(row.duration) : null,
    uploaded ? `uploaded ${formatDate(uploaded)}` : null,
    !nested && dest ? `to ${dest}` : null,
    !nested && !isPlaylist ? `up to ${row.max_height}p` : null,
  ].filter(Boolean)
  const showMessage = active && row.message && !/^(Checking the link…|Downloading video…)$/.test(row.message)

  const removeGroup = async () => {
    for (const k of kids) if (!isActive(k.status)) await act(k, 'remove')
    await act(row, 'remove')
  }

  return (
    <li className={`${s.item} ${nested ? s.nested : ''}`} data-testid="import-row" data-status={row.status} data-id={row.id}>
      <div className={s.head}>
        <StatusText tone={words.tone} icon={STATUS_ICON[row.status]} spin={row.status === 'probing' || row.status === 'downloading'} className={s.status}>
          {words.label}
        </StatusText>
        <span className={s.title}>{row.title ? row.title : <span className={s.mono}>{row.url}</span>}</span>
      </div>
      {meta.length > 0 && <p className={s.meta}>{meta.join(' · ')}</p>}
      {row.title && (
        <a className={s.url} href={row.url} target="_blank" rel="noreferrer noopener">
          {row.url}
          <Ic icon={ExternalLink} size={12} />
          <span className="visually-hidden"> (opens in a new tab)</span>
        </a>
      )}
      {active && (
        <div className={s.progress}>
          {row.status === 'downloading' && row.progress >= 0 ? (
            <>
              <Bar value={row.progress} current={row.id === currentId} label={`Downloading ${name}`} />
              <span className={s.pct}>{Math.round(row.progress * 100)}%</span>
            </>
          ) : null}
          {showMessage && <span className={s.message}>{row.message}</span>}
        </div>
      )}
      {row.status === 'failed' && row.error && (
        <p className={s.error} data-testid="import-error">
          {row.error}
        </p>
      )}
      <div className={s.actions}>
        {active && (
          <Button variant="quiet" size="sm" icon={X} onPress={() => act(row, 'cancel')} aria-label={`Cancel ${name}`}>
            Cancel
          </Button>
        )}
        {(row.status === 'failed' || row.status === 'cancelled') && (
          <Button variant="secondary" size="sm" icon={RotateCcw} onPress={() => act(row, 'retry')} aria-label={`Retry ${name}`}>
            Retry
          </Button>
        )}
        {(row.status === 'done' || row.status === 'duplicate') && row.asset_uid && (
          <Link to="/file/$assetId" params={{ assetId: row.asset_uid }} className={buttonClass('secondary', 'sm')} aria-label={`Open file: ${name}`}>
            <Ic icon={FileVideo} size={14} />
            Open file
          </Link>
        )}
        {isPlaylist && kidsActive.length > 0 && (
          <Button variant="quiet" size="sm" icon={X} onPress={async () => { for (const k of kidsActive) await act(k, 'cancel') }} aria-label={`Cancel the remaining videos of ${name}`}>
            Cancel remaining
          </Button>
        )}
        {isPlaylist && kidsFailed.length > 0 && (
          <Button variant="secondary" size="sm" icon={RotateCcw} onPress={async () => { for (const k of kidsFailed) await act(k, 'retry') }} aria-label={`Retry the failed videos of ${name}`}>
            Retry {kidsFailed.length === 1 ? 'the failed video' : `${kidsFailed.length} failed videos`}
          </Button>
        )}
        {!nested && folderAbs && (
          <Button variant="quiet" size="sm" icon={FolderSearch} onPress={() => searchFolder(navigate, folderAbs)} aria-label={`Search this folder: ${folderName}`}>
            Search this folder
          </Button>
        )}
        {!active && (
          <Button
            variant="quiet"
            size="sm"
            icon={Trash2}
            onPress={isPlaylist ? removeGroup : () => act(row, 'remove')}
            isDisabled={kidsActive.length > 0}
            disabledReason={kidsActive.length ? 'Cancel or wait for the videos still importing' : undefined}
            aria-label={`Remove ${name} from the list`}
          >
            Remove
          </Button>
        )}
      </div>
      {kids.length > 0 && (
        <>
          {kids.length > 8 && (
            <button type="button" className={s.toggle} aria-expanded={open} onClick={() => setOpen(!open)}>
              <Ic icon={ChevronRight} size={14} className={s.chev} />
              {open ? 'Hide the videos' : `Show ${plural(kids.length, 'video')}`}
            </button>
          )}
          {open && (
            <ul className={s.children} aria-label={`Videos of ${name}`}>
              {kids.map((k) => (
                <ImportItem key={k.id} row={k} kids={[]} root={root} currentId={currentId} act={act} nested />
              ))}
            </ul>
          )}
        </>
      )}
    </li>
  )
}
