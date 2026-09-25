# Köhnə sistemdən gəlməyən ballar — kim, niyə, necə bərpa olunur (2026-09-25)

**Kimə:** sahib (Elvin) və serverdə tətbiq edəcək orkestrator
**Vəziyyət — 2-ci mərhələ (sahibin göstərişi, 2026-09-25):** «Ballar çox vacibdir, yenidən görünməlidir —
əsas diqqət **indi oxuyanlara**». Hazırda oxuyan **3 649** tələbənin hər biri semestr × fənn səviyyəsində
köhnə sistemlə tutuşduruldu; üç bərpa addımı (J12 → atılmış yazılışlar → P0-1) production-un nüsxəsində
**birlikdə və production kimi** repetisiya olundu (markersiz klon, `NOSUPERUSER NOBYPASSRLS` rol,
`--i-know-this-is-production`): ikinci icra = 0, geri qaytarma bayt-bəbayt, 2026/2027-yə toxunulmayıb.
**Production-a HƏLƏ HEÇ NƏ YAZILMAYIB** (J12 workflow-u hazırdır; qalan iki addım §7-dədir).
**Sübut bazası:** `ems_prodcopy` (production-un ~2026-09-19/20 nüsxəsi, yalnız oxu) + köhnə MyEdu dump-u
(`myedudb.sql`, 2 142 912 818 bayt, sha256 `177ef226…68fe0`) — lokal, `@@GLOBAL.read_only=1` MariaDB-də.
1-ci mərhələnin (bütün tələbələr) tapıntıları **Əlavə A**-dadır.

---

## 1. Qısa cavab (hazırda oxuyanlar)

* **Hazırda oxuyan — 3 649 tələbə** (§2; 3 648-nin hesabı var). Köhnə sistemdə onların **70 364
  «semestr × fənn» sətri** var (130-unda heç bir bal/xana yoxdur).
* **Əvvəl** 10 793 sətir görünmürdü və ya natamam idi: **3 053** — tələbə sistemə ümumiyyətlə girə
  bilmir (P0-1, 74 tələbə); **5 410** — fənn kabinetdə YOXDUR; **2 330** — fənn var, xanaların bir
  hissəsi yoxdur. Ən azı bir belə sətri olan tələbə: **2 138** (58,6 %).
* **Üç addımdan sonra:** **5 459 sətir tam görünür** oldu, 372 sətir qismən düzəldi, bloklanan tələbə
  qalmadı (74 → 0). **3 326 fənn yazılışı** qayıtdı — içində **1 924 yekun/imtahan nəticəsi**,
  109 063 gündəlik xana, 14 533 kollokvium/sərbəst iş balı; J12 isə 100 tələbənin 222 fənninə 3 802
  xana qaytarır. Kabinetdə (transkript qurucusu ilə ölçüldü) qəti nəticəli fənn sətri 54 316 → 56 245,
  qazanılmış kredit 232 199 → 240 919; 819 tələbənin ÜOMG-si dəyişir (əsasən ±2,5 bal — bərpa olunan
  nəticələr həm yuxarı, həm aşağı ola bilər, çünki realdır).
* **Qalan 5 334 sətir** (2 702-si tam yox, 2 632-si qismən) — hər birinin səbəbi CSV-dədir, heç biri
  deterministik bərpa olunmur: jurnal siyahısında olmayan tələbənin xanası (qəsdən, 3 199) · eyni fənnin
  başqa yazılışı artıq var — «əkiz» (876; bunların **417-sində imtahan balı yalnız bərpa olunmayan
  jurnaldadır — §8.1, ən vacib açıq qərar**) · nəticəsiz fake jurnal (595) · qrupu silinmiş, qrup
  sübutu olmayan jurnal (344) · xarici dil komponentləri K6 (259) · hesabı olmayan 1 tələbə (35) ·
  mənbədə olmayan jurnal (20) · digər (6).

## 2. «Hazırda oxuyan» — tərif və saylar

Kod: `repair_enrollments_select._current_students` (SQL ilə müstəqil təkrarlandı — fərq yalnız hesabı
olmayan 1 tələbədir). Tələbə **hazırda oxuyandır**, əgər mənbədə `students.azadedildi = 0` VƏ:

| Sübut | Qayda | Tələbə |
|---|---|---:|
| **E1** | EMS Arena-da **2026/2027** dövrünün açılışına artıq yazılıb | **823** |
| **E2 bakalavr** | qrupun qəbul ili 2023–2026 VƏ 2025/2026-da jurnalda (siyahıda və ya xanası) var | **2 603** |
| **E2 magistr** | qəbul ili 2025–2026 VƏ 2025/2026-da jurnalda var | **148** |
| **E3** | qəbul ili mənbədə yoxdur (`groups.start_year='0000'`) VƏ son tam semestrdə (**2025/2026 Yaz**) jurnalda var | **75** (74-ü arxivdə, 1-nin hesabı yoxdur) |
| **Cəmi** | | **3 649** |

