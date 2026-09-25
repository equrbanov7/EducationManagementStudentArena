# Köhnə sistemdən gəlməyən ballar — kim, niyə, necə bərpa olunur (2026-09-25)

**Kimə:** sahib (Elvin) və serverdə tətbiq edəcək orkestrator
**Vəziyyət:** J12 bərpası üçün alət HAZIRDIR və production-un nüsxəsində tam repetisiya
olunub (plan → dry-run → tətbiq → təkrar icra = 0 → geri qaytarma → yenidən tətbiq).
**Production-a HƏLƏ HEÇ NƏ YAZILMAYIB** — tətbiq §6-dakı runbook ilə serverdə edilir.
**Sübut bazası:** `ems_prodcopy` (production-un ~2026-09-19/20 nüsxəsi, yalnız oxu) +
köhnə MyEdu dump-u (`myedudb.sql`, 2 142 912 818 bayt, sha256 `177ef226…68fe0`) —
lokal, `@@GLOBAL.read_only=1` MariaDB konteynerində, yalnız SELECT icazəli istifadəçi ilə.

---

## 1. Qısa cavab

Production **2026-08-27 repetisiyasından** qurulub (run `fa9516a9`, `rehearsal-identity-v1`,
17 faza). Ondan sonra yazılmış düzəlişlərin **heç biri production-a tətbiq olunmayıb**:
`audit_auditlog`-da bir dənə də `legacy_repair:*` sətri yoxdur, `is_legacy_synthesised`
dərsi 0-dır, 2 490 legacy tələbə hələ də `archived`-dir.

«Bal görünmür» şikayəti bir səbəbdən yox, **doqquz ayrı səbəbdən** gəlir. Onlardan:

* **biri tam avtomatik bərpa olunur** (J12, dərs slotu olmayan xanalar) — alət bu işdə quruldu;
* **biri mövcud alətlə açılır** (səhv arxivlənmiş hesablar — tələbə ümumiyyətlə GİRƏ bilmir),
  alətin production-da işləməsinə mane olan RLS qüsuru bu işdə düzəldildi;
* **dördü sahibin qərarını gözləyir** (fake jurnallar, qrup uyğunsuzluğu, hesabı olmayan
  tələbələr, xarici dil komponentləri);
* **üçü mənbənin öz boşluğudur** (silinmiş qrup, jurnal siyahısında olmayan tələbə,
  jurnal/semestri olmayan imtahan cəhdi) — deterministik bərpası yoxdur, sübut saxlanılıb.

## 2. Tapıntılar — kateqoriyalar

«Tələbə» — fərqli köhnə tələbə id-si; «fənn sətri» — (jurnal, tələbə) cütü; xana sayları
mənbədəndir (`journals_dates_points` + arxiv, J-V7 kəsimi ilə).

