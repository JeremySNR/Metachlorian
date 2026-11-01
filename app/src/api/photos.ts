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
  evidence: { uncertainty?: string[]; exposure?: { render_highlights_fraction: number; render_shadows_fraction: number } }
  faces: { id: number; box: number[]; name: string | null; identity_id: number | null; stale?: boolean }[]
  variants: { uid: string; is_virtual: boolean; copy_name: string }[]
}
export type PhotoStatus = {
  enabled: boolean
  counts: Record<string, number>
  cache: { bytes: number; budget_bytes: number; files: number }
  database_bytes: number
  catalogs: { uid: string; name: string; last_sync: number | null }[]
  lightroom: { connected: boolean; catalog?: { name: string }; message?: string }
  models: { name: string; installed: boolean; size_mb: number }[]
  validation: string
}
export type PhotoContext = { photo_id: string; revision: string; availability?: string; import_on_edit?: boolean }
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
