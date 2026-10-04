import { useEffect } from 'react'

/** Per-route document title (WCAG 2.4.2): "Library · Metachlorian". */
export function useDocumentTitle(...parts: (string | null | undefined | false)[]) {
  const title = [...parts.filter(Boolean), 'Metachlorian'].join(' · ')
  useEffect(() => {
    document.title = title
  }, [title])
}
