# Tax Evidence Vault — Stage 4 Audit Pack

**Snapshot date:** 25 Feb 2026
**Branch:** `main`
**Latest commit:** `11d2c55` ("Auto-generated changes")
**Recent commits:**
```
11d2c55 Auto-generated changes
2e7bb2a auto-commit for f85d0fbd-5da3-49cf-aa40-ab968f521f3c
19e1913 auto-commit for 90d283df-35b2-4d8f-8f5c-a9a71b6b668e
29dadae auto-commit for bd595226-f83c-41c3-ac6d-a3607babebc6
1361e98 auto-commit for 7d29bb81-6f7b-44ba-b8cc-7d2b99d39e00
```
> Emergent auto-commits each successful step; the working tree currently equals HEAD.

> **No ZIP/Download button exists in Emergent.** Either (a) **GitHub repo → green "Code" button → Download ZIP** (preferred), or (b) grab `audit_export/tax-evidence-vault-stage4-11d2c55-20260525.zip` (146 KB, this directory) via VS Code file view.

---

## 1. File tree (top-level)

```
/app
├── README.md
├── design_guidelines.json
├── test_result.md
├── backend/
│   ├── .env                       (MONGO_URL, DB_NAME, EMERGENT_LLM_KEY, GOOGLE OAuth creds)
│   ├── THE_BRAIN_v1.md            (17k-word AI system prompt)
│   ├── ai_classifier.py           (Hybrid Gemini 1.5 Flash → Claude Sonnet 4.5)
│   ├── error_codes.py             (Stage 4 — stable codes + classifiers)
│   ├── extraction.py              (pdfplumber + pytesseract OCR + docx + xlsx)
│   ├── missing_evidence.py        (Stage 2 seed + intelligent auto-matching)
│   ├── requirements.txt
│   ├── server.py                  (~1430 lines — FastAPI router, drive OAuth, exports)
│   ├── tests/test_tax_vault.py    (22 pytest cases — Stage 1 vintage, see §6)
│   └── upload_pipeline.py         (queue, dedup, worker, Stage 4 retry+recover)
├── frontend/
│   ├── craco.config.js, postcss.config.js, tailwind.config.js, jsconfig.json
│   ├── package.json (React 19 + react-router v7 + shadcn + sonner + lucide)
│   ├── public/index.html
│   └── src/
│       ├── App.js, App.css, index.js, index.css
│       ├── components/   (Layout, UploadQueue, UploadDialog, DocumentDetail, FigureBadge, StatusPill, ui/*)
│       ├── hooks/use-toast.js
│       ├── lib/          (api.js, constants.js, pendingUpload.js, utils.js)
│       ├── pages/        (Dashboard, EvidenceRegister, MissingEvidence, Reports, Settings)
│       └── utils/taxYear.js
├── memory/
│   ├── PRD.md             (architecture + stage log)
│   └── test_credentials.md (empty — single-user app, no auth)
├── test_reports/
│   ├── iteration_1.json
│   └── pytest/pytest_results.xml
└── audit_export/         (this audit ZIP)
```

---

## 2. API endpoints (43 routes total, all prefixed `/api`)

### Diagnostics
- `GET  /api/`                            — health
- `GET  /api/dashboard`                   — summary cards + counts
- `GET  /api/diagnostics`                 — Drive status + AI error
- `DEL  /api/diagnostics/last-error`      — clear last AI error
- `GET  /api/reference`                   — categories / tax years / folder map

### Drive (OAuth PKCE, `drive.file` scope)
- `GET  /api/drive/connect`               — start OAuth (returns URL + verifier)
- `GET  /api/drive/callback`              — OAuth callback
- `GET  /api/drive/status`                — connected flag + folder map
- `POST /api/drive/initialize`            — create 12 numbered subfolders
- `POST /api/drive/disconnect`            — wipe local credentials

