# Codex üçün addım-addım prompt-lar — JS modulyarizasiya (FAZA 7)

**İstifadə:** aşağıdakı prompt-ları Codex-ə **bir-bir** ver. Əvvəlcə "PROMPT 0" (kontekst),
sonra hər fayl üçün ayrı addım. Hər addımdan sonra Codex-in nəticəsini yoxla, sonra növbətini ver.
Prompt-ların özü ingiliscədir (coding-agent üçün etibarlı); Codex layihənin `AGENTS.md`-ni
(Azərbaycanca) onsuz da oxuyacaq.

---

## PROMPT 0 — Context & rules (paste this FIRST, once)

```
You are working on EMSArena, a Django + vanilla-JS multi-tenant LMS. We are splitting large
front-end JS "god-files" (600+ lines) into smaller modules. A guard script
`scripts/check_module_size.py` freezes large files (see `scripts/module_size_budget.json`);
new/changed JS files must be < 600 lines.

CRITICAL RULES:
1. BEHAVIOR MUST NOT CHANGE. These files run in the browser. A wrong split (broken IIFE
   closure, `const`/`let` not shared across <script> tags, wrong load order) breaks the page
   silently — pytest will NOT catch it.
2. VERIFICATION IS MANDATORY after EACH file:
   a. `./scripts/claude_pg_sandbox.sh shell` (or your host) — run the Django dev server.
   b. Open the affected page in a REAL browser (Playwright/Chromium). Confirm ZERO new console
      errors and the feature works (click through it).
   c. Run the Playwright E2E suite; it must stay green (baseline: 212 passed).
   d. Run `python scripts/check_module_size.py --update` then `--check`.
   e. Run `black`/`isort`/`flake8` are Python-only — for JS just ensure the guard passes.
3. PREFERRED METHOD = ES modules: convert the file into `import`/`export` modules and load via
   `<script type="module" src="...">`. ES-module scope solves the top-level `const/let` sharing
   problem. If ES modules are not viable (legacy global dependencies), use the global-namespace
   pattern: extract features into separate files that attach to a single `window.EMS_X = {}`
   object, and load them via ordered classic `<script>` tags.
   IMPORTANT — internal relative imports must be QUERY-FREE (`import './state.js'`, NOT
   `import './state.js?v=...'`). Production uses CompressedManifestStaticFilesStorage which keeps
   BOTH hashed and unhashed files and does NOT rewrite JS import statements — so query-free
   relative imports resolve correctly to the unhashed file. Only the ENTRY is cache-busted (via
   the `{% static %}` tag → hashed name). Do NOT put `?v=` inside import statements — a fixed
   query gives no real cache-busting and creates inconsistency (verified: host_lobby/player/
   coding_exam are query-free and correct; keep new splits the same).
4. Keep each resulting file < 600 lines. Update the template(s) that load the original script.
5. Preserve the cache-buster query string (e.g. `?v=...`) on the loaded assets.
6. Work IN-PLACE (edit files directly). Do NOT `rm -rf` + recreate directories on a synced
   folder — it creates "filename 2.js" conflict copies.

Read `AGENTS.md` and `docs/QALAN_FAZALAR_JS_CSS.md` before starting. Confirm you understand,
then wait for the first file.
```

---

## PROMPT 1 — host_lobby.js (FAZA 7B, ES module)

```
File: apps/live_exam/static/js/host_lobby.js (2181 lines). Loaded by templates
apps/live_exam/templates/liveExam/host_lobby.html and host_presentation.html.
Structure: ~89 top-level `const` declarations (e.g. `const $ = id => ...`), NO wrapping IIFE.
Because top-level const/let are NOT shared across separate classic <script> tags, you MUST
convert this to ES modules.

Task:
1. Split into feature ES modules under apps/live_exam/static/js/host_lobby/, e.g.:
   - dom.js (selectors/helpers), state.js (WebSocket + game state), render.js (DOM rendering),
     events.js (event handlers), avatar.js (avatar/option-shapes). Adjust to the real seams.
   - A thin entry `host_lobby.entry.js` that imports and wires them up.
2. Each module uses `export`/`import`. Keep each file < 600 lines.
3. In BOTH templates, change the loader to `<script type="module"
   src="{% static 'js/host_lobby/host_lobby.entry.js' %}?v=...">` (preserve the version query).
4. VERIFY: open the live-exam host lobby page (create a live session as a teacher, open the
   host presentation), confirm the lobby renders, players join, WebSocket updates work, ZERO
   console errors. Run E2E. Run the guard --update/--check.

Do NOT change any logic — only move code into modules and add import/export. Report the module
list + line counts + verification result.
```

---

## PROMPT 2 — player.js (FAZA 7B, ES module)

```
File: apps/live_exam/static/js/player.js (1558 lines). Loaded by
apps/live_exam/templates/liveExam/player_screen.html.
Structure: ~77 top-level `const`, NO IIFE → ES modules required (same reason as host_lobby.js).

Task: split into ES modules under apps/live_exam/static/js/player/ (e.g. dom / join / question /
reaction / render / state) + a thin `player.entry.js`. Load via `<script type="module">`.
VERIFY in a real browser: join a live session as a student, answer a question, send a reaction,
confirm render + WebSocket work, ZERO console errors. Run E2E + guard. Behavior identical.
```

