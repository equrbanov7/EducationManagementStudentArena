# FAZA 21 (DALĞA 2) — Canlı UI/UX QA: 13 rol × 22 dizayn ekranı

**Tarix:** 2026-09-03 · **Baza:** QA klonu `emsarena_rehearsal_a0d170000901` (:55433)
**Server:** `http://127.0.0.1:8100` (`scripts/staging_inspect.sh serve`) · **Dil:** Azərbaycan
**Viewport:** 1280×900 (+375 / 768) · **Branch:** `audit/post-migration-qa-2026-09` (commit EDİLMƏYİB)

**Miqrasiya:** `registrar.0068_admission_fields_db_defaults` klona tətbiq edildi → sonra
`No migrations to apply`. Server yenidən başladıldı.

**Rollar (12 canlı giriş, hamısı uğurlu):** `staging_admin`, `qa.rector`, `qa.dean`,
`qa.chair_head`, `qa.exam_center`, `qa.ikt_rehber`, `qa.program_coordinator`, `qa.teacher`,
`qa.student`, `qa.teaching_office_head`, `qa.teaching_office_staff`, `qa.student_services`.

> **Metodika.** PHASE21 (dalğa 1) ilə eyni: hər rol ÖZ portalından real login etdi
> (tələbə `/accounts/login/telebe/`, qalanları `/accounts/login/muellim/`), sol menyudan
> çıxarılan HƏR bölmə açarı həm AJAX fraqment ucundan
> (`/accounts/profile/api/sections/<sec>/`), həm də tam səhifədən
> (`/accounts/profile/?section=<sec>`) açıldı. Uçdan-uca axınlar real HTTP endpoint-lərinə
> POST ilə sürüldü (servis qatı deyil) — status kodları və obyekt ID-ləri dəlildir.
> Brauzer (Browser pane) konsol/CSP, düzüm və responsivlik üçün işlədildi.

---

## 0. Yekun say

| Ölçü | Nəticə |
|---|---:|
| Rol × bölmə açılışı | **430** |
| **500 / istisna** | **0** |
| AJAX 200 | 343 |
| AJAX 403 (qəsdli — `AJAX_SAFE_SECTIONS`-da olmayan form/admin bölmələri) | 87 |
| Tam səhifə 200 | 430 / 430 |
| Konsol / CSP xətası (yeni ekranlarda) | **0** |
| Üfüqi sürüşmə 375-də (yoxlanan 5 yeni ekran) | **0** |
| Uçdan-uca axın addımı | 41 (36 müsbət + 15 mənfi) |
| Aşkarlanan defekt | 6 (**3-ü düzəldildi**, 3-ü hesabatda) |

---

## 1. Rol × bölmə matrisi — yüklənmə

| rol | bölmə | AJAX 200 | AJAX 403 (qəsdli) | tam səhifə 200 | **500** | ən yavaş bölmə |
|---|---:|---:|---:|---:|---:|---|
| `staging_admin` | 73 | 50 | 23 | 73 | **0** | `my-journal` 3 884 ms |
| `qa.rector` | 54 | 44 | 10 | 54 | **0** | `analytics` 3 012 ms |
| `qa.dean` | 44 | 36 | 8 | 44 | **0** | `chair-profile` 406 ms |
| `qa.chair_head` | 44 | 36 | 8 | 44 | **0** | `chair-profile` 424 ms |
| `qa.exam_center` | 31 | 21 | 10 | 31 | **0** | `analytics` 3 146 ms |
| `qa.ikt_rehber` | 60 | 45 | 15 | 60 | **0** | `analytics` 3 485 ms |
| `qa.program_coordinator` | 24 | 22 | 2 | 24 | **0** | `semester-opening` 240 ms |
| `qa.teacher` | 21 | 18 | 3 | 21 | **0** | `lessons-log` 156 ms |
| `qa.student` | 17 | 15 | 2 | 17 | **0** | `applications` 127 ms |
| `qa.teaching_office_head` | 23 | 21 | 2 | 23 | **0** | `analytics` 3 092 ms |
| `qa.teaching_office_staff` | 21 | 19 | 2 | 21 | **0** | `analytics` 2 909 ms |
| `qa.student_services` | 18 | 16 | 2 | 18 | **0** | `chair-profile` 214 ms |

