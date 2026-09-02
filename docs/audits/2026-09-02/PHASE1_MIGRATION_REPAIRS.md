# FAZA 1 — Köçürmə qüsurlarının TƏMİRİ (2026-09-02)

**Giriş sənədləri:** müstəqil audit `PHASE1_DATA_AUDIT.md` (3 P0 + 4 P1 qüsur) və
`docs/migration/HANDOFF_2026_08_27.md` §3 (sahibin dizayn qərarları).
**Nəticə runbook-u:** `docs/migration/HANDOFF_2026_08_27.md` §8.

**Rejim.** Yazma YALNIZ QA klonunda icra olunub
(`127.0.0.1:55433/emsarena_rehearsal_a0d170000901`).
Qorunan real baza `localhost:5432/emsarena_db` **heç vaxt açılmayıb**.
Branch `audit/post-migration-qa-2026-09`; commit edilməyib.

---

## 0. Bir abzasda

Üç P0 qüsurun hər biri **iki yerdə** bağlandı: (a) fazanın öz qaydası düzəldildi
ki, növbəti tam repetisiya doğru olsun; (b) artıq köçürülmüş hədəf üçün
**dry-run-default, auditli, idempotent təmir əmri** yazıldı. Fazanın hədəflənmiş
təkrar icrası **mümkün deyil** (ledger `run_id`-yə möhürlənib, `upsert_entity_map`
fərqli derivation hash-ı `legacy_entity_identity_conflict` ilə rədd edir) — bu,
sübutun toxunulmazlığı üçün qəsdəndir, ona görə təmir ayrıca səthdir. Qayda
dəyişdiyi üçün `TRANSFORM_FAMILY` **`rehearsal-identity-v1` → `-v2`** bumb edildi.

Klonda ölçülmüş nəticə: **2 291 cari tələbə girişə qaytarıldı** (arxiv 2 490 → 199),
**7 703 profilə qrup nömrəsi yazıldı**, **cari akademik dövr təyin edildi**;
ikinci icra **0 dəyişiklik** verdi.

---

## 1. Qüsur → kök səbəb → düzəliş → əmr

### P0-1 · 2 291 cari tələbə səhvən «məzun» sayılıb

| | |
|---|---|
| **Simptom** | aktiv tələbələrin ~30 %-i `access_state='archived'` + `alumni`; `identity.user_access_is_login_blocked` onları bütün giriş səthlərində bloklayır |
| **Kök səbəb** | `apps/legacy_import/services/rehearsal_sar_phase.py::SarMaterialisationPhase._decide` — arxiv qoluna İKİ şərtlə düşürdü: `students.azadedildi=1` (199 sətir) **və** «qəbul ili həll olunmadı» (2 291 sətir). İkincisi məzunluq ölçüsü DEYİL: mənbədə **248 qrupun** `groups.start_year='0000'`-dır |
| **Kod düzəlişi** | həmin rung artıq arxiv qoluna düşmür — sətir **aktiv tələbə** kimi materiallaşır, `FALLBACK_ADMISSION_YEAR` (1950) sentinelini daşıyır və yeni `legacy_sar_active_no_admission_year` (INFO) kodu alır. İl UYDURULMUR (model NULL qəbul etmir; sentinel açıq sübutdur). `rehearsal_sar_archive.py`: `ARCHIVE_FALLBACK_ADMISSION_YEAR` → neytral `FALLBACK_ADMISSION_YEAR` (köhnə ad geri-uyğunluq üçün qalır); `rehearsal_sar_targets.py`: yeni kodun severity xəritəsi |
| **Yeni DB səthi** | `apps/accounts/migrations/0018_account_restore_evidence.py` — bax §2 |
| **Yeni servis** | `apps/accounts/services/identity_archive.py::restore_archived_account` (+ `apps/accounts/public.py` ixracı) |
| **Təmir əmri** | `legacy_repair_archive_status` (`services/repair_archive.py`) |
| **Seçim qaydası** | profil arxivdə **və** ledger-də `legacy_sar_archived_no_admission_year` var **və** `legacy_sar_departed_student` YOXDUR. `--require-activity` ən azı bir yazılış tələb edir; `--fix-admission-year` (default QAPALI) qəbul ilini ən erkən yazılışın akademik ilindən törədir |