| # | Kateqoriya | Tələbə | Görünməyən | Kök səbəb | Nə edilir |
|---|---|---:|---|---|---|
| 1 | **Dərs cədvəli sətri yoxdur** (K10/K10b) — qeydiyyat VAR, həmin günün dərsi yoxdur | **1 974** (305 aktiv · 1 669 arxivdə) | 7 991 qeydiyyatda **161 775 xana**: 12 208 bal · 18 794 qayıb · 12 üzrlü · 130 761 iştirak; +1 817 sübut faktı | J12 fazası 08-27 run-unda yox idi | ✅ **BƏRPA** — `legacy_repair_lesson_recovery` (§4) |
| 2 | **Səhv arxiv** (P0-1) — tələbə sistemə girə bilmir | **2 291** (199-u həqiqətən buraxılıb, toxunulmur) | bütün öz balları (data yerindədir, giriş bağlıdır) | qəbul ili tapılmayan (`groups.start_year='0000'`) tələbə arxivə salınıb | ⚠️ mövcud `legacy_repair_archive_status` — RLS qüsuru düzəldildi; **əhatə sahibin qərarıdır** (§7) |
| 3 | **Fake jurnallar** (`fake=1`, J-V6) — fənn tamamilə yoxdur | **2 648** | 8 219 fənn sətri · **6 523 imtahan** · 29 678 komponent · 9 131 gündəlik bal · **1 059 rəsmi `yekun` nəticəsi** (699 tələbə); 679 tələbə-semestr TAMAMİLƏ görünmür | J1 `fake=1` jurnalı atır (`rehearsal_journal_offerings_phase.py:207`) | ⏳ sahibin qərarı (DATA_VERIFICATION §4.2 — açıq) |
| 4 | **Qrup uyğunsuzluğu** (K9) — çoxqruplu jurnalda tələbənin qrupu yoxdur | **1 402** | 3 449 fənn sətri · 1 389 imtahan · 9 621 komponent · 344 `yekun` (120 tələbə) | `JournalSlices.resolve_student` → `GROUP_MISMATCH` (`rehearsal_journal_slices.py:173`) | ⏳ sahibin qərarı (dilim qaydası) |
| 5 | **Hesabı yoxdur** (K4 · P0-2) | **171** köhnə id (94-ü mənbədə var: 84 skipped + 10 quarantined; 77-si mənbədə silinib) | 2 782 fənn sətri · 1 788 imtahan · 576 `yekun` (118 tələbə) | e-poçt kimlik açarı kimi işlədilib (`account_cutover.py:185/380`) | ⏳ hesab + tarixçə zənciri (§7) |
| 6 | **Silinmiş qrupun jurnalı** (176 karantin dilim) | 256 | 1 706 fənn sətri · 913 imtahan | jurnalın qrupu mənbənin `groups`-unda YOXDUR | ❌ deterministik deyil |
| 7 | **Jurnal siyahısında olmayan tələbə** (`students_id`-də yox, xanası var) | 2 686 | əsasən davamiyyət: 46 567 qayıb · 28 468 iştirak · 939 bal · 10 imtahan | J4 «qeydiyyat həll olunmur» (`rehearsal_journal_marks_phase.py:307`) | ❌ qəsdən — köhnə sistemin öz siyahısı |
| 8 | **İmtahan cəhdi jurnala bağlanmır** (`imthngrscxsblr`, K13) | 2 031 | 6 513 giriş/çıxış cəhdi | mənbə cədvəlində jurnal/semestr sütunu yoxdur | ❌ deterministik deyil (fakt sübutda saxlanılıb) |
| 9 | **Xarici dil komponentləri** (K6: `pa`/`wr`/`ss`/`ww`/`ll`/`rr`/`ga`) | 712 | 3 535 xana | hədəf modelində belə komponent növü yoxdur | ⏳ məhsul/model qərarı |

Kiçik qalıqlar: jurnal siyahısı pozuq 11 · tələbə aktiv deyil 5 · mənbədə olmayan jurnal 64 sətir.

**Cəmi:** 4 747 tələbənin ən azı bir fənn sətri hədəfə düşməyib; 3 635 tələbənin ən azı bir
fənni **tamamilə** yoxdur (kateqoriya 3–6), onlardan 2 709-unun imtahan balı itib (10 613 xana).

> Anonim nümunələr (tam siyahı adlarla yalnız lokal `backups/restore_2026_09_25/`-dədir, repoya düşmür):
> * **Tələbə A** (hazırda aktiv), 2021/2022 Yaz, bir fənn: köhnə sistemdə 21 seminar balı və 2 qayıb
>   yazılıb, həmin günlərin dərs sətri yoxdur → EMS Arena-da 0 görünürdü. Bərpadan sonra 21 bal
>   görünür; **giriş balı 31 dəyişmir** (köhnə `girish` arxiv komponentindən gəlir).
> * **Tələbə B**, 2025/2026 Payız: **8 fənni** yalnız `fake=1` jurnallardadır (7-sində imtahan balı
>   var) və kabinetdə YOXDUR; həmin semestrdən yalnız 3 fənni görünür. DATA_VERIFICATION §3.2-dəki
>   nümunə də eyni sinifdir (3 fənn: k1–k3, sərbəst iş və imtahan balları ilə). Bütün fənləri
>   yalnız fake jurnalda olan (semestri TAMAMİLƏ boş görünən) tələbə-semestr sayı: **679**.

### 2.1 J12 bərpası dövrlər üzrə

