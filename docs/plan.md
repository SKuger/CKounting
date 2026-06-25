# Plan de desarrollo — Contab

Roadmap por **Entregas** independientes y probables-de-usar. Cada entrega es una unidad funcional que se puede instalar/correr y probar antes de pasar a la siguiente.

> **Estado global** (actualizado 2026-05-28)
> - Entregas completadas: **E1 ✅**
> - Avance del producto al cerrar E1: **~6 %** (incluye parte de E3/E4 fusionada)
> - Entrega en curso: ninguna
> - Próxima sugerida: **E2 — Catálogo de empresas robusto** o **E5 — Plan de cuentas / catálogo de terceros** (ver `## Próxima sesión`).

## Próxima sesión — arranque rápido

1. Asegurarse de que el dev server esté corriendo (`cd apps/desktop && npm run dev`) → http://localhost:3000.
2. Si los tests Python no han corrido recientemente: `cd apps/core && .venv/bin/pytest tests/ -q` (esperado: 37 passed).
3. Hay una empresa "REAL Seguros Ltda." (NIT 900181831-4) ya creada en `~/.local/share/Contab/empresas/` (o el path equivalente del SO) con `default_folder` y `pdfs_folder` configurados a `docs/samples/` y `docs/samples/pdfs/`.
4. Decisiones que el usuario aún debe responder en su momento: D-E1-13 (IVA=0 en V3), D-E2-1, D-E2-2, D-E4-3, D-E8-1, D-E10-1.
5. Candidatos de siguiente trabajo:
   - **E2**: backup/restore por empresa, edición de empresa, validación NIT al editar.
   - **E5**: cargar Plan Único de Cuentas (PUC) por empresa + catálogo de terceros (clientes/proveedores). Ya tenemos terceros implícitos en cada fila DIAN — podríamos derivar el catálogo automáticamente.
   - **Tauri / E10**: empaquetar para Windows (necesita instalar `libwebkit2gtk-4.1-dev` o cambiar a Tauri 1.x).
   - **Mejoras de UX sobre E1**: detalle de cada validación fallida en la tabla (mostrar `razon_falla` por fila in-place), filtros guardados por empresa, columnas reordenables.

Para resúmenes de sesiones anteriores ver [`session_log.md`](session_log.md).

---

## Convenciones

- Cada entrega tiene: **Objetivo**, **Alcance**, **Fuera de alcance** (importante), **Pasos**, **Criterio de aceptación**, **Decisiones pendientes**.
- Decisiones pendientes = preguntas que voy a hacer cuando llegue el momento de esa entrega (no antes, para no marear).
- Al cerrar una entrega: marcar `✅`, mover sus decisiones nuevas a `decisions.md`, e instrucciones de prueba para el usuario.

---

## E1 — Cruce DIAN ↔ soportes ✅ Completada

**Estado**: ✅ Completada — 2026-05-28. End-to-end funcional contra muestras reales.

> Esta entrega creció más allá del alcance original: parte de E3 (cruce con soportes externos) y casi toda E4 (extracción real de CUFE desde PDFs, incluido QR scan) terminaron implementadas aquí. Ver D-032..D-040 en `decisions.md`.

### Resumen de lo logrado

- Stack: Tauri-ready (Nuxt 4 + Python sidecar via stdio JSON-lines, SQLite por empresa).
- 37 tests Python pasando contra los samples reales del usuario (Excel + 6 PDFs incluido Movistar via QR).
- Flujo en navegador: empresas → carpeta de Excels (auto-listada, 1-click import) → carpeta de PDFs (auto-indexada, CUFE mostrado bajo cada uno) → tabla con 35 columnas (14 visibles por defecto) → ejecutar validaciones → exportar `.xlsx` de no conformes con `razon_falla` y signos NC invertidos.
- Validaciones implementadas:
  - **V1 — CUFE en carpeta de PDFs (REAL, no stub)**: extracción multi-pase (pdftotext-raw → pdftotext-layout → cv2 QR scan multi-DPI), cache incremental por `(folder, path, mtime, size)`, regla 1-CUFE-por-PDF con prioridad CUDS > CUDE > CUFE.
  - **V2 — Notas Crédito × −1**: aplicada en memoria al evaluar y al exportar; BD guarda originales (D-029).
  - **V3 — Tarifa IVA 19% / 5% / skip-si-cero** (D-023, D-E1-13).
- Persistencia completa por empresa en SQLite. Schema versionado con migraciones idempotentes.
- UI rediseñada (D-038): dark theme moderno full-width, columnas ocultables (D-031), DirectoryPicker propio.

