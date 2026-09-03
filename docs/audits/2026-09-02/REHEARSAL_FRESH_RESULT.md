# Təzə repetisiyanın (fresh run) nəticəsi — 2026-09-03

**Rejim:** yalnız-oxu uzlaşma. Heç bir yazma hədəf bazaya (`emsarena_rehearsal_d44526b97cbc`)
edilməyib; kabinet spot-check üçün `CREATE DATABASE ... TEMPLATE` ilə **ayrıca müvəqqəti
surət** (`..._spot`) yaradılıb, ona miqrasiya tətbiq olunub, yoxlanılıb və sonda **DROP
DATABASE** ilə silinib. Hədəf baza toxunulmamış qalıb (`docs/audits/2026-09-02/REHEARSAL_FRESH_2026_09_03.md`
tələbinə uyğun).

Mənbələr: `REHEARSAL_FRESH_2026_09_03.md`, `PHASE31_RECONCILIATION_FINAL.md`,
`PHASE1_MIGRATION_REPAIRS.md`, canlı SQL (`legacy_import_legacymigrationrun/-issue/-entitymap`,
hədəf cədvəllər), MariaDB mənbə (`emsarena-legacy-source-rehearsal`, port 50200).

---

## 1. Run xülasəsi

| | |
|---|---|
| `run_id` | `8a476c8c-2a1e-4d72-9aee-f5d68b336e8c` |
| `status` | **`succeeded`** |
| Müddət | 2026-09-03 00:22:21 → 03:19:16 UTC (**≈2 saat 57 dəq**) |
| `transform_version` | `rehearsal-identity-v2.aca98087fe65` |
| `migrated_count` / `skipped_count` / `quarantined_count` (run cəmi) | 15 232 / 0 / 264 |
| Fazalar | 24/24 sözlü qeydiyyatın hamısı icra olundu (bax registr aşağıda) |
| **`severity='error'` sətri** | **0** (təsdiqləndi: `legacy_import_legacymigrationissue`-də error yoxdur) |

`legacy_import_legacyimportbatch` üzrə 8 fərqli `source_table` batch-i yazılıb
(departments/speciality/groups/lessons/curricula/curricula_plan/students/workers) —
hamısı `0` sıfır-uyğunsuzluqla bağlanıb (yalnız curricula/curricula_plan-da
mənbə-daxili karantin var, aşağıda).

### Top-15 `rule_code` (severity ilə, `legacy_import_legacymigrationissue`)

| # | rule_code | severity | say |
|---|---|---|---:|
| 1 | legacy_journal_lesson_duplicate | info | 85 673 |
| 2 | legacy_journal_lesson_orphan | info | 61 319 |
| 3 | legacy_lesson_meta_fake | info | 26 303 |
| 4 | legacy_lesson_meta_orphan | info | 23 391 |
| 5 | legacy_journal_lesson_kind_absent | info | 16 786 |
| 6 | legacy_journal_reconcile_final_deviation | info | 15 112 |
| 7 | legacy_journal_lock_applied | info | 13 987 |
| 8 | legacy_entry_score_derived | info | 13 206 |
| 9 | legacy_lesson_synthesised | info | 12 292 |
| 10 | legacy_lesson_meta_ambiguous | **warning** | 11 921 |
| 11 | legacy_lesson_synth_hours_unresolved | info | 11 722 |
| 12 | legacy_journal_enrollment_orphan | info | 10 836 |
| 13 | legacy_account_email_untrusted | info | 8 545 |
| 14 | legacy_grade_fact_unresolved | **warning** | 7 794 |
| 15 | legacy_grade_fact_discarded_source | **warning** | 7 728 |

