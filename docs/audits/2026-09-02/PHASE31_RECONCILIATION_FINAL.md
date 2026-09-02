# FAZA 31 — Təmirdən SONRAKI yekun uzlaşma (final reconciliation)

**Tarix:** 2026-09-02 · **Yalnız-oxu.** Heç bir yazma əməliyyatı aparılmadı.
**Hədəf:** QA klonu `emsarena_rehearsal_a0d170000901` (`emsarena-staging-pg`, :55433) — FAZA 27
təmizliyindən SONRA ölçülüb, yəni rəqəmlər reqressiya obyektlərindən təmizdir.
**Mənbə:** `emsarena-legacy-source-rehearsal` (MariaDB, `myedudb`, `@@GLOBAL.read_only = 1`) —
port **sabit deyil**, bu icrada `127.0.0.1:50200` (bax PHASE1 §4.7).

Üç müstəqil mənbədən oxundu və çarpaz yoxlandı:
1. **mənbə MariaDB** — xam sətir sayları;
2. **köçürmə dəftəri** `legacy_import_legacyentitymap` — köçürmənin *nəyi saydığı* və hər sətrin
   `migrated / skipped / quarantined` taleyi (bu, «Missing» sütunu üçün AVTORİTETDİR);
3. **hədəf cədvəllər** — bugünkü faktiki vəziyyət (təmirlərdən sonra).

---

## 1. Yekun varlıq cədvəli

