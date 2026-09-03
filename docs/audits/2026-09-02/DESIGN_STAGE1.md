# Dizayn Mərhələ 1 — Tədris şöbəsi (ekran 01–04)

**Tarix:** 2026-09-03 · **Budaq:** `audit/post-migration-qa-2026-09` (commit YOX — sahibin tələbi)
**Mənbə:** `docs/design/HANDOFF_FULL_PLAN.md` + `docs/design/handoff_full/README.md` §2–§5, §7, §8
**Əhatə:** 01 Universitet strukturu · 02 Kafedra profili · 03 İxtisaslar · 04 Fənn kataloqu

---

## 0. Bloklayıcı iş — qabığın bölünməsi (Mərhələ 1-in İLK addımı)

`profile.html` **599/600**, `rbac.py` **591/600** idi — yeni bölmə əlavə etmək
modul ölçüsü qapısını aşırdı. Üçü də DAVRANIŞ DƏYİŞMƏDƏN bölündü:

| Əvvəl | Sonra | Nəticə |
| --- | --- | --- |
| `accounts/profile.html` 599 sətir | **289 sətir** | `{% block extraCss %}` gövdəsi → `accounts/profile/_section_assets.html` (179), `{% elif active_section %}` zənciri → `accounts/profile/_section_dispatch.html` (171) |
| `views/_helpers/rbac.py` 591 sətir | **567 sətir** | U12 kabinet bloku + universitet struktur bloku → `views/_helpers/rbac_university_sections.py::university_role_sections()` (saf funksiya, dəst qaytarır) |

* `data-ajax-sections` **`profile.html`-də QALDI** (AJAX_SAFE_SECTIONS müqaviləsi
  dəyişməyib; yalnız 4 yeni açar əlavə olundu).
* `templates/partials/ems_ui/_assets.html` artıq qabıqdan yüklənir — Mərhələ 0-ın
  komponent kitabxanası ilk dəfə istehsal səthində işləyir.
* **Bölünmə öncəsi/sonrası eyni test dəsti: 242 → 242 keçdi** (`test_sidebar_role_matrix`,
  `test_profile_views`, `test_cabinet_modules`, `test_dashboard_section`,
  `test_section_registry_consistency`, `test_ems_ui_components`).

Sidebar üçün yeni qrup partial-ı: `accounts/profile/sidebar/_teaching_office_group.html`
(«TƏDRİS ŞÖBƏSİ» başlığı yalnız dörd bölmədən biri icazəlidirsə görünür).

---

## 1. Rollar və icazələr

### 1.1 Yeni rollar — `apps/organizations/default_roles_teaching_office.py`

| Açar | Ad (AZ) | Səviyyə | Scope |
| --- | --- | --- | --- |
| `teaching_office_head` | Tədris şöbəsinin rəhbəri | **85** | ORGANIZATION |
| `teaching_office_staff` | Tədris şöbəsi əməkdaşı | **60** | ORGANIZATION |

Fayl AYRIDIR, çünki `default_roles_university.py` 566/600 idi; siyahı orada
`UNIVERSITY_ROLES.extend(...)` ilə birləşir (seed/migration/test tək mənbədən oxuyur).

**`core/roles.py::ADMIN_ALIAS_EXEMPT_ROLE_NAMES`-ə `teaching_office_head` əlavə edildi.**
Səviyyə 85 ≥ 80 olduğu üçün əks halda implicit `org_admin` aliası alırdı.
Dondurulmuş snapshot-lar (`view_as.py`, `view_as_policy.py`, `organizations/services.py`)
həmin dəstdən TÖRƏYİR — əl ilə dəyişiklik lazım olmadı.
Testlə kilidləndi: `test_teaching_office_head_is_alias_exempt`,
`test_teaching_office_head_does_not_get_org_admin_surfaces`.

### 1.2 ⚠ İcazə ADLARINDA PLANDAN SAPMA (məcburi)