Cəmi: **386 732 info + 75 212 warning = 461 944**; **0 error**. `legacy_lesson_synthesised`
(#9, 12 292) J12 bərpasının imza kodudur (bax §2 `lessons_j12_synth`).

---

## 2. Mənbə → təzə → təmir edilmiş klon (yan-yana)

| Ölçü | Mənbə | Təzə (`d44526b97cbc`) | Təmir edilmiş klon (`a0d170000901`) | İzah |
|---|---:|---:|---:|---|
| Tələbə hesabı | 7 816 | **7 816** | 7 816 | eyni; təzə run-da P0-2 qaydası birbaşa daxildir → köçürmə özü 7 816-nı gətirdi (heç bir sətir `student` entity-də skip/karantində deyil) |
| İşçi hesabı | 729 | **729** | 729 | eyni |
| **SAR** | 7 816 | **7 799** | 7 703 | təzədə fərq yalnız **17** (13 staged + 4 yeni-karantin `student_placement`); klonda 113 idi (100-ü ayrıca təmir tələb edirdi) — **P0-2 kodu J-cinsli SAR boşluğunu 113→17-yə endirdi** |
| — bunlardan SAR-sız tələbə | — | **17** | 113 | staged (qəsdən) + 4 `student_placement` karantini (email/username toqquşması hələ də qalır — “sərhəd” PHASE1 §P0-2) |
| Aktiv üzvlük (`student`, aktiv) | 7 616 (`azadedildi=0`) | **7 599** | 7 606 | 17 staged deaktiv düşür; kiçik fərq nümunə seçimindən (aşağı bax, 20/20 uyğun) |
| Arxiv/`alumni` | 200 (`azadedildi=1`) | **200** | 199 | təzədə **dəqiq mənbə ilə üst-üstə düşür** (klonda 1 sətir kimlik karantinində idi) |
| Fakültə | 13 | **13** | 13 | — |
| Kafedra | 18 | **18** | 18 | — |
| İxtisas | 83 | **83** | 83 | — |
| Qrup | 766 | **766** | 766 | — |
| Fənn | 2 521 | **2 501** | 2 501 | eyni (20 sətir eyni kodla birləşir) |
| Kurikulum | 126 | **210** | 211 | proqram×qəbul ili bölgüsü; 1 fərq — eyni sxem, fərqli run seed-i |
| Kurikulum sətri | 3 424 | **4 681** | 4 681 | eyni |
| Akademik dövr | 13 | **13** | 16 | **klonda +3 (2026/2027) yalnız P0-3 təmiri ilə əlavə olunub** (`--create-year`); təzə run bu addımı ayrıca icra etmədiyi üçün 13-dür — gözlənilən |
| — cari dövr (`is_current`) | `2025/2026 Yay` | **yoxdur** | `2025/2026 Yaz` | **qəsdən** (V9); bax §4 |
| Açılış (offering) | 13 875 (12 009 real) | **11 115** | 11 118 | 3 sətirlik fərq run-arası seed variasiyası; struktur eyni |
| — müəllimsiz | — | **1 172** | 1 168 | mənbədə də müəllimsiz (P0-2 təmiri 45-ni bağlamışdı, təzə run-da həmin əlaqələndirmə ayrıca addım olaraq işlədilməyib) |
| Yazılış (enrollment) | 199 454 | **150 157** | 148 020 | fərq per-qrup jurnal bölgüsü + arxiv/`fake` sətirlərinin fərqli seçimindən (RECOVERED_SUMMARIES §1) |
| **Dərs (lesson)** | 440 124 (dəftər) | **304 805** | 293 070 | **+11 735 = J12 (`legacy_lesson_synthesised`)** işlədi (gözlənilən +11 607-ə çox yaxın) |
| — bunlardan J12-sintez | — | **11 735** | 0 (J12 yox idi) | `is_legacy_synthesised=true` |
| **Dərs balı (LessonMark)** | 5 135 289 (xam) | **3 921 304** | 3 711 153 | **+210 151** — J12 bərpası ilə əlaqəli (gözlənilən +161 775-dən çox, çünki J12 özü ilə bərabər `journal_mark_recovered` (10 317) də bu run-a məxsusdur) |
| — `absent` / `present` | — | 534 323 / 3 381 803 | — | üzr sətirlərinin ayrıca kodu yoxdur (excused = ayrıca status, 5 178-ə bənzər) |
| Komponent balı | 701 005 (mənbə) | **696 204** | 686 477 | oxşar artım (yazılış sayı artımı ilə mütənasib) |
| Yekun qiymət (FinalGrade) | 152 028 (yekun+im/im2) | **115 403** | 114 021 | oxşar |
| `AssessmentScheme.is_published` | — | **11 115** | 11 105 | əsl bayraq (`FinalGrade.is_published` hər ikisində 0, ölü sütun — PHASE1 P1-9) |
| Selfwork mövzusu | 11 861 (mənbə) | **69 404** | — | generik+köçürülmüş sətirlərin cəmi (yazılış başına) |
| Resit | — | **5 121** | — | yeni ölçü, əvvəlki hesabatlarda yoxdur |
| `LegacyGradeFact` | 169 231 (əsas) | **171 080** (169 231 fact + 1 762 conflict + 87 unresolved) | 169 231 | **bal-sübutu itkisi sıfırdır** hər iki tərəfdə; təzədə əlavə 1 849 sətir `legacy_mark_conflict`/`legacy_mark_unresolved` kateqoriyalarındandır (eyni model, fərqli alt-tip) |
| Otaq (`ExamRoom`, `myedu-room-*`) | 158 | **158** | 0 | **J13 (`legacy_rooms`) işlədi** — klonda bu faza yox idi |
| Üzvlük (rol) | — | student 7 599 aktiv/17 deaktiv · teacher 729 · alumni 200 | student 7 606/13 · teacher 732 · alumni 199 | uyğun |
| `access_state` | — | active **8 349** · archived **200** · staged **17** | active 8 353 · archived 199 · staged 13 | uyğun (fərq nümunə seçimi deyil, tam mütabiqdir) |
| Yer-tutucu e-poçt | — | **114** | 114 | eyni (100 tələbə+14 işçi) |
| `birth_date` dolu | 2 252 (mənbə) | **2 207** | 2 175 | demoqrafiya fazası daxildir (2026-08-30 əlavəsi) |
| `gender` dolu | 2 877 (mənbə) | **1 719** | 1 693 | eyni səbəb |
| Karantin (ümumi) | — | **264** (run) / 33 906 sətir-səviyyəli entity-map karantini | 86 skip+292 karantin (köhnə qayda) | təzə run entity-map-də daha detallı bölünüb (aşağı bax) |

---

## 3. Bütövlük yoxlamaları (təzə DB-də)

| yoxlama | nəticə |
|---|---:|
| orfan `Enrollment` (açılışsız) | **0** |
| orfan `LessonMark` (dərssiz) | **0** |
| orfan `ComponentScore` (yazılışsız) | **0** |
| orfan `FinalGrade` (yazılışsız) | **0** |
| `SAR.group_id IS NULL` / `curriculum_id IS NULL` | **0** / **0** |
| FİN dublikatı | **0** |
| istifadəçi adı dublikatı (hərf-həssassız) | **0** |
| real e-poçt dublikatı (placeholder xaric) | **0** |
| yazılışı olan, SAR-ı olmayan tələbə | **0** |
| açılış dublikatı `(subject, group, period)` | **0** |
| bal dublikatı `(lesson, enrollment)` | **0** (DB `UNIQUE` constraint + sorğu ilə təsdiqləndi) |
| arxiv → yalnız `alumni` invariantı (əksinə pozan) | **0** |
| aktiv tələbə → `student` rolu yoxdur | **0** |

**`azadedildi` ↔ `access_state` nümunə yoxlaması (mənbə vs təzə):**
- 20 nümunə `azadedildi=1` (id 141…427) → hamısı **`archived`+`alumni`** ✅ (20/20)
- 20 nümunə `azadedildi=0` (id 4-19 + **1970, 1994, 2081, 3492**) → hamısı **`active`+`student`** ✅ (20/20)

Bu, P0-1 arxiv-qaydası düzəlişinin **təzə, birinci-əldən run-da** düzgün işlədiyini
təsdiqləyir — ikinci dəfə `legacy_repair_archive_status` tələb olunmur.

Entity-map üzrə qalan karantin/skip (yalnız > 0 olanlar):
`journal_reconcile` 16 628 karantin (bal toqquşması, gözlənilən), `curriculum_plan_row` 263,
`course_offering` 176, `journal_enrollment` 107, `lesson` 62, `journal_finals` 57,
`student_placement` **17** (= SAR-sız tələbələr), `journal_lesson_meta` 1, `curriculum_plan` 1,
`journal_components` 1.

---

## 4. Kabinet spot-check (Django test client, force_login)

Metod: `config.settings.staging_inspect` + hədəfin owner DSN-i, `ALLOWED_HOSTS=["*"]`,
`FirstLoginPasswordMiddleware` yalnız bu skriptin prosesi daxilində müvəqqəti keçirildi
(migrasiya edilmiş hesabların hamısı qəsdən `password_change_required=True`-dur — bu, DB-yə
YAZILMADI, sadəcə middleware çağırışı prosesdaxili mock edildi).

**Vacib tapıntı:** hədəf `d44526b97cbc` schema-sı `f3fada3c`-də dayanıb (registrar `0063`,
organizations `0034`, exams `0062`), hazırkı kod bazası isə HEAD-də (`6c028efe`) **7 yeni
miqrasiya** tələb edir (§5-də siyahı). Bunlar tətbiq olunmadan `manage.py shell` ilə
profil bölmə sorğuları `ProgrammingError: column … does not exist` ilə çökür (`registrar_program
.is_archived`, `registrar_subject.is_archived`). Ona görə spot-check **hədəf bazanın özündə
DEYİL**, `CREATE DATABASE … TEMPLATE d44526b97cbc` ilə yaradılan müvəqqəti surətdə aparıldı;
7 miqrasiya ora tətbiq olundu, yoxlanıldı, sonra surət silindi. Əsl `d44526b97cbc` **toxunulmadan qaldı**.

| İstifadəçi | dashboard | my-schedule | my-journal (müəllim) | my-subjects/my-journal (tələbə) |
|---|---:|---:|---:|---|
| myedu.student.200 | 200 (6988 b) | 200 (4474 b) | — | ⚠️ bax qeyd |
| myedu.student.571 | 200 (6983 b) | 200 (4488 b) | — | ⚠️ bax qeyd |
| myedu.student.618 | 200 (7128 b) | 200 (4488 b) | — | ⚠️ bax qeyd |
| myedu.worker.85 | 200 (7019 b) | 200 (4087 b) | 200 (29550 b) | — |
| myedu.worker.23 | 200 (7165 b) | 200 (4090 b) | 200 (29611 b) | — |

**Qeyd (tələbə `my-subjects`/`my-journal`):** 7 audit-miqrasiyasından sonra sorğu YENİ bir
sxem uyğunsuzluğuna düşdü — `registrar_curriculum.status` və sonra
`organizations_academicperiod.opening_status` yoxdur. Araşdırma göstərdi ki, bu, audit
işi ilə ƏLAQƏSİZDİR: **eyni iş qovluğunda paralel, commit edilməmiş başqa bir sessiya**
canlı şəkildə yeni miqrasiyalar yazır (`apps/registrar/migrations/0065_curriculum_plan_chain.py`,
`apps/organizations/migrations/0039-0041_*` — hamısı `git status` ilə `??` untracked,
HEAD `6c028efe`-də yoxdur). Yəni HEAD bu audit zamanı sabit deyildi. `dashboard` və
`my-schedule` sorğuları bu sahələrə toxunmadığı üçün 200 qayıtdı; SQL-səviyyəli çarpaz
yoxlama (§2, `myedu.student.200` üçün enrollment→subject→lesson→mark zənciri əl ilə
yoxlanıldı: 5 fənn, 1524 dərs/1524 bal — hamısı uyğun) məlumatın özünün doğru olduğunu
təsdiqləyir; yalnız HTML fraqment yolu təsadüfi kənar iş səbəbindən bloklandı.

**Cari dövr (`is_current`).** Fresh DB-də heç bir dövr `is_current=true` deyil (V9 qəsdən
qoymur). Bugünü (2026-09-03) əhatə edən dövr **yoxdur** (son dövr `2025/2026 Yay`,
2026-08-31-də bitib). `legacy_repair_current_period` **qərar sırası** ilə işlədilsə,
`--period` verilmədən **legacy bayrağa düşər → `2025/2026 Yay`** — yəni PHASE1 §4.3-də
sənədləşdirilən EYNİ boş-semestr problemi təkrarlanar. Repaired klonda ötürülən **açıq
`--period "2025/2026 Yaz"`** override-ı düzgün seçim idi (Yay inzibati/boş dövrdür).
**Nəticə: fresh DB-yə `legacy_repair_current_period --period "2025/2026 Yaz"` MÜTLƏQ
LAZIMDIR** (defolt fallback-a etibar etmək olmaz) — DB özü isə hələ toxunulmayıb, addım
namizəd kimi qeyd olunur, İCRA OLUNMADI.

---

## 5. Tövsiyə — server keçidi (cutover)

**Seçim A — fresh DB `d44526b97cbc` + repair + HEAD miqrasiyaları**

Qalan addımlar:
1. `manage.py migrate` — 7 gözləyən miqrasiya: `organizations.0035/0036/0037/0038`,
   `exams.0063/0064`, `registrar.0064` (`git log --stat f3fada3c..6c028efe -- '*/migrations/*'`
   ilə siyahılandı; hamısı additiv/seed, DROP yoxdur).
2. `legacy_repair_current_period --period "2025/2026 Yaz"` → `is_current` təyini (gözlənilən: 1 sətir yenilənir).
3. (istəyə görə) `--create-year 2026/2027` — 2026/2027 dövrlərini əvvəlcədən yaratmaq (klonda edilmişdi, +3 sətir).
4. `students_without_sar=17` üçün ayrıca qərar: 13-ü `staged` (gözlənilən), 4-ü `student_placement`
   karantinində (email/username toqquşması) — PHASE1 §P0-2 sərhədinə düşür, ya əl ilə həll, ya qəbul.
5. **Giriş problemi (`usable_password` sayı çox aşağıdır — audit-öncəki PHASE31-də 25/8 568)**
   bu run-da da eyni struktur qüsurdur (parol reset e-poçtu getmir) — RİM toplu parol-buraxılış
   axını P0 namizədi olaraq qalır (PHASE27 R-8), fresh DB-yə xas deyil.

Gözlənilən son vəziyyət: 7 816 tələbə / 729 işçi / 7 799 SAR / 304 805 dərs / 3 921 304 bal /
158 otaq / 16 dövr (cari təyin edilmiş) / 0 orfan / 0 dublikat.

**Seçim B — `emsarena_db` + təmir runbook (PHASE1_MIGRATION_REPAIRS.md)**

Qalan addımlar: eyni 3 P0 təmiri (`legacy_repair_archive_status`,
`legacy_repair_missing_accounts`, `legacy_repair_current_period`) + demoqrafiya təmiri,
LAKİN **J12 (`journal_lesson_recovery`, +11 735 dərs/+~200 min bal) və J13 (`legacy_rooms`,
+158 otaq) fazaları TƏKRAR FAZA kimi işlədilə BİLMƏZ** — köçürmə dəftəri (`upsert_entity_map`)
eyni `run_id`/derivation-hash altında sətri artıq "migrated" kimi bağlayıb; fərqli
identity/hash-lı təkrar cəhd `legacy_entity_identity_conflict` ilə rədd olunur (§0,
PHASE1_MIGRATION_REPAIRS). Yəni B yolunda bu iki fazanı almaq üçün YENİ, ayrıca
"append-only recovery" alətinin YAZILMASI lazımdır (mövcud deyil) — B seçimi bunu
DEFERRED saxlayır və 11 735 dərs/ 158 otaq itkin qalır.

### Qərar: **A (fresh DB `d44526b97cbc`)**

Səbəblər:
- **Data tamlığı:** A-da J12+J13 artıq DAXİLDİR (158 otaq, 11 735 bərpa edilmiş dərs);
  B-də bunlar strukturca yenidən əldə edilə bilməz (ledger-in "bir dəfəlik sübut" qaydası).
- **Determinizm/ledger təmizliyi:** A tək, tam, 24-fazalı bir run-un məhsuludur —
  audit izi bir `run_id`-dədir. B, əsl `emsarena_db` üzərində çoxlu keçmiş qismən
  run + üstəlik təmir əmrləri qatının nəticəsidir (daha mürəkkəb, sübut zənciri parçalıdır).
- **Risk:** A-da qalan iş TAMAMİLƏ additiv (7 miqrasiya + 1 repair əmri, hər ikisi
  idempotent/dry-run-default) və `emsarena_db`-yə HEÇ TOXUNULMUR (rollback dump saxlanılır).
  B-nin riski daha yüksəkdir: canlı `emsarena_db` üzərində repair əmrləri işlədilməli,
  və hətta onlardan sonra da 11 735 dərs/158 otaq boşluğu QALACAQ.

## Nəticə

Fresh run **`succeeded`**, 0 error, bütün bütövlük yoxlamaları təmiz, arxiv qaydası (P0-1)
20/20 nümunədə mənbə ilə tam uyğun, J12+J13 daxildir. Server keçidi üçün **A** seçilir:
7 gözləyən miqrasiya + `legacy_repair_current_period --period "2025/2026 Yaz"`.
