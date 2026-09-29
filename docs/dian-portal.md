# El portal de la DIAN — reconocimiento

> Tarea **2.1** del [plan de automatización](../plans/dian-siigo-automation-plan.md).
> Este archivo existe porque el portal es un contrato que nadie firmó con nosotros:
> cuando cambie —y va a cambiar—, la diferencia entre lo que dice aquí y lo que
> responda entonces **es la depuración entera**.
>
> Lo de abajo está **verificado contra el portal real**, no recordado ni supuesto.
> Cada sección dice con qué fecha se comprobó.

## Resumen

El portal expone **dos caminos distintos**, y confundirlos fue el error de partida
del plan original:

| Camino | Necesita credenciales | Qué entrega |
|---|---|---|
| **Documento por CUFE** (`/User/SearchDocument`) | **No.** Solo pasar el Cloudflare Turnstile | Un documento: sus totales, sus validaciones, sus eventos RADIAN y el PDF |
| **Listado del mes** (Documentos electrónicos) | Sí, entrar con la cuenta de la empresa | El Excel con todos los documentos del periodo |

El primero es el que permite **dejar de perseguir soportes**: Contab ya tiene el
CUFE y el NIT de cada fila del reporte, así que puede bajar el documento oficial
en vez de esperar a que el cliente reenvíe un PDF.

---

## Camino público — documento por CUFE

**Verificado el 2026-09-22** con una factura real (Telesentinel → REAL Seguros,
CUFE `b55c678e…0683441`), sin iniciar sesión en ninguna cuenta.

### La cadena

| # | Petición | Cuerpo | Respuesta |
|---|---|---|---|
| 1 | `GET /User/SearchDocument` | — | el formulario, con el token anti-CSRF y el widget de Turnstile |
| 2 | `POST /User/SearchDocument` | `DocumentKey` (el CUFE), `SearchDocumentNit` (NIT **sin puntos ni DV**), `cf-turnstile-response`, `__RequestVerificationToken` | redirige a la vista del documento |
| 3 | `POST /Document/ShowDocumentToPublic` | `Id`, `Nit`, `Captcha`, token anti-CSRF | la página del documento |
| 4 | `POST /Document/DownloadPDF` | token anti-CSRF (cuerpo de ~1,4 KB) | `application/pdf`, ~72 KB |

El formulario pide **dos** datos: el CUFE **y** el NIT del emisor **o** del
receptor. Contab tiene los dos en cada fila del Excel, así que el cruce es directo.

### Lo que muestra la página del documento

Más de lo que trae el Excel de la DIAN:

- **Cabecera**: CUFE, serie, folio, fecha de emisión.
- **Emisor y receptor**: NIT y nombre de los dos.
- **Totales e impuestos**: total y IVA discriminado.
- **Estado en el registro de facturas electrónicas (RADIAN)**: quién es el
  *legítimo tenedor actual*.
- **Validaciones del documento**: nombre y resultado de cada una.
- **Eventos de la factura electrónica**: acuse, aceptación, rechazo — o «no tiene
  eventos asociados». **Esto es lo que necesita el semáforo de los 3 días hábiles
  de la Fase 6**, y creíamos que había que buscarlo en otro lado.

### El obstáculo real es el Turnstile, no la clave

El único portero del camino público es el **Cloudflare Turnstile**. Por eso el
camino `robot` de D-097 —contexto persistente de navegador, que ya funciona en
`apps/dian-rut`— no es el plan B: para este camino **es el plan A**.

### ⚠ El PDF viene cifrado, y la contraseña es el NIT

Al descargar, el portal avisa: *«Este archivo contiene contraseña y corresponde al
NIT del Emisor o Receptor que digitó anteriormente»*.

Comprobado:

```
pdftotext archivo.pdf -          → Command Line Error: Incorrect password
pdftotext -upw 900181831 …       → abre y extrae el texto
```

**Y Contab hoy no lo maneja.** `pdf_cufe.extract_cufes` sobre ese archivo devuelve:

```
ExtractionResult(cufes=[], source='none', status='no_text', error=None)
```

Dice «no tiene texto» —falso— y **no reporta error**. O sea que si se bajaran los
soportes del portal a la carpeta del mes, la validación V1 los marcaría todos como
*«Sin soporte PDF»* y el contador saldría a pedirle al cliente documentos que ya
están en el disco. Es la firma de defecto que D-080 vino a prohibir: una causa
técnica disfrazada de dato faltante.

El arreglo es barato porque **Contab ya sabe la contraseña**: el NIT está en la
fila. Hay que pasárselo a `pdftotext` (`-upw`) y a `pypdfium2`, y cuando aun así no
abra, decir *«protegido con contraseña»* — nunca *«sin texto»*.

---

## Camino autenticado — el listado del mes

**Verificado el 2026-09-28** contra una empresa real, entrando de verdad y
exportando un listado.

### No hay contraseña: el acceso es un enlace de un solo uso

La DIAN manda por correo un enlace de la forma:

```
GET /User/AuthToken?pk=<idUsuario>|<cédula>&rk=<NIT>&token=<uuid>
```

Abrirlo **establece la sesión**. No hay usuario/clave que guardar en ninguna parte.

