# Böyük Fayllar Bölgü Planı (600+ sətir) — sıralı yol xəritəsi

Tarix: 2026-07-01. Prinsip: **ən aşağı riskdən / ən çox test-doğrulanandan → ən riskliyə**.
Hər addım: `black/isort/flake8` + testlər + `check_module_size.py`, sonra CI (Postgres).
İş metodu: profile-də sınanmış **context-fragment / paket / partial** pattern (bax: AGENTS.md,
docs/REFACTOR_PLAN_profile_main.md).

> **Artıq bölünənlər:** parsing.py, results.py, question_bank(services), statistics_selectors,
> question_library, supervision(services), coding_runtime, teacher/exams, teacher/questions,
> structure_views; **və bu davam sessiyada:** live_exam/player, live_exam/host, accounts/views/auth,
> accounts/forms/auth, exams/services/parsing/extraction (facade-patch qorundu),
> exams/views/teacher/supervision, **config/settings/base.py → components/ (exec-include, 153
> setting bit-bit eyni)**, **courses/models.py**, **labs/models.py**, **exams/domain/question_bank.py
> (upload_to `__module__` partial-init ilə qorundu)**, **seed_group_demo_data (mixin-lər)** — hamısı
> test-yaşıl, makemigrations 0 dəyişiklik. profile/main.py 2313→14; HTML partial-lar; CSS token.
>
> **Qalan (yalnız nəhəng-funksiya, ayrıca diqqətli CI-PR):** org_sections.py, organization/management.py,
> roles/assignment.py, context_builder.py — struktur analizi FAZA 3.5 / FAZA 4-də.
>
> **İcra qeydi:** supervision + teacher/exams-də ayrıca `constants.py` modulu yaradıldı
> (sabitlərin dəqiq yeri). coding_runtime-də docker/patch reqressiyası **fasad-patch
> pattern** ilə düzəldildi (AGENTS.md-də sənədləşib — bölgüdən sonra `patch(module.X)`
> hədəfləri call-time fasaddan həll olunmalıdır).

---

## FAZA 1 — Python servisləri (ƏN TƏHLÜKƏSİZ, test-doğrulanan, sınanmış paket pattern)

Bunlar çoxlu müstəqil top-level funksiyalı servis fayllarıdır → `_shared` + qrup modulları paketi,
`__init__` re-export. statistics_selectors/question_library kimi.

| # | Fayl | Sətir | Strategiya |
|---|------|-------|-----------|
| 1 | `apps/exams/services/supervision.py` | 1215 | Proctoring: event-capture / scoring / session-lock qrupları → `_shared` + alt-modullar |
| 2 | `apps/exams/services/coding_runtime.py` | 1033 | Kod icra: dil-runtime-lər + orkestrasiya → `_shared` + `runners` |
| 3 | ✅ `apps/exams/services/parsing/extraction.py` | 836 | BÖLÜNDÜ → _deps/constants/safety/normalize/highlight/ocr/pipeline (87 test; facade-patch qorundu) |
| 4 | ✅ `apps/exams/domain/question_bank.py` | 612 | BÖLÜNDÜ → __init__(callable-lar)/exam_question/bank_question (274 test; upload_to `__module__` partial-init ilə qorundu, makemigrations 0) |

## FAZA 2 — View / helper faylları (paket pattern, test-doğrulanan)

Çoxlu view funksiyası → CRUD/action/api qruplarına paket (question_library kimi). `@login_required`
dekoratorları və patch-hədəflərinə diqqət (call-time fasad lazım ola bilər).

