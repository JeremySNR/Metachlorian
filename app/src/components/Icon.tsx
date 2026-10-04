import type { LucideIcon, LucideProps } from 'lucide-react'

/** Lucide icon at a design-system size: stroke 1.75 at 16/20 px, 2 at 14 px (system.md §7). */
export function Ic({ icon: I, size = 16, className, ...rest }: { icon: LucideIcon; size?: 14 | 16 | 20 | 12 | 24 } & Omit<LucideProps, 'size' | 'ref'>) {
  return <I size={size} strokeWidth={size <= 14 ? 2 : 1.75} aria-hidden="true" focusable="false" className={className} {...rest} />
}
