import { describe, expect, it } from 'vitest'
import type { AnalyserInfo, ProcessingAsset, QueueJob } from '../api/types'
import { stepStates, updatingText } from './processing'

const names = ['technical', 'proxy', 'shots', 'keyframes', 'embed', 'visual_tags', 'motion', 'quality', 'ocr', 'people', 'audio', 'speech', 'fusion', 'rollup', 'text_embed']
const analysers = names.map((name) => ({ name, available: true }) as AnalyserInfo)
const row = (p: Partial<ProcessingAsset>): ProcessingAsset => ({ uid: 'a', filename: 'f.mp4', status: 'updating', duration: 3, priority: 0, updated_at: 0, queued: 0, running: 0, done: 16, failed: 0, unavailable: 1, ...p })
const job = (analyser: string): QueueJob => ({ id: 1, analyser, updated_at: 0, filename: 'f.mp4', uid: 'a' })

describe('re-analysis ("updating") status', () => {
  it('keeps analysed steps done and spins only what is refreshing', () => {
    expect(stepStates(row({ running: 1, queued: 1, pending: ['visual_tags', 'rollup'] }), analysers, [job('visual_tags')], [])).toEqual(['done', 'done', 'done', 'active', 'done', 'waiting'])
  })
  it('names the refreshing analysers', () => {
    expect(updatingText(row({ running: 1, queued: 1, pending: ['visual_tags', 'rollup'] }), [job('visual_tags')])).toBe('Updating: visual tags, rollup')
    expect(updatingText(row({ running: 1, queued: 2 }), [job('fusion')])).toBe('Updating: fusion + 2 queued')
    expect(updatingText(row({ queued: 2 }), [])).toBe('Updating: 2 steps queued')
  })
  it('shows only running steps as active for new files', () => {
    const states = stepStates(row({ status: 'processing', done: 2, queued: 5 }), analysers, [], [])
    expect(states.filter((x) => x === 'active')).toHaveLength(0)
    expect(stepStates(row({ status: 'ready' }), analysers, [], [])).toEqual(Array(6).fill('done'))
  })
})
