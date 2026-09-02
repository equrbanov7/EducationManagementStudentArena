# FAZA 22 — Kabinet ana səhifəsi (`dashboard` / «Ana səhifə»)

**Tarix:** 2026-09-02 · **Branch:** `audit/post-migration-qa-2026-09`
**Baza:** QA klonu `emsarena_rehearsal_a0d170000901` (:55433) · **Server:** `http://127.0.0.1:8100`
**Test bazası:** `ems_dash_2406029007` (agent postgres :55432)

## 0. Problem (FAZA 21 §1 tapıntısı)

Hər rol kabinetə **`profile-info`** ilə girirdi — yəni istifadəçinin ilk gördüyü
ekran öz doğum tarixi və e-poçtu olurdu. «Bu gün nə var, məndən nə gözlənilir»
sualına cavab verən səth **ümumiyyətlə yox idi**; istifadəçi 16–44 bölməlik
menyudan özü axtarmalı idi.

## 1. Nə edildi

Yeni profil bölməsi **`dashboard`** («Ana səhifə»):

* kabinetin **DEFAULT açılışıdır** (`/accounts/profile/` parametrsiz);
  `?section=profile-info` və bütün köhnə hədəflər **işləməyə davam edir**;
* sidebar-da «ÜMUMİ» qrupunun **BİRİNCİ** bəndidir («Profil məlumatı»ndan üstdə);
* **rol-aware vidjet kartları** göstərir — hər kart mövcud bölməyə yönləndirir;
* **yeni məlumat səthi DEYİL**: vidjet yalnız istifadəçinin `allowed_sections`-ında
  olan bölmə üçün qurulur, yəni **sayğac sızması yoxdur** (test ilə kilidli);
* **ucuzdur**: ağır context qurucuları (jurnal xülasəsi, analitika, sillabus
  əhatə hesabatı) çağırılmır — yalnız count/aggregate/`[:5]` dilim.

## 2. Vidjet ↔ rol matrisi (canlı klondan)

| vidjet açarı | başlıq | qapı (bölmə/bayraq) | göstərir |
|---|---|---|---|
| `student-today` | Bu gün dərslər | `my-schedule` + `is_student` | bu günün slotları (həftə paritetinə görə), növbəti dərsin saatı |
| `student-attendance` | Davamiyyət | `my-journal` + `is_student` | cari dövrün qayıb saatı, fənn sayı, proqramın buraxılış limiti |
| `student-grades` | Son qiymətlər | `my-journal` + `is_student` | sonuncu 5 `ComponentScore` (fənn · komponent · bal) |
| `teacher-today` | Bu gün dərslərim | `my-schedule` + `is_teacher` | bu günün slotları + həftəlik slot sayı |
| `teacher-offerings` | Fənlərim | `my-journal` + `is_teacher` | cari dövrün açılışları (say + 5 sətir) |
| `teacher-syllabus` | Sillabus işlərim | `syllabus-list` + `syllabus.edit` **və** `syllabus.review` YOXDURSA | qaralama/düzəliş gözləyən sillabuslar |
| `my-workload` | Dərs yüküm | `my-workload` (`workload.view`); 0 saatlı **qeyri-müəllim**də gizlənir | illik cəmi / norma / doluluq % |
| `applications` | Müraciətlər | `applications` | gözləyən müraciət (keşlənmiş badge — **0 sorğu**) |
| `syllabus-review` | Sillabus təsdiqi | `syllabus-review` | növbədə gözləyən versiyalar (fənn adı + status) |
| `workload-distribution` | Yük bölgüsü | `workload-distribution` | əhatədəki kafedra sayı + cari tapşırığın statusu |
| `schedule-scope` | Cədvəl idarəetməsi | `schedule-manage` | səlahiyyət sahəsindəki qrup sayı + 5 ad |
| `kollokvium-windows` | Kollokvium pəncərələri | `kollokvium-windows` | K1/K2/K3 vəziyyəti (qurulmayıb/deaktiv/planlanıb/açıq/bağlı) |
| `upcoming-exams` | Yaxın imtahanlar | `exam-center-stats` | bu andan sonrakı imtahanlar |
| `appeals` | Apellyasiyalar | `can_manage_appeals` | qərar gözləyənlər (**0 sorğu** — `_stage1`-də hesablanıb) |
| `corrections` | Jurnal düzəlişləri | `can_watch_legacy_grades` (`journal.correct` / `final_score.entry`) | bu gün / bu həftə edilmiş auditli düzəliş |
| `journal-close` | Jurnal bağlama | `journal-close` | aktiv bağlanma bildirişləri |
| `student-intake` | Tələbə idxalı | `student-intake` | keçid kartı (sorğu yoxdur) |
| `org-kpis` | Universitet göstəriciləri | `people-students`/`people-teachers` **VƏ** org-səviyyə scope | aktiv tələbə / müəllim sayı |

