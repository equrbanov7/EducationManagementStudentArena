# Rol matrisi — hansı rol hansı profil bölməsini görür

**Ölçmə tarixi:** 2026-09-03 · **Baza:** QA klonu `emsarena_rehearsal_a0d170000901`
(`:55433`, bax `docs/audits/2026-09-02/`) — **HEÇ VAXT** lokal `emsarena_db`-yə
(qorunan, köçürülmüş real data) qarşı işlədilməyib.
**Mənbə:** `scripts/role_open_all.py` — bu cədvəl ƏLLƏ yazılmayıb, skriptin
`--markdown` çıxışıdır.  Kod dəyişəndə cədvəli yenidən yaratmaq lazımdır —
YALNIZ QA klonuna qarşı (skript `force_login()` işlədir və bir profil bayrağını
müvəqqəti söndürür, ona görə qorunan bazaya qarşı ASLA işlədilməməlidir):

```bash
EMS_STAGING_INSPECT=1 \
DATABASE_URL="postgres://emsarena_staging:emsarena_staging_password@127.0.0.1:55433/emsarena_rehearsal_a0d170000901" \
EMS_STAGING_DB_NAME=emsarena_rehearsal_a0d170000901 \
EMS_STAGING_DB_PORT=55433 \
EMS_DB_ROLE_ENFORCE=off DEBUG=True USE_REDIS=False ENABLE_NGROK=False \
ALLOWED_HOSTS="localhost,127.0.0.1" \
.venv/bin/python scripts/role_open_all.py --settings config.settings.staging_inspect --markdown
```

`--settings` skriptin dəstəklədiyi mövcud arqumentdir (default
`config.settings.local`) — heç nə yamaqlamağa ehtiyac yoxdur, sadəcə QA
klonuna işarə edən `config.settings.staging_inspect`-i ötürün.

## Nə ölçülür

Skript aktiv üzvlüyü olan HƏR rol üçün bir istifadəçi seçir, profil qabığını
yükləyir, sol menyudakı bölmə açarlarını HTML-dən çıxarır və hər birini AJAX
fraqment ucundan (`accounts:profile_section_fragment`) açır.  Yəni cədvəl
«kodda nə yazılıb» yox, **istifadəçinin həqiqətən gördüyü** siyahıdır.

Niyə vacibdir: bölmə görünürlüyü **dörd ayrı siyahıda** qeyd olunur —
`SECTION_PARTIALS` · `AJAX_SAFE_SECTIONS` · şablondakı `data-ajax-sections` ·
`apps/accounts/views/_helpers/rbac_sections.py`.  Biri unudulanda bölmə ya
menyuda görünmür, ya da açılanda 500 verir.  Süpürgə həmin fərqi bir keçidə
üzə çıxarır.

## Nəticə — 2026-09-03 (QA klonu)

| rol | səviyyə | görünən bölmə | 500 |
|---|---:|---:|---:|
| `ikt_rehber` | 88 | 46 | 0 |
| `rector` | 100 | 40 | 0 |
| `chair_head` | 70 | 34 | 0 |
| `dean` | 80 | 33 | 0 |
| `exam_center` | 85 | 28 | 0 |
| `exam_center_staff` | 60 | 24 | 0 |
| `hr` | 65 | 22 | 0 |
| `teacher` | 50 | 20 | 0 |
| `assistant` | 40 | 19 | 0 |
| `student` | 10 | 17 | 0 |
| `member` | 20 | 14 | 0 |
| `program_coordinator` | 45 | 14 | 0 |
| `alumni` | 5 | 0 | 0 |

