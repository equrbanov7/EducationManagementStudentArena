# EMSArena legacy miqrasiyası — status ledger

Son yenilənmə: 25 avqust 2026  
Cari mərhələ: `M4 — Rehearsal orkestratoru kodlandı, PostgreSQL/real-source sübutu gözləyir`  
Ümumi qərar: `NO-GO for production`, lokal hazırlıq davam edir.  
İcraçı qeydi: 25 avqustdan iş Claude tərəfindən davam etdirilir (əvvəlki icraçı
Codex usage limitinə çatdı); mənbə snapshot SHA-256 eyni təsdiqləndi, custody bütövdür.

Bu fayl görülən işi, növbəti işi və gate-ləri qısa formada saxlayır. Əsas
arxitektura və mərhələlər üçün `MASTER_PLAN.md` əsas mənbədir.

## İcra xülasəsi

- Legacy datanın köçürülməsi realdır, amma birbaşa SQL copy kimi aparılmayacaq.
- Heç bir production database və real tətbiq datası dəyişdirilməyib.
- `.env` PostgreSQL konfiqurasiyası var, dəyərlər heç yerdə açıqlanmayıb.
- `.env`-də göstərilən PostgreSQL hazırda reachable deyil; ona yazılmayıb.
- SQLite engine-agnostic testləri və tmpfs disposable PostgreSQL 16 testləri
  işlədilib; PostgreSQL-ə xas RLS/trigger sübutu SQLite-dan ayrıca saxlanılır.
- Qrup-transfer history və approval/scope P0-ları lokal kodda bağlanıb. Registrar
  core migration graph-ı üçün cross-FK, parent immutability və canlı instructor
  authorization qoruması verified-dir; qalan relation matrix ayrıca açıqdır.
- Raw payload və credential saxlamayan, pseudonymous açarlar daşıyan idempotent
  control plane kodlanıb: canonical identity ayrıca, hər run nəticəsi immutable
  observation kimi saxlanır; reviewed remap append-only version tarixçəsi yaradır.
- Default-deny source projection legacy password, açıq parol və PIN sütunlarını
  extractor/transform səthinə buraxmır. Real extractor inteqrasiyası və yeni hesab
  activation flow-u hələ açıqdır.
- Strict read-only preflight real 2.14 GB source snapshot-da hash, ölçü, mode və
  81 cədvəli eyni təsdiqləyib. Transform və domain-write adapterləri hələ yoxdur.
- Rehearsal orkestratoru kodlanıb: attestasiya → identity cohort (ledger + batch
  zənciri + issue taksonomiyası) → reconciliation + PII-siz determinizm hesabatı.
  Hədəf yalnız 10 interlock-dan keçən disposable PostgreSQL ola bilər; sessiya
  boyu `set_rls_tenant` işlədilir, `bypass_rls` heç vaxt çağırılmır. İki təmiz
  hədəfdə real digest sübutu hələ icra edilməyib (VERIFIED).
- İlk domain adapteri (FAZA 3 — SLICE 1) kodlandı: `academic_structure` fazası
  rehearsal hədəfində `organizations.OrgUnit` (fakültə/kafedra/ixtisas/qrup) və
  `registrar.Program` sətirləri, `student_placement` fazası isə `UserProfile.fin`
  ilə `auth_user.first_name/last_name` yazır. **Production və real tətbiq datası
  hələ də toxunulmamışdır** — yazı yalnız 10 interlock-dan keçən disposable
  PostgreSQL hədəfində baş verir. Bu slice qəsdən **sıfır**
  `StudentAcademicRecord` və **sıfır** `Curriculum` sətri yaradır (B-1/B-2, bax
  `MASTER_PLAN.md` → «Semantik düzəlişlər»); yerləşdirmə qərarı ledger-də
  cross-run sabit derivation digest-i kimi saxlanılır və SAR materiallaşdırması
  `curricula` + aktivasiya slice-inə qalır.

## Görülən işlər

