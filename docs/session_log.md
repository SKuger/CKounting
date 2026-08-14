# Bitácora de sesiones

Resumen breve de cada sesión de trabajo. Para detalle ver `plan.md` y `decisions.md`.

---

## Sesión 1 — 2026-05-27 / 28: planificación + E1 completa

**Resultado**: E1 cerrada end-to-end con muestras reales. 37 tests pasando. UI moderna con dark theme + full-width.

### Fases dentro de la sesión

1. **Planificación inicial**
   - Estructura `docs/` creada (plan, decisions, glosario, samples).
   - Decisiones tomadas: stack Tauri + Nuxt 4 + Python sidecar + SQLite (D-002), una `.db` por empresa (D-003), single-user (D-004), formatos Excel + PDF (D-005), export `.xlsx` con columnas originales (D-006), span dev mode primero (D-007), persistencia desde E1 (D-008), español/Colombia/DIAN (D-009), datos falsos en `docs/samples/` commiteables (D-010), preferencia opción múltiple (D-011).
   - Análisis exhaustivo del Excel DIAN (`docs/excel-structure.md`): 32 columnas + estructura confirmada con workflow multi-agente.
   - Lock E1 con verificación adversarial de columnas + reglas de validación.

2. **Implementación E1 Python sidecar**
   - `apps/core/contab_core/{paths, nit, storage, excel, validations, export, sidecar}.py`.
   - Schema SQLite con migraciones idempotentes.
   - Bug fix: factores DIAN módulo 11 estaban invertidos (derecha-izquierda) — corregido en `nit.py`.
   - 22 tests iniciales pasando contra `Ejemplo_LaDian.xlsx`.

3. **Implementación E1 frontend Nuxt 4**
   - `apps/desktop` con páginas `index`, `empresa`, `load`.
   - IPC bridge stdio JSON-lines (singleton subprocess en `server/utils/sidecar.ts`).
   - TanStack Vue Table para la tabla de la carga.
   - End-to-end probado en navegador.

4. **Iteraciones de UX pedidas por el usuario**
   - **D-031**: ocultar 21 columnas por defecto en la tabla (Estado, Grupo, Divisa, impuestos, retenciones, etc.) con panel de visibilidad.
   - File picker nativo + DirectoryPicker propio (`apps/desktop/app/components/DirectoryPicker.vue` + `/api/list-dir`). No más rutas escritas a mano.
   - **D-035**: dos carpetas por empresa (`default_folder` para Excels, `pdfs_folder` para PDFs).
   - **D-036**: auto-listado de archivos en `default_folder` con `imported` flag y 1-click import.
   - **D-038**: rediseño visual completo — tokens dark theme tipo Linear, full-width, layout con grid en empresa.

5. **PDF CUFE: implementación real (adelantando E4 a E1)**
   - **D-032**: extracción multi-pase (`pdftotext-raw` → `pdftotext-layout` → `cv2.QRCodeDetector` con `pypdfium2`).
   - **D-034**: QR scan multi-DPI (300→400→220) para fuentes obfuscadas (Movistar).
   - **D-037**: auto-indexing on validation run.
   - **D-040**: mostrar el CUFE encontrado bajo cada PDF + botón copiar al portapapeles.
   - V1 deja de ser stub y empieza a validar de verdad.
   - 6 PDFs reales → 6 CUFEs indexados (era 7 antes de aplicar la regla siguiente).

6. **Regla 1-CUFE-por-PDF (D-033)**
   - Bug encontrado por el usuario: la NC de Éxito generaba 2 CUFEs porque también extraía el CUFE de la **factura padre** que la NC referencia.
   - Implementada prioridad **CUDS > CUDE > CUFE**: cada PDF aporta solo su identificador propio. La referencia al padre se descarta.
   - Tests actualizados a aserción estricta `len(cufes) == 1` con etiqueta esperada por PDF.

### Estado al cerrar la sesión

