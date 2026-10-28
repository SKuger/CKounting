# Registro de decisiones — Contab

Decisiones tomadas durante el desarrollo, con su contexto y razón. Cada decisión queda registrada para **no volver a preguntar lo mismo** en futuras sesiones.

> Si una decisión necesita revisarse, se anota una nueva entrada con `Revisa: D-XXX` y se actualiza el estado de la original a `🔁 Revisada`.

| Estado | Significado |
|---|---|
| ✅ Vigente | Decidida y en uso |
| 🔁 Revisada | Reemplazada por otra decisión (ver "Revisa") |
| ⏸ Pendiente | Anotada, aún sin decidir |

---

## D-001 — Dominio del producto ✅
**Fecha**: 2026-05-28
**Decisión**: Contab es un software de **contabilidad general multi-empresa**, con foco inicial en **revisión de reportes que el contador descarga manualmente de la DIAN** y cruce contra **soportes enviados por el cliente**.
**Razón**: Lo que pidió el usuario explícitamente. Más adelante se amplía a informes contables completos.
**Fuera de alcance explícito**: Conexión directa con la DIAN, uso del token DIAN por empresa.

## D-002 — Stack ✅
**Fecha**: 2026-05-28
**Decisión**: Tauri (shell) + Nuxt 3 (frontend, TS) + Python (sidecar para lógica/DB) + SQLite (datos).
**Razón**:
- El usuario ya trabaja con Python, TypeScript y Nuxt → cero curva.
- Tauri da instalador Windows liviano (~10 MB) vs Electron (~150 MB).
- Python sidecar permite usar `pandas`/`openpyxl`/`pdfplumber` que son lo mejor para procesar reportes contables colombianos.

## D-003 — Una DB SQLite por empresa ✅
**Fecha**: 2026-05-28
**Decisión**: Cada empresa = un archivo `.db` SQLite **independiente**. No hay tabla global de "empresas" en una DB compartida (el catálogo de empresas se infiere escaneando la carpeta de datos).
**Razón**: El usuario explícitamente pidió **aislamiento total** entre empresas para evitar contaminación de datos. Beneficio adicional: backup/entrega a cliente = copiar 1 archivo. Riesgo: queries cross-empresa (reportes consolidados) requieren abrir varias conexiones — se asume aceptable.

## D-004 — Single-user al inicio ✅
**Fecha**: 2026-05-28
**Decisión**: Las primeras entregas son single-user, sin login. La capa multiusuario se aborda en E8/E9.
**Razón**: El usuario aclaró que aunque a futuro serán 2-5 personas, hoy se enfoca en una sola.
**Implicación**: Nada de tablas `users`, sesiones, ni JWT por ahora.

## D-005 — Formatos de entrada DIAN ✅
**Fecha**: 2026-05-28
**Decisión**: Excel (`.xlsx`/`.xls`) y PDF.
**Orden de implementación**: Excel primero (E1). PDF en E4.

## D-006 — Formato de salida de reportes ✅
**Fecha**: 2026-05-28
**Decisión**: Excel `.xlsx` con las **columnas originales** del archivo cargado.
**Razón**: Es lo que los contadores van a seguir trabajando aguas abajo. Otros formatos (PDF, CSV, copiar al portapapeles) quedan en backlog.

## D-007 — Distribución en E1 ✅
**Fecha**: 2026-05-28
**Decisión**: Solo dev mode (`npm run tauri dev`). El instalador `.msi` se posterga a E10.
**Razón**: Iteración rápida en E1 sin invertir tiempo en empaquetado/firma antes de tener algo útil.

## D-008 — Persistencia desde E1 ✅
**Fecha**: 2026-05-28
**Decisión**: Las cargas de Excel se guardan en la SQLite de la empresa desde la primera entrega. NO son solo-en-memoria.
**Razón**: El usuario quiere reabrir cargas previas. Implica definir schema mínimo desde el día 1.

## D-009 — Idioma y contexto fiscal ✅
**Fecha**: 2026-05-28
**Decisión**: UI en **español (Colombia)**. Contexto fiscal **Colombia / DIAN**.
**Implicación**: validación de NIT colombiano, PUC colombiano, terminología local (régimen común/simplificado, retenciones, etc.).

## D-010 — Datos de muestra son falsos ✅
**Fecha**: 2026-05-28
**Decisión**: El usuario va a entregar Excels/PDFs de muestra con **datos falsos**. Se pueden commitear en `docs/samples/`.
**Razón**: Lo aclaró el usuario explícitamente.

## D-011 — Modo de hacer preguntas ✅
**Fecha**: 2026-05-28
**Decisión**: Siempre usar `AskUserQuestion` con **opción múltiple** (2-4 opciones). Evitar preguntas abiertas salvo cuando sea estrictamente necesario.
**Razón**: El usuario lo pidió explícitamente, prefiere decidir rápido y no escribir respuestas largas.

## D-012 — Estructura del Excel DIAN ✅
**Fecha**: 2026-05-28
**Decisión**: El reporte fuente es el consolidado de "Documentos Electrónicos" del portal MUISCA/DIAN. **32 columnas fijas**, layout plano, sin merges, fechas en texto `dd-mm-yyyy`. Estructura documentada en [`docs/excel-structure.md`](excel-structure.md) y verificada con el sample del usuario.
**Razón**: Análisis directo del Excel entregado por el usuario (`Ejemplo_LaDian.xlsx`).
**Cierra**: D-E1-1.

## D-013 — Columnas visibles por defecto en la tabla 🔁 Revisada por D-027
**Fecha**: 2026-05-28
**Decisión original**: Mostrar 10 columnas curadas con `Tercero` virtual.
**Estado**: Reemplazada por D-027 (mostrar todo).

