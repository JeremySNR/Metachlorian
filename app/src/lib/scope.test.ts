import { describe, expect, it } from 'vitest'
import {
  chipsToScope, collectionLabel, folderLabel, mergeScopes, parseScopeNote, scopeChips, scopeList, scopePhrase, scopeQueryParams, scopeToken, scopeTokens, stripScopeToken,
} from './scope'

describe('scope values', () => {
  it('cleans URL and response values into lists', () => {
    expect(scopeList('Disney 2026')).toEqual(['Disney 2026'])
    expect(scopeList(2026)).toEqual(['2026'])
    expect(scopeList(['a', ' a ', '', 3, null, { x: 1 }])).toEqual(['a', '3'])
    expect(scopeList(undefined)).toBeUndefined()
    expect(scopeList([])).toBeUndefined()
  })
  it('merges without duplicates (case-insensitive)', () => {
    expect(mergeScopes({ folder: ['sample'] }, { folder: ['Sample', 'extra'], collection: ['c1'] })).toEqual({ folder: ['sample', 'extra'], collection: ['c1'] })
  })
})

describe('folder:"…" in the query text', () => {
  it('reads quoted and bare tokens like the core', () => {
    expect(scopeTokens('folder:"Disney 2026" night collection:Kids')).toEqual({ folder: ['Disney 2026'], collection: ['Kids'] })
    expect(scopeTokens('night at the folder')).toEqual({ folder: [], collection: [] })
  })
  it('removes one token and tidies the words', () => {
    expect(stripScopeToken('folder:"extra" night', 'folder', 'extra')).toBe('night')
    expect(stripScopeToken('night FOLDER: sample close-ups', 'folder', 'Sample')).toBe('night close-ups')
    expect(stripScopeToken('night', 'folder', 'extra')).toBeNull()
    expect(stripScopeToken('collection:"a b" folder:"a b"', 'folder', 'a b')).toBe('collection:"a b"')
  })
  it('writes tokens, quoting names with spaces', () => {
    expect(scopeToken('folder', 'Disney 2026')).toBe('folder:"Disney 2026"')
    expect(scopeToken('collection', 'Selects')).toBe('collection:Selects')
  })
})

describe('scope chips from the URL and query.filters', () => {
  it('lists chosen scopes, then ones the core read from the words', () => {
    const chips = scopeChips({ folder: ['/data/sample'], collection: [] }, { folder: ['extra', '/data/sample'], collection: 'Kids on rides' })
    expect(chips.map((c) => [c.kind, c.value, c.typed])).toEqual([
      ['folder', '/data/sample', false],
      ['folder', 'extra', true],
      ['collection', 'Kids on rides', true],
    ])
    expect(chipsToScope(chips)).toEqual({ folder: ['/data/sample', 'extra'], collection: ['Kids on rides'] })
  })
  it('has no chips without a scope', () => {
    expect(scopeChips({}, { min_fps: 25 } as never)).toEqual([])
  })
})

describe('labels and the count line', () => {
  const folders = [{ path: '/v/Holidays/Disney 2026', name: 'Disney 2026', relative: 'v/Holidays/Disney 2026' }]
  const cols = [{ uid: 'c1', name: 'Kids on rides' }]
  it('names folders and collections', () => {
    expect(folderLabel('/v/Holidays/Disney 2026', folders)).toBe('Disney 2026')
    expect(folderLabel('v/holidays/disney 2026', folders)).toBe('Disney 2026')
    expect(folderLabel('Holidays/Disney 2025/')).toBe('Disney 2025')
    expect(collectionLabel('c1', cols)).toBe('Kids on rides')
    expect(collectionLabel('kids on rides', cols)).toBe('Kids on rides')
    expect(collectionLabel('Other', cols)).toBe('Other')
  })
  it('says the scope in words', () => {
    const fl = (v: string) => folderLabel(v, folders)
    const cl = (v: string) => collectionLabel(v, cols)
    expect(scopePhrase({ folder: ['/v/Holidays/Disney 2026'], collection: [] }, fl, cl)).toBe('in Disney 2026')
    expect(scopePhrase({ folder: [], collection: ['c1'] }, fl, cl)).toBe('in collection Kids on rides')
    expect(scopePhrase({ folder: ['a', 'b'], collection: [] }, fl, cl)).toBe('in a and b')
    expect(scopePhrase({ folder: ['a', 'b', 'c'], collection: ['c1'] }, fl, cl)).toBe('in 3 folders, collection Kids on rides')
    expect(scopePhrase({ folder: [], collection: [] }, fl, cl)).toBeNull()
  })
})

describe('the core notes', () => {
  it('reads the missing name and the closest folders', () => {
    expect(parseScopeNote('No folder called "Disney 2025". Closest: Videos/Holidays/Disney 2026.')).toEqual({ kind: 'folder', missing: 'Disney 2025', closest: ['Videos/Holidays/Disney 2026'] })
    expect(parseScopeNote('No folder called "x".')).toEqual({ kind: 'folder', missing: 'x', closest: [] })
    expect(parseScopeNote('No collection called "nope".')?.kind).toBe('collection')
    expect(parseScopeNote('Nobody called "Sam" has been named yet.')).toBeNull()
  })
  it('builds repeated query params for the similar endpoints', () => {
    expect(scopeQueryParams({ folder: ['a', 'b'], collection: ['c'] })).toEqual([['folder', 'a'], ['folder', 'b'], ['collection', 'c']])
  })
})
