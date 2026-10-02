# El portal de la DIAN — reconocimiento

> Tarea **2.1** del [plan de automatización](../plans/dian-siigo-automation-plan.md).
> Este archivo existe porque el portal es un contrato que nadie firmó con nosotros:
> cuando cambie —y va a cambiar—, la diferencia entre lo que dice aquí y lo que
> responda entonces **es la depuración entera**.
>
> Lo de abajo está **verificado contra el portal real**, no recordado ni supuesto.
> Cada sección dice con qué fecha se comprobó.

## Dos sistemas distintos, dos defensas distintas (2026-10-02)

Esto se confunde una y otra vez, y lleva a pensar que «la DIAN empezó a
detectarnos». No es lo mismo:

| Pantalla | Dominio | Qué tiene delante |
|---|---|---|
| **Terceros** (consulta de RUT) | `muisca.dian.gov.co` | nada: responde `Server: DIAN`, sin WAF ni captcha |
| **Soportes y listados** | `catalogo-vpfe.dian.gov.co` | **Azure Front Door** (cabecera `x-azure-ref`) **y** un Turnstile de Cloudflare en la página |

Comprobado con las cabeceras el 2026-10-02. Terceros nunca tuvo que pasar ningún
portero; por eso funcionó desde el primer día sin pelear. Al bajar soportes no es
que nos hayan empezado a detectar: es que cambiamos de puerta, y esta sí tiene
guardia.

> El `CLAUDE.md` decía que el scraper de Terceros «sortea Cloudflare». No hay
> Cloudflare que sortear en MUISCA; la frase mandaba a buscar el problema donde
> no estaba.

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

### El botón de descargar no descarga: hay un aviso de por medio (2026-10-01)

«Descargar PDF» es un `a.downloadLink` que **no pide el archivo**. Abre un aviso
—*«Este archivo contiene contraseña y corresponde al NIT del Emisor o Receptor que
digitó anteriormente»*— y la descarga solo arranca al pulsar **«Aceptar»**.

Esto tuvo a `descargar_soportes` roto desde que se escribió: pulsaba el primero,
esperaba un archivo que no iba a salir y reventaba a los 60 s con un *timeout* de
descarga. **Se culpó a Cloudflare, y no era.** El síntoma engaña porque el clic sí
dispara una petición —el icono de advertencia del aviso— y parece que algo pasó.

### La cadena entera sin navegador, y dónde está el techo (2026-10-01)

Los cuatro pasos se pueden hacer por **HTTP plano**, sin conducir el navegador,
porque el portero —el Turnstile— viaja como **campo del formulario**, no como
cookie, y por tanto se puede trasplantar a un cliente HTTP.

| Paso | Petición | Campos que importan |
|---|---|---|
| 1 | `GET /User/SearchDocument` | de aquí sale `__RequestVerificationToken` |
| 2 | `POST /User/SearchDocument` | `DocumentKey`, `SearchDocumentNit`, `cf-turnstile-response`, rvt |
| 3 | `POST /Document/ShowDocumentToPublic` | `Id`, `Token`, `Captcha`, `Nit`, rvt — **salen del paso 2**, que no devuelve el documento sino un formulario puente que el navegador reenvía solo |
| 4 | `POST /Document/DownloadPDF` | `trackId` (el CUFE), `token`, `captcha`, rvt → el PDF |

Un documento así tarda **2-3 s** en vez de los ~25 s a clics. Pero:

1. **El token del Turnstile es de un solo uso.** `window.turnstile.reset()` da uno
   nuevo en 2-9 s; es el verdadero techo, y por eso el navegador sigue abierto
   aunque ya no descargue nada: solo fabrica tokens.
2. **Cada documento necesita sesión propia.** Reusando cookies el acierto cae a
   1 de 6; con un cliente nuevo por documento sube a 3 de 5 por intento.
3. **El portal deja correr un rato y luego cierra la llave.** Medido con el
   septiembre real (32 documentos): los **primeros 7 a 5,6 s cada uno**, y del
   octavo en adelante aparece **«Un momento, estamos comprobando que no sea un
   bot»** —el WAF de Microsoft, no Cloudflare— y todo se va al respaldo a clics.

Esa tercera trampa tiene una consecuencia que costó una corrida entera entender:
**sin cortacircuitos la optimización sale más lenta que no optimizar**, porque se
paga el intento rápido Y los clics. Medido: 33 s por documento contra los 25 s del
camino a clics. Con cortacircuitos —rendirse tras unos fallos seguidos— el mismo
lote bajó a **7,5 s por documento**.

