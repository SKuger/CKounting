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

## D-046 — Reversión de D-045 + override manual por fila para V3 ✅
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

---

## Decisiones pendientes (a tomar más adelante)

- **D-E1-13** ⏸ Behavior de R-V3 cuando IVA = 0 (default actual: skip). Confirmar si lo cambiamos a "marcar excluido" o "tarifa 0%".
- **D-E2-1** ⏸ Política de backup/restore para empresa.db (manual vs auto al cerrar la app).
- **D-E2-2** ⏸ Política de edición de empresa (NIT/razón social editables vs solo carpetas).
- **D-E8-1** ⏸ Estrategia multiusuario (Postgres servidor vs sync nube vs file-share).
- **D-E10-1** ⏸ Firma del instalador `.msi` (auto-signed dev vs Authenticode).
- **D-E4-3** ⏸ OCR (Tesseract) para PDFs escaneados — solo si aparece un caso real con la muestra del usuario.