Tapşırıqda `structure.view|manage|assign_head` istənilirdi. **`structure.` prefiksi
bu layihədə LEGACY sayılır** və CI testi onu bloklayır:
`apps/organizations/tests/test_permissions.py::DefaultRolesCanonicalPermissionTest`
(`LEGACY_PREFIXES = ("grading.", "courses.", "exams.", "members.", "structure.")`).
Kanonik ailə `unit.*`-dır. Ona görə açarlar bu adlarla əkildi (məna eynidir və
`HANDOFF_FULL_PLAN.md` §3-dəki `unit.tree_manage` ilə uyğundur):

| Handoff adı | Tətbiq olunan kanonik açar |
| --- | --- |
| `structure.view` | `unit.view` (**mövcud** açar — yenidən istifadə) |
| `structure.manage` | `unit.tree_manage` (**yeni**) |
| `structure.assign_head` | `unit.assign_head` (**yeni**) |
| `catalog.view` / `catalog.manage` | eyni qaldı (`catalog.` legacy deyil) — **yeni** |

Kataloq + etiket: `apps/organizations/permissions.py` (`structure` kateqoriyasına
iki açar, yeni `catalog` kateqoriyası + `PERMISSION_CATEGORY_LABELS` girişi).

### 1.3 Paylanma