| Varlıq | Köhnə (mənbə) | Yeni (hədəf) | Xəritələnib | Çatmayan | Dublikat | Sınıq əlaqə | İzah |
|---|---:|---:|---:|---:|---:|---:|---|
| **Tələbə hesabı** | **7 816** | **7 816** | 7 716 (dəftər) + 100 (təmir) | **0** | 0 | — | P0-2 tam bağlandı: `legacy_repair_missing_accounts` 100 hesab yaratdı (PHASE1_MIGRATION_REPAIRS §4.5) |
| Tələbə akademik qeydi (SAR) | 7 816 | **7 703** | 7 703 | **113** | 0 | — | 13 = staged kimlik (dəftər `student_record: skipped 13`); **100 = təmirlə yaradılan hesablara SAR yazılmayıb → PHASE27 R-9** |
| — aktiv tələbə üzvlüyü | 7 616 (`azadedildi=0`) | **7 606** | — | 10 | 0 | — | 13 staged (deaktiv üzvlük) − 3 fərq; P0-1 təmiri arxivi 2 490 → 199-a saldı |
| — arxiv / alumni | 200 (`azadedildi=1`) | **199** | — | 1 | 0 | — | 1 sətir kimlik karantinində (PHASE1 §4.1) |
| **Müəllim / işçi** | **729** | **729** | 715 (dəftər) + 14 (təmir) | **0** | 0 | 0 | `teacher` üzvlüyü 732 (729 + 3 QA hesabı); `workers_without_teacher_membership = 0` |
| Fakültə | 13 | **13** | 13 | 0 | 0 | 0 | mənbədə `departments` 31 sətirdir → 13 fakültə + 18 kafedra |
| Kafedra | 18 | **18** | 18 | 0 | 0 | 0 | — |
| İxtisas | 83 | **83** | 83 | 0 | 0 | 0 | — |
| Proqram | — | **101** | 101 | 0 | 0 | 0 | 83 ixtisasdan 101 proqram (səviyyə/dil bölmələri) |
| **Qrup** | **766** | **766** | 766 | 0 | **8 ad** | 0 | 8 ad təkrarı — ad unikal deyil, `path` unikaldır; defekt deyil |
| **Fənn** | **2 521** (`lessons`) | **2 501** | 2 521 | 0 | **9 ad** | 0 | 20 sətir birləşdirildi (kod eyni); 9 ad hələ təkrarlanır — RECOVERED_SUMMARIES §1 ilə eyni |
| Kurikulum | 126 | **211** | 125 | 0 (1 karantin) | 0 | **119 boşdur** | Hədəf > mənbə: köçürmə proqram × qəbul ili üzrə bölür; **3 595 SAR plan sətri olmayan kurikuluma bağlıdır** (ISSUES P1-8, mənbədə plan yoxdur) |
| Kurikulum sətri | 3 424 | **4 681** | 3 161 | 0 | 0 | 263 karantin | eyni bölmə effekti |
| **Akademik dövr** | **13** | **16** | 13 | 0 | 0 | — | +3 = 2026/2027 Payız/Yaz/Yay (P0-3 təmiri) |
| — cari dövr | `2025/2026 **Yay**` (`is_current='1'`) | **`2025/2026 Yaz`** | — | — | — | **UYĞUN DEYİL (qəsdən)** | PHASE1 §4.3: legacy bayraq 10 açılışlı boş semestri göstərir; qərar sənədlidir. **Amma hər ikisi artıq bitib → PHASE27 R-1** |
| **Açılış (offering)** | 13 875 (`journals`) · dəftərdə 16 029 | **11 118** | 13 987 | 1 866 skip + 176 karantin | 0 | **1 168 müəllimsiz** | `journals`-un 1 866-sı `fake=1` (mənbədə 12 009 real jurnal); müəllimsiz 1 203 → **1 168** (təmir 45-ini bağladı) |
| **Yazılış** | 199 454 (dəftər) | **148 020** | 181 094 | **18 253 skip** + 107 karantin | 0 | 0 orfan | skip səbəbi: arxiv/silinmiş tələbə və `fake` jurnal sətirləri; hədəfdəki fərq (181 094 → 148 020) per-qrup jurnal bölgüsündən doğur |
| **Dərs (lesson)** | 379 215 (`journals_dates_added_by_teacher`) · dəftərdə 440 124 | **293 070** | 293 070 | **146 992 skip** + 62 karantin | 0 | 0 orfan | J12 `journal_lesson_recovery` fazası **işlədilməyib** (ISSUES P1-5) — bu, +11 607 dərs deməkdir |
| **Dərs balı (LessonMark)** | 5 070 824 (RECOVERED_SUMMARIES §1) · xam `journals_dates_points` 5 135 289 | **3 711 153** | — | izahsız **0** | 0 | 0 orfan | fərq tam olaraq skip edilən dərslərə və `fake` jurnallara düşür; qayıb sətri 507 734 |
| **Komponent balı** | 701 005 (RECOVERED_SUMMARIES §1) | **686 477** | — | izahsız **0** | 0 | 0 orfan | 538 457 köçürülmüş + 148 020 generik (yazılış başına) |
| **Yekun qiymət (FinalGrade)** | `yekun` 17 194 · imtahan `im/im2` 134 834 | **114 021** | 8 366 (`journal_finals`) | 1 658 skip + 57 karantin | 0 | 0 orfan | `is_published` **0/114 021** — ölü sütun, əsl bayraq `AssessmentScheme.is_published` = **11 105 / 11 116** (ISSUES P1-9) |
| Qiymətləndirmə sxemi | — | **11 116** | 13 976 | 11 skip | 0 | 0 | |
| Qiymətləndirmə komponenti | — | **51 618** | — | — | 0 | 0 | |
| Legacy bal sübutu (`LegacyGradeFact`) | 169 231 | **169 231** | 169 231 | **0** | 0 | 0 | bal-sübutu itkisi **sıfır** |
| Cədvəl slotu | 433 (`ders_cedveli`) | **1** | — | — | — | — | cədvəl **köçürülmür** (qərar); 1 sətir PHASE23 fixture-idir |
| Otaq | 158 (`rooms`) | **0** | — | **158** | — | — | otaq reyestri köçürülməyib → PHASE27 **R-5** |
| Üzvlük (rol üzrə) | — | student 7 606 aktiv / 13 deaktiv · teacher 732 · alumni 199 · digər 12 | — | — | 0 | 0 | |
| `access_state` | — | active **8 353** · archived **199** · staged **13** | — | — | — | — | P0-1 təmiri: archived 2 490 → 199, active 5 948 → 8 239 → (QA hesabları ilə) 8 353 |
| `birth_date` dolu | 2 252 (mənbədə) | **2 175** | — | 77 | — | — | qalanı mənbədə pozuq tarixdir |
| `gender` dolu | 2 877 (mənbədə) | **1 693** | — | 1 184 | — | — | tanınmayan dəyərlər ötürülmür |
| Yer-tutucu e-poçt | — | **114** | — | — | 0 | — | `…@placeholder.invalid`; 14 e-poçt toqquşması + 86 etibarsız + 14 işçi |

### Bütövlük yoxlamaları (hamısı sıfır)

