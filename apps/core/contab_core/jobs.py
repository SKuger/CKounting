"""Trabajos en segundo plano con progreso (D-076).

El problema que resuelve: el bucle IPC es estrictamente serial (una línea, una
respuesta) y Nitro cortaba toda petición a los 30 s. Indexar los soportes de un
mes son minutos de pdftotext + render + QR, así que:

  - la petición reventaba por timeout mientras Python seguía trabajando,
  - su respuesta llegaba después a un id que ya nadie esperaba,
  - y todo lo que el usuario tocara mientras tanto se encolaba detrás y también
    reventaba.

Ahora las operaciones largas corren en un hilo y devuelven un `job_id` al
instante. El bucle principal queda libre para atender `job_status`, así que la UI
puede mostrar progreso real y el usuario puede seguir usando la aplicación.

Sobre SQLite: cada trabajo abre su PROPIA conexión. Con WAL más el
`busy_timeout` de storage.connect, un trabajo escribiendo y la UI leyendo
conviven sin "database is locked".
"""
from __future__ import annotations

import sys
import threading
import time
import traceback
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

# Un trabajo terminado se conserva este tiempo para que la UI alcance a leer su
# resultado aunque tarde en preguntar; luego se recoge.
RETENTION_SECONDS = 15 * 60

STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_ERROR = "error"
STATUS_CANCELLED = "cancelled"


@dataclass
class Progress:
    done: int = 0
    total: int = 0
    message: str = ""

    def to_dict(self) -> dict:
        pct = round(100 * self.done / self.total) if self.total else None
        return {"done": self.done, "total": self.total, "message": self.message, "percent": pct}


@dataclass
class Job:
    id: str
    method: str
    status: str = STATUS_RUNNING
    progress: Progress = field(default_factory=Progress)
    result: Any = None
    error: str | None = None
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    _cancel: threading.Event = field(default_factory=threading.Event)

    def to_dict(self, *, include_result: bool = True) -> dict:
        out = {
            "job_id": self.id,
            "method": self.method,
            "status": self.status,
            "progress": self.progress.to_dict(),
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed_seconds": round((self.finished_at or time.time()) - self.started_at, 1),
        }
        if include_result:
            out["result"] = self.result
        return out


class Cancelled(Exception):
    """La lanza `report` cuando el usuario canceló el trabajo."""


_JOBS: dict[str, Job] = {}
_LOCK = threading.Lock()


def _collect_expired() -> None:
    """Recoge los trabajos terminados hace rato. Se llama al crear uno nuevo, que
    es el único momento en que el diccionario puede crecer."""
    now = time.time()
    caducados = [
        jid for jid, j in _JOBS.items()
        if j.finished_at is not None and now - j.finished_at > RETENTION_SECONDS
    ]
    for jid in caducados:
        _JOBS.pop(jid, None)


def start(method: str, fn: Callable[[Callable[..., None]], Any]) -> dict:
    """Arranca `fn` en un hilo y devuelve el descriptor del trabajo al instante.

    `fn` recibe un `report(done, total, message)` para publicar progreso. Ese
    `report` lanza `Cancelled` si el usuario canceló, de modo que basta con
    llamarlo periódicamente para que el trabajo sea cancelable."""
    job = Job(id=uuid.uuid4().hex[:12], method=method)
    with _LOCK:
        _collect_expired()
        _JOBS[job.id] = job

    def report(done: int = 0, total: int = 0, message: str = "") -> None:
        if job._cancel.is_set():
            raise Cancelled()
        with _LOCK:
            job.progress = Progress(done=done, total=total, message=message)

    def run() -> None:
        try:
            result = fn(report)
            with _LOCK:
                job.result = result
                job.status = STATUS_DONE
        except Cancelled:
            with _LOCK:
                job.status = STATUS_CANCELLED
                job.error = "Cancelado por el usuario."
        except Exception as exc:
            # La traza va al log (stderr), no al payload: la UI recibe el mensaje
            # para el usuario, no rutas internas ni nombres de módulo.
            print(f"[job {job.id}] {method} falló:\n{traceback.format_exc()}",
                  file=sys.stderr, flush=True)
            with _LOCK:
                job.status = STATUS_ERROR
                job.error = str(exc) or exc.__class__.__name__
        finally:
            with _LOCK:
                job.finished_at = time.time()

    threading.Thread(target=run, name=f"job-{method}-{job.id}", daemon=True).start()
    return job.to_dict(include_result=False)


def status(job_id: str) -> dict:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            raise ValueError(
                "Ese trabajo ya no existe (pudo terminar hace rato o la aplicación se reinició)."
            )
        return job.to_dict()


def cancel(job_id: str) -> dict:
    with _LOCK:
        job = _JOBS.get(job_id)
        if job is None:
            raise ValueError("Ese trabajo ya no existe.")
        if job.status == STATUS_RUNNING:
            job._cancel.set()
        return job.to_dict(include_result=False)


def listar() -> list[dict]:
    with _LOCK:
        return [j.to_dict(include_result=False) for j in _JOBS.values()]
