# PERF-2 — Frontend performance and page weight (2026-10-17)

Scope: page weight, request counts, render-blocking assets, caching and compression, DOM size of the big grids, polling, mobile layout.
Target: local QA clone only. Nothing was run against prod. No repo code was changed. No qa.* password was changed.

## 0. How this was measured (and what it cannot tell you)

* **No logged-in browser session.** I tried a throwaway auto-login shim on a scratch port. The permission layer refused it as a security weakening, so I deleted it and did not retry. Replacement method:
  * HTML of every page was rendered with the Django test client and `force_login` against the clone DB. Sections were reached with `?section=`.
  * The HTML was saved. A throwaway read-only server then served the snapshot with `/static/` resolved through Django's finders (no auth, no DB).
  * The snapshot was opened in my own browser tab. JavaScript ran, so DOM growth and `bootstrap_select.js` enhancement are real. XHR calls to the app return 404, so AJAX-filled data is missing.
* Asset sizes come from disk. gzip sizes are `gzip -6` on each file. Prod serves `.gz` files from `CompressedManifestStaticFilesStorage` through `gzip_static`, which is the same order of magnitude.
* Timings came from a fast desktop CPU with no throttling and localhost latency. They are useful for ratios and DOM counts, not for absolute phone times. Multiply CPU figures by 4–6 for a school PC or phone.
* The clone has thin data: journals with no lessons, an empty timetable. Grid sizes are therefore **extrapolated from measured per-cell cost**, and the report says so wherever that applies.
* Throwaway scripts and saved HTML are in `/private/tmp/claude-501/-Users-elvin-Developer-EMSArena/fbb0dcda-5104-4c01-810c-9dca5de595d2/scratchpad/perf2/`.

## 1. Per-page table

"Reqs" is the number of requests in the HTML plus the fixed extras: font, brand mark, nav sprite, avatar. The browser count is shown where I measured it. "KB" is raw / gzip of CSS and JS only. Blocking means the stylesheets in `<head>` plus synchronous scripts in `<head>`.

| Page (clone user) | HTML KB (gz) | CSS files | CSS KB raw/gz | JS files | JS KB raw/gz | Blocking in `<head>` | Reqs | ≈ cold transfer gz KB | DOM elements at runtime (375px / desktop run) |
|---|---|---|---|---|---|---|---|---|---|
| Login (staff/student) | 11 (3) | 8 | 275 / 46 | 10 | 111 / 34 | 8 CSS + `jsi18n` (87 KB) + `csrf.js` + `base_auth.js` (+ Clarity tag when enabled) | 19–23 | ~83 (+ logo SVG 27 gz) | 126 |
| Student cabinet (dashboard) | 77 (13) | 64 | 736 / 172 | 43 | 457 / 136 | 64 CSS + 6 sync JS (64 KB) | 108 measured | ~509 | 659 |
| Teacher cabinet (dashboard) | 92 (14) | 72 | 864 / 201 | 60 | 639 / 185 | 72 CSS + 6 sync JS | ~136 | ~589 | 850 |
| Teacher «Elektron jurnal» section | 94 (15) | 79 | 980 / 230 | 66 | 664 / 195 | 79 CSS + 6 sync JS | 149 measured | ~627 | 886 |
| Journal list `/jurnal/` | 49 (9) | 27 | 557 / 118 | 33 | 361 / 111 | 27 CSS + 6 sync JS | 63 measured | ~425 | 560 |
| Journal detail `/jurnal/<id>/` | 82 (15) | 39 | 648 / 145 | 47 | 463 / 145 | 39 CSS + 6 sync JS | 88 measured | ~493 | 1,040 (empty journal, see 3.3) |
| Schedule editor (`schedule-manage`) | **339 (57)** | 82 | 1,015 / 238 | 73 | 754 / 220 | 82 CSS + 6 sync JS | 159 measured | ~704 | **9,022** (3,149 in source) |
| Workload distribution | 166 (22) | 77 | 906 / 212 | 67 | 726 / 210 | 77 CSS + 6 sync JS | 150 measured | ~632 | 1,750 |
| Groups registry | **537 (85)** | 77 | 906 / 213 | 66 | 722 / 210 | 77 CSS + 6 sync JS | 147 measured | ~696 | **12,069** (4,387 in source) |
| System monitoring | 155 (20) | 76 | 901 / 211 | 68 | 952 / 285 | 76 CSS + 6 sync JS (+ Chart.js 201 KB in body) | 149 measured | ~704 | 1,250 |
| Live exam player (`/live/play/<pin>/`) | n/a (dynamic) | 9 | 79 / 23 | 4 classic + 1 entry + **25 ES modules** | 194 / 68 | Google Fonts CSS (3rd party) + 9 CSS | 39 + Google Fonts (CSS and woff2 files) | ~90 + fonts | n/a (needs a live session) |

