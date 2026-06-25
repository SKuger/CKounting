# Glosario — Contab

Términos del dominio contable colombiano que aparecen en el código, la UI y las conversaciones. Mantener actualizado para que Claude no tenga que inferir cada vez.

> Si un término aparece en una conversación y no está aquí, agregarlo.

## Entidades fiscales

- **DIAN** — Dirección de Impuestos y Aduanas Nacionales de Colombia. Autoridad tributaria. Emite los reportes que Contab procesa.
- **NIT** — Número de Identificación Tributaria. Identificador único de la empresa o persona ante la DIAN. Formato `XXXXXXXXX-D` donde `D` es dígito de verificación.
- **DV** — Dígito de Verificación del NIT. Se calcula con **módulo 11** sobre los dígitos del NIT (sin el DV) usando los **factores DIAN oficiales** `[71, 67, 59, 53, 47, 43, 41, 37, 29, 23, 19, 17, 13, 7, 3]` (aplicados de derecha a izquierda), `(11 - suma_ponderada % 11) % 11`, con la regla: si el resultado es 10 → DV=`1`, si es 11 → DV=`0`. Usado en validación de NITs reales.
- **RUT** — Registro Único Tributario. Documento que identifica fiscalmente al contribuyente.
- **PUC** — Plan Único de Cuentas. Estructura jerárquica de cuentas contables estándar en Colombia.

## Identificadores de documentos electrónicos

- **CUFE** — Código Único de Factura Electrónica. 96 chars hex (SHA-384). Emitido por la DIAN al validar una factura.
- **CUDE** — Código Único de Documento Electrónico. Mismo formato. Para notas crédito, notas débito, nómina, tiquetes POS.
- **CUDS** — Código Único del Documento Soporte. Mismo formato. Para Documento Soporte Electrónico (compras a no obligados a facturar).

> En el Excel DIAN llegan todos bajo la única columna `CUFE/CUDE`. En PDFs aparecen con etiquetas `CUFE:`, `CUDE:`, `CUDS :` (con espacio antes del `:`).

### Regla "1 código por PDF" (D-033)

Cada PDF representa **una sola factura**, así que tiene **un solo** identificador propio. Cuando un PDF contiene varias etiquetas (caso típico: una Nota Crédito trae **su CUDE propio** + el **CUFE de la factura padre** que está rectificando), el indexador respeta esta prioridad:

```
CUDS  >  CUDE  >  CUFE
```

Y devuelve **solo** el de mayor prioridad. El otro identificador es el de **otro** documento (el padre) y NO debe contarse contra esta carpeta.

| Tipo de PDF | Etiqueta propia | Etiqueta del padre (si la trae) |
|---|---|---|
| Factura electrónica | `CUFE:` | — |
| Factura POS / tiquete | `CUDE:` | — |
| Nota Crédito | `CUDE:` | `CUFE:` ← se descarta |
| Nota Débito | `CUDE:` | `CUFE:` ← se descarta |
| Nómina | `CUDE:` | — |
| Documento Soporte (DSE) | `CUDS :` | — |

> Resultado práctico: en una carpeta con N PDFs distintos, esperamos N códigos indexados (no más).

## Tipos de documento electrónico

- **Factura electrónica** — venta gravada, exenta o excluida.
- **Factura electrónica de contingencia** — emitida cuando el emisor no tenía conexión y se sube después.
- **Nota de crédito electrónica** — disminuye el valor de una factura previa (devoluciones, descuentos posteriores).
- **Nota de débito electrónica** — incrementa el valor de una factura previa (intereses de mora, ajustes).
- **Documento soporte con no obligados** — usado por compradores cuando el proveedor no factura electrónicamente (persona natural no obligada, proveedor extranjero, etc.). El **emisor del documento soporte ES el comprador**.
- **Nomina Individual** — soporte de pago de nómina electrónica.

## Estados DIAN de un documento

- `Aprobado` — validado sin observaciones, contabilizable.
- `Aprobado con notificación` — validado pero con advertencias menores, contabilizable.
- `Aprobado sin notificación` — validado completo sin advertencias.
- `Rechazado` — la DIAN rechazó el documento. **NO contabilizable.**
- `En proceso` / `Pendiente` — la DIAN aún no terminó de validar. **NO contabilizable hasta resolución.**

> Regla recomendada: lista **denylist** `Rechazado` (y opcionalmente `En proceso`) en lugar de allowlist, porque la DIAN puede agregar estados nuevos y allowlist los bloquearía silenciosamente.

## Tipos de comprobante interno (libro contable)

- **CC** — Comprobante de Contabilidad (genérico).
- **CE** — Comprobante de Egreso (pagos).
- **CI** — Comprobante de Ingreso.
- **RC** — Recibo de Caja.
- **RP** — Recibo de Pago.

## Impuestos y retenciones (columnas del Excel DIAN)

