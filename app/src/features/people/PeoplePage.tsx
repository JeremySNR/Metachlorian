import { useState } from 'react'
import { Link, useNavigate, useSearch } from '@tanstack/react-router'
import { Combine, HardDrive, Lock, PenLine, ScanFace, X } from 'lucide-react'
import type { PersonSummary } from '../../api/types'
import { usePeople } from '../../api/queries'
import { Button, IconButton } from '../../components/Button'
import { EmptyState, StatusText } from '../../components/EmptyState'
import { Checkbox, TextField } from '../../components/Field'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { isTyping, useDocumentKeys } from '../../hooks/useHotkeys'
import { formatNumber } from '../../lib/format'
import { personCounts } from '../../lib/people'
import { FaceImg, MergeDialog, NameEditor, usePeopleRights } from './shared'
import l from '../library/Library.module.css'
import s from './People.module.css'

const PERSON_MIME = 'application/x-metachlorian-person'
const PAGE = 120

/** People (face identity): named first, then unnamed clusters to name, largest first. */
export function PeoplePage() {
  const { q = '' } = useSearch({ from: '/people' })
  const navigate = useNavigate({ from: '/people' })
  const [filter, setFilter] = useState(q)
  const [pages, setPages] = useState(1)
  const named = usePeople({ named: true, q: q || undefined, limit: 500 })
  const unnamed = usePeople({ named: false, limit: PAGE * pages }, { enabled: !q })
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [merging, setMerging] = useState<PersonSummary[] | null>(null)
  const { canWrite } = usePeopleRights()
  useDocumentTitle('People')

  const all = [...(named.data?.people ?? []), ...(unnamed.data?.people ?? [])]
  const byId = new Map(all.map((p) => [p.id, p]))
  const chosen = [...selected].map((id) => byId.get(id)).filter((p): p is PersonSummary => Boolean(p))
  const enabled = named.data?.enabled ?? unnamed.data?.enabled ?? true
  const totalNamed = named.data?.total ?? 0
  const totalUnnamed = unnamed.data?.total ?? 0
  const loading = named.isLoading || (!q && unnamed.isLoading)
  const error = named.error ?? unnamed.error

  const toggle = (id: number, on: boolean) =>
    setSelected((cur) => {
      const next = new Set(cur)
      if (on) next.add(id)
      else next.delete(id)
      return next
    })

  useDocumentKeys((e) => {
    if (e.key === 'Escape' && selected.size && !isTyping(e.target) && !document.querySelector('[role="dialog"], [role="alertdialog"]')) setSelected(new Set())
  })

  const applyFilter = (v: string) => {
    setFilter(v)
    navigate({ search: v.trim() ? { q: v.trim() } : {}, replace: true })
  }

  const empty = !loading && !error && totalNamed === 0 && totalUnnamed === 0
  return (
    <main id="main" className={l.page} aria-busy={loading || undefined}>
      <div className={l.inner}>
        <div className={l.titleRow}>
          <h1>People</h1>
          <TextField aria-label="Find a person by name" placeholder="Find by name" value={filter} onChange={applyFilter} className={s.filter} />
        </div>
        <p className={s.privacy}>
          <Lock size={16} strokeWidth={1.75} aria-hidden="true" />
          <span>
            Faces are matched on this machine. Face crops and embeddings stay in this library, are never sent to model providers, and can be forgotten.{' '}
            <Link to="/settings/$section" params={{ section: 'privacy' }}>
              Privacy and analysis settings
            </Link>
          </span>
        </p>
        {!enabled && (
          <StatusText tone="info" icon={HardDrive} className={s.offNote}>
            Face recognition is off: no new faces are matched. People already found stay until you forget them.
          </StatusText>
        )}
        {error ? (
          <EmptyState title="Couldn't load people" role="alert">
            {(error as Error).message}
          </EmptyState>
        ) : empty && !q ? (
          enabled ? (
            <EmptyState icon={ScanFace} title="No faces found yet" actions={<Button variant="secondary" onPress={() => navigate({ to: '/ingest' })}>See analysis progress</Button>}>
              People appear here as files are analysed. Faces large enough to recognise are grouped into people you can name.
            </EmptyState>
          ) : (
            <EmptyState
              icon={ScanFace}
              title="Face recognition is off"
              actions={<Button variant="secondary" onPress={() => navigate({ to: '/settings/$section', params: { section: 'privacy' } })}>Open privacy settings</Button>}
            >
              Turn it on to find faces, name people and search by person. It runs only on this machine, and an admin can switch it off again at any time.
            </EmptyState>
          )
        ) : (
          <>
            <section className={l.section} aria-labelledby="named-h">
              <div className={l.sectionHead}>
                <h2 id="named-h">{q ? `Named “${q}”` : 'Named'}</h2>
                <span className={s.sectionCount}>{formatNumber(totalNamed)}</span>
              </div>
              {named.data && named.data.people.length === 0 ? (
                <p className={s.hint}>{q ? `No one is named “${q}”.` : 'No one is named yet. Name someone below and every shot they are in becomes searchable by their name.'}</p>
              ) : (
                <PeopleGrid people={named.data?.people ?? []} selected={selected} onToggle={toggle} canWrite={canWrite} onMerge={setMerging} label="Named people" />
              )}
            </section>
            {!q && (
              <section className={l.section} aria-labelledby="unnamed-h">
                <div className={l.sectionHead}>
                  <h2 id="unnamed-h">Unnamed: help name them</h2>
                  <span className={s.sectionCount}>{formatNumber(totalUnnamed)}</span>
                </div>
                <p className={s.hint}>Largest groups first. Two groups that are the same person can be merged: select both, or drag one onto the other.</p>
                <PeopleGrid people={unnamed.data?.people ?? []} selected={selected} onToggle={toggle} canWrite={canWrite} onMerge={setMerging} label="Unnamed people" />
                {totalUnnamed > (unnamed.data?.people.length ?? 0) && (
                  <div>
                    <Button variant="secondary" busy={unnamed.isFetching} onPress={() => setPages((n) => n + 1)}>
                      {`Show ${formatNumber(Math.min(PAGE, totalUnnamed - (unnamed.data?.people.length ?? 0)))} more`}
                    </Button>
                  </div>
                )}
              </section>
            )}
          </>
        )}
      </div>
      {selected.size > 0 && (
        <div className={s.selectionBar} role="region" aria-label="Selection" data-testid="people-selection">
          <span className={s.selCount}>
            <strong>{selected.size}</strong> selected
          </span>
          <Button variant="quiet" size="sm" icon={X} shortcut="Esc" onPress={() => setSelected(new Set())}>
            Clear
          </Button>
          <span className={s.selHint}>{selected.size < 2 ? 'Select one more to merge them.' : chosen.map((p) => p.label).join(', ')}</span>
          {canWrite && (
            <Button variant="primary" icon={Combine} isDisabled={chosen.length < 2} disabledReason={chosen.length < 2 ? 'Select at least two people' : undefined} onPress={() => setMerging(chosen)}>
              {chosen.length >= 2 ? `Merge ${chosen.length}…` : 'Merge…'}
            </Button>
          )}
        </div>
      )}
      <MergeDialog people={merging ?? []} isOpen={Boolean(merging)} onClose={() => setMerging(null)} onMerged={() => setSelected(new Set())} />
    </main>
  )
}

