import { describe, expect, it } from 'vitest'
import type { ImportRow, ImportStatus } from '../api/types'
import {
  completions, destination, groupImports, importFolderOptions, importsRootFrom, isWebLink, linksHint, parseLinks, playlistSummary, qualityLabel, siteFolder,
  siteName, statusWords,
} from './imports'

let next = 1
const row = (p: Partial<ImportRow> = {}): ImportRow => ({
  id: next++, url: 'https://www.youtube.com/watch?v=x', parent_id: null, status: 'done', progress: 1, message: '', error: null, folder: '', playlist: false,
  max_height: 1080, origin_key: null, title: null, site: null, uploader: null, duration: null, info: {}, path: null, asset_uid: null, actor: 'local',
  created_at: 0, updated_at: 0, ...p,
})

describe('parseLinks', () => {
  it('takes one link per line or separated by spaces, in order', () => {
    const p = parseLinks('https://a.example/1\nhttps://b.example/2  https://c.example/3\r\n\n')
    expect(p.links).toEqual(['https://a.example/1', 'https://b.example/2', 'https://c.example/3'])
    expect(p.invalid).toEqual([])
    expect(p.repeated).toBe(0)
  })
  it('sends a repeated link once and counts the repeat', () => {
    const p = parseLinks('https://a.example/1 https://a.example/1\nhttps://a.example/1')
    expect(p.links).toEqual(['https://a.example/1'])
    expect(p.repeated).toBe(2)
  })
  it('strips brackets, quotes and trailing commas from a pasted list', () => {
    expect(parseLinks('<https://a.example/1>, "https://b.example/2";').links).toEqual(['https://a.example/1', 'https://b.example/2'])
  })
  it('keeps entries that are not web links, and names them', () => {
    const p = parseLinks('youtube.com/watch?v=1 https://ok.example ftp://x.example/a')
    expect(p.links).toHaveLength(3)
    expect(p.invalid).toEqual(['youtube.com/watch?v=1', 'ftp://x.example/a'])
    expect(linksHint(p)).toBe('3 links · “youtube.com/watch?v=1” isn\'t a web link (use http:// or https://)')
  })
  it('hints at the format when empty', () => {
    expect(linksHint(parseLinks('   \n'))).toBe('One link per line, or separated by spaces.')
    expect(linksHint(parseLinks('https://a.example https://a.example'))).toBe('1 link · 1 repeat ignored')
  })
  it('recognises web links', () => {
    expect(isWebLink('http://127.0.0.1:8799/Holiday%20Parade.mp4')).toBe(true)
    expect(isWebLink('https://')).toBe(false)
    expect(isWebLink('javascript:alert(1)')).toBe(false)
  })
})

describe('groupImports', () => {
  it('puts a playlist\'s videos under it, oldest first, and keeps lone videos', () => {
    const pl = row({ id: 10, status: 'expanded', playlist: true })
    const a = row({ id: 11, parent_id: 10 })
    const b = row({ id: 12, parent_id: 10 })
    const lone = row({ id: 9 })
    const groups = groupImports([b, pl, a, lone])
    expect(groups.map((g) => g.row.id)).toEqual([10, 9])
    expect(groups[0].children.map((c) => c.id)).toEqual([11, 12])
    expect(groups[1].children).toEqual([])
  })
  it('lets a video stand alone when its playlist is not listed', () => {
    const orphan = row({ id: 21, parent_id: 99 })
    expect(groupImports([orphan])).toEqual([{ row: orphan, children: [] }])
  })
  it('lifts a playlist with videos still going above finished rows', () => {
    const done = row({ id: 30, status: 'failed' })
    const pl = row({ id: 31, status: 'expanded' })
    const kid = row({ id: 32, parent_id: 31, status: 'downloading', progress: 0.4 })
    expect(groupImports([done, pl, kid]).map((g) => g.row.id)).toEqual([31, 30])
  })
})