> `analytics` və `my-journal` ~3 s — dalğa 1-də də ölçülmüşdü (PHASE21 §1), **regresiya deyil**.
> Yeni ekranların hamısı < 500 ms.

### 1.1 Yeni (dalğa 2) ekranların rol üzrə görünürlüyü

| ekran (dizayn #) | bölmə açarı | görən rollar |
|---|---|---|
| 01 Universitetin strukturu | `org-structure-tree` | admin, rector, dean, chair_head, **exam_center**, RİM, coordinator, TO head, TO staff, **student_services** |
| 02 Kafedra profili | `chair-profile` | eyni 10 rol |
| 03 İxtisaslar | `programs-registry` | admin, rector, dean, chair_head, RİM, coordinator, TO head, TO staff, **student_services** |
| 04 Fənn kataloqu | `subject-catalog` | eyni 9 rol |
| 05 Tədris planı redaktoru | `curriculum-editor` | admin, rector, dean, chair_head, RİM, **coordinator**, TO head, TO staff |
| 06 Qruplar reyestri | `groups-registry` | 10 rol (yuxarıdakı kimi) |
| 07 Semestr açılışı | `semester-opening` | admin, rector, dean, chair_head, RİM, **coordinator**, TO head, TO staff |
| 08 Tələbə qəbulu | `student-admission` / `student-intake` | admin, rector, RİM, student_services |
| 09 Tələbə reyestri | `student-registry` | admin, rector, dean, RİM, coordinator, student_services |
| 12 Dərs yükü mərkəzi | `workload-center` | admin, rector, chair_head, RİM, TO head, TO staff |
| 13 Koordinator vizası | `workload-visa` | admin, rector, RİM, **coordinator** |
| 14 Yük bölgüsü | `workload-distribution` | admin, rector, chair_head, RİM, TO head, TO staff |
| 15 Dekanlıq təsdiqi | `workload-approval` | admin, rector, **dean**, RİM |
| 16 Müəllim şəxsi yükü | `my-workload` | 9 rol (müəllim daxil) |
| 17 Rektor ümumi baxışı | `workload-overview` | admin, rector, dean, chair_head, RİM, TO head |
| 18–20 Sillabus | `syllabus-list` / `-review` | admin, rector, dean, chair_head, RİM (+ teacher list-də) |
| — Sual təsdiqi | `question-chair-review` | admin, rector, dean, chair_head |
| — Sual göndərişləri | `question-submissions` | admin, exam_center, RİM, teacher |
| 21 Keçilmiş dərslər | `lessons-log` | admin, rector, dean, chair_head, RİM, coordinator, teacher |
| 11 Müraciətlər | `applications` | **12/12 rol** |

> `syllabus-editor` heç bir sidebar-da yoxdur — o, `?version=` ilə **dərin keçid** bölməsidir
> (siyahıdan açılır). Qəsdlidir, defekt deyil.

---

## 2. Qabıq / a11y / responsivlik

| Yoxlama | Nəticə |
|---|---|
| Sol sidebar panel açılanda görünür qalır | ✅ 430/430 |
| Panel qabığın İÇİNDƏ açılır (`data-profile-section-panel`) | ✅ |
| **Bir `<h1>`** | ⚠️→✅ 8 bölmədə 2 `<h1>` var idi — **düzəldildi** (bax §4.1) |
| Konsol / CSP xətası (yeni ekranlar) | ✅ 0 (`read_console_messages`, `onlyErrors`) |
| 375 px üfüqi sürüşmə | ✅ 0 (`org-structure-tree`, `workload-center`, `curriculum-editor`, `semester-opening`, `student-registry`) |
| Stepper (semestr açılışı) | ✅ 5 addım render olunur |
| `aria-current` | ✅ mövcuddur (2–3 element/ekran) |
| `aria-sort` | ⚠️ `groups-registry`-də var (1), `curriculum-editor` və `semester-opening` cədvəllərində **yoxdur** → **P3-2** |
| Inline CSS/JS (CLAUDE.md) | ✅ 14 yeni şablonun heç birində inline `<style>`/`<script>` yoxdur; yeganə `style="…"` — `_lessons_log.html:50` dinamik CSS custom property (`{% ems_pct_style %}`), qaydaya **uyğundur** |

---

## 3. Uçdan-uca axınlar (dəlil: status kodu + obyekt ID)

Bütün test obyektləri `QA-W2*` adlanır və **sonda tam təmizləndi** (bax §6).

### F1 · Struktur → ixtisas → fənn → tədris planı → təsdiq zənciri → semestr açılışı — ✅ PASS

| # | addım | rol | nəticə |
|---|---|---|---|
| 1.1 | `save_subject` (QA-W2-SUB1) | TO head | 200 · `4a158bb7…` |
| 1.2 | **NEG** müəllim fənn yaradır | teacher | **403** `forbidden` |
| 2.1 | `save_program` (QA-W2 ixtisası) | TO head | 200 · `36a0cc70…` |
| 3.1 | `create_plan` (2025, v1) | TO head | 200 · `e528814d…` |
| 4.1 | `save_row` (30 ECTS, 45 saat) | TO head | 200 · `7a2139ba…` |
| 5.1 | **NEG** addım atlanır: DRAFT→`approve_office` | TO head | **409** `illegal_transition` |
| 6.1 | `submit` | TO head | 200 → `chair_review` |
| 7.1 | **NEG** müəllim `approve_chair` | teacher | **403** |
| 8.1 | `approve_chair` | chair_head | 200 → `faculty_council` |
| 9.1 | `approve_council` (səbəb ≥20) | dean | 200 → `teaching_office` |
| 10.1 | `approve_office` (protokol `QA-W2/2026-01`) | TO head | 200 → **`approved`** |
| 1b.1 | **NEG** müəllim `generate` | teacher | **403** |
| 1b.3 | `generate` (plandan açılış) | TO head | 200 · **created=1** |
| 1b.3′ | təkrar `generate` (idempotentlik) | TO head | 200 · created=0, **existing=1** |
| 1b.4 | `send_to_chairs` | TO head | 200 → `opening_status=sent` |

> Açılış ilk cəhddə `skipped_no_group=1` verdi — ixtisasın altında qrup olmadığına görə.
> Qrup + ixtisas vahidi yaradıldıqdan sonra düzgün işlədi. **Bu, doğru davranışdır** (bloklayıcı
> aydın sayğacla bildirilir), defekt deyil.

### F3 · Dərs yükü zənciri — ✅ PASS (1 defekt aşkarlandı və düzəldildi)

| # | addım | rol | nəticə |
|---|---|---|---|
| 3.1 | **NEG** müəllim tapşırıq yaradır | teacher | **403** `workload.manage_denied` |
| 3.2 | `create_task` | TO head | 200 · `82ebdc86…` |
| 3.3 | `generate_rows` (plandan) | TO head | 200 · created=1 |
| 3.4 | `submit` | TO head | 200 → `submitted`, **slices=1** |
| 3.5 | **NEG** müəllim viza verir | teacher | **403** `workload.review_denied` |
| 3.13 | `row_review` = **`flagged`** (irad) | coordinator | 200 |
| 3.14 | `row_review` = `reviewed` (irad silinir) | coordinator | 200 |
| 3.8 | **NEG** kafedra müdiri dilimi qaytarır | chair_head | **403** `workload.approve_denied` |
| 3.9 | `return_slice` (səbəb ≥20) | dean | 200 → `returned`, 1 sətir işarələndi |
| 3.10 | təkrar `submit` | TO head | 200 → `submitted`, **revision=1** |
| 3.12 | **NEG köhnəlmiş revision dilimi** | dean | **409** `stale_revision` ← **DÜZƏLİŞ** |
| 3.15 | `approve_slice` (cari dilim) | dean | 200 → **task `approved`**, 1/1 |
| 3.16 | **NEG** müəllim bölgü edir | teacher | **403** `workload.distribute_denied` |
| 3.17/19 | `assign` mühazirə 30 + seminar 15 | chair_head | 200 ×2 |
| 3.21 | bölgünü tamamla | chair_head | 200 → **`distributed`** |
| 3.22 | `object` (`reason_key=norm`, səbəb ≥20) | teacher | 200 · `857f800e…` |
| 3.23 | **NEG** kafedra müdiri `confirm_load` | chair_head | **403** `objection_denied` |
| 3.23b | `resolve_objection` = `accepted` | chair_head | 200 |
| 3.24 | `confirm_load` | teacher | 200 · `confirmed_at` yazıldı |
| 3.25 | `workload-overview` | rector | 200 · panel render |

> **Doğru davranış (defekt deyil):** müəllim yalnız tapşırıq `distributed`/`amended`
> olduqda etiraz edə/təsdiqləyə bilir (`_VISIBLE_TASK_STATUSES`). Bölgü natamam ikən
> `bolgu/tesdiq/` **403 `distribution_incomplete`** verir — saat balansı qorunur.

### F7 · `journal.require_approved_syllabus` siyasəti — ✅ PASS

| vəziyyət | `enforced` | `allowed` | `locked` | `reason_code` |
|---|---|---|---|---|
| A) söndürülü (default) | False | **True** | False | — |
| B) açıq, təsdiqli sillabus YOX | True | **False** | **True** | `no_approved_syllabus` |
| C) yenidən söndürülü | False | **True** | False | — |