\* Cold transfer = HTML gz + CSS gz + JS gz + about 190 KB of fixed items: `fa-solid-900.woff2` 147 KB, brand PNG 19 KB, nav sprite 22 KB. Warm repeat visits cost roughly the HTML only, because of immutable hashed files (see section 4).
\* Cabinet pages are HTTP/2 multiplexed, so request count hurts mostly on a cold cache. Exam day is the worst case: a whole cohort starts cold at once.

Other checks:

* Inline `<style>`, inline `<script>` and `style="…"` attributes: **0** on every measured page.
* `<img>` without dimensions: only the navbar avatar. It sits in a sized circle, so there is no layout shift.
* No duplicate script fetches. `language_switcher.js` is included once per switcher instance on purpose. `pagination.css` is linked twice, which the browser de-duplicates.
* `bootstrap_select.js` and `ems_multi_select.js` are not duplicates: the single-select calls into the multi-select. `searchable_select.js` (static) and `exams/js/exam_create_edit_modal/searchable_select.js` are different server-backed pickers.

## 2. Findings

### HIGH

**H1. Cabinet pages for teachers and staff import Google Fonts from inside a render-blocking stylesheet.**
* Evidence:
  * `apps/courses/static/courses/css/course_create.css:12` has `@import url('https://fonts.googleapis.com/css2?family=Fraunces…&family=Inter…')`.
  * `apps/accounts/templates/accounts/profile/_section_assets.html:133` links that file, so every teacher/staff section carries it. I confirmed it in teacher cabinet, schedule editor, workload, groups registry and system monitoring.
  * Student cabinet does not load it.
  * In the browser, resource timing shows the request to `fonts.googleapis.com` with initiator `css`.
* Why it matters: a stylesheet is not "loaded" until its `@import` chain is, so the first paint of the whole cabinet waits on a cross-origin DNS, TLS and CSS fetch. It stalls on filtered or slow school networks and leaks user IPs to Google. The fonts are only used inside `.ems-cc` (the create-course modal).
* Fix: delete the `@import` line. Either let `.ems-cc` fall back to the system stack, or self-host Inter and Fraunces woff2 under `static/fonts/` with `@font-face { font-display: swap }`. Use the second option only if the owner wants the look. Better still, load `course_create.css` only when the modal opens (see H4).

**H2. Live-exam pages block on Google Fonts in `<head>`.**
* Files:
  * `apps/live_exam/templates/liveExam/player_screen.html:11-13`
  * `join.html:10-12`
  * `wait_room.html:10-12`
  * `pin_entry.html:10-12`
  * `partials/_host_head_assets.html:3-5`
