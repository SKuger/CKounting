# PyInstaller spec — core sidecar (onedir). Build with:  pyinstaller contab-sidecar.spec --noconfirm
# Produces dist/contab-sidecar/contab-sidecar[.exe] + _internal/. onedir (NOT onefile): onefile
# self-extracts to a tempdir each launch (slow, antivirus-prone, flaky with cv2/pdfium DLLs).
from PyInstaller.utils.hooks import collect_all, collect_submodules

datas, binaries, hiddenimports = [], [], []
# native/data-heavy deps: pull everything PyInstaller's hooks know about
for pkg in ("cv2", "numpy", "pypdfium2", "openpyxl", "xlsxwriter", "PIL"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h
hiddenimports += collect_submodules("contab_core")

a = Analysis(
    ["run_sidecar.py"],
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
    name="contab-sidecar",
    console=True,          # stdio JSON-lines IPC; Electron/Node spawns with windowsHide so no console flashes
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,             # UPX can trip antivirus heuristics on Windows
    name="contab-sidecar",
)
