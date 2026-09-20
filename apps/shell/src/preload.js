// Preload mínimo. La UI es una web normal servida por Nitro en localhost, así que
// casi no necesita puente privilegiado: solo `quit()` para "Salir de Contab"
// (SidebarUser). Funciona con `sandbox: true` (D-088) porque contextBridge e
// ipcRenderer están disponibles también en un preload aislado.
//
// Ojo: en un preload con sandbox NO hay `process.env`. Aquí se exponía un
// `version` que además nadie leía — la versión la sirve /api/version, que la toma
// de CONTAB_VERSION en el proceso de Nitro.
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('contab', {
  // Credencial de la API local (D-089). Se pide por IPC síncrono en vez de leerla
  // de process.env porque un preload con sandbox no tiene entorno.
  token: ipcRenderer.sendSync('contab:token'),
  quit: () => ipcRenderer.send('app:quit'),
})
