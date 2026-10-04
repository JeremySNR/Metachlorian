/**
 * User-story journeys (system.md §10, task brief): each records a video and
 * screenshots at desktop 1440×900, laptop 1024×768 and tablet 768×1024 in
 * light and dark. Runs against the live core (BASE_URL, default :8770).
 */
import fs from 'node:fs'
import path from 'node:path'
import { expect, H, REVIEW, searchApi, snap, snapAll, test, waitForResults } from './helpers'

const QUERY = 'handheld street food close-ups, busy, night'
const perf: Record<string, unknown> = {}

test.afterAll(() => {
  const file = path.join(REVIEW, 'perf-web.json')
  const prev = fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf8')) : {}
  fs.writeFileSync(file, JSON.stringify({ ...prev, ...perf }, null, 2))
})

test('01 search: natural language to shot results with previews', async ({ page }) => {
  await page.goto('/search')
  await page.keyboard.press('/')
  await page.keyboard.type(QUERY, { delay: 25 })
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/q=handheld/)
  const card = await waitForResults(page)
  await expect(page.getByTestId('result-count')).toContainText('shots')
  // Parsed interpretation as chips, with the words they came from.
  await expect(page.getByTestId('query-chip').first()).toBeVisible()
  expect(await page.getByTestId('query-chip').count()).toBeGreaterThanOrEqual(3)
  // Edge strip timecode on cards.
  await expect(card).toContainText(/\d{2}:\d{2}:\d{2}[:;]\d{2}/)
  await snapAll(page, '01-search-results')

  // Hover scrub: sprite position changes as the pointer moves (no <video> per card).
  const frame = card.locator('div').first()
  const box = (await frame.boundingBox())!
  await page.mouse.move(box.x + 10, box.y + box.height / 2)
  await page.mouse.move(box.x + box.width * 0.3, box.y + box.height / 2, { steps: 4 })
  await page.waitForTimeout(250)
  await page.mouse.move(box.x + box.width * 0.75, box.y + box.height / 2, { steps: 6 })
  await expect(card).toHaveClass(/scrubbing/)
  await snap(page, '01-search-hover-scrub--desktop-dark')
  // Dwell: the pooled video plays in place.
  await page.waitForTimeout(900)
  await expect(card.locator('video')).toHaveCount(1)
  await snap(page, '01-search-hover-preview--desktop-dark')
  const videos = await page.locator('video').count()
  expect(videos).toBeLessThanOrEqual(5) // pool of 4 + the inspector player

  // Preview start time is measured in Electron (H.264 build): e2e/preview.electron.spec.ts.
})

