# Dizayn Mərhələ 2 — Tədris şöbəsi (ekran 05–07)

**Tarix:** 2026-09-03 · **Budaq:** `audit/post-migration-qa-2026-09` (commit YOX — sahibin tələbi)
**Mənbə:** `docs/design/HANDOFF_FULL_PLAN.md` §2 (05/06/07) + `docs/design/handoff_full/README.md` §5, §6.1, §8
**Əhatə:** 05 Tədris planı redaktoru · 06 Qruplar · 07 Semestr açılışı
**Əvvəlki mərhələ:** `DESIGN_STAGE1.md` (qabıq bölgüsü, `ems_ui`, TŞ rolları) — hamısı təkrar istifadə olundu

---

## 0. Bölmə açarları və qabıq

Üçü də **kabinet bölməsidir** (`/accounts/profile/?section=…`): sol sidebar qalır,
panel sağda açılır, `<h1>` bölmə şablonunda YAZILMIR (qabıq verir — canlıda ölçüldü,
hər üç ekranda `h1` sayı = **1**).

| # | Bölmə açarı | Sidebar etiketi | Qapı (görünürlük) |
| --- | --- | --- | --- |
| 05 | `curriculum-editor` | Tədris planı | `plan.view` |
| 06 | `groups-registry` | Qruplar | `unit.view` |
| 07 | `semester-opening` | Semestr açılışı | `semester.view` |

Hamısı Mərhələ 1-in **«TƏDRİS ŞÖBƏSİ» sidebar qrupuna** əlavə olundu
(`accounts/profile/sidebar/_teaching_office_group.html`) və `AJAX_SAFE_SECTIONS`-dədir
(panellər OXU-ONLY render olunur; bütün mutasiyalar ayrıca JSON POST-a gedir).

> ⚠️ **Bölmə açarı plandan fərqlidir.** `HANDOFF_FULL_PLAN.md` §2-də açarlar
> `academic-groups` / `semester-open` kimi yazılmışdı; tapşırıqda isə
> `groups-registry` / `semester-opening` verildi və **tapşırıqdakı adlar götürüldü**
> (reyestr adları Mərhələ 1-in `programs-registry` naxışı ilə uzlaşır).

---

## 1. İcazələr — YENİ AÇARLAR və səlahiyyət ayrılığı

### 1.1 Kataloq

`apps/organizations/permissions_stage2.py` (**yeni modul**) — `permissions.py`
556/600 sətir idi, üç kateqoriya birbaşa ora yazılsaydı modul ölçü qapısı qırmızıya
düşərdi. Kataloq yenə **TƏK dəstdir**: `permissions.py` sonunda `merge_stage2(...)`
onu yerində genişləndirir, ona görə `test_permissions.py`-ın «kataloq ↔ etiket tam
üst-üstə» yoxlaması pozulmur.

| Kateqoriya | Açarlar |
| --- | --- |
| `structure` (mövcud) | **+ `unit.group_manage`** |
| `plan` (**yeni**) | `plan.view`, `plan.edit`, `plan.submit`, `plan.approve_chair`, `plan.approve_council`, `plan.approve_office` |
| `semester` (**yeni**) | `semester.view`, `semester.open`, `semester.lock`, `semester.unlock` |

⚠️ **`structure.*` prefiksi LEGACY-dir** (Mərhələ 1-də sənədləşdirilib) — akademik
qrup açarı ona görə `unit.group_manage`-dir. `group.*` ailəsi isə **BAŞQA anlayışdır**
(`exams.StudentGroup` — imtahan kohortu) və toxunulmadı.

### 1.2 Paylanma (`apps/organizations/default_roles_stage2.py`)