| yoxlama | nəticə |
|---|---:|
| orfan yazılış (açılışsız) | **0** |
| orfan `LessonMark` (dərssiz) | **0** |
| orfan `ComponentScore` / `FinalGrade` (yazılışsız) | **0** / **0** |
| `SAR.group_id IS NULL` / `curriculum_id IS NULL` | **0** / **0** |
| FİN dublikatı | **0** |
| istifadəçi adı dublikatı (hərf-həssassız) | **0** |
| real e-poçt dublikatı | **0** |
| profili olmayan istifadəçi | 3 (`blog_system`, `demo_commenter_1/2` — platforma seed-ləri, köçürmə deyil) |

---

## 2. Sual-cavab

### «Bütün tələbələr köçürülüb?»
**Hesab səviyyəsində — BƏLİ.** Mənbədə 7 816 tələbə var, hədəfdə `myedu.student.*` **7 816**.
Köçürmə 7 716-nı gətirdi, `legacy_repair_missing_accounts` qalan 100-ü (14 e-poçt toqquşması
karantini + 86 etibarsız e-poçt) bağladı; ikinci icra **0** sətir yaratdı (idempotent).

**Akademik qeyd səviyyəsində — XEYR (PHASE27 R-9).** SAR sayı **7 703**-dür; 113 tələbənin
akademik qeydi yoxdur: 13-ü `staged` (qəsdən), **100-ü isə məhz təmirlə yaradılan hesablardır**.
Onların qrupu, proqramı və kurikulumu olmadığı üçün kabinet boş açılır. Bu, PHASE21 §4.3-də
düzəldilən «qrupsuz tələbə» kohortudur — UI artıq onları «müəllim» kimi etiketləmir, amma
**datası hələ də əskikdir**.

### «Bütün müəllimlər köçürülüb?»
**BƏLİ.** 729 / 729. 715-i köçürmə, 14-ü təmir gətirdi; hamısının **aktiv `teacher` üzvlüyü var**
(`workers_without_teacher_membership = 0`). Təmir həmçinin 45 müəllimsiz açılışa müəllim bağladı
(1 203 → **1 168**). Qalan 1 168 müəllimsiz açılış mənbədə də müəllimsizdir.

### «Əlaqələr sağlamdır?»
**BƏLİ.** Yuxarıdakı 8 bütövlük yoxlamasının hamısı sıfırdır: nə orfan yazılış, nə orfan bal,
nə qrupsuz/kurikulumsuz SAR, nə də açar dublikatı var. İki *izahlı* struktur zəifliyi qalır:
* **119 boş kurikulum** və onlara bağlı **3 595 SAR** — mənbədə tədris planı yoxdur (ISSUES P1-8, DEFERRED);
* **1 168 müəllimsiz açılış** — mənbədə də belədir.

Bunlara PHASE27-də tapılan bir struktur uyğunsuzluğu əlavə olunur:
**766 qrupun 766-sının valideyni `specialty`-dir; heç bir kafedranın qrup övladı yoxdur** →
sillabus `chair_unit`-i heç vaxt kafedra olmur (PHASE27 **R-2**).

### «Köçürülmüş istifadəçilər sistemə girə bilir? Bu gün neçəsi girə bilər?»

**BU GÜN: 0 köçürülmüş istifadəçi öz-özünə girə bilmir.**

| ölçü | say |
|---|---:|
| Hesabı olan (cəmi) | 8 568 |
| **İstifadə edilə bilən paroluk hesab** | **25** |
| — onlardan QA/test hesabı | 20 (`qa.*`, `staging_admin`) |
| — onlardan **köçürülmüş** hesab | **5** (`myedu.student.4`, `.200`, `.5925`, `myedu.worker.85`, `.459`) — hamısına parolu **audit agentləri** verib |
| «unusable» parollu hesab (`!`-prefiks) | **8 543** |
| `password_change_required = True` | 8 410 |
| real görünüşlü e-poçtu olan | 8 455 |
| `email_verified` | 34 |

**Kök səbəb (empirik təsdiq).** `CustomPasswordResetForm.get_users()` Django-nun
`PasswordResetForm.get_users()`-una söykənir, o isə `has_usable_password()` olmayan hesabları
**süzür**. Ona görə köçürülmüş istifadəçi üçün `/accounts/password-reset/`:

```
myedu.student.5  (alahverdiyevafeddin2350@gmail.com) → POST 302 /password-reset/done/ · outbox = 0
myedu.worker.19  (rena.haciyeva@wcu.edu.az)          → POST 302 /password-reset/done/ · outbox = 0
```

