"""A qué cuenta va cada factura, y cómo se aprende — tarea 4.3.

Las dos formas de regla salen de dos respuestas del contador el 2026-10-20:

> «¿Qué mira para decidir la cuenta del PUC?» → **«LA FACTURA»**
>
> «¿Hay proveedores a los que SIEMPRE les causa en la misma cuenta, pase lo que
> pase?» → Telesentinel, Todo en Artes, Ultragas.

Así que hay **reglas por proveedor** y **reglas por lo que dice la factura**.

El 2026-10-22 lo precisó, y corrige lo que se había entendido antes:

> «Como por lo general el concepto que factura el proveedor es el mismo, las
> siguientes facturas se registrarían de esa forma. Pero si en otra factura el
> concepto cambia, me presentas la nueva propuesta y le doy el visto bueno.»

Es decir: lo aprendido de un proveedor vale **mientras el concepto sea el
mismo**. Si ese proveedor factura otra cosa, no se da por buena la cuenta de
siempre — se vuelve a preguntar. Solo las reglas **sin patrón** son el «pase lo
que pase», y ésas se escriben a propósito para los pocos proveedores que lo
merecen.

## Lo que hace que el segundo mes sea barato

Cada decisión que el contador toma en la bandeja (4.5) **escribe o afina una
regla**. Sin esa vuelta atrás, él vuelve a decidir el mismo proveedor cada mes y
el producto es una hoja de cálculo más bonita.

**Sin centro de costo** (D-112): respondió que no los usa.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

# Cuánto «vale» cada forma de regla. La del proveedor gana a la del texto, y una
# que acierte las dos cosas gana a las dos.
PESO_TERCERO = 2
PESO_PATRON = 1

ORIGEN_MANUAL = "manual"
ORIGEN_APRENDIDA = "aprendida"


@dataclass
class Propuesta:
    cuenta_puc: str | None = None
    concepto_retencion_id: int | None = None
    regla_id: int | None = None
    por_que: str = ""
    seguro: bool = False      # False → el contador tiene que decidirlo
    # True cuando del proveedor se sabe, pero factura algo distinto a lo de
    # siempre. No es lo mismo que un proveedor nuevo, y la bandeja lo dice
    # distinto: «factura algo distinto a lo de siempre».
    concepto_nuevo: bool = False
    # El contador dijo que a esto NO se le retiene. Distinto de «no lo ha dicho».
    sin_retencion: bool = False

    def como_dict(self) -> dict[str, Any]:
        return {
            "cuenta_puc": self.cuenta_puc,
            "concepto_retencion_id": self.concepto_retencion_id,
            "regla_id": self.regla_id, "por_que": self.por_que, "seguro": self.seguro,
            "concepto_nuevo": self.concepto_nuevo,
            "sin_retencion": self.sin_retencion,
        }


def _plano(texto: str | None) -> str:
    """Sin tildes, sin mayúsculas y sin dobles espacios, para poder comparar.

    «Vigilancia» y «VIGILANCIA» son el mismo concepto, y una factura escrita sin
    tildes no puede dejar de casar con una regla escrita con ellas.
    """
    if not texto:
        return ""
    sin = unicodedata.normalize("NFKD", str(texto))
    sin = "".join(c for c in sin if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sin).strip().lower()


def texto_del_documento(documento: dict[str, Any]) -> str:
    """Todo lo que la factura dice y sirve para reconocerla."""
    partes = [documento.get("tercero_nombre") or documento.get("emisor_nombre") or ""]
    for ln in documento.get("lineas") or []:
        partes.append(ln.get("descripcion") or "")
    return _plano(" · ".join(p for p in partes if p))


def proponer(conn, documento: dict[str, Any]) -> Propuesta:
    """La cuenta y el concepto que corresponden, según las reglas que haya.

    Si ninguna regla aplica no se inventa una cuenta: se devuelve vacío y
    `seguro=False`, que es lo que la bandeja usa para separar «apruebe en lote»
    de «decida usted».
    """
    nit = (documento.get("tercero_nit") or documento.get("emisor_nit") or "").strip()
    texto = texto_del_documento(documento)
    # Una regla de ingreso no es una regla de gasto: el mismo NIT puede ser
    # cliente y proveedor, y la cuenta de cada cosa es otra (D-127).
    naturaleza = documento.get("naturaleza") or "compra"
    quien = "cliente" if naturaleza == "venta" else "proveedor"

    mejor: dict[str, Any] | None = None
    mejor_peso = 0
    for fila in conn.execute(
        "SELECT * FROM regla_causacion WHERE archivada = 0 AND naturaleza = ?"
        " ORDER BY id", (naturaleza,)
    ).fetchall():
        regla = dict(fila)
        peso = 0
        if regla["tercero_nit"]:
            if regla["tercero_nit"].strip() != nit:
                continue
            peso += PESO_TERCERO
        if regla["patron"]:
            if _plano(regla["patron"]) not in texto:
                continue
            peso += PESO_PATRON
        if peso == 0:
            continue          # una regla sin tercero ni patrón no aplica a nada
        if peso > mejor_peso:
            mejor, mejor_peso = regla, peso

    if mejor is None:
        # ¿Es un proveedor nuevo, o uno conocido facturando otra cosa? No es lo
        # mismo, y el contador quiere que se le diga distinto.
        conocido = conn.execute(
            "SELECT patron FROM regla_causacion WHERE archivada = 0 AND naturaleza = ?"
            " AND tercero_nit = ? AND patron IS NOT NULL", (naturaleza, nit)).fetchall()
        if conocido:
            de_siempre = ", ".join(f"«{r[0]}»" for r in conocido[:3])
            return Propuesta(
                concepto_nuevo=True,
                por_que=(f"Este {quien} suele facturar {de_siempre}, y esta "
                         f"factura dice otra cosa."))
        return Propuesta(por_que="Ninguna regla aplica todavía a este documento.")

    if mejor["tercero_nit"] and mejor["patron"]:
        por_que = f"Regla para {mejor['tercero_nit']} cuando dice «{mejor['patron']}»."
    elif mejor["tercero_nit"]:
        por_que = f"Este {quien} siempre va a {mejor['cuenta_puc']}."
    else:
        por_que = f"La factura dice «{mejor['patron']}»."

    return Propuesta(
        cuenta_puc=mejor["cuenta_puc"],
        concepto_retencion_id=mejor["concepto_retencion_id"],
        sin_retencion=bool(mejor["sin_retencion"]),
        regla_id=mejor["id"], por_que=por_que, seguro=True,
    )


def aprender(
    conn,
    *,
    cuenta_puc: str,
    tercero_nit: str | None = None,
    patron: str | None = None,
    concepto_retencion_id: int | None = None,
    sin_retencion: bool = False,
    vigencia_desde: str | None = None,
    naturaleza: str = "compra",
) -> dict[str, Any]:
    """Guarda lo que el contador decidió, para no volvérselo a preguntar.

    Es la vuelta atrás que hace barato el segundo mes. Si ya existe una regla
    con la misma llave, **se afina** en vez de duplicarse.
    """
    if not cuenta_puc:
        raise ValueError("Una regla sin cuenta no sirve de nada.")
    if not tercero_nit and not patron:
        raise ValueError(
            "Una regla tiene que decir a qué proveedor o a qué texto se aplica; "
            "si no, se aplicaría a todo.")

    ya = conn.execute(
        "SELECT id FROM regla_causacion WHERE IFNULL(tercero_nit,'') = IFNULL(?,'')"
        " AND IFNULL(patron,'') = IFNULL(?,'')"
        " AND IFNULL(vigencia_desde,'') = IFNULL(?,'') AND naturaleza = ?",
        (tercero_nit, patron, vigencia_desde, naturaleza)).fetchone()
    if ya:
        conn.execute(
            "UPDATE regla_causacion SET cuenta_puc = ?, concepto_retencion_id = ?,"
            " sin_retencion = ?, archivada = 0, updated_at = datetime('now')"
            " WHERE id = ?",
            (cuenta_puc, concepto_retencion_id, 1 if sin_retencion else 0, ya[0]))
        rid = ya[0]
    else:
        cur = conn.execute(
            "INSERT INTO regla_causacion(tercero_nit, patron, cuenta_puc,"
            " concepto_retencion_id, sin_retencion, vigencia_desde, origen, naturaleza)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (tercero_nit, patron, cuenta_puc, concepto_retencion_id,
             1 if sin_retencion else 0, vigencia_desde, ORIGEN_APRENDIDA, naturaleza))
        rid = int(cur.lastrowid)
    conn.commit()
    return dict(conn.execute(
        "SELECT * FROM regla_causacion WHERE id = ?", (rid,)).fetchone())


def marcar_usada(conn, regla_id: int) -> None:
    """Cuántas veces sirvió. Una regla que nunca se usa sobra, y conviene verlo."""
    conn.execute(
        "UPDATE regla_causacion SET veces_usada = veces_usada + 1 WHERE id = ?",
        (int(regla_id),))


def listar(conn, *, incluir_archivadas: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM regla_causacion"
    if not incluir_archivadas:
        sql += " WHERE archivada = 0"
    sql += " ORDER BY naturaleza, tercero_nit IS NULL, tercero_nit, patron"
    return [dict(r) for r in conn.execute(sql)]


def guardar(conn, data: dict[str, Any]) -> dict[str, Any]:
    """Crear o editar una regla a mano."""
    rid = data.get("id")
    if not (data.get("tercero_nit") or data.get("patron")):
        raise ValueError(
            "Una regla tiene que decir a qué proveedor o a qué texto se aplica.")
    if not data.get("cuenta_puc"):
        raise ValueError("Una regla sin cuenta no sirve de nada.")
    valores = (
        (data.get("tercero_nit") or "").strip() or None,
        (data.get("patron") or "").strip() or None,
        str(data["cuenta_puc"]).strip(),
        int(data["concepto_retencion_id"]) if data.get("concepto_retencion_id") else None,
        (data.get("vigencia_desde") or "").strip() or None,
        (data.get("naturaleza") or "compra").strip().lower(),
    )
    if valores[-1] not in ("compra", "venta", "doc_soporte"):
        raise ValueError(f"Naturaleza desconocida: «{valores[-1]}».")
    if rid:
        conn.execute(
            "UPDATE regla_causacion SET tercero_nit = ?, patron = ?, cuenta_puc = ?,"
            " concepto_retencion_id = ?, vigencia_desde = ?, naturaleza = ?,"
            " updated_at = datetime('now') WHERE id = ?", (*valores, int(rid)))
    else:
        cur = conn.execute(
            "INSERT INTO regla_causacion(tercero_nit, patron, cuenta_puc,"
            " concepto_retencion_id, vigencia_desde, naturaleza, origen)"
            " VALUES (?,?,?,?,?,?, 'manual')", valores)
        rid = int(cur.lastrowid)
    conn.commit()
    return dict(conn.execute(
        "SELECT * FROM regla_causacion WHERE id = ?", (int(rid),)).fetchone())


def archivar(conn, regla_id: int, archivada: bool = True) -> None:
    conn.execute(
        "UPDATE regla_causacion SET archivada = ?, updated_at = datetime('now')"
        " WHERE id = ?", (1 if archivada else 0, int(regla_id)))
    conn.commit()