- **37/37 tests Python pasando**.
- Dev server corriendo en http://localhost:3000.
- Empresa de prueba creada y persistida con ambas carpetas configuradas a `docs/samples/` y `docs/samples/pdfs/`.
- Validaciones reales contra la muestra dan **7 / 11 filas no conformes** con razones útiles (sin soporte / tarifa IVA incorrecta).
- 40 decisiones registradas (D-001..D-040).
- Plan reorganizado: E1 ✅, E3 re-scope (probablemente no necesario), E4 reducida a opcional (OCR + templates).

### Atajos útiles para la próxima sesión

```bash
# Arrancar dev (si no está corriendo)
cd apps/desktop && npm run dev

# Tests
cd apps/core && .venv/bin/pytest tests/ -q

# Restart sidecar al cambiar código Python
pkill -f 'contab_core.sidecar'
# (Nuxt lo respawnea en el próximo /api/rpc)

# Reset del cache de CUFEs (para re-extraer)
DB="$HOME/.local/share/Contab/empresas/900181831_real-seguros-ltda.db"
# (VSCode snap: $HOME/snap/code/240/.local/share/Contab/empresas/...)
sqlite3 "$DB" "DELETE FROM pdf_cufe_index;"
```

### Decisiones que el usuario tiene aún pendientes

- **D-E1-13** ⏸ ¿Cuándo `IVA = 0` en V3? Hoy hace skip — ¿confirmamos?
- **D-E2-1** ⏸ Política de backup de empresa.db (manual? auto al cerrar app?).
- **D-E2-2** ⏸ ¿Permitir editar NIT/razón social después de creada la empresa?
- **D-E4-3** ⏸ ¿OCR Tesseract para PDFs escaneados o se posterga?
- **D-E8-1** ⏸ Estrategia multiusuario (Postgres servidor vs sync nube).
- **D-E10-1** ⏸ Firma del instalador Windows.

### Próxima sesión — candidatos

| Opción | Esfuerzo | Valor |
|---|---|---|
| **E2** — Backup/restore, edición de empresa | Medio | Alto si el usuario empieza a usarlo en serio. |
| **E5** — PUC + catálogo de terceros | Alto | Necesario para pasar de "cruce" a contabilidad real. |
| **Tauri / E10** | Medio-alto | Necesario para distribuir como `.msi`. |
| **Mejoras de UX sobre E1** | Bajo | `razon_falla` inline por fila, filtros guardados, columnas reordenables. |
| **Backlog suelto** | Variable | Conciliación bancaria, recordatorios fiscales, dashboard ejecutivo. |

---

## Sesión 2 — 2026-06-25: repo en GitHub + integración del scraper DIAN

**Resultado**: el proyecto quedó versionado en GitHub y se inició la unificación con el segundo proyecto (scraper de terceros DIAN) en un monorepo.

### Fases

1. **Subida a GitHub**
   - Contab no tenía git. Se inició repo, commit inicial y push a `SKuger/CKounting` (**privado**).
   - Detalle de cuentas: `gh` estaba como `SKuger01`; el repo vive bajo `SKuger` (cuenta distinta), así que hubo que reautenticar. `gh` 2.4.0 no soporta multi-cuenta.
   - El `.gitignore` existente ya excluía `.venv`, `*.db`, Excel/PDF reales (salvo `docs/samples/`) y `.env`.