| Rol | plan.view | plan.edit/submit | approve_chair | approve_council | approve_office | semester.view | semester.open | lock | unlock | unit.group_manage |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `rector` | `*` | `*` | `*` | `*` | `*` | `*` | `*` | `*` | `*` | `*` |
| `vice_rector` | ✔ | ✔ | — | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `ikt_rehber` (RİM) | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `teaching_office_head` | ✔ | ✔ | — | — | ✔ | ✔ | ✔ | ✔ | ✔ | ✔ |
| `teaching_office_staff` | ✔ | ✔ | — | — | — | ✔ | ✔ | — | — | ✔ |
| `chair_head` | ✔ | ✔ | ✔ | — | — | ✔ | — | — | — | — |
| `dean` | ✔ | — | — | ✔ | — | ✔ | — | — | — | — |
| `program_coordinator` | ✔ | — | — | — | — | ✔ | — | — | — | ✔ |
| `teacher` / `student` | — | — | — | — | — | — | — | — | — | — |

**Səlahiyyət ayrılığı testlə kilidlənib** (`test_separation_of_duties_in_the_default_grants`):
heç bir akademik rol zəncirin üç halqasını birdən daşımır — yəni bir nəfər planı
təkbaşına başdan-sona keçirə bilmir. Operator rollarında (RİM/rektor) bu qəsdən açıqdır.

Xəritə **AYRI moduldadır** — Mərhələ 1-in `default_roles_teaching_office.py`-ına
əlavə edilsəydi, migration `0038`-in geri dönüşü Mərhələ 2 açarlarını da səssizcə
silərdi.

---

## 2. Model dəyişiklikləri

### 2.1 `apps/registrar/migrations/0065_curriculum_plan_chain.py`

Yeni CƏDVƏL yoxdur → əlavə RLS policy tələb olunmur.

| Model | Yeni sahə | Niyə |
| --- | --- | --- |
| `Curriculum` | `status` (`plan` ailəsi), `version`, `previous_version` (self-FK) | təsdiq zənciri + versiyalama (§6.1, §8/1) |
| `Curriculum` | `submitted_at/by`, `approved_at/by`, `protocol_number`, `last_reason` | Elmi Şura rekvizitləri + qaytarma səbəbi |
| `CurriculumSubject` | `row_code`, `credits`, `total_hours`, `lecture/seminar/lab/selfwork_hours` | saat bölgüsü (TEDRIS_PLANI_SPEC §5.1) |
| `CurriculumSubject` | `assessment_form`, `language`, `teaching_chair` (string-ref OrgUnit) | qiymətləndirmə forması, sektor, xidməti tədris marşrutu |

**Unikallıq dəyişdi:** `uniq_curriculum_program_year` → `uniq_curriculum_program_year_version`.
Səbəb: təsdiqlənmiş plan SİLİNMİR, yeni versiya onun **yanında** yaşayır.

**BACKFILL (miqrasiyanın içində, `RunPython`):**
* mövcud AKTİV planlar `approved` işarələnir — yoxsa `status` default-u (`draft`)
  səbəbindən bir gecədə **hər ixtisas «Plan yoxdur»** olar və semestr açılışı bütün
  universitet üçün bloklanardı. Klonda **211 plan** `approved`-a keçdi;
* sətir kreditləri `Subject.ects`-dən, ümumi saat `kredit × 30` ilə doldurulur;
* saat BÖLGÜSÜ (mühazirə/seminar/lab) **uydurulmur** — köhnə datada yoxdur, 0 qalır
  və redaktor sətri «saat bölgüsü uyğun deyil» kimi işarələyir.

### 2.2 `apps/organizations/migrations/0040_semester_lock_fields.py`

`AcademicPeriod` + `opening_status`, `locked_at`, `locked_by`, `lock_reason`.
Sahələr **abstrakt mixin**-dədir (`apps/organizations/semester_meta.py::SemesterLockMixin`),
çünki `organizations/models.py` 597/600 sətir idi — mixin fayla YALNIZ 1 sətir əlavə etdi.

### 2.3 `apps/organizations/migrations/0041_seed_stage2_permissions.py`

`STAGE2_ROLE_GRANTS` xəritəsindən əkilir (seed ↔ migration sürüşə bilmir), idempotent,
geri dönüş yalnız BU migrasiyanın açarlarını çıxarır.

