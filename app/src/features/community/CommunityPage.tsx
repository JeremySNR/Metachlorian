import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import type { CommunityResults, CommunityStatus } from '../../api/types'
import { api, qs } from '../../api/client'
import { useAdminSettings } from '../../api/queries'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { Switch, TextField } from '../../components/Field'
import { toast } from '../../components/Toast'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { formatLength } from '../../lib/timecode'
import s from './CommunityPage.module.css'

function useCommunityStatus() {
  return useQuery({ queryKey: ['community', 'status'], queryFn: ({ signal }) => api.get<CommunityStatus>('/api/community/status', signal), refetchInterval: 30000 })
}

export function CommunityPage() {
  useDocumentTitle('Community')
  const status = useCommunityStatus()
  const [text, setText] = useState('')
  const [submitted, setSubmitted] = useState<{ query: string; offset: number } | null>(null)
  const results = useQuery({
    queryKey: ['community', 'search', submitted],
    queryFn: ({ signal }) => api.get<CommunityResults>('/api/community/search' + qs({ q: submitted?.query, offset: submitted?.offset }), signal),
    enabled: submitted !== null && Boolean(status.data?.configured), retry: false,
  })
  return (
    <main id="main" className={s.page}>
      <header><p className={s.eyebrow}>Metachlorian Community</p><h1>Find a moment in public video.</h1>
        <p>Search the content people have analysed from public YouTube videos: descriptions, camera movement, spoken words and on-screen text.</p></header>
      <form className={s.search} onSubmit={(e) => {
        e.preventDefault()
        const query = text.trim()
        if (submitted?.query === query && submitted.offset === 0) void results.refetch()
        else setSubmitted({ query, offset: 0 })
      }}>
        <TextField label="Search community videos" placeholder="e.g. coastal drone sunset" value={text} onChange={setText} maxLength={300} />
        <Button type="submit" isDisabled={!status.data?.configured || results.isFetching}>{results.isFetching ? 'Searching…' : 'Search community'}</Button>
      </form>
      {status.isError && <p role="alert">Couldn’t read community status. {String(status.error.message)}</p>}
      {status.data && !status.data.configured && <EmptyState inline title="Community service is not connected yet">An admin can connect it in <Link to="/settings/$section" params={{ section: 'community' }}>Community sharing settings</Link>.</EmptyState>}
      <p className={s.note}>Community search sends your query to the community service. Results open on YouTube. Contributions are machine-generated and may contain errors; a result does not establish permission to reuse footage.</p>
      <section aria-live="polite" aria-busy={results.isFetching}>
        {results.isError && <p role="alert">Couldn’t search the community. {results.error.message}</p>}
        {results.data && <p>{results.data.results.length} moments on this page{results.data.hidden_pending_visibility ? ` · ${results.data.hidden_pending_visibility} hidden while public visibility is checked` : ''}</p>}
        {results.data?.results.length === 0 && <EmptyState inline title="No public moments found">Try fewer words, or search again once more videos have been analysed.</EmptyState>}
        <div className={s.results}>{results.data?.results.map((r, i) => (
          <article key={`${r.video_id}-${r.start_s}-${r.kind}-${i}`} className={s.card}>
            <p className={s.eyebrow}>{r.kind} · {formatLength(r.start_s)} – {formatLength(r.end_s)}</p>
            <h2><a href={`https://www.youtube.com/watch?v=${encodeURIComponent(r.video_id)}&t=${Math.max(0, Math.floor(r.start_s))}s`} target="_blank" rel="noopener noreferrer">{r.title}</a></h2><p>{r.channel}</p>
            <p>{r.snippet}</p><p className={s.note}>Community analysis · {r.license || 'Licence not provided by YouTube'}</p>
          </article>
        ))}</div>
        {results.data?.next_offset != null && <Button variant="quiet" isDisabled={results.isFetching} onPress={() => setSubmitted({ query: submitted?.query ?? '', offset: results.data?.next_offset ?? 0 })}>Next page</Button>}
      </section>
    </main>
  )
}

export function CommunitySettings() {
  const settings = useAdminSettings()
  const status = useCommunityStatus()
  const qc = useQueryClient()
  const [busy, setBusy] = useState(false)
  const [endpoint, setEndpoint] = useState<string | null>(null)
  const [error, setError] = useState('')
  const st = settings.data?.settings
  const save = async (body: { community_enabled?: boolean; community_url?: string }) => {
    setBusy(true); setError('')
    try {
      await api.put('/api/admin/settings', body)
      await Promise.all([qc.invalidateQueries({ queryKey: ['admin', 'settings'] }), qc.invalidateQueries({ queryKey: ['community'] }), qc.invalidateQueries({ queryKey: ['health'] })])
      toast({ title: body.community_enabled === false ? 'Community sharing is off' : 'Community settings saved', tone: 'info' })
    } catch (e) { setError(e instanceof Error ? e.message : String(e)) } finally { setBusy(false) }
  }
  if (settings.isError) return <p role="alert">Community sharing settings require an admin. {settings.error.message}</p>
  if (!st) return <div aria-busy="true" />
  return (
    <section className={s.settings}>
      <h2>Help make public videos searchable</h2>
      <Switch isSelected={st.community_enabled ?? true} isDisabled={busy} onChange={(on) => save({ community_enabled: on })}>Share analysis of public YouTube imports</Switch>
      <p>On by default. After a newly downloaded public YouTube video finishes analysis, its machine descriptions, tags, shot times, transcripts and on-screen text contribute to the public community database.</p>
      <ul><li>Public visibility is checked without your login before each contribution, and independently by the community service.</li>
        <li>Local or personal files, private or unlisted videos, other websites and duplicates of local footage are excluded.</li>
        <li>Videos, frames, audio files, face identities, local paths, your corrections, notes and rights records stay in your library.</li>
        <li>Turning this off stops pending contributions. Videos imported while it is off are not shared later. Previously published metadata stays public; removal requests go to the community operator.</li></ul>
      <form onSubmit={(e) => { e.preventDefault(); save({ community_url: (endpoint ?? st.community_url ?? '').trim() }) }}>
        <TextField label="Community service URL" value={endpoint ?? st.community_url ?? ''} onChange={setEndpoint} placeholder="https://your-community-service.vercel.app" description="The public community service, separate from this private library." />
        <Button type="submit" isDisabled={busy}>Save service URL</Button>
      </form>
      {error && <p role="alert">{error}</p>}
      {status.data && <p role="status">{status.data.state === 'needs_endpoint' ? 'Sharing is enabled. Contributions wait until a community service is configured.' : status.data.state === 'off' ? 'Sharing is off.' : 'Community service configured. Contributions retry if the service is unavailable.'} {status.data.counts.shared ?? 0} shared · {status.data.counts.pending ?? 0} pending.</p>}
      <Link to="/community">Search the community</Link>
    </section>
  )
}
