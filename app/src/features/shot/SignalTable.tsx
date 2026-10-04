import { useRef, useState } from 'react'
import { Check, ChevronRight, PenLine, Undo2, X } from 'lucide-react'
import type { CorrectionKind, FieldValue, ShotDoc, Vocabulary } from '../../api/types'
import { useCorrect, useCorrections, useRevertCorrection, type CorrectionInput } from '../../api/queries'
import { ApiError } from '../../api/client'
import { Button, IconButton } from '../../components/Button'
import { ComboBox, NumberField, Switch, TextField } from '../../components/Field'
import { ConfidenceMeter } from '../../components/ConfidenceMeter'
import { HumanMarker } from '../../components/HumanMarker'
import { Swatches } from '../../components/EmptyState'
import { toast } from '../../components/Toast'
import { humanise, shortLabel } from '../../lib/format'
import { renderValue, signalRows, sourceLabel, technicalRows, termIds, valueText, VOCAB_FIELDS, SIGNAL_GROUPS, type SignalRow } from '../../lib/signals'
import t from '../../styles/type.module.css'
import s from './Shot.module.css'

interface Props {
  shot: ShotDoc
  vocabs: Record<string, Vocabulary>
  label: (vocab: string, term: string) => string
  /** Start with this field in edit mode (E from the grid). */
  editField?: string | null
  groups?: string[]
  /** Fold the measurement groups (Quality, Look) behind a disclosure, so rights and content come first. */
  collapsible?: boolean
}

const FOLDED: string[] = ['Quality', 'Look']

/**
 * Signals with source, confidence and human-correction state (system.md §3.10).
 * Keyboard: ↑/↓ move, Enter confirms, Delete removes, E edits, Esc cancels.
 */