2. **Integración del scraper DIAN (E-DIAN, en progreso)** — ver D-050..D-052.
   - Se localizó el segundo proyecto: `~/Documentos/proyects/Contabilidad_EXT` (*"DIAN RUT Automator"*, FastAPI + Playwright). Copia limpia a `apps/dian-rut/` (original intacto). 92 KB versionados; runtime/PII ignorados.
   - Backend como **2º sidecar** uvicorn (puerto 8756), levantado on-demand por Nuxt (`server/utils/dianSidecar.ts`).
   - Frontend: página nativa Nuxt `/consulta-dian` + nav que une "Empresas" y "Consulta DIAN". Proxy HTTP en `/api/dian/*`; WebSocket directo a localhost.
   - **Verificado**: venv recreado, uvicorn arranca y responde; Nuxt compila, levanta el sidecar, sirve la página y las rutas proxy (`session`, `browser-status`, `template`); handshake WebSocket OK.
   - **Pendiente**: scrape real contra el portal DIAN (en vivo, con NITs reales), manejo de errores por NIT, pulido de UX (cancelación real, modo "Chrome humano" :9222).

3. **Preferencia registrada**: sin trailer `Co-Authored-By` en los commits de este repo (los dos primeros commits se reescribieron para quitarlo).

### Próxima sesión — candidatos

| Opción | Esfuerzo | Valor |
|---|---|---|
| **Validar E-DIAN end-to-end** | Bajo-medio | Confirmar el scrape real con un Excel de NITs y pulir errores. |
| **E2** — Backup/restore, edición de empresa | Medio | Alto si el usuario empieza a usarlo en serio. |
| **E5** — PUC + catálogo de terceros | Alto | Conecta naturalmente con los resultados del scraper DIAN. |
| **Tauri / E10** | Medio-alto | Empaquetar como `.msi` gestionando ambos sidecars. |

---

## Sesión 3 — 2026-06-28: design system Dandelyon (sub-marca Órbita)

**Resultado**: el **shell** de `apps/desktop` adopta el design system Dandelyon (Órbita) siguiendo el issue `SKuger/CKounting#1` (8 fases). Rama `feat/design-system-orbita`, un commit por fase. El frontend pasó de un dark-theme propio a tokens shadcn + Tailwind v4 + reka-ui, con el look Órbita horneado (riel solar índigo). Ver D-053/D-054.

### Fases (todas conciliadas + commiteadas)

0. **Deps** — pinia, reka-ui, shadcn-nuxt, @nuxt/fonts, cva, clsx, tailwind-merge, lucide-vue-next, @vueuse/core, tailwindcss v4. (+`@lucide/vue` y `typescript`, que los componentes `ui/` verbatim requieren y el issue no listó.)
1. **Tokens** — `main.css` = contrato del design system (verbatim salvo 3 bloques solo-playground: Apax @font-face, `.fonts-preload`, letterbox).
2. **nuxt.config** — `ssr:false`, plugin Tailwind v4, `optimizeDeps`, fuentes fijas (Fraunces/Inter/IBM Plex Mono), FOUC con clave `contab-theme`, favicon de marca.
3. **Componentes** — `ui/` (97 archivos) + 7 de marca, verbatim; `useBrand()` reemplaza el store `usePlayground()`.
4. **Shell** — `layouts/default.vue`: sidebar (lockup + nav real Empresas/Consulta DIAN + cosmos + MakerCredit) + topbar (breadcrumb, ⌘K, beacon, notificaciones, toggle de tema). Nav navega (patrón `SidebarMenuButton as-child > NuxtLink`).
5. **Tema horneado** — `.theme-orbita` (índigo `#2b1dc3`) + `data-*` en `<html>`.
6-8. **Lockup + trampas + QA** — verificado en vivo con Playwright: claro/oscuro índigo (sin verdoso), ⌘K filtra/navega, toggle persiste, cero hex crudo en el shell, cero errores de consola.

### Re-tematización de páginas (hecho el mismo día)
Tras el shell, se re-tematizaron **todas** las páginas a shadcn/tokens (D-054 actualizada):
`index` (Empresas), `empresa`, `load` (tabla `@tanstack` con CSS scoped basado en tokens),
`consulta-dian`, + `DirectoryPicker` (→ `Dialog`) y `ToastContainer`. Regla de oro verificada
(0 hex crudo / 0 paleta / 0 tokens viejos), claro y oscuro OK, cero errores. Fase 8 del issue
cumplida en toda la app.

