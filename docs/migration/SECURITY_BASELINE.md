# Legacy miqrasiya təhlükəsizlik baseline-i

Tarix: 24 avqust 2026  
Əhatə: legacy dump custody, staging/import pipeline, tenant/RLS, credential,
provenance, backup və cutover  
Cari qərar: `NO-GO for production`

Bu hesabat miqrasiya səthinə aiddir; bütün EMSArena üçün ümumi penetration test və
ya tam application security audit deyil. Heç bir secret, credential dəyəri və raw
şəxsi məlumat bu sənədə daxil edilməyib.

## İcra xülasəsi

Production cutover hazırda bloklanır. Əsas səbəblər:

- source dump əvvəl geniş fayl icazəli idi; `0600` düzəlişi tətbiq edilib, encrypted
  custody hələ qalıb;
- production runtime DB rollarının RLS-ə tabe olduğu real serverdə attestasiya
  edilməyib;
- registrar core migration graph-ında child/parent tenant immutability və same-org
  FK qoruması var; qalan relation matrix hələ tam deyil;
- canonical identity, per-run observation və lifecycle ledger-i lokal olaraq
  hazırdır; reviewed remap version tarixçəsi də verified-dir, domain adapter və
  full rehearsal açıqdır;
- legacy credential-safe projection verified-dir, ayrıca təhlükəsiz account
  activation yolu isə hazır deyil;
- qrup transfer history və approval/scope bypass lokal kodda bağlanıb, lakin qalan
  registrar relation-ları, syllabus, extractor/activation və rehearsal gate-ləri
  səbəbilə production yenə NO-GO-dur.

## Tapıntılar

### MIG-SEC-001 — Legacy dump PII və credential custody

- **Severity:** Critical / P0
- **Status:** qismən bağlanıb
- **Location:** `~/Downloads/myedudb.sql`; legacy sxem göstəriciləri
  `docs/db-compare/myedu_mysql_schema.sql:1039` və `:1265` ətrafı
- **Evidence:** 2,142,912,818 baytlıq dump tələbə/işçi password, açıq
  `show_password`, PIN, FIN, telefon, kart və IP sahələri saxlayırdı; fayl mode-u
  `0664` idi. 23 avqustda mode `0600` edildi və SHA-256 dəyişmədən təsdiqləndi.
- **Impact:** eyni hostdakı başqa user/group məlumatı oxuya və əvvəlki mode-da
  group source-u dəyişə bilərdi; həm məxfilik, həm source integrity pozulardı.
- **Fix:** owner-only encrypted quarantine, ayrıca key custody, read-only immutable
  source copy, SHA/size/acquisition manifest və hər importdan əvvəl fingerprint
  verification.
- **Mitigation:** hazırda `0600`; SQL dump-ları `.gitignore` bloklayır. Strict
  `legacy_import_preflight` real faylda `O_NOFOLLOW`, streamed SHA-256, ölçü,
  inode/mtime sabitliyi və 81 `CREATE TABLE` marker-i ilə PASS verib.
- **False-positive notes:** OS-level disk encryption ola bilər, amma ayrıca
  migration custody və access log app/repo səviyyəsində görünmür; runtime-da
  təsdiqlənməlidir.
- **Close gate:** encrypted restricted storage + restore/read test + unchanged SHA.

### MIG-SEC-002 — Production runtime DB rolu fail-closed deyil

- **Severity:** Critical / P0
- **Status:** açıq; lokal disposable test rolu təsdiqlənib
- **Location:** `docker-compose.prod.yml:56`, `apps/organizations/checks.py:56`,
  `scripts/provision-app-db-role.sh:39`
- **Evidence:** runtime DB user boş olduqda bootstrap/owner user-ə fallback edir;
  enforcement default `warn`-dır. DB check connection xətasını boş nəticə kimi
  qaytarır. Provision script düzgün `NOSUPERUSER NOBYPASSRLS` rol yarada bilir.
- **Impact:** superuser və ya `BYPASSRLS` rolu `FORCE RLS` daxil bütün tenant
  izolyasiyasını keçə bilər.
- **Fix:** `APP_DATABASE_*` fail-closed, `EMS_DB_ROLE_ENFORCE=error`, web/worker/
  beat/importer konteynerlərinin hər birində runtime role attestation. Owner URL
  yalnız explicit DDL release üçün.
