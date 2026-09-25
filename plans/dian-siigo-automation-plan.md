---
status: in-progress
owner: SKuger
created: 2026-09-21
updated: 2026-09-22
issue: none — repo personal (SKuger/CKounting), sin board de proyecto; el índice de entregas vive en docs/plan.md
start: 2026-09-21
target: none — sin fecha de cierre; el plan avanza por fases y checkpoints, no por calendario (decidido 2026-09-21)
implementation: SKuger
effort: XL — Phase 1 = M · 2 = L · 3 = L · 4 = XL · 5 = L · 6 = M · 7 = M
language: English body; Spanish "Resumen" + decision/criteria glosses.
---

# DIAN → Siigo semi-automation · Semi-automatización de la DIAN a Siigo

> **Resumen (ES).** El mes de un contador con varias empresas tiene nueve etapas.
> Contab cubre una y media —el cruce DIAN ↔ soportes— y son las más baratas; las
> caras (decidir la causación y registrarla en Siigo) están enteras por fuera.
> Este plan las cubre en siete fases: primero los cimientos (perfil fiscal,
> terceros y un tablero que muestre las N empresas), después la descarga
> automática desde el portal de la DIAN, el XML como fuente de verdad, la
> causación asistida con memoria por proveedor, y el puente a Siigo Nube con
> reconciliación inversa. El principio de todo: **la máquina propone, el contador
> dispone** — cada fase tiene una compuerta humana y el camino manual nunca se
> retira.

Contab today is a completeness check: the accountant downloads the DIAN Excel by
hand, Contab crosses it against the support PDFs by CUFE and exports what does
not conform. Everything it produces ends up in an `.xlsx` that the accountant
retypes into Siigo. This plan closes the two ends — the download and the
posting — and builds the accounting decision layer between them.

---

## How to use this plan · Cómo usar este plan

**EN.** This plan is written to be executed with AI-agent assistance — that is
expected and encouraged. The plan, not the agent, makes the technical decisions.
Your job has three parts: **execute** the tasks, **verify** each one against its
Done-when list, and **escalate** the decisions the plan marks for a human.

Read each task fully — including its **Why** and **Done-when** — *before* you
start it. A task is not finished because an agent said so; it is finished when
every Done-when line is literally true and you have checked it yourself.

If a task or its **Why** doesn't make sense, that is a gap in *this plan*, not a
failing in you — stop and ask @SKuger. A question costs minutes; a
misunderstanding shipped costs days.

**If the English here slows you down:** every section opens with a Spanish
**Resumen**, and your AI agent will translate or explain any part of this plan in
Spanish if you ask it — that is a completely legitimate thing to do. Don't let
the language be the reason a task stalls.

**ES.** Este plan está escrito para ejecutarse con ayuda de agentes de IA — eso
se espera y se fomenta. Las decisiones técnicas las toma el plan, no el agente.
Tu trabajo tiene tres partes: **ejecutar** las tareas, **verificar** cada una
contra su lista *Done-when*, y **escalar** las decisiones que el plan marca para
un humano.

Lee cada tarea completa — incluyendo su **Why** y su **Done-when** — *antes* de
empezarla. Una tarea no está terminada porque un agente lo diga; está terminada
cuando cada línea *Done-when* es literalmente cierta y tú mismo la verificaste.

Si una tarea o su **Why** no te quedan claras, eso es un vacío de *este plan*, no
una falla tuya — pregúntale a @SKuger. Y si el inglés te frena: cada sección
tiene un **Resumen** en español, y tu agente de IA te traduce o explica cualquier
parte en español si se lo pides — hazlo sin problema.

## Conventions · Convenciones

| Marker | Meaning |
|---|---|
| 💡 **Heuristic** | A short engineering or working lesson. Worth 30 seconds. *(ES: heurística — lección breve.)* |
| 🛑 **HUMAN DECISION** | A choice the plan deliberately does not make. **Do not let an agent pick it.** Escalate to @SKuger. *(ES: decisión humana — no la toma un agente; escala a @SKuger.)* |
| ✅ **Done-when** | The Definition of Done. The phase is verified only when every line is literally true. *(ES: terminado-cuando — definición de "hecho".)* |
| 🚦 **Checkpoint** | Stop. Show @SKuger the named evidence and answer the questions before continuing. **Mandatory stop — including in auto mode** (see Working rules). *(ES: punto de control — alto obligatorio, también en modo auto.)* |

> **On the checkpoints.** Each 🚦 lists evidence to show and questions to answer.
> The questions are **not a test of you** — they test whether the plan explained
> things well enough. @SKuger may also ask any of them at any time. *(ES: las
> preguntas del checkpoint no son un examen tuyo — prueban si el plan explicó
> bien; @SKuger puede preguntarlas en cualquier momento.)*

## Working rules · Reglas de trabajo

These apply to every phase.

- **Commit and push after every slice.** When a task group or a phase is done and
  its Done-when checks pass, commit and push to GitHub **immediately**. Work that
  lives only on your laptop cannot be seen, reviewed, helped with, or recovered.
  *(ES: haz commit y push a GitHub apenas termines — el trabajo que solo vive en
  tu laptop no existe para el equipo.)*
- **Commit messages — Conventional Commits, scope required.**
  `type(scope): description` — e.g. `feat(ingesta): descarga del listado DIAN por empresa`.
  `type` ∈ `feat|fix|refactor|test|chore|docs|hotfix|ci`. The `(scope)` is
  **mandatory**. Branch names mirror it: `type/scope-short-description`. *(ES:
  Conventional Commits; el `(scope)` es obligatorio; la rama refleja el commit.)*
- **Review the frontend yourself, in the browser.** A phase that touches the UI is
  **not verified** because the RPC returned `{"ok": true}` — it is verified when
  you have opened `http://localhost:3000`, clicked through what you built, and
  seen it work the way the accountant would use it. *(ES: revisa el frontend tú
  mismo, en el navegador — un `ok: true` del sidecar no es una funcionalidad que
  sirve.)*
