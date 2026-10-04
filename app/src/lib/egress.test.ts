import { describe, expect, it } from 'vitest'
import { endpointHost, localityBadge, needsEgressConfirm } from './egress'

const openai = { url: 'https://api.openai.com/v1', local: false, reason: 'resolves to a public address' }
const loop = { url: 'http://127.0.0.1:8080/v1', local: true, reason: 'private address' }

describe('model-adapter locality badge', () => {
  it('is "not configured" without an endpoint', () => {
    expect(localityBadge({ baseUrl: '  ', allowRemote: true }).state).toBe('unset')
  })
  it('says checking until the core has classified this exact URL', () => {
    expect(localityBadge({ baseUrl: 'https://api.openai.com/v1', allowRemote: true }).state).toBe('checking')
    // A stale answer for the previous URL does not count.
    expect(localityBadge({ baseUrl: 'https://api.openai.com/v1', locality: loop, allowRemote: true }).state).toBe('checking')
  })
  it('never labels a public host local', () => {
    const b = localityBadge({ baseUrl: 'https://api.openai.com/v1', locality: openai, allowRemote: true })
    expect(b).toMatchObject({ state: 'remote', label: 'Leaves this machine', tone: 'caution' })
    expect(b.detail).toContain('api.openai.com')
    expect(localityBadge({ baseUrl: 'https://api.openai.com/v1', locality: openai, allowRemote: false })).toMatchObject({ state: 'refused', label: 'Hosted, refused' })
  })
  it('labels a host the core classifies as private local', () => {
    expect(localityBadge({ baseUrl: 'http://127.0.0.1:8080/v1', locality: loop, allowRemote: false })).toMatchObject({ state: 'local', label: 'Local', tone: 'neutral' })
  })
  it('treats a failed check as remote', () => {
    expect(localityBadge({ baseUrl: 'http://x', error: true, allowRemote: true })).toMatchObject({ state: 'unchecked', tone: 'caution' })
  })
})

describe('egress confirmation', () => {
  it('is needed for anything not confirmed local', () => {
    expect(needsEgressConfirm('https://api.openai.com/v1', openai)).toBe(true)
    expect(needsEgressConfirm('https://api.openai.com/v1', null)).toBe(true)
    expect(needsEgressConfirm('https://api.openai.com/v1', loop)).toBe(true)
    expect(needsEgressConfirm('http://127.0.0.1:8080/v1', loop)).toBe(false)
    expect(needsEgressConfirm('', null)).toBe(false)
  })
  it('extracts the host', () => {
    expect(endpointHost('https://api.openai.com/v1')).toBe('api.openai.com')
    expect(endpointHost('not a url')).toBe('not a url')
  })
})