| Rol | `unit.view` | `unit.tree_manage` | `unit.assign_head` | `catalog.view` | `catalog.manage` |
| --- | --- | --- | --- | --- | --- |
| `rector` | `*` | `*` | `*` | `*` | `*` |
| `vice_rector` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ikt_rehber` (RİM) | `unit.*` | `unit.*` | `unit.*` | ✔ | ✔ |
| `teaching_office_head` | ✔ | ✔ | ✔ | ✔ | ✔ |
| `teaching_office_staff` | ✔ | ✔ | — | ✔ | ✔ |
| `dean` | ✔ | — | — | ✔ | — |
| `chair_head` | ✔ | — | — | ✔ | — |
| `program_coordinator` | ✔ | — | — | ✔ | — |
| `teacher` / `student` | — | — | — | — | — |

### 1.4 Migration

`apps/organizations/migrations/0038_seed_teaching_office_roles.py`
(`0036_seed_question_chair_review` və `0037_rls_question_submission_event` başqa
agent tərəfindən artıq yaradılmışdı → növbəti boş nömrə **0038**, asılılıq 0037).

* hər `org_type="university"` təşkilatda iki rolu **idempotent** yaradır;
* mövcud rollara (dekan, kafedra müdiri, koordinator, RİM, prorektor) yeni
  açarları paylayır — xəritə `default_roles_teaching_office.TEACHING_OFFICE_GRANTS`-dan
  oxunur, yəni seed ilə migration sürüşə bilmir;
* geri dönüş yalnız bu migrasiyanın açarlarını çıxarır və üzvü OLMAYAN rolları silir.

---

## 2. Model dəyişiklikləri

`apps/registrar/migrations/0064_catalog_archive_and_metadata.py`
(yeni CƏDVƏL yoxdur → əlavə RLS policy tələb olunmur):

| Model | Yeni sahə | Niyə |
| --- | --- | --- |
| `Program` | `education_form` (əyani/qiyabi/distant) | ekran 03 «Təhsil forması» sütunu |
| `Program`, `Subject` | `is_archived`, `archived_reason`, `archived_at`, `archived_by` | §8/5 «silmə yoxdur — arxivləmə var» |
| `Subject` | `kind` (ixtisas/ümumi/seçmə/təcrübə) | ekran 04 «Növ» |
| `Subject` | `chair_unit` → `"organizations.OrgUnit"` (string-ref) | ekran 04 «Sahibi kafedra» |

Sahələr `apps/registrar/models/catalog_meta.py`-də təyin olunub (abstrakt
`ArchivableCatalogModel` + sahə fabrikləri) — `models/academic.py` 582/600 idi.
`is_active` sahəsinə **TOXUNULMADI**: o «cari semestrdə istifadədədir» mənasını
daşıyır və köçürmə xətti ona söykənir; arxiv AYRI bayraqdır.

---

## 3. Ekranlar

Hamısı **kabinet bölməsidir** (`/accounts/profile/?section=…`), sol sidebar qalır,
panel sağda; `<h1>` bölmə şablonunda YAZILMIR (qabıq verir — canlıda `h1` sayı = 1).

### 01 · `org-structure-tree` «Universitet strukturu»
* `apps/organizations/structure_views/tree.py` — ağac qurucu (TƏK sorğu; valideyn→uşaq
  xəritəsi Python-da), tip filtri + axtarış (valideyn zənciri saxlanılır),
  «Rəhbəri olmayan bölmə» bayrağı, KPI sırası.
* Detal paneli **mövcud** `unit_detail.build_unit_detail_context`-i təkrar istifadə edir
  (müəllim/tələbə/qrup/ixtisas sayğacları orada; CRUD dublikat edilmədi).
* Klaviatura naviqasiyası, `role="tree"`, `aria-selected/expanded` → Mərhələ 0-ın
  `ems_ui/_tree.html` + `ems_ui/nav.js` (yenidən yazılmadı).
* Əməllər: `apps/organizations/structure_actions.py` (JSON POST,
  `organizations:structure_tree_action`) — alt bölmə yarat / adını dəyiş /
  rəhbər təyin et (**≥20 simvol səbəb**) / **arxivlə** (səbəb + audit).
  **Silmə yoxdur**; aktiv alt bölməsi olan vahid arxivlənmir.
* Bölmə tipləri `UNIT_TYPES_BY_ORG` kataloqundan açıldı (köhnə konsol yalnız
  fakültə+kafedra yaratmağa icazə verirdi).

### 02 · `chair-profile` «Kafedra profili»
* Glue: `apps/accounts/views/profile/_sections/teaching_office.py`.
* Kafedra siyahısı `visible_chairs` (əhatəyə görə) → kafedra müdiri YALNIZ özününkü.
* Ştat/yük: **yeni fasad** `apps/workload/public.py::chair_staff_load` — saat, norma,
  doluluq %, `dept_load` bandı (`free/normal/loaded/risk`), ştat payı cəmi.
  **Norma POLICY cədvəlindən** (`TeacherWorkloadProfile.annual_norm_hours`); profil
  yoxdursa NK №215 default-u (500 saat). Kodda hardcode norma YOXDUR.
* Sillabus əhatəsi: kafedranın sillabusları üzrə (təsdiqlənmiş / cəmi) — saxlanılmır.
* Ştat növü çipləri: Ştat · Əvəzçilik · Saathesabı (+ ixtisas/qrup/tələbə sayı).

### 03 · `programs-registry` «İxtisaslar»
* `apps/registrar/catalog_registry.py::build_programs_registry`.
* Filtr (axtarış / pillə / forma / kafedra / «Plan yoxdur» / arxiv), server sıralaması
  (`aria-sort`), server səhifələməsi (25/səhifə, filtrləri saxlayan pager).
* «Plan yoxdur» — `Curriculum` yoxluğundan HESABLANIR (saxlanılmır).
* Yaratma/redaktə dialoqu sətir-içi validasiya ilə; arxivləmə/bərpa səbəb dialoqu ilə.

### 04 · `subject-catalog` «Fənn kataloqu»
* `apps/registrar/catalog_registry.py::build_subject_catalog`.
* Dublikat AD xəbərdarlığı (lent + sətir badge-i + «yalnız dublikatlar» filtri) —
  klonda **7 ad dublikatı** aşkarlandı.
* «Planlarda istifadə» sütunu `CurriculumSubject` sayğacından (sıralana bilən).
* Yaratma/redaktə (kod unikallığı sətir-içi yoxlanılır), arxivləmə/bərpa.

### Yazı endpoint-ləri
`registrar:catalog_action` (`apps/registrar/catalog_actions.py`) — `catalog.manage`
qapısı, tenant filtri (cross-tenant id 404), `core.audit.log_action` hər əməldə.

---

## 4. Komponent kitabxanasına əlavə/düzəlişlər (Mərhələ 0 qatı)

| Fayl | Dəyişiklik | Səbəb |
| --- | --- | --- |
| `templates/partials/ems_ui/_form_dialog.html` | **YENİ** komponent | `_dialog.html`-də `<form>` yalnız gövdədə ola bilirdi → «Yadda saxla» formadan kənarda qalırdı |
| `templates/partials/ems_ui/_reason_dialog.html` | `reason_hidden`, `reason_form_data`, `reason_extra_include`, xəta zolağı | gizli sahələr + rəhbər seçicisi + server xətası |
| `static/js/ems_ui/filter_bar.js` | **BUG:** `EMSProfileLoadSection(section, {sourceUrl})` → `(section, url)` | imza sətir gözləyir; obyektlə URL «[object Object]» olurdu — filtr «Tətbiq et» heç işləməzdi |
| `static/js/ems_ui/overlay.js` | **BUG:** səbəb sayğacı `.ems-reason` daxilində axtarılırdı, halbuki footer-dədir | sayğac «0 / 20»-də donub qalırdı (canlıda ölçüldü) |
| `static/css/ems_ui/header.css` | **BUG:** mobil `flex-direction: column`-da `.ems-header__main{flex:1 1 320px}` basis-i HÜNDÜRLÜYƏ çevirirdi | 375-də başlıqdan sonra 320px boş sahə (ölçüldü: 320px → 51px) |
| `static/css/ems_ui/kpi.css` | `.ems-kpi__unit` üçün `margin-inline-start` | «0saat» yapışıq görünürdü |
| `core/ui/status_catalog.py` | **yeni ailə** `catalog_entry` (aktiv/plan yoxdur/dublikat/istifadəsiz/arxivdə) | ekran 03/04 sətir statusu |

Bölmə-xüsusi düzüm: `accounts/css/profile/sections/teaching_office.css` (yalnız grid;
kart/cədvəl/badge/KPI TƏKRAR TƏRİF OLUNMUR) və `accounts/js/profile/teaching_office.js`
(EMSReady/EMSDelegate, `[data-tof-root]` yoxdursa heç nə etmir). **Inline CSS/JS = 0.**

`teaching_office.js` CSRF tokenini formanın `{% csrf_token %}` sahəsindən oxuyur:
`EMSCore.getCsrfToken()` sabit `csrftoken` kuki adını oxuyur, `staging_inspect`-də isə
ad `emsarena_staging_csrftoken`-dur → eyni hostdakı başqa serverin köhnə kukisi
götürülür və server 403 qaytarırdı (canlı QA-da tapıldı).

---

## 5. Testlər

`apps/accounts/tests/test_teaching_office_sections.py` — **29 test**, hamısı keçir:

* fraqment 200: `teaching_office_head`, RİM · fraqment **403**: müəllim, tələbə (4 bölmə × 2 rol);
* menyuda sızma yoxdur (müəllim/tələbə);
* alias muafiyyəti + `org_admin` səthlərinin (`permission-editor`, `manage-roles`,
  `role-assignment`, `org-roles`) verilməməsi;
* əhatə: `chair_head` yalnız öz kafedrasını, TŞ rəhbəri hamısını;
* əməkdaşda «Rəhbər təyin et» düyməsi YOXDUR (markup yoxlaması);
* CRUD: fənn yarat/redaktə, təkrar kod → 400 + `field: code`;
* arxiv: səbəb <20 → 400 `reason_too_short`; ≥20 → sətir QALIR + `archived_reason` +
  `archived_at` + `AuditLog` yazısı; arxiv default siyahıdan süzülür, `sb_arch=1` ilə görünür;
* ağac: alt bölmə yaratma, rəhbər təyini (icazəsiz 403 → qısa səbəb 400 → uğur + audit),
  arxiv (aktiv uşağı olan vahid 400 `has_children`; uğurda sətir qalır, `is_active=False`),
  tələbə üçün 403;
* ağac konteksti: rəhbəri olmayan bölmə sayğacı, axtarışda valideyn zəncirinin qalması;
* filtr/sıralama/səhifələmə parametrləri; «Plan yoxdur» və dublikat hesablanması;
* icazə kataloqunun keçərliliyi + rol şablonunun açar dəsti + bölmə reyestrinin
  4 yerdə (SECTION_PARTIALS / AJAX_SAFE / DIRECT templates / başlıqlar) uzlaşması.

`apps/accounts/tests/test_syllabus_editor_render.py` yeniləndi: asset skanı artıq
`profile.html` + `_section_assets.html` cütünü oxuyur (CSS bölünməsindən sonra).

**Reqressiya dəsti** (`apps/accounts/tests`, `organizations` icazə/struktur/scope,
`apps/workload/tests`, `apps/registrar/tests`): **2 824 keçdi, 1 keçildi (skip), 0 uğursuz** (8 dəq 22 san).

**Qapılar:** `black` / `isort` / `flake8` ✅ · `check_module_size --check` ✅ ·
`module_deps --check` ✅ (yeni dövr yoxdur) · `check_worker_atomic_coverage --check` ✅ ·
`makemigrations --check` ✅ («No changes detected»).

---

## 6. Canlı yoxlama (QA klonu, `http://127.0.0.1:8100`)