| Dövr | Bərpa dərsi | Xana | Bal | Qayıb | Qeydiyyat |
|---|---:|---:|---:|---:|---:|
| 2021/2022 Payız | 257 | 3 265 | 44 | 33 | 137 |
| **2021/2022 Yaz** | **11 331** | **158 264** | **12 137** | **18 745** | **7 654** |
| 2022/2023 Payız | 3 | 39 | 10 | 2 | 39 |
| 2022/2023 Yaz | 12 | 171 | 3 | 12 | 125 |
| 2024/2025 Payız | 2 | 14 | 0 | 0 | 14 |
| 2025/2026 Payız | 1 | 3 | 0 | 0 | 3 |
| 2025/2026 Yaz | 1 | 19 | 14 | 2 | 19 |
| **Cəmi** | **11 607** | **161 775** | **12 208** | **18 794** | **7 991** |

Səbəb mənbədədir: 2021/2022 Yaz-ın 925 real jurnalından **498-nin dərs cədvəli
(`journals_dates_added_by_teacher`) ümumiyyətlə boşdur**, bal cədvəli isə doludur.
2026/2027 datasına **toxunulmur** (§5 yoxlaması).

## 3. Kök səbəblər (kod istinadları)

1. **J12 production-da heç vaxt işləməyib.** J4 xananı yalnız MÖVCUD dərsə bağlayır
   (`rehearsal_journal_marks_phase.py:310-313` → `lesson` pilləsi); J12
   (`rehearsal_lesson_recovery_phase.py`) 08-30/31-də yazılıb, production isə 08-27 run-undandır.
   HANDOFF §8.5 P1-1 «təmir əmri yazılmadı, tam repetisiya lazımdır» deyirdi; cutover A namizədi
   (J12 daxil) hazırlanmışdı, amma serverə **B yolu** (08-27 bazası, təmirsiz) getdi.
2. **Mövcud təmir əmrləri production-da KORDUR (yeni tapıntı).** Production rolu
   `NOSUPERUSER NOBYPASSRLS`-dir, registrar/ledger cədvəlləri `FORCE ROW LEVEL SECURITY`
   daşıyır, `manage.py`-da isə tenant konteksti yoxdur. Ölçüldü: production-a bənzər rol ilə
   kontekstsiz `registrar_lesson`/`registrar_enrollment`/ledger = **0 sətir**, profil cədvəli
   (RLS-siz) isə 2 490 arxiv göstərir → `legacy_repair_archive_status` **2 490-ın hamısını
   `keep_archived` sayır, heç kimi bərpa etmirdi**. Düzəliş: `repair_support.build_context`
   indi tenant + aktor RLS kontekstini qurur (bypass YOX); eyni rol ilə nəticə 2 291 bərpa.
3. **Paralel sorğu Docker `/dev/shm`-ə sığmır (yeni tapıntı).** Postgres konteynerlərinin
   `/dev/shm`-i 64 MB-dır (compose-da `shm_size` yoxdur); J12-nin `recompute_absence_hours`
   sorğusu ilk icrada «could not resize shared memory segment … No space left on device» ilə
   yıxıldı. Təmir tranzaksiyaları indi paralel sorğunu lokal söndürür (production-da da eyni risk var).
4. **Fake jurnallar** — J-V6 qaydası (`fake=1` və ya `sonra_sil=1` → SKIPPED
   `legacy_journal_discarded_source`). Bu jurnalların 1 059 sətri köhnə sistemin RƏSMİ `yekun`
   nəticəsidir, yəni köhnə sistem onları real sayıb. Qərar DATA_VERIFICATION §4.2-də açıq qalıb.
5. **K9** — çoxqruplu jurnalda seçim tələbənin BUGÜNKÜ qrupu ilə edilir, köhnə qrup tarixçəsi
   mənbədə yoxdur. `yekun.group_id` yalnız 76 cütdə (43 tələbə) jurnalın qruplarından birini
   göstərir; 3 105 cütdə `yekun` sətri ümumiyyətlə yoxdur.
6. **P0-1 arxiv** — `rehearsal_sar_phase._decide` (08-27 kodu) qəbul ili tapılmayanı arxivə
   salırdı; faza sonradan düzəldilib, production datası köhnədir. 2 291-in hamısında mənbədə
   `azadedildi=0`, amma yalnız **184**-ünün 2025/2026 yazılışı var (son il: 2022/2023 — 825,
   2023/2024 — 561, 2024/2025 — 563) — çoxu, ehtimal ki, köhnə sistemin işarələmədiyi məzundur.