- **Which AI tool:** Claude **Sonnet** by default; **Opus** when a task is hard or
  you are stuck; **Copilot** for inline autocomplete and quick questions — not for
  executing a whole task. *(ES: Sonnet por defecto; Opus cuando es difícil o te
  atascas; Copilot para autocompletar.)*
- **You can tell your agent to skip the Why boxes — we won't stop you.** But the
  🚦 checkpoint questions are asked by a person, and that you cannot outsource.
  Reading as you go is the cheap way to be ready. *(ES: puedes pedirle a tu agente
  que se salte las explicaciones — pero las preguntas del checkpoint las hace una
  persona; eso no se delega.)*
- **Auto mode is slice-bounded.** Auto mode (running without clarifying questions
  between turns) is allowed for the duration of **one slice** — a single numbered
  task, or one phase when the plan groups tasks that way. At the end of every
  slice, the agent **STOPS**, surfaces what landed (Done-when items verified,
  files touched, what's next), and waits for explicit human acknowledgement before
  starting the next slice. At 🚦 Checkpoints the stop is stronger — the human
  walks the evidence with the agent. Auto mode is **never** "execute the whole
  plan unattended." *(ES: el modo auto va por slice, no por plan entero. Al final
  de cada slice, el agente **PARA**, te muestra qué cerró (Done-when, archivos
  tocados, qué viene) y espera tu visto bueno antes del siguiente slice. En los 🚦
  el alto es más fuerte — recorres la evidencia con el agente. Auto **nunca**
  significa "ejecuta el plan completo solo".)*

## Glossary · Glosario

> **Resumen (ES).** Términos técnicos en inglés que vas a ver muchas veces en este
> plan, con su traducción y una línea de qué significan. Si te encuentras un
> término del plan que no está aquí y no lo entiendes, pregúntale a tu agente — no
> es una falla tuya, es un vacío de esta tabla.

| English | Español | Means |
|---|---|---|
| Done-when | terminado-cuando | the literal checkable list that means the task is verified |
| slice | rebanada / unidad de trabajo | a small piece of work that can ship on its own |
| commit + push | hacer commit y push | save to git locally **and** send to GitHub — both verbs |
| vault / keyring | bóveda / llavero del sistema | where the OS stores secrets encrypted per user; the app asks for them, never stores them itself |
| dry-run | ensayo en seco | a full run that computes and shows everything but writes nothing to the outside world |
| idempotency | idempotencia | running the same operation twice leaves the same result as running it once — nothing duplicates |
| upsert | insertar-o-actualizar | insert the row if it's new, update it if it already exists; never duplicate |
| mapping table | tabla de mapeo | the stored correspondence between our codes and another system's ids (PUC ↔ Siigo) |
| backfill | relleno retroactivo | filling a new column with values derived from data that already existed |
| probe | sondeo | a small read-only call made only to learn the real shape of someone else's API |
| parser | analizador / parser | the code that reads a file format (Excel, XML) and turns it into our data |

## Out of scope · Fuera de alcance

> **Resumen (ES).** Lo siguiente **no** es parte de este alcance. Si un agente
> sugiere construir algo de esta lista, no lo hagas — varias de estas cosas las
> hace Siigo, y duplicarlas es competirle a un producto maduro sin necesidad.

Explicitly out of scope — not for this plan:

- **Official books, financial statements and full double-entry bookkeeping** —
  Siigo is the book of record (D-096).
- **Filing anything with the DIAN.** This plan computes figures for review; a
  human files.
- **Electronic payroll (nómina electrónica)** beyond reading the rows the DIAN
  report already brings.
- **Email (IMAP) ingestion of the client's invoice mailbox** — considered and set
  aside in D-097; revisit only if the portal paths fail.
- **Multi-user / cloud sync** (E8 in `docs/plan.md`) and **OCR for scanned PDFs**
  (D-E4-3).

---

## Phase 1 — Foundations: fiscal profile, terceros, board ✅

**Cerrada el 2026-09-22.** Las seis tareas hechas, el Done-when verificado y el
Checkpoint 1 recorrido con @SKuger sobre el tablero real. Dos cosas salieron de
esa revisión y ya están corregidas: el perfil fiscal aparecía entre las etapas del
mes —sugiriendo que se rehace cada mes, y es de la empresa—, y un mes con 50 filas
no conformes se anunciaba como «Al día». La segunda es la firma de defecto de
siempre: la pantalla informando un éxito que no entregó.


> **Resumen (ES) — Fase 1: Cimientos.**
>
> Sin esto nada de lo que viene después puede ser correcto: no se puede calcular
> una retención sin saber qué es la empresa y qué es el tercero, y no se puede
> automatizar lo que no se puede ver. Va primero porque desbloquea todo.
>
> En orden, las tareas:
>
> 1. **1.1** — Agregar el perfil fiscal de la empresa (régimen, responsabilidades,
>    CIIU) con fecha de vigencia, en una migración numerada.
> 2. **1.2** — Agregar los municipios de ICA de la empresa con su tarifa por mil.
> 3. **1.3** — Crear el catálogo de terceros por empresa y llenarlo con lo que ya
>    trae el Excel.
> 4. **1.4** — Consultar el RUT de un tercero desde el catálogo y sellar la fecha.
>    Lo que la página pública no entrega —responsabilidades, CIIU, municipio— se
>    fue a la 2.1, que ya abre sesión en el portal.
> 5. **1.5** — Guardar el estado de cada (empresa, mes) en `contab.db` para poder
>    verlo todo junto.
> 6. **1.6** — Convertir la home de lanzador en tablero: las N empresas con su
>    semáforo del mes.
>
> Decisión tomada (D-100): el catálogo de terceros vive **por empresa**, dentro de
> su propia `.db`. D-003 queda intacta y sin excepciones.