### Pase de UX (densidad + viewport) — D-055
El usuario reportó "mucho scroll, espacio desperdiciado". Auditoría UX con workflow (5 críticas
paralelas + síntesis) → raíz: torre de espaciado de catálogo + caps de ancho. Se implementó:
densidad como palanca real (gap var + interior de Card) horneada en `compacta`, superficies de
trabajo full-width, scroll en panel (carga con altura flex que mata el doble scroll), y patrones
nuevos (landing con stats + Nueva empresa en Dialog; detalle empresa maestro-detalle + menú ⋯).
Verificado en claro/oscuro, cero errores.

### Design system (repo hermano) — issues abiertos
Surgieron 2 mejoras que van en `SKuger/DandeLyon-DesignSystem` (no en Contab):
- **#1** MakerCredit → «Creado por: SKuger · V<version>» (sin corchetes, centrado). Ya aplicado
  **localmente** en Contab como stopgap; el issue sigue abierto para la fuente compartida.
- **#2** SidebarUser editable (perfil/correo) + preferencias reales.

### Consumo en CKounting de SidebarUser + preferencias — D-056 (issue CKounting #2)
El DS implementó el estándar (DS #2 / PR #4); se **consumió** en Contab por etapas (commit por
etapa): composables `useUser`/`usePrefs` (claves propias, sin demo, density default compacta) →
efectos CSS reduce-motion/contraste → `SidebarUser` (usePlayground→useBrand) → cableado
(usePrefs = fuente única de tema/densidad/escala; topbar + ⌘K + panel unificados; notif→campana).
Verificado en vivo: todas las preferencias con efecto + CRUD de cuentas; cero errores. Sin auth
(D-004) → localStorage es la fuente real, una cuenta neutra editable.

### Próxima sesión — candidatos

| Opción | Esfuerzo | Valor |
|---|---|---|
| **Re-tematizar páginas a tokens/shadcn** | Medio-alto | Cierra la migración del design system (Fase 8 "cero hex crudo" en todo). |
| **PR de la rama** `feat/design-system-orbita` → cerrar issue #1 | Bajo | Mergear el shell. |
| **Validar E-DIAN end-to-end** | Bajo-medio | Pendiente de la sesión 2. |

---

## Sesión 4 — 2026-06-28: E10 — empaquetado de escritorio (Electron)

**Resultado**: andamiaje completo para entregar Contab como **app de escritorio Windows** instalable + auto-update, en la rama `feat/e10-desktop-electron`. Decisiones D-057 (Electron, supersede Tauri), D-058 (DIAN sin Chromium, modo CDP), D-059 (sin firma; update por sha512; releases en repo público — hosting TBD).

### Qué se hizo (commit por fase)
- **Env-hooks**: `sidecar.ts` (`CONTAB_SIDECAR_BIN`), `dianSidecar.ts` (`DIAN_SIDECAR_BIN`), `pdf_cufe.py` (`CONTAB_PDFTOTEXT`) — retrocompatibles en dev.
- **`apps/shell/`** (Electron): main/nitro/paths/preload/updater + `electron-builder.yml` (NSIS per-user) + icono. Nitro como child_process (Node de Electron), puerto dinámico, tree-kill al cerrar.
- **PyInstaller**: `contab-sidecar.spec` (core) y `dian-sidecar.spec` + `run_server.py` (DIAN, uvicorn embebido), ambos onedir. `dian_paths.py` reubica los dirs escribibles a `%APPDATA%\Contab\dian` (`DIAN_WORKDIR`) y resuelve `static/` por `sys._MEIPASS`.
- **CI**: `.github/workflows/release-windows.yml` (windows-latest, gratis): PyInstaller×2 → Poppler → nuxt build → staging → electron-builder NSIS → upload-artifact (hosting `--publish never` por ahora).

