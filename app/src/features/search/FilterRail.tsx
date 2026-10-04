import { useState, type ReactNode } from 'react'
import { Button as RacButton, Disclosure, DisclosurePanel, Heading } from 'react-aria-components'
import { ChevronRight, Info, PanelLeftClose, X } from 'lucide-react'
import type { FacetValue, SearchFilters, Verdict, Vocabulary } from '../../api/types'
import { Button, IconButton } from '../../components/Button'
import { Checkbox, ComboBox, NumberField, Select, Switch } from '../../components/Field'
import { Ic } from '../../components/Icon'
import { Segmented } from '../../components/Segmented'
import { activeFilterCount } from '../../lib/chips'
import { formatNumber, humanise, shortLabel } from '../../lib/format'
import { COMMON_TERRITORIES } from '../../lib/rights'
import { MOD } from '../../lib/bridge'
import { DEFAULT_INCLUDE, fromState, hasUse, includeFrom, scopeOf, showsBlocked, toState, withBlocked, withScope, type SearchParams } from './searchParams'
import { ScopeControl } from './ScopePicker'
import t from '../../styles/type.module.css'
import s from './FilterRail.module.css'

interface Props {
  params: SearchParams
  facets: Record<string, FacetValue[]>
  excludedByRights: number
  vocabs: Record<string, Vocabulary>
  label: (vocab: string, term: string) => string
  onChange: (p: SearchParams) => void
  onCollapse?: () => void
  /** Tablet drawer: close without applying. */
  onClose?: () => void
  drawer?: boolean
  /** Scopes written in the words (folder:"…"), named, to show under the Scope control. */
  scopeFromWords?: string[]
}

const VERDICT_LABEL: Record<Verdict, string> = { allowed: 'Cleared', restricted: 'Restricted', unknown: 'Rights unknown', blocked: 'Blocked' }

