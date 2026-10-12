# Rol matrisi — hansı rol hansı profil bölməsini görür

**Ölçmə tarixi:** 2026-10-13 (əvvəlki: 2026-09-03) · **Baza:** QA klonu `emsarena_rehearsal_a0d170000901`
(`:55433`, bax `docs/audits/2026-09-02/`) — **HEÇ VAXT** lokal `emsarena_db`-yə
(qorunan, köçürülmüş real data) qarşı işlədilməyib.
**Mənbə:** `scripts/role_open_all.py` — bu cədvəl ƏLLƏ yazılmayıb, skriptin
`--markdown` çıxışıdır.  Kod dəyişəndə cədvəli yenidən yaratmaq lazımdır —
YALNIZ QA klonuna qarşı (skript `force_login()` işlədir və bir profil bayrağını
müvəqqəti söndürür, ona görə qorunan bazaya qarşı ASLA işlədilməməlidir):

```bash
EMS_STAGING_INSPECT=1 \
DATABASE_URL="${QA_CLONE_DATABASE_URL:?QA_CLONE_DATABASE_URL təyin edilməyib — klon DSN-i .claude/staging.env-dən (parol repoya yazılmır, audit 2026-09-13 F-03)}" \
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

## Nəticə — 2026-10-13 (QA klonu, miqrasiyalar `organizations 0060` / `registrar 0088`-ə qədər)

Nümunə hesab seçimi 2026-10-13-dən **tək-rolludur**: əvvəl «teacher» sütununa müəllim + kafedra müdiri olan
hesab düşə bilirdi (49 bölmə, rolların birləşməsi). İndi `_pick_users()` əvvəlcə YALNIZ bir aktiv üzvlüyü olan
hesabı götürür; tapılmasa çoxrollu hesaba düşür və bu, «əlavə rollar» sütununda göstərilir
(`board_chair` klonda yalnız rektorla birlikdə mövcuddur).

⚠️ Klon DSN-i **cədvəl sahibi** (`emsarena_staging`) olmalıdır: `emsarena_app` RLS altında tenant konteksti
olmadan `Membership` sətirlərini görmür (skript indi bu halda exit 2 ilə dayanır).

Menyu YALNIZ `<aside class="profile-sidebar">` blokundan oxunur (dashboard vidcetlərindəki
`data-section` sayılmır), müəllim/admin üçün `/jurnal/` yeni-tab linki `my-journal` kimi sayılır.

| rol | səviyyə | görünən bölmə | 500 | əlavə rollar (çoxrollu nümunə) |
|---|---:|---:|---:|---|
| `ikt_rehber` | 95 | 75 | 0 | — |
| `board_chair` | 110 | 64 | 0 | `rector` |
| `rector` | 100 | 64 | 0 | — |
| `vice_rector` | 90 | 50 | 0 | — |
| `chair_head` | 70 | 47 | 0 | — |
| `dean` | 80 | 46 | 0 | — |
| `vice_dean` | 75 | 38 | 0 | — |
| `rim_staff` | 60 | 37 | 0 | — |
| `exam_center_head` | 85 | 34 | 0 | — |
| `exam_center_staff` | 60 | 31 | 0 | — |
| `hr` | 65 | 30 | 0 | — |
| `program_coordinator` | 45 | 30 | 0 | — |
| `teaching_office_head` | 85 | 29 | 0 | — |
| `teaching_office_staff` | 60 | 27 | 0 | — |
| `teacher` | 50 | 24 | 0 | — |
| `assistant` | 40 | 23 | 0 | — |
| `lab_assistant` | 40 | 23 | 0 | — |
| `student_services` | 60 | 23 | 0 | — |
| `admin_unit_head` | 65 | 21 | 0 | — |
| `lead_student` | 30 | 20 | 0 | — |
| `student` | 10 | 20 | 0 | — |
| `member` | 20 | 15 | 0 | — |
| `tutor` | 40 | 15 | 0 | — |
| `alumni` | 5 | 0 | 0 | — |

| bölmə | `ikt_rehber` | `board_chair` | `rector` | `vice_rector` | `chair_head` | `dean` | `vice_dean` | `rim_staff` | `exam_center_head` | `exam_center_staff` | `hr` | `program_coordinator` | `teaching_office_head` | `teaching_office_staff` | `teacher` | `assistant` | `lab_assistant` | `student_services` | `admin_unit_head` | `lead_student` | `student` | `member` | `tutor` | `alumni` |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `academic-calendar` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `academic-records` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `account-password-reset` | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `analytics` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | ✅ | · |
| `announcements` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `appeal-stats` | ✅ | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `applications` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | ✅ | · |
| `assigned-courses` | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · |
| `assigned-exams` | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · |
| `audit-log` | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | ✅ | ✅ | ✅ | · | ✅ | · | · | · | · | · | · | · | · | · | · | · |
| `chair-profile` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | ✅ | · | · | · | · | · |
| `change-password` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `curriculum-editor` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · |
| `dashboard` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `edit-profile` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `evaluation-campaigns` | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `evaluation-results` | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · |
| `exam-center-pins` | ✅ | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `exam-center-stats` | ✅ | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `exam-chance` | ✅ | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `exam-score-entry` | ✅ | ✅ | ✅ | · | · | · | · | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `groups-registry` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | ✅ | · | · | · | · | · |
| `hr-analytics` | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `journal-close` | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `journal-hygiene` | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `kollokvium-windows` | ✅ | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `legacy-grade-review` | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `lessons-log` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | ✅ | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · |
| `manage-appeals` | ✅ | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `manage-roles` | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `my-appeals` | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · |
| `my-courses` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · |
| `my-exams` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · |
| `my-journal` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | ✅ | · | · | ✅ | ✅ | ✅ | · | · | ✅ | ✅ | · | · | · |
| `my-results` | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · |
| `my-schedule` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `my-subject-folders` | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | ✅ | · | · | · |
| `my-subjects` | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | ✅ | · | · | · |
| `my-workload` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · |
| `notifications` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `org-faculties` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | ✅ | · | · | · | · | · |
| `org-kafedras` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | ✅ | · | · | · | · | · |
| `org-members` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | ✅ | · |
| `org-overview` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | ✅ | · | · | · | ✅ | · |
| `org-roles` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `org-structure-tree` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | ✅ | · | · | · | · | · |
| `overall-academic` | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | ✅ | · | · | · |
| `pending-answers` | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · |
| `pending-review` | · | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · |
| `people-students` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | ✅ | ✅ | · | · | · | · | · | ✅ | ✅ | · | · | · | ✅ | · |
| `people-teachers` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | ✅ | · | ✅ | ✅ | · | · | · | · | ✅ | · | · | · | · | · |
| `permission-editor` | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `profile-info` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `programs-registry` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | ✅ | · | · | · | ✅ | ✅ | ✅ | · | · | · | ✅ | ✅ | · | · | · | · | · |
| `publish-notification` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · |
| `question-bank` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · |
| `question-chair-review` | ✅ | ✅ | ✅ | · | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `question-submissions` | ✅ | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · |
| `registrar-catalog` | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `review-results` | · | · | · | · | · | · | · | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · |
| `rim-center` | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `role-assignment` | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `schedule-manage` | ✅ | ✅ | ✅ | · | ✅ | ✅ | ✅ | · | · | · | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · |
| `semester-opening` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · |
| `statistics` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `student-admission` | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | ✅ | · | · | · | · | · | · | ✅ | · | · | · | · | · | · |
| `student-organization-management` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `student-registry` | ✅ | ✅ | ✅ | ✅ | · | ✅ | · | · | · | · | · | ✅ | · | · | · | · | · | ✅ | · | · | · | · | · | · |
| `subject-catalog` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | ✅ | · | · | · | ✅ | ✅ | ✅ | · | · | · | ✅ | ✅ | · | · | · | · | · |
| `subject-folder-review` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · |
| `subject-folders` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · |
| `superadmin-exam-rooms` | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `surveys-builder` | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `surveys-inbox` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · |
| `syllabus-list` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | ✅ | · | · | · | · | · | · | · | · | · |
| `syllabus-review` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `system-monitoring` | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `system-settings` | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `teacher-intake` | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | ✅ | · | · | · | · | · | · | ✅ | · | · | · | · | · | · |
| `teaching-handover` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `unit-exams` | · | · | · | · | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `workload-approval` | ✅ | ✅ | ✅ | ✅ | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · | · |
| `workload-center` | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · |
| `workload-distribution` | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | ✅ | ✅ | · | · | · | · | · | · | · | · | · | · |
| `workload-overview` | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | ✅ | · | · | · | · | · | · | · | · | · | · | · |
| `workload-visa` | ✅ | ✅ | ✅ | ✅ | · | · | · | · | · | · | · | ✅ | · | · | · | · | · | · | · | · | · | · | · | · |

Cəmi 786 bölmə açılışı.

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
* **Dayandırılmış (`suspended`) təşkilat → sərt çıxış; `pending` → yalnız
  bayraq.**  Aktiv üzvlüyü olan təşkilat `status='active'` deyilsə
  `OrganizationMiddleware` onu `request.blocked_organization` kimi verir
  (sessiyadakı seçilmiş org VƏ — 2026-09-13 access auditi F-11-dən sonra —
  yeganə/bütün təşkilatları dayandırılmış istifadəçi üçün də); sonra
  `SuspendedOrganizationMiddleware` `suspended` (və hər digər qeyri-`pending`)
  statusda sessiyanı bağlayıb login-ə yönləndirir («Təşkilatınız
  dayandırılıb»), `pending` statusda isə yalnız `request.org_pending_approval`
  bayrağını qaldırır.  Bu bayraq **heç bir view-da yazı qapısı deyil** — yalnız
  kabinet xəbərdarlığı (`accounts/profile/_messages.html`) onu oxuyur; yazı
  onsuz da mümkün deyil, çünki `pending` təşkilat heç vaxt
  `request.organization` (aktiv tenant konteksti) olmur.
* **2026-09-14 (sahibin qərarı): `ikt_rehber` şablonu tam wildcard `["*"]`-dır**
  (rektor kimi; səviyyə 95 qalır) və jurnalda BİRBAŞA redaktordur (başqa müəllimin
  jurnalına dərs əlavə edir, bal yazır — `registrar/journal_access.is_direct_editor`).
  Miqrasiya `organizations 0053` mövcud tenantların `ikt_rehber` rolunu `*`-a keçirir.
  Klonda ölçmə: RİM kabineti 63 bölmə, hamısı 200. Aşağıdakı 2026-09-03 cədvəli
  (46 bölmə) bu qərardan ƏVVƏLKİ vəziyyətdir — yenidən ölçmə lazımdır.
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

## Açar-qapı dəyişiklikləri — 2026-09-14 (audit 2026-09-13 `access` F-06)

Cədvəl bölmə GÖRÜNÜRLÜYÜNÜ ölçür; aşağıdakı dəyişikliklər bölmə siyahısını
dəyişmir, bölmənin İÇİNDƏKİ əməlləri açarla qapıya bağlayır (əvvəl bu açarlar
icazə redaktorunda «yalançı düymə» idi — verib/almaq heç nəyi dəyişmirdi):

* **`permission-editor`** (`ikt_rehber`, `rector`, `chair_head`, `dean` görür) —
  rolun icazə dəstini DƏYİŞMƏK (POST) üçün artıq `role.edit` lazımdır (`role.*`
  və `*` əhatə edir); baxış `role.assign`-da qalır. `hr` bölməni onsuz da
  görmürdü; URL ilə POST-u indi rədd olunur.
* **`audit-log`** — «CSV ixrac» düyməsi və `audit:export` üçün `audit.export`
  lazımdır; `audit.view` daşıyan bütün şablonlara (prorektor, imtahan mərkəzi
  rəhbəri/işçisi, RİM rəhbəri/əməkdaşı, HR, Tədris şöbəsi rəhbəri, qəyyum) cüt
  verilib, mövcud rollara miqrasiya 0051 əkir.
* **Təşkilat ayarları** (`organizations:settings`, kabinet bölməsi deyil) —
  səviyyə (≥90) + `org.settings`; POST üçün əlavə `org.edit`.
* **`my-journal` / jurnal detalı** — `journal.view` daşıyan rol əhatəsindəki
  jurnalları YALNIZ-OXU açır və siyahıda görür (heç bir şablona default verilmir).
* **`statistics`** — müəllim/tələbə şəxsi profili `analytics.view_own` tələb edir
  (bütün şablonlarda var); alınarsa `restricted` boş vəziyyət.
* Kataloqdan ÇIXARILDI (funksiya yoxdur): `org.delete`, `role.create`,
  `role.delete`, `grade.override` (= `journal.correct`), `qa.view/review/flag`.
  RİM əməkdaşı, imtahan mərkəzi rəhbəri/işçisi və RİM rəhbəri şablonlarından
  `qa.*` silindi — bu rolların gördüyü bölmələr dəyişmir (QA bölməsi yox idi).

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
