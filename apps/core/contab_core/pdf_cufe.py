"""Extract CUFE/CUDE/CUDS codes from PDF supports.

Strategy (D-017, refined in D-067):
  Pass 1: `pdftotext -raw`; regroup hex by whitespace-separated tokens so a
          neighbouring number can't glue onto the CUFE. A LABELED hit
          (CUFE:/CUDE:/CUDS:) is high-confidence → return it.
  Pass 2: `pdftotext -layout` (the labeled layout sometimes surfaces the anchor).
  Pass 3: render pages with pypdfium2 → cv2.QRCodeDetector. The DIAN QR carries
          the CUFE in cleartext (Movistar/Claro/Tigo case). This runs ONLY when
          the text read fails (nothing, or an unlabeled low-confidence token) and
          is authoritative — the QR is DIAN's machine-readable ground truth.
"""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
import pypdfium2 as pdfium

CUFE_RE = re.compile(r"^[a-f0-9]{96}$")
# A run of hex chars possibly split by whitespace (line-wrapped CUFEs). We then
# regroup by whitespace-separated segments so an adjacent number (e.g. the DIAN
# authorization number, 16 pure digits printed right above the CUFE) can never
# glue onto the CUFE across a line break — the Telesentinel bug (D-067).
_HEX_RUN_RE = re.compile(r"[0-9a-f](?:[0-9a-f\s]*[0-9a-f])?", re.IGNORECASE)
_HEX_SEG_RE = re.compile(r"[0-9a-f]+", re.IGNORECASE)
LABEL_RE = re.compile(r"\b(CUFE|CUDE|CUDS)\b\s*:?\s*", re.IGNORECASE)

EXTRACTION_STATUS_OK = "ok"
EXTRACTION_STATUS_NO_TEXT = "no_text"
EXTRACTION_STATUS_ERROR = "error"

# Bump whenever the extraction algorithm changes so cached entries (keyed only by
# mtime/size) get re-extracted instead of returning a value the old code produced.
#   1 → segment-boundary regrouping (no more glued auth numbers) + QR cross-check
#       of unlabeled/failed text reads (D-067).
EXTRACTOR_VERSION = 1


@dataclass(frozen=True)
class Cufe:
    value: str           # 96-char lowercase hex
    label: str | None    # 'CUFE' / 'CUDE' / 'CUDS' / None when label unknown


@dataclass(frozen=True)
class ExtractionResult:
    cufes: list[Cufe]
    source: str          # 'pdftotext-raw' / 'pdftotext-layout' / 'qr-scan' / 'none'
    status: str          # EXTRACTION_STATUS_*
    error: str | None = None


# Priority order: a PDF's "own" identifier. NC PDFs may also reference the parent
# factura's CUFE — we must NOT return that, only the document's own code.
PRIORITY_LABELS: tuple[str, ...] = ("CUDS", "CUDE", "CUFE")
LOOKAHEAD_WINDOW = 250  # 96 hex chars + buffer for whitespace/line-wraps.


def _hex_candidates(text: str) -> list[tuple[int, str]]:
    """Every 96-hex CUFE candidate in `text`, as (start_offset, lowercase_token).

    A candidate is the concatenation of CONTIGUOUS whitespace-separated hex
    segments that total exactly 96 hex chars — this reconstructs a CUFE wrapped
    across lines while respecting token boundaries. Requiring an a-f letter
    rejects pure-digit numbers (a real SHA-384 CUFE effectively always has one).

    Respecting token boundaries is what fixes the Telesentinel gluing bug (D-067):
    the 16-digit authorization number is its own whitespace-separated segment, so
    no 96-char group can span part of it plus part of the CUFE."""
    out: list[tuple[int, str]] = []
    for run in _HEX_RUN_RE.finditer(text):
        segs = [(m.start(), m.group(0)) for m in _HEX_SEG_RE.finditer(run.group(0))]
        for i in range(len(segs)):
            total = 0
            for j in range(i, len(segs)):
                total += len(segs[j][1])
                if total == 96:
                    token = "".join(s for _, s in segs[i:j + 1]).lower()
                    if any(c in "abcdef" for c in token):
                        out.append((run.start() + segs[i][0], token))
                    break
                if total > 96:
                    break
    seen: set[str] = set()
    result: list[tuple[int, str]] = []
    for pos, tok in sorted(out):
        if tok not in seen:
            seen.add(tok)
            result.append((pos, tok))
    return result


