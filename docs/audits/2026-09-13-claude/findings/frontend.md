# AUDIT — FRONTEND · UX/UI · ƏLÇATANLIQ · NAVİQASİYA · LOKALLAŞDIRMA — `frontend`

Tarix: 2026-09-13 · Develop HEAD (audit başlanğıcı): `7c5dc612` · Auditor: read-only (Claude)
Bazis: Codex 2026-09-12 §19/§20 (Frontend 73, A11y 70); bu audit yalnız onların açıq/yoxlanmamış qoyduqlarını və yeni yoxlamaları əhatə edir.
Sənəd inkremental yazılır — «NOT TESTED» qalan bəndlər kəsilmə halında olduğu kimi qalır.

## 0. Xülasə
1. 343 layihə JS faylı statik təhlil edildi: AJAX-safety (EMSReady/EMSDelegate) kabinetdə praktiki tam gözlənilir; CSRF bütün POST-larda (FormData/`X-CSRFToken`) var; qalıq — 4 geri sayım faylında swap-dan sonra sızan `setInterval`, 4 `console.log`, dərs yükü SPA-sının i18n-siz 18 AZ literalı.
2. 7 rol (student, teacher, ikt_rehber, exam_center_head, dean, tutor, rector) × dashboard + 8–45 bölmə brauzerdə açıldı: **0 CSP pozuntusu, 0 JS xətası, 0 4xx** (yalnız öz `GET /logout/` 405-im); tək 500 — `exam-score-entry`, səbəb clone DB-nin `registrar.0071–0075` miqrasiyalarının tətbiq olunmaması (mühit).
3. Bölmə swap-ları 0.86–1.25 s (analytics/lessons-log/syllabus-list 2.0–2.9 s); heç bir resurs >1.5 s deyil.
4. UX: `ems_ui` qatı kabinetdə hakimdir, amma 5 paralel BEM sistemi (apx/syl/rim/tx/qsubs/smx ≈ 950 class istifadəsi) və 1 194 legacy `card` (əsasən kabinetdən kənar) qalır; native `<select>` yalnız 2 çox-seçimli listbox-da; təhlükəli əməllər təsdiqlidir (22-si hələ native `confirm()`).
5. A11y: skip link, tək `h1`, `aria-current`, `aria-modal` + fokus tələsi, reduced-motion — PASS; **FAIL**: AJAX keçidindən sonra fokus `body`-də qalır (bütün rollar), `neutral-400` (2.56:1) 63 qaydada mətn rəngi, 13–18 px hədəflər (checkbox, sort linkləri), iç-içə `<main>`.
6. Lokallaşdırma: yerdəyişənlər 100% uyğun, kataloqlar dolu; amma **4 P1** — «Close»→«открыть/açık», «Clear selection»→«Удалить/Silmek», «Check»→«Geri/Back» (4 dildə), və kök səbəbli **613 `pgettext(_CTX, …)` sətri heç bir kataloqda yoxdur** (skaner/xgettext modul sabitini görmür) → RU/EN/TR-də audit-log, groups-registry, org-members, registry, intake səhifələri qarışıq dilli.
7. Responsiv 375/768/1024: heç bir bölmədə üfüqi daşma yoxdur, bütün cədvəllər scroll sarğısında, sticky başlıqlar var, mobil sidebar off-canvas + backdrop + ESC işləyir.
8. Yoxlanıla bilməyənlər: screenshot (pane gizli), «ilk resize» keçidi (emulyasiya `change` hadisəsi göndərmir), jurnal grid-i (clone-da 0 offering), imtahan sihirbazı modalı, exam-score-entry (500), HR rolu (parol yoxdur), real klaviatura marşrutları.
9. Codex §19/§20-yə nisbətən yeni: F3/F1/F2 semantik tərcümə qüsurları, F4 kataloq qapısının kor nöqtəsi, F5 fokus idarəsi, F6 kontrast tokenləri, F14 `rim-center` drift-i.
10. Tövsiyə: F1–F4 (i18n) və F5 (fokus) bu dalğada; F6/F11 token/ölçü düzəlişləri CSS səviyyəsində ucuzdur; clone DB `migrate` edilsin ki, bal daxiletmə UI-ı yoxlanıla bilsin.


## 1. JS keyfiyyəti — pozucu inventarı
Metod: `js_inventory.py` (343 layihə JS faylı, 66 446 sətir; vendor yoxdur) + `js_ready_listeners.py` (EMSReady gövdəsində document/window listener-lərin lexik təhlili) + əl ilə yoxlama. Nəticə faylları: `js_inventory.txt`, `js_inventory.json`, `js_ready_listeners.txt`, `js_hardcoded_az.txt`.

