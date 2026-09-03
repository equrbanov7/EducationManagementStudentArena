# EMSArena (PostgreSQL) ↔ myedudb (MariaDB) sxem müqayisəsi

Tarix: 2026-08-21

## Fayllar

| Fayl | Nədir |
|---|---|
| `ems_pg_schema.sql` | EMSArena-nın tam PostgreSQL sxemi (`pg_dump --schema-only`, lokal `emsarena_db`, bütün miqrasiyalar tətbiq olunub) |
| `ems_pg_tables.txt` | EMS cədvəl siyahısı — sütun və sətir sayı ilə |
| `myedu_mysql_schema.sql` | myedudb sxemi (`mysqldump --no-data`, XAMPP-dakı idxal olunmuş baza) |
| `myedu_tables.txt` | myedudb cədvəl siyahısı — sütun və (təxmini) sətir sayı ilə |

Mənbə: `~/Downloads/myedudb.sql` (2.1 GB, phpMyAdmin dump, MariaDB 10.6) — XAMPP-a idxal olunmuş
`myedudb` bazası ilə eyni: hər ikisində **81 cədvəl**.

## Ümumi göstəricilər

| | EMSArena (PG 16) | myedudb (MariaDB) |
|---|---|---|
| Cədvəl | **131** | **81** |
| Xarici açar (FK) | **318** | **0** |
| Unikal məhdudiyyət | 82 | — (yalnız 216 indeks/PK) |
| CHECK məhdudiyyəti | 105 | 0 |
| İndeks | 835 | 216 |
| UUID sütun | 144 | 0 (hər yerdə `int(11)` AUTO_INCREMENT) |
| JSONB sütun | 33 | 0 (`text` içində CSV/serialize) |
| RLS (sətir səviyyəli təhlükəsizlik) | 100 cədvəl / 100 siyasət | yoxdur |
| Trigger | 7 | 2 (`journals_dates_points` üzərində) |
| Kodlaşma | UTF-8 | 79 cədvəl `utf8_bin` (utf8mb3), 2 cədvəl `utf8mb4` |

**Əsas struktur fərqi:** myedudb-də bir dənə də FK yoxdur; əlaqələr tətbiq kodunda saxlanılır və
çox yerdə **vergüllə ayrılmış ID-lər `text` sütununda** yığılıb (məs. `journals.groups_id`,
`journals.students_id`, `ders_cedveli.group_id varchar(255)`, `curricula_plan.lesson_id varchar(250)`).
EMS-də bunlar normal M2M cədvəlləridir. Miqrasiya zamanı bu sətirlərin parçalanması ən çox iş tələb
edən hissə olacaq.

Digər myedudb xüsusiyyətləri:
- Parollar açıq mətndə saxlanılır (`students.show_password char(25)`, `workers.password varchar(50)`).
- Tarixlər bəzən `varchar` (`students.birthday varchar(25)`, `ders_cedveli.from_date varchar(12)`).
- Tenant ayrılması `kollec_or_uni varchar(25)` sətir sahəsi ilə (EMS: `organizations_organization` + RLS).
- Arxiv/versiya cədvəlləri əl ilə: `yekun_old`, `yekun_24_02_2023`, `journals_dates_points_archive`.
- Yeganə DB məntiqi 2 triggerdir: `point_update_counter` (`update_counter`-i artırır) və `update_ss`
  (bal dəyişəndə `update_log`-a yazır) — EMS-də bu, `registrar_lessoncorrection` + `audit_auditlog` ilə edilir.

## Modul üzrə uyğunluq

### 1) Təşkilat / akademik struktur

| myedudb | EMSArena | Qeyd |
|---|---|---|
| `departments` (self-FK `department_id`, `department_types_id`) | `organizations_orgunit` (+ `organizations_organization`, `organizations_institution`) | EMS-də fakültə/kafedra iyerarxiyası tiplənmiş `OrgUnit` ağacıdır |
| `speciality` | `registrar_program` | |
| `groups` (`sector char(2)`, `bak_or_mag`, `eyani_qiyabi`) | `exams_studentgroup` | sektor EMS-də də var |
| `smestr` | `organizations_academicperiod` | EMS: tədris ili + Payız/Yaz/Yay |
| `curricula`, `curricula_tam`, `curricula_plan`, `curricula_plan_patok` | `registrar_curriculum`, `registrar_curriculumsubject` | myedudb-də saat bölgüsü (`saat_muh/sem/lab/prak/aks/as`) plan sətrinin içindədir |
| `lessons` | `registrar_subject` (+ `courses_course`) | |
| `rooms`, `room_types` | `exams_examroom`, `exams_examroomcomputer` | EMS-də otaq **imtahan yönümlüdür**; ümumi auditoriya kataloqu yoxdur |
| `holidays` | — | EMS-də ekvivalent yoxdur |

### 2) İstifadəçilər və rollar

| myedudb | EMSArena |
|---|---|
| `students` (36 sütun, 7 614 sətir) | `auth_user` + `accounts_userprofile` + `organizations_membership` + `registrar_enrollment` |
| `workers` (729) | `auth_user` + `accounts_userprofile` + `organizations_membership` |
| `workers_permits` | `organizations_role` + `auth_permission` |
| `students_login_logs`, `workers_login_logs` | `audit_auditlog` |
| `students_telegram` (48 928), `students_tg_reply` | — (EMS-də Telegram inteqrasiyası yoxdur) |

`students`-dəki maliyyə/qəbul sahələri (`payment_amount`, `payment_type`, `entry_year`, `entry_score`,
`order_no`, `freeze_from/to`, `azadedildi`) EMS-də qismən `registrar_studentacademicrecord`-a düşür —
ödəniş hissəsinin birbaşa qarşılığı yoxdur.

