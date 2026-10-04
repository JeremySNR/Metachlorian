/**
 * TanStack Query hooks over the core API. Server state lives here; components
 * never fetch directly.
 */
import { keepPreviousData, QueryClient, useInfiniteQuery, useMutation, useQueries, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useMemo } from 'react'
import { api, qs } from './client'
import type {
  AdminSettings, AssetDoc, AssetList, AuditEntry, Collection, CollectionSummary, CorrectionsResponse, ExportClipResult, ExportMode,
  Health, IntendedUse, LibraryStats, Me, PackageResult, PackageTarget, Processing, RightsCheck, RightsRecord, SearchRequest,
  SearchResponse, ShotDoc, Source, Sprites, TokensResponse, User, Verdict, Vocabulary,
} from './types'
import { humanise, shortLabel } from '../lib/format'
import type { Locality } from '../lib/egress'

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1, refetchOnWindowFocus: false },
  },
})

export const PAGE_SIZE = 120

// ---------------------------------------------------------------- session
export const useHealth = () => useQuery({ queryKey: ['health'], queryFn: () => api.get<Health>('/api/health'), staleTime: 15_000, refetchInterval: 30_000 })
export const useMe = () => useQuery({ queryKey: ['me'], queryFn: () => api.get<Me>('/api/me'), staleTime: Infinity })

// ---------------------------------------------------------------- vocabularies
export const useVocabList = () =>
  useQuery({
    queryKey: ['vocab'],
    queryFn: () => api.get<{ version: string; vocabularies: Record<string, { version: string; description: string; multi: boolean; terms: number }> }>('/api/vocab'),
    staleTime: Infinity,
  })

export const useVocab = (name: string | null | undefined) =>
  useQuery({ queryKey: ['vocab', name], queryFn: () => api.get<Vocabulary>(`/api/vocab/${name}`), enabled: Boolean(name), staleTime: Infinity })

/** All vocabularies, plus a label function: (vocab, term) → "Close-up". */
export function useVocabularies() {
  const list = useVocabList()
  const names = useMemo(() => Object.keys(list.data?.vocabularies ?? {}), [list.data])
  const results = useQueries({
    queries: names.map((n) => ({ queryKey: ['vocab', n], queryFn: () => api.get<Vocabulary>(`/api/vocab/${n}`), staleTime: Infinity })),
  })
  const stamp = results.map((r) => r.dataUpdatedAt).join(',')
  const vocabs = useMemo(() => {
    const out: Record<string, Vocabulary> = {}
    results.forEach((r, i) => {
      if (r.data) out[names[i]] = r.data
    })
    return out
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stamp, names])
  const label = useCallback(
    (vocab: string, term: string) => {
      const t = vocabs[vocab]?.terms.find((x) => x.id === term)
      return t ? shortLabel(t.label) : humanise(term)
    },
    [vocabs],
  )
  return { vocabs, label, ready: names.length > 0 && results.every((r) => r.data) }
}

// ---------------------------------------------------------------- search
export function useSearch(req: SearchRequest | null) {
  return useInfiniteQuery({
    queryKey: ['search', req],
    enabled: req !== null,
    initialPageParam: null as string | null,
    queryFn: ({ pageParam, signal }) => api.post<SearchResponse>('/api/search', { ...req, cursor: pageParam, limit: PAGE_SIZE, facets: pageParam === null }, signal),
    getNextPageParam: (last) => last.next_cursor,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  })
}

/** Rights options for similar-shot searches: the same verdict, intended use and Hide blocked as search. */
export interface SimilarRights {
  use?: string | null
  channel?: string | null
  territory?: string | null
  include?: Verdict[] | null
  hideBlocked?: boolean
}

function similarQs(limit: number, r: SimilarRights = {}) {
  return qs({ limit, use: r.use, channel: r.channel, territory: r.territory, include: r.include?.length ? r.include.join(',') : undefined, hide_blocked: r.hideBlocked === false ? 'false' : undefined })
}

