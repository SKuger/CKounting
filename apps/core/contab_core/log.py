"""Registro del sidecar (D-083).

Por qué existe: había una docena de `except Exception: pass` repartidos por el
código. Cada uno estaba justificado por separado ("esto es best-effort, no debe
tumbar la operación"), pero sumados significaban que cuando algo fallaba de forma
rara **no quedaba rastro en ningún sitio** y era imposible diagnosticarlo.

La política no cambia — esas operaciones siguen sin tumbar nada — pero ahora
dejan una línea en el log. `warn()` para lo esperable, `exception()` para lo que
no debería pasar.

Salida: stderr. El shell de Electron ya lo recoge (`nitro.js` lo vuelca a
electron-log), así que el log del usuario acaba en `%APPDATA%/Contab/logs/`.
"""
from __future__ import annotations

import logging
import os
import sys

_LOGGER_NAME = "contab"
_configured = False


def _logger() -> logging.Logger:
    global _configured
    lg = logging.getLogger(_LOGGER_NAME)
    if not _configured:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("[contab %(levelname)s] %(message)s"))
        lg.addHandler(handler)
        lg.setLevel(os.environ.get("CONTAB_LOG_LEVEL", "INFO").upper())
        lg.propagate = False
        _configured = True
    return lg


def info(msg: str, *args) -> None:
    _logger().info(msg, *args)


def warn(msg: str, *args) -> None:
    _logger().warning(msg, *args)


def error(msg: str, *args) -> None:
    _logger().error(msg, *args)


def exception(msg: str, *args) -> None:
    """Como `error`, pero adjunta la traza de la excepción en curso."""
    _logger().exception(msg, *args)
