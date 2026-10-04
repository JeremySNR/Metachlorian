import type { ReactNode } from 'react'
import { Dialog as RacDialog, Heading, Modal, ModalOverlay } from 'react-aria-components'
import { X } from 'lucide-react'
import { IconButton } from './Button'
import s from './Overlay.module.css'

export interface DialogProps {
  isOpen: boolean
  onOpenChange: (open: boolean) => void
  title: ReactNode
  size?: 's' | 'm' | 'l'
  children: ReactNode
  footer?: ReactNode
  footerStart?: ReactNode
  /** Command menu sits at 15vh instead of the centre. */
  top?: boolean
  isDismissable?: boolean
  role?: 'dialog' | 'alertdialog'
  bare?: boolean
  'aria-label'?: string
}

/** RAC Modal + Dialog (system.md §3.17). Focus returns to the trigger on close. */
export function Dialog({ isOpen, onOpenChange, title, size = 'm', children, footer, footerStart, top, isDismissable = true, role, bare, ...rest }: DialogProps) {
  return (
    <ModalOverlay isOpen={isOpen} onOpenChange={onOpenChange} isDismissable={isDismissable} className={[s.overlay, top && s.overlayTop].filter(Boolean).join(' ')}>
      <Modal className={`${s.modal} ${s[size]}`}>
        <RacDialog className={s.dialog} role={role} aria-label={rest['aria-label']}>
          {({ close }) =>
            bare ? (
              children
            ) : (
              <>
                <div className={s.dialogHeader}>
                  <Heading slot="title" className={s.dialogTitle}>
                    {title}
                  </Heading>
                  <IconButton icon={X} label="Close" size="sm" onPress={close} />
                </div>
                <div className={s.dialogBody}>{children}</div>
                {(footer || footerStart) && (
                  <div className={s.dialogFooter}>
                    {footerStart && <div className={s.footerStart}>{footerStart}</div>}
                    {footer}
                  </div>
                )}
              </>
            )
          }
        </RacDialog>
      </Modal>
    </ModalOverlay>
  )
}

/** Side sheet (inspector on laptop/tablet, filter drawer on tablet). */
export function Sheet({ isOpen, onOpenChange, side, children, label }: { isOpen: boolean; onOpenChange: (o: boolean) => void; side: 'left' | 'right'; children: ReactNode; label: string }) {
  return (
    <ModalOverlay isOpen={isOpen} onOpenChange={onOpenChange} isDismissable className={s.sheetOverlay}>
      <Modal className={`${s.sheet} ${side === 'left' ? s.sheetLeft : s.sheetRight}`}>
        <RacDialog className={s.dialog} aria-label={label}>
          {children}
        </RacDialog>
      </Modal>
    </ModalOverlay>
  )
}