### Estado original cuando arrancó la entrega

### Objetivo

Que el contador pueda **cargar un Excel descargado de la DIAN**, verlo en una tabla con filtros y búsqueda, aplicar **validaciones** configurables, y **exportar a Excel** las filas no conformes preservando las 32 columnas originales + `razon_falla`. La carga y las reglas quedan guardadas por empresa para reabrirlas luego.

### Alcance

1. App Tauri + Nuxt + Python sidecar corriendo en dev mode (`tauri dev`). IPC = stdio JSON-lines (D-019).
2. Selector de **empresa activa** + creación rápida (NIT + razón social). Una `.db` por empresa en la carpeta estándar del SO (D-021).
3. **Cargar archivo Excel** desde un botón. Backend Python parsea con `openpyxl`, devuelve las 32 columnas + filas, persiste la carga.
4. **Tabla mostrando las 32 columnas originales + 3 derivadas, sin pre-ocultar ni pre-filtrar** (D-027). El contador elegirá después qué ocultar y qué filtrar.
5. **Filtros y búsqueda por columna** (texto contiene, igual, rango numérico, rango de fechas). Búsqueda global.
6. **Sistema de validaciones**: rule editor + run engine + storage por empresa.db (D-015, D-016).
7. **Exportar Excel** de no conformes con las 32 columnas en el orden original + `razon_falla` como columna #33 (D-014).
8. **Persistencia**: `validation_run` + `validation_failure` quedan en la empresa.db. Reabrible (ver veredicto + razones de la última corrida).

### Fuera de alcance (NO hacer en E1)

- Auth / login / usuarios → E9.
- **Implementación real de Validación 1 (CUFE en carpeta de PDFs)** — en E1 solo se schema y se ejecuta inyectando warning "pendiente E4" en `razon_falla` (D-017). La extracción real de CUFEs desde PDFs entra en E4.
- Soportes como segundo dataset Excel/CSV → E3.
- Plan de cuentas, asientos contables, reportes financieros → E5–E7.
- Instalador `.msi` → E10.
- Backup / restore robusto → E2.
- Sincronización a la nube → E8.

### Pasos

1. **Scaffolding del repo**
   - `apps/desktop/` ← `nuxi init` + `tauri init`. Tauri configura el sidecar Python con stdio.
   - `apps/core/` ← proyecto Python con `pyproject.toml`. Dependencias: `openpyxl` (lectura xlsx), `xlsxwriter` (escritura xlsx con styles), `sqlite3` (stdlib). NO pandas en E1 (overkill — openpyxl basta).
   - Wrapper de IPC: loop `for line in stdin: handle(json.loads(line))` que despacha por `method`.