### 2.4 Modul bölgüsü (davranış dəyişmədən)

`apps/registrar/models/academic.py` 633/600-ə qalxmışdı → `Curriculum` +
`CurriculumSubject` **yeni `models/curriculum.py`** modulunun içinə köçdü.
Sxem, `app_label`, cədvəl adları və migrasiyalar TOXUNULMADI; `models/__init__.py`
onları əvvəlki kimi re-eksport edir. `StudentAcademicRecord.curriculum` string-ref-ə
(`"registrar.Curriculum"`) keçdi ki, dövr yaranmasın.

---

## 3. Ekranlar

### 05 · `curriculum-editor` «Tədris planı»

* **Oxu:** `apps/registrar/curriculum_registry.py` — plan seçicisi, semestr tabları,
  sətir cədvəli (11 sütun), semestr üzrə balans, **əvvəlki versiya ilə diff**,
  audit timeline (ayrıca cədvəl SAXLANMIR — `core.audit` oxunur).
* **State maşını:** `apps/registrar/curriculum_state.py` — SAF modul, Django modelini
  import etmir (`apps/syllabus/state_machine.py` naxışı):

```
qaralama ──göndər──> kafedra baxışı ──> fakültə şurası ──> tədris şöbəsi ──> TƏSDİQLƏNİB
     ▲                     └──────── qaytar (səbəb ≥20) ────────> QAYTARILIB ──yenidən işlə──┘
```

* **Qaytarma HƏMİŞƏ cari mərhələnin öz açarını tələb edir** (`RETURN_PERMISSION_BY_STATUS`)
  — kafedra müdiri şuranın qərarını geri qaytara bilməz.
* **Saat düsturu** (TEDRIS_PLANI_SPEC §3): `ümumi = kredit × 30` · `auditoriya = ümumi − sərbəst`
  · `auditoriya = mühazirə + seminar + lab` · `həftəlik = auditoriya ÷ 15`.
  Boş buraxılan «ümumi saat» və «sərbəst iş» SERVERDƏ düsturla doldurulur.
* **Bloklayıcı:** sətir saat uyğunsuzluğu **və ya** semestr kreditinin 30-dan
  fərqlənməsi «açıq xəbərdarlıq» sayılır → «Təsdiqə göndər» düyməsi **disabled**
  (gizlədilmir) və server `400 blocking_warnings` verir.
* **IMMUTABLE (§8/1):** təsdiqlənmiş planda sətir yazısı/silinməsi və status keçidi
  **409 `plan_immutable`**; «Əməllər» sütunu ümumiyyətlə render OLUNMUR.
  Dəyişiklik yalnız **«Yeni versiya»** — sətirlər klonlanır, köhnə plan toxunulmur.
* **Düymələr GİZLƏNMİR, `disabled` olur** (§4): aktorda mərhələnin açarı yoxdursa
  düymə görünür, amma sönükdür (`title`-da səbəb) — server yenə fail-closed 403 verir.
* **Bildiriş:** status dəyişəndə ixtisasın struktur zəncirindəki bölmə rəhbərlərinə
  (ixtisas → kafedra → fakültə) in-app bildiriş gedir; bildiriş modulu əlçatmazdırsa
  keçid POZULMUR.
* **Yazı:** `apps/registrar/curriculum_actions.py` → `registrar:curriculum_action`.

### 06 · `groups-registry` «Qruplar»

* **Oxu:** `apps/organizations/groups_registry.py`; **yazı:** `group_actions.py`
  → `organizations:group_action`.
* ⚠️ **Mövcud `groups` bölməsi TOXUNULMADI** — o, `exams.StudentGroup` (imtahan
  kohortu) üçündür. İki səth qəsdən yan-yanadır və başlıqda **çarpaz keçid** var
  («Dərs cədvəli» → `schedule-manage`, «İmtahan kohortları» → `groups`).
