# Codex Task — P3-1: Accessibility audit & fixes (WCAG 2.1 AA)

> Written in English (handed to Codex). User-facing text stays Azerbaijani via `{% trans %}`/`pgettext`. This is a **university exam system** — a student who relies on a keyboard or screen reader must be able to take an exam end-to-end. That flow is the top priority.

## Context

- Django server-rendered templates + Bootstrap + vanilla ES-module JS. Global design tokens exist (`static/css/design-tokens.css`, `--ems-*`).
- No systematic accessibility audit has been done. Known gaps from the technical audit: inline styles, hardcoded colors (contrast unknown), `!important` overuse, no verified keyboard/ARIA/contrast conformance.
- **Coordinate with the frontend refactor** (`docs/CODEX_PROMPT_FRONTEND_REFACTOR.md`) — do a11y color fixes via the token palette, don't fight that PR.

## Task 0 — Tooling (set up once)

Add an automated a11y harness so regressions are caught:
- Install `@axe-core/playwright` (or `axe-core` + existing Playwright in `tests/e2e`).
- Add `tests/e2e/a11y/` with a helper that loads a page, runs axe, and fails on `violations` of impact `serious`/`critical`.
- Wire a CI job (can piggyback on the existing e2e job) that runs the a11y suite.

## Task 1 — Audit & fix the CRITICAL exam path first (highest priority)

Full keyboard-only + screen-reader pass through: **login → student dashboard → start exam → answer (test + written + coding) → mark/flag question → autosave → submit → finish → view result → file appeal.**
Fix every blocker so the entire flow is operable without a mouse and announced correctly:
- All interactive controls reachable via Tab in a logical order; visible focus (`:focus-visible`) on every control.
- Timer, question navigation, option selection, and submit are keyboard-operable and have accessible names (`aria-label`/associated `<label>`).
- Live regions (`aria-live="polite"`) for timer countdown, autosave status, and validation errors so screen readers announce them.
- No keyboard trap in modals; focus moves into a modal on open and returns to the trigger on close; `Esc` closes.
- Coding/paint widgets: provide an accessible alternative or clear labeling.

## Task 2 — Audit & fix the rest, by role

Login, password reset, dashboards (superadmin, org-admin, rector/dean/department_head, teacher, student, lead_student), profile sections, grading queue, appeals, blog, contact. For each:
- **Color contrast** ≥ 4.5:1 text / 3:1 large text & UI components — fix via `--ems-*` tokens; adjust the token or add a compliant one if a brand color fails (document it).
- **Forms:** every input has a programmatic `<label>` (not placeholder-only); errors linked via `aria-describedby`; required fields marked.
- **Semantics:** headings in order (one `<h1>`/page), landmarks (`<main>`, `<nav>`, `<header>`), tables with `<th scope>`, buttons vs links used correctly.
- **Images/icons:** meaningful `alt`; decorative icons `aria-hidden="true"`.
- **Touch targets** ≥ 44×44px.
- **Skip link** ("skip to main content") at the top of `base.html`.
- **`<html lang>`** reflects the active language (`{% get_current_language %}`).

## Guardrails / Definition of Done
- axe-core: **0 serious/critical violations** on all audited pages; the a11y suite runs in CI.
- The full exam-taking flow is completable with keyboard only and with a screen reader (manually verified; record a short note/gif).
- No visual regression beyond intended contrast/focus changes (visually verify).
- Contrast fixes use `--ems-*` tokens; any token change is documented and coordinated with the frontend-refactor PRs.
- User-facing strings stay Azerbaijian via `{% trans %}`; run `compilemessages` if strings are added.
- `ruff`/`black`/`isort` + `python scripts/check_module_size.py --check` pass.
```
