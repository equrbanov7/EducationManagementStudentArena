# EMSArena legacy məlumat miqrasiyası — əsas plan

Tarix: 24 avqust 2026  
Status: icradadır — M0/M1 və M2/M3 core təhlükəsizlik slice-ləri verified  
Əsas məqsəd: legacy MariaDB snapshot-ını lokal/staging mühitində deterministik
şəkildə EMSArena modelinə uyğunlaşdırmaq və real server hazır olduqda eyni,
yoxlanmış pipeline ilə bir dəfəlik təhlükəsiz cutover etmək.

## Qısa qərar

Birbaşa `MariaDB -> production PostgreSQL` kopyası edilməyəcək. Düzgün yol:

1. mənbə dump dəyişdirilməz və hash-lə təsdiqlənmiş saxlanılır;
2. hədəf sistem tarixi itirən və tenant sərhədini poza bilən P0-lardan təmizlənir;
3. ayrıca idempotent miqrasiya idarəetmə qatı qurulur;
4. məlumat staging-də çevrilir, problemli sətirlər silinmir, izahlı quarantine-a ayrılır;
5. eyni snapshot-la ən azı iki tam PostgreSQL rehearsal aparılır;
6. yalnız say, hash, akademik nəticə və təhlükəsizlik gate-ləri keçdikdən sonra
   production cutover edilir.

SQLite yalnız parser, transformasiya və engine-agnostic unit testləri üçündür.
RLS, trigger, cross-tenant FK, transaction və real miqrasiya sübutu PostgreSQL-də
alınmalıdır.

## 1. Əhatə və dəyişməz prinsiplər

### Məqsədlər

- 9,044,531 legacy sətrin hər birini `migrated`, `skipped` və ya `quarantined`
  kateqoriyalarından birinə izahlı şəkildə salmaq.
- Canlı akademik məlumatı və read-only arxiv sərhədini açıq qaydalarla ayırmaq.
- Hər target obyektin legacy mənbəyini, transform versiyasını və import run-ını
  sonradan sübut edə bilmək.
- Təkrar başladılan job-un duplicate yaratmamasını və uğurlu sətirləri səssizcə
  dəyişməməsini təmin etmək.
- Real serverdə yalnız əvvəlcədən rehearsal olunmuş kod, konfiqurasiya və runbook
  işlətmək.

### Qəti qadağalar

- Legacy dump-da `UPDATE`, `DELETE`, in-place cleanup və ya manual düzəliş yoxdur.
- 9M sətr Django `RunPython` migration-na yerləşdirilmir.
- Import release/startup skriptinə avtomatik bağlanmır.
- Legacy parol, açıq parol, PIN və recoverable secret yeni auth sisteminə daşınmır.
- Raw PII console, log, audit JSON-u və paylaşılacaq CSV/hesabatlara yazılmır.
- Tenant-scoped import üçün job boyu qlobal `bypass_rls()` açılmır.
- Tarixi Enrollment, qiymət, davamiyyət və final nəticə rollback adı ilə CASCADE
  silinmir.
- SQLite nəticəsi production təhlükəsizlik sübutu kimi təqdim edilmir.
- Product məntiqi legacy cədvəl formasına uyğunlaşdırılaraq geriyə çəkilmir;
  semantika təsdiqlənmiş EMSArena domen modelinə çevrilir.

## 2. Təsdiqlənmiş ilkin vəziyyət

### Mənbə snapshot

| Fakt | Təsdiqlənmiş dəyər |
|---|---:|
| SQL dump ölçüsü | 2,142,912,818 bayt |
| SHA-256 | `177ef2269027395fd3a80fc1dd592aab565dda7cbca5f6f08785313881d68fe0` |
| Cədvəl | 81 |
| Dəqiq sətir | 9,044,531 |
| Boş cədvəl | 15 |
| Sütun | 647 |
| Declared foreign key | 0 |
| Declared unique secondary constraint | 0 |
| Trigger | 2 |

`74.01%` göstəricisi row-volume-weighted ekspert schema-fit balıdır; miqrasiya
uğur faizi deyil. Böyük jurnal cədvəli bütün sətirlərin 56.78%-ni təşkil etdiyi
üçün bu rəqəm funksional hazırlığı olduğundan yüksək göstərə bilər.

### Əsas data-quality reconciliation yükü