- **Mitigation:** disposable PG-də test app rolu `rolsuper=false` və
  `rolbypassrls=false` kimi təsdiqlənib. Ayrı synthetic non-super/NOBYPASS
  migration-owner ilə legacy `0005` və registrar `0041` rehearsal-ları keçib;
  bu yenə production runtime sübutu deyil.
- **False-positive notes:** real `.env` artıq restricted role istifadə edə bilər;
  yalnız real container içindən SQL attestation tapıntını bağlayır.
- **Close gate:** bütün runtime-larda `rolsuper=false`, `rolbypassrls=false`,
  `rolcreatedb=false`, `rolcreaterole=false`.

### MIG-SEC-003 — Registrar cross-tenant FK integrity tam deyil

- **Severity:** Critical / P0
- **Status:** core migration graph lokal verified; tam relation matrix açıqdır
- **Location:** `apps/registrar/integrity.py`, `journal_access.py`,
  `migrations/0041_migration_target_tenant_integrity.py`
- **Evidence:** 0041 core graph-də child və parent `organization_id` mutation-ını,
  same-org parent FK-ləri, student membership-i, offering/lesson instructor üçün
  aktiv membership+role+`grade.input` səlahiyyətini DB trigger-ləri ilə qoruyur.
  Tətbiq qatı hər request-də instructor səlahiyyətini yenidən yoxlayır; membership,
  role və ya permission revoke olduqda journal GET/POST 404 olur. Core PostgreSQL
  negative matrix 11/11, registrar+organizations RLS/integrity suite-i 84/84 keçib.
- **Impact:** org-A sətri org-B parent/user-a bağlana, akademik tarix qarışa və
  sonrakı join/export/snapshot-da məlumat sızıntısı yarana bilər. Form queryset
  filtrləri ETL, `bulk_create` və owner SQL-i qorumur.
- **Fix:** core graph üçün tətbiq olunub. `GroupElectiveChoice`, rubric/criterion,
  self-work, coursework, resit, correction və `entered_by/decided_by` kimi qalan
  əlaqələr ayrıca matrix-ə əlavə edilməlidir.
- **Mitigation:** importer hər tenantı ayrıca kiçik transaction-da `SET LOCAL`
  tenant context ilə işlətməli, job-wide bypass açmamalıdır.
- **False-positive notes:** core graph-də həm Python early validation, həm PostgreSQL
  raw/bulk write guard-u var. Tapıntı yalnız bütün import ediləcək relation-lar
  eyni səviyyədə xəritələnəndə tam bağlanır.
- **Close gate:** qalan target əlaqələr üçün cross-tenant INSERT/UPDATE və parent
  tenant mutation negative PostgreSQL testləri; violation count = 0.

### MIG-SEC-004 — Idempotency və provenance ledger

- **Severity:** High / P0
- **Status:** control-plane hissəsi verified; domain rehearsal açıqdır
- **Location:** `apps/legacy_import/models.py`, `review_models.py`,
  `services/ledger.py`, `services/review.py`, `services/versioning.py`,
  migrations `0001`–`0005`
- **Evidence:** canonical source identity global unique-dir; target/hash/state
  səssiz overwrite edilmir. Hər run üçün immutable `LegacyEntityObservation`
  saxlanır, uğur sayları observation-lardan DB-də hesablanır, unresolved
  error/critical issue success-i bloklayır. Reviewed remap stable canonical map-i
  dəyişmir; reviewer/time/reason/evidence ilə append-only version yaradır. Reverse
  v2 və ya review history taparsa məlumatı silmədən STOP edir. Tenant/source lock
  PostgreSQL-də advisory xact lock, SQLite-da yalnız process fallback istifadə edir.
- **Impact:** yarımçıq run-dan sonra təhlükəsiz resume yoxdur; rerun duplicate və ya
  səssiz overwrite yarada, target sətrin mənbə izi itə bilər.
- **Fix:** tenant-scoped run/map/observation/issue modelləri, unique source
  identity, per-batch checkpoint, deterministic source ordering və digest.
- **Mitigation:** RLS, cross-scope/lifecycle/version trigger-ləri, DELETE/TRUNCATE
  guard və restricted-role privilege testləri PostgreSQL-də keçib; domain import
  hələ qadağandır. Legacy suite SQLite-da 114 pass/34 skip, PostgreSQL-də
  146 pass/2 skip verib.
- **False-positive notes:** bəzi domen-specific import token-ləri var, amma ümumi
  9M-row legacy provenance müqaviləsini ödəmir.