* Each loads `<link href="https://fonts.googleapis.com/css2?family=Manrope…&family=Space+Grotesk…" rel="stylesheet">`. That is a render-blocking third-party stylesheet on the phone join flow and the in-game player.
* If the phone cannot reach Google, the player stays blank until the request times out. The CSP allows Google today, so it works only when the client has internet access to Google.
* The CSS already has system fallbacks (`--lxp-font: "Manrope","Segoe UI",system-ui…`), so the page degrades cleanly once the dependency is gone.
* Fix: self-host Manrope 500/700/800 and Space Grotesk 500/700 as woff2 in `apps/live_exam/static/fonts/`, add `@font-face` with `font-display: swap` in `css/player/_base.css` and the join/wait-room base CSS, add `<link rel="preload" as="font" type="font/woff2" crossorigin>` for the two main weights, and remove the three Google lines from each template. Drop the Google entries from the CSP once nothing else uses them.

**H3. `bootstrap_select.js` builds every option menu eagerly. This is the DOM and CPU multiplier for all grids.**
* Evidence: `static/js/bootstrap_select.js` calls `refresh()` → `buildMenu()` at enhance time. It creates a `<button>` plus two `<span>`s plus an `<i>` plus a click listener per option, for every `[data-bootstrap-select]` on the page, even if the user never opens it.
* Measured. Source tag counts come from the HTML; runtime counts come from the real DOM in the browser:

| Page or benchmark | Source tags | Runtime elements |
|---|---|---|
| Groups registry (two 823-option dialog selects + two 86-option selects) | 4,387 | **12,069** |
| Schedule editor (822 groups + 401 teachers + 150 rooms) | 3,149 | **9,022** |
| Journal lecture cell (hidden input + select with 3 options), bench | about 6 | **25 nodes per cell** |
| Journal seminar cell (select with 0–10 scores, as the template comment states), bench | about 20 | **81 nodes per cell** |

* Journal cost, extrapolated from the bench on a desktop CPU:

| Roster × columns (default window = 20 lessons, `DEFAULT_LESSON_WINDOW`) | Cells | DOM nodes | Init | Layout |
|---|---|---|---|---|
| Lecture, 30 students × 20 | 600 | 16,000 | 20 ms | 42 ms |
| Seminar, 30 students × 20 | 600 | 49,600 | 31 ms | 56 ms |
| Lecture stream, 555 students × 20 (the size the template comment cites) | 11,100 | **278,000** | 214 ms | **732 ms** |

  On a phone or school PC, multiply by 4–6.
* Fix, in `static/js/bootstrap_select.js`:
  * Build the menu lazily on the first `show.bs.dropdown` (or first `pointerenter`/`focusin` on the toggle). At init, create only the dropdown wrapper and toggle, and set the label from the selected option.
  * Replace per-option `addEventListener` with one delegated `click` handler on `menu`.
  * Expected effect: lecture cell 25 → about 8 nodes, seminar cell 81 → about 8, groups registry 12k → about 5k elements, schedule editor 9k → about 3.5k.
  * `syncToggleState`/`syncSelectedState` must tolerate an unbuilt menu.

**H4. The exam/course creation modal stack ships on every teacher/staff cabinet section.**
* Evidence: 25 files, **316 KB raw / 79 KB gz**, present in teacher cabinet, schedule editor, workload, groups registry and system monitoring (not on the student dashboard). They are loaded for a modal almost nobody opens on those sections:
  * CSS: `my_exams.css` 38.9 KB, `exam_wizard.css` 42 KB, `exam_create_edit_modal.css`, `bulk_workbench_extras/_part1+2.css`, `course_create.css`, `create_course_modal.css`, `ems_datetime.css`.
  * JS: `exam_wizard.js` 25 KB, `my_exams_dashboard.js` 22 KB, `create_exam_modal.js`, `create_exam_selects.js`, the `exam_create_edit_modal/*` set (about 63 KB), `ems_datetime*.js` 26 KB, `course_create_form.js`, `create_course_modal.js`.