- [x] **1.1** — Add `empresa_perfil_fiscal` to [`apps/core/contab_core/storage.py`](../apps/core/contab_core/storage.py)
      as **migration 4**, following the numbered-migration rules of D-084:
      `regimen` (ordinario · SIMPLE), `responsable_iva`, `periodicidad_iva`
      (bimestral · cuatrimestral), `agente_retefuente`, `agente_reteiva`,
      `agente_reteica`, `autorretenedor_renta`, `gran_contribuyente`, `ciiu`,
      `vigencia_desde`. Expose `get_perfil_fiscal` / `save_perfil_fiscal` RPCs and
      a form in [`apps/desktop/app/pages/empresa.vue`](../apps/desktop/app/pages/empresa.vue).
  - **Why:** every retention in Phase 4 is a function of *what the company is* and
    *what the counterparty is*. Today [`empresa_info`](../apps/core/contab_core/storage.py)
    holds a NIT, a name and two folders — not enough to decide anything. The
    `vigencia_desde` column is not decoration: responsibilities change mid-year,
    and March's accounting must not change because the company became a
    withholding agent in August.
  - 💡 **Heuristic.** A fiscal attribute without a date is a bug waiting for the
    next audit. Anything the State can change by resolution gets a validity date
    the first time you model it — retrofitting dates onto a table that already has
    rows is far more expensive. *(ES: todo atributo fiscal nace con fecha de
    vigencia; ponérsela después, con datos adentro, sale mucho más caro.)*
- [x] **1.2** — Add `empresa_municipio_ica` (municipio, DANE code, tarifa por mil,
      `vigencia_desde`) in the same migration. ICA is municipal: one company can
      withhold at different rates in different municipalities.
- [x] **1.3** — New module `apps/core/contab_core/terceros.py` + `tercero` table
      per empresa. Seed it by upserting the counterparties already present in
      `excel_row` (`nit_emisor` is already projected by D-091).
- [x] **1.4** — Query a tercero's RUT from the catalogue: write `razon_social`
      and `tipo` onto the tercero and seal `consultado_at`, through the plain-HTTP
      path in [`dian_inconsistencias.py`](../apps/core/contab_core/dian_inconsistencias.py).
      What the lookup returns wins over what the Excel imported.
  - **Re-scoped on 2026-09-21, with @SKuger's call.** This task originally also
    demanded *responsabilidades*, *CIIU* and *municipio*. They are **not** in the
    public RUT query's verified field set — NIT, DV, names, razón social and estado
    is what the working scraper extracts — so writing selectors for them would mean
    designing against a page nobody has looked at, the exact failure 2.1 exists to
    prevent. That extraction moved into **2.1**, where a human is already logged
    into the portal and it costs one session instead of two. The columns exist and
    are editable by hand meanwhile.
  - **Decided (D-100):** the enriched catalogue lives **per empresa**, in its own
    `.db`. A central cache in `contab.db` was considered and rejected — it would
    have needed an explicit exception to D-003, and D-003 is worth more than the
    saved lookups. Store `consultado_at` on each tercero row so you can tell a
    stale reading from a fresh one, and copy the tercero's state into the document
    at accrual time (Phase 4) — refreshing the catalogue later must not rewrite
    what justified a withholding six months ago.
- [x] **1.5** — Add `empresa_periodo_estado` to
      [`apps/core/contab_core/program_db.py`](../apps/core/contab_core/program_db.py)
      (`contab.db`): one row per (empresa, periodo) with the stage flags — Excel
      loaded, supports %, validated, accrued, sent to Siigo — updated by the
      operations that already exist. New RPC `tablero`.
  - ⚠️ **Built differently, on purpose (2026-09-21).** `tablero` exists and the
    board works, but **the cache table was not created**. Everything it shows
    already lives in each empresa's own `.db`, so a copy in `contab.db` could only
    add one behaviour: going stale and lying. And a table whose `causado`/`enviado`
    columns nothing writes until Phases 4-5 is the dead schema D-085 removed from
    this repo. It is read live — a few indexed queries per empresa. The table will
    be born in Phase 4, when there is finally something to store that has no other
    home. The reasoning is in the module docstring, not only here.
- [x] **1.6** — Rewrite [`apps/desktop/app/pages/index.vue`](../apps/desktop/app/pages/index.vue)
      from a launcher into the board: every company × current month with its
      status chips and a direct link into the month.
  - **Why:** the accountant's unit of work is *"my 20 companies this month"*, and
    there is no screen in the product that shows it. Every later phase reports
    its progress here, so it is cheaper to build it now than to bolt it on.

✅ **Done-when:**
- With three companies created, `npm run dev` → `http://localhost:3000` shows all
  three with the current month's status; a company with no Excel reads *"sin
  cargar"*, not an empty cell.
- A fiscal profile saved, app closed and reopened, still shows the same values.
- *Consultar RUT* on a tercero brings its razón social from the DIAN and stamps
  the date on the row — and running *Derivar del Excel* again does **not** overwrite
  it. Do both, in that order, and watch the name stay.
- `apps/core` tests and `ruff` pass; `npm run typecheck` passes.
*(ES: el tablero muestra las tres empresas con su estado y lo que le falta a cada
una, el perfil fiscal sobrevive a cerrar la app, y lo que trae el RUT no lo pisa
volver a derivar del Excel. Tests y typecheck en verde.)*

🚦 **Checkpoint 1 — recorrido el 2026-09-22.** Show @SKuger: the board in the browser with three real
companies, the `empresa_perfil_fiscal` rows queried live with `sqlite3`, and the
pushed commits. Questions:
1. Why does every fiscal attribute carry `vigencia_desde`, and what breaks in
   Phase 4 if it doesn't? *(ES: ¿por qué cada atributo fiscal lleva fecha de
   vigencia, y qué se rompe en la Fase 4 si no la lleva?)*
