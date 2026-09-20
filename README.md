# Contab

Software de escritorio para contadores que manejan **múltiples empresas**. Procesa el reporte Excel "Documentos Electrónicos" que se descarga del portal MUISCA / DIAN, lo cruza contra los PDFs de soporte de cada empresa, marca y exporta las filas no conformes, renombra los soportes de forma ordenada, y consulta datos de terceros en la DIAN.

**Stack**: Electron (shell de escritorio) + Nuxt 4 / Vue 3 (frontend, `ssr: false`) + Python como *sidecar* (parser, validaciones, DB, extracción de CUFE) + SQLite (**una `.db` por empresa**). Un segundo sidecar (FastAPI + Playwright) resuelve la Consulta de Terceros contra la DIAN.

- UI en **español (Colombia)**, contexto **DIAN**.
- Diseño **Dandelyon · Órbita** (shadcn + Tailwind v4 + reka-ui).

Documentación interna:
- [CLAUDE.md](CLAUDE.md) — guía de arranque + decisiones inmutables.
- [docs/plan.md](docs/plan.md) — roadmap por Entregas.
- [docs/decisions.md](docs/decisions.md) — registro de decisiones (D-001…D-068).
- [docs/excel-structure.md](docs/excel-structure.md) — estructura verificada del Excel DIAN.
- [docs/glosario.md](docs/glosario.md) — términos del dominio contable colombiano.
- [docs/session_log.md](docs/session_log.md) — bitácora de sesiones.
- [docs/samples/](docs/samples/) — Excel + 6 PDFs de muestra (datos falsos, commiteables).

---

## Modelo mental (importante)

La app se organiza en tres niveles:

```
Empresa  (un libro contable, una .db)
  └── Mes / periodo  (AAAA-MM — un "ambiente" independiente)
        ├── Excel DIAN del mes         (los documentos electrónicos)
        └── Carpeta de soportes del mes (los PDF que envía el cliente)
```

Cada **mes** es su propio ambiente: tiene su Excel y **su** carpeta de soportes. No hay carpeta global de PDFs — la validación de un mes usa la carpeta de ese mes.

---

## Qué puedes hacer hoy

### 1. Empresas
- Crear empresas con validación de **NIT (módulo 11 DIAN)**; el dígito de verificación (DV) se calcula solo.
- Cada empresa vive en su propia `.db` (aislamiento total entre empresas).

### 2. Meses y carga del Excel
- Crear un mes (`AAAA-MM`) dentro de la empresa.
- Subir el **Excel DIAN** de ese mes y elegir su **carpeta de soportes** (con un selector de carpetas propio; no escribes rutas).
- Mover un Excel a otro mes o enviarlo a la papelera.

### 3. Tabla de la carga y validaciones
Al abrir una carga ves la tabla con las columnas DIAN + 3 derivadas (`# de factura` = `Prefijo-Folio`, `Valor Base` = `Total − IVA`, `Base IVA`), con:
- Búsqueda global, panel de columnas (mostrar/ocultar), badge `NC` para Notas Crédito.
- Botón **Validar** que corre las tres validaciones y marca cada fila (✓ / ⚠ con el motivo al pasar el mouse):
  - **V1 — Soporte**: el CUFE/CUDE/CUDS de la fila debe existir en algún PDF de la carpeta del mes.
  - **V2 — Notas Crédito**: `IVA` y `Total` se invierten al evaluar/exportar (la BD guarda los originales).
  - **V3 — Tarifa de IVA**: 19% primero, 5% como fallback; se omite si `IVA = 0`.
- Filtro **Solo no conformes** y casilla **Aprobar** para marcar manualmente una fila que falla V3 como aceptada.
- **Exportar faltantes de soporte** → `.xlsx` con las columnas originales + derivadas + `razon_falla`.

### 4. Soportes del mes  ·  Re-verificar  *(nuevo)*
En la página de la carga, el panel **📎 Soportes del mes** muestra:
- Un conteo: `N archivos · M con CUFE · K sin CUFE`.
- Al desplegarlo, la lista archivo por archivo con su estado (✓ con CUFE / ⚠ sin CUFE / • sin verificar) y **el CUFE encontrado** cuando lo hay. Así ves exactamente **cuáles** PDFs no se pudieron leer.
- Botón **Re-verificar soportes**: vuelve a leer los CUFE de la carpeta del mes y refresca las validaciones **sin re-subir el Excel**. Úsalo cuando agregues, reemplaces o renombres PDFs, o cuando quieras forzar una relectura.

> La extracción de CUFE quedó cacheada; si mejora el algoritmo de lectura, el caché viejo se re-lee solo. "Re-verificar" fuerza una relectura completa de esa carpeta.