* Qrup = `OrgUnit(unit_type="group")`; metadata (`dil sektoru`, `kurs`, `qəbul ili`,
  `tədris planı`, `yer sayı`) **`OrgUnit.settings` JSON-undadır** — yeni cədvəl
  YARADILMIR, çünki akademik struktur tenantdan-tenanta dəyişir (layihə qərarı:
  sektor hardcode edilmir; süzgəcdəki siyahı mövcud datadan yığılır).
* **Əhatə (§8/8):** `get_permission_scope(user, org, "unit.view")` — kafedra müdiri
  yalnız öz alt-ağacının qruplarını görür, əhatəsiz aktor BOŞ siyahı alır.
* **Vəziyyət sütunu** qrupun metadatasından DEYİL, **ixtisasın təsdiqlənmiş planından**
  hesablanır (ekran 03/07 ilə eyni meyar) — köçürülmüş qruplarda `curriculum_id` boşdur
  və o, plan yoxluğu demək deyil. (Canlı QA-da tapıldı və düzəldildi.)
* **Toplu «kursa keçir»:** seçim xanaları sətir əməlləri xanasındadır (ortaq
  `_data_table.html`-ə sütun əlavə edilmədi); səbəb ≥20 simvol; **hər qrup üçün
  AYRICA audit yazısı** (köhnə kurs → yeni kurs); son kursdakı qruplar toxunulmur —
  məzunluq ayrı əməldir.
* **Silmə yoxdur:** arxiv = `is_active=False`; **tələbəsi olan qrup arxivlənmir**.

### 07 · `semester-opening` «Semestr açılışı»

* **Oxu + törətmə:** `apps/registrar/semester_open.py`; **yazı:** `semester_actions.py`
  → `registrar:semester_action`.
* **Açılış törətməsi İDEMPOTENTDİR:** `get_or_create` (org+subject+period+group);
  `defaults`-da `instructor` **YOXDUR** → mövcud açılışın müəllimi heç vaxt
  sıfırlanmır. Heç nə silinmir; yalnız çatışmayan sətirlər yaranır.
* **«Plan yoxdur» = bloklayıcı (§6.1):** təsdiqlənmiş planı olmayan ixtisas üçün
  açılış yaradılmır və adı istifadəçiyə lentdə göstərilir.
* **5 addımlı stepper:** yalnız «göndərildi» və «kilidləndi» SAXLANILIR
  (`AcademicPeriod.opening_status`); qalan üç addım açılış sətirlərindən hesablanır.
* **Kilid qapıları (üçü də mətnlə göstərilir):** «plan təsdiqlənib» · «bütün açılışlara
  müəllim təyin olunub» · «jurnallar açılıb». Ödənməsə düymə **disabled**;
  server də `409 missing_instructors` / `no_offerings` verir.
* **Kilid geri qaytarılmır:** açmaq üçün AYRI `semester.unlock` + ≥20 simvol səbəb + audit.
* **«Cari dövr» açarı** ayrıca təsdiq dialoqundan keçir və audit-ə köhnə/yeni dövrlə
  yazılır — `AcademicPeriod.save()` köhnə cari dövrü avtomatik söndürür, yəni bir klik
  bütün universitetin jurnal/açılış konteksini dəyişir.
* **Açılış SİLİNMİR** — «Ləğv et» `is_active=False` (səbəb ≥20 + audit).
* **Coverage KPI-ları** saxlanılmır, hər sorğuda hesablanır (§8/13): açılış · müəllimsiz
  · jurnalsız · **sillabussuz** (§8/12; sillabus modeli əlçatmazdırsa xana «—»
  göstərir, uydurma 0 YAZILMIR) · semestr saatı.

---

## 4. Komponent kitabxanasına əlavələr (Mərhələ 0 qatı)

