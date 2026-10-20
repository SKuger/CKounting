# El Excel de tarifas del contador — estructura verificada

> Tarea **4.1** del [plan de automatización](../plans/dian-siigo-automation-plan.md).
> Escrito **contra el archivo real** que entregó el contador el 2026-10-20, igual
> que [`excel-structure.md`](excel-structure.md) se escribió contra el reporte de
> la DIAN. Lo de aquí está comprobado leyendo el archivo, no supuesto.
>
> **El archivo NO está en el repo.** Trae NIT y razón social de clientes reales;
> `docs/samples/` es solo para datos falsos. Vive fuera, y para rehacer esta
> lectura hay que pedírselo al usuario.

## Por qué las tarifas las pone él

Son ley y cambian por decreto (D-102). Si las sembrara el programa, cada enero
habría que publicar una versión para cambiar un número, y quien no actualizara
estaría liquidando con las del año pasado sin enterarse.

---

## ⚠ La trampa: las tarifas vienen como fracción, no como número de porcentaje

La columna «Tarifa (%)» trae **`0.11` con formato de celda `'0%'`**, no `11`.
Es una celda de porcentaje de Excel: lo que se ve es `11%` y lo que se guarda es
`0.11`.

```python
celda.value          # 0.11
celda.number_format  # '0%'
```

**Leer ese número como si fuera un porcentaje da 0,11% en vez de 11%: cien veces
menos retención, en todas las filas, sin que nada falle.** El importador tiene
que mirar `number_format`:

| Formato de la celda | Qué significa `0.11` |
|---|---|
| contiene `%` | **fracción** → tarifa = valor × 100 = 11% |
| no contiene `%` | número de porcentaje → tarifa = 11 si el valor es 11 |

Y hay que tolerar las dos, porque el siguiente contador puede escribir `11`.

> El formato que usó es `'0%'` sin decimales, así que `0.035` **se ve como «4%»**
> en pantalla aunque valga 3,5%. El valor guardado es el bueno; no «corregir» por
> lo que se ve.

---

## Las hojas

### 1. UVT — 11 años, con su norma

| Columna | Ejemplo | Notas |
|---|---|---|
| Año | `2026` | entero |
| Valor de la UVT (pesos) | `52374` | entero, pesos |
| Norma de referencia | `Resolución DIAN 000238 de 2025` | texto libre; **vale la pena guardarlo**: es la trazabilidad de por qué ese número |

Entregó de 2016 a 2026. La UVT de 2026 es **52.374**.

### 2. Retenciones — 24 conceptos

| Columna | Qué trae de verdad |
|---|---|
| Concepto | texto libre, en español y con sus palabras (`Honorarios`, `Servicios en general PN no declarantes`) |
| Tarifa (%) | **fracción con formato de porcentaje** (ver la trampa), o **texto** en las de ReteIVA |
| Base mínima (UVT) | número (`2`, `10`), o el texto **`N/A`** |
| Base mínima (pesos) | **inservible, ignorar** (ver abajo) |
| Cuenta PUC | código de 8 dígitos (`23651503`) — cruza con el PUC que ya está cargado |
| Aplica a | `Declarantes`, `No Declarantes`, `Declarantes y No Declarantes`, o una frase |
| Rige desde | fecha (llegó como `datetime`, no como texto) |

**`N/A` en la base mínima significa que no hay mínimo**: se retiene desde el
primer peso. No es un dato faltante, y tratarlo como tal dejaría sin retener los
honorarios, las comisiones y los arrendamientos de muebles.

**La columna de pesos está vacía de hecho.** Sus fórmulas son
`=ROUND(C13*$F$2,-3)` y **`$F$2` no existe**: en la plantilla que le mandé, la
fila 2 es el texto de ayuda combinado, así que no había dónde poner la UVT. Las
fórmulas dan 0. No es culpa suya — es un defecto de mi plantilla. El importador
**calcula los pesos** multiplicando las UVT por el valor del año, que para eso
está la hoja 1.

#### Las dos filas que no son retención en la fuente

Las dos últimas son **ReteIVA** y no encajan en la forma de las demás:

| Campo | Valor |
|---|---|
| Tarifa | `15% del IVA` (texto) |
| Base mínima (UVT) | `Bases retención renta` (texto) |
| Base mínima (pesos) | `IVA Facturado` (texto) |
| Aplica a | `Personas que se encuentren r…` |

Se retiene el **15% del IVA facturado**, no un porcentaje de la base. El motor
necesita distinguir las dos familias: *porcentaje sobre la base* y *porcentaje
sobre el IVA*. Meterlas en la misma tabla sin esa marca haría que ReteIVA se
calculara sobre la base y saliera mal.