> ⚠️ **İki ledger tələsi.** (1) SAR issue-larının `entity_type`-ı `sar` deyil,
> **`student_record`**-dur. (2) `legacy_sar_departed_student` YALNIZ aktivasiya
> açarı bağlı run-da yazılır — bu klonda **0 sətirdir**; açar açıq olanda hər iki
> səbəb eyni `legacy_sar_archived_student` kodunu alır və buraxılmışları
> ilsizlərdən ayıran YEGANƏ nişan `legacy_sar_archived_no_admission_year`-in
> OLMASIDIR. Qayda buna uyğun qurulub və klonda **dəqiq 2 291 / 199** verir.

### P0-2 · 100 tələbə + 14 işçinin heç bir hesabı yoxdur

| | |
|---|---|
| **Simptom** | e-poçtu sınıq (85), boş (1) və ya iki legacy sətrində təkrarlanan (28 = 14 cüt) insanlar hədəfdə ümumiyyətlə yoxdur; 12 belə işçiyə bağlı 62 jurnal müəllimsizdir |
| **Kök səbəb** | `services/account_cutover.py` e-poçtu **kimlik açarı** kimi işlədir; `_MANUAL_REVIEW_RULES` dublikat halda **hər iki tərəfi** karantinə salır |
| **Kod düzəlişi** | yeni `services/rehearsal_identity_placeholder.py`: MƏHZ e-poçt formasına görə bloklanan sətir deterministik yer-tutucu alır — `myedu.{tip}.{legacy_pk}@placeholder.invalid` (RFC 2606 rezerv TLD → poçt getməsi mümkün deyil), `email_verified=False`. `rehearsal_identity_phase.py` **iki keçidli təsnifat** edir (`apply_email_placeholders`): birinci keçid kimin bloklandığını deyir, ikinci keçid əvəzlənmiş kohortu bütöv halda yenidən təsnif edir. Orijinal qayda kodları + `legacy_account_email_placeholder_synthesised` (WARNING) ledger-ə yazılır; `source_row_hash` **xam** e-poçtu digest etməyə davam edir |
| **Sərhəd** | **username** tərəfli kolliziyalar (kimlik açarının özü) yenə karantində qalır — yer-tutucu onları həll etmir |
| **Təmir əmri** | `legacy_repair_missing_accounts` (`services/repair_accounts.py`) — `stage_imported_account` → `activate_staged_account` (eyni qapılar); müəllimlər üçün mənbədəki `journals.teacher_id` uyğunluğuna görə müəllimsiz `CourseOffering`-ə `instructor` yazılır |
| **Qalıq iş** | SAR / Enrollment / jurnal xanaları YARADILMIR — faza zəncirinin məhsuludur; bu 100 tələbənin akademik tarixçəsi yalnız düzəldilmiş identity fazası ilə **növbəti tam repetisiyada** düşür |

### P0-3 · cari akademik dövr yoxdur

| | |
|---|---|
| **Simptom** | `is_current` heç bir sətirdə True deyil; bugünü əhatə edən dövr yoxdur; «Fənlərim» boş görünür |
| **Kök səbəb** | **faza qüsuru deyil** — `journal_periods` (V9) qəsdən cari dövr qərarını tenant-a saxlayır; legacy bayraq `legacy_journal_period_current_flag` INFO issue-su kimi ledger-də qalır. Boşluq: köçürmədən sonra bu qərarı verən **səth yox idi** |
| **Təmir əmri** | `legacy_repair_current_period` (`services/repair_periods.py`) — qərar sırası: `--period` → bugünü əhatə edən dövr → legacy bayraq → ən son dövr. `--create-year 2026/2027` üç fəsli köçürmə ilə eyni tarix reseptiylə yaradır (cari elan ETMİR) |

### P1 · demoqrafiya + profil qrup nömrəsi

| | |
|---|---|
| **birth_date / gender** | **kod qüsurlu deyil**: `services/legacy_demographics.py` və onun `student_placement`-dəki çağırışı 2026-08-30-da əlavə olunub, klondakı run isə 2026-08-27-dədir. Növbəti tam repetisiya onu özü doldurur |
| **`student_group_number`** | profil paneli bu sahəni oxuyur, qrup isə `SAR.group`-dadır — tamamilə hədəf daxilində həll olunur |
| **Təmir əmri** | `legacy_repair_demographics` — default yalnız qrup nömrəsi (mənbə lazım deyil); `--from-source` doğum tarixi/cinsi legacy MariaDB-dən oxuyur. Hər iki halda **yalnız BOŞ** sahə doldurulur |

