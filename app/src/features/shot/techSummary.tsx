import type { ShotDoc } from '../../api/types'
import { aspectLabel } from '../../lib/format'
import { fpsLabel } from '../../lib/timecode'

/** "1280×544 · 23.98p · H264 · 8-bit · SDR · 2.35:1" */
export function techSummary(d: ShotDoc) {
  const tt = d.technical
  const parts = [
    tt.width && tt.height ? `${tt.width}×${tt.height}` : null,
    fpsLabel(tt.fps),
    tt.video_codec?.toUpperCase(),
    tt.bit_depth ? `${tt.bit_depth}-bit` : null,
    tt.hdr ? 'HDR' : 'SDR',
    tt.log_profile ? 'Log' : null,
    aspectLabel(tt.aspect_ratio),
  ].filter(Boolean) as string[]
  return parts.map((p) => <span key={p}>{p}</span>)
}
