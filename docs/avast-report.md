# Avast — false positive submission (texto listo para enviar)

> Se envía en https://www.avast.com/submitsample (o por FTP si ya se entró al
> programa de whitelisting). Está en inglés porque lo leen los analistas de Avast.
> **Antes de enviar**: rellenar `<DETECTION NAME>` y `<ALERT ID>` con lo que muestra
> el aviso de Avast, y actualizar versión, URL y hash si ya hay una release nueva.
> El procedimiento completo está en [`antivirus.md`](antivirus.md).

---

**Subject:** False positive on Contab installer (unsigned Electron + PyInstaller app)

**Detection name:** `<DETECTION NAME>`
**Alert ID:** `<ALERT ID>`

**File:** `Contab-Setup-0.11.0.exe` (200,568,751 bytes)
**Download URL:** https://github.com/SKuger/CKounting-releases/releases/download/v0.11.0/Contab-Setup-0.11.0.exe
**SHA-512 (base64, as published in `latest.yml`):**
`c4PLvEdYLmPNpnFiffCh5MU4q487YU3kP08yHVbulLFKhuLf5/Itbz/svaa6jcGs/I3iyzkKvLMBDHIBVEGNOQ==`

**What the software is**

Contab is a desktop bookkeeping application for Colombian accountants, used to
cross-check the DIAN (the Colombian tax authority) electronic-invoicing reports
against the supporting PDF documents, and to download those supporting documents
from the DIAN's own public portal. It is not distributed commercially; it is used
by a single accounting practice.

**Why it most likely triggers the heuristic**

1. **The installer is not Authenticode-signed.** No code-signing certificate has
   been purchased yet, so the publisher cannot be verified.
2. **It bundles two PyInstaller onedir executables** (`core-sidecar`,
   `dian-sidecar`), which are the application's Python backends. PyInstaller
   binaries are a well-known source of generic/heuristic detections.
3. **Each release is a brand-new binary** with no download history, so no file
   reputation accumulates.

**What the bundled components do**

- `core-sidecar` — local business logic: reads the accountant's Excel reports with
  `openpyxl`, extracts invoice identifiers (CUFE) from PDFs via `pdftotext`
  (Poppler, also bundled) and OpenCV QR scanning, and stores results in local
  SQLite files. It communicates with the app over stdio only.
- `dian-sidecar` — a local FastAPI service that drives **the user's own installed
  Chrome/Edge** through Playwright against the public DIAN portal
  (`catalogo-vpfe.dian.gov.co`) to download the user's own tax documents. It does
  not bundle a browser and does not install drivers.
- The app makes **no outbound connections other than** the DIAN portal and GitHub
  Releases (for its own updates, via electron-updater).

**Build provenance**

The installer is built on GitHub Actions (`windows-latest`) from the project's
repository and published automatically to a public releases repository:
https://github.com/SKuger/CKounting-releases

The source repository is private, but the build workflow, the full file list and
the published hashes can be provided on request, and the binaries can be rebuilt
from source for comparison if that helps the analysis.

**Request**

Please whitelist the installer and the two bundled sidecar executables. We also
intend to register for the whitelisting program so that future builds can be
submitted before release rather than after users see the warning.
