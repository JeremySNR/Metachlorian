import { useMemo, useState } from 'react'
import { useQueries } from '@tanstack/react-query'
import { Download, ExternalLink, FolderOpen, Package, Send, TriangleAlert } from 'lucide-react'
import type { Collection, CutawanMode, MediaPolicy, PackageResult, ShotDoc, Verdict } from '../../api/types'
import { ApiError, mediaUrl } from '../../api/client'
import { buildCollectionPackage, buildPackage, shotQuery, useCollection, useRightsCheck, useVocabularies, verdictCounts } from '../../api/queries'
import { Button } from '../../components/Button'
import { Dialog } from '../../components/Dialog'
import { Checkbox, Radio, RadioGroup, Select, TextField } from '../../components/Field'
import { RightsBadge } from '../../components/RightsBadge'
import { Segmented } from '../../components/Segmented'
import { StatusText } from '../../components/EmptyState'
import { toast } from '../../components/Toast'
import { bridge, can } from '../../lib/bridge'
import { formatDate, plural, shortLabel } from '../../lib/format'
import { stateFromVerdict } from '../../lib/rights'
import { usePrefs, useUi } from '../../lib/store'
import { formatDuration } from '../../lib/timecode'
import s from './Dialogs.module.css'

type Aspect = '9:16' | '1:1' | '4:5' | '16:9' | 'original'

interface Item {
  uid: string
  in: number | null
  out: number | null
  note: string
  title: string
  thumb?: string | null
  duration?: number
  role?: string
}

/** Roles Cutawan treats as A-roll (exports/package.py A_ROLES). */
const A_ROLES = new Set(['interview', 'piece_to_camera', 'a_roll', 'vox_pop'])

const today = () => formatDate(new Date())

export type CropFit = 'ok' | 'none' | 'check' | 'unknown' | 'na'

/**
 * Whether a shot has a safe crop for a delivery aspect, from the shot's composition.vertical_crop
 * (a 9:16 window that keeps the subject). A 9:16 window also fits inside a 1:1 or 4:5 one.
 */
export function cropFit(doc: Pick<ShotDoc, 'fields' | 'technical'> | undefined, aspect: string): CropFit {
  if (aspect === 'original' || aspect === '16:9') return 'na'
  if (!doc) return 'unknown'
  const ar = doc.technical?.aspect_ratio ?? (doc.technical?.width && doc.technical?.height ? doc.technical.width / doc.technical.height : null)
  const target = aspect === '9:16' ? 9 / 16 : aspect === '4:5' ? 4 / 5 : 1
  if (ar && ar <= target * 1.05) return 'na'
  const v = doc.fields?.['composition.vertical_crop']?.value as { safe?: boolean; value?: { safe?: boolean } } | undefined
  const safe = v?.value?.safe ?? v?.safe
  if (safe === true) return 'ok'
  if (safe === false) return aspect === '9:16' ? 'none' : 'check'
  return 'unknown'
}

/**
 * Send to Cutawan / Export timeline (system.md §3.17). Runs the rights check for
 * the chosen use first: blocked and unknown shots are dropped and listed;
 * restricted shots need an explicit choice. Builds the package through
 * POST /api/collections/{uid}/package (or /api/package when shots are dropped).
 */
export function SendDialog() {
  const req = useUi((u) => u.sendDialog)
  const col = useCollection(req?.kind === 'collection' ? req.uid : null)
  if (!req || (req.kind === 'collection' && !col.data)) return null
  return <SendDialogBody key={JSON.stringify(req)} req={req} collection={req.kind === 'collection' ? col.data : undefined} />
}

type SendReq = NonNullable<ReturnType<typeof useUi.getState>['sendDialog']>