Klon miqrasiya olundu (`0038` + `0064` tətbiq edildi). Test hesabları **yalnız klonda**:

| İstifadəçi | Parol | Rol |
| --- | --- | --- |
| `qa.teaching_office_head` | `QaAudit2026!` | Tədris şöbəsinin rəhbəri (85) |
| `qa.teaching_office_staff` | `QaAudit2026!` | Tədris şöbəsi əməkdaşı (60) |

### `qa.teaching_office_head` (1280×1500)
* Sidebar-da «TƏDRİS ŞÖBƏSİ» qrupu 4 bölmə ilə; org-admin bölmələri YOXDUR (alias muafiyyəti canlı təsdiq).
* **01:** KPI `BÖLMƏ 880 · FAKÜLTƏ 13 · KAFEDRA 18 · RƏHBƏRİ YOXDUR 31` (sonuncu sarı tonda);
  880 ağac sətri; qovşağa klik → detal («Rəhbər / Müəllim / Tələbə / Qrup / İxtisas»).
* **01 əməllər:** `QA-DS1 Test kafedrası` yaradıldı → adı dəyişdirildi → rəhbər təyin
  edildi (səbəb 20 simvoldan qısa ikən düymə **disabled**, sayğac `4 / 20` → `59 / 20`)
  → arxivləndi (ağacdan çıxdı, sətir bazada qaldı).