### 5. Renombrar soportes  *(nuevo)*
Botón **Renombrar soportes** en la página de la carga. Renombra los PDF del mes al patrón:

```
DD-MM_NIT_RAZON-SOCIAL_FACTURA.pdf
```

- La fecha `DD-MM` sale de la **Fecha de Emisión** de la fila del Excel; el NIT, la razón social y el número de factura, del cruce por **CUFE** entre el PDF y su fila.
- Primero muestra una **vista previa** (nombre actual → nombre nuevo) con conteos; nada se toca hasta que confirmes **Aplicar**.
- Se renombra **en la misma carpeta** y se deja un manifiesto **`_renombrados.csv`** (nombre nuevo, nombre original, CUFE, fecha) para poder revertir/auditar.
- Es seguro: nunca sobreescribe (si hay choque agrega `_2`, `_3`…), es idempotente (un PDF ya con su nombre destino se salta) y **los PDF sin CUFE o que no cruzan con el Excel se dejan intactos y se reportan**.

### 6. Consultas DIAN
En el sidebar, el grupo **Consultas DIAN**:
- **Terceros** — consulta el RUT / razón social de terceros a partir de sus NIT (abre un navegador dedicado que sortea el "Soy humano" de Cloudflare; sidecar Playwright).
- **Inconsistencias** — obtiene la razón social por **NIT + DV** consultando MUISCA por HTTP plano (sin navegador). Subes un Excel con columnas NIT y DV, consulta fila por fila (con progreso, cancelar y reintentar fallidos) y exportas el resultado.

### 7. Ayuda in-app
El botón **"?"** del topbar lanza un **tour guiado** de la vista actual (incluye los pasos de validar, soportes, re-verificar, renombrar y exportar). Los iconos de ayuda contextual (`HelpHint`) explican conceptos como "no conforme".

---

## Cómo funciona la extracción de CUFE

Cada PDF de soporte se identifica por su **CUFE / CUDE / CUDS** (96 hex). El extractor (D-017, D-033, D-067) intenta, en orden:

1. **`pdftotext -raw`** — reconstruye el código agrupando segmentos hex separados por espacios que sumen exactamente 96 (maneja CUFEs partidos en varias líneas **sin** pegarles números vecinos, como el número de autorización). Si el código viene **etiquetado** (`CUFE:`/`CUDE:`/`CUDS:`) se toma con prioridad **CUDS > CUDE > CUFE** (una Nota Crédito devuelve su propio CUDE, no el CUFE del padre).
2. **`pdftotext -layout`** — por si el layout ayuda a exponer la etiqueta.
3. **Escaneo del QR** (pypdfium2 + `cv2.QRCodeDetector`, multi-DPI) — el QR de la DIAN trae el CUFE en claro. Se usa **como verificación de las lecturas dudosas** (cuando el texto no da nada o da un código sin etiqueta) y es **autoritativo** (es la fuente machine-readable de la DIAN).

El resultado se cachea por `(carpeta, archivo, mtime, tamaño, versión-del-extractor)`; solo se re-lee lo que cambió o lo que quedó de una versión anterior del extractor.

---

## Setup (primera vez)

Requisitos:
- **Node ≥ 20**, **npm ≥ 10**
- **Python ≥ 3.10**
- **Poppler** (binario `pdftotext`). Windows en desarrollo: instálalo y ponlo en el PATH, o apunta `CONTAB_PDFTOTEXT` al .exe; en la app instalada viene empaquetado. Debian/Ubuntu: `sudo apt install poppler-utils` · macOS: `brew install poppler`.
  Si falta, Contab ahora lo dice (RPC `check_dependencies`, D-080) en vez de marcar todo el mes como «sin soporte».

El producto es Windows, así que el setup va primero en PowerShell. El layout del
venv cambia por SO: `Scripts\` en Windows, `bin/` en POSIX.

```powershell
# Sidecar Python (core) — Windows
cd apps\core
py -m venv .venv
.venv\Scripts\pip install -e ".[dev]"
.venv\Scripts\pytest -q            # 158 tests deben pasar
.venv\Scripts\ruff check .         # debe salir limpio