## 4. Qurulan alət: `legacy_repair_lesson_recovery`

**Dizayn — ağır iş lokalda, serverə yalnız yığcam plan gedir.** Serverdə köhnə mənbə yoxdur;
production settings `LEGACY_MARIADB_SOURCE_LOCAL_DISPOSABLE=False` saxlayır, yəni orada mənbə
yalnız TLS-sertifikatlı MariaDB ilə mümkün olardı (P0-2 də belə nəzərdə tutulmuşdu —
HANDOFF §8.6 addım 2 — və heç vaxt qurulmadı). Ona görə:

1. **Plan (lokal)** — `--build-plan`: production nüsxəsinin ATILABİLƏN klonunda (marker
   MƏCBURİ, `--i-know-this-is-production` bu rejimdə QƏBUL EDİLMİR) J12-nin **öz kodu
   dəyişmədən** işləyir. Yeganə fərq: J4-ün həll indeksləri hədəfi quran orijinal import
   run-una bağlanır (`_resolution` hook-u, `rehearsal_lesson_recovery_phase.py`); möhürlər yeni
   «plan run»-una (`legacy-repair-j12-v1`) yazılır. Klonda YENİ yaranan sətirlər deterministik
   `.jsonl.gz` plan faylına çıxarılır (0600, sha256 manifesti ilə).
2. **Tətbiq (server)** — `--plan … --plan-sha256 …`: sha256 yoxlanılır; başlıq CANLI bazada
   eyni təşkilat + eyni import run-u tələb edir; hər sətir canlı dataya qarşı yenidən təsnif
   olunur: açılış ledger-də MIGRATED və dövrü 2026-09-01-dən əvvəl bitməlidir; eyni slotda
   canlı dərs varsa yeni dərs yaradılmır (`reuse_existing`); mövcud xana **heç vaxt** üstündən
   yazılmır (`live_conflict`); müəllimin `grade.input`-lu aktiv üzvlüyü yoxdursa sahə boş qalır.

Qapılar repair konvensiyasının eynisidir: dry-run DEFAULT, `--apply`, markersiz bazada
`--i-know-this-is-production`, `--organization`, `--limit`, `--actor`; qərar cədvəli həmişə
çap olunur; heç nə silinmir; ikinci icra 0 dəyişiklik (audit izi də yoxdur).
**Audit:** hər bərpa dərsi (xana siyahısı ilə), dəyişən hər `absence_hours` (köhnə/yeni dəyər)
və hər sübut faktı üçün `core.audit.log_action` (`legacy_repair:lesson_recovery`), sonda plan
sha256-lı xülasə sətri. **Sübut:** uduzan dəyərlər `LegacyGradeFact`-a (append-only, İmtahan
Mərkəzi baxışı məcburi), dərslər `is_legacy_synthesised=True`. Production ledger-inə yeni run
yazılmır (digər təmir əmrləri kimi) — ledger sübutu plan run-unda və plan faylındadır.

## 5. Repetisiya nəticələri

**Plan qurulması** (klon `ems_restore_a7d1`, marker ilə): 24,5 dəq; slot 11 607 → dərs 11 607,
xana 161 775, `absence_hours` dəyişən 5 400, toqquşma sübutu 1 730 (1 445 təqvim + 285
komponent) + həll olunmayan 87 = 1 817 fakt. Rəqəmlər BAL_PROBLEMLERI §2.1-də ölçülmüş J12
nəticəsi ilə **eynidir** (+11 607 dərs, +161 775 xana). Plan: 4,8 MB,
sha256 **`ab777837e4f517e401d16ada68b362edb625b289df30b6641c598ba8af701538`**.

**Production kimi tətbiq** (ayrı klon `ems_restore_a7d1p`, **markersiz**, production-un öz
`provision-app-db-role.sh` SQL-i ilə qurulmuş `NOSUPERUSER NOBYPASSRLS` rol, `--i-know-this-is-production`):

