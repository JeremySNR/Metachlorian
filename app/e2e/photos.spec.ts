import { test, expect } from '@playwright/test'

// Run against an expendable local core with PHOTO_E2E_FOLDER pointing to
// three synthetic JPEGs (family-wide.jpg, portrait.jpg, travel.jpg).
test('photo folder to search, comparison and inspector', async ({ page, request }) => {
  const folder = process.env.PHOTO_E2E_FOLDER
  test.skip(!folder, 'Needs the documented synthetic photo fixture and a disposable core')
  const failures: string[] = []
  page.on('pageerror', (error) => failures.push(error.message))
  await page.goto('/photos')
  const enable = page.getByRole('button', { name: 'Enable Photos', exact: true })
  const status = await (await request.get('/api/photos/status')).json()
  if (!status.enabled) await enable.click()
  await expect(page.getByText('Sources and Lightroom setup', { exact: true })).toBeVisible()
  if (!(await page.getByLabel('Folder on this computer').isVisible())) await page.getByText('Sources and Lightroom setup', { exact: true }).click()
  await page.getByLabel('Folder on this computer').fill(folder!)
  await page.getByRole('button', { name: 'Index folder', exact: true }).click()
  await expect.poll(async () => (await (await request.get('/api/photos/status')).json()).counts.ready ?? 0).toBe(3)
  await expect(page.getByRole('button', { name: 'Inspect family-wide.jpg', exact: true })).toBeVisible()
  // React Aria visually clips its native input. Exercise keyboard access.
  await page.getByRole('checkbox', { name: 'Select family-wide.jpg', exact: true }).press('Space')
  await page.getByRole('checkbox', { name: 'Select portrait.jpg', exact: true }).press('Space')
  await page.getByRole('button', { name: 'Compare up to four' }).click()
  await expect(page.getByRole('button', { name: 'Inspect travel.jpg', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: 'Inspect portrait.jpg', exact: true }).click()
  const inspector = page.getByRole('complementary', { name: 'Photograph details' })
  await expect(inspector.getByRole('heading', { name: 'portrait.jpg' })).toBeVisible()
  await expect(inspector.getByText('400 × 600')).toBeVisible()
  const image = inspector.getByRole('img', { name: 'portrait.jpg', exact: true })
  await expect(image).toBeVisible()
  expect(await image.evaluate((img) => (img as HTMLImageElement).naturalWidth)).toBe(400)
  await expect(page.getByRole('button', { name: 'Prepare virtual copies' })).toBeDisabled()
  await page.getByRole('button', { name: 'Clear selection' }).click()
  await page.getByLabel('Find photographs', { exact: true }).fill('travel')
  await page.getByRole('button', { name: 'Find photos', exact: true }).click()
  await expect(page.getByRole('button', { name: 'Inspect travel.jpg', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Inspect family-wide.jpg', exact: true })).toHaveCount(0)
  await page.setViewportSize({ width: 768, height: 1024 })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  expect(failures).toEqual([])
})