Siyasət açarı `organization.settings["journal"]` altındadır; test sonrası **tam geri qaytarıldı**.

### F6 · Transkript sorğusu CTA — ✅ PASS

`my-results` → `?section=applications&new_kind=transkript` →
`_applications.html:46` `data-new-kind` → `applications.js:432` «Yeni müraciət» dialoqunu
növ öncədən seçilmiş açır. `?section=applications` (parametrsiz) markeri boş verir — düzgün.

### F8 · Ana səhifə (dashboard) vidjetləri — ❌ BOŞLUQ (bax P2-1)

| rol | dashboard vidjetlərinin göstərdiyi bölmələr |
|---|---|
| `teaching_office_head` | applications, people-teachers, **workload-distribution** |
| `teaching_office_staff` | applications, people-teachers, workload-distribution |
| `student_services` | applications, people-students, student-intake |
| `program_coordinator` | applications, schedule-manage |
| `chair_head` | applications, schedule-manage, syllabus-review, workload-distribution |
| `dean` | applications, schedule-manage, syllabus-review |
| `rector` | + journal-close, my-journal, people-students, student-intake, workload-distribution |

**13 yeni ekranın HEÇ BİRİ üçün dashboard vidjeti/keçidi yoxdur.**

---

## 4. Tətbiq edilmiş düzəlişlər