| Addım | Nəticə |
|---|---|
| `--apply` bayraqsız / səhv sha256 | rədd: `legacy_repair_target_not_disposable` / `legacy_repair_plan_sha256_mismatch` |
| dry-run | `lesson:create 11607 · mark:create 161775 · fact:create 1817` · 7 991 qeydiyyat · müəllim düşümü 0 |
| **apply** (51 san) | FAKTİKİ: dərs **11 607** · xana **161 775** · fakt **1 817** · `absence_hours` **5 400** |
| ikinci apply | hamısı `already_present`, FAKTİKİ **0**, audit izi yoxdur |
| J12-nin öz nəticəsi ilə müqayisə | dərs/xana/fakt/bütün 151 271 qeydiyyatın `absence_hours`-u — checksum **bayt-bəbayt eyni** |
| 2026/2027 | toxunulmayıb (bərpa dərsi kəsimdən sonra 0; 2026/2027 xana sayı 9 → 9) |
| audit | 11 607 dərs + 5 400 qeydiyyat + 1 817 fakt + 1 xülasə sətri |
| geri qaytarma (§6.3) → yenidən apply | prod nüsxəsi ilə checksum eyni → yenidən apply yenə bayt-bəbayt eyni |

**Nəticəyə təsir** (plana düşən 7 991 qeydiyyatın hamısı, `finals.compute_final_result`):
yalnız `absence_hours` (5 400) və göstərilən davamiyyət balı (6 411) dəyişir; **giriş balı,
yekun, hərf, keçib/kəsilib və status: 0 dəyişiklik** — köhnə sistemin hesabladığı nəticə olduğu
kimi qalır, ÜOMG dəyişmir. 7 202 qeydiyyat (90 %) köhnə sistemdə nəticəsizdir
(`legacy_no_result`, əsasən 2021/2022 Yaz) — J12 onların gündəlik jurnalını tamamlayır.

**Tələbə görünüşü** (test klienti, `force_login`, bərpa alan 12 aktiv tələbə, tətbiqdən əvvəl
və sonra): «Fənlərim» / «Nəticələrim» / «Ümumi tədris məlumatı» — 72 render-in hamısı **200**,
xəta yoxdur; ÜOMG 11 tələbədə hesablanır (1-də qəti nəticəli fənn yoxdur → «hesablana bilmir»,
dizayn üzrə). Yekun vəziyyətdə (J12 + P0-1, geri qaytarma → yenidən tətbiqdən sonra) daha 12
tələbə yoxlandı — 8-i P0-1 ilə yenidən aktivləşən, hər biri +23…+26 bərpa balı ilə: 36 render-in
hamısı **200**, ÜOMG 10 tələbədə hesablanır (2-də qəti nəticə yoxdur); nəticəsiz legacy fənni saxta hərf yox, «Köhnə sistemdə bal var, nəticə keçməyib»
+ «İmtahan Mərkəzi ilə dəqiqləşdirilsin» göstərir. ÜOMG/transkript render-ində legacy data üçün
qüsur tapılmadı. Qeyd: köçürülmüş hesablar ilk girişdə `/accounts/set-password/`-ə yönləndirilir
(`password_change_required`) — klon testində seçilən tələbələr üçün bu bayraq əvvəlcədən söndürüldü.

**P0-1 (arxiv) — production yolu ilə** (eyni klon, eyni rol): dry-run 2 291 bərpa / 199 toxunulmur
(`--require-activity` ilə 2 219 / 271); apply 15 san, 2 291 bərpa, 0 uğursuz; ikinci icra 0.
Hər iki bərpadan sonra J12 xanası alan 1 974 tələbədən **1 948-i** giriş edib görə bilir
(1 626-sı bərpa olunmuş balla); arxivdə qalan 26 nəfər həqiqətən buraxılıb.

## 6. Production runbook

> Hər addımdan əvvəl dry-run rəqəmlərini bu cədvəllə tutuşdurun; fərq varsa **dayanın**.
> APP_DIR `/home/wcu/EducationManagementStudentArena`, konteyner `educationmanagementstudentarena-app-1`,
> təşkilat `qku`, aktor `superadmin` (grade-fact trigger-i superuser/owner aktor tələb edir).

### 6.1 Hazırlıq

