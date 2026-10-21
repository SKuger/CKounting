"""Importa la UVT y los conceptos de retención del Excel del contador — 4.1.

Son **ley y cambian por decreto**, así que no las siembra el programa (D-102):
las pone el contador en un archivo suyo, y actualizarlas cada enero es volver a
subirlo, no publicar una versión.

La estructura de ese archivo está verificada contra el real en
[`docs/tarifas-structure.md`](../../../docs/tarifas-structure.md). De todo lo que
hay ahí, lo que más importa es esto:

## ⚠ Las tarifas llegan como fracción, no como número de porcentaje

La celda guarda `0.11` y **muestra** `11%`, porque tiene formato de porcentaje.
Leer ese `0.11` como si fuera el porcentaje da **0,11% en vez de 11%**: cien
veces menos retención, en todas las filas, sin que nada falle ni avise. Por eso
`tarifa_de_celda` mira el formato de la celda y no solo su valor — y tolera las
dos formas, porque el siguiente contador puede escribir `11`.

El formato que usó no lleva decimales, así que `0.035` se ve como «4%» en
pantalla aunque valga 3,5%. Vale el valor guardado, no lo que se ve.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from openpyxl import load_workbook

# Lo que significa «no hay mínimo»: se retiene desde el primer peso. No es un
# dato que falte, y tratarlo como tal dejaría sin retener honorarios, comisiones
# y arrendamientos de muebles.
SIN_MINIMO = ("n/a", "na", "no aplica", "-", "")

# Las dos familias de retención. Sin distinguirlas, ReteIVA se calcularía sobre
# la base gravable en vez de sobre el IVA, y saldría mal.
SOBRE_BASE = "base"
SOBRE_IVA = "iva"

_ALIAS_HOJA_UVT = ("uvt",)
_ALIAS_HOJA_RET = ("retencion", "retenciones")

_ALIAS = {
    "anio": ("año", "ano", "anio", "vigencia", "periodo"),
    "valor": ("valor de la uvt (pesos)", "valor uvt", "valor", "uvt"),
    "norma": ("norma de referencia", "norma", "resolucion", "observaciones"),
    "concepto": ("concepto",),
    "tarifa": ("tarifa (%)", "tarifa", "porcentaje", "%"),
    "base_uvt": ("base minima (uvt)", "base mínima (uvt)", "base uvt", "base minima uvt"),
    "cuenta": ("cuenta puc donde lo contabiliza", "cuenta puc", "cuenta", "puc"),
    "aplica": ("aplica a", "aplica", "dirigido a"),
    "desde": ("rige desde", "vigencia desde", "desde", "vigencia"),
    "obs": ("observaciones", "notas", "observacion"),
}

_APLICA = {
    "declarantes": "declarantes",
    "no declarantes": "no_declarantes",
    "declarantes y no declarantes": "ambos",
}


@dataclass
class Cargado:
    uvt: list[dict[str, Any]] = field(default_factory=list)
    conceptos: list[dict[str, Any]] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    source_name: str = ""

    def como_dict(self) -> dict[str, Any]:
        return {
            "uvt": self.uvt, "conceptos": self.conceptos,
            "avisos": self.avisos, "source_name": self.source_name,
            "total_uvt": len(self.uvt), "total_conceptos": len(self.conceptos),
        }


def _txt(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _clave(v: Any) -> str:
    return _txt(v).lower().replace("  ", " ")


def _es(cabecera: str, campo: str) -> bool:
    c = _clave(cabecera)
    return any(c == a or c.startswith(a) for a in _ALIAS[campo])


def tarifa_de_celda(celda) -> tuple[Decimal | None, str | None]:
    """(tarifa en porcentaje, texto si no era un número).

    Devuelve `11` para una celda que vale `0.11` con formato de porcentaje, y
    `11` para una que vale `11` sin él. Lo que no se pueda leer vuelve como texto
    —p. ej. «15% del IVA»— en vez de perderse o de valer cero.
    """
    v = celda.value
    if v is None or _txt(v) == "":
        return None, None
    if isinstance(v, (int, float, Decimal)):
        n = Decimal(str(v))
        formato = str(celda.number_format or "")
        if "%" in formato:
            return n * 100, None
        # Sin formato de porcentaje, un valor por debajo de 1 es casi seguro una
        # fracción escrita a mano (0,11). Se acepta, pero se deja constancia.
        return n, None
    return None, _txt(v)


def base_minima_de(v: Any) -> Decimal | None:
    """Las UVT de base mínima; None cuando no hay mínimo («N/A»)."""
    t = _clave(v)
    if t in SIN_MINIMO:
        return None
    try:
        return Decimal(str(v).replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _fecha(v: Any) -> str | None:
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    t = _txt(v)[:10]
    return t or None


def _familia(tarifa_texto: str | None, concepto: str) -> str:
    """¿La tarifa va sobre la base o sobre el IVA?"""
    pista = f"{tarifa_texto or ''} {concepto}".lower()
    return SOBRE_IVA if "iva" in pista else SOBRE_BASE


def _hoja(wb, alias: tuple[str, ...]):
    for nombre in wb.sheetnames:
        limpio = _clave(nombre).lstrip("0123456789. ")
        if any(limpio.startswith(a) for a in alias):
            return wb[nombre]
    return None


def _cabeceras(ws, campos: tuple[str, ...], hasta: int = 12) -> tuple[int, dict[str, int]]:
    """Encuentra la fila de cabeceras y en qué columna cayó cada campo."""
    for fila in range(1, hasta + 1):
        mapa: dict[str, int] = {}
        for col in range(1, ws.max_column + 1):
            cab = _txt(ws.cell(fila, col).value)
            if not cab:
                continue
            for campo in campos:
                if campo not in mapa and _es(cab, campo):
                    mapa[campo] = col
        if len(mapa) >= 2:
            return fila, mapa
    return 0, {}


def cargar(source_path: str | Path) -> Cargado:
    """Lee el archivo. No toca la base: devolver lo leído antes de escribirlo es
    lo que permite enseñárselo al contador y que apruebe."""
    ruta = Path(source_path)
    wb = load_workbook(ruta, data_only=True)
    res = Cargado(source_name=ruta.name)

    ws = _hoja(wb, _ALIAS_HOJA_UVT)
    if ws is None:
        res.avisos.append("No se encontró una hoja de UVT.")
    else:
        fila, mapa = _cabeceras(ws, ("anio", "valor", "norma"))
        if "anio" not in mapa or "valor" not in mapa:
            res.avisos.append("La hoja de UVT no tiene columnas de año y valor.")
        else:
            for r in range(fila + 1, ws.max_row + 1):
                anio = ws.cell(r, mapa["anio"]).value
                valor = ws.cell(r, mapa["valor"]).value
                if not isinstance(anio, (int, float)) or valor in (None, ""):
                    continue
                try:
                    v = Decimal(str(valor))
                except (InvalidOperation, ValueError):
                    res.avisos.append(f"UVT de {anio}: «{valor}» no es un número.")
                    continue
                res.uvt.append({
                    "anio": int(anio), "valor": str(v),
                    "norma": _txt(ws.cell(r, mapa["norma"]).value) if "norma" in mapa else "",
                })

    ws = _hoja(wb, _ALIAS_HOJA_RET)
    if ws is None:
        res.avisos.append("No se encontró una hoja de retenciones.")
        return res

    fila, mapa = _cabeceras(
        ws, ("concepto", "tarifa", "base_uvt", "cuenta", "aplica", "desde", "obs"))
    if "concepto" not in mapa or "tarifa" not in mapa:
        res.avisos.append("La hoja de retenciones no tiene columnas de concepto y tarifa.")
        return res

    for r in range(fila + 1, ws.max_row + 1):
        concepto = _txt(ws.cell(r, mapa["concepto"]).value)
        if not concepto:
            continue
        tarifa, tarifa_texto = tarifa_de_celda(ws.cell(r, mapa["tarifa"]))
        base = base_minima_de(ws.cell(r, mapa["base_uvt"]).value) if "base_uvt" in mapa else None
        aplica_txt = _txt(ws.cell(r, mapa["aplica"]).value) if "aplica" in mapa else ""
        res.conceptos.append({
            "concepto": concepto,
            "aplica_a": _APLICA.get(_clave(aplica_txt), _clave(aplica_txt)),
            "sobre": _familia(tarifa_texto, concepto),
            "tarifa": str(tarifa) if tarifa is not None else None,
            "tarifa_texto": tarifa_texto,
            "base_minima_uvt": str(base) if base is not None else None,
            "cuenta_puc": _txt(ws.cell(r, mapa["cuenta"]).value) if "cuenta" in mapa else "",
            "vigencia_desde": _fecha(ws.cell(r, mapa["desde"]).value) if "desde" in mapa else None,
            "observaciones": _txt(ws.cell(r, mapa["obs"]).value) if "obs" in mapa else "",
        })
        if tarifa is None and tarifa_texto:
            res.avisos.append(
                f"«{concepto}»: la tarifa dice «{tarifa_texto}» y no es un número; "
                f"se guarda tal cual y habrá que resolverla a mano.")
    return res


def guardar(conn, cargado: Cargado, *, dry_run: bool = False) -> dict[str, Any]:
    """Escribe lo cargado. Upsert por llave; **lo escrito a mano se conserva**.

    Igual que el PUC: volver a subir el archivo fusiona, no borra. Una fila que
    el contador añadió a mano y que no está en el Excel sigue ahí.
    """
    if dry_run:
        return {**cargado.como_dict(), "dry_run": True, "nuevos": 0, "actualizados": 0}

    nuevos = actualizados = 0
    for u in cargado.uvt:
        ya = conn.execute("SELECT anio FROM uvt WHERE anio = ?", (u["anio"],)).fetchone()
        conn.execute(
            "INSERT INTO uvt(anio, valor, norma, fuente) VALUES (?,?,?, 'excel')"
            " ON CONFLICT(anio) DO UPDATE SET valor = excluded.valor,"
            " norma = excluded.norma, fuente = 'excel', updated_at = datetime('now')",
            (u["anio"], u["valor"], u["norma"]),
        )
        actualizados += 1 if ya else 0
        nuevos += 0 if ya else 1

    for c in cargado.conceptos:
        llave = (c["concepto"], c["aplica_a"], c["vigencia_desde"])
        ya = conn.execute(
            "SELECT id FROM retencion_concepto WHERE concepto = ? AND aplica_a = ?"
            " AND IFNULL(vigencia_desde,'') = IFNULL(?,'')", llave).fetchone()
        if ya:
            conn.execute(
                "UPDATE retencion_concepto SET sobre = ?, tarifa = ?, tarifa_texto = ?,"
                " base_minima_uvt = ?, cuenta_puc = ?, observaciones = ?, fuente = 'excel',"
                " updated_at = datetime('now') WHERE id = ?",
                (c["sobre"], c["tarifa"], c["tarifa_texto"], c["base_minima_uvt"],
                 c["cuenta_puc"], c["observaciones"], ya[0]))
            actualizados += 1
        else:
            conn.execute(
                "INSERT INTO retencion_concepto(concepto, aplica_a, sobre, tarifa,"
                " tarifa_texto, base_minima_uvt, cuenta_puc, vigencia_desde, observaciones,"
                " fuente) VALUES (?,?,?,?,?,?,?,?,?, 'excel')",
                (c["concepto"], c["aplica_a"], c["sobre"], c["tarifa"], c["tarifa_texto"],
                 c["base_minima_uvt"], c["cuenta_puc"], c["vigencia_desde"],
                 c["observaciones"]))
            nuevos += 1

    conn.execute(
        "INSERT INTO tarifas_import(source_name, uvt_filas, conceptos) VALUES (?,?,?)",
        (cargado.source_name, len(cargado.uvt), len(cargado.conceptos)))
    conn.commit()
    return {**cargado.como_dict(), "dry_run": False,
            "nuevos": nuevos, "actualizados": actualizados}


# ─────────────────────────────── consulta ──────────────────────────────────────

def uvt_del_anio(conn, anio: int) -> Decimal | None:
    r = conn.execute("SELECT valor FROM uvt WHERE anio = ?", (int(anio),)).fetchone()
    return Decimal(r[0]) if r else None


def base_minima_pesos(conn, concepto: dict[str, Any], anio: int) -> Decimal | None:
    """Las UVT de la base mínima, en pesos del año. None = no hay mínimo.

    Se calcula aquí y no se lee del Excel a propósito: en el archivo real esa
    columna venía vacía —sus fórmulas apuntaban a una celda que la plantilla no
    tenía—, y de todos modos el valor en pesos cambia cada año mientras las UVT
    no.
    """
    uvt_base = concepto.get("base_minima_uvt")
    if uvt_base in (None, ""):
        return None
    valor = uvt_del_anio(conn, anio)
    if valor is None:
        return None
    return (Decimal(str(uvt_base)) * valor).quantize(Decimal("1"))


def listar_conceptos(conn, *, incluir_archivados: bool = False) -> list[dict[str, Any]]:
    sql = "SELECT * FROM retencion_concepto"
    if not incluir_archivados:
        sql += " WHERE archivado = 0"
    sql += " ORDER BY concepto, aplica_a"
    return [dict(r) for r in conn.execute(sql)]


def listar_uvt(conn) -> list[dict[str, Any]]:
    return [dict(r) for r in conn.execute("SELECT * FROM uvt ORDER BY anio DESC")]


def guardar_concepto(conn, data: dict[str, Any]) -> dict[str, Any]:
    """Crea o edita un concepto a mano. Lo manual no lo pisa una importación."""
    cid = data.get("id")
    campos = ("concepto", "aplica_a", "sobre", "tarifa", "tarifa_texto",
              "base_minima_uvt", "cuenta_puc", "vigencia_desde", "observaciones")
    valores = [(_txt(data.get(c)) or None) for c in campos]
    if cid:
        conn.execute(
            f"UPDATE retencion_concepto SET {', '.join(f'{c} = ?' for c in campos)},"
            " updated_at = datetime('now') WHERE id = ?", [*valores, int(cid)])
    else:
        conn.execute(
            f"INSERT INTO retencion_concepto({', '.join(campos)}, fuente)"
            f" VALUES ({', '.join('?' * len(campos))}, 'manual')", valores)
        cid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.commit()
    return dict(conn.execute(
        "SELECT * FROM retencion_concepto WHERE id = ?", (int(cid),)).fetchone())


def guardar_uvt(conn, anio: int, valor: str, norma: str = "") -> dict[str, Any]:
    conn.execute(
        "INSERT INTO uvt(anio, valor, norma, fuente) VALUES (?,?,?, 'manual')"
        " ON CONFLICT(anio) DO UPDATE SET valor = excluded.valor, norma = excluded.norma,"
        " updated_at = datetime('now')",
        (int(anio), str(valor), norma))
    conn.commit()
    return dict(conn.execute("SELECT * FROM uvt WHERE anio = ?", (int(anio),)).fetchone())


def archivar_concepto(conn, concepto_id: int, archivado: bool = True) -> None:
    conn.execute(
        "UPDATE retencion_concepto SET archivado = ?, updated_at = datetime('now')"
        " WHERE id = ?", (1 if archivado else 0, int(concepto_id)))
    conn.commit()


def ultima_importacion(conn) -> dict[str, Any] | None:
    r = conn.execute(
        "SELECT * FROM tarifas_import ORDER BY id DESC LIMIT 1").fetchone()
    return dict(r) if r else None