/** Filter rail (system.md §3.4). Each facet maps 1:1 to a search filter. */
export function FilterRail({ params, facets, excludedByRights, vocabs, label, onChange, onCollapse, onClose, drawer, scopeFromWords }: Props) {
  const state = toState(params)
  const [showAllEdit, setShowAllEdit] = useState(false)
  const active = activeFilterCount(state)
  const f: SearchFilters = params.f ?? {}

  const setFilters = (patch: Partial<SearchFilters>) => {
    const next = { ...f, ...patch }
    for (const k of Object.keys(next) as (keyof SearchFilters)[]) if (next[k] === null || next[k] === undefined) delete next[k]
    onChange({ ...params, f: Object.keys(next).length ? next : undefined })
  }

  const toggleTerm = (vocab: string, term: string, exclude: boolean) => {
    const req = { ...(params.req ?? {}) }
    const exc = { ...(params.exc ?? {}) }
    const inReq = req[vocab]?.includes(term)
    const inExc = exc[vocab]?.includes(term)
    const drop = (m: Record<string, string[]>) => {
      m[vocab] = (m[vocab] ?? []).filter((x) => x !== term)
      if (!m[vocab].length) delete m[vocab]
    }
    if (exclude) {
      if (inExc) drop(exc)
      else {
        if (inReq) drop(req)
        exc[vocab] = [...(exc[vocab] ?? []), term]
      }
    } else if (inReq || inExc) {
      drop(req)
      drop(exc)
    } else req[vocab] = [...(req[vocab] ?? []), term]
    onChange({ ...params, req: Object.keys(req).length ? req : undefined, exc: Object.keys(exc).length ? exc : undefined })
  }

  const facet = (vocab: string, title?: string) => (
    <FacetList
      key={vocab}
      title={title}
      values={facets[vocab] ?? []}
      selected={params.req?.[vocab] ?? []}
      excluded={params.exc?.[vocab] ?? []}
      labelOf={(term) => label(vocab, term)}
      onToggle={(term, exclude) => toggleTerm(vocab, term, exclude)}
    />
  )

  const editTerms = vocabs.edit_type?.terms ?? []
  const editSelected = Array.isArray(f.edit_type) ? f.edit_type : f.edit_type ? [f.edit_type] : []
  const editCounts = new Map((facets.edit_type ?? []).map((v) => [v.term, v.count]))
  const include = includeFrom(params)
  const useSet = hasUse(params)
  const usageOptions = [{ id: '', label: 'Any use' }, ...(vocabs.usage?.terms ?? []).map((x) => ({ id: x.id, label: shortLabel(x.label) }))]
  const channelOptions = [{ id: '', label: 'Any channel' }, ...(vocabs.channel?.terms ?? []).map((x) => ({ id: x.id, label: shortLabel(x.label) }))]
  const terrOptions = COMMON_TERRITORIES.map(([code, name]) => ({ id: code, label: `${code} · ${name}` }))

  const hideBlocked = !showsBlocked(params)
  const setInclude = (list: Verdict[]) => {
    const same = (a: Verdict[], b: Verdict[]) => a.length === b.length && a.every((x) => b.includes(x))
    const verdicts = list.filter((v) => v !== 'blocked')
    onChange({ ...params, inc: same(verdicts, DEFAULT_INCLUDE) ? undefined : verdicts.join(',') || undefined })
  }

  const count = (keys: (string | undefined)[]) => keys.filter(Boolean).length

  return (
    <div className={s.rail}>
      <div className={`${s.head} ${drawer ? s.drawerHead : ''}`}>
        <h2 className={drawer ? s.drawerTitle : t.slate}>Filters</h2>
        {active > 0 && <span className={s.headCount} aria-label={`${active} active`}>{drawer ? `· ${active}` : active}</span>}
        <span className={s.headSpacer} />
        {active > 0 && (
          <Button variant="quiet" size="sm" onPress={() => onChange({ q: params.q, similar: params.similar, group: params.group, strict: params.strict, folder: params.folder, collection: params.collection })}>
            Clear all
          </Button>
        )}
        {onCollapse && <IconButton icon={PanelLeftClose} label="Collapse filters" shortcut={`${MOD}\\`} size="sm" onPress={onCollapse} />}
        {onClose && <IconButton icon={X} label="Close filters" shortcut="Esc" size="sm" onPress={onClose} />}
      </div>
      <ScopeControl value={scopeOf(params)} onChange={(scope) => onChange(withScope(params, scope))} fromWords={scopeFromWords} />
      <div className={s.scroll}>
        <Section title="Edit stage" count={editSelected.length} defaultExpanded>
          <div className={s.group}>
            {editTerms.filter((term) => showAllEdit || (editCounts.get(term.id) ?? 0) > 0 || editSelected.includes(term.id)).map((term) => {
              const n = editCounts.get(term.id) ?? 0
              const on = editSelected.includes(term.id)
              return (
                <div key={term.id} className={s.value}>
                  <Checkbox isSelected={on} onChange={(v) => setFilters({ edit_type: v ? [...editSelected, term.id] : editSelected.filter((x) => x !== term.id) })}>
                    <span className={`${s.valueLabel} ${!n && !on ? s.zero : ''}`}>{shortLabel(term.label)}</span>
                  </Checkbox>
                  <span className={`${s.count} ${!n ? s.zero : ''}`}>{formatNumber(n)}</span>
                </div>
              )
            })}
            {!editTerms.some((term) => (editCounts.get(term.id) ?? 0) > 0) && !showAllEdit && <span className={s.note}>No file has been classified yet.</span>}
            {editTerms.length > 0 && (
              <Button variant="quiet" size="sm" className={s.more} onPress={() => setShowAllEdit(!showAllEdit)}>
                {showAllEdit ? 'Hide empty stages' : `Show all ${editTerms.length}`}
              </Button>
            )}
          </div>
        </Section>

        <Section title="Rights" count={count([params.use, params.ch, params.terr])} defaultExpanded>
          <div className={s.useGrid}>
            <span className={s.groupLabel}>Intended use</span>
            <Select aria-label="Usage" options={usageOptions} selectedKey={params.use ?? ''} onSelectionChange={(k) => onChange({ ...params, use: (k as string) || undefined })} />
            <Select aria-label="Channel" options={channelOptions} selectedKey={params.ch ?? ''} onSelectionChange={(k) => onChange({ ...params, ch: (k as string) || undefined })} />
            <ComboBox
              aria-label="Territory"
              placeholder="Any territory (e.g. GB)"
              options={terrOptions}
              allowsCustomValue
              inputValue={params.terr ?? ''}
              onInputChange={(v) => {
                const code = v.split(' ')[0].trim().toUpperCase()
                if (!v) onChange({ ...params, terr: undefined })
                else if (/^[A-Z]{2}$/.test(code) && code !== params.terr) onChange({ ...params, terr: code })
              }}
              onSelectionChange={(k) => k && onChange({ ...params, terr: String(k) })}
            />
          </div>
          <div className={s.group}>
            <Switch isSelected={hideBlocked} onChange={(on) => onChange(withBlocked(params, !on))}>
              Hide blocked
            </Switch>
            <span className={s.note}>Blocked footage (not cleared, or past its licence) is blocked for every use.</span>
            <span className={s.groupLabel}>Verdict for this use</span>
            {useSet ? (
              (['allowed', 'restricted', 'unknown'] as Verdict[]).map((v) => (
                <div key={v} className={s.value}>
                  <Checkbox isSelected={include.includes(v)} onChange={(on) => setInclude(on ? [...include, v] : include.filter((x) => x !== v))}>
                    <span className={s.valueLabel}>{VERDICT_LABEL[v]}</span>
                  </Checkbox>
                </div>
              ))
            ) : (
              <span className={s.note}>Choose a use above to check every shot against it and filter by the verdict.</span>
            )}
            {excludedByRights > 0 && <span className={s.hidden} data-testid="rail-rights-hidden">{formatNumber(excludedByRights)} shots hidden by rights{useSet ? ' for this use' : ''}</span>}
          </div>
          <p className={s.note}>
            <Ic icon={Info} size={14} />
            Agents only ever see cleared shots.
          </p>
        </Section>

        <Section title="Shot" count={count([...(params.req?.shot_size ?? []), ...(params.req?.camera_movement ?? []), ...(params.req?.shot_role ?? []), f.min_people !== undefined ? 'p' : undefined, f.max_people !== undefined ? 'q' : undefined])} defaultExpanded>
          {facet('shot_size', 'Shot size')}
          {facet('camera_movement', 'Movement')}
          {facet('shot_role', 'Role')}
          <div className={s.group}>
            <span className={s.groupLabel}>People</span>
            <div className={s.range}>
              <NumberField aria-label="Minimum people" minValue={0} value={f.min_people ?? NaN} onChange={(v) => setFilters({ min_people: Number.isNaN(v) ? null : v })} />
              <span className={s.dash}>–</span>
              <NumberField aria-label="Maximum people" minValue={0} value={f.max_people ?? NaN} onChange={(v) => setFilters({ max_people: Number.isNaN(v) ? null : v })} />
            </div>
          </div>
        </Section>

        <Section title="Content" count={count([...(params.req?.setting ?? []), ...(params.req?.object ?? []), ...(params.req?.concept ?? []), ...(params.req?.audio_class ?? []), f.speech !== undefined ? 's' : undefined])}>
          {facet('setting', 'Setting')}
          {facet('object', 'Objects')}
          {facet('concept', 'Concepts')}
          <TriState label="Speech" value={f.speech} onChange={(v) => setFilters({ speech: v })} on="With speech" off="No speech" />
          {facet('audio_class', 'Audio')}
        </Section>

        <Section title="Time and place" count={count([...(params.req?.time_of_day ?? []), ...(params.req?.weather ?? [])])}>
          {facet('time_of_day', 'Time of day')}
          {facet('weather', 'Weather')}
        </Section>

        <Section title="Look and feel" count={count([...(params.req?.mood ?? []), ...(params.req?.pace ?? []), ...(params.req?.look ?? [])])}>
          {facet('mood', 'Mood')}
          {facet('pace', 'Pace')}
          {facet('look', 'Look')}
        </Section>

        <Section title="Quality" count={count([...(params.req?.quality_flag ?? []), ...(params.exc?.quality_flag ?? []), f.usable !== undefined ? 'u' : undefined])}>
          <Switch isSelected={f.usable === true} onChange={(on) => setFilters({ usable: on ? true : null })}>
            Usable shots only
          </Switch>
          {facet('quality_flag', 'Problems (Alt+click to exclude)')}
        </Section>

        <Section title="Technical" count={count([f.orientation ?? undefined, f.min_height ? 'h' : undefined, f.min_fps !== undefined || f.max_fps !== undefined ? 'f' : undefined, f.min_duration !== undefined || f.max_duration !== undefined ? 'd' : undefined, f.log !== undefined ? 'l' : undefined, f.hdr !== undefined ? 'r' : undefined])} defaultExpanded>
          <div className={s.group}>
            <span className={s.groupLabel}>Orientation</span>
            <Segmented
              label="Orientation"
              value={(f.orientation ?? 'any') as 'any' | 'horizontal' | 'vertical' | 'square'}
              onChange={(v) => setFilters({ orientation: v === 'any' ? null : v })}
              segments={[
                { id: 'any', label: 'Any' },
                { id: 'horizontal', label: 'Horizontal' },
                { id: 'vertical', label: 'Vertical' },
                { id: 'square', label: 'Square' },
              ]}
            />
          </div>
          <Select
            label="Minimum resolution"
            slateLabel
            options={[
              { id: '0', label: 'Any resolution' },
              { id: '720', label: '720p or higher' },
              { id: '1080', label: '1080p or higher' },
              { id: '1440', label: '1440p or higher' },
              { id: '2160', label: '4K (UHD) or higher' },
              { id: '4320', label: '8K' },
            ]}
            selectedKey={String(f.min_height ?? 0)}
            onSelectionChange={(k) => setFilters({ min_height: Number(k) || null })}
          />
          <div className={s.group}>
            <span className={s.groupLabel}>Frame rate (fps)</span>
            <div className={s.range}>
              <NumberField aria-label="Minimum frame rate" minValue={1} maxValue={240} value={f.min_fps ?? NaN} onChange={(v) => setFilters({ min_fps: Number.isNaN(v) ? null : v })} />
              <span className={s.dash}>–</span>
              <NumberField aria-label="Maximum frame rate" minValue={1} maxValue={240} value={f.max_fps ?? NaN} onChange={(v) => setFilters({ max_fps: Number.isNaN(v) ? null : v })} />
            </div>
          </div>
          <div className={s.group}>
            <span className={s.groupLabel}>Duration (seconds)</span>
            <div className={s.range}>
              <NumberField aria-label="Minimum duration in seconds" minValue={0} step={0.5} value={f.min_duration ?? NaN} onChange={(v) => setFilters({ min_duration: Number.isNaN(v) ? null : v })} />
              <span className={s.dash}>–</span>
              <NumberField aria-label="Maximum duration in seconds" minValue={0} step={0.5} value={f.max_duration ?? NaN} onChange={(v) => setFilters({ max_duration: Number.isNaN(v) ? null : v })} />
            </div>
          </div>
          <TriState label="Log profile" value={f.log} onChange={(v) => setFilters({ log: v })} on="Log" off="Not log" />
          <TriState label="HDR" value={f.hdr} onChange={(v) => setFilters({ hdr: v })} on="HDR" off="SDR" />
          {(facets.resolution?.length ?? 0) > 0 && (
            <div className={s.group}>
              <span className={s.groupLabel}>In these results</span>
              {facets.resolution.map((r) => (
                <div key={r.term} className={s.value}>
                  <span className={s.valueLabel}>{humanise(r.label).replace('Hd', 'HD').replace('Uhd', 'UHD').replace('Sd', 'SD')}</span>
                  <span className={s.count}>{formatNumber(r.count)}</span>
                </div>
              ))}
            </div>
          )}
        </Section>
      </div>
    </div>
  )
}

