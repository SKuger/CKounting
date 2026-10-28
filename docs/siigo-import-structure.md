# El archivo de importación de comprobantes de Siigo — estructura verificada

> Verificado el 2026-10-28 sobre el archivo real que el contador sube cada mes a
> Siigo (`CARGA <EMPRESA>.ods`, tres hojas: *Hoja con ejemplos* con el mes de
> septiembre de 2026, *Hoja vacia* y *Hoja historicos* con 1.963 líneas de
> 2023-2026 exportadas de Siigo). Aquí no hay datos de personas: solo la forma.
> Es el modelo **Importación de comprobantes contables** de Siigo Nube.

## La forma

Una hoja, 27 columnas, **una fila por línea de asiento**. Un comprobante es el
conjunto de filas con el mismo `(Tipo de comprobante, Consecutivo comprobante)`,
y tiene que cuadrar: en 482 líneas de un mes no hay uno descuadrado.

| # | Columna | Qué lleva | Quién lo pone |
|---|---------|-----------|---------------|
| 1 | `Tipo de comprobante` | Número del tipo, **del catálogo de cada empresa en Siigo** (ver abajo). | Contab, por naturaleza del asiento |
| 2 | `Consecutivo comprobante` | Correlativo **por tipo**, lo lleva el contador (en septiembre las compras iban por el 850, las ventas por el 426). Siigo no lo asigna: lo exige. | Contab, siguiendo el último de cada tipo |
| 3 | `Fecha de elaboración` | Fecha de la factura. Igual en todas las líneas del comprobante. | Contab, del documento |
| 4 | `Sigla moneda` | `COP` siempre. | Fijo |
| 5 | `Tasa de cambio` | Vacío. | — |
| 6 | `Código cuenta contable` | Subcuenta del PUC de la empresa, **8 dígitos** (`22050501`, `24081501`, `53052001`). Nunca 6. | Contab, de la regla / las cuentas de la empresa / las tarifas |
| 7 | `Identificación tercero` | NIT o cédula sin DV, en **todas** las líneas del comprobante. | Contab |
| 8-12 | `Sucursal`, `Código producto`, `Código de bodega`, `Acción`, `Cantidad producto` | Vacíos. | — |
| 13 | `Prefijo` | Prefijo de la factura, **solo en la línea de cartera** (2205 en compras, 1305 en ventas). | Contab, del número del documento |
| 14 | `Consecutivo` | Número de la factura, misma línea. | Contab |
| 15 | `No. cuota` | `1`, misma línea. | Fijo |
| 16 | `Fecha vencimiento` | Fecha de elaboración **+ 30 días**, misma línea. | Contab (regla por confirmar) |
| 17 | `Código impuesto` | Código del **catálogo de impuestos de Siigo** de la empresa, en las líneas de IVA y de retención. | Contab, de un mapeo nuevo |
| 18-19 | `Código grupo activo fijo`, `Código activo fijo` | Solo en la depreciación (tipo 2). | Fuera de alcance |
| 20 | `Descripción` | El número de la factura (`FE1-123456`, `DSE-242`, `FELE-426`). | Contab |
| 21 | `Código centro/subcentro de costos` | Vacío desde 2024 (en los históricos aparecía `001-1`). Confirma D-112. | — |
| 22-23 | `Débito`, `Crédito` | Pesos, con decimales cuando los hay. | Contab |
| 24 | `Observaciones` | Lo mismo que la descripción, o un texto corto («CUOTA PRESTAMO …»). | Contab |
| 25 | `Base gravable libro compras/ventas` | La **base** de cada línea de impuesto o retención; `0` en las demás. | Contab |
| 26 | `Base exenta libro compras/ventas` | Casi siempre vacío. | — |
| 27 | `Mes de cierre` | Vacío. | — |

## Los tipos de comprobante que usa la empresa de referencia

El catálogo es **de cada empresa en Siigo**; estos son los de REAL. Hay que pedir
los de las otras cuatro.

| Tipo | Qué es | Líneas típicas | Lo arma Contab |
|------|--------|----------------|----------------|
| 11 | Factura de compra | gasto · IVA descontable (`2408xx`, imp.) · [retención `2365xx`, imp.] · proveedores `22050501` con prefijo/consecutivo/vencimiento | **Sí** (hoy) |
| 19 | Documento soporte a no obligados | gasto · [retención `2365xx`, imp.] · proveedores | **Sí** (hoy) |
| 12 | Factura de venta | ingreso `4150xx` · IVA generado `24080504` (imp.) · **retenciones que le practican** `1355xx` (imp., al débito) · clientes `13050501` con prefijo/consecutivo/vencimiento | Parcial: faltan las retenciones que le practican |
| 17 | Nota crédito de venta | devoluciones `417505xx` · IVA `24082004` · las mismas `1355xx` al revés · clientes | Parcial: otra cuenta de ingreso y otra de IVA |
| 15 | Nota crédito de compra | lo de la compra, al revés | Sí (la NC recibida ya se causa en negativo) |
| 992 | Nómina (una por quincena) | ~100 líneas: `5105xx` por empleado, `2370xx` por entidad, `2510xx`, `25050501` por empleado, `2365`, deducciones | **Sí** desde la 0.17 (D-134): desde el Excel de nómina, con la plantilla aprendida del 992 ya subido |
| 1 | Notas contables (autorretención, amortizaciones) | 2 líneas | No: no sale de ningún dato que tengamos |
| 2 | Depreciación del mes | 24 líneas, con activo fijo | No |
| 18 | Gastos bancarios | 14 líneas desde el extracto | No |

