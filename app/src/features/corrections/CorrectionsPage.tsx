import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { Undo2 } from 'lucide-react'
import { ApiError } from '../../api/client'
import { useCorrections, useRevertCorrection, useVocabularies } from '../../api/queries'
import type { Correction } from '../../api/types'
import { useDocumentTitle } from '../../hooks/useDocumentTitle'
import { formatTimecode } from '../../lib/timecode'
import { Button } from '../../components/Button'
import { EmptyState, StatusText } from '../../components/EmptyState'
import { HumanMarker } from '../../components/HumanMarker'
import { Segmented } from '../../components/Segmented'
import { toast } from '../../components/Toast'
import { formatDateTime, formatRelative, humanise } from '../../lib/format'
import { FIELD_META, VOCAB_FIELDS } from '../../lib/signals'
import { usePrefs } from '../../lib/store'
import { LibraryTabs } from '../library/LibraryPage'
import l from '../library/Library.module.css'
import s from './Corrections.module.css'

const OPS: Record<string, string> = { set: 'Set', add: 'Added', remove: 'Removed' }

/** Corrections log (system.md §3.10): every human change, with revert. */
export function CorrectionsPage() {
  const q = useCorrections()
  const revert = useRevertCorrection()
  const { label } = useVocabularies()
  const [filter, setFilter] = useState<'active' | 'all'>('active')
  const rows = (q.data?.corrections ?? []).filter((c) => filter === 'all' || c.active)
  const tcFormat = usePrefs((p) => p.timecodeFormat)
  useDocumentTitle('Corrections', 'Library')

  const valueText = (field: string, v: unknown): string => {
    const vocab = field === 'structure.edit_type' ? 'edit_type' : VOCAB_FIELDS[field]?.vocab
    const one = (x: unknown): string => {
      if (x && typeof x === 'object') {
        const o = x as { term?: unknown; value?: unknown }
        if (o.term !== undefined) return one(o.term)
        if (o.value !== undefined) return one(o.value)
      }
      return typeof x === 'string' && vocab ? label(vocab, x) : typeof x === 'boolean' ? (x ? 'Yes' : 'No') : x === null || x === undefined ? 'nothing' : String(x)
    }
    return Array.isArray(v) ? v.map(one).join(', ') : one(v)
  }

  /** "Night → Morning" for a set; "Removed Night" / "Added Rain" otherwise. */
  const change = (c: Correction) => {
    const before = c.model_value ? valueText(c.field, c.model_value.value) : null
    const after = valueText(c.field, c.value)
    if (c.op === 'set' && before && before !== 'nothing') {
      return (
        <>
          <span className={s.before}>{before}</span>
          {c.model_value?.confidence != null && <span className={s.conf}> ({c.model_value.confidence.toFixed(2)})</span>} → <strong>{after}</strong>
        </>
      )
    }
    return (
      <>
        {OPS[c.op] ?? c.op} <strong>{after}</strong>
        {before && c.op !== 'set' ? <span className={s.conf}> · model had {before}</span> : null}
      </>
    )
  }

  /** "› Shot 9 · 00:00:16:28": the core sends the shot's timecode and frame rate with each row. */
  const where = (c: Correction) => {
    if (!c.shot_uid) return null
    const sh = c.shot
    const tc = sh ? (tcFormat === 'smpte' && sh.timecode ? sh.timecode : formatTimecode(sh.start, sh.fps, tcFormat)) : null
    return (
      <>
        {' › '}
        {sh ? `Shot ${sh.number}` : 'Shot'}
        {tc && <span className={s.tc}> · {tc}</span>}
      </>
    )
  }

  return (
    <main id="main" className={l.page}>
      <div className={l.inner}>
        <div className={l.titleRow}>
          <h1>Corrections</h1>
          <LibraryTabs />
        </div>
        <div className={s.toolbar}>
          <p className={l.muted}>Corrections outrank the models and survive re-analysis. Reverting one hands the value back to the model.</p>
          <Segmented label="Show" value={filter} onChange={setFilter} segments={[{ id: 'active', label: 'In effect' }, { id: 'all', label: 'All, with reverted' }]} />
        </div>
        {q.isError ? (
          <EmptyState title="Couldn't load corrections" role="alert">{(q.error as Error).message}</EmptyState>
        ) : rows.length === 0 && !q.isLoading ? (
          <EmptyState title="No corrections yet">Fix a tag from the inspector (press E on a shot) and it shows up here.</EmptyState>
        ) : (
          <div className={s.wrap}>
            <table className={l.table} data-testid="corrections-table">
              <thead>
                <tr>
                  <th>When</th>
                  <th>Who</th>
                  <th>File · shot</th>
                  <th>Signal</th>
                  <th>Change</th>
                  <th>Note</th>
                  <th>State</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.id}>
                    <td title={formatDateTime(c.created_at)}>{formatRelative(c.created_at)}</td>
                    <td>
                      <HumanMarker by={c.actor} />
                    </td>
                    <td className={s.file}>
                      {c.shot_uid ? (
                        <Link to="/shot/$shotId" params={{ shotId: c.shot_uid }}>
                          {c.filename ?? c.asset_uid}
                          {where(c)}
                        </Link>
                      ) : (
                        <Link to="/file/$assetId" params={{ assetId: c.asset_uid }}>
                          {c.filename ?? c.asset_uid}
                        </Link>
                      )}
                    </td>
                    <td>{FIELD_META[c.field]?.label ?? (c.field === 'structure.edit_type' ? 'Edit stage' : humanise(c.field.split('.').pop()))}</td>
                    <td>{change(c)}</td>
                    <td className={s.note}>{c.note || '—'}</td>
                    <td>{c.active ? <StatusText tone="cleared">In effect</StatusText> : <StatusText tone="neutral">Reverted</StatusText>}</td>
                    <td>
                      {c.active ? (
                        <Button
                          variant="quiet"
                          size="sm"
                          icon={Undo2}
                          onPress={() =>
                            revert.mutate(c.id, {
                              onSuccess: () => toast({ title: 'Correction reverted', description: 'The model value is back.', tone: 'info' }),
                              onError: (e) => toast({ title: "Couldn't revert", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' }),
                            })
                          }
                        >
                          Revert
                        </Button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </main>
  )
}