- 7,816 tələbədən 7,225-də FIN boşdur.
- Bütün 7,816 tələbədə legacy `speciality_id=0`-dır.
- 5,135,289 aktiv jurnal balından 23,979-u olmayan tələbə ID-sinə bağlıdır.
- 1,306,274 type-1 exam answer-dan 575,715-i olmayan sual ID-sinə bağlıdır.
- 4,140,769 aktiv jurnal bal dəyəri numeric deyil; bunlar avtomatik "yararsız"
  sayılmır, business-code mapping tələb edir.
- 13,875 jurnalın 1,531-də müəllim reference-i orphan-dır.
- Bütün 1,306,373 exam answer sətrində `point` boşdur; bal ayrıca qaydadan
  bərpa və ya reconciliation edilməlidir.
- Legacy credential sahələri 32-hex password-lar, açıq `show_password` və worker
  PIN-ləri ehtiva edir; heç biri yeni auth credential kimi istifadə olunmayacaq.

### Semantik düzəlişlər

- `allowed_qb` QuestionBank deyil; sənədli üzrlü iştirak intervalıdır.
- `imthngrscxsblr` exam PIN/ticket deyil; giriş/çıxış bal cəhd tarixçəsidir.
- `track_student` tələbə ID-si daşımır; default ProctoringLog importu təhlükəlidir.
- `umumi_orta_bal` direct insert mənbəyi deyil; reconciliation göstəricisidir.
- `journals_dates`, parsed və teacher-added tarixləri canonical precedence ilə
  dedupe edilməlidir.
- Archive point-lər birbaşa live `LessonMark` kimi yazılmamalıdır.

### Lokal mühit

- `.env` mövcuddur, Git-də izlənmir və PostgreSQL URL konfiqurasiyası var;
  heç bir secret bu sənədə çıxarılmayıb.
- Konfiqurasiya olunmuş lokal PostgreSQL hazırda reachable deyil.
- `DATABASE_URL="sqlite://" python manage.py check` 0 issue ilə keçir.
- Docker daemon və PostgreSQL 18 client alətləri hazırdır; izolə disposable
  PostgreSQL qurmaq mümkündür.
- Repo pin-ləri ilə izolə `.venv` qurulub: Python 3.11.6, Django 5.2.16;
  dependency check təmizdir. Global Python mühiti migration sübutu kimi istifadə
  edilmir.

## 3. Hədəf sistem importdan əvvəl qorunmalıdır

Hazır target-a dərhal data yazmaq təhlükəlidir. Aşağıdakı P0-lar əvvəl bağlanır;
24 avqust lokal statusu mötərizədə göstərilir:

1. **Qrup transferi tarixi silir — lokal fix verified.** Köhnə Enrollment artıq
   delete edilmir; `DROPPED + superseded_by` olur və tarixçə qorunur.
2. **Birbaşa publish approval zəncirini keçir — lokal fix verified.** Direct POST
   bağlanıb, rəsmiləşmə yalnız state machine və DB invariant-i ilə mümkündür.
3. **Scope olmayan rəhbər fail-open olur — lokal fix verified.** Scope konkret
   permission-u verən membership-dən həll edilir; scope-suz UNIT rol deny olur.
4. **Cross-tenant FK — core graph lokal verified, tam matrix açıqdır.** Core
   migration graph-da child/parent organization immutability, same-org FK, active
   student membership və canlı instructor permission PostgreSQL-də qorunur.
   Elective/rubric/self-work/coursework/resit/correction və actor FK-ləri növbəti
   matrix-də bağlanmalıdır.
5. **Sillabus source-of-truth — design backlog.** Bu, hazır dizaynın “broken”
   olması deyil. Legacy syllabus canlı journal-a yalnız yekun UX/business acceptance,
   versioned/approved target model və workflow təsdiqlənəndən sonra daxil ola bilər.

Bu dəyişikliklər məhsulun mahiyyətini dəyişmir; mövcud akademik məntiqin tarixi,
təsdiq və tenant bütövlüyünü qoruyur.

## 4. Hədəf miqrasiya arxitekturası

```text
Immutable legacy dump
        |
        v
Source manifest + fingerprint verification
        |
        v
Restricted staging (raw source read-only)
        |
        +--> Sanitised quarantine / reconciliation queue
        |
        v
Deterministic transforms + identity maps
        |
        v
Tenant-scoped PostgreSQL batches
        |
        +--> Live EMSArena domain data
        +--> Read-only historical archive
        |
        v
Counts + hashes + academic reconciliation + security gates
```

