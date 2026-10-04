import { test as base, expect, type Page, type APIRequestContext } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

export const REVIEW = path.resolve(process.cwd(), '..', 'review', 'm4')
export const SCREENS = path.join(REVIEW, 'screens')
export const VIDEOS = path.join(REVIEW, 'video')
fs.mkdirSync(SCREENS, { recursive: true })
fs.mkdirSync(VIDEOS, { recursive: true })

export const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'laptop', width: 1024, height: 768 },
  { name: 'tablet', width: 768, height: 1024 },
] as const

/** Screenshot the current state at every viewport in light and dark, then restore. */
export async function snapAll(page: Page, name: string, opts: { only?: 'desktop'; settle?: () => Promise<void> } = {}) {
  const original = page.viewportSize() ?? { width: 1440, height: 900 }
  for (const vp of VIEWPORTS) {
    if (opts.only && vp.name !== opts.only) continue
    await page.setViewportSize({ width: vp.width, height: vp.height })
    for (const theme of ['dark', 'light'] as const) {
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' })
      await page.waitForTimeout(350)
      if (opts.settle) await opts.settle()
      await page.screenshot({ path: path.join(SCREENS, `${name}--${vp.name}-${theme}.jpg`), type: 'jpeg', quality: 85 })
    }
  }
  await page.setViewportSize(original)
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'no-preference' })
  await page.waitForTimeout(200)
}

/** Single screenshot (desktop, current theme). */
export async function snap(page: Page, name: string) {
  await page.screenshot({ path: path.join(SCREENS, `${name}.jpg`), type: 'jpeg', quality: 85 })
}

export const H = { 'X-Metachlorian': '1' }

export async function searchApi(request: APIRequestContext, body: Record<string, unknown>) {
  const r = await request.post('/api/search', { data: body, headers: H })
  expect(r.ok()).toBeTruthy()
  return r.json()
}

export const test = base.extend<{ journey: string }>({
  journey: ['', { option: true }],
  page: async ({ page }, use, testInfo) => {
    // Start each journey with a clean UI state (prefs, recent searches).
    await page.addInitScript(() => {
      if (!sessionStorage.getItem('mc.e2e')) {
        localStorage.clear()
        sessionStorage.setItem('mc.e2e', '1')
      }
    })
    await use(page)
    const video = page.video()
    await page.close()
    if (video) {
      const slug = testInfo.title.replace(/[^a-z0-9]+/gi, '-').replace(/^-|-$/g, '').toLowerCase()
      await video.saveAs(path.join(VIDEOS, `${slug}.webm`)).catch(() => undefined)
    }
  },
})

export { expect }

/** Wait for result cards with loaded thumbnails. */
export async function waitForResults(page: Page) {
  const card = page.locator('[role=grid] [role=gridcell][data-uid]').first()
  await expect(card).toBeVisible()
  await page.waitForFunction(() => {
    const imgs = Array.from(document.querySelectorAll<HTMLImageElement>('[role=gridcell][data-uid] img')).slice(0, 6)
    return imgs.length > 0 && imgs.every((i) => i.complete && i.naturalWidth > 0)
  })
  return card
}