# Frontend
cd ..\desktop
npm ci                              # ci, no install: respeta el lockfile
npm test                            # 33 tests de frontend
npm run typecheck
```

```bash
# Lo mismo en Linux / macOS
cd apps/core
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest -q
cd ../desktop && npm ci
```

Para la Consulta de **Terceros** (opcional) hace falta el sidecar DIAN:

```powershell
cd apps\dian-rut
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\playwright install chromium
```

## Correr en dev

```bash
cd apps/desktop
npm run dev                          # http://localhost:3000
```

Nuxt arranca el sidecar Python automáticamente. Si tu sistema tiene pocos *file watchers* (`ENOSPC` de inotify en Linux), súbelos: `sudo sysctl fs.inotify.max_user_watches=524288`.

> Alternativa sin watchers: `npm run build && PORT=3000 node .output/server/index.mjs`.

Al cambiar código **Python**, refresca el sidecar: `pkill -f '[c]ontab_core.sidecar'` (el siguiente request lo levanta).

## Empaquetado (Windows)

El shell Electron (`apps/shell/`) empaqueta el frontend + los sidecars como binarios PyInstaller + Poppler, con `electron-builder` (NSIS per-user). El build corre en GitHub Actions (`.github/workflows/release-windows.yml`, `windows-latest`) por *workflow_dispatch* o al empujar un tag `vX.Y.Z`, y sube el instalador como artefacto del run. Ver [apps/shell/README.md](apps/shell/README.md) y las decisiones D-057…D-060.

---

## Carpeta de datos

| SO | Ruta |
|---|---|
| Windows | `%APPDATA%\Contab\empresas\<nit>_<slug>.db` |
| macOS | `~/Library/Application Support/Contab/empresas/<nit>_<slug>.db` |
| Linux | `~/.local/share/Contab/empresas/<nit>_<slug>.db` |
| VSCode snap (dev) | `~/snap/code/<rev>/.local/share/Contab/empresas/<nit>_<slug>.db` |

Override con `XDG_DATA_HOME` (Linux/macOS) o `APPDATA` (Windows).

---

## RPCs (`POST /api/rpc`)

`{"method": "<name>", "params": {...}}` → `{"ok": true, "result": ...}` o `{"ok": false, "error": "..."}`.

| Método | Qué hace |
|---|---|
| `ping` | Sanity check. |
| `list_empresas` / `create_empresa` / `open_empresa` | Catálogo y apertura de empresas. |
| `validate_nit` | Valida NIT (módulo 11) o calcula el DV. |
| `create_periodo` / `list_periodos` | Meses (ambientes) de la empresa. |
| `import_excel` | Importa el Excel de un mes (in-place, no copia). |
| `list_loads` / `get_load_rows` | Cargas de Excel y sus filas (paginado). |
| `run_validations` | Auto-indexa los soportes del mes + corre V1/V2/V3. |
| `export_no_conformes` | Exporta el `.xlsx` de faltantes con razones. |
| `list_load_soportes` | Soportes del mes con estado + CUFE; `reindex`/`force` para re-verificar. |
| `rename_soportes` | Renombra los PDF del mes (dry-run o aplicar) según el cruce con el Excel. |
| `toggle_validation_override` | Aprobar/desaprobar V3 manualmente en una fila. |
| `reindex_pdfs` / `list_pdfs_folder_files` | Índice sobre la carpeta a nivel empresa (uso legado/depuración). |
| `parse_nit_dv` / `consulta_inconsistencias` / `export_inconsistencias` | Consulta de Inconsistencias DIAN (razón social por NIT+DV). |

Endpoints del frontend: `POST /api/upload-excel`, `POST /api/upload-restore`, `GET /api/list-dir`, `GET /api/version`, y los de `POST /api/dian/*` (Consulta de Terceros).

---

## Tests

```powershell
cd apps\core   ; .venv\Scripts\pytest -q ; .venv\Scripts\ruff check .   # 158 tests
cd apps\desktop; npm test ; npm run typecheck                           # 33 tests
```

El core cubre el parser del Excel, los importes en Decimal (D-075), el DV (módulo 11), V1/V2/V3, la extracción de CUFE (texto + QR + prioridad de etiquetas + invalidación de caché por versión), el índice de PDFs, las migraciones de esquema y el ciclo de vida de una empresa, contra los samples de `docs/samples/`.

El frontend cubre las utilidades de servidor y los composables.

```powershell
cd apps\shell ; npm run e2e        # smoke end-to-end contra el Electron real
```

El smoke arranca la aplicación entera (Electron → Nitro → sidecar Python → preload
→ credencial), crea una empresa, sube el Excel de muestra, valida y comprueba la
papelera. Necesita el build de Nuxt (`apps/desktop && npm run build`) y el venv de
`apps/core`; si falta alguno, se salta con un mensaje que dice qué correr.

Escribe en un temporal, **nunca** en tus datos reales: apunta `APPDATA` y
`XDG_DATA_HOME` a una carpeta desechable antes de lanzar Electron, y hay un test
dedicado a verificarlo.

Todo esto corre solo en cada push y PR (`.github/workflows/test.yml`).
