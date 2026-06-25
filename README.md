# Contab

Software de escritorio para contadores que manejan **múltiples empresas**. Procesa el reporte Excel "Documentos Electrónicos" descargado del portal MUISCA / DIAN, lo cruza contra los PDFs de soporte de cada empresa, y exporta las filas no conformes con su razón.

**Stack**: Tauri (futuro empaquetado) + Nuxt 4 (frontend) + Python sidecar (lógica/parser/DB/extracción PDF) + SQLite (una `.db` por empresa).

Documentación:
- [CLAUDE.md](CLAUDE.md) — guía para Claude en cada sesión.
- [docs/plan.md](docs/plan.md) — roadmap por Entregas (E1–E11).
- [docs/decisions.md](docs/decisions.md) — registro de decisiones (D-001..D-040).
- [docs/excel-structure.md](docs/excel-structure.md) — análisis del Excel DIAN.
- [docs/glosario.md](docs/glosario.md) — términos del dominio contable colombiano.
- [docs/session_log.md](docs/session_log.md) — bitácora de sesiones.
- [docs/samples/](docs/samples/) — Excel + 6 PDFs de muestra (datos falsos).

## Estado: Entrega 1 ✅ (funcional end-to-end)

Lo que ya corre y está probado contra los samples reales:

- Crear empresas con validación de NIT (módulo 11 DIAN).
- Configurar **dos carpetas por empresa** (con folder picker propio, sin escribir rutas):
  - `default_folder` — donde viven los Excels DIAN.
  - `pdfs_folder` — donde viven los PDFs de soporte.
- **Auto-listado** de Excels en `default_folder` con badge `importado` por archivo, botón "Importar" y "Importar pendientes (N)" para batch.
- **Auto-indexing** de PDFs en `pdfs_folder` con:
  - `pdftotext -raw` → captura CUFE/CUDE/CUDS labeled (5/6 samples).
  - `pdftotext -layout` → fallback si el raw devuelve nada.
  - `cv2.QRCodeDetector` multi-DPI (300/400/220) sobre páginas renderizadas con `pypdfium2` → captura el CUFE del QR DIAN cuando la fuente está obfuscada (Movistar).
  - Cache incremental por `(folder, path, mtime, size)`.
  - **Regla 1-CUFE-por-PDF** con prioridad CUDS > CUDE > CUFE (NC de Éxito da solo su CUDE, no el CUFE del padre).
- Tabla con las 32 columnas DIAN + 3 derivadas (`# de factura` = `Prefijo-Folio`, `Valor Base` = `Total−IVA`, `Base IVA` = `IVA/0.19`).
  - **14 columnas visibles por defecto**, 21 ocultas pero filtrables (panel de visibilidad).
  - Búsqueda global, badge `NC` para Notas Crédito.
- Tres validaciones del flujo real del usuario:
  - **V1 — CUFE/CUDE/CUDS de la fila debe existir en algún PDF de la carpeta** (real, no stub).
  - **V2 — Notas Crédito × −1**: `IVA` y `Total` se invierten en memoria al evaluar y al exportar; BD guarda originales.
  - **V3 — Tarifa IVA**: 19% primero, fallback 5%, skip si `IVA = 0`.
- Exportar `.xlsx` de **filas no conformes** con las 36 columnas (32 originales + 3 derivadas + `razon_falla`), valores invertidos en NCs, motivos múltiples separados por `; `.
- Persistencia completa por empresa en SQLite con migraciones idempotentes.

**Tests**: 37 pasando contra `docs/samples/`.

## Setup (primera vez)

Requisitos del sistema:
- **Node ≥ 20** y **npm ≥ 10**.
- **Python ≥ 3.10**.
- **Poppler** (`pdftotext` binary). En Debian/Ubuntu: `sudo apt install poppler-utils`. En macOS: `brew install poppler`. En Windows: incluido en el bundle de poppler.
- (Opcional para futuro Tauri en Linux dev) `libwebkit2gtk-4.1-dev`, `libjavascriptcoregtk-4.1-dev`, `libsoup-3.0-dev`.

```bash
# Python sidecar — crear venv e instalar paquete en modo editable
cd apps/core
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
.venv/bin/pytest          # 37 tests deben pasar

# Frontend
cd ../desktop
npm install
```

## Correr en dev

```bash
cd apps/desktop
npm run dev               # http://localhost:3000
```

El frontend Nuxt arranca el sidecar Python automáticamente como subproceso. Resuelve la ruta del `python` desde `apps/core/.venv/bin/python` o desde la variable de entorno `CONTAB_PYTHON`.

## Flujo de prueba end-to-end