### Düzəldilmədən sənədləşdirilənlər

* **P1-1 (J12).** `journal_lesson_recovery` (order 41) tam və testlidir, amma
  yalnız tam repetisiyanın içində icra olunur → ayrıca əmr YAZILMADI;
  **cutover-dan əvvəl J12 daxil təzə tam repetisiya** tələb olunur.
* **P1-5 (`FinalGrade.is_published`).** Bayraq vestigialdır; tələbə görünüşünü
  `AssessmentScheme.is_published` idarə edir və onu RİM jurnal bağlayanda qoyur.
* **P1-2 (3 075 boş kurikulum).** Ayrıca iş dilimi (backlog).

---

## 2. `archived → active` — niyə yeni miqrasiya lazım oldu

Birinci `--apply` cəhdi klonda **2 291 sətirdə** eyni xəta ilə dayandı:
`ProgrammingError: accounts_activation_evidence_function_required`.

Səbəb: 0016 migration-ı `archived` vəziyyətindən çıxmağı 0013-ün
`AccountActivationEvidence` qapısına bağlayıb, həmin sübut sətri isə
**append-only və birdəfəlikdir** — `accounts_activation_evidence_immutable`
trigger-i yalnız `consumed_at NULL → NOT NULL` keçidinə icazə verir, sətrin
`(organization, user_ref)` açarı isə UNİKALDIR. Yəni arxivləşdirmədə istifadə
olunmuş sübut təkrar işlədilə bilmir, yenisi də yaradıla bilmir: **səhv arxiv
qərarını geri almağın qanuni yolu ümumiyyətlə yox idi.**

`apps/accounts/migrations/0018_account_restore_evidence.py` bunu qapını
**zəiflətmədən** açır:

* `accounts_accountrestoreevidence` — aktivasiya sübutunun eyni forması, öz
  append-only trigger-i ilə (`app.account_restore_evidence_id` GUC + `txid_current()`);
  tətbiq rolu cədvələ YAZA BİLMİR (REVOKE), yalnız oxuyur; RLS + tenant policy.
* `accounts_reject_active_staged_profile` GENİŞLƏNİR: `archived → active` keçidi
  bərpa sübutu ilə də açıla bilər; `staged` budağı və digər bütün `archived`
  keçidləri OLDUĞU KİMİ aktivasiya sübutunu tələb edir.
* `accounts_restore_archived_identity(...)` — 0013-dəki aktivasiya funksiyasının
  EYNİ qapı dəsti: aktor konteksti, aktorun aktivliyi, tenant aktivliyi,
  `member.edit` icazəsi, rolun tenant-a aidliyi, profilin həqiqətən `archived`
  olması, DƏQİQ bir üzvlük. Yalnız bundan sonra sübut yazılır, profil `active`
  edilir və üzvlüyün rolu `alumni → student` olur.

Aktivasiya sübutuna TOXUNULMUR (onun «bir hesab — bir aktivasiya» invariantı
qalır). Heç bir sətir silinmir: arxiv sübutu da, bərpa sübutu da qalır.
Miqrasiya nömrəsi toqquşmur (accounts head 0017 idi).

---

## 3. Ortaq qapılar (hər dörd əmrdə)

`apps/legacy_import/services/repair_support.py`

| Qapı | Davranış |
|---|---|
| Rejim | `--dry-run` DEFAULT; yazmaq üçün `--apply` (ikisi birlikdə → `CommandError`) |
| Baza | `emsarena.rehearsal_target='disposable'` markeri yoxdursa `--apply` **rədd olunur** (`legacy_repair_target_not_disposable`); serverdə `--i-know-this-is-production` açıq şəkildə verilir |
| Tenant | `--organization <slug>` (default `myedu-univ`); naməlum slug → `CommandError` |
| Həcm | `--limit N` · göstərmə: `--show N` |
| Aktor | `--actor <username>`, default təşkilatın sahibi; `member.edit` qapısından keçir |
| Çıxış | deterministik qərar cədvəli + xülasə (dry-run-da da) |
| Audit | dəyişən hər sətir üçün `core.audit.log_action` (`legacy_repair:*` reason) |
| Silmə | **yoxdur**; mövcud dəyər üzərinə yazılmır |
| Təkrar | idempotent — ikinci icra 0 dəyişiklik |