export const useSimilar = (uid: string | null | undefined, limit = 24, rights: SimilarRights = {}) =>
  useQuery({ queryKey: ['similar', uid, limit, rights], queryFn: () => api.get<SearchResponse>(`/api/shots/${uid}/similar${similarQs(limit, rights)}`), enabled: Boolean(uid), staleTime: 5 * 60_000 })

export function searchByExample(file: File, limit = 120, rights: SimilarRights = {}) {
  const form = new FormData()
  form.append('file', file)
  return api.post<SearchResponse>(`/api/similar${similarQs(limit, rights)}`, form)
}

// ---------------------------------------------------------------- shots and assets
export const shotQuery = (uid: string, use?: IntendedUse | null) => ({
  queryKey: ['shot', uid, use?.use ?? null, use?.channel ?? null, use?.territory ?? null],
  queryFn: () => api.get<ShotDoc>(`/api/shots/${uid}${qs({ use: use?.use, channel: use?.channel, territory: use?.territory })}`),
  staleTime: 60_000,
})

export const useShot = (uid: string | null | undefined, use?: IntendedUse | null) =>
  useQuery({ ...shotQuery(uid ?? '', use), enabled: Boolean(uid), placeholderData: keepPreviousData })

export const assetQuery = (uid: string) => ({
  queryKey: ['asset', uid],
  queryFn: () => api.get<AssetDoc>(`/api/assets/${uid}`),
  staleTime: 60_000,
})

export const useAsset = (uid: string | null | undefined, opts: { refetchInterval?: number | false } = {}) =>
  useQuery({ ...assetQuery(uid ?? ''), enabled: Boolean(uid), refetchInterval: opts.refetchInterval })

/** Sprite metadata for a file (from the asset record), cached for the session. */
export function useSprites(assetUid: string | null | undefined) {
  return useQuery({ ...assetQuery(assetUid ?? ''), enabled: Boolean(assetUid), staleTime: 10 * 60_000, select: (a: AssetDoc): Sprites | null => a.media?.sprites ?? null })
}

export function ensureSprites(assetUid: string): Promise<Sprites | null> {
  return queryClient.ensureQueryData({ ...assetQuery(assetUid), staleTime: 10 * 60_000 }).then((a) => a.media?.sprites ?? null)
}

export const useAssets = (params: { q?: string; edit_type?: string; status?: string; limit?: number; offset?: number } = {}) =>
  useQuery({ queryKey: ['assets', params], queryFn: () => api.get<AssetList>(`/api/assets${qs({ limit: 500, ...params })}`), placeholderData: keepPreviousData })

export const useLibraryStats = (opts: { refetchInterval?: number | false } = {}) =>
  useQuery({ queryKey: ['stats'], queryFn: () => api.get<LibraryStats>('/api/library/stats'), refetchInterval: opts.refetchInterval, staleTime: 10_000 })

// ---------------------------------------------------------------- corrections
export const useCorrections = (assetUid?: string) =>
  useQuery({ queryKey: ['corrections', assetUid ?? null], queryFn: () => api.get<CorrectionsResponse>(`/api/corrections${qs({ asset_uid: assetUid })}`) })

export interface CorrectionInput {
  field: string
  op: 'set' | 'add' | 'remove'
  value: unknown
  shot_uid?: string
  asset_uid?: string
  note?: string
}

export function useCorrect() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (c: CorrectionInput) => api.post<{ correction_id: number; record: ShotDoc | AssetDoc }>('/api/corrections', { ...c }),
    onSuccess: (res, vars) => {
      if (vars.shot_uid) {
        qc.setQueriesData({ queryKey: ['shot', vars.shot_uid] }, res.record)
      }
      if (vars.asset_uid) qc.setQueryData(['asset', vars.asset_uid], res.record)
      qc.invalidateQueries({ queryKey: ['search'] })
      qc.invalidateQueries({ queryKey: ['corrections'] })
      qc.invalidateQueries({ queryKey: ['asset'] })
      qc.invalidateQueries({ queryKey: ['stats'] })
    },
  })
}

