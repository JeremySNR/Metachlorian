import { CircleAlert, CircleCheck, Info, TriangleAlert, X } from 'lucide-react'
import {
  Button as RacButton,
  UNSTABLE_Toast as RacToast,
  UNSTABLE_ToastContent as ToastContent,
  UNSTABLE_ToastQueue as ToastQueue,
  UNSTABLE_ToastRegion as ToastRegion,
  Text,
} from 'react-aria-components'
import { Ic } from './Icon'
import { buttonClass } from './Button'
import s from './Overlay.module.css'

export type ToastTone = 'success' | 'info' | 'error' | 'caution'

export interface ToastData {
  title: string
  description?: string
  tone?: ToastTone
  action?: { label: string; onAction: () => void }
}

/** Wrapped behind our own API so the UNSTABLE_ RAC names never leak to call sites. */
export const toastQueue = new ToastQueue<ToastData>({ maxVisibleToasts: 3 })

/** Success and info toasts auto-dismiss after 6 s; errors never do (§3.15). */
export function toast(t: ToastData | string) {
  const data: ToastData = typeof t === 'string' ? { title: t } : t
  const tone = data.tone ?? 'success'
  return toastQueue.add({ ...data, tone }, tone === 'error' ? {} : { timeout: 6000 })
}

const ICONS = { success: CircleCheck, info: Info, error: CircleAlert, caution: TriangleAlert }

export function Toaster() {
  return (
    <ToastRegion queue={toastQueue} className={s.toastRegion} aria-label="Notifications">
      {({ toast: t }) => {
        const tone = t.content.tone ?? 'success'
        return (
          <RacToast toast={t} className={s.toast}>
            <Ic icon={ICONS[tone]} className={`${s.toastIcon} ${s[`tone-${tone}`]}`} />
            <ToastContent className={s.toastContent}>
              <Text slot="title">{t.content.title}</Text>
              {t.content.description && <Text slot="description" style={{ color: 'var(--fg-2)' }}>{t.content.description}</Text>}
            </ToastContent>
            <div className={s.toastActions}>
              {t.content.action && (
                <RacButton
                  className={buttonClass('quiet', 'sm')}
                  onPress={() => {
                    t.content.action?.onAction()
                    toastQueue.close(t.key)
                  }}
                >
                  {t.content.action.label}
                </RacButton>
              )}
              <RacButton slot="close" aria-label="Dismiss" className={`${buttonClass('quiet', 'sm')}`} style={{ inlineSize: 'var(--control-sm)', padding: 0 }}>
                <Ic icon={X} size={14} />
              </RacButton>
            </div>
          </RacToast>
        )
      }}
    </ToastRegion>
  )
}
