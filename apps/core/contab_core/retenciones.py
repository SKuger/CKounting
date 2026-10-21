"""Qué retenciones corresponden a un documento — tarea 4.2.

Combina tres cosas: el **perfil fiscal de la empresa** (1.1), lo que se sepa del
**tercero** (1.3/1.4 y lo que declare la propia factura) y el **documento** de la
Fase 3.

## De dónde sale lo que se sabe del tercero, y en qué orden

Se le preguntó al contador qué hace cuando no tiene el RUT de un proveedor:

> «Verifico la información en la factura para determinar si le practico o no la
> retención.»

Así que ese es el orden, y no otro:

1. **El catálogo de terceros**, si alguien lo llenó a mano — es lo más
   deliberado que hay.
2. **Lo que la propia factura declara** (`cbc:TaxLevelCode` del anexo DIAN), que
   es exactamente lo que él mira.
3. **Nada**: y entonces no se inventa. Se propone la retención ordinaria y se
   **marca la fila** para que la revise, en vez de decidir en silencio.

Ese tercer caso es el que hace que esto sirva desde el primer día con 21 de 25
terceros en blanco. Si exigiera el catálogo lleno, la Fase 4 no serviría hasta
que él terminara un trabajo manual de meses.

## ReteIVA

Las cinco empresas son agentes de ReteIVA **únicamente frente a proveedores del
régimen simple** — confirmado por el contador el 2026-10-21. No es un booleano
suelto: `agente_reteiva` del perfil solo entra en juego si el tercero es del
régimen simple (`O-47`).

## Los importes

`Decimal` de principio a fin (D-075). Una retención calculada en binario deja
céntimos que no cuadran con la que el cliente ya practicó.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from . import tarifas as tarifas_module

# Códigos del RUT que cambian el cálculo.
GRAN_CONTRIBUYENTE = "O-13"
AUTORRETENEDOR = "O-15"
AGENTE_RETEIVA = "O-23"
REGIMEN_SIMPLE = "O-47"

# De dónde se supo lo del tercero. Va en el resultado para que la pantalla pueda
# decir «esto lo dice la factura» y no parezca que Contab se lo inventó.
ORIGEN_CATALOGO = "catalogo"
ORIGEN_FACTURA = "factura"
ORIGEN_SIN_DATOS = "sin_datos"

CERO = Decimal("0")


@dataclass
class Retencion:
    tipo: str                 # 'retefuente' | 'reteiva'
    concepto: str
    base: Decimal
    tarifa: Decimal
    valor: Decimal
    cuenta_puc: str | None
    concepto_id: int | None = None

    def como_dict(self) -> dict[str, Any]:
        return {
            "tipo": self.tipo, "concepto": self.concepto, "base": str(self.base),
            "tarifa": str(self.tarifa), "valor": str(self.valor),
            "cuenta_puc": self.cuenta_puc, "concepto_id": self.concepto_id,
        }


@dataclass
class Calculo:
    retenciones: list[Retencion] = field(default_factory=list)
    origen_tercero: str = ORIGEN_SIN_DATOS
    responsabilidades: list[str] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)
    revisar: bool = False      # el contador tiene que mirar esta fila

    @property
    def total(self) -> Decimal:
        return sum((r.valor for r in self.retenciones), CERO)

    def como_dict(self) -> dict[str, Any]:
        return {
            "retenciones": [r.como_dict() for r in self.retenciones],
            "total": str(self.total),
            "origen_tercero": self.origen_tercero,
            "responsabilidades": self.responsabilidades,
            "avisos": self.avisos,
            "revisar": self.revisar,
        }


def _dec(v: Any) -> Decimal:
    if v in (None, ""):
        return CERO
    if isinstance(v, Decimal):
        return v
    return Decimal(str(v))


def _pesos(v: Decimal) -> Decimal:
    """Redondeo contable al peso: la DIAN no liquida céntimos."""
    return v.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _tiene(codigos: list[str], codigo: str) -> bool:
    return any(c.strip().upper() == codigo for c in codigos)


def datos_del_tercero(
    tercero: dict[str, Any] | None,
    documento: dict[str, Any] | None,
) -> tuple[list[str], str]:
    """(responsabilidades, de dónde salieron). Catálogo primero, factura después."""
    if tercero:
        crudas = tercero.get("responsabilidades") or []
        if isinstance(crudas, str):
            crudas = [x for x in crudas.replace(";", ",").split(",") if x.strip()]
        if crudas:
            return [str(c).strip().upper() for c in crudas], ORIGEN_CATALOGO
    if documento:
        de_factura = documento.get("emisor_responsabilidades") or []
        if isinstance(de_factura, str):
            de_factura = [x for x in de_factura.replace(";", ",").split(",") if x.strip()]
        if de_factura:
            return [str(c).strip().upper() for c in de_factura], ORIGEN_FACTURA
    return [], ORIGEN_SIN_DATOS


def _aplica_a(concepto: dict[str, Any], declarante: bool) -> bool:
    a = (concepto.get("aplica_a") or "").strip().lower()
    if a in ("", "ambos"):
        return True
    if a == "declarantes":
        return declarante
    if a == "no_declarantes":
        return not declarante
    return True       # una frase que no sabemos leer no excluye el concepto


def calcular(
    conn,
    *,
    perfil: dict[str, Any] | None,
    documento: dict[str, Any] | None,
    tercero: dict[str, Any] | None = None,
    concepto_id: int | None = None,
    anio: int | None = None,
) -> Calculo:
    """Las retenciones que corresponden a este documento.

    `concepto_id` es el concepto de retención que el contador eligió (o que una
    regla propuso). Sin él no se puede calcular retefuente: el concepto define la
    tarifa, y adivinarlo desde la descripción de la factura es la tarea 4.3, no
    esta.
    """
    res = Calculo()
    if documento is None:
        res.avisos.append("Sin el XML del documento no se puede calcular la retención.")
        res.revisar = True
        return res
    if perfil is None:
        # Sin perfil no se inventa uno por defecto: una retención calculada sobre
        # un supuesto hace más daño que una no calculada.
        res.avisos.append(
            "Esta empresa no tiene perfil fiscal configurado; no se calcula nada.")
        res.revisar = True
        return res

    res.responsabilidades, res.origen_tercero = datos_del_tercero(tercero, documento)
    if res.origen_tercero == ORIGEN_SIN_DATOS:
        res.revisar = True
        res.avisos.append(
            "No se sabe si este proveedor es gran contribuyente o autorretenedor: "
            "ni está en el catálogo ni la factura lo declara. Se propone la "
            "retención ordinaria — conviene mirarla.")
    elif res.origen_tercero == ORIGEN_FACTURA:
        res.avisos.append("Las responsabilidades del proveedor las declara la factura.")

    base = _dec(documento.get("subtotal"))
    anio = anio or int(str(documento.get("fecha_emision") or "0000")[:4] or 0)

    # ── Retención en la fuente ──
    if not perfil.get("agente_retefuente"):
        res.avisos.append("La empresa no es agente de retención en la fuente.")
    elif _tiene(res.responsabilidades, AUTORRETENEDOR):
        res.avisos.append(
            "No se retiene renta: el proveedor es autorretenedor (O-15).")
    elif concepto_id is None:
        res.revisar = True
        res.avisos.append("Falta decir qué concepto de retención aplica.")
    else:
        fila = conn.execute(
            "SELECT * FROM retencion_concepto WHERE id = ?", (int(concepto_id),)
        ).fetchone()
        if fila is None:
            res.avisos.append(f"El concepto {concepto_id} ya no existe.")
            res.revisar = True
        else:
            concepto = dict(fila)
            declarante = _tiene(res.responsabilidades, GRAN_CONTRIBUYENTE)
            if not _aplica_a(concepto, declarante):
                res.avisos.append(
                    f"«{concepto['concepto']}» no aplica a este tercero "
                    f"({concepto['aplica_a']}).")
            elif concepto.get("tarifa") in (None, ""):
                res.revisar = True
                res.avisos.append(
                    f"«{concepto['concepto']}» no tiene tarifa numérica"
                    f" ({concepto.get('tarifa_texto') or '—'}): hay que resolverla a mano.")
            else:
                minima = tarifas_module.base_minima_pesos(conn, concepto, anio) if anio else None
                if minima is not None and base < minima:
                    res.avisos.append(
                        f"No llega a la base mínima de «{concepto['concepto']}»: "
                        f"{base} < {minima}.")
                else:
                    tarifa = _dec(concepto["tarifa"])
                    res.retenciones.append(Retencion(
                        tipo="retefuente", concepto=concepto["concepto"],
                        base=base, tarifa=tarifa,
                        valor=_pesos(base * tarifa / Decimal("100")),
                        cuenta_puc=concepto.get("cuenta_puc"),
                        concepto_id=concepto["id"]))

    # ── ReteIVA: solo frente a proveedores del régimen simple ──
    iva = _dec(documento.get("total_impuestos"))
    if perfil.get("agente_reteiva") and iva > CERO:
        if _tiene(res.responsabilidades, REGIMEN_SIMPLE):
            concepto = _concepto_reteiva(conn)
            tarifa = _dec(concepto.get("tarifa")) if concepto else Decimal("15")
            res.retenciones.append(Retencion(
                tipo="reteiva",
                concepto=(concepto or {}).get("concepto") or "ReteIVA",
                base=iva, tarifa=tarifa,
                valor=_pesos(iva * tarifa / Decimal("100")),
                cuenta_puc=(concepto or {}).get("cuenta_puc"),
                concepto_id=(concepto or {}).get("id")))
            if concepto is None or concepto.get("tarifa") in (None, ""):
                res.avisos.append(
                    "La tarifa de ReteIVA no está como número en las tarifas; "
                    "se usó el 15% del IVA que declaró el contador.")
        elif res.origen_tercero == ORIGEN_SIN_DATOS:
            res.avisos.append(
                "No se practicó ReteIVA porque no consta que el proveedor sea del "
                "régimen simple — y es justo lo que no se sabe de este tercero.")
    return res


def _concepto_reteiva(conn) -> dict[str, Any] | None:
    fila = conn.execute(
        "SELECT * FROM retencion_concepto WHERE sobre = ? AND archivado = 0"
        " ORDER BY id LIMIT 1", (tarifas_module.SOBRE_IVA,)).fetchone()
    return dict(fila) if fila else None