**Sızma qapıları (qəsdən):**

* `org-kpis` yalnız **org-wide** əhatəsi olan aktora göstərilir — dekan/kafedra
  müdiri kataloqda süzülmüş rəqəm görür, ana səhifədə süzgəcsiz org rəqəmi
  göstərmək sızma olardı.
* Keçid linki hədəf bölmə `allowed_sections`-da deyilsə **silinir**
  (`_finalise_links`) — məsələn imtahan mərkəzi «Jurnal düzəlişləri» sayğacını
  görür, amma jurnal bölməsini aça bilmirsə keçid göstərilmir.

## 3. Fayllar

**Yeni:**

| fayl | təyinat |
|---|---|
| `apps/accounts/views/profile/_sections/dashboard.py` | orkestrator: dövr/rol/qeyd həlli + vidjet siyahısı + link finalizasiyası |
| `apps/accounts/views/profile/_sections/dashboard_widgets.py` | şəxsi vidjetlər (tələbə + müəllim + öz yükü) və `widget()`/`section_link()` müqaviləsi |
| `apps/accounts/views/profile/_sections/dashboard_staff_widgets.py` | idarəetmə vidjetləri (sillabus/yük/cədvəl/RİM/imtahan mərkəzi/rektorluq) |
| `apps/accounts/templates/accounts/profile/sections/_dashboard.html` | panel (tam server-render, **JS YOXDUR**) |
| `apps/accounts/templates/accounts/profile/sidebar/_home_menu_item.html` | sidebar bəndi (ayrıca fayl — `_sidebar.html` 600 sətir qapısını keçməsin) |
| `apps/accounts/static/accounts/css/profile/dashboard.css` | `.dash-*` kartları (`--ems-*` tokenləri, ≤768 px tək sütun) |
| `apps/accounts/tests/test_dashboard_section.py` | 15 test (aşağı) |

**Dəyişən (qeydiyyat 6 nöqtədə + default hədəf):**

* `apps/accounts/views/_helpers/rbac.py` — `dashboard` HƏR autentifikasiya olunmuş
  istifadəçinin `allowed_sections`-ında (superadmin və adi qol);
* `apps/accounts/views/profile/constants.py` — `DEFAULT_PROFILE_SECTION = "dashboard"`,
  `FALLBACK_PROFILE_SECTION = "profile-info"`, `dashboard` → org-context tələb edən bölmələr;
* `apps/accounts/views/profile/context_builder/_stage1.py` — parametrsiz açılışın hədəfi;
* `_stage2.py` — `dashboard_section` ilkin dəyəri; `_stage3.py` — **lazy** qurucu çağırışı
  (yalnız aktiv bölmə `dashboard` olanda); `_stage4.py` — context açarı;
* `apps/accounts/views/profile/sections_api.py` — `SECTION_PARTIALS` + `AJAX_SAFE_SECTIONS`;
* `apps/accounts/views/profile/_sections/labels.py` — başlıq + `DIRECT_PROFILE_SECTION_TEMPLATES`;
* `apps/accounts/templates/accounts/profile.html` — CSS linki, `data-default-section`,
  `data-ajax-sections`, dispatch qolu;
* `apps/accounts/templates/accounts/profile/_sidebar.html` — bənd include-u.

**Yenilənən mövcud testlər (default hədəf dəyişdiyi üçün):**

* `test_profile_refactor_characterization.py` — `test_default_section_is_dashboard`
  (+ `?section=profile-info` hələ də işlədiyini yoxlayır);
* `test_profile_views.py` — iki test `profile-info` panelinin məzmununu yoxlayır,
  indi bölməni AÇIQ istəyir;
