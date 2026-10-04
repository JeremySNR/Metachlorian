import { defineConfig } from '@playwright/test'

/**
 * End-to-end journeys against a live core serving app/dist (ADR 017).
 * Browsers come from /opt/pw-browsers (pinned @playwright/test 1.56.1); never `playwright install`.
 * Screenshots → review/m4/screens, videos → review/m4/video.
 */
export default defineConfig({
  testDir: './e2e',
  outputDir: './test-results',
  timeout: 180_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [['list'], ['json', { outputFile: '../review/m4/e2e-results.json' }]],
  use: {
    baseURL: process.env.BASE_URL ?? 'http://127.0.0.1:8770',
    viewport: { width: 1440, height: 900 },
    colorScheme: 'dark',
    video: { mode: 'on', size: { width: 1440, height: 900 } },
    trace: 'retain-on-failure',
    locale: 'en-GB',
    timezoneId: 'Europe/London',
  },
  projects: [
    { name: 'review', use: { browserName: 'chromium' }, testIgnore: /\.electron\.spec\.ts$/ },
    { name: 'electron', testMatch: /\.electron\.spec\.ts$/ },
  ],
})
