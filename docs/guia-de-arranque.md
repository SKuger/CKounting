# Contab — cómo arrancar con una empresa

> Para Carlos. Son nueve pasos; los cinco primeros se hacen **una sola vez** por
> empresa, y el de las tarifas una sola vez en total. Después, cada mes son
> los tres últimos.

## Lo que necesita tener a la mano

- Google Chrome o Microsoft Edge instalado.
- El Excel de tarifas que ya llenó (el de UVT y conceptos de retención).
- Para cada empresa: su NIT, y saber si es agente de retefuente, responsable
  de IVA y con qué periodicidad. Es lo mismo que puso en la hoja «Empresas».

## Una sola vez por empresa

**1. Crear la empresa.** En *Empresas → Nueva*, con el NIT y la razón social.
Contab solo conoce a REAL Seguros; las otras cuatro hay que crearlas.

**2. Elegir su carpeta.** En la ficha de la empresa, el botón **«Elegir
carpeta»**. Es una carpeta del computador donde Contab va a guardar todo lo de
esa empresa: dentro crea una por mes, y en cada mes van el Excel y la carpeta
`soportes`. Si ya tenía meses en otras carpetas, Contab le enseña qué movería y
no mueve nada hasta que usted apruebe.

**3. Llenar el perfil fiscal.** En la ficha, la tarjeta **«Perfil fiscal»**:
régimen, responsable de IVA y periodicidad, agente de retefuente, de ReteIVA.
Sin esto Contab **no calcula ninguna retención** — a propósito: prefiere no
calcular a calcular sobre un supuesto.

**4. Subir el Excel de tarifas.** Tarjeta **«Tarifas y UVT»** → *Subir el
Excel*. Le enseña qué leyó antes de guardar nada. Sirve para todas las
empresas; basta subirlo una vez. Si cambia una tarifa por decreto, se edita
ahí mismo o se vuelve a subir el archivo: no hay que actualizar el programa.

**5. Marcar los proveedores que importan.** En **«Terceros»**, con el lápiz de
cada fila: si es gran contribuyente, autorretenedor o del régimen simple, y el
estado del RUT. Solo hace falta para los que cambien el cálculo; los demás
pueden quedar en blanco e ir llenándose con calma. Cuando no se sabe, Contab
propone la retención ordinaria y **marca la factura** para que usted la mire.

## Cada mes

**6. Crear el mes y traer el listado.** *Crear mes* → **«Traer de la DIAN»**
con el enlace de acceso que le llega al correo. Si prefiere, suba el Excel que
descargó usted. Queda guardado dentro de la carpeta del mes.

**7. Bajar los soportes (opcional).** Tarjeta **«Soportes oficiales»** → *Bajar
los de este mes*. Trae los PDF que falten, directo del portal, sin pedírselos
al cliente. Si la DIAN rechaza la verificación, pulse **«Abrir mi navegador»**
y vuelva a intentarlo. Se puede detener y seguir después: lo ya bajado no se
pierde.

**8. Causar.** Tarjeta **«Causación»** → *Armar la propuesta del mes*. Verá
tres grupos: **por decidir**, **listos para aprobar** y **aprobados**.

   - El **primer mes** casi todo cae en «por decidir»: una vez por proveedor
     o cliente. Abra la factura, vea el asiento completo, ponga la cuenta del
     gasto (o del ingreso, en una venta), **elija la retención** (o «ninguna»)
     y apruebe. Lo que decida se recuerda.
   - En el **primer asiento de cada empresa** escriba arriba las cuentas que
     Contab no puede saber: **proveedores** e **IVA descontable** para lo que
     compra; **clientes** e **IVA generado** para lo que vende. Se guardan
     para esa empresa.
   - Entran las compras, las ventas (con sus notas crédito) y los documentos
     soporte a no obligados, cada uno marcado. La **nómina no**: el reporte no
     trae lo que hace falta.
   - El **segundo mes**, las facturas de proveedores que ya decidió salen en
     «listos»: *Aprobar los N listos* y adelante. Si un proveedor factura algo
     distinto a lo de siempre, se lo vuelve a preguntar.
   - Lo que esté en rojo o con aviso amarillo es para mirar antes de aprobar.
     Aprobar por error se deshace con la flecha.

**9. El archivo de Siigo.** *Archivo de Siigo* deja `siigo-AAAA-MM.xlsx` en la
carpeta que elija, en el mismo formato de importación de comprobantes que usted
sube hoy. La primera vez, pulse **«Siigo»** y suba el Excel con el catálogo de esa
empresa (hoja «Impuestos»: código, nombre, tipo, tarifa, cuenta; hoja
«Comprobantes»: clase, tipo en Siigo, último consecutivo) — Contab le enseña
qué leyó antes de guardar—, o escriba a mano lo que Contab no puede adivinar: el **tipo de comprobante** de cada clase (compras, ventas, notas,
documento soporte), el **último consecutivo** de cada tipo que ya está en
Siigo, y el **código de IVA** de cada tarifa. El código de Siigo de cada
concepto de retención se escribe en *Tarifas y UVT*, junto a su cuenta. Si al
exportar falta alguno, Contab se lo dice y deja la celda vacía: no inventa
códigos. Las cuentas van tal como las escribió (use las subcuentas de 8
dígitos de su PUC). *Exportar aprobados* sigue ahí, como listado simple.

## Qué esperar

- El primer mes de una empresa cuesta: una decisión por proveedor.
- El segundo mes debería salir en su mayoría solo. **Cuente cuántos**: la
  pantalla muestra «N listos de M». Ese número es el que nos dice si esto
  sirve o no.
- Si algo no cuadra o no entiende un aviso, no lo apruebe: escríbalo tal cual
  y mándeselo a Samuel. Un aviso que no se entiende es un defecto nuestro.
