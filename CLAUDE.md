# Contab — Guía para Claude

Software de contabilidad multi-empresa para escritorio (Windows). Este archivo es el punto de entrada que Claude debe leer en cada sesión.

## Estado actual (último update 2026-09-21 — revisión completa del repo, sesión 9)

- **E1 completada ✅** end-to-end con muestras reales del usuario. Ver [`docs/session_log.md`](docs/session_log.md) para el resumen detallado.
- **158 tests Python + 33 de frontend (vitest) + 7 de smoke end-to-end, todos verdes.** Cubren el parser del Excel, los importes en Decimal, el DV, V1/V2/V3, la extracción de CUFE (texto + QR), el índice de PDFs, las migraciones de esquema, el ciclo de vida de una empresa, los trabajos en segundo plano y la credencial local.
  - El fallo de `test_extracts_expected_cufe[…MOVISTAR…]` que se atribuía a `cv2.QRCodeDetector` **no era del detector**: el renderizado iba por `bitmap.to_pil()`, que importa Pillow — una dependencia no declarada. Arreglado en D-090.
- **Los tests, ruff y el typecheck se corren solos** en push/PR (`.github/workflows/test.yml`). En `apps/desktop`: `npm test` (vitest) y `npm run typecheck`. En `apps/shell`: `npm run e2e` — smoke contra el Electron REAL (D-095), que es lo único que ve la cadena completa Electron → Nitro → sidecar Python → preload → credencial. `conftest.py` aísla `paths.data_dir` en un tmp_path: sin eso, en Windows la suite escribía (y borraba) en `%APPDATA%\Contab` real.
- **Plan de Cuentas (PUC) por empresa (0.2.0, D-070)**: página `/puc` (desde la card en `empresa.vue`); sube el dump Excel (upsert por código = fusionar; bloquea si el NIT no coincide), edita/archiva/agrega cuentas, exporta. Módulo `puc.py`, tablas `puc_account`/`puc_import`, RPCs `puc_import`/`puc_list`/`puc_save_account`/`puc_archive_account`/`puc_delete_account`/`puc_export`, endpoint `upload-puc`.
- **Extracción CUFE robusta (D-067)**: reconstruye el CUFE por segmentos hex (no pega el nº de autorización) + QR como verificación de lecturas dudosas + `extractor_version` que re-extrae el caché viejo. **Panel "Soportes del mes" (D-068)**: en Carga, ve cuáles PDFs tienen/no tienen CUFE y re-verifica sin re-subir el Excel.
- **Renombrar soportes (D-066)**: en Carga, renombra los PDF del mes al patrón `DD-MM_NIT_RAZON-SOCIAL_FACTURA` con manifiesto reversible.
- **Dev server**: `cd apps/desktop && npm run dev` → http://localhost:3000. El sidecar Python se levanta automáticamente como subprocess.
- **Consultas DIAN (0.1.5)**: el sidebar agrupa **Terceros** (scraper Playwright, `apps/dian-rut`, contra `muisca.dian.gov.co` — **sin WAF ni captcha delante**, al contrario que el catálogo de factura electrónica; ver [`docs/dian-portal.md`](docs/dian-portal.md)) e **Inconsistencias** (nueva — razón social por NIT+DV vía sidecar `apps/core`, **HTTP plano sin navegador**, MUISCA `DefSelPublicacionesExterna.faces`). RPCs: `parse_nit_dv`, `consulta_inconsistencias`, `export_inconsistencias`. Ver D-065.
- **Próximo natural (2026-09-21)**: la **Fase 1 del plan de automatización** — [`plans/dian-siigo-automation-plan.md`](plans/dian-siigo-automation-plan.md). El objetivo del plan es llevar el mes del contador desde la DIAN hasta Siigo con él aprobando, no tecleando: cimientos (perfil fiscal, terceros, tablero multiempresa) → ingesta automática del portal → el XML como fuente de verdad → causación asistida → puente a Siigo con reconciliación inversa. Sigue el modelo de planes de `Interval-Col/.github` (frontmatter v2.1, `✅ Done-when` por fase, `🚦 Checkpoint` como alto obligatorio **también en modo auto**, y `🛑 HUMAN DECISION` que un agente no puede resolver solo).