1. **Kod deploy** (miqrasiya YOXDUR): yeni əmr `legacy_repair_lesson_recovery`, `repair_support`
   RLS + paralel-sorğu düzəlişi. Yoxlama:
   `docker exec educationmanagementstudentarena-app-1 python manage.py help legacy_repair_lesson_recovery | head -3`
2. **Plan faylı** — hazırdır: `backups/restore_2026_09_25/j12_plan_a7d1.jsonl.gz` (+ `.manifest.json`,
   `.sha256`), sha256 yuxarıdadır. Serverə şəxsi kanalla (AnyDesk fayl ötürmə / scp) köçürün,
   `sha256sum -c j12_plan_a7d1.jsonl.gz.sha256`. İstəsəniz təzə production dump-undan yenidən
   qurun: `scripts/ops/restore_legacy_scores_build_plan.sh <prod dump> <qovluq> superadmin`
   (yeni sha256 alınır; tətbiq addımı eyni qalır). Plan 2026-09-19/20 nüsxəsindən qurulub, amma
   tətbiq hər sətri canlı bazaya qarşı yenidən yoxlayır.

### 6.2 J12 bərpası

```bash
cd /home/wcu/EducationManagementStudentArena
PLAN=/home/wcu/restore/j12_plan_a7d1.jsonl.gz
SHA=ab777837e4f517e401d16ada68b362edb625b289df30b6641c598ba8af701538

scripts/ops/restore_legacy_scores_server.sh check   "$PLAN" "$SHA" superadmin
scripts/ops/restore_legacy_scores_server.sh dry-run "$PLAN" "$SHA" superadmin
#   gözlənilən: lesson:create 11607 · mark:create 161775 · fact:create 1817
#               yeni xana: present(bal) 12208 · absent 18794 · excused 12 · present 130761
#               yeni xana alan qeydiyyat 7991 · reuse/live_conflict/skip YOXDUR
scripts/ops/restore_legacy_scores_server.sh apply   "$PLAN" "$SHA" superadmin
#   əvvəl `docker exec emsarena-postgres-backup /backup.sh`, sonra apply (~1 dəq):
#   FAKTİKİ dərs 11607 · xana 161775 · fakt 1817 · absence_hours 5400
#   sonra İKİNCİ icra: hamısı already_present, FAKTİKİ 0
```

Skriptsiz ekvivalent: `docker cp` + `docker exec -u 0 … chown appuser:appgroup` (konteyner
`appuser` kimi işləyir, plan 0600-dür), sonra
`docker exec -i educationmanagementstudentarena-app-1 python manage.py legacy_repair_lesson_recovery --organization qku --actor superadmin --plan /tmp/j12_plan_a7d1.jsonl.gz --plan-sha256 $SHA [--apply --i-know-this-is-production]`.
Mərhələli tətbiq üçün `--limit N` (ilk N vahid) işləyir; tam icra sonra qalanı əlavə edir.

**Yoxlama (serverdə, oxu):**
```sql
select count(*) from registrar_lesson where is_legacy_synthesised;        -- 11607
select count(*) from registrar_legacygradefact where transform_version like 'legacy-repair-j12-v1.%';  -- 1817
```
Tələbə görünüşü üçün `scripts/ops/restore_legacy_scores_verify.py` YALNIZ klonda işlədilir
(giriş sessiyası yazır); serverdə staff «view-as» ilə 2-3 tələbəyə baxmaq kifayətdir.

### 6.3 Geri qaytarma

Tətbiq yalnız ƏLAVƏ edir, ona görə hədəfli geri qaytarma mümkündür və repetisiyada sınanıb
(nəticə prod nüsxəsi ilə checksum eyni):
```bash
docker exec -i <postgres konteyneri> psql -U <owner> -d emsarena_db \
  -v plan_sha=$SHA -v drop_facts=1 -f - < scripts/ops/restore_legacy_scores_rollback.psql
```
Skript audit izindən işləyir: `absence_hours`-u audit-dəki ən erkən köhnə dəyərə qaytarır, bu
planın dərslərini və onların xanalarını silir, `drop_facts=1` ilə (yalnız superuser) sübut
faktlarını da. Bərpa dərsinə sonradan düzəliş bağlanıbsa FK silməni dayandırır (sənədli düzəliş
səssizcə silinmir). Son çarə — addım 6.2-dəki `backup.sh` nüsxəsinin bərpası (sonrakı canlı
yazılar itər).