| ID | İş | Status | Sübut/nəticə |
|---|---|---|---|
| M0.1 | Git/worktree inventarı | VERIFIED | Branch `Develop`, başlanğıc HEAD `b30b36bb`; tracked/staged dəyişiklik yox idi |
| M0.2 | User fayllarını ayırmaq | VERIFIED | Mövcud untracked docs qovluqlarına toxunulmadı |
| M0.3 | `.env` redaktə edilmiş yoxlama | VERIFIED | PostgreSQL scheme mövcuddur; secret/DSN/host/user göstərilmədi |
| M0.4 | Lokal DB reachability | VERIFIED | PostgreSQL reachable deyil; heç bir auth/schema write edilmədi |
| M0.5 | SQLite fallback | VERIFIED | `DATABASE_URL="sqlite://" python manage.py check` -> 0 issue |
| M0.6 | Tooling inventarı | VERIFIED | Python 3.11.6, Docker hazır, PostgreSQL client 18.3 |
| M0.7 | Dependency fərqi | VERIFIED | Installed Django 5.2.13; repo pin-i 5.2.16 |
| M0.8 | Legacy source audit artifact-ləri | VERIFIED | SQL audit və 81-table mapping JSON hash-ləri təsdiqləndi |
| M0.9 | Master plan | VERIFIED | M0-M8 mərhələləri, gate, rollback və hesabat qaydası yazıldı |
| M0.10 | Dump permission hardening | VERIFIED | Permission `0600`; ölçü 2,142,912,818 bayt və SHA-256 dəyişməyib |
| M1.1 | Pinned Python venv | VERIFIED | `.venv`: Python 3.11.6, Django 5.2.16, dependency check təmizdir |
| M1.2 | Engine-agnostic baseline | VERIFIED | SQLite check + makemigrations dry-run + modul gate-ləri yaşıl |
| M1.3 | Disposable PostgreSQL | VERIFIED | PG16 tmpfs container; bütün cari migration-lar uğurla tətbiq edildi |
| M1.4 | Restricted runtime role | VERIFIED | Test rolu `NOSUPERUSER`, `NOBYPASSRLS`, `NOCREATEDB`, `NOCREATEROLE` |
| M1.5 | Registrar RLS baseline | VERIFIED | PostgreSQL `apps/registrar/tests/test_rls.py`: 11/11 keçdi |
| M1.6 | Platform RLS/append-only baseline | VERIFIED | PostgreSQL `apps/organizations/tests/test_rls.py`: 62/62 keçdi |
| M2.1 | Qrup transfer tarixçəsinin qorunması | VERIFIED | Köhnə Enrollment silinmir; DROPPED+superseded olur, qiymət/davamiyyət/final tarixçəsi qalır; SQLite 9, PostgreSQL 11 transfer testi keçdi |
| M2.2 | Publish/approval invariant-i | VERIFIED | Direct publish bağlandı; DB state constraint, row lock və fail-closed audit; scope yalnız explicit permission ilə həll olunur |
| M2.3 | Approval/scope inteqrasiya testi | VERIFIED | Cari geniş suite: SQLite 203 pass/2 PG skip, PostgreSQL 197/197 pass |
| M2.4 | Core registrar cross-FK tenant integrity | VERIFIED (CORE SCOPE) | Child+parent tenant dəyişməsi, active student membership və instructor permission PostgreSQL trigger-ləri; core negative matrix 11/11 pass |
| M2.5 | Canlı instructor authorization | VERIFIED | Membership/role/`grade.input` revoke sonrası journal GET/POST fail-closed; owner/superuser yolu qorunur |
| M3.1 | Legacy control-plane modelləri | VERIFIED | `LegacyMigrationRun`, canonical `LegacyEntityMap`, immutable `LegacyEntityObservation`, `LegacyMigrationIssue`; raw payload/credential/DSN saxlanmır |
| M3.2 | İdempotency və provenance | VERIFIED | Canonical source identity global unique-dir; exact rerun no-op, fərqli hash/target/state conflict-dir; per-run observation əvvəlki rehearsal sübutunu qoruyur |
| M3.3 | Tenant və ledger DB qoruması | VERIFIED | PostgreSQL FORCE RLS, lifecycle/cross-scope trigger-ləri, DELETE/TRUNCATE guard və restricted-role privilege testi |
| M3.4 | Engine-agnostic control-plane testi | VERIFIED | SQLite bütün `apps/legacy_import/tests`: 114 pass, 34 PostgreSQL skip |
| M3.5 | PostgreSQL control-plane testi | VERIFIED | PostgreSQL bütün `apps/legacy_import/tests`: 146 pass, 2 SQLite-only skip |
| M3.6 | Paylaşılabilən baseline hesabatı | VERIFIED | Canonical artifact build validation/package/verification gate-lərindən keçdi; secret və lokal path daxil deyil |
| M3.7 | Strict read-only source preflight | VERIFIED | O_NOFOLLOW + streamed SHA/table count; real snapshot: 0600, 2,142,912,818 bayt, 81 cədvəl, gözlənilən SHA |
| M3.8 | Migration forward/rollback/forward | VERIFIED | Təmiz disposable PostgreSQL-də full schema; `legacy_import 0005→0004→0005` və `registrar 0041→0040→0041` uğurlu |
| M3.9 | Credential-safe source projection | VERIFIED (CONTRACT) | Versioned default-deny allowlist; legacy password/show_password/PIN deny; focused 56/56 test pass |
| M3.10 | Reviewed issue/remap workflow | VERIFIED | Reviewer/time/reason/evidence + append-only map version; review history varsa reverse məlumatı silmədən STOP edir |
| M3.11 | Non-super migration portability | VERIFIED (LOCAL) | `NOSUPERUSER/NOBYPASSRLS` synthetic owner ilə 0005 backfill/reverse və 0041 invalid-row precheck/reapply keçdi |
| M3.12 | Real MariaDB read-only adapter + gateway | VERIFIED | `mariadb_source.py`/`mariadb_gateway.py` (PyMySQL, CONSISTENT SNAPSHOT, read-only attestasiya, DSN saxlanmır); real 2.14 GB restore üzərində students=7,816 / workers=729, credential çıxışı 0 |
| M3.13 | Source attestation komandası | VERIFIED | `legacy_import_source_attest` — PII-siz say+fingerprint attestasiyası; server read_only=1 təsdiqi |
| M3.14 | Fixed 81-cədvəl registry | VERIFIED | `table_plan.py` v1 — 81 sətir, cəm 9,044,531, SHA-fingerprint, syllabus DESIGN_GATED, `adapter_key=None` invariantı (fail-closed) |
| M3.15 | Integer-PK streaming inventory | VERIFIED | `pk_inventory.py` + komanda — checkpoint-li chunk skan, hash-chain digest; `LEGACY_TABLESPACE_INVENTORY_V1.json` real restore-dan |
| M3.16 | Scalable batch accounting | VERIFIED | `LegacyImportBatch` (mig 0006) — append-only hash zənciri, migrated+skipped+quarantined=source_rows, run başlanğıcında möhürlənən accounting_mode |
| M3.17 | Account-cutover təsnifatı + staging körpüsü | VERIFIED (2026-08-25 fix) | `classify_projected_account_cutover` + tək-sorğulu `TargetIdentitySnapshot`; Codex-in yarımçıq refactor-undakı KeyError bağlandı — 13/13 test |
| M3.18 | Accounts staging/activation sərhədi | VERIFIED | mig 0013 — NFKC unikal indekslər, staged hesab login/sessiya ala bilmir, aktivasiya yalnız SECURITY DEFINER + `AccountActivationEvidence` ilə |
| M3.19 | Registrar qalan relation matrisi | VERIFIED | mig 0042 — elective/rubric/selfwork/coursework/resit/correction + actor FK guard-ları; R4 qalıq matrisi bağlandı |
| M3.20 | Correction reversal ledger | VERIFIED | mig 0043 — 5 correction cədvəlində append-only + stable locator backfill; `correction_reversals.py` fail-closed revert servisləri |
| M3.21 | Rubrik atomiclik | VERIFIED | mig 0044 — component identity backfill (stop-kodlu), atomik roll-up guard-ları |
| M3.22 | Reference identity + auditli qrup transferi | VERIFIED | mig 0045 — parent-FK freeze, iki fazalı `begin/finalize` PG funksiyaları, saxta-GUC yolu bağlı (evidence sətri `pg_current_xact_id()`-ə bağlıdır) |
| M3.23 | Production komanda qapısı | VERIFIED | `core/management/command_safety.py` — default mühit production sayılır və rədd edilir; 12 seed/import komandası mixin-lə qorunur |
| M3.24 | Müstəqil adversarial təhlükəsizlik baxışı | VERIFIED | 2026-08-25: app səthindən P0/P1 bypass yoxdur; 4 qalıq P2 → `SECURITY_BASELINE.md` MIG-SEC-012 |
| M3.25 | Guard↔test-infra uzlaşması və reqressiya düzəlişləri | VERIFIED | Superuser-only TRUNCATE keçidi (flush bloklaması həlli), accounts 0013 asılılığı exams zəncirindən qopardıldı, dean qlobal axtarışı `can_search_directory` (member.view+unit.view) ilə bərpa, rbac `can_approve_grades` dict override bug-ı düzəldildi |
| M4.1 | Rehearsal orkestratoru (`legacy_import_rehearse`) | VERIFIED | Faza A attestasiya (10 interlock + source attestation) → attested phase registry → Faza C reconciliation; SQLite 22 orkestrator/komanda testi yaşıl, `-m postgres` və real-source sübutu növbəti addımdadır |
| M4.2 | İdempotent resume və interrupt semantikası | VERIFIED | Durable checkpoint = `LegacyImportBatch`; kəsilmiş run `RUNNING` qalır (exit 3), resume eyni pəncərələri kəsir, artıq müşahidə olunmuş sətir yenidən stage edilmir; scope uyğunsuzluğu fail-closed |
| M4.3 | Determinizm artifakt-ı | VERIFIED | `deterministic` bölməsi run/org/vaxt/path daşımır; `--compare-report` digest fərqində `legacy_rehearsal_determinism_mismatch` verir; atomik yazı yalnız eyni digest-i overwrite edir |
| M5.1 | `academic_structure` fazası (order 10) | VERIFIED | `departments`/`speciality`/`groups` (880 sətir) → OrgUnit ağacı + `Program` kataloqu; topoloji valideyn həlli, legacy-açarlı slug (`myedu-dep/spec/grp-{id}`), dərəcəyə görə bir Program (`-M` magistr), 14 issue kodu. SQLite 23 test yaşıl; `-m postgres` (§8/8-9) və real-mənbə sübutu icra edilməyib |
| M5.2 | `student_placement` fazası (order 25) | VERIFIED | `source_tables=()` — batch-siz derived faza; SA-1/SA-2 seam-ləri ilə evidence yalnız öz observation-larında və digest zəncirində yaşayır. Sıfır SAR/Curriculum (B-1/B-2); `UserProfile.fin` + boş `first_name`/`last_name` yazılır, yerləşdirmə `record_derivation_hash`-ə möhürlənir. SQLite 20 test yaşıl; `-m postgres` (§8/10) və real-mənbə sübutu icra edilməyib |
| M5.3 | `UserProfile.fin` sahəsi | VERIFIED | `core/validators.py` (`normalize_fin`/`validate_fin`, `^[A-Z0-9]{7}$`) + mig `accounts 0014` — nullable-unique, **qlobal** (milli identifikator semantikası), admin `list_display`/`search_fields`-də. SQLite 10 test yaşıl; staged profildə yazıla bilməsi və unikallıq PostgreSQL sübutu (§8/10) gözləyir |
| M5.4 | `academic_catalog` fazası (order 12) | VERIFIED | `lessons` (2,521) + `curricula` (126) + `curricula_plan` (3,424) = **6,071 sətir** → `Subject`/`Curriculum`/`CurriculumSubject`. Fənn şəxsiyyəti `lessons.id`-dir (V-6: `lesson_code` 145 fərqli dəyərlə 2,521 sətri örtür, «37» tək başına 1,975 ad daşıyır) — `Subject.code` HƏMİŞƏ `MYEDU-L{id}` sintez olunur; dedup `(ad, department_id)` üzrə, qalib ən kiçik id, uduzan sətir yenə öz batch-sayılan map-ını alır (E-4, C4 dəqiq qalır). `curricula_plan.lesson_id` JSON massivdir (V-8) və **hər elementi genişlənir** (V-14: canlı 883/3,424 sətir çoxelementlidir) — hər uğurlu element üçün bir `CurriculumSubject`, map ilk sətrə baxır. Semestr sxemi siyasətdir və default **ORDINAL**-dır (V-13). 23 issue kodu, heç biri ERROR deyil (E-13). SQLite yaşıl; PG tam suite **4,415 pass / 0 fail** (§10/10 daxil) və real-mənbə beş-fazalı konformans (aşağıda) yaşıl |
| M5.5 | `sar_materialisation` fazası (order 28) | VERIFIED | `source_tables=()` — ikinci batch-siz derived faza; `student_placement`-in möhürlədiyi qərarı `StudentAcademicRecord`-a çevirir. Aktivasiya körpüsü (`apps.accounts.public.activate_staged_account`, reason `signed_authoritative_export`) və SAR yazısı **bir `transaction.atomic()`** içindədir (P-B / E-9), açar isə `--stage-and-activate` (default **False**) + `--max-activated-accounts` (default **0**) — hər ikisi `policy_digest`-dədir, ona görə hesablara toxunan run heç vaxt toxunmayanla eyni `transform_version`-i paylaşa bilmir (SA-5). Aktivasiyadan dərhal sonra `email_verified=False` + `password_change_required=True` (E-11) — legacy email bərpa üçün yararsız olur. V-18: `students.azadedildi=1` (canlı ~200 nəfər) siyasətdən ASILI OLMAYARAQ `departed` → SKIPPED + `legacy_sar_departed_student`. 10 issue kodu. SQLite yaşıl; PG tam suite **4,415 pass / 0 fail** (§10/8-9, 11-13 daxil), real-mənbə determinizm testi yaşıl, Rehearsal #5 real dump-da SUCCEEDED |
| M5.6 | `worker_materialisation` fazası (order 26) | VERIFIED | 715 staged işçi hesabı: Membership.scope_unit = öz kafedrasının OrgUnit-i (`myedu-dep-{id}`, yalnız NULL→dəyər) + aktivasiya körpüsü — scope+aktivasiya+E-11 bir `transaction.atomic()`-də; kap worker+SAR CƏMİnə şamil (SA-5). V-23: `teacher_type`/`inzibati` YALNIZ INFO — rol yüksəltmə yoxdur (RİM əl qərarı). Registry pin `71f2001f8e2f…` (6 faza). SQLite 1,605; PG tam suite 4,443/0; mariadb 6-fazalı determinizm yaşıl |
| M5.7 | `journal_periods` fazası (order 32) | VERIFIED | `semestr_jurnal` (13) → `organizations.AcademicPeriod`; `get_or_create(organization, name, academic_year)` + modelin `format_year`-ı. `is_current` HEÇ VAXT yazılmır (dövrün cari olması yeni sistemin öz qərarıdır). Hər sətir üçün INFO (`period_created` / `matched_existing` / `current_flag`) — 13-sətirlik uyğunluq cədvəli hesabatda görünür (V-9) |
| M5.8 | `journal_offerings` fazası (order 34) | VERIFIED | `journals` → `registrar.CourseOffering` + `AssessmentScheme` (DRAFT). J-V6: `fake=1`/`sonra_sil=1` → SKIPPED `legacy_journal_discarded_source` (uniqid ledger-də qalır — mənbədə heç nə silinmir). J-V5: müəllim həll olunmazsa `instructor=NULL` + INFO (legacy `teacher_id` derivation hash-də saxlanılır). J-V7: çoxqruplu jurnal → `group=NULL` tək offering + INFO; parse xətası VƏ boş massiv → QUARANTINED. Run-daxili eyni açara düşən ikinci jurnal `legacy_journal_offering_merged` ilə birləşir |
| M5.9 | `journal_enrollments` fazası (order 36) | VERIFIED | `journals.students_id` JSON → `registrar.Enrollment` (`kind=mandatory`), map açarı `uniqid:student_id`. Həll olunmayan tələbə YALNIZ öz sətrini atır (jurnal davam edir); offering MIGRATED deyilsə orphan SKIP; `students_id` parse xətası jurnal-səviyyə QUARANTINED |
| M5.10 | `journal_lessons` fazası (order 38) | VERIFIED | `journals_dates_added_by_teacher` (379,215) → `registrar.Lesson`; `kind=lecture`, `hours=2`, `instructor=offering.instructor`; təqvim ili ay-nömrəsindən törədilir (9-12 → Y, 1-8 → Y+1); orphan/invalid/duplicate nərdivanı. Registry 10 faza, pin `59eac1c4b772…` |
| M5.11 | `journal_marks` fazası (order 40) | VERIFIED | `journals_dates_points` təqvim ayları (~4.4M) → `registrar.LessonMark`. İstifadəçi qərarı (F/V1): `ie` = **İŞTİRAK EDİR** → `PRESENT` (score yox), `qb` → `ABSENT`, 0–10 rəqəm → `PRESENT` + score, boş → yazı yaradılmır. `excusable=1` və ya `allowed_qb` pəncərəsi → `EXCUSED` (F/V11). J-V4 dedup: qalib ən böyük `update_counter`, sonra `updated_at`, sonra id — yaddaş-hüdudlu **iki-keçidli seçki** (bit-array prefilter + dəqiq həll, deterministik blake2b, buffer aşımında fail-closed). J-V7 arxiv: yalnız 2022-03-30-dan ƏVVƏLKİ sətirlər, overlap INFO. Seal açarı **jurnaldır** (5M sətirlik map yaradılmır) |
| M5.12 | `journal_components` fazası (order 42) | VERIFIED | `k1`/`k2`/`k3` → `AssessmentComponent(KOLLOKVIUM, k_index)` + `ComponentScore`; `si` (148,505) → `AssessmentComponent(self_work)` + `ComponentScore` (F/V12). **Qalıq risk:** `entry_score_for` SELF_WORK komponentində `SelfWorkMark` checklist-i oxuyur, `ComponentScore`-u yox — yəni `si` balları saxlanılır və komponent bölgüsündə görünür, LAKİN hesablanan giriş balına ƏLAVƏ OLUNMUR; cutover-dan əvvəl istifadəçi qərarı tələb edir |
| M5.13 | `journal_finals` fazası (order 44) | VERIFIED | `im` (126,705) → `FinalGrade.exam_score` (`finals.set_exam_score` güzgüsü), `im2` (5,524) → `ResitRecord`. J-V2: **şkala çevrilmir** — 50-dən böyük 376 dəyər OLDUĞU KİMİ saxlanılır + INFO `legacy_journal_exam_score_above_scheme` (servis onları 50-yə clamp edərdi). Naməlum `month_id` kodları → QUARANTINED `legacy_journal_mark_code_unknown` |
| M5.14 | `journal_lock` fazası (order 46) | VERIFIED | F/V10: dövrü BİTMİŞ semestrlərin `AssessmentScheme`-ləri `APPROVED` + `is_published=True` (CheckConstraint: publish ⟺ approved), cari semestr DRAFT qalır; **baxış açıq qalır** (kilid yalnız redaktəni bağlayır). Qeyd: qərar `localdate()`-ə baxdığı üçün gün-miqyaslıdır — dövr sərhədini keçmək digest-i AÇIQ dəyişir, səssiz yox |
| M5.15 | `journal_reconcile` fazası (order 48) | VERIFIED | Say balansı (mənbə = yazılan + karantin + skip), `yekun` cədvəli ilə `compute_final_result` bulk güzgüsünün müqayisəsi (kənarlaşma INFO), karantin xülasəsi. Hədəf sətri YAZMIR — yalnız sübut. Registry 15 faza, pin `de3579c5e986…` |

