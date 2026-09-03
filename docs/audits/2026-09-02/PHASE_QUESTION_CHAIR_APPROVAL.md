# Sual göndərişi → KAFEDRA TƏSDİQİ halqası (sahib tələbi, 2026-09-03)

**Sahibin tələbi.** Müəllim imtahan suallarını (final və ya aralıq) İmtahan
Mərkəzinə göndərəndə göndəriş **əvvəlcə kafedra müdirinin təsdiqindən**
keçməlidir; təsdiqdən sonra mərkəzə düşməlidir və **bütün yol izlənə bilməlidir**.

Əvvəl: `müəllim → İmtahan Mərkəzi` (birbaşa).
İndi: `müəllim → KAFEDRA MÜDİRİ → İmtahan Mərkəzi`.

Branch: `audit/post-migration-qa-2026-09` (commit EDİLMƏYİB — follow-up PR).

---

## 1. Əvvəlki vəziyyət (tapıntı)

| Səth | Fayl:sətir |
|---|---|
| Model (3 status: `pending/accepted/rejected`) | `apps/exams/domain/submission_inbox.py:33-39` (əvvəlki hal) |
| Göndərmə + mərkəzə bildiriş | `apps/exams/services/question_submission.py:submit_question_set` → `_notify_exam_center_new_submission` |
| Mərkəz qərarı | `apps/exams/services/question_submission.py:accept_submission/reject_submission` |
| Mərkəz qapısı | `ensure_can_review_submission` — YALNIZ `is_exam_center_user` |
| Müəllim/mərkəz bölməsi (eyni açar) | `apps/accounts/views/profile/_sections/question_submissions.py` |
| Mərkəz baxış səhifəsi | `apps/exams/views/teacher/submission_review.py:question_submission_review` |
| Rol matrisi | `docs/ROL_MATRISI.md` — `question-submissions` müəllim + `exam_center` |

Kafedra müdiri zəncirdə **ümumiyyətlə iştirak etmirdi**; iz yalnız `reviewer_note`
sahəsində qalırdı və yenidən göndərişdə **silinirdi**.

---

## 2. Yeni vəziyyət maşını

```
draft
  └─(müəllim göndərir)→ submitted_to_chair
                          ├─(kafedra: düzəliş, səbəb ≥20)→ chair_revision ──┐
                          ├─(kafedra: rədd, səbəb ≥20)────→ rejected ───────┤
                          └─(kafedra: təsdiq)─────────────→ chair_approved  │
                                                              │             │
                                        (mərkəz səhifəni açır)│             │
                                                              ▼             │
                                                        center_review       │
                                     ┌────────────────────────┼─────────────┤
                          (qəbul)→ accepted   (düzəliş≥20)→ center_revision │
                                              (rədd ≥20)→ rejected          │
                                                                            │
   müəllim redaktə edib yenidən göndərir ────────────────────────────────────┘
                       └──→ HƏMİŞƏ submitted_to_chair (kafedra ATLANA BİLMİR)
```

* Kafedra mərhələsi: `QuestionSubmission.CHAIR_STAGE_STATUSES`
* Mərkəz mərhələsi: `CENTER_STAGE_STATUSES = (chair_approved, center_review)`
* Müəllim redaktəsi: `TEACHER_EDITABLE_STATUSES` (`draft, submitted_to_chair,
  chair_revision, center_revision, rejected`) — `chair_approved`/`center_review`
  DONDURULUB (mərkəzin gördüyü məzmun dəyişmir).
* **Mərkəzin görünürlük qapısı** = `reached_center_at` sahəsi (kafedra təsdiqində
  dolur). Boşdursa mərkəz göndərişi **ümumiyyətlə görmür** — 403/404, mövcudluq
  sızması yoxdur.
* Köhnə `pending` sətirləri miqrasiya ilə `center_review`-a köçdü və
  `reached_center_at` `created_at`-dən dolduruldu (mərkəzin növbəsi itmədi).

### Marşrutlaşdırma (kafedra kimdir?)

`apps/exams/services/question_chair_units.py:resolve_submission_chair_unit`
— sillabusun `apps/syllabus/services/units.py` məntiqi ilə eyni sıra
(modul sərhədini keçməmək üçün exams-də təkrar qurulub):