### 6.4 P0-1 (arxiv) — yalnız sahib qərar verəndən sonra

```bash
docker exec -i educationmanagementstudentarena-app-1 python manage.py legacy_repair_archive_status \
    --organization qku --actor superadmin [--require-activity]          # dry-run: 2291 (və ya 2219)
docker exec -i educationmanagementstudentarena-app-1 python manage.py legacy_repair_archive_status \
    --organization qku --actor superadmin [--require-activity] --apply --i-know-this-is-production
```
⚠️ Bu əmr yalnız bu dəyişiklik deploy olunandan SONRA işləyir (RLS düzəlişi); köhnə kodda dry-run
«bərpa 0» göstərir — bu, «iş yoxdur» demək DEYİL.

## 7. Açıq qərarlar (sahib)

1. **P0-1 əhatəsi.** Hamısı (2 291), yazılışı olanlar (`--require-activity`, 2 219), yoxsa yalnız
   yaxın dövrdə oxuyanlar (2025/2026 yazılışı olan 184 — bu süzgəc əmrdə YOXDUR, lazım olsa əlavə
   edilməlidir)? Bərpa olunmayan arxiv tələbəsi J12-nin qaytardığı balları görə bilməyəcək.
2. **Fake jurnallar (§2 #3).** 1 059 rəsmi nəticə + 6 523 imtahan balı. Qərar «köçsün» olarsa iş
   iki qatdır: J-V6 qaydası fazada dəyişir və ayrıca təmir alətı yazılır (açılış + yazılış +
   xanalar; J12 kimi plan/tətbiq dizaynı ilə). J1/J2/J4–J6 fazaları hədəfdə təkrar işlədilə
   bilmir (ledger kimlik konflikti), ona görə bu, ayrıca iş paketidir.
3. **K9 dilim qaydası.** Seçim: (a) `yekun.group_id` sübutu olan 76 cütü bərpa et, qalanı saxla;
   (b) tələbəni jurnalın ilk diliminə «qonaq» (`source_group`) kimi yaz; (c) toxunma.
4. **Hesabı olmayan 94 tələbə (P0-2).** `legacy_repair_missing_accounts` mənbə tələb edir (serverdə
   yoxdur) və `myedu.student.N` adı yaradır (sahib qaydası: «myedu» görünməsin). Tövsiyə: hesab +
   tarixçə üçün J12 kimi plan/tətbiq aləti; tarixçə (yazılış, xana, yekun) yenə J2–J6 məntiqi tələb edir.
5. **Xarici dil komponentləri (K6)** — model qərarı (yeni komponent növləri və ya «digər» sütunu).

## 8. Fayllar

| Fayl | Nədir |
|---|---|
| `apps/legacy_import/management/commands/legacy_repair_lesson_recovery.py` | əmr (plan / tətbiq) |
| `apps/legacy_import/services/repair_lesson_recovery.py` | plan qatı (J12 klonda + delta) |
| `apps/legacy_import/services/repair_lesson_recovery_apply.py` | tətbiq qatı (canlı yoxlama + yazı + audit) |
| `apps/legacy_import/services/repair_plan_file.py` | plan faylı formatı (sha256, manifest) |
| `apps/legacy_import/services/repair_support.py` | + RLS konteksti, `scoped_atomic`, paralel sorğu |
| `apps/legacy_import/services/rehearsal_lesson_recovery_phase.py` | + `_resolution` hook-u (davranış eyni) |
| `apps/legacy_import/tests/test_repair_lesson_recovery.py` | 17 test (PostgreSQL) |
| `scripts/ops/restore_legacy_scores_build_plan.sh` · `…_server.sh` · `…_rollback.psql` | lokal plan · server · geri qaytarma |
| `scripts/ops/restore_legacy_scores_verify.py` · `…_impact.py` | tələbə görünüşü · nəticəyə təsir (klonda) |
| `backups/restore_2026_09_25/` (gitignore) | plan + manifest + adlı tələbə siyahısı (33 990 sətir) |