## Qorunan mövcud user materialları

İlkin iş ağacında aşağıdakılar untracked idi və dəyişdirilmədi:

- `docs/architecture/AKADEMIK_OS_ANALIZI.md` (2026-08-25-də yalnız **əlavə**
  olunub: sonuna «Z. Legacy idxal — modelləşdirmə boşluqları» əlavəsi;
  mövcud mətnin heç bir sətri dəyişdirilməyib)
- `docs/db-compare/`
- `docs/infrastructure/`
- `docs/workload/`

Yeni miqrasiya planı ayrıca `docs/migration/` altında yaradılır.

## Sübut snapshot-ı

| Artifact | SHA-256 |
|---|---|
| Legacy SQL dump | `177ef2269027395fd3a80fc1dd592aab565dda7cbca5f6f08785313881d68fe0` |
| Dəqiq SQL audit JSON | `e03decda34afc07527e151591e22ebc0df85e5a2b79fa8ce5a014dc76f898975` |
| 81-table mapping JSON | `067154ee9a66ed04d0d85cfe8c54e166325ba6532acec11fa003459be9635ecd` |
| Rehearsal 1 hesabatı (`LEGACY_REHEARSAL_V1_RUN1.json`) | **STALE (2026-08-25)** — faza registry-si 3 fazaya genişləndi |
| Rehearsal 2 hesabatı (`LEGACY_REHEARSAL_V1_RUN2.json`) | **STALE (2026-08-25)** — faza registry-si 3 fazaya genişləndi |