def _find_cufes_in_text(text: str) -> list[Cufe]:
    """Return AT MOST ONE Cufe: the document's own identifier.

    Priority: CUDS (doc soporte) > CUDE (NC / POS / nómina) > CUFE (factura).
    A labeled value wins; among labels the highest priority wins (so an NC
    returns its own CUDE, never the parent CUFE it references). With no label we
    fall back to the first standalone candidate.
    """
    if not text:
        return []
    candidates = _hex_candidates(text)
    if not candidates:
        return []

    labeled: dict[str, str] = {}
    for m in LABEL_RE.finditer(text):
        label = m.group(1).upper()
        if label not in PRIORITY_LABELS or label in labeled:
            continue
        end = m.end()
        token = next(
            (tok for pos, tok in candidates if pos >= end and pos - end <= LOOKAHEAD_WINDOW),
            None,
        )
        if token:
            labeled[label] = token

    for label in PRIORITY_LABELS:
        if label in labeled:
            return [Cufe(value=labeled[label], label=label)]

    return [Cufe(value=candidates[0][1], label=None)]


def _pdftotext(pdf_path: Path, layout: bool, timeout: float = 30.0) -> str:
    # Packaged (Windows): CONTAB_PDFTOTEXT points at the bundled Poppler binary (not on PATH).
    # Dev / Linux: fall back to `pdftotext` from PATH.
    exe = os.environ.get("CONTAB_PDFTOTEXT") or "pdftotext"
    args = [exe, "-layout" if layout else "-raw", "-enc", "UTF-8", str(pdf_path), "-"]
    try:
        result = subprocess.run(args, capture_output=True, timeout=timeout, check=False)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.decode("utf-8", errors="replace")


def _render_page(page, dpi: int) -> np.ndarray | None:
    """Render one PdfPage to a BGR numpy array."""
    try:
        scale = dpi / 72.0
        bitmap = page.render(scale=scale)
        pil = bitmap.to_pil().convert("RGB")
        return cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
    except Exception:
        return None


def _decode_qrs_in_image(detector: "cv2.QRCodeDetector", img: np.ndarray) -> list[str]:
    """Return all distinct QR payloads decoded in one image."""
    payloads: set[str] = set()
    try:
        ret, infos, _pts, _sqr = detector.detectAndDecodeMulti(img)
        if ret and infos:
            for s in infos:
                if s:
                    payloads.add(s)
    except cv2.error:
        pass
    if not payloads:
        try:
            data, _pts, _sqr = detector.detectAndDecode(img)
            if data:
                payloads.add(data)
        except cv2.error:
            pass
    if not payloads:
        # Grayscale + Otsu threshold (helps with low-contrast scans).
        try:
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
            data, _pts, _sqr = detector.detectAndDecode(bw)
            if data:
                payloads.add(data)
        except cv2.error:
            pass
    return list(payloads)


def _scan_qrs_in_pdf(pdf_path: Path, dpi_attempts: tuple[int, ...]) -> list[str]:
    """Walk every page at each requested DPI, collect every distinct QR payload.

    Different QRs on the same page can be detected at different DPIs (Movistar:
    payment-QR at 300 dpi, DIAN CUFE-QR at 400 dpi), so we always sweep all DPIs
    rather than stopping at the first hit."""
    detector = cv2.QRCodeDetector()
    seen: set[str] = set()
    try:
        pdf = pdfium.PdfDocument(str(pdf_path))
    except Exception:
        return []
    try:
        for page in pdf:
            for dpi in dpi_attempts:
                img = _render_page(page, dpi)
                if img is None:
                    continue
                for payload in _decode_qrs_in_image(detector, img):
                    seen.add(payload)
            try:
                page.close()
            except Exception:
                pass
    finally:
        try:
            pdf.close()
        except Exception:
            pass
    return list(seen)


def _cufes_from_qr_payloads(payloads: Iterable[str]) -> list[Cufe]:
    """Reuse the same labeled-priority logic on concatenated QR payloads.
    DIAN QRs carry the labeled CUFE in plaintext (Movistar/Claro/Tigo path)."""
    combined = "\n".join(payloads)
    return _find_cufes_in_text(combined)


DEFAULT_QR_DPI_ATTEMPTS: tuple[int, ...] = (300, 400, 220)


