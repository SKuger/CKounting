# El antivirus marca el instalador

Avast avisa de «programa sospechoso» **en cada actualización**. No es un fallo del
instalador ni de una versión concreta: es la consecuencia directa de D-059 (no se
compró certificado de firma), y se va a repetir en cada release hasta que eso
cambie.

## Por qué pasa

Tres cosas que se suman, en orden de peso:

1. **El instalador no va firmado.** Sin Authenticode, Windows y el antivirus no
   tienen manera de saber quién publicó el archivo. Lo dice el propio
   [`electron-builder.yml`](../apps/shell/electron-builder.yml).
2. **Dentro van dos ejecutables de PyInstaller** (los sidecars de Python). Están
   entre lo que más dispara las heurísticas: empaquetan un intérprete y se
   descomprimen solos en memoria, que es el patrón del malware empaquetado.
3. **Cada versión es un archivo nuevo con cero descargas.** La reputación no se
   acumula: aunque Avast deje pasar la 0.4.6, la 0.4.7 vuelve a ser desconocida.

Lo que **no** hay que hacer: ofuscar, renombrar los `.exe`, comprimir distinto o
tocar los metadatos para «no parecer sospechoso». No funciona, y es exactamente lo
que hace el software malicioso de verdad.

## Arreglo de raíz (pendiente)

Firmar con un certificado Authenticode. Quita también el aviso de SmartScreen.
D-098 (hoy superseded por D-133: no hay credenciales que custodiar) anotó que dejaba de ser opcional cuando Contab custodiara credenciales
fiscales de los clientes del contador: *«a un usuario que está por entregar las
claves de la DIAN de sus clientes no se le recibe con una advertencia»*.

## Lo que se hace mientras tanto

### 1. Programa de whitelisting de Avast (gratis, por versión)

Es la vía buena sin certificado. Hay que registrarse **una vez** y luego subir
cada build **antes** de publicarlo.

- Registro: https://www.avast.com/whitelist-program-registration
- Tras la aprobación llegan credenciales FTP por correo; los builds se suben ahí.
- Condiciones: solo archivos completos (nada de *delta updates*), varios archivos
  comprimidos en ZIP. Es gratis y no pide certificado.

> **Esto entra en la lista de cierre de cada release**: subir
> `Contab-Setup-X.Y.Z.exe` antes de publicar el release, no después de que el
> usuario vea el cartel.

### 2. Falso positivo suelto (cuando ya saltó)

- Formulario: https://www.avast.com/submitsample
- Guía: https://support.avast.com/en-us/article/submit-file-url/
- Hay que dar **el nombre de la detección** y el **ID de la alerta** que muestra
  Avast, además del archivo o su URL. Sin el nombre de la detección el reporte
  sirve de poco: pídeselo a quien vio el aviso.

El texto a enviar está en [`avast-report.md`](avast-report.md), con los datos de la
versión al día.

### 3. Exclusión local (inmediato, para el usuario de hoy)

En Avast: **Menú → Configuración → General → Excepciones → Añadir excepción**, y
poner la carpeta de instalación:

```
C:\Users\<usuario>\AppData\Local\Programs\Contab
```

El instalador es **per-user** (`perMachine: false`), así que vive ahí y no en
`Archivos de programa`. Si se cambió la carpeta al instalar
(`allowToChangeInstallationDirectory: true`), se mira con clic derecho en el acceso
directo → *Abrir ubicación del archivo*.

Esto calla el aviso en **ese** equipo. No sirve para nadie más, y por eso no
sustituye al whitelisting.