1. göndərişin qruplarının `org_unit`-indən yuxarı ilk `chair`/`department`;
2. tapılmasa müəllimin **öz aktiv kafedra üzvlüyü**;
3. o da yoxdursa `None`.

Sonra `chair_route_targets` → `chair_head_memberships_for_unit`
(`apps/organizations/unit_heads.py`). Kafedra müdiri **yoxdursa** göndəriş
`dean_memberships_for_unit`-ə (DEKANLIĞA) gedir və `routed_to_dean=True`
qoyulur — UI-də açıq qeyd göstərilir. **Heç vaxt səssizcə mərkəzə düşmür.**

### İz (append-only)

`QuestionSubmissionEvent` (`apps/exams/domain/submission_events.py`):
`submission, organization, actor(SET_NULL), actor_label, actor_role, action,
from_status, to_status, reason, metadata, created_at`; `ordering = ["id"]`,
yalnız `record_event` yazır. UI zaman xəttini (timeline) məhz bundan qurur.
Hər keçid həm də `core.audit.log_action(AuditAction.UPDATE, resource_type=
"question_submission", reason=<səbəb>)` ilə audit olunur.

---

## 3. İcazə

Yeni kanonik açar: **`question.chair_review`**
(`apps/organizations/permissions.py` → `PERMISSION_CATEGORIES["exams"]`,
etiket: «Sual dəstini kafedra adından təsdiqləmək»).

Prefiks **qəsdən `exam.` DEYİL**: `exam.*` wildcard-ı dekanda, imtahan
mərkəzində və müəllimdə var — kafedra təsdiqi onlara avtomatik keçməməlidir.

| Rol | Açar | Faktiki əhatə (fail-closed) |
|---|---|---|
| `chair_head` | var (default + miqrasiya) | YALNIZ öz kafedrası (`scope_unit` kafedra tipli və göndərişin `chair_unit`-ini örtür) |
| `dean` | var | YALNIZ `routed_to_dean=True` olan göndərişlər (fallback təsdiqçi) |
| `ikt_rehber`/rektor/prorektor | `*` / org-scope | bütün təşkilat (audit izi ilə) |
| `teacher`, `exam_center` | YOX | 403 |

* Backfill: `apps/organizations/migrations/0036_seed_question_chair_review.py`
  (depends on `0035_dean_syllabus_review_only`, idempotent, `*`/`question.*`
  daşıyan rola toxunmur).
* Yeni tenant: `apps/organizations/default_roles_university.py` (`chair_head`, `dean`).
* Server qapıları:
  * `question_chair_units.can_review_submission_as_chair` — kafedra qərarı;
  * `question_submission.ensure_can_review_submission` — mərkəz: `is_exam_center_user`
    **VƏ** `has_reached_center`;
  * `ensure_can_decide_as_center` — status `chair_approved|center_review`;
  * müəllim kafedranı ATLAYA BİLMİR: `resubmit_question_set` yeganə yol kimi
    `route_submission_to_chair`-ı çağırır.

---

## 4. Dəyişən/əlavə olunan fayllar

### Model + miqrasiya
* `apps/exams/domain/submission_inbox.py` — 8 status, `chair_unit`,
  `routed_to_dean`, `chair_reviewer/chair_reviewed_at/chair_decision/chair_note`,
  `reached_center_at`, `is_at_chair/is_at_center/has_reached_center`.
* `apps/exams/domain/submission_events.py` **(yeni)** — `QuestionSubmissionEvent`.
* `apps/exams/domain/__init__.py`, `apps/exams/models.py` — ixrac.
* `apps/exams/migrations/0063_question_submission_chair_stage.py` (sxem)
* `apps/exams/migrations/0064_question_submission_chair_backfill.py` (data:
  `pending → center_review`, `reached_center_at` doldurulur)
* `apps/organizations/migrations/0036_seed_question_chair_review.py` (icazə)
* `apps/organizations/migrations/0037_rls_question_submission_event.py`
  (RLS/FORCE RLS, `organization_id` üzrə — postgres xaricində no-op)

### Servis
* `apps/exams/services/question_chair_units.py` **(yeni)** — kafedra həlli,
  marşrut hədəfləri, əhatə (`chair_queue_filter`, `can_review_submission_as_chair`).
