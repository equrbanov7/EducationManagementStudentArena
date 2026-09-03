# Dizayn handoff (22 ekran) — implementasiya planı

**Tarix:** 2026-09-03 · **Mənbə:** `docs/design/handoff_full/README.md` (732 sətir) + `_extract.md` + 22 `.dc.html`
**Baza:** `audit/post-migration-qa-2026-09` · **Sübut bazası:** `docs/audits/2026-09-02/` (FINAL_REPORT, ISSUES, PHASE1/4/5/6/11/18/21/22/32) + `docs/workload/DERS_YUKU_SPEC.md` + `TEDRIS_PLANI_SPEC.md`

---

## 0. Ən vacib qərar — QABIQ (shell)

> **Prototiplərin top bar-ı və sidebar-ı TƏKRAR QURULMUR.**

Handoff §3 öz top bar-ını (56px, logo + wordmark + çıxış) və öz sidebar-ını (300px, rola görə dəyişən başlıq, progress kartı) təsvir edir. **Bunların heç biri tətbiq edilmir.** Səbəb:

1. Layihədə artıq işlək kabinet qabığı var: `apps/accounts/templates/accounts/profile.html` + `accounts/profile/_sidebar.html` (+ `sidebar/_home_menu_item.html`, `sidebar/_org_menu_group.html`, `_sidebar_university.html`, `_sidebar_exam_center.html`). 76 bölmə, 9 rol, `allowed_sections` qapısı, AJAX swap, badge sayğacları, «view as», dil dəyişdirici — hamısı ona bağlıdır.
2. Sahibin tələbi: **sol sidebar HƏMİŞƏ görünür**, panel sağda açılır (`docs/audits/2026-09-02/PHASE18_APPLICATIONS_UI.md` — Müraciətlər məhz belə qurulub).
3. İkinci sidebar = ikinci naviqasiya modeli = rol matrisinin ikiləşməsi.

**Qərar:**

| Handoff deyir | Biz nə edirik |
| --- | --- |
| Öz top bar | Mövcud navbar (`templates/partials/_navbar.html`) qalır |
| 300px öz sidebar-ı | Mövcud `profile-sidebar` qalır; hər ekran ona bir **bölmə açarı** kimi düşür |
| Ekran = ayrıca səhifə | Ekran = **kabinet bölməsi** (`/accounts/profile/?section=<key>`) |
| Content header (breadcrumb + h1 + alt sətir + əməllər) | **Panelin İÇİNDƏ** render olunur — `templates/partials/ems_ui/_content_header.html` |
| Content header-in `<h1>`-i | **Yazılmır** — qabıq `#profileSectionTitle` kimi artıq verir (əks halda səhifədə iki `h1` olur; Mərhələ 0-da ölçülüb və düzəldilib) |
| Sidebar-dakı progress kartı | Ekranın öz KPI sırasına köçür (panelin içi) |
| Rola görə dəyişən sidebar başlığı | Mövcud rol etiketi + `allowed_sections` bunu onsuz da edir |

Prototiplərin **layout-u, ölçüləri, rəngləri, copy-si və state maşınları** isə hərfi götürülür — dəyişən yalnız qabıqdır.

---

## 1. Ümumi mənzərə — 22 ekranın mövcudluq xəritəsi

| # | Ekran | Mövcud vəziyyət | Qərar |
| --- | --- | --- | --- |
| 01 | Universitetin strukturu | Qismən (`org-structure`/`org-faculties`/`org-kafedras` — **düz siyahı, ağac yox**; yalnız fakültə+kafedra yaradıla bilir) | **Genişlət** |
| 02 | Kafedra profili | Qismən (`unit_detail` kartı var; **ştat/norma UI-ı yoxdur**) | **Genişlət** |
| 03 | İxtisaslar | Qismən (registrar konsolu `/jurnal/idareetme/`, bölmə açarı YOX) | **Yenidən stilləşdir + bölməyə köçür** |
| 04 | Fənn kataloqu | Qismən (`SubjectForm` yalnız kod/ad/ECTS; **saat sahələri yoxdur**) | **Genişlət (model daxil)** |
| 05 | Tədris planı redaktoru | Qismən (CRUD var, **təsdiq zənciri yoxdur**) | **Genişlət (model daxil)** |
| 06 | Qruplar | Qarışıq: cədvəl **TAM** (`my-schedule`/`schedule-manage`), akademik qrup reyestri **yoxdur**, `groups` bölməsi başqa şeydir (imtahan kohortu) | **Yeni (qrup reyestri) + cədvəli təkrar istifadə** |
| 07 | Semestr açılışı | Qismən (`sync_offerings` yükdən işləyir, **plandan toplu açılış və 5 addımlı kilid yoxdur**) | **Yeni** |
| 08 | Tələbə qəbulu (ATİS) | **TAM** (`student-intake`, 16 sütunlu müqavilə, dry-run + apply, 26 test) | **Təkrar istifadə + restyle** |
| 09 | Tələbə reyestri və hərəkəti | Qismən (reyestr TAM; 6 hərəkətdən **2-si** var, `StudentMovement` reyestri yoxdur) | **Genişlət (model daxil)** |
| 10 | Tələbə kabineti | Demək olar TAM (`dashboard`, `my-subjects`, `my-schedule`, `my-journal`, `my-results`, `my-transcript`, `applications`); **sillabus oxunuşu bölmə kimi yoxdur** | **Təkrar istifadə + 1 bölmə əlavə** |
| 11 | Müraciətlər paneli | **TAM** (`apps/applications`, 15 növ, 9 vahid, SLA, 152+9 test) | **Təkrar istifadə + restyle** |
| 12 | Dərs yükü — Tədris şöbəsi | **YOX** (F1 planlaşdırılıb, model hazırdır) | **Yeni** |
| 13 | Koordinator — yük vizası | **YOX** (F2; `TaskRowReview` qəsdən yaradılmayıb) | **Yeni (model daxil)** |
| 14 | Kafedra müdiri — yük bölgüsü | **TAM** (F3, `workload-distribution`) | **Təkrar istifadə + restyle** |
| 15 | Dekanlıq — yük təsdiqi | **YOX** (F2; `TaskFacultySlice` yoxdur) | **Yeni (model daxil)** |
| 16 | Müəllim — şəxsi yük | **TAM** (F4, `my-workload`) + **fərdi iş planı YOX** | **Genişlət** |
| 17 | Rektor — ümumi baxış | **YOX** (F5) | **Yeni (yalnız aqreqasiya)** |
| 18 | Müəllim — sillabuslar | **TAM** (`syllabus-list`) | **Restyle (ems_ui-a köçür)** |
| 19 | Sillabus redaktoru | **TAM** (`syllabus-editor`, 10 bölmə, autosave, revision lock) | **Restyle + `saveState` 6 vəziyyəti** |
| 20 | Kafedra müdiri — sillabus təsdiqi | **TAM** (`syllabus-review`; sahib qərarı 2026-09-03: təsdiqçi `chair_head`) | **Restyle + diff/audit paneli** |
| 21 | Müəllim — keçilmiş dərslər | **YOX** (jurnal offering-ə bağlıdır, çarpaz siyahı yoxdur) | **Yeni (oxu-only)** |