* Cause: the "shell" groups in `_section_assets.html` and `_section_scripts.html` are gated on `allowed_sections` (`'my-exams' in allowed_sections`, `'my-courses' in allowed_sections`), not on the rendered section.
* Fix, either:
  * (a) Gate them on `asset_sections` and let `section_assets.js` fetch them on SPA navigation to my-exams/my-courses.
  * (b) Keep them out of the page and load them on the first click of "Create exam/course", using the missing-asset loader that `section_assets.js` already provides.
* Expected saving on staff sections: about 300 KB raw, about 80 KB gz and 25 requests. It also removes `course_create.css`, and with it H1, from those sections.

**H5. Avatars are never resized, and they are served through Django with a 5-minute cache.**
* Evidence:
  * `apps/accounts/services/profile_actions.py:35` allows `MAX_PROFILE_AVATAR_SIZE_BYTES = 10 MB`. `validate_profile_avatar_upload` checks size, extension and dimensions only.
  * `services/profile_avatar.py:replace_avatar` stores the original. The only `Image.open` calls in `apps/accounts` are for academic attachments.
  * The local dev media folder holds four 8.9 MB PNGs in `media/avatars/` (`Gemini_Generated_Image_…png`, 8,947,250 bytes). Prod size distribution is unverified.
  * The navbar shows the avatar at 22–40 px, on every page.
  * `views/profile/avatar.py:53` sends `Cache-Control: private, max-age=300`. Every page visit after 5 minutes goes back through Daphne (user lookup, visibility check, profile query, file stream). There is no conditional handling, although `Last-Modified` is set.
* Fix:
  * On upload, downscale with Pillow to at most 256×256, re-encode as WebP or JPEG q82, and strip EXIF. Add a one-off management command to shrink existing files.
  * In the view, use `max-age=31536000, immutable`. The URL already carries `?v=<updated_at>`, so it changes when the file does.
  * Optionally let nginx serve the avatar through `X-Accel-Redirect` after the access check, as done for protected media.

### MEDIUM

**M1. First-party CSS and JS are not minified.**
* `docker/Dockerfile.prod` runs `collectstatic` only. WhiteNoise compresses but never minifies.
* Estimate (comment and whitespace stripping on all first-party files outside vendor; it undercounts real minification):

| Corpus | Raw | After | gz | After |
|---|---|---|---|---|
| CSS | 2,656 KB | 1,800 KB | 700 KB | 477 KB |
| JS | 3,607 KB | 2,378 KB | 1,051 KB | 738 KB |

  That is about 30% of gz bytes. On one cabinet page it is roughly 50–70 KB gz.
* Fix: add a per-file minify step before `collectstatic` (esbuild `--minify` for `.js`, lightningcss/csso for `.css`; no bundling, so module paths and `?v=` stay valid). Skip `*.min.*`. Keep sourcemaps out of the image.

**M2. Vendor CSS is mostly unused on first paint.**
* `bootstrap.min.css` is 227 KB raw. CSS coverage on the student dashboard shows about 20 KB of 238 KB of rule text used.
* `fontawesome/css/all.min.css` is 99.6 KB and ships 2,502 icon classes. Only about 360 icon-looking class names appear in templates, JS and Python.
* `fa-solid-900.woff2` is 147 KB and loads on every cabinet page. `@font-face` uses `font-display:block`, so icons are invisible while the file loads. There is no preload anywhere.
* Fix:
  * Subset Font Awesome with `pyftsubset` or fontawesome-subset: CSS about 10 KB, woff2 about 30 KB.
  * Add `<link rel="preload" as="font" type="font/woff2" crossorigin href="{% static 'vendor/fontawesome/webfonts/fa-solid-900.woff2' %}">` in `base.html`.
  * Build a trimmed Bootstrap (Sass, only used components) or run PurgeCSS with a safelist for dynamic classes.