2. Walk the board live and explain where each status flag is written from — which
   operation sets it, and what happens if that operation is cancelled halfway.
   *(ES: recorre el tablero y explica qué operación escribe cada estado y qué pasa
   si se cancela a mitad de camino.)*

---

## Phase 2 — DIAN ingestion: token, robot, manual

> **Resumen (ES) — Fase 2: Entrada automática desde la DIAN.**
>
> Aquí empieza la automatización de verdad: entrar al portal, obtener el token y
> exportar los listados de todas las empresas sin escribir una clave. Tres caminos
> hacia la misma interfaz (D-097), y la subida manual se queda como piso.
>
> En orden, las tareas:
>
> 1. **2.1** — Sesión de reconocimiento contra el portal real y documentarla; no se
>    escribe código antes de esto. Incluye leer qué campos del RUT entrega de
>    verdad —responsabilidades, CIIU, municipio— que es lo que quedó pendiente de
>    la 1.4.
> 2. **2.2** — Bóveda de credenciales en el llavero del sistema operativo, una
>    entrada por empresa, nunca en la base ni en el log.
> 3. **2.3** — `dian_portal.py` con una interfaz y tres implementaciones: token,
>    robot y manual.
> 4. **2.4** — El camino `robot` reusa el navegador persistente que ya existe en
>    `apps/dian-rut`.
> 5. **2.5** — Trabajo en segundo plano "bajar el mes de todas las empresas", con
>    progreso, reintentos y bitácora.
> 6. **2.6** — Descargar los adjuntos (XML y PDF) a la carpeta de soportes del mes.
> 7. **2.7** — Botón en el tablero y compuerta de aprobación antes de importar.
>
> Decisión tomada (D-101): **las corridas siempre las dispara el contador.** No se
> construye programador ni ejecución nocturna.

**Decided (D-101): every run is triggered by the accountant.** No scheduler, no
overnight execution — nothing touches a client's DIAN account without a human
present. The stored credentials (D-098) are there so he doesn't type twenty
passwords per run, not so the machine can run without him. *(ES: toda corrida la
dispara el contador; las claves guardadas son para no teclear veinte veces, no
para correr sin él.)*

- [ ] **2.1** — Recon session against the real portal with one company's
      credentials. Write `docs/dian-portal.md`: the login flow, what token is
      issued and how long it lasts, the exact call behind the listado's *Exportar*
      button, and whether the XML/PDF of each document can be downloaded from
      there. **No module is designed before this file exists.**
      While that session is open, also settle what the RUT consultation actually
      returns — **responsabilidades, CIIU and municipio** (inherited from 1.4) — and
      wire them into `terceros.actualizar_desde_rut`, whose columns are already
      waiting. Two questions, one login.
  - 💡 **Heuristic.** The portal is a contract nobody signed with you. Write the
    reconnaissance into a file, not into the head of whoever ran it — when the
    portal changes (and it will), the diff between that file and reality is the
    whole debugging session. *(ES: el reconocimiento va a un archivo, no a la
    memoria de quien lo hizo; cuando el portal cambie, ese archivo es la
    depuración.)*
- [ ] **2.2** — `apps/core/contab_core/vault.py`: one credential entry per NIT in
      the OS keyring (Windows Credential Manager). Add a test that asserts a
      credential never appears in a log line, an RPC error payload or a job
      result.
  - **Why:** from this phase on, Contab custodies the DIAN credentials of third
    parties. The existing failure mode in this codebase is instructive: D-083
    exists because errors were being swallowed, and D-089 because the local API
    was open. A secret that leaks into a log is not recoverable — the log gets
    copied into issues, backups and screenshots.
- [ ] **2.3** — `apps/core/contab_core/dian_portal.py`: one interface, three
      implementations — `token` (direct HTTP, the fast path), `robot` (Playwright,
      the one that survives Cloudflare and 2FA), `manual` (what exists today).
      The path is configurable per empresa and falls back in that order.
- [ ] **2.4** — The `robot` path reuses the persistent browser context and the CDP
      mode already working in [`apps/dian-rut/scraper.py`](../apps/dian-rut/scraper.py),
      instead of launching a second browser stack.
- [ ] **2.5** — `ingesta_mes_async` job over [`apps/core/contab_core/jobs.py`](../apps/core/contab_core/jobs.py)
      — per-company progress, retries, polite pause between companies,
      cancellable — plus an `ingesta_run` log table: when it ran, by which path,
      how many documents, which companies failed and why.
- [ ] **2.6** — Download each document's attachments (XML, PDF) into that month's
      support folder, so V1 sees them immediately and Phase 3 has XML to parse.
- [ ] **2.7** — *"Bajar el mes"* on the board, with a per-company result summary
      that the accountant approves **before** anything is imported.

✅ **Done-when:**
- One run over three companies, one of them with a deliberately wrong password:
  the other two import, and the failed one is named with a message that says what
  to do — not a stack trace.
- `grep -ri` over the `logs/` folder and over the job results finds **no**
  credential.
- Running the same month twice does not create a second load for it.
- The manual upload still works with the sidecar's portal path disabled.
- A tercero shows *responsabilidades* and *CIIU* that came from the RUT — you can
  point at the field and say where it came from — not typed by hand (the debt 1.4
  handed over).
*(ES: tres empresas en una corrida, una con clave mala a propósito; las otras dos
entran, ninguna clave aparece en los logs, repetir el mes no duplica la carga, y
la subida manual sigue funcionando.)*

🚦 **Checkpoint 2.** Show @SKuger: the run over three real companies from the
board, `docs/dian-portal.md`, and the keyring entry (its existence — **never its
value**). Questions:
1. Why do three ingestion paths exist instead of the fastest one, and what is the
   decision rule for falling back? *(ES: ¿por qué tres caminos y no solo el más
   rápido, y cuál es la regla para caerse al siguiente?)*
