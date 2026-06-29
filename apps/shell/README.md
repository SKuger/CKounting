# apps/shell — empaquetador de escritorio (Electron)

Envuelve Contab como app de escritorio Windows. Electron arranca el **servidor Nitro**
(`apps/desktop/.output`) con su propio Node (`ELECTRON_RUN_AS_NODE`), y Nitro lanza los **sidecars
Python** empaquetados (`contab-sidecar` por stdio · `dian-sidecar` por uvicorn). Auto-update con
`electron-updater`.

## Runtime (qué arranca al abrir)
```
Electron → node .output/server/index.mjs (puerto libre)
            ├─ contab-sidecar.exe   (env CONTAB_SIDECAR_BIN) + pdftotext.exe (CONTAB_PDFTOTEXT)
            └─ dian-sidecar.exe     (env DIAN_SIDECAR_BIN) → Chrome del usuario por CDP :9222
Datos: %APPDATA%\Contab\  (empresas\ · dian\ · logs\)
```

## Build (Windows — lo hace el CI, ver `.github/workflows/release-windows.yml`)
1. `apps/core`: `pip install . pyinstaller && pyinstaller contab-sidecar.spec --noconfirm`
2. `apps/dian-rut`: `pip install -r requirements.txt pyinstaller && pyinstaller dian-sidecar.spec --noconfirm`
3. Poppler: descargar y copiar `pdftotext.exe` + DLLs → `apps/shell/resources/poppler/`
4. `apps/desktop`: `npm ci && npm run build`
5. Stage → `apps/shell/resources/{server,core-sidecar,dian-sidecar}`
6. `apps/shell`: `npm install && npx electron-builder --win nsis --publish never`

Salida: `apps/shell/dist/Contab Setup X.Y.Z.exe` (+ `.blockmap` + `latest.yml`).

## Dev (Linux/Windows, contra el repo)
Tras `npm run build` en `apps/desktop` (y opcionalmente PyInstaller de los sidecars en `dist/`):
`cd apps/shell && npm install && npm start`. Si no hay sidecar empaquetado, Nitro cae al venv
(`python -m contab_core.sidecar`).

## Notas
- **Sin firma Authenticode** (de pago) → SmartScreen avisa en la 1ª instalación ("Más información →
  Ejecutar de todos modos"). El auto-update funciona igual (integridad sha512).
- **Hosting del auto-update**: pendiente. `electron-builder.yml → publish` apunta a un repo público
  de releases (`SKuger/CKounting-releases`, por crear). Cambiar el CI a `--publish always` cuando exista.
- **DIAN**: no se bundlea Chromium; usa el Chrome del usuario con `--remote-debugging-port=9222`.
