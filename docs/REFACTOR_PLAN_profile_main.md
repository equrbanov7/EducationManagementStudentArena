# Refaktor planı — `apps/accounts/views/profile/main.py`

## İcra statusu (davam edir)

- **Pattern təsdiqləndi və işləyir.** İki bölmə context-fragment kimi çıxarıldı,
  hər ikisi davranış-identik (153 profil testi keçir, eyni 3 əvvəlcədən mövcud
  sqlite fail dəyişmir), `black/isort/flake8` təmiz:
  - ✅ `_sections/exams.py` → `build_my_exams_context` ("my-exams")
  - ✅ `_sections/question_bank.py` → `build_question_bank_context` ("question-bank")
  - ✅ `_sections/unit_exams.py` → `build_unit_exams_context` ("unit-exams")
  - ✅ `_sections/labels.py` → `build_section_titles()` + `DIRECT_PROFILE_SECTION_TEMPLATES`
    (statik başlıq/şablon data — "sabitləri helper-ə çıxar")
  - ✅ `_sections/groups.py` → `build_groups_context` ("groups"; iç-içə şərt tək şərtə yığıldı)
  - ✅ `_sections/statistics.py` → `build_statistics_section` ("statistics"; ~250 sətir,
    AJAX erkən-return `JsonResponse` və ya dict qaytarır — ən böyük/riskli blok, 9 stat testi yaşıl)
  - ✅ `_sections/role_assignment.py` → `build_role_assignment_section` ("role-assignment")
  - ✅ `_sections/manage_roles.py` → `build_manage_roles_section` ("manage-roles")
  - ✅ `_sections/permission_editor.py` → `build_permission_editor_section` ("permission-editor")
  - ✅ `_sections/superadmin_orgs.py` → `build_superadmin_orgs_sections`
    ("superadmin-org-features" + "superadmin-organizations"; iki dict yerində mutasiya)
  - ✅ `_sections/notifications.py` → `build_notifications_context` ("notifications")
  - ✅ `_sections/review_queue.py` → `build_pending_review_context` + `build_review_results_context`
  - ✅ `_sections/posts.py` → `build_posts_context` ("posts" / "create-post")
- Fayl: 2313 → **1519 sətir** (~794 sətir, ~34% azalma). Qoruyucu baseline 1519-a sıxıldı.
  `_sections/` paketi: 13 bölmə modulu. **Bütün təhlükəsiz, yüksək-ROI bölmələr çıxarıldı.**

## Qalan — best-practice qeydi

- **category-management** (~80 sətir): sqlite-da 3 testi (`test_superadmin_*category_management*`)
  ƏVVƏLCƏDƏN düşür. Best-practice: bu bloku zəif lokal safety net ilə deyil, **CI/Postgres
  ilə doğrulanan ayrıca PR-da** çıxar. Sandbox-da TOXUNULMADI.
- **posts / create-post**: orta blok; çıxarıla bilər (safe).
- Student cluster (assigned-exams/courses, my-results, pending-answers): kiçik + paylaşılan
  default-lar → aşağı ROI, inline saxlamaq məqbuldur.
- Yekun `context = {...}` literal-ı (~200 sətir) sırf açar→dəyər xəritəsidir; faylı 600-dən
  aşağı salmaq üçün ya registry-əsaslı dispatch, ya context-obyekt lazımdır (ayrıca böyük PR).
- Onsuz da ideal formda (toxunulmadı): org-structure/faculties/kafedras/members/roles,
  audit-log, superadmin-org-inspector, superadmin-users, superadmin-ai,
  student-organization-management, my-appeals, manage-appeals.
- Qeyd: "my-appeals" / "manage-appeals" onsuz da ideal formdadır
  (`context.update(build_..._context(...))`) — toxunmağa ehtiyac yoxdur.
- Növbəti iri hədəflər (daha çox diqqət): `statistics` (~330 sətir, daxili AJAX
  `return _JR(...)` erkən-return var → handler həm `HttpResponse`, həm dict
  qaytara bilməli), `superadmin/management` klasteri, `groups` (~190).
- **Qalan bölmələr** (eyni pattern ilə, hər biri ayrıca + test): courses/my-courses,
  unit-exams, assigned-exams/courses, my-results, pending-answers, groups,
  posts/pending-post-approvals, pending-review, review-results, role-assignment,
  student-organization-*, permission-editor, manage-roles, org-structure/faculties/
  kafedras/members/roles, audit-log, superadmin-* (org-inspector/organizations/
  org-features/users/ai), notifications, publish-notification, category-management,
  statistics, my-appeals, manage-appeals.
- Hər çıxarışda: blokun OXUDUĞU lokalları (input) və TƏYİN ETDİYİ açarları (output)
  müəyyən et; output-ların blokdan sonra (yalnız son `context`-də) istifadə
  olunduğunu yoxla; non-aktiv halda main.py default-larını DƏQİQ replikasiya et.

---

## Orijinal plan

> Bu fayl qoruyucu (`scripts/module_size_budget.json`) ilə **dondurulub** —
> böyüyə bilməz. Aşağıdakı plan onu addım-addım, **tam test örtüyü ilə**
> kiçiltmək üçündür. Tələsik mexaniki bölgü TÖVSİYƏ OLUNMUR (səbəb §2).

