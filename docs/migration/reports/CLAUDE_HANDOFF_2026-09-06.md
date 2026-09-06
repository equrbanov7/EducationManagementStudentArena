# Claude üçün son handoff — EMSArena legacy miqrasiyası

**Qısa hökm:** Lokal texniki repetisiya PASS, production cutover hələ NO-GO.
Production-a toxunulmayıb.

## Artıq yoxlanıb

- Eyni 2 142 912 818 baytlıq MyEdu snapshot-u iki ayrı, sıfırdan disposable
  PostgreSQL DB-yə 24/24 faza ilə uğurla köçürülüb.
- Hər iki run-ın deterministik digest-i eynidir:
  `1bf5d78e7a41f0c3d3dfbfe0def22cf6c4bc522881f1b54de75d72af11109379`.
- 5 911 322 jurnal xanası üçün xana-bəxana replay edilib: 4 587 875 target
  sətir, 1 323 447 izahlı fərq, 0 izah olunmamış fərq.
- 171 080 legacy nəticə faktı mənbə/hədəf sətir səviyyəsində tam tutub:
  missing/extra/payload/source-hash/guard fərqlərinin hamısı 0.
- Giriş 29 738; Çıxış/imtahan 158 210; Yekun 17 194; Təkrar 5 728 fakt
  dəyəri ayrıca qorunub.
- 52 386 bal-vərəqi artifact-i və 979 137 679 açılmamış payload baytı
  ayrıca decompress/hash olunub; bütün fərqlər 0.
- 1 594 legacy-import SQLite testi keçib; 68 PG/xarici inteqrasiya testi həmin
  mühərrikdə məqsədli skip olub. Ayrı real-PG dəstində 62 keçib, 1 məqsədli
  skip var. UI nəticə/warning dəstində 41 keçib.
- `manage.py check`, `makemigrations --check`, module-size, module-dependency,
  Black, isort və flake8 keçib.
- “Nəticələrim” paneli bağlı olanda da qırmızı “İmtahan Mərkəzi ilə
  dəqiqləşdirilsin” qeydi görünür; panel açıldıqda Giriş/Çıxış/Yekun/Təkrar
  hər biri ayrıca warning daşıyır. Desktop və 390×844 Chromium renderi yoxlanıb.

## Tapılıb və düzəldilib

1. J12 evidence digest-də disposable Lesson UUID-si stabil
   `calendar:{ay}:{gün}:{saat}` locator-u ilə əvəz edilib.
2. Reconciliation `CellElection` Django-dan ayrılıb saf ortaq modula çıxarılıb.
3. Auditorun J12 sparse payload-a görə verdiyi 1 849 digest və 87 map
   false-positive-i düzəldilib; real 171 080 sətir guard scan indi 0-dır.
4. Bağlı UI panelində daimi qırmızı xəbərdarlığın görünməməsi düzəldilib.
5. SQLite repair-guard testi markersiz PostgreSQL branch-ini açıq mock edir;
   tətbiq təhlükəsizlik qapısı dəyişdirilməyib.

## Hələ şübhə / insan qərarı olanlar

- 17 573 fact xam immutable sübut kimi var, amma kanonik enrollment-a
  avtomatik bağlanmır; yanlış şəxsə bal yazmamaq üçün review tələb olunur.
- Tier 1: 48 tapıntı / 47 tələbə (43 şkala + 5 absurd üç-rəqəmli dəyər).
- Tier 2 əsas: 261 tapıntı / 238 tələbə.
- Mənbədə 1 qrupsuz və 16 orphan-qrup tələbə, 2 duplicate-FİN namizədi,
  1 531 orphan-müəllim jurnal istinadı, 58 orphan-student `yekun` istinadı var.
- 1 323 447 jurnal xanası izahlı səbəblə target business row deyil. Onların
  xam payload-u bütünlüklə əməliyyat cədvəllərində saxlanmır; source dump-un
  hash-lənmiş read-only retention-u buna görə məcburidir.
- `verified` review legacy mənşə warning-ini silməməlidir.

## Claude nəyi yenidən təsdiqləsin

1. `final-2026-09-06-evidence/SHA256SUMS.txt` üçün `sha256sum -c` işlədilsin.
2. İki `LEGACY_REHEARSAL_RUN*.json` faylının `.deterministic` obyektləri
   `jq -cS` + `cmp` ilə eyni təsdiqlənsin.
3. Hər iki `RECONCILE_RUN*.md` daxilində üç nərdivan, fact və artifact
   invariantlarının 0 fərq verdiyi yoxlansın.
4. J12 writer/auditor digest sahələrinin eyniliyi və `cell_election.py`-nin
   Django-suz qalması code review edilsin.
5. Production-da 0052–0054 və sonrakı migration-lar, FORCE RLS, policy,
   4 guard trigger/cədvəl və runtime rolun NOSUPERUSER/NOBYPASSRLS olması
   yenidən attestasiya edilsin.
6. Backup/restore, source freeze, snapshot hash, rollback həddi və post-cutover
   deep reconciliation olmadan GO verilməsin.

## Əsas fayllar

- `LEGACY_MIGRATION_FINAL_AUDIT_2026-09-06.md` — tam qərar və plan
- `final-2026-09-06-evidence/` — PII-siz maşın sübutları
- `output/pdf/EMSArena_Legacy_Miqrasiya_Yekun_Audit_2026-09-06.pdf` — paylaşım PDF-i