| # | Fayl | Sətir | Strategiya |
|---|------|-------|-----------|
| 5 | ✅ `apps/accounts/views/_helpers/org_sections.py` | 1021 | BÖLÜNDÜ → paket: `management`(setup+guard+orkestrasiya)/`_queries`(part1)/`_pagination`(part2)/`request_section`. **Verbatim statement-split** (AST-rewrite yox); sərhəddə yalnız `teacher_members`/`staff_members` threading. Profil characterization + 59 student-org testi yaşıl; makemigrations 0. |
| 6 | ✅ `apps/accounts/views/organization/management.py` | 977 | BÖLÜNDÜ → **extract-class**: `_management_flow/` (_requests/_invites/_members mixin + flow); 8 closure metodlara. Characterization(21) + 200 org/RBAC test yaşıl. |
| 7 | ✅ `apps/accounts/views/roles/assignment.py` | 906 | BÖLÜNDÜ → **extract-class**: `_assignment_flow/` (_audit/_predicates/_resolvers mixin + flow); closure-lar `self.*` state ilə metodlara; nazik view. Characterization + 275 rol/RBAC test yaşıl. |
| 8 | ✅ `apps/accounts/views/auth.py` | 889 | BÖLÜNDÜ → constants/_shared/login/register/otp_api (172 test) |
| 9 | ✅ `apps/accounts/forms/auth.py` | 740 | BÖLÜNDÜ → constants/register/login (179 test) |
| 10 | ✅ `apps/live_exam/views/player.py` | 791 | BÖLÜNDÜ → constants/_shared/join/wait (200 test) |
| 11 | ✅ `apps/live_exam/views/host.py` | 637 | BÖLÜNDÜ → constants/_shared/session/game (84 test) |
| 12 | ✅ `apps/exams/views/teacher/exams.py` | 748 | BÖLÜNDÜ → constants/_shared/list_detail/actions (39 test) |
| 13 | ✅ `apps/exams/views/teacher/questions.py` | 711 | BÖLÜNDÜ → constants/_shared/bank/crud (68 test) |
| 14 | ✅ `apps/exams/views/teacher/supervision.py` | 642 | BÖLÜNDÜ → _shared/monitor/live (37 test) |
| 15 | ✅ `apps/organizations/structure_views.py` | 620 | BÖLÜNDÜ → constants/_shared/context/endpoints (18 test); relative-import +1 + ad-toqquşma dərsi (AGENTS.md) |

## FAZA 3 — Settings və Modellər (orta risk)

| # | Fayl | Sətir | Strategiya |
|---|------|-------|-----------|
| 16 | ✅ `config/settings/base.py` | 650 | BÖLÜNDÜ → `components/` (apps/celery_cache/admin_ratelimit/exam/security/i18n_static/email/integrations/csp); exec-include tək namespace; 153 setting bit-bit eyni (snapshot diff = 0) |
| 17 | ✅ `apps/courses/models.py` | 615 | BÖLÜNDÜ → _base/course/content/enrollment (86 test; makemigrations 0 dəyişiklik) |
| 18 | ✅ `apps/labs/models.py` | 613 | BÖLÜNDÜ → _base/lab/assignment (102 test; makemigrations 0 dəyişiklik) |
| 19 | ✅ `apps/exams/management/commands/seed_group_demo_data.py` | 611 | BÖLÜNDÜ → `_seed_helpers/` mixin-lər (users/courses/exams) + Command; komanda reyestri qorundu |

## FAZA 3.5 — Nəhəng-funksiya view-ları (org_sections / management / assignment)

Bu 3 fayl (#5, #6, #7) mexaniki paket-bölgü ilə **bölünmür**: hər biri tək (və ya
iki) 800–920 sətirlik funksiyadır və çoxlu iç-içə closure ilə request-scoped state
(`request`, `org`, `action_name`, `target_*`) tutur. Təhlükəsiz strategiya:

1. **Xarakterizasiya testi əvvəl** (artıq var: `test_roles_refactor_characterization.py`,
   `test_organization_refactor_characterization.py`) — refaktordan əvvəl/sonra
   eyni davranışı təsdiqləyir. Postgres CI-də işlədilməlidir (RBAC/RLS yolları).
2. **Aşağı-tutumlu (pure) closure-ları əvvəl çıxar** (məs. `_parse_uuid`,
   `_is_owner_role`, `_is_admin_role` — yalnız import/sabit tutur) → module-səviyyə
   helper. Sonra orta-tutumluları açıq parametr-threading ilə (`org`, `request`
   arqument kimi ötürülür). Yüksək-tutumlu orkestratorlar (`_resolve_attach_target`
   206 sətir) ən sonda.
3. **Hər addımdan sonra Postgres CI yaşıl** — bu yollar tenant-izolyasiya/RBAC
   kritikdir; sqlite-only doğrulama KİFAYƏT DEYİL. Ona görə bunlar sandbox-da
   bulk-passda YOX, ayrıca kiçik PR-larla (hər biri bir funksiya seam) aparılmalıdır.

**İcra nəticəsi:** `roles/assignment.py` və `organization/management.py` **extract-class**
pattern-i ilə uğurla bölündü (closure-lar `self.*` state ilə mixin metodlarına; AST-transform
+ characterization testi + Postgres-uyğun sqlite testləri yaşıl). Bu pattern yalnız **closure-əsaslı**
nəhəng funksiyalarda təhlükəsizdir.

`_helpers/org_sections.py` (#5) isə **linear** nəhəng funksiyadır (çoxlu erkən-return + blok-daxili
nested scope) — extract-class/faza-split BURADA davranışı poza bilər. Bu, manual, addım-addım,
hər addımı Postgres CI-də doğrulanan PR tələb edir (avtomatlaşdırma sqlite-only mühitdə RBAC-kritik
render üçün risklidir).

