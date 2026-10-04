import { useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { FileTrigger } from 'react-aria-components'
import { CircleAlert, CircleCheck, CircleDashed, Cookie, Download, ExternalLink, RefreshCw, Trash2, TriangleAlert, Upload } from 'lucide-react'
import type { ImportTool } from '../../api/types'
import { api, ApiError } from '../../api/client'
import { useAdminSettings, useHealth, useImportTool, useMe } from '../../api/queries'
import { Button } from '../../components/Button'
import { StatusText } from '../../components/EmptyState'
import { Select, TextField } from '../../components/Field'
import { Ic } from '../../components/Icon'
import { toast } from '../../components/Toast'
import { sentence } from '../../lib/format'
import { QUALITIES, qualityLabel } from '../../lib/imports'
import s from './Settings.module.css'

const BROWSER_NAME: Record<string, string> = { chrome: 'Chrome', edge: 'Edge', firefox: 'Firefox', brave: 'Brave', opera: 'Opera', vivaldi: 'Vivaldi', safari: 'Safari (macOS)' }
const BROWSER_ORDER = ['chrome', 'edge', 'firefox', 'brave', 'opera', 'vivaldi', 'safari']
const CHROMIUM = new Set(['chrome', 'edge', 'brave', 'opera', 'vivaldi'])
const EXTENSION = 'https://github.com/kairi003/Get-cookies.txt-LOCALLY'

const errText = (e: unknown) => (e instanceof ApiError ? sentence(e.detail) : String(e))

/** Settings → Imports: the yt-dlp program, default quality and logins for private videos (docs/guides/importing-from-the-web.md). */
export function ImportSettings() {
  const tool = useImportTool()
  const me = useMe()
  const isAdmin = Boolean(me.data?.scopes.includes('admin'))
  const t = tool.data
  if (tool.isError) {
    return (
      <p role="alert" className={s.muted}>
        Couldn't read the import settings: {(tool.error as Error).message}
      </p>
    )
  }
  if (!t) return <div aria-busy="true" />
  return (
    <section className={s.stack}>
      {!isAdmin && <p className={s.muted}>Only admins can change these.</p>}
      <Program tool={t} isAdmin={isAdmin} />
      <Quality tool={t} isAdmin={isAdmin} />
      <Logins tool={t} isAdmin={isAdmin} />
    </section>
  )
}

function useRefresh() {
  const qc = useQueryClient()
  return (next?: ImportTool) => {
    if (next) qc.setQueryData(['imports', 'tool'], next)
    qc.invalidateQueries({ queryKey: ['imports', 'tool'] })
    qc.invalidateQueries({ queryKey: ['admin', 'settings'] })
  }
}

async function saveSetting(body: Record<string, unknown>) {
  await api.put('/api/admin/settings', body)
}

function Program({ tool, isAdmin }: { tool: ImportTool; isAdmin: boolean }) {
  const refresh = useRefresh()
  const settings = useAdminSettings()
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null)
  const [path, setPath] = useState<string | null>(null)
  const saved = settings.data?.settings.ytdlp_path ?? ''
  const shownPath = path ?? saved

  const install = async () => {
    setBusy(true)
    setResult(null)
    try {
      const next = await api.post<ImportTool>('/api/imports/tool', { update: tool.installed })
      refresh(next)
      setResult({ ok: true, text: `yt-dlp ${next.version ?? ''} is ready.`.replace('  ', ' ') })
    } catch (e) {
      setResult({ ok: false, text: errText(e) })
    } finally {
      setBusy(false)
    }
  }

  const savePath = async () => {
    try {
      await saveSetting({ ytdlp_path: shownPath.trim() })
      setPath(null)
      refresh()
      toast({ title: shownPath.trim() ? 'yt-dlp program path saved' : 'yt-dlp program path cleared', tone: 'info' })
    } catch (e) {
      toast({ title: "Couldn't save the program path", description: errText(e), tone: 'error' })
    }
  }

  return (
    <div className={s.statusBlock} data-testid="import-tool">
      <div className={s.statusHead}>
        <h2>yt-dlp</h2>
        {tool.installed ? (
          <StatusText tone="cleared" icon={CircleCheck}>Installed</StatusText>
        ) : (
          <StatusText tone="neutral" icon={CircleDashed}>Not installed yet</StatusText>
        )}
      </div>
      <p className={s.followLine}>
        The program that downloads videos from YouTube, Vimeo, the Internet Archive, direct video links and the{' '}
        <a href="https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md" target="_blank" rel="noreferrer noopener">
          thousand-plus sites it supports
          <span className="visually-hidden"> (opens in a new tab)</span>
        </a>
        .
      </p>
      <dl className={s.statusList}>
        <dt>Version</dt>
        <dd data-testid="import-tool-version">{tool.version ?? (tool.installed ? 'Unknown' : '—')}</dd>
        <dt>Program</dt>
        <dd>
          {tool.path ? <code className={s.masked}>{tool.path}</code> : 'None yet'}
          <span className={s.statusNote}>
            {!tool.installed
              ? 'Metachlorian downloads the official standalone build from GitHub into the library the first time someone imports. Install it now to check the server can reach GitHub.'
              : tool.managed
                ? 'The official standalone build, downloaded by Metachlorian into the library.'
                : 'A copy installed on the server (on its PATH or set below). If Update fails, update it the way it was installed.'}
          </span>
        </dd>
      </dl>
      <p className={s.statusNote}>Sites change often, so when a download fails Metachlorian lets yt-dlp update itself once and retries.</p>
      {isAdmin && (
        <div className={s.saveRow}>
          <Button variant="secondary" icon={tool.installed ? RefreshCw : Download} busy={busy} onPress={install}>
            {tool.installed ? 'Update yt-dlp' : 'Install yt-dlp'}
          </Button>
          {result && (
            <span role="status">
              <StatusText tone={result.ok ? 'cleared' : 'blocked'} icon={result.ok ? CircleCheck : CircleAlert} className={s.wrapStatus}>
                {result.text}
              </StatusText>
            </span>
          )}
        </div>
      )}
      {isAdmin && (
        <form
          className={s.keyForm}
          onSubmit={(e) => {
            e.preventDefault()
            savePath()
          }}
        >
          <TextField
            label="Program path"
            value={shownPath}
            onChange={setPath}
            mono
            spellCheck="false"
            placeholder="e.g. /usr/local/bin/yt-dlp"
            description="Leave empty to use yt-dlp on the server's PATH, or else the copy Metachlorian downloads."
            className={s.keyInput}
          />
          <div className={s.keyActions}>
            <Button type="submit" variant="secondary" isDisabled={shownPath.trim() === saved}>
              Save path
            </Button>
          </div>
        </form>
      )}
    </div>
  )
}