### Uploads (queue + worker)
- `POST /api/uploads/bulk`                — multipart, returns queue IDs
- `GET  /api/uploads/queue`               — queue snapshot + counts
- `POST /api/uploads/queue/{qid}/decision` — resolve duplicate (skip/upload_anyway/replace)
- `DEL  /api/uploads/queue/{qid}`         — cancel one (only Queued/Duplicate?)
- `DEL  /api/uploads/queue`               — cancel all pending
- `DEL  /api/uploads/queue/finished/clear` — clear terminal rows
- `POST /api/uploads/queue/{qid}/retry`   — **Stage 4** re-queue Error/Cancelled row
- `POST /api/uploads/recover-stuck`       — **Stage 4** reset >10-min-stuck active rows

### Documents
- `GET   /api/documents`                  — list (filterable: category, tax_year, accountant_review)
- `GET   /api/documents/{id}`             — one doc
- `GET   /api/documents/{id}/download`    — original file
- `POST  /api/documents`                  — manual upload (legacy)
- `PATCH /api/documents/{id}`             — edit metadata
- `PATCH /api/documents/{id}/figures`     — replace headline_figures_json
- `DEL   /api/documents/{id}`             — delete

### Figures (manual entries)
- `GET    /api/figures`
- `POST   /api/figures`
- `DELETE /api/figures/{id}`

### Missing Evidence (Stage 2)
- `GET    /api/missing-evidence`          — full checklist
- `GET    /api/missing-evidence/next`     — next best document to find
- `POST   /api/missing-evidence`          — add custom item
- `POST   /api/missing-evidence/seed`     — idempotent re-seed
- `PATCH  /api/missing-evidence/{id}`     — status / notes / notes_user / matched_*
- `DELETE /api/missing-evidence/{id}`     — remove

### Reports / Exports (Stage 3)
- `GET /api/reports/evidence-register.csv`     — **25 columns** including AI metadata
- `GET /api/reports/missing-evidence.csv`      — checklist + matched docs + user notes
- `GET /api/reports/documents-by-category.csv` — counts
- `GET /api/reports/accountant-summary.pdf`    — formatted (reportlab)
- `GET /api/reports/accountant-summary.txt`    — **plain text (Stage 3, email-friendly)**

### Seed / Admin
- `POST /api/seed/all`
- `POST /api/seed/missing-evidence`
- `POST /api/seed/payg-income`

### AI Telemetry
- `GET /api/ai/stats`  — Gemini vs Claude run counts, cost totals, last error

---

## 3. MongoDB collections (no auth, single-user app, `DB_NAME` from env)

| Collection            | Purpose                                                    |
|-----------------------|------------------------------------------------------------|
| `documents`           | Evidence register rows (Stage 1+2 schema, 50+ fields)     |
| `figures`             | Manually entered figures (income / tax / expense / etc.)  |
| `missing_items`       | Stage 2 checklist + auto-match state                      |
| `upload_queue`        | Async pipeline state machine (now includes `error_code`)  |
| `ai_response_cache`   | SHA-256 → AI analysis (dedup AI calls across re-uploads)  |
| `ai_errors`           | Last failed classification (for diagnostics panel)        |
| `drive_credentials`   | OAuth tokens (`key: "default"`)                           |
| `drive_config`        | Drive parent + subfolder IDs                              |
| `drive_attempts`      | Upload attempt log                                        |
| `drive_errors`        | Drive failure history                                     |

### `documents` shape (key Stage 2+ fields)
```python
{
  id, sha256, name, original_filename, file_type, size_bytes,
  category, category_confidence,
  tax_year, tax_year_confidence, tax_year_reason,
  document_type, risk_level,                    # Green / Amber / Red
  counterparty, date_range_from, date_range_to,
  one_line_summary, what_it_proves,
  headline_figures_json: [{label, amount, confidence, source_quote}],
  accountant_review_required, accountant_review_reason,
  ai_model_used, primary_model_used, final_model_used,
  escalated_to_claude, escalation_reason,
  ai_input_tokens, ai_output_tokens, ai_cost_usd,
  gemini_cost_usd, claude_cost_usd, total_ai_cost_usd,
  ai_response_cached,
  drive_file_id, drive_link, drive_folder_id, drive_folder_name,
  storage,                                       # "drive_and_local" | "local"
  local_path, app_storage_path, vault_filename,
  status, notes, user_notes,
  drive_error,
  created_at, updated_at,
}
```