| Yoxlama | Nəticə | Sübut |
|---|---|---|
| `DOMContentLoaded` + `querySelectorAll().forEach(addEventListener)` antipattern-i | **PASS (kabinet)** — 48 fayl yalnız DCL işlədir, amma hamısı ya tam səhifədir (take_exam, live_exam, register, question bank), ya `initAll(scope)` ilə `profile:section:loaded`-a qoşulur (`overall_academic.js:168-176`, `permission_editor.entry.js:60-68`), ya da `document`-delegasiya + qlobal modal işlədir (`create_course_modal.js:296-335`; modal `profile.html:37`-də paneldən kənar qəsdən). Sırf `qsa.forEach(addEventListener)` 6 faylda (assignment_modals, teacher_check_attempt, testQuestionBank, project_modals, review_submissions×2) — hamısı tam səhifə, AJAX swap olunmur. | `js_inventory.txt` §1-2; `sections_api.py:181-300` (`AJAX_SAFE_SECTIONS`) ilə çarpaz yoxlama: `create-category`/`category-management` AJAX-safe DEYİL → `category_management.js` DCL problemsiz |
| EMSReady gövdəsində `document/window.addEventListener` (swap-da yığılma) | **PARTIAL** — 7 fayl; 5-i qorunur (`teaching_office_groups.js:269 __tofGroupStudentsBound`, `journal_guest.js:505 data-jgs-ready`, `pending_post_approvals.js` once, `chair_review.js` trap açılış/bağlanışda qoşulur/silinir). Qorunmayan: `student_exam_list_filters.js:74` (`window.pageshow`, my-exams AJAX-safe → hər swap-da +1 idempotent listener, zərərsiz) və `final_result_timeout.js:76,81` (tam səhifə). | `js_ready_listeners.txt` |
| Raw `fetch` POST CSRF-siz | **PASS** — 145 raw `fetch`, 82 `EMSCore.fetchJSON`, 120 XHR. CSRF başlığı olmayan 18 fayldakı bütün POST-lar `new FormData(form)` göndərir (form içində `{% csrf_token %}`), yəni token body-dədir. JSON gövdəli tokensiz POST tapılmadı. | `js_inventory.txt` §4 + `python3` yoxlaması (FormData) |
| fetch-də error handling yoxdur | **PASS** — yalnız `applications_core.js` (`fetchJSON` ×6) `.catch` göstərmir; yoxlama: `try/await` ilə sarılıb. | `js_inventory.txt` §5 |
| `setInterval` təmizlənmir (swap-da sızma) | **FAIL (P3)** — 13 fayl. Kabinet bölmələrində sızan: `pending_answers_countdown.js:47`, `pending_review_countdown.js:59`, `assignments/review_submissions.js:59`, `teacher_pending_attempts.js:47` — hər kart üçün `setInterval` yaradılır, `dataset.countdownBound` yalnız eyni node-a təkrar bağlanmanı kəsir; bölmə swap olunanda köhnə node-lar DOM-dan çıxır, interval isə ömürlük 1 s-də bir detached node-a yazır. `appeals_sections.js:420` modul səviyyəsində tək interval (OK). `final_center/room_aggregate.js:512`, `take_exam/draft.js`, `live_exam/player/flow.js` tam səhifədir. | `js_inventory.txt` §6, kod oxunuşu |
| Observer disconnect yoxdur | PASS — 2 fayl (`question_submission_review_questions.js`, `journal_student.js`), hər ikisi tam səhifə. | §7 |
| `console.log` qalıqları | **FAIL (P3)** — `courses/js/topic_edit_modal.js:45,66,130` (3 debug log, biri «✓ Topic Edit Modal initialized»), `live_exam/js/host_lobby/utils.js:278` (`log()` hər çağırışda `console.log`, debug bayrağından ƏVVƏL). | grep |
| Qlobal ad sahəsi | **PARTIAL** — 36 DOM faylı IIFE-siz; `register_wizard/*.js` (5 fayl, 130+ top-level `var/function`), `courses/js/{forms,modal,notifications,accordion}.js` (38 top-level) `window`-a birbaşa yazır. Kabinet faylları (`profile/*`) hamısı `ns.register` namespace-dədir. | `js_inventory.txt` §9 |
| Double-submit qoruması | **PARTIAL** — 22 faylda `submit` handler var, `inFlight/disabled` nümunəsi yoxdur; oxunanlardan `journal_close.js:170` yalnız `window.confirm`, `final_center/confirm_forms.js` disable etmir. Müsbət: `create_course_modal.js:5 submitInFlight`, `section_loader.js` AbortController, `applications_core.js` busy bayrağı. | `js_inventory.txt` §10 |
| JS-də hard-coded AZ mətn (i18n-siz) | **FAIL (P2)** — `profile/workload_distribution.js` (9: `339 confirm("Sətir silinsin?")`, `400 confirm("Bölgü silinsin?")`, `516 "Qalıq: "`, `534 "Vakant (müəllim təyin edilməyib)"`), `workload_distribution_render.js` (8: `79 aria-label="Bölgünü sil"`, `56 "Bölüşdür"`, `110 "Redaktə"`, `139 "Hələ bölgü yoxdur."`), `workload_my.js:54 "Aç"`. Bu 3 faylda `gettext`/`data-*` i18n körpüsü **yoxdur** → EN/RU/TR-də dərs yükü paneli qarışıq dildə. Qalan 100+ AZ literal `gettext()` (JavaScriptCatalog `/jsi18n/`) və ya `||` fallback-dır — PASS. | `js_hardcoded_az.txt`; `grep -c gettext` = 0 |
| Native `confirm()` qalıqları | PARTIAL — 22 çağırış (EMSConfirm 6 faylda). Kabinetdə: `workload_distribution.js:339,400`, `teaching_office.js:459`, `org_units.js:378`, `student_intake.js:367`, `legacy_grade_review_actions.js:112`, `journal_close.js:170`; kurs/tapşırıq səhifələrində 10+. | grep |

**Pozucu inventarı (düzəliş üçün):** (a) `pending_answers_countdown.js`, `pending_review_countdown.js`, `assignments/review_submissions.js`, `teacher_pending_attempts.js` — interval id-ni node-da saxla, `render()` içində `if (!node.isConnected) clearInterval(id)`; (b) `topic_edit_modal.js`, `host_lobby/utils.js` — `console.log` sil / debug bayrağı altına al; (c) `workload_distribution*.js`, `workload_my.js` — mətnləri `gettext()` və ya panel `data-*`/`json_script` körpüsünə keçir; (d) `student_exam_list_filters.js:74` — `EMSReady.once`.