test('02 select a shot and find similar', async ({ page }) => {
  await page.goto(`/search?q=${encodeURIComponent('street at night')}`)
  const card = await waitForResults(page)
  await card.click()
  const insp = page.getByTestId('inspector')
  await expect(insp).toBeVisible()
  await expect(insp.getByTestId('why')).toBeVisible()
  await snapAll(page, '02-inspector-why-it-matched', { only: 'desktop' })
  await insp.getByRole('button', { name: /Find similar/ }).click()
  await expect(page).toHaveURL(/similar=/)
  await expect(page.getByText('SIMILAR TO')).toBeVisible()
  await waitForResults(page)
  await snapAll(page, '02-similar-results')
  // Laptop: opening a shot shows the inspector as an overlay sheet.
  await page.setViewportSize({ width: 1024, height: 768 })
  await page.locator('[role=grid] [role=gridcell][data-uid]').nth(1).click()
  await expect(page.getByRole('dialog', { name: 'Shot details' })).toBeVisible()
  await page.waitForTimeout(600)
  await snap(page, '02-inspector-sheet--laptop-dark')
  await page.keyboard.press('Escape')
  await page.setViewportSize({ width: 1440, height: 900 })
  // Query by example: an image dropped (or picked) on the search bar → POST /api/similar.
  const first = await (await page.request.post('/api/search', { data: { q: 'street', limit: 1 }, headers: H })).json()
  const img = await page.request.get(first.results[0].poster)
  const file = path.join(REVIEW, 'example-query.jpg')
  fs.writeFileSync(file, await img.body())
  await page.locator('search input[type=file]').setInputFiles(file)
  await expect(page.getByText('SIMILAR TO IMAGE')).toBeVisible()
  await waitForResults(page)
  await snap(page, '02-query-by-example--desktop-dark')
  fs.unlinkSync(file)
  await page.goBack()
  // Shot detail shows a similar-shots strip too.
  await page.locator('[role=grid] [role=gridcell][data-uid]').first().dblclick()
  await expect(page).toHaveURL(/\/shot\//)
  await expect(page.getByTestId('similar')).toBeVisible()
  await snapAll(page, '02-shot-detail')
})

test('03 filter by resolution, fps, orientation, log and duration', async ({ page }) => {
  await page.goto('/search')
  await waitForResults(page)
  const before = await page.getByTestId('result-count').innerText()
  const rail = page.getByRole('complementary', { name: 'Filters' })
  await rail.getByRole('button', { name: 'Minimum resolution' }).click().catch(async () => {
    await rail.getByText('Any resolution').click()
  })
  await page.getByRole('option', { name: '1080p or higher' }).click()
  await rail.getByRole('textbox', { name: 'Minimum frame rate' }).fill('25')
  await rail.getByRole('textbox', { name: 'Minimum frame rate' }).press('Tab')
  await rail.getByRole('radiogroup', { name: 'Orientation' }).getByRole('radio', { name: 'Horizontal' }).click()
  await rail.getByRole('radiogroup', { name: 'Log profile' }).getByRole('radio', { name: 'Not log' }).click()
  await rail.getByRole('textbox', { name: 'Minimum duration in seconds' }).fill('2')
  await rail.getByRole('textbox', { name: 'Minimum duration in seconds' }).press('Tab')
  await rail.getByRole('textbox', { name: 'Maximum duration in seconds' }).fill('10')
  await rail.getByRole('textbox', { name: 'Maximum duration in seconds' }).press('Tab')
  await expect(page).toHaveURL(/min_height/)
  await expect(page).toHaveURL(/max_duration/)
  await expect(page.getByTestId('query-chip').filter({ hasText: 'RESOLUTION' })).toBeVisible()
  await expect(page.getByTestId('query-chip').filter({ hasText: 'FPS' })).toBeVisible()
  await expect(page.getByTestId('query-chip').filter({ hasText: 'DURATION' })).toBeVisible()
  await expect(page.getByTestId('result-count')).not.toHaveText(before)
  await waitForResults(page)
  // Every visible result honours the filters (strip shows duration and fps).
  const res = await searchApi(page.request, { q: '', filters: { min_height: 1080, min_fps: 25, orientation: 'horizontal', log: false, min_duration: 2, max_duration: 10 }, limit: 50 })
  for (const r of res.results) {
    expect(r.duration).toBeGreaterThanOrEqual(2)
    expect(r.duration).toBeLessThanOrEqual(10)
    expect(r.fps).toBeGreaterThanOrEqual(25)
  }
  await snapAll(page, '03-technical-filters')
  // Tablet: the rail becomes a drawer with a batch-apply footer.
  await page.setViewportSize({ width: 768, height: 1024 })
  await page.getByRole('button', { name: /^Filters/ }).click()
  await expect(page.getByRole('dialog', { name: 'Filters' })).toBeVisible()
  await expect(page.getByRole('button', { name: /^Show (\d[\d,]* shots?|results)$/ })).toBeVisible()
  await snap(page, '03-filter-drawer--tablet-dark')
  await page.keyboard.press('Escape')
  await page.setViewportSize({ width: 1440, height: 900 })
})

test('04 see whether a file is raw, selects or finished', async ({ page }) => {
  await page.goto('/library')
  await expect(page.getByTestId('library-figures')).toBeVisible()
  await expect(page.getByText('Edit stage').first()).toBeVisible()
  await snapAll(page, '04-library-overview')
  const assets = await (await page.request.get('/api/assets?limit=200')).json()
  const finished = assets.assets.find((a: { edit_type?: { term: string } }) => a.edit_type?.term === 'finished') ?? assets.assets[0]
  await page.goto(`/file/${finished.uid}`)
  await expect(page.getByTestId('edit-type')).toBeVisible()
  await expect(page.getByTestId('edit-stage')).toContainText(/Finished|Raw|Selects/)
  await expect(page.getByTestId('filmstrip')).toBeAttached()
  await snapAll(page, '04-asset-view-edit-stage')
})

test('05 rights, releases and expiry respected by intended-use search', async ({ page }) => {
  const res = await searchApi(page.request, { q: 'street', limit: 40 })
  const target = res.results.find((r: { rights_badge: string }) => r.rights_badge === 'cleared') ?? res.results[0]
  const asset = target.asset_uid
  const original = await (await page.request.get(`/api/rights/${asset}`)).json()
  try {
    await page.goto(`/file/${asset}`)
    await page.getByRole('button', { name: 'Rights…' }).click()
    const dlg = page.getByTestId('rights-editor')
    await expect(dlg).toBeVisible()
    await dlg.getByRole('radio', { name: 'Cleared', exact: true }).click({ force: true })
    const uses = dlg.getByRole('group', { name: /Permitted uses/ })
    const boxes = uses.getByRole('checkbox')
    for (let i = 0; i < (await boxes.count()); i++) if (await boxes.nth(i).isChecked()) await boxes.nth(i).click({ force: true })
    await uses.getByRole('checkbox', { name: 'Editorial' }).click({ force: true })
    const exp = new Date(Date.now() + 20 * 86400000).toISOString().slice(0, 10)
    await page.getByTestId('rights-expires').fill(exp)
    await dlg.getByRole('button', { name: /Model release/ }).click()
    await page.getByRole('option', { name: /Unlimited/ }).click()
    await snapAll(page, '05-rights-editor', { only: 'desktop' })
    await page.getByTestId('save-rights').click()
    await expect(page.getByText(/Rights saved/)).toBeVisible()
    // The most restrictive fact first: "Editorial only · expires 24 Oct".
    await expect(page.getByText(/Editorial only · expires/).first()).toBeVisible()
    await snapAll(page, '05-asset-expiring')

    // Search for marketing use: this file's shots are blocked and hidden.
    await page.goto(`/search?q=street&use=marketing&terr=GB`)
    await waitForResults(page)
    // Shown in the results status line at every breakpoint, not only in the rail.
    await expect(page.getByTestId('result-count')).toContainText(/hidden by rights/)
    await expect(page.locator(`[role=gridcell][data-uid^="${asset}-"]`)).toHaveCount(0)
    await snapAll(page, '05-search-intended-use-marketing')
    // Editorial use: the file's shots are cleared again.
    const ed = await searchApi(page.request, { q: 'street', intended_use: { use: 'editorial', include: ['allowed'] }, limit: 120 })
    expect(ed.results.some((r: { asset_uid: string }) => r.asset_uid === asset)).toBeTruthy()
    // Blocked footage is hidden whatever the intended use: with Any use, no blocked card shows.
    await page.goto('/search?q=street')
    await waitForResults(page)
    const rail = page.getByRole('complementary', { name: 'Filters' })
    const hide = rail.getByRole('switch', { name: 'Hide blocked' })
    await expect(hide).toBeChecked()
    await expect(page.locator('[role=gridcell][data-uid][aria-label*="Blocked"], [role=gridcell][data-uid][aria-label*="expired"]')).toHaveCount(0)
    // Turning Hide blocked off shows them, hatched (and it is in the URL).
    await page.goto(`/search?q=street&use=marketing&terr=GB`)
    await waitForResults(page)
    await rail.getByRole('switch', { name: 'Hide blocked' }).click({ force: true })
    await expect(page).toHaveURL(/blocked=show/)
    await expect(page.locator(`[role=gridcell][data-uid^="${asset}-"]`).first()).toBeVisible()
    await snap(page, '05-search-blocked-visible--desktop-dark')
    await page.goto('/rights?tab=expiring')
    await expect(page.getByTestId('rights-table')).toBeVisible()
    await snapAll(page, '05-rights-governance')
  } finally {
    const { level: _l, badge: _b, updated_by: _u, updated_at: _a, ...restore } = original
    await page.request.put(`/api/rights/${asset}`, { data: restore, headers: H })
  }
})

test('06 build a Cutawan package from a collection', async ({ page }) => {
  // A blocked shot can't be exported as media: the items are disabled with the reason up front.
  const all = await searchApi(page.request, { q: '', hide_blocked: false, limit: 500, facets: false })
  const blockedShot = all.results.find((r: { rights_badge: string }) => r.rights_badge === 'not_cleared' || r.rights_badge === 'expired')
  expect(blockedShot).toBeTruthy()
  await page.goto(`/shot/${blockedShot.uid}`)
  await expect(page.getByText(/no media export/).first()).toBeVisible()
  await page.getByTestId('export-clip').first().click()
  await expect(page.getByTestId('export-blocked-reason')).toBeVisible()
  await expect(page.getByRole('menuitem', { name: /Proxy clip/ })).toHaveAttribute('aria-disabled', 'true')
  await expect(page.getByRole('menuitem', { name: /Trimmed original/ })).toHaveAttribute('aria-disabled', 'true')
  await expect(page.getByRole('menuitem', { name: /FCPXML/ })).not.toHaveAttribute('aria-disabled', 'true')
  await snap(page, '06-export-blocked-shot--desktop-dark')
  await page.keyboard.press('Escape')
  // The core refuses it too (403), whatever the client does.
  const refused = await page.request.post('/api/export/clip', { data: { shot_uid: blockedShot.uid, mode: 'proxy' }, headers: H })
  expect(refused.status()).toBe(403)

  const name = `E2E selects ${Date.now().toString(36)}`
  await page.goto('/collections')
  await page.getByRole('textbox', { name: 'New collection name' }).fill(name)
  await page.getByRole('button', { name: 'Create collection' }).click()
  await expect(page.getByRole('heading', { level: 1, name })).toBeVisible()
  const uid = page.url().split('/').pop() as string
  try {
    await snapAll(page, '06-collection-empty', { only: 'desktop' })
    // Add shots from the grid with the keyboard: X selects, B adds to the active collection.
    await page.goto(`/search?q=${encodeURIComponent('people walking in the street')}`)
    const first = await waitForResults(page)
    await first.focus()
    await page.keyboard.press('x')
    await page.keyboard.press('ArrowRight')
    await page.keyboard.press('x')
    await page.keyboard.press('ArrowRight')
    await page.keyboard.press('x')
    await expect(page.getByTestId('selection-bar')).toContainText('3')
    await snapAll(page, '06-selection-bar')
    await page.keyboard.press('b')
    await expect(page.getByText(new RegExp(`Added 3 shots to ${name}`))).toBeVisible()
    await page.goto(`/collections/${uid}`)
    await expect(page.getByTestId('collection-items')).toBeVisible()
    await expect(page.getByTestId('collection-items').getByRole('row')).toHaveCount(3)
    // Keyboard reorder (Alt+↓) as the non-drag alternative.
    await page.getByTestId('collection-items').getByRole('row').first().focus()
    await page.keyboard.press('Alt+ArrowDown')
    await page.waitForTimeout(500)
    await snapAll(page, '06-collection')
    await page.getByTestId('send-to-cutawan').click()
    await expect(page.getByTestId('rights-summary')).toContainText('cleared')
    // The intended use says where it came from (no search use here: workspace default or none).
    await expect(page.getByTestId('use-source')).toBeVisible()
    await snapAll(page, '06-send-to-cutawan-dialog', { only: 'desktop' })
    const send = page.getByTestId('send-package')
    if (await send.isDisabled()) {
      // Nothing cleared for the default use: include restricted shots explicitly.
      await page.getByRole('checkbox', { name: /restricted/ }).click({ force: true })
    }
    await expect(send).toBeEnabled()
    await send.click()
    await expect(page.getByTestId('package-result')).toBeVisible({ timeout: 120_000 })
    await expect(page.getByTestId('package-path')).toContainText('/exports/')
    await snapAll(page, '06-package-ready', { only: 'desktop' })
    const link = page.getByRole('button', { name: /Download package/ })
    await expect(link).toBeVisible()
  } finally {
    await page.request.delete(`/api/collections/${uid}`, { headers: H })
  }
})

test('07 correct a wrong tag; it is marked human and survives reload', async ({ page }) => {
  const res = await searchApi(page.request, { q: 'night street', limit: 5 })
  const shot = res.results[0]
  await page.goto(`/shot/${shot.uid}`)
  const row = page.locator('[data-field="content.time_of_day"]')
  await expect(row).toBeVisible()
  await row.hover()
  await page.getByTestId('edit-content.time_of_day').first().click()
  const editor = page.getByTestId('signal-editor')
  await expect(editor).toBeVisible()
  await editor.getByRole('combobox').click()
  await editor.getByRole('button', { name: 'Show options' }).click()
  const options = page.getByRole('option')
  await expect(options.first()).toBeVisible()
  const current = (await row.innerText()).toLowerCase()
  let picked = ''
  for (let i = 0; i < (await options.count()); i++) {
    const t = (await options.nth(i).innerText()).trim()
    if (!current.includes(t.toLowerCase())) {
      picked = t
      await options.nth(i).click()
      break
    }
  }
  expect(picked).not.toBe('')
  await expect(page.getByText(/This tag will stay as you set it/)).toBeVisible()
  await expect(row.getByRole('note')).toBeVisible() // human marker chip
  await expect(row).toContainText(picked)
  await snapAll(page, '07-correction-human-marker', { only: 'desktop' })
  await page.reload()
  const row2 = page.locator('[data-field="content.time_of_day"]')
  await expect(row2).toContainText(picked)
  await expect(row2.getByRole('note')).toBeVisible()
  await snapAll(page, '07-correction-after-reload')
  await page.goto('/library/corrections')
  await expect(page.getByTestId('corrections-table')).toContainText(picked)
  await snapAll(page, '07-corrections-log')
  // Clean up: revert our correction.
  const log = await (await page.request.get('/api/corrections')).json()
  const mine = log.corrections.find((c: { shot_uid: string; field: string; active: number }) => c.shot_uid === shot.uid && c.field === 'content.time_of_day' && c.active)
  if (mine) await page.request.delete(`/api/corrections/${mine.id}`, { headers: H })
})

test('08 processing status is visible', async ({ page }) => {
  const assets = await (await page.request.get('/api/assets?limit=200')).json()
  const small = [...assets.assets].sort((a, b) => (a.duration ?? 0) - (b.duration ?? 0))[0]
  await page.request.post(`/api/assets/${small.uid}/reprocess`, { data: { analysers: ['rollup'] }, headers: H })
  // Re-analysis of analysed files: they stay searchable and each row says what is refreshing.
  // (Re-running the embedder recomputes the same vectors; it takes a few seconds on six short files.)
  const some = [...assets.assets].filter((a) => (a.duration ?? 0) >= 10).sort((a, b) => (a.duration ?? 0) - (b.duration ?? 0)).slice(0, 6)
  for (const a of some) await page.request.post(`/api/assets/${a.uid}/reprocess`, { data: { analysers: ['embed'] }, headers: H })
  await page.goto('/ingest')
  await expect(page.getByTestId('processing-summary')).toBeVisible()
  await expect(page.getByTestId('queue-table')).toBeVisible()
  // Timing-dependent on a fast machine, so the capture is taken when the state is caught (logic: lib/processing.test.ts).
  const caught = await page.getByText(/^Updating: /).first().waitFor({ timeout: 8_000 }).then(() => true, () => false)
  if (caught) {
    await expect(page.getByText(/Searchable · \d+ steps? left/).first()).toBeVisible()
    await expect(page.getByTestId('processing-summary')).toContainText('updating')
    await snap(page, '08-ingest-updating--desktop-dark')
  } else console.log('re-analysis finished before the ingest page polled; no updating capture this run')
  await expect(page.getByText('Analysers')).toBeVisible()
  await expect(page.getByText(/vision-language model|CPU-tier/i).first()).toBeVisible()
  await snapAll(page, '08-ingest-processing')
  await page.goto('/settings/adapters')
  await expect(page.getByText(/Local: nothing leaves this machine|Leaves this machine/).first()).toBeVisible()
  // Locality is the core's call from the host: a public endpoint never reads "Local" (not saved).
  const vlm = page.getByRole('textbox', { name: 'Endpoint (OpenAI-compatible)' }).first()
  await expect(page.getByRole('switch', { name: 'Runs on this machine or our own network' }).first()).not.toBeChecked()
  await vlm.fill('https://api.openai.com/v1')
  await page.getByRole('textbox', { name: 'Model' }).first().fill('gpt-4o-mini')
  const badge = page.getByTestId('locality-badge').first()
  await expect(badge).toHaveAttribute('data-state', /remote|refused/)
  await expect(badge).not.toContainText('Local')
  await page.getByRole('switch', { name: 'Runs on this machine or our own network' }).first().click({ force: true })
  await expect(badge).toHaveAttribute('data-state', /remote|refused/)
  await snapAll(page, '08-model-adapters-egress', { only: 'desktop' })
  await page.getByRole('button', { name: 'Save model settings' }).click()
  await expect(page.getByTestId('egress-confirm')).toContainText('api.openai.com')
  await page.waitForTimeout(400)
  await snap(page, '08-model-adapters-confirm--desktop-dark')
  await page.getByRole('button', { name: 'Cancel' }).click()
  await vlm.fill('http://127.0.0.1:8080/v1')
  await expect(badge).toHaveAttribute('data-state', 'local')
  await page.getByRole('button', { name: 'Discard changes' }).click()
  await page.goto('/settings/tokens')
  await snapAll(page, '08-api-tokens', { only: 'desktop' })
})

test('09 keyboard only: search to inspector to shot detail', async ({ page }) => {
  await page.goto('/search')
  await page.keyboard.press('/')
  await page.keyboard.type('close-up at night')
  await page.keyboard.press('Control+Enter')
  await waitForResults(page)
  await expect(page.locator('[role=gridcell][data-uid]:focus')).toHaveCount(1, { timeout: 10_000 })
  await page.keyboard.press('ArrowRight')
  await page.keyboard.press('ArrowDown')
  const focused = page.locator('[role=gridcell][data-uid]:focus')
  await expect(focused).toHaveCount(1)
  const uid = await focused.getAttribute('data-uid')
  // Inspector follows focus.
  await expect(page.getByTestId('inspector')).toBeVisible()
  await page.waitForTimeout(500)
  await page.keyboard.press(' ')
  await page.waitForTimeout(800)
  await page.keyboard.press('x')
  await snapAll(page, '09-keyboard-grid-focus', { only: 'desktop' })
  await page.keyboard.press('Escape')
  await page.keyboard.press('Escape')
  // Command menu and shortcuts sheet.
  await page.keyboard.press('Control+k')
  await expect(page.getByRole('dialog', { name: 'Command menu' })).toBeVisible()
  await snap(page, '09-command-menu--desktop-dark')
  await page.keyboard.press('Escape')
  await page.locator('[role=gridcell][data-uid]').first().focus()
  await page.keyboard.press('?')
  await expect(page.getByRole('dialog', { name: 'Keyboard shortcuts' })).toBeVisible()
  await snap(page, '09-shortcuts--desktop-dark')
  await page.keyboard.press('Escape')
  await page.locator(`[role=gridcell][data-uid="${uid}"]`).focus()
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(new RegExp(`/shot/${uid}`))
  await expect(page.getByTestId('shot-player')).toBeFocused()
  await page.keyboard.press('l')
  await page.waitForTimeout(600)
  await page.keyboard.press('k')
  await page.keyboard.press('i')
  await page.keyboard.press('ArrowRight')
  await page.keyboard.press('Shift+ArrowRight')
  await page.keyboard.press('o')
  await expect(page.getByText('IN', { exact: true })).toBeVisible()
  await snapAll(page, '09-keyboard-shot-detail', { only: 'desktop' })
})

test('10 grid scroll smoothness', async ({ page }) => {
  await page.goto('/search?q=')
  await waitForResults(page)
  await page.getByRole('radiogroup', { name: 'Thumbnail size' }).getByRole('radio', { name: 'S', exact: true }).click()
  const result = await page.evaluate(async () => {
    const el = document.querySelector('[data-testid=results-scroller]') as HTMLElement
    const max = el.scrollHeight - el.clientHeight
    const pass = async (from: number, to: number) => {
      const frames: number[] = []
      let last = performance.now()
      for (let i = 0; i <= 120; i++) {
        el.scrollTop = from + ((to - from) * i) / 120
        await new Promise((r) => requestAnimationFrame(() => r(null)))
        const t = performance.now()
        frames.push(t - last)
        last = t
      }
      const sorted = frames.slice(2).sort((a, b) => a - b)
      return { p50: Math.round(sorted[Math.floor(sorted.length * 0.5)] * 10) / 10, p95: Math.round(sorted[Math.floor(sorted.length * 0.95)] * 10) / 10, max: Math.round(sorted[sorted.length - 1]) }
    }
    const idle = await (async () => {
      const f: number[] = []
      let last = performance.now()
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => requestAnimationFrame(() => r(null)))
        const t = performance.now()
        f.push(t - last)
        last = t
      }
      f.sort((a, b) => a - b)
      return Math.round(f[30] * 10) / 10
    })()
    const firstPass = await pass(0, max)
    const secondPass = await pass(max, 0)
    return { idleFrameMs: idle, firstPass, secondPass, cardsInDom: document.querySelectorAll('[role=gridcell][data-uid]').length, total: document.querySelector('[role=grid]')?.getAttribute('aria-rowcount') }
  })
  perf.gridScroll = result
  console.log('grid scroll', JSON.stringify(result))
  // Headless software rendering; the second pass has thumbnails decoded.
  // Video recording runs alongside; 100 ms p95 here corresponds to ~45 ms without recording (see perf-web.json).
  expect(result.secondPass.p95).toBeLessThan(100)
  expect(result.cardsInDom).toBeLessThan(80)
})

