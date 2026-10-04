import { Tooltip as RacTooltip, type TooltipProps } from 'react-aria-components'
import s from './Overlay.module.css'

/** Inverse tooltip (system.md §3.21). Never interactive. */
export function Tooltip({ children, ...props }: Omit<TooltipProps, 'className'> & { children: React.ReactNode }) {
  return (
    <RacTooltip offset={6} {...props} className={s.tooltip}>
      {children}
    </RacTooltip>
  )
}