### Ayrı `apps.legacy_import` control plane-i

İlk kod slice-i mövcud domen datasına yazmayacaq. Yeni app yalnız importun
izlənməsi və idempotency üçün aşağıdakı modelləri saxlayacaq:

#### `LegacyMigrationRun`

- target organization;
- source system və snapshot SHA-256/ölçü;
- schema/transform version;
- `profile`, `rehearsal`, `cutover` mode-u;
- status, start/end vaxtı, təhlükəsiz say xülasəsi;
- actor və run mənşəyi;
- DSN, parol və raw credential saxlanmır.

#### `LegacyEntityMap`

- unique `(organization, source_system, entity_type, legacy_pk)`;
- source row hash, transform version, target model label/string PK və state üçün
  canonical identity;
- canonical target/hash/state səssiz overwrite edilmir;
- exact rerun no-op, fərqli mapping explicit conflict-dir.

#### `LegacyEntityObservation`

- unique `(run, entity_map)`;
- hər rehearsal/cutover üçün source hash, transform, target, state və
  reconciliation snapshot-ı;
- əvvəlki run nəticəsi sonrakı run tərəfindən overwrite edilmir;
- terminal run sayları observation-lardan DB səviyyəsində hesablanır.

#### `LegacyEntityMapVersion`

- canonical `LegacyEntityMap` stable source identity kimi dəyişməz qalır;
- ilkin snapshot `v1`, yalnız təsdiqli conflict review-dan sonra yeni append-only
  version yaradılır;
- predecessor/supersedes lineage, recorded run, reviewer/time/reason/evidence və
  tətbiq edən actor saxlanır;
- review/version tarixçəsi varsa rollback onu silmir, fail-closed dayanır.

#### `LegacyMigrationIssue`

- run, source table/entity və opaque legacy PK;
- rule code, severity, review status;
- reviewer, review vaxtı, token-formalı reason code və evidence SHA-256;
- raw row əvəzinə payload digest və redaktə edilmiş təhlükəsiz context;
- eyni run+sətir+qayda üçün unique constraint.

Bütün control-plane cədvəlləri tenant-scoped və PostgreSQL `ENABLE/FORCE RLS`
ilə qorunur. Run-map-observation-version-issue organization uyğunluğu,
lifecycle və append-only tarixçə DB səviyyəsində məcbur edilir.

### Faza registry seam-i (adapterlərin yeganə giriş nöqtəsi)

Rehearsal orkestratoru heç bir adapteri birbaşa tanımır. `RehearsalPhase`
protokolunu (`phase_key`, artan `order`, `source_tables`, `entity_types`,
`declared_source_rows(plan)`, `run(context)`) həyata keçirən fazalar kod-sahibli
registry-yə daxil olur və registry `load_legacy_table_plan` kimi barmaq izi ilə
attestasiya olunur. Validator fail-closed-dur:

- `phase_key` unikal, token-formalı və ≤ 32 simvol;
- `order` ciddi artan və unikal;
- hər `source_table` fixed plan-da qeydiyyatdan keçmiş olmalıdır;
- **bir cədvəl iki faza tərəfindən iddia edilə bilməz**;
- yalnız `TRANSFORM_CANDIDATE` / `REVIEW_GATED` / `VALIDATE_ONLY` iddia edilə
  bilər — `DESIGN_GATED` (12 sillabus cədvəli), `SECURITY_GATED`,
  `UNKNOWN_GATED`, `ARCHIVE_GATED`, `EMPTY_GATED` **strukturca** əlçatmazdır;
- iddia edilən hər sətirdə `adapter_key is None` invariantı;
- `declared_source_rows(plan)` iddia edilən cədvəllərin `expected_rows` cəminə
  bərabər olmalıdır;
- registry barmaq izi pinlənmiş dəyərlə üst-üstə düşməlidir.

Faza kontraktı: `PhaseBatchRecord`-lar hər `source_table` üçün artan
`first_legacy_pk` sırasında və 1-dən başlayan bitişik `sequence` ilə verilir;
ledger sətirləri (`upsert_entity_map` → `upsert_issue`) onları sayan batch-dən
**əvvəl** yazılır; eyni anda `policy.batch_rows`-dan çox source sətri saxlanmır
(böyük cədvəllər `compile_pk_chunk_query` ilə pəncərələnir); faza öz MariaDB
bağlantısını açmır və `finish_run` çağırmır.

