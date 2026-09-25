import { defineConfig } from 'vitest/config'
import { fileURLToPath } from 'node:url'

// Tests unitarios del frontend (#20 de la revisión). Hasta ahora TODO el testing
// vivía en Python: 117 .vue y 47 .ts sin una sola prueba.
//
// Esto NO sustituye a un smoke end-to-end de la app (pendiente): cubre la lógica
// pura — composables y utilidades de servidor — que es donde estaban los fallos
// que encontró la revisión (contrato de error, timeouts, rutas por SO).
export default defineConfig({
  test: {
    environment: 'happy-dom',
    include: ['test/**/*.test.ts'],
    globals: true,
  },
  resolve: {
    alias: {
      '~~': fileURLToPath(new URL('./', import.meta.url)),
      '~': fileURLToPath(new URL('./app', import.meta.url)),
    },
  },
})