* `test_registrar_sections.py::test_sidebar_links_per_role` — müqayisə yalnız
  `<aside class="profile-sidebar">` blokunda aparılır (ana səhifə kartlarının
  keçidləri «menyuda var» kimi oxunmasın).

## 4. Sorğu büdcəsi (ölçülmüş)

`build_dashboard_section` birbaşa çağırılıb ölçülür (tam səhifə shell-i daxil
DEYİL — navbar/sidebar/badge dəsti bu bölmə ilə bağlı deyil).
`request.org_permissions` middleware-dəki kimi qoyulur.

| rol | vidjet | sorğu |
|---|---:|---:|
| student | 4 | **6** |
| program_coordinator | 2 | **5** |
| exam_center | 6 | **9** |
| teacher | 5 | **12** |
| chair_head | 4 | **13** |
| rector | 8 | **23** |
| ikt_rehber (RİM) | 11 | **25** |

Testdəki üst hədd: `MAX_DASHBOARD_QUERIES = 28`.

## 5. Testlər

`apps/accounts/tests/test_dashboard_section.py` — **15 test, hamısı yaşıl**:

* `DashboardLandingTest` — 8 rolda default hədəf `dashboard`; `?section=profile-info`
  işləyir; `dashboard` hər rolun `allowed_sections`-ındadır; AJAX fraqmenti 200 +
  `data-profile-section-panel="dashboard"`; sidebar bəndi var;
* `DashboardWidgetVisibilityTest` — **hər vidjet icazəli bölməyə uyğun gəlir**
  (sızma qapısı); tələbədə **heç bir idarəetmə vidjeti yoxdur**; müəllim / kafedra
  müdiri / koordinator / RİM / imtahan mərkəzi / dekan / rektor üçün gözlənilən
  kartlar var-yox yoxlaması;
* `DashboardQueryBudgetTest` — 7 rol üçün sorğu üst həddi.

## 6. Canlı yoxlama (:8100, QA klonu, real köçürülmüş data)

| hesab | panel | vidjetlər | REAL rəqəmlər |
|---|---|---|---|
| `qa.student` | ✅ dashboard | 4 | boş-hal mətnləri (sintetik hesabın SAR-ı yoxdur) |
| **`myedu.student.5925`** | ✅ | 4 | **22 qayıb saat · 9 fənn · 25 % limit · 5 real qiymət sətri** (Balıqların xəstəlikləri, Botanika …) |
| `qa.teacher` | ✅ | 5 | **60 saat / 500 norma / 12 % doluluq** |
| **`myedu.worker.459`** | ✅ | 5 | **6 açılış** (Akademik yazı və etika …) |
| `qa.chair_head` | ✅ | 4 | 1 kafedra · tapşırıq statusu «Bölüşdürülüb» · 1 sillabus növbədə |
| `qa.program_coordinator` | ✅ | 2 | **11 qrup** səlahiyyət sahəsində |
| `qa.dean` | ✅ | 3 | **28 qrup** |
| `qa.ikt_rehber` (RİM) | ✅ | 11 | **50 qrup · 18 kafedra · K1-K3 «qurulmayıb» · 7703 tələbə / 732 müəllim** |
| `qa.exam_center` | ✅ | 6 | kollokvium + apellyasiya + 7703/732 |
| `qa.rector` | ✅ | 8 | 18 kafedra · 7703/732 |

**Brauzerdə (1280 × 900):** kabinet «Ana səhifə» ilə açılır, sol sidebar yerində,
«ÜMUMİ» qrupunun BİRİNCİ bəndi «Ana səhifə» (aktiv/mavi). Kart keçidi
(«Cədvələ keç») SPA ilə swap olunur — səhifə yenilənmir, başlıq «Dərs cədvəli»yə
dəyişir, sidebar akkordeonu açılır. **Məhsul mənşəli konsol xətası YOXDUR**
(loqdakı tək `405` mənim `GET /accounts/logout/` yoxlamamdır — FAZA 21-dəki ilə eyni).

**375 px:** şəbəkə tək sütuna düşür (`343 px` trek), üfüqi sürüşmə yoxdur.
⚠️ İlk versiyada kartlar `703 px`-ə genişlənib kəsilirdi (`1fr` = `minmax(auto, 1fr)`
uzun fənn adının min-content enini götürür) — `min-width: 0` + `minmax(0, 1fr)`
ilə düzəldildi və yenidən ölçüldü.