Hazırda oxumayan 4 167 tələbəyə toxunulmur: qəbul ili bilinməyən, son semestrdə fəaliyyəti olmayan
2 303 · 2025/2026-da heç bir fəaliyyəti olmayan 772 · 2022 bakalavr kohortu (2026-da bitirib) 718 ·
`azadedildi=1` 200 · 2024 magistr kohortu (2026-da bitirib) 154 · daha köhnə kohort 20.

## 3. Hər tələbə üzrə təhlil (tələbə × semestr × fənn)

**Üsul.** Hər hazırda oxuyanın köhnə sistemdəki hər (jurnal, tələbə) cütü götürüldü (`journals_dates_points`
+ arxiv, J-V7 kəsimi): gündəlik bal / qayıb / iştirak, kollokvium + sərbəst iş (`k1`–`k3`, `si`), imtahan
(`im`, `im2`), rəsmi `yekun` sətri, tanınmayan sütunlar (K6). Cütlər (semestr, fənn) üzrə birləşdirildi və
EMS Arena ilə tutuşduruldu: yazılış varmı, neçə xana / komponent balı / imtahan balı var, kabinet nə
göstərir. «Fənlərim» (kredit qutusu), «Nəticələrim» və «Ümumi tədris məlumatı» (transkript + ÜOMG) EYNİ
çoxluqdan — tələbənin `dropped` olmayan yazılışlarından — qurulur (`transcript.student_record_enrollments`),
ona görə **görünür = giriş açıqdır + yazılış var + xanalar yazılışa bağlanıb**. Nəticə sütunları kabinetin
öz qurucusundan (`transcript.build_student_transcript`) götürüldü. Adlı tam cədvəl (70 364 sətir: mənbə /
əvvəl / sonra / kök səbəb / görülən iş / bərpa olunmama səbəbi) yalnız lokaldadır:
`backups/restore_2026_09_25/current_students_by_subject_2026-09-25.csv` (0600, gitignore).

### 3.1 Kök səbəb üzrə cəm (hazırda oxuyanlar; xanalar mənbədəndir)

| Kök səbəb | Tələbə | Sətir | Görünməyən: bal · qayıb · komponent · imtahan · `yekun` | Bərpa olunan (tələbə · sətir · bal · imtahan · komponent) | Qalan niyə |
|---|---:|---:|---|---|---|
| **P0-1** — səhv arxiv, giriş bağlı | 74 | 3 080 (hamısı) | tələbənin bütün məlumatı | **74 · 3 080** — giriş açılır | — |
| **fake=1** jurnal (J-V6 atıb) | 944 | 2 223 | 2 366 · 6 475 · 8 208 · 1 787 · 16 | **682 · 1 439 · 1 726 · 1 457 · 5 729** | nəticəsiz (imtahan/`yekun` yox) 809 cüt; əkiz 319; siyahıdan kənar 148 |
| **K9** — qrup uyğunsuzluğu | 893 | 1 849 | 3 216 · 10 670 · 6 042 · 689 · 49 | **790 · 1 458 · 3 157 · 519 · 5 490** | əkiz 502 cüt; xanasız siyahı cütü 249 |
| **Qrupu silinmiş jurnal** | 136 | 1 013 | 2 036 · 2 351 · 3 375 · 741 · 0 | **76 · 395 · 825 · 421 · 1 551** | əkiz 453; qrup sübutu yoxdur 392; siyahıdan kənar 72 |
| **J12** — dərs slotu yox | 100 | 222 | 358 · 793 · — · — · — (+2 651 iştirak) | **100 · 222 · 358 · — · —** | — |
| Jurnal siyahısında yox (qəsdən) | 1 279 | 3 267 | 503 · 14 743 · 1 185 · 1 · 0 | — | köhnə sistem də göstərmirdi |
| **K6** — xarici dil komponentləri | 150 | 220 | 466 xana | — | model qərarı |
| Mənbədə olmayan jurnal | 20 | 20 | 5 qayıb | — | jurnal cədvəldə yoxdur |
| Hesabı yoxdur | 1 | 33 | 4 · 131 · 128 · 18 · 3 | — | §5.4 |

### 3.2 Sətir vəziyyəti: əvvəl → sonra