## D-014 — Orden del export ✅
**Fecha**: 2026-05-28
**Decisión**: El Excel exportado de "no conformes" preserva el **orden original de las 32 columnas** del archivo fuente, y agrega `razon_falla` como columna final (#33).
**Razón**: D-006 dice "columnas originales" — preservar orden facilita comparación side-by-side con el archivo original que el contador ya conoce.
**Cierra**: parte de D-E1-2.

## D-015 — Catálogo de tipos de regla de validación ✅
**Fecha**: 2026-05-28
**Decisión**: El motor soporta los siguientes tipos de regla (almacenados con `type` + `params_json` para extensibilidad):
- `cufe_in_folder` — CUFE/CUDE de la fila debe existir en al menos un PDF de una carpeta configurada (Validación 1 del usuario).
- `value_in_list` y `value_not_in_list` — valor de columna debe (o no) estar en lista.
- `numeric_range` — valor numérico en rango (min/max, inclusivo configurable).
- `date_range` — fecha en rango (con formato `dd-MM-yyyy`).
- `regex_match` — string matchea regex.
- `formula` — expresión sobre columnas (ej. `IVA + ` + "`Rete IVA`" + ` <= Total`) con tolerancia numérica.
- `nit_dv_check` — validación módulo 11 con factores DIAN sobre columnas NIT.
- `duplicate_check` — detección de duplicados por clave compuesta (ej. CUFE, o NIT+Prefijo+Folio).
- `iva_rate_consistency` — tasa de IVA debe ser 0%/5%/19% del gravado con tolerancia ±1.
- `period_mismatch` — fecha emisión fuera del periodo del reporte cargado.

**Razón**: Cubre lo que un contador colombiano realmente revisa en un cruce DIAN. Verificado adversarialmente por lente contable.
**Cierra**: D-E1-3 (parcial — falta acordar con el usuario cuáles se implementan en E1 vs después).

## D-016 — Esquema de almacenamiento de reglas dentro de cada empresa.db ✅
**Fecha**: 2026-05-28
**Decisión**: Las tablas de validación (`validation_rule`, `validation_run`, `validation_failure`, `pdf_cufe_index`, `pdf_cufe_value`) **viven dentro del archivo `.db` de cada empresa** (consistente con D-003). NO hay tabla global `company` — la identidad de la empresa es implícita = el archivo `.db` abierto. `validation_rule.type` NO tiene `CHECK(...)` constraint (validación a nivel app) para permitir agregar tipos nuevos sin migración.
**Razón**: D-003 manda aislamiento total. La verificación adversarial encontró que el diseño inicial introducía una tabla `company` que rompía D-003.
**Implicación**: Reglas reutilizables entre empresas requieren un mecanismo de "plantillas" futuro (no E1).

## D-017 — Diseño de la Validación 1 (CUFE en carpeta de PDFs) ✅
**Fecha**: 2026-05-28
**Decisión**:
1. **E1**: solo se schema (`pdf_cufe_index`, `pdf_cufe_value`) y se persiste la regla con su `folder_path`. El motor reconoce el tipo pero **inyecta una advertencia visible** en `razon_falla` para todas las filas en scope: `"Validación CUFE-en-carpeta pendiente — disponible en E4"`. Nunca pasa silenciosa como exitosa.
2. **E4** (no E3 — el plan original lo confundía): implementa la extracción real con `pdftotext -raw -enc UTF-8` + segundo pase con `-layout` + tercer pase con `pyzbar` para QRs (necesario para Movistar/Claro/Tigo).
3. **Detección**: capturar **todos** los tokens `^[a-f0-9]{96}$` (después de strip de whitespace) — la entropía SHA-384 hace falsos positivos despreciables. El match con etiquetas `CUFE:`/`CUDE:`/`CUDS :` es complementario para asignar la etiqueta, no primario.
4. **Cache** keyed por `(realpath(pdf_path), mtime, size)`. Re-indexar solo PDFs nuevos o cambiados.
5. **Scope por defecto**: `Grupo=Recibido` excluyendo `Tipo de documento ∈ {Nomina Individual, Documento soporte con no obligados}` — esos no tienen PDF de tercero por construcción.
**Razón**: Verificadores encontraron que el diseño inicial tenía: flag `-layout=raw` inexistente en Poppler, regex greedy que conflataba CUFE+CUDE adyacentes, y pass-through silencioso que engañaría al contador.
**Cierra**: D-E1-3 (parte cufe). Reemplaza la asignación E3 → E4 para el escaneo de PDFs.

## D-018 — Resolución de códigos UBL antes de mostrar ✅
**Fecha**: 2026-05-28
**Decisión**: `Forma de Pago` y `Medio de Pago` se resuelven a texto legible en la UI usando los mappings UBL documentados en `docs/glosario.md`. El código numérico crudo queda en columna oculta para auditoría/export.
**Razón**: Los números UBL no le dicen nada al contador en la práctica.

## D-019 — IPC Tauri ↔ Python sidecar ✅
**Fecha**: 2026-05-28
**Decisión**: **stdio JSON-lines** (cada request/response es una línea JSON sobre stdin/stdout del proceso Python). No HTTP localhost.
**Razón**: cero superficie de red, sin puerto a gestionar, más rápido de inicializar, suficiente para el throughput de un contador. Tauri tiene primitivas para sidecar con stdio.
**Implicación**: el sidecar Python es un loop simple `for line in stdin: handle(json.loads(line))`.
**Cierra**: D-E1-4.

## D-020 — Librería de tabla en Nuxt ✅
**Fecha**: 2026-05-28
**Decisión**: **TanStack Table (Vue Table)** — headless. Estilos propios con CSS/UnoCSS.
**Razón**: Lo más flexible para columnas configurables, filtros por columna, virtual scroll. PrimeVue/Vuetify imponen estética opinada. TanStack es vanilla, Vue 3 friendly, MIT.
**Cierra**: D-E1-6.

## D-021 — Carpeta de datos del usuario ✅
**Fecha**: 2026-05-28
**Decisión**: Carpeta fija siguiendo convención del sistema operativo:
- Windows: `%APPDATA%\Contab\empresas\<slug-nit>.db`
- Linux (dev/test): `~/.local/share/Contab/empresas/<slug-nit>.db`
- macOS: `~/Library/Application Support/Contab/empresas/<slug-nit>.db`

Donde `slug-nit` = `<nit>_<razon_social_slug>` para que sea humanamente reconocible si el contador navega al folder.

**Razón**: Estándar por SO. Permite backup por carpeta. Coexiste con D-003 (una db por empresa).
**Cierra**: D-E1-5.

## D-022 — Defaults pre-aplicados al cargar el Excel 🔁 Revisada por D-027
**Fecha**: 2026-05-28
**Decisión original**: Aplicar filtro `Estado ≠ Rechazado` por defecto.
**Estado**: Reemplazada por D-027. El usuario quiere ver todo tal cual viene del Excel y elegir después qué filtrar.

## D-023 — Las validaciones reales de E1 son específicas, no genéricas ✅
**Fecha**: 2026-05-28
**Decisión**: E1 implementa **exactamente** estas validaciones del flujo del usuario (NO el catálogo genérico que propuse antes, que queda como reglas opcionales en backlog):

1. **V1 — Soporte CUFE en carpeta**. Tipo de regla `cufe_in_folder`. En E1: schema + warning "pendiente E4" según D-017.
2. **V2 — Inversión de signo en Notas Crédito**. NO es una validación clásica; es una **transformación** que se aplica al cargar (o al evaluar — ver D-E1-11): si `Tipo de documento` contiene "Nota de crédito" → `IVA *= -1` y `Total *= -1`. La inversión se refleja en la tabla, en las columnas derivadas (`Valor Base`, `Base IVA`) y en el export.
3. **V3 — Tarifa de IVA**. Tipo de regla `iva_rate_check`. Lógica:
   - Calcular `Base IVA` = `IVA` / 0.19.
   - Si `|Valor Base − Base IVA| ≤ 5` → IVA al 19% **OK**.
   - Si NO → recalcular `Base IVA` = `IVA` / 0.05.
   - Si `|Valor Base − (IVA/0.05)| ≤ 5` → IVA al 5% **OK**.
   - Si tampoco coincide → **no conforme** con razón "IVA no corresponde a tarifa 19% ni 5%".

**Razón**: Es el flujo que el usuario describió textualmente. Los tipos del catálogo extendido (NIT DV check, duplicate check, regex, formula, value_in_list genérico, etc.) no son los que él revisa hoy; los movemos a backlog hasta que él los pida.
**Implicación**: El motor de E1 corre estas 3 reglas hard-coded en el orden V2 → V3 → V1 (V2 transforma antes de validar). En el backlog, el rule editor genérico (tipos varios con params_json) puede llegar después, pero E1 NO necesita esa abstracción.

## D-024 — Columnas derivadas que la app agrega al cargar el Excel ✅
**Fecha**: 2026-05-28
**Decisión**: Al importar el Excel DIAN, la app **agrega automáticamente** estas columnas calculadas (el contador NO las añade manualmente):

| Columna nueva | Fórmula | Tipo |
|---|---|---|
| `# de factura` | `<Prefijo>-<Folio>` (ej. `DSE-211`) | string |
| `Valor Base` | `Total − IVA` (después de aplicar V2 si es NC) | number |
| `Base IVA` | `IVA / 0.19` (después de aplicar V2; tarifa general por defecto) | number |

**Razón**: El usuario hoy agrega `Valor Base` y `Base IVA` manualmente al Excel antes de revisarlo. Que la app las calcule elimina ese paso y previene errores humanos. `# de factura` es el identificador legible que él usa.

**Implicación**:
- La tabla en UI muestra estas 3 columnas adicionales (configurables como cualquier otra).
- El export Excel **incluye** estas 3 columnas además de las 32 originales y `razon_falla` (D-014 actualizada implícitamente: 32 + 3 + 1 = 36 columnas en el export).
- Si el Excel cargado ya trae estas columnas (porque el usuario antiguo las agregaba manualmente), la app las **sobrescribe** con su cálculo para garantizar consistencia.

**Pendiente de confirmar (D-E1-12)**: separador exacto en `# de factura` — `DSE-211` (sin espacios) vs `DSE - 211` (con espacios). El usuario escribió ambos en el mensaje.

## D-025 — Comportamiento ante IVA = 0 en V3 ⏸ Pendiente
**Fecha**: 2026-05-28
**Estado**: Anotada como hueco — preguntar al usuario antes de implementar V3.
**Problema**: Si `IVA = 0` (excluido / exento), entonces `Base IVA = 0/0.19 = 0` y `Valor Base = Total`. Salvo que `Total = 0`, no coinciden y la fila fallaría V3 como falso positivo.
**Default temporal hasta confirmar**: si `IVA = 0`, V3 hace **skip** (no marca la fila como no conforme). El contador puede revisar manualmente esas filas si lo desea.

## D-026 — Cálculo automático de columnas derivadas (consolida D-024) ✅
**Fecha**: 2026-05-28
**Estado**: Mismo contenido que D-024. Mantengo D-024 como entrada principal.

## D-027 — Mostrar el Excel "tal cual" en la tabla ✅
**Fecha**: 2026-05-28
**Decisión**: La tabla muestra **las 32 columnas originales del Excel + las 3 derivadas** (`# de factura`, `Valor Base`, `Base IVA`), en el orden original con las derivadas al final. **No** columna virtual `Tercero`. **No** filtros pre-aplicados. **No** columnas pre-ocultas.
**Razón**: El usuario dijo "muestra tal cual lo que está en el Excel, después te digo qué columnas eliminamos". Mejor no decidir por él y dejarlo elegir cuando vea el render real.
**Implicación**:
- Anula D-013 y D-022.
- El usuario podrá ocultar/mostrar columnas y configurar filtros via UI cuando pruebe E1.
- Mantenemos el resolver de códigos UBL (D-018) — los códigos numéricos se muestran como texto al lado o se reemplazan; confirmar al implementar.
**Cierra**: D-E1-7.

## D-028 — Formato de razon_falla en el export ✅
**Fecha**: 2026-05-28
**Decisión**: Cuando una fila falla varias validaciones, los motivos se concatenan en **una sola celda separados por `; ` (semicolon + espacio)**.
**Razón**: Elección del usuario — compacto, una fila por documento, compatible con filtros de Excel.
**Cierra**: D-E1-8.

## D-029 — NC × -1 solo al evaluar y al exportar (BD guarda originales) ✅
**Fecha**: 2026-05-28
**Decisión**: La transformación V2 (multiplicar `IVA` y `Total` por -1 para Notas Crédito) se aplica **solo en memoria al ejecutar R-V3 y al generar el Excel exportado**. La BD persiste los valores **originales** tal como vienen del Excel DIAN.

**Implicación crítica para columnas derivadas** (`Valor Base`, `Base IVA`):
- Se calculan al cargar usando los valores **originales** (positivos también en NCs).
- Por tanto, en la tabla UI las derivadas se ven positivas para NCs. Esto puede ser visualmente engañoso al revisar — agregamos un indicador en la columna `Tipo de documento` o un badge `NC` en la fila para que el contador no se confunda.
- Al ejecutar R-V3, el evaluador re-calcula `Valor Base` y `Base IVA` en memoria con `IVA*=-1, Total*=-1` para NCs, y compara con tolerancia ±5.
- Al exportar, se aplica V2 a `IVA`, `Total`, `Valor Base`, `Base IVA` antes de escribir el `.xlsx`.

**Razón**: Elección del usuario — preservar fidelidad al Excel original en la BD.
**Cierra**: D-E1-11.

## D-032 — V1 (CUFE en carpeta de PDFs) implementada real en E1 ✅
**Fecha**: 2026-05-28
**Decisión**: La extracción real de CUFE desde PDFs (planeada originalmente para E4) se adelantó a E1. V1 ya **no es un stub**: para cada fila del Excel, el motor cruza el `CUFE/CUDE` contra el conjunto indexado a partir de los PDFs de la carpeta de soportes.
**Razón**: Hacer V1 stub generaba ruido (todas las filas fallaban con "pendiente E4") y la implementación real era directa con el stack elegido. Sin V1 real, E1 era poco útil.
**Stack**:
- `pdftotext -raw` (Poppler) → primer pase, captura CUFE/CUDE/CUDS labeled o tokens 96-hex sueltos.
- `pdftotext -layout` → segundo pase si el raw devuelve nada.
- `pypdfium2` (render) + `opencv-python-headless` (`cv2.QRCodeDetector`) → tercer pase. Decodifica el QR DIAN cuando la fuente del CUFE está obfuscada (Movistar/Claro/Tigo).
- `Pillow` (dep de `pypdfium2.to_pil`).
**Cierra (parcial)**: el alcance principal de E4. Solo queda OCR de PDFs escaneados (no probable con la muestra actual).
**Tests**: 6/6 PDFs reales extraen CUFE — 5 vía pdftotext, 1 (Movistar) vía QR scan.

## D-033 — Una sola CUFE/CUDE/CUDS por PDF (prioridad CUDS > CUDE > CUFE) ✅
**Fecha**: 2026-05-28
**Decisión**: Cada PDF representa **una** factura, por lo tanto debe indexarse **exactamente un** identificador propio:
- Si el PDF trae etiqueta `CUDS :` → ese (Documento Soporte Electrónico).
- Si no, si trae `CUDE:` → ese (Nota Crédito, POS, Nómina).
- Si no, si trae `CUFE:` → ese (Factura electrónica).
- Si no hay etiqueta, fallback: primer token 96-hex suelto.

Otros valores (p.ej. el CUFE de la factura **padre** referenciado dentro de una NC) se **descartan a propósito**: representan otro documento, no este PDF.
**Razón**: Lo aclaró el usuario explícitamente: "por cada soporte solo debe haber un cufe, o si hay 2 deberian ser el mismo". Antes de esta regla, la NC de Éxito generaba 2 CUFEs (su CUDE + el CUFE de la factura referenciada), inflando el índice y confundiendo el conteo.
**Implicación**: el conteo "CUFEs indexados" en la UI ahora coincide con el número de PDFs útiles.

## D-034 — QR scan multi-DPI para fuentes obfuscadas ✅
**Fecha**: 2026-05-28
**Decisión**: El paso 3 (QR scan con cv2) barre los PDFs en **3 DPIs**: 300 → 400 → 220, recogiendo todos los payloads únicos.
**Razón**: En la muestra Movistar hay 2 QRs en la misma página (pago + DIAN). `cv2.QRCodeDetector` detecta uno u otro según el DPI — a 300 captura el QR de pago, a 400 captura el QR DIAN con el CUFE. Quedarnos con un solo DPI nos perdía el CUFE válido.
**Implicación**: el primer indexado de cada PDF nuevo toma 1–3 s extra cuando llega al paso 3. El cache hace que las re-corridas sean instantáneas.

## D-035 — Carpeta de PDFs separada de la carpeta de Excels ✅
**Fecha**: 2026-05-28
**Decisión**: Cada empresa tiene **dos** carpetas configurables independientes en `empresa_info`:
- `default_folder` — carpeta donde viven los Excels DIAN (`imports/` para los importados).
- `pdfs_folder` — carpeta donde viven los PDFs de soporte (se indexan para V1).

Ambas se seleccionan con el mismo `DirectoryPicker` del frontend.
**Razón**: el usuario suele organizar Excels y PDFs en lugares distintos. Mezclarlos forzaría una jerarquía artificial.
**Migración**: `ALTER TABLE empresa_info ADD COLUMN pdfs_folder TEXT` (idempotente en `_run_migrations`).

## D-036 — Auto-listado y 1-click import desde la carpeta de Excels ✅
**Fecha**: 2026-05-28
**Decisión**: Cuando `default_folder` está configurada, la página de la empresa lista automáticamente sus `.xlsx` / `.xls` con badge `importado` si ya están en la BD (match por `source_path` verbatim). Botón "Importar" por archivo + "Importar pendientes (N)" para batch. El upload externo queda como `<details>` colapsable como fallback.
**Razón**: petición explícita del usuario — "más bien se hace la petición para cargar los excels dentro de esa carpeta al entorno automáticamente".
**Implicación**: el import "en sitio" (no copia el archivo) preserva la ruta original — `source_path` en `excel_load` apunta al archivo en `default_folder`, no a una copia.

## D-037 — Auto-indexing de PDFs al correr validaciones ✅
**Fecha**: 2026-05-28
**Decisión**: `run_validations` y `export_no_conformes` **indexan automáticamente** los PDFs nuevos o modificados antes de evaluar. El usuario no tiene que tocar el botón "Re-indexar" manualmente; ese botón existe solo para depurar.
**Razón**: minimizar fricción. La indexación es incremental (cache por `(folder, path, mtime, size)`), así que en operación normal solo procesa archivos nuevos.
**Implicación**: la primera corrida de validaciones de una carpeta nueva toma unos segundos extra; las siguientes son instantáneas.

## D-038 — Stack de empaquetado tipográfico/visual moderno ✅
**Fecha**: 2026-05-28
**Decisión**: Tema oscuro tipo Linear (fondo `#08090c`, panel `#11131a`, accent `#5e6ad2`), tipografía `Inter` con `letter-spacing` negativo, layout full-width sin `max-width` global, header sticky con `backdrop-filter`. Página de carga usa ancho completo para minimizar scroll horizontal de la tabla.
**Razón**: petición del usuario tras ver el primer prototipo — "esta todo super basico, hazlo màs moderno, lindo, legible y no tan regado".
**Cierra**: D-E1-14 (parte estética).

## D-039 — La columna `Total` se muestra como `Total`, no como `Valor Total` ✅
**Fecha**: 2026-05-28
**Decisión**: Mantenemos el nombre del header del Excel DIAN verbatim (`Total`) en toda la UI y el export. NO renombramos a `Valor Total` ni similar.
**Razón**: D-027 y D-013 — el orden y los nombres originales del Excel mandan. Confirmado al implementar.

## D-041 — NIT inmutable después de creación; razón social editable ✅
**Fecha**: 2026-05-28
**Decisión**: Una vez creada la empresa, el NIT y su DV son **inmutables**. La razón social SÍ es editable desde la UI de la empresa.
**Razón**: El NIT es la identidad fiscal y vive en el nombre del archivo (`<nit>_<slug>.db`). Cambiar el NIT implicaría renombrar el `.db`, migrar referencias y romper backups antiguos. La razón social cambia de verdad (renombres legales, fusiones) → debe poder editarse.
**Implicación**: Si el usuario se equivocó al crear con el NIT incorrecto, el flujo es: crear empresa nueva con el NIT bueno + restore de backup si tenía uno + eliminar la incorrecta.
**Cierra**: D-E2-2.

## D-042 — Archivar (soft delete) por defecto, eliminar permanente con doble confirmación ✅
**Fecha**: 2026-05-28
**Decisión**: La acción primaria de "borrar empresa" la **archiva** (campo `archived` en `empresa_info`, oculta de la lista por defecto). Hay un toggle "Mostrar archivadas" para verlas y un botón "Desarchivar". Existe además una acción separada **"Eliminar permanentemente"** que sí borra el archivo `.db`, y requiere que el usuario escriba el NIT exacto en un campo de confirmación.
**Razón**: Datos contables: borrado accidental sin backup = pérdida real. Soft delete es la opción reversible que cubre 99% de los casos.
**Implicación**: Schema migration `ALTER TABLE empresa_info ADD COLUMN archived INTEGER NOT NULL DEFAULT 0`. `list_empresas` toma opcionalmente `include_archived=true`.

## D-043 — Backup = zip con .db + Excels importados + PDFs de soporte ✅
**Fecha**: 2026-05-28
**Decisión**: El backup de una empresa es un único `.contab.zip` con:
- `empresa.db` (el .db con WAL checkpointed antes para que sea self-contained).
- `excels/<original_filename>` por cada Excel importado (resuelto por `source_path` de cada `excel_load`; se omiten los que ya no existen en disco).
- `pdfs/<original_filename>` por cada PDF en `pdfs_folder` (al momento del backup).
- `meta.json` con NIT, razón social, rutas originales, timestamp, versión de backup, listado de archivos incluidos.

Nombre del archivo: `<slug>_<YYYYMMDD-HHMMSS>.contab.zip`.

**Razón**: Elección del usuario — quiere que el backup sea auto-contenido para mover una empresa a otro PC sin perder los originales.
**Implicación**: Backups pueden pesar varios MB (PDFs). Se escribe a `.tmp` y se hace rename atómico para evitar corrupción si el proceso muere.

## D-044 — Sin campos fiscales adicionales en E2 ✅
**Fecha**: 2026-05-28
**Decisión**: E2 NO agrega `tipo_regimen`, código de responsabilidades DIAN, código CIIU ni otros campos fiscales al `empresa_info`. Se mantiene NIT + DV + razón social + carpetas + archived.
**Razón**: Elección del usuario — mantener simple. Esos campos llegarán cuando E6 (asientos) o E7 (reportes) los necesiten.

## D-049 — Columnas ocultas adicionales por defecto en la tabla ✅
**Fecha**: 2026-05-29
**Decisión**: Se suman a `HIDDEN_BY_DEFAULT` las columnas **`Prefijo`**, **`Folio`** y **`CUFE/CUDE`**.
**Razón**: Petición del usuario — la columna derivada `# de factura` ya muestra `Prefijo-Folio` en formato legible, y `CUFE/CUDE` es un hash largo que satura el ancho de la tabla.
**Implicación**: Total de columnas ocultas por defecto sube a **27 de 36**. El panel "Columnas" sigue permitiendo activarlas individualmente; el export `.xlsx` no se ve afectado (sigue trayendo las 32 originales + 4 derivadas).
**Cierra**: parte de D-013 / D-031 (visibilidad por defecto).

## D-048 — V1 y reporte de faltantes excluyen filas emitidas por la propia empresa ✅
**Fecha**: 2026-05-29
**Decisión**: V1 (CUFE en carpeta de soportes) y el reporte "faltantes de soporte" **omiten** cualquier fila donde `NIT Emisor` coincide con el NIT de la empresa activa.
**Razón**: Petición del usuario. Cuando la empresa misma emitió una factura, ella generó (y por tanto tiene) el documento — no tiene sentido pedirle "soporte" a sí misma ni marcar esa fila como no conforme por falta de PDF.

**Mecánica**:
- Nueva utilidad `validations._normalize_nit(value)` que conserva solo dígitos, tolerante a puntos, guiones y espacios.
- Nueva función `is_self_emitted(row, self_nit)`.
- `evaluate_v1(row, indexed_cufes, *, self_nit=None)` retorna `None` para filas self-emitted.
- `evaluate_rows(..., self_nit=...)` propaga el parámetro.
- Los handlers `run_validations`, `export_no_conformes` y `export_missing_supports` leen `empresa_info.nit` y lo pasan a `evaluate_rows` / `evaluate_v1`.

**Implicación**:
- En la tabla de la carga, filas con `NIT Emisor == empresa.nit` dejan de tener chip ⚠ rojo por V1 — pasan al check verde ✓ (si V3 también pasa).
- El reporte de **faltantes de soporte** ya no las incluye (se ahorra ruido al encargado del cliente).
- V3 (tarifa de IVA) sigue aplicando normalmente — el filtro solo afecta a V1.
- Comparación NIT robusta: `900181831` == `900.181.831` == ` 900181831 ` (se normalizan a solo dígitos).

**Tests** (`test_self_nit_and_missing.py`): `test_v1_skips_self_emitted`, `test_missing_supports_excludes_self_emitted`, `test_evaluate_v1_self_nit_helper`, `test_override_excludes_from_no_conformes` (esta última verifica explícitamente lo que el usuario pidió confirmar: los rows aprobados con el checkbox salen del conteo de no-conformes). **61/61 verdes**.

## D-047 — Reporte de exportación: faltantes de soporte (no más "no conformes") ✅
**Fecha**: 2026-05-29
**Decisión**: El botón principal de exportación de la carga pasa de "Exportar no conformes" a **"Exportar faltantes de soporte"**. Ese reporte solo incluye las filas que **fallaron V1** (CUFE/CUDE no encontrado en la carpeta de PDFs) y tiene exactamente **5 columnas en este orden**:

1. `NIT Emisor`
2. `Nombre Emisor`
3. `# de factura`
4. `Fecha Emisión`
5. `Total`

**Razón**: Petición del usuario. El reporte de "todas las filas no conformes" mezclaba dos tipos de problema (sin soporte + tarifa fuera del 19%) y era ruidoso para enviarle al encargado del cliente. El reporte de faltantes le dice al encargado exactamente qué facturas falta enviar.

**Implicación**:
- Nuevo handler en el sidecar: `export_missing_supports(db_path, load_id, output_path)`.
- El handler antiguo `export_no_conformes` se conserva para compatibilidad (útil si alguien quiere el reporte completo de 36+1 columnas), pero ya no es la acción primaria.
- El reporte de faltantes solo es generable si la carpeta de PDFs está configurada (sino V1 está inactivo). Si no hay carpeta → error "Configura la carpeta de PDFs (soportes) antes de generar este reporte".
- Filas Nota Crédito heredan la inversión V2 — `Total` aparece en negativo en el reporte.
- V3 overrides (D-046) **no afectan** este reporte. Una fila puede tener V3 aprobado pero seguir faltando soporte; va al reporte.
- Filename: `faltantes_soporte_load<id>_<timestamp>.xlsx`.
- Tests: `test_missing_supports_report_has_5_columns`, `test_missing_supports_export_inverts_nc_totals`, `test_missing_supports_errors_when_no_pdfs_folder`.

## D-046 — ⚠️ SUPERSEDE por D-093 — Reversión de D-045 + override manual por fila para V3 ✅
**Fecha**: 2026-05-29
**Decisión**:

**A) Reversión de la lógica de `Base IVA` y `Diferencia`** (revisa D-045):
```
Valor Base = Total − IVA               (siempre)
Base IVA   = IVA / 0.19                (siempre, salvo IVA=0 → 0)
Diferencia = Valor Base − Base IVA     (literal; ≈ 0 cuando la tarifa es 19%)
```
La columna `Base IVA` ya no se "pega" al `Valor Base` cuando la tarifa no cuadra. Refleja siempre el valor real `IVA/0.19`, y la `Diferencia` queda como la diferencia matemática exacta.