| bölmə | `ikt_rehber` | `rector` | `chair_head` | `dean` | `exam_center` | `exam_center_staff` | `hr` | `teacher` | `assistant` | `student` | `member` | `program_coordinator` | `alumni` |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `academic-calendar` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `academic-records` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · |
| `analytics` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | ✅ | · |
| `appeal-stats` | ✅ | · | · | · | ✅ | ✅ | · | · | · | · | · | · | · |
| `applications` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | ✅ | · |
| `assigned-courses` | · | · | · | · | · | · | · | · | · | ✅ | ✅ | · | · |
| `assigned-exams` | · | · | · | · | · | · | · | · | · | ✅ | ✅ | · | · |
| `audit-log` | ✅ | ✅ | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · |
| `change-password` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `dashboard` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `edit-profile` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `exam-center-pins` | ✅ | · | · | · | ✅ | ✅ | · | · | · | · | · | · | · |
| `exam-center-stats` | ✅ | · | · | · | ✅ | ✅ | · | · | · | · | · | · | · |
| `exam-chance` | ✅ | · | · | · | ✅ | ✅ | · | · | · | · | · | · | · |
| `exam-score-entry` | · | ✅ | · | · | ✅ | · | · | · | · | · | · | · | · |
| `groups` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | ✅ | ✅ | · | ✅ | · | · |
| `journal-close` | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · |
| `kollokvium-windows` | ✅ | · | · | · | ✅ | ✅ | · | · | · | · | · | · | · |
| `legacy-grade-review` | ✅ | ✅ | · | · | ✅ | · | · | · | · | · | · | · | · |
| `manage-appeals` | ✅ | · | · | · | ✅ | ✅ | · | · | · | · | · | · | · |
| `manage-roles` | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | · | · | · | · | · | · |
| `my-appeals` | · | · | · | · | · | · | · | · | · | ✅ | ✅ | · | · |
| `my-courses` | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | ✅ | · | · | · | · |
| `my-exams` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | ✅ | ✅ | · | · | · | · |
| `my-journal` | ✅ | ✅ | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · |
| `my-results` | · | · | · | · | · | · | · | · | · | ✅ | ✅ | · | · |
| `my-schedule` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `my-subjects` | · | · | · | · | · | · | · | · | · | ✅ | · | · | · |
| `my-workload` | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | ✅ | · | · | ✅ | · |
| `notifications` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `org-faculties` | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | · | · | · | · | · | · |
| `org-kafedras` | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | · | · | · | · | · | · |
| `org-members` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | ✅ | · |
| `org-roles` | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · |
| `overall-academic` | · | · | · | · | · | · | · | · | · | ✅ | · | · | · |
| `pending-answers` | · | · | · | · | · | · | · | · | · | ✅ | ✅ | · | · |
| `pending-review` | · | · | · | · | · | · | · | ✅ | ✅ | · | · | · | · |
| `people-students` | ✅ | ✅ | ✅ | ✅ | ✅ | · | ✅ | · | · | · | · | ✅ | · |
| `people-teachers` | ✅ | ✅ | ✅ | ✅ | ✅ | · | ✅ | · | · | · | · | · | · |
| `permission-editor` | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · |
| `profile-info` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `publish-notification` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · |
| `question-bank` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | ✅ | ✅ | · | · | · | · |
| `question-chair-review` | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · |
| `question-submissions` | ✅ | · | · | · | ✅ | ✅ | · | ✅ | ✅ | · | · | · | · |
| `review-results` | · | · | · | · | · | · | · | ✅ | ✅ | · | · | · | · |
| `rim-center` | ✅ | ✅ | · | · | · | · | ✅ | · | · | · | · | · | · |
| `role-assignment` | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | · | · | · | · | · | · |
| `schedule-manage` | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | ✅ | · |
| `statistics` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `student-intake` | ✅ | ✅ | · | · | · | · | ✅ | · | · | · | · | · | · |
| `student-organization-management` | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | · | · | · | · | · | · |
| `superadmin-exam-rooms` | ✅ | · | · | · | · | · | · | · | · | · | · | · | · |
| `syllabus-list` | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | · | · | · | · | · |
| `syllabus-review` | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · |
| `teaching-handover` | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · |
| `unit-exams` | · | · | ✅ | ✅ | · | · | · | · | · | · | · | · | · |
| `workload-distribution` | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · |

Cəmi 311 bölmə açılışı.

**500 / istisna: yoxdur.**

`ui-gallery` (superadmin-only) bu cədvəldə **görünmür** — süpürgə YALNIZ aktiv
`Membership`-i olan rolları gəzir (`_pick_users()`), superadmin isə QA
klonunda `is_superuser=True` bayraqlı ayrıca hesabdır (`staging_admin`),
heç bir rol üzvlüyünə bağlı deyil. Bu, gözlənilən haldır — nasazlıq deyil.

## Oxunuş qeydləri

* **`alumni` — 0 bölmə.  Bu QƏSDƏNDİR, defekt DEYİL — DÜZƏLTMƏYİN.**

  Rol `apps/organizations/default_roles_university.py:434`-dədir və
  `permissions = []` **qəsdən boşdur**: rol heç bir hüquq VERMİR, yalnız
  `registrar_guard_active_member` trigger-inin tələb etdiyi **aktiv üzvlüyü**
  təmin edir ki, tarixi jurnal/qiymət sətirləri köçə bilsin.

  Giriş isə ayrıca qatda bağlanır — `UserProfile.access_state='archived'`
  (`login_blocked_access_states()` = `STAGED, ARCHIVED`, bax
  `apps/accounts/identity.py:75`).  Qapı **15 nöqtədə** tətbiq olunur
  (auth backend, login formaları, OTP, middleware, view-as, hesab silmə).
  Yəni **bu 2,490 hesab ümumiyyətlə giriş edə bilmir**; «0 bölmə» qapının
  İŞLƏMƏSİDİR.

  ⚠️ Yuxarıdakı cədvəldəki `alumni` sətri **ölçmə artefaktıdır**: süpürgə
  `force_login()` işlədir və sessiya qapını yan keçir, sonra middleware ilk
  request-də onu söndürür.  Real brauzerdə 14 URL-in hamısı `302 → login`.

  ⚠️ Bu 2,490 hesab **«məzun» deyil — «məzun ∪ XARİC EDİLMİŞ»dir** və legacy
  `students.azadedildi` bayrağı onları AYIRMIR.  Portalı onlara açmaq xaric
  edilmiş tələbələrə də giriş verərdi.

  Sahibin qərarı: `docs/migration/STATUS.md:261` — «hesab girişə bağlı qalsın,
  akademik qeydləri köçsün».  Müqaviləni `apps/accounts/tests/test_account_archive.py`
  (16 test) kilidləyir.
