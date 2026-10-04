/**
 * Journey 15: search inside a folder or a collection ("use my Disney holiday videos").
 * Library → Folders → Search this folder; folder:"…" written in the words; a folder that doesn't exist
 * (the core's note, one-click closest); a temporary collection with two shots → Search in this collection
 * (deleted afterwards); the command menu; tablet drawer and 320 px reflow.
 */
import fs from 'node:fs'
import path from 'node:path'
import type { Page, Response } from '@playwright/test'
import { expect, H, SCREENS, snap, snapAll, test, waitForResults } from './helpers'

interface Result {
  uid: string
  folder: string
}

/** The search page's own results request (a page of 120 with facets), matching `pred` on its body. */
function searchResponse(page: Page, pred: (body: Record<string, unknown>) => boolean): Promise<Response> {
  return page.waitForResponse((r) => {
    if (!r.url().endsWith('/api/search') || r.request().method() !== 'POST') return false
    const body = r.request().postDataJSON() as Record<string, unknown>
    return body.limit === 120 && body.facets === true && pred(body)
  })
}

const inside = (folder: string, root: string) => folder === root || folder.startsWith(`${root}/`)

/** WCAG 1.4.10: nothing but clipped content reaches past the viewport. */
async function overflowAt(page: Page): Promise<number> {
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

async function snap320(page: Page, name: string) {
  const original = page.viewportSize() ?? { width: 1440, height: 900 }
  await page.setViewportSize({ width: 320, height: 640 })
  await page.waitForTimeout(500)
  expect(await overflowAt(page), `${name} overflows at 320 px`).toBe(0)
  for (const theme of ['dark', 'light'] as const) {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
    await page.waitForTimeout(300)
    await page.screenshot({ path: path.join(SCREENS, `${name}--320-${theme}.jpg`), type: 'jpeg', quality: 85 })
  }
  await page.setViewportSize(original)
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'no-preference' })
}

