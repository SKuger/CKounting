"""Dónde vive en el disco cada cosa de una empresa.

La forma la fijó el usuario: **una carpeta por empresa, dentro una por mes, y
dentro de cada mes el Excel y una carpeta `soportes`**.

    <carpeta de la empresa>/
        2026-09/
            listado-septiembre.xlsx
            soportes/
                <cufe>.pdf
                …
        2026-10/
            …

El mes se nombra con el periodo tal cual —`AAAA-MM`— y no «Septiembre 2026»,
porque así se ordena solo en cualquier explorador de archivos y coincide con lo
que la app muestra.

Antes de esto cada mes podía apuntar a cualquier carpeta suelta, los Excel caían
en `<raíz>/imports` y lo que Contab bajaba del portal iba a una carpeta interna
que el contador no veía. Funcionaba, pero la contabilidad de un cliente quedaba
repartida en tres sitios que solo la base de datos sabía unir.
"""
from __future__ import annotations

import csv
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import storage as storage_module
from .log import warn

NOMBRE_SOPORTES = "soportes"
MANIFIESTO = "_contab_movimientos.csv"


def carpeta_mes(raiz: str | Path, periodo: str) -> Path:
    return Path(raiz) / storage_module._norm_periodo(periodo)


def carpeta_soportes(raiz: str | Path, periodo: str) -> Path:
    return carpeta_mes(raiz, periodo) / NOMBRE_SOPORTES


def preparar_mes(raiz: str | Path, periodo: str) -> dict[str, str]:
    """Crea `<raíz>/<mes>/soportes` y devuelve las dos rutas. Idempotente."""
    mes = carpeta_mes(raiz, periodo)
    soportes = mes / NOMBRE_SOPORTES
    soportes.mkdir(parents=True, exist_ok=True)
    return {"mes": str(mes), "soportes": str(soportes)}


# ───────────────────────── mudanza de lo que ya existía ─────────────────────────

@dataclass
class Movimiento:
    periodo: str
    origen: str
    destino: str
    motivo: str          # 'soporte' | 'excel'
    hecho: bool = False
    error: str | None = None

    def como_dict(self) -> dict[str, Any]:
        return {
            "periodo": self.periodo, "origen": self.origen, "destino": self.destino,
            "motivo": self.motivo, "hecho": self.hecho, "error": self.error,
        }


@dataclass
class Mudanza:
    raiz: str
    movimientos: list[Movimiento] = field(default_factory=list)
    manifiesto: str | None = None

    def como_dict(self) -> dict[str, Any]:
        return {
            "raiz": self.raiz,
            "movimientos": [m.como_dict() for m in self.movimientos],
            "total": len(self.movimientos),
            "movidos": sum(1 for m in self.movimientos if m.hecho),
            "fallidos": sum(1 for m in self.movimientos if m.error),
            "manifiesto": self.manifiesto,
        }


def _destino_libre(destino: Path) -> Path:
    """Nunca se pisa un archivo que ya estaba: se le añade un sufijo."""
    if not destino.exists():
        return destino
    for n in range(1, 1000):
        alterno = destino.with_name(f"{destino.stem}_{n}{destino.suffix}")
        if not alterno.exists():
            return alterno
    raise RuntimeError(f"No hay nombre libre para {destino}")


def planear_mudanza(db_path: str | Path, raiz: str | Path) -> Mudanza:
    """Qué habría que mover para que la empresa quede con la forma nueva.

    No toca nada: devolver el plan antes de ejecutarlo es la diferencia entre
    reorganizar y perder documentos ajenos.
    """
    raiz = Path(raiz)
    plan = Mudanza(raiz=str(raiz))
    carpetas = storage_module.periodo_folders(db_path)

    for periodo, origen in sorted(carpetas.items()):
        if not origen:
            continue
        actual = Path(origen)
        destino_soportes = carpeta_soportes(raiz, periodo)
        if actual.resolve() == destino_soportes.resolve():
            continue                      # ya está en su sitio
        if not actual.is_dir():
            # La ruta vieja ya no existe —un disco que se fue, un escritorio que
            # se rehízo—. No hay nada que mover; el mes se re-apunta y basta.
            continue
        for archivo in sorted(actual.iterdir()):
            if not archivo.is_file() or archivo.name == MANIFIESTO:
                continue
            es_excel = archivo.suffix.lower() in (".xlsx", ".xls", ".xlsm")
            destino = (carpeta_mes(raiz, periodo) if es_excel else destino_soportes) / archivo.name
            plan.movimientos.append(Movimiento(
                periodo=periodo, origen=str(archivo), destino=str(destino),
                motivo="excel" if es_excel else "soporte",
            ))
    return plan


def mudar(db_path: str | Path, raiz: str | Path, *, dry_run: bool = True) -> dict[str, Any]:
    """Mueve los archivos a la forma nueva y re-apunta cada mes.

    Deja un manifiesto en la raíz con cada movimiento: son documentos de un
    cliente, y una reorganización que no se puede deshacer no es una ayuda.
    """
    raiz = Path(raiz)
    plan = planear_mudanza(db_path, raiz)
    if dry_run:
        return plan.como_dict()

    raiz.mkdir(parents=True, exist_ok=True)
    for mov in plan.movimientos:
        try:
            destino = _destino_libre(Path(mov.destino))
            destino.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(mov.origen, str(destino))
            mov.destino = str(destino)
            mov.hecho = True
        except Exception as exc:          # noqa: BLE001
            mov.error = f"{exc.__class__.__name__}: {exc}"
            warn(f"mudanza: no se pudo mover {mov.origen}: {mov.error}")

    # Cada mes conocido pasa a apuntar a su carpeta `soportes`, exista o no la
    # vieja: los meses con ruta rota se arreglan aquí sin pedir nada.
    for periodo in storage_module.periodo_folders(db_path):
        rutas = preparar_mes(raiz, periodo)
        storage_module.set_periodo_folder(db_path, periodo, rutas["soportes"])

    if plan.movimientos:
        destino_manifiesto = raiz / MANIFIESTO
        nuevo = not destino_manifiesto.exists()
        try:
            with destino_manifiesto.open("a", newline="", encoding="utf-8-sig") as fh:
                escritor = csv.writer(fh)
                if nuevo:
                    escritor.writerow(["cuando", "periodo", "motivo", "origen", "destino", "error"])
                cuando = datetime.now(timezone.utc).isoformat(timespec="seconds")
                for mov in plan.movimientos:
                    escritor.writerow([cuando, mov.periodo, mov.motivo,
                                       mov.origen, mov.destino, mov.error or ""])
            plan.manifiesto = str(destino_manifiesto)
        except Exception as exc:          # noqa: BLE001
            warn(f"mudanza: no se pudo escribir el manifiesto: {exc}")
    return plan.como_dict()
