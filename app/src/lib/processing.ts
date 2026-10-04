/**
 * Processing status for the ingest queue (system.md §3.23). Pure: from /api/processing rows.
 * An "updating" file is analysed and searchable, refreshing with newer analyser versions.
 */
import type { AnalyserInfo, ProcessingAsset, QueueJob } from '../api/types'
import { humanise } from './format'

export const STEPS: { label: string; analysers: string[] }[] = [
  { label: 'Probe', analysers: ['technical', 'place'] },
  { label: 'Proxies', analysers: ['proxy'] },
  { label: 'Shots', analysers: ['shots', 'keyframes'] },
  { label: 'Vision', analysers: ['embed', 'visual_tags', 'motion', 'quality', 'ocr', 'people', 'faces', 'caption'] },
  { label: 'Audio', analysers: ['audio', 'speech'] },
  { label: 'Index', analysers: ['fusion', 'rollup', 'text_embed'] },
]

export type StepState = 'done' | 'active' | 'waiting' | 'failed'

/** Analysers being refreshed for an "updating" file: the core's `pending` list (queued and running, in queue order). */
export function updatingAnalysers(a: ProcessingAsset): string[] {
  return [...new Set(a.pending)]
}

/** "Updating: rollup, fusion" (every queued or running analyser, by name). */
export function updatingText(a: ProcessingAsset): string {
  const names = updatingAnalysers(a).map((n) => humanise(n).toLowerCase())
  return names.length ? `Updating: ${names.join(', ')}` : 'Updating'
}

/** Files with queued or running jobs for an analyser ("caption" → 12). */
export function filesPending(assets: ProcessingAsset[], analyser: string): number {
  return assets.filter((a) => a.pending.includes(analyser)).length
}

/** Step states for a queue row from its counts, running and failed jobs (approximate between polls). */
export function stepStates(a: ProcessingAsset, available: AnalyserInfo[], running: QueueJob[], failed: QueueJob[]): StepState[] {
  const order = available.filter((x) => x.available).map((x) => x.name)
  if (a.status === 'updating') {
    // Analysed and searchable: steps stay done except the ones being refreshed.
    const runningSet = new Set(running.filter((j) => j.uid === a.uid).map((j) => j.analyser))
    const pendingSet = new Set(a.pending)
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
