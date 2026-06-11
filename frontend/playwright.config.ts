import { defineConfig, devices } from '@playwright/test';

/**
 * E2E config. Runs against a server the CI job already has up:
 *   - the static export served on :3000
 *   - the FastAPI backend (sample bundle) on :8000
 * Locally you can point at any deploy with E2E_BASE_URL.
 */
export default defineConfig({
  testDir: './e2e',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: [['list']],
  use: {
    baseURL: process.env.E2E_BASE_URL ?? 'http://localhost:3000',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
});
