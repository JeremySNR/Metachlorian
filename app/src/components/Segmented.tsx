import type { Key } from 'react-aria-components'
import { ToggleButton, ToggleButtonGroup, TooltipTrigger } from 'react-aria-components'
import type { LucideIcon } from 'lucide-react'
import { Ic } from './Icon'
import { Tooltip } from './Tooltip'
import s from './Data.module.css'

export interface Segment<T extends string> {
  id: T
  label: string
  icon?: LucideIcon
  iconOnly?: boolean
}

/** Segmented control (§3.13): single selection, arrow keys move and select. */
export function Segmented<T extends string>({ label, segments, value, onChange, className }: { label: string; segments: Segment<T>[]; value: T; onChange: (v: T) => void; className?: string }) {
  return (
    <ToggleButtonGroup
      aria-label={label}
      selectionMode="single"
      disallowEmptySelection
      selectedKeys={[value]}
      onSelectionChange={(keys: Set<Key>) => {
        const k = [...keys][0]
        if (k !== undefined) onChange(k as T)
      }}
      className={[s.segmented, className].filter(Boolean).join(' ')}
    >
      {segments.map((seg) => {
        const btn = (
          <ToggleButton key={seg.id} id={seg.id} aria-label={seg.iconOnly ? seg.label : undefined} className={`${s.segment} ${seg.iconOnly ? s.iconSeg : ''}`}>
            {seg.icon && <Ic icon={seg.icon} size={16} />}
            {!seg.iconOnly && seg.label}
          </ToggleButton>
        )
        return seg.iconOnly ? (
          <TooltipTrigger key={seg.id} delay={500}>
            {btn}
            <Tooltip>{seg.label}</Tooltip>
          </TooltipTrigger>
        ) : (
          btn
        )
      })}
    </ToggleButtonGroup>
  )
}