> **Stale artifakt qeydi (FAZA 3 — SLICE 1).** `academic_structure` və
> `student_placement` registry-yə qoşulduqda `_EXPECTED_PHASE_REGISTRY_FINGERPRINT`
> yenidən pinləndi (`160216a1…` → `7d4dfddb…`) və `policy.phase_keys` böyüdü, yəni
> `policy_digest` → `transform_version` → D5 scope açarı → `determinism_digest`
> zənciri **konstruksiyaya görə** dəyişdi. `docs/migration/reports/` altındakı hər
> iki mövcud hesabat bu səbəbdən köhnəlmişdir. Fayllar tarixi sübut kimi
> **silinmir**; onlar iki yeni təmiz rehearsal-dan yenidən generasiya edilməlidir —
> **əl ilə redaktə edilmir**.

Audit JSON-ları hazırda temp artifact-dir; kod pipeline-ı onları source-of-truth kimi
hardcode etməyəcək. Preflight gözlənilən manifest faktlarını parametr kimi qəbul edir
və yalnız sanitizasiya edilmiş nəticə çıxarır.

## Cari P0 risk reyestri

| ID | Risk | Cari qərar |
|---|---|---|
| R0 | Dump faylı PII/credential saxlayır | `0600` tətbiq edilib; encrypted quarantine/retention bağlanmadan production import yoxdur |
| R1 | Qrup transferi Enrollment və CASCADE tarixini silir | Lokal fix VERIFIED; same-semester əvvəlki DROPPED qrupa geri dönüş ayrıca biznes qərarıdır |
| R2 | Birbaşa `publish` approval zəncirini keçir | Lokal fix VERIFIED; 0040 ziddiyyətli mövcud state taparsa səssiz dəyişmədən STOP edir |
| R3 | Scope-suz chair/dean fail-open ola bilir | Lokal permission-specific fail-closed fix VERIFIED |
| R4 | Registrar cross-tenant FK DB-də tam qorunmur | BAĞLANDI (M3.19, mig 0042) — qalan relation matrisi PostgreSQL trigger-ləri ilə örtüldü |
| R5 | Runtime DB rolu RLS bypass edə bilər | Real runtime role attestasiya olmadan cutover STOP |
| R6 | Legacy provenance/idempotency ledger tələb olunur | Canonical identity + observation + lifecycle + reviewed versioning VERIFIED; rehearsal orkestratoru kodlanıb (M4.1-M4.3, VERIFIED); domain adapterləri və iki təmiz hədəfdə real determinizm sübutu açıqdır |
| R7 | Legacy credential üçün təhlükəsiz activation yoxdur | BAĞLANDI (M3.12/M3.18) — real read-only extractor + staged hesab / evidence-li aktivasiya; qalıq P2-lər MIG-SEC-012-də. Rehearsal-da email səlahiyyəti default-deny-dir; stage yalnız reviewer-in imzaladığı digest manifest-i + açıq `--max-staged-accounts` limiti ilə mümkündür |
| R8 | 9M ETL deploy migration-na düşə bilər | Schema migration və explicit ETL ayrılır |
| R9 | Syllabus target lifecycle yoxdur | Dizayn inkişaf backlog-udur; yekun UX/business acceptance-dan sonra versioned/approved target qurulana qədər live syllabus import bloklanır |

## Növbəti icra sırası

1. Rehearsal orkestratorunun PostgreSQL və real-source sübutu: `-m postgres`
   (`test_rehearsal_postgres.py`, 8 test) və disposable MariaDB + PostgreSQL
   konformans testi (`test_rehearsal_source_integration.py`); sonra iki təmiz
   hədəfdə `--compare-report` ilə eyni `determinism_digest`. M4.1-M4.3 yalnız
   bundan sonra `VERIFIED` → `VERIFIED` olur.
2. Lokal müşahidə mühiti: staging PG konteyneri + app-in həmin bazaya qoşulan
   inspection rejimi (sahib datanı UI-da yoxlaya bilsin) + bir-komandalı reset.
3. Domain adapterləri M4 sırası ilə (org struktur → proqram/fənn/kurikulum →
   akademik qeyd/qrup → offering/enrollment → jurnal → imtahan); hər biri
   `table_plan` registry-dən açılır, ledger/batch/issue kontraktı ilə.
4. MIG-SEC-012 P2 hardening-i (profil INSERT gate, DB-də digest recompute,
   generik kolliziya kodu) — rehearsal-lara paralel.
5. ~~İlk akademik-referens adapteri phase registry-yə əlavə olunur~~ — BAĞLANDI
   (FAZA 3 / SLICE 1, M5.1-M5.3): `academic_structure` və `student_placement`
   registry-dədir, barmaq izi yenidən pinlənib, gated cədvəllər strukturca
   iddia edilə bilmir. Qalan: bu iki fazanın `-m postgres` + real-mənbə sübutu
   (bax 1) və **iki yeni** rehearsal hesabatının generasiyası — köhnə RUN1/RUN2
   artifakt-ları konstruksiyaya görə stale-dir.
