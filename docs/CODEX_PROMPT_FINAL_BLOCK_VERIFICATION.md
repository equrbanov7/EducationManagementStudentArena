# Codex Prompt — Final Block Verification: M3-C + Async Jobs + Cleanups (EMSArena)

Copy everything below this line into Codex.

---

You are verifying the final uncommitted work block in EMSArena (Django 5.2 multi-tenant exam/LMS; PostgreSQL RLS; Daphne; Celery; Redis). You already verified M2 (zero module cycles) and M3 (clean core + facades) on this tree. This block layers on top of that verified state and contains SIX sub-changes. Zero URL renames; all async flows have synchronous fallbacks, so behavior for small/normal cases is byte-compatible.

## What changed

### 1. M3-C — facade consumer migration (import-only)
All cross-app imports of facade-listed names were rewritten to `apps.<module>.public` (67 files, 119 imports; mixed imports were split so non-facade names kept their original paths). Later additions to facades: `apps/exams/public.py` gained `StudentGroupForm`, `get_ai_rate_limit` (alias of `services.ai_summary._get_rate_limit`); `apps/appeals/public.py` gained `can_open_appeal_management` (alias of views `_can_open_appeal_management`).

### 2. P9 — navbar org-switcher cache
`OrganizationMiddleware._cached_active_memberships` (60s TTL, key `ems:org_switcher:v1:<user_id>`) used ONLY by the lazy navbar path (`request._all_org_memberships`); org-resolution/permission paths still query live. Invalidation: `Membership` post_save/post_delete signal (organizations/signals.py). Tests: `apps/organizations/tests/test_org_switcher_cache.py` (uses pytest `settings` fixture to switch DummyCache→locmem).

### 3. Async job infrastructure — P3 / P3-b / P4 / C2 (the big one)
Model `TextExtractionJob` (`apps/exams/domain/import_jobs.py`; UUID pk, nullable org FK, user FK, `kind` ∈ {extract, ai_generate, export}, `payload`/`result_meta` JSON, temp `file`, `result_file`, status). Migrations: **exams 0024, 0025, 0026** + **organizations 0012** (RLS policy for `exams_textextractionjob`, direct NULLABLE-org pattern).

Tasks (`apps/exams/tasks.py`): `exams.run_text_extraction_job` (extract text; `stash_math` payload flag additionally runs `stash_math_images` for PDFs → `result_meta.math_token`; stash failure is non-fatal), `exams.run_ai_generation_job` (optional file extract + `generate_question_bank_text(**payload)`; the generator is resolved via the view facade `apps.exams.views.teacher.question_bank.generate_question_bank_text` so the existing test patch point works in eager mode), `exams.run_export_job` (builders in `apps/exams/export_registry.py`, org-mismatch guard fails closed).

Endpoints (`apps/exams/views/teacher/extract_jobs.py`, urls under `exams:`): `start_text_extraction` (POST; broker-down → synchronous inline fallback), `text_extraction_status` (owner-only; includes `meta`), `export_job_waiting` (HTML page `exams/teacher/export_waiting.html`, nonce script polling → auto-download), `export_job_download` (owner-only FileResponse). Shared helpers `start_ai_generation_job` / `start_export_job`: when the job finishes eagerly (CELERY_TASK_ALWAYS_EAGER or broker-down fallback) the response is the CLASSIC pre-existing shape (AI: service result dict with 200/400/500 mapping; export: direct attachment) — old tests/JS unaffected; with a real broker they return 202+job_id (AI) or redirect to the waiting page (export).

View rewiring: `ai_generate_question_bank` + `ai_generate_bank_questions` are thin payload-builders calling `start_ai_generation_job`; `export_exam_results_xlsx` and `question_bank_word_export` use threshold routing — `EXPORT_SYNC_MAX_ROWS` (default 500): under → old synchronous path (NO job row created), over → export job. The xlsx workbook code moved verbatim to `views/teacher/results/_export_builder.py`; `_apply_results_filters` got a params variant `_apply_results_filters_from_params` (thin request wrapper kept).