---

## 4. Klon sübutu — ƏVVƏL / SONRA

Ölçmə: `docker exec -i emsarena-staging-pg psql -U emsarena_staging -d emsarena_rehearsal_a0d170000901`.

| Ölçü | Əvvəl | Sonra |
|---|---:|---:|
| `access_state='archived'` profil | 2 490 | **199** |
| `access_state='active'` profil | 5 948 | **8 239** |
| `access_state='staged'` profil | 13 | 13 |
| `alumni` üzvlüyü | 2 490 | **199** |
| `student` üzvlüyü | 5 228 | **7 519** |
| `teacher` üzvlüyü | 718 | 718 |
| `accounts_accountrestoreevidence` sətri | — | **2 291** |
| `audit_auditlog` (`reason='legacy_repair:archive_status'`) | 0 | **2 291** |
| `AcademicPeriod` cəmi / `is_current` | 13 / **0** | 16 / **1 (2025/2026 Yaz)** |
| profil `student_group_number` dolu | **0** | **7 703** |
| profil `birth_date` / `gender` dolu | 0 / 0 | 0 / 0 (mənbə bağlantısı tələb olunur) |
| ledger `student` map bloklanmış / `worker` bloklanmış | 100 / 14 | 100 / 14 (əmr mənbəsiz işləmir) |

### 4.1 `legacy_repair_archive_status`

```
=== legacy_repair_archive_status — DRY-RUN ===       === APPLY ===
  arxivdə olan profil             : 2490               2490
  bərpa namizədi (restore)        : 2291               2291
  toxunulmur (keep_archived)      : 199                199
    səbəb: no_admission_year_only : 2291               2291
    səbəb: source_azadedildi      : 199                199
  FAKTİKİ bərpa olunan            : 0                  2291
  uğursuz                         : 0                  0
```

**İdempotentlik (dərhal ikinci icra):** `arxivdə olan profil : 199`,
`bərpa namizədi (restore) : 0`, `FAKTİKİ bərpa olunan : 0`.

Bərpa namizədlərinin **2 219-unun** ən azı bir yazılışı, **184-ünün** 2025/2026
tədris ilində yazılışı var (`--require-activity` verilsə 2 219 sətir bərpa olunardı).

### 4.2 Giriş qapısı və kabinet (Django test client, `force_login`, yalnız oxu)

```
myedu.student.1970: state=active rol=student qrup_nömrəsi='530 BI' login_blocked=False my-subjects=200
myedu.student.1994: state=active rol=student qrup_nömrəsi='529 BI' login_blocked=False my-subjects=200
myedu.student.2081: state=active rol=student qrup_nömrəsi='529 ML' login_blocked=False my-subjects=200
myedu.student.3492: state=active rol=student qrup_nömrəsi='628.1' login_blocked=False my-subjects=200
```

Auditin dörd nümunəsi (`1970/1994/2081/3492`) artıq **girişi bağlı deyil** və
profil paneli qrupu göstərir. Onların «Fənlərim» bölməsi yenə boşdur — bu **data
faktıdır, qüsur deyil**: hər dördünün son yazılışı 2022/2023-dədir. Cari dövrdə
yazılışı olan bərpa olunmuş tələbələrdə bölmə fənləri göstərir:

```
myedu.student.3515: semestr=1 login_blocked=False my-subjects=200 FƏNN VAR (28 marker)
myedu.student.3494: semestr=1 login_blocked=False my-subjects=200 FƏNN VAR (28 marker)
myedu.student.2481: semestr=1 login_blocked=False my-subjects=200 FƏNN VAR (28 marker)
```

### 4.3 `legacy_repair_current_period` — qərar əsası

| Dövr | Başlanğıc | Son | Açılış | Yazılış |
|---|---|---|---:|---:|
| 2024/2025 Payız | 2024-09-15 | 2025-01-31 | 1 539 | 20 393 |
| 2024/2025 Yay | 2025-07-01 | 2025-08-31 | 0 | 0 |
| **2025/2026 Payız** | 2025-09-15 | 2026-01-31 | **1 574** | 22 936 |
| **2025/2026 Yaz** | 2026-02-01 | 2026-06-30 | **1 212** | 19 033 |
| 2025/2026 Yay (legacy `is_current`) | 2026-07-01 | 2026-08-31 | **10** | 59 |
| 2026/2027 Payız (yeni yaradıldı) | 2026-09-15 | 2027-01-31 | **0** | 0 |

