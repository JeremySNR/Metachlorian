/**
 * Typed fetch wrapper for the core's REST API.
 *
 * Every non-GET request carries `X-Metachlorian: 1` (the core's CSRF rule for
 * cookie and solo-mode sessions). Errors surface as ApiError with the core's
 * `detail` message, which is already written for people.
 */
export class ApiError extends Error {
  status: number
  detail: string
  id: string
  constructor(status: number, detail: string) {
    super(detail || `Request failed (${status})`)
    this.status = status
    this.detail = detail
    this.id = `E${Date.now().toString(36).toUpperCase()}-${status}`
  }
}

/** Base URL of the core. The web app and the desktop shell both load the UI from the core, so it is same-origin. */
export function coreBase(): string {
  return ''
}

export function mediaUrl(path: string | null | undefined): string | undefined {
  if (!path) return undefined
  if (/^(https?:|blob:|data:|mc-media:)/.test(path)) return path
  return `${coreBase()}${path}`
}

type Json = Record<string, unknown> | unknown[]

async function request<T>(method: string, path: string, body?: Json | FormData, signal?: AbortSignal): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (method !== 'GET' && method !== 'HEAD') headers['X-Metachlorian'] = '1'
  let payload: BodyInit | undefined
  if (body instanceof FormData) payload = body
  else if (body !== undefined) {
    headers['Content-Type'] = 'application/json'
    payload = JSON.stringify(body)
  }
  let res: Response
  try {
    res = await fetch(`${coreBase()}${path}`, { method, headers, body: payload, signal, credentials: 'same-origin' })
  } catch (e) {
    if ((e as Error).name === 'AbortError') throw e
    throw new ApiError(0, navigator.onLine ? "Metachlorian didn't respond. Check that the core is running." : "You're offline.")
  }
  if (!res.ok) {
    let detail: string
    try {
      const j = await res.json()
      detail = typeof j.detail === 'string' ? j.detail : JSON.stringify(j.detail)
    } catch {
      detail = res.statusText
    }
    throw new ApiError(res.status, detail)
  }
  if (res.status === 204) return undefined as T
  const type = res.headers.get('content-type') ?? ''
  return (type.includes('json') ? res.json() : res.text()) as Promise<T>
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>('GET', path, undefined, signal),
  post: <T>(path: string, body?: Json | FormData, signal?: AbortSignal) => request<T>('POST', path, body ?? {}, signal),
  put: <T>(path: string, body: Json | FormData) => request<T>('PUT', path, body),
  patch: <T>(path: string, body: Json) => request<T>('PATCH', path, body),
  del: <T>(path: string) => request<T>('DELETE', path),
}

/** Build a query string, dropping empty values. */
export function qs(params: Record<string, string | number | boolean | null | undefined>): string {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== null && v !== '') p.set(k, String(v))
  const s = p.toString()
  return s ? `?${s}` : ''
}

/**
 * Upload with progress (fetch has no upload progress). Resolves with the JSON body.
 */
export function upload<T>(path: string, form: FormData, onProgress?: (fraction: number) => void): Promise<T> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${coreBase()}${path}`)
    xhr.setRequestHeader('X-Metachlorian', '1')
    xhr.responseType = 'json'
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable) onProgress?.(e.loaded / e.total)
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve(xhr.response as T)
      else reject(new ApiError(xhr.status, (xhr.response && xhr.response.detail) || xhr.statusText))
    }
    xhr.onerror = () => reject(new ApiError(0, "The upload didn't reach Metachlorian."))
    xhr.send(form)
  })
}
