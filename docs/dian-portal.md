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

**Pendiente de verificar.** Es la mitad que necesita entrar con la cuenta de la
empresa. Lo que hay que dejar escrito aquí cuando se haga:

- Cómo se autentica y **qué token se emite, y cuánto dura** — de eso depende si se
  pueden bajar N empresas en una corrida o hay que reautenticar en medio.
- **Qué petición hay detrás del botón «Exportar»** del listado de Documentos
  electrónicos, con sus parámetros de rango de fechas.
- Si desde ahí se puede bajar el **XML** de cada documento. El camino público
  **no ofrece XML**, solo PDF, así que hoy la Fase 3 sigue dependiendo de
  conseguir los XML por otra vía (el correo de recepción del cliente).

## Cómo se capturó esto

Un Chromium con contexto persistente, con el registro de peticiones filtrado para
anotar **método, URL y los nombres de los parámetros — nunca los valores**, de modo
que ni la clave ni los tokens quedan en ningún archivo. De un token se anota su
forma y su expiración, no su contenido.