Bugünü (2026-09-02) əhatə edən dövr **yoxdur**; legacy bayraq demək olar boş
semestri göstərir; 2026/2027-də **0 açılış** var. Ona görə cutover anında cari
dövr **2025/2026 Yaz** təyin edildi; 2026/2027 Payız isə tədris ili rəsmən
başlayanda cari elan olunmalıdır. Legacy bayrağı kor-koranə izləmək «Fənlərim»-i
boş qoyardı.

### 4.4 `legacy_repair_demographics`

```
sahə                  hədəfdə dolu (əvvəl)  namizəd  yazıldı
birth_date            0                     —        0
gender                0                     —        0
student_group_number  0                     7703     7703
```
İkinci icra: `qrup nömrəsi namizədi : 0` (idempotent).

### 4.5 `legacy_repair_missing_accounts` (mənbə ilə)

Mənbə: `emsarena-legacy-source-rehearsal` (MariaDB `myedudb`, **yalnız oxu**).

```
=== DRY-RUN ===                        === APPLY ===        === təkrar DRY-RUN ===
  hesabsız legacy sətri   : 114          114                  114
  yaradılacaq (create)    : 114          114                  0
    tələbə                : 100          100                  0
    işçi                  : 14           14                   0
  onsuz da var            : 0            0                    114
  FAKTİKİ yaradılan       : 0            114                  0
  müəllim bağlanan açılış : 0            35                   0
  uğursuz                 : 0            0                    0
```

| Ölçü | Əvvəl | Sonra |
|---|---:|---:|
| `myedu.student.*` hesab | **7 716** | **7 816** (= mənbədəki `students` sayı) |
| `myedu.worker.*` hesab | **715** | **729** (= mənbədəki `workers` sayı) |
| `auth_user` cəmi | 8 454 | 8 568 |
| yer-tutucu e-poçtlu hesab (`@placeholder.invalid`) | 0 | **114** (hamısı `email_verified=false`) |
| `student` üzvlüyü / `teacher` üzvlüyü | 7 519 / 718 | **7 619 / 732** |
| müəllimsiz `CourseOffering` | 1 203 | **1 168** (−35) |

Bloklanma səbəbləri (dry-run cədvəlindən): `legacy_account_email_invalid`,
`legacy_account_email_blank`, `legacy_account_email_duplicate_source` — yəni
məhz auditin sadaladığı üç qayda. Hər 114 hesab yer-tutucu e-poçt aldı; ad,
soyad və ata adı **mənbədən** oxundu (uydurulmadı).

**«62 jurnal» iddiasının dəqiqləşdirilməsi.** Yeni yaradılan 14 işçinin legacy
`journals` sətri: **62** (auditin rəqəmi təsdiqləndi). Onlardan **19-u `fake=1`**
(mənbə tərəfi ləğvi — heç vaxt açılışa çevrilməyib), **43-ü canlıdır**; 43-dən
**42-si** materiallaşmış açılışa bağlanır (1-i `legacy_journal_group_unresolved`
ilə karantindədir), qrup-başına bölgü səbəbindən həmin 42 jurnal **45 açılış**
verir və indi **45-nin hamısının müəllimi var**. Əmr 35 sətir yazdı, çünki
qalan 10 açılışın müəllimi (birləşmə klasterində) onsuz da dolu idi — qlobal
düşüş (1 203 → 1 168 = 35) bununla üst-üstə düşür.

### 4.6 `legacy_repair_demographics --from-source`

```
sahə                  hədəfdə dolu (əvvəl)  namizəd  yazıldı
birth_date            0                     mənbə    2175
gender                0                     mənbə    1693
student_group_number  7703                  0        7703
  mənbədən oxunan demoqrafiya : 2397
  demoqrafiya yazıldı         : 2397     ← ikinci APPLY: 0 (idempotent)
```

| Ölçü | Əvvəl | Sonra |
|---|---:|---:|
| profil `birth_date` NOT NULL | 0 | **2 175** |
| profil `gender <> 'unspecified'` | 0 | **1 693** |
| profil `student_group_number` dolu | 7 703 | 7 703 (dəyişməz) |