### Disposable hədəf provisioning kontraktı

Rehearsal yalnız təsdiqlənmiş şəkildə birdəfəlik bir PostgreSQL bazasına
aparılır. On müstəqil interlock-un hamısı tələb olunur: açıq settings opt-in
(`LEGACY_REHEARSAL_TARGET_DISPOSABLE is True`), `local`/`test` mühiti,
`postgresql` vendor-u, `emsarena_rehearsal_<12 hex>` ad şablonu, loopback host,
5432-dən fərqli port (1024-65535), baza səviyyəli marker, `rolsuper=false`,
`rolbypassrls=false`, aktiv `app.bypass_rls` olmaması və tətbiq edilmiş migration
başlığı. Marker DBA-nın həmin bazada apardığı qəsdli əməliyyatdır:

```sql
CREATE DATABASE emsarena_rehearsal_ab12cd34ef56;
ALTER DATABASE emsarena_rehearsal_ab12cd34ef56
    SET emsarena.rehearsal_target = 'disposable';
```

Orkestrator bütün sessiya boyu `core.rls.set_rls_tenant(org.pk, local=False)`
işlədir və `bypass_rls()` **heç vaxt** çağırmır. Attestasiya real baza adını
deyil, yalnız `emsarena_rehearsal_<12hex>` şablon token-ini raportlayır, çünki
hesabat artifakt-ı repoya commit olunur.

## 5. Mərhələli icra planı

### M0 — Baseline, custody və plan

Görüləcək:

- repo/worktree və mühit inventarı;
- `.env` konfiqurasiyasının yalnız mövcudluq/scheme səviyyəsində redaktə edilmiş
  yoxlaması;
- source SHA, ölçü və audit artifact-lərinin təsdiqi;
- dump fayl icazəsinin owner-only edilməsi;
- bu master plan və davamlı status ledger-i.

Çıxış gate-i:

- real data və production dəyişməyib;
- source content hash eynidir;
- bütün növbəti addımlar rollback və test gate-i ilə sənədləşib.

### M1 — İzolə və təkrarlana bilən test mühiti

Görüləcək:

- repo pin-ləri ilə ayrıca Python venv;
- engine-agnostic testlər üçün SQLite;
- disposable Docker PostgreSQL;
- eyni migration head-ləri ilə təmiz DB qurulması;
- məhdud runtime/importer rolunun `NOSUPERUSER NOBYPASSRLS` attestasiya testi.

Çıxış gate-i:

- `manage.py check`, `makemigrations --check`, module-size və module-boundary yaşıl;
- SQLite testləri yaşıl;
- PostgreSQL schema migrate, RLS və trigger smoke yaşıl;
- heç bir test real `.env` DB-yə yazmayıb.

### M2 — Target P0 hardening

Sıra və cari lokal status:

1. qrup transferində tarixi qoruma — `VERIFIED`;
2. publish/approval invariant-i — `VERIFIED`;
3. chair/dean scope fail-closed davranışı — `VERIFIED`;
4. migration-target registrar FK-ləri üçün cross-tenant DB integrity — core graph
   `VERIFIED`, qalan relation matrix `IN_PROGRESS`;
5. sillabus target lifecycle və journal activation invariant-i — design/business
   acceptance gözləyir.

Hər dəyişiklik ayrıca characterization + negative security test ilə edilir.

Çıxış gate-i:

- köhnə mark/final/component sayı transferdən sonra dəyişmir;
- draft/submitted jurnal heç bir endpoint və service ilə published ola bilmir;
- scope-suz management role org-wide data görmür;
- cross-tenant INSERT və UPDATE PostgreSQL tərəfindən reject edilir;
- journal yalnız approved syllabus versiyasına bağlandıqda aktivləşir.

### M3 — Legacy control plane və preflight

Görüləcək:

- `apps.legacy_import` modelləri, constraints və RLS;
- default dry-run `legacy_import_preflight` command-i;
- source hash/size/schema manifest yoxlaması;
- compiled default-deny field projection, credential denylist və PII-safe logging;
- tenant/source üzrə advisory lock;
- reviewer attribution və append-only reviewed-remap workflow;
- chunk checkpoint və deterministic ordering müqaviləsi.