## 2. Konsol / şəbəkə süpürməsi (rol üzrə)
Mühit: dev clone `:8011` (clone DB `emsarena_rehearsal_a0d170000901`), UI dili EN (brauzer), viewport 1024 px; in-page harness `probe_harness.js` (`securitypolicyviolation` + `error` + `unhandledrejection` dinləyiciləri, hər bölmədə `profile:section:loaded`-dan sonra ölçmə; «yavaş» = resurs >1500 ms; Browser pane gizli olduğu üçün **screenshot çəkmək mümkün olmadı** — bütün sübutlar DOM ölçmələridir, xam qeydlər `sweep_notes.md`). Login: `qa.<rol>` / `<QA parolu>` (`qa.sec.hr` bu parolu daşımır → HR NOT TESTED).

| Rol | Açılan | Konsol xətası | JS `error`/`unhandledrejection` | CSP pozuntusu | 4xx/5xx | >1.5 s | Qeyd |
|---|---|---|---|---|---|---|---|
| qa.student | dashboard + 13 bölmə (12 AJAX, statistics tam səhifə) | 0 | 0 | 0 | 0 | 0 | swap 0.87–0.98 s (0.8 s settle daxil) |
| qa.teacher | dashboard + 11 | 0 (yalnız öz `GET /logout/` 405-im) | 0 | 0 | 0 | 0 | lessons-log 1.2 s |
| qa.ikt_rehber | dashboard + 45 | 0 | 0 | 0 | 0 | 0 (resurs səviyyəsində) | bölmə swap-ı: analytics 2.85 s, lessons-log 2.52 s, syllabus-list 2.03 s, teaching-handover 1.5 s — qalanı ≤1.25 s |
| qa.exam_center_head | dashboard + 14 (6-sı tam səhifə) | **1 × 500** | 0 | 0 | **`?section=exam-score-entry` → 500** (2 cəhd) | 0 | səbəb mühitdir: clone DB `registrar.0070`-dədir, repo `0071_exam_score_sheet`…`0075` tətbiq olunmayıb → `relation "registrar_examscoresheet" does not exist` (`apps/registrar/exam_score_entry.py:236`). Frontend qüsuru deyil; bal daxiletmə UI-ı brauzerdə NOT TESTED |
| qa.dean | dashboard + 15 | 0 | 0 | 0 | 0 | 0 | teaching-handover 1.56 s |
| qa.tutor | dashboard + 8 | 0 | 0 | 0 | 0 | 0 | — |
| qa.rector | dashboard + 8 (+ 10 bölmə 375 px, 3 bölmə 768 px) | 0 | 0 | 0 | 0 | 0 | analytics 2.27 s |
| qa.sec.hr | — | — | — | — | — | — | NOT TESTED (parol yoxdur) |

Əlavə müşahidələr (bütün rollarda eyni):
- `h1` = 1 (yalnız `#profileSectionTitle`), `main` = **2** (`templates/base.html:139 <main id="main-content">` içində `profile.html:24 <main class="profile-main">` — iç-içə landmark).
- AJAX swap-dan sonra `document.activeElement` = `BODY` — fokus yeni bölmə başlığına aparılmır (`section_loader.js`-də `focus()` çağırışı yoxdur).
- `rim-center` serverdə `AJAX_SAFE_SECTIONS`-dadır (`sections_api.py`), amma `profile.html:16 data-ajax-sections` siyahısında **yoxdur** → həmişə tam səhifə yüklənir; `test_section_registry_consistency.py` yalnız client⊆server yoxlayır (server⊆client yox).
- `statistics` (`data-force-navigation`), `academic-records`, `publish-notification`, imtahan mərkəzi bölmələri (pins/stats/kollokvium/exam-chance) — dizayn üzrə tam səhifə.
- Xam yerdəyişən `%(x)s` / `{x}` mətn heç bir bölmədə görünmədi.


## 3. UX ardıcıllığı (komponent sayları, təhlükəli əməllər, native select, fokus)
Metod: `ux_scan.py` (şablon skaneri, şərhlər çıxarılmaqla; nəticə `ux_scan.txt`/`ux_scan.json`) + brauzer.

**Komponent ailələri (class istifadə sayı, e-poçt şablonları xaric):** `card` 1194 · `syl-*` 594 · `ems-btn` 300 · `apx-*` 153 · `ems-table` 144 · `modal fade` 75 · `rim-*` 65 · `btn btn-primary` 50 · `ems-card` 50 · `smx-*` 16 · `qsubs-*` 28 · `tx-*` 58 · `table table-` 11. Kabinet bölmələri üzrə ən çox ad-hoc: `applications_dialogs` (apx 82), `applications` (apx 70), sillabus redaktoru/rəyi (`syl-` 64+61+51+50+44+40+39), `rim_center` (rim 63), `my_exams_card` (tx 36), `question_chair_review` (qsubs 28), `system_monitoring` (smx 16). Legacy Bootstrap `card` kabinetdən kənar səhifələrdə cəmlənib (`teacher_exam_detail` 59, `teacher_exam_statistics` 54, `_question_management` 40, register `_step2` 32, `question_submission_*` 31/29/21, live_exam 30, labs/projects 10–18). **PARTIAL** — `ems_ui` qatı kabinetdə üstünlük təşkil edir, amma 5 paralel BEM sistemi (apx/syl/rim/tx/qsubs/smx) hələ də ~950 class istifadəsi ilə yaşayır.

