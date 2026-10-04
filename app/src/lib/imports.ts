/**
 * Imports from web links (yt-dlp; docs/guides/importing-from-the-web.md): reading pasted links, grouping
 * playlists with their videos, and the words each state is shown with.
 */
import type { ImportRow, ImportStatus } from '../api/types'

export const ACTIVE_STATUSES: readonly ImportStatus[] = ['queued', 'probing', 'downloading']
export const isActive = (s: ImportStatus) => ACTIVE_STATUSES.includes(s)
/** States a row can be removed from the list in (the core refuses active ones). */
export const isFinished = (s: ImportStatus) => !isActive(s)

/** Heights the core accepts for `max_height`. */
export const QUALITIES = [360, 480, 720, 1080, 1440, 2160, 4320] as const
export type Quality = (typeof QUALITIES)[number]

const QUALITY_NAME: Record<number, string> = { 720: 'HD', 1080: 'Full HD', 1440: '2K', 2160: '4K', 4320: '8K' }

/** "1080p (Full HD)", "480p". */
export function qualityLabel(h: number): string {
  return QUALITY_NAME[h] ? `${h}p (${QUALITY_NAME[h]})` : `${h}p`
}

export interface ParsedLinks {
  /** Distinct entries, in the order pasted (sent to the core, which validates them). */
  links: string[]
  /** Entries that aren't http(s) links, so the core will refuse the batch. */
  invalid: string[]
  /** Repeats that were dropped. */
  repeated: number
}