export function useRevertCorrection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.del<{ ok: boolean }>(`/api/corrections/${id}`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['shot'] })
      qc.invalidateQueries({ queryKey: ['search'] })
      qc.invalidateQueries({ queryKey: ['corrections'] })
      qc.invalidateQueries({ queryKey: ['asset'] })
    },
  })
}

// ---------------------------------------------------------------- rights
export const useRights = (assetUid: string | null | undefined, shotUid?: string | null) =>
  useQuery({ queryKey: ['rights', assetUid, shotUid ?? null], queryFn: () => api.get<RightsRecord>(`/api/rights/${assetUid}${qs({ shot_uid: shotUid })}`), enabled: Boolean(assetUid) })

export function useSetRights() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ assetUid, shotUid, rights }: { assetUid: string; shotUid?: string | null; rights: Partial<RightsRecord> }) =>
      api.put<RightsRecord>(`/api/rights/${assetUid}${qs({ shot_uid: shotUid })}`, rights as Record<string, unknown>),
    onSuccess: () => invalidateRights(qc),
  })
}

export function useBulkRights() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ assetUids, rights }: { assetUids: string[]; rights: Partial<RightsRecord> }) => api.post<{ updated: number }>('/api/rights/bulk', { asset_uids: assetUids, rights }),
    onSuccess: () => invalidateRights(qc),
  })
}

function invalidateRights(qc: QueryClient) {
  for (const k of ['rights', 'assets', 'asset', 'shot', 'search', 'stats', 'collection', 'collections', 'rightsCheck']) qc.invalidateQueries({ queryKey: [k] })
}

export interface RightsCheckInput {
  shot_uids?: string[]
  asset_uids?: string[]
  use?: string | null
  channel?: string | null
  territory?: string | null
  date?: string | null
}

export const checkRights = (body: RightsCheckInput) => api.post<RightsCheck>('/api/rights/check', { ...body })

export const useRightsCheck = (body: RightsCheckInput | null) =>
  useQuery({ queryKey: ['rightsCheck', body], queryFn: () => checkRights(body as RightsCheckInput), enabled: Boolean(body && ((body.shot_uids?.length ?? 0) > 0 || (body.asset_uids?.length ?? 0) > 0)) })

/** Summarise verdicts for a set of check items. */
export function verdictCounts(check: RightsCheck | undefined): Record<Verdict, number> {
  const c: Record<Verdict, number> = { allowed: 0, restricted: 0, blocked: 0, unknown: 0 }
  for (const i of check?.items ?? []) c[i.verdict]++
  return c
}

// ---------------------------------------------------------------- collections
export const useCollections = () => useQuery({ queryKey: ['collections'], queryFn: () => api.get<{ collections: CollectionSummary[] }>('/api/collections').then((r) => r.collections) })

export const useCollection = (uid: string | null | undefined) =>
  useQuery({ queryKey: ['collection', uid], queryFn: () => api.get<Collection>(`/api/collections/${uid}`), enabled: Boolean(uid), placeholderData: keepPreviousData })

function useCollectionMutation<V>(fn: (v: V) => Promise<Collection>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: (c) => {
      qc.setQueryData(['collection', c.uid], c)
      qc.invalidateQueries({ queryKey: ['collections'] })
    },
  })
}

export const useCreateCollection = () =>
  useCollectionMutation((v: { name: string; description?: string; brief?: string; shot_uids?: string[] }) => api.post<Collection>('/api/collections', { ...v }))

export const useAddToCollection = () =>
  useCollectionMutation((v: { uid: string; shot_uids: string[]; in?: number | null; out?: number | null; note?: string }) =>
    api.post<Collection>(`/api/collections/${v.uid}/items`, { shot_uids: v.shot_uids, in: v.in ?? null, out: v.out ?? null, note: v.note ?? '' }),
  )

