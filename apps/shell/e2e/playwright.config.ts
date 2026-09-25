import { defineConfig } from '@playwright/test'

// Smoke end-to-end contra el Electron REAL (#20). No es una suite de UI: es la
// comprobación de que la cadena completa arranca y funciona —
// Electron → Nitro → sidecar Python → preload → credencial local — que es
// justo lo que ni vitest ni pytest pueden ver.
export default defineConfig({
  testDir: '.',
  testMatch: '*.spec.ts',
  // Arrancar Electron + Nitro + Python tarda; y son pocos tests.
  timeout: 120_000,
  expect: { timeout: 30_000 },
  // En SERIE y con un solo worker: cada test levanta la aplicación entera.
  workers: 1,
  fullyParallel: false,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['github'], ['list']] : [['list']],
})
