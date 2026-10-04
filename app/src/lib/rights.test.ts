import { describe, expect, it } from 'vitest'
import { describeRights, stateFromBadge, usesOnly } from './rights'

describe('rights text', () => {
  it('leads with the most restrictive fact', () => {
    const rec = { permitted_uses: ['editorial'], expires: '2026-10-24' }
    expect(describeRights('expiring', rec).short).toBe('Editorial only · expires 24 Oct')
    expect(describeRights('expiring', rec).long).toMatch(/^Editorial use only · licence expires 24 Oct 2026/)
    expect(describeRights('expiring', { expires: '2026-10-24' }).short).toBe('Expires 24 Oct')
    expect(describeRights('cleared', { permitted_uses: ['editorial', 'internal'] }).short).toBe('Editorial and internal only')
    expect(describeRights('cleared', { permitted_uses: ['commercial', 'editorial', 'marketing'] }).short).toBe('Cleared')
  })
  it('names narrow scopes only', () => {
    expect(usesOnly(null)).toBeNull()
    expect(usesOnly({ permitted_uses: [] })).toBeNull()
    expect(usesOnly({ permitted_uses: ['editorial'] })).toBe('Editorial only')
  })
  it('maps not cleared to blocked', () => {
    expect(stateFromBadge('not_cleared')).toBe('blocked')
    expect(stateFromBadge(undefined)).toBe('unknown')
  })
})