| Yoxlama | Nəticə |
|---|---|
| Native `<select>` (sahib qaydası) | **PASS (praktiki)** — 283 select `data-bootstrap-select`/`bootstrap-single-select` ilə; qalan 5: `teaching_office/_generate_fields.html:10` və `workload/_generate_fields.html:5` (`multiple size="8"` — çox-seçimli listbox, komponentin tək-seçim olduğu üçün əvəzsiz), `_create_exam_modal_form.html:333,355,360` (`d-none` gizli proxy). Brauzerdə heç bir bölmədə görünən native select tapılmadı (`nativeSelects=0`). |
| Təhlükəli əməl təsdiqsiz | **PASS** — skanerin 6 namizədi əl ilə yoxlandı: bildiriş silmə (tək+toplu) `notifications.js:265-303` modal ilə; jurnal sərbəst iş silmə `journal_grid.js:387-398` `alertdialog`; `EMSConfirm` 6 faylda. Qalıq: 22 native `confirm()` (`workload_distribution.js:339,400`, `teaching_office.js:459`, `org_units.js:378`, `student_intake.js:367`, `legacy_grade_review_actions.js:112`, `journal_close.js:170`, kurs/tapşırıq səhifələrində 10+) — təsdiq VAR, amma vahid dialoq deyil (P3). `_superadmin_organizations_content.html:131` «Rədd et» səbəb sahəsi ilə birbaşa submit (təsdiqsiz) — superadmin, P3. |
| İkon-only düymə adsız (`aria-label`/`title`/sr-only yox) | **FAIL (P3, 18 yer)** — `assignments/review.html:21,80,85`, `teacher_group_list.html:65,81,252`, `labs/manage_blocks.html:158,165`, `accounts/assigned_exams.html:27,80` (axtarış `btn-primary` + `fa-search`), `assigned_courses.html:27`, `assignment_detail.html:190`, `host_lobby.html:86`, `course_members.html:111`, `_member_accordion.html:79`, `_post_edit_modal.html:7`, `_superadmin_contact_messages.html:363`, `_student_org_request_content.html:125`. Kabinet qabığı (`_navbar`, `sidebar/*`, `_header`) — PASS (Agent F qoruyucu testi). |
| Form sahəsi etiketsiz | PARTIAL — skaner 86 namizəd (ən çox `_jd_lesson_modal.html` 9, `syllabus/_editor_plan.html` 4, `_pending_review_content.html` 4, `_create_exam_modal_form.html` 4); heuristikdir, brauzerdə yoxlanmadı. |
| `<img alt>` | PASS — 0 alt-sız şəkil. |
| Fokus konturu qlobal silinməsi | **PASS** — `outline:none/0` 128 qaydada, hamısında (2 istisna) `box-shadow`/`border` fokus əvəzi var; qlobal `*`/`button` reset yoxdur; `:focus-visible` 40 qaydada. İstisna: `registrar/css/jd2.css:56,62` (`.jd2-filter select:focus`, `.jd2-filter-search:focus { outline:none }` əvəzsiz) — WCAG 2.4.7 (P3). |
| Cədvəl boş/yükləmə vəziyyəti | PASS (nümunə) — `ems-empty` my-journal/my-workload/workload-distribution-da görünür; `section_loader` `is-loading` + `EMSRouteProgress`; `_skeleton_rows.html` mövcuddur. |
| İkiqat «primary» düymə | NOT TESTED (vizual; screenshot yoxdur). |
| Inline `<style>`/`<script>` (CSP) | **PASS** — 0 inline `<style>`; 22 inline script gövdəsi, hamısı ya `nonce` (17: take_exam, live_exam, `_seo_head` ld+json, clarity, language switcher), ya `application/json` (5). `style="…"` atributu 205 (197 statik), 122-si e-poçt şablonlarında (legitim), qalan 75-dən: `password_reset_email.html` 17, `_bank_picker_shell.html` 7, `take_exam.html` 3, `_snapshot_modal.html` 3 … — CLAUDE.md «statikləri class-a çevir» hədəfi üçün qalıq. |
| Qlobal AZ mətn brauzer `lang` ilə | `document.documentElement.lang` = seçilən dil (en/ru) — PASS. |