### 3) Jurnal / dərs prosesi — ən böyük data həcmi

| myedudb (sətir) | EMSArena |
|---|---|
| `journals` (13 773) | `registrar_courseoffering` |
| `journals_dates` (42 316), `journals_dates_parsed` (34 272), `journals_dates_added_by_teacher` (378 216) | `registrar_lesson` |
| **`journals_dates_points` (4 979 126)** + `_archive` (773 080) | `registrar_lessonmark` (+ `registrar_lessoncorrection` audit izi ilə) |
| `journals_dates_rooms` (290 598) | `registrar_scheduleslot` |
| `journals_files` (23 085) | — (jurnal fayl əlavəsi EMS-də yoxdur) |
| `ders_cedveli` (433) | `registrar_scheduleslot` |
| `lessons` × `journals` bağı | `registrar_courseoffering` + `registrar_enrollment` |
| `semestr_jurnal`, `journal_exam_joint` (5 041) | `registrar_finalgrade` ↔ `exams_exam` körpüsü |
| `balvereqi_logs` (24 810), `update_log` (252 582) | `audit_auditlog` |

`journals_dates_points`-də `excusable`, `why`, `description`, `update_counter`, `updated_at`, `ga`
sahələri var — EMS-dəki üzrlü qayıb + audited correction axını ilə funksional olaraq üst-üstə düşür.

### 4) Qiymətləndirmə / yekun

| myedudb | EMSArena |
|---|---|
| `yekun` (17 252: `girish`, `imtahanda`, `yekun`, `guzest_girish`, `guzest_artim`, `kesr`) | `registrar_finalgrade` + `registrar_componentscore` + `registrar_assessmentscheme`/`assessmentcomponent` |
| `yekun_old`, `yekun_24_02_2023` | — (EMS-də arxiv cədvəl yox; korreksiya tarixçəsi ayrı modeldədir) |
| `umumi_orta_bal` (1 570) | `registrar_studentacademicrecord` |
| `level_exams`, `level_exams_questions`, `level_exams_topics`, `level_results` | qismən `exams_exam` (səviyyə imtahanı ayrıca tipləşdirilməyib) |

### 5) İmtahan

| myedudb | EMSArena |
|---|---|
| `exam_list` (5 908) | `exams_exam` (32 sütun — daha zəngin: rejim, nəzarət, dil variantları) |
| `exam_questions` (298 488), `exam_question_topics` | `exams_examquestion` + `exams_examquestionoption` |
| `exam_answers` (1 301 676) | `exams_examanswer` (+ `exams_examanswer_selected_options`) |
| `exam_students_start` (28 017) | `exams_examattempt` |
| `allowed_qb` | `exams_questionbank`, `exams_bankquestion`, `exams_bankquestionoption` |
| `imthngrscxsblr` (12 440) | `exams_finalexamticket`, `exams_examstudentpin` |
| `track_student` | `exams_proctoringlog`, `exams_supervisionincident` |
| `turnirs*` (7 cədvəl, hamısı boş) | `live_exam_*` |

EMS-də qarşılığı **olmayan** imtahan tərəfi yoxdur; əksinə EMS-də əlavə var:
kodlaşdırma imtahanları (`exams_coding*`), OCR/mətn çıxarışı (`exams_textextractionjob`),
apellyasiya (`appeals_*`), otaq sessiyası/kompüter kilidi, AI konfiqurasiyası.

### 6) EMS-də olmayan myedudb modulları (boşluqlar)

- **Sillabus (13 cədvəl, ~300 min sətir):** `sillabus`, `sillabus_sem_muh` (130 891), `sillabus_serbest_is`
  (60 372), `sillabus_imtahan_suallari` (21 233), `sillabus_derslikler`, `sillabus_certificates`,
  `sillabus_elmi_maraq`, `sillabus_eldeolunacaq_tecrubeler`, `sillabus_dersin_islenme_formasi`,
  `sillabus_yoxlama_formasi`, `sillabus_qarsilama_mesaji`, `sillabus_tesviri_ve_meqsedi`,
  `sillabus_certificates`. → **EMS-də sillabus modulu yoxdur.**
- **Kitabxana:** `books`, `books_order` (boş).
- **Xidməti müraciət:** `xidmeti_muraciet`, `xidmeti_muraciet_files` (EMS-dəki `appeals_*` yalnız imtahan apellyasiyasıdır).
- **Telegram bot** inteqrasiyası.
- `ferdi_plan`, `niq`, `ntg`, `alerts_workers`, `notifications_groups/logs` — qismən `notifications_*` ilə örtülür.

### 7) EMS-də olan, myedudb-də olmayan

`organizations_*` (çox-tenantlıq + RLS), `audit_auditlog`, `monitoring_incident`/`securityevent`,
`appeals_*`, `assignments_*`, `projects_*`, `labs_*`, `blog_*`, `contact_*`, `ai_assistant_*`,
`trial_exams_*`, `accounts_emailotp` (OTP), `registrar_*correction` (audit izli düzəlişlər),
`registrar_kollokviumwindow`/`kollokviumextragrant`, `registrar_rubric*`, `exams_examroomsession`.

## Sxemi yenidən çıxarmaq (əmrlər)

PostgreSQL (konteyner işləməlidir):

```bash
docker start emsarena-postgres && docker exec emsarena-postgres pg_dump -U emsarena_user -d emsarena_db --schema-only --no-owner --no-privileges > docs/db-compare/ems_pg_schema.sql
```

MariaDB (XAMPP):

```bash
/Applications/XAMPP/xamppfiles/bin/mysqldump -u root --no-data --skip-comments myedudb > docs/db-compare/myedu_mysql_schema.sql
```