— yəni istifadəçi «e-poçtunuza göndərdik» səhifəsini görür, **amma heç nə göndərilmir**.
Girişin yeganə açıq yolu: RİM mərkəzindən **tək-tək** parol təyini. Toplu buraxılış yolu yoxdur.
→ PHASE27 **R-8** (canlıya çıxış üçün P0 namizədi).

---

## 3. SQL-lər (açılan bloklar)

<details>
<summary>Mənbə (MariaDB) — xam saylar</summary>

```sql
-- port: docker port emsarena-legacy-source-rehearsal   (bu icrada 50200)
SELECT 'students', COUNT(*) FROM students;                              -- 7816
SELECT 'students_active', COUNT(*) FROM students WHERE azadedildi=0;    -- 7616
SELECT 'students_released', COUNT(*) FROM students WHERE azadedildi=1;  -- 200
SELECT 'workers', COUNT(*) FROM workers;                                -- 729
SELECT 'departments', COUNT(*) FROM departments;                        -- 31 (13 fakültə + 18 kafedra)
SELECT 'speciality', COUNT(*) FROM speciality;                          -- 83
SELECT 'groups', COUNT(*) FROM `groups`;                                -- 766
SELECT 'subjects(lessons)', COUNT(*) FROM lessons;                      -- 2521
SELECT 'curricula', COUNT(*) FROM curricula;                            -- 126
SELECT 'curricula_plan', COUNT(*) FROM curricula_plan;                  -- 3424
SELECT 'semestr_jurnal', COUNT(*) FROM semestr_jurnal;                  -- 13
SELECT id,name,type,is_current FROM semestr_jurnal ORDER BY id;         -- cari = id 13 «2025/2026 Yay»
SELECT 'journals', COUNT(*) FROM journals;                              -- 13875
SELECT 'journals_real', COUNT(*) FROM journals WHERE fake=0;            -- 12009
SELECT 'lesson_rows', COUNT(*) FROM journals_dates_added_by_teacher;    -- 379215
SELECT 'points', COUNT(*) FROM journals_dates_points;                   -- 5135289
SELECT 'points_archive', COUNT(*) FROM journals_dates_points_archive;   -- 776033
SELECT 'yekun', COUNT(*) FROM yekun;                                    -- 17194
SELECT 'ders_cedveli', COUNT(*) FROM ders_cedveli;                      -- 433
SELECT 'rooms', COUNT(*) FROM rooms;                                    -- 158
```
</details>

<details>
<summary>Köçürmə dəftəri — hər varlığın taleyi (AVTORİTET «Çatmayan» mənbəyi)</summary>

```sql
SELECT entity_type,
       COUNT(*)                                        AS source_rows,
       COUNT(*) FILTER (WHERE state='migrated')        AS migrated,
       COUNT(*) FILTER (WHERE state='skipped')         AS skipped,
       COUNT(*) FILTER (WHERE state='quarantined')     AS quarantined
FROM legacy_import_legacyentitymap
GROUP BY 1 ORDER BY 1;
```

```
 academic_period          13      13        0       0
 course_offering       16029   13987     1866     176
 curriculum_plan         126     125        0       1
 curriculum_plan_row    3424    3161        0     263
 department_unit          31      31        0       0
 group_unit              766     766        0       0
 journal_components    11238    9426     1811       1
 journal_enrollment   199454  181094    18253     107
 journal_entry_scores  13987   13759      228       0
 journal_finals        10081    8366     1658      57
 journal_lock          13987   13976       11       0
 journal_marks         12184   10090     2094       0
 journal_reconcile     17199       0      553   16646
 journal_selfwork      11861   10156     1705       0
 lesson               440124  293070   146992      62
 lesson_subject         2521    2521        0       0
 speciality_program      101     101        0       0
 speciality_unit          83      83        0       0
 student                7816    7716       84      16
 student_placement      7716       0     7703      13
 student_record         7716    7703       13       0
 worker                  729     715        2      12
 worker_materialisation  715     715        0       0
```
</details>

<details>
<summary>Hədəf (PostgreSQL klonu) — bugünkü saylar</summary>

