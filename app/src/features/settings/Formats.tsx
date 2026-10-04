import { useState } from 'react'
import { Link } from '@tanstack/react-router'
import { useQueryClient } from '@tanstack/react-query'
import { Button as RacButton, Disclosure, DisclosurePanel, Form, Heading } from 'react-aria-components'
import { ChevronRight, CircleAlert, CircleCheck, CircleDashed, FileVideo, Save, Trash2 } from 'lucide-react'
import type { FormatFile, FormatsResponse, RawFormat } from '../../api/types'
import { api, ApiError } from '../../api/client'
import { useAdminSettings, useFormats, useMe } from '../../api/queries'
import { Button } from '../../components/Button'
import { StatusText } from '../../components/EmptyState'
import { TextField } from '../../components/Field'
import { Ic } from '../../components/Icon'
import { toast } from '../../components/Toast'
import { plural, sentence } from '../../lib/format'
import { decoderMap, unreadableOnly } from '../../lib/formats'
import s from './Settings.module.css'

const PLACEHOLDER_HELP: Record<string, string> = {
  '{input}': 'the raw file',
  '{output}': 'the .mov file to write',
  '{output_stem}': 'the same path without the extension',
  '{output_dir}': 'the folder it goes in',
}

const EXAMPLE: Record<string, string> = {
  r3d: 'REDline --i {input} --o {output_stem} …',
  braw: 'braw-decode {input} {output} …',
}

/** Settings → Formats: what plays and what's analysed, camera-raw decoders and unreadable files (docs/guides/formats.md). */
export function FormatsSettings() {
  const formats = useFormats({ refetchInterval: typeof document !== 'undefined' && document.visibilityState === 'visible' ? 5000 : false })
  const me = useMe()
  const isAdmin = Boolean(me.data?.scopes.includes('admin'))
  const settings = useAdminSettings()
  const f = formats.data
  if (formats.isError) {
    return (
      <p role="alert" className={s.muted}>
        Couldn't read the formats: {(formats.error as Error).message}
      </p>
    )
  }
  if (!f) return <div aria-busy="true" />
  // The whole map is saved at once: the stored settings when an admin can read them, else what the formats list shows.
  const current: Record<string, string> =
    settings.data?.settings.raw_decoders ?? Object.fromEntries(f.raw.filter((r) => r.command).map((r) => [r.extension, r.command as string]))
  const waiting = f.raw.reduce((n, r) => n + r.waiting.length, 0)
  const unreadable = unreadableOnly(f.undecodable, f.raw)
  return (
    <section className={s.stack}>
      <Summary />
      <div className={s.group} data-testid="raw-formats">
        <div className={s.statusHead}>
          <h2>Camera raw</h2>
          {waiting > 0 ? (
            <a href="#waiting" className={s.inlineLink}>
              {plural(waiting, 'file')} waiting for a decoder
            </a>
          ) : (
            <span className={s.muted} style={{ fontSize: 'var(--text-sm)' }}>No files waiting</span>
          )}
        </div>
        <p className={s.followLine}>
          Raw that only the camera maker's software can read works through that software. Give Metachlorian the maker's command-line tool for each extension:
          it runs the command once per file, keeps the result as the file's working master, and analyses and exports from it. Any output FFmpeg can read
          works; ProRes 4444 or 422 HQ is a good choice. Saving a command reprocesses the files of that format. Or export a ProRes/DNx copy from DaVinci
          Resolve or the maker's software into a watched folder.
        </p>
        <dl className={s.placeholders} aria-label="Placeholders">
          {f.placeholders.map((p) => (
            <div key={p}>
              <dt>
                <code>{p}</code>
              </dt>
              <dd>{PLACEHOLDER_HELP[p] ?? ''}</dd>
            </div>
          ))}
        </dl>
        {!isAdmin && <p className={s.muted}>Only admins can set decoder commands.</p>}
        <ul className={s.rawList}>
          {f.raw.map((r) => (
            <RawRow key={r.extension} raw={r} current={current} isAdmin={isAdmin} />
          ))}
        </ul>
      </div>

      {waiting > 0 && (
        <div className={s.group} id="waiting" data-testid="waiting">
          <h2>Waiting for a decoder</h2>
          {f.raw
            .filter((r) => r.waiting.length)
            .map((r) => (
              <div key={r.extension} className={s.subBlock} id={`waiting-${r.extension}`}>
                <h3 className={s.subhead}>
                  {r.name} <code className={s.ext}>.{r.extension}</code>
                </h3>
                <FileList files={r.waiting} />
              </div>
            ))}
        </div>
      )}

      <div className={s.group} data-testid="unreadable">
        <h2>Unreadable files</h2>
        {unreadable.length ? (
          <>
            <p className={s.followLine}>FFmpeg couldn't read these files. The reason is under each one; damaged copies are often fixed by copying the file again from the card.</p>
            <FileList files={unreadable} />
          </>
        ) : (
          <p className={s.followLine}>None: every other file in the library could be read.</p>
        )}
      </div>

      <AllExtensions formats={f} />
    </section>
  )
}

function Summary() {
  return (
    <div className={s.group}>
      <h2>What plays and what's analysed</h2>
      <ul className={s.facts}>
        <li>
          Anything FFmpeg can decode is analysed and plays in the app, at any bit depth and in any colour space: 8, 10, 12 and 16-bit, floating point, 4:2:0,
          4:2:2, 4:4:4, RGB and alpha.
        </li>
        <li>
          The app plays a small preview made when a file is added (H.264, 8-bit 4:2:0, 540p), converted to BT.709 for display. HDR (HLG and HDR10/PQ) is
          tone-mapped to SDR, interlaced footage is deinterlaced, and log is shown flat, as recorded.
        </li>
        <li>
          Your originals stay untouched. Exports from originals keep their quality: 10-bit or 4:2:2 footage becomes ProRes 422 HQ, and 4:4:4, RGB, alpha or
          12-bit footage ProRes 4444. Timelines point at the original files.
        </li>
        <li>If part of a file can't be decoded, Metachlorian makes what it can and flags the file as “Damaged picture”.</li>
      </ul>
    </div>
  )
}