6. ~~Növbəti dilim: `curricula` + aktivasiya axını~~ — BAĞLANDI (FAZA 3 /
   SLICE 2, M5.4-M5.5): `academic_catalog` (12) və `sar_materialisation` (28)
   registry-dədir, barmaq izi 5 faza üçün yenidən pinlənib. Qalan: bu iki
   fazanın `-m postgres` (§10/8-13) + real-mənbə (§10/14-15, 15,496 sətir)
   sübutu və **iki yeni** rehearsal hesabatı.
   Syllabus version/approval modeli yekun dizayn və biznes acceptance-dan sonra
   (DESIGN_GATED qalır); runbook + yekun hesabat cutover-dən əvvəl.

## Bu mərhələnin çıxış şərti

Cari lokal M2/M3 slice-i yalnız aşağıdakılar olduqda `VERIFIED` sayılır:

- source content hash dəyişməyib;
- dump owner-only custody-dədir;
- plan və status repoda mövcuddur;
- production və business data dəyişməyib;
- PostgreSQL məcburi gate-ləri SQLite-dan açıq ayrılıb;
- domain adapteri aktiv deyil və mövcud domen datasına yazı edilməyib.

## Dəyişiklik jurnalı

### 28 avqust 2026 (gecə) — FAZA 3B / J4–J8: jurnal məzmunu + Rehearsal #7 tapıntısı

- Beş yeni faza (M5.11–M5.15) — jurnalın **məzmunu**: 5.1M bal/qayıb hüceyrəsi,
  kollokvium/sərbəst iş komponentləri, imtahan yekunları, semestr kilidi və
  üzləşdirmə. Registry **15 faza**, pin `de3579c5e986…`.
- **Servis qatı qəsdən güzgüləndi** (import edilmədi) — data qorunması qərarı:
  `save_marks` EXCUSED statusunu ifadə edə bilmir və balı yalnız seminar/lab
  dərsində saxlayır (J3 hər dərsi `lecture` yaratdığı üçün **250,588 bal** itərdi),
  `set_exam_score` isə 50-yə clamp edir (**376 dəyər** təhriflənərdi). Bütün
  invariantlar güzgülənib və hər targets modulunun docstring-ində sadalanıb.
- **Rehearsal #7 real tapıntısı (düzəldildi):** `journal_enrollments` staged
  (aktivləşməmiş) tələbə üçün `Enrollment` yaratmağa çalışırdı; PG
  `registrar_guard_active_member` haqlı olaraq rədd edirdi və **tutulmamış**
  `IntegrityError` bütün run-u dayandırırdı (ledger RUNNING qaldı, data itmədi).
  DB-də probe ilə təsdiqləndi (staged bloklanır / aktiv keçir). Düzəliş: faza
  aktiv-üzvlük indeksini ÖNCƏDƏN qurur, belə sətir SKIPPED +
  `legacy_journal_student_inactive` (WARNING) — jurnalın qalanı davam edir.
  Reqressiya testi əlavə olundu.
- Rehearsal #7-nin (yarımçıq) verdiyi real rəqəmlər: **13,875 CourseOffering**,
  2,262 birləşmiş, 1,866 süzülmüş (fake/sonra_sil), 1,426 çoxqruplu,
  1,402 müəllimi həll olunmayan.
- Qapılar: sqlite 966; PG `apps/legacy_import` **1,026 pass**; **tam PG suite
  4,695 pass / 0 fail**; lint/module-size/module_deps təmiz; **CI Pipeline +
  CodeQL yaşıl (c91bc7f3)**.
- PG-yə xas 48 uğursuzluq yenə FIXTURE idi (ortaq `journal_points_harness`
  tələbələri aktiv üzvlüksüz yaradırdı) — `activate_member` köməkçisi ilə həll.

### 28 avqust 2026 (gecə) — FAZA 3B / J0–J3: jurnal skeleti

- Dörd yeni derived faza (M5.7–M5.10) — jurnalın **strukturu** (dövr → fənn
  açılışı → tələbə yazılışı → dərs günü). Bal/qayıb hüceyrələri (5.1M) NÖVBƏTİ
  alt-dilimdir (J4–J8), speki yazılıb.
- Qapılar: sqlite `apps/legacy_import` 831 pass; genişləndirilmiş dəst
  (legacy_import + registrar + organizations) 1,418 pass; lint / module-size /
  module_deps təmiz; **tam PG suite 4,544 pass**; **mariadb 10-fazalı
  determinizm dəsti 3 pass (37 dəq)**; **CI Pipeline + CodeQL yaşıl (818f0702)**.
- PG-yə xas 15 uğursuzluq test FIXTURE-lərində idi (məhsul kodu deyil):
  `registrar_guard_active_member` offering.instructor / enrollment.student üçün
  AKTİV üzvlük tələb edir, fixture isə `is_active=False` saxlayırdı. Real axın
  onsuz da belədir (worker 26 / sar 28 fazaları jurnaldan ƏVVƏL aktivləşdirir) —
  fixture-lərə `_activate_member` köməkçisi əlavə olundu (818f0702).
- İstifadəçi jurnal qərarları bağlayıcı qeydə alındı: `ie` = **iştirak edir**
  (present), `qb` = qayıb, boş = qeyd yoxdur; bitmiş semestrlər kilidlənir amma
  baxıla bilər; `allowed_qb` pəncərəsi → üzürlü; BÜTÜN illər köçürülür.
- Yeni tələ sənədləşdi: zsh-də dəyişənə yığılmış əmr arqumentləri TƏK söz kimi
  ötürülür (bash-dan fərq) → rehearsal əmrlərində env/arqumentlər həmişə literal.

### 27 avqust 2026 (gecə) — Rehearsal #6: müəllimlər canlı dumpda aktiv

- **Rehearsal #6** (`emsarena_rehearsal_10d2ae2b15d0`, 6 faza, transform
  `rehearsal-identity-v1.84f118bcc319`, run `f8e38b7b-…`): status **succeeded**.
  DB faktları: 8,431 hesab → **5,928 aktiv** (5,213 tələbə + **715 müəllim**),
  **715/715 müəllim `Membership.scope_unit`-i öz kafedrasına yazılıb** (V-24),
  SAR 5,213, staged qalan 2,503 (qəbul ili tapılmayan kohort).
- UI təsdiqi (staging serve, superadmin): akademik qeydlər 5,213; view-as
  seçicisində müəllimlər (`myedu.worker.*`, rol Teacher) və tələbələr görünür;
  müəllim profili view-as ilə açılır (audit banneri ilə).
- «Qruplar» icazə seed-i (0028) rehearsal tenantında yoxlandı: rector `*`,
  vice_rector/ikt_rehber/dean/chair_head `group.view+group.manage`;
  exam_center*/hr/teacher/program_coordinator ALMADI — köhnə davranışın
  dəqiq güzgüsü (heç kim qazanmır/itirmir), koordinatora indi UI-dan verilə bilər.
- **Yeni tapıntı (P2, cutover-dan əvvəl düzəlt):** `--emit-report-only`
  identity rebase-inə girir və `auth.User` sorğusunu RLS-li tətbiq rolu altında
  edir → `legacy_rehearsal_resume_target_missing`; owner DSN ilə cəhd guard
  tərəfindən DÜZGÜN rədd edildi (`target_role_privileged` — guard yumşaldılmadı).
  Nəticə: #6-nın JSON artefaktı çıxarılmadı, ledger isə tam möhürlüdür və
  yuxarıdakı rəqəmlər ondan oxunub.