const WRAP = /^[<("'“‘[]+|[>)"'”’\],;]+$/g

/** True for an http:// or https:// address with a host. */
export function isWebLink(s: string): boolean {
  try {
    const u = new URL(s)
    return (u.protocol === 'http:' || u.protocol === 'https:') && Boolean(u.hostname)
  } catch {
    return false
  }
}

/**
 * One link per line or separated by spaces (a paste of several works). Wrapping angle brackets, quotes
 * and trailing commas from a pasted list are dropped; exact repeats are sent once.
 */
export function parseLinks(text: string): ParsedLinks {
  const seen = new Set<string>()
  const links: string[] = []
  const invalid: string[] = []
  let repeated = 0
  for (const raw of text.split(/\s+/)) {
    const t = raw.replace(WRAP, '')
    if (!t) continue
    if (seen.has(t)) {
      repeated++
      continue
    }
    seen.add(t)
    links.push(t)
    if (!isWebLink(t)) invalid.push(t)
  }
  return { links, invalid, repeated }
}

/** "2 links", "1 link · 1 repeat ignored", with the first entry that isn't a link. */
export function linksHint(p: ParsedLinks): string {
  if (!p.links.length) return 'One link per line, or separated by spaces.'
  const parts = [`${p.links.length} ${p.links.length === 1 ? 'link' : 'links'}`]
  if (p.repeated) parts.push(`${p.repeated} ${p.repeated === 1 ? 'repeat' : 'repeats'} ignored`)
  if (p.invalid.length) parts.push(`“${truncate(p.invalid[0], 40)}” isn't a web link (use http:// or https://)`)
  return parts.join(' · ')
}

function truncate(s: string, n: number) {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s
}

// ---------------------------------------------------------------- grouping

export interface ImportGroup {
  row: ImportRow
  /** A playlist's videos, oldest first (empty for a single video). */
  children: ImportRow[]
}

/**
 * Playlists with their videos. The list arrives active first, newest first; a playlist keeps its place and
 * takes its videos with it. A video whose playlist isn't in the list (removed, or past the limit) stands alone.
 */
export function groupImports(rows: readonly ImportRow[]): ImportGroup[] {
  const ids = new Set(rows.map((r) => r.id))
  const kids = new Map<number, ImportRow[]>()
  for (const r of rows) {
    if (r.parent_id !== null && ids.has(r.parent_id)) {
      const k = kids.get(r.parent_id) ?? []
      k.push(r)
      kids.set(r.parent_id, k)
    }
  }
  const out: ImportGroup[] = []
  for (const r of rows) {
    if (r.parent_id !== null && ids.has(r.parent_id)) continue
    out.push({ row: r, children: (kids.get(r.id) ?? []).sort((a, b) => a.id - b.id) })
  }
  // A playlist with videos still going belongs with the active rows at the top.
  const active = (g: ImportGroup) => isActive(g.row.status) || g.children.some((c) => isActive(c.status))
  return [...out.filter(active), ...out.filter((g) => !active(g))]
}

export type Tally = Record<'active' | 'done' | 'duplicate' | 'failed' | 'cancelled', number>

export function tally(rows: readonly ImportRow[]): Tally {
  const t: Tally = { active: 0, done: 0, duplicate: 0, failed: 0, cancelled: 0 }
  for (const r of rows) {
    if (isActive(r.status)) t.active++
    else if (r.status === 'done' || r.status === 'duplicate' || r.status === 'failed' || r.status === 'cancelled') t[r.status]++
  }
  return t
}

/** "3 of 12 imported · 1 already in the library · 2 failed · 6 to go". */
export function playlistSummary(children: readonly ImportRow[]): string {
  const t = tally(children)
  const parts = [`${t.done} of ${children.length} imported`]
  if (t.duplicate) parts.push(`${t.duplicate} already in the library`)
  if (t.failed) parts.push(`${t.failed} failed`)
  if (t.cancelled) parts.push(`${t.cancelled} cancelled`)
  if (t.active) parts.push(`${t.active} to go`)
  return parts.join(' · ')
}

// ---------------------------------------------------------------- wording

export type Tone = 'info' | 'cleared' | 'caution' | 'blocked' | 'neutral'

export interface StatusWords {
  label: string
  tone: Tone
}

/** The state of a row in plain words (icon + word + colour, system.md §0 rule 3). */
export function statusWords(row: Pick<ImportRow, 'status' | 'progress'>, children: readonly ImportRow[] = []): StatusWords {
  switch (row.status) {
    case 'queued':
      return { label: 'Waiting', tone: 'info' }
    case 'probing':
      return { label: 'Checking the link', tone: 'info' }
    case 'downloading':
      return { label: row.progress >= 0 && row.progress < 1 ? `Downloading · ${Math.round(row.progress * 100)}%` : 'Downloading', tone: 'info' }
    case 'done':
      return { label: 'Imported', tone: 'cleared' }
    case 'duplicate':
      return { label: 'Already in the library', tone: 'neutral' }
    case 'failed':
      return { label: 'Failed', tone: 'blocked' }
    case 'cancelled':
      return { label: 'Cancelled', tone: 'neutral' }
    case 'expanded': {
      const t = tally(children)
      if (t.active) return { label: `Playlist · ${t.active} to go`, tone: 'info' }
      if (t.failed) return { label: `Playlist · ${t.failed} failed`, tone: 'caution' }
      return { label: 'Playlist imported', tone: 'cleared' }
    }
    default:
      return { label: String(row.status), tone: 'neutral' }
  }
}

/** The core's folder for a site when no folder is given (importer.SITE_FOLDERS). */
const SITE_FOLDERS: Record<string, string> = {
  youtube: 'YouTube', vimeo: 'Vimeo', archiveorg: 'Internet Archive', generic: 'Web', dailymotion: 'Dailymotion', twitch: 'Twitch',
  tiktok: 'TikTok', instagram: 'Instagram', facebook: 'Facebook', twitter: 'X',
}

export function siteFolder(site: string | null | undefined): string {
  const s = site || 'Web'
  return SITE_FOLDERS[s.toLowerCase()] ?? s
}

/** The site as a person names it: "YouTube", "Internet Archive", "Web link" for a direct file. */
export function siteName(site: string | null | undefined): string {
  if (!site || site.toLowerCase() === 'generic') return 'Web link'
  return siteFolder(site)
}

/**
 * The folder a row lands in, relative to imports/: the file's own folder once imported, else the chosen
 * folder, else the site's name (null while the site isn't known yet).
 */
export function destination(row: Pick<ImportRow, 'folder' | 'site' | 'path'>, importsRoot?: string | null): string | null {
  if (row.path && importsRoot) {
    const dir = row.path.replace(/\\/g, '/').replace(/\/[^/]*$/, '')
    const root = importsRoot.replace(/\/+$/, '')
    if (dir.startsWith(`${root}/`)) return dir.slice(root.length + 1)
  }
  if (row.folder) return row.folder
  return row.site ? siteFolder(row.site) : null
}

/** The imports root (<library>/imports) from an imported file's path and its folder. */
export function importsRootFrom(rows: readonly Pick<ImportRow, 'path' | 'folder'>[]): string | null {
  for (const r of rows) {
    if (!r.path || !r.folder) continue
    const dir = r.path.replace(/\\/g, '/').replace(/\/[^/]*$/, '')
    if (dir.endsWith(`/${r.folder}`)) return dir.slice(0, -r.folder.length - 1)
  }
  return null
}

/** Folder suggestions: existing folders under the imports root, relative to it ("YouTube", "Disney 2026/Day 2"). */
export function importFolderOptions(folders: readonly { path: string; source: string }[]): string[] {
  const out: string[] = []
  for (const f of folders) {
    const src = f.source.replace(/\/+$/, '')
    if (!/\/imports$/.test(src)) continue
    const p = f.path.replace(/\/+$/, '')
    if (p.startsWith(`${src}/`)) out.push(p.slice(src.length + 1))
  }
  return [...new Set(out)].sort((a, b) => a.localeCompare(b, 'en-GB'))
}

/**
 * Polite announcements for rows that finished since the last poll: "Imported Holiday Parade." Rows seen
 * for the first time are not announced (they finished before the page opened).
 */
export function completions(prev: ReadonlyMap<number, ImportStatus>, rows: readonly ImportRow[]): string[] {
  const out: string[] = []
  for (const r of rows) {
    const before = prev.get(r.id)
    if (!before || !isActive(before) || isActive(r.status)) continue
    const name = r.title || r.url
    if (r.status === 'done') out.push(`Imported ${name}.`)
    else if (r.status === 'duplicate') out.push(`${name} is already in the library.`)
    else if (r.status === 'failed') out.push(`Import failed: ${name}.`)
    else if (r.status === 'expanded') out.push(`Playlist ${name}: ${r.message || 'videos queued'}.`)
  }
  return out
}
