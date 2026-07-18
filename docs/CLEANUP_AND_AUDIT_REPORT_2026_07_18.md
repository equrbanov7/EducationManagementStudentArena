# Cleanup & audit report — 2026-07-18 (autonomous session)

Six parallel analyses (app inventory, dead code, misplaced files, duplicate URLs/code,
optimize/constants, rebrand) → executed the high-confidence/low-risk subset, deferred
the judgment-heavy items below. Every delete/move was grep-verified for 0 references
first; 1,153 tests pass across all touched areas (core, blog, live_exam, accounts,
contact, trial_exams) + lint/module-size/boundary/worker-atomic green.

## ✅ EXECUTED (committed to Develop→main)

### Rebrand → white-label (commit `970e74ad`)
- ~90 visible "EMSArena"/"EMS Arena" occurrences across 39 templates routed through
  `{{ brand }}` (emails) / `{{ site_brand_name }}` / `SITE_BRAND_NAME` (pages, admin,
  PWA). i18n-safe (brand split out of `{% trans %}`, +22 `.po` strings/locale, `.mo`
  recompiled). `brand` added to 8 email-render contexts.
- **Prod bug fixed:** `SITE_BRAND_NAME`/`SITE_BRAND_SHORT` were missing from
  production/local/test `from .base import (...)` lists → brand silently fell back to
  "EMSArena" in prod. Added.
- Favicon set (16–512 + ico + apple-touch + svg) regenerated from `wcu-logo-circle.png`.

### Dead-code removal (commit `846584cb` + guard fix `cab437d7`)
Deleted (0 refs each): `create_roles.py`, `seed_journal_demo.py`, `scripts/seed_data.py`,
`scripts/create_groups.py`; `core/constants.py` classes `UserRole`/`ExamType`/
`SubmissionStatus`/`QuestionType`; `core/tasks.py::export_exam_results_csv`;
`live_exam/urls.py` dead routes `skip_intro`/`end_question`; 11 unreferenced templates/static.
Removed the stale `create_roles.py` entry from the worker-atomic guard exemptions.
**Kept (audit false-positives — actually referenced):** `create_question.html`,
`questions_i_can_see.html`, `exam_create_edit_modal.js`, `coding_exam.js`,
`host_lobby.js`, `player.js`, `statistics.js`.

### Misplaced files moved (commit `eafd7081`)
- `accounts/emails/new_post_notification.html` → `blog/emails/` (the "notification file in
  accounts" flag). `accounts/{org,superadmin}_post_management.html` + css → `blog/`.
  Root `DUSTUR_...md` → `docs/exams/`. All render/static paths updated, 0 stale refs.

### README refresh (commit `8acbc491`)
- Added branding/white-label, architecture (18-app modular monolith), performance, and
  k6 sections + doc pointers. (Product name "EMS Arena" kept — internal identifier.)

## ⏸️ DEFERRED — recommended, needs review/testing (do next, with the server/CI)

### Rebrand — need YOUR decision (values I must not invent)
1. Footer/contact socials & emails: `info@emsarena.com`, `support@emsarena.com`,
   `@emsarena_edtech` (`_footer.html`, `contact.html`, email footers). Supply WCU's.
2. Theme color `#0f766e` (teal) — `_seo_head.html` mask-icon, manifest `theme_color`,
   email accent gradients. Provide WCU's brand color.
3. Email subjects/sender name still "EMSArena" (`contact/services.py`, `trial_exams/services.py`
   `[EMSArena Contact]`, `from_name="EMSArena"`) — coupled to `info@emsarena.com`; route
   through brand once socials decided.
4. `blog/about.html` team bios ("EMSArena-nın baş memarı Elvin Qurbanov") — needs a rewrite
   for a university deployment, not a name swap.

### Constants → extract (optimize workflow; behavior-sensitive, test before merge)
- `ATTEMPT_FINISHED_STATUSES` (`apps/exams/constants.py:56`) redefined at
  `cheap_counts.py:40`, `exam_center/statistics.py:28` → import canonical.
- new `ATTEMPT_ACTIVE_STATUSES=("draft","in_progress")` — 8 inline sites (access_policy.py:130,137,161;
  domain/attempts.py:206; services/attempts.py:179,208; assigned_tasks.py:168; results/_helpers.py:348).
- Big: `ExamAttempt.STATUS_*` TextChoices (40+ sites), `SUPERVISION_STATUS_*` (25 sites),
  `exam_type=="test"`→`is_auto_graded` (15), role literals→`ProfileRole` (15, vocab nuance),
  Gemini model-id consts (6), `EMAIL_TASK_RETRY_KWARGS`, JS reconnect-backoff (6 files),
  grading 17/50 + JS `data-pass-threshold`, cache prefix `"emsarena:"` vs `"ems:"`.

### Duplicates (duplicate-hunt workflow)
- live_exam URL aliases: `host_start_game`/`host_next_question`/`host_finish` are test-only
  long forms (`urls.py:18-22`) — collapse to one scheme + update tests.
- `/accounts/assigned-exams/` vs `/exams/assigned/` — same filter rule hand-duplicated
  (`accounts/queries/assignments.py:28` vs `exams/views/student/lists.py:420`) → shared facade.
- OTP-email builders duplicated 3-4× with drift (LIVE=`accounts/services/auth.py`;
  `core/email_tasks.py` OTP task is DEAD/test-only) → consolidate.
- `blog/legacy_urls.py:47-53` — 6 routes skip the redirect pattern; add comment or redirect.

### Misplaced (needs care — signature/facade work)
- Notification-broadcast logic in `accounts/services/profile_actions.py:81-228` → `notifications`
  (reshape `capabilities` dict to booleans first, expose via `notifications.public`).
- Kollokvium-windows admin in `accounts/{forms,views}/kollokvium_windows.py` → `registrar`
  (needs `registrar.public` WRITE functions — currently read-only).

### Architecture
- 7 apps lack a `public.py` facade: `ai_assistant, assignments, blog, labs, live_exam,
  monitoring, projects` — add facades so cross-app edges go through a contract.

_Verdict: disciplined modular monolith (0 circular deps, 0 core→apps, CI boundary gate).
For 5000–10000 users: scale the monolith, not microservices. See
docs/architecture/RLS_POLICY_OWNERSHIP.md, docs/performance/OPTIMIZATION_5000_USERS.md._