function RawRow({ raw, current, isAdmin }: { raw: RawFormat; current: Record<string, string>; isAdmin: boolean }) {
  const qc = useQueryClient()
  const [draft, setDraft] = useState<string | null>(null)
  const [errors, setErrors] = useState<Record<string, string>>({})
  const [busy, setBusy] = useState<'save' | 'remove' | null>(null)
  const saved = raw.command ?? ''
  const value = draft ?? saved
  const label = `Decoder command for .${raw.extension}`

  const save = async (command: string | null) => {
    setErrors({})
    setBusy(command ? 'save' : 'remove')
    try {
      await api.put('/api/admin/settings', { raw_decoders: decoderMap(current, raw.extension, command) })
      setDraft(null)
      for (const k of [['formats'], ['admin', 'settings'], ['processing']]) qc.invalidateQueries({ queryKey: k })
      toast({
        title: command ? `Decoder for .${raw.extension} saved` : `Decoder for .${raw.extension} removed`,
        description: raw.files ? (command ? `${plural(raw.files, `.${raw.extension} file`)} queued to be decoded again.` : `${plural(raw.files, `.${raw.extension} file`)} will wait for a decoder.`) : undefined,
        tone: 'info',
      })
    } catch (e) {
      setErrors({ command: e instanceof ApiError ? (e.status === 403 ? 'Only admins can set decoder commands.' : sentence(e.detail)) : String(e) })
    } finally {
      setBusy(null)
    }
  }

  return (
    <li className={s.rawRow} data-testid={`raw-${raw.extension}`}>
      <div className={s.rawHead}>
        <span className={s.rawName}>{raw.name}</span>
        <code className={s.ext}>.{raw.extension}</code>
        <span className={s.rawHint}>{raw.decoder_hint ?? 'The camera maker’s tools'}</span>
        <span className={s.rawFiles}>
          {raw.files ? plural(raw.files, 'file') : 'No files'}
          {raw.waiting.length > 0 && (
            <>
              {' · '}
              <a href={`#waiting-${raw.extension}`}>{raw.waiting.length} waiting</a>
            </>
          )}
        </span>
        {raw.command ? (
          <StatusText tone="cleared" icon={CircleCheck} className={s.rawState}>Decoder set</StatusText>
        ) : (
          <StatusText tone="neutral" icon={CircleDashed} className={s.rawState}>No decoder</StatusText>
        )}
      </div>
      {isAdmin ? (
        <Form
          className={s.keyForm}
          validationBehavior="aria"
          validationErrors={errors}
          onSubmit={(e) => {
            e.preventDefault()
            if (value.trim()) save(value)
          }}
        >
          <TextField
            name="command"
            aria-label={label}
            value={value}
            onChange={(v) => {
              setDraft(v)
              if (errors.command) setErrors({})
            }}
            mono
            spellCheck="false"
            autoComplete="off"
            placeholder={`e.g. ${EXAMPLE[raw.extension] ?? 'your-decoder {input} {output}'}`}
            className={s.commandInput}
          />
          <div className={s.keyActions}>
            <Button type="submit" variant="secondary" icon={Save} busy={busy === 'save'} isDisabled={!value.trim() || value.trim() === saved} aria-label={`Save the decoder for .${raw.extension}`}>
              Save
            </Button>
            {raw.command && (
              <Button variant="quiet" icon={Trash2} busy={busy === 'remove'} onPress={() => save(null)} aria-label={`Remove the decoder for .${raw.extension}`}>
                Remove
              </Button>
            )}
          </div>
        </Form>
      ) : raw.command ? (
        <code className={s.masked}>{raw.command}</code>
      ) : null}
    </li>
  )
}

function FileList({ files }: { files: FormatFile[] }) {
  return (
    <ul className={s.fileList}>
      {files.map((x) => (
        <li key={x.uid}>
          <Link to="/file/$assetId" params={{ assetId: x.uid }} className={s.fileLink}>
            <Ic icon={FileVideo} size={14} />
            {x.filename}
          </Link>
          {x.error && (
            <p className={s.fileError}>
              <Ic icon={CircleAlert} size={14} />
              <span>{x.error}</span>
            </p>
          )}
        </li>
      ))}
    </ul>
  )
}

function AllExtensions({ formats }: { formats: FormatsResponse }) {
  const raw = new Set(formats.raw.map((r) => r.extension))
  return (
    <Disclosure className={s.advanced} data-testid="all-extensions">
      <Heading level={2} className={s.advancedHead}>
        <RacButton slot="trigger" className={s.advancedButton}>
          <Ic icon={ChevronRight} size={14} className={s.chev} />
          All {formats.extensions.length} file types Metachlorian picks up
        </RacButton>
      </Heading>
      <DisclosurePanel>
        <p className={s.statusNote} style={{ paddingBlock: 'var(--space-2)' }}>
          Folders are scanned for these extensions. Camera raw ones (marked) need a decoder; the rest are read by FFmpeg.
        </p>
        <ul className={s.extList}>
          {formats.extensions.map((e) => (
            <li key={e}>
              <code>.{e}</code>
              {raw.has(e) && <span className={s.rawMark}> raw</span>}
            </li>
          ))}
        </ul>
      </DisclosurePanel>
    </Disclosure>
  )
}
