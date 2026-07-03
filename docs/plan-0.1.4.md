# Contab 0.1.4 — Plan de 2 tracks (trabajo en paralelo)

> Este documento es el **brief para el segundo Claude** (Track 2). El primer Claude (Track 1)
> hace el backend en `apps/core/**` y es la **autoridad del contrato RPC** de abajo.
> Ambos comparten el mismo workspace y la rama `feat/e10-desktop-electron`.

## 0. Empieza por aquí (contexto)
1. Lee `CLAUDE.md` (raíz) — guía del proyecto, decisiones inmutables, reglas de código.
2. Estás en el repo **SKuger/CKounting** (privado), local en `/home/samuel/Documentos/proyects/Dandelyon/Contab`.
3. Reglas de oro del repo (NO negociables):
   - **Los commits NO llevan trailer `Co-Authored-By`.** (regla del repo)
   - Mensajes de UI y errores **en español (Colombia)**.
   - No renombrar los headers del Excel DIAN (**D-039**).
   - En `.vue`/`.ts` solo **tokens semánticos** del design system Órbita (shadcn/Tailwind v4), **nada de hex crudo** salvo SVGs de marca.
   - Preguntar en **opción múltiple** antes de implementar algo no decidido.
4. Dev server: `cd apps/desktop && npm run dev` → http://localhost:3000. Tras cambiar Python: `pkill -f 'contab_core.sidecar'`.
5. **Propiedad de archivos (anti-conflicto):** Track 2 edita SOLO `apps/desktop/**`, `apps/shell/**`, `apps/dian-rut/**`. NO toques `apps/core/**` (es de Track 1) ni `apps/shell/package.json` versión (la sube Track 1 al integrar).

## 1. Objetivo de 0.1.4 (8 mejoras)
1. Organización por **mes/año** (imports + carpeta de soportes por mes).
2. **Mover** documentos entre meses + **editar** mes + **papelera** (soft-delete; quedan en BD, ocultos del front).
3. **Renovar UI** para un usuario NO técnico + sección de **Ayuda/Instrucciones**.
4. **DIAN sin terminal**: el programa abre Chrome en modo depuración con un botón.
5. **"Salir"** (hoy "Cerrar sesión") cierra el programa.
6. **Persistir el usuario** creado (no se pierde al cerrar) → vive en la BD del programa.
7. **Quitar el badge "3"** de la campana (y las notificaciones mock).
8. **BD del programa** (`contab.db`) fundacional: usuario, ajustes, registro central de empresas (+ espacio para firmas/correos/fechas).

## 2. Decisiones cerradas (confirmadas por el usuario)
- **Arquitectura de dos niveles** (D-003 intacto): `contab.db` global (programa) + **una `.db` por empresa** (datos fiscales aislados). NO monolito.
- **Periodo** = mes calendario `YYYY-MM`. **Cada mes tiene su propio Excel + su propia carpeta de soportes (PDFs)**. La validación cruza el Excel del mes contra la carpeta de ese mes. Se pueden **mover documentos** entre meses y mandarlos a **papelera**.
- Entrega: **todo junto en 0.1.4**.
- `contab.db` alcance: **usuario + ajustes + registro central de empresas** (con espacio para firmas/correos/fechas).

## 3. Arquitectura
```
%APPDATA%/Contab/               (contabDataDir; en Linux dev ~/.local/share/Contab)
├── contab.db                   ← BD del PROGRAMA (Track 1)  · user, settings, empresa(registro)
└── empresas/<nit>_<slug>.db    ← una por empresa (D-003)    · excel_load/row, validaciones, periodos
```
- `contab.db` guarda lo transversal (usuario, ajustes, catálogo de empresas + metadatos futuros).
- Cada `.db` de empresa guarda sus datos fiscales, ahora etiquetados por **periodo** y con **papelera**.
- La carpeta de soportes pasa de ser **una por empresa** a **una por periodo** (tabla `periodo_folder`).

---

