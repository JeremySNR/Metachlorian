import { useEffect, useMemo, useRef } from 'react'
import { Button as RacButton, Tag, TagGroup, TagList, type Key } from 'react-aria-components'
import { Pin, PinOff, X } from 'lucide-react'
import type { SearchResponse } from '../../api/types'
import { Button } from '../../components/Button'
import { Ic } from '../../components/Icon'
import { toast } from '../../components/Toast'
import {
  buildPhraseIndex, chipsFromQuery, demoteChip, promoteChip, removeChip, toggleExcludeChip, type QueryChip, type SearchState,
} from '../../lib/chips'
import type { Vocabulary } from '../../api/types'
import tip from '../../components/Tip.module.css'
import s from './SearchPage.module.css'

export interface ExtraChip {
  key: string
  slate: string
  label: string
  onRemove: () => void
}

interface Props {
  query: SearchResponse['query'] | undefined
  state: SearchState
  vocabs: Record<string, Vocabulary>
  label: (vocab: string, term: string) => string
  onChange: (next: SearchState) => void
  extra?: ExtraChip[]
}

/**
 * Parsed-query chips (system.md §3.3): inferred values carry a dotted underline
 * and "From your words …"; Enter promotes or demotes, Alt+Enter / Alt+click
 * toggles exclude, Backspace/Delete removes.
 */
export function ChipRow({ query, state, vocabs, label, onChange, extra = [] }: Props) {
  const index = useMemo(() => buildPhraseIndex(vocabs), [vocabs])
  const chips = useMemo(() => (query ? chipsFromQuery(query, state, label, index) : []), [query, state, label, index])
  const groupRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const h = () => {
      const tags = groupRef.current?.querySelectorAll<HTMLElement>('[role="row"]')
      tags?.[tags.length - 1]?.focus()
    }
    window.addEventListener('mc:focus-last-chip', h)
    return () => window.removeEventListener('mc:focus-last-chip', h)
  }, [])

  const byKey = new Map(chips.map((c) => [c.key, c]))
  const apply = (next: SearchState | null, chip: QueryChip) => {
    if (next) onChange(next)
    else toast({ title: `Couldn't find the words behind “${chip.label}”.`, description: 'Edit the search text to change it.', tone: 'caution' })
  }
  const remove = (chip: QueryChip) => apply(removeChip(state, chip, index), chip)
  const promote = (chip: QueryChip) => onChange(chip.kind === 'require' && !chip.inferred ? demoteChip(state, chip) : promoteChip(state, chip))
  const exclude = (chip: QueryChip) => apply(toggleExcludeChip(state, chip, index), chip)

  const all = chips.length + extra.length
  if (!all) return null

  return (
    <div className={s.chipRow}>
      <div className={s.chipScroller}>
        <TagGroup
          ref={groupRef}
          aria-label="Search interpretation"
          onRemove={(keys: Set<Key>) => {
            for (const k of keys) {
              const ex = extra.find((e) => e.key === k)
              if (ex) ex.onRemove()
              const c = byKey.get(String(k))
              if (c) remove(c)
            }
          }}
        >
          <TagList className={s.tagList}>
            {extra.map((e) => (
              <Tag key={e.key} id={e.key} textValue={`${e.slate} ${e.label}`} className={s.chip}>
                <span className={s.chipSlate}>{e.slate}</span>
                <span className={s.chipValue}>{e.label}</span>
                <RacButton slot="remove" className={s.chipBtn} aria-label={`Remove ${e.label}`}>
                  <Ic icon={X} size={14} />
                </RacButton>
              </Tag>
            ))}
            {chips.map((c) => {
              const isTerm = Boolean(c.vocab && c.term)
              const required = c.kind === 'require'
              const tipText = c.kind === 'prefer' ? (c.words ? `From your words “${c.words}”. Enter makes it required` : 'Preferred, not required') : c.inferred && c.words ? `From your words “${c.words}”` : undefined
              return (
                <Tag
                  key={c.key}
                  id={c.key}
                  textValue={`${c.slate} ${c.label}${c.kind === 'prefer' ? ', preferred' : required ? ', required' : ''}`}
                  className={[s.chip, c.kind === 'prefer' && s.inferred, c.kind === 'exclude' && s.excluded, required && s.required, tip.tip].filter(Boolean).join(' ')}
                  data-tip={tipText}
                  data-testid="query-chip"
                  data-kind={c.kind}
                  onAction={isTerm ? () => promote(c) : undefined}
                  onKeyDown={(e: React.KeyboardEvent) => {
                    if (e.key === 'Enter' && e.altKey && isTerm) {
                      e.preventDefault()
                      exclude(c)
                    }
                  }}
                  onPointerDown={(e: React.PointerEvent) => {
                    if (e.altKey && isTerm) {
                      e.preventDefault()
                      exclude(c)
                    }
                  }}
                >
                  <span className={s.chipSlate}>{c.slate}</span>
                  <span className={s.chipValue}>{c.label}</span>
                  {isTerm && c.kind !== 'exclude' && (
                    <RacButton className={`${s.chipBtn} ${s.chipPin}`} aria-label={required ? `Make ${c.label} preferred, not required` : `Require ${c.label}`} onPress={() => promote(c)}>
                      <Ic icon={required ? PinOff : Pin} size={14} />
                    </RacButton>
                  )}
                  <RacButton slot="remove" className={s.chipBtn} aria-label={`Remove ${c.label}`}>
                    <Ic icon={X} size={14} />
                  </RacButton>
                </Tag>
              )
            })}
          </TagList>
        </TagGroup>
      </div>
      {all >= 2 && (
        <Button
          variant="quiet"
          size="sm"
          onPress={() => {
            extra.forEach((e) => e.onRemove())
            onChange({ q: '', require: {}, exclude: {}, filters: {}, use: null })
          }}
        >
          Clear all
        </Button>
      )}
    </div>
  )
}