Fərq (mənbədə 2 252 doğum tarixi vs hədəfdə 2 175) **qəsdəndir**:
`legacy_demographics.legacy_birth_date` təqvimə uyğun olmayan, kəsik və
ağlabatan pəncərədən kənar dəyəri fail-closed NULL saxlayır və `MM/DD/YYYY`
kimi görünən sətirləri təxmin ETMİR.

### 4.7 Mənbə bağlantısının şərtləri (hər iki `--from-source` əmri üçün)

`default_source_factory` yalnız **opt-in settings** oxuyur; DSN qəbul etmir:

```bash
export LEGACY_MARIADB_SOURCE_ATTEST_ENABLED=1
export LEGACY_MARIADB_SOURCE_LOCAL_DISPOSABLE=local-container-only   # YALNIZ lokal konteyner
export LEGACY_MARIADB_SOURCE_HOST=127.0.0.1
export LEGACY_MARIADB_SOURCE_PORT=<docker port emsarena-legacy-source-rehearsal>
export LEGACY_MARIADB_SOURCE_USER=root
export LEGACY_MARIADB_SOURCE_PASSWORD="$LEGACY_SOURCE_PASSWORD"
export LEGACY_MARIADB_SOURCE_DATABASE=myedudb
```

**İki tələ (hər ikisi bu sessiyada real olaraq qarşıya çıxdı):**

1. **Port sabit deyil.** Host yenidən başlayandan sonra Docker konteynerə YENİ
   host portu verdi (55000 → 50200). Portu həmişə
   `docker port emsarena-legacy-source-rehearsal` ilə oxuyun; səhv port
   `legacy_source_connection_factory_failed` verir.
2. **Mənbə server `read_only` olmalıdır.** `source_extraction` fail-closed
   yoxlayır: `@@GLOBAL.read_only <> 1` → `legacy_source_server_not_read_only`.
   Konteyner yenidən başlayanda bayraq itir; sənədləşdirilmiş vəziyyət 1-dir
   (`docs/migration/DATA_VERIFICATION_2026_08_27.md`). Bərpası:
   `SET GLOBAL read_only = 1;` — bu, mənbəni yalnız DAHA məhdudlaşdırır və
   köçürmə kodunun mənbəyə heç vaxt yaza bilməməsini təmin edir.
   *(Bu sessiyada məhz bu əmr icra olundu; mənbə datasına heç bir yazı getməyib.)*

---

## 4A. Reqressiya qaçışının iki əlavəsi (R-9, R-5)

`PHASE27_REGRESSION.md` iki qalıq boşluq tapdı; hər ikisi eyni qapı dəsti ilə
bağlandı (dry-run default, `--apply`, org-scoped, auditli, idempotent).

### R-9 · təmirlə yaradılmış 100 tələbənin akademik qeydi yox idi

**Simptom.** 7 816 tələbə hesabı, cəmi 7 703 SAR.
`registrar.public.build_student_subjects_context` ilk addımda
`StudentAcademicRecord` axtarır — tapmayanda «Fənlərim» boş vəziyyət qaytarır,
yəni yeni 100 hesab kabinetdə heç nə görmürdü.

**Düzəliş.** `services/repair_sar.py` (yeni) + `legacy_repair_missing_accounts
--with-sar`. Qərar qaydası fazanın öz pilləkəni ilə eynidir: qrup
(`OrgUnit.settings['legacy']['id']`) → proqram (`(specialty_unit, degree_level)`)
→ qəbul ili (`entry_year` → qrupun ili → `FALLBACK_ADMISSION_YEAR` sentineli) →
kurikulum (dəqiq il → həmin proqramın ən yaxın ili → yeni sətir, çünki
`SAR.curriculum` NOT NULL-dur). `resolve_placement` fazadan **olduğu kimi**
gəlir; FİN mövcud `_apply_fin` ilə yazılır (dublikat FİN yazılmır).

`--with-sar` yalnız bu icrada yaradılanları deyil, **əvvəlki icradan qalan**
hesabları da namizəd sayır (R-9 məhz odur); SAR-ı olanları `plan_records` özü
kənara qoyur.