2. **Carpeta de datos y selector de empresa**
   - Resolver carpeta por SO con `appdirs`/equivalente Tauri: `%APPDATA%\Contab\empresas\` en Windows.
   - Pantalla inicial: escanea `empresas/*.db` y lista las detectadas.
   - "Nueva empresa": NIT (con validación módulo 11) + razón social → crea `<nit>_<slug>.db` aplicando el schema E1 (ver más abajo).
3. **Carga de Excel**
   - Botón "Importar reporte DIAN" → file picker (Tauri dialog).
   - Sidecar Python: leer con `openpyxl` modo read-only, detectar header en fila 1, coercer NIT/Folio a string (preservar ceros), trim/collapse whitespace en razones sociales, parsear fechas dd-mm-yyyy con `datetime.strptime`.
   - Insertar metadata en `excel_load` + filas en `excel_row` (JSON column con la fila completa para no rigidizar el schema).
   - Retornar preview (primeras 50 filas) al frontend.
4. **Tabla con filtros (TanStack Table — D-020)**
   - Muestra las 32 columnas originales + 3 derivadas en el orden: originales primero (orden del Excel), derivadas al final (D-027).
   - **Sin** filtros pre-aplicados. **Sin** columnas pre-ocultas. El contador configura su vista.
   - `Tipo de documento = Nota de crédito electrónica` muestra un badge `NC` en la fila (D-029) — la BD guarda valores originales positivos y la transformación V2 ocurre solo al evaluar/exportar; el badge alerta al contador que los signos visibles no son los contables finales.
   - Resolver UBL codes (Forma/Medio Pago) a texto (D-018): mostrar texto en la celda y el código original en tooltip.
   - Filtros por columna + búsqueda global.
   - Virtual scroll (`@tanstack/vue-virtual`) por si crece a miles de filas.
5. **Sistema de validaciones**
   - Schema en empresa.db (ver más abajo).
   - Rule editor UI: selector de tipo + form dinámico según `type` (D-015).
   - Engine en Python: itera reglas habilitadas, evalúa fila por fila, escribe failures.
   - "Ejecutar validaciones" muestra resumen (X filas / Y reglas / Z fallas).
6. **Exportar no conformes**
   - Botón "Exportar Excel de no conformes" → file dialog.
   - Sidecar genera `.xlsx` con `xlsxwriter`. Orden: 32 columnas originales (orden del Excel) → 3 derivadas (`# de factura`, `Valor Base`, `Base IVA`) → `razon_falla`. Total 36 columnas.
   - **Aplicar V2 en memoria antes de escribir** (D-029): para filas con `Tipo de documento` "Nota de crédito electrónica", multiplicar por -1 las columnas `IVA`, `Total`, `Valor Base`, `Base IVA`.
   - `razon_falla`: motivos múltiples concatenados en **una sola celda separados por `; `** (D-028).

### Esquema SQLite para E1 (dentro de cada empresa.db)

```sql
-- Metadata de la empresa (1 fila — identidad implícita = el archivo)
CREATE TABLE empresa_info (
  nit            TEXT NOT NULL,
  dv             TEXT,
  razon_social   TEXT NOT NULL,
  created_at     TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Cada importación de un Excel DIAN
CREATE TABLE excel_load (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  source_path  TEXT NOT NULL,
  source_name  TEXT NOT NULL,
  loaded_at    TEXT NOT NULL DEFAULT (datetime('now')),
  total_rows   INTEGER NOT NULL,
  sheet_name   TEXT
);

-- Filas del Excel, con la fila completa como JSON para no rigidizar el schema
CREATE TABLE excel_row (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  load_id      INTEGER NOT NULL REFERENCES excel_load(id) ON DELETE CASCADE,
  row_index    INTEGER NOT NULL,
  cufe_cude    TEXT,            -- denormalizado para joins/filters rápidos
  grupo        TEXT,            -- denormalizado: 'Emitido' / 'Recibido'
  data_json    TEXT NOT NULL    -- todas las 32 columnas
);
CREATE INDEX idx_excel_row_load ON excel_row(load_id);
CREATE INDEX idx_excel_row_cufe ON excel_row(cufe_cude);

-- Definiciones de reglas (D-015, D-016 — sin CHECK constraint sobre type)
CREATE TABLE validation_rule (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  name            TEXT NOT NULL,
  description     TEXT,
  type            TEXT NOT NULL,       -- cufe_in_folder, value_in_list, ...
  scope_json      TEXT,                -- JSON: {"Grupo":["Recibido"], ...} o null = todas
  params_json     TEXT NOT NULL,       -- config específica del tipo
  failure_message TEXT NOT NULL,       -- soporta placeholders {ColumnName}
  severity        TEXT NOT NULL DEFAULT 'error',
  enabled         INTEGER NOT NULL DEFAULT 1,
  vigencia_desde  TEXT,
  vigencia_hasta  TEXT,
  created_at      TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Una ejecución de las reglas sobre una carga Excel
CREATE TABLE validation_run (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  load_id       INTEGER NOT NULL REFERENCES excel_load(id) ON DELETE CASCADE,
  started_at    TEXT NOT NULL DEFAULT (datetime('now')),
  finished_at   TEXT,
  total_rows    INTEGER,
  failing_rows  INTEGER,
  notes         TEXT                  -- diagnósticos a nivel run (folder unreadable, etc.)
);

-- Solo failures se persisten (los passes son implícitos)
CREATE TABLE validation_failure (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id         INTEGER NOT NULL REFERENCES validation_run(id) ON DELETE CASCADE,
  rule_id        INTEGER NOT NULL REFERENCES validation_rule(id) ON DELETE CASCADE,
  row_index      INTEGER NOT NULL,
  cufe_cude      TEXT,
  column_name    TEXT,                 -- para drilldown UI sin parsear el mensaje
  value_snapshot TEXT,                 -- valor de la celda al momento de la corrida
  rule_severity  TEXT,                 -- denormalizado para queries de export
  reason         TEXT NOT NULL
);
CREATE INDEX idx_failure_run_row ON validation_failure(run_id, row_index);

-- Cache de CUFEs por PDF para Validación 1. En E1 SOLO se crean las tablas;
-- la población es en E4.
CREATE TABLE pdf_cufe_index (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  folder_path       TEXT NOT NULL,
  pdf_path          TEXT NOT NULL,
  pdf_mtime         INTEGER NOT NULL,
  pdf_size_bytes    INTEGER NOT NULL,
  extraction_status TEXT NOT NULL,     -- ok / no_text / error
  extraction_error  TEXT,
  indexed_at        TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(folder_path, pdf_path)
);
CREATE TABLE pdf_cufe_value (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  pdf_index_id INTEGER NOT NULL REFERENCES pdf_cufe_index(id) ON DELETE CASCADE,
  cufe_cude    TEXT NOT NULL,
  label        TEXT,
  UNIQUE(pdf_index_id, cufe_cude)
);
CREATE INDEX idx_pdf_cufe_value_hex ON pdf_cufe_value(cufe_cude);
```

### Reglas y transformaciones reales de E1 (D-023, D-024)

En E1 NO se construye un rule editor genérico — se implementan **estas tres operaciones específicas del flujo del usuario, en este orden**:

**Al cargar el Excel (transformaciones)**:

1. Agregar 3 columnas calculadas (D-024):
   - `# de factura` = `<Prefijo>-<Folio>` (separador a confirmar — D-E1-12).
   - `Valor Base` = `Total − IVA`.
   - `Base IVA` = `IVA / 0.19`.

2. Si el Excel cargado ya trae alguna de las 3, la app la **sobrescribe** para garantizar consistencia.

**Al evaluar / al cargar (orden estricto)**:

**T-V2 — Inversión de signo en Notas Crédito** (D-023, V2)
- Condición: `Tipo de documento` contiene `"Nota de crédito"`.
- Efecto: `IVA *= -1` y `Total *= -1`.
- Cuándo aplicar: **D-E1-11** pendiente. Implementación más limpia = al cargar (la BD ya tiene los signos correctos y todo aguas abajo es consistente).
- Las columnas derivadas `Valor Base` y `Base IVA` se recalculan **después** de invertir.

**R-V3 — Tarifa de IVA** (D-023, V3)
- Para cada fila:
  1. Si `|Valor Base − Base IVA| ≤ 5` → IVA al **19% OK**.
  2. Si no, recalcular: `Base IVA' = IVA / 0.05`. Si `|Valor Base − Base IVA'| ≤ 5` → IVA al **5% OK**.
  3. Si tampoco → **no conforme**, razón: `"IVA no corresponde a tarifa 19% ni 5% (Valor Base={vb}, IVA={iva})"`.
- IVA = 0: **D-E1-13** pendiente (¿skip, marcar excluido, validar contra 0%?).

**R-V1 — Soporte CUFE en carpeta** (D-017)
- Tipo `cufe_in_folder`. En E1: schema + warning "pendiente E4" en `razon_falla` para todas las filas en scope. Sin extracción real.

**Tipos de regla extendidos en backlog** (no E1)

El rule editor genérico (selector de tipo + form dinámico por `type`) queda como backlog futuro. Cuando llegue, soportará: `value_in_list`, `value_not_in_list`, `numeric_range`, `date_range`, `regex_match`, `formula`, `nit_dv_check`, `duplicate_check`, `period_mismatch`. El schema D-016 ya está preparado para recibirlos (`params_json` + sin `CHECK` constraint sobre `type`).

### Criterio de aceptación

End-to-end sin intervención del desarrollador:

1. `npm run tauri dev` desde `apps/desktop/`.
2. Crear empresa "REAL Seguros Ltda" NIT 900.181.831-4 (DV módulo 11 verificado).
3. Importar `Ejemplo_LaDian.xlsx`.
4. Ver la tabla con las 32 columnas originales + 3 derivadas (`# de factura`=`DSE-211`, `Valor Base`, `Base IVA`). Sin filtros aplicados — todo visible (D-027).
5. Las filas `Nota de crédito electrónica` muestran un badge `NC` (los valores `IVA`/`Total` se ven positivos en la tabla — la transformación V2 ocurre solo al evaluar y exportar, D-029).
6. Configurar una regla `cufe_in_folder` apuntando a `docs/samples/`. El scope se aplica a todas las filas (el usuario decidirá después qué tipos excluir).
7. Ejecutar validaciones. Conteo esperado:
   - Filas con `razon_falla` por R-V3 (IVA no encaja con 19% ni 5% en la muestra).
   - Filas con `razon_falla` por R-V1 (warning "Validación CUFE pendiente — E4" en todas las filas en scope).
8. Exportar Excel de no conformes → 36 columnas, los valores `IVA`/`Total` invertidos en filas NC. `razon_falla` usa `; ` como separador (D-028).
9. Cerrar y reabrir la app → la empresa aparece, la última corrida con sus failures está persistida.

### Decisiones pendientes para E1 (preguntar al implementar)

> Ya resueltas: D-E1-1..D-E1-12 (ver `decisions.md`).

- **D-E1-13** Behavior de R-V3 cuando IVA = 0. Default temporal: skip. Confirmar al implementar V3.
- **D-E1-14** Qué columnas ocultar / qué filtros guardar como defaults. Se decide después de probar E1.

---

## E2 — Catálogo de empresas robusto

**Objetivo**: convertir la "creación rápida" de E1 en una gestión real de empresas.

### Alcance

- CRUD completo: editar datos fiscales, archivar empresa, eliminar (con confirmación doble).
- Backup manual: botón "Exportar copia" que comprime el `.db` con timestamp.
- Restore desde backup.
- Validación de NIT colombiano (dígito de verificación).
- Importar/exportar empresa completa (`.contab-empresa` = .db comprimido).

### Decisiones pendientes (a su tiempo)

- Campos fiscales necesarios (régimen, responsabilidades, gran contribuyente, etc.).
- Política de eliminación: ¿hard delete real o soft delete con archivado?

---

## E3 — Soportes del cliente (segundo dataset Excel/CSV) ⚠️ Re-scope

**Estado**: en pausa — el flujo real del usuario no usa un Excel/CSV adicional como soporte, usa PDFs (resueltos en E1 vía V1 real). Esta entrega queda como reserva para si más adelante aparece un caso que sí necesite cruce con un segundo Excel.

### Posible alcance futuro (si se reactiva)

- Cargar Excel/CSV adicional con conceptos / movimientos no electrónicos.
- Mapear columnas del soporte ↔ columnas del reporte DIAN.
- Reglas de cruce con tolerancia numérica/fecha.

---

## E4 — Mejoras opcionales al pipeline de PDFs ⚠️ Reducida

**Estado**: el alcance original de E4 (extracción de CUFE desde PDFs) **se completó en E1** (D-032). Lo que queda son extensiones opcionales:

### Pendientes posibles

- **OCR con Tesseract** como cuarto pase de fallback para PDFs escaneados (no necesario con la muestra actual — todos los PDFs son texto o tienen QR decodificable).
- **Templates de extracción por emisor** (D1, Éxito, Movistar) si se necesitan datos estructurados del PDF más allá del CUFE.
- **Diagnóstico de PDFs sin CUFE** mejorado en la UI: lista aparte de PDFs que cayeron a `status='no_text'` con sugerencias de acción.

### Decisiones pendientes

- **D-E4-3** ¿OCR Tesseract o se posterga? Default: posterga hasta caso real.

---

## E5 — Plan de cuentas y catálogo contable

**Objetivo**: empezar la contabilidad "real" (no solo cruces).

### Alcance

- Plan de cuentas estándar Colombia (PUC) por empresa.
- Catálogo de terceros (clientes/proveedores con NIT, régimen).
- Catálogo de centros de costo.
- Importadores desde Excel.

---

## E6 — Asientos contables

- Comprobantes (encabezado + detalle).
- Numeración por tipo (CC, CE, CI, RC, RP, etc.).
- Validación de partida doble.
- Adjuntar PDF de soporte por comprobante.

---

## E7 — Reportes financieros

- Libro mayor, libro auxiliar, balance de prueba.
- Estado de resultados, balance general.
- Generación a Excel y PDF.

---

## E8 — Multiusuario / sincronización

**Objetivo**: pasar de single-user local a 2-5 usuarios.

### Decisiones pendientes (importantes — definen arquitectura)

- ¿PostgreSQL en un PC servidor, o sync a la nube de las DB SQLite?
- ¿Drive/Dropbox como medio (NO recomendado para SQLite) o servicio propio?

---

## E9 — Autenticación y roles

- Usuarios, roles (admin / contador / asistente).
- Auditoría: quién cambió qué y cuándo.
- Bloqueo de comprobantes ya revisados.

---

## E10 — Instalador firmado + auto-update

- `tauri build` con instalador `.msi` firmado.
- Canal de actualizaciones (Tauri updater).
- Notas de versión visibles in-app.

---

## E11 — Auditoría / logs / observabilidad

- Log local rotado.
- Vista in-app de "últimas acciones".
- Reporte de errores opt-in.

---

## Backlog libre (sin entrega asignada aún)

- Recordatorios de vencimientos tributarios.
- Conciliación bancaria.
- Integración lectura de extractos bancarios.
- Dashboard ejecutivo por empresa.
- Multi-moneda (NIIF — probablemente fuera de alcance).
- Modo oscuro / accesibilidad.
- Atajos de teclado completos para data entry intensivo.
