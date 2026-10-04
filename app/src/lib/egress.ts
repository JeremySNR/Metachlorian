/**
 * Model-adapter egress (system.md §3.20). Whether an endpoint is local is decided by the core from the
 * host (loopback, private ranges, .local, or a name that resolves only to private addresses), never by a
 * self-declared flag: GET /api/admin/endpoint-locality?url=… → {url, local, reason}.
 */

export interface Locality {
  url: string
  local: boolean
  reason: string
}

export type LocalityState = 'unset' | 'checking' | 'local' | 'remote' | 'refused' | 'unchecked'

export interface LocalityBadge {
  state: LocalityState
  /** Badge text. */
  label: string
  tone: 'neutral' | 'caution'
  /** One line under the badge: the core's reason, in plain words. */
  detail: string | null
}

/** The host part of an endpoint URL ("api.openai.com"), or the input when it is not a URL. */
export function endpointHost(url: string): string {
  try {
    return new URL(url.trim()).host || url.trim()
  } catch {
    return url.trim()
  }
}

const REASONS: Record<string, string> = {
  'private address': 'this machine or a private network address',
  'public address': 'a public internet address',
  'local name': 'a local network name',
  'resolves to a private address': 'a name on your private network',
  'resolves to a public address': 'a public internet address',
  'name does not resolve': "a name that doesn't resolve here, so it is treated as remote",
  'no host': 'no host in the address',
}

/**
 * Badge for an adapter form, from the endpoint being typed and the core's classification of it.
 * A classification for a different URL (still in flight) counts as checking. Anything not confirmed
 * local by the core is treated as leaving the machine.
 */
export function localityBadge(input: { baseUrl: string; locality?: Locality | null; error?: boolean; allowRemote: boolean }): LocalityBadge {
  const url = input.baseUrl.trim()
  if (!url) return { state: 'unset', label: 'Not configured', tone: 'neutral', detail: null }
  const fresh = input.locality && input.locality.url.trim() === url ? input.locality : null
  if (!fresh) {
    if (input.error) return { state: 'unchecked', label: 'Leaves this machine', tone: 'caution', detail: "Couldn't check this address, so it is treated as remote." }
    return { state: 'checking', label: 'Checking address…', tone: 'neutral', detail: null }
  }
  const why = REASONS[fresh.reason] ?? fresh.reason
  if (fresh.local) return { state: 'local', label: 'Local', tone: 'neutral', detail: `${endpointHost(url)} is ${why}.` }
  return {
    state: input.allowRemote ? 'remote' : 'refused',
    label: input.allowRemote ? 'Leaves this machine' : 'Hosted, refused',
    tone: 'caution',
    detail: `${endpointHost(url)} is ${why}.${input.allowRemote ? '' : ' Hosted adapters are off, so it will not be used.'}`,
  }
}

/** Saving an endpoint the core does not classify as local needs the §3.20 confirmation. */
export function needsEgressConfirm(baseUrl: string, locality: Locality | null | undefined): boolean {
  if (!baseUrl.trim()) return false
  return !(locality && locality.url.trim() === baseUrl.trim() && locality.local)
}
