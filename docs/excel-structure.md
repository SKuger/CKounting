# Estructura del Excel DIAN — referencia verificada

Análisis estructural del archivo `Ejemplo_LaDian.xlsx` (muestra entregada por el usuario, datos falsos). Esta referencia se usa para implementar el parser, las columnas de la tabla y el export.

## Identidad del reporte

- **Origen**: portal MUISCA / DIAN — sección "Documentos Electrónicos".
- **Naturaleza**: consolidado de documentos electrónicos emitidos + recibidos para un NIT.
- **NO es**: información exógena (form. 1001/1003/etc.), ni medios magnéticos.
- **Tipos de documento observados**: `Factura electrónica`, `Factura electrónica de contingencia`, `Nota de crédito electrónica`, `Documento soporte con no obligados`, `Nomina Individual`, y —visto el 2026-09-28— **`Application response`**: los eventos RADIAN (acuse de recibo, aceptación), con `Total` e `IVA` en cero. No son facturas y no tienen soporte que buscarles; en un listado real fueron 9 de 10 filas.

## Layout

- **1 sola hoja**. Nombre interno: `Reporte_Documentos_20260305_195` (truncado por el límite de 31 chars de Excel).
- Header en fila 1 (estilo bold). Datos desde fila 2. **Sin celdas combinadas, sin headers multilínea, sin filas totales/footer, sin filas separadoras.**
- 32 columnas (A–AF). En la muestra, 11 filas de datos.
- Generado en Windows: ruta interna `C:\Users\Hogar\Downloads\pruebas\`.

## Convenciones críticas a tener en cuenta al parsear

| Tema | Detalle | Acción al implementar |
|---|---|---|
| **Fechas** | **Cambió.** La muestra de 2026-03 traía `dd-mm-yyyy`; un listado exportado el **2026-09-28** trae **ISO**: `2026-09-28` (Emisión) y `2026-09-28T14:42:08` (Recepción). **NO son seriales de Excel.** | `_parse_date` normaliza a ISO y `periodo_from_row` VALIDA la forma antes de usarla (D-081). No asumir ninguno de los dos formatos: la DIAN ya cambió una vez. |
| **NIT con ceros a la izquierda** | NITs como `051904524` se preservan solo si vienen del shared-string XML. Numéricos como `900183118` pierden ceros si los hubiera. | Coercer a `str` siempre y zero-pad si la longitud esperada lo amerita. |
| **Folio** | Almacenado como número. Hasta 9-10 dígitos (`509558651`). | Coercer a `str` para evitar formato exponencial en exportes y para preservar prefijos no esperados. |
| **Espacios en razón social** | Múltiples espacios internos y trailing (`'REAL '`, `' YOHANA MUÑOZ  SANCHEZ '`). | `re.sub(r'\s+', ' ', value).strip()` antes de mostrar/exportar. |
| **Columnas siempre presentes con 0** | Todas las columnas de impuestos están aunque el valor sea 0. | No asumir que columna ausente = 0; columna nula en Divisa/Forma/Medio sí es legítimo (Nómina). |
| **Divisa nula en Nómina** | `Nomina Individual` no trae `Divisa`, `Forma de Pago` ni `Medio de Pago`. | Reglas con scope que dependa de esas columnas deben excluir Nómina, o tratar null como "no aplica" (no error). |
| **CUFE/CUDE** | 96 chars hex minúscula (`^[a-f0-9]{96}$`) — SHA-384. | Normalizar a lowercase y strip antes de comparar. |

## Las 32 columnas (orden exacto del Excel)

| # | Header verbatim | Tipo | Semántica | Notas |
|---:|---|---|---|---|
| 1 | `Tipo de documento` | string | tipo_documento | Valores: Factura electrónica / Factura electrónica de contingencia / Nota de crédito electrónica / Documento soporte con no obligados / Nomina Individual |
| 2 | `CUFE/CUDE` | string | cufe_cude | 96 hex chars. CUFE = facturas; CUDE = notas/nómina/doc soporte. Ancho ~104 en el Excel original. |
| 3 | `Folio` | number | numero | Consecutivo. Coercer a str. |
| 4 | `Prefijo` | string | prefijo | Alfanumérico (DSE, FELE, SP, BEC, 94DD, NOM, TCNC, NCLA, ...) asignado por resolución DIAN. |
| 5 | `Divisa` | string | moneda | ISO 4217. Siempre COP en muestra. **Null en Nómina.** |
| 6 | `Forma de Pago` | number | otro | UBL code: `1`=Contado, `2`=Crédito. **Null en Nómina.** |
| 7 | `Medio de Pago` | mixed | otro | UBL Payment Means: `47`=Transferencia, `30`=Crédito, `49`=Tarjeta débito, `71`=Bonos, `ZZZ`=Mutuamente definido. **Null en Nómina.** |
| 8 | `Fecha Emisión` | string | fecha_emision | `dd-mm-yyyy` texto. |
| 9 | `Fecha Recepción` | string | otro | `dd-mm-yyyy HH:MM:SS` texto. Es el timestamp DIAN, **NO un vencimiento**. Crítico para plazo legal de rechazo (3 días hábiles). |
| 10 | `NIT Emisor` | number | nit_emisor | 9-10 dígitos. Sin DV. Coercer a str. |
| 11 | `Nombre Emisor` | string | razon_social_emisor | Trim/collapse whitespace. |
| 12 | `NIT Receptor` | number | nit_receptor | Igual que NIT Emisor. Incluye cédulas en nómina. |
| 13 | `Nombre Receptor` | string | razon_social_receptor | Trim/collapse whitespace. |
| 14 | `IVA` | number | valor_iva | Impuesto al Valor Agregado. Decimales posibles. |
| 15 | `ICA` | number | otro | Industria y Comercio (municipal). 0 en muestra. |
| 16 | `IC` | number | otro | Impuesto al Consumo general. 0 en muestra. |
| 17 | `INC` | number | otro | Impuesto Nacional al Consumo. 0 en muestra. |
| 18 | `Timbre` | number | otro | Impuesto de Timbre Nacional. 0 en muestra. |
| 19 | `INC Bolsas` | number | otro | Impuesto Bolsas Plásticas. Activo en facturas de retail (D1: 73). |
| 20 | `IN Carbono` | number | otro | Impuesto Nacional al Carbono. 0 en muestra. |
| 21 | `IN Combustibles` | number | otro | Impuesto a Gasolina/ACPM. 0 en muestra. |
| 22 | `IC Datos` | number | otro | Impuesto sobre servicio de datos/telecom. 0 en muestra. |
| 23 | `ICL` | number | otro | Impuesto al Consumo de Licores/Cervezas. 0 en muestra. |
| 24 | `INPP` | number | otro | Impuesto a Productos Plásticos de un solo uso (Ley 2277/2022). 0 en muestra. |
| 25 | `IBUA` | number | otro | Impuesto a Bebidas Ultraprocesadas Azucaradas (Ley 2277/2022). 0 en muestra. |
| 26 | `ICUI` | number | otro | Impuesto a Comestibles Ultraprocesados Industrialmente (Ley 2277/2022). 0 en muestra. |
| 27 | `Rete IVA` | number | valor_retencion | Retención de IVA. 0 en muestra. |
| 28 | `Rete Renta` | number | valor_retencion | Retención de Renta. 0 en muestra. |
| 29 | `Rete ICA` | number | valor_retencion | Retención de Industria y Comercio. 0 en muestra. |
| 30 | `Total` | number | valor_total | Headline. Decimales posibles. |
| 31 | `Estado` | string | estado | Valores observados: `Aprobado`, `Aprobado con notificación`. Otros DIAN posibles: `Rechazado`, `En proceso`, `Aprobado sin notificación`. |
| 32 | `Grupo` | string | otro | `Emitido` (ventas) o `Recibido` (compras). **Determina qué columna usar como "Tercero".** |

## Estructura de los PDFs de soporte (referencia para E3/E4)

Análisis de los 6 PDFs en `docs/samples/`. Todos texto extraíble por `pdftotext` salvo el de Movistar.

### Patrón de CUFE/CUDE/CUDS en PDFs

- Formato: **96 chars hex minúscula** (SHA-384).
- Etiquetas observadas (en orden de frecuencia):
  - `CUFE:` — facturas electrónicas
  - `CUDE:` — notas crédito, documento equivalente POS
  - `CUDS :` (con espacio antes del `:`) — Documento Soporte Electrónico
- **Casos especiales** ya identificados:
  - **Multi-CUFE en un mismo PDF**: notas crédito traen el CUFE de la factura original **además** de su propio CUDE → indexar **todos** los hex tokens, no solo el etiquetado.
  - **Line-wrapping**: D1 partió el CUDE en 2 líneas (`...ea4484ac58edbbeb9d02540b` + `ea3b16f9bed3cb27`) → reensamblar con regex tolerante a whitespace + post-validación contra `^[a-f0-9]{96}$`.
  - **Fuente custom (Movistar)**: el PDF es texto pero la región del CUFE/QR usa una fuente con codepoints privados → `pdftotext` extrae glifos basura. **Solución**: decodificar el QR con `pyzbar` — la URL del QR DIAN contiene el CUFE en cleartext. Movistar/Claro/Tigo son clientes muy comunes; esto debe estar en E3 (no diferido a E4 opcional).

### Estrategia de extracción para E3

1. **Primer pase**: `pdftotext -raw -enc UTF-8 <pdf> -` (NO `-layout=raw` — esa flag no existe).
2. Buscar **todos los tokens** que matcheen `^[a-f0-9]{96}$` (después de strip de whitespace).
3. **Segundo pase opcional con `-layout`** si el primero no devolvió tokens (layout suele preservar mejor labels).
4. **Tercer pase con `pyzbar`** sobre páginas renderizadas si los pases 1+2 no devolvieron CUFEs — necesario para Movistar/Claro/Tigo.
5. Cachear resultado por `(pdf_path_realpath, mtime, size)`.

### CUFEs presentes en la muestra (para tests futuros)

| Archivo | CUFE/CUDE/CUDS principal |
|---|---|
| `26-02 ANNY CASTANEDA FRA SP144.pdf` | `b49f9ecc41fac5566c46b49ae2810dfae43862f2ff3c1f49201c715172b6e33ba857d1f54537e756a8a7ec17ba185cbc` |
| `26-02 D1 FRA 94DD49995.pdf` | `8dc7aa629731b81d691c61bf2e1edfb5177607a8e4d84d179c635091ae4484ac58edbbeb9d02540bea3b16f9bed3cb27` |
| `dseDSE210.pdf` | `be6c31620a5bf5a8b66ee47379d13edcb5dffb12308e368f9985db48b05be1ae7472778f78775c418b17dda35a465111` |
| `dseDSE211.pdf` | `a763959ca331e3e0d275ea2feb573d4d56b00f2257415c30476faeca116bee14bbb2bbb8c15fbbf9c38ad63d16d804e3` |
| `09-02 ALMACENES EXITO NC TCNC1952292.pdf` | CUDE: `71fdf3781e9e57c77d792f4f8dcea9c5853b8e8d85fe8cb9f00eca9765cd72884db68542af6472f6e72ba6e7dd066ba5` + CUFE factura asociada: `4daa61d2720436822c10879797178a46a969e31fc1c6be3f1b87bd7bdda69da5594d6c5d0d8ddd92e1ea848a99dfd730` |
| `24-02 MOVISTAR BEC-509558651.pdf` | **No extraíble por pdftotext** (fuente obfuscada). Requiere QR decode. |

DSE210 y DSE211 son los únicos cuyos CUFE/CUDE coinciden con valores del Excel (porque son emitidos por REAL Seguros, el NIT del reporte). Los otros PDFs son **soportes de facturas recibidas** y sus CUFE están en la base del Excel para validar contra ellos en E4.