## 4. Əlçatanlıq (WCAG 2.1 AA)
| Meyar | Nəticə | Sübut |
|---|---|---|
| 2.4.1 Skip link | PASS | `templates/base.html:98` ilk fokuslanan; `main#main-content tabindex=-1` (:139); brauzerdə `.skip-link` mövcud |
| 1.3.1 / ARIA landmark — tək `main` | **FAIL (P3)** | `base.html:139 <main>` + `profile.html:24 <main class="profile-main">` iç-içə → 2 `main` (bütün kabinet səhifələrində ölçüldü). Düzəliş: `profile.html:24` → `<div class="profile-main" role="region" aria-label=…>` |
| 2.4.6 / 1.3.1 Tək `h1` | PASS | hər bölmədə `h1`=1 (`#profileSectionTitle`); `test_cabinet_no_duplicate_titles.py` qoruyur |
| Başlıq sırası (h1→h3 atlaması) | PARTIAL | `headingSkips=1` bölmələrdə: dashboard, workload-distribution/center/overview, people-students/teachers, teacher-intake, student-admission, curriculum-editor, semester-opening, my-exams, my-courses, assigned-exams, my-results, pending-review (h2 atlanıb h3) — P3 |
| 2.4.3 Fokus sırası — AJAX swap-dan sonra | **FAIL (P2)** | `activeEl=BODY` hər swap-dan sonra (7 rol × 100+ bölmə); `section_loader.js` `replaceSectionHtml` sonra `#profileSectionTitle`-a fokus vermir və `aria-live` elan etmir. Düzəliş: `replaceSectionHtml` sonunda `title.setAttribute('tabindex','-1'); title.focus({preventScroll:false})` |
| 2.4.3 Off-canvas sidebar fokus | PARTIAL (P3) | 375 px: toggle → sidebar açılır (`aria-expanded=true`, `body overflow:hidden`, backdrop `pointer-events:auto`), amma fokus sidebar-a keçmir; ESC bağlayır (`aria-expanded=false`) amma fokus toggle-a qayıtmır (`activeEl=BODY`) |
| 4.1.2 `aria-current` | PASS | sidebar aktiv link `aria-current="page"` (`ui.js:315-326`), hər bölmədə 2 element (link + qrup) |
| 4.1.2 `aria-expanded/controls` | PASS | `_header.html:6-7` toggle; `aria-expanded` mobil açıb-bağlamada sinxron |
| 4.1.3 Status mesajları (`aria-live`) | PARTIAL | qabıqda 2–3 live region (toast + bölmə); bölmə dəyişməsi elan edilmir; login səhifəsində «Please enter a correct username…» xətası `div.auth-page-wrapper` içində düz mətn — `role="alert"` / `aria-invalid` / `aria-describedby` YOX (P3, `login.html`) |
| 2.5.8 Hədəf ölçüsü (min 24×24, WCAG 2.2 AA) | **FAIL (P3)** | qabıq: bütün hədəflər ≥24 (sidebar link 251×40, toggle 32×32, AI chat close 36×36 — 44 AAA-dan kiçik). Bölmələr: `permission-editor` 112 checkbox **13×13**; `groups-registry` checkbox 13×13; `people-students/teachers` checkbox 13×42 + `BUTTON.people__th-sort` 64×**18**; `A.ems-sort` 48–127×**18** (audit-log, student-registry, groups, programs, subject-catalog, superadmin-exam-rooms); `BUTTON.rls-chip__x` **18×18** (manage-roles); `INPUT.thx-pick__box` 16×16 (teaching-handover); cədvəl daxili ad linkləri 17–22 px hündür (inline istisnasına düşür). Düzəliş: `ems_table` sort linklərinə `min-height:24px; padding-block:3px`; checkbox-lara 18–20 px + 24 px klik sahəsi |
| 2.4.7 Fokus görünür | PASS (2 istisna `jd2.css:56,62`) | §3 |
| 2.3.3 / reduced-motion | PASS | `prefers-reduced-motion` 40 CSS qaydasında |
| 1.4.3 Kontrast (badge/status palitrası) | **PARTIAL** | `contrast.txt` (WCAG formulu, `design-tokens.css`). `ems_ui/badge.css` bütün variantlar PASS: success `#15803d/#dcfce7` 4.57, warning `#92400e/#fef3c7` 6.37, danger `#b91c1c/#fee2e2` ≈5.7, info 8.01, primary 7.15, neutral 9.45, muted 6.92. **FAIL**: tokenlərin MƏTN kimi istifadəsi — `--ems-neutral-400 #94a3b8` ağ üzərində **2.56:1**, 63 CSS qaydasında `color:` (məs. `sidebar.css:191 .sidebar-menu-ext 0.62rem`, `:329 0.66rem`, `applications_modal.css:288 .apx-step__when 0.72rem`, `dashboard.css:45`); `--ems-success-600` 3.77 (28 qayda), `--ems-danger-500` 3.76 (16), `--ems-warning-600` 3.19 (25), `--ems-primary-500` 3.68 (16) — normal ölçülü mətn üçün AA-dan aşağı (ikon/dekorativ istifadələr istisna). Düz düymələr: `#fff` on `primary-600` 5.17 PASS, on `danger-600` 4.83 PASS, on `success-600` **3.77**, on `danger-500` **3.76**, on `warning-500/600` **2.15/3.19**. Düzəliş: mətn üçün `neutral-500`+ (4.76), `success-700`, `danger-600`, `warning-700`; solid uğur/xəbərdarlıq düymələrində tünd ton |
| Modal semantikası / fokus tələsi | PASS (kod) | `ems_ui/_dialog.html:18`, `_form_dialog.html:28`, `_drawer.html:14` `role=dialog aria-modal aria-labelledby`; `static/js/ems_ui/overlay.js:38-102` FOCUSABLE siyahısı + ilk fokus + Tab tələsi + scroll kilidi. Legacy Bootstrap `modal fade` (75 istifadə, kabinetdən kənar) Bootstrap-ın öz tələsinə güvənir |
| Klaviatura: dropdown/wizard/cədvəl əməlləri (real klaviatura) | NOT TESTED (screenshot/klaviatura sürüşü mümkün olmadı; sintetik ESC yalnız sidebar üçün yoxlandı) |


## 5. Lokallaşdırma semantikası
Metod: `po_semantic_scan.py` (polarite lüğətləri, yerdəyişən dəstləri AZ istinad kataloqu ilə — `po_placeholders_vs_az.txt`, təkrar msgstr-lər, dil qarışığı) + brauzerdə RU UI (`qa.rector`, sidebar 53 bənd + 12 bölmənin düymə/etiket/aria-label-ları, `sessionStorage.__collect_ru`) + `.po` əl yoxlaması. Kataloqlar: en/ru 13 770, tr 13 748 msgid; fuzzy 0, boş msgstr 0.

**Semantik qüsurlar cədvəli (təsdiqlənmiş):**
| # | ctx / msgid | az | en | ru | tr | Görünən yer | Ciddilik |
|---|---|---|---|---|---|---|---|
| L1 | `exams.partial.exam_modals` / `action_close` | Bağla | Close | **открыть** (=Aç) | **açık** (=Açıq) | `exams/components/_exam_modals.html:88` modal bağlama düyməsi | **P1** (polarite tərs) |
| L2 | `exams.template.test_question_bank` / `action_deselect_all` | Seçimi sıfırla | Clear selection | **Удалить** (=Sil) | **Silmek** | `_bulk_question_workbench.html:407` toplu seçim paneli | **P1** (zərərsiz əməl «Sil» kimi) |
| L3 | `exams.template.teacher_pending_attempts` / `action_check` | **Geri** | **Back** | Назад | Geri | `teacher_pending_attempts.html:123` — cəhdi yoxlamağa aparan əsas link (`fa-marker`) hər 4 dildə «Geri» | **P1** (əsas əməl yanlış adlanıb) |
| L4 | `exams.template.test_question_bank` / `stat_duplicates` | **Mövzu** | Subject | Предмет | Ders | `_bulk_question_workbench.html:127` dublikat sayı kartı «Mövzu» adlanır (title: «Yalnız dublikatları göstər») | P2 |
| L5 | `abbrev. month` və `alt. month` / `March` | Mart | **Search** | **Поиск** | **Ara** | Django tarix formatı `N`/`E` — mart ayı EN/RU/TR-də «Search 5, 2026» | P2 |
| L6 | `supervision.config.field` / `enabled` | Söndürüldükdə bütün AI xüsusiyyətləri… | When disabled, all AI features… | … | … | `apps/exams/domain/supervision.py:51 verbose_name` — sahə ETİKETİ kimi köməkçi cümlə (bütün dillərdə, admin/forma) | P3 |
| L7 | `exams.template.coding_exam` / `Clear` | Sil | Clear | Удалить | Temizle | kod redaktorunu təmizləmə düyməsi ru-da «Sil» (silmə çalarlı) | P3 |
| L8 | `accounts.student_org` / `revoke_*` | — | — | — | «…geri çekmek istediğinizi **onaylayın**» | mənaca düzgündür (skaner yalançı siqnalı) | — |