describe('wording', () => {
  const w = (status: ImportStatus, progress = 0) => statusWords({ status, progress })
  it('says what each state means', () => {
    expect(w('queued')).toEqual({ label: 'Waiting', tone: 'info' })
    expect(w('probing').label).toBe('Checking the link')
    expect(w('downloading', 0.426).label).toBe('Downloading · 43%')
    expect(w('downloading', -1).label).toBe('Downloading')
    expect(w('done')).toEqual({ label: 'Imported', tone: 'cleared' })
    expect(w('duplicate').label).toBe('Already in the library')
    expect(w('failed')).toEqual({ label: 'Failed', tone: 'blocked' })
    expect(w('cancelled').label).toBe('Cancelled')
  })
  it('summarises a playlist from its videos', () => {
    const kids = [row({ status: 'done' }), row({ status: 'duplicate' }), row({ status: 'failed' }), row({ status: 'queued' })]
    expect(statusWords({ status: 'expanded', progress: 1 }, kids)).toEqual({ label: 'Playlist · 1 to go', tone: 'info' })
    expect(statusWords({ status: 'expanded', progress: 1 }, kids.slice(0, 3))).toEqual({ label: 'Playlist · 1 failed', tone: 'caution' })
    expect(statusWords({ status: 'expanded', progress: 1 }, kids.slice(0, 2)).label).toBe('Playlist imported')
    expect(playlistSummary(kids)).toBe('1 of 4 imported · 1 already in the library · 1 failed · 1 to go')
  })
  it('names quality caps', () => {
    expect(qualityLabel(1080)).toBe('1080p (Full HD)')
    expect(qualityLabel(480)).toBe('480p')
  })
  it('names sites and their default folders like the core', () => {
    expect(siteFolder('Youtube')).toBe('YouTube')
    expect(siteFolder('Generic')).toBe('Web')
    expect(siteFolder('BiliBili')).toBe('BiliBili')
    expect(siteFolder(null)).toBe('Web')
    expect(siteName('Generic')).toBe('Web link')
    expect(siteName('ArchiveOrg')).toBe('Internet Archive')
  })
})

describe('folders', () => {
  const ROOT = '/lib/imports'
  it('finds where a row lands, relative to imports/', () => {
    expect(destination({ folder: 'Disney 2026', site: null, path: null })).toBe('Disney 2026')
    expect(destination({ folder: '', site: 'Youtube', path: null })).toBe('YouTube')
    expect(destination({ folder: '', site: null, path: null })).toBeNull()
    expect(destination({ folder: '', site: 'Youtube', path: `${ROOT}/YouTube/My playlist/a [x].mp4` }, ROOT)).toBe('YouTube/My playlist')
  })
  it('works out the imports root from an imported file', () => {
    expect(importsRootFrom([{ path: null, folder: 'X' }, { path: `${ROOT}/Journey import/Holiday Parade [Holiday Parade].mp4`, folder: 'Journey import' }])).toBe(ROOT)
    expect(importsRootFrom([{ path: `${ROOT}/Web/a.mp4`, folder: '' }])).toBeNull()
  })
  it('suggests folders under the imports root only', () => {
    const folders = [
      { path: ROOT, source: ROOT },
      { path: `${ROOT}/YouTube`, source: ROOT },
      { path: `${ROOT}/Disney 2026/Day 2`, source: ROOT },
      { path: '/footage/imports-old/x', source: '/footage' },
      { path: '/footage', source: '/footage' },
    ]
    expect(importFolderOptions(folders)).toEqual(['Disney 2026/Day 2', 'YouTube'])
  })
})

describe('completions', () => {
  it('announces rows that finished since the last poll, not ones already finished', () => {
    const prev = new Map<number, ImportStatus>([[1, 'downloading'], [2, 'probing'], [3, 'done'], [4, 'queued'], [5, 'probing']])
    const rows = [
      row({ id: 1, status: 'done', title: 'Holiday Parade' }),
      row({ id: 2, status: 'failed', url: 'https://www.youtube.com/watch?v=jNQXAC9IVRw' }),
      row({ id: 3, status: 'done', title: 'Old' }),
      row({ id: 4, status: 'probing' }),
      row({ id: 5, status: 'duplicate', title: 'Again' }),
      row({ id: 6, status: 'done', title: 'New to this page' }),
    ]
    expect(completions(prev, rows)).toEqual([
      'Imported Holiday Parade.',
      'Import failed: https://www.youtube.com/watch?v=jNQXAC9IVRw.',
      'Again is already in the library.',
    ])
  })
})