---

## PROMPT 3 — coding_exam.js (FAZA 7A, IIFE)

```
File: apps/exams/static/exams/js/coding_exam.js (2087 lines). Single IIFE `(function(){ ... })()`.
Loaded on the practical/coding exam student page.

Task: extract the inner functions into ES modules (editor / runner / test-results / ui / api),
convert the IIFE into a thin module entry that imports them. Load via `<script type="module">`.
Keep behavior identical (code editor, run-code, test execution, result rendering).
VERIFY in a browser: open a coding exam, write code, run it, see test results — ZERO console
errors. Run E2E + guard. If the code editor is a 3rd-party lib loaded separately, keep that as-is.
```

---

## PROMPT 4 — profile.js (FAZA 7C)

```
File: apps/accounts/static/accounts/js/profile.js (2022 lines). Loaded on the profile page.
It handles AJAX profile-section loading (see the project's `ems_ajax_init.js` / EMSReady pattern).

Task: split into modules (section-loader / ajax / ui / init). Preserve the EMSReady/EMSDelegate
AJAX-safe init pattern (buttons must keep working after AJAX section swaps — this is a known
past bug). Load via ES module or ordered <script> as appropriate.
VERIFY: open profile, switch between sections (they load via AJAX), confirm buttons/handlers work
after each swap, ZERO console errors. Run E2E + guard.
```

---

## PROMPT 5 — register_wizard.js (FAZA 7C)

```
File: apps/accounts/static/accounts/js/register_wizard.js (1704 lines). Loaded on the register
page. Multi-step wizard (step1 country → step2 org-type → step3 institution → step4 details).
Note: the register template's step panels were already extracted to
accounts/partials/register_steps/. Mirror that: split the JS by wizard step + shared
state/validation/submit modules.
VERIFY: complete a full registration wizard flow in a browser (all 4 steps + submit + OTP),
ZERO console errors. Run E2E + guard.
```

---

## PROMPT 6 — exam_supervision.js (FAZA 7C)

```
File: apps/exams/static/exams/js/exam_supervision.js (1351 lines). Proctoring/anti-cheat on the
student exam page. Split into modules (event-capture / scoring / websocket / ui). This is
security-adjacent (anti-cheat) — be extra careful behavior is identical.
VERIFY: take an exam with supervision enabled, trigger events (tab switch, etc.), confirm they
are captured/reported, ZERO console errors. Run E2E + guard.
```

---

## PROMPT 7 — permission_editor_ui.js (FAZA 7C)

```
File: apps/accounts/static/accounts/js/permission_editor_ui.js (973 lines). RBAC permission
matrix editor UI. Split into modules (matrix / interactions / save-state). RBAC-adjacent — verify
the saved permission payload is byte-identical to before.
VERIFY: open the permission editor, toggle permissions, save, confirm the request payload and UI
match the old behavior, ZERO console errors. Run E2E + guard.
```

---

## PROMPT 8 — smaller files (FAZA 7D)

```
Split each of these the same way (ES module or ordered <script>), one at a time, with browser +
E2E verification after each:
- apps/exams/static/exams/js/exam_create_edit_modal.js (809, IIFE with window._EXAM_... guard)
- apps/exams/static/exams/js/profile_group_modal.js (680)
- apps/exams/static/exams/js/exam_live_monitor.js (675, IIFE "use strict"; reads json_script DOM)
- apps/blog/static/js/user_profile.js (628)
- apps/accounts/static/accounts/js/statistics.js (615)
```

---

## PROMPT 9 — JS-in-HTML script partials (FAZA 8)

```
Two templates embed large inline JS that uses {% trans %} (so it can't be pure static):
- apps/exams/templates/exams/student/partials/_take_exam_scripts.html (1309)
- apps/accounts/templates/accounts/partials/_staff_management_scripts.html (663)

Task: move the i18n strings into a `{{ data|json_script:"..." }}` element in the template, then
move the JS logic to a static .js file that reads the i18n from that DOM element. Then split the
static .js per FAZA 7. Load via <script src>. VERIFY the take-exam page and staff-management page
in a browser (ZERO console errors) + E2E + guard.
```

---

## PROMPT 10 — bundler (FAZA 10, optional but recommended)

```
Add django-compressor (or Vite/esbuild) so global assets (navbar.css 983, ai_assistant.css 635,
and all JS) can be split at source but shipped as one bundle — no extra HTTP requests. Wrap the
base.html CSS/JS in {% compress css %}/{% compress js %}, configure offline compression, wire it
into collectstatic and the deploy. VERIFY every page renders identically in a browser (visual
check) + full E2E. This affects the whole static pipeline — do it carefully and reversibly.
```

---

### Yoxlama xülasəsi (hər addım üçün)
`dev server → brauzerdə səhifə + konsol 0 xəta → Playwright E2E yaşıl → check_module_size --update/--check`.
Hər hansı addım brauzerdə pozularsa — geri qaytar, seam-i düzəlt, yenidən yoxla.