| Əvvəl \ Sonra | görünür | qismən | yoxdur | Cəmi |
|---|---:|---:|---:|---:|
| görünür | 59 441 | — | — | 59 441 |
| qismən | 70 | 2 260 | — | 2 330 |
| yoxdur | 2 687 | 245 | 2 478 | 5 410 |
| bloklu (P0-1) | 2 702 | 127 | 224 | 3 053 |
| **Cəmi** | **64 900** | **2 632** | **2 702** | 70 234 (+130 boş) |

Tam görünən tələbə: **1 511 → 1 953**. Əvvəl problemli sətirlərin semestr bölgüsü: 2025/2026 Yaz 1 510 ·
2025/2026 Payız 1 894 · 2024/2025 Yaz 1 424 · 2024/2025 Payız 1 648 · 2023/2024 Yaz 1 129 · 2023/2024
Payız 1 700 · 2022/2023 — 1 164 · 2021/2022 — 205 · Yay dövrləri 99 · jurnalsız 20.

## 4. Nümunə tələbələr (anonimləşdirilib — T1…T13; legacy id/inisial və tam siyahı yalnız lokal, git-dən kənar `backups/restore_2026_09_25/`-dədir)

Hamısı yekun repetisiya klonunda production rolu ilə, test klienti + `force_login`: «Fənlərim»,
«Nəticələrim», «Ümumi tədris məlumatı» — **36 render-in hamısı 200**, xəta yoxdur; səhifədəki sətir sayı və
ÜOMG kabinet qurucusunun rəqəmi ilə eynidir.

| Tələbə | Sübut | Əvvəl | Görülən iş | Sonra (transkript sətri · ÜOMG · kredit) |
|---|---|---|---|---|
| **T1** | E3 | arxivdə — girə bilmir; 62 sətrin hamısı bloklu; 17 fənni yalnız fake jurnaldadır | P0-1 + 17 fake + 2 K9 yazılışı | 38 → **56** · 54,69 → **58,20** · 45 → **129**; qalan 17 sətir: nəticəsiz fake, K6, siyahıdan kənar |
| **T2** | E3 | arxivdə; 2023/2024 Payız və 2024/2025 Payız semestrləri YALNIZ fake jurnalda | P0-1 + 15 fake yazılışı | 17 → **32** · 43,50 → **52,22** · 10 → **74** |
| **T3** | E2 mag | DATA_VERIFICATION §3.2 nümunəsi: 2025/2026 Payızda 3 fənn (k1–k3, sərbəst iş, imtahan) yalnız fake jurnalda | 3 fake yazılışı (yeganə nəticə) | 7 → **10** · 86,14 → **88,20** · 35 → **49**; **tam görünür** |
| **T4** | E1 | 3 fənn K9 ilə atılıb (4 imtahan) | 2 qonaq yazılışı (dilim: eyni dövrün qrupu) | 14 → **16** · 63,33 → **66,77**; 1 sətir əkiz qalır |
| **T5** | E2 | fake + K9 + K6; 9 imtahan görünmür | 3 fake + 5 K9 cütü | 27 → **34** · 85,40 → **82,54** (bərpa olunan nəticələr orta balı azaldır — realdır) |
| **T6** | E2 | 6 fənnində J12 slotu yox + fake | J12 + 6 fake yazılışı | 23 → **29** · 49,63 → **48,68**; +10 bal, +6 imtahan |
| **T7** | E1 | silinmiş qrup (9 cüt, 16 imtahan) + fake + K9 | 12 cüt: 5 silinmiş qrup (sübutla) + 4 fake + 3 K9 | 23 → **34** · 66,14 → **68,50**; 8 sətir: qrup sübutu yox / əkiz |
| **T8** | E2 | K9 + K6 | 2 K9 cütü (eyni açılış — bir yazılış) | 41 → 42 · 72,66 → 72,15; K9 əkizləri və K6 qalır |
| **T9** | E2 | K9 + K6 (8 xana) | 4 K9 cütü (2-si əkiz — toxunulmur) | 48 → **52** · 93,65 → 92,06; K6 qalır |
| **T10** | E2 | 3 fake cütü — əkiz | toxunulmur (əkiz) | 30 → 30; §8.1 |
| **T11** | E2 | 9 fake cütü imtahansız | toxunulmur (nəticəsiz) | 24 → 24; §8.2 |
| **T12** | E2 | 21 cüt — siyahıdan kənar (yalnız davamiyyət) | toxunulmur (qəsdən) | 15 → 15; ÜOMG əvvəl də hesablanmırdı |
| **T13** | E3 | hesabı yoxdur (`legacy_account_email_invalid`) — 35 cüt, 18 imtahan, 3 `yekun` | — | §5.4 |

