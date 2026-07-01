# Böyük Fayllar Bölgü Planı (600+ sətir) — sıralı yol xəritəsi

Tarix: 2026-07-01. Prinsip: **ən aşağı riskdən / ən çox test-doğrulanandan → ən riskliyə**.
Hər addım: `black/isort/flake8` + testlər + `check_module_size.py`, sonra CI (Postgres).
İş metodu: profile-də sınanmış **context-fragment / paket / partial** pattern (bax: AGENTS.md,
docs/REFACTOR_PLAN_profile_main.md).

> **Artıq bölünənlər (bu sessiya):** parsing.py, results.py, question_bank.py,
> statistics_selectors.py, question_library.py (Python paketlər); profile/main.py 2313→14
> (14 bölmə + context_builder); take_exam/create_question_bank/student_exam_list/staff_management
> (HTML partial); 623 CSS rəng → token.

---

## FAZA 1 — Python servisləri (ƏN TƏHLÜKƏSİZ, test-doğrulanan, sınanmış paket pattern)

Bunlar çoxlu müstəqil top-level funksiyalı servis fayllarıdır → `_shared` + qrup modulları paketi,
`__init__` re-export. statistics_selectors/question_library kimi.

| # | Fayl | Sətir | Strategiya |
|---|------|-------|-----------|
| 1 | `apps/exams/services/supervision.py` | 1215 | Proctoring: event-capture / scoring / session-lock qrupları → `_shared` + alt-modullar |
| 2 | `apps/exams/services/coding_runtime.py` | 1033 | Kod icra: dil-runtime-lər + orkestrasiya → `_shared` + `runners` |
| 3 | `apps/exams/services/parsing/extraction.py` | 836 | Onsuz da paketin bir hissəsi; OCR / normalizasiya / highlight alt-qruplarına |
| 4 | `apps/exams/domain/question_bank.py` | 612 | Domain məntiqi — funksiya qrupları üzrə |

## FAZA 2 — View / helper faylları (paket pattern, test-doğrulanan)

Çoxlu view funksiyası → CRUD/action/api qruplarına paket (question_library kimi). `@login_required`
dekoratorları və patch-hədəflərinə diqqət (call-time fasad lazım ola bilər).

| # | Fayl | Sətir | Strategiya |
|---|------|-------|-----------|
| 5 | `apps/accounts/views/_helpers/org_sections.py` | 1021 | Section-builder köməkçiləri → mövzu qruplarına |
| 6 | `apps/accounts/views/organization/management.py` | 977 | Org idarəetmə view-ları → CRUD/action qrupları |
| 7 | `apps/accounts/views/roles/assignment.py` | 906 | Rol təyinat view/action-ları |
| 8 | `apps/accounts/views/auth.py` | 889 | login / register / otp / reset alt-modullara |
| 9 | `apps/accounts/forms/auth.py` | 740 | Auth formaları — form qrupları üzrə |
| 10 | `apps/live_exam/views/player.py` | 791 | Player view/api/ws qrupları |
| 11 | `apps/live_exam/views/host.py` | 637 | Host view/api qrupları |
| 12 | `apps/exams/views/teacher/exams.py` | 748 | Teacher exam CRUD/list/detail qrupları |
| 13 | `apps/exams/views/teacher/questions.py` | 711 | Question CRUD/import qrupları |
| 14 | `apps/exams/views/teacher/supervision.py` | 642 | Supervision monitor view/api |
| 15 | `apps/organizations/structure_views.py` | 620 | Fakültə/kafedra action qrupları |

## FAZA 3 — Settings və Modellər (orta risk)

| # | Fayl | Sətir | Strategiya |
|---|------|-------|-----------|
| 16 | `config/settings/base.py` | 650 | `components/` böl: database / security / csp / celery / channels (import order-a diqqət) |
| 17 | `apps/courses/models.py` | 615 | Model qrupları (əgər aydın ayrılırsa); əks halda `_managers`/`_querysets` çıxar |
| 18 | `apps/labs/models.py` | 613 | Eyni — model/manager/queryset ayrımı |
| 19 | `apps/exams/management/commands/seed_group_demo_data.py` | 611 | Seed helper-lərini ayır (aşağı prioritet) |

## FAZA 4 — context_builder.py (ƏN RİSKLİ — ayrıca CI-PR)

| # | Fayl | Sətir | Strategiya |
|---|------|-------|-----------|
| 20 | `apps/accounts/views/profile/context_builder.py` | 1440 | Mərhələ B/C: `ProfileContext` state-obyekti + `_stage_base`/`_stage_sections`/`_stage_assemble`. ~150 lokal → ctx sahələri. Ən çox istifadə olunan səhifə — mərhələ-mərhələ, hər dəfə CI yaşıl (docs/REFACTOR_PLAN_profile_main.md) |

---

## FAZA 5 — HTML şablonları (600+) → partial / static asset

Böyük inline `<script>`/`<style>` → partial və ya static fayl; təkrar UI parçaları → ortaq partial.
Render-test ilə doğrulanır.

| # | Fayl | Sətir | Strategiya |
|---|------|-------|-----------|
| 21 | `accounts/partials/_staff_management_content.html` | 1802 | Filtr / cədvəl / modal sub-partial-lara (script artıq çıxarıldı) |
| 22 | `accounts/partials/_student_org_management_content.html` | 1268 | Bölmə sub-partial-lar |
| 23 | `exams/student/partials/_take_exam_scripts.html` | 1309 | Çıxarılmış JS — template-var yoxdursa hissələri static `.js`-ə |
| 24 | `accounts/profile/sections/_statistics.html` | 815 | Kart/qrafik blokları partial |
| 25 | `exams/teacher/supervision_monitor.html` | 803 | style/script çıxar + kart partial |
| 26 | `liveExam/teacher_live_session_detail.html` | 775 | Bölmə partial |
| 27 | `labs/partials/_lab_modals.html` | 738 | Hər modal ayrı partial |
| 28 | `accounts/partials/_role_assignment_content.html` (686), `exams/teacher/exam_section.html` (678), `teacher_exam_statistics.html` (675), `_exam_live_monitor_js.html` (675), `accounts/register.html` (666) | 666-686 | Script/style çıxar + təkrar bloklar ortaq partial |

## FAZA 6 — CSS (600+) → rəng token miqrasiyası + bölgü

Əvvəlcə qalan hex→token (behavior-neutral, docs/UI_COLOR_TOKENS_MIGRASIYA.md), sonra böyük faylları
komponent üzrə (@import parçaları) böl.

| # | Fayl | Sətir | Qeyd |
|---|------|-------|------|
| 29 | `live_exam/css/host_lobby.css` | 3606 | Komponent üzrə böl (lobby / player-card / avatar / grid); token davam |
| 30 | `player.css` (1576), `test_question_bank.css` (1524), `coding_exam.css` (1504) | 1500+ | Ekran-bölmə üzrə böl |
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
