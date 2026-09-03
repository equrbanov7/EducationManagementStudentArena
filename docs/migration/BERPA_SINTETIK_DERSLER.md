# Bərpa olunan dərslər (J12) və toqquşma sübutu — sahib sənədi

> **Qayda dəyişmir:** «Biz köhnə datanı dəyişmirik, sadəcə yeni sistemə
> köçürürük.»  Bu iş həmin qaydanın **tələbidir**: mənbədə DURAN data hədəfə
> ÇATMIRDI.  Heç bir mövcud dəyər dəyişmir — yalnız çatmayan sətirlər əlavə
> olunur.

| | |
|---|---|
| Faza | `journal_lesson_recovery` (J12), sıra **41** |
| Modullar | `apps/legacy_import/services/rehearsal_lesson_recovery_{source,scan,targets,phase}.py` |
| Ledger varlıqları | `lesson_synthesised`, `journal_mark_recovered`, `legacy_mark_conflict` |
| Model nişanı | `registrar.Lesson.is_legacy_synthesised` (migrasiya `0059`) |

---

## 1. Problem — ölçülmüş, təxmin deyil

J4 (`journal_marks`) bir bal xanasını **yalnız mövcud `Lesson` sətrinə** bağlaya
bilir; dərs indeksi isə `journals_dates_added_by_teacher` cədvəlindən qurulur.

Canlı mənbədə **570 jurnalın** həmin cədvəli boşdur və ya demək olar boşdur
(**183-ündə sıfır sətir**), halbuki bal cədvəli doludur.  Nəticə:

| | dəyər |
|---|---:|
| Hədəfə düşməyən xana | **164,747** |
| Fərqli dərs slotu | 11,057 |
| Təsirlənən tələbə | 1,984 |
| Təsirlənən fənn | 567 |

İtən xanaların tərkibi:

| Məzmun | Xana | Nə itir |
|---|---:|---|
| İştirak (`ie`) | 133,215 | davamiyyət sübutu |
| Qayıb (`qb`) | 19,108 | `absence_hours` və imtahana buraxılış həddi |
| Rəqəmli bal 1-10 | 12,029 | **akademik qiymət** |
| Bal 0 | 395 | akademik qiymət |

**Bağlanma artefaktı deyil.**  Yoxlandı: `journals_dates_added_by_teacher`-də
cəmi **28** orphan sətir və **20** pozuq saatlı sətir var; `journals`-də təkrar
`uniqid` **yoxdur**.  Yəni itən dərs cədvəli mənbənin özündə yoxdur, başqa açar
altında gizlənmir.

---

## 2. Bərpa qaydası — dərs UYDURULMUR

İtən dərsin `(ay, gün, saat)` üçlüyü **bal xanasının özündədir**
(`journals_dates_points.month_id` / `day_number` / `time`).  J12 həmin
üçlükdən `Lesson` sətrini bərpa edir.

Nərdivan (J4-ün öz pillələri, eyni sırada):

1. **A keçidi (kəşfiyyat).** J4-ün nərdivanı yeridilir; yalnız `lesson`
   pilləsində ilişən xanaların slotları toplanır.
2. **Materiallaşma.** Hər slot üçün bir `Lesson`:
   * `is_legacy_synthesised = True` — **açıq nişan**;
   * ledger kodu `legacy_lesson_synthesised`;
   * `created_by = NULL` (import heç kimin adından yazmır);
   * `instructor` = açılışın müəllimi (J3 ilə eyni);
   * `kind` J3-ün öz `LessonKindIndex`-i ilə xanalardan törəyir — **ballı xana
     `lecture` altında gizlənmir**.
3. **B keçidi (yazı).** Eyni nərdivan genişlənmiş dərs indeksi ilə təkrarlanır;
   xanalar J4-ün ÖZ `LessonMarkWriter`-i ilə yazılır: xalis `INSERT`, mövcud
   xana **üstündən yazılmır**.
