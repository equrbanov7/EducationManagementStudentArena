# Codex Task — Frontend Refactor (FRONTEND-001): color tokens, `:root` consolidation, god-template split

> **Language note:** this prompt is written in English on purpose (it is handed to Codex). All *user-facing* strings you touch must stay Azerbaijani and go through `pgettext`/`{% trans %}` — never hardcode UI text.

## Context

EMSArena is a Django 5.2 multi-tenant EdTech/exam platform. A global design-token layer already exists and is wired into `templates/base.html`:

- **Tokens:** `static/css/design-tokens.css` — 40 `--ems-*` custom properties (slate/blue palette: `--ems-primary-*`, `--ems-neutral-*`, `--ems-gray-*`, `--ems-success/danger/warning-*`, plus semantic aliases `--ems-text`, `--ems-border`, `--ems-bg`, `--ems-link`).
- **Migration guide (follow it):** `docs/UI_COLOR_TOKENS_MIGRASIYA.md`.
- **Module-size rule (mandatory):** `AGENTS.md §1` — new files ≤ 600 lines; existing large assets are frozen in `scripts/module_size_budget.json` (ratchet: you may only shrink them). Run `python scripts/check_module_size.py --check` before committing; CI enforces it.

**Current measured state (2026-07-04):**
- The mechanical/exact-match color migration is largely DONE already: `#2563eb` and `#ffffff` each now appear only ~1–2× (were 269× / 718×).
- Remaining: **~2537 hardcoded hex colors** and **42 CSS files that define their own `:root` token sets** (top offenders: `apps/exams/static/exams/css/teacher_exam_results/_part1.css` 28 local vars, `static/css/error-pages.css` 26, `apps/exams/static/exams/css/student_exam_list.css` 23, `apps/live_exam/static/css/player/_part1.css`, `apps/accounts/static/accounts/css/profile/base.css`, …).
- **~195 `!important`.**
- Several god-templates (39 KB): `apps/exams/templates/exams/teacher/partials/_create_exam_modal_form.html`, `_bulk_question_workbench.html`, `_question_management.html`, `apps/exams/templates/exams/student/take_coding_exam.html`, `apps/accounts/templates/accounts/profile/sections/_notifications.html`.

## CRITICAL guardrail — do NOT change rendered output

Most remaining hardcoded colors are **Tailwind-gray / custom shades that do NOT exactly equal a token value** (e.g. `#4b5563` ≠ `--ems-neutral-600` which is `#475569`). Replacing them with a token would **change the color** = visual regression. Therefore:

1. **Auto-tokenize ONLY exact-value matches** (hex identical to a token's defined value → `var(--ems-…)`). These are zero-visual-change. Skip 8-digit `#rrggbbaa` hexes.
2. **For non-matching colors**, do NOT silently snap them to the nearest token. Either (a) leave them and add a semantic token to `design-tokens.css` if the color is clearly a reused brand/semantic value, or (b) flag them in the PR description for design review. Any change that alters a computed color must be **visually verified** (see below).
3. **Verify visually.** Run the app locally (`docker compose` or `manage.py runserver`), open each affected page, and confirm zero visual difference for exact-match changes and intended-only changes otherwise. Screenshot before/after for the design-review set.

## Tasks (do as SEPARATE, small PRs — one concern per PR)

### PR 1 — Exact-match color tokenization (safe, zero-visual)
- Across `static/css/**` and `apps/*/static/**/*.css` (exclude `vendor/`), replace hex values that **exactly equal** a `--ems-*` token value with `var(--ems-…)`.
- Do it per-file, verify no 8-digit hex is mangled, keep formatting.
- Verification: page renders identical; `git diff` shows only hex→var swaps.

### PR 2 — Consolidate fragmented `:root` local tokens
- For the 42 files with local `:root { --x: … }`: where a local var's value **equals** a global token, alias it (`--local: var(--ems-…)`) or replace usages with the global token. Where it differs, promote genuinely-shared values into `design-tokens.css` as new named tokens (additive) and reference them; leave one-off component colors local but documented.
- Goal: shrink duplicated palette definitions; single source of truth.
- Verification: visual diff per touched page.

### PR 3 — Reduce `!important` (only where safe)
- Investigate the 195 `!important`. Remove only where specificity can be achieved otherwise **without** changing the cascade result. Do not bulk-strip. Visually verify.

### PR 4+ — God-template split (follow the existing pattern)
- Follow the in-progress pattern (see git history / `AGENTS.md`): split 39 KB templates into `{% include %}` partials with **byte-identical rendered output**. Split at clean structural boundaries; preserve template context/scope.
- One template per PR. Verify the rendered HTML is unchanged (diff the rendered output for a fixed fixture) and that the module-size budget ratchets **down**.
- Candidates in priority order: `_create_exam_modal_form.html`, `_bulk_question_workbench.html`, `take_coding_exam.html`, `_question_management.html`, `accounts/profile/sections/_notifications.html`.

## Optional — P0-2 exam-mode instant feedback (needs backend + frontend + product sign-off)
Add a teacher-configurable `instant_answer_feedback` session setting to `apps/live_exam/session_settings.py` (`DEFAULT_SESSION_SETTINGS` + `BOOLEAN_SETTING_KEYS`, default `True` = current behavior). When `False`, suppress correctness fields (`is_correct`, `fraction`, `picked_correct/wrong`, `correct_total`, and the awarded-points delta) from the `answer_saved` payload in `apps/live_exam/scoring.py` (`_save_answer_and_score_impl` result) so a proctored exam can hide immediate right/wrong feedback. Update the player frontend (`apps/live_exam/static/js/player/*`) to handle the absent fields, and the host settings UI to expose the toggle. Add tests. **The reveal-stage gating is already fail-closed** (see `apps/live_exam/tests/test_reveal_gating.py`) — do not weaken it.

## Definition of Done (every PR)
- No user-facing string hardcoded (use `pgettext`/`{% trans %}`; run `makemessages -a` + `compilemessages` if you add strings).
- `pytest -m "not postgres"` green; `pytest -m postgres` green if you touched RLS-relevant code.
- `ruff check` + `ruff format` clean; `python scripts/check_module_size.py --check` passes (ratchet not exceeded).
- Visual verification done (screenshots for any intended visual change).
- Tenant isolation / RLS untouched; no behavior change beyond the stated concern.