Frontend: `aiQuestionBank.js` — pre-extracts an attached file via start+poll before the AI request, and handles 202+job_id by polling then synthesizing the classic result; `testQuestionBank.js` — workbench form submit with a file is intercepted: extract job (with `stash_math=1`) fills `raw_text` + hidden `math_token`, clears the file input, re-submits (`form.dataset.extractDone`); 404 from the endpoint → legacy direct-file submit. `data-extract-url` attributes added in `_bulk_question_workbench.html` (panel + form) and `_create_question_bank_scripts.html`. i18n: new keys in 4 locales (contexts `exams.template.ai_question_bank`, `exams.view.extract_job.error`, `exams.view.export_job.error`, `exams.template.export_waiting`).

Tests: `apps/exams/tests/test_text_extraction_jobs.py` (19 tests: extract/AI/export/stash/ownership/threshold).

### 4. P10 — global blog category-tree cache
`get_post_category_tree()` default call cached (`ems:blog:category_tree:v1`, TTL 300) with Category post_save/post_delete invalidation (blog/signals.py). Custom-queryset calls bypass the cache. `Category` is deliberately NOT tenant-scoped (see its model docstring), so a single key is safe; pickle-copy semantics keep caller mutations out of the cache (tested). Tests: `apps/blog/tests/test_category_tree_cache.py`.

