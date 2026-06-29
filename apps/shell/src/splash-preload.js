// Preload del splash: expone una API mínima y segura (contextIsolation) para que el botón
// "Ingresar" pida al proceso principal abrir la app, y para recibir el estado "cargando".
const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('contabSplash', {
  enter: () => ipcRenderer.send('splash:enter'),
  onLoading: (cb) => ipcRenderer.on('splash:loading', () => cb()),
})
