import { defineConfig } from '@playwright/test';

// Explicit opt-in to an installed browser; CI retains Playwright's bundled Chromium.
const channel = process.env.SENTINEL_E2E_BROWSER_CHANNEL;
if (channel && !['chrome', 'msedge'].includes(channel)) {
  throw new Error('SENTINEL_E2E_BROWSER_CHANNEL must be chrome or msedge');
}

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  retries: 0,
  use: {
    baseURL: process.env.SENTINEL_E2E_URL,
    ...(channel ? { channel } : {}),
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  reporter: 'list',
});