### 3. ICA — **no aplica**

Llegó solo con mi fila de ejemplo. Carlos lo dijo explícitamente:

> «La Hoja de ICA por ahora no aplica ya que ninguna de las empresas es agente de
> retención de ICA.»

Lo confirma la hoja de empresas: las cinco con `NO` en «¿Agente de ReteICA?».
**No se construye la tabla de tarifas de ICA** hasta que alguna lo sea. La tabla
`empresa_municipio_ica` que ya existe se queda sin usar; no construir encima.

### 4. Empresas — cinco, y Contab solo conoce una

| NIT | Razón social | Régimen | IVA | Periodicidad | Retefuente | ReteIVA | ReteICA | Autorret. | Gran contr. |
|---|---|---|---|---|---|---|---|---|---|
| 900181831 | REAL SEGUROS LTDA AGENCIA DE SEGUROS | Ordinario | SÍ | Cuatrimestral | SÍ | *(ver abajo)* | NO | NO | NO |
| 900921756 | ALAGUNA HERNANDEZ LTDA AGENCIA… | Ordinario | SÍ | Cuatrimestral | SÍ | *(ver abajo)* | NO | NO | NO |
| 900911552 | CONOBRAS FG S.A.S. | Ordinario | SÍ | Cuatrimestral | SÍ | *(ver abajo)* | NO | NO | NO |
| 901048063 | CONESTRUCTURA INGENIERIA S.A.S | Ordinario | SÍ | Cuatrimestral | SÍ | *(ver abajo)* | NO | NO | NO |
| 901217207 | GRUPO DE COMERCIALIZADORES DE… | Ordinario | SÍ | **Bimestral** | SÍ | *(ver abajo)* | NO | NO | NO |

**Solo REAL SEGUROS existe hoy en Contab.** Las otras cuatro hay que crearlas.

#### El «SÍ/NO» que no era un sí ni un no

En «¿Agente de ReteIVA?» las cinco dicen **`SOLO AL REGIMEN SIMPLE DE TRIB`**.
No es una respuesta mal escrita: es la regla real. Son agentes de ReteIVA
**únicamente frente a proveedores del régimen simple**.

El perfil fiscal de hoy (`empresa_perfil_fiscal.agente_reteiva`) es un booleano,
y un booleano no puede decir esto. O se guarda con su condición, o el motor
retendrá ReteIVA a todo el mundo. **Decisión pendiente** antes de la 4.2.

### 5. Terceros — 4 de 25, y así va a seguir

Respondió 4: Colombia Telecomunicaciones, Seguros Comerciales Bolívar y las dos
Suramericana — todas `SÍ` gran contribuyente, `SÍ` autorretenedor, RUT `ACTIVO`.

> «La hoja de los terceros toca llenarla con despacio y de acuerdo con la
> información que repose en las facturas ya que no tengo los RUT.»

**Esto es un requisito de diseño, no un retraso.** El motor tiene que funcionar
desde el primer día con los terceros en blanco y mejorar según se vayan
llenando. Si exige el catálogo completo para arrancar, la Fase 4 no sirve hasta
que él termine un trabajo manual de meses.

### 6. Preguntas — las cuatro respuestas

| Pregunta | Respuesta | Qué cambia |
|---|---|---|
| ¿Centros de costo? | **NO** | **Se caen de la tarea 4.3.** La regla mapea a cuenta PUC y nada más: una tabla, un campo y una pantalla menos |
| ¿Qué mira para decidir la cuenta? | **LA FACTURA** | La regla se indexa por **concepto**, no por proveedor |
| ¿Proveedores que siempre van a la misma cuenta? | Telesentinel (800144355), Todo en Artes (900252156), Ultragas (811046191) | Hace falta **también** una regla por tercero, que gana sobre la del concepto |
| ¿Régimen simple? | **Todas ordinario** | La rama del simple no se construye todavía |

Las dos del medio juntas dan la forma de la regla: **primero se mira si ese
tercero tiene cuenta fija; si no, se decide por el concepto de la factura.**

---

## Lo que hay que devolverle a Carlos

1. Que su columna de pesos quedó en cero por un fallo de **mi** plantilla, y que
   no hace falta que la rellene: se calcula con la UVT.
2. Que la hoja de ICA se retira de la próxima versión.
3. Una pregunta nueva, que decide cómo se comporta el motor con los 21 terceros
   sin datos: **cuando no sabe si un proveedor es gran contribuyente o
   autorretenedor, ¿qué hace hoy — retiene normal, o lo deja pendiente?**