| Fayl | Dəyişiklik | Səbəb |
| --- | --- | --- |
| `core/ui/status_catalog.py` | `plan` ailəsinə **`returned`**, `offering` ailəsinə **`cancelled`** | §6.1 «+ returned with reason»; açılış silinmir, ləğv olunur |
| `static/…/js/profile/teaching_office.js` | **`data-tof-submit` + `data-tof-confirm`** — dialoqsuz JSON POST (təsdiqlə) | «Cari dövr et», «Kafedraya göndər», «Kilidlə», «Yeni versiya» üçün dialoq lazım deyil |
| `…/teaching_office.js` | ÇOXLU seçim (`select[multiple]`) və təkrarlanan sahə adı → **massiv** (server `getlist`) | semestr açılışında ixtisas seçimi + toplu `ids` |
| `…/teaching_office.js` | CSRF fallback: forma yoxdursa səhifədəki İSTƏNİLƏN `{% csrf_token %}` sahəsi | dialoqsuz POST-un tokeni |
| `…/js/profile/teaching_office_bulk.js` | **YENİ** — sətir seçimi, sayğac, toplu düymənin `disabled` vəziyyəti | ekran 06 |
| `…/css/profile/sections/teaching_office_plan.css` | **YENİ** — yalnız düzüm (plan meta, diff, kilid şərtləri, toplu seçim) | komponentlər təkrar tərif olunmur |

**Inline CSS/JS = 0** (CLAUDE.md). Bütün dinamik dəyər `data-*` atributları ilə ötürülür;
toplu əməlin mətnləri də şablondan `data-tof-bulk-empty` / `data-tof-bulk-selected`
ilə gəlir (xarici `.js` Django template engine-dən keçmir).

---

## 5. Testlər

`apps/accounts/tests/test_teaching_office_stage2.py` — **39 test, hamısı keçir**:

* fraqment **200**: `teaching_office_head` (3 bölmə) · fraqment **403**: müəllim, tələbə
  (3 bölmə × 2 rol) · menyuda sızma yoxdur;
* `chair_head` «Tədris planı»nı görür, «Semestr açılışı»nı GÖRMÜR; qrup reyestrində
  yalnız öz alt-ağacını görür;
* zəncir başdan-sona (`draft → … → approved` + protokol nömrəsi);
* **səlahiyyət ayrılığı:** kafedra müdiri `approve_council`-da **403**;
* **qeyri-qanuni keçid 409** (`illegal_transition`);
* **qaytarma** səbəbsiz 400 (`reason_too_short`), səbəblə 200 + `AuditLog`;
* **IMMUTABLE:** təsdiqlənmiş planda sətir yazısı/silmə/status keçidi **409
  `plan_immutable`**; sətir əməlləri render OLUNMUR;
* **yeni versiya** sətirləri klonlayır, köhnə planı toxunmur;
* **saat balansı** göndərişi bloklayır (həm `total_mismatch`, həm semestr krediti);
  düzəldiləndən sonra keçir; `row_hour_errors` saf funksiyası ayrıca;
* sətir yazısında `total_hours` və `selfwork_hours` düsturla dolur;
* **düymə `disabled`** yanlış təsdiqçidə (`can_advance` / `can_return`);
* qrup yaratma/redaktə, arxiv (səbəb + sətir qalır + audit), **toplu promote**
  (kurs +1 + audit), səbəbsiz promote 400, müəllimə 403, server filtr/səhifələmə;
* **qrup vəziyyəti** metadatadan deyil, təsdiqlənmiş plandan gəlir;
* açılış törətməsi **idempotent** (created 2 → 0/existing 2), **müəllimi sıfırlamır**,
  qaralama plan mənbə DEYİL, «Plan yoxdur» bloklayıcıdır;
* kilid müəllimsiz açılışda **409**, kilid → açma səbəbsiz 400 → səbəblə 200 + audit;
* kilidlənmiş semestrdə törətmə **409**;
* «cari dövr» açarı audit-ə yazılır, köhnə cari söndürülür;
* açılışın ləğvi **soft** (sətir qalır) + səbəb;
* icazə kataloqunun bütövlüyü, legacy prefiksin olmaması, səlahiyyət ayrılığı,
  universitet rol seed-inin yeni açarları daşıması.