**Yekun:** 6 ekran tam təkrar istifadə · 7 ekran genişləndirmə · 9 ekran yeni · **model dəyişikliyi tələb edən: 6** (04, 05, 09, 13, 15, 16).

---

## 2. Ekran-ekran plan

Hər bənd: **mövcud → boşluq → qərar → fayllar → rol/icazə → data modeli.**

### 01 · Universitetin strukturu — `org-structure` (genişlət)

* **Mövcud:** `apps/organizations/structure_views/` (`context.py`, `endpoints.py`, `unit_detail.py`, `_shared.py`), `templates/organizations/partials/_structure_content.html` · `_faculties_content.html` · `_kafedras_content.html` · `_unit_detail.html`; model `apps/organizations/models.py::OrgUnit` (self-FK `parent`, materialized `path`, `unit_type`, `head`).
* **Boşluq:** ağac UI yoxdur (iki düz səhifələnmiş kart siyahısı); `apps/organizations/views/org_admin/context.py:121` yaratmanı `{faculty, kafedra}` ilə məhdudlaşdırır — dekanlıq/ixtisas/qrup/mərkəz/laboratoriya yalnız admin/seed-dən yaranır; «Rəhbəri olmayan bölmə» bayrağı yoxdur.
* **Qərar:** genişlət — `_structure_content.html` daxilində `ems_ui/_tree.html`; `unit_kind` ağ siyahısını `core/constants.py::OrgUnitType` + `apps/organizations/unit_types.py::UNIT_TYPES_BY_ORG` üzərindən aç.
* **Fayllar:** `apps/organizations/structure_views/context.py` (ağac qurucu, ≤600), yeni `structure_views/tree.py`, `templates/organizations/partials/_structure_content.html`, `apps/organizations/views/org_admin/context.py`.
* **Rol/icazə:** `unit.view` / `unit.edit` (mövcud). `teaching_office_head` + `teaching_office_staff` **yeni** — `unit.view` + `unit.edit`.
* **Data:** model dəyişikliyi **YOX**. Silmə yoxdur → `OrgUnit.is_active=False` (arxiv) + səbəb `AuditLog`-a.

### 02 · Kafedra profili — `org-kafedras` (genişlət)

* **Mövcud:** `structure_views/unit_detail.py::build_unit_detail_context` (heyət, qrup/tələbə sayı, offering bölgüsü); `apps/workload/models/assignment.py::TeacherWorkloadProfile` (`position`, `staff_fraction`, `annual_norm_hours=500`, `is_external`) — **CRUD ekranı yoxdur**, yalnız `services/queries.py::_norm_for` oxuyur.
* **Boşluq:** ştat / əvəzçilik / saathesabı reyestri, «Ştat vahidi cəmi», 4 yük statusu (`boş tutum / normada / yüklü / risk`), `normSet` (Nazirlik ↔ Universitet normaları) seçicisi.
* **Qərar:** genişlət. **Norma dəyərləri policy cədvəlindən oxunur** (handoff §10 sonu) — `apps/workload/constants.py`-dakı hardcode `WorkloadSettings` modelinə köçür.
* **Fayllar:** yeni `apps/workload/models/settings.py` (`WorkloadNormSet`, `WorkloadNorm`), `apps/workload/services/norms.py`, `apps/organizations/structure_views/unit_detail.py`, `templates/organizations/partials/_unit_detail.html`.
* **Rol/icazə:** oxu `unit.view`; ştat redaktəsi **yeni** `workload.staff_manage` → `chair_head`, `teaching_office_head`, `hr`, `ikt_rehber`.
* **Data:** `TeacherWorkloadProfile.employment_kind` enum (`stat|evezcilik|saathesabi`) + `WorkloadNormSet` (org-scoped, RLS migration). String-ref FK: `"organizations.OrgUnit"`.
* **Status ailəsi:** `dept_load` (artıq `core/ui/status_catalog.py`-dədir).

### 03 · İxtisaslar — yeni bölmə açarı `programs` (yenidən stilləşdir + köçür)

* **Mövcud:** `apps/registrar/console_views.py::registrar_console` + `program_form_view`, `forms.py::ProgramForm`, model `registrar.Program` (`code`, `official_code`, `degree_level`, `ects_total`, `absence_limit_percent`, `specialty_unit`).
* **Boşluq:** kabinet bölməsi deyil (ayrıca səhifə, sidebar itir); qapı `course.edit` **və** `scope.is_org_wide` → dekan/kafedra müdiri tamamilə 404; «Plan yoxdur» bayrağı yoxdur; arxivləmə səbəbi yoxdur; təhsil forması sahəsi yoxdur.
* **Qərar:** yeni bölmə `programs`, məzmun mövcud servisdən; qapını `program.view` / `program.manage` icazəsinə çevir (rol adı yoxlanmır — `rbac_sections.py` üslubu).
* **Fayllar:** `apps/accounts/views/profile/_sections/programs.py`, `apps/accounts/templates/accounts/profile/sections/_programs.html`, `apps/registrar/services/programs.py`, `sections_api.py`, `rbac_sections.py`, `_sidebar.html` qrupu.
* **Data:** `Program.education_form` (əyani/qiyabi/distant), `Program.is_archived` + `archived_reason` + `archived_by/at` (**silmə YOX**). «Plan yoxdur» = `Curriculum.objects.filter(program=…, status=APPROVED)` boşdur — hesablanır, saxlanılmır.

### 04 · Fənn kataloqu — yeni bölmə `subjects` (genişlət, model daxil)