### 27 avqust 2026 — DİLİM 3A: worker_materialisation + «Qruplar» icazə açarları

- Yeni `worker_materialisation` fazası (order 26, derived) — M5.6 sətrinə bax.
  Registry pin `964bd7a5…` → `71f2001f8e2f…` (6 faza; order 30 sillabusa rezerv).
- Sübutlar: SQLite 1,605 pass; tam PG suite **4,443 pass / 0 fail**; mariadb
  6-fazalı determinizm testi yaşıl. İlk mariadb icrasında tapılan «0 scoped»
  uğursuzluğu MƏHSUL deyildi: testin Membership assert-i qlobal-vəziyyət
  təmizliyindən (myedu.* silinməsi, kaskadla üzvlüklər) SONRA yerləşdirilmişdi —
  imtina-tutucusuz diaqnostik keçid pipeline-ın qüsursuzluğunu sübut etdi,
  assert run-1-dən dərhal sonraya köçürüldü (test-sıra insidenti sənədləşdi).
- Paralel commit (b2a152c4): rol-əsaslı «Qruplar» icazə açarları —
  `group.view`/`group.manage` kataloqda, bütün açarlara AZ etiket, qrup qapısı
  icazə-əsaslı, 0028 seed miqrasiyası köhnə org_admin-ekvivalent davranışı
  eynilə qoruyur (heç kim imkan itirmir/qazanmır). Fokus dəstlər 466 pass.
- İstifadəçi jurnal qərarları (V1/V9/V10/V11/V14) qəbul edildi — ən önəmlisi:
  legacy `ie` = «iştirak edir» (present), boş hüceyrə = qeyd yoxdur. J0–J3
  alt-dilim speki yazıldı (dövr/açılış/yazılış/dərs).

### 26 avqust 2026 — SLICE 2 PG təsdiqi + Rehearsal #5 (aktivasiyalı)

- Tam PG suite (postgres, ayrı DB): **4,415 pass / 0 fail / 13 skip** — bütün
  §10 slice-2 sübutları daxil. Real-mənbə mariadb dəsti: 3/3 (o cümlədən
  beş-fazalı determinizm testi; ilk icrada SA-5 müqayisə keçidi qəsdən fərqli
  digest-i EYNİ hesabat faylına yazdığı üçün overwrite-qoruma onu bloklamışdı —
  test öz keçidinə ayrıca `activation-reports/` qovluğu verməklə düzəldildi;
  məhsul kodu dəyişmədi).
- **Rehearsal #5** (`emsarena_rehearsal_3db8d2727a55`, real 2.14GB dump,
  `--stage-and-activate --max-activated-accounts 20000 --stage-contact-pending`):
  SUCCEEDED, digest `2c471169d607430f25243baf2705e84122f8601ef0e6c988723255e814ea374a`.
  15,496 mənbə sətri → 15,118 migrated / 292 quarantined / 86 skipped.
  Fazalar: structure 880; catalog 5,807 migrated + 264 quarantined
  (Subject 2,501 / Curriculum 168 / CurriculumSubject 4,681, onlardan
  **2,433 elective** — V-21); identity 8,431 staged hesab (Membership 8,431);
  placement 7,703 deferred + 13 unresolved; SAR fazası **5,213 sar_created +
  2,503 sar_deferred**. V-18: 199 `azadedildi` tələbə siyasətdən asılı olmayaraq
  bloklu qaldı (`legacy_sar_departed_student`).
- Hesab vəziyyəti (DB-də təsdiqləndi): 5,213 hesab `access_state=active` +
  SAR eyni tranzaksiyada; hamısında `password_change_required=True`,
  `email_verified=False`, **usable parol yoxdur** (kredensial çatdırılması —
  o2 addımı). 3,218 hesab staged qalır: 2,503 sar_deferred (əsas səbəb
  `legacy_record_admission_year_missing` 2,291 — FİN/qəbul-ili backfill
  kohortu) + 715 işçi hesabı (müəllim aktivasiyası kafedra yerləşdirməsi
  tələb edir — növbəti dilim).
- UI təsdiqi (staging serve, superadmin): «Akademik qeydlər» kaskadı 5,213
  tələbə göstərir; qrup filtri (məs. 132T → 17 tələbə, ixtisas «Tarix») qrup
  İÇİNDƏ real tələbə adları ilə işləyir — dilim-1-in B-1/B-2 boşluğu bağlandı.
  Diaqnostika tələsi: 8100 portunda köhnə DB4 serveri qalmışdı (stale-server
  tələsi) — öldürülüb DB5 ilə yenidən qaldırıldıqdan sonra data göründü.
- Hesabat semantikası qeydi: `totals.staged_accounts` ledger-rebuild
  məhdudiyyətinə görə batch-fazaların migrated sayının cəmidir (determinizm
  digest-inə daxildir, dəyişdirilməsi `DETERMINISM_VERSION` bump tələb edir);
  HƏQİQİ hesab sayı identity fazasının `staged_account_count`-u (8,431) və
  DB `access_state` bölgüsüdür. Arxiv: köhnə aktivasiyasız hesabat
  `LEGACY_REHEARSAL_STAGED_V1_RUN1.json` adına köçürüldü.

### 25 avqust 2026 — FAZA 3 / SLICE 2: kataloq + akademik qeyd (M5.4-M5.5)

- Faza registry-si 3 fazadan **5 fazaya** genişləndi (ciddi artan `order`):
  `academic_structure` (10) → `academic_catalog` (**12**) → `identity_cohort`
  (20) → `student_placement` (25) → `sar_materialisation` (**28**); 30 sillabus
  domeni üçün ayrılmış qalır. Barmaq izi yenidən pinləndi:
  `964bd7a537b41616b874c14c2f490435a72ef72d3a5d64fe7230912b49644bdc`.
  Run-un cəmi mənbə sətri: 880 + 6,071 + 8,545 = **15,496**.
- İki seam düzəlişi: **SA-4** — `source_extraction._AUDITED_CONTRACTS` üç
  kataloq kontraktı (+ V-18-in `STUDENT_STATUS_FIELDS`-i) ilə genişləndi;
  **SA-5** — `RehearsalPolicy` dörd yeni sahə aldı (`stage_and_activate`,
  `max_activated_accounts`, `sar_curriculum_fallback`, `plan_semester_scheme`)
  və hər dördü `_digest_payload()`-dadır. Nəticə qəsdəndir: `policy_digest` →
  `transform_version` → D5 ledger scope açarı dəyişir, ona görə **mövcud hər
  rehearsal bazası yararsızdır** və `docs/migration/reports/LEGACY_REHEARSAL_V1_RUN{1,2}.json`
  konstruksiyaya görə stale-dir — əl ilə redaktə yox, iki təzə rehearsal-dan
  yenidən generasiya.
- **B-3 (bloklayıcı kəşfin bağlanması):** «staged hesabların hamısı (8,431)
  qeyri-boş legacy email daşıyır (`legacy_account_email_untrusted`), buna görə
  `accounts_activate_staged_identity`-nin `BTRIM(email) <> ''` şərti keçilir —
  B-1 heç bir trigger dəyişikliyi olmadan həll olunur; qalan sual texniki
  deyil, ETİBAR qərarıdır.» Yəni bu dilim heç bir trigger-i, heç bir
  SECURITY DEFINER funksiyasını və heç bir accounts servisini dəyişmir.
