import { useMemo, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { ListBox, ListBoxItem, Radio as RacRadio, RadioGroup as RacRadioGroup } from 'react-aria-components'
import { Check, CircleAlert, ScanFace, X } from 'lucide-react'
import type { PersonRef, PersonSummary } from '../../api/types'
import { ApiError, mediaUrl } from '../../api/client'
import { useForgetPerson, useMe, useMergePeople, useNamedPeople, usePeople, useRenamePerson } from '../../api/queries'
import { Button, IconButton } from '../../components/Button'
import { Dialog } from '../../components/Dialog'
import { StatusText } from '../../components/EmptyState'
import { TextField } from '../../components/Field'
import { Ic } from '../../components/Icon'
import { toast } from '../../components/Toast'
import { plural } from '../../lib/format'
import { cleanName, mergePlan, mergeTarget, personCounts, personSearch } from '../../lib/people'
import s from './People.module.css'

/** Who may name, merge and move faces (tags:write, never an agent), and forget people (admin). */
export function usePeopleRights() {
  const me = useMe()
  const scopes = me.data?.scopes ?? []
  return { canWrite: scopes.includes('tags:write') && me.data?.role !== 'agent', isAdmin: scopes.includes('admin') }
}

/** A face crop (square, letterboxed), decorative: the name or label is always beside it. */
export function FaceImg({ src, size = 'm', className }: { src: string | null | undefined; size?: 's' | 'm' | 'l'; className?: string }) {
  return (
    <span className={[s.face, s[`face-${size}`], className].filter(Boolean).join(' ')}>
      {src ? <img src={mediaUrl(src)} alt="" loading="lazy" decoding="async" /> : <Ic icon={ScanFace} size={size === 's' ? 14 : 20} />}
    </span>
  )
}

/**
 * Inline name editor. Enter saves, Esc cancels. Typing a name someone already has offers a merge
 * instead, so one person never ends up as two identities with the same name.
 */
export function NameEditor({ person, onDone, onMerge }: { person: PersonRef; onDone: () => void; onMerge?: (into: PersonSummary) => void }) {
  const [value, setValue] = useState(person.name ?? '')
  const rename = useRenamePerson()
  const named = useNamedPeople()
  const navigate = useNavigate()
  const name = cleanName(value)
  const clash = name ? (named.data?.people ?? []).find((p) => p.id !== person.id && p.name?.toLowerCase() === name.toLowerCase()) : undefined
  const save = async () => {
    if (clash) return
    if (name === (person.name ?? '')) return onDone()
    try {
      await rename.mutateAsync({ id: person.id, name })
      onDone()
      if (name) {
        toast({
          title: `Named ${person.name ? `${person.name} as ${name}` : `${person.label} as ${name}`}`,
          description: 'Their shots are searchable by this name now.',
          action: { label: 'Find shots', onAction: () => navigate({ to: '/search', search: { q: name } }) },
        })
      } else toast({ title: `${person.name} is unnamed again`, description: `Shown as ${person.label.startsWith('Person ') ? person.label : `Person ${person.id}`}.`, tone: 'info' })
    } catch (e) {
      toast({ title: "Couldn't save the name", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    }
  }
  return (
    <form
      className={s.nameEditor}
      onSubmit={(e) => {
        e.preventDefault()
        save()
      }}
      onKeyDown={(e) => {
        if (e.key === 'Escape') {
          e.stopPropagation()
          onDone()
        }
      }}
    >
      <div className={s.nameRow}>
        <TextField
          aria-label={person.name ? `New name for ${person.name}` : `Name for ${person.label}`}
          value={value}
          onChange={setValue}
          autoFocus
          maxLength={80}
          placeholder="Name"
          className={s.nameInput}
        />
        <IconButton icon={Check} label={name ? 'Save name' : person.name ? 'Remove the name' : 'Save name'} type="submit" size="sm" variant="secondary" isDisabled={Boolean(clash) || rename.isPending} />
        <IconButton icon={X} label="Cancel" shortcut="Esc" size="sm" onPress={onDone} />
      </div>
      {clash && (
        <div className={s.clash} role="status">
          <span>{clash.name} already exists.</span>
          {onMerge && (
            <Button variant="secondary" size="sm" onPress={() => onMerge(clash)}>
              {`Merge into ${clash.name}`}
            </Button>
          )}
        </div>
      )}
      {!clash && person.name && !name && <span className={s.hint}>Saving an empty name makes them unnamed again.</span>}
    </form>
  )
}

async function mergeAll(merge: ReturnType<typeof useMergePeople>, from: PersonRef[], into: PersonRef) {
  for (const p of from) await merge.mutateAsync({ from: p.id, into: into.id })
}

/** Merge two or more people: pick who to keep; everyone else's faces move to them (§2.5.7: the non-drag way to merge). */
export function MergeDialog({ people, isOpen, onClose, onMerged }: { people: PersonSummary[]; isOpen: boolean; onClose: () => void; onMerged?: (into: PersonSummary) => void }) {
  const [keep, setKeep] = useState<number | null>(null)
  const merge = useMergePeople()
  const navigate = useNavigate()
  const target = keep ?? mergeTarget(people)?.id ?? null
  const plan = target !== null ? mergePlan(people, target) : null
  const go = async () => {
    if (!plan?.into) return
    try {
      await mergeAll(merge, plan.from, plan.into)
      const into = plan.into
      const label = plan.keepsName ?? into.label
      toast({ title: `Merged ${plural(people.length, 'person', 'people')} into ${label}`, action: { label: 'Open', onAction: () => navigate({ to: '/people/$personId', params: { personId: String(into.id) } }) } })
      setKeep(null)
      onMerged?.(into)
      onClose()
    } catch (e) {
      toast({ title: "Couldn't merge", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    }
  }
  return (
    <Dialog
      isOpen={isOpen}
      onOpenChange={(o) => {
        if (!o) {
          setKeep(null)
          onClose()
        }
      }}
      title={`Merge ${plural(people.length, 'person', 'people')}?`}
      size="m"
      footer={
        <>
          <Button variant="secondary" onPress={onClose}>
            Cancel
          </Button>
          <Button variant="primary" busy={merge.isPending} isDisabled={!plan?.into || people.length < 2} onPress={go}>
            {`Merge ${plural(people.length, 'person', 'people')}`}
          </Button>
        </>
      }
    >
      <div className={s.dialogBody} data-testid="merge-dialog">
        <p>Their faces become one person. This can't be undone as one step, but a wrong face can be moved out again with <em>Not this person</em>.</p>
        <RacRadioGroup value={target !== null ? String(target) : null} onChange={(v) => setKeep(Number(v))} className={s.keepList} aria-label="Keep this person">
          <span className={s.slate}>Keep</span>
          {people.map((p) => (
            <RacRadio key={p.id} value={String(p.id)} className={s.keepRow}>
              <span className={s.dot} aria-hidden="true" />
              <FaceImg src={p.cover} size="s" />
              <span className={s.keepText}>
                <span>{p.label}</span>
                <span className={s.counts}>{personCounts(p)}</span>
              </span>
            </RacRadio>
          ))}
        </RacRadioGroup>
        {plan && plan.dropsNames.length > 0 && (
          <StatusText tone="caution" icon={CircleAlert}>
            {`${plan.dropsNames.join(', ')} ${plan.dropsNames.length === 1 ? 'is' : 'are'} dropped; the merged person keeps the name ${plan.keepsName}.`}
          </StatusText>
        )}
      </div>
    </Dialog>
  )
}

/** "Merge into…" from a person's page: pick the other person from a filterable list. */
export function MergeIntoDialog({ person, isOpen, onClose, onMerged }: { person: PersonSummary; isOpen: boolean; onClose: () => void; onMerged: (into: PersonRef) => void }) {
  const [q, setQ] = useState('')
  const [pick, setPick] = useState<number | null>(null)
  const all = usePeople({ limit: 500 }, { enabled: isOpen })
  const merge = useMergePeople()
  const others = useMemo(() => {
    const t = q.trim().toLowerCase()
    return (all.data?.people ?? []).filter((p) => p.id !== person.id && (!t || p.label.toLowerCase().includes(t)))
  }, [all.data, q, person.id])
  const target = others.find((p) => p.id === pick) ?? (all.data?.people ?? []).find((p) => p.id === pick)
  const plan = target ? mergePlan([person, target], target.id) : null
  const close = () => {
    setPick(null)
    setQ('')
    onClose()
  }
  const go = async () => {
    if (!target) return
    try {
      await merge.mutateAsync({ from: person.id, into: target.id })
      toast({ title: `Merged ${person.label} into ${plan?.keepsName ?? target.label}` })
      onMerged(target)
      close()
    } catch (e) {
      toast({ title: "Couldn't merge", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    }
  }
  return (
    <Dialog
      isOpen={isOpen}
      onOpenChange={(o) => !o && close()}
      title={`Merge ${person.label} into…`}
      size="m"
      footer={
        <>
          <Button variant="secondary" onPress={close}>
            Cancel
          </Button>
          <Button variant="primary" busy={merge.isPending} isDisabled={!target} onPress={go}>
            {target ? `Merge into ${target.label}` : 'Merge'}
          </Button>
        </>
      }
    >
      <div className={s.dialogBody}>
        <p>
          {person.label}'s {plural(person.faces, 'face')} move to the person you pick, and {person.label} goes away. A wrong face can be moved out again with{' '}
          <em>Not this person</em>.
        </p>
        <TextField aria-label="Filter people" placeholder="Filter by name" value={q} onChange={setQ} autoFocus />
        <ListBox
          aria-label="Merge into"
          selectionMode="single"
          selectedKeys={pick !== null ? [String(pick)] : []}
          onSelectionChange={(keys) => {
            const k = [...(keys as Set<string>)][0]
            setPick(k ? Number(k) : null)
          }}
          className={s.pickList}
          items={others}
          renderEmptyState={() => <div className={s.hint}>{all.isLoading ? 'Loading people…' : 'No one matches.'}</div>}
        >
          {(p) => (
            <ListBoxItem id={String(p.id)} textValue={p.label} className={s.pickRow}>
              <FaceImg src={p.cover} size="s" />
              <span className={s.keepText}>
                <span>{p.label}</span>
                <span className={s.counts}>{personCounts(p)}</span>
              </span>
            </ListBoxItem>
          )}
        </ListBox>
        {plan && plan.dropsNames.length > 0 && <StatusText tone="caution" icon={CircleAlert}>{`${plan.dropsNames.join(', ')} is dropped; the merged person keeps the name ${plan.keepsName}.`}</StatusText>}
      </div>
    </Dialog>
  )
}

/** Forget (admin): deletes this person's face crops and embeddings. Confirm names exactly what goes. */
export function ForgetDialog({ person, isOpen, onClose, onForgotten }: { person: PersonSummary; isOpen: boolean; onClose: () => void; onForgotten: () => void }) {
  const forget = useForgetPerson()
  const go = async () => {
    try {
      const r = await forget.mutateAsync(person.id)
      toast({ title: `Forgot ${person.label}`, description: `${plural(r.faces_deleted, 'face crop')} and their face embeddings were deleted.`, tone: 'info' })
      onClose()
      onForgotten()
    } catch (e) {
      toast({ title: "Couldn't forget this person", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    }
  }
  return (
    <Dialog
      isOpen={isOpen}
      onOpenChange={(o) => !o && onClose()}
      title={`Forget ${person.label}?`}
      size="s"
      role="alertdialog"
      footer={
        <>
          <Button variant="secondary" autoFocus onPress={onClose}>
            Cancel
          </Button>
          <Button variant="dangerFilled" busy={forget.isPending} onPress={go}>
            {`Forget ${person.label}`}
          </Button>
        </>
      }
    >
      <div className={s.dialogBody} data-testid="forget-dialog">
        <p>
          <strong>
            This deletes {plural(person.faces, 'face crop')} and their face embeddings from this library
            {person.name ? `, and the name ${person.name}` : ''}.
          </strong>{' '}
          {person.label} disappears from {plural(person.shots, 'shot')} in {plural(person.files, 'file')}. The footage, the shots and every other tag stay.
        </p>
        <p className={s.hint}>It can't be undone. If these files are analysed again, their faces may be found again as a new, unnamed person.</p>
      </div>
    </Dialog>
  )
}

/** Search for this person: by name when named, else by identity (both are hard filters in the core). */
export function useFindShots() {
  const navigate = useNavigate()
  return (p: PersonRef) => navigate({ to: '/search', search: personSearch(p) })
}
