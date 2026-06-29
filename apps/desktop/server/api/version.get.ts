// App version for the UI (sidebar credit). The Electron shell injects CONTAB_VERSION
// (= app.getVersion(), the installer/release version) into Nitro's env. In dev (browser,
// no shell) it falls back to 'dev'. Single source of truth: apps/shell/package.json.
export default defineEventHandler(() => ({
  version: process.env.CONTAB_VERSION ?? 'dev',
}))
