import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'
import { Ic } from './Icon'
import s from './Data.module.css'

/** Empty, error and first-run states: in place, left-aligned at 64ch, top at ~25% (§3.16). */
export function EmptyState({ icon, title, children, actions, inline, role }: { icon?: LucideIcon; title: ReactNode; children?: ReactNode; actions?: ReactNode; inline?: boolean; role?: 'alert' | 'status' }) {
  return (
    <div className={`${s.empty} ${inline ? s.emptyInline : ''}`} role={role}>
      {icon && <Ic icon={icon} size={20} className={s.emptyIcon} />}
      <h2 className={s.emptyTitle}>{title}</h2>
      {children && <div className={s.emptyBody}>{children}</div>}
      {actions && <div className={s.emptyActions}>{actions}</div>}
    </div>
  )
}

export function ProgressLine({ visible }: { visible: boolean }) {
  if (!visible) return null
  return <span className={s.progress} role="progressbar" aria-label="Loading" />
}

export function StatusText({ tone, icon, children, filled, className }: { tone: 'info' | 'cleared' | 'caution' | 'blocked' | 'neutral'; icon?: LucideIcon; children: ReactNode; filled?: boolean; className?: string }) {
  return (
    <span className={[s.status, s[`s-${tone}`], filled && s.statusFilled, className].filter(Boolean).join(' ')}>
      {icon && <Ic icon={icon} size={14} />}
      {children}
    </span>
  )
}

export function Bar({ value, current, label }: { value: number; current?: boolean; label?: string }) {
  const v = Math.max(0, Math.min(1, value))
  return (
    <div className={s.bar} role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(v * 100)} aria-label={label}>
      <div className={`${s.barFill} ${current ? s.current : ''}`} style={{ inlineSize: `${v * 100}%` }} />
    </div>
  )
}

export function Swatches({ colours }: { colours: { hex: string; share?: number }[] }) {
  return (
    <span className={s.swatches}>
      {colours.map((c) => (
        <span key={c.hex} className={s.swatch} style={{ background: c.hex }} role="img" aria-label={`${c.hex}${c.share ? `, ${Math.round(c.share * 100)}%` : ''}`} />
      ))}
    </span>
  )
}