2. Walk a failed company live: where is the failure recorded, what does the
   accountant see, and what does he do next? *(ES: recorre en vivo una empresa que
   falló: dónde queda registrado, qué ve el contador y qué hace después.)*

---

## Phase 3 — The XML as the source of truth

> **Resumen (ES) — Fase 3: el XML manda.**
>
> Hoy el PDF se abre solo para sacar 96 caracteres. El XML UBL trae el documento
> entero: líneas, impuestos por tarifa, retenciones y la referencia de la nota
> crédito a su factura. Sin XML, causar es adivinar desde el total.
>
> En orden, las tareas:
>
> 1. **3.1** — Escribir el parser de XML UBL con el mismo patrón de caché que el de
>    CUFE, incluida la re-lectura cuando el parser mejore.
> 2. **3.2** — Crear las tablas de documento, línea e impuesto, y las referencias
>    entre documentos.
> 3. **3.3** — V3 pasa de inferir la tarifa a contrastarla con la declarada.
> 4. **3.4** — Agregar las validaciones que solo el XML permite: duplicados, nota
>    crédito sin origen, rezagados y RUT cancelado.
> 5. **3.5** — Mostrar el detalle por línea en la página de la carga.

- [ ] **3.1** — `apps/core/contab_core/xml_ubl.py`: parser for `AttachedDocument`,
      `Invoice`, `CreditNote`, `DebitNote` and the documento soporte (UBL 2.1),
      cached by `(archivo, mtime, tamaño, parser_version)` — the same shape as
      [`pdf_cufe.py`](../apps/core/contab_core/pdf_cufe.py), including the version
      bump that re-reads old entries (D-067).
- [ ] **3.2** — Migration 5: `documento`, `documento_linea`, `documento_impuesto`
      (tipo, tarifa, base, valor) and the document-to-document references.
  - **Why:** the Excel stays the source of the table the accountant sees (D-039,
    D-064). The XML is a **layer attached to it**, never a replacement for
    `data_json`. If you replace it, every column the accountant recognises moves,
    and the trust built in E1 goes with it.
- [ ] **3.3** — V3 in [`apps/core/contab_core/validations.py`](../apps/core/contab_core/validations.py)
      contrasts the **declared** rate when XML exists; keep the D-093 inference
      for rows without XML.
- [ ] **3.4** — New validations, each one only possible with the XML: duplicate
      document, credit note with no origin invoice, *rezagados* (issued in one
      period, received in another — relevant because of the three-period window of
      art. 496 ET, already noted in [`docs/glosario.md`](../docs/glosario.md)),
      and issuer with a cancelled RUT.
- [ ] **3.5** — Show the line-level detail in [`apps/desktop/app/pages/load.vue`](../apps/desktop/app/pages/load.vue),
      reusing the composable split from D-092.

✅ **Done-when:**
- The sample documents in `docs/samples/` parse into lines and taxes with their
  XML counterparts, and the totals match the Excel row to the cent.
- A month **without** XML behaves exactly as today — run the existing suite and
  see it green, that's the regression guard.
- Each new validation fires on a deliberately seeded case, and you can name the
  row it caught.
*(ES: las muestras parsean y cuadran al centavo; un mes sin XML se comporta igual
que hoy; cada validación nueva caza un caso sembrado a propósito.)*

---

## Phase 4 — Assisted accounting: rules and withholdings

> **Resumen (ES) — Fase 4: causación asistida.**
>
> El corazón del ahorro de tiempo. El 80% de los documentos de un mes son los
> mismos proveedores del mes anterior; lo que el contador hizo con ese NIT la vez
> pasada es la propuesta de esta vez. La pantalla del mes debe decir: «412
> documentos · 380 con regla conocida [aprobar todos] · 32 nuevos [decidir]».
>
> En orden, las tareas:
>
> 1. **4.1** — Crear las tablas de parámetros: UVT por año, conceptos de retención
>    con tarifa y base mínima, y tarifas de ICA — todas editables desde la UI.
> 2. **4.2** — Escribir el motor de retenciones que combina el perfil de la empresa,
>    el del tercero y el documento.
> 3. **4.3** — Crear las reglas de causación (tercero + concepto → cuenta PUC y
>    centro de costo).
> 4. **4.4** — Generar la propuesta de asiento de todo el mes.
> 5. **4.5** — Bandeja de aprobación: lote para lo conocido, uno por uno para lo
>    nuevo, y cada decisión nueva se vuelve regla.
>
> Decisión tomada (D-102): las tarifas, la UVT y las bases mínimas **se importan
> de un Excel del contador**, igual que el PUC. Un agente no las siembra.

**Decided (D-102): the tax tables are imported from the accountant's own Excel**,
the same way the PUC already is. Rates, minimum bases in UVT and the UVT value are
law and change by decree; an agent must **not** seed them from memory or from a
web search, and updating them each year is re-uploading the file — not a release.
*(ES: las tarifas se importan de tu Excel, igual que el PUC; actualizarlas cada año
es volver a subir el archivo, no publicar una versión.)*

- [ ] **4.1** — Parameter tables, all dated and all editable from the UI after
      import: `uvt` (año, valor), `retencion_concepto` (concepto, tarifa, base
      mínima en UVT, cuenta PUC, vigencia), `ica_tarifa` (municipio, actividad, por
      mil, vigencia). The importer follows the shape of
      [`puc.py`](../apps/core/contab_core/puc.py) — header aliases, upsert by key,
      manual rows preserved. First get a real sample of that Excel from @SKuger and
      write `docs/tarifas-structure.md` against it, the way
      [`docs/excel-structure.md`](../docs/excel-structure.md) was written for the
      DIAN report.
  - 💡 **Heuristic.** Tax rates are data, not code. If a decree forces a release,
    the design is wrong: every January you would be shipping a version to change
    a number, and every client on an older version would be computing last year's
    tax. *(ES: las tarifas son datos, no código; si un decreto obliga a desplegar,
    el diseño está mal.)*