Digər 40+ polarite namizədi yalançı siqnaldır (`sil` ⊂ `sillabus`, `aç` ⊂ `açıqdır`).

**Yerdəyişənlər:** AZ istinadına görə en/ru/tr `%(x)s`/`{x}` dəstləri **0 fərq** (django + djangojs) — PASS; brauzerdə xam `%(` / `{x}` görünmədi — PASS.

**Qarışıq dilli səhifələr (RU UI, brauzer):** `audit-log` (KPI/filtrlər AZ: «Səbəbsiz dəyişiklik», «Ən çox əməliyyat», «Bütün icraçılar», «Son 30 gün», «Hamısı»; aria «Baxış — открыть запись»), `groups-registry` (KPI «QRUP», «TƏLƏBƏ (SƏHİFƏDƏ)», «KURATORSUZ», «PLAN YOXDUR», filtrlər «Fakültə/İxtisas/Arxiv/Kod/Kafedra»), `org-members` (segmentlər «Heyət/Müəllim/Tələbə/Rəhbərlik/Bölməsiz», «Bütün rollar», «Rol (yuxarıdan aşağı)», sütun «Üzv/Rol/Bölmə/Növ»), sidebar `org-kafedras` = «Kafedralar». **Kök səbəb (təsdiqlənib):** Python-da `pgettext(_CTX, "…")` — kontekst modul sabitidir (`ast.Name`), `xgettext` bunu çıxara bilmir və `scripts/i18n_source_scan.py:_const_str` də yalnız literal qəbul edir → bu sətirlər heç bir kataloqa düşmür, `check_i18n_catalogs.py` «yeni borc yoxdur» deyir. Ölçü (`i18n_ctx_variable_gap.txt`): 2 450 belə çağırış, **613-ü en/ru/tr kataloqlarının heç birində yoxdur** — ən çox `curriculum_sections.py` 56, `structure_registry_actions.py` 52, `structure_views/registry.py` 49, `structure_views/members.py` 48, `audit/views.py` 46, `intake/teachers.py` 42, `exam_score_import.py` 29 (kontekstlər: `organizations.registry` 101, `teacher_intake` 54, `organizations.members` 50, `audit.section` 46, `accounts.groups` 32). **P1 (Lokallaşdırma)** — i18n agentinə: (a) `i18n_source_scan.py` `_pair_from_call`-da `ast.Name`-i modul səviyyəli string sabitinə həll et (qapı görsün), (b) 613 cütü fill skripti ilə doldur.

**JS-də i18n-siz mətn:** §1 — `workload_distribution*.js`, `workload_my.js` (18 AZ literal, `confirm("Sətir silinsin?")`, `aria-label="Bölgünü sil"`) — EN/RU/TR-də dərs yükü paneli qarışıq. P2.

**RU üslub:** bütün bağlama düymələrində aria-label «Закрой это» (sən-forması; rəsmi UI üçün «Закрыть») — P3 (`aria_close` msgid).

**TR:** `tr/django.po`-da 80 (+djangojs 100) AZ msgid eyni msgstr ilə (tərcüməsiz kopiya) — i18n agenti doldurur; RU/EN-də 0.

**Tarix/rəqəm formatı:** RU səhifələrdə `Дата начала/окончания` sahələri native date input; cədvəllərdə `61,4%` (vergül) — RU lokalına uyğun; EN-də NOT TESTED (screenshot yoxdur). RTL: yoxdur (tələb olunmur).


## 6. Responsiv (390/768/1280)
Alət: Browser pane viewport emulyasiyası (375×812 «mobile», 768×1024 «tablet», 1024 masaüstü; 1280 ayrıca emulyasiya edilmədi — 1024-də heç bir bölmədə üfüqi daşma yoxdur). Qeyd: pane gizli olduğundan CSS transition-lar irəliləmir (ölçmələr `transition:none` ilə təkrarlandı) və emulyasiya `resize`/`matchMedia change` hadisəsi **göndərmir** (0 hadisə loglandı) — «masaüstü→mobil ilk resize» keçidi (Codex §19, düzəliş `ui.js:88-100 handleViewportChange`, commit 119783a1) bu alətlə **yoxlanıla bilmədi**; kod oxunuşu ilə handler `matchMedia('(max-width:768px)').addEventListener('change')`-ə bağlıdır (`ui.js:513-517`).