* **03:** KPI `İXTİSAS 101 · PLAN YOXDUR 4 · ARXİVDƏ 0 · CƏMİ 101`; 9 sütun,
  `aria-sort="ascending"` «Tam ad»-da; 25 sətir + səhifələmə.
  `QA-DS1 Sınaq ixtisası` yaradıldı → filtr «QA-DS1» tətbiq edildi (`Nəticə: 1 sətir`)
  → redaktə (ECTS 240→180) → arxivləndi (aktiv siyahıdan çıxdı, «İxtisas tapılmadı» boş
  vəziyyəti) → `pg_arch=1` ilə göründü («Arxivdə» badge) → arxivdən qaytarıldı.
* **04:** KPI `FƏNN 2501 · AD DUBLİKATI 7 · PLANDA İSTİFADƏDƏ 1884 · ARXİVDƏ 0`;
  dublikat lenti göründü. `QA-DS1-001` yaradıldı; eyni kodla ikinci yazı →
  «Bu kodla fənn artıq mövcuddur.» + `aria-invalid="true"`; sonra arxivləndi.
* **02:** kafedra seçicisi işlədi (Azərbaycan dili → Menecment: 23 → 59 müəllim sətri),
  ştat çipləri, `dept_load` badge-ləri («boş tutum»), `Sillabus 0 / 0`.
  Klonda yük profili/paylanmış tapşırıq olmadığı üçün saatlar 0-dır (gözlənilən).