* `apps/exams/services/question_chair_review.py` **(yeni)** — `route_submission_to_chair`,
  `chair_approve/chair_request_revision/chair_reject`, `record_event`, audit,
  bildirişlər, `chair_queue_queryset`, `pending_chair_review_count`.
* `apps/exams/services/question_submission.py` — göndərmə/yenidən göndərmə
  kafedraya marşrutlanır; mərkəz qapıları; `open_center_review`,
  `request_center_revision`; mərkəz «geri qaytar» ailəsi səbəb ≥20 tələb edir.

### View + URL
* `apps/exams/views/teacher/submission_chair.py` **(yeni)** — kafedra baxışı + qərar.
* `apps/exams/urls.py` — `question_submission_chair_review`, `..._chair_decide`.
* `apps/exams/views/__init__.py` — ixrac.
* `apps/exams/views/teacher/submission_review.py` — `open_center_review`,
  zaman xətti konteksti, 3-cü qərar (`revision`), lazy sual endpoint-i kafedraya açıq.
* `apps/exams/views/teacher/submission_inbox.py` — «Kafedra müdirinə göndər»,
  mərkəz detalı `has_reached_center` ilə qapılı, zaman xətti konteksti.
* `apps/exams/views/teacher/submission_media.py` — vizual önizləmə kafedraya
  açıq, mərkəzə yalnız təsdiqdən sonra.

### Profil bölməsi «Sual təsdiqi» (`question-chair-review`)
* `apps/accounts/views/profile/_sections/question_chair_review.py` **(yeni)** —
  növbə + KPI kartlar (status filtri) + filtrlər (imtahan növü / müəllim / axtarış).
* `apps/accounts/templates/accounts/profile/sections/_question_chair_review.html` **(yeni)**
* Qeydiyyat (`schedule-manage`/`student-intake` ilə eyni naxış):
  `sections_api.py` (SECTION_PARTIALS + AJAX_SAFE_SECTIONS),
  `_sections/labels.py` (şablon + başlıq), `_helpers/rbac_sections.py`
  (`can_review_question_chair` qapısı), `context_builder/_stage1.py` + `_stage4.py`,
  `templates/accounts/profile.html` (dispatch + `data-ajax-sections`),
  `profile/_sidebar_university.html` («Sillabus təsdiqi»-nin yanında, badge ilə).
* Badge: `_dashboard_helpers/cheap_counts.py:count_question_chair_pending`
  (+ `compute_profile_badge_counts`), `sections_api.py:profile_badges_api`
  (`question_chair_pending_count`), keş invalidasiyası hər yazıda
  (`question_chair_review._invalidate_badges`).

### UI (xarici CSS/JS, AJAX-safe — inline YOXDUR)
* `apps/exams/templates/exams/teacher/partials/_question_submission_chain.html` **(yeni)**
  — 4 mərhələli zolaq + «Kafedra tarixçəsi» hadisə lentı; müəllim detalında,
  kafedra səhifəsində və **mərkəzin baxış səhifəsində** eyni partial.
* `apps/exams/templates/exams/teacher/question_submission_chair_review.html` **(yeni)**
  — `accounts/profile_embed_base.html` extend edir → **sol sidebar qalır**;
  sual önizləməsi mərkəzin `_question_submission_preview_items.html` fraqmenti
  və eyni lazy endpoint.
* `apps/exams/static/exams/css/question_submission_chain.css` **(yeni)** — yalnız
  `--ems-*` tokenləri, light-only.
* `apps/exams/static/exams/js/question_submission_chair_review.js` **(yeni)** —
  səbəb dialoqu: focus trap, Esc, `aria-modal`, ≥20 simvol sayğacı; `EMSReady`.
* `apps/exams/static/exams/js/question_submission_review.js` — panel `data-decision`
  artıq siyahıdır (`"reject revision"`), 3-cü qərar üçün etiket/ikon.
* `apps/accounts/templates/.../_question_submissions.html` — yeni status pill-ləri
  + sətir-daxili «Yolu izlə» draweri (`prefetch_related("events__actor")`).
* `apps/accounts/views/profile/_sections/question_submissions.py` — status
  QRUPLARI (`at_chair/at_center/accepted/returned`), mərkəz sorğusu
  `reached_center_at__isnull=False` ilə daralıb.

