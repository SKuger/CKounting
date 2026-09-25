#!/bin/bash
if [ ! -d "venv" ]; then
  python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt
playwright install chromium
# 127.0.0.1, NO 0.0.0.0 (D-086): esto es un sidecar local del escritorio. El
# 0.0.0.0 era herencia del despliegue web original y dejaba el scraper de la DIAN
# accesible desde toda la red.
uvicorn main:app --host 127.0.0.1 --port 8000
