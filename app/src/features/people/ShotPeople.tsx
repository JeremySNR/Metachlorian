import { Link } from '@tanstack/react-router'
import { Dialog as RacDialog, DialogTrigger, Popover } from 'react-aria-components'
import { PenLine } from 'lucide-react'
import type { PersonRef } from '../../api/types'
import { usePeople } from '../../api/queries'
import { Button } from '../../components/Button'
import { FaceImg, NameEditor, usePeopleRights } from './shared'
import o from '../../components/Overlay.module.css'
import s from './ShotPeople.module.css'

/**
 * "People" row for a shot (inspector and Shot detail): who is recognised, each linking to their page.
 * Unnamed people offer "Name…" in place for editors. Face data never leaves this library.
 */
export function ShotPeople({ people }: { people: PersonRef[] | undefined }) {
  const { canWrite } = usePeopleRights()
  // Covers come from the people list (cached); the shot record carries ids and names only.
  const all = usePeople({ limit: 500 }, { enabled: Boolean(people?.length) })
  const cover = new Map((all.data?.people ?? []).map((p) => [p.id, p.cover]))
  if (!people) return null
  if (!people.length) return <p className={s.empty}>No recognised faces in this shot.</p>
  return (
    <ul className={s.list} data-testid="shot-people">
      {people.map((p) => (
        <li key={p.id} className={s.item}>
          <Link to="/people/$personId" params={{ personId: String(p.id) }} className={s.chip} data-named={p.name ? 'true' : undefined}>
            <FaceImg src={cover.get(p.id)} size="s" className={s.face} />
            <span>{p.label}</span>
          </Link>
          {!p.name && canWrite && (
            <DialogTrigger>
              <Button variant="quiet" size="sm" icon={PenLine} aria-label={`Name ${p.label}`}>
                Name…
              </Button>
              <Popover placement="bottom start" offset={4} className={`${o.popover} ${o.dialogPopover}`}>
                <RacDialog aria-label={`Name ${p.label}`} className={s.popoverBody}>
                  {({ close }) => <NameEditor person={p} onDone={close} />}
                </RacDialog>
              </Popover>
            </DialogTrigger>
          )}
        </li>
      ))}
    </ul>
  )
}