## 7. Gate-lər

| gate | nəticə |
|---|---|
| `black --check` (14 fayl) | ✅ |
| `isort --check-only` | ✅ |
| `flake8` | ✅ |
| `scripts/check_module_size.py --check` | ✅ (sidebar bəndi ayrıca fayla çıxarıldı: 602 → 588) |
| `scripts/module_deps.py --check` | ✅ yeni dövr yoxdur |

Modul sərhədi: `accounts` yalnız **mövcud** kənarları işlədir —
`apps.registrar` (schedule/models/schedule_manage), `apps.syllabus.public`,
`apps.workload.public`, `apps.organizations.public/models`, `apps.exams.models`.
**Yeni modul asılılığı əlavə edilməyib.**

## 8. QALAN İŞ / xəbərdarlıqlar

### 8.1 i18n — BLOKLANIB (növbəti agentin kataloq doldurmasını gözləyir)

`apps/accounts/tests/test_profile_i18n_role_matrix.py::test_azerbaijani_text_does_not_leak_into_other_languages`
**18 alt-testdə qırmızıdır** (6 rol × en/ru/tr). Səbəb YALNIZ yeni msgid-lərin
tərcüməsiz olmasıdır (sızan sözlər: `Xülasə`, `bölmə`, `göstəriləcək`, `hələ`,
`səhifə`). `.po` fayllarına **QƏSDƏN toxunulmayıb** (koordinasiya: kataloq
doldurma inteqrasiya agentindədir). Kataloq dolduqdan sonra test yaşıl olmalıdır.

**Kontekst `accounts.dashboard`** (98 msgid) — tam siyahı:

```
Akademik qeydiniz tapılmadı — RİM-ə müraciət edin. · Aktiv · Aktiv jurnal bağlama
bildirişi yoxdur. · Apellyasiyalar · Apellyasiyalara keç · Açıq · Bağlamaya keç ·
Bu gün · Bu gün dərslər · Bu gün dərslərim · Bu gün üçün cədvəldə dərs yoxdur. ·
Bu gün üçün cədvəldə dərsiniz yoxdur. · Bu həftə · Bu həftə düzəliş edilməyib. ·
Bu kabinet üçün hələ göstəriləcək xülasə yoxdur — sol menyudan bölmə seçin. ·
Bölgüyə keç · CSV ilə toplu tələbə hesabı yaradın. · Cari dövr · Cari dövr üçün
pəncərə qurulmayıb. · Cari dövrdə qeydiyyat yoxdur. · Cari dövrdə sizə fənn təyin
olunmayıb. · Cari semestr üçün qrup cədvəliniz tapılmadı. · Cədvəl idarəetməsi ·
Cədvələ keç · Davamiyyət · Doluluq · Dərs yüküm · Dərs yükünə keç · Fənlərim ·
Fənn · Gözləyən · Həftədə · Hələ heç bir bal yazılmayıb. · Hərəkət gözləyən
müraciət yoxdur. · Jurnal bağlama · Jurnal düzəlişləri · Jurnala keç · Kafedra ·
Kataloqa keç · Kollokvium pəncərələri · Limit · Müraciətlər · Müraciətlərə keç ·
Müəllim · Norma · Növbədə · Növbəti · Növbəyə keç · Planlanmış imtahan yoxdur. ·
Planlanıb · Pəncərələrə keç · Qaralama və ya düzəliş gözləyən sillabus yoxdur. ·
Qayıb · Qrup · Qərar gözləyən apellyasiya yoxdur. · Salam, %(name)s · Sillabus
işlərim · Sillabus təsdiqi · Sillabuslara keç · Son qiymətlər · Statistikaya keç ·
Status · Struktur əhatəniz təyin edilməyib — növbə boşdur. · Səlahiyyət sahənizdə
qrup yoxdur. · Tələbə · Tələbə idxalı · Təsdiq gözləyən sillabus yoxdur. ·
Təsdiqlənmiş dərs yükü yoxdur. · Universitet göstəriciləri · Xülasə hazır deyil ·
Yaxın imtahanlar · Yazılan bal · Yük bölgüsü · aktiv · apellyasiya · açılış ·
açıq · bağlı · bildiriş · cari dövr · deaktiv · düzəliş · dərs · imtahan ·
müraciət · planlanıb · proqram üzrə · pəncərə · qurulmayıb · saat · sillabus ·
slot · sonuncu · səlahiyyət sahənizdə · tapşırıq yoxdur · yoxdur · İdxala keç ·
İllik cəmi · Əhatənizdə kafedra tapılmadı. · əhatədə
```

