import { useEffect, useMemo, useRef, useState } from 'react'
import { useIsFetching } from '@tanstack/react-query'
import { useNavigate, useRouterState } from '@tanstack/react-router'
import { FileTrigger } from 'react-aria-components'
import { History, ImageUp, ScanFace, Search, Tag, X } from 'lucide-react'
import { searchByExample, useNamedPeople, useVocabularies } from '../../api/queries'
import { ApiError } from '../../api/client'
import { IconButton } from '../../components/Button'
import { Ic } from '../../components/Icon'
import { ProgressLine } from '../../components/EmptyState'
import { toast } from '../../components/Toast'
import { useDelayedFlag } from '../../hooks/useDebounced'
import { MOD } from '../../lib/bridge'
import { useUi } from '../../lib/store'
import { VOCAB_SLATE } from '../../lib/chips'
import { shortLabel } from '../../lib/format'
import { effectiveScope, similarRightsOf, validateSearch, type SearchParams } from './searchParams'
import t from '../../styles/type.module.css'
import s from './SearchBar.module.css'

const SUGGEST_VOCABS = ['shot_size', 'camera_movement', 'shot_role', 'setting', 'time_of_day', 'weather', 'mood', 'pace', 'audio_class', 'edit_type']
const RECENT_KEY = 'mc.recentSearches'

function loadRecent(): string[] {
  try {
    return JSON.parse(localStorage.getItem(RECENT_KEY) ?? '[]')
  } catch {
    return []
  }
}

export function saveRecent(q: string) {
  if (!q.trim()) return
  const list = [q, ...loadRecent().filter((x) => x !== q)].slice(0, 8)
  localStorage.setItem(RECENT_KEY, JSON.stringify(list))
}

interface Suggestion {
  id: string
  kind: 'tag' | 'recent' | 'person'
  label: string
  slate: string
  vocab?: string
  term?: string
}