> Y un defecto que firmaba sus propios duplicados: el resultado del camino rápido
> se guardaba DENTRO del `try`, así que si cerrar el cliente HTTP reventaba con el
> PDF ya en disco, el documento se daba por fallido y el respaldo lo bajaba otra
> vez. Se vio como **17 archivos `_dian` en una corrida de 32**.

### Y sí se puede automatizar: tres seguidas, sin credenciales (2026-10-01)

Comprobado con una factura real (SURAMERICANA → ALAGUNA HERNANDEZ, 71 KB), con el
navegador que lanza Playwright usando el Chrome del sistema y **sin sesión de
nadie**: tres descargas seguidas en la misma corrida, sin que el Turnstile pidiera
nada. Unos **25 s por documento**: un mes de 40 facturas son ~17 minutos.

Lo que Cloudflare protege es la vista de documento **dentro de la sesión**
(`/Document/Received`), no esta búsqueda pública. Son dos cosas distintas y
conviene no volver a mezclarlas.

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

### Documentos recibidos — **aquí sí está el XML** (2026-10-01)

`/Document/Received` es la sección que faltaba mirar, y responde la pregunta que
bloqueaba la Fase 3: **cada documento se baja con su XML**.

### Cómo

| # | Paso | Detalle |
|---|---|---|
| 1 | `GET /Document/Received` | el buscador. El rango por defecto son los **últimos dos días** |
| 2 | `POST /Document/GetDocumentsPageToken` | la búsqueda: `StartDate`, `EndDate`, `DocumentKey`, `SerieAndNumber`, `SenderCode`, `ReceiverCode`, `DocumentTypeId`, `Status`, `RadianStatus`, `ReferencesType`, `FilterType`, token anti-CSRF |
| 3 | botón `button.download-document` de cada fila | su `data-id` es el **CUFE**; el tooltip dice «Descargar elementos» |
| 4 | la descarga | **ZIP con dos archivos**: `<cufe>.pdf` y `<cufe>.xml` |

### Qué trae el XML

Comprobado con una factura real: es un **`Invoice` UBL directo** —no un
`AttachedDocument` con el documento dentro de un CDATA, así que no hay que
desenvolver nada—. En la muestra: `cbc:UUID` (el CUFE), `IssueDate`, `ProfileID`,
`AccountingSupplierParty`, `AccountingCustomerParty`, **dos `cac:InvoiceLine`**,
`LineExtensionAmount` y `PayableAmount`. Sin `TaxTotal`, porque era una póliza de
seguros (exenta); hay que ver uno con IVA para confirmar la forma de los impuestos.

### ⚠ Esto NO se puede automatizar con un navegador propio

**Cloudflare Turnstile rechaza el navegador que lanza Playwright**, aunque se le
pase el Chrome del sistema con `executable_path`. El síntoma es silencioso y
costó un rato entenderlo: el botón de descarga **no dispara ni una petición** —el
JavaScript se detiene porque la verificación falló— y la página no dice nada.

> **Pendiente de volver a mirar con esta lente**: el 2026-10-01 se descubrió que en
> el camino público el mismo síntoma —un clic que no baja nada— era un aviso con un
> «Aceptar», no el Turnstile. Nadie ha comprobado si `button.download-document`
> abre algo parecido.

Lo que sí funciona es el **modo humano** que este proyecto ya tenía para el scraper
del RUT (D-058): el usuario abre **su propio navegador** con el puerto de
depuración (`/api/dian/launch-browser`), entra él, y el bot se engancha con
`connect_over_cdp("http://127.0.0.1:9222")`. Cloudflare ve un navegador normal
porque lo es. Con eso la descarga funcionó a la primera.

> **Y no es parejo**: la *Descarga de listados* (el Excel del mes) **sí** funciona
> con el navegador automatizado — se comprobó el 2026-09-28. Lo que Cloudflare
> protege es la vista de documento. Así que la Fase 2 puede seguir como está, pero
> **traer los XML exige el modo humano**.

## Lo que sigue sin resolver

~~No se vio dónde bajar el XML.~~ **Resuelto el 2026-10-01**: está en *Documentos
recibidos*, uno por uno, con el modo humano. Lo que queda por decidir es **cómo
encaja en el producto**: bajar N documentos exige que el contador abra su navegador
y entre, así que no puede ser una corrida desatendida.

## Cómo se capturó esto

Un Chromium con contexto persistente, con el registro de peticiones filtrado para
anotar **método, URL y los nombres de los parámetros — nunca los valores**, de modo
que ni la clave ni los tokens quedan en ningún archivo. De un token se anota su
forma y su expiración, no su contenido.