## 1. Vəziyyət

`main.py` praktiki olaraq tək nəhəng funksiyadır: `user_profile()` (sətir
201–1996). 3 kiçik top-level köməkçi onsuz da ayrıdır
(`_build_effective_user_roles`, `_restore_profile_org_context`,
`_get_publish_notification_targets`), POST emalı da çıxarılıb
(`handle_profile_post`, `handle_contact_reply_post`).

## 2. Niyə bu digər god-file-lardan FƏRQLİDİR (mexaniki bölgü işləməz)

`parsing.py` / `results.py` / `question_bank.py` **çoxlu müstəqil top-level
funksiya** idi → AST ilə paketə bölündü, import səthi qorundu.

`user_profile` isə **monolit "doldur-sonra-render"** funksiyasıdır:

1. ~50+ müştərək lokal dəyişən ilkin dəyərlə qurulur (`my_exams_list = []`,
   `question_bank_banks = []`, `context vars`, ...).
2. Uzun `if active_section == "X":` blok ardıcıllığı (sətir 318–1995) bu
   lokalları **şərti doldurur** (erkən return YOXDUR — yalnız 1657-də bir AJAX
   JSON return).
3. Sonda **tək** `context = {... 50+ açar ...}` yığılır və bir dəfə
   `return render(request, "accounts/profile.html", context)` (sətir 1996).

Yəni hər blok son render-ə gedən müştərək state-i mutasiya edir. Bloku sadəcə
ayrı modula köçürmək olmaz — çıxarılan funksiya doldurduğu bütün dəyişənləri
qaytarmalı, çağıran isə onları yenidən təyin etməlidir.

## 3. Tövsiyə olunan yanaşma — "context-fragment" registry (addım-addım)

Hər bölmə bloku, **yalnız öz doldurduğu açarları** olan dict qaytaran funksiyaya
çevrilir; `user_profile` onları çağırıb birləşdirir.

```python
# apps/accounts/views/profile/_sections/exams.py  (YENİ)
def build_my_exams_context(request, *, capabilities, my_exams_qs, active_section) -> dict:
    if active_section != "my-exams":
        return {}
    ...mövcud məntiq...
    return {
        "my_exams_list": ...,
        "my_exams_search_query": ...,
        "my_exams_filter_type": ...,
        "my_exams_dashboard": ...,
    }
```

```python
# main.py — dispatcher
context = {... base ...}
context.update(build_my_exams_context(request, capabilities=capabilities,
                                      my_exams_qs=my_exams_qs, active_section=active_section))
context.update(build_question_bank_context(request, ...))
... hər bölmə üçün ...
return render(request, "accounts/profile.html", context)
```

Bölmələr `_sections/` alt-paketinə qruplaşır (hər biri <600 sətir):
`courses.py`, `exams.py`, `appeals.py`, `posts.py`, `org_management.py`,
`superadmin.py`, `notifications.py`, `statistics.py`, `groups.py`.

## 4. Məcburi addım-addım proses (hər increment-də)

1. **Bir bölməni** seç (məs. `my-exams`).
2. O blokun OXUDUĞU bütün lokalları (input) və TƏYİN ETDİYİ açarları (output)
   dəqiq müəyyən et. Diqqət: bəzi bloklar əvvəlki blokun doldurduğu dəyişəni
   oxuyur — asılılıqları izlə.
3. `build_<section>_context(...)` funksiyasına çıxar; `main.py`-da
   `context.update(...)` ilə əvəz et.
4. **Testləri işlət** (aşağı) — yaşıl olmalı. Yalnız sonra növbəti bölməyə keç.
5. `black/isort/flake8` + `python scripts/check_module_size.py --check`.
6. Fayl ≤600-ə düşəndə `--update` ilə baseline-i sıx.

## 5. Test əmri (safety net)

```bash
DATABASE_URL="sqlite://" pytest apps/accounts/tests/test_profile_views.py \
  -p no:cacheprovider --no-migrations
```

> **MÖVCUD problem (refaktordan ƏVVƏL):** sqlite-da 3 test əvvəlcədən düşür —
> `test_superadmin_profile_*category_management*` (assertion @ test line 2616).
> Bunlar bu refaktorla bağlı DEYİL (ehtimal sqlite vs Postgres kateqoriya-ağac
> davranışı). Tam doğrulama üçün `-m postgres` daxil CI-də işlət. Refaktor bu 3
> testin vəziyyətini DƏYİŞMƏMƏLİDİR (153 keçən test keçən qalmalı).

## 6. Risk

- **Yüksək** — `accounts/profile.html` platformanın ən çox istifadə olunan
  səhifəsidir; bütün rollar (student/teacher/admin/superadmin) eyni view-dan
  keçir. Hər increment ayrıca PR + tam test (CI, Postgres daxil) ilə.
- Şablon (`accounts/profile.html` + `sections/` partial-ları) `context`
  açarlarını birbaşa oxuyur → hər açar qorunmalıdır (heç biri düşməməli).
- AJAX bölmə yükləyici (`sections_api.py`) eyni `user_profile`-i çağırır —
  fragment-lər həm tam səhifə, həm AJAX yolunda işləməli.