## 5. Bərpa qaydaları və alətlər

### 5.1 J12 — `legacy_repair_lesson_recovery` (1-ci mərhələ, dəyişməyib)
Dərs slotu olmayan xanalar; plan `j12_plan_a7d1.jsonl.gz`, sha256 `ab777837…701538`, 4 766 078 bayt.
Dizayn və 1-ci mərhələ repetisiyası — Əlavə B.

### 5.2 Yeni: `legacy_repair_journal_enrollments` — atılmış yazılışlar (yalnız hazırda oxuyanlar)

**Nə bərpa olunur** (`services/repair_enrollments_select.py`, hər qayda testli):

* **K9 (qrup uyğunsuzluğu):** tələbə çoxqruplu jurnalın siyahısındadır, amma cari qrupu dilimlərdən
  heç biri deyil → J2 yazılışı atıb. **Dilim qaydası:** (1) cari qrup dilimdirsə — o; (2) yoxdursa
  tələbənin HƏMİN dövrdəki köçmüş yazılışlarının qrupu dilimlərdən birinə düşürsə — o (bir neçəsidirsə
  jurnal sırasında birincisi); (3) yoxdursa jurnalın ilk dilimi (`primary_offering` qaydası).
  Nəticə: eyni dövr qrupu 789 · birinci-uyğun 115 · ilk dilim 744. Cari qrupdan fərqli dilimə yazılış
  **qonaq** kimi yaranır (`source_group` = tələbənin öz qrupu, `added_by`, `added_at`) — `guest_roster` /
  `subgroup_rollup`-un EYNİ təmsili (jurnalda «alt qrupdan əlavə» çipi), sadəcə bağlı dövr üçün
  `add_guest_student` işləmədiyindən birbaşa yazılır; sənəd əvəzinə sübut: plan faylı + audit.
* **fake=1:** J-V6 jurnalı atıb, amma tələbənin həmin fənn+semestr üzrə **nəticəsini YALNIZ bu jurnal
  daşıyır** — imtahan xanası (`im`/`im2`, rəqəm) və ya rəsmi `yekun` sətri, VƏ tələbənin həmin
  fənn+semestrdə başqa yazılışı yoxdur. Sübut: köhnə sistem bu nəticəni rəsmi saymışdı (`yekun` yalnız
  2022/2023 Payız üçün doludur; qalan semestrlərdə nəticənin daşıyıcısı jurnalın imtahan xanasıdır;
  DATA_VERIFICATION §3.2: 6 341 fake cütündən yalnız 268-inin normal jurnalda qarşılığı var). Açılış J1-in
  öz kodu ilə qurulur və ya mövcud (fənn, dövr, qrup) açılışına birləşdirilir (C6); dövr bitdiyi üçün
  sxem J7 kimi kilidlənir. Müəllimin `grade.input`-lu aktiv üzvlüyü yoxdursa açılış müəllimsiz qalır.
* **Qrupu silinmiş jurnal (yeni kateqoriya):** real jurnal, amma bütün qrupları mənbənin `groups`
  cədvəlində yoxdur (J1: `legacy_journal_group_unresolved`). Qrup yalnız **sübutla** seçilir: tələbənin
  həmin dövrdəki köçmüş yazılışlarının hamısı TƏK qrupdadırsa — o qrup; sübut yoxdursa və ya bir neçə
  qrupdursa cüt bərpa olunmur (təxmin edilmir).

**Hamısı üçün təhlükəsizlik qaydaları:** yalnız jurnalın `students_id` siyahısındakı tələbə (J2 qaydası —
siyahıdan kənar xana köhnə sistemdə də görünmürdü); tələbənin həmin fənn+semestrdə ARTIQ yazılışı varsa
(«əkiz») bərpa olunmur — fənn transkriptdə/ÜOMG-də iki dəfə sayılmasın; xanası olmayan siyahı cütü bərpa
olunmur; eyni açılışa düşən ikinci jurnal (məs. mühazirə + seminar) J2 kimi **eyni yazılışa** bağlanır
(177 cüt) — onun xanaları da yazılır.

