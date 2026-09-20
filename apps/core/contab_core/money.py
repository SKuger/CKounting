"""Importes en Decimal con redondeo contable (D-075).

Por qué no `float`: el problema medido NO es la deriva acumulada — a la escala de
este aplicativo, sumar miles de facturas en float64 no produce diferencia visible.
Los problemas reales son dos:

1. **Redondeo a centavos.** `round(2.675, 2)` da 2.67 porque 2.675 no existe en
   binario. En pesos eso es un centavo mal, cada vez, en la dirección que decida
   la representación binaria. `Decimal.quantize(..., ROUND_HALF_UP)` da 2.68, que
   es lo que espera un contador (y la DIAN).
2. **Falta de cuantización.** `Base IVA = IVA / 0.19` es periódico: hoy se guarda
   y se EXPORTA como 40463.15789473684, con 14 decimales de ruido en la columna
   que recibe el contador. Con Decimal se cuantiza a centavos en el origen.

Además deja el terreno listo para comparar importes por igualdad exacta, que con
float nunca es seguro.

Convenciones:
- Todo importe vive como `Decimal` cuantizado a 2 decimales (centavos).
- `ROUND_HALF_UP` (medio hacia arriba), la convención contable — NO el
  `ROUND_HALF_EVEN` que Python usa por defecto.
- La conversión a `float` ocurre solo en los BORDES: JSON hacia la UI y celdas de
  xlsxwriter. La aritmética nunca pasa por float.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

CENTAVO = Decimal("0.01")
ZERO = Decimal("0.00")


def quantize(value: Decimal) -> Decimal:
    """Redondea a centavos con la convención contable (medio hacia arriba)."""
    return value.quantize(CENTAVO, rounding=ROUND_HALF_UP)


def to_money(value: Any) -> Decimal:
    """Convierte a Decimal cuantizado. Lanza ValueError si no es un importe.

    `float` se pasa por `repr()` a propósito: `Decimal(0.1)` daría
    0.1000000000000000055511151231257827021181583404541015625, mientras que
    `Decimal(repr(0.1))` da exactamente Decimal('0.1'). Esto importa al leer
    `data_json` de cargas viejas, donde los importes quedaron como números JSON.
    """
    if isinstance(value, Decimal):
        return quantize(value)
    if isinstance(value, bool):
        raise ValueError(f"valor booleano en columna de importe: {value!r}")
    if isinstance(value, int):
        return quantize(Decimal(value))
    if isinstance(value, float):
        return quantize(Decimal(repr(value)))
    try:
        return quantize(Decimal(str(value).strip()))
    except (InvalidOperation, ValueError, ArithmeticError):
        raise ValueError(f"no es un importe: {value!r}") from None


def is_money(value: Any) -> bool:
    return isinstance(value, Decimal)


def to_json(value: Any) -> Any:
    """Borde de salida: Decimal → float para que la UI reciba un número JSON.

    Los valores están cuantizados a 2 decimales, así que el double más cercano los
    representa sin pérdida perceptible para mostrar y ordenar en la tabla.
    """
    if isinstance(value, Decimal):
        return float(value)
    return value


def a_centavos(value: Decimal | None) -> int | None:
    """Decimal → entero de centavos, para guardarlo en una columna INTEGER.

    Es la forma de tener importes **sumables en SQL sin perder exactitud**: un
    REAL reintroduciría el binario que evitamos, y un TEXT no suma (D-091)."""
    if value is None:
        return None
    return int(quantize(value) * 100)


def de_centavos(value: int | None) -> Decimal | None:
    """Entero de centavos → Decimal. Exacto en los dos sentidos."""
    if value is None:
        return None
    return quantize(Decimal(value) / 100)


def row_to_json(row: dict[str, Any]) -> dict[str, Any]:
    """Aplica `to_json` a todos los importes de una fila."""
    return {k: to_json(v) for k, v in row.items()}


def rows_to_json(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row_to_json(r) for r in rows]
