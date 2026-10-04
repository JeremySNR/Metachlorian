/**
 * Journey 16: import videos from web links (docs/guides/importing-from-the-web.md).
 * YouTube is not reachable from the review machine, so the happy path uses a local link
 * (python http.server on :8799) and the YouTube link exercises the failure state.
 * Afterwards: the import rows are removed, the cookies file deleted and the imported file deleted from the library
 * (DELETE /api/assets; the downloaded copy stays on disk under imports/Journey import).
 */
import type { Page, Response } from '@playwright/test'
import { expect, H, snap, snapAll, test, waitForResults } from './helpers'

const LOCAL = 'http://127.0.0.1:8799/Holiday%20Parade.mp4'
const FAILING = 'https://www.youtube.com/watch?v=jNQXAC9IVRw'
const FOLDER = 'Journey import'
const COOKIES = '# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tFALSE\t2147483647\tsession_token\tjourney-secret-0f9e\n'

interface Row {
  id: number
  status: string
  asset_uid: string | null
  path: string | null
}

const isPost = (r: Response) => r.url().endsWith('/api/imports') && r.request().method() === 'POST'

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

test('16 import videos from web links: progress, origin, rights unknown, folder search, failure, cookies', async ({ page }) => {
  test.setTimeout(900_000)
  const created = new Set<number>()
  const importedAssets = new Set<string>()
  page.on('response', async (r) => {
    if (isPost(r) && r.ok()) for (const i of (await r.json()).imports as Row[]) created.add(i.id)
  })
  try {
    // ⌘K → Import from links… lands on Ingest with the links field focused.
    await page.goto('/search')
    await page.keyboard.press('Control+k')
    await page.keyboard.type('Import from links')
    await page.keyboard.press('Enter')
    await expect(page).toHaveURL(/\/ingest/)
    const form = page.getByTestId('add-from-links')
    const links = form.getByRole('textbox', { name: 'Links' })
    await expect(links).toBeFocused()

    // The core validates the links; its message shows on the field.
    await links.fill('youtube.com/watch?v=jNQXAC9IVRw')
    await expect(form).toContainText("isn't a web link")
    await form.getByRole('button', { name: 'Import', exact: true }).click()
    await expect(form).toContainText('Not a web link')
    await expect(links).toHaveAttribute('aria-invalid', 'true')
    await snap(page, '16-add-from-links-invalid--desktop-dark')

    // The local link into "Journey import": live progress to Imported.
    await links.fill(`${LOCAL}\n${LOCAL}`)
    await expect(form).toContainText('1 link · 1 repeat ignored')
    const folder = form.getByRole('combobox', { name: 'Folder' })
    await folder.fill(FOLDER)
    await page.keyboard.press('Escape')
    await expect(folder).toHaveValue(FOLDER)
    await expect(form.getByRole('button', { name: /Quality/ })).toContainText('1080p')
    const posted = page.waitForResponse(isPost)
    await form.getByRole('button', { name: 'Import', exact: true }).click()
    const local = ((await (await posted).json()).imports as Row[])[0]
    expect(local.status).toBe('queued')
    await expect(form.getByRole('status')).toContainText('1 link added')
    const row = page.locator(`[data-testid=import-row][data-id="${local.id}"]`)
    await expect(row).toBeVisible()
    if ((await row.getAttribute('data-status')) !== 'done') {
      await row.scrollIntoViewIfNeeded()
      await snap(page, '16-import-progress--desktop-dark')
    }
    await expect(row).toHaveAttribute('data-status', 'done', { timeout: 300_000 })
    await expect(row).toContainText('Imported')
    await expect(row).toContainText('Holiday Parade')
    await expect(row).toContainText(`to ${FOLDER}`)
    await expect(page.getByTestId('imports-announce')).toContainText('Imported Holiday Parade')

    // A link that can't be reached (YouTube is blocked here): Failed, with the error in full.
    const posted2 = page.waitForResponse(isPost)
    await links.fill(FAILING)
    await form.getByRole('button', { name: 'Import', exact: true }).click()
    const failing = ((await (await posted2).json()).imports as Row[])[0]
    const bad = page.locator(`[data-testid=import-row][data-id="${failing.id}"]`)
    await expect(bad).toHaveAttribute('data-status', 'failed', { timeout: 240_000 })
    await expect(bad.getByTestId('import-error')).not.toBeEmpty()
    await expect(page.getByTestId('imports-announce')).toContainText('Import failed')
    await page.getByTestId('imports').scrollIntoViewIfNeeded()
    await snapAll(page, '16-imports', { settle: () => page.getByTestId('imports').scrollIntoViewIfNeeded() })

    // Retry queues it again (and it fails again), then Remove takes it off the list.
    const retried = page.waitForResponse((r) => r.url().endsWith(`/api/imports/${failing.id}/retry`))
    await bad.getByRole('button', { name: /^Retry/ }).click()
    expect(((await (await retried).json()) as Row).status).toBe('queued')
    await expect(bad).toHaveAttribute('data-status', 'failed', { timeout: 240_000 })
    await bad.getByRole('button', { name: /^Remove/ }).click()
    await expect(bad).toHaveCount(0)
    created.delete(failing.id)

    // Open file: where it came from, and rights unknown with the nudge to check them.
    const done = (await (await page.request.get(`/api/imports/${local.id}`)).json()) as Row
    expect(done.asset_uid).toBeTruthy()
    importedAssets.add(done.asset_uid as string)
    await row.getByRole('link', { name: /Open file/ }).click()
    await expect(page).toHaveURL(new RegExp(`/file/${done.asset_uid}`))
    const origin = page.getByTestId('origin')
    await expect(origin).toContainText('Holiday Parade')
    await expect(origin).toContainText('Web link')
    await expect(origin.getByRole('link', { name: /Holiday Parade/ })).toHaveAttribute('target', '_blank')
    const nudge = page.getByTestId('check-rights-nudge')
    await expect(nudge).toContainText('Rights unknown')
    await snapAll(page, '16-asset-origin', { only: 'desktop' })
    await nudge.getByRole('button', { name: 'Check rights' }).click()
    const rightsDialog = page.getByRole('dialog')
    await expect(rightsDialog).toBeVisible()
    await expect(rightsDialog.getByRole('textbox', { name: 'Notes' })).toHaveValue(/Downloaded from http:\/\/127\.0\.0\.1:8799/)
    await expect(rightsDialog.getByRole('textbox', { name: 'Source' })).toHaveValue(/^Web: /)
    await snap(page, '16-check-rights--desktop-dark')
    await page.keyboard.press('Escape')
    await expect(rightsDialog).toHaveCount(0)

    // Search this folder finds it (once its shots are analysed).
    await expect
      .poll(async () => ((await (await page.request.get(`/api/assets/${done.asset_uid}`)).json()).shots ?? []).length, { timeout: 480_000, intervals: [3000] })
      .toBeGreaterThan(0)
    await page.goto('/ingest')
    const searched = page.waitForResponse((r) => r.url().endsWith('/api/search') && r.request().method() === 'POST')
    await row.getByRole('button', { name: `Search this folder: ${FOLDER}` }).click()
    await expect(page).toHaveURL(/folder=/)
    const res = await (await searched).json()
    expect(res.results.some((x: { asset_uid: string }) => x.asset_uid === done.asset_uid)).toBe(true)
    await waitForResults(page)
    await expect(page.getByTestId('scope-chip').first()).toContainText(FOLDER)
    await snap(page, '16-search-import-folder--desktop-dark')

    // Shot detail: origin and the nudge in the rights block.
    const shotUid = res.results.find((x: { asset_uid: string; uid: string }) => x.asset_uid === done.asset_uid).uid
    await page.goto(`/shot/${shotUid}`)
    await expect(page.getByTestId('origin')).toContainText('Web link')
    await expect(page.getByTestId('check-rights-nudge')).toBeVisible()
    await snapAll(page, '16-shot-origin', { only: 'desktop' })

    // Settings → Imports: yt-dlp status, default quality, logins. A bad cookies file is refused with the reason.
    await page.goto('/settings/imports')
    await expect(page.getByTestId('import-tool')).toContainText('Installed')
    await expect(page.getByTestId('import-tool-version')).toHaveText(/\d{4}\.\d{2}\.\d{2}/)
    await expect(page.getByTestId('cookies-state')).toContainText('No cookies file')
    await snapAll(page, '16-import-settings')
    const input = page.getByTestId('cookies').locator('input[type=file]')
    await input.setInputFiles({ name: 'cookies.txt', mimeType: 'text/plain', buffer: Buffer.from('these are not cookies\n') })
    await expect(page.getByTestId('cookies-error')).toContainText('not a cookies.txt file')
    await expect(page.getByTestId('cookies-error')).toContainText('Get cookies.txt LOCALLY')
    await page.getByTestId('cookies').scrollIntoViewIfNeeded()
    await snap(page, '16-cookies-invalid--desktop-dark')
    await input.setInputFiles({ name: 'cookies.txt', mimeType: 'text/plain', buffer: Buffer.from(COOKIES) })
    await expect(page.getByTestId('cookies-state')).toContainText('Cookies file stored')
    await expect(page.getByTestId('cookies-error')).toHaveCount(0)
    expect(await page.content()).not.toContain('journey-secret-0f9e')
    expect(JSON.stringify(await (await page.request.get('/api/imports/tool')).json())).not.toContain('journey-secret-0f9e')
    await page.getByTestId('cookies').scrollIntoViewIfNeeded()
    await snap(page, '16-cookies-stored--desktop-dark')
    await page.getByRole('button', { name: 'Remove cookies file' }).click()
    await expect(page.getByTestId('cookies-state')).toContainText('No cookies file')

    // 320 px: no sideways scroll on Ingest (with the imports list) and Settings → Imports.
    await page.setViewportSize({ width: 320, height: 640 })
    for (const route of ['/ingest', '/settings/imports']) {
      await page.goto(route)
      await page.waitForTimeout(800)
      expect(await noSidewaysScroll(page), `${route} overflows at 320 px`).toBe(0)
    }
    await page.goto('/ingest')
    await page.getByTestId('add-from-links').scrollIntoViewIfNeeded()
    for (const theme of ['dark', 'light'] as const) {
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
      await page.waitForTimeout(300)
      await snap(page, `16-add-from-links--320-${theme}`)
    }
    await page.getByTestId('imports').scrollIntoViewIfNeeded()
    for (const theme of ['dark', 'light'] as const) {
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
      await page.waitForTimeout(300)
      await snap(page, `16-imports--320-${theme}`)
    }
    await page.goto('/settings/imports')
    for (const theme of ['dark', 'light'] as const) {
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
      await page.waitForTimeout(300)
      await snap(page, `16-import-settings--320-${theme}`)
    }
    // Let the imported file's analysis finish, so the journeys after this one run on a quiet machine.
    await expect
      .poll(async () => ((await (await page.request.get(`/api/assets/${done.asset_uid}`)).json()).jobs ?? []).length, { timeout: 600_000, intervals: [3000] })
      .toBe(0)
  } finally {
    for (const id of created) {
      await page.request.post(`/api/imports/${id}/cancel`, { headers: H })
      await page.request.delete(`/api/imports/${id}`, { headers: H })
    }
    await page.request.delete('/api/imports/cookies', { headers: H })
    // The imported file itself (the API marks it deleted; the downloaded copy stays under imports/ on disk).
    for (const uid of importedAssets) await page.request.delete(`/api/assets/${uid}`, { headers: H })
  }
})