**Razón**: El usuario lo pidió explícitamente — "base iva no se debe igualar a valor base, sino que debe ser el valor real".

**B) Override manual por fila para V3** (nueva mecánica):
- Nueva tabla `validation_override (load_id, row_index, validation_code, created_at)` con `UNIQUE(load_id, row_index, code)`.
- En la UI, junto a la columna `Diferencia` aparece una columna pegada a la derecha llamada **"Aprobar"** con un checkbox que solo se muestra para filas con **V3 fallando**.
- Al activarlo, la fila se aprueba: V3 deja de marcarla como no conforme. Persiste en BD.
- El motor (`evaluate_rows`) recibe `overrides_by_row: dict[int, set[str]]` y omite los códigos overrideados al construir las razones.
- Las **otras validaciones (V1)** siguen aplicando — solo se silencia V3 para esa fila.

**Razón**: Petición del usuario para manejar los falsos positivos legítimos de V3 (D1, Movistar, FELE-823) sin necesidad de relajar la fórmula global. El contador revisa manualmente y aprueba caso por caso.

**Implicación**:
- `validations.evaluate_rows` ahora retorna `list[list[tuple[code, message]]]` en lugar de `list[list[str]]`. Hay un helper `failures_to_strings()` para el export legacy.
- Nuevo handler `toggle_validation_override(db_path, load_id, row_index, code, active)`.
- `get_load_rows` y `run_validations` retornan `v3_overrides: int[]` para que el frontend muestre el estado correcto del checkbox.
- En la UI: filas overrideadas tienen tinte verde sutil; filas con V3 fallando muestran el checkbox; las demás filas no muestran el checkbox.
- Tests: 4 nuevos en `test_overrides_and_missing_supports.py` (`test_toggle_override_persists`, `test_get_load_rows_returns_overrides`, `test_run_validations_respects_override`, etc.).

**Cierra**: la conversación abierta sobre falsos positivos de V3. La fórmula sigue intacta (D-023, D-029), pero el contador tiene escape manual.

## D-045 — Columnas derivadas relacionadas a IVA: Base IVA pegada a Valor Base + nueva columna Diferencia 🔁 Revertida por D-046
**Fecha**: 2026-05-29
**Decisión**: Cambia la fórmula de la columna derivada **`Base IVA`** y se agrega una **nueva columna derivada `Diferencia`** al final.

**Lógica (corre al cargar el Excel; D-045 también vive como helper `excel.compute_iva_columns`)**:

```
Valor Base = Total − IVA                       (siempre)

Si IVA == 0:
    Base IVA   = 0
    Diferencia = 0

Sino, sea base_19 = IVA / 0.19
    Si |Valor Base − base_19| ≤ 5 pesos:
        Base IVA   = base_19           (= Valor Base efectivo)
        Diferencia = 0
    Sino:
        Base IVA   = Valor Base        (se igualan en pantalla)
        Diferencia = Valor Base − base_19
```

**Razón**: Petición del usuario. Cuando la tarifa de IVA NO da 19%, la columna `Base IVA` ahora refleja el valor real (= Valor Base) y la columna nueva `Diferencia` deja explícito **cuánto sobra/falta** vs lo que se esperaría a tarifa general — útil para detectar facturas con otros impuestos al consumo (`INC`, `INC Bolsas`, `Timbre`, `IC Datos`, etc.) o mezcla de items 19% + excluidos.

**Implicación**:
- `DERIVED_COLUMNS` pasa de 3 a 4 entradas (`#factura`, `Valor Base`, `Base IVA`, `Diferencia`).
- El export ahora tiene **37 columnas** (32 originales + 4 derivadas + `razon_falla`) en lugar de 36 (D-014 implícitamente actualizada).
- En la tabla UI, `Diferencia` aparece al final, en el grupo "Importes" del panel de columnas, visible por defecto.
- V2 (NC × −1) recalcula `Base IVA` y `Diferencia` sobre los valores invertidos para mantener consistencia al evaluar y exportar.
- V3 (validación de tarifa) **no cambia**. Sigue marcando "IVA no corresponde a tarifa 19% ni 5%" cuando ni 19% ni 5% encajan. La columna `Diferencia` complementa al mensaje con el valor numérico exacto.
- `fetch_load_rows` ahora **recomputa las derivadas en cada lectura**, así las cargas viejas (importadas antes de D-045) obtienen `Diferencia` automáticamente sin re-importar.

**Tests** ([test_excel.py](apps/core/tests/test_excel.py)): `test_diferencia_zero_when_iva_at_19pct`, `test_diferencia_nonzero_when_iva_offrate` (caso D1: diff ≈ 73 = INC Bolsas exacto), `test_diferencia_zero_when_iva_zero`. **47/47 verdes**.

**Cierra**: parte de la conversación abierta sobre los falsos positivos de V3 — ahora son **visibles y cuantificados** en la columna nueva sin cambiar la regla de validación.

## D-040 — Mostrar el CUFE encontrado bajo cada PDF + copiar al portapapeles ✅
**Fecha**: 2026-05-28
**Decisión**: En el panel "Soportes PDF" cada PDF muestra debajo de su línea principal el valor `CUFE/CUDE/CUDS:` extraído + un botón `⧉` para copiarlo al portapapeles. El chip de estado dice "CUFE encontrado" / "CUDE encontrado" / "CUDS encontrado" según el label real.
**Razón**: petición del usuario — "sería muy bueno que abajo de cada soporte diga el cufe encontrado".

## D-031 — Columnas ocultas por defecto en la tabla ✅
**Fecha**: 2026-05-28
**Decisión**: La tabla de la carga oculta por defecto **21 columnas** (siguen en los datos y en el export — solo no se muestran). El usuario las puede mostrar desde el panel "Columnas" en la barra superior; hay botones "Mostrar todo" y "Restaurar" para volver al default.

**Columnas ocultas por defecto**:
- Identificación: `Divisa`, `Forma de Pago`, `Medio de Pago`, `Fecha Recepción`, `Estado`, `Grupo`
- Impuestos: `ICA`, `IC`, `INC`, `Timbre`, `INC Bolsas`, `IN Carbono`, `IN Combustibles`, `IC Datos`, `ICL`, `INPP`, `IBUA`, `ICUI`
- Retenciones: `Rete IVA`, `Rete Renta`, `Rete ICA`

**Columnas visibles por defecto (14)**:
`Tipo de documento`, `CUFE/CUDE`, `Folio`, `Prefijo`, `Fecha Emisión`, `NIT Emisor`, `Nombre Emisor`, `NIT Receptor`, `Nombre Receptor`, `IVA`, `Total`, `# de factura`, `Valor Base`, `Base IVA`.

**Razón**: Elección directa del usuario después de ver E1 funcionando — son las columnas que no usa en su revisión diaria pero que sí deben estar disponibles para auditoría/export.
**Implicación**: El export sigue incluyendo las 36 columnas (D-014, D-027). El panel persiste solo dentro de la sesión actual; persistir entre sesiones lo dejamos para más adelante.
**Cierra**: D-E1-14.
**Fecha**: 2026-05-28
**Decisión**: `# de factura` = `<Prefijo>-<Folio>` con **guion sin espacios**. Ejemplo: `DSE-211`, `94DD-49995`, `TCNC-1952292`.
**Razón**: Elección del usuario — compacto, estilo identificador.
**Cierra**: D-E1-12.

---

## D-050 — Unificar Contab + scraper DIAN en un monorepo ✅

**Decisión**: Los dos proyectos (Contab y el *"DIAN RUT Automator"*) viven en **un solo repo**, `SKuger/CKounting` (privado). El scraper entra como `apps/dian-rut/`, copia limpia del original `~/Documentos/proyects/Contabilidad_EXT` (que se conserva intacto fuera del repo).

**Razón**: el usuario quiere "un gran aplicativo, no dos separados" y unificarlos a futuro. Contab ya usaba estructura `apps/`, así que el monorepo es la vía natural. Se ignoran del scraper: `venv/`, `browser_profile/` (cookies de sesión), `debug_html/` (PII real de terceros), `results/`, `uploads/`.

**Nota de cuentas**: el repo vive bajo la cuenta `SKuger` (distinta de `SKuger01`, la sesión gh habitual).

## D-051 — El scraper corre como 2º sidecar FastAPI, no fundido en el sidecar stdio ✅

**Decisión**: `apps/dian-rut/` se mantiene como servicio FastAPI (uvicorn, puerto local `8756`), levantado on-demand por Nuxt (`server/utils/dianSidecar.ts`). **No** se reescribe para el sidecar stdio JSON-lines de `apps/core` (D-019).

**Razón**: el scraping es asíncrono, de larga duración y reporta progreso en vivo por WebSocket — encaja con FastAPI, no con el modelo pregunta-respuesta corto del stdio sidecar. Reescribirlo perdería el streaming de progreso y sería una reescritura grande. Compatible con el Tauri futuro (E10), que gestiona varios sidecars.

## D-052 — Unificación en el frontend: página nativa Nuxt + proxy `/api/dian/*` ✅

**Decisión**: La UI de consulta se **reconstruye nativa en Nuxt** (página `/consulta-dian`, mismo tema), no se embebe la UI glassmorphism original. El frontend habla con el scraper así: HTTP (subida, descarga, estado, plantilla) **proxeado** vía rutas `/api/dian/*` para un solo origen; el WebSocket de progreso conecta **directo** a `ws://localhost:8756/ws/{id}` (Nitro no proxea WS cómodamente y es todo localhost).

**Razón**: experiencia unificada de verdad (un solo estilo, una sola ventana) sin pelear con CORS en las llamadas HTTP.

---

## D-053 — El frontend adopta el design system Dandelyon (sub-marca Órbita) ✅
**Fecha**: 2026-06-28
**Decisión**: `apps/desktop` deja su dark-theme propio y **consume el design system Dandelyon**, sub-marca **Órbita (Contabilidad)**, vía *copy-in* desde el repo hermano `design-studio` (`SKuger/DandeLyon-DesignSystem`). Stack: tokens shadcn + Tailwind v4 (`@tailwindcss/vite`) + reka-ui + shadcn-nuxt + @nuxt/fonts, `ssr:false`. Look horneado con `.theme-orbita` (acento índigo `#2b1dc3`, sol `#FDB813`) + `data-*` en `<html>` (concept=faro, spine=beacon, strength=definido, density=media, accent-spread=sutil, swell=alto, ocean-tint=accent, fraunces/beam=on). El store `usePlayground()` se reemplaza por el composable mínimo `app/composables/useBrand.ts`; NO se copia el panel "Control de marca" ni los componentes solo-playground.
**Razón**: issue `SKuger/CKounting#1`. Unifica la identidad visual con el resto de la familia Dandelyon y aporta un shell maduro (sidebar + topbar + ⌘K + beacon).
**Regla de oro**: en `.vue`/`.ts` solo tokens semánticos (`bg-primary`, `text-status-error`), nunca hex crudo ni utilidades de paleta; los hex viven en `main.css` y en SVGs de marca.
**Implicación**: deps nuevas incluyen `@lucide/vue` y `typescript`, que los componentes `ui/` verbatim requieren aunque el issue no los listó. Trabajado en la rama `feat/design-system-orbita` (commit por fase, sin trailer de co-autoría).