4. **Davamiyyət.** `recompute_absence_hours` (J4-ün güzgüsü) işləyir.

### Sahib nəyi görür

Jurnalda bərpa olunan sütun adi dərs kimi görünür, amma `Lesson` sətrində
`is_legacy_synthesised = True` durur və ledger-də `legacy_lesson_synthesised`
kodu var.  Sual «bu dərsi müəllim yazıb?» — **cavab: XEYR**; sual «bu dərsdəki
bal mənbədən gəlir?» — **cavab: BƏLİ, dəyişdirilməmiş**.

```sql
-- Bərpa olunan dərslər (hədəf bazada):
SELECT count(*) FROM registrar_lesson WHERE is_legacy_synthesised;
-- Bir açılışın bərpa sütunları:
SELECT date, start_time, kind, hours FROM registrar_lesson
 WHERE offering_id = :offering AND is_legacy_synthesised ORDER BY date;
```

---

## 3. Saat — 2024 semantika dəyişikliyi

`journals_dates_rooms.saatliq_ders` sütununun **vahidi** 2023/2024 tədris ilinin
yaz semestrində dəyişib.  Canlı ölçü (`fake=0`, dərsin öz `date` sütunu üzrə):

| Dövr | Jurnal | Orta slot/jurnal | `saatliq_ders` cəmi/jurnal |
|---|---:|---:|---:|
| < 2024-02 | 4,471 | 19.7 | **38.8** (≈ 2 / slot) |
| ≥ 2024-02 | 7,157 | 24.8 | **24.5** (≈ 1 / slot) |

Aylıq keçid nöqtəsi dəqiqdir: 2023-12-də 9,932 sətrin 756-sı `1`; 2024-02-də
6,363 sətrin 6,297-si `1`.

Slot sayı azalmayıb (əksinə artıb), yəni akademik saat cəmi yarıya düşə bilməz —
**dəyişən vahiddir**: köhnə dövrdə sütun akademik saat, yeni dövrdə **cüt**
sayır.  Slot şəbəkəsi hər iki dövrdə eynidir (08:30 · 10:00 · 11:30 · 13:30 ·
15:00 · 16:30 — 90 dəqiqəlik addım), yəni bir slot həmişə bir cütdür.

Bərpa olunan dərsin saatı:

```
saat = saatliq_ders × 2   (tarix ≥ 2024-02-01)
saat = saatliq_ders       (tarix <  2024-02-01)
```

* Yeni dövrdə `0.5` (yarım cüt) artıq tam ədədə düşür → **1 akademik saat**.
* Köhnə dövrdə `0.5` tam ədəd vermir → J3 defoltu (2) qalır +
  `legacy_lesson_synth_hours_fractional` (WARNING).
* Metadata sətri ümumiyyətlə tapılmasa → J3 spec defoltu **2 saat** (bir cüt) +
  `legacy_lesson_synth_hours_unresolved` (INFO).

Praktikada metadata demək olar yoxdur: **11,057 bərpa slotundan yalnız 13-ü**
`journals_dates_rooms`-da qarşılıq tapır (193 xana).  Qalanı defolt 2 saatla
qalır — bu, yeni dövrün bir cütü ilə eynidir.

### ⚠️ Sahibin AYRICA qərar verməli olduğu məsələ (bu iş onu DƏYİŞMİR)

J11 (`journal_lesson_meta`) **mövcud** dərslərə `saatliq_ders`-i **olduğu kimi**
yazır, vahid çevrilməsi olmadan.  Yəni 2024-02-dən sonrakı real dərslərin
hədəfdəki `hours` dəyəri **1**-dir, halbuki bir cüt = 2 akademik saatdır.
Bu, `absence_hours`-u və imtahana buraxılış həddini **aşağı** göstərir.