## Qué es Contab

Aplicativo de escritorio que ayuda al contador a procesar la contabilidad de **varias empresas**. Hasta 0.2.1 trabajaba solo sobre los **reportes que el usuario descarga manualmente** de la DIAN y los **soportes que envía el cliente** (encargado dentro de cada empresa). **Desde D-097 (2026-09-21) eso cambia**: la descarga desde el portal de la DIAN entra al alcance por tres caminos (`token`, `robot`, `manual`), y el envío a Siigo por su API (D-099). La subida manual del Excel se conserva como piso, no como único camino.

El primer flujo concreto, implementado en E1, es el **cruce DIAN ↔ soportes**: cargar el reporte Excel de la DIAN, visualizarlo, aplicar tres validaciones definidas con el usuario y exportar las filas que no cumplen. La Validación 1 cruza el CUFE/CUDE de cada fila contra los PDFs de una carpeta de soportes (extracción real con pdftotext + cv2 QR scan).

## Stack final

- **Desktop shell**: **Electron** en [`apps/shell/`](apps/shell/) (E10, en curso — D-057, supersede el Tauri original D-002). Electron arranca el servidor Nitro como child_process (Node embebido) y éste lanza los sidecars; en dev seguimos corriendo en navegador (`npm run dev`).
- **Frontend**: Nuxt 4 (Vue + TypeScript) en `apps/desktop/`, `ssr: false`.
  - **Design system Dandelyon · Órbita** (D-053): tokens shadcn + Tailwind v4 + reka-ui + shadcn-nuxt + @nuxt/fonts. Look horneado con `.theme-orbita` + `data-*` en `<html>`; composable `useBrand()` reemplaza el store del playground. Contrato de tokens en [`apps/desktop/app/assets/css/main.css`](apps/desktop/app/assets/css/main.css). Regla de oro: solo tokens semánticos en `.vue`/`.ts`, nada de hex crudo (salvo SVGs de marca).
  - **Toda la app migrada** (D-054): shell (sidebar + topbar Órbita) **y** páginas (Empresas, Carga, Consulta DIAN) + `DirectoryPicker`/`ToastContainer`, todo sobre tokens/shadcn (cero hex crudo salvo SVGs de marca).
  - `@tanstack/vue-table` (tabla headless). `DirectoryPicker` propio (modal navegable server-side via `/api/list-dir`).
- **Backend / lógica de negocio**: Python 3.10+ como *sidecar* en `apps/core/`.
  - IPC stdio JSON-lines (D-019).
  - Deps: `openpyxl`, `xlsxwriter`, `pypdfium2`, `opencv-python-headless`, `numpy`. **Pillow NO** (D-090): el renderizado usa `bitmap.to_numpy()`, no `to_pil()`. Figuraba aquí sin estar en `pyproject.toml`, y eso rompía en silencio la lectura por QR.
  - Binario de sistema requerido: `pdftotext` (Poppler) — viene con la mayoría de distros.
- **Base de datos**: SQLite — **un archivo .db por empresa** (aislamiento total, D-003).
- **Empaquetado** (E10, en curso): **Electron + electron-builder** (NSIS Windows per-user). Sidecars como `.exe` PyInstaller (onedir) + Poppler bundleado; el shell los inyecta a Nitro por env (`CONTAB_SIDECAR_BIN`, `DIAN_SIDECAR_BIN`, `CONTAB_PDFTOTEXT`, `DIAN_WORKDIR`). Build en GitHub Actions `windows-latest`; auto-update con electron-updater (sin firma Authenticode → integridad sha512; hosting de releases por decidir). Ver D-057/058/059 y [`apps/shell/README.md`](apps/shell/README.md).

## Decisiones inmutables (no re-preguntar)