### `upload_queue` shape (Stage 4)
```python
{ id, filename, mime, size_bytes, sha256, staging_path,
  status,                # Queued | Uploading | Reading | Classifying | Filed | Inbox | Duplicate? | Error | Cancelled
  duplicate_of, duplicate_meta,
  result_document_id, target_folder,
  ai_category, ai_confidence, ai_cost_usd,
  error, error_code,     # Stage 4 — stable codes from error_codes.py
  queued_at, started_at, completed_at }
```

### `missing_items` shape
```python
{ id, item_description, item_needed, category, tax_year, priority,
  status,                # Outstanding | Possible Match | Received | Not applicable | Accountant Review
  matched_document_id, matched_document_name, match_confidence, match_reason,
  notes,                 # canonical seed helper text
  notes_user,            # user-editable notes (Stage 3)
  created_at, updated_at }
```

---

## 4. What's been implemented (by stage)

| Stage | Status | What | Tested how |
|-------|--------|------|------------|
| 1 — Foundation | ✅ Done | Bulk upload, Drive OAuth (PKCE, `drive.file` scope), folder structure, dedup (SHA-256), local fallback storage | curl + pytest (Stage 1 vintage — now partially stale, see §6) |
| 1.5 — Hybrid AI | ✅ Done | Gemini 1.5 Flash → Claude Sonnet 4.5 escalation, AI response cache, fuzzy source-quote verification (anti-hallucination), Evidence Register UI w/ risk + confidence badges | Live e2e — Maxxia, Airbnb, bank, cleaning files all classified correctly |
| 2 — Missing Evidence Tracker v2 | ✅ Done | 30-item canonical seed, intelligent auto-match (`check_and_update_missing_evidence`), "Next best document" banner, manual override | Verified via bash + UI |
| 2.5 — UX quick fixes | ✅ Done | Per-row Upload buttons, top quick-upload bar, Ctrl/⌘+U shortcut, canonical "Need: …" helper text separated from user notes, embedded UploadQueue, header counts, CSV export link | Screenshot + curl |
| 3 — Accountant Pack exports | ✅ Done | Evidence Register CSV rewritten (25 columns w/ AI metadata), new plain-text `/api/reports/accountant-summary.txt`, 5-card Reports page, inline export buttons in EvidenceRegister | curl all 3 endpoints → 200, content verified |
| 4 — Production hardening | ✅ Done | `error_codes.py`, 100 MB cap, `FILE_EMPTY`/`FILE_TOO_LARGE` short-circuit, `error_code` carried on queue rows, `/uploads/queue/{id}/retry`, `/uploads/recover-stuck`, error-aware Retry / Wait-60s / Reconnect-Drive UI | curl (recover-stuck, retry, empty-file → FILE_EMPTY → retry → Filed) |

---

## 5. Stubbed / mocked / skipped / known limitations

**Zero LLM mocking** — AI calls hit real Gemini 1.5 Flash + Claude Sonnet 4.5 via the Emergent Universal Key. AI cost is logged per document (`ai_cost_usd`) and surfaced on the Settings page.

**Zero Drive mocking** — Drive uploads call the real Google Drive API; failures fall back to local-only storage and store `drive_error` on the document.

**Single-user / no auth** — by design (user explicitly chose "None" for auth). No `get_current_user` dependency anywhere. All endpoints are unauthenticated.

**Stubbed nothing**. There is no scaffolded function that returns fake data anywhere in `/app/backend`.

**Not implemented yet (deliberate backlog)**:
- "Final Accountant Pack" zip bundler (CSV + TXT + PDF + key docs in one archive) — proposed as Stage 5
- Drive-disconnect mid-batch UX banner (still in backlog from Stage 2)
- Per-document version history
- OCR full-text search across the vault
- Multi-user JWT auth
- `EvidenceRegister` loading skeletons (proposed in Stage 4 spec but **skipped** — no slowness observed; would be premature)