**Plan (lokal, atılabilən klonda).** J12 planı tətbiq olunmuş klonda J1/J3/J4/J12/J5/J5b/J6/J9 **öz
kodu ilə** ayrı ledger ad-sahəsində (`myedu-repair`) işləyir (J12 yalnız bərpa yazılışlarının xanalarını
emal edir — qalanını J12 planı artıq edib); klonda YALNIZ bərpa sətirləri plana çıxarılır, qalan hər
dəyişiklik sayılır (bu planda mövcud sətirlərin yenilənməsi **0**). Başlıqda: seçim sayları, hazırda
oxuyanların siyahısı (P0-1 üçün), ön-şərt planı (J12 sha256), sxem vəziyyəti.
**Tətbiq (server, mənbəsiz):** sha256 → başlıq (tenant, snapshot, import run) → ön-şərt (J12 planının
xülasə audit sətri canlıda VARMI — yoxdursa heç nə edilmir) → plan sahələri canlı modeldə varmı (yoxdursa
heç nə edilmir) → sətir-sətir canlı yoxlama: açılışın dövrü 2026-09-01-dən əvvəl bitməlidir, mövcud açılış
ledger-də MIGRATED olmalıdır; tələbənin aktiv üzvlüyü olmalıdır; başqasının (tələbə, açılış) yazılışı varsa
sətir və uşaqları atlanır; xana/bal/yekun heç vaxt üstündən yazılmır; dərs–yazılış eyni açılışda olmalıdır.
Qapılar: dry-run DEFAULT, `--apply`, markersiz bazada `--i-know-this-is-production`, `--limit`, `--actor`.
**Audit:** hər açılış/sxem/komponent/mövzu/yazılış/dərs/fakt üçün `legacy_repair:journal_enrollments: …`
(yazılışda `restore_key(s)` = legacy jurnal:tələbə açarı), sonda plan sha256-lı xülasə; boş təkrar icra iz
qoymur. **Geri qaytarma:** `scripts/ops/restore_legacy_enrollments_rollback.psql` (audit izindən).

### 5.3 P0-1 yalnız hazırda oxuyanlar — `legacy_repair_archive_status --current-plan`
Tam əhatə 2 291 idi (çoxu keçmiş tələbə). İndi siyahı yazılış planının **möhürlənmiş başlığından**
gəlir (`--current-plan <yazılış planı> --current-plan-sha256 <sha>`): yalnız hazırda oxuyan (E3) 74
tələbə açılır, qalan 2 217 `not_current` səbəbi ilə arxivdə qalır, 199 buraxılmış toxunulmur. Hədəf-tərəf
alternativi `--active-period "2025/2026 Yaz"` da var, amma 8 E3 tələbəni buraxır (onların son semestr
fəaliyyəti yalnız nəticəsiz fake jurnalda və ya siyahıdan kənar xanadadır) — ona görə siyahı tövsiyə olunur.

### 5.4 Hesabı olmayan hazırda oxuyan (d)
Yalnız **1 tələbə** (**T13**, E3): hesab kəsimində `legacy_account_email_invalid` ilə
atlanıb; 35 cüt, 18 imtahan, 3 `yekun`. **Avtomatik yaradılmadı:** hesab yaratmaq kimlik qərarıdır (e-poçt
etibarsızdır), `ad.soyad` toqquşma qaydası və tələbə nömrəsi reyestrin işidir, tarixçə üçün isə legacy id →
hesab bağlantısı (P0-2 yolu) lazımdır. Tövsiyə: reyestr hesabı adi qaydada yaratsın (`ad.soyad`), sonra
P0-2 bağlantısı ilə bu alət yenidən qurulsun — 35 cüt eyni qaydalarla gələcək.

## 6. Repetisiya (production kimi, üç addım birlikdə)

Klon: production nüsxəsi + cari miqrasiyalar, **markersiz**, production-un öz `provision-app-db-role.sh`
SQL-i ilə qurulmuş `NOSUPERUSER NOBYPASSRLS` rol, hər yazı `--i-know-this-is-production` ilə.

| Addım | Nəticə |
|---|---|
| J12 dry-run → apply → təkrar | `lesson 11 607 · mark 161 775 · fact 1 817` · 7 991 qeydiyyat; apply 1,5 dəq; təkrar 0 |
| Yazılış planı: qapılar | markersiz → `legacy_repair_target_not_disposable`; səhv sha → `legacy_repair_plan_sha256_mismatch` |
| dry-run | hamısı `create`: açılış 365 · sxem 365 · komponent 1 846 · mövzu 1 667 · **yazılış 3 326 (1 315 tələbə)** · dərs 9 736 · xana 109 063 · komponent balı 14 533 · **yekun 1 924** · təkrar imtahan 51 · fakt 83; atlanan/konflikt **0** |
| apply | 59 san; FAKTİKİ eyni; mövcud sətirlərin yenilənməsi **0**; 2026/2027 dövrünə düşən açılış/dərs **0** |
| ikinci apply | hamısı `already_present`, FAKTİKİ **0**, audit yoxdur |
| plan = baza | 144 963 sətrin hamısı eyni pk və dəyərlə bazadadır |
| geri qaytarma | `drop_facts` olmadan **rədd** (bağlı sübut faktı var), heç nə dəyişmir; `drop_facts=1` ilə 20 cədvəlin hamısı tətbiqdən əvvəlki izə **eyni**; yenidən apply → ilk tətbiqlə **eyni** |
| P0-1 (plan siyahısı) | arxiv 2 490 → **restore 74** · not_current 2 217 · buraxılmış 199; apply 74 / 0 uğursuz; təkrar 0 |
| 2026/2027 | yazılış 3 251, dərs 1, xana 9 — tam təmiz nüsxə ilə hash **eyni** |
| audit | J12 18 825 · yazılış planı 17 389 · P0-1 74 |
| tələbə görünüşü | §4 — 36 render, hamısı 200 |

