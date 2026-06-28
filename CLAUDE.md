# Contab — Guía para Claude

Software de contabilidad multi-empresa para escritorio (Windows). Este archivo es el punto de entrada que Claude debe leer en cada sesión.

## Estado actual (último update 2026-05-28)

- **E1 completada ✅** end-to-end con muestras reales del usuario. Ver [`docs/session_log.md`](docs/session_log.md) para el resumen detallado.
- **37/37 tests Python verdes** (Excel parser, NIT DV, V1/V2/V3, PDF CUFE extraction incluido QR scan).
- **Dev server**: `cd apps/desktop && npm run dev` → http://localhost:3000. El sidecar Python se levanta automáticamente como subprocess.
- **Próximo natural**: E2 (catálogo de empresas robusto) o E5 (PUC + terceros). Ver `## Próxima sesión` en `docs/plan.md`.

## Qué es Contab

Aplicativo de escritorio que ayuda al contador a procesar la contabilidad de **varias empresas**. El alcance inicial NO incluye conexión a la DIAN ni uso de su token: trabajamos sobre los **reportes que el usuario descarga manualmente** de la DIAN y los **soportes que envía el cliente** (encargado dentro de cada empresa).

El primer flujo concreto, implementado en E1, es el **cruce DIAN ↔ soportes**: cargar el reporte Excel de la DIAN, visualizarlo, aplicar tres validaciones definidas con el usuario y exportar las filas que no cumplen. La Validación 1 cruza el CUFE/CUDE de cada fila contra los PDFs de una carpeta de soportes (extracción real con pdftotext + cv2 QR scan).

## Stack final

- **Desktop shell**: Tauri (Rust) — pendiente para E10. Hoy corremos en navegador.
- **Frontend**: Nuxt 4 (Vue + TypeScript) en `apps/desktop/`, `ssr: false`.
  - **Design system Dandelyon · Órbita** (D-053): tokens shadcn + Tailwind v4 + reka-ui + shadcn-nuxt + @nuxt/fonts. Look horneado con `.theme-orbita` + `data-*` en `<html>`; composable `useBrand()` reemplaza el store del playground. Contrato de tokens en [`apps/desktop/app/assets/css/main.css`](apps/desktop/app/assets/css/main.css). Regla de oro: solo tokens semánticos en `.vue`/`.ts`, nada de hex crudo (salvo SVGs de marca).
  - **Toda la app migrada** (D-054): shell (sidebar + topbar Órbita) **y** páginas (Empresas, Carga, Consulta DIAN) + `DirectoryPicker`/`ToastContainer`, todo sobre tokens/shadcn (cero hex crudo salvo SVGs de marca).
  - `@tanstack/vue-table` (tabla headless). `DirectoryPicker` propio (modal navegable server-side via `/api/list-dir`).
- **Backend / lógica de negocio**: Python 3.10+ como *sidecar* en `apps/core/`.
  - IPC stdio JSON-lines (D-019).
  - Deps: `openpyxl`, `xlsxwriter`, `pypdfium2`, `opencv-python-headless`, `numpy`, `Pillow`.
  - Binario de sistema requerido: `pdftotext` (Poppler) — viene con la mayoría de distros.
- **Base de datos**: SQLite — **un archivo .db por empresa** (aislamiento total, D-003).
- **Empaquetado**: `tauri build` para Windows (pendiente E10).

## Decisiones inmutables (no re-preguntar)

> Estas decisiones ya las tomó el usuario. Si una nueva idea las contradice, **avisar y pedir confirmación explícita** antes de cambiarlas.

- Una **DB SQLite por empresa**, nunca mezclar datos entre empresas (D-003).
- **Sin auth** en las primeras entregas (single-user) (D-004).
- Reportes DIAN llegan en **Excel y PDF** — Excel para datos, PDF como soporte (D-005).
- Salida de reportes: **Excel `.xlsx`** con las columnas originales + 3 derivadas + `razon_falla` (D-006, D-014, D-024).
- Idioma de la UI: **Español (Colombia)** (D-009).
- Contexto fiscal: **Colombia / DIAN** (D-009).
- **Un solo identificador por PDF** con prioridad CUDS > CUDE > CUFE (D-033).
- **Auto-listado de archivos** en `default_folder` y `pdfs_folder` — el usuario no escribe rutas, las elige con picker o las ve listadas (D-036).
- **Auto-indexing** de PDFs en `run_validations` y `export_no_conformes` (D-037). El botón "Re-indexar" es solo para depurar.

Catálogo completo (40 entradas) → [`docs/decisions.md`](docs/decisions.md).

## Cómo trabajamos juntos

- **Plan vivo**: roadmap en [`docs/plan.md`](docs/plan.md). E1 cerrada, E3/E4 reducidas. Próxima sugerida: E2 o E5.
- **Preguntas siempre en opción múltiple**. El usuario prefiere `AskUserQuestion` con 2-4 opciones a preguntas abiertas. Antes de implementar algo no decidido, preguntar.
- Cuando el usuario dice *"te voy a pasar un Excel de muestra"* o *"te guío en este punto"*, **detenerse y esperar el input** antes de inventar columnas, validaciones o estructuras.
- Los datos de prueba en `docs/samples/` son **falsos** (sin PII real) y se pueden commitear.

## Estructura del repo

```
Contab/
├── CLAUDE.md              ← este archivo
├── README.md              ← guía de setup + flujo de prueba
├── apps/
│   ├── core/              ← Python sidecar
│   │   ├── contab_core/
│   │   │   ├── sidecar.py     stdio JSON-lines IPC loop
│   │   │   ├── storage.py     schema SQLite + migraciones por empresa
│   │   │   ├── excel.py       parser DIAN + columnas derivadas
│   │   │   ├── validations.py V1/V2/V3
│   │   │   ├── export.py      xlsxwriter (no conformes)
│   │   │   ├── pdf_cufe.py    extracción CUFE (pdftotext + cv2 QR) + indexer
│   │   │   ├── paths.py       carpetas por SO
│   │   │   └── nit.py         DV módulo 11 DIAN
│   │   ├── tests/             37 tests
│   │   ├── .venv/             venv del proyecto (NO commitear)
│   │   └── pyproject.toml
│   └── desktop/           ← Nuxt 4 frontend
│       ├── app/
│       │   ├── pages/         index / empresa / load
│       │   ├── components/    DirectoryPicker
│       │   ├── layouts/       default
│       │   ├── composables/   useRpc
│       │   └── assets/css/    main.css (theme tokens)
│       ├── server/
│       │   ├── api/           rpc.post / upload-excel.post / list-dir.get
│       │   └── utils/         sidecar (subprocess manager)
│       ├── nuxt.config.ts
│       └── package.json
└── docs/
    ├── plan.md            ← roadmap por entregas
    ├── decisions.md       ← registro completo (40 entradas)
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
