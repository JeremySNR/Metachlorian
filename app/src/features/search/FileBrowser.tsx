import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { api, mediaUrl, qs } from '../../api/client'
import type { AssetList, AssetListItem } from '../../api/types'
import { Button } from '../../components/Button'
import { usePrefs } from '../../lib/store'
import { formatNumber, humanise } from '../../lib/format'
import { formatDuration } from '../../lib/timecode'
import { FolderCrumbs } from './FolderCrumbs'
import s from './FileBrowser.module.css'

const PAGE = 60

function FileCard({ file }: { file: AssetListItem }) {
  const [broken, setBroken] = useState(false)
  const folder = file.path.replaceAll('\\', '/').replace(/\/[^/]+$/, '')
  const date = file.captured ? new Date(file.captured) : null
  return <article className={s.card}>
    <Link to="/file/$assetId" params={{ assetId: file.uid }} className={s.open} aria-label={`Open ${file.filename}`}>
      <div className={s.preview}>
        {file.preview_ready && !broken
          ? <img src={mediaUrl(file.poster)} alt="" loading="lazy" decoding="async" onError={() => setBroken(true)} />
          : <span>{file.status === 'error' ? 'Preview failed' : broken ? 'Preview unavailable' : 'Preview pending'}</span>}
      </div>
      <div className={s.details}>
        <strong title={file.filename}>{file.filename}</strong>
        <span>{date && !Number.isNaN(date.getTime()) ? date.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : 'Capture date unknown'}</span>
        <span>{file.duration != null ? formatDuration(file.duration) : 'Duration pending'} · {humanise(file.status)}</span>
        <p className={s.description}>{file.summary || 'Description will appear after analysis.'}</p>
      </div>
    </Link>
    <div className={s.folder}><FolderCrumbs folder={folder} /></div>
  </article>
}

/** Pages through assets, including files that do not have any indexed shots yet. */
export function FileBrowser({ folder, collection, sort, hideBlocked }: { folder?: string; collection?: string; sort: string; hideBlocked: boolean }) {
  const [page, setPage] = useState(0)
  const view = usePrefs((p) => p.view)
  const size = usePrefs((p) => p.thumbSize)
  const files = useQuery({
    queryKey: ['file-browser', folder, collection, sort, hideBlocked, page],
    queryFn: ({ signal }) => api.get<AssetList>(`/api/assets${qs({ folder, collection, sort, hide_blocked: hideBlocked, limit: PAGE, offset: page * PAGE })}`, signal),
    refetchInterval: 15_000,
  })
  const total = files.data?.total ?? 0
  return <section className={s.browser} aria-label="All library files">
    <div className={s.pager}>
      <span role="status">{files.isPending ? 'Loading files…' : `${formatNumber(total)} files · ${total ? page * PAGE + 1 : 0}–${Math.min((page + 1) * PAGE, total)} shown`}</span>
      <Button size="sm" variant="secondary" isDisabled={page === 0 || files.isFetching} onPress={() => setPage(page - 1)}>Previous</Button>
      <span>Page {page + 1}{total ? ` of ${Math.ceil(total / PAGE)}` : ''}</span>
      <Button size="sm" variant="secondary" isDisabled={!files.data || (page + 1) * PAGE >= total || files.isFetching} onPress={() => setPage(page + 1)}>Next</Button>
    </div>
    <p className={s.hint}>Includes files still being analysed. Dates come from capture metadata; unknown dates appear last.</p>
    {files.isError && <div role="alert">Couldn’t load files. <Button onPress={() => files.refetch()}>Retry</Button></div>}
    {!files.isPending && !files.isError && total === 0 && <p>No files in this folder or collection.</p>}
    <div className={s.scroller} key={page}>
      <div className={s.items} data-view={view} data-size={size} style={{ ['--file-width' as string]: `${{ s: 168, m: 240, l: 340 }[size]}px` }}>
        {files.data?.assets.map((file) => <FileCard key={file.uid} file={file} />)}
      </div>
    </div>
  </section>
}