Çıxış gate-i:

- eyni entity map iki dəfə yaradıla bilmir;
- eyni source+version rerun canonical mapping-i dəyişmədən yeni immutable
  observation verir; fərqli target/hash/state fail-closed conflict-dir;
- ledger/audit yazılmasa batch uğurlu sayılmır;
- password/show_password/PIN allowlist-ə düşə və safe log/export-a çıxa bilmir;
- reviewed remap canonical identity-ni overwrite etmir və version lineage yaradır;
- command explicit apply olmadan domain data yazmır.

Cari lokal sübut: legacy suite SQLite-da `114 pass / 34 engine skip`, PostgreSQL
16-da `146 pass / 2 engine skip` verib. Təmiz full schema ilə
`legacy_import 0005→0004→0005` və `registrar 0041→0040→0041` keçib; ayrıca
`NOSUPERUSER/NOBYPASSRLS` migration-owner rehearsalları RLS-aware backfill və
invalid-row precheck davranışını təsdiqləyib. Bu, domain rehearsal deyil.

### M4 — Staging və canonical mapping

Import sırası:

1. organization və akademik period;
2. org-unit iyerarxiyası, proqram, ixtisas, kurikulum, fənn;
3. user identity və membership (credential-siz);
4. academic record və qrup;
5. syllabus root/version/content/approval history;
6. offering və enrollment;
7. schedule, lesson və canonical journal dates;
8. attendance/marks və düzəliş tarixçəsi;
9. assessment components, final grade və resit history;
10. exam, question, option, attempt və answer;
11. attachment/notification/archive-only domenlər.

Hər adapter üçün:

- source-to-target field map;
- normalizasiya və business-code dictionary;
- orphan/dedupe precedence;
- live/archive/quarantine qərarı;
- batch ölçüsü və checkpoint;
- source/target count və digest;
- rollback/forward-fix qaydası.

Adapter kod olaraq `legacy_import_rehearse` faza registry-sinə **əlavə bir
faza** kimi qoşulur; ayrı komanda yazılmır. Fazalar registry sırasında
(`order` artan) icra olunur, hər biri öz `source_tables` çoxluğunu iddia edir və
iddia edilmiş cədvəl başqa faza tərəfindən götürülə bilmir. Gated cədvəllər
(bütün sillabus dəsti, `students_telegram`, `workers_permits`, `ntg`,
archive/empty sətirlər) validator səviyyəsində iddia edilə bilmədiyi üçün
"yanlışlıqla import" ssenarisi struktur olaraq mümkün deyil. Registry barmaq izi
dəyişdikdə pinlənmiş dəyər yenilənmədən heç bir rehearsal başlamır.

### M5 — Pilot

Əvvəl bir məhdud akademik period + fakültə/kafedra seçilir. Pilotda:

- identity collision-ları;
- qrup/subject/offering əlaqələri;
- 100% tələbə enrollment sayları;
- jurnal tarixləri, bal və davamiyyət cəmləri;
- final nəticə və transcript nümunələri;
- orphan və quarantine qərarları

akademik məsul şəxslə yoxlanır.

### M6 — İki tam rehearsal

Hər rehearsal təmiz PostgreSQL snapshot-a sıfırdan aparılır.

Məcburi müqayisələr:

- source row accounting: migrated + skipped + quarantined = source rows;
- entity və domain count-ları;
- source/entity-map/target digest-ləri;
- duplicate və cross-tenant violation = 0;
- credential import/export/log = 0;
- seçmə tələbə dosyeləri, transkript, bal və davamiyyət;
- batch resume, failure injection, timeout və lock davranışı;
- backup restore və cutover rollback rehearsal-ı;
- performans, WAL/disk və maintenance window ölçüsü.

Rehearsal 1 mapping və performans düzəlişləri üçündür. Rehearsal 2 eyni source SHA və
transform version ilə yekun determinism sübutudur.

Determinizm mexanizmi konkretdir. Hər rehearsal
`docs/migration/reports/LEGACY_REHEARSAL_V1_RUN{1,2}.json` artifakt-ı yazır;
artifakt iki bölmədən ibarətdir və **yalnız** `deterministic` bölməsi
`determinism_digest = sha256(canonical_json(deterministic))` ilə möhürlənir:

| Digest mənbəyi | Cross-run stabil? |
|---|---|
| `plan_fingerprint`, `phase_registry_fingerprint` | bəli |
| `snapshot_sha256` / `snapshot_size_bytes` | bəli |
| `source_attestation` bloku | bəli |
| `target_guard` bloku (`migration_head_digest` daxil) | eyni migration başlığında bəli |
| `target_identity_baseline.digest` (pre-run canonical açarlar) | eyni provisioning-də bəli |
| batch üzrə `source_digest` / `classification_digest` / `target_digest` | bəli |
| `phase_digest`, `determinism_digest` | bəli |

`provenance` bölməsi (run/org UUID-ləri, vaxt möhürləri, `chain_digest` uçları)
qəsdən **digest-dən kənardadır**, çünki `LegacyImportBatch.chain_digest` run və
organization identity-sini zəncirə qatır — o yalnız run-daxili bütövlük sübutudur.
`target_digest` heç vaxt target UUID-i deyil, canonical username‖email açarlarının
hash-idir. 8.5k sətirlik kohort üçün per-row digest brute-force edilə bildiyindən
artifakt-a **per-row digest yazılmır**; onlar RLS ilə qorunan ledger-də qalır.

Gate əmri:

```bash
python manage.py legacy_import_rehearse --mode apply --rehearsal-ordinal 1 …
python manage.py legacy_import_rehearse --mode apply --rehearsal-ordinal 2 \
    --compare-report docs/migration/reports/LEGACY_REHEARSAL_V1_RUN1.json …
```

İkinci icra digest fərqli olarsa `legacy_rehearsal_determinism_mismatch` ilə
fail-closed dayanır; run FAILED kimi bağlanır.

### M7 — Production cutover

Yalnız bütün GO gate-ləri keçdikdən sonra:

1. production backup və restore sübutu;
2. app/worker/beat/importer runtime DB rollarının attestasiya edilməsi;
3. legacy sistemdə elan olunmuş write-freeze;
4. final snapshot və SHA manifest;
5. app writers və Celery maintenance rejimi;
6. schema release owner rolu ilə, data ETL məhdud importer rolu ilə;
7. per-tenant, per-batch import və live reconciliation;
8. RLS, login activation, journal/transcript smoke;
9. GO imzasından sonra yeni sistemi açmaq;
10. legacy sistemi read-only saxlamaq.

Failure açılışdan əvvəl baş verərsə target pre-cutover backup-a bərpa olunur və
legacy write-freeze geri götürülür. Yeni sistem real write qəbul etdikdən sonra
destructive batch delete edilmir; forward-fix və ya idarə olunan switchback qərarı
verilir.

### M8 — Keçiddən sonrakı nəzarət

- İlk 24–48 saat 5xx, RLS deny, audit, queue və reconciliation monitorinqi;
- credential activation ayrıca dalğa;
- istifadəçi uyğunsuzluqlarının rule-code ilə issue queue-da idarəsi;
- legacy read-only arxiv retention qərarı;
- yekun qəbul və bağlanış hesabatı.

## 6. Test matrisi

| Yoxlama | SQLite | PostgreSQL | Production GO üçün |
|---|:---:|:---:|:---:|
| Parser və field transform | Bəli | Bəli | Məcburi |
| Business-code mapping | Bəli | Bəli | Məcburi |
| Idempotency model logic | Bəli | Bəli | Məcburi |
| Management command dry-run | Bəli | Bəli | Məcburi |
| FK/unique/check real semantikası | Qismən | Bəli | PostgreSQL nəticəsi |
| RLS deny/tenant visibility | Xeyr | Bəli | Məcburi |
| Cross-tenant INSERT/UPDATE reject | Xeyr | Bəli | Məcburi |
| Append-only/immutability trigger | Xeyr | Bəli | Məcburi |
| Advisory lock/concurrency | Xeyr | Bəli | Məcburi |
| Batch resume və performance | Xeyr | Bəli | Məcburi |
| Backup/restore rehearsal | Xeyr | Bəli | Məcburi |
| Rehearsal orkestratoru (attestasiya→faza→reconciliation) | Bəli | Bəli | PostgreSQL nəticəsi |
| İki təmiz hədəfdə determinizm digest bərabərliyi | Xeyr | Bəli | Məcburi |

## 7. Production GO/NO-GO gate-ləri

Production yalnız aşağıdakıların hamısında GO olduqda açılır:

- **Source custody:** final SHA/size eynidir, owner-only və encrypted storage var.
- **Runtime role:** bütün runtime-larda `rolsuper=false`, `rolbypassrls=false`;
  enforcement fail-closed-dur.
- **Tenant integrity:** cross-FK negative matrix yaşıl, violation sayı 0-dır.
- **Identity:** legacy credential daşınmayıb, mövcud parol overwrite sayı 0-dır.
- **Determinism:** iki full rehearsal count və digest-lərdə eyni nəticə verib.
  Maşınla yoxlanan forma: `LEGACY_REHEARSAL_V1_RUN1.json` və
  `LEGACY_REHEARSAL_V1_RUN2.json` fayllarının `determinism_digest` sahələri
  bayt-bayt eynidir və hər iki fayl saxlanmış digest-i öz `deterministic`
  məzmunundan yenidən sübut edir (tamper aşkarlanır). İkinci icra
  `--compare-report` ilə aparılır; fərq halında komanda `exit 1` və
  `legacy_rehearsal_determinism_mismatch` verir. Bu gate insan gözü ilə deyil,
  komanda çıxış kodu ilə qiymətləndirilir.
- **Completeness:** bütün sətirlər izahlı son status alıb, səbəbsiz exception 0-dır.
- **History:** transfer/delete/cascade regression-ları tarixi və provenance-i qoruyur.
- **Recovery:** backup scratch DB-yə uğurla restore edilib.
- **Cutover:** write-freeze, owner/importer ayrılığı və iki nəfərlik GO qeydə alınıb.

Bir məcburi PostgreSQL isolation testi belə fail olarsa qərar `STOP`-dur.

## 8. Hesabat və iz buraxma qaydası

Hər mərhələ aşağıdakı materialları yeniləyir:

- `STATUS.md`: görülən iş, növbəti iş, blocker və test nəticələri;
- phase-specific mapping/decision sənədi;
- machine-readable count/digest/reconciliation artifact-i;
- təhlükəsizlik və data-quality finding-ləri;
- command, timestamp, commit və transform version;
- heç bir secret və raw PII olmayan paylaşım xülasəsi.

Status terminləri:

- `PLANNED`: hələ başlanmayıb;
- `IN_PROGRESS`: məhdud və aktiv iş;
- `BLOCKED`: konkret xarici şərt yoxdur;
- `VERIFIED`: məcburi testlər keçib;
- `READY_FOR_REHEARSAL`: lokal gate-lər tamamdır;
- `READY_FOR_CUTOVER`: iki full rehearsal və bütün production gate-ləri tamamdır.

## 9. Dizayn və kodlaşdırma ardıcıllığı

Tam UI design-to-code işi legacy data-dan əvvəl məcburi deyil. Doğru asılılıq:

1. business invariant və target data model;
2. migration ledger və adapter müqaviləsi;
3. Syllabus -> approval -> Journal vertical slice-ının yekun dizaynı və acceptance-i;
4. yalnız acceptance-dan sonra həmin vertical slice-ın kodu;
5. pilot/rehearsal nəticəsinə görə reconciliation ekranları;
6. qalan Claude Design ekranlarının design-to-code implementasiyası.

Beləliklə data modeli real serverdən əvvəl lokal disposable PostgreSQL-də yoxlanır,
amma yalnız SQLite-a güvənilmir. Dizayn inkişaf etdikcə UI dəyişə bilər; provenance,
tenant, approval və immutable history invariant-ləri dəyişməməlidir.
Hazırda dizaynda görünməyən state və ekranlar xəta deyil, implementasiyadan əvvəl
tamamlanacaq design backlog-dur.

## 10. Uğur tərifi

Layihə yalnız data "import olundu"qda yox, aşağıdakılar eyni anda doğru olduqda
uğurlu sayılır:

- akademik tarix itmir və səssiz overwrite edilmir;
- hər target qeydinin mənbə izi var;
- tenant sərhədi DB və tətbiq qatında qorunur;
- legacy credential heç yerdə aktivləşmir və yayılmır;
- rerun duplicate yaratmır;
- problemli data silinmir, izahlı quarantine/reconciliation alır;
- production cutover bir dəfəlik, ölçülmüş və geri dönüş ssenarili olur;
- EMSArena-nın mövcud məhsul mahiyyəti qorunur.