> **Esto contradice el supuesto de D-098.** Esa decisión guardaba credenciales
> cifradas en el llavero del sistema porque se asumía un login con clave. No hay
> clave: lo que el contador pega es un enlace efímero. La bóveda deja de ser
> necesaria para este camino, y con ella se va el mayor riesgo del proyecto
> —custodiar credenciales fiscales ajenas—. **Pendiente de confirmar con @SKuger
> antes de reescribir la decisión.**

### La cadena

| # | Petición | Datos | Respuesta |
|---|---|---|---|
| 1 | `GET /User/AuthToken` | `pk`, `rk`, `token` (del correo) | sesión establecida (cookie) |
| 2 | `GET /Document/Export` | — | el formulario de «Descargar listados» |
| 3 | `POST /Document/Export` | `StartDate`, `EndDate`, `GroupCode`, `ReceiverCode`, `Type`, `AmountAdmin`, token anti-CSRF | `200 application/json` — la solicitud queda **encolada** |
| 4 | `POST /Document/TasksPartial` | token anti-CSRF | la tabla de solicitudes con su estado |
| 5 | `GET /Document/DownloadExportedZipFile?pk=<NIT>&rk=<uuid de la solicitud>` | — | **un ZIP** |

**Es asíncrono**: crear la solicitud no devuelve el archivo. Hay que sondear el
paso 4 hasta que la fila aparezca completa, y solo entonces descargar. El `rk` de
la descarga es el identificador de esa solicitud, no el token de acceso.

### El formulario

| Campo | Qué es |
|---|---|
| `ReceiverCode` | NIT receptor. Opcional, filtra |
| `export-range` | rango de fechas, formato `AAAA-MM-DD - AAAA-MM-DD` |
| `GroupCode` | `0` Todos · `1` Emitidos · `2` Recibidos |

Tope declarado en la página: **100.000 documentos por exportación**.

### Tres trampas al automatizarlo

1. **El navegador sin ventana está bloqueado.** Con `headless=True` el portal
   responde *«Solicitud bloqueada por controles de seguridad»*. Necesita navegador
   real — lo mismo que ya hace `apps/dian-rut`.
2. **El campo de fechas no acepta que le escriban.** Es un selector de rango con
   calendario propio: un `fill()` se descarta y queda el rango por defecto. Hay que
   manejar el calendario o fijar el valor disparando los eventos del widget. *(Se
   descubrió creando sin querer una solicitud con el rango por defecto.)*
3. **Lo que baja es un ZIP, no un `.xlsx`.** Dentro viene un único Excel con el
   nombre del uuid de la solicitud. El importador tiene que descomprimir.

### El Excel de adentro es el que Contab ya sabe leer

Comprobado con `excel.load_excel` sobre el archivo descargado: **32 columnas**, la
estructura de `excel-structure.md`, y parsea sin tocar nada.

Dos diferencias con lo documentado, que se corrigieron en `excel-structure.md`:

- **Las fechas vienen ISO** (`2026-09-28`, `2026-09-28T14:42:08`), no `dd-mm-yyyy`.
  El código ya lo maneja —`periodo_from_row` valida la forma antes de usarla
  (D-081)—; lo que estaba desactualizado era la documentación.
- Aparece el tipo **`Application response`**, que no estaba en la lista. Son los
  eventos RADIAN (acuse, aceptación), con `Total` e `IVA` en cero. En la muestra:
  9 de 10 filas. **Ojo al validar**: no son facturas y no tienen soporte que
  buscarles.

### ⚠ Lo que NO se ha mirado: «Documentos recibidos»

**Pendiente, y es la pregunta más importante que queda del portal.** El menú tiene
una sección `/Document/Received` que **nunca se abrió**. El recorrido del
2026-09-28 fue directo a «Descarga de listados», que era lo que el contador usa a
diario, y la sección de documentos recibidos quedó sin revisar.

Importa porque es **el único sitio del portal donde podría estar el XML**. Lo que
hay que comprobar cuando haya un enlace de acceso nuevo:

- ¿Cada documento de esa lista tiene descarga propia?
- Si la tiene, ¿entrega el **XML**, un **ZIP con XML y PDF**, o solo el PDF otra vez?

De la respuesta depende la **Fase 3 entera**: el portal público solo da PDF, y el
correo de facturación —la vía que la ley garantiza— no está disponible en este
caso. Si esa sección tampoco da XML, la Fase 3 se queda esperando a que se resuelva
el acceso al correo, y conviene decirlo en el plan en vez de arrastrarla.

> Nota de método: la frase «el portal no da XML» se escribió aquí antes de haber
> mirado esta sección. Era una conclusión más amplia que la evidencia que la
> sostenía — dos pantallas de las cinco del menú.

## Lo que sigue sin resolver

**No se vio dónde bajar el XML** de un documento. Ni el camino público (solo PDF)
ni el listado lo ofrecen. Hasta que aparezca, la Fase 3 depende de conseguir los
XML por el correo de recepción del cliente.

## Cómo se capturó esto

Un Chromium con contexto persistente, con el registro de peticiones filtrado para
anotar **método, URL y los nombres de los parámetros — nunca los valores**, de modo
que ni la clave ni los tokens quedan en ningún archivo. De un token se anota su
forma y su expiración, no su contenido.