> **Qeyd:** Qoruyucu bütün faylları dondurub — böyüyə bilməzlər. Qalan bölgü təcili
> deyil; təhlükəsizlik-kritik olduğu üçün diqqətli, CI-doğrulanan PR tələb edir.

## FAZA 4 — context_builder.py ✅ BÖLÜNDÜ (staged-builder)

| # | Fayl | Sətir | Strategiya |
|---|------|-------|-----------|
| 20 | ✅ `apps/accounts/views/profile/context_builder.py` | 1440 | BÖLÜNDÜ → paket: `_helpers`(3 kiçik funksiya)/`_stage1..4`(mixin)/`builder`(class+run+thin view). **staged-builder extract-class**: lambda param-sız + comprehension/walrus/global YOX → bütün ~130 lokal təhlükəsiz `self.X`-ə (AST-rewrite), gövdə 4 ardıcıl stage-metoda; erkən-return-lar (246/258→st1, 1138→st3) `run()`-da None-check ilə propagate olunur. Nested relative-import +1 bump. **Characterization 23/23 + 208 profil testi yaşıl**, makemigrations 0. Qeyd: AST-unparse şərhləri itirdi (korrektlik üçün tradeoff; davranış test-doğrulanıb). |

---

> **✅ PYTHON FAZALARI (1–4) TAM BİTDİ.** Heç bir production `.py` faylı 600+ deyil
> (guard budcəsi boşdur). Bütün bölgülər Postgres tam suite (2159 passed, 417 subtests)
> + browser E2E (212 passed) ilə təsdiqlənib (Codex icra etdi). Növbə: HTML/CSS/JS (5–7).

> **✅ GUARD GENİŞLƏNDİ (2026-07-01):** `scripts/check_module_size.py` artıq `.py` ilə
> yanaşı **HTML/CSS/JS** assetlərini də əhatə edir (templates/ + static/ daxil; istisna:
> staticfiles/htmlcov/output/vendor/node_modules/.min). Cari: **43 asset donmuş** (20 CSS,
> 11 JS, 12 HTML) — böyüyə bilməzlər, yalnız kiçilə. Yeni asset >600 CI-da düşür. Beləliklə
> qalan bölgü TƏCİLİ DEYİL — mərhələli, hər dəfə render/E2E-doğrulanan aparıla bilər.
>
> **HTML partial dərsi:** xarici `{% if/for/block %}` bloku bütöv qalmalı — yalnız DAXİLİ
> məzmun `{% include %}`-ə çıxarılır (bağlayan tag main-də qalır). Hər çıxarışdan sonra
> `get_template()` compile + characterization/render testi MƏCBURİ. Nümunə: `staff_management/`,
> `student_org_management/`, `lab_modals/`.

## FAZA 5 — HTML şablonları (600+) → partial / static asset

Böyük inline `<script>`/`<style>` → partial və ya static fayl; təkrar UI parçaları → ortaq partial.
Render-test ilə doğrulanır.

| # | Fayl | Sətir | Strategiya |
|---|------|-------|-----------|
| 21 | ✅ `accounts/partials/_staff_management_content.html` | 1802 | BÖLÜNDÜ → 1802→313; `staff_management/` alt-qovluğu: students-members/pending/unassigned/invites + teacher_tabs + staff_tabs + superadmin (hamısı <600, {% include %} render-neytral, characterization 23/23 yaşıl) |
| 22 | ✅ `accounts/partials/_student_org_management_content.html` | 1268 | BÖLÜNDÜ → 1268→64; `student_org_management/`: students/pending/unassigned/invites + modals + scripts (hamısı <600, characterization yaşıl) |
| 23 | `exams/student/partials/_take_exam_scripts.html` | 1309 | Çıxarılmış JS — template-var yoxdursa hissələri static `.js`-ə |
| 24 | `accounts/profile/sections/_statistics.html` | 815 | Kart/qrafik blokları partial |
| 25 | ✅ `exams/teacher/supervision_monitor.html` | 803 | BÖLÜNDÜ → 803→270; inline `<style>`→static `exams/css/supervision_monitor.css` (197, CSP nonce-suz), inline `<script>`→`partials/_supervision_monitor_js.html` (337); 30 test yaşıl |
| 26 | `liveExam/teacher_live_session_detail.html` | 775 | Bölmə partial |
| 27 | ✅ `labs/partials/_lab_modals.html` | 738 | BÖLÜNDÜ → 738→12; `lab_modals/`: add/edit modal + scripts. **Dərs:** xarici `{% if is_owner %}` bütöv qalmalı — yalnız daxili məzmun çıxarılmalı (bağlayan `{% endif %}` main-də) |
| 23 | ✅ `teacher_live_session_detail.html` | 775 | BÖLÜNDÜ → 775→241; inline style→static CSS, script→partial |
| 24 | ✅ `accounts/profile/sections/_statistics.html` | 815 | BÖLÜNDÜ → 815→458; summary_cards + filter_bar partial |
| 28 | ✅ Cluster (666-686) BÖLÜNDÜ | | `_role_assignment_content` 686→299 (script→partial), `exam_section` 678→395 (script→partial), `teacher_exam_statistics` 675→352 (style→CSS, script→partial), `_exam_live_monitor_js` 675→**static JS** (exam_live_monitor.js), `register` 666→277 (wizard step-lər partial), `_sidebar` 612→500 (org menyu qrupu partial), `_create_question_bank_styles` 602→**static CSS** (create_question_bank.css). Bütün 265 şablon 0 sintaksis xətası, 250+ test yaşıl. |
| — | **Qalan (2 HTML frozen):** `_staff_management_scripts.html` (663), `_take_exam_scripts.html` (1309) — hər ikisi `{% trans %}`-lı JS; JS-aware bölgü + vizual/E2E doğrulama lazım (istifadəçi tərəfi). | | |