**Reqressiya** (eyni özəl bazada):
`test_teaching_office_sections` (29) · `test_sidebar_role_matrix` (13) ·
`organizations/test_permissions` (15) · `registrar/tests` (schedule daxil) ·
`test_section_registry_consistency` (4) → **1 484 + 111 keçdi, 0 uğursuz**.
`apps/accounts/tests` + `apps/organizations/tests` + `apps/workload/tests` →
**1 651 keçdi, 1 skip, 1 uğursuz**.

> ⚠️ **Həmin 1 uğursuzluq MƏNİM DEYİL:**
> `test_account_archive_postgres.py::test_archiving_opens_the_registrar_guard_without_opening_the_login`
> — `registrar_studentacademicrecord.admission_exam_type` NOT NULL sütunu
> (Mərhələ 3 agentinin `0066_student_movement_and_admission_fields` miqrasiyası) və
> həmin testdəki XAM SQL INSERT sütunu vermir. Mərhələ 3 agentinə aiddir.

**Qapılar (dəyişən fayllarda):** `black` ✅ · `isort` ✅ · `flake8` ✅ ·
`check_module_size --check` ✅ · `module_deps --check` ✅ (yeni dövr yoxdur) ·
`check_worker_atomic_coverage --check` ✅ · `makemigrations --check` ✅ («No changes detected»).

---

## 6. Canlı yoxlama (QA klonu, `http://127.0.0.1:8100`)

Klon miqrasiya olundu (`registrar 0065`, `organizations 0040/0041`). Backfill klonda
**211 planı `approved`** etdi; `plan.approve_*` açarları `chair_head` / `dean` /
`teaching_office_head` / `ikt_rehber` rollarına düşdü (DB-dən yoxlanıldı).

### Tam axın — `QA-DS2` (1280×1500)

1. **`qa.teaching_office_head`** «Tədris planı» → «Yeni plan» dialoqu →
   *Kompüter elmləri · 2026 · QA-DS2 sınaq planı* (status **Qaralama**);
2. sətir #1 (15 kredit / 450 saat / 150-75-75-150) → KPI `AÇIQ XƏBƏRDARLIQ 1`,
   lent: «1-ci semestr: 15 kredit (hədəf 30)», «Kafedra baxışına göndər» **disabled**;
3. sətir #2 (15 kredit) → `CƏMİ KREDİT 30`, `AÇIQ XƏBƏRDARLIQ 0`, düymə **aktiv**;
4. göndərildi → **Kafedra baxışı**. Eyni istifadəçidə «Kafedra adından təsdiqlə»
   **disabled**; əl ilə POST → **403 `forbidden`** (səlahiyyət ayrılığı canlı təsdiq);
5. **`qa.chair_head`** → düymə aktiv → təsdiq → **Fakültə şurası**;
6. **`qa.dean`** → `approve_council` → **Tədris şöbəsi**;
7. **`qa.teaching_office_head`** → `approve_office` + protokol `QA-DS2 № 07 — 03.09.2026`
   → **Təsdiqlənib**; təkrar `submit` → **409 `plan_immutable`**, yeganə düymə «Yeni versiya»;
   audit timeline 6 yazını sıra ilə göstərdi (plan created → row saved ×2 → submit →
   approve_chair → approve_council → approve_office).
8. **Semestr açılışı:** «Yeni dövr» → *QA-DS2 Payız semestri · 2026/2027 · 15.09.2026–25.01.2027*;
   «Plandan açılış yarat» (semestr 1, ixtisas *Kompüter elmləri*) → **24 açılış**
   (2 plan sətri × 12 real qrup), `SEMESTR SAATI 7 200`; təkrar çağırış →
   `created 0 / existing 24` (**idempotentlik canlı təsdiq**).
9. **Qruplar:** `QA-DS2 KE-26A` yaradıldı (kurs 1, sektor AZ) → vəziyyət **Aktiv**
   (ixtisasın təsdiqlənmiş planı var) → toplu «Kursa keçir» (səbəb 67 simvol,
   sayğac `67 / 20`) → **kurs 2**.

### Mövcud data üzərində (cari dövr)