* **`ikt_rehber` (46) rektordan (40) çox bölmə görür.**  Bu qəsdəndir: rol
  full-override texniki rəhbərdir (bax `project_ikt_rehber_role`), `rector` isə
  təsdiq/idarəetmə səthlərinə baxır — `superadmin-exam-rooms`,
  `exam-center-*`, `kollokvium-windows`, `appeal-stats` ona verilməyib.
* **`dean` (33) və `chair_head` (34) demək olar eyni bölmə dəstini görür** —
  fərq (`unit-exams` hər ikisində, `question-chair-review` hər ikisində) bölmə
  siyahısında deyil, bölmə İÇİNDƏKİ əhatə dairəsindədir (fakültə vs kafedra) —
  o qapı servis qatındadır, menyuda görünmür.
* **`teacher` (20) və `student` (17) demək olar eyni sayda bölmə görür**, amma
  kəsişmə azdır: müəllimdə `my-courses`/`syllabus-list`/`review-results`,
  tələbədə `my-journal`/`my-results`/`my-appeals`.
* **`program_coordinator` (14)** ən dar staff rollarından biridir — yalnız
  analitika + insanlar kataloqu + ortaq bölmələr.
* **`assistant` / `exam_center_staff` / `hr` / `member` (19/24/22/14) —
  2026-08-31 ölçümündə YOX idi.**  Bu 2026-09-03 QA klonunda seçilmiş nümunə
  istifadəçilərin arasında bu rollara aktiv üzvlük olduğuna görədir (əvvəlki
  ölçmə lokal `emsarena_db`-də bu rollar üçün fərqli/az nümunə tapmışdı); rol
  təyinatının özü dəyişməyib — süpürgə sadəcə bazadakı MÖVCUD üzvlükdən
  nümunə seçir (`_pick_users()`), rol siyahısı əvvəlcədən sabit deyil.
* **`question-chair-review` yalnız `rector`/`chair_head`/`dean`-ə görünür.**
  Bu, 2026-09-02 audit fazasında əlavə olunan «Sual təsdiqi» bölməsidir (bax
  `docs/audits/2026-09-02/PHASE_QUESTION_CHAIR_APPROVAL.md`) — kafedra müdiri
  (və ya müdir yoxdursa dekan) müəllimin imtahan sual dəstini İmtahan
  Mərkəzinə göndərilmədən əvvəl təsdiqləyir; `rector` isə RİM kimi
  full-override deyil, amma təşkilat səviyyəsində eyni əhatəyə malikdir.
* **`dashboard` / `applications` / `schedule-manage` / `student-intake` /
  `workload-distribution` / `my-workload`** — bu ölçmədə bütün müvafiq
  rollarda gözlənilən şəkildə görünür (bax cədvəl); bunlar sabit, öncədən
  mövcud bölmələrdir.

## Tələlər (skriptdə həll olunub — silməyin)

1. **`ALLOWED_HOSTS`.**  `django.test.Client` `testserver` host-u ilə gəlir;
   `config.settings.local` onu tanımır və HƏR sorğu **400** qaytarır.  Bölmələr
   «sınıq» görünür, əslində host rədd edilib.  Skript `django.setup()`-dan
   SONRA `settings.ALLOWED_HOSTS = ["*"]` verir — yalnız prosesin öz
   yaddaşında, fayla yazmadan.
2. **Parol divarı.**  `FirstLoginPasswordMiddleware` `password_change_required`
   olan hesabı hər sorğuda parol dəyişmə səhifəsinə yönləndirir; süpürgə boş
   HTML alır və rolu «0 bölmə» kimi yazır (yalançı `alumni`-yə bənzər nəticə).
   Skript bayrağı müvəqqəti söndürür və `finally` blokunda **geri qaytarır** —
   proses yarımçıq kəsilsə belə.
3. **Tələbə seçimi.**  Yazılışı olmayan tələbə hesabında bölmələr yanlış boş
   görünür; skript ən çox `Enrollment`-i olan tələbəni seçir.

⚠️ Skript defolt olaraq **canlı bazaya** qoşulur (`--settings` verilməsə
`config.settings.local`).  Yalnız GET sorğusu göndərir, lakin `force_login()`
işlədir və bir profil bayrağını müvəqqəti söndürür — ona görə **YALNIZ QA
klonuna** (`--settings config.settings.staging_inspect` + klonun `DATABASE_URL`-i,
yuxarıdakı əmrə bax) qarşı işlədilməlidir, əsla qorunan `emsarena_db`-yə və ya
prod-a qarşı YOX.

## Çıxış formatları

| əmr | nə verir |
|---|---|
| `scripts/role_open_all.py` | rol-rol bölmə siyahısı (mətn) |
| `scripts/role_open_all.py --markdown` | bu sənəddəki iki cədvəl |
| `scripts/role_open_all.py --json out.json` | maşın oxusu (CI/diff üçün) |

Çıxış kodu: 500/istisna tapılsa `1`, təmiz keçsə `0` — CI-da qapı kimi
işlədilə bilər.