test('15 search inside a folder or a collection', async ({ page }) => {
  const folders = (await (await page.request.get('/api/folders')).json()).folders as { path: string; name: string; files: number }[]
  const sample = folders.find((f) => f.name === 'sample')
  const extra = folders.find((f) => f.name === 'extra')
  expect(sample, 'the demo library has a "sample" folder').toBeTruthy()
  expect(extra, 'the demo library has an "extra" folder').toBeTruthy()

  // Library → Folders: files, length, shoot dates and edit stages per folder.
  await page.goto('/library')
  await page.getByRole('navigation', { name: 'Library' }).getByRole('link', { name: 'Folders' }).click()
  await expect(page).toHaveURL(/\/library\/folders/)
  const row = page.getByTestId('folder-row').filter({ has: page.getByRole('heading', { name: 'sample', exact: true }) })
  await expect(row).toContainText(`${sample!.files}`)
  await expect(row.getByTestId('folder-stages')).not.toHaveText('…')
  await snapAll(page, '15-library-folders')
  await snap320(page, '15-library-folders')

  // Show files: the folder's files from /api/assets?folder=.
  await row.getByRole('button', { name: /Show files in sample/ }).click()
  const files = row.getByTestId('folder-files')
  await expect(files.getByRole('row')).toHaveCount(sample!.files + 1)
  await expect(page).toHaveURL(/open=/)
  await snapAll(page, '15-folder-files', { only: 'desktop' })

  // Search this folder: every result is from the folder, the scope chip shows, the words are focused.
  const scoped = searchResponse(page, (b) => JSON.stringify((b.filters as Record<string, unknown> | undefined)?.folder ?? '').includes(sample!.path))
  await row.getByRole('button', { name: /Search this folder: sample/ }).click()
  const res = await (await scoped).json()
  await expect(page).toHaveURL(/\/search\?.*folder=/)
  expect(res.total).toBeGreaterThan(0)
  for (const r of res.results as Result[]) expect(inside(r.folder, sample!.path), `${r.uid} is in ${r.folder}`).toBe(true)
  await waitForResults(page)
  const chip = page.getByTestId('scope-chip')
  await expect(chip).toHaveCount(1)
  await expect(chip).toContainText('In')
  await expect(chip).toContainText('sample')
  await expect(page.getByTestId('result-count')).toContainText(`${res.total} shot${res.total === 1 ? '' : 's'} in sample`)
  await expect(page.locator('#mc-search')).toBeFocused()
  await expect(page.getByTestId('scope-trigger')).toContainText('In sample')
  // The inspector shows the shot's folder as a breadcrumb.
  await page.locator('[role=grid] [role=gridcell][data-uid]').first().click()
  await expect(page.getByRole('complementary', { name: 'Shot details' }).getByTestId('folder-crumbs')).toContainText('sample')
  await snapAll(page, '15-search-in-folder')
  await snap320(page, '15-search-in-folder')

  // The scope control: Everything / a folder (searchable tree) / a collection.
  await page.getByTestId('scope-trigger').click()
  const picker = page.getByRole('dialog', { name: 'Search scope' })
  await expect(picker.getByRole('treegrid', { name: 'Folders' })).toBeVisible()
  await expect(picker.getByRole('row', { name: /extra/ })).toContainText('files')
  await page.waitForTimeout(400)
  await snapAll(page, '15-scope-picker', { only: 'desktop' })
  await page.keyboard.press('Escape')
  // Tablet: the same control at the top of the filter drawer.
  await page.setViewportSize({ width: 768, height: 1024 })
  await page.getByRole('button', { name: /^Filters/ }).click()
  const drawer = page.getByRole('dialog', { name: 'Filters' })
  await expect(drawer.getByTestId('scope-trigger')).toContainText('In sample')
  await page.waitForTimeout(400)
  for (const theme of ['dark', 'light'] as const) {
    await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
    await page.waitForTimeout(300)
    await snap(page, `15-scope-drawer--tablet-${theme}`)
  }
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'no-preference' })
  await page.keyboard.press('Escape')
  await page.setViewportSize({ width: 1440, height: 900 })

  // Find similar keeps the scope: similar shots only from sample (POST /api/search with similar_to + filters).
  const similar = searchResponse(page, (b) => Boolean(b.similar_to) && JSON.stringify(b.filters ?? '').includes(sample!.path))
  await page.getByRole('complementary', { name: 'Shot details' }).getByRole('button', { name: /Find similar/ }).click()
  const simRes = await (await similar).json()
  await expect(page).toHaveURL(/similar=.*folder=|folder=.*similar=/)
  for (const r of simRes.results as Result[]) expect(inside(r.folder, sample!.path)).toBe(true)
  await expect(page.getByTestId('scope-chip')).toContainText('sample')
  // So does query by example (POST /api/similar?folder=…).
  const poster = await page.request.get((simRes.results as { poster: string }[])[0].poster)
  const file = path.join(SCREENS, '..', 'example-scope.jpg')
  fs.writeFileSync(file, await poster.body())
  const byExample = page.waitForResponse((r) => r.url().includes('/api/similar?') && r.request().method() === 'POST')
  await page.locator('search input[type=file]').setInputFiles(file)
  const exRes = await byExample
  expect(new URL(exRes.url()).searchParams.getAll('folder')).toEqual([sample!.path])
  for (const r of (await exRes.json()).results as Result[]) expect(inside(r.folder, sample!.path)).toBe(true)
  await expect(page.getByText('SIMILAR TO IMAGE')).toBeVisible()
  await expect(page.getByTestId('result-count')).toContainText('in sample')
  fs.rmSync(file, { force: true })

  // Written in the words: folder:"extra" night → a scope chip from the words, results from extra only.
  await page.goto('/search')
  const typed = searchResponse(page, (b) => String(b.q ?? '').includes('folder:"extra"'))
  await page.locator('#mc-search').click()
  await page.keyboard.type('folder:"extra" night', { delay: 15 })
  await page.keyboard.press('Enter')
  const typedRes = await (await typed).json()
  expect(typedRes.query.filters.folder).toEqual(['extra'])
  expect(typedRes.total).toBeGreaterThan(0)
  for (const r of typedRes.results as Result[]) expect(inside(r.folder, extra!.path)).toBe(true)
  await waitForResults(page)
  await expect(page.getByTestId('scope-chip')).toContainText('extra')
  await expect(page.getByTestId('result-count')).toContainText('in extra')
  await expect(page.getByText(/From your words: In extra/)).toBeVisible()
  await snapAll(page, '15-typed-folder', { only: 'desktop' })
  // Removing the chip edits the words.
  await page.getByTestId('scope-chip').getByRole('button', { name: /Remove scope extra/ }).click()
  await expect(page.locator('#mc-search')).toHaveValue('night')
  await expect(page.getByTestId('scope-chip')).toHaveCount(0)

  // A folder that doesn't exist: the core's note, and the closest folder as a one-click fix.
  await page.goto('/search?folder=samples')
  await expect(page.getByTestId('scope-note')).toContainText('sample')
  await expect(page.getByRole('heading', { name: 'No folder called “samples”' })).toBeVisible()
  await snapAll(page, '15-folder-not-found', { only: 'desktop' })
  await page.getByTestId('scope-fix').first().click()
  await expect(page).toHaveURL(/folder=sample(&|$)/)
  await waitForResults(page)
  await expect(page.getByTestId('scope-chip')).toContainText('sample')
  await page.goto(`/search?folder=${encodeURIComponent('Disney 2025')}`)
  await expect(page.getByRole('heading', { name: 'No folder called “Disney 2025”' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Search every folder' })).toBeVisible()

  // Command menu → Search in folder… → extra.
  await page.goto('/library')
  await page.keyboard.press('Control+k')
  await page.keyboard.type('Search in folder')
  await page.keyboard.press('Enter')
  const dlg = page.getByRole('dialog', { name: 'Search in a folder' })
  await expect(dlg).toBeVisible()
  await page.waitForTimeout(400)
  await snap(page, '15-command-search-in-folder--desktop-dark')
  await dlg.getByRole('row', { name: /^extra/ }).click()
  await expect(page).toHaveURL(/\/search\?.*folder=/)
  await expect(page.getByTestId('scope-chip')).toContainText('extra')

  // Ingest → sources: Search this folder / Show files.
  await page.goto('/ingest')
  await expect(page.getByRole('button', { name: /Search this folder/ }).first()).toBeVisible()
  await snapAll(page, '15-ingest-sources', { only: 'desktop' })

  // A temporary collection with two shots → Search in this collection → exactly those shots.
  const pool = await (await page.request.post('/api/search', { data: { q: '', filters: { folder: extra!.path }, limit: 2, facets: false }, headers: H })).json()
  const two = (pool.results as Result[]).map((r) => r.uid)
  expect(two).toHaveLength(2)
  const name = `E2E scope ${Date.now().toString(36)}`
  const created = await (await page.request.post('/api/collections', { data: { name, shot_uids: two }, headers: H })).json()
  try {
    await page.goto(`/collections/${created.uid}`)
    await expect(page.getByRole('heading', { level: 1, name })).toBeVisible()
    await snapAll(page, '15-collection-search-action', { only: 'desktop' })
    const inCol = searchResponse(page, (b) => JSON.stringify((b.filters as Record<string, unknown> | undefined)?.collection ?? '').includes(created.uid))
    await page.getByTestId('search-in-collection').click()
    const colRes = await (await inCol).json()
    expect(colRes.total).toBe(2)
    expect((colRes.results as Result[]).map((r) => r.uid).sort()).toEqual([...two].sort())
    await waitForResults(page)
    await expect(page.getByTestId('scope-chip')).toContainText('In collection:')
    await expect(page.getByTestId('scope-chip')).toContainText(name)
    await expect(page.getByTestId('result-count')).toContainText(`2 shots in collection ${name}`)
    await expect(page.locator('#mc-search')).toBeFocused()
    await snapAll(page, '15-search-in-collection', { only: 'desktop' })
  } finally {
    await page.request.delete(`/api/collections/${created.uid}`, { headers: H })
  }
  const after = await (await page.request.get('/api/collections')).json()
  expect((after.collections as { uid: string }[]).some((c) => c.uid === created.uid)).toBe(false)
})