### Verificado en Linux
`nuxt build` → `node .output/server/index.mjs` arranca y el sidecar responde por RPC; **binario PyInstaller del core construido y probado** directo (ping→pong) y vía Nitro con `CONTAB_SIDECAR_BIN` (ping + list_empresas). DIAN: import chain OK + `DIAN_WORKDIR` crea dirs. 61/61 tests del core verdes.

### Pendiente (Windows / decisión)
- Build real + prueba del instalable en **Windows** (CI o máquina): ventana Electron, sin procesos huérfanos al cerrar, Poppler extrae CUFE, WS DIAN, SmartScreen.
- **Hosting de auto-update**: crear el repo público de releases y pasar el CI a `--publish always`.
- Pulido: `DIAN_PORT` dinámico, `playwright install` on-demand opcional, splash/logging.

---

## Sesión 5 — 2026-07-03: Consulta de Inconsistencias DIAN + release 0.1.5

**Resultado**: nueva **Consulta de Inconsistencias** (razón social por NIT+DV) integrada en Contab, por el sidecar de `apps/core` con **scraping HTTP plano** de MUISCA (`DefSelPublicacionesExterna.faces`, JSF/Mojarra, **sin Cloudflare** — a diferencia de Terceros que usa Playwright). Decisión **D-065**. Release **0.1.5**.

### Qué se hizo
- **Backend** (`apps/core`, sin dependencias nuevas — solo `urllib`): módulo `dian_inconsistencias.py` (scraper GET→ViewState→POST→Razón Social; parser Excel NIT/DV con autocálculo de DV; export xlsxwriter) + 3 RPCs en `sidecar.py`: `parse_nit_dv`, `consulta_inconsistencias`, `export_inconsistencias`.
- **Frontend** (Nuxt/Órbita): página `/consulta-inconsistencias` (subir → tabla en vivo, consulta fila por fila con progreso/cancelar/reintentar, pausa 450 ms → export con `DirectoryPicker`); ruta `server/api/consulta-inconsistencias/upload.post.ts`; sidebar reorganizado en grupo desplegable **"Consultas DIAN" → Terceros + Inconsistencias** (reka-ui Collapsible + `SidebarMenuSub`), con `flatNav` aplanado para ⌘K/breadcrumb.

### Verificado
Scrape real (NIT 860002180 → "SEGUROS COMERCIALES BOLIVAR S.A."); upload+parse (autocalcula DV faltante); export; ambas páginas 200; **prueba real con 115 NITs (102 encontrados, 13 sin resultado, 0 errores)**. 73/73 tests del core verdes.

### Notas
- Entorno: `ENOSPC` de file watchers (inotify) hace reiniciar Nuxt en dev; subir `fs.inotify.max_user_watches`.
- La clave de la IA (Haiku) sigue fuera de alcance; esta consulta es pública (sin token/login).

---

## Sesión 6 — 2026-07-14: renombrar soportes + fix extracción de CUFE (números pegados) + QR de verificación

**Resultado**: nueva acción **Renombrar soportes** (D-066), fix de la tabla de validaciones con filtro "solo no conformes", y **corrección de la extracción de CUFE** (D-067) que fallaba en facturas donde el número de autorización DIAN (16 dígitos) se pegaba al CUFE. 74/74 tests del core verdes.

