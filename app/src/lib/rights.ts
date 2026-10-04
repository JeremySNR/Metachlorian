/**
 * Rights display model (system.md §3.9). Maps API badges and verdicts to the six
 * UI states. "Expiring" is derived on the client (≤ 30 days). Unknown is never
 * treated as cleared.
 */
import type { RightsBadge, RightsRecord, Verdict } from '../api/types'
import { daysUntil, formatDate, formatDayMonth, humanise } from './format'

export type RightsState = 'cleared' | 'restricted' | 'expiring' | 'expired' | 'blocked' | 'unknown'

export const RIGHTS_SHORT: Record<RightsState, string> = {
  cleared: 'Cleared',
  restricted: 'Restricted',
  expiring: 'Expires',
  expired: 'Expired',
  blocked: 'Blocked',
  unknown: 'Rights unknown',
}

export function stateFromBadge(badge: RightsBadge | null | undefined): RightsState {
  switch (badge) {
    case 'cleared':
    case 'restricted':
    case 'expiring':
    case 'expired':
      return badge
    case 'not_cleared':
      return 'blocked'
    default:
      return 'unknown'
  }
}

export function stateFromVerdict(verdict: Verdict | null | undefined, reasons: string[] = [], expires?: string | null): RightsState {
  switch (verdict) {
    case 'allowed':
    case 'restricted': {
      const d = daysUntil(expires)
      if (d !== null && d >= 0 && d <= 30) return 'expiring'
      return verdict === 'allowed' ? 'cleared' : 'restricted'
    }
    case 'blocked':
      return reasons.some((r) => /expired/i.test(r)) ? 'expired' : 'blocked'
    default:
      return 'unknown'
  }
}

export interface RightsDisplay {
  state: RightsState
  short: string
  long: string
}

/**
 * The narrowest use a record allows, when it is narrow enough to be the headline
 * ("Editorial only", "Editorial and internal only"); null for broad or unknown scopes.
 */
export function usesOnly(record?: Partial<RightsRecord> | null): string | null {
  const uses = record?.permitted_uses ?? []
  if (!uses.length || uses.length > 2) return null
  const words = uses.map((u) => humanise(u).toLowerCase())
  const text = words.length === 1 ? words[0] : `${words[0]} and ${words[1]}`
  return `${text.charAt(0).toUpperCase()}${text.slice(1)} only`
}

/** Short and long text for a state, given the record (when known) and reasons. The most restrictive fact comes first. */
export function describeRights(state: RightsState, record?: Partial<RightsRecord> | null, reasons: string[] = []): RightsDisplay {
  const exp = record?.expires ?? null
  const first = reasons.find((r) => !/^Cleared/.test(r))
  const only = usesOnly(record)
  switch (state) {
    case 'cleared': {
      const scope = record?.permitted_uses?.length ? `for ${record.permitted_uses.join(', ')}` : 'for all uses'
      return { state, short: only ?? 'Cleared', long: `Cleared ${scope}${exp ? ` · expires ${formatDate(exp)}` : ''}` }
    }
    case 'restricted':
      return { state, short: 'Restricted', long: `Restricted${first ? `: ${first.replace(/\.$/, '')}` : ''}` }
    case 'expiring': {
      const d = daysUntil(exp)
      const when = exp ? `expires ${formatDayMonth(exp)}` : 'expiring'
      const short = only ? `${only} · ${when}` : `${when.charAt(0).toUpperCase()}${when.slice(1)}`
      const long = exp ? `Licence expires ${formatDate(exp)}${d !== null ? ` (${d} day${d === 1 ? '' : 's'})` : ''}` : 'Licence expires soon'
      return { state, short, long: only ? `${only.replace(/ only$/, ' use only')} · ${long.charAt(0).toLowerCase()}${long.slice(1)}` : long }
    }
    case 'expired':
      return { state, short: 'Expired', long: exp ? `Licence expired ${formatDate(exp)}` : 'Licence expired' }
    case 'blocked':
      return { state, short: 'Blocked', long: `Blocked${first ? `: ${first.replace(/\.$/, '')}` : record?.status === 'not_cleared' ? ': marked as not cleared' : ''}` }
    default:
      return { state, short: 'Rights unknown', long: 'No rights information yet' }
  }
}

/** Agents only ever see cleared shots (ADR 011). */
export function agentsVisible(state: RightsState): boolean {
  return state === 'cleared' || state === 'expiring'
}

export const RIGHTS_STATUS_LABEL: Record<string, string> = {
  cleared: 'Cleared',
  restricted: 'Restricted',
  not_cleared: 'Not cleared (blocked)',
  unknown: 'Unknown',
}

/** ISO 3166-1 alpha-2 codes offered first in territory pickers (any code may be typed). */
export const COMMON_TERRITORIES: [string, string][] = [
  ['WW', 'Worldwide'],
  ['GB', 'United Kingdom'],
  ['IE', 'Ireland'],
  ['US', 'United States'],
  ['CA', 'Canada'],
  ['AU', 'Australia'],
  ['NZ', 'New Zealand'],
  ['DE', 'Germany'],
  ['FR', 'France'],
  ['ES', 'Spain'],
  ['PT', 'Portugal'],
  ['IT', 'Italy'],
  ['NL', 'Netherlands'],
  ['SE', 'Sweden'],
  ['NO', 'Norway'],
  ['DK', 'Denmark'],
  ['JP', 'Japan'],
  ['SG', 'Singapore'],
  ['AE', 'United Arab Emirates'],
  ['ZA', 'South Africa'],
  ['IN', 'India'],
  ['BR', 'Brazil'],
  ['MX', 'Mexico'],
]
