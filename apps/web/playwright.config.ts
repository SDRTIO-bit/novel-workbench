import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  timeout: 30000,
  retries: 0,
  use: {
    baseURL: 'http://localhost:8765',
    headless: true,
  },
  webServer: [
    {
      command: 'cd ../api && python -m uvicorn app.main:app --host 0.0.0.0 --port 8766',
      port: 8766,
      reuseExistingServer: true,
    },
    {
      command: 'npx vite --port 8765',
      port: 8765,
      reuseExistingServer: true,
    },
  ],
})
