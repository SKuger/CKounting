// Adjunta la credencial local a TODA petición a la API (D-089).
//
// Se hace reemplazando el `$fetch` global en vez de tocar cada llamada: así
// `useRpc`, las subidas de archivos y cualquier `$fetch` futuro quedan cubiertos
// sin que nadie tenga que acordarse.
//
// En desarrollo (`npm run dev`) no hay shell de Electron, así que `window.contab`
// no existe, no se manda cabecera y el servidor tampoco la exige.

declare global {
  interface Window {
    contab?: { token?: string; quit?: () => void }
  }
}

const CABECERA_TOKEN = 'x-contab-token'

export default defineNuxtPlugin(() => {
  const token = window.contab?.token
  if (!token) return

  const conCredencial = $fetch.create({
    onRequest({ options }) {
      const headers = new Headers(options.headers as HeadersInit | undefined)
      headers.set(CABECERA_TOKEN, token)
      options.headers = headers
    },
  })

  // `useRpc` y los endpoints de subida usan el `$fetch` global directamente.
  globalThis.$fetch = conCredencial as typeof globalThis.$fetch
})