| Sigla | Nombre completo | Notas |
|---|---|---|
| `IVA` | Impuesto al Valor Agregado | Tarifas estándar: **0%, 5%, 19%**. Tolerancia recomendada al validar tasa: ±1 peso por redondeo. |
| `ICA` | Impuesto de Industria y Comercio | Municipal. Tarifa por tipo de actividad y municipio. |
| `IC` | Impuesto al Consumo (general) | |
| `INC` | Impuesto Nacional al Consumo | |
| `Timbre` | Impuesto de Timbre Nacional | |
| `INC Bolsas` | Impuesto Nacional al Consumo de Bolsas Plásticas | Aparece en retail. |
| `IN Carbono` | Impuesto Nacional al Carbono | |
| `IN Combustibles` | Impuesto a Gasolina y ACPM | |
| `IC Datos` | Impuesto sobre servicio de datos / telecomunicaciones | |
| `ICL` | Impuesto al Consumo de Licores / Cervezas | |
| `INPP` | Impuesto a Productos Plásticos de un solo uso | Ley 2277/2022. |
| `IBUA` | Impuesto a Bebidas Ultraprocesadas Azucaradas | Ley 2277/2022. |
| `ICUI` | Impuesto a Comestibles Ultraprocesados Industrialmente | Ley 2277/2022. |
| `Rete IVA` | Retención en la fuente de IVA | |
| `Rete Renta` | Retención en la fuente de Renta | |
| `Rete ICA` | Retención de Industria y Comercio | |

> Identidad contable real (no completable solo con el Excel DIAN):
> `Total = Subtotal + IVA + Otros impuestos − Descuentos − Rete IVA − Rete Renta − Rete ICA`.
> El Excel DIAN **no trae Subtotal ni Descuentos** explícitos → la conciliación matemática completa requiere el XML/PDF. Documentado como limitación.

## Plazos legales clave

- **Rechazo de factura electrónica recibida**: **3 días hábiles** desde la `Fecha Recepción` DIAN (Decreto 358/2020 → art. 1.6.1.4.25 ET). Por eso la columna `Fecha Recepción` es crítica visible.
- **IVA descontable**: la factura recibida puede causarse en el periodo de la `Fecha Recepción` o en hasta **3 periodos siguientes** (art. 496 ET) — por eso para reglas de periodo sobre compras se usa `Fecha Recepción`, no `Fecha Emisión`.

## Códigos UBL (forma y medio de pago)

### `Forma de Pago`
- `1` = Contado
- `2` = Crédito

### `Medio de Pago` (subset común; lista completa es UBL Payment Means)
- `10` = Efectivo
- `30` = Crédito documentario / pago a crédito
- `42` = Consignación bancaria
- `47` = Transferencia bancaria
- `48` = Tarjeta de crédito
- `49` = Tarjeta débito
- `71` = Bonos
- `ZZZ` = Mutuamente definido

> El Excel DIAN trae estos códigos en crudo (números/`ZZZ`). El UI debe resolverlos a texto legible y mantener el código en una columna oculta para auditoría.

## Conceptos del flujo Contab

- **Empresa activa** — Empresa seleccionada en la UI. Todo lo que se cargue/edite afecta solo su archivo `.db` (D-003).
- **Reporte DIAN** — Archivo (Excel o PDF) que el contador descarga manualmente del portal de la DIAN. En el Excel se identifica al contribuyente porque su NIT aparece como `NIT Emisor` en filas `Grupo=Emitido` y como `NIT Receptor` en `Grupo=Recibido`.
- **Soporte** — Documento (PDF) enviado por el cliente que respalda los movimientos contables. Se cruzan contra el reporte DIAN para detectar diferencias.
- **Cruce / Cruce CUFE-PDF** — Validación 1: para cada fila del reporte, comprobar si su `CUFE/CUDE` aparece en algún PDF de una carpeta seleccionada por el contador.
- **Validación** — Regla configurable por el usuario que evalúa una fila. Catálogo: ver `docs/plan.md` E1.
- **No conforme** — Fila del reporte DIAN que **no pasa** al menos una validación. El reporte principal de E1 exporta estas filas.
- **Tercero** — En la UI, la **contraparte** de la empresa activa: si `Grupo=Recibido`, el tercero es el emisor (proveedor); si `Grupo=Emitido`, el tercero es el receptor (cliente). Se renderiza como columna virtual única para no duplicar.

## Roles / personas

- **Contador** — Usuario principal de Contab. Procesa la contabilidad de varias empresas.
- **Cliente** — Empresa cuyos libros maneja el contador.
- **Encargado** — Persona dentro del cliente que envía los soportes (PDFs) al contador.

## Términos técnicos del proyecto

- **Sidecar** (Tauri) — Proceso Python que Tauri arranca junto a la UI para tareas que no son del frontend.
- **Carga** — Acto de importar un archivo (Excel/PDF) a la empresa activa. Genera un registro en `validation_run` con timestamp.
- **Razón de falla** — Texto que se inyecta en la columna `razon_falla` del export por cada regla que una fila incumple.