J12 mövcud sətirlərə toxunmur (tapşırığın 5-ci bəndi), ona görə bu düzəliş
**ayrıca qərar** kimi qalır.  Ölçü: ~285,000 dərs sətri 2024-02-dən sonrakıdır.

---

## 4. Saat və tarix naməlum olanda

| Hal | Qərar |
|---|---|
| Saat "HH:MM"-ə düşmür (legacy `TIME` 24 saatı aşır) | **Dərs YARADILIR**, `start_time` NULL qalır, `legacy_lesson_synth_time_unknown` (WARNING) |
| Törədilmiş il + (ay, gün) real tarix vermir (məs. 31 noyabr) | Dərs YARADILMIR, xana karantində qalır — `legacy_lesson_synth_date_invalid` (WARNING).  Tarix **təxmin edilmir**. |
| Mövzu/otaq metadatası yoxdur | Boş qalır (təxmin yoxdur) |

---

## 5. İdempotentlik

`SynthLessonWriter` əvvəlcə mövcud sətri axtarır, sonra yalnız çatışmayanı
yaradır; açar `(organization, offering, date, start_time)` — J3-ün öz təbii
açarı.  İkinci icrada:

* bütün açarlar tapılır → `bulk_create` boşdur, möhür `already_present` ilə
  SKIPPED yazılır;
* jurnal-səviyyə möhür (`mr:<uniqid>`) ledger-də olduğu üçün sürücü həmin
  jurnalın heç bir sətrini yenidən hesaba almır;
* faza digest-i **eynidir** (test: `test_running_the_phase_twice_creates_no_duplicates`).

⚠️ **Yarımçıq keçidin resume-u.**  İcra dərs möhürü ilə xana yazısı ARASINDA
kəsilsə, davam etməli olan run dərsi yenidən yaratmır (möhür var), amma slot
indeksini YENƏ doldurur — əks halda xanalar «dərs tapılmadı» sayılıb İKİNCİ
dəfə itərdi.  Bu, 2026-08-31 klon icrasında ölçülmüş real boşluqdur; regressiya
testi: `test_a_half_finished_run_resumes_and_still_writes_the_missing_marks`.

> **Doğrulamanın əhatəsi — dürüst qeyd.**  Yuxarıdakı rəqəmləri verən klon
> icrası bu düzəlişdən ƏVVƏLKİ kodla getdi (düzəliş məhz həmin icranın
> çıxışına baxarkən tapıldı).  Düzəlişin özü **vahid testi ilə** örtülüdür,
> real data üzərində TƏKRAR icra edilməyib.  Rəqəmlərə təsiri yoxdur: `add()`
> yolundakı fərq yalnız `recorded` DOLU olanda (yəni resume-da) işə düşür,
> təmiz icrada `recorded` boşdur və iki kod yolu sətir-sətir eyni davranır.

---

## 6. Toqquşma sübutu — 1,653 xana

J-V4 dedup açarı `journal_uniqid`-i **daxil edir**, hədəf açarı
(`lesson`, `enrollment`) / (`component`, `enrollment`) / (`enrollment`, `im`)
isə **etmir**.  13,875 legacy jurnal hədəfdə 11,115 açılışa **birləşir**, ona
görə iki ayrı jurnalın eyni tələbə/slot xanası hədəfdə **bir** sətrə düşür.

| Domen | Toqquşma | Eyni dəyər (itki YOX) | Fərqli dəyər (İTKİ) | Uduzan indi haradadır? |
|---|---:|---:|---:|---|
| Təqvim (`LessonMark`) | 25,920 | 24,572 | **1,348** | J12 → `registrar_legacygradefact` |
| Komponent (`ComponentScore`) | 2,292 | 2,007 | **285** | J12 → `registrar_legacygradefact` |
| İmtahan (`FinalGrade`/`ResitRecord`) | 557 | 537 | **20** | **ARTIQ** `registrar_legacygradefact`-də (aşağı bax) |
| **CƏMİ** | **28,769** | **27,116** | **1,653** | |