**M3. On-demand features load on every authenticated page.**
* The following are eager in `base.html` even though most pages never use them:
  * AI assistant: `ai_assistant.css` 21 KB + `ai_assistant_fab.js` 18 KB + `ai_assistant.js` 21 KB.
  * Global search: `global_search.css` 17 KB + `global_search.js` 22 KB.
  * `view_as.css` 16 KB + `view_as.js` 13 KB, for privileged users.
  * `ems_datetime*` (see H4).
* Together that is about 110 KB raw, about 30 KB gz and 5 requests per page.
* Fix: load them on first interaction (FAB click, ⌘K, view-as toggle) with a tiny loader. `EMSReady` stubs already exist for deferred registration.

**M4. The student dashboard pulls CSS for sections it does not render.**
* About 120 KB raw of unconditional links in `_section_assets.html`: `assigned_exams`, `assigned_courses`, `my_courses`, `courses`, `my_results`, `my_results_academic`, `notifications*`, `posts/_part1+2`, `profile_info*`, `list_cards`, `blogCard`.
* Coverage on the dashboard: `assigned_exams.css` 0.2 of 12.4 KB used, `profile_info.css` 0.5 of 9.5 KB, `my_results.css` 0.1 of 8.9 KB.
* Fix: move these links under `asset_sections` conditions, the way `pending_review.css` and the workload CSS already are. Extend `SECTION_ASSET_BORROWS` where one section reuses another's file.

**M5. Duplicated option lists bloat the HTML.**
* Groups registry HTML is 537 KB (85 gz) and the schedule editor 339 KB (57 gz).
* Groups registry has two identical 823-option group `<select>`s in the always-in-DOM dialogs (`#tofStudentTransferDialog-target` and `#tofGroupMoveDialog-target`, 79 KB each). It also has two 86-option specialty selects (11 KB each).
* Schedule editor has an 822-option group filter (95 KB), 401 teachers (26 KB) and 150 rooms (14 KB).
* Fix:
  * Use the existing server-backed `EMSSearchableSelect` (`static/js/searchable_select.js`, `data-search-url`, 10-per-page infinite scroll) for groups and teachers. Lazy-filling the dialog selects from the first fetch is the minimum.
  * Alternatively emit the group list once as a `application/json` script block and fill the dialogs on open.
  * Expected saving: about 160 KB HTML and about 3,300 enhanced nodes per removed select.