- **Close gate:** control-plane exact rerun və reviewed-remap workflow-u lokal
  verified-dir. Tapıntının tam bağlanması üçün real RBAC authorizer/tenant-aware
  target registry qoşulmalı və iki full domain rehearsal eyni count/digest verməlidir.

### MIG-SEC-005 — Legacy credential activation yolu təhlükəsiz ayrılmayıb

- **Severity:** Critical / P0
- **Status:** credential projection lokal verified; activation açıqdır
- **Location:** `apps/accounts/management/commands/import_users_from_excel.py:51`,
  `apps/accounts/management/commands/provision_student_credentials.py:43`
- **Evidence:** mövcud generic alətlər plaintext ilkin parol qəbul və credential
  CSV yarada bilir. Legacy source isə `students.password`, `students.show_password`,
  `workers.password` və `workers.pin_for_lock` daşıyır. Yeni versioned default-deny
  field contract yalnız explicit audited sütunları select edir; credential alias-ləri
  allowlist-dən üstün deny edilir və row/log metadata xam dəyər saxlamır.
- **Impact:** kompromis sayılmalı köhnə credential-in reuse-u account takeover,
  CSV export isə ikinci credential dump yarada bilər.
- **Fix:** parser səviyyəsində credential denylist/allowlist; mövcud target paroluna
  heç vaxt overwrite etməmək; yeni hesabı unusable/locked yaratmaq; qısaömürlü,
  hash-lənmiş, bir dəfəlik activation token + ownership verification + yeni
  Django-validated password.
- **Mitigation:** generic Excel credential commands legacy ETL-də reuse edilmir;
  field-contract focused suite-i 56/56 keçib. Real MySQL extractor hələ bu contract-a
  qoşulmadığı üçün end-to-end gate açıqdır.
- **False-positive notes:** projection credential-safe-dir, PII-free deyil; FIN,
  ad, e-mail və telefon yalnız restricted migration mühitində işlənə bilər.
- **Close gate:** import/log/export/quarantine-da credential dəyəri = 0; existing
  password overwrite = 0.
- **2026-08-25 əlavəsi (FAZA 3 / SLICE 2 — aktivasiya körpüsü):** rehearsal indi
  `signed_authoritative_export` səbəb kodlu `AccountActivationEvidence`-i
  **proqramla** kəsə bilir. Evidence digest-i uydurulmur: o,
  `sha256(transform_version ‖ snapshot_sha256 ‖ "student" ‖ legacy_pk)` təmiz
  funksiyasıdır və `snapshot_sha256` 2.14 GB dump-ın `table_plan.SOURCE_SNAPSHOT_SHA256`-də
  pinlənmiş, Faza A tərəfindən attestasiya olunan dəyəridir — **həmin pin imzanın
  özüdür**. Təmiz funksiya olması eyni zamanda təkrar-aktivasiyanı
  `identity_access`-in `evidence_digest`/`reason_code`/`role_ref` müqayisəsinə görə
  konstruksiyaya görə uyğun edir, `accounts_activation_evidence_user_uniq` isə
  ikiqat aktivasiyanı struktur olaraq mümkünsüz saxlayır. Aktivasiyadan **dərhal
  sonra, eyni atomik blokda** `email_verified=False` + `password_change_required=True`
  yazılır (E-11): aktivasiya «reyestr bu şəxsi tanıyır» deməkdir, «bu email
  təsdiqlidir» yox — legacy ünvan bərpa üçün dərhal yararsız olur və hesab mövcud
  ilk-giriş axınına (yeni email → OTP → yeni parol) düşür. Bütün bunlar
  `--stage-and-activate` (default **bağlı**) + `--max-activated-accounts` (default
  **0**) arxasındadır və hər ikisi `policy_digest`-dədir. Kredensial çatdırılması
  bu dilimdə **implementasiya edilmir**: aktivləşdirilmiş hesabda parol hələ də
  yararsızdır (`set_unusable_password()`), tövsiyə olunan yol isə mövcud
  `provision_student_credentials --generate --csv` (çap olunmuş birdəfəlik parol)
  və CSV-nin paylanmadan sonra məhv edilməsidir.

### MIG-SEC-006 — Böyük ETL owner Django migration/release yoluna düşə bilər