### `qa.chair_head` (əhatə)
* «Kafedra profili»ndə seçicidə **TƏK** kafedra («Proqramlaşdırma və informasiya
  təhlükəsizliyi»); ağacda `BÖLMƏ 1 / KAFEDRA 1`, tək kök qovşaq.
* «İxtisaslar» **oxu-only**: «Əməllər» sütunu YOXDUR, sətir düymələri yoxdur,
  «Yeni ixtisas» düyməsi yoxdur (`catalog.manage` verilməyib).

### 375×900
* `document.scrollWidth == clientWidth == 375` (üfüqi sürüşmə **0**), `h1` sayı **1**;
* KPI 1 sütun, `tof-split` 1 sütun, cədvəl ÖZ konteynerində sürüşür;
* başlıq bloku düzəlişdən sonra 320px → **51px**.

### Konsol / şəbəkə
`performance.getEntriesByType('resource')` üzrə **≥400 statuslu sorğu 0** (133 resurs).
Konsol tarixçəsindəki 3 yazı: giriş səhifəsinin favicon 404-ü və CSRF diaqnostikası
üçün ƏLLƏ göndərdiyim 2 sınaq POST-u (düzəlişdən əvvəl) — bölmə sorğularından deyil.

**Təmizlik:** `QA-DS1*` obyektləri (1 OrgUnit, 1 Program, 1 Subject) klondan silindi;
audit yazıları sübut kimi saxlanıldı.

---

## 7. i18n — yeni msgid-lər (kataloqları BAŞQA agent doldurur)

`.po` fayllarına TOXUNULMADI. Yeni mətnlər `pgettext` / `{% trans … context %}` ilədir.
**185 msgid, 8 kontekst.** Tam siyahı (kontekst üzrə, kopyalanmağa hazır):
`docs/audits/2026-09-02/DESIGN_STAGE1_MSGIDS.txt`. Kontekstlər və sayları:

| Kontekst | Say |
| --- | --- |
| `accounts.catalog` | 77 |
| `accounts.structure_tree` | 50 |
| `accounts.chair_profile` | 37 |
| `profile.sidebar` | 5 (Tədris şöbəsi, Universitet strukturu, Kafedra profili, İxtisaslar, Fənn kataloqu) |
| `ui.status` | 5 (Aktiv, Plan yoxdur, Ad dublikatı, Planda istifadə olunmur, Arxivdə) |
| `organizations.permission.label` | 4 |
| `registrar.subject_kind` | 4 (İxtisas fənni, Ümumi fənn, Seçmə fənn, Təcrübə) |
| `registrar.education_form` | 3 (Əyani, Qiyabi, Distant) |

`scripts/check_i18n_catalogs.py` hazırda QIRMIZIDIR (`django/az/source_missing` 85);
baseline 125 idi — yəni ümumi rəqəm AZALIB, qalan hissə paylaşılan sayğacdır.

---

## 8. Təxirə salınanlar / sahib qərarı gözləyənlər

1. **Fənn birləşdirmə (`merge`)** — ekran 04-də QƏSDƏN yoxdur. Destruktivdir: plan
   sətirləri və sillabuslar yeni koda köçürülməli, köhnə kod `merged_into` ilə
   arxivlənməlidir. UI dublikatları xəbərdarlıq kimi göstərir.
2. **Prerekvizit** — model YOXDUR (`SubjectPrerequisite`), ona görə sütun da yoxdur.
   Tədris planı ilə birlikdə (Mərhələ 2) gəlir.