> Estas decisiones ya las tomó el usuario. Si una nueva idea las contradice, **avisar y pedir confirmación explícita** antes de cambiarlas.

- Una **DB SQLite por empresa**, nunca mezclar datos entre empresas (D-003).
- **Sin auth** en las primeras entregas (single-user) (D-004).
- Reportes DIAN llegan en **Excel y PDF** — Excel para datos, PDF como soporte (D-005).
- Salida de reportes: **Excel `.xlsx`** con las columnas originales + 4 derivadas + `razon_falla` (D-006, D-014, D-024). `Base IVA` usa la **tarifa detectada** (19% o 5%), no siempre 19% — D-093 supersede D-046, confirmado por el usuario.
- Idioma de la UI: **Español (Colombia)** (D-009).
- Contexto fiscal: **Colombia / DIAN** (D-009).
- **Un solo identificador por PDF** con prioridad CUDS > CUDE > CUFE (D-033).
- **Auto-listado de archivos** en `default_folder` y `pdfs_folder` — el usuario no escribe rutas, las elige con picker o las ve listadas (D-036).
- **Auto-indexing** de PDFs en `run_validations` y `export_no_conformes` (D-037). El botón "Re-indexar" es solo para depurar.
- **Contab es el puente; Siigo es el libro contable** (D-096). Contab controla, causa y exporta; los libros oficiales, los estados financieros y la partida doble los hace Siigo. **E6 y E7 quedan aparcadas.**
- **Tres caminos de ingesta DIAN** —`token`, `robot`, `manual`— hacia una sola interfaz; el manual **nunca se retira** (D-097).
- **No se guarda ningún acceso a la DIAN** (D-133, supersede D-098): el portal manda un enlace de un solo uso al correo; vive en memoria durante la corrida y nunca toca la `.db`, el log ni un error.
- **El puente a Siigo arranca por el archivo de importación de comprobantes** que el contador ya sube (D-128): estructura en `docs/siigo-import-structure.md`, exportador en `siigo.py`, cuentas e impuestos desde el catálogo de Siigo de cada empresa (D-129). La API de Siigo Nube con idempotencia por CUFE (D-099, D-103) queda **aplazada, no derogada**: el archivo no se lee de vuelta, así que la reconciliación inversa sigue pendiente.
- **El envío a Siigo va por tipo de documento** (D-103): `/purchases` para factura recibida, `/purchase-support-documents` para el documento soporte, `/journals` para lo que no encaje. Auth `POST /auth` (JWT 24 h) + header `Partner-Id`. Las cuentas viajan por **código PUC** (sin tabla de mapeo); **no hay campo de referencia externa**, así que la idempotencia vive en `siigo_envio` y se verifica listando el periodo.
- **Los terceros viven por empresa**, no en un catálogo central (D-100) — D-003 sin excepciones.
- **Toda corrida de ingesta la dispara el contador** (D-101). Sin programador ni ejecución nocturna.
- **Las tarifas, la UVT y las bases mínimas se importan de un Excel del usuario** (D-102), con el patrón de `puc.py`. Un agente no las siembra de memoria.

Catálogo completo (103 entradas) → [`docs/decisions.md`](docs/decisions.md).

## Cómo trabajamos juntos

- **Plan vivo**: roadmap en [`docs/plan.md`](docs/plan.md). E1 cerrada, E3/E4 reducidas. Próxima sugerida: E2 o E5.
- **Preguntas siempre en opción múltiple**. El usuario prefiere `AskUserQuestion` con 2-4 opciones a preguntas abiertas. Antes de implementar algo no decidido, preguntar.
- Cuando el usuario dice *"te voy a pasar un Excel de muestra"* o *"te guío en este punto"*, **detenerse y esperar el input** antes de inventar columnas, validaciones o estructuras.
- Los datos de prueba en `docs/samples/` son **falsos** (sin PII real) y se pueden commitear.

### Nada de modales para formularios (norma, 2026-09-28)