function PeopleGrid({ people, selected, onToggle, canWrite, onMerge, label }: { people: PersonSummary[]; selected: Set<number>; onToggle: (id: number, on: boolean) => void; canWrite: boolean; onMerge: (p: PersonSummary[]) => void; label: string }) {
  return (
    <ul className={s.grid} aria-label={label}>
      {people.map((p) => (
        <PersonTile key={p.id} person={p} selected={selected.has(p.id)} onToggle={(on) => onToggle(p.id, on)} canWrite={canWrite} onDropPerson={(from) => onMerge([from, p])} people={people} />
      ))}
    </ul>
  )
}

function PersonTile({ person, selected, onToggle, canWrite, onDropPerson, people }: { person: PersonSummary; selected: boolean; onToggle: (on: boolean) => void; canWrite: boolean; onDropPerson: (from: PersonSummary) => void; people: PersonSummary[] }) {
  const [editing, setEditing] = useState(false)
  const [over, setOver] = useState(false)
  const [mergeInto, setMergeInto] = useState<PersonSummary | null>(null)
  const counts = personCounts(person)
  return (
    <li
      className={s.tile}
      data-selected={selected || undefined}
      data-drop-target={over || undefined}
      data-testid="person-tile"
      data-person={person.id}
      draggable={canWrite && !editing}
      onDragStart={(e) => {
        e.dataTransfer.setData(PERSON_MIME, JSON.stringify(person))
        e.dataTransfer.effectAllowed = 'move'
      }}
      onDragOver={(e) => {
        if (!canWrite || !e.dataTransfer.types.includes(PERSON_MIME)) return
        e.preventDefault()
        e.dataTransfer.dropEffect = 'move'
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => {
        setOver(false)
        const raw = e.dataTransfer.getData(PERSON_MIME)
        if (!raw) return
        e.preventDefault()
        const from = JSON.parse(raw) as PersonSummary
        if (from.id !== person.id) onDropPerson(from)
      }}
    >
      <div className={s.frame}>
        <Link to="/people/$personId" params={{ personId: String(person.id) }} className={s.frameLink} aria-label={`${person.label}, ${counts}`} draggable={false}>
          <FaceImg src={person.cover} size="l" />
        </Link>
        <Checkbox selection isSelected={selected} onChange={onToggle} aria-label={`Select ${person.label}`} className={s.tileCheck} />
      </div>
      <div className={s.tileBody}>
        {editing ? (
          <NameEditor
            person={person}
            onDone={() => setEditing(false)}
            onMerge={(into) => {
              setEditing(false)
              setMergeInto(into)
            }}
          />
        ) : (
          <>
            <div className={s.nameLine}>
              <Link to="/people/$personId" params={{ personId: String(person.id) }} className={person.named ? s.name : s.unnamedLabel} tabIndex={-1}>
                {person.label}
              </Link>
              {canWrite && person.named && <IconButton icon={PenLine} label={`Rename ${person.label}`} size="sm" onPress={() => setEditing(true)} />}
            </div>
            <span className={s.counts}>{counts}</span>
            {canWrite && !person.named && (
              <Button variant="quiet" size="sm" icon={PenLine} onPress={() => setEditing(true)} className={s.nameButton} aria-label={`Name ${person.label}`}>
                Name this person
              </Button>
            )}
          </>
        )}
      </div>
      {mergeInto && (
        <MergeDialog
          people={[person, people.find((p) => p.id === mergeInto.id) ?? mergeInto]}
          isOpen
          onClose={() => setMergeInto(null)}
        />
      )}
    </li>
  )
}


