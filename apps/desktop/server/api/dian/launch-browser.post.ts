import { spawn } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import { DIAN_DEBUG_PORT, debugProfileDir, findBrowser } from '../../utils/chromeLauncher'

// Launches a Chromium-based browser in remote-debugging mode (CDP :9222) so the DIAN scraper can
// attach to it ("modo humano"), WITHOUT the user opening a terminal. Idempotent: if the debugger
// is already answering, we don't relaunch. Returns { launched | already_running | not_found }.

async function debuggerUp(): Promise<boolean> {
  try {
    const ctrl = new AbortController()
    const t = setTimeout(() => ctrl.abort(), 1000)
    // 127.0.0.1 (not localhost) to dodge the Windows IPv6-first resolution issue.
    const res = await fetch(`http://127.0.0.1:${DIAN_DEBUG_PORT}/json/version`, { signal: ctrl.signal })
    clearTimeout(t)
    return res.ok
  } catch {
    return false
  }
}

export default defineEventHandler(async () => {
  if (await debuggerUp()) return { status: 'already_running' as const }

  const browser = findBrowser()
  if (!browser) return { status: 'not_found' as const }

  const profile = debugProfileDir()
  try {
    mkdirSync(profile, { recursive: true })
  } catch {
    /* si el perfil no se puede crear, Chrome usará uno temporal igual */
  }

  const args = [
    `--remote-debugging-port=${DIAN_DEBUG_PORT}`,
    '--remote-debugging-address=127.0.0.1',
    `--user-data-dir=${profile}`,
    '--no-first-run',
    '--no-default-browser-check',
  ]

  // Fully detach: the browser must outlive this request and not be tied to the Node process.
  const child = spawn(browser.path, args, { detached: true, stdio: 'ignore' })
  child.unref()

  return { status: 'launched' as const, browser: browser.browser }
})