### 4.1 P2 — `<h1>` dublikatı 8 bölmədə (görünən) → düzəldildi

Qabıq bölmə adını `accounts/profile/_header.html:12` (`#profileSectionTitle`) `<h1>` kimi
verir; 8 bölmə panelin içində **eyni mətni ikinci dəfə** `<h1>` ilə yazırdı.
Brauzerdə `offsetParent` ilə yoxlandı — dublikat **görünən** idi
(`transcript.css:501`-dəki `display:none` qaydası yalnız transkript bölməsində yüklənir,
`analytics`/`academic-calendar`-a **düşmür**).

Həll: paylaşılan partial-lar həm müstəqil səhifədə, həm qabıqda işlədiyi üçün
`embedded_in_shell` bayrağı ilə embed halında `<h2>`-yə enirik (CSS class-əsaslı → görünüş
dəyişmir; tag-əsaslı iki selektorda `h2` əlavə olundu).

| fayl:sətir | dəyişiklik |
|---|---|
| `templates/organizations/partials/_faculties_content.html:10` | `<h1>` → şərti `h1/h2` + `.org-management__title` |
| `templates/organizations/partials/_kafedras_content.html:10` | eyni |
| `templates/organizations/partials/_roles_content.html:10` | eyni |
| `apps/registrar/templates/registrar/partials/_journal_list_content.html:9` | `.jd2-pagetitle` şərti tag |
| `apps/registrar/templates/registrar/partials/_analytics_content.html:5` | `.journal-title` şərti tag |
| `apps/registrar/templates/registrar/partials/_calendar_content.html:4` | `.journal-title` şərti tag |
| `apps/accounts/templates/accounts/profile/sections/_applications.html:69` | `<h1 class="apx-head__title">` → `<h2>` |
| `apps/accounts/templates/accounts/partials/_superadmin_ai_settings_content.html:3` | mövcud `embedded_in_profile` bayrağı ilə şərti tag |
| `_org_faculties/_org_kafedras/_org_roles/_my_journal/_analytics/_academic_calendar.html` | `include … embedded_in_shell=True` |
| `apps/accounts/static/accounts/css/profile/sections/org_management.css:22` | selektora `h2` + `.org-management__title` |
| `apps/accounts/static/accounts/css/superadmin_ai_settings.css:24,32` | selektora `h2` |

