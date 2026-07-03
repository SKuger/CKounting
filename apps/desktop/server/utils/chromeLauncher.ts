// Discovers a Chromium-based browser and the writable profile dir used to launch it in remote-
// debugging mode (CDP :9222) for the DIAN "human mode". Cross-platform: Windows (Chrome → Edge
// fallback), macOS, Linux. The launched browser uses a DEDICATED profile (chrome-debug-profile),
// separate from the user's normal Chrome, so it never collides with an already-running instance.

import { existsSync } from 'node:fs'
import { join } from 'node:path'
import { homedir } from 'node:os'

export type BrowserKind = 'chrome' | 'edge' | 'chromium'
export type ChromeInfo = { path: string; browser: BrowserKind } | null

function firstExisting(candidates: (string | undefined)[]): string | null {
  for (const c of candidates) if (c && existsSync(c)) return c
  return null
}

// Scan the PATH for any of the given binary names (Linux/macOS discovery).
function fromPath(names: string[]): string | null {
  const sep = process.platform === 'win32' ? ';' : ':'
  const dirs = (process.env.PATH || '').split(sep).filter(Boolean)
  for (const name of names) {
    for (const d of dirs) {
      const c = join(d, name)
      if (existsSync(c)) return c
    }
  }
  return null
}

export function findBrowser(): ChromeInfo {
  const platform = process.platform

  if (platform === 'win32') {
    const pf = process.env['ProgramFiles'] || 'C:\\Program Files'
    const pf86 = process.env['ProgramFiles(x86)'] || 'C:\\Program Files (x86)'
    const local = process.env['LOCALAPPDATA'] || join(homedir(), 'AppData', 'Local')
    const chrome = firstExisting([
      join(pf, 'Google', 'Chrome', 'Application', 'chrome.exe'),
      join(pf86, 'Google', 'Chrome', 'Application', 'chrome.exe'),
      join(local, 'Google', 'Chrome', 'Application', 'chrome.exe'),
    ])
    if (chrome) return { path: chrome, browser: 'chrome' }
    const edge = firstExisting([
      join(pf, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
      join(pf86, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
      join(local, 'Microsoft', 'Edge', 'Application', 'msedge.exe'),
    ])
    if (edge) return { path: edge, browser: 'edge' }
    return null
  }

  if (platform === 'darwin') {
    const chrome = firstExisting([
      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      join(homedir(), 'Applications/Google Chrome.app/Contents/MacOS/Google Chrome'),
    ])
    if (chrome) return { path: chrome, browser: 'chrome' }
    const edge = firstExisting(['/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge'])
    if (edge) return { path: edge, browser: 'edge' }
    return null
  }

  // linux
  const chrome = firstExisting([
    '/opt/google/chrome/chrome',
    '/usr/bin/google-chrome',
    '/usr/bin/google-chrome-stable',
  ]) || fromPath(['google-chrome', 'google-chrome-stable'])
  if (chrome) return { path: chrome, browser: 'chrome' }
  const chromium = firstExisting([
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
    '/snap/bin/chromium',
  ]) || fromPath(['chromium', 'chromium-browser'])
  if (chromium) return { path: chromium, browser: 'chromium' }
  const edge = firstExisting(['/usr/bin/microsoft-edge', '/usr/bin/microsoft-edge-stable']) || fromPath(['microsoft-edge', 'microsoft-edge-stable'])
  if (edge) return { path: edge, browser: 'edge' }
  return null
}

// Writable, dedicated profile for the debug browser. Packaged: under DIAN_WORKDIR (%APPDATA%/Contab/dian).
// Dev: platform data dir, so it never lands in a read-only or repo location.
export function debugProfileDir(): string {
  if (process.env.DIAN_WORKDIR) return join(process.env.DIAN_WORKDIR, 'chrome-debug-profile')
  const platform = process.platform
  if (platform === 'win32') {
    const appData = process.env.APPDATA || join(homedir(), 'AppData', 'Roaming')
    return join(appData, 'Contab', 'dian', 'chrome-debug-profile')
  }
  if (platform === 'darwin') {
    return join(homedir(), 'Library', 'Application Support', 'Contab', 'dian', 'chrome-debug-profile')
  }
  return join(homedir(), '.local', 'share', 'Contab', 'dian', 'chrome-debug-profile')
}

export const DIAN_DEBUG_PORT = 9222
