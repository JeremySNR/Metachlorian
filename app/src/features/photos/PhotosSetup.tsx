import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { ArrowRight, Check, Copy, Download, FolderOpen, RefreshCw, Sparkles, X } from 'lucide-react'
import { api } from '../../api/client'
import type { PhotoStatus } from '../../api/photos'
import { Button, IconButton } from '../../components/Button'
import { TextField } from '../../components/Field'
import { Ic } from '../../components/Icon'
import s from './Photos.module.css'

export type PhotoAction = (task: () => Promise<unknown>, success: string) => Promise<void>
export const exampleBrief = 'Find a lovely candid family photo with a nostalgic holiday feel. Compare the strongest candidates visually, then create a warm Kodak Gold-inspired edit in Lightroom on a virtual copy. Review the rendered result and tell me what changed.'

export function PhotosSetup({ status, canAdmin, canIngest, busy, action, enqueue, onCheck, onClose }: {
  status: PhotoStatus; canAdmin: boolean; canIngest: boolean; busy: boolean; action: PhotoAction
  enqueue: (path: string, body?: Record<string, unknown>) => Promise<unknown>
  onCheck: () => void; onClose: () => void
}) {
  const [step, setStep] = useState<'source' | 'connect' | 'agent'>(status.coverage.total ? 'connect' : 'source')
  const [source, setSource] = useState<'lightroom' | 'folder'>('lightroom')
  const [folder, setFolder] = useState('')
  const lr = status.lightroom
  const copied = status.connector.files_current
  const config = `[mcp_servers.metachlorian]\nurl = "${status.agent.endpoint}"\nbearer_token_env_var = "METACHLORIAN_TOKEN"`
  const copy = (value: string, message: string) => void action(() => navigator.clipboard.writeText(value), message)
  return <section className={`${s.panel} ${s.onboarding}`} aria-label="Photo setup">
    <div className={s.row}><div className={s.grow}><p className={s.eyebrow}>GET STARTED</p><h2>Connect your library and your agent.</h2></div><IconButton icon={X} label="Close photo setup" onPress={onClose} /></div>
    <nav className={s.steps} aria-label="Photo setup steps">
      {([['source', 'Choose your photos'], ['connect', 'Connect Lightroom'], ['agent', 'Use your agent']] as const).map(([id, title], index) => <button key={id} aria-current={step === id ? 'step' : undefined} onClick={() => setStep(id)}><span>{id === 'source' && status.coverage.total > 0 || id === 'connect' && lr.can_edit ? <Ic icon={Check} size={14} /> : index + 1}</span>{title}</button>)}
    </nav>
    {step === 'source' ? <>
      <p>Start with the photos you already have. Originals stay in place; temporary previews use a bounded cache.</p>
      <div className={s.sourceChoices}>
        <button className={s.sourceChoice} aria-pressed={source === 'lightroom'} onClick={() => setSource('lightroom')}><Ic icon={Sparkles} size={20} /><strong>Lightroom catalogue</strong><span>Recommended if your photos are already in Lightroom. Reuse its metadata, edits and available Smart Previews.</span></button>
        <button className={s.sourceChoice} aria-pressed={source === 'folder'} onClick={() => setSource('folder')}><Ic icon={FolderOpen} size={20} /><strong>Photo folder</strong><span>Index files on this computer. Connect Lightroom afterwards to preview matching RAWs and edit your selections.</span></button>
      </div>
      {source === 'lightroom' ? <div className={s.actions}><Button variant="primary" iconEnd={ArrowRight} onPress={() => setStep('connect')}>Set up Lightroom</Button></div> : <div className={s.setupBody}>
        <TextField label="Folder on this computer" value={folder} onChange={setFolder} placeholder="/Pictures/Family or C:\Pictures\Family" />
        {!status.decoders.raw.available ? <p className={s.hint}>RAW decoder unavailable. Files can still be indexed; connect Lightroom to view photos already in its catalogue. JPEG previews work without it.</p> : null}
        <div className={s.actions}><Button variant="primary" icon={FolderOpen} isDisabled={busy || !canIngest || !folder.trim()} disabledReason={!canIngest ? 'Your account needs ingest:write to add a source.' : undefined} onPress={() => void action(async () => { await enqueue('/api/photos/sources/folder', { path: folder }); setStep('connect') }, 'Folder indexing started. Metadata appears first; image analysis follows in Activity.')}>Index folder</Button></div>
      </div>}
    </> : null}
    {step === 'connect' ? <>
      <p>The Lightroom plug-in is the connection to your catalogue and Develop tools. Your agent chooses the photos and makes the edits; the plug-in carries out its requests in Lightroom.</p>
      <ol className={s.connectionSteps}>
        <li><div><h3>{copied ? 'Connector files are ready' : 'Copy the Lightroom connector'}</h3><p>Keep this folder in place after adding it to Lightroom.</p><div className={s.actions}><Button icon={Download} size="sm" isDisabled={!canAdmin || busy} disabledReason={!canAdmin ? 'An administrator must copy the connector files.' : undefined} onPress={() => void action(() => api.post('/api/photos/connector/install'), 'Files copied. Now add or reload the plug-in in Lightroom.')}>{copied ? 'Copy connector files again' : 'Copy connector files'}</Button>{status.connector.files_copied ? <Button icon={Copy} size="sm" onPress={() => copy(status.connector.path, 'Connector path copied.')}>Copy path</Button> : null}</div>{status.connector.files_copied ? <code className={s.path}>{status.connector.path}</code> : null}</div></li>
        <li><div><h3>Add it in Lightroom Classic</h3><p>Open <strong>File → Plug-in Manager → Add</strong>, choose <strong>MetachlorianPhotos.lrplugin</strong> from the folder above and enable it. Select <strong>Start connection</strong> in the plug-in’s panel if needed.</p>{lr.update_available || copied ? <p className={s.hint}>Already added it? After copying an update, select <strong>Reload Plug-in</strong> in Lightroom’s Plug-in Manager.</p> : null}</div></li>
        <li><div><h3>{lr.connected ? 'Lightroom has answered' : 'Verify the connection'}</h3><p>{lr.message}</p><div className={s.actions}><Button icon={RefreshCw} variant={lr.connected ? 'secondary' : 'primary'} isDisabled={busy} busy={busy} onPress={onCheck}>Check connection</Button>{lr.connected ? <span className={s.connectionProof}>Classic {lr.catalog?.version} · {lr.catalog?.name} · connector {lr.connector_version ?? 'update needed'}</span> : null}</div></div></li>
      </ol>
      {lr.connected ? <div className={s.nextStep}><div><h3>{source === 'folder' || status.coverage.folder_only ? 'Your folder photos can connect too' : 'Bring your catalogue into view'}</h3><p>{source === 'folder' || status.coverage.folder_only ? 'Matching files link to their existing Lightroom master when previewed. Sync the catalogue to discover the rest of your photos.' : 'Sync reads the open catalogue and indexes its photographs. It does not copy your originals.'}</p></div><Button isDisabled={busy || !canIngest} onPress={() => void action(() => enqueue('/api/photos/sources/lightroom'), 'Catalogue sync started. Follow its progress in Activity.')}>Sync catalogue</Button><Button iconEnd={ArrowRight} variant="primary" onPress={() => setStep('agent')}>Set up your agent</Button></div> : null}
      <details className={s.advanced}><summary>Connection help and compatibility</summary><p>Keep Lightroom and Metachlorian open under the same OS account. The connector uses local ports {status.connector.ports.join(' and ')}. Its Plug-in Manager panel shows whether requests have actually arrived.</p><p>Global edits are enabled for Classic 14.2–15.6, using the controls each photo exposes. AI subject, sky and background masks require 15.6. Real Lightroom validation on Mac and Windows is still pending.</p><p>For RAW files outside Lightroom, source installations can install the <code>photos</code> Python extra. Importing a selected file during an edit adds it to Lightroom in place.</p></details>
    </> : null}
    {step === 'agent' ? <div className={s.agentSetup}>
      <div><h3>Connect Codex or your preferred MCP agent</h3><p>Create a token in <Link to="/settings/$section" params={{ section: 'tokens' }}>Settings → API tokens for agents</Link> with <code>library:read</code>, <code>photos:edit</code> and <code>collections:write</code>. Add <code>ingest:write</code> if the agent should add sources.</p><p>For Codex on this computer, add this to <code>~/.codex/config.toml</code>. Set <code>METACHLORIAN_TOKEN</code> in the environment that launches Codex to your token, then restart or reconnect it.</p><pre className={s.code}>{config}</pre><Button icon={Copy} size="sm" onPress={() => copy(config, 'Codex configuration copied.')}>Copy Codex configuration</Button><p className={s.muted}>Other agents: use <code>{status.agent.endpoint}</code> with your token as a Bearer authorization header.</p></div>
      <div className={s.promptCard}><p className={s.eyebrow}>YOUR FIRST EDIT</p><h3>Start with the feeling you want.</h3><blockquote>{exampleBrief}</blockquote><Button icon={Copy} size="sm" onPress={() => copy(exampleBrief, 'Photo brief copied.')}>Copy example brief</Button><p>The agent should check the connection, look at previews, edit a virtual copy and review Lightroom’s rendered result. You can follow its jobs in Activity and review the copies here.</p><p className={s.muted}>Indexing runs locally. Previews requested by your agent go to that agent’s model provider.</p></div>
    </div> : null}
    <div className={s.setupFooter}><span>{status.coverage.total.toLocaleString()} photos indexed · {lr.can_edit ? 'Lightroom editing ready for this account' : 'Lightroom editing needs setup'}</span><Button size="sm" onPress={onClose}>{status.coverage.total ? 'Browse photos' : 'Close setup'}</Button></div>
  </section>
}
