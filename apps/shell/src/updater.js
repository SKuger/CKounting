// Auto-update (electron-updater). The feed/provider is baked from electron-builder.yml `publish:`
// (github → public releases repo, hosting TBD). Integrity is verified by sha512 from latest.yml,
// independent of Authenticode (which we don't have). Only runs when packaged: dev has no
// app-update.yml, and a missing/unreachable feed must never crash the app — all guarded.
const { autoUpdater } = require('electron-updater')
const { dialog } = require('electron')
const log = require('electron-log')

function initUpdater() {
  autoUpdater.logger = log
  autoUpdater.autoDownload = true
  autoUpdater.autoInstallOnAppQuit = true

  autoUpdater.on('error', (err) => log.warn('[updater] error:', (err && err.message) || err))
  autoUpdater.on('checking-for-update', () => log.info('[updater] checking…'))
  autoUpdater.on('update-available', (info) => log.info('[updater] available:', info && info.version))
  autoUpdater.on('update-not-available', () => log.info('[updater] up to date'))
  autoUpdater.on('download-progress', (p) => log.info(`[updater] ${Math.round(p.percent)}%`))
  autoUpdater.on('update-downloaded', async (info) => {
    log.info('[updater] downloaded:', info && info.version)
    const { response } = await dialog.showMessageBox({
      type: 'info',
      buttons: ['Reiniciar ahora', 'Más tarde'],
      defaultId: 0,
      cancelId: 1,
      title: 'Actualización disponible',
      message: `Contab ${info && info.version ? info.version : ''} está listo.`,
      detail: 'Reinicia para aplicar la actualización.',
    })
    if (response === 0) autoUpdater.quitAndInstall()
  })

  // fire-and-forget; never throw into the main flow
  autoUpdater.checkForUpdates().catch((e) => log.warn('[updater] check failed:', (e && e.message) || e))
}

module.exports = { initUpdater }
