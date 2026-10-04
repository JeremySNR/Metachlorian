import { PenLine } from 'lucide-react'
import { formatDayMonth } from '../lib/format'
import { Ic } from './Icon'
import s from './Data.module.css'
import tip from './Tip.module.css'

/** Inverse solid chip: a person changed this value; it outranks the model (§3.10). */
export function HumanMarker({ by, at, modelSaid, confirmed }: { by?: string; at?: number; modelSaid?: string | null; confirmed?: boolean }) {
  const who = by && by !== 'local' ? by : 'You'
  const label = `${confirmed ? 'Confirmed' : 'Corrected'} by ${who}${at ? `, ${formatDayMonth(at)}` : ''}${modelSaid ? `. Model said: ${modelSaid}` : ''}`
  return (
    <span className={`${s.human} ${tip.tip}`} data-tip={modelSaid ? `Model said: ${modelSaid}` : undefined} aria-label={label} role="note">
      <Ic icon={PenLine} size={12} />
      <span aria-hidden="true">
        {who}
        {at ? ` · ${formatDayMonth(at)}` : ''}
      </span>
    </span>
  )
}