## 7. Production runbook

> Hər addımdan əvvəl dry-run rəqəmlərini bu cədvəllə tutuşdurun; fərq varsa **dayanın**. Konteyner
> `educationmanagementstudentarena-app-1`, təşkilat `qku`, aktor `superadmin`, APP_DIR
> `/home/wcu/EducationManagementStudentArena`. Sıra dəyişməzdir: **J12 → yazılışlar → P0-1**.

### 7.0 Hazırlıq
1. **Kod deploy** (yeni miqrasiya yoxdur; production `registrar ≥ 0081_selfwork_points`-da olmalıdır —
   plan bu sxemlə qurulub, uyğunsuz sahə olarsa tətbiq heç nə etmədən rədd edir):
   `docker exec educationmanagementstudentarena-app-1 python manage.py showmigrations registrar | tail -3`
2. **Plan faylları** (`backups/restore_2026_09_25/`, 0600, repoya düşmür):

| Fayl | sha256 | Ölçü |
|---|---|---:|
| `j12_plan_a7d1.jsonl.gz` | `ab777837e4f517e401d16ada68b362edb625b289df30b6641c598ba8af701538` | 4 766 078 |
| `enroll_plan_v7.jsonl.gz` | `9ef7443ac3d786496e9d6620e4de5011b56c1c2088ab2fa438ac46fa265195ec` | 9 408 396 |

### 7.1 J12 (workflow hazırdır)
`COMMAND=legacy_repair_lesson_recovery` (default) — gözlənilən dry-run: `lesson:create 11607 ·
mark:create 161775 · fact:create 1817` · yeni xana alan qeydiyyat 7 991. Apply sonrası:
`select count(*) from registrar_lesson where is_legacy_synthesised;` → 11 607.

### 7.2 Hazırda oxuyanların yazılışları — J12-dən SONRA
```bash
PLAN=/home/wcu/restore/enroll_plan_v7.jsonl.gz
SHA=9ef7443ac3d786496e9d6620e4de5011b56c1c2088ab2fa438ac46fa265195ec
COMMAND=legacy_repair_journal_enrollments scripts/ops/restore_legacy_scores_server.sh check   "$PLAN" "$SHA" superadmin
COMMAND=legacy_repair_journal_enrollments scripts/ops/restore_legacy_scores_server.sh dry-run "$PLAN" "$SHA" superadmin
#   gözlənilən (HAMISI create, skip/konflikt YOX):
#   courseoffering 365 · assessmentscheme 365 · assessmentcomponent 1846 · selfworktopic 1667
#   enrollment 3326 (tələbə 1315) · lesson 9736 · lessonmark 109063 · componentscore 14533
#   finalgrade 1924 · resitrecord 51 · legacygradefact 83
#   J12 tətbiq olunmayıbsa: legacy_repair_plan_prerequisite_missing:lesson_recovery:ab777837e4f5 (dayanın)
COMMAND=legacy_repair_journal_enrollments scripts/ops/restore_legacy_scores_server.sh apply   "$PLAN" "$SHA" superadmin
#   backup.sh → apply (~1 dəq, FAKTİKİ yuxarıdakı rəqəmlər) → ikinci icra: hamısı already_present, FAKTİKİ 0
```
Canlı data plan qurulandan sonra dəyişibsə dry-run bəzi sətirləri `skip_enrollment_exists` /
`skip_live_conflict` / `skip_student_inactive` göstərə bilər — bu, qoruyucunun işidir (üstündən yazılmır);
sayı kiçikdirsə davam etmək olar, böyükdürsə planı təzə dump-dan yenidən qurun
(`scripts/ops/restore_legacy_scores_build_plan.sh <prod dump> <qovluq>` hər iki planı qurur, ~1,5 saat).
**Yoxlama (oxu):**
```sql
select count(*) from audit_auditlog where reason = 'legacy_repair:journal_enrollments: enrollment';  -- 3326
select count(*) from registrar_enrollment e join audit_auditlog a on a.object_id = e.id::text
 where a.reason = 'legacy_repair:journal_enrollments: enrollment' and e.source_group_id is not null;  -- qonaq
```

