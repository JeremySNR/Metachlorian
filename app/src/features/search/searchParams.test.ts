import { describe, expect, it } from 'vitest'
import { fromState, includeFrom, showsBlocked, toRequest, toState, validateSearch, withBlocked } from './searchParams'

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
