import { Cloud, HardDrive } from 'lucide-react'
import { Button as RacButton, Dialog, DialogTrigger, Heading, Popover } from 'react-aria-components'
import { Link } from '@tanstack/react-router'
import { useHealth } from '../../api/queries'
import { Ic } from '../../components/Icon'
import o from '../../components/Overlay.module.css'
import s from './AppShell.module.css'

/** "Local" or "Leaves this machine", always in the top bar (system.md §3.20). */
export function EgressIndicator() {
  const { data } = useHealth()
  const egress = data?.egress
  const remote = Boolean(egress?.content_leaves_machine)
  const active = egress?.adapters.filter((a) => a.active) ?? []
  return (
    <DialogTrigger>
      <RacButton className={`${s.egress} ${remote ? s.egressRemote : ''}`} aria-label={remote ? 'Content leaves this machine. Show details' : 'Local: nothing leaves this machine. Show details'} data-testid="egress">
        <Ic icon={remote ? Cloud : HardDrive} size={16} />
        <span>{remote ? 'Leaves this machine' : 'Local'}</span>
      </RacButton>
      <Popover placement="bottom end" offset={6} className={`${o.popover} ${o.dialogPopover}`}>
        <Dialog className={s.egressPanel} aria-label="Where content goes">
          <Heading slot="title" level={3}>
            {remote ? 'Content leaves this machine' : 'Everything runs on this machine'}
          </Heading>
          {remote ? (
            active.map((a) => (
              <dl key={a.adapter} className={s.egressRow}>
                <dt>Adapter</dt>
                <dd>{a.adapter === 'vlm' ? 'Vision language model' : 'Language model'} · {a.model || 'model not set'}</dd>
                <dt>What leaves</dt>
                <dd>{a.sends === 'sampled keyframes and analyser text' ? 'Frames (sampled keyframes) and analyser text' : 'Analyser text and search queries'}</dd>
                <dt>Where to</dt>
                <dd>{safeHost(a.base_url)}</dd>
                <dt>When</dt>
                <dd>{a.adapter === 'vlm' ? 'During analysis of every new file' : 'During analysis and searches'}</dd>
              </dl>
            ))
          ) : (
            <p style={{ color: 'var(--fg-2)' }}>
              Analysis, search and previews use local models and this server. Footage, frames, audio and text stay here.
              {data && !data.vlm && ' No vision language model is configured, so descriptions come from the CPU tier.'}
            </p>
          )}
          <Link to="/settings/$section" params={{ section: 'adapters' }}>
            Model adapters settings
          </Link>
        </Dialog>
      </Popover>
    </DialogTrigger>
  )
}

function safeHost(url: string): string {
  try {
    return new URL(url).host
  } catch {
    return url || 'unknown endpoint'
  }
}