---

## 5. Testlər

**Yeni:** `apps/exams/tests/test_question_chair_review.py` — 22 test:
marşrut (kafedra tapılır / dekanlıq fallback), hadisə lentı, bildiriş alıcıları
(kafedra HƏ, mərkəz YOX), təsdiq/düzəliş/rədd, audit sətri, səbəb ≥20,
ikiqat qərar bloku, dekan yalnız fallback-da, başqa kafedra müdiri 403,
müəllim 403, mərkəz təsdiqdən əvvəl 403/404 və sonra 200 (+`center_opened` izi),
müəllim kafedranı atlaya bilmir, mərkəz düzəlişi yenidən kafedradan keçir,
növbə əhatəsi, badge sayğacı, bölmə görünürlüyü (rol üzrə).

**Uyğunlaşdırılan:** `apps/exams/tests/test_question_submission.py` (yeni statuslar,
kafedra fixture-ları, `_to_center` köməkçisi), `test_question_submission_visual.py`.

```
apps/exams/tests/test_question_submission.py          54 passed
apps/exams/tests/test_question_chair_review.py        22 passed
apps/exams/tests/test_question_submission_visual.py    9 passed
apps/exams/tests/test_import_retention.py              1 passed
apps/accounts/tests/test_sidebar_role_matrix.py       13 passed
apps/accounts/tests/test_dashboard_section.py         15 passed
apps/organizations/tests/test_permissions.py          15 passed
apps/accounts/tests/test_profile_views.py            159 passed
```
(postgres, `--ds=config.settings.test`, şəxsi baza `ems_qs_chair01/02`)

**Qapılar:** `black`/`isort`/`flake8` təmiz; `check_module_size.py --check` ✅;
`module_deps.py --check` ✅; `makemigrations --check` → «No changes detected».

---

## 6. Canlı yoxlama (QA klonu, `:8100`)

Klon miqrasiya olundu (`exams.0063/0064`, `organizations.0036/0037` OK).
`qa.teacher` və `qa.chair_head` eyni kafedradadır
(«Proqramlaşdırma və informasiya təhlükəsizliyi»); miqrasiya `chair_head` və
`dean` rollarına `question.chair_review` verdi.

| # | Addım | Nəticə |
|---|---|---|
| 1 | `qa.teacher` aralıq (midterm) sual dəsti göndərir | ✅ status «Kafedra müdirinə göndərilib» |
| 2 | `qa.exam_center` siyahısı | ✅ dəst **görünmür**; `/review/` → **403** |
| 3 | `qa.chair_head` «Sual təsdiqi» bölməsi | ✅ panel render olunur, dəst növbədə |
| 4 | Kafedra qərar səhifəsi | ✅ 200, **sol sidebar qalır**, Təsdiqlə/Düzəliş/Rədd düymələri |
| 5 | Qısa səbəblə düzəliş | ✅ **rədd edilir** (status dəyişmir) |
| 6 | Səbəblə düzəliş tələbi | ✅ müəllim «Kafedra düzəliş istəyib» + səbəbi lentdə görür |
| 7 | Müəllim yenidən göndərir | ✅ **yenidən kafedraya** (mərkəzə yox) |
| 8 | Kafedra təsdiqləyir | ✅ müəllimdə «Kafedra təsdiqləyib — İmtahan Mərkəzində» |
| 9 | `qa.exam_center` | ✅ indi **görünür**, `/review/` 200, «Kafedra tarixçəsi» + kafedra qeydi görünür |
| 10 | Mərkəz qəbul edir | ✅ bank yaradıldı |
| 11 | Sidebar badge | ✅ `data-badge-key="question_chair_pending_count"` = 1; `/accounts/profile/api/badges/` = 1 |

**CSP/konsol:** 5 səth (kafedra bölməsi, kafedra qərar səhifəsi, mərkəz baxışı,
müəllim bölməsi, müəllim detalı) — hamısı HTTP 200, **inline `<style>` = 0,
inline `<script>` = 0**, istinad edilən bütün `static/` faylları 200.
(Brauzer pəncərəsində login formuna parol yazmaq təhlükəsizlik qaydama görə
edilmədi — yoxlama render olunmuş HTML + statik aktivlərin statusu üzərindən
aparıldı; CSP-nin pozula biləcəyi yeganə hal inline blokdur və o, sıfırdır.)