- [ ] **4.2** — `apps/core/contab_core/retenciones.py`: company profile (1.1) +
      tercero profile (1.3/1.4) + document (Phase 3) → retención en la fuente,
      ReteIVA, ReteICA and autorretención where they apply.
- [ ] **4.3** — `regla_causacion` (tercero · concepto · pattern → cuenta PUC +
      centro de costo, with validity) and `apps/core/contab_core/causacion.py`.
      The chart of accounts is already there: [`puc.py`](../apps/core/contab_core/puc.py)
      imports it per company.
- [ ] **4.4** — Generate `asiento_propuesto` for a whole month as a background job
      (same `jobs.py` pattern — this one has no duration ceiling either).
- [ ] **4.5** — The approval tray in the frontend: known documents approved in
      bulk, new ones decided one by one, and **every new decision writes or
      refines a rule**.
  - **Why:** this is the loop that makes month two cheap. Without the
    write-back, the accountant re-decides the same supplier every month and the
    product is just a prettier spreadsheet.

✅ **Done-when:**
- On a real company's second month, at least 80% of documents are proposed and
  approved without edits — measure it, don't estimate it: the tray shows the
  count.
- Changing a rate in the UI changes next month's proposal **without touching
  code** — do it, re-run, and see the number move.
- A document whose tercero is a withholding agent and one whose tercero is not
  produce different retentions from the same invoice amount.
*(ES: el segundo mes propone ≥80% sin correcciones, cambiar una tarifa en la UI
cambia la propuesta sin tocar código, y dos terceros distintos sobre la misma
factura dan retenciones distintas.)*

---

## Phase 5 — The Siigo bridge and reverse reconciliation

> **Resumen (ES) — Fase 5: el puente a Siigo.**
>
> Aquí se cierra el camino completo: lo aprobado sale a Siigo Nube por API, sin
> tecleo, sin duplicados, y vuelve el reporte que hoy nadie hace bien — qué dice la
> DIAN que recibiste contra qué está realmente contabilizado.
>
> En orden, las tareas:
>
> El contrato ya está verificado (D-103): `POST https://api.siigo.com/auth` con
> `username` + `access_key` devuelve un JWT de 24 horas, el header `Partner-Id` va
> en todas las llamadas, y cada documento sale **al recurso que le corresponde por
> tipo** — factura recibida a `/purchases`, documento soporte con no obligados a
> `/purchase-support-documents`, y `/journals` solo para lo que no encaje.
>
> En orden, las tareas:
>
> 1. **5.1** — Pedir la credencial de prueba a soporte y sondear los tres recursos
>    con ella; no hay sandbox público.
> 2. **5.2** — Modelo interno de asiento + un adaptador por tipo de documento,
>    pensados como capa: Siigo es el primero, no el único.
> 3. **5.3** — Mapear centros de costo, impuestos y tipos de comprobante. Las
>    cuentas NO necesitan mapeo: Siigo las recibe por código PUC.
> 4. **5.4** — Registrar cada envío con su CUFE en nuestra tabla, que es la única
>    autoridad: Siigo no tiene campo de referencia externa.
> 5. **5.5** — Ensayo en seco obligatorio antes del primer envío real de cada
>    empresa.
> 6. **5.6** — Reconciliación inversa a tres columnas, leyendo por rango de fechas
>    con paginación.

**Decided (D-103): the contract is verified and the routing is by document type.**
`POST https://api.siigo.com/auth` with `username` + `access_key` returns a JWT that
lasts 24 h (`expires_in: 86400`); `Partner-Id` is required on every call;
credentials come from Siigo Nube → *Alianzas → Mi Credencial API*. Received
invoices go to `/purchases`, *documento soporte con no obligados* to
`/purchase-support-documents`, and `/journals` is the fallback for what fits
neither. What this buys: Siigo applies **each company's own configuration**
(supplier, taxes, withholdings) when it books a purchase, so Contab does not have
to replicate that setup per company. What it costs, accepted knowingly: each
company's Siigo configuration has to be right, and 5.5's dry-run is where you find
out it isn't. *(ES: el envío va por tipo de documento; Siigo aplica la
configuración de cada empresa, y el ensayo en seco es donde se descubre si esa
configuración está mal.)*

- [ ] **5.1** — Request the test credential from `soporteapi@siigo.com` with the
      company's NIT — **there is no public sandbox**. Then probe: `POST /auth`,
      read the catalogs (taxes, cost centers, document types, terceros) and one
      existing journal, and write `docs/siigo-api.md` with what actually came
      back — not with what the documentation says.
  - 💡 **Heuristic.** When you depend on someone else's API, confirm the exact
    field you need exists before you write code against it. This phase already
    proved it: reading the docs found that a Siigo entry has **no external-
    reference field**, which rewrote the whole idempotency design (5.4) before a
    line of it existed. *(ES: confirma que el campo existe antes de escribir código
    contra él — leer la doc ya cambió el diseño de 5.4 antes de escribirlo.)*
- [ ] **5.2** — `apps/core/contab_core/siigo/`: one internal asiento model and
      **one adapter per document type** (`/purchases`,
      `/purchase-support-documents`, `/journals`). Design them **as a layer** —
      World Office, Helisa and Contapyme come later without touching the engine.
      Contab is a product, not a suit tailored to the first owner.
- [ ] **5.3** — Mapping for **cost centers, taxes and document types only**.
      Accounts need no mapping: a journal item references the account by `code`
      (`"11050501"`) plus `movement` (Debit/Credit), and `cost_center` by its
      numeric id.
  - **Why:** the PUC that [`puc.py`](../apps/core/contab_core/puc.py) already
    imports has exactly the shape of Siigo's chart of accounts, and Siigo takes the
    code directly — so what looked like the heaviest table in this phase is a
    pass-through. Verify it with the probe before building any mapping UI for
    accounts.
