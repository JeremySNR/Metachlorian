import { forwardRef, useEffect, useState, type ReactNode } from 'react'
import { Button as RacButton, TooltipTrigger, type ButtonProps as RacButtonProps } from 'react-aria-components'
import { LoaderCircle, type LucideIcon } from 'lucide-react'
import { Ic } from './Icon'
import { Tooltip } from './Tooltip'
import s from './Button.module.css'

export type Variant = 'primary' | 'secondary' | 'quiet' | 'danger' | 'dangerFilled'
export type Size = 'sm' | 'md' | 'lg'

export interface ButtonProps extends Omit<RacButtonProps, 'children' | 'className'> {
  variant?: Variant
  size?: Size
  icon?: LucideIcon
  iconEnd?: LucideIcon
  shortcut?: string
  busy?: boolean
  className?: string
  children?: ReactNode
  /** Reason shown in a tooltip when disabled (button stays focusable, aria-disabled). */
  disabledReason?: string
}

function useDelayed(flag: boolean, ms = 400) {
  const [show, setShow] = useState(false)
  useEffect(() => {
    if (!flag) {
      setShow(false)
      return
    }
    const t = window.setTimeout(() => setShow(true), ms)
    return () => window.clearTimeout(t)
  }, [flag, ms])
  return show
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', icon, iconEnd, shortcut, busy, className, children, disabledReason, isDisabled, onPress, ...rest },
  ref,
) {
  const showBusy = useDelayed(Boolean(busy))
  const iconSize = size === 'sm' ? 14 : 16
  const softDisabled = Boolean(disabledReason) && isDisabled
  const btn = (
    <RacButton
      ref={ref}
      {...rest}
      isDisabled={softDisabled ? false : isDisabled}
      aria-disabled={softDisabled || undefined}
      data-disabled={softDisabled || undefined}
      onPress={softDisabled ? undefined : onPress}
      aria-busy={busy || undefined}
      className={[s.button, s[variant], size !== 'md' && s[size], className].filter(Boolean).join(' ')}
    >
      {showBusy ? <Ic icon={LoaderCircle} size={14} className="mc-spin" /> : icon ? <Ic icon={icon} size={iconSize} /> : null}
      {children}
      {iconEnd && <Ic icon={iconEnd} size={iconSize} />}
      {shortcut && <kbd className={s.kbd} aria-hidden="true">{shortcut}</kbd>}
    </RacButton>
  )
  if (!softDisabled) return btn
  return (
    <TooltipTrigger delay={300}>
      {btn}
      <Tooltip>{disabledReason}</Tooltip>
    </TooltipTrigger>
  )
})

export interface IconButtonProps extends Omit<RacButtonProps, 'children' | 'className'> {
  icon: LucideIcon
  label: string
  shortcut?: string
  variant?: Variant
  size?: Size
  className?: string
  tooltip?: boolean
  placement?: 'top' | 'bottom' | 'start' | 'end'
}

/** Square icon button: always has an aria-label and a tooltip with label + shortcut. */
export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(function IconButton(
  { icon, label, shortcut, variant = 'quiet', size = 'md', className, tooltip = true, placement = 'bottom', ...rest },
  ref,
) {
  const btn = (
    <RacButton ref={ref} aria-label={label} {...rest} className={[s.button, s.icon, s[variant], size !== 'md' && s[size], className].filter(Boolean).join(' ')}>
      <Ic icon={icon} size={size === 'lg' ? 20 : size === 'sm' ? 14 : 16} />
    </RacButton>
  )
  if (!tooltip) return btn
  return (
    <TooltipTrigger delay={500}>
      {btn}
      <Tooltip placement={placement}>
        {label}
        {shortcut && <kbd>{shortcut}</kbd>}
      </Tooltip>
    </TooltipTrigger>
  )
})

export const buttonClass = (variant: Variant = 'secondary', size: Size = 'md') => [s.button, s[variant], size !== 'md' && s[size]].filter(Boolean).join(' ')