**Qalib DƏYİŞMİR.**  J12 yalnız uduzan dəyəri append-only sübut qatına yazır:

```sql
SELECT source_table, source_pk, score_code, raw_score_text, source_journal_ref,
       source_student_ref, source_lesson_ref
  FROM registrar_legacygradefact
 WHERE mapping_status = 'conflict';
```

* `raw_score_text` — **itən** dəyər (clamp/quantize edilmədən);
* `score_code` — hansı domendən (`01`…`12` təqvim, `k1`/`k2`/`k3`/`si` komponent);
* `source_lesson_ref` — qalibin daşıyıcısı olan `Lesson` (təqvim halında);
* `enrollment` — hər iki dəyərin baxdığı yazılış.

> `mapping_issue_code` sütunu `legacy_grade_fact_conflict`-dir — onu PostgreSQL
> trigger-i (`registrar_guard_legacy_grade_fact_insert`) bağlayır.  Domen kodu
> (`legacy_journal_mark_recovered_target_conflict` /
> `legacy_journal_component_target_conflict`) ledger issue-sundadır.

---

## 7. ⚠️ ƏL İLƏ BAXILMALI: 20 imtahan balı toqquşması

Bu 20 sətir **yekun bala birbaşa təsir edir** və avtomatik həll edilmir.

**Onların dəyəri İTMƏYİB**: J-facts fazası bütün `im`/`im2` sətirlərini
`registrar_legacygradefact`-ə yazır, yəni hər iki dəyər sübut qatındadır
(yoxlanıldı: 20/20 sətir mövcuddur).  İtən yalnız **hansının qalib olduğu**
qərarıdır — kanonik `FinalGrade.exam_score` / `ResitRecord.resit_score`
sətrində yalnız biri durur.

Qərar meyarı mənbədə **yoxdur** (hər iki jurnal eyni tələbənin eyni fənnini
göstərir, `update_counter` bərabərdir), ona görə İmtahan Mərkəzi əl ilə
baxmalıdır.

| # | Fənn | Jurnal (`uniqid`) | Legacy tələbə | Kod | Hədəfdə QALAN | İTƏN dəyər | `source_pk` |
|---:|---|---|---:|---|---:|---:|---:|
| 1 | Ehtimal nəzəriyyəsi və riyazi statistika | `1ISwpTnGkd` | 2655 | `im2` | 11 | **23** | 4677295 |
| 2 | Ehtimal nəzəriyyəsi və riyazi statistika | `1ISwpTnGkd` | 2672 | `im2` | 13 | **24** | 4677299 |
| 3 | Ekonometrika | `I7lfOZk0uU` | 465 | `im2` | 11 | **17** | 911411 |
| 4 | Kompüter diaqnostikası | `ASuNVSqTD2` | 129 | `im` | 17 | **11** | 2890957 |
| 5 | Kompüter diaqnostikası | `ASuNVSqTD2` | 132 | `im2` | 18 | **24** | 2890956 |
| 6 | Mülki müdafiə | `192la7eXkB` | 3256 | `im` | 1 | **39** | 940110 |
| 7 | Psixi sağlamlıq | `PBJML4X1lY` | 6412 | `im` | 49 | **47** | 4658455 |
| 8 | Psixi sağlamlıq | `PBJML4X1lY` | 6414 | `im` | 47 | **45** | 4658457 |
| 9 | Psixi sağlamlıq | `PBJML4X1lY` | 6415 | `im` | 41 | **42** | 4658459 |
| 10 | Psixi sağlamlıq | `PBJML4X1lY` | 6416 | `im` | 41 | **44** | 4658463 |
| 11 | Psixi sağlamlıq | `PBJML4X1lY` | 6417 | `im` | 48 | **47** | 4658460 |
| 12 | Psixi sağlamlıq | `PBJML4X1lY` | 6418 | `im` | 48 | **45** | 4658456 |
| 13 | Psixi sağlamlıq | `PBJML4X1lY` | 6422 | `im` | 48 | **44** | 4658458 |
| 14 | Qafqaz xalqları tarixi | `IIY4XEtb4r` | 2680 | `im` | 36 | **34** | 824961 |
| 15 | Qafqaz xalqları tarixi | `IIY4XEtb4r` | 2683 | `im` | 38 | **35** | 824962 |
| 16 | Qafqaz xalqları tarixi | `IIY4XEtb4r` | 2687 | `im` | 38 | **36** | 824965 |
| 17 | Qafqaz xalqları tarixi | `IIY4XEtb4r` | 2692 | `im` | 32 | **27** | 824966 |
| 18 | Qafqaz xalqları tarixi | `IIY4XEtb4r` | 2694 | `im` | 34 | **35** | 824963 |
| 19 | Qafqaz xalqları tarixi | `IIY4XEtb4r` | 2696 | `im` | 33 | **27** | 824960 |
| 20 | Qafqaz xalqları tarixi | `IIY4XEtb4r` | 2880 | `im` | 42 | **32** | 824964 |