**No se usan modales.** Todo formulario —editar, crear, configurar, listar— se abre
como un **panel expansible** que despliega y repliega el mismo botón que lo invoca.

- El panel vive **en su sitio**: lo grande (traer de la DIAN, un listado) se expande
  como una banda a lo ancho, bajo la cabecera; lo pequeño (una ficha del panel
  lateral) se expande dentro de su propia tarjeta.
- Solo uno abierto a la vez, y el botón que lo abrió lo cierra.
- **Por qué**: un modal tapa el contexto justo cuando se necesita —configurar el
  perfil fiscal mientras se mira el mes, o pegar el enlace mientras se ve qué mes
  falta— y obliga a cerrarlo para comprobar cualquier cosa. El panel deja ver lo de
  atrás y no roba el foco de la página.

### El libro de avance (norma, 2026-09-21)

Hay un **libro de avance publicado como artifact**, que es donde el dueño mira cómo va el plan sin abrir el repo:

**https://claude.ai/artifact/QndrGPnMCXiF5hTXfUD5hU**

- **Se actualiza al cerrar cada sub-fase** (cada tarea numerada del plan: 1.1, 1.2, 1.3…), no al cerrar la fase entera. Cerrar una sub-fase y no republicar deja el libro mintiendo.
- Lo que hay que mover en cada actualización: las celdas de la tarea en el mapa, el marcador de arriba (cerradas / sin empezar / espera a una persona), el ancho de la barra, la entrada de la cabecera si el hallazgo lo merece, y **una línea nueva en «El recorrido»**.
- **La fuente NO está en el repo.** El HTML vive en el scratchpad de la sesión que lo publicó, que no sobrevive. Para actualizarlo desde una sesión nueva: `Artifact` con `action: "read"` sobre esa URL, reconstruir sobre el archivo que devuelve, y republicar pasando la **misma URL** en `url` — publicar sin `url` crea un artifact nuevo y parte el historial en dos.
- El tono no es de informe corporativo: se nombra lo que costó encontrar y lo que salió mal, con el número y el detalle concreto. Un libro que solo dice «avanzamos» no sirve para decidir nada.

## Estructura del repo

```
Contab/
├── CLAUDE.md              ← este archivo
├── README.md              ← guía de setup + flujo de prueba
├── apps/
│   ├── core/              ← Python sidecar
│   │   ├── contab_core/
│   │   │   ├── sidecar.py     stdio JSON-lines IPC loop + registro de RPCs
│   │   │   ├── jobs.py        trabajos en segundo plano con progreso (D-076)
│   │   │   ├── money.py       importes en Decimal, redondeo contable (D-075)
│   │   │   ├── log.py         registro a stderr (D-083)
│   │   │   ├── storage.py     schema SQLite + migraciones numeradas (D-084)
│   │   │   ├── program_db.py  contab.db: usuario, ajustes, catálogo de empresas
│   │   │   ├── backup.py      backup/restore + papelera de empresas (D-078)
│   │   │   ├── excel.py       parser DIAN + columnas derivadas
│   │   │   ├── validations.py V1/V2/V3
│   │   │   ├── export.py      xlsxwriter (no conformes)
│   │   │   ├── pdf_cufe.py    extracción CUFE (pdftotext + cv2 QR) + indexer
│   │   │   ├── puc.py         Plan Único de Cuentas por empresa (D-070)
│   │   │   ├── rename_soportes.py  renombrado de PDFs (D-066)
│   │   │   ├── dian_inconsistencias.py  consulta MUISCA por NIT+DV
│   │   │   ├── paths.py       carpetas por SO
│   │   │   └── nit.py         DV módulo 11 DIAN
│   │   ├── tests/             158 tests
│   │   ├── .venv/             venv del proyecto (NO commitear)
│   │   └── pyproject.toml     deps + config de ruff
│   └── desktop/           ← Nuxt 4 frontend
│       ├── app/
│       │   ├── pages/         index / empresa / load
│       │   ├── components/    DirectoryPicker
│       │   ├── layouts/       default
│       │   ├── composables/   useRpc / useJob / useToast / useBrand
│       │   ├── plugins/       auth.client (credencial en cada petición)
│       │   └── assets/css/    main.css (theme tokens)
│       ├── server/
│       │   ├── api/           rpc.post / upload-*.post / list-dir.get
│       │   ├── middleware/    auth (credencial local, D-089)
│       │   └── utils/         sidecar, dianSidecar, uploads, auth
│       ├── test/              33 tests (vitest)
│       ├── nuxt.config.ts
│       └── package.json
├── plans/
│   └── dian-siigo-automation-plan.md   ← plan de automatización DIAN → Siigo (modelo .github)
└── docs/
    ├── plan.md            ← roadmap por entregas
    ├── decisions.md       ← registro completo (94 entradas)
    ├── glosario.md        ← términos DIAN / contables
    ├── excel-structure.md ← estructura verificada del Excel DIAN
    ├── session_log.md     ← bitácora de sesiones
    └── samples/           ← Excel + 6 PDFs (datos falsos)
        ├── Ejemplo_LaDian.xlsx
        └── pdfs/          ← los 6 PDFs de soporte
```

