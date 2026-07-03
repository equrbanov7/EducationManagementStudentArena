# Codex Task — Remaining i18n: HTML templates, export documents, JavaScript strings

> Written in English on purpose (handed to Codex). The **translated msgids stay Azerbaijani** (AZ is the source language); you add `en`/`ru`/`tr` translations via `.po`. Never change what the user sees in AZ.

## Context — what is already done vs. remaining

**Done (do NOT redo):** every Python **view-layer** user-facing string (flash `messages.*`, `success_message`/`result_message`, notification `create_notification(title=/message=)`, email subjects) is already wrapped in `pgettext`/`gettext`. Contexts introduced: `accounts.org.message`, `accounts.review.message`, `accounts.my_results.message`, `accounts.auth.message`, `accounts.permission_editor.message`, `accounts.superadmin_orgs.message` / `.notification`, `accounts.role_assignment.message`, `blog.category.message`, `blog.moderation.message`, `blog.notification`, `blog.author.message`, `organizations.views.message`, `labs.blocks.message`, `exams.question_bank.message`.

**Remaining (this task), measured 2026-07-04:**
- **HTML templates:** 300 total; **236 already use `{% trans %}`/`{% blocktrans %}`** (pattern is well established); **~112 still contain hardcoded Azerbaijani text** in element text/attributes.
- **Export documents:** DOCX/Excel builder strings are hardcoded (see exact list below).
- **JavaScript:** **55 non-vendor JS files** contain hardcoded AZ string literals; **there is NO JS i18n infrastructure yet** (no `JavaScriptCatalog`, no `gettext()` in JS). Top offenders: `apps/accounts/static/accounts/js/permission_editor/labels.js` (108), `apps/courses/static/courses/js/course_ai_drawer.js` (58), `apps/exams/static/exams/js/exam_live_monitor/{snapshot_modal,utils,actions}.js` (30/24/23), `apps/live_exam/static/js/host_lobby/utils.js` (23), `apps/exams/static/exams/js/teacher_questions_bank.js` (23), `apps/accounts/static/accounts/js/register_wizard/step2.js` (21).

Workflow for every string you wrap: `python manage.py makemessages -a` → fill `locale/{en,ru,tr}/LC_MESSAGES/django.po` (and `djangojs.po` for JS) → `python manage.py compilemessages`. AZ already displays correctly as the msgid.

## Task 1 — HTML templates (~112 files)

- For each template with hardcoded AZ text, add `{% load i18n %}` (if missing) and wrap visible text in `{% trans "…" %}`; use `{% blocktrans %}…{% endblocktrans %}` for text with variables/placeholders (`{% blocktrans with name=obj.name %}… {{ name }} …{% endblocktrans %}`).
- Wrap translatable HTML attributes too: `title`, `placeholder`, `aria-label`, `alt`, button `value`.
- **Do NOT translate:** class names, data-* keys, URLs, icon names, code/`<pre>` samples.
- Match the existing style in the 236 already-migrated templates (grep for `{% trans` to see conventions).
- Reuse existing msgids where the same phrase already exists (avoid duplicates).

## Task 2 — Export documents (exact files)

Wrap with `pgettext("exams.export", "…")` and interpolate with `%(var)s` / `.format`:
- `apps/exams/export_registry.py:52,55` — `f"Dil: {language.upper()}"`, `title=f"Sual bankı — {bank.name}"`.
- `apps/exams/views/teacher/question_library/export.py:77,80` — same two.
- `apps/exams/views/teacher/question_bank/_views_misc.py:77,80` — `f"Dil: …"`, `title=f"İmtahan sualları — {exam.title}"`.
- `apps/exams/views/teacher/question_bank/_reports.py:51,52` — Excel sheet names `"Xülasə"`, `wb.create_sheet("Problemlər")`. **Caveat:** Excel sheet names are limited to 31 chars and forbid `: \ / ? * [ ]` — ensure every translation respects this (truncate/validate) or the export will raise.
- Also check `build_questions_docx` (the shared DOCX builder) for hardcoded column headers / labels and wrap those.
- `apps/accounts/views/profile/_sections/statistics.py:284` `exam_title=f"Profil Statistikası (…)"` — this feeds an AI-summary prompt, not direct UI. Decide: leave as-is (AI context) or wrap. Prefer leaving unless product wants it localized.

## Task 3 — JavaScript strings (55 files) — infra first

There is no JS i18n yet, so **choose and set up an approach** before migrating:

- **Option A (recommended for broad coverage): Django `JavaScriptCatalog`.** Add the `JavaScriptCatalog` view + URL (`/jsi18n/`), include `<script src="{% url 'javascript-catalog' %}"></script>` in `base.html`, then replace JS literals with `gettext("…")` / `interpolate()`. Strings are collected via `makemessages -d djangojs` into `djangojs.po`.
- **Option B (lighter, good for a few exam-critical strings): server-provided config.** Render translated strings into a `data-*` attribute or a `<script type="application/json">` block from the template (using `{% trans %}`), and read them in JS. No catalog needed, but doesn't scale to 108-string files.

Recommendation: **Option A** given `permission_editor/labels.js` alone has 108 strings. Set up the catalog, then migrate top files first (labels.js, course_ai_drawer.js, exam_live_monitor/*). Keep AZ as the msgid.

## Guardrails / Definition of Done

- **Placeholders preserved** in every translation (`{name}`, `%(x)s`, `{{ var }}`) — a missing/renamed placeholder is a runtime error.
- `makemessages -a` (+ `-d djangojs` if you did Task 3) → translate `en`/`ru`/`tr` → `compilemessages`. Commit `.po` and `.mo`.
- `pytest -m "not postgres"` green; add a template smoke test if practical.
- No behavior/logic change — only externalizing strings. No user-visible AZ text changes.
- `ruff`/`prettier` (if configured) clean; follow `AGENTS.md` module-size budget.
- Do exportable work in small PRs: (1) templates by app, (2) export docs, (3) JS infra, (4) JS migration by file.
```
