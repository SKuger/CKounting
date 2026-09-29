import os
import uuid
import asyncio
from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import httpx
from processor import process_excel
from dian_paths import UPLOADS_DIR, RESULTS_DIR, STATIC_DIR
from citas import vigia
import portal as portal_mod

app = FastAPI(title="DIAN RUT Automator")

# Writable dirs (uploads/results/errors/browser_profile) are created under DIAN_WORKDIR by dian_paths.
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

active_websockets: dict[str, WebSocket] = {}
active_jobs: dict[str, str] = {}

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open(os.path.join(STATIC_DIR, "index.html"), "r", encoding="utf-8") as f:
        return f.read()

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    active_websockets[client_id] = websocket
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        if client_id in active_websockets:
            del active_websockets[client_id]

async def send_log(client_id: str, message_type: str, data: dict):
    if client_id in active_websockets:
        try:
            await active_websockets[client_id].send_json({"type": message_type, "data": data})
        except Exception as e:
            print(f"Error sending log to {client_id}: {e}")

@app.post("/upload")
async def upload_file(client_id: str = Form(...), file: UploadFile = File(...)):
    if not file.filename.endswith('.xlsx'):
        return JSONResponse(status_code=400, content={"error": "Solo se permiten archivos Excel (.xlsx)"})
    
    file_id = str(uuid.uuid4())
    upload_path = os.path.join(UPLOADS_DIR, f"{file_id}_{file.filename}")
    
    with open(upload_path, "wb") as buffer:
        buffer.write(await file.read())
        
    asyncio.create_task(process_excel(upload_path, file_id, client_id, send_log, active_jobs))
    
    return {"message": "Archivo recibido, procesando...", "file_id": file_id}

@app.get("/download/current/{file_id}")
async def download_current_file(file_id: str):
    # Primero buscamos en los trabajos activos
    file_path = active_jobs.get(file_id)
    
    # Si no está en activos, intentamos buscarlo por patrón en results (por si se reinició el servidor)
    if not file_path:
        for f in os.listdir(RESULTS_DIR):
            if file_id in f:
                file_path = os.path.join(RESULTS_DIR, f)
                break
                
    if file_path and os.path.exists(file_path):
        filename = os.path.basename(file_path)
        return FileResponse(
            path=file_path, 
            filename=filename, 
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    return JSONResponse(status_code=404, content={"error": "Archivo no encontrado o aún no se ha generado la primera versión."})

@app.get("/health")
async def health():
    # Chequeo de vida para el shell. No usar /browser-mode-status para esto: sondea :9222, y en
    # Windows una conexión rechazada tarda ~2 s, más que el timeout del chequeo.
    return {"ok": True}

@app.get("/browser-mode-status")
async def get_browser_mode_status():
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get("http://127.0.0.1:9222/json/version")
            if response.status_code == 200:
                return {"status": "human_connected"}
    except (httpx.ConnectError, httpx.TimeoutException):
        pass
    return {"status": "human_not_available"}

@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = os.path.join(RESULTS_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(
            path=file_path, 
            filename=filename, 
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    return JSONResponse(status_code=404, content={"error": "File not found"})


# ─── Vigía de citas DIAN (D-104) ───────────────────────────────────────────────────────────────

# ─────────────── Portal DIAN: descarga del listado del mes (Fase 2) ───────────────
# Cada corrida vive en memoria mientras dura. El ENLACE DE ACCESO no se guarda:
# entra por el cuerpo de la petición, se pasa al navegador y no queda en el estado.

_corridas: dict[str, dict] = {}


async def _correr_descarga(corrida_id: str, datos: dict):
    estado = _corridas[corrida_id]
    enlace = datos.pop("enlace")          # sale del dict antes de guardar nada
    try:
        def avisa(mensaje: str):
            estado["mensaje"] = mensaje
        res = await portal_mod.descargar_listado(
            enlace,
            datos["desde"], datos["hasta"], datos["carpeta"],
            etiqueta=datos.get("etiqueta") or "listado",
            grupo=datos.get("grupo") or "todos",
            nit_receptor=datos.get("nit_receptor"),
            progreso=avisa,
        )
        estado.update(estado="listo", mensaje="Listo", **res.como_dict())
    except portal_mod.PortalError as exc:
        estado.update(estado="error", mensaje=str(exc), error=str(exc))
    except Exception as exc:
        # Nunca se propaga el texto crudo: podría arrastrar la URL con el token.
        estado.update(estado="error", error="La descarga falló por un error inesperado.",
                      mensaje="La descarga falló por un error inesperado.")
        print("portal: fallo inesperado:", type(exc).__name__)


@app.post("/portal/descargar")
async def portal_descargar(payload: dict):
    faltan = [k for k in ("enlace", "desde", "hasta", "carpeta") if not payload.get(k)]
    if faltan:
        return JSONResponse(status_code=400,
                            content={"error": f"Faltan datos: {', '.join(faltan)}"})
    corrida_id = str(uuid.uuid4())
    _corridas[corrida_id] = {"estado": "corriendo", "mensaje": "Arrancando…",
                             "archivo": None, "empresa": None, "error": None}
    asyncio.create_task(_correr_descarga(corrida_id, dict(payload)))
    return {"id": corrida_id, **_corridas[corrida_id]}


async def _correr_soportes(corrida_id: str, datos: dict):
    estado = _corridas[corrida_id]
    try:
        def avisa(mensaje: str):
            estado["mensaje"] = mensaje
        res = await portal_mod.descargar_soportes(
            datos["documentos"], datos["carpeta"], progreso=avisa)
        estado.update(estado="listo", mensaje="Listo", **res.como_dict())
    except Exception:
        estado.update(estado="error", error="La descarga de soportes falló.",
                      mensaje="La descarga de soportes falló.")


@app.post("/portal/soportes")
async def portal_soportes(payload: dict):
    documentos = payload.get("documentos") or []
    if not documentos or not payload.get("carpeta"):
        return JSONResponse(status_code=400,
                            content={"error": "Faltan los documentos o la carpeta."})
    corrida_id = str(uuid.uuid4())
    _corridas[corrida_id] = {"estado": "corriendo", "mensaje": "Arrancando…", "error": None}
    asyncio.create_task(_correr_soportes(corrida_id, dict(payload)))
    return {"id": corrida_id, **_corridas[corrida_id]}


@app.get("/portal/estado/{corrida_id}")
async def portal_estado(corrida_id: str):
    estado = _corridas.get(corrida_id)
    if estado is None:
        return JSONResponse(status_code=404, content={"error": "Esa descarga no existe."})
    return {"id": corrida_id, **estado}


@app.get("/citas/status")
async def citas_status():
    return vigia.snapshot()

@app.post("/citas/start")
async def citas_start():
    return {"started": vigia.iniciar(), **vigia.snapshot()}

@app.post("/citas/continuar")
async def citas_continuar():
    return {**vigia.continuar(), **vigia.snapshot()}

@app.post("/citas/stop")
async def citas_stop():
    vigia.detener()
    return vigia.snapshot()

@app.get("/citas/captura")
async def citas_captura():
    ruta = vigia.ruta_captura()
    if not ruta:
        return JSONResponse(status_code=404, content={"error": "Todavía no hay captura."})
    return FileResponse(path=str(ruta), media_type="image/png")