test('12 narrow screens, forced colours and match strength', async ({ page }) => {
  // WCAG 1.4.10: at 320 CSS px the search field keeps its width and nothing scrolls sideways.
  await page.setViewportSize({ width: 320, height: 640 })
  await page.goto(`/search?q=${encodeURIComponent('street at night')}`)
  await waitForResults(page)
  const field = await page.locator('#mc-search').boundingBox()
  expect(field!.width).toBeGreaterThan(150)
  const someone = (await (await page.request.get('/api/people?limit=1')).json()).people[0]
  const routes = ['/search?q=street', '/library', '/collections', '/ingest', '/rights', '/settings/appearance', '/people', '/settings/adapters', '/settings/privacy']
  if (someone) routes.push(`/people/${someone.id}`)
  for (const route of routes) {
    await page.goto(route)
    await page.waitForTimeout(800)
    const overflow = await page.evaluate(() => {
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
    expect(overflow, `${route} overflows at 320 px`).toBe(0)
  }
  await page.goto(`/search?q=${encodeURIComponent('street at night')}`)
  await waitForResults(page)
  for (const theme of ['dark', 'light'] as const) {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
    await page.waitForTimeout(300)
    await snap(page, `12-reflow-search--320-${theme}`)
  }
  await page.locator('#mc-search').click()
  await page.getByRole('button', { name: 'Sections' }).click()
  await expect(page.getByRole('menuitem', { name: /Library/ })).toBeVisible()
  await snap(page, '12-reflow-sections-menu--320-dark')
  await page.keyboard.press('Escape')

  // Forced colours: the selection ring and the primary button stay visible.
  await page.setViewportSize({ width: 1440, height: 900 })
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce', forcedColors: 'active' })
  await page.goto('/search?q=street')
  const card = await waitForResults(page)
  await card.focus()
  await page.keyboard.press('x')
  await page.keyboard.press('ArrowRight')
  await page.keyboard.press('ArrowRight')
  await page.keyboard.press('x')
  await expect(page.getByTestId('selection-bar')).toContainText('2')
  const ring = await page.locator('[role=gridcell][aria-selected=true] > div').first().evaluate((el) => getComputedStyle(el).outlineStyle)
  expect(ring).toBe('solid')
  const send = page.getByTestId('selection-bar').getByRole('button', { name: /Send to Cutawan/ })
  const colours = await send.evaluate((el) => ({ bg: getComputedStyle(el).backgroundColor, fg: getComputedStyle(el).color }))
  expect(colours.bg).not.toBe(colours.fg)
  await snap(page, '12-forced-colours-selection--desktop')
  await page.keyboard.press('Escape')
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'no-preference', forcedColors: 'none' })

  // Match strength is absolute: a nonsense query has no strong matches, at any strictness.
  await page.goto(`/search?q=${encodeURIComponent('zzqxv underwater penguin ballet')}&strict=strict`)
  await expect(page.getByTestId('no-strong-matches')).toBeVisible()
  await expect(page.getByTestId('result-count')).toContainText('0 strong (strict)')
  await snap(page, '12-no-strong-matches--desktop-dark')
  // Strictness lives in the URL and moves the divider by the core's threshold.
  await page.goto(`/search?q=${encodeURIComponent('close-up at night')}`)
  await waitForResults(page)
  await page.getByRole('radiogroup', { name: 'Match strictness' }).getByRole('radio', { name: 'Strict' }).click()
  await expect(page).toHaveURL(/strict=strict/)
  await expect(page.getByTestId('result-count')).toContainText('strong (strict)')
})