## 4. CONTRATO RPC (interfaz compartida — autoridad: Track 1)
> Track 2 programa contra estos nombres/params/returns. Si necesitas cambiar algo, avísale a Track 1.
> Todo va por `rpc('<method>', {...params})` (composable `useRpc`, POST `/api/rpc`). Las subidas de
> archivos siguen usando endpoints dedicados (`/api/upload-excel`, etc.). Errores llegan como `Error(message)`.

### 4.1 BD del programa (contab.db) — SIN `db_path`
| método | params | returns |
|---|---|---|
| `program_get_user` | `{}` | `{ user: {name, email, created_at, updated_at} \| null }` |
| `program_save_user` | `{ name?, email? }` | `{ user }` |
| `program_get_settings` | `{}` | `{ settings: {…kv} }` |
| `program_save_settings` | `{ patch: {…} }` | `{ settings }` |
| `program_list_empresas` | `{ include_archived?=false }` | `[ {empresa_id, nit, dv, razon_social, db_path, created_at, last_opened_at, archived:bool} ]` |
| `program_touch_empresa` | `{ db_path }` | `{ ok:true }`  *(actualiza last_opened_at)* |

*(Track 1 hace que `create_empresa` registre en `contab.db` y que un `program_sync_registry` interno registre las empresas existentes al arrancar. Track 2 usa `program_list_empresas` como catálogo en `index.vue`.)*

### 4.2 Por empresa — periodos, soportes por mes, papelera
| método | params | returns |
|---|---|---|
| `list_periodos` | `{ db_path, include_deleted?=false }` | `[ {periodo:'YYYY-MM', load_count, row_count, pdfs_folder\|null, indexed_cufe_count} ]` (desc) |
| `set_periodo_pdfs_folder` | `{ db_path, periodo, folder\|null }` | `{ periodo, pdfs_folder }` |
| `set_load_periodo` | `{ db_path, load_id, periodo }` | `{ load_id, periodo }` |
| `move_rows_periodo` | `{ db_path, load_id, row_indexes:[int], periodo }` | `{ moved:int, periodo }` |
| `soft_delete_rows` | `{ db_path, load_id, row_indexes:[int] }` | `{ deleted:int }` |
| `restore_rows` | `{ db_path, load_id, row_indexes:[int] }` | `{ restored:int }` |
| `soft_delete_load` | `{ db_path, load_id }` | `{ load_id, deleted:true }` |
| `restore_load` | `{ db_path, load_id }` | `{ load_id, deleted:false }` |

### 4.3 Comandos EXISTENTES que cambian de forma (mismo nombre)
- `import_excel` `{ db_path, source_path, periodo? }` → además de lo actual, ahora **asigna periodo por fila** (derivado de `Fecha Emisión`, `YYYY-MM`; o el `periodo` forzado). Return incluye `{ …, periodo }` (mes dominante del lote).
- `list_loads` `{ db_path, periodo?, include_deleted?=false }` → cada carga ahora incluye `periodo` y `deleted:bool`; filtra papelera por defecto.
- `get_load_rows` `{ db_path, load_id, offset?, limit?, include_deleted?=false }` → **cada fila del array `rows` ahora incluye `row_index` (explícito) y `periodo`**; excluye borradas por defecto. **IMPORTANTE (Track 2):** mapea fallas/overrides por `row.row_index`, **NO por la posición del array** (antes se asumía posición == row_index; con filtros eso se rompe).
- `run_validations` `{ db_path, load_id, run_v3?=true }` → ahora valida el lote contra **la carpeta de soportes de SU periodo** (`periodo_folder`), no la carpeta global de la empresa; excluye filas en papelera de conteos; `failures[].row_index` es el persistido.
- `export_no_conformes` / `export_missing_supports` → excluyen filas en papelera; usan la carpeta del periodo.

*(Nota: `set_pdfs_folder` global de empresa queda como fallback/compat; el modelo nuevo es por periodo.)*

---

## 5. Track 2 — tareas (Frontend + shell + DIAN) · el OTRO Claude
Trabaja en `apps/desktop/**`, `apps/shell/**`, `apps/dian-rut/**`. Commits pequeños por sub-tarea, sin trailer.

