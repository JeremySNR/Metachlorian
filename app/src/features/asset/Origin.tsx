import { ExternalLink, ShieldCheck } from 'lucide-react'
import type { Origin } from '../../api/types'
import { Button } from '../../components/Button'
import { RightsBadge } from '../../components/RightsBadge'
import { Ic } from '../../components/Icon'
import { formatDate, formatDateTime } from '../../lib/format'
import { siteName } from '../../lib/imports'
import s from './Origin.module.css'

/** Where a file imported from a web link came from: the link, site, channel, upload date and the licence the site states. */
export function OriginDetails({ origin }: { origin: Origin | Omit<Origin, 'description'> }) {
  const description = 'description' in origin ? origin.description : undefined
  return (
    <>
      <dl className={s.kv} data-testid="origin">
        <dt>Link</dt>
        <dd>
          <a className={s.link} href={origin.url} target="_blank" rel="noreferrer noopener">
            {origin.title || origin.url}
            <Ic icon={ExternalLink} size={12} />
            <span className="visually-hidden"> (opens in a new tab)</span>
          </a>
          {origin.title && <span className={s.url}>{origin.url}</span>}
        </dd>
        <dt>Site</dt>
        <dd>{siteName(origin.site)}</dd>
        <dt>Channel</dt>
        <dd>{origin.uploader || <span className={s.muted}>Not given</span>}</dd>
        <dt>Uploaded</dt>
        <dd>{origin.upload_date ? formatDate(origin.upload_date) : <span className={s.muted}>Unknown</span>}</dd>
        <dt>Licence</dt>
        <dd>{origin.license ? `${origin.license} (as the site states it)` : <span className={s.muted}>None stated</span>}</dd>
        {origin.tags.length > 0 && (
          <>
            <dt>Tags</dt>
            <dd>{origin.tags.join(', ')}</dd>
          </>
        )}
        <dt>Imported</dt>
        <dd>{formatDateTime(origin.imported_at)}</dd>
      </dl>
      {description && (
        <details className={s.description}>
          <summary>Description from the site</summary>
          <p>{description}</p>
        </details>
      )}
    </>
  )
}

/** Rights still unknown on an imported file: being online is not clearance. */
export function CheckRightsNudge({ onCheck, badge = true }: { onCheck: () => void; badge?: boolean }) {
  return (
    <div className={s.nudge} data-testid="check-rights-nudge">
      {badge && <RightsBadge state="unknown" />}
      <p>
        Downloaded from the web. Being online, or labelled Creative Commons by whoever uploaded it, is not clearance: check the rights and mark it cleared. Agents
        don't see it until then.
      </p>
      <Button variant="secondary" size="sm" icon={ShieldCheck} onPress={onCheck}>
        Check rights
      </Button>
    </div>
  )
}
