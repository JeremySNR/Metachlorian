/**
 * Journey 17: Settings → Formats (docs/guides/formats.md). Three small files are made with ffmpeg and uploaded:
 * a "MotionCam RAW" file (an MP4 under a .mcraw name, so `cp {input} {output}` is a working decoder), a file of
 * random bytes (unreadable) and a transport stream with corrupted packets (damaged picture).
 * Afterwards: the decoder map is restored to what it was and the three files are deleted from the library
 * (DELETE /api/assets; their uploads stay on disk under <library>/uploads).
 */
import { execFileSync } from 'node:child_process'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import type { APIRequestContext, Page } from '@playwright/test'
import { expect, H, snap, snapAll, test } from './helpers'

interface Asset {
  uid: string
  status: string
  technical: Record<string, unknown>
  fields: Record<string, { value: unknown }>
  processing: { analyser: string; status: string; error: string | null }[]
  jobs: { analyser: string; status: string }[]
}

function makeFixtures(stamp: string) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'mc-formats-'))
  const mp4 = path.join(dir, 'raw.mp4')
  const ts = path.join(dir, 'damaged.ts')
  const lavfi = (d: number) => ['-f', 'lavfi', '-i', `testsrc2=d=${d}:s=640x360:r=25`]
  execFileSync('ffmpeg', ['-v', 'error', '-y', ...lavfi(3), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-metadata', `comment=journey ${stamp}`, '-f', 'mp4', mp4])
  execFileSync('ffmpeg', ['-v', 'error', '-y', ...lavfi(4), '-f', 'lavfi', '-i', 'sine=d=4', '-c:v', 'libx264', '-g', '25', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-metadata', `comment=journey ${stamp}`, ts])
  // Overwrite the payload of a run of TS packets in three places: decodable, with errors.
  const b = fs.readFileSync(ts)
  let seed = 7
  const rnd = () => (seed = (seed * 1103515245 + 12345) & 0x7fffffff) & 0xff
  for (const start of [Math.floor(b.length / 3), Math.floor(b.length / 2), Math.floor((2 * b.length) / 3)]) {
    for (let i = start; i < start + 6000 && i + 188 < b.length; i += 188) for (let j = 8; j < 180; j++) b[i + j] = rnd()
  }
  return {
    raw: { name: `journey-motioncam-${stamp}.mcraw`, buffer: fs.readFileSync(mp4) },
    unreadable: { name: `journey-unreadable-${stamp}.mp4`, buffer: Buffer.concat([Buffer.from(`not a video ${stamp}\n`), Buffer.alloc(200_000, 0x5a)]) },
    damaged: { name: `journey-damaged-${stamp}.ts`, buffer: b },
  }
}

async function uploadFile(request: APIRequestContext, f: { name: string; buffer: Buffer }): Promise<string> {
  const r = await request.post('/api/upload', { headers: H, multipart: { file: { name: f.name, mimeType: 'application/octet-stream', buffer: f.buffer } } })
  expect(r.ok(), await r.text()).toBeTruthy()
  const body = await r.json()
  expect(body.outcome).toBe('added')
  return body.asset_uid
}

const asset = async (request: APIRequestContext, uid: string) => (await (await request.get(`/api/assets/${uid}`)).json()) as Asset
const run = (a: Asset, analyser: string) => a.processing.find((p) => p.analyser === analyser)?.status ?? 'pending'

async function noSidewaysScroll(page: Page) {
  return page.evaluate(() => {
    const W = window.innerWidth
    const clippedBy = (el: Element) => {
      for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
        if (getComputedStyle(p).overflowX !== 'visible' && p.getBoundingClientRect().right <= W + 1) return true
      }
      return false
    }
    return [...document.querySelectorAll('body *')].filter((el) => {
      const r = el.getBoundingClientRect()
      return r.width > 0 && r.right > W + 1 && getComputedStyle(el).position !== 'fixed' && !clippedBy(el)
    }).length
  })
}

test('17 formats: camera raw decoders, unreadable and damaged files', async ({ page }) => {
  test.setTimeout(900_000)
  const original = ((await (await page.request.get('/api/admin/settings')).json()).settings.raw_decoders ?? {}) as Record<string, string>
  expect(original.mcraw).toBeUndefined()
  const uploaded: string[] = []
  try {
    const fx = makeFixtures(Date.now().toString(36))
    const rawUid = await uploadFile(page.request, fx.raw)
    uploaded.push(rawUid)
    const badUid = await uploadFile(page.request, fx.unreadable)
    uploaded.push(badUid)
    const damagedUid = await uploadFile(page.request, fx.damaged)
    uploaded.push(damagedUid)
    // Uploads jump the queue: wait for the technical step on all three, and the damaged file's preview.
    await expect.poll(async () => run(await asset(page.request, rawUid), 'technical'), { timeout: 300_000, intervals: [2000] }).toBe('failed')
    await expect.poll(async () => run(await asset(page.request, badUid), 'technical'), { timeout: 300_000, intervals: [2000] }).toBe('failed')
    await expect.poll(async () => run(await asset(page.request, damagedUid), 'proxy'), { timeout: 300_000, intervals: [2000] }).toBe('done')

    // Settings → Formats: what plays, camera raw with decoder hints, waiting and unreadable files.
    await page.goto('/settings/formats')
    await expect(page.getByRole('heading', { name: 'Formats', level: 1 })).toBeVisible()
    const mcraw = page.getByTestId('raw-mcraw')
    await expect(mcraw).toContainText('MotionCam RAW')
    await expect(mcraw).toContainText('MotionCam Tools')
    await expect(mcraw).toContainText('1 waiting')
    await expect(mcraw).toContainText('No decoder')
    await expect(page.getByTestId('waiting')).toContainText(fx.raw.name)
    await expect(page.getByTestId('waiting')).toContainText('Set a raw decoder command for .mcraw in Settings → Formats')
    const unreadable = page.getByTestId('unreadable')
    await expect(unreadable).toContainText(fx.unreadable.name)
    await expect(unreadable).toContainText('FFmpeg cannot read this file')
    await expect(unreadable).not.toContainText(fx.raw.name)
    await snapAll(page, '17-formats')
    await page.getByTestId('waiting').scrollIntoViewIfNeeded()
    await snapAll(page, '17-formats-waiting', { only: 'desktop', settle: () => page.getByTestId('waiting').scrollIntoViewIfNeeded() })
    await page.getByRole('button', { name: /file types Metachlorian picks up/ }).click()
    await expect(page.getByTestId('all-extensions')).toContainText('.braw')
    await expect(page.getByTestId('all-extensions')).toContainText('.mxf')
    await page.getByTestId('all-extensions').scrollIntoViewIfNeeded()
    await snap(page, '17-formats-extensions--desktop-dark')

    // An invalid command: the core's message on the field.
    const field = mcraw.getByRole('textbox', { name: 'Decoder command for .mcraw' })
    await field.fill('cp {input}')
    await mcraw.getByRole('button', { name: 'Save the decoder for .mcraw' }).click()
    await expect(mcraw).toContainText('needs {input} and {output}')
    await expect(field).toHaveAttribute('aria-invalid', 'true')
    await mcraw.scrollIntoViewIfNeeded()
    await snap(page, '17-decoder-invalid--desktop-dark')

    // A working command: saved, and the file is decoded again through it.
    await field.fill('cp {input} {output}')
    await expect(field).not.toHaveAttribute('aria-invalid', 'true')
    await mcraw.getByRole('button', { name: 'Save the decoder for .mcraw' }).click()
    await expect(mcraw).toContainText('Decoder set')
    expect((await (await page.request.get('/api/admin/settings')).json()).settings.raw_decoders).toEqual({ ...original, mcraw: 'cp {input} {output}' })
    await snap(page, '17-decoder-saved--desktop-dark')
    await expect
      .poll(async () => Boolean((await asset(page.request, rawUid)).technical.decoded_from), { timeout: 300_000, intervals: [2000] })
      .toBe(true)
    await page.goto(`/file/${rawUid}`)
    await expect(page.getByTestId('decoded-from')).toContainText('Decoded from MotionCam RAW with cp {input} {output}')
    await snapAll(page, '17-asset-decoded', { only: 'desktop' })

    // Remove: back to the original map; the file waits for a decoder again.
    await page.goto('/settings/formats')
    await mcraw.getByRole('button', { name: 'Remove the decoder for .mcraw' }).click()
    await expect(mcraw).toContainText('No decoder')
    await expect(field).toHaveValue('')
    expect((await (await page.request.get('/api/admin/settings')).json()).settings.raw_decoders ?? {}).toEqual(original)

    // Damaged picture on the asset view, with bit depth and colour.
    await page.goto(`/file/${damagedUid}`)
    await expect(page.getByTestId('damaged-picture')).toContainText('Damaged picture')
    await expect(page.getByText('640×360 · 25p · H264 · 8-bit')).toBeVisible()
    await snapAll(page, '17-asset-damaged', { only: 'desktop' })

    // An unreadable file: the reason and "Set up a decoder", from the ingest row and from the asset view.
    await page.goto('/ingest')
    await expect(page.getByTestId('queue-table').getByTestId('set-up-decoder').first()).toBeVisible()
    await page.goto(`/file/${badUid}`)
    await expect(page.getByText("Metachlorian can't read this file yet")).toBeVisible()
    await expect(page.getByText('FFmpeg cannot read this file').first()).toBeVisible()
    await snapAll(page, '17-asset-unreadable', { only: 'desktop' })
    await page.getByTestId('set-up-decoder').first().click()
    await expect(page).toHaveURL(/\/settings\/formats/)

    // 320 px: no sideways scroll; the rows stack.
    await page.setViewportSize({ width: 320, height: 640 })
    await page.goto('/settings/formats')
    await page.waitForTimeout(800)
    expect(await noSidewaysScroll(page), '/settings/formats overflows at 320 px').toBe(0)
    await page.getByTestId('raw-formats').scrollIntoViewIfNeeded()
    for (const theme of ['dark', 'light'] as const) {
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
      await page.waitForTimeout(300)
      await snap(page, `17-formats--320-${theme}`)
    }
  } finally {
    await page.request.put('/api/admin/settings', { headers: H, data: { raw_decoders: original } })
    for (const uid of uploaded) await page.request.delete(`/api/assets/${uid}`, { headers: H })
  }
})