## D-054 — La migración del design system se hizo solo en el shell; las páginas quedan diferidas ✅
**Fecha**: 2026-06-28
**Decisión**: En esta entrega solo se migró el **shell** (layout: sidebar + topbar). Las **páginas** reales (Empresas, Carga, Consulta DIAN) y los componentes `DirectoryPicker`/`ToastContainer` **conservan su CSS propio viejo** y se ven crudas temporalmente; se re-tematizan a tokens/shadcn en una sesión de seguimiento.
**Razón**: elección explícita del usuario ("solo shell, páginas después") para ver el shell Órbita rápido sin rehacer todas las páginas de una vez. Cierra la Fase 8 del issue a nivel shell; el "cero hex crudo" total queda pendiente para las páginas.
**Implicación**: hasta re-tematizar, el interior de las páginas no usa tokens. El `main.css` viejo se reemplazó completo, así que las clases bespoke (`.card`, `table.data`, `.chip`, etc.) ya no existen — el follow-up debe reconstruir esas vistas con componentes `ui/`.
**Actualización 2026-06-28 (mismo día)**: el follow-up se hizo enseguida. **Todas** las páginas (`index`, `empresa`, `load`, `consulta-dian`) y los componentes `DirectoryPicker` (→ `Dialog`) y `ToastContainer` se re-tematizaron a shadcn/tokens. Regla de oro verificada (0 hex crudo / 0 utilidades de paleta / 0 tokens viejos). La tabla `@tanstack` de `load.vue` mantiene CSS scoped pero **basado en tokens** (`--muted`, `--border`, `--status-*`, `color-mix`) para las columnas sticky y los tints de fila. Fase 8 del issue cumplida en toda la app. Aparte: el crédito `MakerCredit` se actualizó a «Creado por: SKuger · V<version>» localmente como stopgap (design-system issue #1 sigue abierto para la fuente compartida).

---

## D-055 — Densidad de "instrumento" + mejor uso del viewport (pase UX) ✅
**Fecha**: 2026-06-28
**Decisión**: Tras una auditoría UX (queja del usuario: "mucho scroll, espacio desperdiciado"), se ajusta el sistema de densidad y los layouts de las páginas para una herramienta densa, no una landing:
- **Densidad como única palanca real** (en `main.css`): `--pg-section-gap` por densidad (consumida por el concepto faro, resolviendo la colisión de especificidad que clavaba el gap), padding de `[data-pg-content]`, y reglas que comprimen el **interior de las Card** (`[data-slot=card|card-header|card-content|card-footer]`), colocadas tras los concept-skins para ganar el desempate. Una palanca mueve todo el aire.
- **Densidad horneada = `compacta`** (era `media`) en `nuxt.config.ts` (`<html data-density>`). Solo afecta el contenido (`[data-pg-content]`), no el shell.
- **Superficies de trabajo full-width** (`max-w-[120rem]`); solo flujos de lectura conservan cap (Consulta DIAN `max-w-5xl`).
- **Scroll en el panel, no en la página**: `load.vue` con altura flex (root `flex h-full min-h-0` → tabla `flex-1` → wrapper `height:100%`), elimina el doble scroll; listas largas (PDFs) con `max-h` + overflow interno.
- **Patrones**: Empresas = franja de stats/accesos + lista grid + "Nueva empresa" en `Dialog`. Detalle empresa = maestro-detalle (Archivos+Cargas angosto | PDFs ancho) + acciones de mantenimiento en un menú ⋯ (Popover).
**Razón**: petición directa del usuario; auditoría confirmó que la raíz era la "torre de espaciado" de catálogo shadcn + caps de ancho que tiraban 25-30% del viewport.
**Implicación**: el design system de Contab queda con densidad `compacta`; si una sub-marca/consumidor quiere más aire, la palanca `data-density` lo gobierna sin tocar componentes.

---

## D-056 — SidebarUser: gestor de cuenta + preferencias reales (consumo del DS, issue #2) ✅
**Fecha**: 2026-06-28
**Decisión**: Se consume del DS (`SKuger/DandeLyon-DesignSystem#2` / PR #4) el estándar *dual-source* de `SidebarUser`: composables `useUser` (multi-cuenta: editar/añadir/eliminar — nunca la última; persistido) + `usePrefs` (preferencias reales aplicadas al DOM) + efectos CSS (`data-reduce-motion`, `data-contrast`). En Contab:
- **`usePrefs` es la ÚNICA fuente de tema/densidad/escala.** El toggle del topbar y la acción ⌘K enrutan por `usePrefs`; `useBrand` pierde su manejo de tema. La densidad horneada (D-055, `compacta`) pasa a ser el **default** de `usePrefs.density` (el usuario puede cambiarla y persiste).
- **Sin backend de sesión (D-004 single-user)**: no hay auth que inyectar, así que el `localStorage` (`contab-user-accounts`, `contab-user-prefs`) ES la fuente real. Se siembra **una cuenta neutra editable** ("Mi cuenta"); se eliminan los perfiles demo del DS (Carlos Kuger/Ana Ríos).
- **Notificaciones** (preferencia) controlan el badge de la campana del topbar.
**Razón**: issue `SKuger/CKounting#2`. El DS define que los componentes compartidos son dual-source con features reales (no mocks).
**Conciliación (en vivo)**: tema/densidad/escala/reduce-motion/alto-contraste se aplican al togglearlos; editar perfil se refleja; añadir/eliminar cuenta persiste; sin datos demo; cero errores. Hecho por etapas (composables → css → componente → cableado), commit por etapa.
**Pendiente menor**: `region`/`notifications` quedan persistidas; cablear `region` al formato de números de las tablas es incremental (no bloquea la aceptación).

---

## D-057 — Shell de escritorio = Electron (supersede D-002 Tauri) ✅
**Fecha**: 2026-06-28
**Decisión**: El empaquetado de escritorio (E10) usa **Electron**, no Tauri. Electron envuelve la arquitectura actual tal cual: corre el **servidor Nitro (Node)** como `child_process` (con el Node embebido de Electron vía `ELECTRON_RUN_AS_NODE`), y Nitro lanza los sidecars Python como hasta ahora. El shell vive en **`apps/shell/`** (separado de `apps/desktop` para no ensuciar el árbol Nuxt).
**Razón**: la app **no es un SPA estático** — depende en runtime de Nitro para `/api/*` y del spawn de los sidecars. Tauri obligaría a empacar Node como sidecar o reescribir `server/api` en Rust (mucho más trabajo), y su ventaja de "shell liviano" se diluye porque igual empaquetamos Python (~200 MB). **Supersede D-002** (Tauri, previo a esta arquitectura).
**Mecánica**: los sidecars se empaquetan con **PyInstaller (onedir)** y Nitro los spawnea vía env-hooks nuevos: `CONTAB_SIDECAR_BIN`, `DIAN_SIDECAR_BIN` (si están, ejecuta el `.exe` directo; si no, dev `python -m`). Poppler/`pdftotext` se bundlea y se resuelve con `CONTAB_PDFTOTEXT`. Verificado end-to-end en Linux (Nitro construido + binario PyInstaller responden por RPC).

## D-058 — DIAN en v1 sin Chromium bundleado (modo CDP) ✅
**Fecha**: 2026-06-28
**Decisión**: La Consulta DIAN se incluye en v1, pero **no se empaqueta el navegador de Playwright** (~300 MB). El scraper usa el **Chrome real del usuario** vía CDP (`--remote-debugging-port=9222`) — que ya es su modo preferido (evade Cloudflare) y cuya UI ya existe. Los dirs escribibles del sidecar (uploads/results/errors/browser_profile) se reubican a `%APPDATA%\Contab\dian` vía `DIAN_WORKDIR`; `static/` viaja read-only en el bundle (`sys._MEIPASS`).
**Razón**: instalador más liviano y robusto; el fallback automatizado con Chromium propio es propenso a bloqueos. (Opcional futuro: botón "instalar navegador" con `playwright install` on-demand.)

## D-059 — Sin firma Authenticode; auto-update por sha512; releases en repo público ✅
**Fecha**: 2026-06-28 (cierra D-E10-1)
**Decisión**: No se compra certificado de firma Windows (Authenticode) — habrá warning de SmartScreen en la 1ª instalación ("Más información → Ejecutar de todos modos"). El **auto-update** (`electron-updater`) funciona igual: verifica integridad por **sha512** desde `latest.yml`, independiente de la firma. El instalador es **NSIS per-user** (`%LOCALAPPDATA%`, sin UAC). Build en **GitHub Actions `windows-latest`** (gratis).
**Hosting de updates**: pendiente de decidir; el cableado queda listo apuntando a un **repo público de releases** (`SKuger/CKounting-releases`, por crear) para que el cliente descargue sin token (el código sigue privado). El CI hoy hace `--publish never` + sube el instalador como artefacto.

---

## D-060 — Hosting de releases resuelto: repo público + GH_TOKEN, con compuerta de borrador ✅
**Fecha**: 2026-06-29 (resuelve el "pendiente" de D-059)
**Decisión**: El hosting de updates es el repo público **`SKuger/CKounting-releases`** (creado). El código sigue en el privado `SKuger/CKounting`. Para que el CI pueda publicar en ese repo distinto se usa un **PAT** (fine-grained, solo `CKounting-releases`, Contents: RW) guardado como secreto **`GH_TOKEN`** en CKounting — el `GITHUB_TOKEN` por defecto no alcanza a otro repo. El cliente **descarga y se auto-actualiza sin ningún token** porque el repo es público (`…/releases/latest`).
**CI**: el paso *Build installer* publica condicional: `--publish always` si existe `GH_TOKEN`, si no `--publish never` (nunca rompe el build).
**Compuerta de calidad (elección del usuario)**: electron-builder sube los releases como **borrador (draft)** por defecto y **así se deja** — el tag genera el borrador, el usuario prueba el `.exe` y hace clic en **"Publish release"** (o `gh release edit <tag> --draft=false`) cuando está listo. *No* se usa `releaseType: release` (publicación automática) a propósito, para revisar antes de que llegue al cliente.
**Gotcha resuelto**: el repo de releases debía tener ≥1 commit (rama default) o la publicación falla con `422 Repository is empty`. Se inicializó con un README; no se repite.
**Primer release publicado**: v0.1.2 (favicon/icono CK ya horneado).

---

## D-061 — BD del programa (contab.db): modelo de DOS niveles (no monolito) ✅
**Fecha**: 2026-07-03 (0.1.4)
**Decisión**: Se añade una **BD global del programa** en `%APPDATA%\Contab\contab.db` (`program_db.py`) para datos **transversales**: perfil de **usuario** (persiste al cerrar — antes se perdía), **ajustes**, y un **registro central de empresas** (`empresa_registry`: nit, dv, razón, `db_path`, fechas, `meta_json` para firmas/correos/fechas futuros). **Complementa D-003, no lo revisa**: los datos fiscales siguen **una `.db` por empresa** (aislados); el registro solo *referencia* cada `.db` por ruta.
**Descartado explícitamente (con el usuario)**: el **monolito** (una sola DB con `empresa_id` por fila) — mezcla datos en un archivo (contra D-003), riesgo de fuga si se olvida filtrar, y una corrupción afecta a todas. SQLite además **no tiene esquemas** (no hay `CREATE SCHEMA`), así que "esquemas por empresa" no aplica.
**Migración**: `sync_registry()` al arrancar el sidecar registra en el catálogo las empresas ya existentes en disco; `create_empresa` registra las nuevas. Comandos: `program_get/save_user`, `program_get/save_settings`, `program_list_empresas`, `program_touch_empresa`.

## D-062 — El MES es el contenedor: crear mes → cargar su Excel + su carpeta de soportes ✅
**Fecha**: 2026-07-03 (0.1.4) · *revisa la idea inicial de "mover por documento"*
**Decisión**: La unidad organizadora es el **mes (`periodo` = `YYYY-MM`)**, un **contenedor/ambiente** que el usuario **crea** (`create_periodo`) y **dentro** del cual carga **su** Excel (`import_excel {periodo REQUERIDO}` → `excel_load.periodo`) y elige **su** carpeta de soportes (`set_periodo_pdfs_folder`, tabla `periodo_folder`). `run_validations` cruza el Excel del mes contra la carpeta **de ese mes**. Comandos: `create_periodo`, `list_periodos` (incluye meses vacíos), `set_periodo_pdfs_folder`, `delete_periodo`, `set_load_periodo` (mover el Excel a otro mes).
**NO hay carpeta de soportes global** — `periodo_pdfs_folder` **no** cae a `empresa_info.pdfs_folder`; sin carpeta del mes → V1 inactivo con aviso. `set_pdfs_folder` (empresa) queda obsoleto.
**El periodo vive a nivel de LOTE (Excel), no por fila.** Migración: `excel_load.periodo` se backfillea del mes dominante de "Fecha Emisión" en BD viejas.

## D-063 — Papelera / borrado a nivel de Excel y de mes (NO por fila) ✅
**Fecha**: 2026-07-03 (0.1.4)
**Decisión**: Lo que se mueve/borra es el **Excel cargado** y el **mes**, nunca filas sueltas. `excel_load.deleted_at` (papelera del Excel): `soft_delete_load`/`restore_load`; `list_loads` la oculta salvo `include_deleted`. `delete_periodo` borra el mes y su(s) Excel (hard delete, cascada). **La tabla del Excel NO tiene acciones por fila** (sin mover-de-mes ni papelera por fila). *(Descarta la variante inicial `soft_delete_rows`/`move_rows_periodo`.)*

## D-064 — La tabla del Excel se mantiene igual (mapeo posicional) ✅ (revisa el intento de row_index explícito)
**Fecha**: 2026-07-03 (0.1.4)
**Decisión**: Como no se opera a nivel de fila, `get_load_rows`/`fetch_load_rows` **quedan como estaban** (no inyectan `row_index`/`periodo` en las filas) y `run_validations` mapea fallas/overrides por **posición** (igual que antes). El intento previo de transportar `row_index` explícito (necesario solo si se filtraban filas) se **revirtió** al eliminarse las operaciones por fila.

## D-065 — Consulta de Inconsistencias DIAN (razón social por NIT+DV) ✅
**Fecha**: 2026-07-03 (0.1.5)
**Decisión**: Segunda consulta DIAN, **separada de Terceros** (D-050..D-052). El botón "Consulta DIAN" del sidebar pasa a ser el grupo desplegable **"Consultas DIAN" → Terceros + Inconsistencias**, cada una con su página (`/consulta-dian`, `/consulta-inconsistencias`); `flatNav` se aplana para que ⌘K y el breadcrumb sigan operando con hojas.
A diferencia de Terceros (FastAPI + Playwright, sortea Cloudflare), **Inconsistencias scrapea `DefSelPublicacionesExterna.faces` (MUISCA, JSF/Mojarra, sin Cloudflare) por HTTP plano desde el sidecar de `apps/core`** (solo `urllib`, sin dependencias nuevas). Flujo: GET (ViewState + cookies) → POST (numNit + dv) → la respuesta ya trae la Razón Social. Tres RPCs: `parse_nit_dv` (lee Excel NIT/DV, normaliza NITs, **autocalcula el DV faltante** con módulo 11), `consulta_inconsistencias` (una fila → razón social; **nunca lanza**, el error viaja en el payload) y `export_inconsistencias` (xlsx NIT/DV/Razón Social vía xlsxwriter).
La UI consulta **fila por fila desde el cliente** (progreso en vivo + reintentar fallidos + pausa cortés de 450 ms), **no en lote**: respeta el timeout de 30 s de `callSidecar` y evita martillar el balanceador de la DIAN. Es una consulta **pública** (sin token/login). Probado con 115 NITs reales (102 encontrados, 0 errores).

---

## D-066 — Renombrar soportes en la misma carpeta según el cruce CUFE ↔ fila del Excel ✅
**Fecha**: 2026-07-14
**Decisión**: Nueva acción en la página de Carga: renombrar los PDFs de soportes al patrón **`DD-MM_NIT_RAZON-SOCIAL_FACTURA.pdf`** (`DD-MM` de la Fecha de Emisión, decidido por el usuario sobre Fecha de Recepción). El match PDF→fila es por **CUFE/CUDE normalizado** (mismo `_norm_cufe` que el indexado). Módulo `rename_soportes.py` (RPC `rename_soportes`), reutiliza el índice de `pdf_cufe`.
Reglas confirmadas con el usuario: **renombrar IN PLACE** en la misma carpeta (no copiar a otra); los PDFs **sin match** (sin CUFE, o CUFE que no está en el Excel del mes) se **dejan intactos y se reportan**, nunca se inventan nombres. Nunca sobreescribe: colisiones → sufijo `_2`, `_3`… Idempotente (un PDF que ya tiene el nombre destino se salta). Deja un manifiesto **`_renombrados.csv`** (nombre_nuevo, nombre_original, cufe, fecha_hora) para auditar/revertir. La UI muestra primero un **preview (dry-run)** con conteos y la lista actual→nuevo antes de aplicar.

## D-067 — Extracción de CUFE robusta a números pegados + QR como verificación de los casos dudosos ✅
**Fecha**: 2026-07-14
**Problema**: Facturas tipo **Telesentinel** imprimen el número de autorización DIAN (16 dígitos puros) en la línea inmediatamente anterior al CUFE, y éste viene partido en 3 líneas. El regex viejo `(?:[a-f0-9]\s*){96}` colapsaba todo el espacio en blanco y **pegaba** los dígitos de autorización al CUFE (los dígitos también son hex), devolviendo un token de 96 chars **equivocado** y sin etiqueta.
**Decisión**:
1. **Reconstruir el CUFE respetando límites de token**: se agrupan segmentos hex separados por espacios que sumen exactamente 96 y contengan al menos una letra a-f. El número de autorización es su propio token → ninguna ventana de 96 puede abarcar parte de él + parte del CUFE. Se conserva la prioridad **CUDS > CUDE > CUFE** (D-033) y la asociación etiqueta→valor.
2. **QR como verificación extra SOLO en lecturas que fallan** (decisión del usuario: "en todos" tardaba ~136 s / 37 PDFs, excede el timeout de 30 s → se limita a los dudosos, ~29 s / 8 PDFs). Un hit de texto **etiquetado** es alta confianza → se retorna sin QR. Si el texto no da nada **o** da un token **sin etiqueta** (baja confianza) → corre el QR, que es **autoritativo** (fuente machine-readable de la DIAN). El resultado se cachea en `pdf_cufe_index`, así que el costo del QR es una sola vez por PDF.
**Verificado**: Telesentrinel (jul y may) → CUFE correcto (`b55c…683441`, coincide con el Excel, vía qr-scan con etiqueta CUFE); 73/73 tests verdes; carpeta real de mayo sin regresiones.

## D-068 — Panel "Soportes del mes": visor con/sin CUFE + re-verificar sin re-subir Excel ✅
**Fecha**: 2026-07-14
**Problema**: La tabla de validaciones muestra el resultado del **último `validation_run` guardado** — no se refresca sola. Tras corregir la extracción (D-067), el usuario no veía el cambio hasta re-validar, y no había forma de ver **cuáles** PDFs de la carpeta del mes no obtuvieron CUFE.
**Decisión**: Nuevo panel colapsable **"Soportes del mes"** en la página de Carga (RPC `list_load_soportes`), sobre la carpeta **del periodo del load** (no la de la empresa, que en el modelo por-mes está vacía — D-062). Muestra conteos (`N archivos · M con CUFE · K sin CUFE`) y, por archivo, el estado (✓ con CUFE / ⚠ sin CUFE / • sin verificar) y **el CUFE encontrado** (decisión del usuario: con/sin y el valor si lo tiene). Botón **"Re-verificar soportes"** = re-indexa la carpeta del mes (`force`: limpia caché + re-extrae) y re-corre V1, **sin re-subir el Excel**. El panel se refresca solo tras validar/renombrar. Reutiliza `pdf_cufe.list_indexed_pdfs`.

## D-069 — Consulta de Inconsistencias: soportar personas naturales, no solo empresas ✅
**Fecha**: 2026-07-15 (0.1.7)
**Problema**: El Excel de consulta trae empresas Y personas naturales. `DefSelPublicacionesExterna.faces` responde con **campos distintos** según el documento: empresa → "Razón Social"; persona natural → **Primer Nombre + Otros Nombres + Primer Apellido + Segundo Apellido**. El parser solo leía "Razón Social", así que las personas salían sin resultado.
**Decisión**: `consultar()` ahora, si no hay "Razón Social", lee los 4 campos de persona y **compone el nombre** en orden natural (`nombres apellidos`); devuelve además `tipo` ('empresa' | 'persona'). El **documento de la persona va en la misma columna NIT** (así lo hace el usuario en el portal), por lo que el parser del Excel de entrada NO cambia. El export pasa a columnas **NIT, DV, "Razón Social / Nombre", Tipo**; la UI muestra la columna Tipo. Verificado en vivo (860002180→empresa; 3358520→"ALDEMAR PATIÑO CHICA"; 80415208→"CARLOS ALBERTO KUGER ARBELAEZ").

---

## D-070 — Plan Único de Cuentas (PUC) por empresa ✅
**Fecha**: 2026-08-14 (E5)
**Decisión**: Cada empresa maneja su **PUC** (catálogo de cuentas contables) a nivel empresa (no por mes). Se sube el **dump Excel** que exporta el software contable (preámbulo con empresa+NIT, encabezado `Código · Nombre · Categoría · Clase · Relación con · Maneja vencimientos · Diferencia fiscal · Activo · Nivel agrupación`, pie `Procesado en:`). Módulo `puc.py` (`load_puc`/`persist_puc`/CRUD/`export_puc`) + tablas `puc_account` y `puc_import`; RPCs `puc_import`/`puc_list`/`puc_save_account`/`puc_archive_account`/`puc_delete_account`/`puc_export`; endpoint `upload-puc`; página **`/puc`** (tabla con indentado por nivel, filtros clase/nivel/estado, buscador) enlazada desde la card "Plan de Cuentas" en `empresa.vue`.
Reglas confirmadas con el usuario: **subir dump = fusionar por `codigo`** (upsert: actualiza las existentes, agrega las nuevas, **conserva** las cuentas manuales; nada se borra; `fuente` distingue dump/manual). **Bloquear** la subida si el **NIT del encabezado no coincide** con la empresa. El **nivel** se deriva de la longitud del código (1=Clase, 2=Grupo, 4=Cuenta, 6=Subcuenta, 8=Auxiliar → `nivel = 1 + len//2`). Archivar es soft (nunca borra por importar); hay historial de dumps (`puc_import`). Verificado con el dump real (885 cuentas, NIT 900181831). Tests: 12 (parseo, niveles, upsert/merge, dry-run, bloqueo NIT, CRUD, archivar, export).

---

## D-071 — Contrato único de error en la API interna (2026-09-20)

`/api/rpc` y todos los endpoints de subida devuelven **siempre HTTP 200** con `{ok:true, result}` o `{ok:false, error}`. Un error de dominio del sidecar no es un fallo de transporte. Con status 500, `$fetch` lanza antes de que el llamador lea el cuerpo, así que los mensajes cuidados en español (bloqueo por NIT, formato del Excel) nunca llegaban al usuario: veía "FetchError: 500 Internal Server Error". Los 4xx/5xx quedan para fallos reales de transporte. `list-dir.get` conserva sus códigos HTTP por ser un GET con semántica propia.

---

## D-072 — V3 se evalúa en espacio de IVA (2026-09-20)

La comprobación de tarifa compara `|IVA − base × tarifa| ≤ tolerancia`, no `|base − IVA/tarifa| ≤ tolerancia`. Dividir por la tarifa amplifica el redondeo del IVA por 1/tarifa: la tolerancia de ±5 pesos sobre la base equivalía a ±0,95 pesos de IVA al 19% y a solo ±0,25 al 5%, así que casi toda factura del 5% con el IVA redondeado al peso fallaba V3 sin motivo. La tolerancia sigue siendo `V3_TOLERANCE_PESOS = 5.0` y ahora significa literalmente "hasta 5 pesos de diferencia en el IVA".

---

## D-073 — Un importe ilegible es un error, nunca un 0 (2026-09-20)

`_to_number` distingue tres casos: celda **vacía** → `None` → se persiste 0 (ausencia legítima); valor **legible** → número; valor **presente pero ininterpretable** → `ExcelParseError` con fila y columna. Antes los dos últimos colapsaban al mismo 0: un importe mal leído aprobaba V3 en silencio (IVA = 0 se omite) y descuadraba el reporte sin ninguna señal.

Corolario: ante formatos **ambiguos** se para en vez de adivinar. `"10.000"` puede ser diez mil (es-CO) o diez (en-US) y equivocarse son tres órdenes de magnitud. Se aceptan solo formas sin ambigüedad: `1.234,56`, `1234,56`, `1.234.567`, `1234.56`, `1234`, `(1234)`.

---

## D-074 — Los datos de un backup no deciden dónde se escribe (2026-09-20)

El `meta.json` de un `.zip` de backup es entrada externa (los backups se intercambian por correo). `paths.empresa_slug` reduce el `nit` a dígitos y `backup._assert_dentro_de` verifica que el destino quede dentro de la carpeta de empresas. Antes el `nit` se interpolaba crudo en el nombre del archivo, así que un backup con `nit: "../../../evil"` escribía fuera.

---

## D-075 — Los importes son Decimal, no float (2026-09-20)

Todo importe vive como `Decimal` cuantizado a **2 decimales** con `ROUND_HALF_UP` (la convención contable, no el `ROUND_HALF_EVEN` de Python). La conversión a `float` ocurre **solo en los bordes**: `money.to_json` para el JSON hacia la UI y `_coerce_cell` para las celdas de xlsxwriter. La aritmética no pasa nunca por float.

Motivo medido, para que no se repita el mito: a la escala de este aplicativo el float **no** produce deriva acumulada visible — sumar 3.000 facturas en float64 da el mismo resultado que en Decimal. Los dos problemas reales eran otros:

1. **Redondeo**: `round(2.675, 2)` da 2.67 porque 2.675 no existe en binario. En pesos es un centavo mal, en la dirección que decida la representación.
2. **Falta de cuantización**: `Base IVA = IVA / 0.19` es periódico y se guardaba y **exportaba** como `40463.15789473684`, con `Diferencia = -1.1578947368398076`. El contador recibía esas columnas con 14 decimales de ruido. Ahora son `40463.16` y `-1.16`.

En `data_json` los importes se guardan como **string exacto** (`"12952.83"`), no como número JSON: un float en el archivo reintroduciría la representación binaria. Las cargas anteriores (que sí tienen floats) se leen igual: `money.to_money` pasa el float por `repr()`, así que `12952.83` vuelve como `Decimal('12952.83')` y no como el binario largo.

---

## D-076 — Las operaciones largas son trabajos en segundo plano (2026-09-20)

`run_validations`, `reindex_pdfs` y `list_load_soportes` (con `reindex`) se piden como `<método>_async`: devuelven un `job_id` al instante y el progreso se consulta con `job_status` (`job_cancel` los cancela). El trabajo corre en un hilo con su propia conexión SQLite.

Antes: el bucle IPC es estrictamente serial y Nitro cortaba toda petición a los 30 s. Indexar los soportes de un mes son minutos, así que la petición reventaba mientras Python seguía trabajando, su respuesta llegaba a un id que ya nadie esperaba, y todo lo que el usuario tocara entretanto se encolaba detrás y también reventaba. Medido tras el cambio: arrancar el trabajo responde en ~0 ms y el bucle sigue atendiendo peticiones mientras corre.

Los timeouts de `callSidecar` pasan a ser **por método** (`utils/sidecar.ts`), y el temporizador se limpia al resolver. Lo que no tiene techo no se pide de forma síncrona: se pide como trabajo.

---

## D-077 — El catálogo central se reconcilia en las dos direcciones (2026-09-20)

`program_db.unregister_empresa` saca la fila al borrar, `sync_registry` PURGA las filas cuyo `.db` ya no existe, y `restore_empresa` da de alta la empresa restaurada. Antes `sync_registry` solo añadía y nadie borraba: el catálogo anunciaba empresas inexistentes para siempre, y una restaurada no aparecía hasta el siguiente arranque.

---

## D-078 — Borrar una empresa la manda a la papelera, no al vacío (2026-09-20)

`delete_empresa_file` hace `wal_checkpoint` y **mueve** el `.db` a `<data_dir>/papelera/<sello>_<nombre>.db`; se conserva **30 días** (`PAPELERA_RETENCION_DIAS`) y se purga solo. RPCs `papelera_list` y `papelera_restore` para recuperarlo. Los `-wal`/`-shm` sí se descartan: son estado transitorio y el checkpoint ya volcó su contenido.

Motivo: borrar una empresa es borrar la contabilidad completa de un cliente, con obligación legal de conservación en Colombia. Un `unlink()` irreversible confirmado solo con el NIT es demasiado frágil para eso. La confirmación por NIT se mantiene.

---

## D-079 — Crear una empresa que ya existe es un error, no un éxito (2026-09-20)

`create_empresa` falla si el `.db` ya existe, y también si **el NIT ya está registrado con otra razón social** (que generaría un archivo distinto y dos contabilidades paralelas del mismo contribuyente). Antes `init_empresa_db` era idempotente y el handler devolvía éxito con la razón social ENVIADA aunque la BD conservara la anterior: el usuario creía haber creado una empresa nueva y estaba editando otra.

---

## D-080 — Una dependencia ausente no puede disfrazarse de dato faltante (2026-09-20)

`_pdftotext` lanza `PopplerNoDisponible` cuando falta el binario, en vez de devolver `""` ante cualquier fallo, y `extract_cufes` lo reporta como `status=error` con el motivo real. Nuevo RPC `check_dependencies` para avisar ANTES de procesar.

Antes, 'falta Poppler' y 'este PDF no tiene texto' acababan en el mismo sitio: el usuario veía el mes entero como «sin soporte» y no tenía forma de saber que el problema era una instalación incompleta.

---

## D-081 — El periodo se valida y el mes dominante es determinista (2026-09-20)

`periodo_from_row` comprueba la forma `AAAA-MM` (mes 01–12) antes de devolverla: `_parse_date` deja pasar el texto original cuando no reconoce el formato, así que cortar a ciegas `fe[:7]` producía periodos basura como `'Marzo 2'` — y ese periodo decide contra qué carpeta de soportes se valida el lote.

`_periodo_dominante` usa `Counter` con desempate explícito (gana el mes más antiguo). `max(set(p), key=p.count)` dependía del orden de iteración de un set de strings, que cambia **entre procesos** por el hash aleatorio de Python: verificado que con `PYTHONHASHSEED` 0/1/42/7 daba `2024-03` y con 12345/99999/13 daba `2024-02` para el mismo empate.

---

## D-082 — Linters y tests de frontend en CI (2026-09-20)

- **`ruff`** en `apps/core` con un conjunto acotado (E/W/F/I/B/UP/C4/SIM/RUF) que atrapa errores reales, no estilo discutible. Se ignoran `RUF001/002/003`: el proyecto está escrito en español (D-009) y las tildes y comillas angulares no son «caracteres ambiguos».
- **`vue-tsc`** contra los dos tsconfig que genera Nuxt (app y servidor). Hacía falta añadir `@types/node`, que no estaba: todo el código de servidor usaba `process`, `Buffer` y `node:*` sin tipos. El primer typecheck encontró 5 errores reales de `possibly undefined`.
- **`vitest`** para la lógica pura del frontend (composables y utilidades de servidor). Sigue pendiente un smoke end-to-end de la aplicación.

---

## D-083 — Los errores se registran, no se tragan (2026-09-20)

Nuevo `log.py` (a stderr, que el shell recoge en `%APPDATA%/Contab/logs/`). Los `except Exception: pass` repartidos por el código pasan a `log.warn` / `log.exception`: la política no cambia (esas operaciones siguen sin tumbar nada) pero dejan rastro. Solo quedan dos `except` desnudos, al cerrar recursos de pdfium, marcados con `noqa`.

La traza de una excepción deja de viajar en el payload de la respuesta y va al log: la UI recibe el mensaje para el usuario, no rutas internas.

---

## D-084 — Migraciones numeradas y bloqueo de downgrade (2026-09-20)

`MIGRACIONES` es una lista `(número, función)` que corre en orden una sola vez. `ensure_schema` ahora:

1. **Bloquea el downgrade**: si la BD declara un esquema mayor que el de la app, lanza `EsquemaMasNuevoQueLaApp` y no toca nada. Antes `SCHEMA_VERSION` llevaba en 1 desde el primer día pese a los cambios de 0.1.4/0.1.6/0.2.0, y una versión vieja abría y **escribía** en una BD nueva. Con auto-update eso pasa.
2. **Sale temprano** cuando la versión ya coincide. Antes ejecutaba el `executescript` entero y todos los `PRAGMA table_info` en CADA llamada RPC, o sea en cada clic.

La migración 1 conserva el código antiguo tal cual (ALTER idempotentes): es lo que ya corrió en las BD instaladas y reescribirla cambiaría el resultado para alguien.

---

## D-085 — Fuera el esquema que describía un sistema inexistente (2026-09-20)

Migración 2. Retira `validation_rule` (motor de reglas con `severity` y vigencias que ninguna línea leía ni escribía), la FK `validation_failure.rule_id` que la apuntaba, y `excel_row.deleted_at` (papelera por fila que nunca se implementó; la que funciona es la del LOTE).

`excel_row.deleted_at` no era solo inútil: si algún día se filtrara por ella en `fetch_load_rows`, el `enumerate(rows)` de validations dejaría de coincidir con el `row_index` de los overrides y las aprobaciones manuales se aplicarían a filas equivocadas.

Se borra solo si está vacío. Si alguien tuviera datos ahí, se conserva y se avisa por log.

---

## D-086 — El sidecar DIAN escucha en loopback (2026-09-20)

`run.sh` y el README pasan de `0.0.0.0` a `127.0.0.1`. Era herencia del despliegue web original y dejaba el scraper accesible desde toda la red. El `Dockerfile` mantiene `0.0.0.0` porque dentro de un contenedor es lo correcto, con un comentario que aclara que no se usa en el producto de escritorio.

---

## D-087 — Retención de los archivos subidos (2026-09-20)

Cada Excel importado y cada dump de PUC se guardaban con marca temporal y nadie los borraba nunca. Se conservan **90 días** y se purgan al subir el siguiente. Los backups `.contab.zip` quedan fuera: los guarda el usuario donde quiere y son su copia de seguridad, no un temporal nuestro.

---

## D-088 — Endurecimiento del shell de Electron (2026-09-20)

- `sandbox: true` y `webviewTag: false` en ambas ventanas. El preload seguía funcionando porque solo usa `contextBridge`/`ipcRenderer`; se quitó de él un `version` que además nadie leía (la sirve `/api/version`).
- `will-navigate` limita la ventana a nuestro propio origen. Sin él, un enlace o un redirect llevaba el renderer a un sitio externo **conservando el puente del preload**.
- `shell.openExternal` solo acepta `https:`, `http:` y `mailto:`. Antes aceptaba cualquier cosa, incluido `file://`.
- `setPermissionRequestHandler` deniega todo: la app no usa cámara, micrófono ni geolocalización.
- `activate` (macOS) reabre la ventana en vez de llamar a `boot()`, que levantaba un SEGUNDO servidor Nitro con sus sidecars.
- `process.on('exit')` se sustituye por `uncaughtException`: en `exit` ya no se puede programar nada y `treeKill` es asíncrono, así que no servía de nada.

---

## D-089 — Credencial local para la API (2026-09-20)

El shell genera un secreto por arranque, se lo pasa a Nitro por `CONTAB_TOKEN` y llega al renderer por el preload (IPC síncrono; un preload con sandbox no tiene `process.env`). Un middleware lo exige en todo `/api/**` salvo `/api/version`. El cliente lo adjunta reemplazando el `$fetch` global, así que las llamadas futuras quedan cubiertas sin acordarse.

Sin `CONTAB_TOKEN` en el entorno la autenticación **no se activa**: `npm run dev` sigue funcionando con curl y con el navegador suelto.

Motivo: `/api/rpc` es un ejecutor universal que recibe `db_path`, `source_path` y `output_path` sin validar. El puerto aleatorio en 127.0.0.1 descarta la red, pero no a otro proceso de la máquina ni a una página barriendo puertos de localhost. El sidecar DIAN pasa también a puerto aleatorio (estaba fijo en 8756).

Un 401 aquí **sí** lleva código HTTP de error, a diferencia de D-071: esto es un fallo de autorización, no un error de dominio.

---

## D-090 — El renderizado de PDF no usa Pillow (2026-09-20)

`_render_page` va por `bitmap.to_numpy()` y no por `to_pil()`.

`to_pil()` importa Pillow, que **no está en las dependencias del paquete** (aunque CLAUDE.md lo listaba). En un entorno limpio lanzaba `ModuleNotFoundError`, el `except Exception` lo convertía en `None`, y la lectura por QR —única vía en los PDF con la fuente ofuscada, como los de Movistar/Claro/Tigo— fallaba en silencio. Se veía como «sin CUFE», nunca como un fallo de instalación.

Este era el fallo que llevaba toda la revisión atribuido a `cv2.QRCodeDetector`. No era el detector: era que nunca le llegaba una imagen.

---

## D-091 — Los campos consultables salen del blob JSON (2026-09-20)

`excel_row` gana cuatro columnas proyectadas desde `data_json`: `total_centavos`, `iva_centavos`, `nit_emisor` y `fecha_emision` (migración 3, con backfill de lo ya cargado). `data_json` **sigue siendo la fuente de verdad** de la fila completa — D-039 intacto: no se renombra ningún header de la DIAN.

Los importes van en **centavos como INTEGER**, no como REAL ni TEXT: `SUM` en SQL es exacto, un REAL reintroduciría el binario del que salimos en D-075 y un TEXT no suma. `money.a_centavos` / `money.de_centavos` convierten en ambos sentidos sin pérdida.

Motivo: toda la fila vivía como un blob JSON, así que no se podía sumar, agrupar ni filtrar en SQL — cualquier total pasaba por cargar el lote entero a memoria en Python. Eso bloqueaba cualquier reporte agregado o comparación entre meses.

Se añaden `resumen_periodos` y `resumen_emisores` como primeros consumidores, para que la capacidad quede demostrada y no solo prometida.

Nota de implementación: los índices de las columnas nuevas NO van en `SCHEMA_SQL`. En una BD antigua la tabla ya existe sin ellas (`CREATE TABLE IF NOT EXISTS` no las añade) y el `CREATE INDEX` falla — exactamente la trampa que el código ya documentaba para `idx_excel_row_periodo`.

---

## D-092 — `load.vue` se parte en composables (2026-09-20)

La página juntaba seis responsabilidades en 934 líneas y es el archivo que más se toca del repo. Se extraen a `app/composables/`:

- `useColumnasTabla` — visibilidad, grupos y panel de columnas.
- `useExportarFaltantes` — reporte de faltantes de soporte (D-047).
- `useRenombrarSoportes` — plan y aplicación del renombrado (D-066).
- `useSoportesDelMes` — panel de soportes y re-verificación (D-068).

La página queda con lo que es suyo: la tabla, las validaciones y los overrides. Las dependencias entre piezas van como parámetros explícitos (`alAplicar`, `alReverificar`), no como variables compartidas por estar en el mismo archivo.

---

## D-093 — `Base IVA` usa la tarifa detectada (2026-09-20) · **supersede D-046**

> Cambio de una decisión que estaba marcada como inmutable. **Confirmado explícitamente por el usuario** el 2026-09-20, tras plantearle las tres opciones (detectar la tarifa / renombrar la columna / dejarlo).

`Base IVA = IVA / tarifa detectada` (19% o 5%, la que explique ese IVA dentro de la tolerancia de ±5 pesos). Antes era `IVA / 0.19` **siempre**.

Por qué: las columnas `Base IVA` y `Diferencia` se EXPORTAN al contador. En una factura al 5%, dividir por 0,19 daba una base cinco veces menor de lo debido y una `Diferencia` enorme que no era un descuadre sino ruido:

| | D-046 (antes) | D-093 (ahora) |
|---|---|---|
| `Base IVA` | 263.157,89 | 1.000.000,00 |
| `Diferencia` | 736.842,11 | 0,00 |

*(factura al 5%: base 1.000.000, IVA 50.000)*

La `Diferencia` vuelve a significar «aquí hay algo que no cuadra» en las dos tarifas.

Cuando **ninguna** tarifa cuadra —la fila que V3 marcará como no conforme— se usa el 19% como referencia, para que la `Diferencia` muestre cuánto se aparta del caso general, que es lo útil al revisarla a mano. Una tarifa inventada sigue saltando a la vista.

La detección comparte criterio con V3 (D-072): se compara en espacio de IVA, no dividiendo.

**Efecto en datos existentes**: `_derive_columns` recalcula en cada lectura (D-045 retrofit), así que las cargas ya guardadas muestran los valores nuevos sin necesidad de re-subir nada. Las filas al 19% no cambian.

---

## D-094 — Las carpetas de los sidecars se BUSCAN, no se calculan con `..` (2026-09-20)

`resolveCoreDir` y `dianCwd` suben desde el directorio actual buscando un marcador (`contab_core/sidecar.py`, `main.py`). Antes se calculaban con un número fijo de `..` asumiendo que el cwd era `apps/desktop`.

Esa suposición es falsa cuando **el shell de Electron arranca Nitro**: ahí el cwd es `apps/desktop/.output`, y las dos rutas candidatas (`../core` y `../../apps/core`) apuntaban a carpetas inexistentes. El sidecar se lanzaba con un cwd inválido, moría al instante, y toda petición fallaba con *"Cannot call write after a stream was destroyed"* — un mensaje que no dice nada del problema real.

En producción no se notaba porque `CONTAB_SIDECAR_BIN` apunta al ejecutable de PyInstaller, que trae su propio cwd. Pero era un fallo real en el arranque no empaquetado, y lo encontró el smoke end-to-end el primer día que existió.

Si no se encuentra, ahora se lanza un error que **dice qué falta y cómo arreglarlo** (`CONTAB_CORE_DIR` / `DIAN_DIR`), en vez de spawnear a ciegas.

---

## D-095 — Smoke end-to-end contra el Electron real (2026-09-20)

`apps/shell/e2e/` con Playwright. No es una suite de UI: es la comprobación de que la cadena entera arranca y funciona — Electron → Nitro → sidecar Python → preload → credencial — que es justo lo que ni vitest ni pytest pueden ver.

Cubre: el arranque completo, que el preload entrega la credencial **pese a `sandbox: true`** (D-088 + D-089 podrían haberse roto entre sí y la app instalada habría quedado inservible), que la API rechaza con 401 sin ella, que Poppler está, el flujo real (crear empresa → subir el Excel de muestra → validar como trabajo en segundo plano → resumen agregado en SQL), y que borrar manda a la papelera y se puede recuperar.

**Aislamiento**: `APPDATA` y `XDG_DATA_HOME` apuntan a un temporal antes de lanzar Electron, que lo propaga a Nitro y este al sidecar. Hay un test dedicado a comprobar que las empresas creadas viven ahí. No es paranoia: durante esta misma revisión, correr pytest en Windows escribió en el `%APPDATA%\Contab` real del usuario, incluidos los tests que BORRAN empresas.

---

## D-096 — Contab es el puente; Siigo sigue siendo el libro contable ✅ (2026-09-21)

Contab controla, causa y **exporta**; Siigo guarda los libros y produce los reportes oficiales. Decidido por el usuario en opción múltiple, frente a la alternativa de volver a Contab el libro completo.

Por qué: el contador ya paga Siigo y confía en él para lo legal. Competirle con libros oficiales, estados financieros y partida doble es tres o cuatro veces más trabajo y traslada a Contab una responsabilidad legal que hoy no tiene.

**Efecto en el roadmap**: **E6 (asientos contables) y E7 (reportes financieros) quedan aparcadas**. El cumplimiento que sí se hace (Fase 7 del plan de automatización) entrega **cifras para revisar, no documentos para presentar**: prellenado del 300 y el 350, y los formatos de exógena sobre la base de la causación.

Costo asumido: se depende del formato y la disponibilidad de otro producto. Se mitiga diseñando el envío como **capa de adaptador** (el modelo interno de asiento es nuestro; Siigo es el primer destino, no el único), para que World Office, Helisa o Contapyme entren después sin rehacer el motor.

Ver [`plans/dian-siigo-automation-plan.md`](../plans/dian-siigo-automation-plan.md).

---

## D-097 — Tres caminos de ingesta desde la DIAN ✅ (2026-09-21)

La información de la DIAN entra por tres caminos hacia **una sola interfaz interna**:

1. `token` — autenticación contra el portal y llamadas HTTP directas. El rápido: las N empresas en minutos.
2. `robot` — Playwright sobre el portal, reusando el contexto persistente y el modo CDP que ya funciona en `apps/dian-rut`. El que sobrevive a Cloudflare y al segundo factor.
3. `manual` — la subida del Excel que existe hoy. **No se retira nunca**: es el piso cuando los otros dos fallen.

Por qué tres y no el mejor: el portal es un contrato que nadie firmó con nosotros y cambia sin avisar. Un solo camino convierte un cambio de la DIAN en un mes perdido.

**Descartada por ahora**: la ingesta por correo (IMAP) del buzón de facturación del cliente. Es la vía más robusta y la única que trae el XML sin depender del portal, pero exige acceso al correo de cada empresa. Se revisa si los caminos del portal se caen.

Antes de escribir el módulo hay una **sesión de reconocimiento** contra el portal real, documentada en `docs/dian-portal.md`. No se diseña sobre endpoints recordados de memoria.

---

## D-098 — Las credenciales de la DIAN se guardan cifradas en la máquina ⛔ superseded por D-133 (2026-09-21)

Una entrada por empresa en el **llavero del sistema operativo** (Windows Credential Manager). Nunca en la `.db`, nunca en el log, nunca en el payload de un error — con un test que lo comprueba.

Por qué: la alternativa (pedirlas en cada corrida) mata justo lo que se venía a automatizar cuando son veinte empresas. La otra (heredar la sesión que el contador abrió a mano) no permite corridas desatendidas.

Costo asumido y explícito: **Contab pasa a custodiar credenciales fiscales de terceros.** De ahí se siguen tres cosas que dejan de ser opcionales: el llavero del SO en vez de cifrado propio, la auditoría de quién disparó cada corrida, y la **firma Authenticode** del instalador que D-059 dejó pendiente — a un usuario que está por entregar las claves de la DIAN de sus clientes no se le recibe con una advertencia de SmartScreen.

Queda abierto si las corridas pueden ser **desatendidas** (programadas de noche) o siempre las dispara el contador: es una decisión de política, no técnica.

---

## D-099 — El puente a Siigo va por la API de Siigo Nube ✅ (2026-09-21)

Se envía por API con credenciales de integración, no por la plantilla de importación de archivo plano.

Por qué la API y no el archivo: **un archivo se escribe pero no se lee de vuelta.** La API permite la **reconciliación inversa** — leer de Siigo lo que quedó contabilizado en el periodo y cruzarlo contra el reporte de la DIAN, en tres columnas: en la DIAN y en Siigo · solo en la DIAN (falta causar) · solo en Siigo (causado sin documento electrónico). Ese reporte responde la pregunta que hoy el contador no puede responder, y es la razón principal de la decisión.

Dos cosas se confirman **antes** de diseñar: el contrato vigente de la API y el tipo de credencial. Un agente no inventa endpoints de memoria.

Idempotencia por **CUFE**: un documento no sale dos veces, ni al repetir la corrida ni al reabrir el mes.

A favor: el PUC que ya importa `puc.py` tiene la forma del catálogo de cuentas que exporta Siigo, así que buena parte del mapeo de cuentas es un join, no digitación.

---

## D-100 — El catálogo de terceros vive por empresa ✅ (2026-09-21)

Los terceros enriquecidos con el RUT (responsabilidades, CIIU, municipio, estado) se guardan **en la `.db` de cada empresa**, no en un catálogo central.

Se evaluó el caché central en `contab.db`: una consulta al RUT serviría a las veinte empresas en vez de repetirse veinte veces. Se descartó porque **habría necesitado una excepción explícita a D-003** («una DB por empresa, nunca mezclar»), y esa regla vale más que las consultas ahorradas. Una excepción escrita hoy es una excepción que alguien amplía en seis meses.

Dos consecuencias para la implementación:

- Cada fila de tercero guarda `consultado_at`, para distinguir una lectura fresca de una vieja.
- Al **causar** un documento se copia el estado del tercero dentro del documento. Refrescar el catálogo después no puede reescribir lo que justificó una retención hace seis meses: la tarifa dependía de lo que el RUT decía **ese día**.

---

## D-101 — Toda corrida de ingesta la dispara el contador ✅ (2026-09-21)

Sin programador y sin ejecución nocturna. Nada toca la cuenta DIAN de un cliente sin que haya un humano presente.

D-098 (credenciales guardadas y cifradas) hacía *posible* la corrida desatendida; se decidió no quererla. Las credenciales guardadas siguen justificándose solas: son para **no teclear veinte claves por corrida**, no para correr sin nadie.

Costo aceptado: arrancar y vigilar la corrida es trabajo manual que se repite cada mes. A cambio, un cambio del portal o un segundo factor nuevo fallan **delante de alguien**, no en silencio a las 3 de la mañana.

---

## D-102 — Las tarifas se importan de un Excel del contador ✅ (2026-09-21)

La UVT del año, los conceptos de retención con su tarifa y su base mínima, y las tarifas de ICA por municipio **se cargan importando el Excel que el contador ya maneja**, con el mismo patrón de `puc.py`: alias de encabezado, upsert por clave, y las filas manuales se conservan.

Por qué: es su fuente, la que ya usa y en la que confía. Un agente **no** siembra tarifas de impuestos de memoria ni de una búsqueda web — son ley, cambian por decreto, y un error citado con fuente convence más de lo que debería.

Actualizar cada año es volver a subir el archivo. **Si un decreto obliga a publicar una versión de la aplicación, el diseño está mal.**

Primer paso al implementar la Fase 4: pedir una muestra real de ese Excel y escribir `docs/tarifas-structure.md` contra ella, como se hizo con `docs/excel-structure.md` para el reporte DIAN.

---

## D-103 — El contrato de Siigo, verificado; el envío va por tipo de documento ✅ (2026-09-21)

Verificado contra la documentación vigente de Siigo el 2026-09-21 (no de memoria):

- **Autenticación**: `POST https://api.siigo.com/auth` con `username` + `access_key` → JWT con `expires_in: 86400` (24 horas). El header **`Partner-Id`** va en todas las llamadas. Las credenciales salen de Siigo Nube → *Alianzas → Mi Credencial API*; las de prueba se piden a `soporteapi@siigo.com` con el NIT. **No hay sandbox público.**
- **Enrutamiento por tipo de documento**: factura recibida → `/purchases`; documento soporte con no obligados → `/purchase-support-documents`; `/journals` solo para lo que no encaje en ninguno de los dos.

Por qué por tipo y no todo por `/journals`: el mundo del contador son documentos, no asientos sueltos, y **Siigo aplica la configuración de cada empresa** (proveedor, impuestos, retenciones) al contabilizar una compra. Eso evita que Contab tenga que replicar esa configuración empresa por empresa. El documento soporte, además, tiene recurso propio: forzarlo al molde de factura de compra ensuciaría justo el tipo que más se revisa.

Costo aceptado: la configuración de cada empresa en Siigo tiene que estar bien, y el **ensayo en seco** obligatorio antes del primer envío real es donde se descubre que no lo está.

Dos hallazgos del sondeo que cambian el diseño:

1. **Las cuentas viajan por código.** Una línea referencia la cuenta por `code` (`"11050501"`) y `movement`, no por un id interno — el PUC que `puc.py` ya importa pasa directo. La tabla de mapeo se reduce a centros de costo, impuestos y tipos de comprobante.
2. **No hay campo de referencia externa.** Lo más cercano es `observations` (cabecera) y `description` (línea). Por eso la idempotencia **no** puede apoyarse en Siigo: la tabla `siigo_envio` es la única autoridad sobre lo que ya salió, el CUFE se estampa además en `observations` para que un humano pueda rastrearlo dentro de Siigo, y la verificación posterior se hace **listando el periodo** (`date_start`/`date_end`, `page`/`page_size`, `total_results`), nunca preguntando por un CUFE.

Ese mismo listado por rango de fechas es lo que hace viable la **reconciliación inversa**, que fue la razón de elegir la API sobre el archivo plano (D-099).

---

## D-104 — Vigía de citas DIAN: vigilar y dejar lista, no reservar a ciegas (2026-09-25)

Página **Consultas DIAN → Citas** (`/consulta-citas`): botón *Buscar cita* / *Detener*, estado en vivo,
registro y captura. Busca **Devoluciones · Videoatención · Persona natural** y solo sirve **Medellín**
(requisito del usuario).

- **Vive en el sidecar DIAN** (`apps/dian-rut/citas.py`, endpoints `/citas/{status,start,stop,captura}`,
  proxys en `server/api/dian/citas/`), no en un sidecar nuevo: ese servicio ya trae Playwright y ya va en
  el instalador. Corre en un hilo con Playwright síncrono (el loop de uvicorn está en otro hilo).
- **Navegador del sistema** (Chrome → Edge) con perfil propio en `<DIAN_WORKDIR>/citas/`: el instalador
  no trae Chromium (D-058). Sin stealth ni evasión de CAPTCHA: si aparece uno, es "detenerse y avisar".
- **Navegador real, no HTTP plano**: el portal pasa todo por `Player.aspx/ValidadorValidar` con varios
  iframes y estado de sesión; imitar esas llamadas sería frágil.
- **Señal de "sin cupo"**: el modal *"No se encontraron especialidades relacionadas según los filtros
  seleccionados."* Cualquier otra pantalla → se detiene con la ventana abierta, guarda captura, ventana
  emergente siempre-encima + pitidos + toast (la ventana va primero: el usuario tiene los toasts de Windows
  apagados) y `CITA_DIAN.txt`.
- **Flujo tras Devoluciones, según el manual del usuario** (capturas del 2026-08-28, cuando sí había
  trámites): aparece un desplegable **Trámite** con opciones por ciudad (p. ej. *Bucaramanga "Solicitud de
  devolución y/o compensación persona natural"*); sus opciones no salen en el texto de la página hasta
  abrirlo, así que "¿hay Medellín?" se decide leyendo las opciones. Solo sirve la que dice Medellín **y**
  persona natural; si no está → sigue buscando. Si está → la elige, Siguiente, pantalla *Ciudad o
  municipio, sede, fecha y hora*: elige el **primer día** que pinta el calendario (solo pinta los
  disponibles), Siguiente, y se detiene ahí a avisar. Sin días → sigue buscando.
- **Lo que viene después del día** (datos del solicitante, confirmación) aún no se ha visto: ahí para y el
  usuario termina. Cualquier paso que no salga como en el manual también es "parar y avisar", nunca "error
  y reintentar", para no perder un cupo real por un selector.
- **Cada 1–2 min (al azar)**, con backoff si el portal falla. Empezó en 3 min; el usuario lo pidió más corto.

Arreglos previos que salieron al integrarlo:
- `playwright-stealth==1.0.6` no exporta `Stealth`, que es lo que importa `scraper.py`: con los pines del
  repo el sidecar DIAN **no arrancaba**. Pin subido a 2.0.0.
- El chequeo de vida del sidecar usaba `/browser-mode-status`, que sondea :9222; en Windows una conexión
  rechazada tarda ~2 s, más que el timeout de 1,2 s, así que el servicio nunca se daba por vivo. Nuevo
  `/health`, y 90 s de margen para el arranque en frío.


**Ampliación del 2026-09-25 (tarde), con el portal activo y el manual del usuario:**

- **Cola de personas** en `contab.db` (tabla `cita_persona`, módulo `apps/core/contab_core/cita_personas.py`,
  RPCs `citas_list` / `citas_save_persona` / `citas_delete_persona` / `citas_set_estado`). El contador carga
  cédula (obligatoria) + nombre, correo y celular; el bot toma la primera `pendiente`, la lleva hasta donde sabe
  y la deja `en_curso` con el detalle (trámite · día · hora). Cuando el contador la marca `agendada` (o la
  devuelve a `pendiente`) en Contab, el bot sigue solo con la siguiente. El sidecar DIAN lee/escribe esa tabla
  directamente (`CONTAB_PROGRAM_DB`, que pasa Nuxt); el esquema es del núcleo.
- **Tratamiento de datos, por persona**: solo si la casilla "esta persona autorizó…" está marcada, el bot elige
  cédula de ciudadanía, llena el número y acepta el tratamiento. Sin ella, se detiene en esa pantalla.
- **Flujo completo conocido**: trámite → Siguiente → fecha más cercana → primera hora → Siguiente → datos.
  El calendario no es una `<table>`: se buscan los días por el contenedor con la fila DO LU MA MI JU VI SA.
- **Trámite válido = el general**: `Medellín "Solicitud de devolución y/o compensación persona natural"`. Hay
  variantes "Vehículos eléctricos o Híbridos persona natural" y "gran contribuyente" que no sirven aunque digan
  Medellín o persona natural.
- **Falso CAPTCHA**: el portal carga SIEMPRE un reCAPTCHA invisible (iframe `anchor` con `scale(0)`). La 0.3.0
  lo tomaba por un CAPTCHA y se detenía al ver trámites de otra ciudad (pasó con Cali). Ahora solo cuenta la
  ventana del desafío (`bframe`) visible.
- **Modo estudio**: la primera vez que aparece un trámite de otra ciudad, el bot lo sigue hasta la pantalla de
  datos (sin llenarla) y guarda capturas `estudio_*`, para conocer las pantallas sin esperar a Medellín. Una
  sola vez: con la captura `estudio_3_siguiente` ya no repite.

---

## Decisiones pendientes (a tomar más adelante)

- **D-E1-13** ⏸ Behavior de R-V3 cuando IVA = 0 (default actual: skip). Confirmar si lo cambiamos a "marcar excluido" o "tarifa 0%".
- **D-E2-1** ⏸ Política de backup/restore para empresa.db (manual vs auto al cerrar la app).
- **D-E2-2** ⏸ Política de edición de empresa (NIT/razón social editables vs solo carpetas).
- **D-E8-1** ⏸ Estrategia multiusuario (Postgres servidor vs sync nube vs file-share).
- **D-E10-1** ⏸ Firma del instalador `.msi` (auto-signed dev vs Authenticode).
- **D-E4-3** ⏸ OCR (Tesseract) para PDFs escaneados — solo si aparece un caso real con la muestra del usuario.

## D-104 — El XML es una capa pegada al Excel, nunca su reemplazo ✅

**Decisión**: el documento que se lee del XML UBL vive en tablas propias
(`documento`, `documento_linea`, `documento_impuesto`, `documento_referencia`) y
se engancha a las filas **por CUFE**. `excel_row.data_json` sigue siendo la fuente
de la tabla que el contador ve (D-039, D-064).

**Por qué**: si el XML reemplazara al Excel, cada columna que el contador
reconoce cambiaría de sitio y de nombre, y la confianza que costó construir en E1
se iría con ellas. Además el XML **no siempre está**: un mes sin XML tiene que
comportarse exactamente igual que antes, y la suite vieja en verde es la prueba
de que así es.

## D-105 — Con XML se contrasta la tarifa; sin XML se sigue infiriendo ✅

**Decisión**: V3 contrasta la tarifa **declarada** en el XML cuando existe, y
conserva la inferencia de D-093 para las filas sin XML.

**Por qué**: inferir obliga a adivinar entre 19% y 5%, y da por buena cualquier
combinación que cuadre con una de las dos — una factura con IVA del 8% mal
liquidado pasaba si el total casualmente encajaba. Cuando el XML declara la
tarifa no hay nada que adivinar. No se retira la inferencia porque las filas sin
XML siguen siendo la mayoría.

## D-106 — Los importes del XML se guardan como TEXT ✅

**Decisión**: `subtotal`, `total`, bases, tarifas y valores de impuesto se
guardan en columnas `TEXT` y se leen con `Decimal(texto)`.

**Por qué**: SQLite solo tiene `REAL`, y un `REAL` es un float. Guardar ahí un
importe reintroduce por la puerta de atrás justo lo que D-075 prohíbe, y el
céntimo que se pierde acaba en una retención que no cuadra con la del cliente.

## D-107 — El rezagado se informa con su ventana, no se marca como error ✅

**Decisión**: un documento emitido en un periodo anterior al que se está cerrando
genera un aviso que **dice cuántos meses lleva** y si sigue dentro de los tres
periodos del art. 496 ET.

**Por qué**: un rezagado dentro de la ventana es descontable y no es un error;
fuera de ella ya no lo es. Marcar los dos igual obliga al contador a ir a mirar
la fecha uno por uno, que es exactamente el trabajo que esto venía a quitar.

## D-108 — Sin tabla de tarifas de ICA ✅

**Decisión**: no se construye `ica_tarifa`. La Fase 4.1 entrega UVT y conceptos
de retención, y nada más.

**Por qué**: ninguna de las cinco empresas que lleva el contador es agente de
retención de ICA —lo dijo por escrito el 2026-10-20 y lo confirman las cinco
filas de su Excel con «NO»—. Construirla sería esquema muerto desde el primer
día, que es lo que D-085 prohíbe. Cuando alguna empresa pase a ser agente, se
añade; `empresa_municipio_ica`, que ya existe, se queda sin uso hasta entonces.

## D-109 — La tarifa se lee mirando el formato de la celda ✅

**Decisión**: el importador decide si `0.11` son 11% o 0,11% **mirando
`number_format`**, y acepta las dos formas.

**Por qué**: el Excel real trae las tarifas como celdas de porcentaje, que
guardan `0.11` y muestran `11%`. Leer el número a secas liquida al 0,11% —cien
veces menos retención, en todas las filas, sin que nada falle ni avise—. Y no se
puede asumir siempre la fracción, porque el siguiente contador puede escribir
`11` en una celda normal.

## D-110 — «Sin mínimo» no es un dato que falte ✅

**Decisión**: `N/A` en la base mínima significa que **se retiene desde el primer
peso**, y se guarda como `NULL` con ese significado explícito.

**Por qué**: tratarlo como dato faltante dejaría sin retener honorarios,
comisiones y arrendamientos de muebles, que son justo los conceptos que no
tienen mínimo.

## D-111 — Hay dos familias de retención: sobre la base y sobre el IVA ✅

**Decisión**: `retencion_concepto.sobre` distingue `base` de `iva`.

**Por qué**: las dos filas de ReteIVA del Excel real dicen «15% del IVA», no un
porcentaje de la base gravable. Sin la marca, el motor las calcularía sobre la
base y el valor saldría mal sin que nada lo delate.

## D-112 — Sin centros de costo ✅

**Decisión**: la regla de causación mapea a **cuenta PUC** y nada más.

**Por qué**: el contador respondió «NO» a si los usa. Una tabla, un campo y una
pantalla que no existen no se pueden llenar mal.

## D-113 — ReteIVA solo frente a proveedores del régimen simple ✅

**Decisión**: `agente_reteiva` del perfil solo entra en juego si el tercero
tiene la responsabilidad `O-47` (régimen simple).

**Por qué**: las cinco empresas del contador escribieron «SOLO AL RÉGIMEN SIMPLE
DE TRIB» en esa casilla del formulario, y él lo confirmó el 2026-10-21. Leer el
campo como un sí a secas haría que se practicara ReteIVA a todos los
proveedores. No hizo falta cambiar el esquema: la condición vive en el motor.

## D-114 — Las responsabilidades se leen de la factura cuando no están en el catálogo ✅

**Decisión**: el motor busca las responsabilidades del proveedor en este orden —
catálogo de terceros, luego `cbc:TaxLevelCode` del XML, y si ninguno dice nada
propone la retención ordinaria y **marca la fila para revisar**.

**Por qué**: se le preguntó al contador qué hace sin el RUT de un proveedor y
respondió «verifico la información en la factura». El anexo técnico de la DIAN
declara ahí las responsabilidades, así que lo que él hace a mano se puede leer.
Y el tercer caso es el que importa: con 21 de 25 terceros en blanco, exigir el
catálogo lleno dejaría la Fase 4 inservible hasta terminar un trabajo manual de
meses.

> ⚠ `TaxLevelCode` se implementó contra el anexo técnico, **no contra un XML
> real**: los dos que teníamos se perdieron. Si el campo no viniera, el motor
> cae al tercer caso y marca para revisar — no rompe, pero tampoco ayuda.

## D-115 — Sin perfil fiscal no se calcula ninguna retención ✅

**Decisión**: si la empresa no tiene perfil fiscal configurado, el motor
devuelve cero retenciones y lo dice.

**Por qué**: el mismo criterio de la Fase 1 con `perfil_vigente`. Una retención
calculada sobre un supuesto hace más daño que una no calculada: la primera se
contabiliza y se paga, la segunda se nota.

## D-116 — La regla del proveedor gana a la del concepto ✅

**Decisión**: cuando una regla por tercero y una por texto aplican al mismo
documento, se usa la del tercero. Una que acierte las dos cosas gana a ambas.

**Por qué**: el contador decide la cuenta mirando la factura, **salvo** unos
proveedores que siempre van a la misma cuenta «pase lo que pase» —nombró tres—.
Eso es una excepción explícita, y una excepción que no gana no es una excepción.

## D-117 — El crédito al proveedor es el resto, no un dato ✅

**Decisión**: en la propuesta de asiento, la línea de proveedores se calcula
como el total menos lo retenido, en vez de leerse de ninguna parte.

**Por qué**: así el asiento **cuadra por construcción**. Si se tomara de otro
lado, cuadrar dependería de que dos sumas coincidan, y el día que no coincidan
se contabiliza un asiento descuadrado que alguien deshace a mano.

## D-118 — Las cuentas que Contab no puede deducir no tienen valor por defecto ✅

**Decisión**: `cuenta_proveedores` y `cuenta_iva_descontable` nacen vacías. Sin
ellas la propuesta sale marcada diciendo cuál falta.

**Por qué**: poner `220505` «porque es lo habitual» produciría un mes entero
contabilizado contra una cuenta que puede no ser la de esa empresa, y eso se
descubre tarde. Es el mismo criterio del perfil fiscal: no inventar un valor
por defecto en algo que se contabiliza.

## D-119 — Volver a generar la propuesta no toca lo aprobado ✅

**Decisión**: `asiento.generar` salta los asientos ya aprobados.

**Por qué**: rehacer la propuesta después de que el contador aprobó media mañana
de trabajo le borraría esa mañana. Y la propuesta se rehace a menudo —cada vez
que llega un XML nuevo o cambia una regla—.

## D-120 — Lo aprendido de un proveedor vale mientras el concepto sea el mismo ✅

**Decisión**: una regla aprendida se guarda con el **patrón del concepto**. Si
ese proveedor factura algo que no casa con ninguno de sus patrones, la propuesta
sale marcada como «factura algo distinto a lo de siempre» y vuelve a pasar por
él. Solo las reglas **sin patrón** son el «siempre a la misma cuenta».

**Por qué**: el contador lo precisó el 2026-10-22 — «como por lo general el
concepto que factura el proveedor es el mismo, las siguientes se registrarían de
esa forma; pero si el concepto cambia, me presentas la nueva propuesta». Esto
**corrige a D-116**: lo que allí se leyó como «la regla del proveedor gana pase
lo que pase» era en realidad la excepción de tres proveedores concretos, no la
regla general.

**Y la pantalla lo dice distinto**: «no conozco a este proveedor» y «lo conozco
y está facturando otra cosa» son dos situaciones diferentes para quien revisa.

## D-121 — Las cuentas de la empresa se aprenden en el primer asiento ✅

**Decisión**: `cuenta_proveedores` y `cuenta_iva_descontable` no se piden en una
pantalla de configuración: se escriben **en la bandeja, sobre el primer asiento
de esa empresa**, y se guardan al aprobarlo.

**Por qué**: es lo que pidió — «para cada empresa me gustaría ver la sugerencia
del primer registro». Preguntar una cuenta en abstracto obliga a imaginarse el
asiento; preguntarla con el asiento delante es la misma pregunta con la
respuesta a la vista. Y como cada empresa tiene su propia base (D-003), que «las
cuentas varíen por empresa» sale gratis: no hay una tabla común que pudiera
mezclarlas.

## D-122 — La propuesta se arma del Excel cuando no hay XML ✅

**Decisión**: `asiento.generar` toma el documento del XML si existe y **de la
fila del Excel de la DIAN si no**. El Excel ya trae NIT y nombre del emisor,
fecha, IVA y total: con eso el asiento se propone completo, sin el detalle por
línea.

**Por qué**: es D-104 llevado hasta el final —el XML es una capa pegada al
Excel, nunca su reemplazo— y hasta ahora el código lo incumplía. Un ensayo sobre
el julio real del contador lo destapó: **55 documentos, 0 propuestas**, porque
ninguno tenía XML. Y los XML se bajan uno por uno del portal con el navegador
abierto, así que exigirlos dejaba la Fase 4 inservible hasta hacer horas de
trabajo manual.

## D-123 — Solo se causan compras ⛔ superseded por D-127

**Decisión**: la bandeja ignora las filas con `Grupo = Emitido` y las que emitió
la propia empresa.

**Por qué**: `Grupo` dice `Emitido` (ventas) o `Recibido` (compras) — ver
`docs/excel-structure.md`—, y las ventas no se causan desde aquí. En el julio
real eran **31 de 55**: quince facturas emitidas, siete documentos soporte,
cuatro notas y cinco nóminas, todas pidiendo una cuenta de gasto que no les
corresponde. Las filas **sin** grupo sí entran: esconder una compra significa
que nunca se causa y nadie se entera; colar una venta se ve y se salta.

## D-124 — Si ya hay regla, no se vuelve a preguntar por el tercero ✅

**Decisión**: cuando existe una regla que decide la retención de un proveedor,
el motor **deja de marcar** sus facturas por no conocer sus responsabilidades.
El aviso se conserva; lo que desaparece es el bloqueo.

**Por qué**: sin esto, aprobar la primera factura de un proveedor no servía de
nada — las siguientes volvían a pedir revisión por el mismo motivo, para
siempre. Es justo la promesa que el contador pidió: «como por lo general el
concepto que factura el proveedor es el mismo, las siguientes se registrarían de
esa forma». Comprobado sobre su julio real: aprobar una de las cuatro facturas
de un proveedor dejó **las cuatro** listas.

## D-125 — Solo se exporta lo aprobado ✅

**Decisión**: `export_asientos` saca a Excel únicamente los asientos con
`aprobado = 1`. Lo que está «por decidir» no entra aunque tenga todas sus
líneas.

**Por qué**: una propuesta no es un asiento todavía. Mezclarlas en el mismo
archivo es exactamente cómo acaba contabilizado en Siigo algo que nadie aprobó
— y el archivo es lo que él va a importar. El archivo además dice si cuadra,
que es la comprobación más barata que existe antes de llevarlo.

## D-126 — Lo que se pasa de 30 segundos va en segundo plano ✅

**Decisión**: armar la propuesta del mes, mudar las carpetas y leer los XML
corren como trabajos con progreso (D-076), no como RPC síncronos.

**Por qué**: la mudanza reindexa cada PDF con `pdftotext` y lector de QR; con
cien soportes se pasa del tope de 30 s, la pantalla dice «error» y el sidecar
sigue trabajando. Un error falso mientras se mueven documentos de un cliente es
la peor combinación: el contador no sabe si parar, repetir o esperar.

## D-127 — Lo que la empresa emite también se causa ✅

**Decisión**: supersede a D-123. La bandeja causa tres naturalezas, y cada
asiento y cada regla llevan la suya:

- **compra** (`Grupo = Recibido`): lo de siempre — gasto, IVA descontable,
  retenciones, proveedores por el resto.
- **doc_soporte** (`Documento soporte con no obligados`, emitido): una compra a
  alguien que no factura. El tercero es el **receptor**, no hay IVA, y la
  retención se elige al aprobar como en cualquier compra.
- **venta** (factura o nota crédito emitida): el tercero es el **receptor**.
  Débito a **clientes** por el total; crédito al **ingreso** (la cuenta que dice
  la regla) y al **IVA generado**. Sin retenciones: las practica el cliente.
- **Nómina individual** no se causa.

Cuatro cuentas por empresa en lugar de dos: proveedores, IVA descontable,
clientes e IVA generado. Siguen sin valor por defecto (D-118).

**Por qué**: lo pidió el contador el 2026-10-27, probando la 0.11 con su primer
mes real. D-123 decía que «las ventas no se causan desde aquí» y era la mitad
del mes: en el julio de REAL eran 31 filas emitidas de 55. Una regla de ingreso
lleva su naturaleza porque el mismo NIT puede ser cliente y proveedor, y la
cuenta de cada cosa es otra: sin eso, aprobar la venta pisaría la regla del
gasto. La retención en el documento soporte no la mencionó —habló de cuentas—;
se deja elegible, y si no la quiere es un clic en «ninguna».

## D-128 — El puente a Siigo arranca por el archivo de importación, no por la API ✅

**Decisión**: la salida hacia Siigo es, primero, el **archivo de importación de
comprobantes contables** que el contador ya sube cada mes (27 columnas, una fila
por línea; estructura verificada en `docs/siigo-import-structure.md`). Contab lo
arma desde los asientos aprobados. D-099 (API) queda aplazada, no derogada: el
archivo no se lee de vuelta, así que la reconciliación inversa sigue pendiente.

Lo que el archivo exige y Contab no deduce vive por empresa en `siigo_config`:
el tipo de comprobante de cada clase (compra, NC de compra, venta, NC de venta,
documento soporte), el último consecutivo de cada tipo, el código de IVA por
tarifa y los días de vencimiento. El código de Siigo de cada concepto de
retención va junto a su cuenta, en las tarifas. Cada línea del asiento guarda su
**rol** (gasto, ingreso, IVA, retención, cartera), su base y su concepto; cada
asiento guarda el número del documento y el **consecutivo de Siigo** que se le
dio al exportar, que no cambia ni se repite.

**Por qué**: lo decidió el dueño el 2026-10-28 con el contador: «hasta donde
hemos hecho vamos genial, pero falta el archivo que él sube a Siigo». Es lo que
cierra el mes hoy, sin credencial ni sandbox. Lo que falta para que el archivo
salga completo —códigos de impuesto, tipos de comprobante, las retenciones que
le practican a la empresa en sus ventas, la nómina— se pide con nombre en vez
de inventarse: una celda vacía que él rellena es mejor que un código supuesto
que Siigo acepta y contabiliza mal.

## D-129 — La cuenta del impuesto la decide el catálogo de Siigo, por contexto ✅

**Decisión**: con el catálogo de impuestos de la empresa cargado
(`siigo_impuesto`: código × contexto → cuenta), la cuenta de cada línea de IVA
y de retención sale de ahí según el contexto del asiento —venta, compra,
devolución en venta, devolución en compra—. Las cuentas de IVA de la empresa
(D-127) y la cuenta del concepto de retención quedan de respaldo cuando no hay
catálogo. Qué IVA factura un tercero (bienes o servicios) es una decisión del
contador que la regla recuerda (`iva_codigo`); servicios es el valor por
defecto cuando hay dos códigos para la misma tarifa.

**Por qué**: el catálogo real (2026-10-28) trae cada código cuatro veces con
cuatro cuentas distintas. Una «cuenta del IVA descontable» por empresa era una
simplificación que ya estaba mal para la nota crédito de venta y lo estaba para
bienes contra servicios. Leer la cuenta del catálogo es lo único que coincide
con lo que Siigo espera, y es lo que el contador ya tiene escrito.

## D-130 — Las reglas se siembran desde los históricos de Siigo ✅

**Decisión**: el archivo de carga de Siigo del contador, con su hoja de
históricos, crea una regla por tercero: la cuenta del gasto (o del ingreso, en
una venta) a la que fueron sus últimos 10 comprobantes, si todos fueron a la
misma o una pesa al menos el 70 %; el código de IVA que traían, y el concepto de
retención cuyo código de Siigo aparece en ellos. Las reglas llevan
`origen = 'historico'`. No se pisa una regla que ya exista, no se elige cuando
no hay cuenta dominante (se devuelve como ambiguo) y las notas crédito no
siembran. Exige el catálogo cargado: sin los tipos de comprobante no se sabe
qué es compra, qué venta y qué soporte.

**Por qué**: el primer mes de cada empresa costaba una decisión por proveedor,
y esas decisiones ya estaban tomadas en Siigo. Sobre la copia de REAL: 240
reglas de 266 terceros (9 ambiguos), y el julio pasó de 0 a 42 documentos con
regla de 50. Los últimos 10 y no todos: un proveedor que cambió de cuenta hace
un año tiene que ir a la de ahora.

## D-131 — En una venta, lo que el cliente retiene va al débito y la cartera por el neto ✅

**Decisión**: con el catálogo de Siigo cargado, una venta lleva las retenciones
que el cliente le practica a la empresa —retefuente sobre la base, ReteIVA
sobre el IVA, ReteICA **en por mil** sobre la base— al débito, en las cuentas
1355 del catálogo y con su código y su base; la cartera queda por el neto, con
centavos, como en su archivo. Qué retiene cada cliente vive en su regla
(`retenciones_cliente`: códigos de Siigo, «ninguna», o NULL si no se sabe) y se
siembra de los históricos o se elige al aprobar. Si el cliente aplicó una
tarifa distinta a la del catálogo con el mismo código, se guarda con él:
«05:1.8» es ReteICA al 1,8 por mil. Una venta de un cliente del que no se sabe
no se aprueba en lote.

**Por qué**: en tres años de ventas de REAL, 79 de 90 llevan las mismas tres
retenciones y la cartera por el neto; sin ellas, el archivo de Siigo no
coincidía con el suyo en ninguna venta. Y la venta de prueba de su septiembre
(FELE-426) tenía el ICA al 1,8 por mil, no al 2 del catálogo: con la tarifa
aprendida del cliente, la cartera sale igual a la suya, al centavo.

## D-132 — Las hojas de cálculo se leen también en `.ods` ✅

**Decisión**: el catálogo y los históricos de Siigo se leen de `.xlsx` o de
`.ods` (`hojas.py`), sin dependencia nueva: un `.ods` es un ZIP con XML.

**Por qué**: el contador guarda en LibreOffice; su archivo de carga llegó en
`.ods`. Pedirle que lo convierta cada vez es una instrucción más que olvidar.
Sobre su archivo real, las 2.445 filas salen idénticas a las del `.xlsx`.

## D-133 — No hay credenciales de la DIAN que guardar: el enlace no se persiste ✅

**Decisión**: supersede a D-098. Contab **no guarda ningún acceso a la DIAN**. El
portal no autentica con usuario y clave: manda al correo del representante un
enlace de un solo uso (`AuthToken`). Ese enlace vive en memoria durante la
corrida y se descarta; no entra a la base, ni al log, ni al texto de un error
(`dian_portal.enmascarar`, con pruebas). No hay llavero, ni bóveda, ni cifrado
propio, porque no hay nada que custodiar. Las corridas las dispara siempre el
contador (D-101): sin enlace fresco no hay corrida, así que «desatendidas de
noche» deja de ser una pregunta abierta.

**Por qué**: D-098 se escribió el 21 de septiembre suponiendo usuario y clave;
el reconocimiento del portal del 28 de septiembre (`docs/dian-portal.md`)
encontró el enlace de un solo uso, y la decisión siguió escrita describiendo un
mundo que no existe, citada como inmutable en CLAUDE.md. Lo que D-098 derivaba
de custodiar credenciales —la firma Authenticode— no desaparece, pero cambia
de motivo: hoy es el aviso del antivirus en cada actualización (D-059,
`docs/antivirus.md`), no la entrega de claves ajenas.

## D-134 — La nómina se arma desde el Excel de liquidación y se aprende del 992 de Siigo ✅

**Decisión**: la nómina del mes entra al archivo de Siigo como un comprobante por
quincena (tipo de nómina de la empresa, 992 en REAL), armado desde el **Excel de
nómina del contador** (hojas «1Q» y «2Q»), no desde la DIAN. Las cuentas, las
tarifas de provisiones y aportes, y la entidad de cada empleado (EPS, fondo,
caja, ARL: cuenta y NIT) viven en una plantilla por empresa que **se aprende**
comparando ese Excel con el 992 que ya está en Siigo para el mismo mes. Por
empleado, con su cédula como tercero: devengos, provisiones (5105 contra 2510),
aportes del empleador, neto, retención y deducciones. Por aporte, con la
entidad como tercero. Redondeo al peso por empleado y concepto. Se aprueba por
quincena; sin cuentas no se aprueba.

**Por qué**: el contador lo pidió como parte del archivo que sube cada mes, y
el reporte de la DIAN no trae lo que hace falta (D-127 dejó la nómina fuera de
la causación por eso). Sobre el septiembre real de REAL, la segunda quincena
sale **idéntica en sus 80 pares cuenta-tercero** y la primera en 79 de 83: la
diferencia es un solo empleado cuyos otros pagos de esa quincena fueron, en
parte, a un tercero — eso no está en el Excel y se ajusta a mano.
