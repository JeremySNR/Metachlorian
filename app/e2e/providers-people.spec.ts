/**
 * Journeys 13 (hosted model providers) and 14 (people: face identity).
 * Nothing hosted is ever saved here (there are no real keys); the fake key is removed afterwards; the
 * named person is unnamed again; the merged face is split out again; nobody is forgotten.
 */
import type { APIRequestContext } from '@playwright/test'
import { expect, H, snap, snapAll, test, waitForResults } from './helpers'

const FAKE_KEY = 'sk-test-metachlorian-0000abcd'

test('13 hosted model providers: what each unlocks and costs, what leaves, write-only keys', async ({ page }) => {
  const before = await (await page.request.get('/api/admin/providers')).json()
  expect(before.active).toEqual({ vlm: 'custom', llm: 'custom' })
  try {
    await page.goto('/settings/adapters')
    await expect(page.getByTestId('status-vlm')).toContainText('CPU tier')
    await expect(page.getByTestId('status-queue')).toBeVisible()
    await expect(page.getByRole('radiogroup', { name: 'Provider for captions and labels' })).toBeVisible()
    await snapAll(page, '13-model-providers')

    // OpenAI: hosted means "Leaves this machine", with exactly what is sent and what never is.
    await page.getByTestId('provider-vlm-openai').click()
    await expect(page.getByRole('radio', { name: /OpenAI/ })).toBeChecked()
    const privacy = page.getByTestId('privacy-vlm')
    await expect(privacy).toContainText('Leaves this machine')
    await expect(privacy).toContainText('contact-sheet')
    await expect(privacy).toContainText('Face crops and face embeddings')
    await expect(page.getByTestId('details-vlm')).toContainText('Billed per request')
    await expect(page.getByTestId('llm-follows')).toContainText('OpenAI')

    // A key is write-only: stored, shown masked with where it came from, never echoed back.
    const keyField = page.getByRole('textbox', { name: 'OpenAI API key' })
    await expect(keyField).toHaveAttribute('type', 'password')
    await keyField.fill(FAKE_KEY)
    await page.getByRole('button', { name: 'Save key' }).click()
    const state = page.getByTestId('key-state')
    await expect(state).toContainText('Key saved')
    await expect(state).toContainText('sk-te…abcd')
    await expect(state).toContainText('stored in this library')
    await expect(keyField).toHaveValue('')
    expect(await page.content()).not.toContain(FAKE_KEY)
    const keyStatus = await (await page.request.get('/api/admin/providers')).json()
    expect(JSON.stringify(keyStatus)).not.toContain(FAKE_KEY)
    await snapAll(page, '13-provider-openai-key', { only: 'desktop' })

    // Saving a hosted provider asks first (§3.20). Cancelled: nothing hosted is saved.
    await page.getByRole('button', { name: 'Save model settings' }).click()
    const confirm = page.getByTestId('egress-confirm')
    await expect(confirm).toContainText('will be sent to OpenAI (api.openai.com)')
    await expect(confirm).toContainText('Never sent: footage files and audio, face crops and face embeddings')
    await expect(page.getByRole('button', { name: 'Turn on and send frames' })).toBeVisible()
    await page.waitForTimeout(400)
    await snap(page, '13-provider-confirm--desktop-dark')
    await page.getByRole('button', { name: 'Cancel' }).click()
    const after = await (await page.request.get('/api/admin/providers')).json()
    expect(after.active).toEqual({ vlm: 'custom', llm: 'custom' })
    expect(after.allow_remote).toBe(false)
    await expect(page.getByTestId('egress')).toContainText('Local')

    // Remove clears the stored key.
    await page.getByRole('button', { name: 'Remove key' }).click()
    await expect(state).toContainText('No OpenAI key yet')

    // OpenRouter: model picker with vision filter and prices, or the offline fallback (the core answers 502 here).
    await page.getByTestId('provider-vlm-openrouter').click()
    await expect(page.getByTestId('openrouter-offline').or(page.getByRole('listbox', { name: 'OpenRouter models' }))).toBeVisible()
    await expect(page.getByRole('textbox', { name: 'Model' }).first()).toHaveValue(/gpt|\//)
    await snap(page, '13-provider-openrouter--desktop-dark')

    // ChatGPT via Codex: setup state and the two commands, daily cap.
    await page.getByTestId('provider-vlm-codex').click()
    const codex = page.getByTestId('codex-setup')
    await expect(codex).toContainText('npm i -g @openai/codex')
    await expect(codex).toContainText('codex login')
    await expect(codex).toContainText(/not found|not signed in|signed in/i)
    await expect(page.getByTestId('details-vlm')).toContainText('requests a day')
    await snapAll(page, '13-provider-codex', { only: 'desktop' })

    // A different provider for summaries (advanced).
    await page.getByText('Use a different provider for summaries').click()
    await expect(page.getByRole('radiogroup', { name: 'Provider for summaries' })).toBeVisible()
    await page.getByTestId('provider-llm-custom').click()
    await snap(page, '13-provider-separate-summaries--desktop-dark')
    await page.getByRole('button', { name: 'Discard changes' }).click()
    await expect(page.getByRole('radio', { name: /^Local/ }).first()).toBeChecked()

    // Narrow: the provider chooser stacks at 320 px.
    await page.setViewportSize({ width: 320, height: 640 })
    await page.goto('/settings/adapters')
    await expect(page.getByTestId('status-vlm')).toBeVisible()
    await page.waitForTimeout(400)
    await snap(page, '13-model-providers--320-dark')
  } finally {
    await page.request.put('/api/admin/keys/openai_api_key', { data: { value: '' }, headers: H })
  }
})

const HEAD_POSE = 'head-pose-face-detection-female-and-male.mp4'

interface Found {
  id: number
  faces: { id: number; thumb: string; filename: string }[]
  name: string | null
}

/** The identity holding a face crop of the head-pose clip, by crop file name. */
async function personWithFace(request: APIRequestContext, crop: string): Promise<Found | null> {
  const list = await (await request.get('/api/people?limit=500')).json()
  for (const p of list.people) {
    const d: Found = await (await request.get(`/api/people/${p.id}?limit=500`)).json()
    if (d.faces.some((f) => f.filename === HEAD_POSE && f.thumb.endsWith(`/faces/${crop}`))) return d
  }
  return null
}

test('14 people: name someone, search by name, merge, not this person, restore', async ({ page }) => {
  const NAME = 'Jonah Fielding'
  // Two clusters of the same man in the head-pose clip: a single face (00000_2) and his main cluster (00000_0).
  let small = await personWithFace(page.request, '00000_2.jpg')
  const big = await personWithFace(page.request, '00000_0.jpg')
  test.skip(!small || !big || small.id === big.id, 'the demo library has no separate clusters for the head-pose clip')
  if (!small || !big) return
  // A failed earlier run may have left the name behind.
  for (const p of (await (await page.request.get(`/api/people?named=true&q=${encodeURIComponent(NAME)}`)).json()).people) {
    await page.request.patch(`/api/people/${p.id}`, { data: { name: '' }, headers: H })
  }
  const faceId = small.faces[0].id
  const restoreName = async (id: number) => page.request.patch(`/api/people/${id}`, { data: { name: '' }, headers: H })

  await page.goto('/people')
  await expect(page.getByRole('heading', { name: 'People', level: 1 })).toBeVisible()
  await expect(page.getByText('never sent to model providers')).toBeVisible()
  await expect(page.locator('[data-testid=person-tile] img').first()).toBeVisible()
  await snapAll(page, '14-people')

  // Name an unnamed person inline.
  const tile = page.locator(`[data-testid=person-tile][data-person="${small.id}"]`)
  await tile.scrollIntoViewIfNeeded()
  await tile.getByRole('button', { name: `Name Person ${small.id}` }).click()
  const field = tile.getByRole('textbox', { name: `Name for Person ${small.id}` })
  await expect(field).toBeFocused()
  await field.fill(NAME)
  await page.waitForTimeout(400)
  await snap(page, '14-people-naming--desktop-dark')
  await field.press('Enter')
  try {
    const named = page.getByRole('list', { name: 'Named people' })
    await expect(named.getByText(NAME)).toBeVisible()
    await snap(page, '14-people-named--desktop-dark')

    // The name is searchable: the core makes it a hard filter and says so; the app shows a PERSON chip.
    await page.goto(`/search?q=${encodeURIComponent(NAME)}`)
    const chip = page.getByTestId('query-chip').filter({ hasText: 'PERSON' })
    await expect(chip).toContainText(NAME)
    await waitForResults(page)
    const res = await (await page.request.post('/api/search', { data: { q: NAME, limit: 50 }, headers: H })).json()
    expect(res.notes.join(' ')).toContain('recognised faces')
    expect(res.total).toBeGreaterThan(0)
    for (const r of res.results) expect(r.identities.map((p: { id: number }) => p.id)).toContain(small.id)
    await page.locator('[role=grid] [role=gridcell][data-uid]').first().click()
    const insp = page.getByTestId('inspector')
    await expect(insp.getByTestId('shot-people')).toContainText(NAME)
    await snapAll(page, '14-search-person', { only: 'desktop' })
    // Shot detail lists everyone recognised; unnamed people offer "Name…".
    await page.locator('[role=grid] [role=gridcell][data-uid]').first().dblclick()
    await expect(page).toHaveURL(/\/shot\//)
    const people = page.getByTestId('shot-people')
    await expect(people.getByRole('link', { name: NAME })).toBeVisible()
    await expect(people.getByRole('button', { name: /^Name Person / }).first()).toBeVisible()
    await snapAll(page, '14-shot-people')
    await people.getByRole('link', { name: NAME }).click()
    await expect(page).toHaveURL(new RegExp(`/people/${small.id}$`))
    await expect(page.getByRole('heading', { name: NAME, level: 1 })).toBeVisible()
    await snap(page, '14-person-named--desktop-dark')

    // Restore: rename back to unnamed.
    await page.getByRole('button', { name: 'Rename' }).click()
    await page.getByRole('textbox', { name: `New name for ${NAME}` }).fill('')
    await page.getByRole('textbox', { name: `New name for ${NAME}` }).press('Enter')
    await expect(page.getByRole('heading', { name: `Person ${small.id}`, level: 1 })).toBeVisible()
  } finally {
    await restoreName(small.id)
  }

  // Merge two clusters of the same man: drag one onto the other opens the merge (cancelled), then select both.
  await page.goto('/people')
  const smallTile = page.locator(`[data-testid=person-tile][data-person="${small.id}"]`)
  const bigTile = page.locator(`[data-testid=person-tile][data-person="${big.id}"]`)
  await smallTile.dragTo(bigTile)
  const dialog = page.getByTestId('merge-dialog')
  if (await dialog.isVisible().catch(() => false)) await page.getByRole('button', { name: 'Cancel' }).click()
  await bigTile.hover()
  await bigTile.getByRole('checkbox', { name: `Select Person ${big.id}` }).click({ force: true })
  await smallTile.hover()
  await smallTile.getByRole('checkbox', { name: `Select Person ${small.id}` }).click({ force: true })
  const bar = page.getByTestId('people-selection')
  await expect(bar).toContainText('2 selected')
  await snapAll(page, '14-people-selection', { only: 'desktop' })
  await bar.getByRole('button', { name: /Merge 2/ }).click()
  await expect(dialog).toBeVisible()
  // The larger cluster is kept by default.
  await expect(page.getByRole('radio', { name: new RegExp(`Person ${big.id}`) })).toBeChecked()
  await page.waitForTimeout(400)
  await snap(page, '14-merge-dialog--desktop-dark')
  await page.getByRole('button', { name: 'Merge 2 people' }).click()
  await expect(bar).toHaveCount(0)
  expect((await page.request.get(`/api/people/${small.id}`)).status()).toBe(404)
  const merged = await (await page.request.get(`/api/people/${big.id}?limit=500`)).json()
  expect(merged.faces.map((f: { id: number }) => f.id)).toContain(faceId)

  // "Not this person" moves that face out again: the split is restored (as a new person).
  await page.goto(`/people/${big.id}`)
  const face = page.locator(`[data-testid=face-item][data-face="${faceId}"]`)
  await expect(face).toBeVisible()
  await snapAll(page, '14-person')
  await face.getByRole('button', { name: /^Not this person/ }).click()
  await expect(page.getByText(/Moved the face to a new person, Person \d+/)).toBeVisible()
  await page.waitForTimeout(400)
  await snap(page, '14-not-this-person--desktop-dark')
  await expect(face).toHaveCount(0)
  small = await personWithFace(page.request, '00000_2.jpg')
  expect(small && small.id !== big.id && small.faces.length === 1 && !small.name).toBeTruthy()

  // Forget (admin) explains exactly what is deleted. Cancelled: nobody is forgotten.
  await page.getByRole('button', { name: 'Forget this person' }).click()
  await expect(page.getByTestId('forget-dialog')).toContainText('face embeddings')
  await page.waitForTimeout(400)
  await snap(page, '14-forget-confirm--desktop-dark')
  await page.getByRole('button', { name: 'Cancel' }).click()
  expect((await page.request.get(`/api/people/${big.id}`)).ok()).toBeTruthy()

  // Privacy: where face identity is switched off.
  await page.goto('/settings/privacy')
  await expect(page.getByRole('switch', { name: /On|Off/ })).toBeVisible()
  await expect(page.getByText('never sent to a model provider')).toBeVisible()
  await snapAll(page, '14-privacy-settings', { only: 'desktop' })
  await page.setViewportSize({ width: 320, height: 640 })
  await page.goto('/people')
  await page.waitForTimeout(600)
  await snap(page, '14-people--320-dark')
})