## Lo que el archivo enseña y Contab no sabía

1. **Las cuentas son subcuentas de 8 dígitos**, y la del IVA cambia según el
   comprobante: `24081501` en compras, `24080504` en ventas, `24082004` en notas
   crédito de venta. Las «cuatro cuentas de la empresa» (D-127) se quedan cortas
   para la nota crédito de venta: necesita su cuenta de devoluciones (`4175…`) y
   su cuenta de IVA.
2. **Cada impuesto y cada retención lleva un código de Siigo** (`01`/`02`/`03`
   para tarifas de IVA, `09`/`11`/`13`/`14`/`17`/`18`/`22` para conceptos de
   retención, `05`/`07`/`11` para las que le practican a la empresa, `100` para
   la autorretención). Son del catálogo de cada empresa y **no se pueden
   deducir**: hay que importarlos como las tarifas (D-102). El concepto de
   retención de Contab tiene que llevar su código de Siigo al lado de su cuenta.
3. **La venta lleva las retenciones que le practica el cliente** —retefuente
   11 %, ReteIVA 15 % del IVA, ReteICA por mil— al débito en `1355xx`, con la
   base en cada línea, y la cartera es el neto. Contab no tiene motor para «lo
   que me retienen a mí»; es una regla por cliente, aprendible al aprobar igual
   que la del gasto.
4. **El consecutivo lo lleva el contador**, por tipo y por empresa. Contab tiene
   que saber el último de cada tipo para seguir la numeración, y nunca repetir
   uno: en Siigo un consecutivo repetido es un comprobante rechazado o pisado.
5. **La fecha de vencimiento es +30 días** en todo el mes de muestra. Si no es
   regla general, es un dato del proveedor.
6. **Los históricos son reglas gratis.** 1.963 líneas con tercero → cuenta de
   tres años. Sembrar `regla_causacion` desde ahí haría que el primer mes no
   costara una decisión por proveedor.

## Lo que queda fuera del archivo que arma Contab

La nómina, las notas contables, la depreciación y los gastos bancarios no salen
de la DIAN. El archivo que Contab genera lleva **solo lo que causó**; el contador
sigue añadiendo lo demás a mano en el mismo formato, o se le da un sitio donde
pegar sus filas para que salga un solo archivo. Eso es una decisión suya.

## El catálogo real: un código, cuatro cuentas

El catálogo que mandó el contador el 2026-10-28 (106 filas, hojas «Hoja1» y
«Hoja2») enseñó que **un código de impuesto de Siigo no tiene una cuenta: tiene
cuatro**, una por contexto, y el archivo las trae como cuatro bloques sin
columna que lo diga:

| Contexto | Cómo se reconoce | IVA 19 % servicios (`02`) | Compras 2,5 % (`17`) |
|---|---|---|---|
| venta | cuenta `1355…` (lo que me retienen) o `2408 05…` | `24080504` | `13551519` |
| compra | cuenta `2365/2367/2368…` o `2408 1…` | `24081501` | `23654001` |
| dev_venta | como venta, con «Dev» en la descripción | `24082004` | `13551520` |
| dev_compra | como compra, con «Dev» en la descripción | `24080604` | `23654002` |

Con el catálogo cargado (`siigo_impuesto`), **la cuenta de cada línea de IVA y
de retención sale de él** según el contexto del asiento; las cuatro cuentas de
la empresa (D-127) quedan de respaldo. Y como hay dos códigos de IVA por
tarifa —bienes y servicios—, qué IVA factura un proveedor es lo único del IVA
que el documento no dice: se elige al aprobar y la regla lo recuerda
(`regla_causacion.iva_codigo`); servicios es el valor por defecto.

## Cómo entra el catálogo de cada empresa

El contador manda **un Excel por empresa** y carga las demás él mismo desde el
panel «Siigo» de la bandeja (`siigo_importar`, con vista previa). Dos hojas,
leídas por nombre de columna:

- **Impuestos**: `Código`, `Nombre`, `Tipo` (IVA · Retefuente · ReteIVA ·
  ReteICA · Autorretención), `Tarifa (%)`, `Cuenta`. Los de IVA van a
  `iva:<tarifa>`; los de retención se cruzan con el concepto **por cuenta** y, si
  no, por tipo y tarifa, y le ponen su `codigo_siigo`. Lo que no cruza se
  devuelve con nombre.
- **Comprobantes**: `Clase` (texto: «factura de compra», «nota crédito de
  venta», «documento soporte»…), `Tipo en Siigo`, `Último consecutivo`.
