# Bitácora de sesiones

Resumen breve de cada sesión de trabajo. Para detalle ver `plan.md` y `decisions.md`.

---

## Sesión 1 — 2026-05-27 / 28: planificación + E1 completa

**Resultado**: E1 cerrada end-to-end con muestras reales. 37 tests pasando. UI moderna con dark theme + full-width.

### Fases dentro de la sesión

1. **Planificación inicial**
   - Estructura `docs/` creada (plan, decisions, glosario, samples).
   - Decisiones tomadas: stack Tauri + Nuxt 4 + Python sidecar + SQLite (D-002), una `.db` por empresa (D-003), single-user (D-004), formatos Excel + PDF (D-005), export `.xlsx` con columnas originales (D-006), span dev mode primero (D-007), persistencia desde E1 (D-008), español/Colombia/DIAN (D-009), datos falsos en `docs/samples/` commiteables (D-010), preferencia opción múltiple (D-011).
   - Análisis exhaustivo del Excel DIAN (`docs/excel-structure.md`): 32 columnas + estructura confirmada con workflow multi-agente.
   - Lock E1 con verificación adversarial de columnas + reglas de validación.

2. **Implementación E1 Python sidecar**
   - `apps/core/contab_core/{paths, nit, storage, excel, validations, export, sidecar}.py`.
   - Schema SQLite con migraciones idempotentes.
   - Bug fix: factores DIAN módulo 11 estaban invertidos (derecha-izquierda) — corregido en `nit.py`.
   - 22 tests iniciales pasando contra `Ejemplo_LaDian.xlsx`.

3. **Implementación E1 frontend Nuxt 4**
   - `apps/desktop` con páginas `index`, `empresa`, `load`.
   - IPC bridge stdio JSON-lines (singleton subprocess en `server/utils/sidecar.ts`).
   - TanStack Vue Table para la tabla de la carga.
   - End-to-end probado en navegador.

4. **Iteraciones de UX pedidas por el usuario**
   - **D-031**: ocultar 21 columnas por defecto en la tabla (Estado, Grupo, Divisa, impuestos, retenciones, etc.) con panel de visibilidad.
   - File picker nativo + DirectoryPicker propio (`apps/desktop/app/components/DirectoryPicker.vue` + `/api/list-dir`). No más rutas escritas a mano.
   - **D-035**: dos carpetas por empresa (`default_folder` para Excels, `pdfs_folder` para PDFs).
   - **D-036**: auto-listado de archivos en `default_folder` con `imported` flag y 1-click import.
   - **D-038**: rediseño visual completo — tokens dark theme tipo Linear, full-width, layout con grid en empresa.

5. **PDF CUFE: implementación real (adelantando E4 a E1)**
   - **D-032**: extracción multi-pase (`pdftotext-raw` → `pdftotext-layout` → `cv2.QRCodeDetector` con `pypdfium2`).
   - **D-034**: QR scan multi-DPI (300→400→220) para fuentes obfuscadas (Movistar).
   - **D-037**: auto-indexing on validation run.
   - **D-040**: mostrar el CUFE encontrado bajo cada PDF + botón copiar al portapapeles.
   - V1 deja de ser stub y empieza a validar de verdad.
   - 6 PDFs reales → 6 CUFEs indexados (era 7 antes de aplicar la regla siguiente).

6. **Regla 1-CUFE-por-PDF (D-033)**
   - Bug encontrado por el usuario: la NC de Éxito generaba 2 CUFEs porque también extraía el CUFE de la **factura padre** que la NC referencia.
   - Implementada prioridad **CUDS > CUDE > CUFE**: cada PDF aporta solo su identificador propio. La referencia al padre se descarta.
   - Tests actualizados a aserción estricta `len(cufes) == 1` con etiqueta esperada por PDF.

### Estado al cerrar la sesión

- **37/37 tests Python pasando**.
- Dev server corriendo en http://localhost:3000.
- Empresa de prueba creada y persistida con ambas carpetas configuradas a `docs/samples/` y `docs/samples/pdfs/`.
- Validaciones reales contra la muestra dan **7 / 11 filas no conformes** con razones útiles (sin soporte / tarifa IVA incorrecta).
- 40 decisiones registradas (D-001..D-040).
- Plan reorganizado: E1 ✅, E3 re-scope (probablemente no necesario), E4 reducida a opcional (OCR + templates).

### Atajos útiles para la próxima sesión

```bash
# Arrancar dev (si no está corriendo)
cd apps/desktop && npm run dev

# Tests
cd apps/core && .venv/bin/pytest tests/ -q

# Restart sidecar al cambiar código Python
pkill -f 'contab_core.sidecar'
# (Nuxt lo respawnea en el próximo /api/rpc)

# Reset del cache de CUFEs (para re-extraer)
DB="$HOME/.local/share/Contab/empresas/900181831_real-seguros-ltda.db"
# (VSCode snap: $HOME/snap/code/240/.local/share/Contab/empresas/...)
sqlite3 "$DB" "DELETE FROM pdf_cufe_index;"
```

### Decisiones que el usuario tiene aún pendientes

- **D-E1-13** ⏸ ¿Cuándo `IVA = 0` en V3? Hoy hace skip — ¿confirmamos?
- **D-E2-1** ⏸ Política de backup de empresa.db (manual? auto al cerrar app?).
- **D-E2-2** ⏸ ¿Permitir editar NIT/razón social después de creada la empresa?
- **D-E4-3** ⏸ ¿OCR Tesseract para PDFs escaneados o se posterga?
- **D-E8-1** ⏸ Estrategia multiusuario (Postgres servidor vs sync nube).
- **D-E10-1** ⏸ Firma del instalador Windows.

### Próxima sesión — candidatos

| Opción | Esfuerzo | Valor |
|---|---|---|
| **E2** — Backup/restore, edición de empresa | Medio | Alto si el usuario empieza a usarlo en serio. |
| **E5** — PUC + catálogo de terceros | Alto | Necesario para pasar de "cruce" a contabilidad real. |
| **Tauri / E10** | Medio-alto | Necesario para distribuir como `.msi`. |
| **Mejoras de UX sobre E1** | Bajo | `razon_falla` inline por fila, filtros guardados, columnas reordenables. |
| **Backlog suelto** | Variable | Conciliación bancaria, recordatorios fiscales, dashboard ejecutivo. |
