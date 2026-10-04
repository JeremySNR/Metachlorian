import { useState } from 'react'
import { Layers, Plus } from 'lucide-react'
import { ApiError } from '../../api/client'
import { useAddToCollection, useCollections, useCreateCollection } from '../../api/queries'
import { Button } from '../../components/Button'
import { Dialog } from '../../components/Dialog'
import { TextField } from '../../components/Field'
import { Ic } from '../../components/Icon'
import { toast } from '../../components/Toast'
import { plural } from '../../lib/format'
import { usePrefs, useUi } from '../../lib/store'
import s from './Dialogs.module.css'

/** "Add to…" (A): pick or create a collection; the choice becomes the active collection. */
export function AddToDialog() {
  const uids = useUi((u) => u.addToDialog)
  const set = useUi((u) => u.set)
  const cols = useCollections()
  const add = useAddToCollection()
  const create = useCreateCollection()
  const [name, setName] = useState('')
  const close = () => {
    set({ addToDialog: null })
    setName('')
  }
  const pick = async (uid: string, label: string) => {
    if (!uids) return
    try {
      await add.mutateAsync({ uid, shot_uids: uids })
      usePrefs.getState().set({ activeCollection: uid })
      toast({ title: `Added ${plural(uids.length, 'shot')} to ${label}` })
      close()
    } catch (e) {
      toast({ title: "Couldn't add to the collection", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    }
  }
  const make = async () => {
    if (!uids || !name.trim()) return
    const c = await create.mutateAsync({ name: name.trim(), shot_uids: uids })
    usePrefs.getState().set({ activeCollection: c.uid })
    toast({ title: `Created ${c.name} with ${plural(uids.length, 'shot')}` })
    close()
  }
  return (
    <Dialog isOpen={Boolean(uids)} onOpenChange={(o) => !o && close()} title={`Add ${plural(uids?.length ?? 0, 'shot')} to…`} size="s">
      <div className={s.form}>
        {(cols.data?.length ?? 0) > 0 && (
          <div className={s.colList} role="list">
            {cols.data?.map((c) => (
              <button key={c.uid} type="button" role="listitem" className={s.colOption} onClick={() => pick(c.uid, c.name)}>
                <Ic icon={Layers} />
                <span>{c.name}</span>
                <span>{plural(c.items, 'shot')}</span>
              </button>
            ))}
          </div>
        )}
        <form
          onSubmit={(e) => {
            e.preventDefault()
            make()
          }}
          style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'end' }}
        >
          <TextField label="New collection" value={name} onChange={setName} placeholder="e.g. Night market selects" className={undefined} autoFocus={!cols.data?.length} />
          <Button type="submit" icon={Plus} isDisabled={!name.trim()} busy={create.isPending}>
            Create
          </Button>
        </form>
      </div>
    </Dialog>
  )
}