### 7.3 P0-1 — yalnız hazırda oxuyanlar (yazılış planından SONRA)
```bash
COMMAND=legacy_repair_archive_status scripts/ops/restore_legacy_scores_server.sh dry-run "$PLAN" "$SHA" superadmin
#   gözlənilən: hazırda oxuyan (plan siyahısı) 3648 · arxivdə olan profil 2490
#               bərpa namizədi 74 · not_current 2217 · source_azadedildi 199
COMMAND=legacy_repair_archive_status scripts/ops/restore_legacy_scores_server.sh apply   "$PLAN" "$SHA" superadmin
#   FAKTİKİ bərpa olunan 74, uğursuz 0; ikinci icra 0
```
(Plan faylı burada yalnız möhürlənmiş siyahı mənbəyidir: `--current-plan/--current-plan-sha256`.)
Tələbə görünüşü: serverdə staff «view-as» ilə 2-3 tələbəyə baxmaq kifayətdir;
`scripts/ops/restore_current_students_verify.py` YALNIZ klonda (giriş sessiyası yazır).

### 7.4 Geri qaytarma
* Yazılış planı (DB owner / superuser): `docker exec -i <postgres> psql -U <owner> -d emsarena_db
  -v plan_sha=$SHA -v drop_facts=1 -f - < scripts/ops/restore_legacy_enrollments_rollback.psql` —
  bağlı faktlar varsa `drop_facts=1`-siz dayanır; sonradan bu sətirlərə düzəliş bağlanıbsa FK silməni
  dayandırır. Repetisiyada nəticə tətbiqdən əvvəlki vəziyyətlə eynidir.
* J12: `scripts/ops/restore_legacy_scores_rollback.psql` (Əlavə B). P0-1 geri qaytarması skriptlənməyib
  (74 hesabı yenidən arxivləmək lazım olsa — audit `legacy_repair:archive_status` siyahısı ilə).
* Son çarə — addımdan əvvəlki `backup.sh` nüsxəsi.

### 7.5 Workflow-a əlavə (koordinator üçün)
`prod-legacy-restore.yml`-ə `repair` girişi (choice: `lesson_recovery` | `journal_enrollments` |
`archive_status`) və addım env-i `COMMAND: legacy_repair_${{ github.event.inputs.repair }}` kifayətdir —
server skripti üç əmri eyni `check/dry-run/apply` interfeysi ilə işlədir; `archive_status` üçün asset
yazılış planının özüdür (eyni sha256).

## 8. Açıq qərarlar (sahib)

1. **Əkiz jurnalda qalan imtahan (ən vacib).** 417 fənn sətrində (301 hazırda oxuyan, 430 imtahan xanası;
   əsasən 2024/2025 və 2025/2026) tələbənin köçmüş yazılışı var, amma **imtahanı yoxdur** («köhnə sistemdə
   nəticə yoxdur» göstərir), imtahan balı isə bərpa olunmayan ikinci jurnaldadır (308 fake, 109 K9).
   Təklif: yalnız imtahan/yekun köçürən ayrıca plan (J6-nın öz kodu, hədəf = mövcud yazılış, yalnız BOŞ
   `exam_score` doldurulur, audit ilə); gündəlik xanalar qarışdırılmır. Qərar: hansı jurnal rəsmidir?
2. **Nəticəsiz fake jurnallar** (595 sətir: yalnız gündəlik bal/komponent, imtahan yox) — DATA_VERIFICATION §4.2.
3. **Qrup sübutu olmayan silinmiş-qrup jurnalları** (344 sətir, 76 tələbə, ~320 imtahan): tələbənin o
   semestrdə başqa yazılışı yoxdur — qrupu yalnız cari qrupla «təxmin» etmək olar; təklif etmirik.
4. **K6** xarici dil komponentləri (259 sətir) — model qərarı. 5. **Hesabı olmayan 1 tələbə** — §5.4.
6. **Hazırda oxumayanlar** (P0-1-in qalan 2 217 arxivi, onların K9/fake cütləri) — ayrıca qərar.

## 9. Fayllar

