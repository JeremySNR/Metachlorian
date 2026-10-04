import { useMemo, useState } from 'react'
import { Download, ExternalLink, FolderOpen, Package, Send } from 'lucide-react'
import type { Collection, CutawanMode, MediaPolicy, PackageResult, Verdict } from '../../api/types'
import { ApiError, mediaUrl } from '../../api/client'
import { buildCollectionPackage, buildPackage, useCollection, useRightsCheck, useVocabularies, verdictCounts } from '../../api/queries'
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
  const [use, setUse] = useState(def.use ?? 'marketing')
  const [channel, setChannel] = useState(def.channel ?? 'organic_social')
  const [territory, setTerritory] = useState(def.territory ?? 'GB')
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
                <Radio value="stringout">Stringout</Radio>
                <Radio value="proxies">Proxies</Radio>
                <Radio value="trimmed_originals">Trimmed originals</Radio>
                <Radio value="none">None</Radio>
              </RadioGroup>
            </div>
          </>
        )}
        <div>
          <span className={s.legend}>Intended use</span>
          <div className={s.cols3}>
            <Select aria-label="Usage" options={[{ id: '', label: 'Any use' }, ...opt('usage')]} selectedKey={use} onSelectionChange={(k) => setUse(String(k))} />
            <Select aria-label="Channel" options={[{ id: '', label: 'Any channel' }, ...opt('channel')]} selectedKey={channel} onSelectionChange={(k) => setChannel(String(k))} />
            <TextField aria-label="Territory (ISO code)" value={territory} onChange={(v) => setTerritory(v.toUpperCase().slice(0, 2))} placeholder="GB" mono />
          </div>
        </div>
        <div className={s.summary} role="status" data-testid="rights-summary">
          <span className={s.summaryCounts}>
            <strong>{counts.allowed}</strong> cleared · <strong>{counts.restricted}</strong> restricted · <strong>{counts.blocked}</strong> blocked · <strong>{counts.unknown}</strong> unknown
          </span>
          {credits.length > 0 && <span>Credits: {credits.join('; ')}</span>}
          {expiries.length > 0 && <span>Earliest expiry {formatDate(expiries[0])}</span>}
          {(counts.blocked > 0 || counts.unknown > 0) && <span style={{ color: 'var(--fg-2)' }}>Blocked and unknown shots are left out.</span>}
        </div>
        {counts.restricted > 0 && (
          <Checkbox isSelected={includeRestricted} onChange={setIncludeRestricted}>
            {`${counts.restricted} of ${items.length} shots are restricted${credits.length ? ' (credit required)' : ''}. Include them`}
          </Checkbox>
        )}
        <div>
          <span className={s.legend}>Shot list</span>
          <div className={s.shots}>
            {items.map((i, n) => {
              const v = verdictOf.get(i.uid)
              const st = v ? stateFromVerdict(v.verdict, v.reasons, v.rights.expires) : 'unknown'
              const out = !keep(v?.verdict)
              return (
                <div key={`${i.uid}-${n}`} className={`${s.shot} ${out ? s.dropped : ''}`}>
                  <span className={s.idx}>{n + 1}</span>
                  {i.thumb ? <img src={mediaUrl(i.thumb)} alt="" /> : <span className={s.well} />}
                  <span className={s.shotText}>
                    <span>{i.title}</span>
                    <span>{i.duration ? formatDuration(i.duration) : ''}{out ? ' · left out' : ''}</span>
                  </span>
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
