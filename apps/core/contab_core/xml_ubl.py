"""Lee el XML de la factura electrónica (UBL 2.1) — tarea 3.1 del plan.

Hoy el PDF se abre solo para sacar 96 caracteres: el CUFE. El XML trae el
documento entero —líneas, impuestos por tarifa, retenciones, y la referencia de
una nota crédito a su factura—, que es lo que hace falta para causar sin adivinar
desde el total.

**El XML es una capa pegada al Excel, nunca su reemplazo** (D-039, D-064). La
tabla que el contador reconoce sigue saliendo de `data_json`; esto se le añade.

## Dos envoltorios, un mismo documento

| Lo que llega | De dónde | Qué hay que hacer |
|---|---|---|
| `Invoice` / `CreditNote` / `DebitNote` directo | el portal (*Documentos recibidos*) | leerlo tal cual |
| `AttachedDocument` | el correo de recepción | el documento va **dentro de un CDATA**; hay que desenvolverlo |

El portal entregó un `Invoice` directo —comprobado el 2026-10-01, ver
[`docs/dian-portal.md`](../../../docs/dian-portal.md)—, pero el que llega por
correo viene envuelto, y los dos caminos siguen vivos (D-097). Se aceptan ambos.

> ⚠ **Lo que falta comprobar.** Esta implementación se escribió contra el estándar
> UBL 2.1 y contra la estructura que el reconocimiento anotó de un documento real
> (una póliza exenta: sin `TaxTotal`). **No se ha corrido contra un XML real con
> IVA ni con retenciones**, así que la forma de los impuestos está construida
> sobre el estándar, no sobre una muestra. Hasta que eso pase, no cantar la tarea
> como verificada.

## Por qué los importes nunca pasan por float

`Decimal` desde el texto del XML hasta la base (D-075). Un `19` por ciento sobre
`1.234.567` calculado en binario deja céntimos que no cuadran con la retención
que el cliente ya practicó, y ese descuadre lo paga el contador.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

# Subirlo re-lee lo que quedó cacheado con la versión vieja, igual que el de CUFE
# (D-067). Si no, una mejora del parser no llega nunca a los documentos ya leídos.
PARSER_VERSION = 1

NS = {
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "inv": "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2",
    "cn": "urn:oasis:names:specification:ubl:schema:xsd:CreditNote-2",
    "dn": "urn:oasis:names:specification:ubl:schema:xsd:DebitNote-2",
    "ad": "urn:oasis:names:specification:ubl:schema:xsd:AttachedDocument-2",
}

# El tipo de documento, tal como lo nombra la raíz del XML.
TIPO_FACTURA = "factura"
TIPO_NOTA_CREDITO = "nota_credito"
TIPO_NOTA_DEBITO = "nota_debito"
TIPO_DESCONOCIDO = "desconocido"

_RAIZ_A_TIPO = {
    "Invoice": TIPO_FACTURA,
    "CreditNote": TIPO_NOTA_CREDITO,
    "DebitNote": TIPO_NOTA_DEBITO,
}

# Estados, con el mismo criterio que `pdf_cufe`: un fallo técnico NUNCA se
# devuelve como «no hay datos» (D-080). Si no se pudo leer, se dice por qué.
ESTADO_OK = "ok"
ESTADO_NO_ES_XML = "no_es_xml"
ESTADO_SIN_DOCUMENTO = "sin_documento"
ESTADO_ERROR = "error"


class XmlInvalido(ValueError):
    """El archivo no es un XML que podamos leer."""


@dataclass
class Impuesto:
    """Un renglón de impuesto. `tipo` es el código DIAN: 01 IVA, 06 ReteFuente…"""
    tipo: str
    nombre: str | None
    base: Decimal | None
    tarifa: Decimal | None
    valor: Decimal | None
    es_retencion: bool = False

    def como_dict(self) -> dict[str, Any]:
        return {
            "tipo": self.tipo, "nombre": self.nombre,
            "base": _str_o_none(self.base), "tarifa": _str_o_none(self.tarifa),
            "valor": _str_o_none(self.valor), "es_retencion": self.es_retencion,
        }


@dataclass
class Linea:
    numero: int
    descripcion: str | None
    cantidad: Decimal | None
    valor_unitario: Decimal | None
    total: Decimal | None
    impuestos: list[Impuesto] = field(default_factory=list)

    def como_dict(self) -> dict[str, Any]:
        return {
            "numero": self.numero, "descripcion": self.descripcion,
            "cantidad": _str_o_none(self.cantidad),
            "valor_unitario": _str_o_none(self.valor_unitario),
            "total": _str_o_none(self.total),
            "impuestos": [i.como_dict() for i in self.impuestos],
        }


@dataclass
class Referencia:
    """A qué documento apunta este. Una nota crédito sin esto no se puede imputar."""
    cufe: str | None
    numero: str | None
    fecha: str | None
    codigo_motivo: str | None = None
    motivo: str | None = None

    def como_dict(self) -> dict[str, Any]:
        return {
            "cufe": self.cufe, "numero": self.numero, "fecha": self.fecha,
            "codigo_motivo": self.codigo_motivo, "motivo": self.motivo,
        }


@dataclass
class Documento:
    tipo: str
    cufe: str | None
    numero: str | None
    fecha_emision: str | None
    hora_emision: str | None = None
    moneda: str | None = None
    emisor_nit: str | None = None
    emisor_nombre: str | None = None
    # Lo que la FACTURA dice del emisor. Es lo que el contador mira cuando no
    # tiene el RUT del proveedor delante.
    emisor_responsabilidades: list[str] = field(default_factory=list)
    receptor_nit: str | None = None
    receptor_nombre: str | None = None
    subtotal: Decimal | None = None
    total_impuestos: Decimal | None = None
    total: Decimal | None = None
    lineas: list[Linea] = field(default_factory=list)
    impuestos: list[Impuesto] = field(default_factory=list)
    referencias: list[Referencia] = field(default_factory=list)

    def como_dict(self) -> dict[str, Any]:
        return {
            "tipo": self.tipo, "cufe": self.cufe, "numero": self.numero,
            "fecha_emision": self.fecha_emision, "hora_emision": self.hora_emision,
            "moneda": self.moneda,
            "emisor_nit": self.emisor_nit, "emisor_nombre": self.emisor_nombre,
            "emisor_responsabilidades": self.emisor_responsabilidades,
            "receptor_nit": self.receptor_nit, "receptor_nombre": self.receptor_nombre,
            "subtotal": _str_o_none(self.subtotal),
            "total_impuestos": _str_o_none(self.total_impuestos),
            "total": _str_o_none(self.total),
            "lineas": [x.como_dict() for x in self.lineas],
            "impuestos": [x.como_dict() for x in self.impuestos],
            "referencias": [x.como_dict() for x in self.referencias],
        }


@dataclass
class Lectura:
    """Resultado de leer un archivo. `estado` dice por qué si no hay documento."""
    documento: Documento | None
    estado: str
    error: str | None = None
    parser_version: int = PARSER_VERSION


def _str_o_none(x: Decimal | None) -> str | None:
    return None if x is None else str(x)


def _dec(texto: str | None) -> Decimal | None:
    """Decimal desde el texto del XML. Nunca float (D-075)."""
    if texto is None:
        return None
    t = texto.strip()
    if not t:
        return None
    try:
        return Decimal(t)
    except (InvalidOperation, ValueError):
        return None


def _txt(nodo: ET.Element | None, ruta: str) -> str | None:
    if nodo is None:
        return None
    hijo = nodo.find(ruta, NS)
    if hijo is None or hijo.text is None:
        return None
    t = hijo.text.strip()
    return t or None


def _sin_ns(etiqueta: str) -> str:
    return etiqueta.rsplit("}", 1)[-1]


# ─────────────────────────── desenvolver el AttachedDocument ───────────────────

def _desenvolver(raiz: ET.Element) -> ET.Element:
    """Saca el documento de dentro del `AttachedDocument`, si viene envuelto.

    El de correo llega como `AttachedDocument` con el `Invoice` entero metido en
    un CDATA dentro de `cbc:Description`. Es texto, no nodos: hay que volver a
    parsearlo.
    """
    if _sin_ns(raiz.tag) != "AttachedDocument":
        return raiz
    for desc in raiz.iter():
        if _sin_ns(desc.tag) != "Description" or not (desc.text or "").strip():
            continue
        interior = desc.text.strip()
        if "<" not in interior:
            continue
        try:
            return ET.fromstring(interior)
        except ET.ParseError:
            continue
    raise XmlInvalido(
        "El AttachedDocument no traía dentro ningún documento que se pudiera leer."
    )


# ─────────────────────────────────── impuestos ─────────────────────────────────

def _impuestos_de(nodo: ET.Element, etiqueta: str, es_retencion: bool) -> list[Impuesto]:
    salida: list[Impuesto] = []
    for total in nodo.findall(f"cac:{etiqueta}", NS):
        for sub in total.findall("cac:TaxSubtotal", NS):
            categoria = sub.find("cac:TaxCategory", NS)
            esquema = categoria.find("cac:TaxScheme", NS) if categoria is not None else None
            salida.append(Impuesto(
                tipo=(_txt(esquema, "cbc:ID") or "").strip() or "00",
                nombre=_txt(esquema, "cbc:Name"),
                base=_dec(_txt(sub, "cbc:TaxableAmount")),
                tarifa=_dec(_txt(categoria, "cbc:Percent")) if categoria is not None else None,
                valor=_dec(_txt(sub, "cbc:TaxAmount")),
                es_retencion=es_retencion,
            ))
        if not total.findall("cac:TaxSubtotal", NS):
            # Un total de impuesto sin desglose: se conserva, porque el importe
            # existe aunque no sepamos su base ni su tarifa.
            salida.append(Impuesto(
                tipo="00", nombre=None, base=None, tarifa=None,
                valor=_dec(_txt(total, "cbc:TaxAmount")), es_retencion=es_retencion,
            ))
    return salida


def _todos_los_impuestos(nodo: ET.Element) -> list[Impuesto]:
    return (_impuestos_de(nodo, "TaxTotal", False)
            + _impuestos_de(nodo, "WithholdingTaxTotal", True))


# ──────────────────────────────────── líneas ───────────────────────────────────

_ETIQUETAS_LINEA = ("InvoiceLine", "CreditNoteLine", "DebitNoteLine")


def _lineas_de(raiz: ET.Element) -> list[Linea]:
    salida: list[Linea] = []
    for etiqueta in _ETIQUETAS_LINEA:
        for i, nodo in enumerate(raiz.findall(f"cac:{etiqueta}", NS), 1):
            # La cantidad cambia de nombre según el tipo de documento.
            cantidad = None
            for campo in ("cbc:InvoicedQuantity", "cbc:CreditedQuantity",
                          "cbc:DebitedQuantity", "cbc:Quantity"):
                cantidad = _dec(_txt(nodo, campo))
                if cantidad is not None:
                    break
            item = nodo.find("cac:Item", NS)
            precio = nodo.find("cac:Price", NS)
            salida.append(Linea(
                numero=int(_txt(nodo, "cbc:ID") or i),
                descripcion=_txt(item, "cbc:Description") if item is not None else None,
                cantidad=cantidad,
                valor_unitario=_dec(_txt(precio, "cbc:PriceAmount")) if precio is not None else None,
                total=_dec(_txt(nodo, "cbc:LineExtensionAmount")),
                impuestos=_todos_los_impuestos(nodo),
            ))
    return salida


# ───────────────────────────────── participantes ───────────────────────────────

_RE_RESP = re.compile(r"O-?\s?(\d{1,3})", re.I)


def responsabilidades_de(texto: str | None) -> list[str]:
    """Los códigos de responsabilidad que vengan en un texto del XML.

    El anexo técnico de la DIAN los pone en `cbc:TaxLevelCode`, separados por
    `;` —«O-13;O-15»— pero se han visto con coma, con espacio y sin guion. Se
    normalizan a `O-13`.
    """
    if not texto:
        return []
    vistos: list[str] = []
    for n in _RE_RESP.findall(texto):
        codigo = f"O-{int(n)}"
        if codigo not in vistos:
            vistos.append(codigo)
    return vistos


def _parte(raiz: ET.Element, etiqueta: str) -> tuple[str | None, str | None, list[str]]:
    """(NIT, nombre, responsabilidades) del emisor o del receptor.

    Las responsabilidades salen de `cbc:TaxLevelCode` **de la propia factura**.
    Importa porque es lo que el contador hace a mano: cuando no sabe si a un
    proveedor se le retiene, *mira la factura*. Si el documento lo dice, Contab
    no tiene que esperar a que alguien teclee el catálogo de terceros.
    """
    cont = raiz.find(f"cac:{etiqueta}", NS)
    if cont is None:
        return None, None, []
    parte = cont.find("cac:Party", NS)
    if parte is None:
        return None, None, []
    nit = None
    ident = parte.find("cac:PartyTaxScheme/cbc:CompanyID", NS)
    if ident is None:
        ident = parte.find("cac:PartyIdentification/cbc:ID", NS)
    if ident is not None and ident.text:
        # El NIT llega a veces como «900181831-7»: el DV no es parte del NIT.
        nit = ident.text.strip().split("-")[0].strip() or None
    nombre = (_txt(parte, "cac:PartyTaxScheme/cbc:RegistrationName")
              or _txt(parte, "cac:PartyName/cbc:Name")
              or _txt(parte, "cac:PartyLegalEntity/cbc:RegistrationName"))
    resp = responsabilidades_de(_txt(parte, "cac:PartyTaxScheme/cbc:TaxLevelCode"))
    return nit, nombre, resp


# ───────────────────────────────── referencias ─────────────────────────────────

def _referencias(raiz: ET.Element) -> list[Referencia]:
    salida: list[Referencia] = []
    for etiqueta in ("BillingReference", "DiscrepancyResponse"):
        for nodo in raiz.findall(f"cac:{etiqueta}", NS):
            if etiqueta == "DiscrepancyResponse":
                salida.append(Referencia(
                    cufe=_txt(nodo, "cbc:ReferenceID"),
                    numero=None, fecha=None,
                    codigo_motivo=_txt(nodo, "cbc:ResponseCode"),
                    motivo=_txt(nodo, "cbc:Description"),
                ))
                continue
            factura = nodo.find("cac:InvoiceDocumentReference", NS) or nodo
            salida.append(Referencia(
                cufe=_txt(factura, "cbc:UUID"),
                numero=_txt(factura, "cbc:ID"),
                fecha=_txt(factura, "cbc:IssueDate"),
            ))
    # Una nota trae la misma referencia por los dos caminos: `BillingReference`
    # con el número y la fecha, y `DiscrepancyResponse` con el motivo. Se funden
    # por **CUFE**, que es el identificador único del documento; usar también el
    # número no fundía nada, porque la segunda no lo trae.
    vistos: dict[str, Referencia] = {}
    for r in salida:
        clave = (r.cufe or r.numero or "").strip().lower()
        if not clave:
            continue
        if clave in vistos:
            previo = vistos[clave]
            previo.numero = previo.numero or r.numero
            previo.fecha = previo.fecha or r.fecha
            previo.codigo_motivo = previo.codigo_motivo or r.codigo_motivo
            previo.motivo = previo.motivo or r.motivo
        else:
            vistos[clave] = r
    return list(vistos.values())


# ─────────────────────────────────── la entrada ────────────────────────────────

def parsear_texto(texto: str | bytes) -> Documento:
    """Lee un XML ya en memoria. Lanza `XmlInvalido` si no se puede."""
    if isinstance(texto, bytes):
        texto = texto.decode("utf-8", errors="replace")
    # El BOM y los espacios delante hacen fallar el parser con un error que no
    # dice nada; se quitan antes de intentarlo.
    limpio = texto.lstrip("﻿ \t\r\n")
    try:
        raiz = ET.fromstring(limpio)
    except ET.ParseError as exc:
        raise XmlInvalido(f"No es un XML válido: {exc}") from exc

    raiz = _desenvolver(raiz)
    tipo = _RAIZ_A_TIPO.get(_sin_ns(raiz.tag), TIPO_DESCONOCIDO)

    subtotal = _dec(_txt(raiz, "cac:LegalMonetaryTotal/cbc:LineExtensionAmount"))
    total = (_dec(_txt(raiz, "cac:LegalMonetaryTotal/cbc:PayableAmount"))
             or _dec(_txt(raiz, "cac:LegalMonetaryTotal/cbc:TaxInclusiveAmount")))
    impuestos = _todos_los_impuestos(raiz)
    suma_impuestos = sum((i.valor for i in impuestos if i.valor is not None
                          and not i.es_retencion), Decimal("0"))

    nit_e, nombre_e, resp_e = _parte(raiz, "AccountingSupplierParty")
    nit_r, nombre_r, _resp_r = _parte(raiz, "AccountingCustomerParty")

    return Documento(
        tipo=tipo,
        cufe=_txt(raiz, "cbc:UUID"),
        numero=_txt(raiz, "cbc:ID"),
        fecha_emision=_txt(raiz, "cbc:IssueDate"),
        hora_emision=_txt(raiz, "cbc:IssueTime"),
        moneda=_txt(raiz, "cbc:DocumentCurrencyCode"),
        emisor_nit=nit_e, emisor_nombre=nombre_e,
        emisor_responsabilidades=resp_e,
        receptor_nit=nit_r, receptor_nombre=nombre_r,
        subtotal=subtotal,
        total_impuestos=suma_impuestos if impuestos else None,
        total=total,
        lineas=_lineas_de(raiz),
        impuestos=impuestos,
        referencias=_referencias(raiz),
    )


def leer(ruta: str | Path) -> Lectura:
    """Lee un archivo del disco. Nunca lanza: devuelve el motivo en `estado`.

    Un fallo técnico no puede llegar a la pantalla disfrazado de «este documento
    no tiene datos» (D-080): cada estado dice qué pasó.
    """
    ruta = Path(ruta)
    try:
        crudo = ruta.read_bytes()
    except OSError as exc:
        return Lectura(None, ESTADO_ERROR, f"No se pudo abrir el archivo: {exc}")

    try:
        doc = parsear_texto(crudo)
    except XmlInvalido as exc:
        return Lectura(None, ESTADO_NO_ES_XML, str(exc))
    except Exception as exc:                       # el XML existe pero nos superó
        return Lectura(None, ESTADO_ERROR, f"{exc.__class__.__name__}: {exc}")

    if doc.tipo == TIPO_DESCONOCIDO and not doc.cufe:
        return Lectura(None, ESTADO_SIN_DOCUMENTO,
                       "El XML no es una factura, nota crédito ni nota débito.")
    return Lectura(doc, ESTADO_OK)


_RE_CUFE = re.compile(r"^[0-9a-f]{40,128}$", re.I)


def cufe_del_nombre(ruta: str | Path) -> str | None:
    """El portal nombra cada archivo con su CUFE; sirve para emparejar sin abrir."""
    tallo = Path(ruta).stem.strip().lower()
    return tallo if _RE_CUFE.match(tallo) else None