```
=== APPLY ===                          === təkrar APPLY ===
  SAR namizədi                : 100      100
  SAR yaradıldı               : 96       0
    SAR curriculum_exact      : 96       —
    SAR already_present       : —        96
    SAR skip_group_unresolved : 4        4
```

| Ölçü | Əvvəl | Sonra |
|---|---:|---:|
| `StudentAcademicRecord` | 7 703 | **7 799** |
| yer-tutucu e-poçtlu tələbənin SAR-ı | 0 | **96** |

**Niyə 100 deyil, 96.** Qalan dördünün qrupu mənbədə HƏLL OLUNMUR — bu, uydurma
ilə bağlana bilməyəcək mənbə qüsurudur (fazanın 13 `staged` sətri ilə eyni
qayda, `legacy_record_group_unresolved`):

| legacy id | `students.group_id` | `groups`-da varmı |
|---|---:|---|
| 2583 · 2585 · 2588 | 197 | **yox** (orphan FK) |
| 3502 | 0 | qrup təyin edilməyib |

Yəni **7 799 mümkün maksimumdur**; 7 803 rəqəmi 100-ün hamısının qrupu olduğunu
fərz edirdi.

**Kabinet yoxlaması** (test client, `force_login`):
```
myedu.student.1039: SAR qrup=130 T ing proqram=MYEDU-20 il=1950 my-subjects=200 has_record=True
myedu.student.1040: SAR qrup=130 T ing proqram=MYEDU-20 il=1950 my-subjects=200 has_record=True
myedu.student.1042: SAR qrup=130 T ing proqram=MYEDU-20 il=1950 my-subjects=200 has_record=True
```
(`il=1950` sentineldir: bu üç tələbənin nə `entry_year`-i, nə qrupunun ili var —
uydurulmur, işarələnir.)

### R-5 · 158 otaq hədəfə heç düşməmişdi

**Simptom.** `exams.ExamRoom` = 0, ona görə jurnalın dərs modalındakı
KORPUS→OTAQ seçimi bütün tenant üzrə boş idi.

**Kök səbəb faza qüsuru DEYİL.** `legacy_rooms` (J10, order 13) fazası tam və
testlidir — sadəcə klondakı run-ın faza siyahısında yox idi.

**Düzəliş.** `services/repair_rooms.py` + `legacy_repair_rooms --from-source`.
**Heç bir yeni xəritələmə yazılmadı**: fazanın öz saf funksiyaları
(`LegacyRoomDecision`, `room_code`, `room_capacity`, `materialise_rooms`) olduğu
kimi işlədilir, ona görə təmirin nəticəsi növbəti tam repetisiya ilə eynidir.

* `code = "myedu-room-<legacy id>"` — `(organization, code)` unikaldır, yəni
  idempotentlik natural açarladır (otaq adı unikal deyil: 158-dən 25-i təkrar);
* `building` = `rooms.bina` tam ədədinin onluq mətni ("1"/"2"/"3"/"5");
* `capacity` = `max_student_count` rəqəmdirsə, deyilsə 0;
* `floor` — mənbədə belə sütun **yoxdur** → boş qalır (uydurulmur);
* `room_types` (Auditoriya / laboratoriya / emalatxana) hədəfdə qarşılığı
  olmayan ölçüdür → yazılmır.

```
=== DRY-RUN ===        === APPLY ===        === təkrar DRY-RUN ===
  mənbə otağı     158    158                  158
  yaradılacaq     158    158                  0
  onsuz da var    0      0                    158
  FAKTİKİ yaradılan 0    158                  0
  hədəf otaq      0 → 0  0 → 158              158 → 158
  korpus sayı     0      4                    4
```

| Ölçü | Əvvəl | Sonra |
|---|---:|---:|
| `exams.ExamRoom` | **0** | **158** (hamısı aktiv) |
| fərqli korpus | 0 | **4** (`1`, `2`, `3`, `5`) |
| `capacity = 0` olan otaq | — | **0** (158 sətrin hamısında tutum oxundu) |

**Dərs modalı kaskadı yoxlandı** (`registrar.lesson_rooms`):
```
lesson_room_choices: 158 otaq, korpuslar=['1', '2', '3', '5']
  nümunə: {'id': '34', 'name': '102 (myedu-room-149)', 'building': '1', 'capacity': 76}
  resolve_lesson_room → 102 (myedu-room-149) korpus=1
```