### Qué se hizo
- **Renombrar soportes** (D-066): módulo `rename_soportes.py` + RPC `rename_soportes`; renombra IN PLACE al patrón `DD-MM_NIT_RAZON-SOCIAL_FACTURA.pdf` cruzando CUFE↔fila del Excel; deja manifiesto `_renombrados.csv` (reversible); PDFs sin match se dejan intactos y se reportan; nunca sobreescribe (sufijo `_2`); idempotente. UI en `load.vue`: botón + modal con preview (dry-run) antes de aplicar.
- **Fix tabla** (`load.vue`): con el filtro "solo no conformes" activo, validar mostraba errores/hovers en filas equivocadas. Causa: pre-filtrar `tableData` rompía el `row.id`↔índice original de @tanstack/vue-table. Fix: `getRowId` sobre un `__idx` absoluto + `globalFilterFn` que ignora `__idx`.
- **Fix extracción CUFE** (D-067): el regex viejo `(?:[a-f0-9]\s*){96}` colapsaba los espacios y **pegaba** el nº de autorización (16 dígitos, también hex) al CUFE, devolviendo un token de 96 chars equivocado (caso Telesentinel). Ahora se reconstruye el CUFE agrupando **segmentos hex separados por espacios** que sumen exactamente 96 (respeta límites de token) + prioridad CUDS>CUDE>CUFE (D-033) intacta. Además el **QR se usa como verificación** de las lecturas dudosas (texto sin etiqueta o vacío) — no en todas (medido: 37 PDFs≈136 s excedía el timeout de 30 s; limitado a los ~8 dudosos≈29 s, decisión del usuario), y es **autoritativo** (fuente machine-readable de la DIAN). Nuevo `extractor_version` en `pdf_cufe_index` (migración) invalida el caché viejo automáticamente.

### Verificado
- Telesentinel **julio** (329485) → `b55c…683441` = Excel ✓ (vía QR, label CUFE). Telesentinel **mayo** (325044) → `2074facb…f48a93` = Excel ✓ (vía fix de texto). El caché viejo tenía literalmente `0229510000325044`+CUFE cortado; tras la migración+re-index quedó corregido.
- 74/74 tests del core verdes; carpeta real de mayo (31 PDFs) sin regresiones; NC Éxito (CUDE) y Movistar (QR) intactos.

### Pendiente
- Commit de esta sesión (rename + fix tabla + fix CUFE + migración + docs) y decidir release **0.1.6**.

---

## Sesión 7 — 2026-07-15: Inconsistencias soporta personas naturales (0.1.7)

**Resultado**: la Consulta de Inconsistencias ahora resuelve **empresas Y personas naturales** (D-069). Release **0.1.7** (urgente).

- `consultar()`: si no hay "Razón Social", compone el nombre de persona (Primer/Otros Nombres + Primer/Segundo Apellido) y devuelve `tipo` (empresa|persona). El documento de la persona va en la misma columna NIT → el parser de entrada no cambia.
- Export: columnas NIT, DV, "Razón Social / Nombre", Tipo. UI: columna Tipo + textos actualizados.
- 5 tests nuevos; 79/79 verdes. Verificado en vivo (empresa + 2 personas). Nuevo flujo de release: develop→main→tag en main→CI publica en CKounting-releases.

---

## Sesión 8 — 2026-08-14: Plan de Cuentas (PUC) por empresa (0.2.0)

**Resultado**: nueva característica **PUC** a nivel empresa (D-070). Se sube el dump Excel de cuentas contables, queda en BD, y se puede editar/archivar/agregar/exportar. Flujo de entrega: commits por capa → code review → PR develop→main → tag v0.2.0 → CI publica en CKounting-releases.

- **Backend**: `puc.py` (`load_puc` parsea preámbulo empresa/NIT + tabla + pie; `persist_puc` upsert por código = fusionar; CRUD manual; `export_puc`). Tablas `puc_account` (con `fuente` dump/manual, `archived`, `nivel` derivado de la longitud del código) y `puc_import` (historial). 6 RPCs. Endpoint `upload-puc` (vista previa dry-run). **Bloqueo por NIT** del encabezado.
- **Front**: página `/puc` (tabla con indentado por nivel, filtros clase/nivel/estado, buscador, subir dump con preview, CRUD, export), card en `empresa.vue`, nav match.
- **Verificado**: dump real de 885 cuentas (REAL Seguros), NIT 900181831, merge sin duplicar, bloqueo por NIT distinto. 12 tests nuevos; 91/91 verdes. Probado en vivo por el usuario.
