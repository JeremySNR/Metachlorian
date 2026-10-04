import { describe, expect, it } from 'vitest'
import { fromState, includeFrom, toRequest, toState, validateSearch } from './searchParams'

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
    expect(toRequest({ q: 'x', use: 'marketing' })).toEqual({ q: 'x', intended_use: { use: 'marketing', channel: null, territory: null, include: ['allowed', 'restricted', 'unknown'] } })
    expect(includeFrom({ inc: 'all' })).toHaveLength(4)
    expect(includeFrom({ inc: 'allowed' })).toEqual(['allowed'])
    expect(toRequest({ similar: 's1', assets: 'a,b' })).toEqual({ q: '', similar_to: 's1', asset_uids: ['a', 'b'] })
  })
})
