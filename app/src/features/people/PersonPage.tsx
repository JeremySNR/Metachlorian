import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from '@tanstack/react-router'
import { Check, ChevronLeft, Combine, PenLine, Search, Trash2, UserRoundX } from 'lucide-react'
import type { Face, PersonSummary } from '../../api/types'
import { ApiError } from '../../api/client'
import { useAssets, useAssignFace, usePerson } from '../../api/queries'
import { Button } from '../../components/Button'
import { EmptyState } from '../../components/EmptyState'
import { Timecode } from '../../components/Timecode'
import { toast } from '../../components/Toast'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { plural } from '../../lib/format'
import { groupFacesByFile } from '../../lib/people'
import { FaceImg, ForgetDialog, MergeIntoDialog, NameEditor, useFindShots, usePeopleRights } from './shared'
import l from '../library/Library.module.css'
import s from './People.module.css'

/** One person: every face, grouped by file and linked to its shot, with naming, merging and forgetting. */
export function PersonPage() {
  const { personId } = useParams({ from: '/people/$personId' })
  const id = Number(personId)
  const person = usePerson(Number.isFinite(id) ? id : null)
  const navigate = useNavigate()
  const assign = useAssignFace()
  const findShots = useFindShots()
  const { canWrite, isAdmin } = usePeopleRights()
  const assets = useAssets()
  const [editing, setEditing] = useState(false)
  const [mergeOpen, setMergeOpen] = useState(false)
  const [forgetOpen, setForgetOpen] = useState(false)
  const d = person.data
  useDocumentTitle(d?.label ?? 'Person', 'People')

  const groups = useMemo(() => groupFacesByFile(d?.faces ?? []), [d])
  // Face rows carry no frame rate; the file list has it (for timecode, §0 rule 5).
  const fpsOf = useMemo(() => new Map((assets.data?.assets ?? []).map((a) => [a.uid, a.fps])), [assets.data])
  const summary: PersonSummary | null = d
    ? {
        id: d.id, name: d.name, label: d.label, named: Boolean(d.name), faces: d.faces.length, shots: d.shot_uids.length, files: groups.length,
        cover: [...d.faces].sort((a, b) => b.size_px - a.size_px)[0]?.thumb ?? null,
      }
    : null

  if (person.isError && !d) {
    const gone = person.error instanceof ApiError && person.error.status === 404
    return (
      <main id="main" className={l.page}>
        <EmptyState title={gone ? 'This person isn’t in the library any more' : 'Couldn’t load this person'} role="alert" actions={<Button variant="secondary" onPress={() => navigate({ to: '/people' })}>Back to People</Button>}>
          {gone ? 'They may have been merged into someone else, or forgotten.' : (person.error as Error).message}
        </EmptyState>
      </main>
    )
  }
  if (!d || !summary) return <main id="main" className={l.page} aria-busy="true" />

  const notThis = async (face: Face) => {
    try {
      const r = await assign.mutateAsync({ faceId: face.id, identityId: null })
      toast({
        title: `Moved the face to a new person, Person ${r.identity_id}`,
        description: `${face.filename} · shot ${face.shot_number}`,
        action: {
          label: 'Undo',
          onAction: () =>
            assign.mutate(
              { faceId: face.id, identityId: d.id },
              { onError: (e) => toast({ title: "Couldn't undo", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' }) },
            ),
        },
      })
    } catch (e) {
      toast({ title: "Couldn't move the face", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    }
  }

  const only = d.faces.length <= 1
  return (
    <main id="main" className={l.page}>
      <div className={l.inner}>
        <div className={s.personHead}>
          <Link to="/people" className={s.back}>
            <ChevronLeft size={16} strokeWidth={1.75} aria-hidden="true" />
            People
          </Link>
          <div className={s.personTitle}>
            <FaceImg src={summary.cover} size="l" />
            <div className={s.personText}>
              {editing ? (
                <NameEditor person={d} onDone={() => setEditing(false)} onMerge={() => { setEditing(false); setMergeOpen(true) }} />
              ) : (
                <h1 className={d.name ? undefined : s.unnamedTitle}>{d.label}</h1>
              )}
              <p className={s.counts}>
                {plural(summary.faces, 'face')} · {plural(summary.shots, 'shot')} · {plural(summary.files, 'file')}
                {d.name && d.named_by ? ` · named by ${d.named_by === 'local' ? 'you' : d.named_by}` : ''}
              </p>
            </div>
          </div>
          <div className={s.actions}>
            <Button variant="primary" icon={Search} onPress={() => findShots(d)}>
              Find shots with this person
            </Button>
            {canWrite && !editing && (
              <Button variant="secondary" icon={PenLine} onPress={() => setEditing(true)}>
                {d.name ? 'Rename' : 'Name this person'}
              </Button>
            )}
            {canWrite && (
              <Button variant="secondary" icon={Combine} onPress={() => setMergeOpen(true)}>
                Merge into…
              </Button>
            )}
            {isAdmin && (
              <Button variant="danger" icon={Trash2} onPress={() => setForgetOpen(true)}>
                Forget this person
              </Button>
            )}
          </div>
          {!d.name && <p className={s.hint}>Search can only filter by a name once they have one; until then, Find shots uses this group of faces.</p>}
        </div>

        {groups.map((g) => (
          <section key={g.asset_uid} className={l.section} aria-labelledby={`g-${g.asset_uid}`}>
            <div className={l.sectionHead}>
              <h2 id={`g-${g.asset_uid}`}>
                <Link to="/file/$assetId" params={{ assetId: g.asset_uid }} className={s.fileLink}>
                  {g.filename}
                </Link>
              </h2>
              <span className={s.sectionCount}>
                {plural(g.faces.length, 'face')} · {plural(g.shots, 'shot')}
              </span>
            </div>
            <ul className={s.faces} aria-label={`Faces in ${g.filename}`}>
              {g.faces.map((face) => (
                <li key={face.id} className={s.faceItem} data-testid="face-item" data-face={face.id}>
                  <Link to="/shot/$shotId" params={{ shotId: face.shot_uid }} className={s.frameLink} aria-label={`Shot ${face.shot_number}, ${face.filename}`}>
                    <FaceImg src={face.thumb} size="m" />
                  </Link>
                  <span className={s.faceMeta}>
                    <span>Shot {face.shot_number}</span>
                    <Timecode seconds={face.t} fps={fpsOf.get(face.asset_uid) ?? null} size="xs" />
                  </span>
                  {face.confirmed && (
                    <span className={s.confirmed}>
                      <Check size={12} strokeWidth={2} aria-hidden="true" />
                      Confirmed
                    </span>
                  )}
                  {canWrite && (
                    <Button
                      variant="quiet"
                      size="sm"
                      icon={UserRoundX}
                      isDisabled={only || assign.isPending}
                      disabledReason={only ? 'This is their only face. Forget the person instead.' : undefined}
                      aria-label={`Not this person: shot ${face.shot_number}, ${face.filename}`}
                      onPress={() => notThis(face)}
                    >
                      Not this person
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
      <MergeIntoDialog person={summary} isOpen={mergeOpen} onClose={() => setMergeOpen(false)} onMerged={(into) => navigate({ to: '/people/$personId', params: { personId: String(into.id) }, replace: true })} />
      {isAdmin && <ForgetDialog person={summary} isOpen={forgetOpen} onClose={() => setForgetOpen(false)} onForgotten={() => navigate({ to: '/people', replace: true })} />}
    </main>
  )
}