1. Abre [http://localhost:3000](http://localhost:3000).
2. Crea la empresa **"REAL Seguros Ltda."** con NIT `900181831` (el DV `4` se calcula y muestra automáticamente).
3. En la página de la empresa, pulsa **"📂 Elegir carpeta"** en el panel **"Carpeta de archivos de la empresa"** y selecciona el directorio donde tienes tus Excels DIAN (por ejemplo `<repo>/docs/samples/`).
4. Pulsa **"📂 Elegir carpeta"** en el panel **"Soportes PDF"** y selecciona la carpeta de PDFs (por ejemplo `<repo>/docs/samples/pdfs/`).
5. El panel de PDFs mostrará los 6 archivos con su CUFE extraído debajo. La primera indexación toma unos segundos por el QR scan; las siguientes son instantáneas (cache).
6. En el panel "Archivos en la carpeta", pulsa **"Importar"** en el Excel.
7. Abre la carga creada → ves la tabla con 14 columnas visibles + búsqueda + panel de columnas.
8. Pulsa **"Validar"** → ves **"7 / 11 filas no conformes · V1 activa (6 CUFE indexados)"**.
9. Pulsa **"📂 Carpeta de salida"**, elige un destino, y pulsa **"Exportar no conformes"** → genera el `.xlsx`.

## Resultado esperado con los samples del repo

Al validar el Excel `Ejemplo_LaDian.xlsx` con la carpeta `docs/samples/pdfs/` indexada (6 CUFEs):

| # factura | Tipo | Resultado |
|---|---|---|
| DSE-210, DSE-211, SP-144, TCNC-1952292 | Doc soporte / Factura / NC | ✅ Pasan todas |
| BEC-509558651 (Movistar) | Factura | ⚠️ Pasa V1 (CUFE encontrado via QR), falla V3 (tarifa IVA) |
| 94DD-49995 (D1) | Factura POS | ⚠️ Pasa V1, falla V3 |
| FELE-827, FELE-823 | Factura | ❌ Fallan V1 (sin soporte PDF) |
| NOM-317, NOM-318 | Nómina | ❌ Fallan V1 |
| NCLA-1017 | Nota crédito | ❌ Falla V1 |

## Carpeta de datos (D-021)

| SO | Ruta |
|---|---|
| Windows | `%APPDATA%\Contab\empresas\<nit>_<slug>.db` |
| macOS | `~/Library/Application Support/Contab/empresas/<nit>_<slug>.db` |
| Linux | `~/.local/share/Contab/empresas/<nit>_<slug>.db` |
| VSCode snap (dev) | `~/snap/code/<rev>/.local/share/Contab/empresas/<nit>_<slug>.db` |

Override con `XDG_DATA_HOME` (Linux/macOS) o `APPDATA` (Windows).

## RPCs disponibles (`POST /api/rpc`)

`{"method": "<name>", "params": {...}}` → `{"ok": true, "result": ...}` o `{"ok": false, "error": "..."}`.

| Método | Qué hace |
|---|---|
| `ping` | Sanity check. |
| `list_empresas` | Lista empresas escaneando la carpeta. |
| `validate_nit` | Valida NIT (módulo 11) o calcula DV. |
| `create_empresa` | Crea `.db` para una empresa con NIT + razón social. |
| `open_empresa` | Lee `empresa_info` (incluye `default_folder`, `pdfs_folder`). |
| `set_default_folder` | Persiste la carpeta de Excels. |
| `set_pdfs_folder` | Persiste la carpeta de PDFs. |
| `list_folder_files` | Lista Excels de `default_folder` con flag `imported`. |
| `list_pdfs_folder_files` | Lista PDFs de `pdfs_folder` con CUFE extraído y status. |
| `reindex_pdfs` | Re-indexa la carpeta de PDFs (manual; normalmente automático). |
| `import_excel` | Importa un Excel a la empresa (in-place, no copia). |
| `list_loads` | Historial de cargas de Excel. |
| `get_load_rows` | Filas de una carga (paginado). |
| `run_validations` | Auto-indexa PDFs + corre V1/V2/V3. Devuelve conteos. |
| `export_no_conformes` | Auto-indexa PDFs + exporta `.xlsx` con razones. |

Endpoints adicionales del frontend:
- `POST /api/upload-excel` — multipart upload + persistencia + `import_excel`.
- `GET /api/list-dir?path=...&show_hidden=0|1` — para el `DirectoryPicker`.

## Próximos pasos sugeridos

Ver [docs/plan.md](docs/plan.md) → `## Próxima sesión`. Candidatos:

- **E2** — Backup/restore de empresa, edición de NIT/razón social, archive de empresas.
- **E5** — Plan de cuentas (PUC) + catálogo de terceros (clientes/proveedores). Podemos derivar terceros automáticamente de las filas del Excel DIAN.
- **E10** — Empaquetado Tauri para Windows.
- **Mejoras de UX sobre E1** — mostrar `razon_falla` en línea por fila en la tabla, filtros guardados por empresa, columnas reordenables.