function SendDialogBody({ req, collection }: { req: SendReq; collection?: Collection }) {
  const set = useUi((u) => u.set)
  const open = true
  const consumer = req.consumer ?? 'cutawan'
  const cache = useUi((u) => u.resultCache)
  const { vocabs } = useVocabularies()
  const def = usePrefs((p) => p.defaultUse)
  // Intended use: the search's own, else the workspace default (Rights → Policies), else none. Say which.
  const fromSearch = req.use && (req.use.use || req.use.channel || req.use.territory) ? req.use : null
  const hasDefault = Boolean(def.use || def.channel || def.territory)
  const [useSource, setUseSource] = useState<'search' | 'default' | 'none' | 'edited'>(fromSearch ? 'search' : hasDefault ? 'default' : 'none')

  const items: Item[] = useMemo(() => {
    if (req.kind === 'collection')
      return (collection?.items ?? []).map((i) => ({ uid: i.shot.uid, in: i.in, out: i.out, note: i.note, title: i.shot.caption || `${i.shot.filename} · shot ${i.shot.idx + 1}`, thumb: i.shot.thumb, duration: (i.out ?? i.shot.end) - (i.in ?? i.shot.start), role: i.shot.role?.[0]?.term }))
    return req.uids.map((u) => {
      const r = cache.get(u)
      return { uid: u, in: null, out: null, note: '', title: r ? r.caption || `${r.filename} · shot ${r.idx + 1}` : u, thumb: r?.thumb, duration: r?.duration, role: r?.role?.[0]?.term }
    })
  }, [req, collection, cache])

  const [name, setName] = useState(() => (collection ? collection.name : `Selects · ${today()}`))
  const [brief, setBrief] = useState(() => (collection ? collection.brief || collection.description : ''))
  const [mode, setMode] = useState<CutawanMode>(() => (items.some((i) => i.role && A_ROLES.has(i.role)) ? 'a_roll_with_inserts' : 'stringout'))
  const [aspect, setAspect] = useState<Aspect>(consumer === 'nle' ? 'original' : '9:16')
  const [use, setUse] = useState(fromSearch ? (fromSearch.use ?? '') : (def.use ?? ''))
  const [channel, setChannel] = useState(fromSearch ? (fromSearch.channel ?? '') : (def.channel ?? ''))
  const [territory, setTerritory] = useState(fromSearch ? (fromSearch.territory ?? '') : (def.territory ?? ''))
  const [media, setMedia] = useState<MediaPolicy>(consumer === 'nle' ? 'none' : 'proxies')
  const [includeRestricted, setIncludeRestricted] = useState(false)
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<PackageResult | null>(null)

  const check = useRightsCheck(open && items.length ? { shot_uids: items.map((i) => i.uid), use: use || null, channel: channel || null, territory: territory || null } : null)
  const verdictOf = new Map((check.data?.items ?? []).map((i) => [i.shot_uid as string, i]))
  const counts = verdictCounts(check.data)
  const keep = (v: Verdict | undefined) => v === 'allowed' || (v === 'restricted' && includeRestricted)
  const kept = items.filter((i) => keep(verdictOf.get(i.uid)?.verdict))
  const dropped = items.length - kept.length
  const aRoll = kept.filter((i) => i.role && A_ROLES.has(i.role)).length
  const effectiveMode: CutawanMode = mode === 'a_roll_with_inserts' && aRoll === 0 ? 'stringout' : mode
  const credits = [...new Set((check.data?.items ?? []).map((i) => i.rights.attribution).filter(Boolean))]
  const docs = useQueries({ queries: consumer === 'cutawan' ? items.slice(0, 80).map((i) => ({ ...shotQuery(i.uid), staleTime: 5 * 60_000 })) : [] })
  const docOf = new Map(docs.map((q) => [q.data?.uid, q.data]))
  const fitOf = (uid: string) => cropFit(docOf.get(uid), aspect)
  const noCrop = consumer === 'cutawan' ? kept.filter((i) => fitOf(i.uid) === 'none').length : 0
  const checkCrop = consumer === 'cutawan' ? kept.filter((i) => fitOf(i.uid) === 'check').length : 0
  const expiries = (check.data?.items ?? []).map((i) => i.rights.expires).filter(Boolean).sort() as string[]

  const close = () => set({ sendDialog: null })

  const send = async () => {
    if (!kept.length) return
    setBusy(true)
    const body = {
      name,
      brief,
      target: { consumer, aspect, usage: use ? [use] : [], channels: channel ? [channel] : [], territories: territory ? [territory] : [] },
      media_policy: media,
      mode: consumer === 'cutawan' ? effectiveMode : undefined,
      zip: true,
    }
    try {
      const res =
        req.kind === 'collection' && kept.length === items.length
          ? await buildCollectionPackage(req.uid, body)
          : await buildPackage(kept.map((i) => ({ shot_uid: i.uid, in: i.in, out: i.out, note: i.note })), body)
      setResult(res)
      toast({ title: consumer === 'cutawan' ? `Package ready for Cutawan: ${plural(kept.length, 'shot')}` : `Timeline package ready: ${plural(kept.length, 'shot')}` })
      if (consumer === 'cutawan' && can('canLaunchCutawan')) {
        const r = await bridge()?.openInCutawan(res.path)
        if (r && !r.ok) toast({ title: "Couldn't open Cutawan", description: r.error, tone: 'error' })
      }
    } catch (e) {
      toast({ title: "Couldn't build the package", description: e instanceof ApiError ? e.detail : String(e), tone: 'error' })
    } finally {
      setBusy(false)
    }
  }

  const opt = (v: string) => (vocabs[v]?.terms ?? []).map((t) => ({ id: t.id, label: shortLabel(t.label) }))
  const title = consumer === 'cutawan' ? 'Send to Cutawan' : 'Export timeline'

  if (result) {
    return (
      <Dialog
        isOpen={open}
        onOpenChange={(o) => !o && close()}
        title={consumer === 'cutawan' ? 'Package ready for Cutawan' : 'Timeline package ready'}
        size="m"
        footer={
          <>
            {can('canRevealInFolder') && (
              <Button variant="secondary" icon={FolderOpen} onPress={() => bridge()?.reveal(result.path)}>
                Show in folder
              </Button>
            )}
            {consumer === 'cutawan' && can('canLaunchCutawan') && (
              <Button variant="secondary" icon={ExternalLink} onPress={() => bridge()?.openInCutawan(result.path)}>
                Open in Cutawan
              </Button>
            )}
            <Button variant="primary" icon={Download} onPress={() => window.open(mediaUrl(result.download), '_blank', 'noopener')}>
              Download package (.zip)
            </Button>
          </>
        }
      >
        <div className={s.result} data-testid="package-result">
          <StatusText tone={result.verdict === 'allowed' ? 'cleared' : result.verdict === 'restricted' ? 'caution' : 'blocked'} icon={Package}>
            {result.verdict === 'allowed' ? 'Every shot is cleared for this use' : `Rights verdict: ${result.verdict}`}
          </StatusText>
          <p>
            {counts.allowed} cleared · {result.counts.restricted ?? 0} restricted · {result.counts.blocked ?? 0} blocked · {result.counts.unknown ?? 0} unknown in the package.
            {dropped > 0 && ` ${plural(dropped, 'shot')} left out by the rights check.`}
          </p>
          <div>
            <span className={s.legend}>Package folder</span>
            <div className={s.path} data-testid="package-path">{result.path}</div>
          </div>
          <p style={{ color: 'var(--fg-2)', fontSize: 'var(--text-sm)' }}>
            Contains manifest.json, timelines (OTIO, FCPXML 1.10, CMX 3600 EDL){media !== 'none' ? ', media' : ''} and transcripts. {consumer === 'cutawan' && !can('canLaunchCutawan') && 'In Cutawan, choose Import package and pick this folder or the downloaded zip.'}
          </p>
        </div>
      </Dialog>
    )
  }

  return (
    <Dialog
      isOpen={open}
      onOpenChange={(o) => !o && close()}
      title={title}
      size="l"
      footerStart={check.data ? (dropped ? `${plural(dropped, 'shot')} left out by the rights check` : 'Every shot passes the rights check') : 'Checking rights…'}
      footer={
        <>
          <Button variant="secondary" onPress={close}>
            Cancel
          </Button>
          <Button variant="primary" icon={consumer === 'cutawan' ? Send : Download} busy={busy} isDisabled={!kept.length || !check.data} onPress={send} data-testid="send-package">
            {consumer === 'cutawan' ? `Send ${plural(kept.length, 'shot')}` : `Export ${plural(kept.length, 'shot')}`}
          </Button>
        </>
      }
    >
      <div className={s.form}>
        <div className={s.cols2}>
          <TextField label="Package name" value={name} onChange={setName} />
          {consumer === 'cutawan' ? (
            <div>
              <span className={s.legend}>Aspect</span>
              <Segmented label="Aspect" value={aspect} onChange={setAspect} segments={(['9:16', '1:1', '4:5', '16:9', 'original'] as Aspect[]).map((a) => ({ id: a, label: a === 'original' ? 'Original' : a }))} />
            </div>
          ) : (
            <RadioGroup label="Media" value={media} onChange={(v) => setMedia(v as MediaPolicy)}>
              <Radio value="none">None (timelines only, original paths)</Radio>
              <Radio value="proxies">Proxies</Radio>
              <Radio value="trimmed_originals">Trimmed originals</Radio>
            </RadioGroup>
          )}
        </div>
        {consumer === 'cutawan' && (
          <>
            <TextField label="Brief" description="What the edit is for. Cutawan shows it with the package." value={brief} onChange={setBrief} multiline placeholder="e.g. 30-second organic social cut for the night market launch" />
            <div className={s.cols2}>
              <RadioGroup label="What Cutawan should make" value={mode} onChange={(v) => setMode(v as CutawanMode)}>
                <Radio value="a_roll_with_inserts" description={aRoll ? 'Interview or piece to camera as the spine, B-roll cut in over it.' : 'Needs at least one interview or piece-to-camera shot; this package will be a stringout.'}>A-roll with B-roll inserts</Radio>
                <Radio value="stringout" description="One conformed video of every shot in order.">Stringout</Radio>
                <Radio value="broll_library" description="No project; feeds Cutawan's B-roll picker.">B-roll library</Radio>
              </RadioGroup>
              <RadioGroup label="Media" value={media} onChange={(v) => setMedia(v as MediaPolicy)}>
                <Radio value="stringout" description="Every shot in order, rendered as one file.">One rendered video</Radio>
                <Radio value="proxies" description="One small clip per shot.">Proxy clips</Radio>
                <Radio value="trimmed_originals" description="Full-quality clips cut from the source files.">Trimmed originals</Radio>
                <Radio value="none" description="Timelines only, pointing at the original files.">No media</Radio>
              </RadioGroup>
            </div>
          </>
        )}
        <div>
          <span className={s.legend}>Intended use</span>
          <div className={s.cols3}>
            <Select aria-label="Usage" options={[{ id: '', label: 'Any use' }, ...opt('usage')]} selectedKey={use} onSelectionChange={(k) => { setUse(String(k)); setUseSource('edited') }} />
            <Select aria-label="Channel" options={[{ id: '', label: 'Any channel' }, ...opt('channel')]} selectedKey={channel} onSelectionChange={(k) => { setChannel(String(k)); setUseSource('edited') }} />
            <TextField aria-label="Territory (ISO code)" value={territory} onChange={(v) => { setTerritory(v.toUpperCase().slice(0, 2)); setUseSource('edited') }} placeholder="Any territory (e.g. GB)" mono />
          </div>
          {useSource !== 'edited' && (
            <p className={s.hint} data-testid="use-source">
              {useSource === 'search'
                ? 'From your search.'
                : useSource === 'default'
                  ? 'Workspace default from Rights → Policies. Change it if this edit is for something else.'
                  : 'No use chosen: shots are checked for blocks only. Pick what this edit is for to check permissions too.'}
            </p>
          )}
        </div>
        <div className={s.summary} role="status" data-testid="rights-summary">
          <span className={s.summaryCounts}>
            <strong>{counts.allowed}</strong> cleared · <strong>{counts.restricted}</strong> restricted · <strong>{counts.blocked}</strong> blocked · <strong>{counts.unknown}</strong> unknown
          </span>
          {credits.length > 0 && <span>Credits: {credits.join('; ')}</span>}
          {expiries.length > 0 && <span>Earliest expiry {formatDate(expiries[0])}</span>}
          {(counts.blocked > 0 || counts.unknown > 0) && <span style={{ color: 'var(--fg-2)' }}>Blocked and unknown shots are left out.</span>}
          {noCrop > 0 && (
            <span className={s.cropWarn} data-testid="crop-summary">
              <TriangleAlert size={14} strokeWidth={2} aria-hidden="true" />
              {`${plural(noCrop, 'shot')} ${noCrop === 1 ? 'has' : 'have'} no safe ${aspect} crop`}
            </span>
          )}
          {checkCrop > 0 && (
            <span className={s.cropWarn}>
              <TriangleAlert size={14} strokeWidth={2} aria-hidden="true" />
              {`${plural(checkCrop, 'shot')} may need reframing for ${aspect}`}
            </span>
          )}
        </div>
        {counts.restricted > 0 && (
          <Checkbox isSelected={includeRestricted} onChange={setIncludeRestricted}>
            {`${counts.restricted} of ${plural(items.length, 'shot')} ${counts.restricted === 1 ? 'is' : 'are'} restricted${credits.length ? ' (credit required)' : ''}. Include ${counts.restricted === 1 ? 'it' : 'them'}?`}
          </Checkbox>
        )}
        <div>
          <span className={s.legend}>Shot list</span>
          <div className={s.shots}>
            {items.map((i, n) => {
              const v = verdictOf.get(i.uid)
              const st = v ? stateFromVerdict(v.verdict, v.reasons, v.rights.expires) : 'unknown'
              const out = !keep(v?.verdict)
              const fit = consumer === 'cutawan' ? fitOf(i.uid) : 'na'
              return (
                <div key={`${i.uid}-${n}`} className={`${s.shot} ${out ? s.dropped : ''}`}>
                  <span className={s.idx}>{n + 1}</span>
                  {i.thumb ? <img src={mediaUrl(i.thumb)} alt="" /> : <span className={s.well} />}
                  <span className={s.shotText}>
                    <span>{i.title}</span>
                    <span>{i.duration ? formatDuration(i.duration) : ''}{out ? ' · left out' : ''}</span>
                  </span>
                  {(fit === 'none' || fit === 'check') && !out ? (
                    <span className={s.cropWarn} title={fit === 'none' ? `No safe ${aspect} crop: the subject doesn't fit a ${aspect} window` : `May need reframing for ${aspect}`}>
                      <TriangleAlert size={14} strokeWidth={2} aria-hidden="true" />
                      <span className={s.cropText}>{fit === 'none' ? `No safe ${aspect} crop` : 'Check crop'}</span>
                    </span>
                  ) : (
                    <span />
                  )}
                  {v && <RightsBadge state={st} reasons={v.reasons} record={v.rights} />}
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </Dialog>
  )
}