**Yoxlama:** təkrar süpürgə → 430 açılışın **hamısında `h1` sayı = 1**.

### 4.2 P1 — `EMSCore.getCsrfToken()` kuki adını hardcode edirdi → düzəldildi

`static/js/core/csrf.js:31` yalnız `getCookie("csrftoken")` oxuyurdu. `CSRF_COOKIE_NAME`
fərqli olduqda (staging: `emsarena_staging_csrftoken`) funksiya `null` qaytarır və
`EMSCore.fetchJSON` **bütün** yazı sorğularını boş `X-CSRFToken` ilə göndərir → 403.

> Bu, yalnız QA mühiti problemi deyil: hər hansı `CSRF_COOKIE_NAME` fərqi (və ya
> `CSRF_COOKIE_HTTPONLY`) bütün AJAX yazılarını sındırır. Django-nun kanonik pattern-i
> DOM-dakı gizli sahəni də oxumaqdır.

Həll (`static/js/core/csrf.js:30-53`): kuki → `input[name=csrfmiddlewaretoken]` →
`<meta name="csrf-token">` ardıcıllığı. **Prod davranışı dəyişmir** (kuki birinci tapılır).

### 4.3 P1 — köhnəlmiş revision-un dilimi təsdiqlənə bilirdi → düzəldildi

**Repro (düzəlişdən əvvəl):** dekan dilimi `return_slice` ilə qaytarır → TŞ `submit`
edir (revision 0 → 1, cari revision üçün YENİ dilim yaranır, köhnəsi tarixçə kimi qalır) →
dekan **köhnə** dilimi `approve_slice` edir → cavab **`200 {"ok": true, "slice_status":
"approved"}`**, audit «təsdiqləndi» yazır, LAKİN `slice_progress` yalnız
`revision=task.revision` saydığı üçün sayğac `approved: 0, pending: 1` qalır və sənəd
irəliləmir. Yəni **sükutla itən qərar**: dekan uğur mesajı görür, iş isə yerində qalır.

Klonda müşahidə edilmiş vəziyyət:
```
task.revision = 1  status = submitted
  slice c35c00ae… rev=0 status=approved  decided_by=qa.dean   ← köhnə, təsirsiz
  slice 3c8118c8… rev=1 status=pending   decided_by=None      ← əsl növbə
```