## FAZA 6 — CSS (600+) → rəng token miqrasiyası + bölgü

Əvvəlcə qalan hex→token (behavior-neutral, docs/UI_COLOR_TOKENS_MIGRASIYA.md), sonra böyük faylları
komponent üzrə (@import parçaları) böl.

| # | Fayl | Sətir | Qeyd |
|---|------|-------|------|
| 29 | ✅ `live_exam/css/host_lobby.css` | 3606 | BÖLÜNDÜ → `host_lobby/_part1..7.css` (hər ~520, brace-balanslı, **bayt-identik konkatenasiya**); 2 template ardıcıl `<link>`; 114 test yaşıl. Metod: brace-depth-0 sərhədlərində böl, sıra qoru → cascade dəyişmir (vizual yoxlama tələb etmir). |
| 30 | ✅ `player.css`(1576), `test_question_bank.css`(1524), `coding_exam.css`(1504), `appeals.css`(1282), `register.css`(1194), `take_exam.css`(1099), `wait_room.css`(1012) | 1000+ | BÖLÜNDÜ → hər biri `<file>/_partN.css` (byte-identik, brace-balanslı, template `<link>` ardıcıl yeniləndi); reusable splitter (`/tmp/css_split.py` metodu); 427 test yaşıl. **Qeyd:** yalnız SƏHİFƏ-SPESİFİK CSS bölünür; QLOBAL (navbar, base.html) bölünmür (hər səhifəyə request əlavə edər). |
| 31 | `appeals.css` (1282), `register.css` (1194), `take_exam.css` (1099), `wait_room.css` (1012), `navbar.css` (983), `teacher_questions_bank.css` (979) | 979-1282 | Bölmə/komponent üzrə böl + token tamamla |
| 32 | Qalan CSS (teacher_exam_detail 835, bulk_workbench_extras 783, host_lobby_shell 770, exam_result 764, teacher_check_attempt 744, posts 693, contact_messages 645, ai_assistant 635, join 623, teacher_exam_results 610) | 610-835 | Token miqrasiyası + lazımsa böl |

## FAZA 7 — JS (600+) → ES modul / feature-modul

Böyük SPA-vari JS-ləri modula (state / api / ui / events) böl; ortaq utility-lər (EMSReady/EMSDelegate)
təkrar istifadə. JS test-neti zəif → diqqətli, addım-addım.

| # | Fayl | Sətir | Qeyd |
|---|------|-------|------|
| 33 | `live_exam/js/host_lobby.js` | 2181 | WebSocket-state / render / event modul-ları |
| 34 | `exams/js/coding_exam.js` | 2087 | Editor / runner / ui modul-ları |
| 35 | `accounts/js/profile.js` | 2022 | Section-loader / ajax / ui modul-ları |
| 36 | `register_wizard.js` (1704), `player.js` (1558), `exam_supervision.js` (1351) | 1350+ | Feature-modul üzrə |
| 37 | `permission_editor_ui.js` (973), `exam_create_edit_modal.js` (809), `profile_group_modal.js` (680), `user_profile.js` (628), `statistics.js` (615) | 615-973 | Modul üzrə |

---

## Ümumi sıra (qısa)

**Python:** 1→supervision, 2→coding_runtime, 3→extraction, 4→domain/question_bank → sonra view-lar
(5-15) → settings/models (16-19) → context_builder (20, ayrıca PR).
**HTML:** 21-28. **CSS:** 29-32. **JS:** 33-37.

**Qoruyucu** bütün 600+ faylları (Python) dondurub — heç biri böyüyə bilməz; bölgü təcili deyil,
mərhələli aparıla bilər. Hər PR kiçik, test-yaşıl, CI-doğrulanan.
