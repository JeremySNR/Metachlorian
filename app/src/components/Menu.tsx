import type { ReactNode } from 'react'
import { Check, type LucideIcon } from 'lucide-react'
import {
  Header, Menu as RacMenu, MenuItem as RacMenuItem, MenuSection, MenuTrigger, Popover, Separator,
  type MenuItemProps, type MenuProps, type PopoverProps,
} from 'react-aria-components'
import { Ic } from './Icon'
import s from './Overlay.module.css'
import t from '../styles/type.module.css'

export { MenuTrigger, MenuSection }

export function MenuPopover({ children, ...props }: Omit<PopoverProps, 'className'> & { children: ReactNode }) {
  return (
    <Popover offset={4} {...props} className={s.popover}>
      {children}
    </Popover>
  )
}

export function Menu<T extends object>(props: Omit<MenuProps<T>, 'className'>) {
  return <RacMenu {...props} className={s.menu} />
}

export function MenuItem({ icon, shortcut, children, danger, checked, ...props }: Omit<MenuItemProps, 'className' | 'children'> & { icon?: LucideIcon; shortcut?: string; children: ReactNode; danger?: boolean; checked?: boolean }) {
  const text = typeof children === 'string' ? children : undefined
  return (
    <RacMenuItem textValue={text} {...props} className={s.menuItem} data-danger={danger || undefined}>
      {checked !== undefined && <span className={s.check}>{checked && <Ic icon={Check} />}</span>}
      {icon && <Ic icon={icon} />}
      <span>{children}</span>
      {shortcut && <kbd className={s.shortcut} style={{ border: 0 }}>{shortcut}</kbd>}
    </RacMenuItem>
  )
}

export function MenuSeparator() {
  return <Separator className={s.menuSeparator} />
}

export function MenuHeader({ children }: { children: ReactNode }) {
  return <Header className={`${s.menuHeader} ${t.slate}`}>{children}</Header>
}