/** The command input: natural language, query by example, suggestions (system.md §3.2). */
export function SearchBar() {
  const navigate = useNavigate()
  const location = useRouterState({ select: (st) => st.location })
  const onSearch = location.pathname === '/search'
  const params = validateSearch(onSearch ? (location.search as Record<string, unknown>) : {})
  const urlQ = params.q ?? ''
  const [draft, setDraft] = useState(urlQ)
  const lastSent = useRef(urlQ)
  const inputRef = useRef<HTMLInputElement>(null)
  const [dropping, setDropping] = useState(false)
  const [exampleBusy, setExampleBusy] = useState(false)
  const [open, setOpen] = useState(false)
  const [active, setActive] = useState(-1)
  const fetching = useIsFetching({ queryKey: ['search'] }) > 0
  const showProgress = useDelayedFlag(fetching || exampleBusy, 400)
  const { vocabs } = useVocabularies()
  const named = useNamedPeople()
  const example = useUi((u) => u.example)

  // URL → field (chip edits rewrite the words; back/forward restore them).
  useEffect(() => {
    if (urlQ !== lastSent.current) {
      lastSent.current = urlQ
      setDraft(urlQ)
    }
  }, [urlQ])

  const commit = (q: string, replace: boolean) => {
    lastSent.current = q
    if (useUi.getState().example) useUi.getState().set({ example: null })
    navigate({ to: '/search', search: (prev: SearchParams) => ({ ...(onSearch ? prev : {}), q: q.trim() ? q : undefined, similar: undefined }), replace })
  }

  // Perceived-instant: search 150 ms after typing stops; previous results stay visible.
  useEffect(() => {
    if (draft === lastSent.current) return
    const timer = window.setTimeout(() => commit(draft, onSearch), 150)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft])

  // Focus requests from global shortcuts (/, ⌘F).
  useEffect(() => {
    const h = () => {
      inputRef.current?.focus()
      inputRef.current?.select()
    }
    window.addEventListener('mc:focus-search', h)
    return () => window.removeEventListener('mc:focus-search', h)
  }, [])

  const word = /([\p{L}-]{2,})$/u.exec(draft)?.[1]?.toLowerCase() ?? ''
  const suggestions = useMemo<Suggestion[]>(() => {
    const out: Suggestion[] = []
    if (word.length >= 2) {
      for (const v of SUGGEST_VOCABS) {
        for (const term of vocabs[v]?.terms ?? []) {
          const lbl = shortLabel(term.label)
          if (lbl.toLowerCase().startsWith(word) || term.synonyms.some((x) => x.toLowerCase().startsWith(word))) {
            out.push({ id: `tag:${v}:${term.id}`, kind: 'tag', label: lbl, slate: VOCAB_SLATE[v] ?? v, vocab: v, term: term.id })
          }
          if (out.length >= 8) break
        }
        if (out.length >= 8) break
      }
    }
    if (word.length >= 2) {
      // People (named face clusters): Tab adds a PERSON filter, like a tag.
      for (const p of named.data?.people ?? []) {
        if (p.name && p.name.toLowerCase().split(/\s+/).some((w) => w.startsWith(word))) {
          out.push({ id: `person:${p.id}`, kind: 'person', label: p.name, slate: 'PERSON', vocab: 'person', term: String(p.id) })
        }
        if (out.length >= 12) break
      }
    }
    if (!draft.trim()) {
      for (const r of loadRecent()) out.push({ id: `recent:${r}`, kind: 'recent', label: r, slate: 'RECENT' })
    }
    return out
  }, [word, draft, vocabs, named.data])
  const showSuggest = open && suggestions.length > 0

  const accept = (sug: Suggestion) => {
    if (sug.kind === 'recent') {
      setDraft(sug.label)
      commit(sug.label, false)
    } else if (sug.vocab && sug.term) {
      // Tab/Enter on a tag: becomes a required chip; the partial word is removed.
      const rest = draft.slice(0, draft.length - word.length).replace(/[\s,]+$/, '')
      setDraft(rest)
      lastSent.current = rest
      navigate({
        to: '/search',
        search: (prev: SearchParams) => {
          const base = onSearch ? prev : {}
          const req = { ...(base.req ?? {}) }
          req[sug.vocab as string] = [...new Set([...(req[sug.vocab as string] ?? []), sug.term as string])]
          return { ...base, q: rest || undefined, req }
        },
      })
    }
    setOpen(false)
    setActive(-1)
  }

  const runExample = async (file: File) => {
    const kind = file.type.startsWith('video/') || /\.(mp4|mov|mkv|webm)$/i.test(file.name) ? 'clip' : file.type.startsWith('image/') ? 'image' : null
    if (!kind) {
      toast({ title: 'Drop an image or a video clip to find similar shots.', tone: 'caution' })
      return
    }
    setExampleBusy(true)
    try {
      // Same rights verdict, intended use, Hide blocked and scope as text search (keep only those params;
      // a folder:"…" written in the words becomes the chosen scope, since the words are cleared).
      const scope = effectiveScope(params)
      const keep: SearchParams = {
        use: params.use, ch: params.ch, terr: params.terr, inc: params.inc, blocked: params.blocked, strict: params.strict,
        folder: scope.folder.length ? scope.folder : undefined, collection: scope.collection.length ? scope.collection : undefined,
      }
      const rights = similarRightsOf(keep)
      const response = await searchByExample(file, 120, rights)
      useUi.getState().set({ example: { name: file.name, kind, response, file, rightsKey: JSON.stringify(rights) }, selection: new Set() })
      lastSent.current = ''
      setDraft('')
      navigate({ to: '/search', search: Object.fromEntries(Object.entries(keep).filter(([, v]) => v)) as SearchParams })
    } catch (e) {
      toast({ title: "Couldn't search by example", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    } finally {
      setExampleBusy(false)
    }
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown' && suggestions.length) {
      e.preventDefault()
      setOpen(true)
      setActive((a) => (a + 1) % suggestions.length)
    } else if (e.key === 'ArrowUp' && showSuggest) {
      e.preventDefault()
      setActive((a) => (a <= 0 ? suggestions.length - 1 : a - 1))
    } else if (e.key === 'Tab' && showSuggest && active >= 0 && !e.shiftKey) {
      e.preventDefault()
      accept(suggestions[active])
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (showSuggest && active >= 0) {
        accept(suggestions[active])
        return
      }
      setOpen(false)
      saveRecent(draft)
      commit(draft, false)
      if (e.metaKey || e.ctrlKey) useUi.getState().set({ focusResultsPending: draft })
    } else if (e.key === 'Escape') {
      if (showSuggest) {
        setOpen(false)
        setActive(-1)
      } else if (draft) {
        setDraft('')
      } else inputRef.current?.blur()
    } else if (e.key === 'Backspace' && !draft && onSearch) {
      window.dispatchEvent(new Event('mc:focus-last-chip'))
    }
  }

  return (
    <search className={s.form} role="search" aria-label="Search shots">
      <div
        className={[s.field, dropping && s.dropping].filter(Boolean).join(' ')}
        onDragOver={(e) => {
          if (e.dataTransfer.types.includes('Files')) {
            e.preventDefault()
            setDropping(true)
          }
        }}
        onDragLeave={() => setDropping(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDropping(false)
          const f = e.dataTransfer.files?.[0]
          if (f) runExample(f)
        }}
        data-testid="search-field"
      >
        <Ic icon={Search} />
        <label htmlFor="mc-search" className="visually-hidden">
          Search shots
        </label>
        <input
          ref={inputRef}
          id="mc-search"
          className={s.input}
          type="search"
          role="combobox"
          aria-expanded={showSuggest}
          aria-controls="mc-suggest"
          aria-autocomplete="list"
          aria-activedescendant={showSuggest && active >= 0 ? `mc-sug-${active}` : undefined}
          autoComplete="off"
          spellCheck={false}
          placeholder={example ? `Similar to ${example.name}` : 'Describe the shot you need, e.g. handheld street food close-ups at night'}
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value)
            setOpen(true)
            setActive(-1)
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => window.setTimeout(() => setOpen(false), 120)}
          onKeyDown={onKeyDown}
        />
        <div className={s.trail}>
          {draft && <IconButton icon={X} label="Clear search" size="sm" onPress={() => { setDraft(''); inputRef.current?.focus() }} />}
          <FileTrigger acceptedFileTypes={['image/*', 'video/*']} onSelect={(files) => { const f = files?.[0]; if (f) runExample(f) }}>
            <IconButton icon={ImageUp} label="Search by example image or clip" size="sm" />
          </FileTrigger>
          <kbd className={s.hint} aria-hidden="true">{MOD}K</kbd>
        </div>
        {dropping && <div className={s.dropHint}>Drop an image or clip to find similar shots</div>}
        <ProgressLine visible={showProgress} />
      </div>
      {showSuggest && (
        <div className={s.suggest} id="mc-suggest" role="listbox" aria-label="Suggestions">
          {suggestions.map((sug, i) => (
            <div
              key={sug.id}
              id={`mc-sug-${i}`}
              role="option"
              aria-selected={i === active}
              className={s.suggestItem}
              onMouseDown={(e) => {
                e.preventDefault()
                accept(sug)
              }}
              onMouseEnter={() => setActive(i)}
            >
              <Ic icon={sug.kind === 'tag' ? Tag : sug.kind === 'person' ? ScanFace : History} />
              <span>{sug.label}</span>
              <span className={`${t.slate} ${s.suggestMeta}`}>{sug.kind === 'recent' ? sug.slate : `${sug.slate} · Tab adds`}</span>
            </div>
          ))}
        </div>
      )}
    </search>
  )
}

