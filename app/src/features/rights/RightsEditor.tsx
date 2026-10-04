import { useState } from 'react'
import type { RightsRecord, RightsStatus, Vocabulary } from '../../api/types'
import { ApiError } from '../../api/client'
import { useBulkRights, useRights, useSetRights, useVocabularies } from '../../api/queries'
import { Button } from '../../components/Button'
import { Dialog } from '../../components/Dialog'
import { Checkbox, Radio, RadioGroup, Select, TextField } from '../../components/Field'
import { toast } from '../../components/Toast'
import { plural, shortLabel } from '../../lib/format'
import { useUi } from '../../lib/store'
import s from '../collections/Dialogs.module.css'

type Draft = Omit<RightsRecord, 'level' | 'badge' | 'updated_at' | 'updated_by'>

const EMPTY: Draft = {
  status: 'unknown', source: '', owner: '', licence: '', permitted_uses: [], channels: [], territories: [], excluded_territories: [],
  starts: null, expires: null, model_release: 'unknown', property_release: 'unknown', brand_safety: 'unknown', attribution: '', notes: '',
}

const codes = (v: string) =>
  v
    .split(/[\s,;]+/)
    .map((x) => x.trim().toUpperCase())
    .filter(Boolean)

/** Rights editor (per file, per-shot override, or bulk). PUT /api/rights/{asset}, POST /api/rights/bulk. */
export function RightsEditor() {
  const req = useUi((u) => u.rightsDialog)
  const [scope, setScope] = useState<'file' | 'shot'>('file')
  const single = req && req.assetUids.length === 1 ? req.assetUids[0] : null
  const current = useRights(single, scope === 'shot' ? req?.shotUid : null)
  if (!req || (single && !current.data)) return null
  return <RightsEditorBody key={`${JSON.stringify(req)}|${scope}|${current.dataUpdatedAt}`} req={req} record={single ? current.data : undefined} scope={scope} setScope={setScope} />
}

type RightsReq = NonNullable<ReturnType<typeof useUi.getState>['rightsDialog']>

function initialDraft(r?: RightsRecord): Draft {
  if (!r) return EMPTY
  const d = { ...EMPTY, ...Object.fromEntries(Object.entries(r).filter(([k]) => k in EMPTY)) } as Draft
  if (r.status === 'unknown' && r.level === 'none') d.status = 'cleared'
  return d
}

