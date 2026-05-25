# Tax Evidence Vault — PRD

## Original problem statement
Build Stage 1 of a private tax evidence management app to help gather and organise evidence for overdue Australian tax returns (FY2024 + FY2025). Upload → categorise → save to Drive → register → missing evidence tracker. No tax calculations, no AI extraction in Stage 1.

## User persona
Single private user (the owner). Single-user, no auth. Australian taxpayer with multiple income sources (PAYG from 3 employers per FY, Airbnb, Waggrakine rental, Heathridge property, Revive Pty Ltd) preparing evidence packs for accountant.

## User decisions captured
- Google Drive: **Full OAuth** (Drive-only storage)
- Auth: **None** (single private user)
- Storage: **Google Drive only** — uploads rejected if Drive not connected
- Design: **Clean / minimal / spreadsheet-like**
- Accountant summary export: **PDF** (reportlab)

## Architecture
- **Backend**: FastAPI + Motor (MongoDB). Single file `/app/backend/server.py`. Drive OAuth via `google-auth-oauthlib` + `googleapiclient`. PDF via `reportlab`.
- **Frontend**: React 19 + react-router-dom v7 + shadcn UI + sonner toasts + lucide icons. Tailwind 3.
- Single-user data is keyed by `SINGLETON_KEY="default"` (drive_credentials, drive_config collections).
- Mongo collections: `documents`, `figures`, `missing_items`, `drive_credentials`, `drive_config`.
- All routes prefixed `/api`. Drive callback `/api/drive/callback` configured in Google Cloud Console.

## What's been implemented (Stage 1 — Feb 2026)
- Dashboard: FY2024/FY2025 summary cards with PAYG income preloaded totals (FY2024 $27,388 / FY2025 $75,863), category cards (ATO, Airbnb, Waggrakine Rental, Heathridge, Revive, Bank Statements), Accountant Review Required card, Missing Documents card (count of 30 preloaded items).
- Document upload: multipart with name, tax year, category, notes, accountant_review flag. Auto-routes to correct numbered Drive subfolder. Rejects upload if Drive not connected.
- Evidence Register: searchable, filterable (category/year/review), spreadsheet-style dense table; click row to open detail dialog.
- Document Detail dialog: edit metadata + add/delete manual figures (income/tax_withheld/expense/interest/liability/other) + Drive link.
- Missing Evidence Tracker: 30 preloaded items grouped by priority (Critical 16, Important 9, Later 5). Inline status update, add custom items.
- Reports: CSV exports (Evidence Register, Missing Evidence, Documents by Category) + PDF Accountant Summary (documents, key figures with subtotals, outstanding evidence, review items).
- Settings: Google Drive connect → callback → initialize folder structure (parent "Tax Evidence Vault" + 11 numbered subfolders). Lists each subfolder with direct open link.
- Auto-seed on backend startup: 30 missing items + 6 PAYG figures.
- Backend tested 22/22 pytest cases (iteration_1.json).

## What's been implemented (Stage 2 + Quick Fixes — Feb 2026)
- Stage 2 Missing Evidence Tracker v2 with intelligent auto-matching.
- Hybrid AI classifier (Gemini 1.5 Flash → Claude Sonnet 4.5) via Emergent Universal Key.
- Bulk drag-and-drop uploads + live UploadQueue.
- **Missing Evidence page UX (Feb 25, 2026)**:
  - Per-row "Upload" button on every Outstanding / Possible Match / Accountant Review row + on the "Next best document" banner.
  - Top "Have documents ready?" quick-upload bar with file & folder pickers.
  - Italic "Need: …" canonical helper text under every item (sourced from seed `notes`, separated from user-editable `notes_user`).
  - **Export CSV** link (→ `/api/reports/missing-evidence.csv`) in header, now including matched-document columns + user notes.
  - **Ctrl/⌘+U** keyboard shortcut opens the quick-upload picker.
  - Embedded `<UploadQueue>` shows live processing + AI auto-match status without leaving the page.
  - Backend PATCH `/api/missing-evidence/{id}` now accepts `notes_user` so user notes never overwrite the canonical seed helper text.
- **Stage 3 — Accountant Pack exports (Feb 25, 2026)**:
  - `/api/reports/evidence-register.csv` rewritten with 25 columns: document type, risk level, counterparty, date range, AI-verified headline figures (with confidence), manual figures, AI model used, AI cost, Drive folder/link, accountant review reason, status, notes.
  - New `/api/reports/accountant-summary.txt` — plain-text snapshot grouping totals by category, tax year, risk; review items and outstanding evidence by priority. Email-friendly companion to the existing PDF.
  - Reports page now lists 5 downloads (Evidence Register CSV, Missing Evidence CSV, Accountant Summary PDF, Accountant Summary TXT, Documents by Category CSV).
  - Inline "Export CSV" + "Accountant summary" buttons in the Evidence Register header.
  - Sidebar footer updated: "Stage 1 + 2 · Hybrid AI".
- **Stage 4 — Production hardening (Feb 25, 2026)**:
  - New `/app/backend/error_codes.py` — `ErrorCode` enum + `ERROR_MESSAGES` map + `classify_ai_error()` / `classify_drive_error()` helpers; queue rows now carry a stable `error_code` field.
  - Hard 100 MB file cap (`MAX_UPLOAD_BYTES`); oversize and 0-byte uploads land directly in `Error` state with `FILE_TOO_LARGE` / `FILE_EMPTY` codes — no worker time wasted.
  - Pipeline crash handler now sets `error_code=UNEXPECTED_ERROR`; staging-missing path sets `STAGING_MISSING`; successful rows surface non-fatal `AI_*` / `DRIVE_*` codes as informational hints.
  - New `POST /api/uploads/queue/{qid}/retry` — re-queues `Error`/`Cancelled` rows (404 if missing, 409 if staging file gone, 400 if status wrong).
  - New `POST /api/uploads/recover-stuck` — resets items stuck >10 min in `Uploading`/`Reading`/`Classifying` back to `Queued`; fired from `<Layout>` on app load.
  - Existing endpoints kept: cancel-one, cancel-all, clear-finished, duplicate-decision.
  - `UploadQueue.jsx` rewritten to render `error_code` → action mapping: **Retry** for transient errors, **Retry (wait 60s)** countdown for `AI_RATE_LIMIT`, **Reconnect Drive** link for `DRIVE_DISCONNECTED`, banner showing total error count.
  - **Note**: the spec's wholesale `upload_pipeline.py` replacement was rejected — it contained stub Drive code (`drive_file_id = "..."`) and assumed an auth layer this single-user app doesn't have. Stage 4 hardening was integrated surgically into the existing working pipeline instead.

## Backlog / deferred
### P1 — Stage 2 candidates
- AI extraction of figures from uploaded PDFs/images (currently manual only — by Stage 1 design)
- Bulk upload (drag-drop multiple files at once)
- Local fallback storage when Drive is offline
- "Final Accountant Pack" zip generator (combines reports + key docs)
- Per-document version history
- Multi-user mode + JWT auth

### P2
- Tax calculations & ATO lodgement helpers (explicitly out of Stage 1 scope per user)
- OCR text search within uploaded documents
- Inline Drive folder preview / file picker

## Next tasks
- Stage 2: AI-powered figure extraction (Claude Sonnet vision for PDFs/images) once user approves Stage 1.
- Tighten Pydantic validation with Enums for figure_type/status/accountant_review.
- Split server.py into routers (drive/documents/reports/seed) for maintainability if app grows.