### T2.1 · BD del programa en el front
- `apps/desktop/app/composables/useUser.ts` (o el que exista): persistir vía `program_get_user`/`program_save_user` en vez de memoria/localStorage. El usuario NO debe perderse al cerrar.
- `apps/desktop/app/composables/usePrefs.ts`: opcionalmente respaldar en `program_get/save_settings` (mantener localStorage como caché).
- `apps/desktop/app/pages/index.vue`: listar empresas con `program_list_empresas` (catálogo central) en vez del folder-scan directo; al abrir una empresa, `program_touch_empresa`.

### T2.2 · "Salir" cierra el programa (#5) + limpieza de UI ficticia (#7)
- `apps/shell/src/preload.js`: exponer `window.contab.quit()` (`ipcRenderer.send('app:quit')`).
- `apps/shell/src/main.js`: `ipcMain.on('app:quit', () => app.quit())`.
- `apps/desktop/app/components/SidebarUser.vue`: renombrar "Cerrar sesión" → **"Salir de Contab"**, que llame `window.contab?.quit()` (en navegador dev: no-op o cerrar pestaña). **Quitar** el gestor multi-cuenta / "Añadir cuenta" (D-004 sin auth); dejar solo **Preferencias + Salir**.
- `apps/desktop/app/layouts/default.vue`: **quitar** las notificaciones mock y el badge "3" de la campana (líneas ~36-40, 124-147). Quitar/neutralizar `SystemBeacon` (estado ficticio) o cablearlo a algo real (p.ej. sidecar activo).

### T2.3 · Organización por mes en la empresa (#1, #2)
- `apps/desktop/app/pages/empresa.vue`: reorganizar el detalle **por periodos (meses)**. Cada mes muestra: su Excel importado + su **carpeta de soportes** (elegir con `DirectoryPicker` → `set_periodo_pdfs_folder`) + estado de indexado + botón validar. Usa `list_periodos`.
- `apps/desktop/app/pages/load.vue`: mapear fallas/overrides por `row.row_index` (viene explícito). Acciones por fila/selección: **mover de mes** (`move_rows_periodo`) y **enviar a papelera** (`soft_delete_rows`); vista de **papelera** con **restaurar** (`restore_rows`). Filtrar borradas.
- Considerar mover la elección de "carpeta de soportes" desde el nivel empresa al nivel mes.

### T2.4 · Humanizar (#3) + Ayuda
- Mostrar **nombre** de carpeta (no ruta absoluta) con la ruta en tooltip; quitar `load_id=`, filename `.db` y rutas crudas de textos visibles.
- Errores: reemplazar `String(exc)` por mensajes en español accionables (mapear en `useToast`/call-sites).
- Empty states → **pasos guiados** (crear→carpeta→importar→validar→exportar). Reemplazar `confirm()` nativo por `Dialog` del design system.
- **Sección Ayuda**: nueva ruta `apps/desktop/app/pages/ayuda.vue` con `Tabs` (hoy sin uso): Primeros pasos, Cargar Excel, Carpeta de soportes por mes, Validaciones (qué es V1/V2/V3 y "no conformes" en llano), Exportar, Consulta DIAN, FAQ. Registrar el ítem en el array `nav` de `default.vue` (se propaga a ⌘K y breadcrumb).
- Componente `apps/desktop/app/components/HelpHint.vue` (botón "?" + Popover/Tooltip) junto a la jerga (CUFE, V1/V2/V3, NIT/DV, papelera…).