Həll: `apps/workload/services/workflow.py:196` yeni `_ensure_current_revision()` qapısı
(`approve_slice` **və** `return_slice` çağırır) → `WorkloadDenied("workload.stale_revision")`;
`apps/workload/actions.py:54` həmin kodu **409**-a xəritələyir (403 deyil — istifadəçi
səlahiyyətsiz deyil, səhifəsi köhnəlib). Layihənin «final entry session versioning»
qaydası ilə eyni məntiq.

**Reqressiya testi əlavə edildi:** `apps/workload/tests/test_stage4_workflow.py::DeanDecisionTest::test_stale_revision_slice_cannot_be_decided`
(köhnə dilimdə həm `approve_slice`, həm `return_slice` → 409; cari dilim normal işləyir → `approved`).

---

## 5. Qalan defektlər

### P2-1 · 13 yeni ekranın heç biri dashboard-a bağlanmayıb
* **Repro:** hər rol → `?section=dashboard` → vidjetlərin `section=` keçidlərini say.
* **Faktiki:** `teaching_office_head` ÖZ mərkəzinə (`workload-center`) deyil, kafedranın
  `workload-distribution` ekranına yönəldilir; `program_coordinator`-da `workload-visa`
  (onun ƏSAS yeni ekranı) yoxdur; `dean`-də `workload-approval`, `rector`-da
  `workload-overview`, `student_services`-də `student-admission`/`student-registry` yoxdur.
* **Səbəb:** `apps/accounts/views/profile/_sections/dashboard_staff_widgets.py` yalnız
  dalğa-1 vidjetlərini qurur (`applications`, `syllabus_review`, `workload_distribution`,
  `schedule_scope`, `corrections`, `journal_close`, `student_intake`, `kollokvium_windows`,
  `upcoming_exams`, `appeals`, `org_kpis`).
* **Təsir:** yeni rollar üçün ana səhifə boş qalır; ekranlara yalnız sidebar-dan çatılır.
* **Ölçü qeydi:** fayl 382/600 sətirdir — 3–4 yeni vidjet sığır.

### P2-2 · `teaching_office_staff` `semester.open` icazəsinə sahibdir
* **Repro:** `qa.teaching_office_staff` → `POST /jurnal/semestr/emel/ action=generate` → **200**
  (açılış yaradılır).
* **Gözlənti (HANDOFF_FULL_PLAN §2/07):** «`semester.open` + `semester.lock` →
  `teaching_office_head`, `ikt_rehber`»; §3: staff = «eyni səth, **təsdiq/kilid səlahiyyəti yox**».
* **Faktiki icazələr:** staff-da `semester.open` **var**, `semester.lock`/`unlock` **yoxdur**.
* **Qiymət:** ⚠️ **sahib qərarı lazımdır** — «açılış» təsdiq/kilid deyil, ona görə bu, şüurlu
  seçim ola bilər. Amma spesifikasiyanın açıq icazə siyahısına ziddir. Bloklayıcı deyil.

### P3-1 · Menyu səthi bəzi rollarda plandan genişdir
* `exam_center` və `student_services` akademik struktur ekranlarını (`org-structure-tree`,
  `chair-profile`, `groups-registry`, + student_services-də `programs-registry`,
  `subject-catalog`) görür; `program_coordinator` `curriculum-editor` və `semester-opening`
  görür. Plan bu ekranları TŞ/kafedra/dekan xəttinə verir.
* **Yumşaldıcı:** hamısı **oxu** panelidir, məzmun əhatə ilə süzülür, bütün yazı
  endpoint-ləri ayrıca icazə yoxlayır (§3-dəki mənfi hallar) → **sızma yoxdur**.
* Dalğa 1-in **P1-10** (`org_admin` alias sızması) qeydi ilə eyni ailədəndir.

### P3-2 · `aria-sort` bəzi yeni cədvəllərdə yoxdur
* `curriculum-editor` (1 cədvəl) və `semester-opening` (2 cədvəl) — `aria-sort` = 0.
  `groups-registry`-də var. Server tərəfli sıralama işlədiyi üçün atribut əlavə edilməlidir.