```sql
SELECT 'auth_user' k, COUNT(*)::text v FROM auth_user
UNION ALL SELECT 'students(myedu.student.*)', COUNT(*)::text FROM auth_user WHERE username LIKE 'myedu.student.%'
UNION ALL SELECT 'workers(myedu.worker.*)',   COUNT(*)::text FROM auth_user WHERE username LIKE 'myedu.worker.%'
UNION ALL SELECT 'sar',                       COUNT(*)::text FROM registrar_studentacademicrecord
UNION ALL SELECT 'subjects',                  COUNT(*)::text FROM registrar_subject
UNION ALL SELECT 'offerings',                 COUNT(*)::text FROM registrar_courseoffering
UNION ALL SELECT 'offerings_no_instructor',   COUNT(*)::text FROM registrar_courseoffering WHERE instructor_id IS NULL
UNION ALL SELECT 'enrollments',               COUNT(*)::text FROM registrar_enrollment
UNION ALL SELECT 'lessons',                   COUNT(*)::text FROM registrar_lesson
UNION ALL SELECT 'lesson_marks',              COUNT(*)::text FROM registrar_lessonmark
UNION ALL SELECT 'component_scores',          COUNT(*)::text FROM registrar_componentscore
UNION ALL SELECT 'final_grades',              COUNT(*)::text FROM registrar_finalgrade
UNION ALL SELECT 'curricula',                 COUNT(*)::text FROM registrar_curriculum
UNION ALL SELECT 'curriculum_rows',           COUNT(*)::text FROM registrar_curriculumsubject
UNION ALL SELECT 'periods',                   COUNT(*)::text FROM organizations_academicperiod
UNION ALL SELECT 'period_current', COALESCE((SELECT academic_year||' '||name FROM organizations_academicperiod WHERE is_current),'(yoxdur)')
UNION ALL SELECT 'legacygradefact',           COUNT(*)::text FROM registrar_legacygradefact
UNION ALL SELECT 'assessmentscheme_published',COUNT(*)::text FROM registrar_assessmentscheme WHERE is_published
UNION ALL SELECT 'finalgrade_published',      COUNT(*)::text FROM registrar_finalgrade WHERE is_published
ORDER BY 1;
```

```
 assessmentscheme_published | 11105      lesson_marks            | 3711153
 auth_user                  | 8568       lessons                 | 293070
 component_scores           | 686477     offerings               | 11118
 curricula                  | 211        offerings_no_instructor | 1168
 curriculum_rows            | 4681       period_current          | 2025/2026 Yaz
 enrollments                | 148020     periods                 | 16
 final_grades               | 114021     sar                     | 7703
 finalgrade_published       | 0          students(myedu.student.*)| 7816
 legacygradefact            | 169231     subjects                | 2501
                                         workers(myedu.worker.*) | 729
```
</details>

<details>
<summary>Üzvlük · access_state · demoqrafiya · e-poçt · parol</summary>

```sql
SELECT 'access_state:'||COALESCE(p.access_state,'(null)'), COUNT(*)::text
  FROM accounts_userprofile p GROUP BY 1
UNION ALL
SELECT 'role:'||r.name||CASE WHEN m.is_active THEN ' (aktiv)' ELSE ' (deaktiv)' END, COUNT(*)::text
  FROM organizations_membership m JOIN organizations_role r ON r.id = m.role_id
 GROUP BY r.name, m.is_active
ORDER BY 1;

SELECT 'birth_date_filled',  COUNT(*) FROM accounts_userprofile WHERE birth_date IS NOT NULL;     -- 2175
SELECT 'gender_filled',      COUNT(*) FROM accounts_userprofile WHERE gender NOT IN ('','unspecified'); -- 1693
SELECT 'placeholder_email',  COUNT(*) FROM auth_user WHERE email LIKE '%@placeholder.invalid';    -- 114
SELECT 'usable_password',    COUNT(*) FROM auth_user WHERE password NOT LIKE '!%' AND password<>''; -- 25
SELECT username FROM auth_user WHERE password LIKE 'pbkdf2%' ORDER BY username;                   -- 25 sətrin hamısı QA/audit hesabıdır
```
</details>

<details>
<summary>Bütövlük / dublikat / sınıq əlaqə</summary>

