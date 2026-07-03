// Minimal, safe preload. The UI is a normal web app served by Nitro over localhost, so it needs
// almost no privileged bridge. We expose the app version and a `quit()` so "Salir de Contab"
// (SidebarUser) can close the program.
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('contab', {
  version: process.env.CONTAB_VERSION || null,
  quit: () => ipcRenderer.send('app:quit'),
})