def extract_cufes(
    pdf_path: str | Path,
    *,
    qr_dpi_attempts: tuple[int, ...] = DEFAULT_QR_DPI_ATTEMPTS,
) -> ExtractionResult:
    """Run the layered extraction: pdftotext-raw → pdftotext-layout → QR scan.

    A LABELED text hit (CUFE:/CUDE:/CUDS: anchor) is high-confidence and returns
    immediately — no QR. The QR scan runs only when the text read "fails", i.e.
    yields nothing OR only an UNLABELED token (the low-confidence fallback, e.g.
    the Telesentinel case where an adjacent number could distort the read). There
    the QR — the DIAN machine-readable ground truth — is authoritative (D-067).
    This keeps the common labeled case instant while cross-checking the risky few.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.is_file():
        return ExtractionResult(cufes=[], source="none", status=EXTRACTION_STATUS_ERROR,
                                error=f"PDF no encontrado: {pdf_path}")

    # Pass 1: raw text. Labeled hit → done.
    text = _pdftotext(pdf_path, layout=False)
    cufes = _find_cufes_in_text(text)
    if cufes and cufes[0].label is not None:
        return ExtractionResult(cufes=cufes, source="pdftotext-raw", status=EXTRACTION_STATUS_OK)

    # Pass 2: layout text (a labeled layout sometimes surfaces the anchor).
    text2 = _pdftotext(pdf_path, layout=True)
    cufes2 = _find_cufes_in_text(text2) if (text2 and text2 != text) else []
    if cufes2 and cufes2[0].label is not None:
        return ExtractionResult(cufes=cufes2, source="pdftotext-layout", status=EXTRACTION_STATUS_OK)

    # Best UNLABELED text hit (correct-looking token but no anchor → lower
    # confidence). Keep it, but cross-check against the QR first.
    best_text = cufes or cufes2
    best_source = "pdftotext-raw" if cufes else "pdftotext-layout"

    # Pass 3: QR scan — authoritative when present.
    try:
        payloads = _scan_qrs_in_pdf(pdf_path, qr_dpi_attempts)
    except Exception as exc:
        if best_text:
            return ExtractionResult(cufes=best_text, source=best_source, status=EXTRACTION_STATUS_OK)
        return ExtractionResult(cufes=[], source="qr-scan", status=EXTRACTION_STATUS_ERROR,
                                error=f"Renderizado/decoding falló: {exc}")
    cufes_qr = _cufes_from_qr_payloads(payloads)
    if cufes_qr:
        return ExtractionResult(cufes=cufes_qr, source="qr-scan", status=EXTRACTION_STATUS_OK)

    # No QR → fall back to the unlabeled text hit if we had one.
    if best_text:
        return ExtractionResult(cufes=best_text, source=best_source, status=EXTRACTION_STATUS_OK)

    return ExtractionResult(cufes=[], source="none", status=EXTRACTION_STATUS_NO_TEXT)


# =========== Folder indexing (cache via pdf_cufe_index / pdf_cufe_value) ===========

@dataclass
class IndexStats:
    folder: str
    total_pdfs: int = 0
    indexed_now: int = 0
    cached: int = 0
    pruned: int = 0                 # entradas de PDFs que ya no están en la carpeta
    failed: list[str] = None        # type: ignore
    no_cufe: list[str] = None       # type: ignore

    def __post_init__(self):
        if self.failed is None:
            self.failed = []
        if self.no_cufe is None:
            self.no_cufe = []

    def to_dict(self) -> dict:
        return {
            "folder": self.folder,
            "total_pdfs": self.total_pdfs,
            "indexed_now": self.indexed_now,
            "cached": self.cached,
            "pruned": self.pruned,
            "failed": self.failed,
            "no_cufe": self.no_cufe,
        }


def index_folder(conn, folder: str | Path) -> IndexStats:
    """Incrementally index every PDF in folder.
    Re-extracts only when (mtime, size) changed or the PDF is new.

    Transacciones: COMMIT por archivo (no una sola que envuelva toda la carpeta).
    Extraer un mes de soportes son minutos de pdftotext + render + QR; con una
    transacción única, morir en el PDF 79 de 80 tiraba TODO el trabajo por rollback
    y mantenía el bloqueo de escritura abierto mientras tanto.

    Al terminar purga las entradas de PDFs que ya no están en la carpeta: si no,
    `get_indexed_cufes` seguiría devolviendo el CUFE de un soporte borrado y V1
    daría por respaldada una fila que ya no tiene soporte.

    Uses tables pdf_cufe_index + pdf_cufe_value created in storage.SCHEMA_SQL."""
    from .storage import transaction

    folder = Path(folder).resolve()
    stats = IndexStats(folder=str(folder))
    if not folder.is_dir():
        return stats

    pdfs = sorted(
        (p for p in folder.iterdir() if p.is_file() and p.suffix.lower() == ".pdf"),
        key=lambda p: p.name.lower(),
    )
    stats.total_pdfs = len(pdfs)
    present: set[str] = set()

    for pdf_path in pdfs:
        full = str(pdf_path.resolve())
        present.add(full)
        try:
            st = pdf_path.stat()
        except OSError as exc:
            stats.failed.append(f"{pdf_path.name}: {exc}")
            continue
        mtime = int(st.st_mtime)
        size = st.st_size

        cached_row = conn.execute(
            "SELECT id, extraction_status FROM pdf_cufe_index "
            "WHERE folder_path = ? AND pdf_path = ? AND pdf_mtime = ? AND pdf_size_bytes = ? "
            "AND extractor_version = ?",
            (str(folder), full, mtime, size, EXTRACTOR_VERSION),
        ).fetchone()
        if cached_row is not None:
            stats.cached += 1
            if cached_row["extraction_status"] != EXTRACTION_STATUS_OK:
                stats.no_cufe.append(pdf_path.name)
            continue

        # Stale / new entry → re-extract. La extracción va FUERA de la transacción:
        # es la parte lenta y no toca la BD.
        result = extract_cufes(pdf_path)
        with transaction(conn):
            conn.execute(
                "DELETE FROM pdf_cufe_index WHERE folder_path = ? AND pdf_path = ?",
                (str(folder), full),
            )
            cur = conn.execute(
                "INSERT INTO pdf_cufe_index"
                " (folder_path, pdf_path, pdf_mtime, pdf_size_bytes, extraction_status, extraction_error, extractor_version)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (str(folder), full, mtime, size, result.status, result.error, EXTRACTOR_VERSION),
            )
            idx_id = cur.lastrowid
            if result.cufes:
                conn.executemany(
                    "INSERT OR IGNORE INTO pdf_cufe_value(pdf_index_id, cufe_cude, label)"
                    " VALUES (?, ?, ?)",
                    [(idx_id, c.value, c.label) for c in result.cufes],
                )
        if result.status == EXTRACTION_STATUS_ERROR:
            stats.failed.append(f"{pdf_path.name}: {result.error or 'error'}")
        elif result.status != EXTRACTION_STATUS_OK:
            stats.no_cufe.append(pdf_path.name)
        stats.indexed_now += 1

    stats.pruned = _prune_missing(conn, folder, present)
    return stats


def _prune_missing(conn, folder: Path, present: set[str]) -> int:
    """Borra del índice los PDFs que ya no están en la carpeta. Devuelve cuántos.

    ON DELETE CASCADE se lleva sus pdf_cufe_value, así que el CUFE de un soporte
    eliminado deja de contar como respaldo en V1."""
    from .storage import transaction

    known = [
        r["pdf_path"]
        for r in conn.execute(
            "SELECT pdf_path FROM pdf_cufe_index WHERE folder_path = ?", (str(folder),)
        ).fetchall()
    ]
    gone = [p for p in known if p not in present]
    if not gone:
        return 0
    with transaction(conn):
        conn.executemany(
            "DELETE FROM pdf_cufe_index WHERE folder_path = ? AND pdf_path = ?",
            [(str(folder), p) for p in gone],
        )
    return len(gone)


def get_indexed_cufes(conn, folder: str | Path) -> set[str]:
    folder = str(Path(folder).resolve())
    rows = conn.execute(
        "SELECT v.cufe_cude FROM pdf_cufe_value v "
        "JOIN pdf_cufe_index i ON v.pdf_index_id = i.id "
        "WHERE i.folder_path = ?",
        (folder,),
    ).fetchall()
    return {row["cufe_cude"] for row in rows}


def list_indexed_pdfs(conn, folder: str | Path) -> list[dict]:
    """Return per-PDF index info for UI surfacing. Each entry includes the
    extracted CUFE/CUDE/CUDS value when available (post-priority-selection,
    so exactly one per PDF in the normal case)."""
    folder = str(Path(folder).resolve())
    rows = conn.execute(
        "SELECT i.id, i.pdf_path, i.pdf_mtime, i.pdf_size_bytes, i.extraction_status,"
        " i.extraction_error, i.indexed_at "
        "FROM pdf_cufe_index i WHERE i.folder_path = ? "
        "ORDER BY i.pdf_path",
        (folder,),
    ).fetchall()
    out: list[dict] = []
    for r in rows:
        values = conn.execute(
            "SELECT cufe_cude, label FROM pdf_cufe_value WHERE pdf_index_id = ?",
            (r["id"],),
        ).fetchall()
        cufes = [{"value": v["cufe_cude"], "label": v["label"]} for v in values]
        entry = dict(r)
        entry["cufe_count"] = len(cufes)
        entry["cufes"] = cufes
        out.append(entry)
    return out