- **Severity:** High / P0
- **Status:** planla bloklanıb, texniki gate hazırlanmalıdır
- **Location:** `docker/release.sh:7`, `docker/prod-entrypoint.sh:13`
- **Evidence:** release owner `MIGRATION_DATABASE_URL` ilə `manage.py migrate`
  işlədir və startup bunu tetikləyə bilər.
- **Impact:** 9M-row `RunPython` owner rolunda RLS bypass, uzun lock/WAL, yarımçıq
  deploy və restart zamanı qeyri-müəyyən rerun yarada bilər.
- **Fix:** Django migration yalnız schema/constraint/ledger; data ETL ayrıca
  explicit job/management command, məhdud DML role, direct PostgreSQL endpoint,
  kiçik batch və checkpoint.
- **Mitigation:** import command production deploy/startup-a qoşulmayacaq.
- **False-positive notes:** hazırda belə legacy `RunPython` yoxdur; risk gələcək
  implementasiya səhvinə qarşı qəbul gate-idir.
- **Close gate:** release pipeline inspection + rehearsal zamanı importun yalnız
  explicit operator action ilə başlaması.

### MIG-SEC-007 — Qrup transferi tarixi və audit atomicliyi

- **Severity:** High / P0
- **Status:** lokal fix verified; production rollout açıq
- **Location:** `apps/registrar/transfer.py:52`, `:63`, `:20`;
  `apps/registrar/migrations/0024_journal_mark_immutability_trigger.py:7`
- **Evidence:** əvvəl köhnə Enrollment delete edilirdi. İndi köhnə qeydiyyat
  `DROPPED` olur və `superseded_by` ilə yeni qeydiyyata bağlanır; LessonMark,
  ComponentScore, FinalGrade, CourseWork və JournalCorrection saxlanır. Audit
  uğursuzluğu eyni transaction-u rollback edir.
- **Impact:** legacy tarix import edildikdən sonra adi transfer qiymət/davamiyyət
  və provenance-i səssiz itirə bilər.
- **Fix:** tətbiq olunub; PostgreSQL supersession trigger-i cross-org/student/
  subject/period, self-link və cycle-i reject edir.
- **Mitigation:** SQLite service/model validation, production PostgreSQL trigger.
- **False-positive notes:** business əvvəl "yeni qrupda sıfırdan" istəyə bilər;
  bu, köhnə tarixin silinməsini əsaslandırmır, yalnız yeni active grade context-i
  müəyyən edir.
- **Close gate:** lokal SQLite/PostgreSQL regression-ları keçib. Rolloutdan əvvəl
  eyni semestrdə əvvəllər DROPPED qrupa geri dönüş üçün enrollment-epoch biznes
  qərarı tələb olunur.

### MIG-SEC-011 — Approval bypass və permission scope fail-open

- **Severity:** Critical / P0
- **Status:** lokal fix verified; data reconciliation/rollout açıq
- **Location:** `apps/registrar/approval.py`, `finals.py`, `views.py`,
  `migrations/0040_assessment_scheme_publish_invariant.py`;
  `apps/organizations/scoping.py`
- **Evidence:** direct `publish` POST artıq 404-dür; compatibility service yalnız
  artıq `APPROVED + published` state-i qəbul edir. DB CHECK publication ilə final
  approval-u ekvivalent edir. Approval transition row-lock və atomic mandatory
  audit istifadə edir. Scope yalnız konkret permission-u verən membership-dən
  həll olunur; UNIT rol scope-suzdursa deny edilir.
- **Impact:** əvvəl müəllim approval chain-i keçə, scope-suz rəhbər org-wide inbox
  və analitika görə bilirdi.
- **Mitigation:** cari geniş regression SQLite-da 203 pass/2 PG skip,
  PostgreSQL-də 197/197 pass verib; ayrıca RLS/integrity suite-i 84/84 keçib.
  Console object-scope tam olmadığı üçün yalnız org-wide scope-a açıqdır.
- **Close gate:** 0040-dan əvvəl mövcud `published/status` ziddiyyətləri audit
  sübutu ilə manual reconciliation edilməlidir; migration onları səssiz dəyişmir.

### MIG-SEC-008 — SQLite RLS/trigger təhlükəsizlik sübutu deyil

- **Severity:** High / P1
- **Status:** idarə olunur
- **Location:** `core/rls.py:27`, registrar RLS migration vendor guards,
  `apps/registrar/tests/test_rls.py:21`
- **Evidence:** non-PostgreSQL-də RLS helper və migration policy-ləri no-op olur;
  immutability trigger yoxdur.
