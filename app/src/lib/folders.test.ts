import { describe, expect, it } from 'vitest'
import { buildFolderTree, dirname, editStageCounts, flattenTree, folderCrumbs, formatDateRange, formatHours } from './folders'

const f = (path: string, source: string) => {
  const root = source.split('/').pop() as string
  const relative = path === source ? root : `${root}/${path.slice(source.length + 1)}`
  return { path, name: path.split('/').pop() as string, relative, source, depth: relative.split('/').length - 1 }
}

const SRC = '/Volumes/Videos'
const LIST = [f(SRC, SRC), f(`${SRC}/Holidays`, SRC), f(`${SRC}/Holidays/Disney 2026`, SRC), f(`${SRC}/Holidays/Disney 2026/Day 2`, SRC), f(`${SRC}/Work`, SRC), f('/data/sample', '/data/sample')]

describe('folder tree', () => {
  it('nests folders under their nearest listed ancestor, keeping order', () => {
    const tree = buildFolderTree(LIST)
    expect(tree.map((n) => n.folder.name)).toEqual(['Videos', 'sample'])
    expect(tree[0].children.map((n) => n.folder.name)).toEqual(['Holidays', 'Work'])
    expect(tree[0].children[0].children[0].children[0].folder.name).toBe('Day 2')
  })
  it('makes orphans (missing ancestors) top-level and skips a missing middle', () => {
    const tree = buildFolderTree([f(`${SRC}/Holidays/Disney 2026`, SRC), f(`${SRC}/Holidays/Disney 2026/Day 2`, SRC), f(SRC, SRC)])
    expect(tree.map((n) => n.folder.name)).toEqual(['Videos'])
    expect(tree[0].children[0].folder.name).toBe('Disney 2026')
    expect(tree[0].children[0].children[0].folder.name).toBe('Day 2')
    const orphans = buildFolderTree([f(`${SRC}/Holidays/Disney 2026`, SRC), f(`${SRC}/Work`, SRC)])
    expect(orphans.map((n) => n.folder.name)).toEqual(['Disney 2026', 'Work'])
  })
  it('flattens only expanded branches, with levels', () => {
    const tree = buildFolderTree(LIST)
    expect(flattenTree(tree, new Set()).map((r) => r.folder.name)).toEqual(['Videos', 'sample'])
    const rows = flattenTree(tree, new Set([SRC, `${SRC}/Holidays`]))
    expect(rows.map((r) => `${r.level}:${r.folder.name}`)).toEqual(['0:Videos', '1:Holidays', '2:Disney 2026', '1:Work', '0:sample'])
    expect(rows[2].hasChildren).toBe(true)
    expect(rows[2].expanded).toBe(false)
  })
})

describe('folder breadcrumbs', () => {
  it('runs from the source root with absolute paths', () => {
    expect(folderCrumbs(`${SRC}/Holidays/Disney 2026`, LIST)).toEqual([
      { name: 'Videos', path: SRC },
      { name: 'Holidays', path: `${SRC}/Holidays` },
      { name: 'Disney 2026', path: `${SRC}/Holidays/Disney 2026` },
    ])
    expect(folderCrumbs('/data/sample/', LIST)).toEqual([{ name: 'sample', path: '/data/sample' }])
  })
  it('finds the root by prefix for folders not in the list, and falls back to the name', () => {
    expect(folderCrumbs(`${SRC}/New/Thing`, LIST).map((c) => c.name)).toEqual(['Videos', 'New', 'Thing'])
    expect(folderCrumbs('/elsewhere/clips', LIST)).toEqual([{ name: 'clips', path: '/elsewhere/clips' }])
    expect(dirname('/data/sample/a.mp4')).toBe('/data/sample')
  })
})

describe('dates, length and edit stages', () => {
  it('formats shoot-date ranges compactly', () => {
    expect(formatDateRange('2026-08-03', '2026-08-14')).toBe('3–14 Aug 2026')
    expect(formatDateRange('2026-07-28', '2026-08-03')).toBe('28 Jul – 3 Aug 2026')
    expect(formatDateRange('2013-10-20', '2026-10-04')).toBe('20 Oct 2013 – 4 Oct 2026')
    expect(formatDateRange('2026-08-03', '2026-08-03')).toBe('3 Aug 2026')
    expect(formatDateRange('2026-08-03T10:00:00Z', null)).toBe('3 Aug 2026')
    expect(formatDateRange(null, undefined)).toBe('')
  })
  it('formats footage length', () => {
    expect(formatHours(0.125)).toBe('8 min')
    expect(formatHours(0.005)).toBe('Under 1 min')
    expect(formatHours(1.54)).toBe('1.5 h')
    expect(formatHours(12.4)).toBe('12 h')
    expect(formatHours(0)).toBe('0 min')
  })
  it('counts edit stages per file, unclassified last', () => {
    expect(editStageCounts([{ edit_type: { term: 'raw' } }, { edit_type: null }, { edit_type: 'finished' }, { edit_type: { term: 'raw' } }])).toEqual([
      { term: 'raw', count: 2 },
      { term: 'finished', count: 1 },
      { term: null, count: 1 },
    ])
  })
})
