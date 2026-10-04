/**
 * Preview start latency (system.md §6: Space / dwell → first frame ≤ 300 ms).
 * Playwright's bundled Chromium has no H.264, so this runs in Electron (the
 * desktop target) under xvfb, loading the same web UI from the core.
 */
import { _electron as electron, expect, test } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'
import { REVIEW, SCREENS, VIDEOS } from './helpers'

const ELECTRON = process.env.ELECTRON_PATH ?? path.resolve(process.cwd(), '../desktop/node_modules/electron/dist/electron')

test('11 preview starts in under 300 ms (Electron, H.264)', async () => {
  test.skip(!fs.existsSync(ELECTRON), 'Electron binary not found (set ELECTRON_PATH)')
  const app = await electron.launch({
    executablePath: ELECTRON,
    args: [path.resolve(process.cwd(), 'e2e/electron/main.cjs'), '--no-sandbox', '--disable-gpu'],
    env: { ...process.env, BASE_URL: process.env.BASE_URL ?? 'http://127.0.0.1:8770' },
    recordVideo: { dir: path.join(process.cwd(), 'test-results', 'electron-video'), size: { width: 1440, height: 900 } },
  })
  const page = await app.firstWindow()
  await page.setViewportSize({ width: 1440, height: 900 }).catch(() => undefined)
  const cards = page.locator('[role=grid] [role=gridcell][data-uid]')
  await expect(cards.first()).toBeVisible({ timeout: 30_000 })
  await page.waitForTimeout(1500)

  // Keyboard: focus rest then Space, eight shots.
  for (let i = 0; i < 8; i++) {
    await cards.nth(i).focus()
    await page.waitForTimeout(400)
    await page.keyboard.press(' ')
    await page.waitForTimeout(900)
    if (i === 2) await page.screenshot({ path: path.join(SCREENS, '11-electron-space-preview--desktop-dark.jpg'), type: 'jpeg', quality: 85 })
    await page.keyboard.press(' ')
  }
  // Pointer: hover intent, then rest (dwell) on three cards.
  for (let i = 8; i < 11; i++) {
    const box = await cards.nth(i).locator('div').first().boundingBox()
    if (!box) continue
    await page.mouse.move(box.x + 8, box.y + box.height / 2)
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2, { steps: 5 })
    await page.waitForTimeout(1200)
    if (i === 9) await page.screenshot({ path: path.join(SCREENS, '11-electron-dwell-preview--desktop-dark.jpg'), type: 'jpeg', quality: 85 })
    await page.mouse.move(2, 2)
    await page.waitForTimeout(200)
  }
  const starts: number[] = await page.evaluate(() => window.__mcPerf?.previewStarts ?? [])
  const videos = await page.locator('video').count()
  const sorted = [...starts].sort((a, b) => a - b)
  const result = { samples: starts, median: sorted[Math.floor(sorted.length / 2)], p90: sorted[Math.floor(sorted.length * 0.9)], max: sorted[sorted.length - 1], videoElements: videos }
  fs.writeFileSync(path.join(REVIEW, 'perf-electron.json'), JSON.stringify(result, null, 2))
  console.log('preview start (Electron):', JSON.stringify(result))
  const video = page.video()
  await app.close()
  if (video) await video.saveAs(path.join(VIDEOS, '11-electron-preview-latency.webm')).catch(() => undefined)
  expect(starts.length).toBeGreaterThanOrEqual(6)
  expect(result.median).toBeLessThan(300)
  expect(videos).toBeLessThanOrEqual(5)
})
