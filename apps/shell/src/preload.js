// Minimal, safe preload. The UI is a normal web app served by Nitro over localhost, so it needs
// no privileged bridge today. We only expose the app version (handy for an "Acerca de" later).
const { contextBridge } = require('electron')

contextBridge.exposeInMainWorld('contab', {
  version: process.env.CONTAB_VERSION || null,
})