| Səhifə | 375 | 768 | 1024 | Qeyd |
|---|---|---|---|---|
| Dashboard (rector) | PASS — daşma yox, sidebar `collapsed` (translateX(-80px)), `aria-expanded=false`, toggle 32×32 | PASS | PASS | 768 px-də `max-width:768px` media matches → mobil rejim (sərhəd daxil) |
| Mobil sidebar aç/bağla | PASS — toggle → `aria-expanded=true`, `body overflow:hidden`, backdrop `pointer-events:auto`; ESC → bağlanır | — | — | fokus idarəsi §4 |
| applications, notifications | PASS | — | — | |
| org-members (üzv reyestri) | PASS — 1 cədvəl scroll sarğısında, sticky `th` 26 | PASS | PASS | |
| groups-registry | PASS — sarğı + sticky; checkbox 13×13 (§4) | PASS | PASS | |
| people-students | PASS — 13 cədvəl, hamısı sarğıda | PASS (3 cədvəl) | PASS | |
| student-registry, semester-opening, audit-log, analytics, my-schedule | PASS — daşma yox, cədvəllər sarğıda, sticky başlıqlar | — | PASS | |
| statistics (tam səhifə) | PASS — 4 KPI, `--ems-bar-pct` custom property, «Submissions (CSV)» + «Indicators (CSV)» düymələri | PASS | PASS | |
| `/jurnal/` siyahısı | PASS — daşma yox | — | — | |
| Jurnal GRID (`registrar:journal_detail`) | NOT TESTED — clone DB-də `registrar_courseoffering` = **0 sətir** | | | |
| İmtahan sihirbazı | NOT TESTED — `/exams/create/` `?section=my-exams`-a yönləndirir (modal sihirbaz); modal açılışı klaviatura/screenshot olmadan yoxlanmadı | | | |
| exam-score-entry | NOT TESTED — 500 (mühit, §2) | | | |
| Uzun AZ etiket kəsilməsi 375 px | PASS — yalnız gizli `H2.sidebar-title` (collapsed) `overflow:hidden` ilə kəsilir | | | |
| Tap hədəfi <44 px | §4 — qabıqda 32–40 px (AA ≥24 PASS, AAA 44 FAIL); bölmələrdə 13–18 px elementlər (AA FAIL) | | | |


## 7. Screenshot siyahısı
**Heç biri çəkilə bilmədi** — Browser pane bu (qeyri-interaktiv) sessiyada gizlidir; `computer.screenshot` «pane is not displayed, not compositing frames» ilə uğursuz olur. Əvəzində DOM ölçmələri: `sweep_notes.md`, `sessionStorage.__walk_*` çıxarışları bu sənəddə, `contrast.txt`, `po_semantic_scan.txt`, `po_placeholders_vs_az.txt`, `i18n_ctx_variable_gap.txt`, `js_inventory.txt`, `js_ready_listeners.txt`, `js_hardcoded_az.txt`, `ux_scan.txt`.


## 8. Tapıntılar P0–P3 (minimal düzəlişlə)
P0: **yoxdur**.

