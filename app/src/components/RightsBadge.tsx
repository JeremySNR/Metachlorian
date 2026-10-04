import { CalendarClock, CircleDashed, ShieldAlert, ShieldCheck, ShieldX, type LucideIcon } from 'lucide-react'
import type { ReactNode } from 'react'
import type { RightsRecord } from '../api/types'
import { agentsVisible, describeRights, type RightsState } from '../lib/rights'
import { Ic } from './Icon'
import s from './Data.module.css'
import tip from './Tip.module.css'

export const RIGHTS_ICON: Record<RightsState, LucideIcon> = {
  cleared: ShieldCheck,
  restricted: ShieldAlert,
  expiring: CalendarClock,
  expired: ShieldX,
  blocked: ShieldX,
  unknown: CircleDashed,
}

interface Props {
  state: RightsState
  record?: Partial<RightsRecord> | null
  reasons?: string[]
}

/** Card glyph: icon only, 24×24 hit area, the text lives in the tooltip and the card's name. */
export function RightsGlyph({ state, record, reasons }: Props) {
  const d = describeRights(state, record, reasons)
  return (
    <span className={`${s.glyph} ${s[`r-${state}`]} ${tip.tip}`} data-tip={d.long} role="img" aria-label={d.long}>
      <Ic icon={RIGHTS_ICON[state]} size={16} />
    </span>
  )
}

/** Compact: icon + short text on the status background (tables, headers). */
export function RightsBadge({ state, record, reasons }: Props) {
  const d = describeRights(state, record, reasons)
  return (
    <span className={`${s.compact} ${s[`r-${state}`]} ${tip.tip}`} data-tip={d.long !== d.short ? d.long : undefined}>
      <Ic icon={RIGHTS_ICON[state]} size={14} />
      {d.short}
    </span>
  )
}

/** Full inspector block. */
export function RightsFull({ state, record, reasons, action, lines }: Props & { action?: ReactNode; lines?: ReactNode[] }) {
  const d = describeRights(state, record, reasons)
  return (
    <div className={s.full}>
      <span className={s[`r-${state}`]}>
        <Ic icon={RIGHTS_ICON[state]} size={16} />
      </span>
      <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', justifyContent: 'space-between' }}>
        <span className={s.fullTitle}>{d.long}</span>
        {action}
      </div>
      <div className={s.fullLines}>
        {lines?.map((l, i) => <span key={i}>{l}</span>)}
        <span>Agents: {agentsVisible(state) ? 'visible' : 'hidden (not cleared)'}</span>
      </div>
    </div>
  )
}
