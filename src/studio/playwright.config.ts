import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './test',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: 0,
  use: {
    baseURL: 'http://127.0.0.1:5173',
    viewport: { width: 1459, height: 900 },
    locale: 'zh-CN',
    deviceScaleFactor: 1,
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], deviceScaleFactor: 1 } }],
})