export function SignalTable({ shot, vocabs, label, editField, groups, collapsible }: Props) {
  const corrections = useCorrections()
  const correctable = corrections.data?.correctable.shot ?? {}
  const rows = signalRows(shot.fields, correctable)
  const [editing, setEditing] = useState<string | null>(editField ?? null)
  const [focusField, setFocusField] = useState<string | null>(null)
  const rootRef = useRef<HTMLDivElement>(null)
  const correct = useCorrect()
  const revert = useRevertCorrection()
  const [showFolded, setShowFolded] = useState(false)
  const folded = (g: string) => Boolean(collapsible && !showFolded && FOLDED.includes(g) && !(editField && rows.get(g as never)?.some((r) => r.field === editField)))
  const foldedCount = collapsible ? FOLDED.reduce((n, g) => n + (rows.get(g as never)?.length ?? 0), 0) : 0

  const [seenEdit, setSeenEdit] = useState(editField)
  if (editField !== seenEdit) {
    setSeenEdit(editField)
    if (editField) {
      setEditing(editField)
      setFocusField(editField)
    }
  }

  const flat: SignalRow[] = SIGNAL_GROUPS.flatMap((g) => (groups && !groups.includes(g)) || folded(g) ? [] : rows.get(g) ?? [])
  const current = focusField ?? flat[0]?.field

  const send = async (c: Omit<CorrectionInput, 'shot_uid'>, what: string) => {
    try {
      const res = await correct.mutateAsync({ ...c, shot_uid: shot.uid })
      setEditing(null)
      toast({
        title: 'Saved. This tag will stay as you set it, even if the shot is re-analysed.',
        description: what,
        action: { label: 'Undo', onAction: () => revert.mutate(res.correction_id) },
      })
    } catch (e) {
      toast({ title: "Couldn't save the correction", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    }
  }

  const confirm = (row: SignalRow) => {
    const v = row.fv.value
    const kind = row.kind
    if (!kind) return
    let value: unknown
    if (kind === 'term') value = termIds(v)[0]
    else if (kind === 'terms') value = termIds(v)
    else {
      const r = renderValue(row.field, v)
      value = r.kind === 'text' ? (typeof (v as { value?: unknown })?.value !== 'undefined' ? (v as { value: unknown }).value : v) : v
    }
    if (value === undefined || value === null) return
    send({ field: row.field, op: 'set', value }, `${row.label}: confirmed`)
  }

  const focusRow = (field: string) => {
    setFocusField(field)
    requestAnimationFrame(() => rootRef.current?.querySelector<HTMLElement>(`[data-field="${field}"]`)?.focus())
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if ((e.target as HTMLElement).closest('input, textarea, [role=combobox], [role=listbox]')) return
    const i = flat.findIndex((r) => r.field === current)
    const row = flat[i]
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      const next = flat[Math.max(0, Math.min(flat.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))]
      if (next) focusRow(next.field)
    } else if (!row || !row.kind) {
      return
    } else if (e.key === 'Enter') {
      e.preventDefault()
      confirm(row)
    } else if (e.key.toLowerCase() === 'e' && !e.metaKey && !e.ctrlKey) {
      e.preventDefault()
      setEditing(row.field)
    } else if (e.key === 'Escape' && editing) {
      e.preventDefault()
      setEditing(null)
      focusRow(row.field)
    } else if ((e.key === 'Delete' || e.key === 'Backspace') && row.kind === 'terms') {
      e.preventDefault()
      const ids = termIds(row.fv.value)
      const last = ids[ids.length - 1]
      if (last) send({ field: row.field, op: 'remove', value: last }, `${row.label}: removed ${humaniseTerm(row.field, last, label)}`)
    }
  }

  return (
    <div className={s.signals} ref={rootRef} role="grid" aria-label="Signals" onKeyDown={onKeyDown} data-testid="signals">
      {SIGNAL_GROUPS.map((g) => {
        if (groups && !groups.includes(g)) return null
        if (folded(g)) {
          if (g !== FOLDED[0] || !foldedCount) return null
          return (
            <div key="folded" role="row">
              <span role="gridcell">
                <Button variant="quiet" size="sm" icon={ChevronRight} onPress={() => setShowFolded(true)} aria-expanded={false} className={s.foldButton}>
                  {`Show quality and look measurements (${foldedCount})`}
                </Button>
              </span>
            </div>
          )
        }
        if (g === 'Technical') {
          const tech = technicalRows(shot.technical)
          if (!tech.length) return null
          return (
            <div key={g} role="rowgroup">
              <div className={s.groupHead} role="row">
                <span role="columnheader">Technical · Camera metadata</span>
              </div>
              <dl className={s.techTable}>
                {tech.map(([k, v]) => (
                  <div key={k} style={{ display: 'contents' }}>
                    <dt>{k}</dt>
                    <dd>{v}</dd>
                  </div>
                ))}
              </dl>
            </div>
          )
        }
        const list = rows.get(g) ?? []
        if (!list.length) return null
        return (
          <div key={g} role="rowgroup">
            <div className={s.groupHead} role="row">
              <span role="columnheader">{g}</span>
            </div>
            {list.map((row) => (
              <Row
                key={row.field}
                row={row}
                focused={row.field === current}
                editing={editing === row.field}
                vocabs={vocabs}
                label={label}
                onFocus={() => setFocusField(row.field)}
                onEdit={() => setEditing(row.field)}
                onCancel={() => {
                  setEditing(null)
                  focusRow(row.field)
                }}
                onConfirm={() => confirm(row)}
                onSend={send}
                onRevert={() => row.fv.correction_id && revert.mutate(row.fv.correction_id, { onSuccess: () => toast({ title: `${row.label} is back to the model's value`, tone: 'info' }) })}
                busy={correct.isPending}
              />
            ))}
          </div>
        )
      })}
    </div>
  )
}

function humaniseTerm(field: string, term: string, label: (v: string, t: string) => string) {
  const v = VOCAB_FIELDS[field]?.vocab
  return v ? label(v, term) : humanise(term)
}

function isConfirmed(fv: FieldValue): boolean {
  if (!fv.corrected) return false
  const a = termIds(fv.value).sort().join('|')
  const b = termIds(fv.machine).sort().join('|')
  if (a || b) return a === b
  const sv = (x: unknown) => JSON.stringify(x && typeof x === 'object' && 'value' in (x as object) ? (x as { value: unknown }).value : x)
  return sv(fv.value) === sv(fv.machine)
}

interface RowProps {
  row: SignalRow
  focused: boolean
  editing: boolean
  vocabs: Record<string, Vocabulary>
  label: (vocab: string, term: string) => string
  onFocus: () => void
  onEdit: () => void
  onCancel: () => void
  onConfirm: () => void
  onSend: (c: Omit<CorrectionInput, 'shot_uid'>, what: string) => void
  onRevert: () => void
  busy: boolean
}

function Row({ row, focused, editing, vocabs, label, onFocus, onEdit, onCancel, onConfirm, onSend, onRevert, busy }: RowProps) {
  const { fv, field } = row
  const r = renderValue(field, fv.value)
  const vocab = VOCAB_FIELDS[field]?.vocab
  const corrected = Boolean(fv.corrected)
  const confirmed = isConfirmed(fv)
  const modelSaid = corrected && !confirmed ? valueText(field, fv.machine, label) : null
  const termLabel = (term: string) => (vocab ? label(vocab, term) : humanise(term))
  const machineTerms = new Set(termIds(fv.machine))
  const removedTerms = corrected && r.kind === 'terms' ? [...machineTerms].filter((x) => !r.items.some((i) => i.term === x)) : []
  // Multi-value rows: each value carries its own confidence and its own remove button.
  const multi = r.kind === 'terms' && row.kind === 'terms' && (r.items.length > 1 || VOCAB_FIELDS[field]?.multi === true)
  const perValue = multi && r.kind === 'terms' && r.items.some((i) => i.confidence !== null)

  const conf = (c: number | null) => (c === null || c >= 1 ? '' : `${Math.round(c * 100)}${c < 0.6 ? ' low' : ''}`)
  const valueNames = r.kind === 'terms' ? r.items.map((i) => `${termLabel(i.term)}${!corrected && conf(i.confidence) ? ` (confidence ${conf(i.confidence)})` : ''}`).join(', ') : valueText(field, fv.value, label)
  const name = `${row.label}: ${valueNames}. ${corrected ? (confirmed ? 'Confirmed by a person' : `Corrected by a person${modelSaid ? `. Model said: ${modelSaid}` : ''}`) : `${sourceLabel(fv)}${!perValue && fv.confidence !== null ? `, confidence ${Math.round((fv.confidence ?? 0) * 100)}` : ''}`}`

  return (
    <div className={s.row} role="row" tabIndex={focused ? 0 : -1} data-field={field} aria-label={name} onFocus={(e) => e.target === e.currentTarget && onFocus()} data-corrected={corrected || undefined}>
      <span className={s.rowLabel} role="rowheader">
        {row.label}
      </span>
      <span className={s.rowValue} role="gridcell">
        {(r.kind === 'terms' || removedTerms.length > 0) && (
          <span className={multi ? s.termList : undefined}>
            {r.kind === 'terms' &&
              r.items.map((i, k) =>
                multi ? (
                  <span key={i.term} className={s.valueChip}>
                    <span>{termLabel(i.term)}</span>
                    {!corrected && conf(i.confidence) && <span className={`${s.valueConf} ${(i.confidence ?? 1) < 0.6 ? s.valueLow : ''}`}>{conf(i.confidence)}</span>}
                    <IconButton
                      icon={X}
                      label={`Remove ${termLabel(i.term)} from ${row.label}`}
                      size="sm"
                      className={s.valueRemove}
                      excludeFromTabOrder
                      tooltip={false}
                      onPress={() => onSend({ field, op: 'remove', value: i.term }, `${row.label}: removed ${termLabel(i.term)}`)}
                    />
                  </span>
                ) : (
                  <span key={i.term} title={i.confidence !== null && i.confidence < 1 ? `Confidence ${Math.round(i.confidence * 100)}` : undefined}>
                    {k > 0 ? ', ' : ''}
                    {termLabel(i.term)}
                  </span>
                ),
              )}
            {removedTerms.map((term, k) => (
              <span key={term}>
                {!multi && (k > 0 || (r.kind === 'terms' && r.items.length)) ? ', ' : ''}
                <span className={s.removed} aria-label={`${termLabel(term)}, removed`}>
                  {termLabel(term)}
                </span>
              </span>
            ))}
          </span>
        )}
        {r.kind === 'text' && <span>{r.text}</span>}
        {r.kind === 'colours' && <Swatches colours={r.colours} />}
        {r.kind === 'empty' && <span className={s.empty}>None</span>}
      </span>
      <span className={s.rowMeta}>
        {corrected ? (
          <>
            <HumanMarker by={fv.corrected_by} at={fv.corrected_at} modelSaid={modelSaid} confirmed={confirmed} />
            <span>{confirmed ? 'Confirmed' : 'Human'}</span>
            {modelSaid && <span className={s.modelSaid}>Model said: {modelSaid}</span>}
          </>
        ) : (
          <>
            <span>{sourceLabel(fv)}</span>
            {r.kind !== 'empty' && !perValue && <ConfidenceMeter value={fv.confidence} label={row.label} />}
          </>
        )}
      </span>
      {row.kind && (
        <span className={s.rowActions} role="gridcell">
          {corrected ? (
            <IconButton icon={Undo2} label={`Undo correction to ${row.label}`} size="sm" onPress={onRevert} excludeFromTabOrder />
          ) : (
            r.kind !== 'empty' && <IconButton icon={Check} label={`Confirm ${row.label}`} shortcut="Enter" size="sm" onPress={onConfirm} excludeFromTabOrder />
          )}
          <IconButton icon={PenLine} label={`Edit ${row.label}`} shortcut="E" size="sm" onPress={onEdit} excludeFromTabOrder data-testid={`edit-${field}`} />
        </span>
      )}
      {editing && row.kind && <Editor row={row} kind={row.kind} vocab={vocab} vocabs={vocabs} termLabel={termLabel} onSend={onSend} onCancel={onCancel} busy={busy} />}
    </div>
  )
}

function Editor({ row, kind, vocab, vocabs, termLabel, onSend, onCancel, busy }: { row: SignalRow; kind: CorrectionKind; vocab?: string; vocabs: Record<string, Vocabulary>; termLabel: (t: string) => string; onSend: RowProps['onSend']; onCancel: () => void; busy: boolean }) {
  const { field, fv } = row
  const options = (vocab ? vocabs[vocab]?.terms ?? [] : []).map((x) => ({ id: x.id, label: shortLabel(x.label) }))
  const current = termIds(fv.value)
  const scalar = (() => {
    const v = fv.value as { value?: unknown } | unknown
    return v && typeof v === 'object' && 'value' in (v as object) ? (v as { value: unknown }).value : v
  })()
  const [text, setText] = useState(typeof scalar === 'string' ? scalar : '')
  const [num, setNum] = useState(typeof scalar === 'number' ? scalar : 0)
  const [input, setInput] = useState('')
  const keyHandler = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') {
      e.stopPropagation()
      onCancel()
    }
  }
  return (
    <div className={s.edit} onKeyDown={keyHandler} data-testid="signal-editor">
      {(kind === 'term' || kind === 'terms') && (
        <>
          {kind === 'terms' && current.length > 0 && (
            <div className={s.rowValue}>
              {current.map((term) => (
                <span key={term} className={s.editTerm}>
                  {termLabel(term)}
                  <IconButton icon={X} label={`Remove ${termLabel(term)}`} size="sm" onPress={() => onSend({ field, op: 'remove', value: term }, `${row.label}: removed ${termLabel(term)}`)} />
                </span>
              ))}
            </div>
          )}
          <div className={s.editRow}>
            <ComboBox
              aria-label={kind === 'terms' ? `Add to ${row.label}` : `Set ${row.label}`}
              placeholder={kind === 'terms' ? 'Add a value' : 'Choose a value'}
              options={options.filter((o) => !current.includes(o.id))}
              autoFocus
              allowsCustomValue={!vocab}
              inputValue={input}
              onInputChange={setInput}
              onSelectionChange={(k) => {
                if (!k) return
                const term = String(k)
                setInput('')
                onSend({ field, op: kind === 'terms' ? 'add' : 'set', value: term }, `${row.label}: ${termLabel(term)}`)
              }}
              onKeyDown={(e: React.KeyboardEvent) => {
                if (e.key === 'Enter' && !vocab && input.trim()) {
                  onSend({ field, op: 'add', value: input.trim() }, `${row.label}: added ${input.trim()}`)
                  setInput('')
                }
              }}
            />
            <Button variant="quiet" onPress={onCancel}>
              Done
            </Button>
          </div>
        </>
      )}
      {kind === 'text' && (
        <>
          <TextField aria-label={row.label} value={text} onChange={setText} multiline autoFocus />
          <div className={s.editRow} style={{ justifyContent: 'flex-end' }}>
            <Button variant="quiet" onPress={onCancel}>
              Cancel
            </Button>
            <Button variant="secondary" busy={busy} onPress={() => onSend({ field, op: 'set', value: text }, `${row.label} updated`)}>
              Save
            </Button>
          </div>
        </>
      )}
      {kind === 'int' && (
        <div className={s.editRow}>
          <NumberField aria-label={row.label} value={num} minValue={0} onChange={setNum} autoFocus />
          <Button variant="secondary" busy={busy} onPress={() => onSend({ field, op: 'set', value: Math.round(num) }, `${row.label}: ${Math.round(num)}`)}>
            Save
          </Button>
          <Button variant="quiet" onPress={onCancel}>
            Cancel
          </Button>
        </div>
      )}
      {kind === 'bool' && (
        <div className={s.editRow}>
          <Switch isSelected={Boolean(scalar)} onChange={(v) => onSend({ field, op: 'set', value: v }, `${row.label}: ${v ? 'Yes' : 'No'}`)} autoFocus>
            {row.label}
          </Switch>
          <Button variant="quiet" onPress={onCancel}>
            Done
          </Button>
        </div>
      )}
      <span className={t.slate} style={{ textTransform: 'none', letterSpacing: 0 }}>
        Your value outranks the model and survives re-analysis.
      </span>
    </div>
  )
}
