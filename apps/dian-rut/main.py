import os
import uuid
import asyncio
from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import httpx
from processor import process_excel

app = FastAPI(title="DIAN RUT Automator")

os.makedirs("uploads", exist_ok=True)
os.makedirs("results", exist_ok=True)
os.makedirs("static", exist_ok=True)
os.makedirs("errors", exist_ok=True)

app.mount("/static", StaticFiles(directory="static"), name="static")

active_websockets: dict[str, WebSocket] = {}
active_jobs: dict[str, str] = {}

@app.get("/", response_class=HTMLResponse)
async def read_index():
    with open("static/index.html", "r", encoding="utf-8") as f:
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
    upload_path = os.path.join("uploads", f"{file_id}_{file.filename}")
    
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
        for f in os.listdir("results"):
            if file_id in f:
                file_path = os.path.join("results", f)
                break
                
    if file_path and os.path.exists(file_path):
        filename = os.path.basename(file_path)
        return FileResponse(
            path=file_path, 
            filename=filename, 
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    return JSONResponse(status_code=404, content={"error": "Archivo no encontrado o aún no se ha generado la primera versión."})

@app.get("/browser-mode-status")
async def get_browser_mode_status():
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get("http://localhost:9222/json/version")
            if response.status_code == 200:
                return {"status": "human_connected"}
    except (httpx.ConnectError, httpx.TimeoutException):
        pass
    return {"status": "human_not_available"}

@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = os.path.join("results", filename)
    if os.path.exists(file_path):
        return FileResponse(
            path=file_path, 
            filename=filename, 
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
    return JSONResponse(status_code=404, content={"error": "File not found"})