| # | Sev | Sahə | Tapıntı | Sübut | Minimal düzəliş |
|---|---|---|---|---|---|
| F1 | **P1** | i18n | `_exam_modals.html:88` bağlama düyməsi RU «открыть», TR «açık» (əks məna) | `locale/{ru,tr}` `exams.partial.exam_modals`/`action_close` | i18n agenti: ru «Закрыть», tr «Kapat» (fill skripti) |
| F2 | **P1** | i18n | «Seçimi sıfırla» RU «Удалить», TR «Silmek» — toplu sual seçimində zərərsiz əməl «Sil» görünür | `action_deselect_all` ctx `exams.template.test_question_bank`; `_bulk_question_workbench.html:407` | ru «Снять выделение», tr «Seçimi temizle» |
| F3 | **P1** | i18n/UX | Yoxlanmamış cəhdlər siyahısında əsas əməl (`fa-marker`) bütün 4 dildə «Geri/Back/Назад» | `action_check` ctx `exams.template.teacher_pending_attempts`; `teacher_pending_attempts.html:123` | az «Yoxla», en «Check», ru «Проверить», tr «Kontrol et» |
| F4 | **P1** | i18n | 613 `pgettext(_CTX, …)` sətri heç bir kataloqda yoxdur → EN/RU/TR-də audit-log, groups-registry, org-members, registry, teacher-intake, exam_score_import, semester-opening qarışıq dilli; qapı kor | `i18n_ctx_variable_gap.txt`; `scripts/i18n_source_scan.py:85-110` (`_const_str` yalnız literal) | `_pair_from_call`-da `ast.Name` → modul sabiti həlli (`ast.walk(module)` ilə `NAME = "…"` lüğəti); sonra fill skripti (i18n agenti) |
| F5 | P2 | a11y | AJAX bölmə keçidindən sonra fokus `body`-də qalır, elan yoxdur (2.4.3/4.1.3) | 7 rol × 100+ swap, `activeEl=BODY`; `section_loader.js replaceSectionHtml` | `replaceSectionHtml` sonunda `var t=document.getElementById('profileSectionTitle'); if(t){t.tabIndex=-1; t.focus();}` |
| F6 | P2 | a11y | `--ems-neutral-400` (2.56:1) 63 qaydada mətn rəngi, çoxu 0.6–0.72rem; `success-600`/`danger-500`/`warning-600`/`primary-500` mətn kimi 85 qayda (3.2–3.8:1) | `contrast.txt`; `sidebar.css:191,329,358`, `applications_modal.css:290` | mətn üçün `neutral-500`/`success-700`/`danger-600`/`warning-700` tokenlərinə keçid (sed-səviyyəli, ikon/dekorativ istisna) |
| F7 | P2 | i18n/JS | Dərs yükü paneli JS-i i18n-siz: 18 AZ literal (`confirm("Sətir silinsin?")`, `aria-label="Bölgünü sil"`, «Vakant…», «Qalıq:») | `workload_distribution.js:81,339,400,432,436,477,493,516,534`, `workload_distribution_render.js:31,56,79,110,139,175,178,184`, `workload_my.js:54` | `gettext()` (JavaScriptCatalog artıq `/jsi18n/`-dədir) və ya panel `data-*`/`json_script` körpüsü |
| F8 | P2 | i18n | `abbrev. month`/`alt. month` «March» → «Search/Поиск/Ara» | `locale/en/LC_MESSAGES/django.po:46893` və ru/tr | ru «Март», en «March», tr «Mart» |
| F9 | P2 | i18n | Dublikat sayı kartı «Mövzu/Subject» adlanır | `stat_duplicates` `_bulk_question_workbench.html:127` | az «Dublikatlar», en «Duplicates», ru «Дубликаты», tr «Kopyalar» |
| F10 | P3 | a11y | İç-içə `<main>` (2 landmark) | `profile.html:24` | `<main class="profile-main">` → `<div class="profile-main">` (CSS seçici sinifdir) |
| F11 | P3 | a11y | 24 px-dən kiçik hədəflər: checkbox 13×13 (permission-editor 112, groups-registry), `ems-sort` 18 px, `people__th-sort` 64×18, `rls-chip__x` 18×18 | §4 | `ems_ui/table.css .ems-sort{min-height:24px;padding-block:3px}`; checkbox `width/height:18px` + 24 px `padding` klik sahəsi |
| F12 | P3 | JS | Kart başına `setInterval` swap-dan sonra detached node-a yazmağa davam edir | `pending_answers_countdown.js:47`, `pending_review_countdown.js:59`, `assignments/review_submissions.js:59`, `teacher_pending_attempts.js:47` | `render()` başında `if(!node.isConnected){clearInterval(id);return;}` |
| F13 | P3 | JS | `console.log` qalıqları | `topic_edit_modal.js:45,66,130`, `host_lobby/utils.js:278` | sil / `if (UI.debugLog)` altına al |
| F14 | P3 | nav | `rim-center` `AJAX_SAFE_SECTIONS`-da var, `data-ajax-sections`-da yox → həmişə tam səhifə | `profile.html:16`, `sections_api.py`; `test_section_registry_consistency.py` server⊆client yoxlamır | siyahıya `rim-center` əlavə et; testə əks istiqamət assert-i |
| F15 | P3 | a11y | Login xətası `role=alert`/`aria-invalid`/`aria-describedby`-sız düz mətn | `login.html` (brauzer: `div.auth-page-wrapper` içində) | xəta blokuna `role="alert"`, sahələrə `aria-invalid="true"` |
| F16 | P3 | a11y | Mobil sidebar açılanda fokus içəri keçmir, ESC-dən sonra toggle-a qayıtmır | brauzer 375 px | `setSidebarCollapsed(false)`-dan sonra ilk linkə `focus()`, bağlananda `mobileSidebarTrigger.focus()` |
| F17 | P3 | a11y | 18 ikon-only düymə adsız (kabinetdən kənar səhifələr) | §3 siyahısı | `aria-label="{% trans … %}"` |
| F18 | P3 | a11y | `jd2.css:56,62` fokus konturu əvəzsiz silinir | grep | `outline:none` sil və ya `box-shadow` fokus əvəzi |
| F19 | P3 | UX | 22 native `confirm()`; `_superadmin_organizations_content.html:131` «Rədd et» təsdiqsiz | §3 | `EMSConfirm.open({danger:true})` |
| F20 | P3 | i18n | RU aria-label «Закрой это» (sən-forması) | `aria_close` msgid | «Закрыть» |
| F21 | P3 | JS | `rim_center/create_combo.js:35 box()` `el.closest` qorumasız (target Element deyilsə TypeError) | brauzer konsolu (sintetik `keydown` ilə) | `return el && el.closest ? el.closest(...) : null` |
| F22 | P3 | i18n | `supervision.config.field/enabled` sahə etiketi = köməkçi cümlə | `apps/exams/domain/supervision.py:51` + 4 kataloq | az «Aktiv», en «Enabled», ru «Включено», tr «Etkin» |
| ENV | — | mühit | `exam-score-entry` 500 — clone DB `registrar.0070`, repo `0071–0075` tətbiq olunmayıb | `preview_logs`; `django_migrations` (SELECT) | clone-da `migrate` (sahib/mühit agenti) — frontend qüsuru deyil |

Say: P0 0 · P1 4 · P2 5 · P3 13 (+1 mühit).


## 9. Qiymətlər (0–100)
| Sahə | Qiymət | Əsaslandırma |
|---|---|---|
| Frontend (JS keyfiyyəti, CSP, şəbəkə) | **82** | 7 rol/100+ bölmədə 0 konsol/CSP/JS xətası; AJAX-safe nümunə və CSRF ardıcıl; çıxılan: interval sızması (F12), console.log (F13), i18n-siz workload JS (F7), `rim-center` drift (F14), 36 IIFE-siz fayl |
| UX/UI | **74** | ems_ui komponentləri, boş/yükləmə vəziyyətləri, təsdiq dialoqları, mobil cədvəl sarğıları yaxşı; çıxılan: 5 paralel BEM sistemi + 1 194 legacy `card`, 22 native `confirm()`, 18 adsız ikon düymə, iki-primary/vizual ardıcıllıq screenshot-suz yoxlanmadı |
| Əlçatanlıq | **67** | skip link, landmark/aria-current/aria-modal, fokus tələsi, reduced-motion var; çıxılan: F5 fokus (P2), F6 kontrast (P2), F11 hədəf ölçüsü, F10 iç-içə main, F15/F16; screen-reader və real klaviatura attestasiyası yoxdur |
| Lokallaşdırma | **56** | yerdəyişənlər və kataloq tamlığı əla; çıxılan: 4 P1 semantik qüsur (F1–F4), 613 kataloqsuz sətir → qarışıq dilli admin səhifələri, workload JS, TR 180 tərcüməsiz kopiya, «Закрой это» üslubu |
| **Frontend sahəsi (ümumi)** | **70** | çəki: Frontend 0.3 · UX 0.25 · A11y 0.2 · L10n 0.25 → 24.6+18.5+13.4+14 = 70.5 |