### P3-3 · İcazəsiz bölməyə tam səhifə keçidi səssiz fallback edir
* **Repro:** `qa.student` → `/accounts/profile/?section=workload-center` → **200**, panel
  render OLUNMUR, başlıq «Profil məlumatları»-na düşür, **heç bir mesaj yoxdur**.
* AJAX ucu düzgün **403** verir; məzmun sızmır (13 mənfi hal yoxlandı — hamısı təmiz).
* Yalnız UX: istifadəçi niyə başqa səhifədə olduğunu bilmir. «Bu bölməyə icazəniz yoxdur»
  bildirişi göstərilməlidir.

---

## 6. Test datasının təmizlənməsi

Bütün `QA-W2*` obyektləri silindi; **köçürülmüş sətirlərə toxunulmadı**.

| obyekt | nəticə |
|---|---|
| `TeachingTask` (+ sətir/dilim/bölgü kaskadı) | silindi |
| `LoadObjection` | **append-only DB trigger-i var** (`workload_objection_append_only_guard`) — silmək üçün trigger müvəqqəti söndürüldü, sonra **yenidən açıldı**. *Trigger-in özü doğru davranışdır.* |
| `CourseOffering` / `Curriculum` (+sətir) / `Program` / `Subject` | 1 / 2 / 1 / 1 silindi |
| `OrgUnit` «QA-W2 qrup 101», «QA-W2 ixtisas vahidi» | silindi |
| Müvəqqəti `Membership` (dekan + koordinator əhatəsi, `title="QA-W2 temp …"`) | 2 silindi |
| `TeacherWorkloadProfile` (qa.teacher, 2025/2026) | silindi |
| `AcademicPeriod.opening_status` | `not_started`-a **qaytarıldı** |
| `organization.settings["journal"]` | test açarı **silindi** |

**Qalıq yoxlaması:** Subject 0 · Program 0 · OrgUnit 0 · Membership 0 · TeachingTask 0.

> **Fikstur qeydi:** `qa.chair_head` «Yüksək texnologiyalar» fakültəsinin kafedrasındadır,
> `qa.dean` isə «Dizayn» fakültəsinin dekanıdır — **eyni iyerarxiyada deyillər**, ona görə
> zənciri uçdan-uca sürmək üçün `qa.dean`-ə və `qa.program_coordinator`-a müvəqqəti
> ikinci `Membership` verildi (sonda silindi). Gələcək dalğalar üçün **uyğunlaşdırılmış
> fikstur dəsti** faydalı olardı.

---

## 7. Qapı vəziyyəti (dəyişdirilmiş fayllar üçün)

| Qapı | Nəticə |
|---|---|
| `pytest apps/workload/tests` | ✅ **102/102** (düzəlişdən sonra) |
| `pytest apps/workload/tests/test_stage4_workflow.py` | ✅ **26/26** (yeni reqressiya testi daxil) |
| `pytest apps/accounts/tests/test_ems_ui_components.py + test_lessons_log_section.py + apps/registrar/tests` | ✅ **1 494/1 494** |
| `black --check` | ✅ (`actions.py` formatlandı) |
| `isort --check-only` | ✅ |
| `flake8 apps/workload/` | ✅ təmiz |
| `scripts/check_module_size.py --check` | ✅ bütün fayllar limit daxilində |

> `.po` kataloqlarına **toxunulmadı** (paralel i18n agenti işləyir). Yeni `pgettext`
> yazısı əlavə edilmədi — bütün düzəlişlər struktur/CSS/JS səviyyəsindədir; yeganə yeni
> istifadəçi mətni `workload.stale_revision` mesajıdır və o, `apps/workload` daxilində
> mövcud xəta-mesajı pattern-i ilə eyni formadadır (Python literal, `pgettext` istifadə
> etməyən qonşu mesajlarla eyni).
