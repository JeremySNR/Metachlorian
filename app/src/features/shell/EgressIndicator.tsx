import { Cloud, HardDrive } from 'lucide-react'
import { Button as RacButton, Dialog, DialogTrigger, Heading, Popover } from 'react-aria-components'
import { Link } from '@tanstack/react-router'
import { useHealth } from '../../api/queries'
import { Ic } from '../../components/Icon'
import { NEVER_SENT, PROVIDER_DESTINATION, PROVIDER_NAME, SENDS } from '../../lib/providers'
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
      <RacButton className={`${s.egress} ${remote ? s.egressRemote : ''}`} aria-label={remote ? 'Content leaves this machine. Show details' : 'Local library analysis. Show content destinations'} data-testid="egress">
        <Ic icon={remote ? Cloud : HardDrive} size={16} />
        <span>{remote ? 'Leaves this machine' : 'Local'}</span>
      </RacButton>
      <Popover placement="bottom end" offset={6} className={`${o.popover} ${o.dialogPopover}`}>
        <Dialog className={s.egressPanel} aria-label="Where content goes">
          <Heading slot="title" level={3}>
            {remote ? 'Content leaves this machine' : 'Library analysis runs on this machine'}
          </Heading>
          {remote ? (
            <>
              {active.map((a) => {
                const role = a.adapter === 'vlm' ? 'vlm' : 'llm'
                const provider = a.provider && a.provider !== 'custom' ? a.provider : null
                return (
                  <dl key={a.adapter} className={s.egressRow}>
                    <dt>Adapter</dt>
                    <dd>
                      {role === 'vlm' ? 'Captions (vision language model)' : 'Summaries (language model)'} · {provider ? `${PROVIDER_NAME[provider]} · ` : ''}
                      {a.model || 'model not set'}
                    </dd>
                    <dt>What leaves</dt>
                    <dd>{SENDS[role].join('. ')}.</dd>
                    <dt>Where to</dt>
                    <dd>{provider ? PROVIDER_DESTINATION[provider] : safeHost(a.base_url)}</dd>
                    <dt>When</dt>
                    <dd>During analysis of every new or re-analysed file</dd>
                  </dl>
                )
              })}
              {egress?.community?.active && (
                <dl className={s.egressRow}>
                  <dt>Community index</dt><dd>Public YouTube analysis</dd>
                  <dt>What leaves</dt><dd>{egress.community.sends}. No videos, frames, face data or human notes.</dd>
                  <dt>Where to</dt><dd>{safeHost(egress.community.url)}</dd>
                  <dt>When</dt><dd>After eligible imports finish analysis. Local files are excluded.</dd>
                </dl>
              )}
              <p style={{ color: 'var(--fg-2)', fontSize: 'var(--text-xs)' }}>Never sent: {NEVER_SENT.join(', ').toLowerCase()}.</p>
            </>
          ) : (
            <p style={{ color: 'var(--fg-2)' }}>
              Library analysis, private-library search, previews and face recognition use local models and this server. Footage, frames, audio, text and face data stay here.
              {data && !data.vlm && ' No vision language model is configured, so descriptions come from the CPU tier.'}
            </p>
          )}
          {egress?.community?.url && <p style={{ color: 'var(--fg-2)', fontSize: 'var(--text-xs)' }}>Community searches send the query to {safeHost(egress.community.url)} when you search, even when contribution sharing is off.</p>}
          <Link to="/settings/$section" params={{ section: 'community' }}>Community sharing settings</Link>
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