**Kontekst `profile.sidebar`** (1 YENİ msgid): `Ana səhifə`
— hər üç yerdə eyni: `labels.build_section_titles()`, `_home_menu_item.html`,
`profile.html` (`data-default-section-title`).

> `Salam, %(name)s` — Python `pgettext`-dədir (şablon `{% trans %}` DEYİL), ona görə
> `%` tələsi yoxdur; tərcümədə **`%(name)s` yer tutucusu saxlanılmalıdır**.

### 8.2 Bu bölmə ilə ƏLAQƏSİ OLMAYAN mövcud qırmızı test

`apps/accounts/tests/test_view_as.py::MutatingGetRouteScanTests::test_no_unreviewed_mutating_get_route_exists`
→ `workload:my_export` GET ilə mutasiya edir və `MUTATING_GET_URL_NAMES` /
`REVIEWED_SAFE` siyahılarına salınmayıb. **Mənim diffimdə nə marşrut, nə də
`apps/workload` var** — əvvəldən mövcud nasazlıqdır, `apps.workload` sahibinə
aiddir. (Ya `REVIEWED_SAFE`-ə əlavə edilməli, ya da ixrac GET-i yan-təsirsiz
edilməlidir.)

### 8.3 Kosmetik P3

Sidebar bəndi **bölmə linki olmayan** hədəflərdə (məsələn müəllimin
«Elektron jurnal»ı `/jurnal/`-a YENİ TABDA gedir) SPA başlığı yenilənmir:
`ui.js::updateSidebarActiveState` başlığı YALNIZ uyğun **sidebar** linkindən
oxuyur. Panel düzgün yüklənir, sidebar yerində qalır — yalnız H1 «Ana səhifə»
olaraq qalır. Ortaq SPA JS-inə toxunmamaq üçün dəyişdirilmədi.

### 8.4 Gələcək genişləndirmə

* **Elanlar** (blog/post) vidjeti qurulmadı — `posts` bölməsi org modul
  bayrağı ilə söndürülə bilir və ucuz public fasadı yoxdur.
* **Sistem/təhlükəsizlik hadisələri** vidjeti qurulmadı — `apps/monitoring`-in
  `public.py` fasadı YOXDUR; modul sərhədini pozmamaq üçün buraxıldı.
  (Fasad yarananda `dashboard_staff_widgets`-ə bir funksiya əlavə etmək kifayətdir.)

### 8.5 ⚠️ Commit vəziyyəti

Mən **commit etmədim** (tapşırıq şərti). Ancaq iş gedərkən inteqrasiya agentinin
`01eb0193` commit-i işçi ağacı süpürüb və `dashboard.py`, `dashboard_widgets.py`,
`dashboard_staff_widgets.py`, `rbac.py`, `constants.py`, `_stage1.py` fayllarını
**YARIMÇIQ** vəziyyətdə commit-ə salıb. **Bitmiş versiya işçi ağacındadır**
(commit-dən sonrakı `M` diffləri + 4 izlənməyən yeni fayl):

* `apps/accounts/static/accounts/css/profile/dashboard.css` (yeni)
* `apps/accounts/templates/accounts/profile/sections/_dashboard.html` (yeni)
* `apps/accounts/templates/accounts/profile/sidebar/_home_menu_item.html` (yeni)
* `apps/accounts/tests/test_dashboard_section.py` (yeni)
* və `profile.html` / `_sidebar.html` / `sections_api.py` / `labels.py` /
  `_stage2..4.py` / 3 test faylının dəyişiklikləri.

`01eb0193`-dəki hal **TAM DEYİL** (şablon, CSS, bölmə qeydiyyatı və testlər
orada yoxdur) — deploy/rebase edilərkən işçi ağacının hazırkı halı əsas
götürülməlidir.