```sql
SELECT 'dup_fin', COUNT(*) FROM (SELECT fin FROM accounts_userprofile
        WHERE fin IS NOT NULL AND fin<>'' GROUP BY 1 HAVING COUNT(*)>1) x;                 -- 0
SELECT 'dup_username_ci', COUNT(*) FROM (SELECT lower(username) FROM auth_user
        GROUP BY 1 HAVING COUNT(*)>1) x;                                                   -- 0
SELECT 'dup_email_real', COUNT(*) FROM (SELECT lower(email) FROM auth_user
        WHERE email<>'' AND email NOT LIKE '%placeholder.invalid' GROUP BY 1 HAVING COUNT(*)>1) x; -- 0
SELECT 'dup_subject_name', COUNT(*) FROM (SELECT lower(name) FROM registrar_subject
        GROUP BY 1 HAVING COUNT(*)>1) x;                                                   -- 9
SELECT 'dup_group_name', COUNT(*) FROM (SELECT lower(name) FROM organizations_orgunit
        WHERE unit_type='group' GROUP BY 1 HAVING COUNT(*)>1) x;                           -- 8
SELECT 'orphan_enrollment', COUNT(*) FROM registrar_enrollment e
        LEFT JOIN registrar_courseoffering o ON o.id=e.offering_id WHERE o.id IS NULL;      -- 0
SELECT 'orphan_lessonmark', COUNT(*) FROM registrar_lessonmark lm
        LEFT JOIN registrar_lesson l ON l.id=lm.lesson_id WHERE l.id IS NULL;               -- 0
SELECT 'empty_curricula', COUNT(*) FROM registrar_curriculum c
        WHERE NOT EXISTS (SELECT 1 FROM registrar_curriculumsubject s WHERE s.curriculum_id=c.id); -- 119
SELECT 'sar_on_empty_curriculum', COUNT(*) FROM registrar_studentacademicrecord r
        JOIN registrar_curriculum c ON c.id=r.curriculum_id
        WHERE NOT EXISTS (SELECT 1 FROM registrar_curriculumsubject s WHERE s.curriculum_id=c.id); -- 3595
SELECT 'students_without_sar', COUNT(*) FROM auth_user u
        WHERE u.username LIKE 'myedu.student.%'
          AND NOT EXISTS (SELECT 1 FROM registrar_studentacademicrecord r WHERE r.student_id=u.id); -- 113
SELECT 'workers_without_teacher_membership', COUNT(*) FROM auth_user u
        WHERE u.username LIKE 'myedu.worker.%'
          AND NOT EXISTS (SELECT 1 FROM organizations_membership m
                          JOIN organizations_role r ON r.id=m.role_id
                          WHERE m.user_id=u.id AND r.name='teacher');                       -- 0
SELECT 'qrup valideyn tipi', parent_id IS NULL, COUNT(*) FROM organizations_orgunit
        WHERE unit_type='group' GROUP BY 2;   -- 766 qrupun hamısının valideyni specialty-dir
```
</details>

---

## 4. Gözlənilən boşluqların sənəd istinadları

| boşluq | izah edən sənəd |
|---|---|
| 113 SAR əskiyi (13 staged + **100 təmir hesabı**) | dəftər `student_record: skipped 13` + **PHASE27 R-9 (YENİ)** |
| 18 253 yazılış + 146 992 dərs skip | per-qrup jurnal bölgüsü + `fake=1` jurnallar — RECOVERED_SUMMARIES §1, §6 |
| +11 607 dərs / +161 775 bal əskiyi | **J12 `journal_lesson_recovery` işlədilməyib** — ISSUES P1-5, RECOVERED_SUMMARIES §6 |
| 199 arxiv üzvlüyü | P0-1 təmiri: `azadedildi=1` yeganə arxiv meyarıdır — PHASE1_MIGRATION_REPAIRS §P0-1, §4.1 |
| 1 866 skip açılış | mənbədə `journals.fake=1` (13 875 − 12 009 = 1 866) |
| 16 646 karantin `journal_reconcile` | bal toqquşmaları — BAL_PROBLEMLERI.md, ISSUES P2-6 |
| 119 boş kurikulum / 3 595 SAR | mənbədə plan yoxdur — ISSUES P1-8 (DEFERRED) |
| `FinalGrade.is_published = 0` | ölü sütun; əsl bayraq `AssessmentScheme.is_published` — ISSUES P1-9 (WONTFIX-izah) |
| cari dövr ≠ legacy `is_current` | qəsdli qərar — PHASE1_MIGRATION_REPAIRS §4.3 (**amma bax PHASE27 R-1**) |
| 114 yer-tutucu e-poçt | kimlik fazası — PHASE1_MIGRATION_REPAIRS §P0-2 |
| 158 otaq köçürülməyib | **PHASE27 R-5 (YENİ)** |
| cədvəl (433 slot) köçürülməyib | köçürmə əhatəsindən kənar (qərar) |
