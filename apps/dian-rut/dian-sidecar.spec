# PyInstaller spec — DIAN sidecar (onedir). Build with:  pyinstaller dian-sidecar.spec --noconfirm
# Produces dist/dian-sidecar/dian-sidecar[.exe] + _internal/. Ships the Playwright Python lib but
# NOT a browser (the scraper connects to the user's Chrome via CDP :9222; see plan/D-058).
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []
for pkg in (
    "uvicorn", "fastapi", "starlette", "anyio",
    "pandas", "openpyxl", "httpx", "websockets",
    "playwright", "playwright_stealth",
):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

# uvicorn loads its loop/protocol/lifespan impls dynamically; python-multipart imports as `multipart`.
hiddenimports += collect_submodules("uvicorn")
hiddenimports += ["multipart"]

# ship the read-only static assets (index.html, app.js, style.css, plantilla_rut.xlsx) → _internal/static
datas += [("static", "static")]

a = Analysis(
    ["run_server.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    excludes=["tkinter", "matplotlib", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="dian-sidecar",
    console=True,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="dian-sidecar",
)
