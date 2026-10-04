/**
 * Native drag-out (desktop shell only). The shell's startDrag needs real files
 * that already exist when dragstart fires, so clips are exported on hover
 * intent or selection and cached by shot + range.
 */
import { exportClip } from '../api/queries'
import { can } from './bridge'

const ready = new Map<string, string>()
const pending = new Map<string, Promise<string | null>>()

const key = (uid: string, inS?: number | null, outS?: number | null) => `${uid}|${inS ?? ''}|${outS ?? ''}`

/** Export a proxy clip for the shot so it can be dragged; no-op in the browser. */
export function prepareDrag(uid: string, inS?: number | null, outS?: number | null): Promise<string | null> {
  if (!can('canDragOut')) return Promise.resolve(null)
  const k = key(uid, inS, outS)
  const done = ready.get(k)
  if (done) return Promise.resolve(done)
  let p = pending.get(k)
  if (!p) {
    p = exportClip({ shot_uid: uid, in: inS ?? null, out: outS ?? null, mode: 'proxy' })
      .then((r) => {
        if (r.file) ready.set(k, r.file)
        return r.file ?? null
      })
      .catch(() => null)
      .finally(() => pending.delete(k))
    pending.set(k, p)
  }
  return p
}

/** Files ready to drag right now (synchronous, for dragstart). */
export function dragFiles(uids: string[]): string[] {
  const out: string[] = []
  for (const u of uids) {
    for (const [k, f] of ready) if (k.startsWith(`${u}|`)) {
      out.push(f)
      break
    }
  }
  return out
}
