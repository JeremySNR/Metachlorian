/**
 * Folder browser logic: the tree from GET /api/folders (a flat list sorted by relative path, counts
 * including subfolders), breadcrumbs for a file's folder, shoot-date ranges and edit-stage summaries.
 */
import { basename } from './scope'

export interface FolderLike {
  path: string
  name: string
  relative: string
  source: string
  depth: number
}

export interface FolderNode<F> {
  folder: F
  children: FolderNode<F>[]
}

const parentOf = (p: string) => {
  const i = p.replace(/\/+$/, '').lastIndexOf('/')
  return i > 0 ? p.slice(0, i) : null
}

/** The directory of a file path ("/a/b/c.mp4" → "/a/b"). */
export function dirname(path: string): string {
  const p = path.replace(/\\/g, '/')
  return parentOf(p) ?? p
}

/**
 * Nest the flat list. A folder's parent is its nearest ancestor in the list; a folder whose ancestors
 * are missing (a filtered or truncated list) becomes a top-level node. Order is kept.
 */
export function buildFolderTree<F extends { path: string }>(folders: readonly F[]): FolderNode<F>[] {
  const byPath = new Map<string, FolderNode<F>>()
  for (const f of folders) byPath.set(f.path.replace(/\/+$/, ''), { folder: f, children: [] })
  const roots: FolderNode<F>[] = []
  for (const f of folders) {
    const node = byPath.get(f.path.replace(/\/+$/, '')) as FolderNode<F>
    let up = parentOf(f.path)
    let parent: FolderNode<F> | undefined
    while (up && !parent) {
      parent = byPath.get(up)
      up = parentOf(up)
    }
    if (parent && parent !== node) parent.children.push(node)
    else roots.push(node)
  }
  return roots
}

export interface FolderRow<F> {
  folder: F
  level: number
  hasChildren: boolean
  expanded: boolean
}

/** Visible rows of the tree, depth-first, with children shown only under expanded folders. */
export function flattenTree<F extends { path: string }>(nodes: FolderNode<F>[], expanded: ReadonlySet<string>, level = 0, out: FolderRow<F>[] = []): FolderRow<F>[] {
  for (const n of nodes) {
    const open = expanded.has(n.folder.path)
    out.push({ folder: n.folder, level, hasChildren: n.children.length > 0, expanded: open })
    if (open) flattenTree(n.children, expanded, level + 1, out)
  }
  return out
}

export interface Crumb {
  name: string
  path: string
}

/**
 * Breadcrumb for a folder from its source root: "sample › day 2". Each crumb carries its absolute path,
 * which scopes search exactly (a name matches that folder name anywhere).
 */
export function folderCrumbs(abs: string, folders: readonly FolderLike[]): Crumb[] {
  const dir = abs.replace(/\\/g, '/').replace(/\/+$/, '')
  if (!dir) return []
  const known = folders.find((f) => f.path === dir)
  let root = known?.source
  if (!root) {
    for (const f of folders) {
      const s = f.source.replace(/\/+$/, '')
      if ((dir === s || dir.startsWith(`${s}/`)) && (!root || s.length > root.length)) root = s
    }
  }
  if (!root) return [{ name: basename(dir), path: dir }]
  const crumbs: Crumb[] = [{ name: basename(root), path: root }]
  if (dir === root) return crumbs
  let acc = root
  for (const seg of dir.slice(root.length + 1).split('/').filter(Boolean)) {
    acc = `${acc}/${seg}`
    crumbs.push({ name: seg, path: acc })
  }
  return crumbs
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function ymd(iso: string | null | undefined): [number, number, number] | null {
  const m = iso ? /^(\d{4})-(\d{2})-(\d{2})/.exec(iso) : null
  return m ? [Number(m[1]), Number(m[2]) - 1, Number(m[3])] : null
}

/**
 * Shoot dates as one compact range (system.md §8 dates, en dash): "3–14 Aug 2026", "28 Jul – 3 Aug 2026",
 * "20 Oct 2013 – 4 Oct 2026", or a single day "3 Aug 2026". Empty when unknown.
 */
export function formatDateRange(from: string | null | undefined, to: string | null | undefined): string {
  const a = ymd(from) ?? ymd(to)
  const b = ymd(to) ?? ymd(from)
  if (!a || !b) return ''
  const [y1, m1, d1] = a
  const [y2, m2, d2] = b
  if (y1 === y2 && m1 === m2 && d1 === d2) return `${d1} ${MONTHS[m1]} ${y1}`
  if (y1 === y2 && m1 === m2) return `${d1}–${d2} ${MONTHS[m1]} ${y1}`
  if (y1 === y2) return `${d1} ${MONTHS[m1]} – ${d2} ${MONTHS[m2]} ${y1}`
  return `${d1} ${MONTHS[m1]} ${y1} – ${d2} ${MONTHS[m2]} ${y2}`
}

/** Footage length from hours: "Under 1 min", "8 min", "1.5 h", "12 h". */
export function formatHours(hours: number | null | undefined): string {
  if (hours === null || hours === undefined || !Number.isFinite(hours) || hours <= 0) return '0 min'
  const min = hours * 60
  if (min < 1) return 'Under 1 min'
  if (min < 60) return `${Math.round(min)} min`
  return `${hours < 10 ? (Math.round(hours * 10) / 10).toString() : Math.round(hours)} h`
}

/** Edit stage per file, most common first: [{term: 'raw', count: 5}, …]; unclassified files under null. */
export function editStageCounts(assets: readonly { edit_type?: { term: string } | string | null }[]): { term: string | null; count: number }[] {
  const m = new Map<string | null, number>()
  for (const a of assets) {
    const e = a.edit_type
    const term = typeof e === 'string' ? e : e?.term ?? null
    m.set(term, (m.get(term) ?? 0) + 1)
  }
  return [...m.entries()].map(([term, count]) => ({ term, count })).sort((x, y) => (x.term === null ? 1 : y.term === null ? -1 : y.count - x.count))
}
