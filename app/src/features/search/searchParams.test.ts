import { describe, expect, it } from 'vitest'
import { defaultParseSearch } from '@tanstack/react-router'
import {
  effectiveScope, fromState, includeFrom, showsBlocked, similarRightsOf, stringifySearch, toRequest, toState, validateSearch, withBlocked, withoutScope, withScope, withScopeFix,
} from './searchParams'

describe('search URL params', () => {
  it('validates and drops junk', () => {
    expect(validateSearch({ q: 'night', req: { shot_size: ['close_up', 3] }, f: { min_fps: 50, log: 'yes', orientation: 'vertical' }, group: 'x' })).toEqual({
      q: 'night', req: { shot_size: ['close_up'] }, f: { min_fps: 50, orientation: 'vertical' },
    })
  })
  it('round-trips state', () => {
    const p = { q: 'drone', req: { setting: ['coast'] }, f: { min_height: 2160 }, use: 'marketing', terr: 'GB' }
    expect(fromState(toState(p))).toEqual({ q: 'drone', req: { setting: ['coast'] }, exc: undefined, f: { min_height: 2160 }, use: 'marketing', ch: undefined, terr: 'GB' })
  })
  it('builds the core request with intended use and the default include', () => {
    expect(toRequest({ q: 'x', use: 'marketing' })).toEqual({ q: 'x', intended_use: { use: 'marketing', channel: null, territory: null, include: ['allowed', 'restricted', 'unknown'] }, hide_blocked: true })
    expect(includeFrom({ inc: 'all' })).toHaveLength(4)
    expect(includeFrom({ inc: 'allowed' })).toEqual(['allowed'])
    expect(toRequest({ similar: 's1', assets: 'a,b' })).toEqual({ q: '', similar_to: 's1', asset_uids: ['a', 'b'], hide_blocked: true })
  })
  it('hides blocked footage by default, with or without an intended use', () => {
    expect(toRequest({ q: 'x' }).hide_blocked).toBe(true)
    expect(toRequest({ q: 'x', blocked: 'show' }).hide_blocked).toBe(false)
    expect(toRequest({ q: 'x', use: 'marketing', blocked: 'show' }).intended_use?.include).toContain('blocked')
    // Older links: inc=all also shows blocked.
    expect(showsBlocked({ inc: 'all' })).toBe(true)
    expect(validateSearch({ blocked: 'show', strict: 'strict' })).toEqual({ blocked: 'show', strict: 'strict' })
    expect(validateSearch({ blocked: 'yes', strict: 'balanced' })).toEqual({})
  })
  it('toggles Hide blocked without losing the verdict choice', () => {
    expect(withBlocked({ q: 'x', inc: 'all' }, false)).toEqual({ q: 'x', inc: undefined, blocked: undefined })
    expect(withBlocked({ inc: 'allowed,blocked' }, false)).toEqual({ inc: 'allowed', blocked: undefined })
    expect(withBlocked({ inc: 'allowed' }, true)).toEqual({ inc: 'allowed', blocked: 'show' })
    expect(includeFrom(withBlocked({ inc: 'allowed' }, true))).toEqual(['allowed', 'blocked'])
  })
  it('puts strictness in the URL and the request', () => {
    expect(toRequest({ q: 'x', strict: 'strict' }).strictness).toBe('strict')
    expect(toRequest({ q: 'x' }).strictness).toBeUndefined()
  })
})

describe('search scope in the URL', () => {
  it('reads one or repeated folder= and collection= params', () => {
    expect(validateSearch({ folder: 'Disney 2026' })).toEqual({ folder: ['Disney 2026'] })
    expect(validateSearch({ folder: ['/a/sample', 2026, ''], collection: 'c1' })).toEqual({ folder: ['/a/sample', '2026'], collection: ['c1'] })
    expect(validateSearch({ folder: [] })).toEqual({})
  })
  it('writes repeated params that the router reads back', () => {
    const p = { q: 'night', folder: ['/home/demo/sample', 'Disney 2026'], collection: ['c1'], f: { min_fps: 25 } }
    const str = stringifySearch(p)
    expect(str).toContain('folder=%2Fhome%2Fdemo%2Fsample&folder=Disney+2026')
    expect(str).toContain('collection=c1')
    expect(validateSearch(defaultParseSearch(str))).toEqual(p)
    // A single numeric-looking name survives the round trip as text.
    expect(validateSearch(defaultParseSearch(stringifySearch({ folder: ['2026'] })))).toEqual({ folder: ['2026'] })
    expect(stringifySearch({ q: 'x' })).toBe('?q=x')
  })
  it('sends the scope in filters, beside the other filters', () => {
    expect(toRequest({ folder: ['sample'] }).filters).toEqual({ folder: ['sample'] })
    expect(toRequest({ q: 'x', f: { log: true }, collection: ['c1'] }).filters).toEqual({ log: true, collection: ['c1'] })
    expect(toRequest({ q: 'x' }).filters).toBeUndefined()
  })
  it('keeps the scope through chip edits and passes it to similar searches', () => {
    const p = { q: 'night folder:"extra"', folder: ['/a/sample'] }
    expect(fromState(toState(p), p).folder).toEqual(['/a/sample'])
    expect(effectiveScope(p)).toEqual({ folder: ['/a/sample', 'extra'], collection: [] })
    // Raw router search (not yet validated): a single folder= is a string.
    expect(effectiveScope({ folder: '/a/sample' } as never)).toEqual({ folder: ['/a/sample'], collection: [] })
    expect(similarRightsOf(p).scope).toEqual({ folder: ['/a/sample', 'extra'], collection: [] })
    expect(similarRightsOf({ q: 'x' }).scope).toBeUndefined()
  })
  it('changes and removes scopes from the URL or the words', () => {
    expect(withScope({ q: 'x', folder: ['a'] }, { collection: ['c1'] })).toEqual({ q: 'x', folder: undefined, collection: ['c1'] })
    expect(withoutScope({ folder: ['a', 'b'] }, 'folder', 'A')).toEqual({ folder: ['b'] })
    expect(withoutScope({ q: 'folder:"extra" night' }, 'folder', 'extra')).toEqual({ q: 'night' })
    expect(withoutScope({ q: 'night' }, 'folder', 'extra')).toBeNull()
  })
  it('replaces a folder that does not exist with the closest one', () => {
    expect(withScopeFix({ folder: ['Disney 2025'] }, 'folder', 'Disney 2025', 'Videos/Holidays/Disney 2026')).toEqual({ folder: ['Videos/Holidays/Disney 2026'] })
    expect(withScopeFix({ q: 'folder:"samples" night' }, 'folder', 'samples', 'sample')).toEqual({ q: 'night', folder: ['sample'] })
  })
})