* **Mövcud:** `registrar.Subject` = `code`, `name`, `ects`, `description`, `is_active`. Vəssalam.
* **Boşluq (TEDRIS_PLANI_SPEC §4.2 boşluq #1/#2):** mühazirə/seminar/laboratoriya saatları, tədris dili, qiymətləndirmə forması, prerekvizit, fənn blokları, «Planlarda istifadə» sütunu, `merge` (dublikat birləşdirmə).
* **Qərar:** genişlət. **Saat bölgüsü fənnin özündə deyil, plan sətrindədir** (kredit ixtisasa görə dəyişir — layihə yaddaşı) → saatlar `CurriculumSubject`-ə (bax 05), `Subject`-də yalnız kataloq sahələri.
* **Fayllar:** `apps/registrar/models/academic.py` (+`SubjectBlock`, `SubjectPrerequisite`), `apps/registrar/forms.py::SubjectForm`, `apps/accounts/views/profile/_sections/subjects.py`, `_subjects.html`, migration + RLS.
* **Rol/icazə:** `subject.view` / `subject.manage`; `merge` üçün ayrıca `subject.merge` → yalnız `teaching_office_head` + `ikt_rehber`.
* **Data:** `merge` **destruktivdir** → köhnə kod `is_archived=True` + `merged_into` FK; plan sətirləri və sillabuslar yeni koda **köçürülür, silinmir**; səbəb (≥20 simvol) + `AuditLog`.

### 05 · Tədris planı redaktoru — yeni bölmə `curriculum-editor` (genişlət, model daxil)

* **Mövcud:** `Curriculum` + `CurriculumSubject` (yalnız `semester_number`, `is_elective`, `elective_group`, `required_choices`, `order`), `console_views.py::curriculum_form_view` / `curriculum_detail`.
* **Boşluq:** kredit/saat sahələri, `CurriculumBlock`, prerekvizit, aparan kafedra, kredit balansı paneli (semestr hədəfi 30 ECTS), təsdiq zənciri + kilid, klonlama, audit paneli.
* **Qərar:** genişlət — `TEDRIS_PLANI_SPEC.md` §5-in T0–T3 fazaları.
* **Fayllar:** `apps/registrar/models/curriculum.py` (yeni modul), `apps/registrar/services/curriculum_balance.py`, `apps/registrar/state_machine_curriculum.py` (**`apps/syllabus/state_machine.py` nümunəsi ilə**), `_sections/curriculum_editor.py`, `_curriculum_editor.html`, migration + RLS.
* **Rol/icazə:** `curriculum.edit` (kafedra), `curriculum.review` (fakültə şurası/dekan), `curriculum.approve` (`teaching_office_head`), `curriculum.lock` (rektor/`ikt_rehber`).
* **Data:** `CurriculumSubject` + `credits`, `total_hours`, `lecture_hours`, `seminar_hours`, `lab_hours`, `selfwork_hours`, `teaching_chair` (`"organizations.OrgUnit"`), `assessment_form`, `language`, `block` FK. `Curriculum` + `status` (`plan` ailəsi), `approved_by/at`, `protocol_number`, `locked_at`.
* **Qəbul qaydası (§8/1):** **təsdiqlənmiş plan immutable** — DB CHECK + servis qapısı; dəyişiklik yalnız yeni versiya.
* **Bloklayıcı:** açıq xəbərdarlıq (semestr ≠ 30 ECTS) varsa təsdiqə göndərmə bağlıdır.

### 06 · Qruplar — yeni bölmə `academic-groups` (yeni) + mövcud cədvəl

* **Mövcud:** həftəlik cədvəl **TAM** — `apps/registrar/schedule.py` (`build_week_grid`, `week_parity`), `schedule_views.py`, `schedule_manage.py`, `ScheduleSlot` (konflikt yoxlaması, audit, bildiriş), bölmələr `my-schedule` / `schedule-manage` (PHASE5). Akademik qrup = `OrgUnit(unit_type=group)` — **reyestr ekranı yoxdur**.
* **⚠ TƏLƏ:** mövcud `groups` bölməsi `apps.exams.models.StudentGroup` (imtahan kohortu) üçündür — **başqa anlayış, toxunma.**
* **Qərar:** yeni `academic-groups` bölməsi; içindəki cədvəl tabı **mövcud `schedule.py` grid-ini təkrar istifadə edir** (yenidən yazılmır).
* **Fayllar:** `_sections/academic_groups.py`, `_academic_groups.html`, `apps/organizations/services/groups.py`.
* **Data:** `OrgUnit.settings` JSON-da qrup metadatası (dil sektoru — layihə yaddaşı: sektor tenant-konfiqurasiya olunandır, hardcode edilmir). Tələbə köçürməsi 09-a keçid verir.

### 07 · Semestr açılışı — yeni bölmə `semester-open` (yeni)

* **Mövcud:** `apps/registrar/services.py::get_or_create_offering` / `enroll_mandatory_subjects` (yalnız seed/testdən çağırılır); `apps/workload/services/distribution.py::sync_offerings` (yükdən açılış yaradır, jurnal açır, bildiriş göndərir); `journal_close.py` (jurnal kilidi, **semestr kilidi deyil**).
* **Boşluq:** təsdiqlənmiş plandan toplu açılış, 5 addımlı stepper, müəllim təyinatı ekranı, semestr kilidi.
* **Qərar:** yeni bölmə; `sync_offerings` servisini **təkrar istifadə et**, üstünə plan mənbəyini əlavə et.
* **Rol/icazə:** `semester.open` + `semester.lock` → `teaching_office_head`, `ikt_rehber`.
* **Data:** `AcademicPeriod` + `opening_status`, `locked_at`, `locked_by`, `lock_reason`. **Kilid geri qaytarılmır** — açmaq üçün `semester.unlock` + səbəb (≥20) + audit.
* **Gate-lər:** «plan təsdiqlənib» · «bütün açılışlara müəllim təyin olunub» · «jurnallar açılıb» — üçü ödənməsə kilid düyməsi `disabled` (gizlədilmir).
* **Status ailələri:** `offering`, `semester_steps` (hazır).

### 08 · Tələbə qəbulu — `student-intake` (təkrar istifadə + restyle)

* **Mövcud: TAM.** `apps/accounts/services/intake/` (`policy`, `spec` — 16 sütun + xlsx şablon, `parsing` — 5 MB/2000 sətir, `validate` — dry-run `RowPlan`, `apply` — sətir-başına savepoint + audit), `views/student_intake.py`, `_student_intake.html`, icazə `user.import` (migration 0034), 26 test.
* **Boşluq:** yalnız UI — 4 addımlı stepper, KPI zolağı, hərfi validasiya mesajları (`intake_row` status ailəsi hazırdır), «bloklayan xəta olan sətir qrupa təyin edilə bilmir» vizualı, dolu qrupda `newG`.
* **Qərar:** **backend-ə toxunma.** `_student_intake.html`-i `ems_ui` komponentlərinə köçür.
* **Qeyd:** ATİS-in öz API/formatı yoxdur — `intake/spec.py`-dakı ümumi cədvəl müqaviləsi ATİS ixracını qəbul edir. Ayrıca konnektor **plana daxil deyil** (sahib qərarı tələb olunur).

### 09 · Tələbə reyestri və hərəkəti — `people-students` (genişlət, model daxil)

* **Mövcud:** reyestr TAM (`services/people/`, `people_list/detail/options` API, drawer). Hərəkət: `academic_actions.py::transfer_group` (→ `registrar/transfer.py`, `Enrollment.superseded_by` ilə nəsil qorunur) + `set_academic_status` (`enrolled|academic_leave|expelled|graduated`).
* **Boşluq:** 6 hərəkət növündən **2-si** var; **`StudentMovement` reyestri yoxdur** — tarixçə yalnız `core.audit`-dədir; əmr nömrəsi sahəsi yoxdur.
* **Qərar:** genişlət — `StudentMovement` ledger modeli (append-only, DB trigger ilə — `WorkloadAmendment` nümunəsi).
* **Fayllar:** `apps/registrar/models/movement.py`, `apps/registrar/services/movement.py`, `apps/accounts/services/people/academic_actions.py`, `_people_students.html`.
* **Rol/icazə:** `people.manage_academic` (mövcud); `student_services` **yeni** rol bunu alır; xaric etmə üçün ayrıca `people.expel` → `dean` + `teaching_office_head`.
* **Data:** `StudentMovement(kind, order_number, order_date, reason, actor, from_*, to_*, created_at)` — `student_movement` status ailəsi hazırdır. **Status dəyişikliyi silinmir — tarixçə yazısıdır** (§8/5, §8/7).

### 10 · Tələbə kabineti — mövcud bölmələr (təkrar istifadə + 1 yeni)

* **Mövcud:** `dashboard` (student vidjetləri), `my-subjects`, `my-schedule`, `my-journal`, `my-results`, `overall-academic`, `my-transcript` (bayraqlı), `applications`, `my-appeals`.
* **Boşluq:** tələbə **sillabusu bölmə kimi görmür** (`syllabus-*` üçü də `syllabus.view/edit/review` tələb edir; `student`-də yoxdur). Yalnız `accounts:syllabus_detail` müstəqil səhifəsi var.
* **Qərar:** yeni oxu-only bölmə `my-syllabus` — **yalnız APPROVED versiya** (§8/9).
* **Fayllar:** `_sections/my_syllabus.py`, `_my_syllabus.html`, `rbac_sections.py`.
* **Açıq qərar (§10.1) — QƏBUL EDİLƏN DEFAULT: `transcriptPolicy = request`.** Transkript kabinetdən birbaşa PDF kimi verilmir; **Müraciətlər** modulundakı «Transkript sorğusu» növü ilə **Tələbə Xidmətləri**-nə gedir (SLA 3 iş günü). Səbəb: möhür/imza siyasəti və QR verifikasiyası hələ yoxdur; `STUDENT_TRANSCRIPT_SELF_SERVICE` bayrağı **söndürülü** qalır. Sahib `download`-a keçmək istəsə — yalnız bayraq dəyişir, yeni UI lazım deyil.

### 11 · Müraciətlər paneli — `applications` (təkrar istifadə + restyle)

* **Mövcud: TAM.** `apps/applications/` (10 status, 15 növ + «Digər», 9 vahid, SLA, append-only `ApplicationEvent`, əlavələr, RLS, 152+9 test). UI: `_applications.html` + `_applications_dialogs.html`, `apx-*` CSS/JS.
* **Boşluq:** yalnız kosmetik — handoff-un 8 növü mövcud 15-in altçoxluğudur; «Təqdimat» növü var (PHASE32 F22).
* **Qərar:** **backend-ə toxunma.** `apx-*` → `ems-*` köçürməsi Mərhələ 6-da.
* **Qalan iş:** `close_stale_resolved` cron-a bağlanmayıb (FINAL_REPORT §13.6).

### 12 · Dərs yükü — Tədris şöbəsi — yeni bölmə `workload-center` (yeni)

* **Mövcud:** modellər hazırdır — `TeachingTask` (`status` artıq `draft/submitted/returned/pending_final_approval/approved`, `revision`, `submitted_by/at`), `TeachingTaskRow` (bütün saat sahələri). İcazə `workload.submit` kataloqda var, **heç bir rolda yoxdur**.
* **Boşluq:** ekran, Excel importu, göndərmə axını, izləmə paneli (DERS_YUKU_SPEC F1).
* **Qərar:** yeni. **Migration TƏLƏB OLUNMUR** (F1 modeli hazırdır) — yalnız icazə seed-i.
* **Rol/icazə:** `teaching_office_head` (85) → `workload.view/manage/submit/report`; `teaching_office_staff` (60) → `workload.view/manage/submit`.
* **Görünüşlər:** `dashboard` · `tasks` · `import` · `reports` (boş vəziyyət) · `settings` (boş vəziyyət) — handoff boş vəziyyətləri **qəsdən saxlayır**.

### 13 · Koordinator — yük vizası — yeni bölmə `workload-visa` (yeni, model daxil)

* **Mövcud:** `TeachingTaskRow.review_status` sahəsi **var, heç kim işlətmir**; `TaskRowReview` modeli qəsdən yaradılmayıb (PHASE4 §2).
* **Qərar:** yeni — `TaskRowReview(row, reviewer, state, remark, created_at)`.
* **Qayda (handoff §5/13):** **irad yazılan sətrin `reviewed` bayrağı silinir** — sətir eyni anda həm vizalanmış, həm iradlı ola bilməz. Servis səviyyəsində atomic.
* **Rol/icazə:** `workload.review` → `program_coordinator` (mövcud rol, yeni icazə).
* **Arxiv rejimi:** keçmiş il → read-only, qeyd `arxiv — yalnız oxunuş` (`archive_mode` status ailəsi hazırdır).
* **Status ailəsi:** `workload_visa` (hazır).

### 14 · Kafedra müdiri — yük bölgüsü — `workload-distribution` (təkrar istifadə + restyle)

* **Mövcud: TAM (F3).** `apps/workload/services/{tasks,assignments,distribution,people,scoping,queries,amendments,curriculum_import}.py`, 14 JSON endpoint, saat balansı həm servisdə həm **DB trigger-də** (`workload_assignment_balance`), vakant = `teacher=NULL`, 71 test.
* **Boşluq:** yalnız UI — müəllim üzrə `teachers` görünüşü, `reports`, norma badge-i (`teacher_norm` ailəsi hazırdır), `noRows` boş vəziyyəti.
* **Qərar:** `workload_base.css` + `workload_dialog.css` → `ems_ui` komponentlərinə köçür.

### 15 · Dekanlıq — yük təsdiqi — yeni bölmə `workload-approval` (yeni, model daxil)

* **Mövcud:** `dean` yalnız `workload.view` + `workload.report`; `workload.approve` **qəsdən heç bir rolda deyil** (`apps/workload/tests/test_permission_catalog.py` bunu kilidləyir — testi də yeniləmək lazımdır).
* **Qərar:** yeni — `TaskFacultySlice(task, faculty, status, submitted_at, decided_by, decided_at, remark)`.
* **Rol/icazə:** `workload.approve` → `dean`. **Açıq qərar §10.2 — DEFAULT: dekanın ikinci təsdiqi AÇIQ** (bu ekran onun özüdür); sillabus üçün isə **SÖNDÜRÜLÜ** (bax 20).
* **Toplu əməllər:** `Qaytar` yalnız ≥1 sətir seçildikdə aktiv; hər ikisi modal + səbəb (≥20).
* **Status ailəsi:** `workload_line` (hazır: Göndərilib/Qaytarılıb/Təsdiqlənib — dəqiq rənglərlə).

### 16 · Müəllim — şəxsi yük — `my-workload` (genişlət)

* **Mövcud: TAM (F4)** — `teacher_api.py::my_rows` / `my_export` (XLSX), il seçicisi, 4 stat kartı, jurnal keçidi.
* **Boşluq:** **fərdi iş planı** (4 bölmə: tədris / metodiki / elmi-tədqiqat / inzibati, plan-fakt saatı — KQ-12 üçün məcburi sənəd), ödəniş kalkulyatoru (read-only), təsdiq/etiraz.
* **Qərar:** genişlət — `IndividualPlan` + `PlanItem` + `LoadObjection`.
* **Rol/icazə:** `workload.view` (mövcud) + `workload.object` → `teacher`.
* **Data:** `LoadObjection(row, teacher, reason_key, text, status, created_at)` — `load_objection` ailəsi (4 hərfi səbəb) hazırdır.

### 17 · Rektor — ümumi baxış — yeni bölmə `workload-overview` (yeni, yalnız oxu)

* **Mövcud:** `vice_rector`-da `workload.*` var, amma aqreqat ekran yoxdur; `workload.report` icazəsinin **səthi yoxdur**.
* **Qərar:** yeni, **sətir səviyyəsində redaktə YOX**.
* **⚠ Aqreqasiya qaydası (§8/13):** kafedra → fakültə → universitet **yalnız aşağıdan yuxarı hesablanır; yekun rəqəmlər ayrıca SAXLANILMIR.** Denormalizasiya qadağandır.
* **Rol/icazə:** `workload.report` → `rector`, `vice_rector`, `teaching_office_head`.
* **Status ailəsi:** `load_band` (4 bant, hazır).

### 18–20 · Sillabus — `syllabus-list` / `syllabus-editor` / `syllabus-review` (restyle)

* **Mövcud: ÜÇÜ DƏ TAM.** `apps/syllabus/` (`constants.SectionKey` = 10 bölmə, `completion.py` — `WEEK_ROWS=16`, `MIN_FILLED_WEEKS=14`, `MIN_OUTCOMES=3`, `MIN_METHODS=2`, sərbəst iş cəmi 10), `state_machine.py` (7 status), `services/{workflow,coverage,units,notifications,scoping}.py`, per-bölmə autosave + optimistic `revision` lock, approved versiya DB constraint ilə immutable, e2e jsdom testləri.
* **Boşluq (18):** 5 klik edilə bilən KPI, `Cədvəl ⇄ Kart` açarı, statusa görə sıralama, «növbəti addım» mətnləri → **hamısı `core/ui/status_catalog.py::SYLLABUS`-a köçürülüb (Mərhələ 0-da hazır)**.
* **Boşluq (19):** `saveState` 6 vəziyyəti üçün ayrı banner (`failed` Retry, `offline` növbə, `conflict` 2 CTA, `stale`) — `save_state` ailəsi hazırdır; `viewState=permission` boş vəziyyəti.
* **Boşluq (20):** diff kartı (v1.1 ↔ v2.0), audit timeline, `role=noscope` boş vəziyyəti (**§8/8: `no scope ≠ bütün universitet`**).
* **Rol/icazə:** dəyişmir. Sahib qərarı (PHASE6, migration `0035_dean_syllabus_review_only`): **təsdiqçi `chair_head`**; dekanda yalnız `syllabus.view` + `syllabus.review`.
* **Açıq qərar §10.2 — DEFAULT: dekanın ikinci sillabus təsdiqi SÖNDÜRÜLÜ.** Policy parametri (`SyllabusPolicy.second_approval_enabled`), açılanda marşrut kafedra → dekan kimi uzanır; UI hazırdır (`role=dekan`).
* **Açıq qərar §10.3 — DEFAULT: versiya təsnifatı müəllimin seçimidir, LAKİN mövzu / çəki / struktur dəyişikliyi avtomatik MAJOR-a qaldırır.** Yəni «kiçik» seçimi validasiyadan keçmir: `services/versioning.py` diff-i yoxlayır, `week`/`assess`/`self` bölmələri dəyişibsə minor rədd edilir və istifadəçiyə səbəb göstərilir. Bu, §8/1 (approved immutable) və §8/3 (jurnal strukturu sillabusdan gəlir) ilə uyğundur.
* **Açıq qərar §10.4 — DEFAULT: sillabus təsdiq SLA-sı 5 iş günü**, «10 gündən çox gözləyir» KPI-ı isə **eskalasiya həddi** kimi qalır (dekana bildiriş). `SyllabusPolicy.review_sla_days = 5`, policy cədvəlində — kodda hardcode YOX.

### 21 · Müəllim — keçilmiş dərslər — yeni bölmə `my-lessons` (yeni, oxu-only)

* **Mövcud:** jurnal offering-ə bağlıdır (`registrar/views.py::journal_detail`, `gradebook_lessons.py`, `Lesson`/`LessonMark`); düzəliş izi tam (`corrections.py`, `JournalCorrection` + PDF).
* **Boşluq:** müəllim öz dərslərini offering/semestrdən asılı olmayaraq siyahı kimi görmür; «gec yazılıb / jurnal boşdur» bayraqları yoxdur.
* **Qərar:** yeni oxu-only bölmə; **model dəyişikliyi YOX** — `Lesson.created_at` vs `Lesson.date` fərqi «gec yazılıb»ı verir.
* **Rol/icazə:** `journal.roster` (mövcud); `role > müəllim` olduqda `teacher` filtri açılır (nəzarət görünüşü).
* **Status ailəsi:** `journal_note` (hazır).

---

## 3. Əlavə olunan rollar

`apps/organizations/default_roles_university.py` (18 rol) + migration (növbəti nömrə **0036**, çünki `0035_dean_syllabus_review_only` artıq var).

| Açar | Ad (AZ) | Səviyyə | Scope | Niyə |
| --- | --- | --- | --- | --- |
| `teaching_office_head` | Tədris şöbəsinin müdiri | **85** | ORGANIZATION | 01–07, 12, 17 ekranlarının sahibi |
| `teaching_office_staff` | Tədris şöbəsinin əməkdaşı | **60** | ORGANIZATION | eyni səth, təsdiq/kilid səlahiyyəti yox |
| `student_services` | Tələbə Xidmətləri | **60** | ORGANIZATION | 08, 09, 10, 11 (transkript sorğusunun icraçısı) |

> **⚠ MƏCBURİ:** `teaching_office_head` səviyyəsi 85 ≥ 80 olduğu üçün `core/roles.py:111::ProfileRole.ADMIN_ALIAS_EXEMPT_ROLE_NAMES` dəstinə **əlavə edilməlidir** — əks halda implicit `org_admin` alias-ı alır və bütün superadmin səthini görür (`aliases_for_membership_role`, `core/roles.py:144`). Bu, `DERS_YUKU_SPEC.md` §3.2-də də qeyd olunub. Dondurulmuş snapshot-lar da yenilənməlidir: `apps/accounts/services/view_as.py:243`, `view_as_policy.py:114`, `apps/organizations/services.py:186`.

### İcazə ailələri — mərhələ-mərhələ

| Mərhələ | Yeni icazə açarları | Kimə |
| --- | --- | --- |
| 1 | `unit.tree_manage`, `subject.view`, `subject.manage`, `subject.merge`, `program.view`, `program.manage`, `workload.staff_manage` | TO head/staff; `merge` yalnız head + RİM |
| 2 | `curriculum.edit`, `curriculum.review`, `curriculum.approve`, `curriculum.lock`, `semester.open`, `semester.lock`, `semester.unlock` | kafedra → dekan → TO head → rektor/RİM |
| 3 | `people.expel`, (mövcud `user.import`, `people.manage_academic` → `student_services`) | student_services, dean, TO head |
| 4 | `workload.submit`, `workload.review`, `workload.approve`, `workload.object` | TO head/staff, koordinator, dekan, müəllim |
| 5 | — (sillabus icazələri mövcuddur) | — |
| 6 | — | — |

---

## 4. Mərhələ bölgüsü (README §9 ilə eyni)

| Mərhələ | Ekranlar | Əhatə | Təxmini həcm | İşlətdiyi ORTAQ komponentlər |
| --- | --- | --- | --- | --- |
| **0** ✅ | 00 | Tokenlər + komponent kitabxanası + qalereya | **BİTDİ** | — |
| **1** | 01, 02, 03, 04 | Struktur və kataloq | ~9–12 gün · 3 rol, 7 icazə, 2 migration | ağac, cədvəl, filtr paneli, drawer, səbəb dialoqu, badge, KPI, boş/xəta |
| **2** | 05, 06, 07 | Tədris planı + semestr açılışı | ~12–15 gün · 7 icazə, 3 migration, 1 state machine | stepper, addım nav, cədvəl, kredit balans lenti, dialoq, timeline, banner |
| **3** | 08, 09 | Tələbə qəbulu və reyestri | ~5–7 gün · 1 rol, 1 migration | stepper, cədvəl, drawer, səbəb dialoqu, badge, KPI |
| **4** | 12, 13, 14, 15, 16, 17 | Dərs yükü zənciri | ~14–18 gün · 4 icazə, 3 migration | filtr paneli (draft/applied), cədvəl, KPI, səbəb dialoqu, timeline, tab, badge |
| **5** | 18, 19, 20 | Sillabus və təsdiq | ~6–8 gün · 0 migration (yalnız policy) | KPI-filtr, cədvəl⇄kart, addım nav, diff kartı, timeline, drawer, dialoq |
| **6** | 21, 10, 11 | Jurnal izi + tələbə görünüşü + müraciətlər | ~5–7 gün · 0 migration | cədvəl, filtr paneli, badge, timeline, boş vəziyyət |

**Mərhələ 1-in İLK işi (bloklayıcı):** `apps/accounts/templates/accounts/profile.html` **599/600 sətirdir** — modul ölçüsü limitinə tam dayanıb. Növbəti bölmə əlavə oluna bilməz. Qabıq bölünməlidir (`extraCss` və dispatch ladder-i ayrıca include-lara), sonra `templates/partials/ems_ui/_assets.html` panel-daxilindən qabığa köçürülməlidir. `apps/accounts/views/_helpers/rbac.py` da 592/600-dədir.

---

## 5. Mərhələ 0 — TAMAMLANDI

### 5.1 Tokenlər (add-only, `static/css/design-tokens.css` sonuna)

README §2.2-nin 8 adından **7-si artıq var idi** (sillabus qatı ilə gəlib). Əlavə olunanlar:

* Rəng: `--ems-danger-bd` (**işlənirdi, təyin olunmamışdı** — `workload_dialog.css:64` və `workload_base.css:161` fallback ilə çağırırdı), `--ems-green-400`, `--ems-blue-300`.
* Ölçü ailələri (handoff §2.4/2.5/2.6 + `00 Dizayn konstantları` kataloqu): `--ems-fs-2xs…3xl`, `--ems-ff-mono`, `--ems-r-xs…pill`, `--ems-sh-card/raised/dialog/toast/focus/nav-active`, `--ems-h-chip/cell/xs/tab/field/action`, `--ems-sp-1…8`, `--ems-pad-row/card`, `--ems-w-page/text/dialog/drawer`.
* **Heç bir mövcud ad dəyişdirilmədi, heç bir dəyər yenidən təyin olunmadı.**

### 5.2 §2.3 ziddiyyətinin həlli — WCAG AA lehinə (ölçülmüş)

| Cüt | Kontrast | Qərar |
| --- | --- | --- |
| `#10b981` (`--ems-success`) / `#dcfce7` | **2.31 — KEÇMİR** | mətn kimi İŞLƏNMİR; yalnız ikon/nöqtə/progress/accent |
| `#15803d` (`--ems-success-700`) / `#dcfce7` | 4.57 — AA | **yaşıl mətnin yeganə dəyəri** |
| `#166534` / `#dcfce7` | 6.49 — AA | işlənmir (ikinci yaşıl çalar saxlanılmır) |
| `#92400e` (`--ems-warning-800`) / `#fef3c7` | 6.37 — AA | sarı mətn |
| `#b91c1c` (`--ems-danger-strong`) / `#fee2e2` | 5.30 — AA | qırmızı mətn |
| `#64748b` (`--ems-neutral-500`) / `#f1f5f9` | **4.34 — KEÇMİR** | `locked/archived` badge mətni → `--ems-neutral-600` (6.92) |
| `#94a3b8` (`--ems-neutral-400`) / `#ffffff` | **2.56 — KEÇMİR** | KPI etiketi və `th` overline → `--ems-neutral-500` / `-600` |

Prototiplər 3 yerdə AA-dan keçməyən cüt istifadə edir (`neutral-400` CAPS etiket, `neutral-500` kilid badge-i, `--ems-success` mətn). **Handoff §7 «Kontrast … WCAG AA» tələbini üstün tutduq** və rəngi bir pillə tündləşdirdik — hue dəyişmir, vizual eyni qalır. Fərq `static/css/ems_ui/badge.css`, `kpi.css`, `table.css`, `controls.css` şərhlərində sənədləşdirilib.

### 5.3 Komponentlər — nə YENİ, nə TƏKRAR

**Təkrar istifadə (yenidən yazılmadı):** `static/js/toast.js` + `toast.css` (`EMSToast.show`) · `static/css/skeleton.css` · `templates/partials/_pagination.html` · `_empty_state.html` · `_bootstrap_select_field.html` + `static/js/bootstrap_select.js` · `static/js/ems_table.js` · `static/js/ems_ajax_init.js` (`EMSReady`/`EMSDelegate`) · `static/js/core/{csrf,http}.js` (`EMSCore.fetchJSON`).

**Yeni (`static/css/ems_ui/` · `static/js/ems_ui/` · `templates/partials/ems_ui/`):**

| # | Komponent | CSS | JS | Şablon |
| --- | --- | --- | --- | --- |
| 1 | Content header | `header.css` | — | `_content_header.html` |
| 2 | KPI kartı / sıra | `kpi.css` | `nav.js` (filtr açarı) | `_kpi_tile.html`, `_kpi_row.html` |
| 3 | Status badge | `badge.css` | — | `_status_badge.html` (+ `core/ui/status_catalog.py`, `templatetags/ems_ui.py`) |
| 4 | Filtr paneli (draft/applied) | `filter_bar.css` | `filter_bar.js` | `_filter_bar.html` |
| 5 | Data cədvəli | `table.css` | — (server sıralama) | `_data_table.html` |
| 6 | Boş / xəta / skeleton | `table.css` | — | `_empty.html`, `_skeleton_rows.html` |
| 7 | Ağac naviqasiyası | `nav.css` | `nav.js` | `_tree.html`, `_tree_node.html` |
| 8 | Axtarışlı seçici | *(mövcud)* | *(mövcud)* | `_bootstrap_select_field.html` — **a11y əlavəsi** |
| 9 | Drawer | `overlay.css` | `overlay.js` | `_drawer.html` |
| 10 | Dialoq | `overlay.css` | `overlay.js` | `_dialog.html` |
| 11 | Səbəb dialoqu (≥20 simvol) | `overlay.css` | `overlay.js` | `_reason_dialog.html` |
| 12 | Timeline | `timeline.css` | — | `_timeline.html` |
| 13 | Tab-lar (`aria-current`) | `nav.css` | `nav.js` | `_tabs.html` |
| 14 | Sətir-içi validasiya + lent | `validation.css` | — | `_field_message.html`, `_banner.html` |
| 15 | Stepper + addım nav | `nav.css` | `nav.js` | `_stepper.html`, `_step_nav.html` |
| 16 | Diff kartı, radio kartlar, düymə/sahə/kart/çip/progress | `overlay.css`, `controls.css` | — | *(class-lar)* |
| — | Asset yükləyicisi | — | — | `_assets.html` (10 CSS + 3 JS, bir dəfə) |

**Status kataloqu — TƏK Python mənbəyi:** `core/ui/status_catalog.py`, **17 ailə** (`generic`, `syllabus`, `workload_line`, `workload_visa`, `load_band`, `teacher_norm`, `dept_load`, `load_objection`, `plan`, `offering`, `semester_steps`, `intake_row`, `intake_steps`, `student_movement`, `journal_note`, `save_state`, `archive_mode`). Rəng Python-da **yoxdur** — yalnız ton adı; CSS tonu tokenə bağlayır. Naməlum ailə **səssiz keçmir** (`UnknownStatusFamily`), naməlum açar boş badge vermir (açarın özünü göstərir).

**Konsolidasiya hədəfləri (Mərhələ 1+ üçün, indi TOXUNULMADI):** `.syl-*` (~3 873 sətir) və `.apx-*` (~1 241 sətir) ailələri `ems-*`-in dublikatıdır; `apps/applications/constants.py::BADGE_PALETTES` hex-ləri mövcud tokenlərin eynisidir; `apps/accounts/views/syllabus/labels.py::STATUS_TONES` və `services/people/academic.py::STATUS_TONES` `status_catalog`-a yığılmalıdır. Uyğunluq üçün `badge.css` `submitted` / `review` / `archived` ton alias-larını da qəbul edir — yəni `labels.py` **dəyişmədən** yeni badge-ə keçə bilər.

### 5.4 Qalereya — MƏHSUL AĞACINDA YOXDUR (sahib qərarı, 2026-09-03)

Komponentləri bir yerdə göstərən qalereya **kabinet bölməsi kimi mövcud deyil** və heç bir istifadəçiyə görünmür. Qısa müddət yaradılmış `ui-gallery` bölməsi tam geri alındı: `sections_api.SECTION_PARTIALS` + `AJAX_SAFE_SECTIONS`, `rbac.py` superadmin dəsti, `_sections/labels.py`, `profile.html` (dispatch + `data-ajax-sections`), `sidebar/_org_menu_group.html`, bölmə şablonları, `ui_gallery.css` və `core/ui/gallery_samples.py` — hamısı silindi. `grep -rn "ui-gallery\|ui_gallery" apps core templates static config` → **0 nəticə**.

Vizual yoxlama üçün **deploy olunmayan statik səhifə** saxlanılır:

```
<scratchpad>/ui_gallery/
├── index.html      ← render olunmuş 16 blok (partial-ların real çıxışı)
├── gallery.css     ← yalnız bu səhifənin öz düzümü
└── static → repo-nun `static/` qovluğuna symlink
```

İşə salmaq: `cd <scratchpad>/ui_gallery && python3 -m http.server 8768` → `http://127.0.0.1:8768/`. Səhifə repo-nun **canlı** `design-tokens.css`, `ems_components.css`, `skeleton.css`, `ems_ui/*.css` və `ems_ui/*.js` fayllarını yükləyir — yəni komponentə edilən hər dəyişiklik dərhal orada görünür.

Qalereyanın yerini test qatı tutur: `apps/accounts/tests/test_ems_ui_components.py::ComponentPartialRenderTest` hər partial-ı öz kontekst müqaviləsi ilə **birbaşa render edir** və a11y şərtlərini yoxlayır; `NoGalleryInProductTreeTest` isə qalereyanın təsadüfən geri qayıtmasını bloklayır.

---

## 6. Bütün mərhələlərə şamil olunan qaydalar (README §8)

1. **APPROVED immutable** — sillabus və təsdiqlənmiş plan üçün PATCH/PUT qəbul edilmir; dəyişiklik = yeni versiya.
2. **Silmə YOXDUR — arxivləmə var.** Mövzu, sərbəst iş, ixtisas, fənn, qrup: `is_archived` + səbəb; əlaqəli qiymət və tarixçə qalır.
3. **Səbəb məcburi (≥20 simvol, audit-ə aktor + timestamp ilə):** «Geri qaytar», «Rədd et», «Yenidən aç», «Düzəliş sorğusu», «İrad», «Arxivləmə», «Xaric etmə», «Semestr kilidini aç». → `_reason_dialog.html` + `EMSOverlay` bunu artıq məcbur edir.
4. **Scope qaydası:** `no scope ≠ bütün universitet` — əhatəsiz istifadəçiyə data qaytarılmır (boş vəziyyət + administrator kanalı).
5. **Filtr semantikası:** `applied` server sorğusuna çevrilir, draft yox; sıralama və səhifələmə server tərəfdə. → `EMSFilterBar` bunu təmin edir.
6. **Aqreqasiya yalnız aşağıdan yuxarı** — yekun rəqəmlər saxlanılmır.
7. **Qiymət dəyişikliyi versiyalı yazıdır** (köhnə/yeni dəyər + səbəb + protokol nömrəsi) — mövcud `JournalCorrection` ailəsi bunu artıq edir.
8. **RLS:** hər yeni model `organization` FK + RLS migration; tenant izolyasiya testi `emsarena_ci_rls` rolu ilə (agent rolu BYPASSRLS-dir).
9. **String-ref FK** (`"organizations.OrgUnit"`) — `registrar` `organizations`-ı statik import etməməlidir (`scripts/module_deps.py`).
10. **Frontend:** inline/internal CSS-JS yoxdur; dinamik dəyər `data-*` / `json_script` / CSS custom property ilə; JS `EMSReady`/`EMSDelegate`; hər fayl ≤600 sətir; mətn `pgettext_lazy` + 4 kataloq.

---

## 7. Həll edilməmiş / sahib qərarı gözləyən

1. **ATİS konnektoru** — hazırda ümumi cədvəl importu var; ATİS-in rəsmi API/format müqaviləsi yoxdur. Plana daxil edilmədi.
2. **`profile.html` 599/600, `rbac.py` 591/600** — Mərhələ 1-də bir bölmə əlavə etmək limiti aşır; qabıq bölünməlidir (texniki, sahib qərarı deyil). Bölünəndə `templates/partials/ems_ui/_assets.html` include-u qabığa qoyulmalıdır — hazırda heç bir istehsal bölməsi komponent kitabxanasını YÜKLƏMİR (kitabxana hazırdır, istehlakçısı Mərhələ 1-də gəlir).
3. **i18n qapısı hazırda QIRMIZIDIR** — `source_missing` 125, hamısı paralel işləyən başqa agentlərin kontekstlərindəndir (`accounts.profile.question_chair_review`, `accounts.syllabus`, `exams.template.question_chair` …). Bu işin öz payı **0-dır** (bax §8).
4. **`program_coordinator`-un `workload-distribution` görməməsi** (ISSUES R-?) — Mərhələ 4-də `workload.review` ilə həll olunur, amma sahib təsdiqi lazımdır.

---

## 8. Mərhələ 0 — qapı vəziyyəti

> Qalereya bölməsi sahib qərarı ilə geri alındıqdan SONRAKI vəziyyət.

| Qapı | Nəticə |
| --- | --- |
| `black` / `isort` / `flake8` | ✅ təmiz |
| `scripts/check_module_size.py --check` | ✅ (`profile.html` **600/600** — limitdə) |
| `scripts/module_deps.py --check` | ✅ yeni dövr yoxdur |
| `makemigrations --check` | ✅ dəyişiklik yoxdur |
| pytest (`test_ems_ui_components.py`) | ✅ 39/39 (kataloq, tag-lər, hər partial-ın render + a11y müqaviləsi, asset gigiyenası, «qalereya qayıtmasın» qoruyucusu) |
| pytest (registry/routing/a11y/applications/dashboard/workload sections) | ✅ 104/104 (birlikdə) |
| `scripts/check_i18n_catalogs.py` | ⚠️ **QIRMIZI — paylaşılan sayğac, bu işin payı 0.** `ui.status` / `ui.filters` / `ui.dialog` (84 sətir × 4 dil) əlavə edildi; qalereya geri alınanda 136 `ui.gallery` girişi 4 kataloqdan da təmizləndi. Nəticə: `extra_vs_source` 0/24/24/1 və `identity` 235/125/306 — **hamısı baseline-də**. Qalan `source_missing`=125 başqa agentlərin kontekstlərindəndir (`accounts.profile.question_chair_review`, `accounts.syllabus`, `exams.template.question_chair` …). |
| Brauzer 1280 | ✅ kabinet qabığında yoxlanıldı (sidebar sol tərəfdə qaldı, panel sağda; KPI/badge/filtr/cədvəl/boş-xəta düzgün). Bölmə sonradan geri alındı — indi eyni markup statik səhifədə yoxlanılır. |
| Brauzer 375 | ✅ `scrollWidth == clientWidth` (üfüqi sürüşmə **0**), KPI 1 sütun, filtr sütuna düşür, cədvəl öz konteynerində sürüşür, `h1` sayı 1 |
