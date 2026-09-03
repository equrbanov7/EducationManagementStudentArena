# Faza 23 — Təhlükəsizlik auditi, DALĞA 2

**Tarix:** 2026-09-03 · **Branch:** `audit/post-migration-qa-2026-09`
**Əhatə:** PR #119-dan sonra düşən hər şey — `a5d3ee9c..HEAD`
(`92ade45a` … `7de8926c`, 9 commit, 186 fayl, +28 070 sətir).

**Metod.** Kod oxunuşu + hədəflənmiş `pytest` (in-process Django test client)
**öz privat bazamda** (`127.0.0.1:55432`, `ems_sec2_*`). RLS mənfiləri
`emsarena_ci_rls` (NOBYPASSRLS) rolu ilə. Brauzer alətlərinə TOXUNULMADI (QA
agenti :8100-dədir), `locale/*.po` TOXUNULMADI (i18n agenti), commit EDİLMƏDİ.

**Nəticə: 2 P0/P1 + 1 P2 düzəldildi (red→green testlə), 4 açıq (P2/P3).**
RLS örtüyü tam, CSP/XSS təmiz, CSRF-də boşluq yoxdur.

---

## 1. Yekun cədvəl

| Ağırlıq | Tapıntı | Fayl:sətir | Status |
|---|---|---|---|
| **P0** | `student_movements/` media prefiksi private deyildi → köçürmə/akademik məzuniyyət/**xaric etmə** əmrinin sənədi (ərizə, tibbi arayış, protokol) `/media/...` altında **autentifikasiyasız** verilirdi; fayl adı da təsadüfiləşmirdi (`emr.pdf` təxmin edilə bilirdi) | `core/media_policies.py:346` (prefiks siyahısı) · `apps/registrar/models/movement.py:49` (`movement_document_path`) | ✅ **DÜZƏLDİ** |
| **P1** | Tədris planı əməllərində **STRUKTUR ƏHATƏSİ yox idi**: `plan.edit` / `plan.approve_chair` daşıyan İSTƏNİLƏN kafedra müdiri başqa fakültənin planına sətir yaza, sətir silə, yeni versiya aça və kafedra mərhələsini keçirə bilirdi; dekan da yad fakültənin şura mərhələsini təsdiqləyirdi | `apps/registrar/curriculum_actions.py:77` (`_plan`), `:137` (`_create_plan`), `:309` (`_transition`) | ✅ **DÜZƏLDİ** |
| **P1** | `QuestionSubmissionEvent` (kafedra→mərkəz zəncirinin yeganə sətir-sətir izi) özünü «əlavə-only» elan edir, amma nə DB trigger-i, nə model qapısı vardı — `StudentMovement` (registrar/0067) və `LoadObjection` (workload/0005) üçün trigger var idi | `apps/exams/domain/submission_events.py:29` · `apps/organizations/migrations/0037` (yalnız RLS) | ✅ **DÜZƏLDİ** (yeni `exams/0065`) |
| **P2** | Dərs yükü idxalının 1-ci addımı (`import_upload`) **icazəsiz** idi: hər autentifikasiya olunmuş üzv tapşırıq UUID-ini bilsə 10 MB xlsx göndərib parser-i (openpyxl) və uyğunlaşdırma sorğularını işlədə bilirdi (`import_apply` isə qapılı idi) | `apps/workload/actions.py:124` | ✅ **DÜZƏLDİ** |
| **P2** | `structure_tree_action` / `group_action` hədəf təşkilatı **URL slug-ından**, icazələri isə `request.org_permissions`-dan (AKTİV təşkilat) götürür — iki fərqli tenant. A təşkilatında `unit.tree_manage` daşıyan, B-də isə yalnız `unit.view` üzvlüyü olan aktor B-nin ağacını dəyişə bilər | `apps/organizations/structure_actions.py:205` · `group_actions.py:271` · `views/shared/_helpers.py:68` | 🔶 **AÇIQ** (tək tenantda latent) |
| **P3** | `TaskRowReview` «tarixçə» deyil: `update_or_create` ilə üstündən yazılır (koordinatorun əvvəlki vizası itir) | `apps/workload/services/reviews.py:126` | 🔶 **AÇIQ** (dizayn qərarı — sənədləşdirilməlidir) |
| **P3** | `QuestionSubmissionEvent` DELETE **qəsdən** bloklanmır (FK `CASCADE`): göndərişin özünü silmək lenti də silir | `apps/exams/views/teacher/submission_inbox.py:327` | 🔶 **AÇIQ** (audit sətri `core.audit`-də qalır) |
| **P3** | Qəbulun bir dəfəlik parol siyahısı (`credentials[]`) JSON cavabında qayıdır — saxlanılmır, amma brauzer tarixçəsinə/loglara düşə bilər | `apps/accounts/services/intake/apply.py:246` | 🔶 **AÇIQ** (əvvəlki fazadan miras dizayn) |

---

## 2. İcazə matrisi — nəticələr

Yoxlama üsulu: bölmə qapısı (`rbac_sections.apply_permission_section_gates`) +
JSON endpoint qapısı + servis qatının əhatə yoxlaması, hər üçü ayrıca oxundu.

| Səth | Oxu açarı | Yazma açarı | Struktur əhatəsi | Nəticə |
|---|---|---|---|---|
| Universitet strukturu (ağac) | `unit.view` | `unit.tree_manage` / `unit.assign_head` (ayrı) | `tree_scope` + `_visible_units_queryset` (fail-closed) | ✅ |
| Kafedra profili | `unit.view` | — (oxu) | eyni | ✅ |
| İxtisaslar / Fənn kataloqu | `catalog.view` | `catalog.manage` | org-səviyyə (açar yalnız ORGANIZATION scope-lu rollarda) | ✅ qəbul edilir |
| Tədris planı redaktoru | `plan.view` | `plan.edit` + `plan.approve_{chair,council,office}` | **YOX İDİ → əlavə olundu** | ✅ düzəldi |
| Qruplar reyestri | `unit.view` | `unit.group_manage` | `group_scope` + `scope_org_units` | ✅ |
| Semestr açılışı | `semester.view` | `semester.open` / `lock` / `unlock` (üçü ayrı) | org-səviyyə | ✅ |
| Dərs yükü mərkəzi (12) | `workload.view` | `workload.manage` | `actor.covers_unit(chair_id, …)` | ✅ (idxal addım 1 düzəldi) |
| Koordinator vizası (13) | `workload.review` | eyni | `ensure_can_review_row` — yad ixtisas 403 | ✅ |
| Dekanlıq təsdiqi (15) | `workload.approve` | eyni | `ensure_can_approve(faculty_id)` | ✅ |
| Kafedra bölgüsü (14) | `workload.distribute` | eyni | `ensure_can_distribute` + `ensure_distribution_stage` | ✅ |
| Müəllim (16) | `workload.object` | eyni | `_own_assignment` — yalnız öz sətri | ✅ |
| Sual kafedra baxışı | `question.chair_review` | eyni | `can_review_submission_as_chair` (kafedra alt-ağacı; dekanlıq YALNIZ fallback-da) | ✅ |
| Sillabus təsdiqi | `syllabus.review` | `syllabus.approve` (dekandan alınıb — `organizations/0035`) | `review_scope_queryset` | ✅ |
| Tələbə qəbulu (08) | `user.import` | `student.assign_group` (ayrı) | org-səviyyə | ✅ |
| Tələbə reyestri (09) | `student.registry_view` | `student.movement` **+** `people.manage_academic` (ikiqat) | `registry_records_qs` → `get_permission_scope` | ✅ |
| Keçilmiş dərslər (21) | müəllim = öz sətirləri; `journal.roster` = nəzarət | — | `scoped_lessons`; `ll_teacher` filtri nəzarətçisiz **403** | ✅ |

### Cross-scope mənfilər (yeni test sinfi `PlanCrossScopeTest`)

| # | Hal | Aktor | Gözlənilən | ƏVVƏL | İNDİ |
|---|---|---|---|---|---|
| 1 | `save_row` yad kafedranın planına | chair_head (B) | 403/404 | **200, sətir yarandı** | 404 |
| 2 | `approve_chair` yad kafedranın planı | chair_head (B) | 403/404 | **200, `faculty_council`** | 404 |
| 3 | `approve_council` yad fakültənin planı | dean (B) | 403/404 | **200, `teaching_office`** | 404 |
| 4 | `create_plan` yad ixtisas üçün | chair_head (B) | 403/404 | **200, plan yarandı** | 404 |
| 5 | *pozitiv nəzarət* — öz kafedrası | chair_head (A) | 200 | 200 | 200 |
| 6 | *pozitiv nəzarət* — Tədris şöbəsi (org scope) | teaching_office_head | 200 | 200 | 200 |

**403 ↔ 404 semantikası:** açarı ÜMUMİYYƏTLƏ olmayan aktor **403** alır
(«səlahiyyətin yoxdur» — o, planı onsuz da görür); açarı olan, amma əhatədən
kənar aktor **404** alır (planın mövcudluğu sızmır). Mövcud test
`test_chair_head_cannot_approve_faculty_council_stage` (403 gözləyir) beləliklə
pozulmadı.

### Atlanmış mərhələ (skipped-stage) hücumları

| Hal | Nəticə |
|---|---|
| İmtahan Mərkəzi kafedra təsdiqindən ƏVVƏL qərar verir | ✅ `ensure_can_review_submission` — `reached_center_at` şərti (403); `question_submission_detail` / `visual_preview` / `questions` da 404 |
| Kafedra təsdiqlənməmiş tapşırığı bölür | ✅ `ensure_distribution_stage` → 409 `workload.not_approved_yet` |
| Müəllim təsdiqlənmiş planı redaktə edir | ✅ `assert_editable` → 409 `plan_immutable` |
| Baxışdakı (submitted) plana sətir yazmaq | ✅ 409 `plan_locked` |
| Planı olmayan ixtisas üçün semestr açılışı | ✅ `blocked_programs` (mövcud test) |
| Sıra pozan tələbə hərəkəti (məs. `enrolled → reinstatement`) | ✅ `movements.validate` → 409 `illegal_transition` |
| Düzəlişsiz təkrar göndəriş | ✅ `TEACHER_EDITABLE_STATUSES` |
| Dekan sillabusu təsdiqləyir | ✅ `syllabus.approve` dekandan alınıb (`organizations/0035`) |

---

## 3. Server tərəfli validasiya və mass assignment

| Endpoint | Naməlum sahə | ID-lər org+scope ilə | Səbəb ≥20 | Fayl |
|---|---|---|---|---|
| `organizations:structure_tree_action` | POST açarları ağ siyahıdadır | ✅ `_visible_unit` | ✅ (`assign_head`, `archive`) | — |
| `organizations:group_action` | ✅ | ✅ `_visible_group`, `curriculum_id` mövcudluq yoxlanışı, `tutor` = aktiv üzv | ✅ (`archive`, `restore`, `promote`) | — |
| `registrar:catalog_action` | ✅ | ✅ org filtri | ✅ (`archive`) | — |
| `registrar:curriculum_action` | ✅ (`_int_or` clamp: semestr 1–16, kredit 0–60, saat 0–2000) | ✅ **düzəlişdən sonra** | ✅ (`return`) | — |
| `registrar:semester_action` | ✅ | ✅ | ✅ (`unlock`, `cancel_offering`) | — |
| `accounts:student_registry_action` | ✅ | ✅ `_target_group` (scope), `_target_program` (org+aktiv) | ✅ `MOVEMENT_REASON_MIN_LENGTH=20` | `.pdf/.jpg/.jpeg/.png/.webp`, 10 MB, `FileUploadValidator` |
| `accounts:student_admission_create_group` | ✅ | ✅ `unit_type=SPECIALTY` + org | — | — |
| `student_intake_apply` (`group_<n>` override) | ✅ `_resolve_overrides` — org + `unit_type=GROUP` + `is_active` filtri, yad id ATILIR | ✅ | — | — |
| `workload:action` | ✅ `_uuid()` — sərbəst mətn UUID sütununa düşmür | ✅ hər handler org+`covers_unit` | ✅ `ensure_reason` | xlsx: 10 MB / 1000 sətir (`imports.MAX_*`) |
| `exams:question_submission_chair_decide` | ✅ (`decision` ağ siyahı) | ✅ org + `ensure_can_chair_review` | ✅ `MIN_REASON_LENGTH=20` | — |

**Fayl yükləmələri.** `StudentMovement.document` — `core.upload_security
.FileUploadValidator(allowed_extensions=…, max_size_mb=10)`, `full_clean()`
save-dən əvvəl çağırılır. Dərs yükü xlsx-i model sahəsi deyil (sessiyada
önizləmə), öz limitləri var. **Yeni prefiks `student_movements/` artıq media
reyestrindədir** (aşağı bax).

---

## 4. Əlavə-only / dəyişməzlik + RLS örtüyü

### Trigger / qapı vəziyyəti

| Obyekt | RLS | UPDATE bloklanır | DELETE bloklanır | Mənbə |
|---|---|---|---|---|
| `registrar_studentmovement` | ✅ force | ✅ trigger | ✅ trigger | `registrar/0067` |
| `workload_loadobjection` | ✅ force | ✅ **qismən** (mətn/`row_id`/`created_at` toxunulmaz, qərar sahələri açıq) | ✅ | `workload/0005` |
| `workload_taskfacultyslice` | ✅ force | — (iş axını) | — | `workload/0005` |
| `workload_taskrowreview` | ✅ force | ❌ `update_or_create` | — | P3 |
| `exams_questionsubmissionevent` | ✅ force | ✅ **yeni trigger** | ⚠️ CASCADE (qəsdən) | `organizations/0037` + **`exams/0065`** |
| təsdiqlənmiş `Curriculum` | ✅ force | ✅ `assert_editable`/`resolve` → 409 | plan heç vaxt silinmir (yeni versiya) | `curriculum_state.py` |
| təsdiqlənmiş `SyllabusVersion` | ✅ force | ✅ state maşını + `escalate_if_structural` | — | `syllabus/services` |

### RLS örtüyü — bütün org-scoped cədvəllər (təzə miqrasiya olunmuş bazada `pg_policy` sorğusu)

`registrar_*` (41 cədvəl), `workload_*` (7), `syllabus_*` (4),
`exams_questionsubmission*` (2) — **hamısında** `relrowsecurity=t`,
`relforcerowsecurity=t` və 1 `rls_tenant_isolation` siyasəti.
**RLS-siz org-scoped yeni cədvəl YOXDUR.**

Miqrasiyalar `0064`/`0065` yalnız MÖVCUD cədvəllərə sahə əlavə edir (yeni
cədvəl yaratmır), ona görə əlavə RLS tələb etmirlər.

**Mənfi suitlər (`emsarena_ci_rls`, NOBYPASSRLS): 91 test, 91 keçdi** —
`registrar/organizations/syllabus/workload/workload-stage4/applications`.

---

## 5. Injection / XSS / CSRF / CSP

* **`|safe` / `mark_safe` / `autoescape off`** — dəyişən 103 SERVER şablonunun
  (docs-dakı dizayn maketləri xaric) heç birində istifadəçi mətnində YOXDUR.
  Yeganə `|safe` (`partials/_bootstrap_select_field.html`) hər üç çağırış
  yerində HARDCODED sətir alır (`data-post-category-sub-hint`).
* **Inline `<style>` / `<script>`** — yeni server şablonlarında **yoxdur**
  (yalnız `<script src=…>` və `type="application/json"` blokları). CSP
  (`SELF` + `NONCE`) pozulmur, `CLAUDE.md` qaydası saxlanılıb. Diffdəki inline
  bloklar `docs/design/**` altındakı `.dc.html` maketlərindədir — servis
  olunmur.
* **CSRF** — yeni Python-da bir dənə də `csrf_exempt` yoxdur; bütün JSON
  yazmaları `@require_POST` + standart CSRF middleware ilə gedir.
* **Log injection** — yeni kodda f-string ilə log yoxdur; `logger.warning(...)`
  çağırışları sabit mətn + `exc_info`. `core.logging_utils.safe_log_value`
  `sections_api.py`-da işlədilir.
* **Redirect** — 3 `redirect()` çağırışı da NAMED URL-ə gedir
  (`exams:question_submission_chair_review`) və ya daxili sabit sətrə
  (`_profile_section_url`); istifadəçi girişindən gələn `next`/URL yoxdur.
* **Raw SQL** — yeni `.raw(` / `cursor.execute(` YALNIZ miqrasiyalarda (DDL),
  hamısı `params=None` ilə sabit gövdə; string interpolyasiyası istifadəçi
  girişindən DEYİL.

---

## 6. Data ifşası

* **CSV ixracları** — `student_registry_export` (`student.registry_view` + scope
  + 10 000 sətir tavanı) və `lessons_log_csv` (`scoped_lessons` + `ll_teacher`
  filtri nəzarətçisiz **403** + 5 000 sətir tavanı). Hər ikisi
  `Cache-Control: private, no-store` / `X-Content-Type-Options: nosniff`.
* **Əmr sənədinin endirilməsi** — `student_registry_document` icazə + scope
  yoxlayır; **əlavə olaraq** raw media prefiksi indi private-dır (P0 düzəlişi).
* **Bildirişlər** — `_programme_watchers` qrupun `path`-ı üzrə üzvlüklərlə
  məhdudlaşır; `_notify_next_approver` ixtisas→kafedra→fakültə rəhbər zəncirini
  gəzir. Cross-scope sızma tapılmadı. `_notify_chairs` (semestr) təşkilatın
  bütün kafedra rəhbərlərinə gedir — hadisə onsuz da org-səviyyəlidir.
* **Badge sayğacları** — `pending_chair_review_count` → `chair_queue_queryset`
  (əhatəsiz aktor **boş** növbə).
* **Qəbul cavabı** — `credentials[]` yalnız bir dəfə, bu sorğuda qayıdır və
  saxlanılmır (P3 qeydi).

---

## 7. Tətbiq olunan düzəlişlər (commit EDİLMƏYİB)

| # | Fayl | Nə edildi | Test |
|---|---|---|---|
| 1 | `core/media_policies.py` (+`check_student_movement_access`, `PRIVATE_PREFIXES`, `ACCESS_CHECKERS`) | `student_movements/` private prefiks + checker: əmrin aid olduğu TƏLƏBƏ, yaxud sahibi təşkilatda `student.registry_view` daşıyan aktor; qalan hamı **DENY** | `test_student_services_sections.py::MovementActionTest::test_raw_media_path_is_private_and_not_guessable` |
| 2 | `apps/registrar/models/movement.py:49` | `movement_document_path` fayl adını UUID-ə çevirir (uzantı orijinaldan, `slugify`-lı); miqrasiya TƏLƏB OLUNMUR (Django funksiya REFERANSINI serialize edir — `makemigrations --check` təmiz) | eyni test |
| 3 | `apps/registrar/curriculum_registry.py:70-113` | `plan_scope` / `unit_in_scope` / `program_in_scope` / `plan_in_scope` — əhatə `OrgUnit.user_permission_scope` ilə (modul sərhədi pozulmur: `apps.organizations` statik import EDİLMİR) | — |
| 4 | `apps/registrar/curriculum_actions.py:77,137,309` | `_plan()` artıq `request` + tələb olunan AÇAR alır və planı əhatə ilə süzür; `_create_plan` hədəf ixtisası `plan.edit` əhatəsi ilə yoxlayır; `_transition` əhatəni `permission_for(action, status)` ilə seçir | `test_teaching_office_stage2.py::PlanCrossScopeTest` (6 test) |
| 5 | `apps/exams/migrations/0065_question_submission_event_append_only.py` | `exams_questionsubmissionevent` üçün UPDATE bloklayan trigger (DELETE qəsdən açıq — FK CASCADE) | `test_question_chair_review.py::ChairEventLedgerImmutabilityTests` |
| 6 | `apps/workload/actions.py:124` | `import_upload` → `ensure_can_manage(actor, task.chair_id)` (idxalın 1-ci addımı da qapılı) | mövcud `test_stage4_*` yaşıl |

### Doğrulama

```
apps/accounts/tests/test_teaching_office_stage2.py ......... 45 passed
apps/accounts/tests/test_student_services_sections.py + core/tests/test_media_views.py ... 87 passed
apps/exams/tests/test_question_chair_review.py ............. 23 passed
organizations/test_permissions + media + view_as + workload + syllabus
  + question_submission + journal_topic_source + teaching_office_sections
  + lessons_log_section ....................................  528 passed
RLS (emsarena_ci_rls, NOBYPASSRLS) ..........................  91 passed
black / isort / flake8 / check_module_size / module_deps /
makemigrations --check / check_i18n_catalogs ................  hamısı ✅
```

---

## 8. Açıq qalanlar (fix TƏKLİFİ ilə)

**P2 — slug ↔ aktiv təşkilat uyğunsuzluğu.**
`structure_tree_action(request, slug)` və `group_action(request, slug)` hədəfi
slug-dan, icazəni isə `request.org_permissions`-dan (aktiv təşkilat) alır.
*Fix:* endpoint-in başında `if organization.pk != getattr(request.organization,
"pk", None): raise Http404` — və ya icazəni `user_has_org_permission(user,
organization, …)` ilə HƏDƏF təşkilatdan həll et. Düzəlişi bu dalğada
etmədim, çünki eyni naxış bütün `organizations/<slug>/…` səthində var və
təşkilat dəyişmə axınını qıra bilər — ayrıca dilim kimi aparılmalıdır.

**P3 — `TaskRowReview` tarixçə deyil.** Ya modelin/sənədin dili düzəlsin
(«cari viza», tarixçə deyil), ya da `update_or_create` yerinə append + `latest`
güzgüsü qurulsun.

**P3 — hadisə lentinin CASCADE silinməsi.** `QuestionSubmission.delete()` lenti
də aparır. `on_delete=PROTECT` + göndərişin soft-delete-i (imtahan modulunda
onsuz da mövcud naxış) təklif olunur.

**P3 — qəbul parollarının JSON cavabı.** Ayrıca bir dəfəlik CSV/PDF endpoint-i
(`Cache-Control: no-store`) və ekranda bir dəfə göstərmə daha təhlükəsizdir.