Mövcud sətrin adı/korpusu **üstündən yazılmır** — imtahan mərkəzi otağı sonradan
adlandıra bilər (test: `test_rooms_never_overwrite_a_renamed_room`).

---

## 5. Test əhatəsi

`DATABASE_URL="postgres://emsarena_agent:…@127.0.0.1:55432/ems_mig_<random>" pytest … --ds=config.settings.test`

| Fayl | Nə sübut edir |
|---|---|
| `apps/legacy_import/tests/test_repair_commands.py` (21 test) | markersiz bazada `--apply` rəddi · dry-run-ın heç nə yazmaması · seçim qaydasının üç şaxəsi · **real PostgreSQL trigger-i üzərindən** bərpa · giriş qapısının açılması · idempotentlik · audit sətri · `--limit` · dövr seçimi/yaradılması · qrup nömrəsi |
| `apps/legacy_import/tests/test_rehearsal_identity_placeholder.py` (13 test) | yer-tutucu konvensiyası · e-poçt-forma qaydalarının tam siyahısı · **username qüsuru yer-tutucu ALMIR** · dublikat cütün HƏR İKİ tərəfinin staged olması · mənbə sətrinin toxunulmazlığı |
| `apps/legacy_import/tests/test_rehearsal_sar_phase.py` | ilsiz sətir AKTİV tələbə qalır (`…_stays_an_active_student`) · `azadedildi=1` yenə arxivlənir (`…_is_still_archived`) · bərpa olunmuş sətir `registrar_guard_active_member` qapısından keçir VƏ girişi açıqdır · ladder/digest/idempotentlik dəstləri yeniləndi |
| `apps/legacy_import/tests/test_rehearsal_identity_phase.py` | severity taksonomiyası yeni kodu əhatə edir |
| `apps/legacy_import/tests/test_rehearsal_contracts.py` | `transform_version` ailəsi `rehearsal-identity-v2` |
| `test_repair_commands.py` (R-5/R-9 blokları) | otaq xəritələməsinin faza ilə eyniliyi · idempotentlik · **adı dəyişdirilmiş otağın qorunması** · rəqəm olmayan tutumun 0-a düşməsi · markersiz `--apply` rəddi · SAR il pilləkəni (entry_year → qrup → sentinel) · SAR idempotentliyi · **orphan qrupda SAR UYDURULMUR** · kurikulum exact→substituted→created |

---

## 6. Dəyişən fayllar

```
apps/legacy_import/services/rehearsal_sar_phase.py            (arxiv qaydası)
apps/legacy_import/services/rehearsal_sar_archive.py          (sentinel adı)
apps/legacy_import/services/rehearsal_sar_targets.py          (severity)
apps/legacy_import/services/rehearsal_identity_phase.py       (iki keçidli təsnifat)
apps/legacy_import/services/rehearsal_identity_placeholder.py YENİ
apps/legacy_import/services/rehearsal_contracts.py            (TRANSFORM_FAMILY v2)
apps/legacy_import/services/repair_support.py                 YENİ
apps/legacy_import/services/repair_archive.py                 YENİ
apps/legacy_import/services/repair_accounts.py                YENİ
apps/legacy_import/services/repair_periods.py                 YENİ
apps/legacy_import/services/repair_demographics.py            YENİ
apps/legacy_import/services/repair_sar.py                     YENİ (R-9)
apps/legacy_import/services/repair_rooms.py                   YENİ (R-5)
apps/legacy_import/management/commands/legacy_repair_archive_status.py     YENİ
apps/legacy_import/management/commands/legacy_repair_missing_accounts.py   YENİ
apps/legacy_import/management/commands/legacy_repair_current_period.py     YENİ
apps/legacy_import/management/commands/legacy_repair_demographics.py       YENİ
apps/legacy_import/management/commands/legacy_repair_rooms.py              YENİ (R-5)
apps/accounts/migrations/0018_account_restore_evidence.py     YENİ (SQL-only)
apps/accounts/services/identity_archive.py                    (restore_archived_account)
apps/accounts/services/__init__.py · apps/accounts/public.py  (ixrac)
apps/legacy_import/tests/…                                    (2 yeni + 3 yenilənmiş)
docs/migration/HANDOFF_2026_08_27.md                          (§8 + runbook)
```

`apps/legacy_import/migrations/` **toxunulmayıb** (perf agentinin `0007_*` indeksi).
