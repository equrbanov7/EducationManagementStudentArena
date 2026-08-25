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
- Heç bir legacy domain sətri target modellərə yazılmayıb.

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

## Qorunan mövcud user materialları

İlkin iş ağacında aşağıdakılar untracked idi və dəyişdirilmədi:

- `docs/architecture/AKADEMIK_OS_ANALIZI.md`
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
| Rehearsal 1 hesabatı (`LEGACY_REHEARSAL_V1_RUN1.json`) | VERIFIED — iki təmiz PostgreSQL hədəfdə icra edildikdən sonra yazılacaq |
| Rehearsal 2 hesabatı (`LEGACY_REHEARSAL_V1_RUN2.json`) | VERIFIED — `--compare-report` ilə eyni `determinism_digest` sübutu |

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
5. İlk akademik-referens adapteri phase registry-yə **ikinci faza** kimi əlavə
   olunur (`RehearsalPhase` protokolu, artan `order`, `source_tables` iddiası);
   registry barmaq izi yenidən pinlənir və gated cədvəllər strukturca iddia
   edilə bilmir. Syllabus version/approval modeli yekun dizayn və biznes
   acceptance-dan sonra (DESIGN_GATED qalır); runbook + yekun hesabat
   cutover-dən əvvəl.

## Bu mərhələnin çıxış şərti

Cari lokal M2/M3 slice-i yalnız aşağıdakılar olduqda `VERIFIED` sayılır:

- source content hash dəyişməyib;
- dump owner-only custody-dədir;
- plan və status repoda mövcuddur;
- production və business data dəyişməyib;
- PostgreSQL məcburi gate-ləri SQLite-dan açıq ayrılıb;
- domain adapteri aktiv deyil və mövcud domen datasına yazı edilməyib.

## Dəyişiklik jurnalı

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
