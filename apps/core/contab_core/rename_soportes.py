"""Renombrado de soportes PDF según el cruce CUFE ↔ fila del Excel (D-066).

Patrón:  DD-MM_NIT_RAZON-SOCIAL_FACTURA.pdf
  - DD-MM   ← Fecha Emisión de la fila del Excel
  - NIT     ← NIT Emisor
  - RAZON   ← Nombre Emisor (saneado; espacios → '-')
  - FACTURA ← # de factura (Prefijo-Folio)

Renombra IN PLACE en la misma carpeta y deja un manifiesto `_renombrados.csv`
(nombre_nuevo, nombre_original, cufe, fecha_hora) para poder revertir/auditar.
Los PDFs sin CUFE, o cuyo CUFE no está en el Excel del mes, se dejan intactos
y se reportan. Es idempotente: un PDF que ya tiene el nombre destino se salta.
"""
from __future__ import annotations

import csv
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MANIFEST_NAME = "_renombrados.csv"
_RAZON_MAXLEN = 60


def _norm_cufe(x: Any) -> str:
    """Misma normalización que el indexado/V1: solo hex, minúsculas."""
    return re.sub(r"[^a-f0-9]", "", str(x or "").lower())


def _safe(s: Any, maxlen: int | None = None) -> str:
    text = str(s if s is not None else "").strip()
    text = re.sub(r'[\\/:*?"<>|]', "", text)   # caracteres ilegales en el sistema de archivos
    text = re.sub(r"\s+", "-", text)            # espacios → guiones
    text = re.sub(r"-{2,}", "-", text).strip("-._ ")
    if maxlen and len(text) > maxlen:
        text = text[:maxlen].strip("-._ ")
    return text


def _ddmm(fecha: Any) -> str:
    m = re.match(r"\s*(\d{4})-(\d{2})-(\d{2})", str(fecha or ""))
    return f"{m.group(3)}-{m.group(2)}" if m else ""


def _build_base_name(row: dict[str, Any], date_field: str) -> tuple[str, str | None]:
    """(base_name, motivo_si_incompleto)."""
    ddmm = _ddmm(row.get(date_field))
    nit = _safe(row.get("NIT Emisor"))
    razon = _safe(row.get("Nombre Emisor"), _RAZON_MAXLEN)
    factura = _safe(row.get("# de factura"))
    missing = [name for name, v in (("fecha", ddmm), ("NIT", nit), ("factura", factura)) if not v]
    if missing:
        return "", "Datos incompletos en el Excel: falta " + ", ".join(missing)
    parts = [ddmm, nit]
    if razon:
        parts.append(razon)
    parts.append(factura)
    return "_".join(parts), None


def build_plan(
    rows: list[dict[str, Any]],
    pdfs: list[dict[str, Any]],
    folder: str | Path,
    *,
    date_field: str = "Fecha Emisión",
) -> list[dict[str, Any]]:
    """Plan de renombrado (sin tocar disco). Un item por PDF existente."""
    folder_path = Path(folder)

    by_cufe: dict[str, dict[str, Any]] = {}
    for r in rows:
        key = _norm_cufe(r.get("CUFE/CUDE"))
        if key and key not in by_cufe:
            by_cufe[key] = r

    existing: set[str] = set()
    try:
        for p in folder_path.iterdir():
            if p.is_file():
                existing.add(p.name.lower())
    except Exception:
        pass

    assigned: set[str] = set()
    plan: list[dict[str, Any]] = []
    for pdf in sorted(pdfs, key=lambda x: str(x.get("pdf_path", ""))):
        path = pdf.get("pdf_path", "")
        if not path or not Path(path).is_file():
            continue  # entradas huérfanas del índice (archivo ya renombrado/borrado)
        current = Path(path).name
        cufes = [c.get("value") for c in (pdf.get("cufes") or [])]

        matched_row = matched_cufe = None
        for cv in cufes:
            k = _norm_cufe(cv)
            if k in by_cufe:
                matched_row, matched_cufe = by_cufe[k], k
                break

        if matched_row is None:
            reason = ("El PDF no tiene CUFE extraído" if not cufes
                      else "El CUFE del PDF no está en el Excel de este mes")
            plan.append({"path": path, "current_name": current, "new_name": None,
                         "matched": False, "status": "nomatch", "reason": reason, "cufe": None})
            continue

        base, incomplete = _build_base_name(matched_row, date_field)
        if incomplete:
            plan.append({"path": path, "current_name": current, "new_name": None,
                         "matched": True, "status": "skip", "reason": incomplete, "cufe": matched_cufe})
            continue

        candidate = f"{base}.pdf"
        n = 2
        while candidate.lower() in assigned or (
            candidate.lower() in existing and candidate.lower() != current.lower()
        ):
            candidate = f"{base}_{n}.pdf"
            n += 1
        assigned.add(candidate.lower())

        status = "already" if candidate.lower() == current.lower() else "rename"
        plan.append({"path": path, "current_name": current, "new_name": candidate,
                     "matched": True, "status": status, "reason": None, "cufe": matched_cufe})
    return plan


def _counts(plan: list[dict[str, Any]]) -> dict[str, int]:
    c = {"total": len(plan), "rename": 0, "already": 0, "nomatch": 0, "skip": 0, "renamed": 0, "error": 0}
    for it in plan:
        c[it["status"]] = c.get(it["status"], 0) + 1
    return c


def rename_soportes(
    rows: list[dict[str, Any]],
    pdfs: list[dict[str, Any]],
    folder: str | Path,
    *,
    date_field: str = "Fecha Emisión",
    dry_run: bool = True,
) -> dict[str, Any]:
    folder_path = Path(folder)
    plan = build_plan(rows, pdfs, folder_path, date_field=date_field)
    result: dict[str, Any] = {
        "folder": str(folder_path), "date_field": date_field,
        "dry_run": dry_run, "items": plan, "manifest": None,
    }
    if dry_run:
        result["counts"] = _counts(plan)
        return result

    applied: list[dict[str, Any]] = []
    for it in plan:
        if it["status"] != "rename":
            continue
        src = folder_path / it["current_name"]
        dst = folder_path / it["new_name"]
        try:
            if not src.exists():
                it["status"], it["reason"] = "error", "El archivo ya no existe"
            elif dst.exists():
                it["status"], it["reason"] = "error", "Ya existe un archivo con ese nombre destino"
            else:
                src.rename(dst)
                it["status"] = "renamed"
                applied.append(it)
        except Exception as exc:
            it["status"], it["reason"] = "error", f"{exc.__class__.__name__}: {exc}"

    if applied:
        manifest_path = folder_path / MANIFEST_NAME
        is_new = not manifest_path.exists()
        try:
            with manifest_path.open("a", newline="", encoding="utf-8-sig") as fh:
                w = csv.writer(fh)
                if is_new:
                    w.writerow(["nombre_nuevo", "nombre_original", "cufe", "fecha_hora"])
                stamp = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M:%S")
                for it in applied:
                    w.writerow([it["new_name"], it["current_name"], it.get("cufe") or "", stamp])
            result["manifest"] = str(manifest_path)
        except Exception as exc:
            result["manifest_error"] = f"{exc.__class__.__name__}: {exc}"

    result["counts"] = _counts(plan)
    return result