### T2.5 · DIAN sin terminal (#4) — lo más crítico para el cliente
- `apps/desktop/server/utils/chromeLauncher.ts` (NUEVO): descubrir el ejecutable por SO — win32: `%ProgramFiles%/Google/Chrome/Application/chrome.exe`, `(x86)`, `%LOCALAPPDATA%/…`; fallback **Edge** (`msedge.exe`); darwin: `/Applications/Google Chrome.app/Contents/MacOS/Google Chrome`; linux: `google-chrome`/`chromium` en PATH.
- `apps/desktop/server/api/dian/launch-browser.post.ts` (NUEVO): spawnea Chrome `{ detached:true, stdio:'ignore' }` + `unref()` con flags `--remote-debugging-port=9222 --remote-debugging-address=127.0.0.1 --user-data-dir=<perfil escribible dedicado> --no-first-run --no-default-browser-check`. Perfil escribible: `%APPDATA%/Contab/dian/chrome-debug-profile` (usa `DIAN_WORKDIR`/contabDataDir). Antes de lanzar, sondear `http://127.0.0.1:9222/json/version` (si ya corre, no relanzar). Return `{ launched|already_running|not_found }`.
- `apps/desktop/app/pages/consulta-dian.vue`: **quitar** el `CHROME_CMD` Linux hardcodeado (línea 8) y el bloque de terminal. Poner botón **"Abrir navegador para la DIAN"** → `POST /api/dian/launch-browser` → luego polling de `checkBrowserMode()` hasta verde. Dejar el comando manual solo como "ayuda avanzada" **generado por SO** (chrome.exe + `%USERPROFILE%` en Windows). Reemplazar la consola de logs cruda por pasos en lenguaje humano.
- `apps/dian-rut/scraper.py` (línea ~135) y `apps/dian-rut/main.py` (sonda): alinear a **`127.0.0.1`** (no `localhost`) para evitar el problema IPv6 en Windows. `apps/dian-rut/dian_paths.py`: si hace falta, exponer el dir del perfil de depuración.

### T2.6 · Notas de decisiones de Track 2
Anota tus decisiones nuevas en la sección "## Track 2 notes" al final de este archivo (Track 1 las consolidará en `docs/decisions.md` al integrar, para no chocar en ese archivo).

---

## 6. Track 1 — tareas (Backend / apps/core) · primer Claude [referencia]
- `program_db.py` (NUEVO): esquema + handlers de `contab.db` (user, settings, registro de empresas). `program_sync_registry` al arrancar. `create_empresa` registra en el catálogo.
- `storage.py`: migración idempotente — `excel_load`/`excel_row` ADD `periodo TEXT`, `deleted_at TEXT`; nueva tabla `periodo_folder(periodo PK, pdfs_folder)`. Extender `_run_migrations` para inspeccionar esas tablas.
- `excel.py`: derivar `periodo` de `Fecha Emisión` al persistir; `fetch_load_rows` devuelve `row_index` + `periodo`, filtra `deleted_at IS NULL`.
- `sidecar.py`: registrar todos los handlers nuevos (§4). `run_validations`/`export_*` usan la carpeta del periodo y excluyen papelera. `get_load_rows` transporta `row_index`.
- `paths.py`: ruta de `contab.db` (contabDataDir). Tests en `apps/core/tests/`.

## 7. Coordinación / integración / git
- **Contrato**: autoridad Track 1. Cambios → coordinar antes de tocar.
- **Ownership estricto**: Track 1 = `apps/core/**`; Track 2 = `apps/desktop/**` + `apps/shell/**` + `apps/dian-rut/**`. Nadie edita fuera de su árbol.
- **No** bumpear `apps/shell/package.json` (versión) — lo hace Track 1 al integrar (→ 0.1.4) + tag + build.
- `docs/decisions.md`, `docs/plan.md`, `docs/session_log.md`: los consolida Track 1 al final (evita conflictos).
- Commits pequeños por sub-tarea, en `feat/e10-desktop-electron`, **sin** `Co-Authored-By`.
- Verificación: Track 1 corre `cd apps/core && .venv/bin/pytest tests/ -q`; Track 2 corre `npm run dev` y prueba flujos; al integrar, smoke test conjunto.

## 8. Verificación de aceptación (0.1.4)
- Crear usuario → cerrar app → reabrir → **el usuario persiste**.
- Empresa con 2 meses: cada mes su Excel + su carpeta de soportes; validar cruza contra la carpeta del mes.
- Mover un documento de mes; mandarlo a papelera → desaparece del front pero sigue en BD; restaurar.
- "Salir" cierra el programa. La campana **sin** badge "3".
- Consulta DIAN: botón abre Chrome en modo depuración **sin terminal** (Windows) y la sesión se detecta.
- Ayuda accesible con lenguaje llano.

## Track 2 notes
<!-- El segundo Claude anota aquí sus decisiones/dudas para consolidación. -->