- **Impact:** yalnız SQLite testinin yaşıl olması cross-tenant write, RLS və
  history protection səhvlərini production-a buraxa bilər.
- **Fix:** disposable PG-də schema, restricted role, RLS, cross-FK, triggers,
  concurrency, resume və restore gate-ləri.
- **Mitigation:** cari disposable PG full migration/rollback baseline, core
  cross-FK negative matrix və registrar/organizations RLS suite-i yaşıl keçib;
  core xaricində qalan relation matrix ayrıca açıqdır.
- **False-positive notes:** parser/unit testləri üçün SQLite düzgün və sürətli
  seçimdir; risk yalnız onu PG sübutu kimi istifadə etməkdir.
- **Close gate:** bütün məcburi `postgres` marker testləri və migration rehearsal
  real PostgreSQL-də yaşıl.

### MIG-SEC-009 — Quarantine, audit və backup PII minimallaşdırması natamamdır

- **Severity:** High / P1
- **Status:** açıq
- **Location:** `docs/architecture/AKADEMIK_OS_ANALIZI.md:1576`,
  `apps/audit/models.py:141`, `core/audit.py:49`, `scripts/ops/db_backup.sh:17`
- **Evidence:** konsept sənəd raw payload CSV təklif edir; audit JSON arbitrary
  changes saxlaya bilir; mövcud log filter bəzi sahələri maskalayır, amma FIN,
  kart, birthday, ad və arbitrary raw payload üçün migration-specific allowlist
  yoxdur. Backup gzip-dir, ayrıca encryption sübutu yoxdur.
- **Impact:** exception CSV, audit/log və backup ikinci PII dump-a çevrilə bilər.
- **Fix:** shareable report-də yalnız source locator, rule code və digest;
  restricted encrypted quarantine-da da credential-ləri atmaq; migration-specific
  allowlist redactor; backup/quarantine encryption, access log və retention.
- **Mitigation:** raw payload app ledger modelinə daxil edilməyəcək.
- **False-positive notes:** host/disk encryption və external backup encryption ola
  bilər; app/repo-dan görünmür və runtime sübut tələb edir.
- **Close gate:** redaction tests + scratch restore + access/retention review.

### MIG-SEC-010 — 9M import üçün transaction/pooling modeli ayrıca olmalıdır

- **Severity:** Medium-High / P1
- **Status:** planlanıb
- **Location:** `core/rls_pooling.py:85`,
  `apps/accounts/management/commands/import_users_from_excel.py:63`
- **Evidence:** mövcud worker helper bütün əməliyyatı `transaction.atomic()` ilə
  sarıya və generic import job-wide bypass aça bilər.
- **Impact:** 9M sətirdə uzun transaction, böyük WAL, lock, retry partlayışı və
  tenant blast radius yaradar.
- **Fix:** PgBouncer transaction pool-dan kənar direct PG, kiçik explicit batch,
  `SET LOCAL` tenant, lock/statement timeout, checkpoint/retry və deterministic
  order.
- **Mitigation:** ilk control-plane slice-i business data yazmır; full ETL ayrıca
  adapterlərə bölünür.
- **False-positive notes:** mövcud helper kiçik task-lar üçün düzgündür; risk onu
  bütöv 9M job-a tətbiq etməkdir.
- **Close gate:** failure injection və resume rehearsal-ında duplicate/partial
  success yoxdur, ölçülmüş WAL/lock window qəbul edilir.

### MIG-SEC-012 — 2026-08-25 müstəqil adversarial baxış (Claude) — qalıq P2-lər

2026-08-25-də miqrasiya-kritik yeni modullara (staged hesab lifecycle-ı, qrup-transfer
GUC bağlaması, MariaDB gateway, batch hash-chain, komanda qapısı) müstəqil hücumçu-
perspektivli baxış keçirildi. **App səthindən keçən heç bir P0/P1 bypass tapılmadı.**
Xüsusilə təsdiqləndi (yenidən yoxlamağa ehtiyac yoxdur): saxta-GUC qrup-transfer yolu
həqiqətən bağlıdır (evidence sətri `pg_current_xact_id()`-ə bağlıdır, INSERT app-roldan
REVOKE edilib, DEFERRABLE constraint trigger commit-i yalnız tam lineage + audit ilə
buraxır); staged hesab autentifikasiya edə və sessiya saxlaya bilmir; bütün 49
SECURITY DEFINER funksiyası search_path-pinned və REVOKE ALL FROM PUBLIC-dir;
MariaDB plaintext rejimi production-da əlçatmazdır və loopback yoxlaması DNS/octal/
IPv4-mapped hiylələrinə davamlıdır; credential/DSN sızması yoxdur.