`AÇILIŞ 1 212 · MÜƏLLİMSİZ 0 · JURNALSIZ 1 212 · SİLLABUSSUZ — · SEMESTR SAATI 64 620`;
stepper: 1-ci və 3-cü addım **done**, 2-ci **current**, 4/5 **todo**;
«Plan yoxdur» lenti real ixtisasları adla sadaladı; kilid düyməsi **disabled**.
Qrup reyestri: **766 qrup**, `KURATORSUZ 25`, server filtri (`gr_lang`, `gr_course`),
səhifələmə 25/səhifə.

### 375×900

`document.scrollWidth == clientWidth == 375` (üfüqi sürüşmə **0**), `h1` sayı **1**,
KPI 1 sütun, `tof-split` 1 sütun, cədvəl ÖZ konteynerində sürüşür.

### Konsol / şəbəkə

`performance.getEntriesByType('resource')` üzrə **≥400 statuslu sorğu 0** (141 resurs).
Konsol tarixçəsindəki 403/409/400 yazıları — mənim QƏSDƏN göndərdiyim mənfi test
POST-larıdır (səlahiyyət ayrılığı və immutability sübutu), bölmə sorğularından deyil.

### Canlı QA-da tapılan və düzəldilən 2 defekt

1. **Toplu `ids` boş gedirdi.** Ortaq `teaching_office.js` dialoqu açanda bütün
   `[name]` sahələrini prefill-dən doldurur və siyahıda olmayan sahəni BOŞALDIR —
   yəni açılışda yazılan `ids` silinirdi. Həll: id-lər artıq **`submit` hadisəsinin
   CAPTURE fazasında** əlavə olunur (`data-tof-bulk-target` işarəli form).
2. **Qrupun «Plan yoxdur» bayrağı yanlış idi** — `settings.curriculum_id`-dən
   hesablanırdı və köçürülmüş 766 qrupun HAMISI yanlış bayraq alırdı. Həll: meyar
   ixtisasın TƏSDİQLƏNMİŞ planına keçdi (+ `PLAN YOXDUR` KPI xanası).

**Təmizlik:** `QA-DS2` obyektləri klondan silindi (24 açılış, 1 dövr, 1 plan + 2 sətir,
1 qrup). Köçürülmüş sətirlərə TOXUNULMADI (`registrar_curriculum` 211 approved qalır);
audit yazıları sübut kimi saxlanıldı.

---

## 7. i18n — yeni msgid-lər (kataloqları BAŞQA agent doldurur)

`.po` fayllarına **TOXUNULMADI**. **295 msgid, 9 kontekst.**
Tam siyahı: `docs/audits/2026-09-02/DESIGN_STAGE2_MSGIDS.txt`.

| Kontekst | Say |
| --- | --- |
| `accounts.curriculum` | 102 |
| `accounts.semester` | 101 |
| `accounts.groups` | 61 |
| `organizations.permission.label` | 11 |
| `registrar.plan_status` | 6 |
| `registrar.assessment_form` | 5 |
| `organizations.semester_opening` | 4 |
| `profile.sidebar` | 3 (Tədris planı, Qruplar, Semestr açılışı) |
| `ui.status` | 2 (Qaytarılıb, Ləğv edilib) |

---

## 8. Təxirə salınanlar / sahib qərarı gözləyənlər

1. **Prerekvizit** — model YOXDUR (`CurriculumPrerequisite`), ona görə sütun və
   dialoq da yoxdur. Yeni cədvəl + RLS policy + DAG (dövr) yoxlaması tələb edir.
   Ekran 05-in prototipindəki «Prerekvizit seç» modalı bu mərhələdə **qəsdən** yoxdur.
2. **`CurriculumBlock`** (fənn blokları + blok üzrə kredit payı yoxlaması, NK 117:
   humanitar 15–20%, seçmə 25–30%) — yenə yeni cədvəldir; `is_elective` +
   `elective_group` mövcud mexanizmi saxlanıldı.
