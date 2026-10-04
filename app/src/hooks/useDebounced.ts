import { useEffect, useRef, useState } from 'react'

export function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value)
  useEffect(() => {
    const t = window.setTimeout(() => setV(value), ms)
    return () => window.clearTimeout(t)
  }, [value, ms])
  return v
}

/** True only after `flag` has stayed true for `ms` (instant-or-honest progress, §0 rule 7). */
export function useDelayedFlag(flag: boolean, ms = 400): boolean {
  const [show, setShow] = useState(false)
  useEffect(() => {
    if (!flag) return
    const t = window.setTimeout(() => setShow(true), ms)
    return () => {
      window.clearTimeout(t)
      setShow(false)
    }
  }, [flag, ms])
  return flag && show
}

/** Latest value in a ref, for event handlers registered once. */
export function useLatest<T>(value: T) {
  const ref = useRef(value)
  useEffect(() => {
    ref.current = value
  })
  return ref
}