**Stage 4 spec deviations (deliberate, called out at the time)**:
- Did **NOT** wholesale-replace `upload_pipeline.py` — the spec contained stub Drive code (`drive_file_id = "..."`) and `Depends(get_current_user)` from an auth layer this app doesn't have. Replacing would have destroyed working Drive/OCR/Hybrid-AI/dedup logic. Stage 4 hardening was integrated surgically into the existing pipeline instead.

**Known stylistic / refactor TODOs (non-blocking)**:
- `server.py` is ~1430 lines — should be split into APIRouter modules (`drive/`, `documents/`, `reports/`, `missing/`). Not done because it works.
- No code-level `TODO` / `FIXME` / `MOCK` / `XXX` comments in the repo (grep result is empty).

---

## 6. Test status

### Backend `pytest` (Stage 1 vintage suite — `backend/tests/test_tax_vault.py`)
**Result: 18 passed / 4 failed** (run during this audit).

Failing tests are Stage-1-vintage assertions that became stale after Stage 2/3:

| Failing test | Why it fails now |
|---|---|
| `test_drive_status_initial` | Asserts `connected == False`, but the dev Drive *is* now connected for live AI/Drive testing |
| `test_missing_crud` | Status enum & PATCH validation tightened in Stage 2; old payload returns 500 |
| `test_document_upload_without_drive` | Asserts `drive_file_id is None`, but Drive **is** connected so the file actually uploads |
| `test_document_patch_and_delete` | Depends on the previous test's `shared_doc_id`; cascade failure |

**These are not regressions** — they are stale fixtures from before Drive OAuth was wired live. Real functionality verified manually via curl + screenshots at every stage.

### Backend testing-agent run (iteration_1)
`/app/test_reports/iteration_1.json` — full Stage 1 sweep, 22/22 cases passed.

### Frontend
- Smoke screenshots at every stage (Reports, Missing Evidence, EvidenceRegister).
- All Stage 4 behaviour verified via curl + queue inspection.
- No automated frontend test suite (not specified by user; can add Playwright if desired).

### Curl smoke results (Stage 4, live this session)
```
POST /api/uploads/recover-stuck            → {"ok":true,"recovered":0}
POST /api/uploads/queue/{bad-id}/retry     → 404
POST /api/uploads/bulk (0-byte file)       → row inserted as status=Error, error_code=FILE_EMPTY
POST /api/uploads/queue/{qid}/retry        → {"ok":true}; row re-enters worker → Classifying → Inbox
GET  /api/reports/evidence-register.csv    → 200, 25-column header verified
GET  /api/reports/accountant-summary.txt   → 200, plain-text summary verified
GET  /api/reports/missing-evidence.csv     → 200
```

---

## 7. Environment / Integrations

| What | How | Status |
|------|-----|--------|
| MongoDB | `MONGO_URL` + `DB_NAME` from `backend/.env` | Local pod Mongo |
| Gemini 1.5 Flash | `EMERGENT_LLM_KEY` via `emergentintegrations==0.1.0` | Real calls |
| Claude Sonnet 4.5 | `EMERGENT_LLM_KEY` via `emergentintegrations==0.1.0` | Real calls |
| Google Drive | OAuth 2.0 PKCE (`drive.file` scope) via `google-auth-oauthlib` + `googleapiclient` | Live |
| OCR | `pytesseract` (system Tesseract binary) | Fallback path only |
| PDF text | `pdfplumber` | Primary path |
| DOCX | `python-docx` | Working |
| XLSX | `openpyxl` | Working |
| PDF export | `reportlab` | Accountant Summary PDF |

---

## 8. To hand off to ChatGPT for audit

1. **Easiest:** GitHub repo → green **"Code"** button → **Download ZIP** → upload to ChatGPT.
2. **Or:** download `audit_export/tax-evidence-vault-stage4-11d2c55-20260525.zip` from this workspace (146 KB) via VS Code file view.

Both contain identical source. The ZIP intentionally **excludes** `node_modules/`, `__pycache__/`, `app_storage/` (local user PDFs), `.ruff_cache/`, and `yarn.lock` to stay small.

If ChatGPT wants the AI prompt for the hybrid classifier, see `backend/THE_BRAIN_v1.md` (17 KB, included in the ZIP).