| Fayl | Nədir |
|---|---|
| `apps/legacy_import/management/commands/legacy_repair_journal_enrollments.py` | yeni əmr: plan / tətbiq / yenidən çıxarış |
| `apps/legacy_import/services/repair_enrollments_{select,replay,extract,plan,apply,specs}.py` | seçim qaydaları · klonda təkrar · çıxarış · plan · canlı tətbiq · model spesifikasiyası |
| `apps/legacy_import/services/repair_archive.py` · `…/commands/legacy_repair_archive_status.py` | P0-1: `--current-plan`, `--active-period` |
| `apps/legacy_import/services/repair_plan_file.py` | + `read_plan_header` |
| `apps/legacy_import/tests/test_repair_journal_enrollments.py` · `test_repair_archive_current.py` | 22 + 10 test (PostgreSQL) |
| `scripts/ops/restore_legacy_scores_server.sh` · `…_build_plan.sh` | server (3 əmr) · lokal plan (hər iki plan) |
| `scripts/ops/restore_legacy_enrollments_rollback.psql` · `restore_current_students_verify.py` | geri qaytarma · tələbə görünüşü (klonda) |
| `backups/restore_2026_09_25/` (gitignore, 0600) | planlar + manifest + sha256, bərpa olunmayan cütlər, adlı tələbə × fənn cədvəli |

---

## Əlavə A — 1-ci mərhələ: bütün tələbələr üzrə kateqoriyalar

| Kateqoriya | Tələbə | Görünməyən | Kök səbəb | Vəziyyət |
|---|---:|---|---|---|
| Dərs slotu yoxdur (K10/K10b) | 1 974 | 7 991 qeydiyyatda 161 775 xana (12 208 bal, 18 794 qayıb) | J12 production-da işləməyib | ✅ J12 planı |
| Səhv arxiv (P0-1) | 2 291 | bütün balları (giriş bağlı) | qəbul ili tapılmayan tələbə arxivə salınıb | ✅ hazırda oxuyan 74 (§5.3) |
| Fake jurnallar (J-V6) | 2 648 | 8 219 fənn sətri, 6 523 imtahan, 1 059 `yekun` | J1 `fake=1`-i atır | ✅ hazırda oxuyanlarda yeganə nəticə daşıyıcısı |
| Qrup uyğunsuzluğu (K9) | 1 402 | 3 449 fənn sətri, 1 389 imtahan | J2 cari qrupla seçir | ✅ hazırda oxuyanlar (qonaq) |
| Hesabı yoxdur (P0-2) | 171 | 2 782 fənn sətri | e-poçt kimlik açarı | ⏳ |
| Silinmiş qrupun jurnalı | 256 | 1 706 fənn sətri, 913 imtahan | qrup mənbədə yoxdur | ✅ sübutla (hazırda oxuyanlar) |
| Siyahıda olmayan tələbə | 2 686 | əsasən davamiyyət | köhnə sistemin öz siyahısı | ❌ qəsdən |
| İmtahan cəhdi jurnala bağlanmır (K13) | 2 031 | 6 513 cəhd | mənbədə jurnal sütunu yoxdur | ❌ (fakt sübutda) |
| Xarici dil komponentləri (K6) | 712 | 3 535 xana | modeldə növ yoxdur | ⏳ |

## Əlavə B — J12 (1-ci mərhələ): alət, repetisiya, geri qaytarma

Production 2026-08-27 repetisiyasından qurulub (run `fa9516a9`), J12 fazası ondan sonra yazılıb; mövcud
təmir əmrləri production-un `NOSUPERUSER NOBYPASSRLS` rolu altında RLS-kor idi (düzəldildi:
`repair_support.build_context` tenant + aktor kontekstini qurur); Docker `/dev/shm` 64 MB olduğundan təmir
tranzaksiyaları paralel sorğunu söndürür. Plan: J12-nin öz kodu klonda, orijinal import run-una bağlı
həll indeksləri ilə; tətbiq hər sətri canlıya qarşı yoxlayır, mövcud xana üstündən yazılmır.
Repetisiya (production kimi): dry-run `lesson 11 607 · mark 161 775 · fact 1 817`; apply 51–90 san; təkrar
0; J12-nin öz nəticəsi ilə checksum bayt-bəbayt eyni; nəticəyə təsir yalnız `absence_hours` (5 400) və
davamiyyət balıdır — giriş/yekun/hərf/keçid **dəyişmir**. J12 dövrlər üzrə: 2021/2022 Yaz 11 331 dərs /
158 264 xana; qalan dövrlər cəmi 276 dərs. Geri qaytarma:
`psql -v plan_sha=$SHA -v drop_facts=1 -f - < scripts/ops/restore_legacy_scores_rollback.psql`
(audit izindən `absence_hours`-u köhnə dəyərə qaytarır, planın dərslərini/xanalarını silir).