- Yeni CLI bayraqları (§3.12): `--stage-and-activate` (cap-siz verilməsi exit 1
  ilə `legacy_rehearsal_policy_activation_invalid`), `--max-activated-accounts`
  (0..20,000 və ≤ `--max-staged-accounts`), `--sar-curriculum-fallback
  {strict,synthesise}` (default `synthesise`), `--plan-semester-scheme
  {term_pair,ordinal}` (default **`ordinal`** — V-13 canlı mənbə faktı).
- Yeni taksonomiya: **33** issue kodu (23 kataloq + 10 SAR), 1 yeni run-fatal
  (`legacy_rehearsal_catalog_index_ambiguous`) və 6 yeni config kodu. Hər SAR
  kodu `legacy_sar_` prefiksi daşıyır ki, `student_placement` ilə eyni
  `source_table="students"` altında `(run, source_table, legacy_pk, rule_code)`
  unikallığı pozulmasın.
- Yoxlama (yalnız SQLite, N5/V-5 qaydası ilə): `apps/legacy_import` +
  `apps/accounts` + `apps/registrar` = **1,782 pass / 153 skip**;
  `makemigrations --check`, `check_module_size.py --check` (SOFT_CAP=600) və
  `module_deps.py --check` (0 yeni dövr) yaşıl.
- `-m postgres` (§10/8-13: aktivasiyanın SAR-ı açması, boş-email rədd,
  RLS altında kataloq yazısı, kurikulum↔proqram koherensiyası, dependent
  evidence sonrası `program_id` dondurulması, aktiv profildə E-11 bayraqları)
  və real-mənbə beş-fazalı konformans testi (§10/14-15, 15,496 sətir + iki
  digest-in fərqlənməsi sübutu) sonradan icra edildi və yaşıldır — M5.4-M5.5
  `VERIFIED`-ə keçirildi (aşağıdakı 26 avqust girişinə bax).

### 25 avqust 2026 — FAZA 3 / SLICE 1: ilk domain adapteri (M5.1-M5.3)

- Faza registry-si 1 fazadan **3 fazaya** genişləndi (ciddi artan `order`):
  `academic_structure` (10) → `identity_cohort` (20) → `student_placement` (25).
  Barmaq izi yenidən pinləndi:
  `7d4dfddb9272d8473c50486482b874acd6bd0ac447e12eaf8d70077f7a4667ae`.
  `--phase` verilməzsə siyasət artıq bütün registry-ni seçir.
- İki seam düzəlişi (spec SA-1/SA-2), imza dəyişikliyi olmadan:
  `reconcile_run`-un C4 çarpaz yoxlaması **batch ilə sayılan** entity type-larla
  məhdudlaşdırıldı (derived hədəf sətri yanlış mismatch yaradırdı) və eyni anda
  registry-nin elan etmədiyi entity type üçün fail-closed
  `legacy_rehearsal_derived_entity_type_unregistered` gətirildi;
  `phase_report_from_ledger` isə `source_tables=()` olan fazanı öz immutable
  observation-larından bərpa edir, ona görə `--emit-report-only` reqressiya
  vermir. Hər iki opsional hook (`derived_digest_namespace`,
  `derived_state_key`) `getattr` ilə oxunur və barmaq izi payload-una **daxil
  deyil** — onlar sübutun necə etiketləndiyini dəyişir, fazanın nə yaza
  biləcəyini yox.
- Yeni taksonomiya: 20 issue kodu (14 struktur + 6 yerləşdirmə) və 6 run-fatal
  kod; `ISSUE_SEVERITY` dondurulmuşdur və naməlum kod INFO-ya **düşmür**.
- B-1/B-2 tapıntıları `MASTER_PLAN.md` → «Semantik düzəlişlər» bölməsinə əlavə
  edildi; bu slice qəsdən sıfır `StudentAcademicRecord`/`Curriculum` yaradır.
- Yoxlama (yalnız SQLite, N5/V-5 qaydası ilə): `apps/legacy_import` +
  `apps/accounts` = **1,220 pass / 72 skip**; `makemigrations --check`,
  `check_module_size.py --check` və `module_deps.py --check` yaşıl.
- `-m postgres` (§8/7-10: B-1 sübutu, RLS altında struktur yazısı, cross-org
  `specialty_unit` rədd, staged profildə FİN) və real-mənbə tam-slice
  konformans testi (§8/11, 9,425 sətir) **yazıldı, lakin icra edilmədi** —
  M5.1-M5.3 ona görə `VERIFIED` statusundadır.

### 25 avqust 2026 — M4 rehearsal orkestratoru

- `legacy_import_rehearse` komandası və 7 modullu servis slice-i əlavə olundu:
  `rehearsal_contracts` (digest primitivləri, `RehearsalPolicy`, barmaq izi ilə
  attestasiya olunan faza registry-si), `rehearsal_target_guard` (10 interlock),
  `rehearsal_authorizer`, `rehearsal_identity_phase` (Faza B), `rehearsal_phase_a`,
  `rehearsal_reconciliation`, `rehearsal_orchestrator` və `rehearsal_report`.
- Faza registry barmaq izi pinləndi
  (`160216a1051ff24af2252df8dd88144fba2c4079d0fcb33c1c6df59d4aff5e70`); gated
  cədvəllər (12 sillabus + security/unknown/archive/empty) strukturca iddia
  edilə bilmir.
- Default `--mode plan`-dır və heç nə yazmır; `--apply` operatordan hədəf baza
  adını hərfi-hərfinə yazmağı tələb edir.
- `docs/migration/reports/` altındakı artifakt PII-siz saxlanılır: raw dəyər,
  username/email, per-row digest, path, host və baza adı daxil edilmir.
- SQLite yoxlaması: `apps/legacy_import/tests` 395 pass / 57 skip; modul ölçü,
  modul-sərhəd və flake8 qapıları yaşıl.
- `-m postgres` və mariadb inteqrasiya testləri yazıldı, lakin bu addımda
  **icra edilmədi** — M4.1-M4.3 ona görə `VERIFIED` statusundadır.

### 23 avqust 2026 — ilkin baseline

- Read-only repo, mühit, DB və legacy audit inventarı aparıldı.
- Secret-lər açıqlanmadan `.env` database konfiqurasiyası təsdiqləndi.
- SQLite check və Docker/PostgreSQL imkanları ayrıldı.
- Production-a `NO-GO` qərarı qeyd edildi.
- Əsas miqrasiya planı və bu status ledger-i yaradıldı.
- Legacy dump məzmunu dəyişdirilmədən `0600` owner-only permission-a keçirildi;
  ölçü və SHA-256 yenidən eyni təsdiqləndi.
- Repo pin-ləri ilə izolə `.venv` quruldu və dependency check təmiz keçdi.
- Tmpfs disposable PostgreSQL 16-da bütün mövcud schema migration-ları tətbiq edildi.
- Məhdud runtime test rolu RLS-bypass atributları olmadan attestasiya edildi.
- Mövcud registrar PostgreSQL RLS suite-i 11/11 keçdi; cross-FK negative matrix
  ayrıca P0 kimi açıq saxlanıldı.
- Platformun geniş RLS, cross-exam və append-only PostgreSQL suite-i 62/62 keçdi.
- Raw payload və credential saxlamayan, opaque açarları pseudonymous data kimi
  qoruyan `apps.legacy_import` control plane-i əlavə edildi.
- Run/map/issue reyestri üçün idempotency, tenant uyğunluğu, FORCE RLS və
  append-only DELETE qoruması PostgreSQL səviyyəsində quruldu.
- Control-plane modeli SQLite-da 10/10, PostgreSQL negative suite-də 11/11 keçdi.
- Share edilə bilən HTML baseline hesabatı schema/build/responsive yoxlamalarından
  keçdi; real connection və secret dəyəri daxil edilmədi.