**M6. The `<head>` is a long synchronous chain.**
* `base.html` puts 6 classic scripts in `<head>` without `defer` (64 KB): `ems_early.js`, `search_fold.js`, `ems_search_input.js`, `ems_search_swap.js`, `searchable_select_keys.js`, `searchable_select.js`. It also links 24 global stylesheets, plus 40–58 section stylesheets on cabinets.
* The comment justifying this (`base.html:84-92`, a section's inline script calling `EMSSearchableSelect` during parse) looks stale. The project now forbids inline JS, and the checker finds none.
* Fix:
  * Check that nothing calls `EMSSearchableSelect`/`EMSSearch*` at script top level, then add `defer`.
  * Concatenate the global CSS (24 files) and the shell CSS into 2–3 build artefacts so a cold start is about 8 requests, not about 65.

**M7. The live player's ES module graph is revalidated on every game start.**
* The 25 modules (`js/player/*.js?v=lx20261014`, 141 KB raw / 50 KB gz) are imported by relative path, which `ManifestStaticFilesStorage` cannot rewrite. They are therefore served unhashed.
* The nginx `$ems_static_cache_control` map gives unhashed names `public, no-cache`, so every start of every phone does 25 conditional GETs (304s) even though `modulepreload` fetches them in one wave. The wait-room `prefetch` does not avoid the revalidation.
* That is deliberate and safe: see the docstring of `apps/live_exam/tests/test_static_module_versions.py`, which records the earlier 30-day-immutable staleness incident. It is a latency cost, not a correctness bug.
* Fix: bundle `player.entry.js` and `host_lobby.entry.js` into one hashed file at build time (esbuild, ESM, no splitting). That gives one request, immutable, and no `?v=` token to bump by hand. Do not make `?v=` URLs immutable in nginx: the token is manual.

### LOW

* **L1. Avatar caching.** Covered in H5. Even without resizing, the `max-age` change alone is a one-liner.
* **L2. Brand assets.** `static/brand/wcu-official-mark.png` is 240×218 and displayed at 40×40 (18.5 KB; a 96 px WebP is enough). `wcu-official-lockup.svg` on the login page is 47 KB and still 27 KB gzipped; run svgo with a lower coordinate precision.
* **L3. Favicons.** `/favicon.svg` and `/favicon.ico` answer a 301 to static (cached 1 day) through Django. Point `<link rel="icon">` straight at the hashed static URL. `_seo_head.html` also emits 7 `rel=icon` links.
* **L4. Pollers without a hidden-tab guard** (all at 30–60 s, so low impact): `exams/js/final_center/room_monitor.js:328` (30 s snapshot fallback), `final_center/snapshot_modal.js:78` (30 s), `final_center/waiting_room.js` fallback (30 s), `audit/audit_log.js:512` (60 s), `static/js/ai_assistant.js:455` (60 s, on every page). Add `if (document.hidden) return;` and refresh on `visibilitychange`.
* **L5. Duplicate `<link>`.** `pagination.css` is linked in `base.html:54` and in `_section_assets.html:106`. Harmless; remove one.
* **L6. Login page weight.** It loads `bootstrap.bundle.min.js` (78 KB) + `bootstrap_select.js` (16 KB) + `bootstrap-select.css` for the language select, and the 87 KB `jsi18n` catalogue synchronously in `<head>` (`base_auth.html`). A tiny language menu would avoid about 95 KB of JS on the page every student hits first. `jsi18n` could move to body end with `defer` if `base_auth.js` and `login_lockout.js` do not call `gettext` at load.
* **L7. No Brotli.** nginx uses gzip level 5 plus `gzip_static`. The stock image has no brotli module, so skip unless the image is rebuilt.
* **L8. Big vendor files on single pages.** `codemirror/lib/codemirror.js` is 392 KB unminified (coding exam only). `katex.min.js` is 266 KB (exam pages only). `chart.umd.min.js` is 201 KB and blocks the parser at body end on 5 sections; add `defer` and call through `EMSReady`.
* **L9. Manual `?v=` tokens.** `?v=…` on every `{% static %}` link is redundant under the manifest storage (the URL already carries a content hash) and a stale-token risk for any path served unhashed. Leave as is; do not add more.

## 3. Mobile (375 px), CLS, long tasks

### 3.1 Layout at 375 px

Emulated 375×812. I scanned `<main>` for elements wider than the viewport that are not inside a clipping or scrolling ancestor.

| Page | Horizontal scroll | Overflowing elements outside clipping containers |
|---|---|---|
| Login staff | none | 0 |
| Student cabinet | none | 0 |
| Teacher cabinet | none | 0 |
| Journal list | none | 0 |
| Journal detail (empty) | none | 0 |
| Schedule editor | none | 0 |
| Workload distribution | none | 0 |
| Groups registry | none | 0 |
| System monitoring | none | 0 |
| Teacher «Elektron jurnal» | none | 0 |

* The off-canvas mobile nav panel is positioned outside the viewport as designed; I excluded it as a false positive.
* Caveat: `body` uses `overflow-x: clip` (per the cabinet notes). This hides any real overflow instead of scrolling, so I checked elements in `<main>` directly. The snapshots had no AJAX-filled tables, so wide data grids were not exercised.

### 3.2 Layout shift and long tasks

* CLS = 0 on all ten pages measured. Fonts and CSS were warm and local, so first-load shift with `font-display:block` icon fonts on a slow network is **not** measured.
* No long tasks (>50 ms) were reported on any page load on this CPU. That is not a clean bill for slow devices: the bench in H3 shows layout of 600 enhanced journal cells costs 56 ms on a fast desktop, and 11,100 cells costs 732 ms.

### 3.3 DOM size of the big grids

* **Journal grid.** Windowed to 20 lesson columns by default (`journal_window.DEFAULT_LESSON_WINDOW`), and `{% spaceless %}` is used. The clone's journals are empty, so the measured page has only 1,040 elements. The extrapolation in H3 stands on the per-cell cost of the real template markup.
* **Timetable matrix (`/jurnal/cedvel/`).** One `<button class="smtx-card">` per slot with about 20 `data-*` attributes and no per-cell `<select>`. Cost is O(slots). The clone's timetable is empty (the page is 50 KB with 48 `<td>`), so I could not measure at scale. Re-measure on the prod-copy before judging.
* **Schedule editor.** 9,022 elements at runtime, of which about 5,900 come from enhanced selects (H3).

## 4. What is already fine

* **Static caching.** `docker/nginx/nginx.conf` maps hashed `name.<12hex>.ext` to `public, max-age=31536000, immutable` and unhashed names to `public, no-cache`. `CompressedManifestStaticFilesStorage` is on in production. `gzip_static on` plus dynamic `gzip` (level 5, JS/CSS/JSON/SVG types), `http2 on`, `open_file_cache`, and `X-Content-Type-Options` on every static block.
* **JS translation catalogue.** `core/jsi18n.py`: versioned URL, `private, max-age=31536000, immutable`, built once per process; 87 KB raw / 15.7 KB gz.
* **Per-section assets.** The cabinet gates most section CSS and JS on `asset_sections` and loads missing assets on SPA swaps. Chart.js is limited to the 5 sections that need it; KaTeX and CodeMirror to exam pages.
* **Auth pages** use a light base (`base_auth.html`) with no navbar, no Font Awesome and no AI widget.
* **No inline JS or CSS** anywhere measured, matching the CSP rule.
* **Journal windowing** (20 columns) and `{% spaceless %}` already fixed the earlier 41.5 MB HTML case.
* **Polling is well behaved.**
  * Live player: `polling.js` backs off 4 → 8 → 16 → 30 s when the server message is overdue, skips ticks when `document.hidden`, and uses WebSocket as primary with a 3 s fallback only if the socket is closed.
  * Wait room and host lobby: hidden-tab guarded; lobby resync about 15 s, host state poll only when the WS is closed.
  * System monitoring: 30 s step (heavy tabs every 60 s), skipped when hidden or detached, aborts in-flight requests.
  * Final-center rooms: 30 s fallback only when the WebSocket is down.
* **Images.** `loading="lazy"` on list images; all `<img>` except the navbar avatar have explicit dimensions.
* **Live player preload.** `modulepreload` for the whole import graph and `prefetch` from the wait room are in place, and CSS has system-font fallbacks.
* **Layout shift.** CLS 0 and no horizontal overflow at 375 px on every page measured.

## 5. Top 5 fixes, in order

1. **Remove the third-party Google Fonts dependency**: delete the `@import` in `apps/courses/static/courses/css/course_create.css:12`, and self-host Manrope/Space Grotesk for the live templates (H1, H2).
2. **Make `bootstrap_select.js` lazy**: build the option menu on first open and delegate clicks. This cuts DOM by 60–70% on the registry and schedule editor and 3× on journal cells (H3).
3. **Stop loading the exam/course creation modal stack (316 KB / 25 files) on every staff section**: gate on `asset_sections` or load on first click (H4).
4. **Downscale avatars on upload and cache them immutably**: Pillow to 256 px WebP/JPEG, `max-age=31536000, immutable` in `views/profile/avatar.py`, plus a one-off shrink of existing files (H5).
5. **Add a build step**: minify first-party CSS/JS (about 30% gz) and bundle the live player graph; then trim Bootstrap/Font Awesome and preload the icon font (M1, M2, M7).