export const useUpdateCollection = () =>
  useCollectionMutation((v: { uid: string; name?: string; description?: string; brief?: string }) => {
    const { uid, ...rest } = v
    return api.patch<Collection>(`/api/collections/${uid}`, rest)
  })

export const useReorderCollection = () => useCollectionMutation((v: { uid: string; order: number[] }) => api.patch<Collection>(`/api/collections/${v.uid}`, { order: v.order }))

export const useUpdateItem = () =>
  useCollectionMutation((v: { uid: string; itemId: number; in?: number | null; out?: number | null; note?: string }) => {
    const body: Record<string, unknown> = {}
    if (v.in !== undefined) body.in = v.in
    if (v.out !== undefined) body.out = v.out
    if (v.note !== undefined) body.note = v.note
    return api.patch<Collection>(`/api/collections/${v.uid}/items/${v.itemId}`, body)
  })

export const useRemoveItem = () => useCollectionMutation((v: { uid: string; itemId: number }) => api.del<Collection>(`/api/collections/${v.uid}/items/${v.itemId}`))

export function useDeleteCollection() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (uid: string) => api.del<{ ok: boolean }>(`/api/collections/${uid}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['collections'] }),
  })
}

export interface PackageInput {
  name?: string
  brief?: string
  target: PackageTarget
  media_policy: string
  mode?: string
  zip?: boolean
}

export const buildCollectionPackage = (uid: string, body: PackageInput) => api.post<PackageResult>(`/api/collections/${uid}/package`, { ...body })

export const buildPackage = (items: { shot_uid: string; in?: number | null; out?: number | null; note?: string }[], body: PackageInput) =>
  api.post<PackageResult>('/api/package', { ...body, items })

export const exportClip = (body: { shot_uid: string; in?: number | null; out?: number | null; mode: ExportMode; intended_use?: IntendedUse | null }) =>
  api.post<ExportClipResult>('/api/export/clip', { ...body })

// ---------------------------------------------------------------- ingest
export const useProcessing = (enabled = true) =>
  useQuery({
    queryKey: ['processing'],
    queryFn: () => api.get<Processing>('/api/processing'),
    enabled,
    refetchInterval: () => (typeof document !== 'undefined' && document.visibilityState === 'visible' ? 2500 : false),
    refetchIntervalInBackground: false,
    staleTime: 1000,
  })

export const useSources = () => useQuery({ queryKey: ['sources'], queryFn: () => api.get<{ sources: Source[] }>('/api/sources').then((r) => r.sources) })

// ---------------------------------------------------------------- admin
export const useEndpointLocality = (url: string) =>
  useQuery({
    queryKey: ['admin', 'locality', url.trim()],
    queryFn: ({ signal }) => api.get<Locality>(`/api/admin/endpoint-locality${qs({ url: url.trim() })}`, signal),
    enabled: Boolean(url.trim()),
    staleTime: 60_000,
    retry: false,
  })

export const checkEndpointLocality = (url: string) =>
  queryClient.fetchQuery({ queryKey: ['admin', 'locality', url.trim()], queryFn: () => api.get<Locality>(`/api/admin/endpoint-locality${qs({ url: url.trim() })}`), staleTime: 60_000 })

export const useAdminSettings = () => useQuery({ queryKey: ['admin', 'settings'], queryFn: () => api.get<AdminSettings>('/api/admin/settings'), retry: false })
export const useTokens = () => useQuery({ queryKey: ['admin', 'tokens'], queryFn: () => api.get<TokensResponse>('/api/admin/tokens'), retry: false })
export const useUsers = () => useQuery({ queryKey: ['admin', 'users'], queryFn: () => api.get<{ users: User[] }>('/api/admin/users').then((r) => r.users), retry: false })
export const useAudit = (agentsOnly: boolean, limit = 200) =>
  useQuery({ queryKey: ['admin', 'audit', agentsOnly, limit], queryFn: () => api.get<{ entries: AuditEntry[] }>(`/api/admin/audit${qs({ agents_only: agentsOnly || undefined, limit })}`).then((r) => r.entries), retry: false })