Üç jurnal itkinin 90 %-ni daşıyır: `PBJML4X1lY` (7), `IIY4XEtb4r` (7),
`ASuNVSqTD2` + `1ISwpTnGkd` (4).  **12 halda** itən dəyər hədəfdəkindən
AŞAĞIDIR, **8 halda** (`#1`, `#2`, `#3`, `#5`, `#6`, `#9`, `#10`, `#18`)
YUXARIDIR — yəni «həmişə yüksəyi seç» kimi avtomatik qayda tətbiq etmək olmaz.

> ⚠️ **`#6` sətri 2026-08-31-də düzəldildi.**  Əvvəlki redaksiya onu
> `to1pjtYjdE` / `835502` / «qalan 39, itən 1» kimi göstərirdi.  Bu, oflayn
> replay-in TƏXMİN etdiyi qalib idi; hədəfin FAKTİKİ dəyəri isə
> `FinalGrade.exam_score = 1.00`-dır.  Səbəb: bu, iki deyil, **üç** sətirlik
> qrupdur — `192la7eXkB` jurnalında həmin tələbənin iki `im` sətri var
> (`835169` = 1, `940110` = 39; J-V4 dedup `940110`-u seçir), `to1pjtYjdE`-də
> isə bir sətir (`835502` = 1).  Hədəfə `to1pjtYjdE`-nin **1**-i düşüb, ona görə
> həqiqətən itən dəyər `192la7eXkB`-nin **39**-udur.  `835502` eyni dəyərli
> təkrardır — itki deyil.  Siyahının qalan 19 sətri hədəfin kanonik dəyəri ilə
> bir-bir tutuşdurulub və dəqiqdir.  Bu, siyahıdakı ən böyük fərqdir (38 bal).

Hər sətir üçün mənbə faktı:

```sql
SELECT * FROM registrar_legacygradefact WHERE source_pk = 4658460;
```

İmtahan Mərkəzi qərarını `registrar_legacygradereview` (append-only) ilə
qeyd edir; kanonik dəyər yalnız audited düzəliş axını ilə dəyişə bilər.

---

## 8. Nə DƏYİŞMİR

* Mövcud `Lesson` sətri (saat, mövzu, otaq, növ) — **toxunulmur**.
* Mövcud `LessonMark` / `ComponentScore` / `FinalGrade` dəyəri —
  **üstündən yazılmır** (yazıcı xalis `INSERT` axınıdır, J-V10).
* `im`/`im2` sətirləri — J12 onlara heç bir sətir əlavə etmir.
* J3/J4/J5/J6 fazalarının möhür resepti və `phase_digest`-i — dəyişməyib
  (J12 ayrıca faza, ayrıca varlıq tiplərindədir).