/** Utility to turn the rail's state back into URL params from SearchState. */
export const railFromState = fromState

function Section({ title, count, defaultExpanded, children }: { title: string; count: number; defaultExpanded?: boolean; children: ReactNode }) {
  return (
    <Disclosure className={s.section} defaultExpanded={defaultExpanded}>
      <Heading className={s.sectionHead} level={3}>
        <RacButton slot="trigger" className={s.sectionButton}>
          <span className={t.slate}>{title}</span>
          {count > 0 && <span className={s.sectionCount}>{count}</span>}
          <Ic icon={ChevronRight} size={14} className={s.chev} />
        </RacButton>
      </Heading>
      <DisclosurePanel>
        <div className={s.panel}>{children}</div>
      </DisclosurePanel>
    </Disclosure>
  )
}

function TriState({ label, value, onChange, on, off }: { label: string; value: boolean | null | undefined; onChange: (v: boolean | null) => void; on: string; off: string }) {
  return (
    <div className={s.tri}>
      <span className={s.groupLabel} style={{ padding: 0 }}>{label}</span>
      <Segmented
        label={label}
        value={value === true ? 'on' : value === false ? 'off' : 'any'}
        onChange={(v) => onChange(v === 'on' ? true : v === 'off' ? false : null)}
        segments={[
          { id: 'any', label: 'Any' },
          { id: 'on', label: on },
          { id: 'off', label: off },
        ]}
      />
    </div>
  )
}