- [ ] **5.4** — `siigo_envio` (cufe, tipo, remote id, status, payload, response).
      **Siigo has no external-reference field**, so this table is the only
      authority on what has already left. Stamp the CUFE into `observations` as
      well, so a human reading the entry inside Siigo can trace it back, and verify
      after the fact by listing with `date_start`/`date_end` and paginating —
      never by asking Siigo for "the document with this CUFE", because it cannot
      answer that.
- [ ] **5.5** — Mandatory dry-run before the first real send of each company: it
      computes and shows the whole batch and writes nothing.
- [ ] **5.6** — Reverse reconciliation: list what Siigo holds for the period
      (`date_start`/`date_end`, `page`/`page_size`, and the `total_results` the
      response carries) across the three resources, and cross it against the DIAN
      report. Three columns — *in DIAN and in Siigo* · *only in DIAN* (missing
      accrual) · *only in Siigo* (booked with no electronic document).
  - **Why:** this is the report that answers the question the accountant cannot
    answer today, and the reason D-099 chose the API over a flat import file — a
    file can be written, but it cannot be read back.

✅ **Done-when:**
- One real month of one company is approved, sent, and the reconciliation returns
  zero differences — open Siigo and see the documents there.
- Running the send a second time creates **nothing** new: same count in
  `siigo_envio` and the same `total_results` when you list the period in Siigo.
- A seeded document that exists in Siigo but not in the DIAN report shows up in
  the third column.
*(ES: un mes real enviado y reconciliado en cero, repetir el envío no crea nada, y
un documento sembrado solo en Siigo aparece en la tercera columna.)*

🚦 **Checkpoint 3 — the core loop.** This is the MVP exit: the month goes from the
DIAN to Siigo with the accountant approving, not typing. Show @SKuger: one real
company's month end to end — download, validate, accrue, send — and the
reconciliation report. Walk it live, don't narrate it. Questions:
1. Why is idempotency keyed on the CUFE and not on our own row id, and what
   breaks if the month is reopened after a send? *(ES: ¿por qué la idempotencia va
   por CUFE y no por nuestro id, y qué se rompe si el mes se reabre después de
   enviar?)*
2. Show a document that reconciliation put in *"only in Siigo"* and explain the
   three ways it could have got there. *(ES: muestra un documento que quedó en
   «solo en Siigo» y explica las tres formas en que pudo llegar ahí.)*
3. What in this chain still needs a human, and what would it cost to remove that
   human — is it worth it? *(ES: ¿qué parte de la cadena todavía necesita un
   humano, cuánto costaría quitarlo y vale la pena?)*

---

## Phase 6 — The client loop and the legal clock

> **Resumen (ES) — Fase 6: el ciclo con el cliente y los plazos.**
>
> Lo que hoy se hace persiguiendo por WhatsApp. Contab ya sabe qué soportes faltan;
> falta entregar esa lista y vigilar los plazos que hoy no vigila nadie.
>
> En orden, las tareas:
>
> 1. **6.1** — Convertir la lista de faltantes en una solicitud al cliente, con
>    registro de a quién se le pidió qué y cuándo.
> 2. **6.2** — Semáforo de los 3 días hábiles para aceptar o rechazar una factura
>    recibida.
> 3. **6.3** — Calendario tributario por últimos dígitos del NIT, con alertas en el
>    tablero.

- [ ] **6.1** — Turn `export_missing_supports` into a request: the list goes out
      by email or WhatsApp and the app records who was asked for what, and when.
- [ ] **6.2** — Three-business-day semaphore for acceptance/rejection, computed
      from `Fecha Recepción` — the column [`docs/glosario.md`](../docs/glosario.md)
      already flags as critical and that nothing in the product watches today.
  - **Why:** an invoice tacitly accepted cannot be rejected afterwards. This is
    one of the few places where the software missing a date costs the client real
    money.
- [ ] **6.3** — Tax calendar by the NIT's last digits, filtered by the obligations
      in the fiscal profile (1.1), surfaced as alerts on the board.

✅ **Done-when:**
- A month with missing supports produces a request you can actually send, and the
  app shows it was sent.
- A document received 2 business days ago shows amber; 4 days ago shows the
  window closed — check both against a real received date.
*(ES: la solicitud de soportes se puede enviar de verdad y queda registrada, y el
semáforo de los 3 días hábiles distingue una factura de hace 2 días de una de
hace 4.)*

---

## Phase 7 — Compliance figures

> **Resumen (ES) — Fase 7: cifras de cumplimiento.**
>
> Como Siigo es el libro (D-096), esta fase entrega **cifras para revisar, no
> documentos para presentar**. La exógena sale casi gratis sobre la causación de la
> Fase 4, y es el dolor anual más grande.
>
> En orden, las tareas:
>
> 1. **7.1** — Prellenar las cifras de los formularios 300 (IVA) y 350 (retención)
>    desde lo causado.
> 2. **7.2** — Generar los formatos de información exógena desde la misma base.

- [ ] **7.1** — Figures for forms 300 (IVA) and 350 (retención en la fuente) from
      the accrued month, presented as review support. **Nothing is filed from
      Contab.**
- [ ] **7.2** — Exógena formats (1001, 1003, 1005, 1007, 1008, 1009, 1010, 1011)
      generated from the Phase 4 data.

✅ **Done-when:**
- The 350 figure for one real month matches what the accountant computed by hand —
  he checks it, you don't assert it.
- One exógena format exports and opens in the DIAN's validation tool without
  structural errors.
*(ES: la cifra del 350 coincide con la que el contador sacó a mano —la revisa él—,
y un formato de exógena abre en el validador de la DIAN sin errores de
estructura.)*

🚦 **Checkpoint 4 — exit.** Show @SKuger: one company carried through a full month
in one sitting, from *"bajar el mes"* to the reconciliation and the 350 figure.
This plan is not archived until Checkpoints 1, 2 and 3 have each been walked.
Questions:
1. Where is the remaining manual work, and is that where it *should* be? *(ES:
   ¿dónde quedó el trabajo manual y es ahí donde debe estar?)*