3. **Saat bölgüsü (mühazirə/seminar/laboratoriya)** — fənnin özündə DEYİL, plan
   sətrindədir (kredit ixtisasa görə dəyişir). Mərhələ 2.
4. **`normSet` seçicisi (Nazirlik ↔ Universitet normaları)** — ekran 02-də göstərilmir:
   dəyərlər verilməyib. Hazırda norma per-müəllim policy sətrindən oxunur
   (`TeacherWorkloadProfile`), fallback NK №215 = 500 saat. Ayrı `WorkloadNormSet`
   modeli SAHİB QƏRARI olmadan yaradılmadı.
5. **«Plan yoxdur» meyarı** — Mərhələ 1-də AKTİV `Curriculum`-un yoxluğu. Təsdiq
   zənciri (`Curriculum.status`) Mərhələ 2-də gələndə meyar «APPROVED plan yoxdur»a keçir.
6. **`teaching_office_staff` və arxivləmə** — əməkdaşda `unit.tree_manage` var, yəni
   arxivləyə bilir. Sahib «arxivləmə yalnız rəhbərdə olsun» desə, açar
   `TEACHING_OFFICE_ROLES`-dan çıxarılır (kod dəyişikliyi lazım deyil).
7. **`student_services` rolu** — planın §3-ündədir, amma Mərhələ 3 (ekran 08/09) ilə
   gəlir; bu mərhələdə yaradılmadı.

---

## 9. Dəyişən / yaranan fayllar

**Yeni:**
`apps/accounts/templates/accounts/profile/_section_assets.html` ·
`…/_section_dispatch.html` · `…/sections/_org_structure_tree.html` ·
`…/sections/_chair_profile.html` · `…/sections/_programs_registry.html` ·
`…/sections/_subject_catalog.html` · `…/sections/teaching_office/{_unit_fields,
_rename_fields,_head_field,_program_fields,_subject_fields,_program_actions,
_subject_actions}.html` · `…/sidebar/_teaching_office_group.html` ·
`apps/accounts/static/accounts/css/profile/sections/teaching_office.css` ·
`apps/accounts/static/accounts/js/profile/teaching_office.js` ·
`apps/accounts/views/_helpers/rbac_university_sections.py` ·
`apps/accounts/views/profile/_sections/{teaching_office,catalog_sections}.py` ·
`apps/accounts/views/profile/context_builder/_teaching_office.py` ·
`apps/accounts/tests/test_teaching_office_sections.py` ·
`apps/organizations/default_roles_teaching_office.py` ·
`apps/organizations/structure_actions.py` ·
`apps/organizations/structure_views/tree.py` ·
`apps/organizations/migrations/0038_seed_teaching_office_roles.py` ·
`apps/registrar/{catalog_registry,catalog_actions}.py` ·
`apps/registrar/models/catalog_meta.py` ·
`apps/registrar/migrations/0064_catalog_archive_and_metadata.py` ·
`templates/partials/ems_ui/_form_dialog.html`

**Dəyişən:**
`apps/accounts/templates/accounts/profile.html` · `…/profile/_sidebar.html` ·
`apps/accounts/views/_helpers/{rbac,rbac_sections}.py` ·
`apps/accounts/views/profile/sections_api.py` · `…/_sections/labels.py` ·
`…/context_builder/{_stage2,_stage3,_stage4}.py` ·
`apps/accounts/tests/test_syllabus_editor_render.py` ·
`apps/organizations/{permissions,urls,default_roles_university}.py` ·
`apps/organizations/structure_views/__init__.py` ·
`apps/registrar/{urls}.py` · `apps/registrar/models/academic.py` ·
`apps/workload/public.py` · `core/roles.py` · `core/ui/status_catalog.py` ·
`static/js/ems_ui/{filter_bar,overlay}.js` · `static/css/ems_ui/{header,kpi}.css` ·
`templates/partials/ems_ui/{_assets,_reason_dialog}.html`