### 26 avqust 2026 — FAZA 3 dilim 1 canlı: struktur + yerləşdirmə + FİN

- Rehearsal #4 (emsarena_rehearsal_f8cafdd11d9d, üç faza birlikdə): SUCCEEDED —
  9,311 migrated (880 struktur + 8,431 hesab) / 86 skipped / 28 quarantined =
  9,425 dəqiq; blocking/credential/PII = 0; digest e6a6b4de….
- UI təsdiqi: 13 fakültə + 18 kafedra real adlarla (entity-təmizlənmiş) və
  düzgün valideyn zənciri ilə görünür; 101 Program; admin-də 7,716 idxal
  profili; FİN 576 yazıldı (15 format/dublikat issue).
- Full-slice inteqrasiya testi: 2 müstəqil icra × 9,425 sətir → birə-bir eyni
  determinism_digest; ledger-rebuild (SA-2) təkrarlayır. Yol boyu tapılan
  4 test-dizayn qüsuru (fixture id, qlobal-state sızması, regen hədəfi/ordinal)
  və 1 məhsul qüsuru (append-only batch oxusunda select_for_update →
  least-privilege rolda permission-denied) bağlandı.
- Köhnə identity-only artefaktlar LEGACY_REHEARSAL_IDENTITY_V1_RUN*.json kimi
  arxivləndi; yeni RUN1 tam-slice hesabatıdır.

### 26 avqust 2026 (gecə) — contact-pending staging + UI təsdiqi

- `stage_contact_pending` siyasət düyməsi (default OFF, fail-closed): yalnız
  `email_untrusted`-dan başqa qaydası olmayan sətirlər açıq bayraq + açıq
  blast-radius qapağı ilə locked hesab kimi stage edilir; email authority
  verilmir, aktivasiya evidence-li axında qalır.
- Rehearsal #3 (emsarena_rehearsal_96856e79a96c): SUCCEEDED — migrated/staged
  8,431, skipped 86 (boş/yararsız email), quarantined 28 (dublikat); cəm 8,545.
- Real-mənbə inteqrasiya testi (56) iki resume bug-ı tapdı və bağlandı:
  anchor rebase sırası + replay-staged sayımı; kəsilmə+resume eyni digest verir.
- UI təsdiqi (staging inspection, RLS-mirror emsarena_app rolu ilə):
  staged idxal hesabı DÜZGÜN parolla belə login edə bilmir (generic xəta,
  enumeration yox); superadmin admin-də 7,716 idxal tələbəsini real legacy
  email-ləri ilə görür (hamısı qeyri-aktiv); müəllim/tələbə rol girişləri və
  rol-məhdud sidebar-lar işləyir; standart üzv siyahısı yalnız aktiv üzvlükləri
  göstərir — staged-lər aktivasiyaya qədər orada görünmür (dizayn üzrə).
- Modul-ölçü büdcəsi üçün email-trust manifest köməkçiləri
  `rehearsal_email_trust.py`-yə ayrıldı (re-export ilə, semantika dəyişməz).

### 26 avqust 2026 — orkestrator canlı: iki real rehearsal + determinizm sübutu

- `legacy_import_rehearse` PG suite ilə birlikdə yaşıl (208 pass / 0 fail; 8 saatlıq
  advisory-lock self-deadlock insidenti test-in transaction=True-ya keçirilməsi və
  lock_timeout sığortası ilə bağlandı; batch-tamper testi iki-laylı sübuta keçirildi).
- Real 2.14 GB snapshot ilə Rehearsal #1 (emsarena_rehearsal_b4d40c19c429) və
  Rehearsal #2 (emsarena_rehearsal_9165f408727d — tam ayrı təmiz baza): hər ikisi
  SUCCEEDED; 8,545 = 8,517 skipped + 28 quarantined + 0 migrated; blocking issue 0;
  credential/PII çıxışı 0.
- Determinizm: iki run-un `determinism_digest`-i birə-birdir
  (`e602975f185cd627e8908fbe55749f5e8e8027edd011237f6506e4223ffb364f`);
  `--compare-report` qapısı fail-closed keçdi. M6-nın maşın-yoxlanan tələbi ödəndi.
- Artefaktlar: `reports/LEGACY_REHEARSAL_V1_RUN1.json` / `RUN2.json` (PII-siz).
- Mənbə girişi üçün `rehearsal_reader` (yalnız SELECT) istifadəçisi; server read_only=1.
- Qeyd: MariaDB konteynerinin host portu efemerdir — canlı port
  `docker port emsarena-legacy-source-rehearsal 3306` ilə götürülməlidir.

### 25 avqust 2026 — handoff, yarımçıq işin bağlanması və uzlaşma düzəlişləri

- İş Claude-a keçdi; dump SHA-256 eyni təsdiqləndi (2,142,912,818 bayt, 0600).
- Codex-in limitdə yarımçıq qalan snapshot refactor-u (account_cutover KeyError)
  düzəldildi — 13/13 test.
- 6 xətli paralel yoxlama aparıldı: SQLite full suite, PostgreSQL `-m postgres`,
  CI lint qapıları, son editlərin tamlığı, sənəd-kod drift inventarı, adversarial
  təhlükəsizlik baxışı.
- No-TRUNCATE guard-ları ilə Django test flush-ının ziddiyyəti superuser-only
  TRUNCATE keçidi ilə həll edildi (təhlükəsizlik itkisiz — MIG-SEC-012 qeydi);
  TRUNCATE-blok testləri qeyri-super probe roluna keçirildi.
- accounts 0013 asılılığı organizations zəncirinin ucundan yalnız blanket-GRANT
  edən 0007-yə endirildi (exams rollback testinin qraf tələsi).
- Dean qlobal axtarışı bərpa edildi (`can_search_directory` = member.view+unit.view
  rol imzası; scope tələb etmir), rbac `can_approve_grades` dict override bug-ı
  düzəldildi.
- M3.12–M3.25 ledger sətirləri əlavə olundu; R4 və R7 bağlandı.

### 24 avqust 2026 — M2/M3 təhlükəsizlik hardening

- Real legacy snapshot strict read-only preflight-dən keçdi; hash/ölçü/81 cədvəl
  və `0600` custody eyni təsdiqləndi.
- Qrup transferi non-destructive supersession-a keçirildi; audit xətası bütün
  əməliyyatı rollback edir və tarixi qiymət/jurnal/final sətirləri qorunur.
- Direct publish bypass bağlandı, approval↔published DB invariant-i və
  permission-specific fail-closed scope tətbiq edildi.
- Ledger design review-da tapılan overwrite/rollback boşluğu düzəldildi:
  canonical identity və per-run immutable observation ayrıldı.
- Legacy domain datası və real server yenə dəyişdirilməyib; production `NO-GO` qalır.
- Core registrar graph üçün child/parent tenant immutability, same-org FK və canlı
  instructor permission guard-ları əlavə edildi; qalan relation matrix açıq saxlanıldı.
- Credential-safe default-deny projection və reviewed issue/remap version tarixçəsi
  tamamlandı; legacy parol/PIN heç bir transform səthinə daxil edilmir.
- Kök təkrar yoxlamasında SQLite legacy 114 pass/34 skip, SQLite inteqrasiya
  203 pass/2 skip, PostgreSQL legacy 146 pass/2 skip, PostgreSQL inteqrasiya
  197 pass və PostgreSQL RLS/integrity 84 pass nəticəsi alındı.
- Təmiz PostgreSQL-də full schema, `0005` və `0041` rollback/reapply keçdi;
  ayrıca non-super/NOBYPASS migration-owner rehearsalları da yaşıl oldu.
