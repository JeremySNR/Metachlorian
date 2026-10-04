/**
 * Processing status for the ingest queue (system.md §3.23). Pure: from /api/processing rows.
 * An "updating" file is analysed and searchable, refreshing with newer analyser versions.
 */
import type { AnalyserInfo, ProcessingAsset, QueueJob } from '../api/types'
import { humanise, plural } from './format'

export const STEPS: { label: string; analysers: string[] }[] = [
  { label: 'Probe', analysers: ['technical'] },
  { label: 'Proxies', analysers: ['proxy'] },
  { label: 'Shots', analysers: ['shots', 'keyframes'] },
  { label: 'Vision', analysers: ['embed', 'visual_tags', 'motion', 'quality', 'ocr', 'people', 'caption'] },
  { label: 'Audio', analysers: ['audio', 'speech'] },
  { label: 'Index', analysers: ['fusion', 'rollup', 'text_embed'] },
]

export type StepState = 'done' | 'active' | 'waiting' | 'failed'

/** Analysers being refreshed for an "updating" file: its running jobs, plus the queued ones when the core lists them. */
export function updatingAnalysers(a: ProcessingAsset, running: QueueJob[]): string[] {
  const names = [...running.filter((j) => j.uid === a.uid).map((j) => j.analyser), ...(a.pending ?? [])]
  return [...new Set(names)]
}

/** "Updating: rollup, fusion" / "Updating: fusion + 2 queued" / "Updating: 2 steps queued". */
export function updatingText(a: ProcessingAsset, running: QueueJob[]): string {
  const names = updatingAnalysers(a, running).map((n) => humanise(n).toLowerCase())
  const listed = new Set(updatingAnalysers(a, running))
  const extra = Math.max(0, a.queued + a.running - listed.size)
  if (names.length) return `Updating: ${names.join(', ')}${extra ? ` + ${extra} queued` : ''}`
  return extra ? `Updating: ${plural(extra, 'step')} queued` : 'Updating'
}

/** Step states for a queue row from its counts, running and failed jobs (approximate between polls). */
export function stepStates(a: ProcessingAsset, available: AnalyserInfo[], running: QueueJob[], failed: QueueJob[]): StepState[] {
  const order = available.filter((x) => x.available).map((x) => x.name)
  if (a.status === 'updating') {
    // Analysed and searchable: steps stay done except the ones being refreshed.
    const runningSet = new Set(running.filter((j) => j.uid === a.uid).map((j) => j.analyser))
    const pendingSet = new Set(a.pending ?? [])
    const failedSet = new Set(failed.filter((j) => j.uid === a.uid).map((j) => j.analyser))
    return STEPS.map((st) => {
      const names = st.analysers.filter((n) => order.includes(n))
      if (names.some((n) => failedSet.has(n))) return 'failed'
      if (names.some((n) => runningSet.has(n))) return 'active'
      if (names.some((n) => pendingSet.has(n))) return 'waiting'
      return 'done'
    })
  }
  const ready = a.status === 'ready'
  const doneSet = new Set(ready ? order : order.slice(0, a.done))
  const runningSet = new Set(running.filter((j) => j.uid === a.uid).map((j) => j.analyser))
  const failedSet = new Set(failed.filter((j) => j.uid === a.uid).map((j) => j.analyser))
  // Only a step with a running job is active (magenta); queued work is waiting.
  return STEPS.map((st) => {
    const names = st.analysers.filter((n) => order.includes(n))
    if (names.some((n) => failedSet.has(n))) return 'failed'
    if (names.some((n) => runningSet.has(n))) return 'active'
    if (names.every((n) => doneSet.has(n))) return 'done'
    return 'waiting'
  })
}