3. **«Keçən ildən klonla»** (başqa ixtisasın planından köçürmə) — `new_version`
   MƏNTİQİ hazırdır, amma çarpaz-ixtisas klonlaması UI-da açılmadı: hansı sətirlərin
   köçürüləcəyi (kredit ixtisasa görə dəyişir) sahib qərarı tələb edir.
4. **Tədris qrafiki tabı** (ekran 05-in ikinci tabı — 52 həftəlik təqvim şəbəkəsi) —
   `AcademicPeriod` həftə strukturu saxlamır; akademik təqvim modulu ilə birlikdə gəlməlidir.
5. **Qrup kartının «tələbə tərkibi / cədvəl / jurnal» tabları** (ekran 06-nın sağ paneli)
   — tələbə hərəkəti **Mərhələ 3**-dədir (paralel agent), cədvəl isə mövcud
   `schedule-manage` bölməsindədir; reyestr onlara çarpaz keçid verir, təkrar qurmur.
6. **Müəllim təyinatı ekranı** (ekran 07-nin `assign` modalı) — təyinat **dərs yükü**
   modulundan gəlir (`workload.services.distribution.sync_offerings`, Mərhələ 4);
   burada yalnız «müəllim gözləyir» vəziyyəti və kafedra üzrə əhatə göstərilir.
7. **Jurnal açılışı** addımı — `CourseOffering.course` (LMS kursu) bağlanmasıdır və
   jurnal modulunun öz axınıdır; ekran onu yalnız ÖLÇÜR (KPI + stepper), yaratmır.
8. **`semester.unlock` və `teaching_office_staff`** — əməkdaşda kilid/kilid açma
   QƏSDƏN yoxdur. Sahib «əməkdaş da kilidləsin» desə, açar
   `STAGE2_ROLE_GRANTS`-a əlavə olunur (kod dəyişikliyi lazım deyil).

---

## 9. Dəyişən / yaranan fayllar

**Yeni:**
`apps/registrar/models/curriculum.py` · `…/models/curriculum_meta.py` ·
`apps/registrar/{curriculum_state,curriculum_registry,curriculum_actions}.py` ·
`apps/registrar/{semester_open,semester_actions}.py` ·
`apps/registrar/migrations/0065_curriculum_plan_chain.py` ·
`apps/organizations/{groups_registry,group_actions,permissions_stage2,default_roles_stage2,semester_meta}.py` ·
`apps/organizations/migrations/{0040_semester_lock_fields,0041_seed_stage2_permissions}.py` ·
`apps/accounts/views/profile/_sections/curriculum_sections.py` ·
`apps/accounts/templates/accounts/profile/sections/{_curriculum_editor,_groups_registry,_semester_opening}.html` ·
`…/sections/teaching_office/{_plan_header_actions,_plan_warnings,_plan_row_actions,_plan_fields,_plan_row_fields,_group_header_actions,_group_row_actions,_group_fields,_semester_header_actions,_semester_blockers,_offering_row_actions,_period_fields,_generate_fields}.html` ·
`apps/accounts/static/accounts/css/profile/sections/teaching_office_plan.css` ·
`apps/accounts/static/accounts/js/profile/teaching_office_bulk.js` ·
`apps/accounts/tests/test_teaching_office_stage2.py`

**Dəyişən:**
`apps/registrar/models/{__init__,academic}.py` · `apps/registrar/urls.py` ·
`apps/organizations/{models,permissions,default_roles_university,urls}.py` ·
`apps/accounts/views/_helpers/rbac_sections.py` ·
`apps/accounts/views/profile/{sections_api.py,_sections/labels.py}` ·
`apps/accounts/views/profile/context_builder/{_stage2,_stage4,_teaching_office}.py` ·
`apps/accounts/templates/accounts/profile.html` · `…/profile/{_section_assets,_section_dispatch}.html` ·
`…/profile/sidebar/_teaching_office_group.html` ·
`apps/accounts/static/accounts/js/profile/teaching_office.js` · `core/ui/status_catalog.py`