## 9. Gözlənilən yan təsir: `absence_hours` DƏYİŞƏCƏK

19,108 bərpa olunan qayıb `Enrollment.absence_hours`-u artıracaq.  Bu,
**gözləniləndir**: hazırkı dəyər aşağıdır, çünki həmin qayıblar hədəfə heç vaxt
düşməyib.  Faza `recompute_absence_hours`-un qaytardığı **dəyişən yazılış
sayını** `journal_lesson_recovery.absence_updated.<N>` qeydi ilə hesabata
çıxarır.

⚠️ Qiymət dəyərlərinə toxunulmur — yalnız çatışmayan xanalar əlavə olunur.

---

## 10. Necə yoxlanılıb

**Vahid/qərar testləri** — `apps/legacy_import/tests/test_rehearsal_lesson_recovery_phase.py`
(26 test): dərs cədvəli BOŞ olan sintetik mənbə, nişanın yoxlanması, dövr-şüurlu
saat cədvəli, saatsız/pozuq tarixli hallar, mövcud sətirlərə toxunmama,
idempotentlik (iki icra → eyni `phase_digest`), `absence_hours`, toqquşma
uduzanının `LegacyGradeFact`-a düşməsi və ledger rebuild-in digest-i
təkrarlaması.

**Real data doğrulaması** — faza `emsarena_rehearsal_52ea0301808c` sübut
bazasının **KLONU** üzərində icra olunub (sübut bazasına yalnız `SELECT`).
Mənbə həmin MariaDB snapshot-udur (`177ef226…`).  Nəticələr aşağıdakı
bölmədədir.

### Ölçülmüş nəticə (klon üzərində REAL icra, 2026-08-31)

| Göstərici | BƏRPADAN ƏVVƏL | SONRA | Fərq |
|---|---:|---:|---:|
| `registrar_lesson` | 293,070 | 304,677 | **+11,607** |
| ondan `is_legacy_synthesised` | 0 | **11,607** | +11,607 |
| `registrar_lessonmark` | 3,711,153 | 3,872,928 | **+161,775** |
| ondan `status='absent'` | 507,734 | 526,528 | **+18,794** |
| ondan `score IS NOT NULL` | 216,453 | 228,661 | **+12,208** |
| `LegacyGradeFact` (`mapping_status='conflict'`) | 506 | 2,236 | **+1,730** |
| `Enrollment.absence_hours` CƏMİ | 660,446 | 698,025 | **+37,579 saat** |
| `absence_hours > 0` olan yazılış | 99,934 | 104,156 | **+4,222** |

**Bərpa olunan dərsin profili:**

| Növ | Say | | Saat | Say |
|---|---:|---|---|---:|
| `seminar` | 6,281 | | 2 | 11,604 |
| `lecture` | 5,322 | | 1 | 3 |
| `lab` | 4 | | `start_time` NULL | 1 |

11,607 dərsin **6,285-i** `seminar`/`lab`-dır — yəni bərpa olunan rəqəmli bal
jurnal interfeysində GÖRÜNÜR (LECTURE bal xanasını bağlayardı).

**Niyə 161,775, 164,747 deyil?**  Fərq (2,972) hədəf açarı toqquşmasıdır: eyni
açılışa birləşən iki legacy jurnalın eyni tələbə/slot xanası hədəfdə BİR sətrə
düşür.  Dəyərləri eyni olanlar itki DEYİL; fərqli olanlar (**97 yeni toqquşma**)
sübut qatına yazılıb.

**Toqquşma sübutunun bölgüsü** (`registrar_legacygradefact`, `conflict`):

| `score_code` | Say | Qeyd |
|---|---:|---|
| təqvim (`01`…`12`) | **1,445** | 1,348 J4-ün gördüyü + 97 bərpa xanaları arasında YENİ |
| komponent (`k1`/`k2`/`k3`/`si`) | **285** | ölçülmüş rəqəmlə DƏQİQ üst-üstə düşür |
| `yekun` | 506 | bərpadan ƏVVƏL də var idi (J-facts) |