## Reglas de código

- **No introducir features fuera del alcance de la entrega actual.** Si surge algo útil para una entrega futura, anotarlo en `docs/plan.md` y seguir.
- **No mezclar empresas.** Toda query/operación recibe explícitamente el `db_path` de la empresa. Nunca usar una conexión "global".
- Comentarios solo cuando el *por qué* no es obvio. Nada de comentarios narrativos sobre el código.
- Mensajes de UI y errores de cara al usuario: **en español**.
- Nombres internos (variables, funciones, tablas): **inglés** salvo términos contables colombianos sin traducción razonable (`rut`, `nit`, `dian`, etc).
- Nunca renombrar headers del Excel DIAN (D-039). El parser preserva los nombres originales en BD y export.

## Cuando termines una entrega

1. Marcar la entrega como `✅ Completada` en [`docs/plan.md`](docs/plan.md) con fecha.
2. Anotar en [`docs/decisions.md`](docs/decisions.md) cualquier decisión nueva que haya surgido durante la implementación.
3. Listar al usuario qué puede probar **ya mismo** en esa entrega (instrucciones concretas, no genéricas).
4. Actualizar [`docs/session_log.md`](docs/session_log.md) con el resumen de la sesión.
5. Preguntarle (opción múltiple) qué quiere abordar a continuación.

### Antes de publicar un release

Subir el instalador al **programa de whitelisting de Avast** antes de publicar, no
después de que el usuario vea el cartel de «programa sospechoso». El instalador no
va firmado (D-059) y lleva dos ejecutables de PyInstaller, así que cada versión
nueva vuelve a saltar. Procedimiento y texto listo en
[`docs/antivirus.md`](docs/antivirus.md).

## Cuando cierres una sub-fase del plan de automatización

1. Marcar la tarea como `[x]` en [`plans/dian-siigo-automation-plan.md`](plans/dian-siigo-automation-plan.md).
2. **Actualizar el libro de avance** (ver la norma arriba). Es parte de cerrar, no un extra.
3. Parar y mostrar qué quedó: el modo auto va por *slice*, no por plan entero.

## Comandos útiles para arranque rápido

```bash
# Tests Python
cd apps/core && .venv/bin/pytest tests/ -q

# Dev server
cd apps/desktop && npm run dev

# Forzar respawn del Python sidecar (al cambiar código Python)
pkill -f 'contab_core.sidecar'   # el siguiente request lo levanta

# Reset del cache de CUFEs en la empresa de prueba
DB="$HOME/.local/share/Contab/empresas/900181831_real-seguros-ltda.db"
# (en VSCode snap: $HOME/snap/code/240/.local/share/Contab/...)
sqlite3 "$DB" "DELETE FROM pdf_cufe_index;"
```