function RightsEditorBody({ req, record, scope, setScope }: { req: RightsReq; record?: RightsRecord; scope: 'file' | 'shot'; setScope: (s: 'file' | 'shot') => void }) {
  const set = useUi((u) => u.set)
  const single = req.assetUids.length === 1 ? req.assetUids[0] : null
  const { vocabs } = useVocabularies()
  const save = useSetRights()
  const bulk = useBulkRights()
  const [draft, setDraft] = useState<Draft>(() => initialDraft(record))
  const [touched, setTouched] = useState<Set<keyof Draft>>(new Set())
  const [terr, setTerr] = useState((record?.territories ?? []).join(', '))
  const [exTerr, setExTerr] = useState((record?.excluded_territories ?? []).join(', '))

  const patch = <K extends keyof Draft>(k: K, v: Draft[K]) => {
    setDraft((d) => ({ ...d, [k]: v }))
    setTouched((t) => new Set(t).add(k))
  }

  const close = () => set({ rightsDialog: null })

  const submit = async () => {
    const full: Draft = { ...draft, territories: codes(terr), excluded_territories: codes(exTerr) }
    try {
      if (single) {
        await save.mutateAsync({ assetUid: single, shotUid: scope === 'shot' ? req.shotUid : null, rights: full })
        toast({ title: `Rights saved for ${scope === 'shot' ? 'this shot' : 'the file'}`, description: req.title })
      } else {
        const changed: Partial<Draft> = {}
        const keys = new Set<keyof Draft>([...touched, ...(terr ? (['territories'] as const) : []), ...(exTerr ? (['excluded_territories'] as const) : [])])
        for (const k of keys) (changed as Record<string, unknown>)[k] = full[k]
        await bulk.mutateAsync({ assetUids: req.assetUids, rights: changed })
        toast({ title: `Rights saved for ${plural(req.assetUids.length, 'file')}` })
      }
      close()
    } catch (e) {
      toast({ title: "Couldn't save rights", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    }
  }

  return (
    <Dialog
      isOpen
      onOpenChange={(o) => !o && close()}
      title={single ? 'Rights' : `Rights for ${plural(req.assetUids.length, 'file')}`}
      size="l"
      footerStart={req.title}
      footer={
        <>
          <Button variant="secondary" onPress={close}>
            Cancel
          </Button>
          <Button variant="primary" busy={save.isPending || bulk.isPending} onPress={submit} data-testid="save-rights">
            Save rights
          </Button>
        </>
      }
    >
      <div className={s.form} data-testid="rights-editor">
        {single && req.shotUid && (
          <RadioGroup label="Apply to" value={scope} onChange={(v) => setScope(v as 'file' | 'shot')} orientation="horizontal">
            <Radio value="file">The whole file</Radio>
            <Radio value="shot" description="Overrides the file for this shot only.">This shot only</Radio>
          </RadioGroup>
        )}
        {!single && <p style={{ color: 'var(--fg-2)' }}>Only the fields you change are applied. Everything else on each file stays as it is.</p>}
        <RadioGroup label="Status" value={draft.status} onChange={(v) => patch('status', v as RightsStatus)} orientation="horizontal">
          <Radio value="cleared">Cleared</Radio>
          <Radio value="restricted">Restricted</Radio>
          <Radio value="not_cleared">Blocked (not cleared)</Radio>
          <Radio value="unknown">Unknown</Radio>
        </RadioGroup>
        <TermChecks title="Permitted uses (none ticked means any use)" vocab={vocabs.usage} value={draft.permitted_uses} onChange={(v) => patch('permitted_uses', v)} />
        <TermChecks title="Channels (none ticked means any channel)" vocab={vocabs.channel} value={draft.channels} onChange={(v) => patch('channels', v)} />
        <div className={s.cols2}>
          <TextField label="Territories" description="ISO country codes, comma separated. WW means worldwide." value={terr} onChange={(v) => { setTerr(v); setTouched((t) => new Set(t).add('territories')) }} placeholder="GB, IE, WW" mono />
          <TextField label="Excluded territories" value={exTerr} onChange={(v) => { setExTerr(v); setTouched((t) => new Set(t).add('excluded_territories')) }} placeholder="e.g. US" mono />
        </div>
        <div className={s.cols2}>
          <DateInput label="Licence starts" value={draft.starts} onChange={(v) => patch('starts', v)} />
          <DateInput label="Licence expires" value={draft.expires} onChange={(v) => patch('expires', v)} testId="rights-expires" />
        </div>
        <div className={s.cols3}>
          <Select label="Model release" options={(vocabs.release_status?.terms ?? []).map((t) => ({ id: t.id, label: shortLabel(t.label) }))} selectedKey={draft.model_release} onSelectionChange={(k) => patch('model_release', String(k))} />
          <Select label="Property release" options={(vocabs.release_status?.terms ?? []).map((t) => ({ id: t.id, label: shortLabel(t.label) }))} selectedKey={draft.property_release} onSelectionChange={(k) => patch('property_release', String(k))} />
          <Select label="Brand safety" options={[{ id: 'unknown', label: 'Not assessed' }, { id: 'safe', label: 'Brand safe' }, { id: 'unsafe', label: 'Not brand safe' }]} selectedKey={draft.brand_safety} onSelectionChange={(k) => patch('brand_safety', String(k))} />
        </div>
        <div className={s.cols2}>
          <TextField label="Licence" value={draft.licence} onChange={(v) => patch('licence', v)} placeholder="e.g. Staff shoot, Getty RM 1234" />
          <TextField label="Owner" value={draft.owner} onChange={(v) => patch('owner', v)} />
          <TextField label="Source" value={draft.source} onChange={(v) => patch('source', v)} />
          <TextField label="Credit line" value={draft.attribution} onChange={(v) => patch('attribution', v)} />
        </div>
        <TextField label="Notes" value={draft.notes ?? ''} onChange={(v) => patch('notes', v)} multiline />
      </div>
    </Dialog>
  )
}

function TermChecks({ title, vocab, value, onChange }: { title: string; vocab?: Vocabulary; value: string[]; onChange: (v: string[]) => void }) {
  const terms = vocab?.terms ?? []
  const tops = terms.filter((t) => !t.broader)
  return (
    <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
      <legend className={s.legend}>{title}</legend>
      <div className={s.checkGroup}>
        {tops.flatMap((t) => [t, ...terms.filter((c) => c.broader === t.id)]).map((t) => (
          <div key={t.id} className={t.broader ? s.indent : undefined}>
            <Checkbox isSelected={value.includes(t.id)} onChange={(on) => onChange(on ? [...value, t.id] : value.filter((x) => x !== t.id))}>
              {shortLabel(t.label)}
            </Checkbox>
          </div>
        ))}
      </div>
    </fieldset>
  )
}

function DateInput({ label, value, onChange, testId }: { label: string; value: string | null; onChange: (v: string | null) => void; testId?: string }) {
  const id = `d-${label.replace(/\W/g, '')}`
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-1_5)' }}>
      <label htmlFor={id} style={{ fontWeight: 'var(--weight-medium)' }}>
        {label}
      </label>
      <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
        <input id={id} type="date" data-testid={testId} value={value ?? ''} onChange={(e) => onChange(e.target.value || null)} style={{ blockSize: 'var(--control-md)', background: 'var(--bg-raised)', border: 'var(--border-width) solid var(--border-control)', borderRadius: 'var(--radius-sm)', paddingInline: 'var(--space-2)', colorScheme: 'inherit', flex: 1 }} />
        {value && (
          <Button variant="quiet" size="sm" onPress={() => onChange(null)}>
            Clear
          </Button>
        )}
      </div>
    </div>
  )
}
