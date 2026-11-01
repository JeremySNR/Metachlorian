import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { api } from './client'

export type Photo = {
  uid: string
  filename: string
  capture_time: string | null
  width: number | null
  height: number | null
  rating: number
  availability: string
  status: string
  revision: string
  burst_id: string | null
  is_virtual: boolean
  copy_name: string
  why?: { uncertainty: string[]; visual_review_required: boolean }
}
export type PhotoDetail = Photo & {
  metadata: Record<string, unknown>
  keywords: string[]
  evidence: {
    uncertainty?: string[]; width?: number; height?: number
    provenance?: { source?: string; native_resolution?: boolean }
    exposure?: { render_highlights_fraction: number; render_shadows_fraction: number }
    global_sharpness?: { gradient_energy?: number }
    composition?: { bright_border_fraction?: number; horizontal_line_angles?: number[] }
    crop_candidates?: { reason: string }[]
    models?: Record<string, string>
    faces?: { evidence?: { eyes?: { available: boolean }[] } }[]
  }
  faces: { id: number; box: number[]; name: string | null; identity_id: number | null; stale?: boolean }[]
  variants: { uid: string; is_virtual: boolean; copy_name: string }[]
}
export type PhotoStatus = {
  enabled: boolean
  counts: Record<string, number>
  cache: { bytes: number; budget_bytes: number; files: number }
  database_bytes: number
  catalogs: { uid: string; name: string; last_sync: number | null }[]
  lightroom: {
    connected: boolean; can_edit: boolean; editing_supported: boolean; busy?: boolean
    catalog?: { name: string; version: string }; message: string; label: string
    connector_version?: string; update_available: boolean; checked_at?: number; last_connected_at?: number
  }
  coverage: { total: number; analysed: number; needs_attention: number; linked: number; folder_only: number }
  connector: { path: string; files_copied: boolean; files_current: boolean; bundled_version: string; ports: number[] }
  decoders: { raw: { available: boolean }; heic: { available: boolean } }
  agent: { endpoint: string; can_edit: boolean; can_save_collection: boolean; required_scopes: string[] }
  models: { name: string; installed: boolean; size_mb: number }[]
  validation: string
}
export type PhotoContext = { photo_id: string; revision: string; availability?: string; import_on_edit?: boolean; workflow: { state: string; reason?: string }; capabilities: { editing: boolean; reason?: string } }
export type PhotoSession = { session_id: string; photo_id: string; source_photo_id?: string; revision: string; baseline_snapshot?: string }
export type PhotoJob = {
  uid: string
  kind: string
  status: 'queued' | 'running' | 'done' | 'waiting' | 'conflict' | 'failed' | 'cancelled'
  error: string | null
  result: {
    processed?: number; total?: number; unavailable?: number; collection?: string
    current_model?: string; downloaded_bytes?: number; total_bytes?: number
    sessions?: PhotoSession[]; accepted?: { photo_id: string; session_id: string }[]
    session_id?: string; photo_id?: string; revision?: string
  }
}
type PhotoResults = { results: Photo[]; total: number; next_cursor: string | null; semantic_available: boolean }

export const usePhotoStatus = () => useQuery({ queryKey: ['photos', 'status'], queryFn: () => api.get<PhotoStatus>('/api/photos/status'), refetchInterval: 10_000, retry: false })
export const usePhotoJobs = (enabled: boolean) => useQuery({ queryKey: ['photos', 'jobs'], queryFn: () => api.get<{ jobs: PhotoJob[] }>('/api/photos/jobs'), enabled, refetchInterval: 2500 })
export const usePhoto = (uid: string | null) => useQuery({ queryKey: ['photos', 'detail', uid], queryFn: () => api.get<PhotoDetail>(`/api/photos/${uid}`), enabled: Boolean(uid) })
export const usePhotoSearch = (query: string, filters: Record<string, string | number | boolean>, diverse: boolean, enabled: boolean) => useInfiniteQuery({
  queryKey: ['photos', 'search', query, filters, diverse],
  queryFn: ({ pageParam }) => api.post<PhotoResults>('/api/photos/search', { query, filters, diverse, limit: 40, cursor: pageParam }),
  initialPageParam: null as string | null,
  getNextPageParam: (page) => page.next_cursor ?? undefined,
  enabled,
  refetchInterval: 15_000,
})

export function photoPreview(uid: string, edge = 600, revision?: string, region?: number[], native = false) {
  const params = new URLSearchParams({ edge: String(edge) })
  if (revision) params.set('revision', revision)
  if (region) params.set('region', region.join(','))
  if (native) params.set('native', 'true')
  return `/api/photos/${encodeURIComponent(uid)}/preview?${params}`
}

export const photoRequestKey = () => crypto.randomUUID()
