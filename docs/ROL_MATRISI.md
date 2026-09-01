# Rol matrisi — hansı rol hansı profil bölməsini görür

**Ölçmə tarixi:** 2026-08-31 · **Baza:** lokal `emsarena_db` (köçürülmüş real data)
**Mənbə:** `scripts/role_open_all.py` — bu cədvəl ƏLLƏ yazılmayıb, skriptin
`--markdown` çıxışıdır.  Kod dəyişəndə cədvəli yenidən yaratmaq lazımdır:

```bash
.venv/bin/python scripts/role_open_all.py --markdown
```

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

## Nəticə — 2026-08-31

| rol | səviyyə | görünən bölmə | 500 |
|---|---:|---:|---:|
| `ikt_rehber` | 88 | 38 | 0 |
| `rector` | 100 | 31 | 0 |
| `chair_head` | 70 | 28 | 0 |
| `dean` | 80 | 28 | 0 |
| `exam_center` | 85 | 25 | 0 |
| `teacher` | 50 | 16 | 0 |
| `student` | 10 | 15 | 0 |
| `program_coordinator` | 45 | 10 | 0 |
| `alumni` | 5 | 0 | 0 |

| bölmə | `ikt_rehber` | `rector` | `chair_head` | `dean` | `exam_center` | `teacher` | `student` | `program_coordinator` | `alumni` |
|---|---|---|---|---|---|---|---|---|---|
| `academic-calendar` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `academic-records` | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · |
| `analytics` | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | · |
| `appeal-stats` | ✅ | · | · | · | ✅ | · | · | · | · |
| `assigned-courses` | · | · | · | · | · | · | ✅ | · | · |
| `assigned-exams` | · | · | · | · | · | · | ✅ | · | · |
| `audit-log` | ✅ | ✅ | · | · | ✅ | · | · | · | · |
| `change-password` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `edit-profile` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `exam-center-pins` | ✅ | · | · | · | ✅ | · | · | · | · |
| `exam-center-stats` | ✅ | · | · | · | ✅ | · | · | · | · |
| `exam-chance` | ✅ | · | · | · | ✅ | · | · | · | · |
| `exam-score-entry` | · | ✅ | · | · | ✅ | · | · | · | · |
| `groups` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · |
| `journal-close` | ✅ | ✅ | · | · | · | · | · | · | · |
| `kollokvium-windows` | ✅ | · | · | · | ✅ | · | · | · | · |
| `manage-appeals` | ✅ | · | · | · | ✅ | · | · | · | · |
| `manage-roles` | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · |
| `my-appeals` | · | · | · | · | · | · | ✅ | · | · |
| `my-courses` | ✅ | ✅ | ✅ | ✅ | · | ✅ | · | · | · |
| `my-exams` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · |
| `my-journal` | · | · | · | · | · | · | ✅ | · | · |
| `my-results` | · | · | · | · | · | · | ✅ | · | · |
| `my-schedule` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `my-subjects` | · | · | · | · | · | · | ✅ | · | · |
| `notifications` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `org-faculties` | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · |
| `org-kafedras` | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · |
| `org-members` | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | · |
| `org-roles` | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · |
| `overall-academic` | · | · | · | · | · | · | ✅ | · | · |
| `pending-answers` | · | · | · | · | · | · | ✅ | · | · |
| `pending-review` | · | · | · | · | · | ✅ | · | · | · |
| `people-students` | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | ✅ | · |
| `people-teachers` | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · |
| `permission-editor` | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · |
| `profile-info` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `publish-notification` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · |
| `question-bank` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · |
| `question-submissions` | ✅ | · | · | · | ✅ | ✅ | · | · | · |
| `review-results` | · | · | · | · | · | ✅ | · | · | · |
| `rim-center` | ✅ | ✅ | · | · | · | · | · | · | · |
| `role-assignment` | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · |
| `statistics` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `student-organization-management` | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · |
| `superadmin-exam-rooms` | ✅ | · | · | · | · | · | · | · | · |
| `syllabus-list` | ✅ | ✅ | ✅ | ✅ | · | ✅ | · | · | · |
| `syllabus-review` | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · |
| `teaching-handover` | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · |
| `unit-exams` | · | · | ✅ | ✅ | · | · | · | · | · |

Cəmi 191 bölmə açılışı.

**500 / istisna: yoxdur.**

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
* **`ikt_rehber` (38) rektordan (31) çox bölmə görür.**  Bu qəsdəndir: rol
  full-override texniki rəhbərdir (bax `project_ikt_rehber_role`), `rector` isə
  təsdiq/idarəetmə səthlərinə baxır — `superadmin-exam-rooms`,
  `exam-center-*`, `kollokvium-windows`, `appeal-stats` ona verilməyib.
* **`dean` və `chair_head` eyni 28 bölməni görür.**  Fərq bölmə siyahısında
  deyil, bölmə İÇİNDƏKİ əhatə dairəsindədir (fakültə vs kafedra) — o qapı
  servis qatındadır, menyuda görünmür.
* **`teacher` (16) və `student` (15) demək olar eyni sayda bölmə görür**, amma
  kəsişmə azdır: müəllimdə `my-courses`/`syllabus-list`/`review-results`,
  tələbədə `my-journal`/`my-results`/`my-appeals`.
* **`program_coordinator` (10)** ən dar staff rolüdür — yalnız analitika +
  insanlar kataloqu + ortaq bölmələr.

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

⚠️ Skript **canlı lokal bazaya** qoşulur (`config.settings.local`).  Yalnız GET
sorğusu göndərir; yeganə yazısı yuxarıdakı müvəqqəti bayraqdır.  **Prod-a qarşı
işlətməyin.**

## Çıxış formatları

| əmr | nə verir |
|---|---|
| `scripts/role_open_all.py` | rol-rol bölmə siyahısı (mətn) |
| `scripts/role_open_all.py --markdown` | bu sənəddəki iki cədvəl |
| `scripts/role_open_all.py --json out.json` | maşın oxusu (CI/diff üçün) |

Çıxış kodu: 500/istisna tapılsa `1`, təmiz keçsə `0` — CI-da qapı kimi
işlədilə bilər.