> A keçidi canlı mənbədə **11,607 bərpa slotu** tapıb (11,057 legacy slot ×
> jurnalın qrup dilimləri).  Xam log: `scratchpad/j12_verify*.log`.

### Müstəqil təsdiq (2026-08-31, klon bazasına birbaşa SQL)

Yuxarıdakı cədvəl faza hesabatındandır.  Aşağıdakılar hədəf bazanın ÖZÜNDƏN,
fazadan asılı olmadan ölçülüb.

**1. Mövcud heç bir dəyər dəyişməyib — barmaq izi ilə sübut.**
Bərpadan ƏVVƏLKİ 3,711,153 xananın `(id, status, score)` üçlüyü üzrə MD5:

| Baza | Xana | Barmaq izi |
|---|---:|---|
| sübut bazası (`…52ea0301808c`, toxunulmamış) | 3,711,153 | `5b03c2f057b23ad9f6b4d1c13dbb8e5b` |
| bərpadan sonra (sintetik olmayan dərslərdəki xanalar) | 3,711,153 | `5b03c2f057b23ad9f6b4d1c13dbb8e5b` |

**EYNİDİR** — yəni bir dənə də mövcud qiymət və ya davamiyyət dəyəri
dəyişməyib, silinməyib, üstündən yazılmayıb.

**2. Yeni xanaların HAMISI bərpa olunan dərslərdədir.**
Sintetik olmayan dərslərdəki xana sayı bərpadan sonra da tam **3,711,153**-dür;
161,775 yeni xananın hamısı `is_legacy_synthesised=True` dərslərə bağlıdır.
Yəni müəllimin yazdığı heç bir dərs sütununa xana ƏLAVƏ də edilməyib.

**3. Bərpa olunan 161,775 xananın tərkibi:**

| Status | Xana | ondan ballı |
|---|---:|---:|
| `present` | 142,969 | **12,208** |
| `absent` | 18,794 | — |
| `excused` | 12 | — |

Təsir: **7,991 yazılış**, **564 açılış**.

**4. Davamiyyət dəyişikliyi — dəqiq rəqəm.**
Hər iki bazanın `registrar_enrollment.absence_hours` sütunu sətir-sətir
tutuşdurulub (148,020 yazılış):

| Göstərici | Dəyər |
|---|---:|
| `absence_hours`-u DƏYİŞƏN yazılış | **5,400** |
| əlavə olunan saat (cəmi) | **+37,579** |
| dəyəri AZALAN yazılış | **0** |

Bütün dəyişikliklər ARTIMdır — gözlənilən nəticə: həmin qayıblar əvvəl hədəfə
heç vaxt düşməmişdi, ona görə `absence_hours` aşağı görünürdü.

### Əl ilə izlənən nümunələr — bərpadan sonra

İlkin auditin 20 nümunəsindən üçü (məhz «bal itdi» diaqnozu alanlar) klon bazada
yenidən izlənib:

| Jurnal | Legacy tələbə | Slot | Mənbədəki dəyər | Hədəfdə İNDİ |
|---|---:|---|---|---|
| `55FruTFBaJ` | 837 | 2022-03-09 11:30 | **2** | `seminar`, 2 saat, `present`, **bal 2.00** |
| `KOdUVeGD5D` | 612 | 2022-03-31 15:00 | **10** | `seminar`, 2 saat, `present`, **bal 10.00** |
| `N4sgxDwzXT` | 346 | 2022-03-29 13:30 | `qb` | `seminar`, 2 saat, **`absent`** |

Üçü də əvvəl hədəfdə TAMAMİLƏ YOX idi.  Üçü də `seminar` növündədir, yəni bal
xanası jurnal interfeysində AÇIQdır.