**Təmizlik:** yaradılan bütün test obyektləri silindi (2 göndəriş + 7 hadisə,
7 bildiriş, 1 bank + 2 sual, 1 qrup, 1 fənn). Real köçürülmüş data-ya
toxunulmadı; `emsarena_db` (prod klon) ümumiyyətlə açılmadı.

---

## 7. i18n — YENİ msgid-lər (i18n agenti üçün; `.po` REDAKTƏ EDİLMƏYİB)

`scripts/check_i18n_catalogs.py` **qırmızıdır** (`source_missing 0 → 125`) —
bu, məhz aşağıdakı yeni mətnlərin hələ kataloqlara düşməməsidir.

### Yeni kontekstlər
* `exams.template.question_chain` (18) — zəncir zolağı + hadisə lentı etiketləri
* `exams.template.question_chair` (29) — kafedra qərar səhifəsi
* `exams.service.question_chair_review` (13) — bildiriş başlıq/mətnləri + səbəb xətası
* `exams.view.question_submission.chair` (4) — qərar mesajları
* `accounts.profile.question_chair_review` (25) — «Sual təsdiqi» bölməsi
* `exams.model.question_submission_event.choice|field|meta` (9 + 3 + 2)
* `exams.model.question_submission.choice.chair_decision` (3): `approved`,
  `revision`, `rejected`

### Mövcud kontekstlərə əlavələr
* `exams.model.question_submission.choice.status` (6 yeni): `draft`,
  `submitted_to_chair`, `chair_revision`, `chair_approved`, `center_review`,
  `center_revision`
* `exams.model.question_submission.field` (4): `chair_unit`, `chair_reviewer`,
  `chair_decision`, `chair_note`
* `exams.service.access.permission` (2): `question_submission_chair_review_denied`,
  `question_submission_requires_chair_approval`
* `exams.service.question_submission.error` (1): «Səbəb ən azı {count} simvol…»
* `exams.notification.question_submission` (2): İM düzəliş mesajı + rədd mesajı
  («…rədd edildi: {reason}» — köhnə variant DƏYİŞDİ)
* `exams.template.question_submission` (8): «Kafedra müdirinə göndər»,
  «Kafedra təsdiqinə sual göndər», «Düzəliş istə», «Düzəliş üçün geri qaytar»,
  «Rədd et», «Kafedra qeydi», + 2 izah mətni
* `exams.view.question_submission.message` (4): «Göndəriş kafedra müdirinin
  təsdiqinə göndərildi ({count} sual, {groups} qrup).», «Göndəriş yeniləndi və
  kafedra müdirinin təsdiqinə təkrar göndərildi.», «Düzəliş tələbi müəllimə
  göndərildi — düzəlişdən sonra yenidən kafedradan keçəcək.», «Rədd/düzəliş üçün
  müəllimə ən azı {count} simvolluq qeyd yazın — nəyi düzəltməlidir.»
* `accounts.profile.question_submissions` (10): yeni status pill-ləri +
  «Kafedra qeydi», «Yolu izlə», «Kafedrada»
* `profile.sidebar` (1): «Sual təsdiqi»
* `organizations.permission` (1): «Sual dəstini kafedra adından təsdiqləmək»

Tam siyahı (kontekst|msgid) üçün: bu fazanın fayllarında `pgettext`/`{% trans %}`.

---

## 8. Qalıq / növbəti addımlar

1. **i18n**: 4 kataloqa (az/en/ru/tr) yuxarıdakı msgid-lər əlavə olunmalıdır —
   qapı yaşıllaşana qədər CI qırmızı qalacaq.
2. `docs/ROL_MATRISI.md`-yə `question-chair-review` sətri əlavə edilməlidir
   (sənəd başqa agentin əlindədir — toxunulmadı).
3. Köhnə göndərişlərdə `chair_unit` **qəsdən boşdur** (kafedra mərhələsindən
   keçməyiblər) — uydurma bağ yaradılmadı.
4. `QuestionSubmissionEvent` üçün RLS tenant-izolyasiya testi
   `emsarena_ci_rls` rolu ilə ayrıca əlavə oluna bilər (siyasət tətbiq olunub,
   test hələ yoxdur).