### 5. C3 — 119 micro-static inline styles → classes
Per the documented list in `docs/UI_COLOR_TOKENS_MIGRASIYA.md`, 119 static `style="..."` attributes across 58 templates became file-local `c3-N` classes (rules appended to the template's own `<style>`; templates without one got a new block — inside `{% block content %}` for extends-templates). `display`-carrying attributes (11) were left inline (JS-toggle rule). All 352 project templates compile with zero errors; zero duplicate-class tags.

### 6. C4 — accounts facade tightening + ADR
All 13 deep-path cross-app imports in accounts rerouted to sanctioned surfaces (`core.permissions.has_permission` ×7; `apps.exams.models` for StudentGroup/AIConfiguration; new public names above). Decision recorded in `AGENTS.md` §5: the cross-domain profile aggregators (`accounts/views/_dashboard_helpers/*`) intentionally STAY in accounts (each one merges exams+assignments+labs+projects; moving them into a content app would create wrong-direction edges).

## Steps (in order; stop and report on hard failures)

1. Scope sanity: `git status --short` / `git diff --stat` matches the above (plus AGENTS.md, plan/docs, locale po+mo files).
2. Static gates: flake8 / black --check / isort --check-only on `apps core config`; `python scripts/module_deps.py --check` (0 cycles, 0 core→apps); `python scripts/check_module_size.py --check`.
3. `manage.py check --fail-level WARNING`; `makemigrations --check --dry-run` (no drift); `migrate` on a clean Postgres (applies exams 0024/0025/0026 + organizations 0012).
4. Template compile sweep (all app+project template dirs via `engines["django"].get_template`) → 0 errors (script pattern is in the C3 section of the docs if needed).
5. sqlite fast lane: `DATABASE_URL="sqlite://" pytest apps core tests -q --no-migrations --ignore=tests/e2e` → 0 failures (~2150+ passed).
6. Authoritative Postgres lane: full non-E2E suite with coverage gate `--cov=apps --cov=core --cov=config --cov-fail-under=68` → 0 failures.
7. **Real-broker smoke (REQUIRED — this is the part your previous runs could not cover):** start Redis + a Celery worker (`celery -A config worker -l info -Q celery` or the project's compose service). Then, in a browser (Playwright or manual) as a teacher:
   - AI panel (exam question bank): attach a small .txt + prompt with the worker RUNNING and eager mode OFF → observe extraction/generation status messages, network shows `import/extract-jobs/` 202 + status polling, generated text lands in the textarea, quota message renders.
   - Workbench direct upload (bulk question import): attach a small PDF → submit; observe "Mətn çıxarılır..." on the submit button, `raw_text` filled, form re-submits without the file; with a formula PDF confirm `math_token` hidden input is set.
   - Export: temporarily set `EXPORT_SYNC_MAX_ROWS = 0` in a local settings override, hit "İmtahan nəticələri xlsx" → redirected to the waiting page → auto-download fires when the worker finishes; restore the setting. Also confirm the DEFAULT setting still downloads synchronously with no job row.
   - Kill the worker and repeat the AI panel call → synchronous fallback returns the classic response (no hang).
8. Security spot-checks: `text_extraction_status`/`export_job_download` for another user's job → 404; anonymous → login redirect; student → blocked. RLS: with tenant GUC set to another org, `exams_textextractionjob` rows are invisible (bypass off).
9. Regression sweeps you already know: admin 2FA tests, tenant-isolation set, profile page GET for all roles, org-switcher shows fresh list right after a membership change (P9 invalidation).
10. Visual sanity for C3 (spot-check, not exhaustive): open profile statistics, assignments modals, labs grade page, organizations dashboard — converted elements look unchanged (widths/margins intact).

## Rules

- Do NOT weaken assertions, delete tests, or add skips.
- Back-compat surfaces that must keep working: every `apps.<module>.public` name; classic response shapes of `ai_generate_question_bank` / `ai_generate_bank_questions` in eager mode; synchronous export downloads under the threshold; `_apply_results_filters(exam, request)` signature; all pre-existing i18n keys.
- Known intentional details (not bugs): job rows are user-scoped + RLS'd, temp files are deleted by the tasks, export `result_file` is kept after download (cleanup is a documented backlog item); `run_ai_generation_job` resolves the generator via the views facade on purpose (test patch point).
- App-code fixes only for obvious mechanical slips; any behavior difference (status code, redirect, message, payload key, authorization outcome) → STOP and report with a repro.

## Report format

Table: step | command | result | notes. Then modified files (if any) with justification, coverage %, worker-smoke observations (screenshots/console notes welcome), and verdict: "Final block verified" or blocking findings.

---

# RE-VERIFICATION ADDENDUM (after your blocking finding — worker-dead fallback)

Your finding was correct: `.delay()` succeeding only proves the BROKER accepted the message; a stopped worker left jobs `pending` (202 + endless poll). Fixed as follows — verify just this delta plus a quick regression pass:

**The fix (files: `apps/exams/tasks.py`, `apps/exams/views/teacher/extract_jobs.py`):**
1. All three tasks now claim work via an atomic CAS (`filter(pk=..., status=PENDING).update(status=PROCESSING, started_at=now)`); a loser (late worker or duplicate inline run) returns the current status without touching the job — double-execution is impossible.
2. New `_ensure_job_progress(job, runner)` pickup-watchdog in the three start helpers: after a successful `.delay()`, the request waits up to `JOB_WORKER_PICKUP_TIMEOUT` seconds (default **3.0**; `0` disables — used by tests that need the real-broker pending path) polling every 250ms; if the job never leaves `pending`, the task function runs INLINE (CAS makes this safe) and the response is the classic synchronous one. A worker that is alive flips the row to `processing` within milliseconds, so the async path is unaffected.
3. `start_text_extraction`'s bespoke inline-extract code was replaced by the same runner+watchdog path; its response is now 200 (success payload) / 400 (failed, body includes `error`+`job_id`) / 202 (pending) — the JS already handles all three.
4. New tests (`TestWorkerDeadFallback` ×3 — including the exact AI scenario you exercised, `TestCasClaim`, `TestMathTokenPropagation` which also covers the math_token gap your simple PDFs couldn't show): `apps/exams/tests/test_text_extraction_jobs.py` (24 tests total).

**Steps:**
1. `pytest apps/exams/tests/test_text_extraction_jobs.py -q` on BOTH lanes (sqlite `--no-migrations` and Postgres).
2. Repeat your browser scenario: Redis up, worker STOPPED, AI panel generate → expect the classic 200 response after ~3s (watch for the `worker pickup görünmədi` ERROR log), text inserted, no endless poll. Same quick check for a >threshold export (direct download after ~3s instead of a stuck waiting page).
3. Worker back up: confirm the normal 202→poll path still works and each job executes exactly once (no duplicate rows/status flapping in `exams_textextractionjob`).
4. Re-run the static gates + full Postgres lane once for regression.

Everything else from the main prompt stands verified per your report; your `test_category_tree_cache.py` Postgres-seed fixture fix is accepted. Verdict options: "Final block verified (addendum)" or remaining findings.

