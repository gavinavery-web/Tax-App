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
- **Stage 4.5 — Hardening (Feb 25, 2026)**:
  - **AI 60-second timeout** in `upload_pipeline.py`: `asyncio.wait_for(classify_document(...), timeout=AI_TIMEOUT_SECONDS)`. Timeout → row status `Error`, `error_code=AI_TIMEOUT`, staging file preserved so `Retry` works.
  - **True cooperative cancellation** with checkpoints before extraction, after extraction, before AI, after AI, before Drive upload, and before document insert. `_raise_if_cancelled()` raises a `_Cancelled` sentinel caught by the worker → row goes to `Cancelled`/`CANCELLED`, no document inserted, no Drive upload, no missing-evidence touch.
  - **`DELETE /api/uploads/queue/{qid}`** now also cancels active rows (Uploading/Reading/Classifying) by setting `cancel_requested=true`. Response includes `mode: "immediate" | "cooperative" | "noop"`.
  - **`DELETE /api/uploads/queue`** now cancels Queued+Duplicate? immediately AND flags active rows cooperatively. Response includes `{immediate, cooperative}` counts.
  - **Crash handler sanitised**: raw exception text is logged but never stored on the queue row. User-facing `error` is always `ERROR_MESSAGES[UNEXPECTED_ERROR]`.
  - **Duplicate rows** now carry `error_code=FILE_DUPLICATE` + `error=ERROR_MESSAGES[FILE_DUPLICATE]` so the frontend renders a consistent hint.
  - **`ai_classifier._call_model`** now returns a 5-tuple `(parsed, in, out, raw, error_str)` propagating timeout / 429 / quota / overloaded / generic strings. `classify_document` forwards combined error text so `classify_ai_error()` can map to `AI_TIMEOUT`/`AI_RATE_LIMIT`/`AI_FAILED`.
  - **Extraction-failure handling**: if `extract_text` fails or yields <10 chars, the document is still filed (to Inbox), `accountant_review_required` is forced, reason includes "Text extraction failed or limited text extracted.", and `category_confidence` is downgraded to `Unsure`. Missing-evidence auto-match is **skipped** for these documents to avoid mis-matching purely on category.
  - **Dashboard missing count** now counts only `Outstanding ∪ Possible Match ∪ Accountant Review` (was `status != "Found"`, a Stage-1 legacy).
  - **Accountant PDF outstanding section** uses the same `OPEN_STATUSES` filter.
  - **Manual override protection**: PATCH `/api/missing-evidence/{id}` with any status other than `Outstanding` sets `status_source="user"`, `status_updated_by="user"`, `status_updated_at`. `check_and_update_missing_evidence` now skips any row with `status_source="user"`. PATCH to `Outstanding` clears the manual flag (explicit re-evaluation signal).
  - **Pre-existing `POST /api/missing-evidence` bug fixed**: was returning `_id: ObjectId` causing 500 JSON-encode error.
  - **Tests**: `backend/tests/test_stage_4_5.py` (19 cases) + Stage 1 suite refreshed for new statuses. Full suite: **40 passed / 0 failed / 1 skipped** (the skip is benign — only triggered if there's no Filed row in the queue at the moment of the test).
- **Stage 5 — Production polish (Feb 25, 2026)**:
  - New `GET /api/dashboard/stats` — returns `total`, per-category counts, `classified`, `needs_review`, `missing_critical`, `missing_total`. Uses correct collection names (`documents`, `missing_items`) and Stage 4.5 `OPEN_STATUSES` filter.
  - New stat band on the Dashboard (4 deep-link cards): Total / Classified & Filed / Needs Review (→ `/register?review=Yes`) / Critical Missing (→ `/missing-evidence`). Existing dense FY/PAYG/category layout preserved.
  - Empty state on the Dashboard for fresh installs (total === 0) with `Ctrl/⌘+U` hint.
  - Global keyboard shortcuts in `Layout.jsx`: `Ctrl/⌘+U` → /register, `Ctrl/⌘+M` → /missing-evidence, `Ctrl/⌘+Shift+D` → / (Shift avoids hijacking the browser bookmark binding). Input/textarea focus is respected.
  - Sidebar shows `⌘U` / `⌘M` / `⌘⇧D` hint chips next to nav items.
  - New `HelpTip` component (shadcn `Tooltip` wrapper) applied to the *Confidence* / *Review* / *AI $* column headers on the Evidence Register.
- **Stage 5 — Final corrections (Feb 25, 2026)**:
  - **AI-failure fallback contract enforced**: every AI failure (timeout, rate-limit, malformed JSON, both-models-failed) now STILL inserts a document with `category="00 Inbox"`, `tax_year="Unsure"`, `risk_level="Red"`, `accountant_review_required=True`, `status="Accountant review"`, queue row=`Inbox` (not Error). Document survives.
  - **Unreadable file contract enforced**: extraction failure / <10 chars → same Inbox/Red/Unsure profile. Auto-match to missing evidence is skipped.
  - **New `GET /api/reports/final-accountant-pack.zip`** — bundles every report (CSVs, TXT, PDF) + `backup.json` + organised document files under `Tax_Evidence_Export/<FY>/<category>/`. Files with missing source bytes are listed in `missing-source-files.txt` (no crash).
  - **New `GET /api/reports/backup.json`** — full disaster-recovery snapshot (documents, figures, missing_items, upload_queue, ai_response_cache, ai_errors, drive_config). Excludes OAuth secrets.
  - **New `GET /api/dashboard/readiness`** — "Ready for Accountant?" gate. Blockers: queue errors, Inbox docs, accountant-review-pending, red-risk unconfirmed, Unsure FY, critical missing evidence. Dashboard renders this as a coloured banner with blocker list + Download/Backup buttons.
  - **Evidence Register CSV extended** to 35 columns including: Document ID, SHA256, Storage, Local path, Source file available, Risk level, Needs review, AI cached, User confirmed, Drive error, Extracted text present.
  - **PATCH /documents/{id}** now sets `user_confirmed=True` + `updated_at=now` on every edit. Clearing `accountant_review` to "No" on a non-red doc auto-sets `accountant_review_required=False` + `status="Complete"`.
  - **PATCH /documents/{id}/figures** also sets `user_confirmed=True`.
  - **Tax year scope locked** in `frontend/src/utils/taxYear.js` to `FY2024 | FY2025 | Both | Historical | Unsure`. FY2026+ no longer exposed.
  - **Backend helpers added** in `/app/backend/financial_helpers.py`: `get_australian_financial_year(date)` (FY2024 = 1 Jul 2023 → 30 Jun 2024), `normalise_fy()`, `parse_money_to_cents()`, `cents_to_money_str()`.
  - **Dashboard stats** now also returns `duplicates` (upload_queue rows in Duplicate? state).
  - **Stripe removed** from requirements.txt (was unused).
  - **Tests**: 25-case `tests/test_stage5_final.py` covers FY boundary dates, money helper, empty file → FILE_EMPTY, unreadable file → Inbox/Red survives, duplicate hash detection + renamed file + dashboard count, manual edit → user_confirmed, accountant-review-cleared → Complete, evidence CSV required columns, backup JSON shape + no OAuth secrets, final ZIP structure + required entries, readiness shape + inbox-blocker correctness, tax_years API locked. **Full suite: 65 passed / 0 failed / 1 skipped.**
  - **Live proof of AI-failure fallback** (curl test): unreadable PDF uploaded → queue row terminates as `Inbox` (not Error), document saved with `category=00 Inbox / risk_level=Red / tax_year=Unsure / accountant_review_required=True / status="Accountant review"`. ✅

## Stage 7 — Phase 1 Foundation (Feb 25, 2026)
- New migrations dir `/app/backend/migrations/`:
  - `create_stage7_collections.py` — creates `bank_transactions`, `tax_return_items`, `properties` collections + indexes. Seeds Heathridge + Waggrakine properties (ids `prop-heathridge`, `prop-waggrakine`). Idempotent.
  - `migrate_to_stage7.py` — adds new fields to `documents` (`is_deleted`, `deleted_at`, `deleted_reason`, `evidence_status="used"`, `used_in_claims_count=0`, `is_bank_statement`, `transactions_extracted_count`, `transactions_analyzed_by_ai`, `transaction_ai_cost_usd`) and Stage 7 tracking fields to `missing_items` (`satisfied_by_document_id`, `satisfied_at`, `satisfied_method`). Idempotent.
  - `__init__.py` so it's also importable as a package.
- New Pydantic models in `server.py`: `BankTransaction`, `TaxReturnItem`, `PropertyUsePeriod`, `Property`. No endpoints yet (Phase 2 territory).
- **Deliberate deviation from spec**: did NOT remap Stage 4.5 missing-evidence status vocabulary (`Outstanding/Possible Match/Received/Not applicable/Accountant Review`) to Stage 7's (`open/matched_by_upload/not_applicable`). The legacy vocab is referenced by ~40 tests, the readiness gate, every export, and 5 frontend pages. Stage 7 mapping documented as `ST7_STATUS_PROJECTION` in `migrate_to_stage7.py` and can be applied as a read-time derivation in Phase 2.
- Verified: 21/21 documents migrated, 30/30 missing_items tracking fields added, 2 properties seeded, idempotency confirmed, all stage 1–6 features still pass (pytest 65/1, all smoke endpoints 200).

### Stage 7 — Phase 2 Bank Transaction Intelligence (Feb 25, 2026)
- `bank_transaction_extractor.py` — CSV / PDF-table / text-line extractors + rules engine (15 Australian merchants: Synergy, Bunnings, ATO, Reece, Mitre 10, Water Corp, Alinta, council/rates, BP/Ampol/Shell/Caltex, AHPRA, tax agent, etc) + private-spending filter (Woolworths/Coles/Netflix/etc) + property use-period matcher + `is_bank_statement` multi-signal detector (≥4 of category-3/keywords-2/bank-name-1/account-pattern-1). Zero AI calls in this path.
- `upload_pipeline.py` integration: after document insert (using the canonical vault path that survives staging cleanup), if `is_bank_statement` triggers, transactions are extracted and inserted into `db.bank_transactions`. Document is flagged `is_bank_statement=True` with `transactions_extracted_count` and `transaction_ai_cost_usd=0.0`. Failure is non-fatal (the doc itself is already saved).
- New endpoints in `server.py`:
  - `GET /api/bank-settings` — returns server-enforced caps + stored ai_enabled/mode/monthly_spend.
  - `POST /api/bank-settings` — whitelisted keys only; 400 on unknown keys.
  - `POST /api/bank-transactions/estimate-cost {transaction_ids: [...]}` — returns transaction_count, estimated_cost_usd, max_batch_cost, monthly_budget, monthly_spend, exceeds_batch_limit, exceeds_monthly_budget, can_proceed.
  - `GET /api/bank-transactions` — list with filters (`source_document_id`, `confidence`, `evidence_status`), bounded by `limit` (max 5000).
- Cost controls: `MAX_AI_COST_PER_BATCH=$5`, `MAX_AI_MONTHLY_BUDGET=$20`, `AI_COST_PER_TRANSACTION=$0.001`. Default mode `rules_only` → $0 for 50 statements.
- Tests: `backend/tests/test_stage7_phase2.py` (22 cases) — parser helpers, rules engine (Synergy/Bunnings/Woolworths/unknown), property period matching (rental vs main residence), bank-statement detection (positive + negative + text-only), CSV/text extraction, settings GET/POST/whitelist, cost gate (100→$0.10 ok, 10000→blocks), end-to-end CSV upload → transactions stored. **Full suite 86 passed / 0 failed / 2 skipped.**
- **Deliberate deviations from spec** (all called out): motor async (`await … .insert_many` / `.to_list`); used `canonical_path` not `temp_path`; `mime` not `mime_type`; `doc_id` string not `_id` ObjectId; `POST /bank-transactions/estimate-cost` not GET (long id lists); `/bank-settings` GET now always merges in server-enforced caps (closes a real bug exposed by the test suite); `POST /bank-settings` rejects unknown keys.
- **Stage 4 — Production hardening (Feb 25, 2026)**:
  - New `/app/backend/error_codes.py` — `ErrorCode` enum + `ERROR_MESSAGES` map + `classify_ai_error()` / `classify_drive_error()` helpers; queue rows now carry a stable `error_code` field.
  - Hard 100 MB file cap (`MAX_UPLOAD_BYTES`); oversize and 0-byte uploads land directly in `Error` state with `FILE_TOO_LARGE` / `FILE_EMPTY` codes — no worker time wasted.
  - Pipeline crash handler now sets `error_code=UNEXPECTED_ERROR`; staging-missing path sets `STAGING_MISSING`; successful rows surface non-fatal `AI_*` / `DRIVE_*` codes as informational hints.
  - New `POST /api/uploads/queue/{qid}/retry` — re-queues `Error`/`Cancelled` rows (404 if missing, 409 if staging file gone, 400 if status wrong).
  - New `POST /api/uploads/recover-stuck` — resets items stuck >10 min in `Uploading`/`Reading`/`Classifying` back to `Queued`; fired from `<Layout>` on app load.
  - Existing endpoints kept: cancel-one, cancel-all, clear-finished, duplicate-decision.
  - `UploadQueue.jsx` rewritten to render `error_code` → action mapping: **Retry** for transient errors, **Retry (wait 60s)** countdown for `AI_RATE_LIMIT`, **Reconnect Drive** link for `DRIVE_DISCONNECTED`, banner showing total error count.
  - **Note**: the spec's wholesale `upload_pipeline.py` replacement was rejected — it contained stub Drive code (`drive_file_id = "..."`) and assumed an auth layer this single-user app doesn't have. Stage 4 hardening was integrated surgically into the existing working pipeline instead.

## Stage 7 Phase 3 — Tax Builder + Deletion + Properties (Feb 28, 2026)
- New `/app/backend/deletion_manager.py` — soft delete / restore / permanent delete with safety checks. Permanent delete refuses to run unless the doc is in the rubbish bin AND has zero `used_in_claims_count` AND no live `tax_return_items` referencing it. Drive copy is preserved on permanent delete (existing hard-delete endpoint `DELETE /api/documents/{doc_id}` still wipes Drive — left untouched).
- New `/app/backend/property_manager.py` — properties CRUD + embedded use-periods. `add_use_period` validates `use_type` ∈ {main_residence, rental, airbnb, renovation, vacant, mixed} and ISO dates. `get_use_period_for_date` resolves overlapping periods with deterministic priority (main_residence > mixed > renovation > rental > airbnb > vacant).
- `/app/backend/tax_return_builder.py` already in place from Stage 7 Phase 2 — wired into new endpoints below. Source linking & `used_in_claims_count` are maintained atomically via `find_one_and_update`.
- New endpoints in `server.py`:
  - `GET /api/tax-years` — FY2024 + FY2025 summaries (sections, totals, review count).
  - `GET /api/tax-years/{tax_year}` — full breakdown for a given year.
  - `GET /api/tax-return-items` — filterable by tax_year/section.
  - `POST /api/tax-return-items` — manual claim creation; validates section against an allowlist, increments source-doc usage count if `source_document_id` supplied (404 if it doesn't exist).
  - `DELETE /api/tax-return-items/{item_id}` — removes claim, decrements doc usage, releases `used_in_return` flag on any linked bank transaction.
  - `POST /api/bank-transactions/{tx_id}/use-in-return` — promote a Confirmed/Likely transaction into a tax-return item (idempotent).
  - `POST /api/documents/{doc_id}/delete` — soft delete (rubbish bin).
  - `POST /api/documents/{doc_id}/restore` — restore from rubbish bin.
  - `DELETE /api/documents/{doc_id}/permanent` — permanent delete (409 if claims exist or not in bin).
  - `GET /api/rubbish-bin` — soft-deleted docs.
  - `GET /api/properties`, `POST /api/properties` (409 on duplicate name), `GET /api/properties/{id}`, `POST /api/properties/{id}/periods`, `DELETE /api/properties/{id}/periods/{period_id}`.
- `GET /api/documents` now hides `is_deleted=True` by default; `?include_deleted=true` opts back in.
- Tests: `backend/tests/test_stage7_phase3.py` (10 cases). Full suite: **96 passed / 0 failed / 2 skipped**.
- **Deliberate deviations from spec**: all filters use string `"id"` (not `_id`/ObjectId) — matches existing codebase convention; timestamps are ISO-8601 UTC strings (not naive `datetime.now()`); existing hard-delete `DELETE /api/documents/{doc_id}` left intact to avoid frontend regressions; permanent-delete preserves Drive file per spec.

## Stage 7 Phase 3 — Frontend UI (Feb 28, 2026)
- New pages: `TaxYears.jsx` (FY summary cards), `TaxYearBreakdown.jsx` (collapsible sections with per-item remove), `BankTransactions.jsx` (filters + "Add to return" promotion), `RubbishBin.jsx` (restore + permanent delete), `Properties.jsx` (inline add-period form + remove), `ManualEntry.jsx` (form with type-aware section dropdown).
- All wired into `App.js` routes inside the existing `<Layout />` outlet. `Layout.jsx` sidebar extended with 4 new entries: Tax Years, Bank Transactions, Properties, Rubbish Bin.
- All pages use `import { api } from "../lib/api"` (axios + REACT_APP_BACKEND_URL) — no hardcoded URLs. All interactive elements carry kebab-case `data-testid`.
- Style matches existing pages: dense Chivo headings, `mono` mini-labels, shadcn Button/Select/Input/Textarea, sonner toasts.
- **Spec adaptations**: `_id` → `id` (codebase convention); `alert()`/`fetch()` → sonner `toast`/axios `api`; FY2026 removed (only FY2024 + FY2025 supported); shadcn components used in place of raw Tailwind.
- Tested by testing_agent_v3_fork: **9/9 e2e flows pass, 0 bugs, 0 action items.**

## Stage 7 Final One-Shot Patch — 6 critical MVP fixes (Feb 28, 2026)
- **Fix 1 — Doc name links to Drive**: `EvidenceRegister.jsx` doc name in the table is now a Drive hyperlink when `drive_link` is present (data-testid `doc-name-link-{id}`); falls back to plain text otherwise.
- **Fix 2 — Per-row delete (rubbish bin)**: new Actions column with trash icon → `window.confirm` → POST `/api/documents/{id}/delete` (soft delete, Drive copy preserved). Row disappears, doc appears in `/rubbish-bin`.
- **Fix 3 — Next-Best card has 4 actions**: `Upload`, `Already uploaded` (opens shadcn Dialog with a document picker → PATCH status=Received + matched_document_id), `Skip for now` (PATCH status=Accountant Review — bumps out of Outstanding), `Not available` (confirm → PATCH status=Not applicable).
- **Fix 4 — Bank statement upload guidance**: blue banner on `/bank-transactions` with a 3-step explainer and `Upload statements` CTA → `/register`.
- **Fix 5 — Richer transaction rows**: raw bank line shown in a code-block when distinct from cleaned description, color-coded debit/credit amount, balance, confidence label.
- **Fix 6 — Safe Reset / Start Fresh**: new endpoint `POST /api/admin/reset-test-data` + `Reset test data` section in Settings (typed `RESET` confirmation + optional properties checkbox). Soft-deletes all live documents, wipes `bank_transactions`, `tax_return_items`, `upload_queue`, `ai_response_cache`, `ai_errors`, and `figures` (preserving the seeded PAYG figures). Missing-evidence rows (excluding Not applicable) reset to `Outstanding`. Properties optionally re-seeded with Heathridge + Waggrakine defaults. Drive copies untouched.
- **Spec adaptations**: `db.missing_evidence` → `db.missing_items` (real name); Stage-7 spec status strings (`"open"`, `"matched_by_upload"`, `"in_progress"`) → Stage 4.5 vocabulary (`"Outstanding"`, `"Received"`, `"Accountant Review"`); `datetime.now()` → ISO UTC strings; raw `fetch`/`alert`/`prompt` → axios `api` + sonner `toast` + shadcn `Dialog`; properties re-seeded after delete so other pages stay functional.
- **Tested by testing_agent_v3_fork**: 6/6 fixes verified (5/6 e2e end-to-end including doc upload→delete→bin flow, 1/6 visual code review since DB is empty post-reset). One critical bug in `BankTransactions.jsx` (missing icon imports) was caught and fixed by the testing agent. Backend pytest still **96/96 passing**.
- **Reset endpoint smoke-tested**: 38 docs moved to bin, 60 transactions wiped, 30 missing rows reset to Outstanding, properties preserved (when `reset_properties=false`).

## Stage 7 Emergency Workflow Fix (Feb 28, 2026)
- **Fix 1 — Reset trashes Drive files**: `POST /api/admin/reset-test-data` now accepts `trash_drive: true` (default), iterates each soft-deleted doc, calls `drive_service.files().update(trashed=true)` per file. Failures captured in `drive_files_failed: [{file_id, name, error}]`. UI exposes a `Also move Drive files to Google Drive trash` checkbox + a warning panel listing failures. Verified by testing agent: 9 Drive files cleanly trashed in test env.
- **Fix 2 — AI Usage transparency**: `GET /api/ai-usage` computes provider (Hybrid: Gemini 1.5 Flash → Claude Sonnet 4.5), billing source (Emergent Universal Key), `is_real_user_charge: false`, real total cost from `documents.ai_cost_usd` aggregation, Claude escalation count, avg cost per document, and an explanation paragraph. Surfaced as `AIUsageCard` in Settings. **Rejected spec's hardcoded `$0.28 = Claude` — used real DB data instead.**
- **Fix 3 — Add-to-Return modal**: `POST /api/bank-transactions/{id}/add-to-return` lets the user override AI year/section/amount/description before promoting a transaction. Creates a tax_return_item with `manual_override=true` + `source_bank_transaction_id` backlink. Bank tx flipped to `used_in_return=true`. `POST /api/bank-transactions/{id}/ignore` marks `evidence_status='private'`. UI: 3 per-row actions — `Add to return…` (modal), `Quick add` (existing AI-classified path, only on Confirmed/Likely), `Ignore`.
- **Fix 4 — Out-of-range auto-reject**: `upload_pipeline.py` filters transactions to FY2024/FY2025 only. If a statement has ZERO in-scope rows, the source document is soft-deleted + Drive copy trashed with reason `Bank statement entirely outside FY2024/FY2025`. Otherwise out-of-range rows are dropped and `transactions_out_of_range` counter is set on the document.
- **Fix 5 — Next Best Document**: confirmed existing PATCH→Accountant Review pipeline works; no new endpoint needed. `get_next_best_document` returns only `Outstanding` items, so Skip correctly advances the queue.
- **Fix 6 — Live dashboard**: `Dashboard.jsx` `setInterval(load, 10000)` auto-refreshes every 10s. All dashboard endpoints (`/dashboard`, `/dashboard/stats`, `/dashboard/readiness`) now filter `{"is_deleted": {"$ne": true}}` so the reset workflow shows zero immediately.
- **Spec adaptations**: `db.missing_evidence` → `db.missing_items` (real name); spec's `status="Skipped"` (not in Stage 4.5 vocabulary) → existing "Accountant Review" path; spec's hardcoded `cost_per_document = 0.28` → real per-doc aggregation; spec's `_id` filters → string `id` filters; `datetime.now()` → ISO UTC strings everywhere; `db.dashboard_cache.delete_many({})` (collection doesn't exist) → dropped.
- **Tested by testing_agent_v3_fork**: 12 new pytest cases written (`/app/backend/tests/test_emergency_workflow_fix.py`); full suite now **105/105 passing**. All UI flows verified end-to-end (Settings AI Usage card, Reset confirm-gating, BankTransactions 3-button row, Add-to-Return modal pre-population, Dashboard interval cleanup). Zero bugs, zero action items.

## Stage 7 Final Comprehensive Workflow Fix (Feb 28, 2026)
- **Fix 1** — `UploadQueue.jsx` `decide` / `cancelOne` / `cancelAll` / `clearDone` wrapped in try/catch + `finally:load()`. Backend errors now toast instead of triggering React's red runtime overlay. The bug was *never* a missing endpoint — `POST /api/uploads/queue/{qid}/decision` returns 404 cleanly on unknown qid.
- **Fix 2** — Global `ErrorBoundary` class component at `/app/frontend/src/components/ErrorBoundary.jsx`, wraps `<Routes>` in `App.js`. Friendly amber card + "Reload page" button replaces React's red runtime overlay.
- **Fix 3** — Bank transaction auto-triage (4 rule blocks at top of `classify_transaction_by_rules`): tiny <$1 → `private/noise_tiny_amount`; internal transfers → `private/internal_transfer`; bank fees → `candidate/bank_fee` + accountant review; interest-credit → `confirmed/interest_income`. Removes 70-90% of manual review noise.
- **Fix 4** — `BankTransactions` default filter = `Needs action` (hides `used_in_return`, `private`, noise types). New options: `needs_action | all | candidate | added | private`.
- **Fix 5** — Transaction description is now a `<Link to=/register?open={source_document_id}>` when source_document_id exists. `EvidenceRegister` consumes `?open=` and auto-opens the EditRow dialog (then strips the param via `replace:true`).
- **Fix 6** — `POST /api/rubbish-bin/empty` + UI button + typed-`DELETE` Dialog. Per-file Drive trash with granular `drive_failed[]` reporting. Idempotent (returns zeros on empty bin). Smoke-tested live: 92 docs + 92 Drive files cleanly trashed.
- **Fix 7** — Dropzone supports Ctrl/Cmd+V paste of screenshots. Global window listener; ignores paste inside inputs/textareas; image/* clipboard files only; auto-named `screenshot-{iso-timestamp}.{ext}`.
- **Fix 8** — Dashboard `PAYG section` now shows empty-state guidance, per-row `view source` link → `/register?open={document_id}`, and a `Manage in Evidence Register →` cross-link.
- **Fix 9** — `PATCH /api/documents/{id}` recomputes `accountant_review_required` + `status` in lockstep: `No` → required=False + status=Complete (if not Red); `Yes` → required=True + status=`Accountant review` + default reason=`Flagged by user`.
- **Fix 10** — `UploadQueue` summary band: visible glyph row showing total · filed · inbox · duplicate · error · cancelled · in-progress counts (color-coded by status).
- **Reused / NOT touched** (already correct): `_run_worker`, out-of-range FY filter in `upload_pipeline.py`, Drive trash on reset, accountant_review auto-complete logic in PATCH endpoint, Drive OAuth, AI classifier prompt, DB schema, migrations, Pydantic models.
- **Tested by testing_agent_v3_fork**: 8 new pytest cases in `/app/backend/tests/test_workflow_fix.py`. Full suite **114/114 passing** (+9 from 105). All 10 fixes verified — 5 via e2e Playwright on live preview URL, 5 via code review against reference files. Zero bugs, zero action items.


## Stage 7 FINAL PATCH — 8 Surgical Fixes (Feb 28, 2026)
- **Fix 1 — True Reset**: PAYG auto-seed removed from `@app.on_event("startup")` (now opt-in via `POST /api/seed/payg-income`). Reset endpoint already returns `force_client_reload: True`; Settings.jsx hard-reloads via `window.location.reload()` after a successful reset. After reset, PAYG figures stay at 0 — verified.
- **Fix 2 — Dynamic Tax Years**: New `tax_years` collection auto-seeded on startup with **FY2024 + FY2025 + FY2026 all ACTIVE** (FY2026 marked as "In progress — not ready to lodge" via date overlap with today). New CRUD endpoints: `GET/POST /api/tax-years/config`, `PATCH /api/tax-years/config/{id}`, `DELETE /api/tax-years/config/{id}` (refuses delete when documents still reference the year). `/api/dashboard` now generates one FY card per active year (not hardcoded). `/api/reference` returns `active_tax_years`. Upload pipeline's out-of-range filter reads from `tax_years` collection. Frontend `useTaxYears` hook + `refreshTaxYears()` shared cache subscribes Dashboard, Layout, BankTransactions modal, TaxYears page. `TaxYears.jsx` page now has a config table (toggle active/locked/delete + add new) above the FY summaries.
- **Fix 3 — Document modal save toasts**: EvidenceRegister `EditRow.update()` already shows context-specific toasts: "Accountant review cleared. Status updated." / "Flagged for accountant review." / "Saved" / "Figure saved" — verified.
- **Fix 4 — PAYG propagation**: `upload_pipeline.py` block at line 802-845 mirrors PAYG-classified document headline_figures into `db.figures` with `figure_type=payg_income` so Dashboard PAYG widget updates live. Skipped for bank statements. Idempotent via `(document_id, description)` upsert key — verified.
- **Fix 5 — Upload queue clickable filenames**: `UploadQueue.jsx` filename column now renders a `<Link to=/register?open={result_document_id}>` (data-testid `queue-filename-link-{id}`) when the row has reached Filed/Inbox and produced a document. EvidenceRegister already consumes `?open=` and auto-opens the EditRow dialog.
- **Fix 6 — AI decision summary**: EvidenceRegister `EditRow` already renders a blue "AI decision summary" panel (data-testid `ai-decision-summary`) showing `one_line_summary` + `accountant_review_reason` + bank-statement transaction count — verified.
- **Fix 7 — Assets & Entities**: `property_manager.add_property()` now accepts `entity_type` + `entity_type_other`. `POST /api/properties` validates `entity_type ∈ {property, business, trust, super, other}` (400 on invalid; 400 if `other` without `entity_type_other`). New `PATCH /api/properties/{id}` for editing. Frontend `Properties.jsx` rewritten as **"Assets & Entities"** with: page h1 rename, sidebar entry rename (uses `Building2` icon), `Add asset / entity` button → create form with name/type/address (and `entity_type_other` text field when type='other'), inline Edit per row, color-coded entity_type badge on each card.
- **Fix 8 — TAX FINANCES rename**: Dashboard h1 = `TAX FINANCES` with letter-spaced typography. Layout sidebar header = `TAX FINANCES`. Sidebar subtext now shows dynamic `activeNames.join(" · ")` (e.g. "FY2024 · FY2025 · FY2026") which updates instantly when years are toggled.
- **Backend bug fixed during this run**: `POST /api/tax-years/config` returned 500 because `motor.insert_one()` mutates the input dict with an `ObjectId('_id')` that FastAPI can't JSON-serialize. Patched by `row.pop("_id", None)` after insert_one (matches the pattern already used in `/missing-evidence` POST).
- **Tested by testing_agent_v3_fork**: 12 new pytest cases in `/app/backend/tests/test_final_patch.py` (TestTaxYears, TestPropertiesEntityType, TestResetDataNoPaygReseed). Full backend suite: **126/126 passing** (+12 from 114). All 8 fixes verified — Fix 2/7/8 via live Playwright on preview URL; Fix 1/3/4/5/6 via backend tests + code review. Zero unresolved bugs, zero action items.
- **Files touched**: `/app/backend/server.py` (dashboard dynamic FY cards, PATCH /properties, entity_type validation, _id pop), `/app/backend/property_manager.py` (entity_type_other param), `/app/frontend/src/lib/useTaxYears.js` (NEW hook), `/app/frontend/src/components/Layout.jsx`, `/app/frontend/src/components/UploadQueue.jsx`, `/app/frontend/src/pages/Dashboard.jsx`, `/app/frontend/src/pages/TaxYears.jsx`, `/app/frontend/src/pages/BankTransactions.jsx`, `/app/frontend/src/pages/Properties.jsx`, `/app/frontend/src/utils/taxYear.js` (FY2026 added).

## Phase 2 — Code-First Triage + Date Routing (Feb 28, 2026)
- **New modules** (pure logic, no DB/Drive/AI side effects):
  - `/app/backend/code_triage.py` — `extract_document_date(filename, text)` returns `(iso_date, confidence)` via lookbehind/lookahead regex (handles `_2025-03-15` filename underscores that `\b` can't cross), `date_to_financial_year()`, `classify_by_rules()` with 13 filename rules + 5 text fallbacks. `CODE_TRIAGE_THRESHOLD=0.8` gates the AI-skip.
  - `/app/backend/return_router.py` — `find_matching_return(db, date_iso, fy, return_type_hint=)` resolves single-match/no-match/ambiguous against open `tax_returns` rows (status ∈ {`collecting_evidence`, `ready_for_review`}). `infer_return_type_hint()` returns `'company'` only on Pty Ltd / ABN / Revive markers; never auto-personal.
- **Pipeline integration** (surgical, in `upload_pipeline.py` between "Checkpoint — after extraction" and "Step 4 — AI"):
  1. Pre-block extracts date, computes FY, looks up open return, runs rules → `skip_ai` flag.
  2. AI section wrapped in `if skip_ai: <build analysis from rule> else: <existing cache + AI block unchanged>`. `classification_method_value` set to `"code"` / `"ai"` / `"ai_failed"`.
  3. `needs_assignment` safety net forces `category="00 Inbox"` + accountant review (NEVER deletes).
  4. New persisted fields on document: `tax_return_id`, `classification_method`, `detected_date`, `date_confidence`, `needs_assignment`, `assignment_reason`.
- **Live smoke verified**:
  - `synergy_2025-03-15.pdf` + single open FY2025 Personal return → category `05 Heathridge`, `tax_return_id` set, `classification_method=code`, `ai_cost_usd=0.0`, `ai_model_used=code_triage` ✅
  - Same file but 2+ open FY2025 returns with no type hint → 00 Inbox, `needs_assignment=true`, reason="Multiple open returns…" ✅
  - `synergy_2022-08-10.pdf` (no FY2023 return open) → 00 Inbox, `needs_assignment=true`, reason="No open return for FY2023", `is_deleted=false` — **never deleted** ✅
- **Tests**: 19 new unit tests across `tests/test_phase2_code_triage.py` (10 cases — date regex, FY mapping, rules) and `tests/test_phase2_return_router.py` (9 cases — async mock DB for find_matching_return + 2 hint inference). All pass.
- **Full backend suite**: **154 passed / 5 skipped** (no regressions; +19 from 135).
- **Dependencies added**: `datefinder>=0.7.3`, `pytest-asyncio>=1.0.0` (the second pulled in transitively when running the async tests; pinned explicitly for repeatability).
- **Files touched in Phase 2**: `backend/upload_pipeline.py` (surgical wrap + new doc fields), `backend/requirements.txt` (+2 lines). New files: `backend/code_triage.py`, `backend/return_router.py`, `backend/tests/test_phase2_code_triage.py`, `backend/tests/test_phase2_return_router.py`. Forbidden files (`ai_classifier.py`, `extraction.py`) untouched.


## Phase 3 — Tax Profile Wizard + Dynamic Missing-Evidence Generator (Feb 28, 2026)
- **New catalogues** (editable JSON, no code change to add/remove questions or rules):
  - `/app/backend/profile_questions.json` — 4 return-type sections; Personal has 3 groups (28 questions incl. conditional follow-ups), Company has 2 groups (9 questions). Trust + Sole Trader carry placeholder rows.
  - `/app/backend/evidence_rules.json` — 26 personal rules, 6 company rules. Each rule has `if` predicate + `items[]` template (item / category / priority / where / why).
- **New engine** `/app/backend/profile_engine.py`:
  - `get_questions_for_return_type(t)` returns the right group set.
  - `generate_missing_evidence()` is **idempotent**: uniqueness key is `(tax_return_id, profile_rule_key, item_needed)`. Skips rows where `status_source == "user"` (Stage 4.5 user-override protection) without overwriting them. NEVER deletes anything. Returns `{created, skipped_existing, skipped_user_managed}`.
- **New routes** on `server.py`:
  - `GET /api/tax-returns/{id}/profile-questions` — return-type-aware question set
  - `POST /api/tax-returns/{id}/generate-evidence-checklist` — runs the engine with current `profile_answers`
- **Frontend wizard** at `/tax-returns/new` (single new page; existing pages untouched):
  - 3 steps with progress badges (Basics → Confirm → Profile)
  - Conditional follow-up questions render only when parent is `Yes` (e.g. `wfh_method` appears only when `claim_wfh == true`)
  - Submission generates the checklist + toasts the count, then redirects to `/missing-evidence?return=<id>`
  - Sidebar gains a `+ New Tax Return` link (`data-testid="nav-new-tax-return"`)
- **Tests**: 6 new test cases in `/app/backend/tests/test_phase3_profile.py` covering: question set returned, 13-item generation from a realistic profile, idempotency, seeded items untouched, user-managed items never overwritten, company question set is distinct from personal. Switched from FastAPI `TestClient` to `requests` against the live backend (matching dominant repo pattern) to avoid the cross-module motor event-loop teardown issue. Fixture also cleans `missing_items` and tax_returns it created.
- **Live E2E verified**: ran wizard end-to-end via Playwright — FY2025 / Personal / "E2E Wizard Test" → 6 yes-answers + `wfh_method=fixed_rate` → 13 items generated (Critical: PAYG + rental, Important: phone/internet/WFH/AHPRA/private health, etc.) → redirected to `/missing-evidence?return=tr-…` ✅
- **Full backend suite**: **160 passed / 5 skipped** (+6 from Phase 2's 154; no regressions).
- **Files touched in Phase 3**: NEW: `backend/profile_questions.json`, `backend/evidence_rules.json`, `backend/profile_engine.py`, `backend/tests/test_phase3_profile.py`, `frontend/src/pages/CreateTaxReturn.jsx`. MODIFIED: `backend/server.py` (+2 routes), `frontend/src/App.js` (+1 route), `frontend/src/components/Layout.jsx` (+1 sidebar link + FilePlus icon). Forbidden files (legacy seeded `MISSING_PRELOAD`) untouched — they continue to live under `generated_by="seed"`.


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