function FacetList({ title, values, selected, excluded, labelOf, onToggle }: { title?: string; values: FacetValue[]; selected: string[]; excluded: string[]; labelOf: (term: string) => string; onToggle: (term: string, exclude: boolean) => void }) {
  const [all, setAll] = useState(false)
  const [filter, setFilter] = useState('')
  const known = new Set(values.map((v) => v.term))
  const list = [...values, ...[...selected, ...excluded].filter((x) => !known.has(x)).map((term) => ({ term, label: term, count: 0 }))]
  if (!list.length) return null
  const filtered = filter ? list.filter((v) => labelOf(v.term).toLowerCase().includes(filter.toLowerCase())) : list
  const shown = all ? filtered : filtered.slice(0, 6)
  return (
    <div className={s.group}>
      {title && <span className={s.groupLabel}>{title}</span>}
      {all && list.length >= 8 && (
        <input className={s.filterInput} aria-label={`Filter ${title ?? 'values'}`} placeholder="Filter values" value={filter} onChange={(e) => setFilter(e.target.value)} />
      )}
      {shown.map((v) => {
        const on = selected.includes(v.term)
        const ex = excluded.includes(v.term)
        return (
          <div
            key={v.term}
            className={`${s.value} ${ex ? s.excludedValue : ''}`}
            onPointerDownCapture={(e) => {
              if (e.altKey) {
                e.preventDefault()
                e.stopPropagation()
                onToggle(v.term, true)
              }
            }}
            onKeyDownCapture={(e) => {
              if (e.key === ' ' && e.shiftKey) {
                e.preventDefault()
                e.stopPropagation()
                onToggle(v.term, true)
              }
            }}
          >
            <Checkbox isSelected={on || ex} onChange={() => onToggle(v.term, false)} aria-label={`${ex ? 'Not ' : ''}${labelOf(v.term)}, ${v.count} shots`}>
              {ex && <span className={s.not}>not</span>}
              <span className={`${s.valueLabel} ${!v.count && !on ? s.zero : ''}`}>{labelOf(v.term)}</span>
            </Checkbox>
            <span className={`${s.count} ${!v.count ? s.zero : ''}`}>{formatNumber(v.count)}</span>
          </div>
        )
      })}
      {filtered.length > 6 && (
        <Button variant="quiet" size="sm" className={s.more} onPress={() => setAll(!all)}>
          {all ? 'Show fewer' : `Show all ${list.length}`}
        </Button>
      )}
    </div>
  )
}