2. If the DIAN changed its portal tomorrow, what exactly stops working and what
   keeps working? *(ES: si mañana la DIAN cambia el portal, ¿qué deja de funcionar
   y qué sigue funcionando?)*

---

## Decisions · Decisiones

> Collected 🛑 markers that are still open, and resolved decisions logged below
> for traceability.

**Open:**

- **Inputs @SKuger still owes the plan** (not decisions, deliveries): the tax-rate
  Excel that 4.1 imports, and the Siigo test credential that 5.1 probes with —
  requested from `soporteapi@siigo.com` with the company's NIT.

**Resolved during planning (2026-09-21):**

- **No closing date.** The plan starts today and advances phase by phase; there is
  no `target`. The owner's call, made explicitly: if it takes a month, fine; if it
  takes three, fine. This deviates from the frontmatter schema, which expects a
  date — the deviation is deliberate and recorded here so nobody "fixes" it by
  inventing one. The pace is governed by the 🚦 checkpoints instead.

- **D-100 — The tercero catalogue lives per empresa**, inside its own `.db`. A
  central cache in `contab.db` was considered and rejected: it would have required
  an explicit exception to D-003, which is worth more than the saved lookups.
- **D-101 — Every ingestion run is triggered by the accountant.** No scheduler, no
  overnight execution. The stored credentials (D-098) exist so he doesn't type
  twenty passwords per run, not so the machine can run without him.
- **D-102 — The tax tables are imported from the accountant's own Excel**, the way
  the PUC already is. Updating them each year is re-uploading the file, not
  shipping a release.
- **D-103 — The Siigo contract is verified, and posting is routed by document
  type**: `/purchases` for received invoices, `/purchase-support-documents` for the
  documento soporte, `/journals` as the fallback. Auth is `POST /auth` with
  `username` + `access_key` → JWT valid 24 h, with `Partner-Id` on every call.
  Accounts travel by PUC `code`, so they need no mapping table; there is **no
  external-reference field**, so idempotency lives in our `siigo_envio` table and
  verification is done by listing the period.

- **D-096 — Contab is the bridge; Siigo stays the book of record.** Contab
  controls, accrues and posts; Siigo keeps the books and produces the reports.
  This parks E6 (comprobantes) and E7 (financial reports) in `docs/plan.md`.
- **D-097 — Three ingestion paths**: portal robot, portal token, and the manual
  upload kept as the floor. IMAP ingestion of the client's mailbox considered and
  set aside.
- **D-098 — DIAN credentials are stored, encrypted, on the machine** (OS keyring),
  which is what makes unattended runs technically possible.
- **D-099 — Siigo Nube via API**, not the flat import file — chosen for the
  reverse reconciliation, which a file cannot give.

## Risks · Riesgos

> **Resumen (ES).** Los riesgos reales son tres: que la DIAN cambie el portal, que
> el contrato de Siigo no sea el que suponemos, y que estemos custodiando claves
> fiscales ajenas. Cada uno tiene su mitigación concreta y en qué fase ocurre.

- **The DIAN changes the portal** → ingestion breaks mid-month. **Mitigation:**
  three paths (Phase 2.3) with the manual upload as the floor, plus
  `docs/dian-portal.md` (2.1) as the diff against reality when it happens.
- **Cloudflare / second factor blocks the automated path** → the token path stops
  working. **Mitigation:** the `robot` path with the persistent context that
  already works in `apps/dian-rut` (2.4).
- **The Siigo contract is not what we assume** → Phase 5 is redesigned late.
  **Mitigation:** the probe in 5.1 happens *before* 5.2, and the adapter layer
  (5.2) keeps the rest of the system away from Siigo's shape.
- **Custody of third parties' fiscal credentials** → a leak is not recoverable.
  **Mitigation:** OS keyring only (2.2), the no-secret-in-logs test (2.2), and the
  installer signature that D-059 left pending — a user about to hand over his
  clients' DIAN passwords should not be met by a SmartScreen warning.
- **Tax rates change by decree** → silently wrong withholdings. **Mitigation:**
  parameters as dated data editable from the UI (4.1), never constants.
- **The 80% proposal target is not met** → Phase 4 saves less time than expected.
  **Mitigation:** measure it in the tray on a real second month before building
  Phase 5 on top of it; if it is far below, the rule granularity is wrong and that
  is cheaper to fix then than after the bridge exists.

## References

- [`docs/plan.md`](../docs/plan.md) — the E1–E11 delivery roadmap this plan
  complements. E6 and E7 are parked by D-096.
- [`docs/decisions.md`](../docs/decisions.md) — D-001…D-099; the four decisions
  above are logged there.
- [`docs/glosario.md`](../docs/glosario.md) — Colombian accounting and DIAN terms
  (legal deadlines, UBL codes, document types).
- [`docs/excel-structure.md`](../docs/excel-structure.md) — the verified structure
  of the DIAN Excel this plan automates the download of.
- [`CLAUDE.md`](../CLAUDE.md) — immutable decisions and working rules for this
  repo.
- `.github/templates/plan-template.md` and `.github/agents/plan-craft.agent.md`
  in `Interval-Col/.github` — the authoring model this plan follows.
- Siigo API, verified 2026-09-21 for D-103:
  [authentication](https://developers.siigo.com/docs/siigoapi/autenticacion/autenticacion) ·
  [resource index](https://developers.siigo.com/docs/siigoapi/) ·
  [list journal entries](https://developers.siigo.com/docs/siigoapi/journal-entry/3-get-journals/) ·
  [generating API credentials](https://siigonube.portaldeclientes.siigo.com/credenciales-api/) ·
  [the Partner-Id header](https://siigonube.portaldeclientes.siigo.com/campo-oblibatorio-para-siigo-api-partner-id/)