function Quality({ tool, isAdmin }: { tool: ImportTool; isAdmin: boolean }) {
  const refresh = useRefresh()
  const change = async (h: number) => {
    try {
      await saveSetting({ import_max_height: h })
      refresh()
      toast({ title: `Imports default to ${qualityLabel(h)}`, tone: 'info' })
    } catch (e) {
      toast({ title: "Couldn't change the default quality", description: errText(e), tone: 'error' })
    }
  }
  return (
    <div className={s.group}>
      <h2>Default quality</h2>
      <Select
        label="Highest quality"
        description="Imports download at this height, or the nearest below it when a video has nothing this size. You can choose for each import on the Ingest page."
        options={QUALITIES.map((h) => ({ id: String(h), label: qualityLabel(h) }))}
        selectedKey={String(tool.max_height)}
        onSelectionChange={(k) => change(Number(k))}
        isDisabled={!isAdmin}
        className={s.narrowField}
      />
    </div>
  )
}

function Logins({ tool, isAdmin }: { tool: ImportTool; isAdmin: boolean }) {
  const refresh = useRefresh()
  const health = useHealth()
  const team = Boolean(health.data?.auth_required)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [stored, setStored] = useState('')
  const browser = tool.cookies_browser ?? ''
  const browsers = BROWSER_ORDER.filter((b) => tool.browsers.includes(b)).concat(tool.browsers.filter((b) => !BROWSER_ORDER.includes(b)))

  const uploadCookies = async (files: FileList | null) => {
    const f = files?.[0]
    if (!f) return
    setBusy(true)
    setError('')
    setStored('')
    try {
      const form = new FormData()
      form.append('file', f)
      const next = await api.put<ImportTool>('/api/imports/cookies', form)
      refresh(next)
      setStored(`Cookies file stored (${f.name}).`)
    } catch (e) {
      setError(errText(e))
    } finally {
      setBusy(false)
    }
  }

  const removeCookies = async () => {
    setError('')
    setStored('')
    try {
      const next = await api.del<ImportTool>('/api/imports/cookies')
      refresh(next)
      setStored('Cookies file removed.')
    } catch (e) {
      setError(errText(e))
    }
  }

  const setBrowser = async (b: string) => {
    try {
      await saveSetting({ import_cookies_browser: b })
      refresh()
      toast({ title: b ? `Imports borrow the ${BROWSER_NAME[b] ?? b} login` : 'Imports no longer borrow a browser login', tone: 'info' })
    } catch (e) {
      toast({ title: "Couldn't change the browser login", description: errText(e), tone: 'error' })
    }
  }

  return (
    <div className={s.group}>
      <h2>Private, unlisted and members-only videos</h2>
      <p className={s.followLine}>
        yt-dlp can borrow a login. Sign in to the site in a browser, then give Metachlorian that login in one of these two ways. When both are set, the cookies.txt
        file is used.
      </p>

      <div className={s.subBlock} data-testid="cookies">
        <h3 className={s.subhead}>cookies.txt file</h3>
        <p className={s.statusNote}>Works everywhere; recommended for servers.</p>
        <div className={s.keyState} data-testid="cookies-state">
          {tool.cookies_file ? (
            <>
              <StatusText tone="cleared" icon={Cookie}>Cookies file stored</StatusText>
              <span className={s.muted}>readable only by the server, never sent back</span>
            </>
          ) : (
            <StatusText tone="neutral" icon={Cookie}>No cookies file</StatusText>
          )}
        </div>
        <ol className={s.howTo}>
          <li>Sign in to the site in your browser (open the video there once).</li>
          <li>
            Export that site's cookies with the{' '}
            <a href={EXTENSION} target="_blank" rel="noreferrer noopener">
              Get cookies.txt LOCALLY
              <Ic icon={ExternalLink} size={12} />
              <span className="visually-hidden"> (opens in a new tab)</span>
            </a>{' '}
            browser extension. It saves a Netscape-format cookies.txt file.
          </li>
          <li>Upload the file here.</li>
        </ol>
        {isAdmin && (
          <div className={s.saveRow}>
            <FileTrigger acceptedFileTypes={['.txt', 'text/plain']} onSelect={uploadCookies}>
              <Button variant="secondary" icon={Upload} busy={busy}>
                {tool.cookies_file ? 'Replace cookies.txt…' : 'Upload cookies.txt…'}
              </Button>
            </FileTrigger>
            {tool.cookies_file && (
              <Button variant="quiet" icon={Trash2} onPress={removeCookies}>
                Remove cookies file
              </Button>
            )}
          </div>
        )}
        {error && (
          <p role="alert" className={s.alertLine} data-testid="cookies-error">
            <Ic icon={CircleAlert} size={14} />
            <span>{error}</span>
          </p>
        )}
        <span role="status" className={s.followLine}>{stored}</span>
        <p className={s.statusNote}>
          A cookies file is a login: whoever has it can act as you on that site. Remove it when you no longer need it, and upload a fresh one if imports start
          asking for a login again.
        </p>
      </div>

      <div className={s.subBlock}>
        <h3 className={s.subhead}>Browser login</h3>
        <p className={s.statusNote}>
          Solo or desktop only. It reads the browser on the machine running Metachlorian, so it helps only when that machine is your computer.
        </p>
        {team && (
          <StatusText tone="caution" icon={TriangleAlert} className={s.wrapStatus}>
            This server is in team mode: a browser login would read the server's browser, not yours. Use a cookies.txt file.
          </StatusText>
        )}
        <Select
          label="Browser"
          options={[{ id: 'none', label: 'No browser login' }, ...browsers.map((b) => ({ id: b, label: BROWSER_NAME[b] ?? b }))]}
          selectedKey={browser || 'none'}
          onSelectionChange={(k) => setBrowser(k === 'none' ? '' : String(k))}
          isDisabled={!isAdmin || (team && !browser)}
          className={s.narrowField}
        />
        {CHROMIUM.has(browser) ? (
          <StatusText tone="caution" icon={TriangleAlert} className={s.wrapStatus}>
            On Windows, Chrome and Edge encrypt their cookies so other programs cannot read them; use a cookies.txt file or Firefox there. Chromium browsers also
            lock their cookies while open: if an import fails, quit the browser fully and retry.
          </StatusText>
        ) : (
          <p className={s.statusNote}>On Windows, Chrome and Edge encrypt their cookies so other programs cannot read them; use a cookies.txt file or Firefox there.</p>
        )}
      </div>
    </div>
  )
}