Qalıq P2-lər (hamısı artıq ələ keçirilmiş app DB rolu — SQLi/creds leak — tələb edir;
app səthindən çatılmır; hardening backlog-udur, emergency deyil):

| ID | Qalıq risk | Qeyd |
|---|---|---|
| P2-a | Staged→active evidence qapısı profil DELETE+re-INSERT ilə keçilə bilər (app-rol DML) | Trigger yalnız UPDATE keçidini yoxlayır; INSERT `access_state='active'` evidence istəmir. Fix: INSERT-i də gate-lə və ya profil DELETE-i qadağan et |
| P2-b | Aktivasiya aktoru `app.current_user_id` GUC-una söykənir | Audit aktor sahəsi app-prosesin bütövlüyü qədər etibarlıdır (misattribution). Sənədləşdirilmiş qəbul edilə bilər |
| P2-c | Batch hash-chain MƏZMUN bütövlüyü yalnız Python `finish_run`-da yoxlanır | DB run-guard say-reconciliation edir, digest recompute etmir; birbaşa SQL terminal keçidi digest saxtakarlığını tuta bilməz (saylar yenə qorunur). Fix: digest recompute-u DB funksiyasına köçür |
| P2-d | `stage_imported_account` cross-tenant username/email enumeration + namespace squatting | Fərqli kolliziya kodları qlobal mövcudluğu sızdırır; member.invite ilə inert staged hesabla ad tutmaq olur. Fix: generik kolliziya kodu + rate-limit |

**Dizayn qeydi — superuser TRUNCATE keçidi (2026-08-25):** bütün no-TRUNCATE guard
funksiyalarına `session_user` PostgreSQL superuser olduqda TRUNCATE keçidi əlavə
edildi. Səbəb: Django TransactionTestCase teardown `flush`-ı TRUNCATE işlədir və test
infrastrukturu bootstrap superuser ilə işləyir. Təhlükəsizlik itkisi yoxdur: superuser
onsuz da trigger-i `DROP TRIGGER` ilə söküb keçə bilərdi — real qorunma app-rolun
privilege REVOKE-u + qeyri-super rollar (o cümlədən cədvəl owner-i) üçün trigger-dir;
production runtime rolu `NOSUPERUSER` hard gate-i ilə təsbitlənib (MIG-SEC-002).
DELETE/UPDATE append-only qorunması superuser üçün də dəyişməz qalır.

## Production təhlükəsizlik acceptance gate-ləri

1. Source SHA/size dəyişməyib; owner-only encrypted storage və access log var.
2. Web, worker, beat və importer `NOSUPERUSER NOBYPASSRLS` kimi attestasiya edilib.
3. Cross-tenant relation negative PostgreSQL matrix tam yaşıl, violation = 0.
4. Legacy password/PIN import, log, export və quarantine dəyəri = 0.
5. İki full rehearsal eyni count və reconciliation digest verir; duplicate = 0.
6. Hər source sətir izahlı status alır; səbəbsiz exception = 0.
7. Transfer və delete regression-ları akademik tarix/provenance-i qoruyur.
8. Backup scratch PostgreSQL-ə uğurla restore edilir.
9. Cutover write-freeze, owner/importer ayrılığı və iki nəfərlik GO ilə aparılır.
10. Açılışdan sonra 24–48 saat RLS, audit, 5xx və reconciliation monitorinqi var.

Bu gate-lərdən hər hansı biri fail olarsa production qərarı `STOP`-dur.

## Müsbət mövcud nəzarətlər

- SQL dump faylları Git ignore qaydaları ilə bloklanır.
- Tenant cədvəllərində FORCE RLS presedentləri mövcuddur.
- Restricted app role provision script-i hazırdır.
- Audit/grade event üçün append-only PostgreSQL trigger presedentləri var.
- Production log filter və first-login password flow mövcuddur.
- Disposable PG16-da bütün cari migration-lar, `0005`/`0041` rollback-reapply,
  registrar core integrity və RLS baseline testləri uğurla keçib.
- Non-super/NOBYPASS synthetic migration owner-ları ilə RLS-aware backfill və
  invalid-row precheck fail-closed davranışı ayrıca təsdiqlənib.
