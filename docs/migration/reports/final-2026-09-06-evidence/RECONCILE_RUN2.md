# Legacy → EMS Arena köçürmə uzlaşdırma hesabatı

> Bu «testlər keçdi» hesabatı DEYİL.  Bu, **hər mənbə xanasına nə olduğunun**
> mühasibatıdır.  Tutmayan hər rəqəm aşağıda **İZAH OLUNMAMIŞ FƏRQ** kimi
> açıq göstərilir — gizlədilmir.

**Rejim:** hər iki bazaya YALNIZ OXU (`SET TRANSACTION READ ONLY`).  Heç bir
`INSERT` / `UPDATE` / `DELETE` icra olunmur.

| Sahə | Dəyər |
|---|---|
| Hesabat vaxtı | 2026-09-06 20:48:37 |
| Mənbə (MariaDB) | `emsarena-legacy-source-rehearsal:myedudb` |
| Hədəf (PostgreSQL) | `127.0.0.1:55433/emsarena_rehearsal_66a6dfed1f70` |
| Repetisiya rejimi / statusu | `rehearsal` / `succeeded` |
| Snapshot SHA-256 | `177ef2269027395f…` |
| Ledger-in gördüyü mənbə sətri | 15,496 |
| Başlama → bitmə | 2026-09-06 08:20:02.590617+00:00 → 2026-09-06 12:44:34.612123+00:00 |

## 0. Bir baxışda

| Göstərici | Say | Mənbənin %-i |
|---|---|---|
| Mənbə jurnal xanası (canlı + arxiv, xam) | 5,911,322 | 100 % |
| Hədəfdə yaradılan sətir | 4,587,875 | 77.6 % |
| İzah olunmuş fərq (boş / oxunmayan / arxiv / dublikat / orphan / yazılış / dərs slotu / toqquşma) | 1,323,447 | 22.4 % |
| **İZAH OLUNMAMIŞ FƏRQ** | **0** | 0.0 % |

**Nəticə:** ✅ Bütün domenlər tutur.

### Ən diqqətçəkən rəqəmlər

1. **15,576** jurnal-yazılışı ötürülüb (7.8 %) — əsas səbəb `legacy_journal_student_inactive` (5 hadisə). Həmin tələbələrin bal xanaları da hədəfə düşmür.
2. **2,042** legacy jurnal açılışa çevrilməyib; onlara bağlı bütün xanalar nərdivanda «orphan jurnal» pilləsindədir.
3. **17** tələbə arxiv üzvlüyü ilə köçüb (aktiv: 7,599) — heç bir hesab silinməyib.
4. **534,323** qayıb və **3,381,803** iştirak xanası davamiyyət kimi oturub; bal daşıyan xana isə **231,677**.
5. `yekun` cədvəlinin **1,513** sətri hədəfdəki yazılışa bağlana bilməyib (yazılış köçürülmədiyi üçün).
6. **4,659** xana heç bir domenə düşmür (naməlum `month_id`) — import-un say balansı onları görmür, bu hesabat görür (§1.3).

## 1. Sətir mühasibatı

### 1.1 Mənbə cədvəllərinin xam sayları

| Mənbə cədvəli | Sətir sayı |
|---|---|
| `balvereqi_logs` | 52,386 |
| `curricula` | 126 |
| `curricula_plan` | 3,424 |
| `departments` | 31 |
| `groups` | 766 |
| `imthngrscxsblr` | 12,544 |
| `journals` | 13,875 |
| `journals_dates_added_by_teacher` | 379,215 |
| `journals_dates_points` | 5,135,289 |
| `journals_dates_points_archive` | 776,033 |
| `lessons` | 2,521 |
| `speciality` | 83 |
| `students` | 7,816 |
| `workers` | 729 |
| `yekun` | 17,194 |

### 1.2 Struktur varlıqları — ledger möhürləri

Ledger hər mənbə sətri üçün bir möhür saxlayır: `migrated` / `skipped` /
`quarantined`.  «Mənbə sətri» sütunu bu hesabatın MÜSTƏQİL saydığı xam
sətir sayıdır: möhür cəmi ona bərabər olmalıdır, yoxsa sətir səssizcə
itib.

| Varlıq | Mənbə sətri | Möhür cəmi | Köçürülən | Ötürülən | Karantin | Tutur? |
|---|---|---|---|---|---|---|
| `academic_period` | — | 13 | 13 | 0 | 0 | — (törəmə varlıq) |
| `course_offering` | `journals` = 13,875 | 16,029 | 13,987 | 1,866 | 176 | 🔴 +2,154 |
| `curriculum_plan` | `curricula` = 126 | 126 | 125 | 0 | 1 | ✅ tutur |
| `curriculum_plan_row` | `curricula_plan` = 3,424 | 3,424 | 3,161 | 0 | 263 | ✅ tutur |
| `department_unit` | `departments` = 31 | 31 | 31 | 0 | 0 | ✅ tutur |
| `group_unit` | `groups` = 766 | 766 | 766 | 0 | 0 | ✅ tutur |
| `journal_components` | — | 11,238 | 9,443 | 1,794 | 1 | — (törəmə varlıq) |
| `journal_enrollment` | — | 199,454 | 183,771 | 15,576 | 107 | — (törəmə varlıq) |
| `journal_entry_scores` | — | 13,987 | 13,802 | 185 | 0 | — (törəmə varlıq) |
| `journal_finals` | — | 10,081 | 8,375 | 1,649 | 57 | — (törəmə varlıq) |
| `journal_lesson_meta` | — | 337,480 | 275,835 | 61,644 | 1 | — (törəmə varlıq) |
| `journal_lock` | — | 13,987 | 13,987 | 0 | 0 | — (törəmə varlıq) |
| `journal_mark_recovered` | — | 12,184 | 10,317 | 1,867 | 0 | — (törəmə varlıq) |
| `journal_marks` | — | 12,184 | 10,109 | 2,075 | 0 | — (törəmə varlıq) |
| `journal_reconcile` | `yekun` = 17,194 | 17,199 | 0 | 571 | 16,628 | 🔴 +1 |
| `journal_selfwork` | — | 11,861 | 10,156 | 1,705 | 0 | — (törəmə varlıq) |
| `legacy_excuse_document` | — | 2,964 | 2,964 | 0 | 0 | — (törəmə varlıq) |
| `legacy_grade_artifact` | — | 52,386 | 52,386 | 0 | 0 | — (törəmə varlıq) |
| `legacy_grade_fact` | — | 169,231 | 169,231 | 0 | 0 | — (törəmə varlıq) |
| `legacy_mark_conflict` | — | 1,762 | 1,762 | 0 | 0 | — (törəmə varlıq) |
| `legacy_mark_unresolved` | — | 87 | 87 | 0 | 0 | — (törəmə varlıq) |
| `legacy_room` | — | 158 | 158 | 0 | 0 | — (törəmə varlıq) |
| `lesson` | `journals_dates_added_by_teacher` = 379,215 | 440,124 | 293,070 | 146,992 | 62 | 🔴 +60,909 |
| `lesson_subject` | `lessons` = 2,521 | 2,521 | 2,521 | 0 | 0 | ✅ tutur |
| `lesson_synthesised` | — | 11,735 | 11,735 | 0 | 0 | — (törəmə varlıq) |
| `speciality_program` | — | 101 | 101 | 0 | 0 | — (törəmə varlıq) |
| `speciality_unit` | `speciality` = 83 | 83 | 83 | 0 | 0 | ✅ tutur |
| `student` | `students` = 7,816 | 7,816 | 7,816 | 0 | 0 | ✅ tutur |
| `student_placement` | — | 7,816 | 0 | 7,799 | 17 | — (törəmə varlıq) |
| `student_record` | — | 7,816 | 7,799 | 17 | 0 | — (törəmə varlıq) |
| `syllabus_document` | — | 8,262 | 7,049 | 1,213 | 0 | — (törəmə varlıq) |
| `worker` | `workers` = 729 | 729 | 729 | 0 | 0 | ✅ tutur |
| `worker_materialisation` | — | 729 | 729 | 0 | 0 | — (törəmə varlıq) |

### 1.3 Jurnal xanaları — mənbədən hədəfə nərdivan

Bu, hesabatın **ürəyidir**.  Hər pillə mənbə sayından nə qədər və NİYƏ
çıxıldığını göstərir; sonuncu sətir tutmayan qalığı açıq elan edir.

#### Təqvim xanaları (davamiyyət + gündəlik bal)

| Pillə | Dəyişiklik | Qalıq |
|---|---|---|
| Mənbə sətri (xam) | 5,070,824 |  |
| − boş xana (mənbədə dəyər yoxdur) | −7,355 | 5,063,469 |
| − oxunmayan xana (karantin) | −0 | 5,063,469 |
| − arxiv örtüşməsi (J-V7 kəsimindən sonra) | −654,399 | 4,409,070 |
| − dublikat xana (J-V4 uduzanları) | −2,986 | 4,406,084 |
| − orphan jurnal (açılış yaradılmayıb) | −261,523 | 4,144,561 |
| − həll olunmayan yazılış (tələbə jurnalda aktiv deyil) | −193,362 | 3,951,199 |
| − arxiv xanası canlı hədəf tərəfindən əvəzlənib (J-V7) | −1,259 | 3,949,940 |
| − dərs slotu MƏNBƏDƏ yoxdur (J12 bərpasının hədəfi) | −0 | 3,949,940 |
| − dərs slotu mənbədə VAR, hədəfdə materiallaşmayıb | −87 | 3,949,853 |
| − hədəf toqquşması — EYNİ dəyər (izahlı buraxılış, itki DEYİL) | −27,077 | 3,922,776 |
| − hədəf toqquşması — FƏRQLİ dəyər (uduzan dəyər sübuta yazılır) | −1,472 | 3,921,304 |
| **= Gözlənilən hədəf sətri** |  | **3,921,304** |
| **Hədəfdə FAKTİKİ** |  | **3,921,304** |
| ✅ **İZAH OLUNMAMIŞ FƏRQ** |  | **0** |

#### Komponent xanaları (kollokvium + sərbəst iş)

| Pillə | Dəyişiklik | Qalıq |
|---|---|---|
| Mənbə sətri (xam) | 701,005 |  |
| − boş xana (mənbədə dəyər yoxdur) | −630 | 700,375 |
| − oxunmayan xana (karantin) | −469 | 699,906 |
| − arxiv örtüşməsi (J-V7 kəsimindən sonra) | −99,423 | 600,483 |
| − dublikat xana (J-V4 uduzanları) | −1,960 | 598,523 |
| − orphan jurnal (açılış yaradılmayıb) | −34,861 | 563,662 |
| − həll olunmayan yazılış (tələbə jurnalda aktiv deyil) | −15,236 | 548,426 |
| − arxiv xanası canlı hədəf tərəfindən əvəzlənib (J-V7) | −49 | 548,377 |
| − hədəf toqquşması — EYNİ dəyər (izahlı buraxılış, itki DEYİL) | −2,040 | 546,337 |
| − hədəf toqquşması — FƏRQLİ dəyər (uduzan dəyər sübuta yazılır) | −290 | 546,047 |
| **= Gözlənilən hədəf sətri** |  | **546,047** |
| **Hədəfdə FAKTİKİ** |  | **546,047** |
| ✅ **İZAH OLUNMAMIŞ FƏRQ** |  | **0** |

#### İmtahan xanaları (im / im2)

| Pillə | Dəyişiklik | Qalıq |
|---|---|---|
| Mənbə sətri (xam) | 134,834 |  |
| − boş xana (mənbədə dəyər yoxdur) | −634 | 134,200 |
| − oxunmayan xana (karantin) | −507 | 133,693 |
| − arxiv örtüşməsi (J-V7 kəsimindən sonra) | −2,591 | 131,102 |
| − dublikat xana (J-V4 uduzanları) | −875 | 130,227 |
| − orphan jurnal (açılış yaradılmayıb) | −7,437 | 122,790 |
| − həll olunmayan yazılış (tələbə jurnalda aktiv deyil) | −1,706 | 121,084 |
| − arxiv xanası canlı hədəf tərəfindən əvəzlənib (J-V7) | −0 | 121,084 |
| − hədəf toqquşması — EYNİ dəyər (izahlı buraxılış, itki DEYİL) | −540 | 120,544 |
| − hədəf toqquşması — FƏRQLİ dəyər (uduzan dəyər sübuta yazılır) | −20 | 120,524 |
| **= Gözlənilən hədəf sətri** |  | **120,524** |
| **Hədəfdə FAKTİKİ** |  | **120,524** |
| ✅ **İZAH OLUNMAMIŞ FƏRQ** |  | **0** |

#### Yazı nərdivanının səbəb pillələri — nə ölçülüb

Bu pillələr ledger sayğacından DEYİL, mənbə xanalarının öz axınından
hesablanır: import-un `_decide()` qərarı oflayn təkrar icra olunur.
Ledger HADİSƏ sayır, nərdivan XANA sayır — fərq vacibdir, çünki
`classify_mark_write()` mövcud xanaya eyni dəyər gələndə `"written"`
qaytarır (ledger «yazıldı» görür), hədəfdə isə sətir YARANMIR.

Hədəfdən yalnız iki materiallaşmış xəritə oxunur (dərs slotları,
yazılış→açılış); üçüncü sübut — MƏNBƏNİN öz dərs indeksi
(`journals_dates_added_by_teacher`) — birbaşa mənbədən gəlir və
pilləni hədəfdən asılı olmadan ikiyə bölür.

**Pillə 1–2. Dərs slotu tapılmadı → İKİ AYRI SƏBƏB.**  `LessonMark` yalnız
mövcud `Lesson`-a bağlana bilər.  Xananın `(açılış, ay, gün, saat)` slotu
hədəfdə materiallaşmayıbsa xana yazılmır.  Sual: həmin dərs MƏNBƏDƏ varmı?

| Pillə | Xana | Pay | Bu nə deməkdir |
|---|---|---|---|
| **1.** dərs slotu MƏNBƏDƏ yoxdur (J12 bərpasının hədəfi) | **0** | 0.0 % | Mənbənin öz boşluğu — köçürmə qüsuru DEYİL.  J12 bərpası xananın öz `(ay, gün, saat)` açarından dərsi yaradır → bərpadan sonra bu pillə **0** olur. |
| **2.** dərs slotu mənbədə VAR, hədəfdə materiallaşmayıb | **87** | 100.0 % | Dərs sətri mənbədə VAR, hədəfə düşməyib.  Səbəb aşağıda ayrıca ölçülür — sətrin öz tarixi/saatı həqiqi təqvim anı deyilsə J3 dərs yarada bilmir. |
| **CƏMİ** | **87** |  |  |

İtən xananın NƏ DAŞIDIĞI (pillə üzrə) — «bal itdi» ilə «davamiyyət itdi»
eyni şey deyil:

| Pillə | Xananın məzmunu | Xana |
|---|---|---|
| dərs slotu mənbədə VAR, hədəfdə materiallaşmayıb | iştirak (`ie`) | 78 |
| dərs slotu mənbədə VAR, hədəfdə materiallaşmayıb | rəqəmli bal | 5 |
| dərs slotu mənbədə VAR, hədəfdə materiallaşmayıb | qayıb (`qb`) | 4 |

Təsirlənən jurnal (hər iki pillə birlikdə): **8**.
🔴 Rəqəmli bal daşıyan xanalar birmənalı **akademik data itkisidir**;
`qb` xanaları `Enrollment.absence_hours`-u aşağı göstərir.

**2-ci pillənin daxili bölgüsü** — dərs sətri mənbədə VAR, bəs niyə
hədəfdə dərs yoxdur?  J3 dərsi yalnız HƏQİQİ təqvim anından yarada bilir
(`parse_lesson_schedule`), ona görə bu pillə də adlandırılmış hallara bölünür:

| Alt-hal | Xana | Pay |
|---|---|---|
| tarix heç bir ildə mövcud deyil (31 aprel · 31 sentyabr · 31 noyabr · 30 fevral) | 86 | 98.9 % |
| 29 fevral — mənbədə İL sütunu yoxdur, uzun il olub-olmadığı bilinmir | 1 | 1.1 % |

✅ Bu pillədə **adsız qalıq YOXDUR**: hər xana mənbənin öz təqvim/saat səhvi ilə izah olunur — köçürmə qərarı deyil.

**1-ci pillənin proqnozu — bu hədəf nüsxəsində bərpa varmı?**

Bu nüsxədə J12 bərpası tətbiq olunub: **11,735** sintetik `Lesson`
(`is_legacy_synthesised`) və onlara bağlı **169,513** `LessonMark`.

✅ **Proqnoz TUTDU**: pillə 1 = **0** — mənbədə dərsi olmayan xanaların hamısı bərpa dərslərinə oturub.

**Pillə 3–4. Hədəf açarı toqquşması → İKİ AYRI SƏBƏB.**  J-V4 dedup açarı
`journal_uniqid`-i daxil edir, hədəf açarı isə etmir.  Bir neçə legacy
jurnal BİR açılışa birləşdiyi üçün (`legacy_journal_offering_merged`) iki
mənbə xanası eyni hədəf açarına düşür — ikincisi sətir yaratmır.  Uduzan
xananın dəyəri qalibin dəyəri ilə müqayisə olunur:

| Domen | Toqquşma | **3.** hədəf toqquşması — EYNİ dəyər (izahlı buraxılış, itki DEYİL) | 🔴 **4.** hədəf toqquşması — FƏRQLİ dəyər (uduzan dəyər sübuta yazılır) |
|---|---|---|---|
| Təqvim xanaları (davamiyyət + gündəlik bal) | 28,549 | 27,077 | **1,472** |
| Komponent xanaları (kollokvium + sərbəst iş) | 2,330 | 2,040 | **290** |
| İmtahan xanaları (im / im2) | 560 | 540 | **20** |
| **CƏMİ** | **31,439** | **29,657** | **1,782** |

**3-cü pillə (eyni dəyər)** — eyni fakt iki birləşən jurnalda qeyd olunub,
hədəfdə bir dəfə durur: dəyər QORUNUB, itki yoxdur.  Bu pillə nərdivanda
«izahlı buraxılış» kimi durur.

**4-cü pillə (fərqli dəyər)** — iki jurnal eyni tələbə üçün FƏRQLİ dəyər
saxlayır, hədəfə yalnız biri düşür.  Uduzan dəyər jurnal interfeysində
GÖRÜNMÜR; sübut qatında (`registrar_legacygradefact`) saxlanılır.

Təsirlənən jurnal: **804**.

**Bölgünün qeyri-müəyyənliyi — ölçülüb.**  Toqquşmanın ÜMUMİ sayı axın
sırasından asılı deyil, «eyni / fərqli» bölgüsü isə yalnız bir halda
asılıdır: eyni hədəf açarını ÜÇ və daha çox mənbə xanası iddia edəndə.
Belə xana: **1,055** (3.4 %).
Bu rəqəm 3-cü və 4-cü pillə arasında sürüşə biləcək MAKSİMUM xana sayıdır —
yəni bölgünün xəta payının yuxarı sərhədi.  Cəm heç bir halda dəyişmir.

#### Pillələr üst-üstə düşürmü — kəsişmənin ÖLÇÜSÜ

«Pillələr ayrıqdır» iddiası kodun quruluşuna (hər xana bir `continue`-da
bitir) söykənir, amma hesabat iddianı yoxlayır: hər bütövün öz
hissələrinə bərabərliyi AYRICA sayılır.

| Domen | Bütöv | Bütövün sayı | Hissələrin cəmi | Qalıq |
|---|---|---|---|---|
| Təqvim xanaları (davamiyyət + gündəlik bal) | `deduped` | 4,406,084 | 4,406,084 | ✅ 0 |
| Təqvim xanaları (davamiyyət + gündəlik bal) | `lesson_missing` | 87 | 87 | ✅ 0 |
| Təqvim xanaları (davamiyyət + gündəlik bal) | `collision` | 28,549 | 28,549 | ✅ 0 |
| Komponent xanaları (kollokvium + sərbəst iş) | `deduped` | 598,523 | 598,523 | ✅ 0 |
| Komponent xanaları (kollokvium + sərbəst iş) | `lesson_missing` | 0 | 0 | ✅ 0 |
| Komponent xanaları (kollokvium + sərbəst iş) | `collision` | 2,330 | 2,330 | ✅ 0 |
| İmtahan xanaları (im / im2) | `deduped` | 130,227 | 130,227 | ✅ 0 |
| İmtahan xanaları (im / im2) | `lesson_missing` | 0 | 0 | ✅ 0 |
| İmtahan xanaları (im / im2) | `collision` | 560 | 560 | ✅ 0 |

✅ Hər bütöv öz hissələrinin CƏMİNƏ bərabərdir → xana səviyyəsində pillələr AYRIQDIR: heç bir xana iki pilləyə düşmür, heç bir xana pilləsiz qalmır.

XANA səviyyəsində kəsişmə sıfır olsa da, eyni JURNAL və ya eyni YAZILIŞ
bir neçə pillədə görünə bilər.  Bu, ikiqat çıxılma DEYİL (say ikiqat
getmir), amma «pillələr müstəqil hadisələrdir» fərziyyəsini yalanlayır —
ona görə ölçülüb göstərilir:

| Pillə A | Pillə B | Ortaq jurnal | Ortaq yazılış |
|---|---|---|---|
| dərs slotu MƏNBƏDƏ yoxdur (J12 bərpasının hədəfi) | dərs slotu mənbədə VAR, hədəfdə materiallaşmayıb | 0 | 0 |
| dərs slotu MƏNBƏDƏ yoxdur (J12 bərpasının hədəfi) | hədəf toqquşması — EYNİ dəyər (izahlı buraxılış, itki DEYİL) | 0 | 0 |
| dərs slotu MƏNBƏDƏ yoxdur (J12 bərpasının hədəfi) | hədəf toqquşması — FƏRQLİ dəyər (uduzan dəyər sübuta yazılır) | 0 | 0 |
| dərs slotu mənbədə VAR, hədəfdə materiallaşmayıb | hədəf toqquşması — EYNİ dəyər (izahlı buraxılış, itki DEYİL) | 1 | 16 |
| dərs slotu mənbədə VAR, hədəfdə materiallaşmayıb | hədəf toqquşması — FƏRQLİ dəyər (uduzan dəyər sübuta yazılır) | 1 | 9 |
| hədəf toqquşması — EYNİ dəyər (izahlı buraxılış, itki DEYİL) | hədəf toqquşması — FƏRQLİ dəyər (uduzan dəyər sübuta yazılır) | 301 | 869 |

#### Qalan izahsız fərq haqqında

✅ Hər üç domen tam tutur — mənbənin hər xanası ya hədəfdədir, ya da
adlandırılmış səbəblə çıxılıb.

⚠️ Bu, «itki yoxdur» demək DEYİL.  Nərdivan xananın hədəfdə sətir
yaratmamasının SƏBƏBİNİ adlandırır; həmin səbəblərin bir hissəsi
(dərs slotu yoxdur · toqquşmada fərqli dəyər) HƏQİQİ DATA İTKİSİDİR —
yuxarıdakı «səbəb pillələri» bölməsinə bax.

Qapının hələ də mənası var: pillələr hədəfin sətir sayından ASILI OLMADAN
hesablanır (mənbə xanaları + mənbənin dərs indeksi + materiallaşmış
dərs/yazılış xəritələri), ona görə yazılması gözlənilən bir sətir hər hansı
başqa səbəbdən düşsə qalıq yenə açılır.

**Bərpadan sonra nə gözlənilir (yoxlanan proqnoz, fərziyyə deyil).**
1-ci pillə (`dərs slotu MƏNBƏDƏ yoxdur`) hazırda **0** xanadır.
J12 (`journal_lesson_recovery`) həmin dərsləri xananın öz `(ay, gün, saat)`
açarından yaradır, yəni bərpa tətbiq olunmuş bazada bu pillə **0** olmalıdır;
0 çıxmasa bərpa natamamdır və hesabat bunu dərhal göstərəcək.

**2-ci pillə** (`dərs slotu mənbədə VAR, hədəfdə yoxdur`) — **87** xana.
Bu, bərpa ilə bağlanmır; səbəbi §1.3-ün «2-ci pillənin daxili bölgüsü»
cədvəlində ölçülüb (təqvimdə mövcud olmayan tarix · divar saatı olmayan saat).

✅ Bu pillədə ADSIZ qalıq yoxdur — hər xana mənbənin öz təqvim/saat
səhvi ilə izah olunur.

#### ⚠️ Heç bir domenə düşməyən xanalar

Mənbədə **4,659** xananın `month_id` kodu nə təqvim ayı, nə
`k1/k2/k3/si`, nə də `im/im2`-dir.  İmport-un say balansı bu sətirləri
tamamilə kənarda saxlayır — bu hesabat onları GÖRÜNƏN edir.

Bu xanalar YUXARIDAKI üç nərdivanın heç birinə düşmür, amma **itmiş sayılmır**:
onların taleyi aşağıdakı «legacy qiymət faktları» bölməsində sətir-sətir
tutuşdurulur (`registrar_legacygradefact.raw_score_text`) — həmin uzlaşdırma
yalnız təqvim aylarını və `k1/k2/k3/si`-ni kənarda saxlayır, bu kodları YOX.

⚠️ Struktur qeyd: J5 komponent fazası yalnız `k1/k2/k3/si` kodlarını tanıyır,
ona görə bu xanalar `ComponentScore` kimi MATERİALLAŞMIR — dəyər sübut
cədvəlindədir, jurnal interfeysində görünmür.  Sahib qərar verməlidir.

## 2. Varlıq-varlıq müqayisə cədvəli

| Sahə | Mənbə | Hədəf | Fərq | İzah |
|---|---|---|---|---|
| Fakültə / kafedra (OrgUnit) | 31 | 13 | -18 | Legacy `departments` düz siyahıdır; hədəfdə fakültə/kafedra iyerarxiyasına yığılır — say azalır. |
| İxtisas (OrgUnit) | 83 | 83 | 0 | Bire-bir. |
| İxtisas proqramı (Program) | 83 | 101 | +18 | Bir ixtisas bakalavr/magistr üzrə ayrı proqrama bölünür → hədəfdə ÇOX olur. |
| Kurikulum (Curriculum) | 126 | 210 | +84 | Hədəfdə kurikulum (proqram + qəbul ili) cütünə görə açılır → say arta bilər. |
| Kurikulum fənni | 3,424 | 4,681 | +1,257 | Seçmə bloklar və istinad açılmaları sayı dəyişir (`legacy_plan_*` problem kodlarına bax). |
| Fənn (Subject) | 2,521 | 2,501 | -20 | Eyni adlı legacy fənlər bir Subject-ə birləşə bilər → hədəfdə az olur. |
| Qrup (OrgUnit) | 766 | 766 | 0 | Bire-bir. |
| Tələbə (auth.user) | 7,816 | 8,545 | +729 | Hədəfə müəllim/işçi hesabları da daxildir — aşağıdakı rol cədvəlinə bax. |
| Müəllim / işçi | 729 | — | — | Rol cədvəlində ayrıca görünür. |
| Jurnal → açılış (CourseOffering) | 13,875 | 11,115 | -2,760 | ⚠️ Gözləntinin ƏKSİ: eyni fənn+qrup+dövr üçün bir neçə legacy jurnal BİR açılışa BİRLƏŞİR (`legacy_journal_offering_merged`) → hədəfdə AZ olur, çox yox. |
| Dərs (Lesson) | 379,215 | 304,805 | -74,410 | Eyni slot üçün bir neçə müəllim sətri bir dərsə düşür (`legacy_journal_lesson_duplicate`) → hədəfdə az olur. |
| Yekun cədvəli (`yekun`) | 17,194 | 115,403 | +98,209 | Hədəfdə FinalGrade jurnalın `im` xanasından da doğur — `yekun` cədvəli yeganə mənbə deyil. |
| Təqvim xanaları (davamiyyət + gündəlik bal) | 5,070,824 | 3,921,304 | -1,149,520 | Nərdivan üçün §1.3-ə bax. |
| Komponent xanaları (kollokvium + sərbəst iş) | 701,005 | 546,047 | -154,958 | Nərdivan üçün §1.3-ə bax. |
| İmtahan xanaları (im / im2) | 134,834 | 120,524 | -14,310 | Nərdivan üçün §1.3-ə bax. |

### Hədəf tərəfdə rol üzrə üzvlüklər

Məzun / qeyri-aktiv tələbələr **arxiv üzvlüyü** kimi köçür — hesabdan silinmir,
sadəcə `is_active = false` olur.

| Rol | Aktiv üzvlük | Arxiv (qeyri-aktiv) |
|---|---|---|
| `student` | 7,599 | 17 |
| `teacher` | 729 | 0 |
| `alumni` | 200 | 0 |

## 3. Nümunə-yoxlama — 20 təsadüfi tələbə

Seçim toxumu: `random.Random(20260827)` — **təkrarlana biləndir**:
eyni əmr hər dəfə eyni 20 nəfəri göstərir.

Nümunə **bərabər bölünüb**: yarısı yazılışı köçən, yarısı köçməyən tələbədən.
Sırf təsadüfi seçim bu datada demək olar ki, həmişə arxiv tələbələrini gətirir
və «heç nə köçməyib» mənzərəsi yaradır; bərabər bölgü hər iki tərəfi göstərir —
köçən datanın xana-bəxana düzgünlüyünü VƏ köçməyənin miqyasını.

Hər fənn üçün iki sətir var: `köhnə` (MyEdu xanalarından yenidən hesablanmış)
və `yeni` (EMS Arena cədvəllərindən).  Sağ sütun: ✅ = tutur, 🔴 = fərq var,
`↔ birləşmə` = bu legacy jurnal başqa bir jurnalla EYNİ açılışa birləşib
(«yeni» sütunu birləşmiş nəticəni göstərir, ona görə ayrıca müqayisə olunmur).
«Giriş balı» və «Yekun» sütunlarında `—` o deməkdir ki, legacy `yekun`
cədvəlində bu fənn üçün sətir yoxdur — bu, uyğunsuzluq DEYİL.
Paylaşım təhlükəsizliyi üçün adlar, legacy identifikatorları, hədəf user ID-ləri
və qrup/proqram dəyərləri göstərilmir; nümunələr deterministik sıra etiketi ilə verilir.

### Nümunənin bir baxışda mənzərəsi

| Nümunə | Üzvlük | Fənn (köçən/cəmi) | Nəticə |
|---|---|---|---|
| Nümunə 01 | aktiv | 13/27 | ⚠️ 13/27 fənn köçüb |
| Nümunə 02 | aktiv | 15/15 | ✅ bütün fənlər köçüb |
| Nümunə 03 | aktiv | 0/0 | — jurnal xanası yoxdur |
| Nümunə 04 | aktiv | 8/14 | ⚠️ 8/14 fənn köçüb |
| Nümunə 05 | aktiv | 34/39 | ⚠️ 34/39 fənn köçüb |
| Nümunə 06 | aktiv | 0/3 | 🔴 heç bir fənn köçməyib |
| Nümunə 07 | aktiv | 15/15 | ✅ bütün fənlər köçüb |
| Nümunə 08 | aktiv | 22/24 | ⚠️ 22/24 fənn köçüb |
| Nümunə 09 | aktiv | 50/72 | ⚠️ 50/72 fənn köçüb |
| Nümunə 10 | aktiv | 0/0 | — jurnal xanası yoxdur |
| Nümunə 11 | aktiv | 26/32 | ⚠️ 26/32 fənn köçüb |
| Nümunə 12 | aktiv | 0/0 | — jurnal xanası yoxdur |
| Nümunə 13 | aktiv | 0/0 | — jurnal xanası yoxdur |
| Nümunə 14 | aktiv | 0/0 | — jurnal xanası yoxdur |
| Nümunə 15 | aktiv | 0/0 | — jurnal xanası yoxdur |
| Nümunə 16 | aktiv | 45/45 | ✅ bütün fənlər köçüb |
| Nümunə 17 | aktiv | 0/0 | — jurnal xanası yoxdur |
| Nümunə 18 | aktiv | 0/0 | — jurnal xanası yoxdur |
| Nümunə 19 | aktiv | 0/0 | — jurnal xanası yoxdur |
| Nümunə 20 | aktiv | 13/15 | ⚠️ 13/15 fənn köçüb |

### Nümunə 01

| Yoxlama | Nəticə |
|---|---|
| Ad/soyad uyğunluğu | ✅ uyğun |
| Qrup uyğunluğu | ✅ uyğun |
| İxtisas/proqram uyğunluğu | ✅ uyğun |
| Hədəf statusu | enrolled (aktiv üzvlük) |

| Fənn | Tərəf | Qayıb | Seminar bal | Kollokvium | Sərbəst iş | İmtahan | Giriş balı | Yekun | ⚑ |
|---|---|---|---|---|---|---|---|---|---|
| Sənədləşmə və terminologiya | köhnə | 1 | 60 | 30 | 10 | 27 | — | — | ✅ |
|  | yeni | 1 | 60 | 30 | 10 | 27 | 50 | 77 |  |
| Yazılı mətnin şifahi tərcüməsi | köhnə | 2 | 60 | 30 | 10 | 48 | 49 | 97 | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| KİV tərcüməsi | köhnə | 0 | 24 | 20 | 9 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Linqokulturologiya | köhnə | 4 | 57 | 30 | 10 | 42 | — | — | ✅ |
|  | yeni | 4 | 57 | 30 | 10 | 42 | 50 | 92 |  |
| II Xarici dil-1 | köhnə | 0 | 8 | 0 | 0 | — | — | — | ✅ |
|  | yeni | 0 | 8 | 0 | 0 | — | 8 | 8 |  |
| Xarici dildə işgüzar və akademik kommunikasiya -3 | köhnə | 1 | 19 | 27 | 10 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Akademik yazı | köhnə | 2 | 25 | 23 | 10 | 46 | 43 | 89 | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Ekologiya sahəsi üzrə tərcümə | köhnə | 5 | 29 | 27 | 10 | 43 | — | — | ✅ |
|  | yeni | 5 | 29 | 27 | 10 | 43 | 50 | 93 |  |
| Peşəkar tərcümənin əsasları | köhnə | 0 | 24 | 24 | 10 | — | — | — | ✅ |
|  | yeni | 0 | 24 | 24 | 10 | — | 48 | 48 |  |
| II xarici dil - Alman dili | köhnə | 2 | 35 | 29 | 10 | 37 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Hüquqi tərcümə | köhnə | 4 | 28 | 27 | 10 | 46 | — | — | ✅ |
|  | yeni | 4 | 28 | 27 | 10 | 46 | 50 | 96 |  |
| Xarici dil-2 | köhnə | 2 | 30 | 29 | 10 | 28 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Tərcümə nəzəriyyəsi | köhnə | 0 | 20 | 30 | 10 | 40 | — | — | ✅ |
|  | yeni | 0 | 20 | 30 | 10 | 40 | 50 | 90 |  |
| Kargüzarlığın təşkili və yazı texnikası | köhnə | 0 | 21 | 26 | 10 | 23 | 44 | 67 | ↔ birləşmə |
|  | yeni | 1 | 21 | 26 | 10 | 23 | 47 | 70 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Akademik yazı | köhnə | 0 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| İnsan haqları hüququ | köhnə | 1 | 18 | 25 | 10 | — | — | — | ✅ |
|  | yeni | 1 | 18 | 25 | 10 | — | 43 | 43 |  |
| Şifahi tərcümə | köhnə | 0 | 37 | 28 | 10 | 43 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| İnformasiya texnologiyaları | köhnə | 0 | 14 | 23 | 9 | 41 | — | — | ✅ |
|  | yeni | 0 | 14 | 23 | 9 | 41 | 37 | 78 |  |
| Yazılı tərcümə -2 | köhnə | 1 | 30 | 23 | 10 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Ardıcıl tərcümə və qeydgötürmə texnikası | köhnə | 2 | 87 | 29 | 10 | 45 | — | — | ✅ |
|  | yeni | 2 | 87 | 29 | 10 | 45 | 50 | 95 |  |
| İqtisadi tərcümə | köhnə | 0 | 19 | 30 | 10 | 45 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| İdiomatik ingilis dili | köhnə | 1 | 28 | 25 | 10 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Tərcümə və mədəniyyətlərarası ünsiyyət | köhnə | 0 | 20 | 27 | 10 | 43 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Kargüzarlığın təşkili və yazı texnikası | köhnə | 1 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 1 | 21 | 26 | 10 | 23 | 47 | 70 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Kompüter tərcümə proqramları | köhnə | 0 | 75 | 24 | 8 | 35 | 43 | 78 | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Tərcümə və müqayisəli üslubiyyət | köhnə | 0 | 30 | 30 | 10 | 49 | — | — | ✅ |
|  | yeni | 0 | 30 | 30 | 10 | 49 | 50 | 99 |  |
| Müxtəlif mədəni kontekstlərin tərcüməsi | köhnə | 2 | 59 | 27 | 10 | 42 | 48 | 90 | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |

### Nümunə 02

| Yoxlama | Nəticə |
|---|---|
| Ad/soyad uyğunluğu | ✅ uyğun |
| Qrup uyğunluğu | ✅ uyğun |
| İxtisas/proqram uyğunluğu | ✅ uyğun |
| Hədəf statusu | enrolled (aktiv üzvlük) |

| Fənn | Tərəf | Qayıb | Seminar bal | Kollokvium | Sərbəst iş | İmtahan | Giriş balı | Yekun | ⚑ |
|---|---|---|---|---|---|---|---|---|---|
| Marketinq kanalları | köhnə | 1 | 0 | 24 | 9 | 31 | — | — | ✅ |
|  | yeni | 1 | 0 | 24 | 9 | 31 | 24 | 55 |  |
| Riyazi məntiqi məsələlər | köhnə | 0 | 6 | 18 | 5 | 24 | — | — | ✅ |
|  | yeni | 0 | 6 | 18 | 5 | 24 | 24 | 48 |  |
| Marketinq tədqiqatları | köhnə | 0 | 0 | 24 | 10 | 18 | 44 | 62 | 🔴 |
|  | yeni | 0 | 0 | 24 | 10 | 18 | 24 | 42 |  |
| Logistika | köhnə | 0 | 0 | 30 | 10 | 23 | — | — | ✅ |
|  | yeni | 0 | 0 | 30 | 10 | 23 | 30 | 53 |  |
| İnsan resurslarının idarə edilməsi | köhnə | 0 | 0 | 21 | 9 | 20 | — | — | ✅ |
|  | yeni | 0 | 0 | 21 | 9 | 20 | 21 | 41 |  |
| İşgüzar yazışmalar | köhnə | 0 | 0 | 0 | 0 | 23 | 28 | 51 | ↔ birləşmə |
|  | yeni | 0 | 8 | 4 | 6 | 23 | 12 | 35 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| İstehsal sahələrinin marketinqi | köhnə | 0 | 0 | 24 | 9 | 12 | 43 | 55 | 🔴 |
|  | yeni | 0 | 0 | 24 | 9 | 22 | 24 | 46 |  |
| İşgüzar yazışmalar | köhnə | 0 | 8 | 4 | 6 | 23 | 28 | 51 | ↔ birləşmə |
|  | yeni | 0 | 8 | 4 | 6 | 23 | 12 | 35 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Vergilər və vergitutma | köhnə | 0 | 12 | 22 | 8 | 29 | — | — | ✅ |
|  | yeni | 0 | 12 | 22 | 8 | 29 | 34 | 63 |  |
| Marketinqin kommunikasiya sistemi | köhnə | 0 | 0 | 25 | 10 | 28 | — | — | ✅ |
|  | yeni | 0 | 0 | 25 | 10 | 28 | 25 | 53 |  |
| Marketinq menecmenti | köhnə | 0 | 0 | 24 | 9 | 20 | — | — | ✅ |
|  | yeni | 0 | 0 | 24 | 9 | 20 | 24 | 44 |  |
| Ətraf mühitin iqtisadiyyati | köhnə | 1 | 7 | 21 | 7 | 8 | 37 | 45 | 🔴 |
|  | yeni | 1 | 7 | 21 | 7 | 21 | 28 | 49 |  |
| İqtisadiyyatın tənzimlənməsi | köhnə | 2 | 0 | 12 | 8 | 8 | 28 | 36 | 🔴 |
|  | yeni | 2 | 0 | 12 | 8 | 8 | 12 | 20 |  |
| İctimaiyyətlə əlaqələr | köhnə | 1 | 0 | 24 | 10 | 27 | — | — | ✅ |
|  | yeni | 1 | 0 | 24 | 10 | 27 | 24 | 51 |  |
| Beynelxalq marketinq | köhnə | 0 | 0 | 23 | 10 | 23 | — | — | ✅ |
|  | yeni | 0 | 0 | 23 | 10 | 23 | 23 | 46 |  |

### Nümunə 03

| Yoxlama | Nəticə |
|---|---|
| Ad/soyad uyğunluğu | ✅ uyğun |
| Qrup uyğunluğu | ✅ uyğun |
| İxtisas/proqram uyğunluğu | ✅ uyğun |
| Hədəf statusu | enrolled (aktiv üzvlük) |

> Bu tələbə üçün jurnal xanası tapılmadı.

### Nümunə 04

| Yoxlama | Nəticə |
|---|---|
| Ad/soyad uyğunluğu | ✅ uyğun |
| Qrup uyğunluğu | ✅ uyğun |
| İxtisas/proqram uyğunluğu | ✅ uyğun |
| Hədəf statusu | enrolled (aktiv üzvlük) |

| Fənn | Tərəf | Qayıb | Seminar bal | Kollokvium | Sərbəst iş | İmtahan | Giriş balı | Yekun | ⚑ |
|---|---|---|---|---|---|---|---|---|---|
| Qafqaz bölgəsində İlham Əliyevin transmilli layihələrinin həyata keçirilməsində rolu | köhnə | 11 | 8 | 6 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Psixologiya | köhnə | 2 | 0 | 14 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Qafqaz xalqları tarixi | köhnə | 0 | 30 | 23 | 9 | 32 | 42 | 84 | ↔ birləşmə |
|  | yeni | 2 | 64 | 24 | 9 | 42 | 50 | 92 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Tarix elminin müasir problemləri | köhnə | 2 | 0 | 24 | 8 | 34 | 41 | 75 | 🔴 |
|  | yeni | 2 | 0 | 24 | 8 | 34 | 24 | 58 |  |
| İqtisadiyyat | köhnə | 0 | 10 | 29 | 9 | 24 | 48 | 72 | 🔴 |
|  | yeni | 0 | 10 | 29 | 9 | 24 | 39 | 63 |  |
| Dinlər tarixi | köhnə | 1 | 8 | 23 | 8 | 32 | 41 | 73 | 🔴 |
|  | yeni | 1 | 8 | 23 | 8 | 32 | 31 | 63 |  |
| Tarixin tədrisi metodologiyası və metodikası | köhnə | 1 | 0 | 16 | 8 | 30 | 33 | 63 | 🔴 |
|  | yeni | 1 | 0 | 16 | 8 | 30 | 16 | 46 |  |
| Qafqaz xalqlarına qarşı erməni soyqırımları | köhnə | 8 | 15 | 8 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Qafqaz xalqları intibah dövründə (IX-XII əsrlər ) | köhnə | 8 | 0 | 21 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Ali məktəb pedaqogikası | köhnə | 2 | 0 | 15 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Xarici dil | köhnə | 4 | 45 | 27 | 10 | 39 | 45 | 84 | 🔴 |
|  | yeni | 4 | 45 | 27 | 10 | 39 | 50 | 89 |  |
| 1917-1920 -ci illərdə Qafqaz xalqlarının ictimai -siyasi vəziyyəti | köhnə | 2 | 31 | 23 | 8 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| 1917-1920 -ci illərdə Qafqaz xalqlarının ictimai -siyasi vəziyyəti | köhnə | 0 | 0 | 0 | 0 | — | — | — | ✅ |
|  | yeni | 0 | 0 | 0 | 0 | — | 0 | 0 |  |
| Qafqaz xalqları tarixi | köhnə | 2 | 34 | 26 | 7 | 42 | 42 | 84 | ↔ birləşmə |
|  | yeni | 2 | 64 | 24 | 9 | 42 | 50 | 92 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |

### Nümunə 05

| Yoxlama | Nəticə |
|---|---|
| Ad/soyad uyğunluğu | ✅ uyğun |
| Qrup uyğunluğu | ✅ uyğun |
| İxtisas/proqram uyğunluğu | ✅ uyğun |
| Hədəf statusu | enrolled (aktiv üzvlük) |

| Fənn | Tərəf | Qayıb | Seminar bal | Kollokvium | Sərbəst iş | İmtahan | Giriş balı | Yekun | ⚑ |
|---|---|---|---|---|---|---|---|---|---|
| informasiya təhlükəsizliyinin idarəedilməsi sistemləri | köhnə | 7 | 0 | 23 | 9 | 37 | — | — | ✅ |
|  | yeni | 7 | 0 | 23 | 9 | 37 | 23 | 60 |  |
| C proqramlaşdırma dili | köhnə | 5 | 0 | 22 | 8 | 29 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Mobil və Simsiz avadanlıqların təhlükəsizliyi | köhnə | 1 | 0 | 21 | 10 | 35 | — | — | ✅ |
|  | yeni | 1 | 0 | 21 | 10 | 35 | 21 | 56 |  |
| Xarici dildə işgüzar və akademik kommunikasiya | köhnə | 0 | 36 | 24 | 8 | — | — | — | ✅ |
|  | yeni | 0 | 36 | 24 | 8 | — | 50 | 50 |  |
| Elektronikanın əsasları və İOT təhlükəsizliyi | köhnə | 5 | 0 | 22 | 10 | 30 | — | — | ✅ |
|  | yeni | 5 | 0 | 22 | 10 | 30 | 22 | 52 |  |
| Sistem dizaynı | köhnə | 1 | 7 | 28 | 0 | — | — | — | ✅ |
|  | yeni | 1 | 7 | 28 | 0 | — | 35 | 35 |  |
| Şəbəkələrin əsasları | köhnə | 8 | 17 | 21 | 9 | 17 | — | — | ✅ |
|  | yeni | 8 | 17 | 21 | 9 | 17 | 38 | 55 |  |
| verilənlər bazasının təhlükəsizliyi | köhnə | 6 | 9 | 23 | 9 | 46 | — | — | ✅ |
|  | yeni | 6 | 9 | 23 | 9 | 46 | 32 | 78 |  |
| Azərbaycan dilində işgüzar və akademik kommunikasiya | köhnə | 3 | 7 | 19 | 8 | 32 | — | — | ✅ |
|  | yeni | 3 | 7 | 19 | 8 | 32 | 26 | 58 |  |
| İnformasiya təhlükəsizliyinin əsasları | köhnə | 4 | 38 | 28 | 9 | 46 | — | — | ✅ |
|  | yeni | 4 | 38 | 28 | 9 | 46 | 50 | 96 |  |
| Kriptoqrafiyanın əsasları | köhnə | 4 | 37 | 18 | 10 | 31 | — | — | ↔ birləşmə |
|  | yeni | 6 | 37 | 18 | 10 | 31 | 50 | 81 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Tətbiqi statistika və data analitikası | köhnə | 5 | 9 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 5 | 9 | 20 | 10 | 33 | 29 | 62 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Diskret riyaziyyat | köhnə | 4 | 8 | 24 | 9 | 35 | — | — | ↔ birləşmə |
|  | yeni | 4 | 16 | 24 | 9 | 35 | 40 | 75 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Ehtimal nəzəriyyəsi | köhnə | 4 | 8 | 20 | 10 | 31 | — | — | ✅ |
|  | yeni | 4 | 8 | 20 | 10 | 31 | 28 | 59 |  |
| Kiber risklərin idarə olunması | köhnə | 6 | 9 | 25 | 10 | 45 | — | — | ✅ |
|  | yeni | 6 | 9 | 25 | 10 | 45 | 34 | 79 |  |
| Əməliyyat sistemləri | köhnə | 6 | 8 | 26 | 10 | 43 | — | — | ✅ |
|  | yeni | 6 | 8 | 26 | 10 | 43 | 34 | 77 |  |
| Sahibkarlığın əsasları və biznesə giriş | köhnə | 1 | 0 | 19 | 9 | 22 | — | — | ✅ |
|  | yeni | 1 | 0 | 19 | 9 | 22 | 19 | 41 |  |
| Kriptoqrafiyanın əsasları | köhnə | 2 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 6 | 37 | 18 | 10 | 31 | 50 | 81 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Diskret riyaziyyat | köhnə | 0 | 8 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 4 | 16 | 24 | 9 | 35 | 40 | 75 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Bulud təhlükəsizliyi | köhnə | 6 | 0 | 21 | 9 | 40 | — | — | ✅ |
|  | yeni | 6 | 0 | 21 | 9 | 40 | 21 | 61 |  |
| Azərbaycan tarixi | köhnə | 3 | 19 | 20 | 7 | 37 | — | — | ✅ |
|  | yeni | 3 | 19 | 20 | 7 | 37 | 39 | 76 |  |
| Psixologiya | köhnə | 2 | 7 | 17 | 7 | 30 | — | — | ✅ |
|  | yeni | 2 | 7 | 17 | 7 | 30 | 24 | 54 |  |
| Veb təhlükəsizliyi | köhnə | 0 | 0 | 0 | 0 | — | — | — | ✅ |
|  | yeni | 0 | 0 | 0 | 0 | — | 0 | 0 |  |
| Xarici dildə işgüzar və akademik kommunikasiya | köhnə | 10 | 17 | 8 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 15 | 44 | 24 | 10 | — | 50 | 50 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Kibertəhlükəsizliyin əsasları | köhnə | 4 | 10 | 30 | 10 | 42 | — | — | ✅ |
|  | yeni | 4 | 10 | 30 | 10 | 42 | 40 | 82 |  |
| Zərərverici proqram vasitələrinin təhlili | köhnə | 2 | 16 | 23 | 10 | 36 | — | — | ✅ |
|  | yeni | 2 | 16 | 23 | 10 | 36 | 39 | 75 |  |
| Proqramlaşdırmanın əsasları | köhnə | 1 | 36 | 17 | 10 | 37 | — | — | ✅ |
|  | yeni | 1 | 36 | 17 | 10 | 37 | 50 | 87 |  |
| Mülki müdafiə | köhnə | 1 | 7 | 16 | 8 | 34 | — | — | ✅ |
|  | yeni | 1 | 7 | 16 | 8 | 34 | 23 | 57 |  |
| Sistem dizaynı | köhnə | 0 | 0 | 0 | 10 | 45 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Nüfuzetmə siqnallarının əsasları | köhnə | 4 | 18 | 23 | 10 | 45 | — | — | ✅ |
|  | yeni | 4 | 18 | 23 | 10 | 45 | 41 | 86 |  |
| şəbəkələrin təhlükəsizliyi | köhnə | 4 | 19 | 27 | 10 | 41 | — | — | ✅ |
|  | yeni | 4 | 19 | 27 | 10 | 41 | 46 | 87 |  |
| Riyazi analiz | köhnə | 3 | 19 | 21 | 6 | 4 | — | — | ✅ |
|  | yeni | 3 | 19 | 21 | 6 | 4 | 40 | 44 |  |
| Veb təhlükəsizliyi | köhnə | 3 | 0 | 25 | 8 | 41 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Xarici dildə işgüzar və akademik kommunikasiya | köhnə | 5 | 27 | 16 | 10 | — | — | — | ↔ birləşmə |
|  | yeni | 15 | 44 | 24 | 10 | — | 50 | 50 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| İT layihələrin idarəedilməsi | köhnə | 6 | 0 | 26 | 10 | 49 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Xətti cəbr | köhnə | 7 | 23 | 17 | 9 | 23 | — | — | ✅ |
|  | yeni | 7 | 23 | 17 | 9 | 23 | 40 | 63 |  |
| Tətbiqi statistika və data analitikası | köhnə | 0 | 0 | 20 | 10 | 33 | — | — | ↔ birləşmə |
|  | yeni | 5 | 9 | 20 | 10 | 33 | 29 | 62 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Sosial mühəndislik | köhnə | 2 | 15 | 18 | 10 | 31 | — | — | ✅ |
|  | yeni | 2 | 15 | 18 | 10 | 31 | 33 | 64 |  |
| informasiya təhlükəsizliyi və kibertəhlükəsizliyin hüquqi aspektləri | köhnə | 5 | 26 | 27 | 10 | 47 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |

### Nümunə 06

| Yoxlama | Nəticə |
|---|---|
| Ad/soyad uyğunluğu | ✅ uyğun |
| Qrup uyğunluğu | ✅ uyğun |
| İxtisas/proqram uyğunluğu | ✅ uyğun |
| Hədəf statusu | enrolled (aktiv üzvlük) |

| Fənn | Tərəf | Qayıb | Seminar bal | Kollokvium | Sərbəst iş | İmtahan | Giriş balı | Yekun | ⚑ |
|---|---|---|---|---|---|---|---|---|---|
| Azərbaycan coğrafiyası | köhnə | 0 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Turizmə giriş | köhnə | 0 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Azərbaycan tarixi | köhnə | 0 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |

### Nümunə 07

| Yoxlama | Nəticə |
|---|---|
| Ad/soyad uyğunluğu | ✅ uyğun |
| Qrup uyğunluğu | ✅ uyğun |
| İxtisas/proqram uyğunluğu | ✅ uyğun |
| Hədəf statusu | enrolled (aktiv üzvlük) |

| Fənn | Tərəf | Qayıb | Seminar bal | Kollokvium | Sərbəst iş | İmtahan | Giriş balı | Yekun | ⚑ |
|---|---|---|---|---|---|---|---|---|---|
| Sahibkarlığın əsasları | köhnə | 8 | 0 | 0 | 0 | — | — | — | ✅ |
|  | yeni | 8 | 0 | 0 | 0 | — | 0 | 0 |  |
| Makroiqtisadiyyat | köhnə | 19 | 0 | 0 | 0 | — | — | — | ✅ |
|  | yeni | 19 | 0 | 0 | 0 | — | 0 | 0 |  |
| Ehtimal nəzəriyyəsi və riyazi statistika | köhnə | 15 | 0 | 0 | 0 | — | — | — | ✅ |
|  | yeni | 15 | 0 | 0 | 0 | — | 0 | 0 |  |
| Xətti cəbr və riyazi analiz | köhnə | 2 | 7 | 16 | 8 | 3 | — | — | ✅ |
|  | yeni | 2 | 7 | 16 | 8 | 3 | 23 | 26 |  |
| Xarici dildə işgüzar və akademik kommunikasiya-2 | köhnə | 2 | 21 | 21 | 8 | 17 | — | — | ✅ |
|  | yeni | 2 | 21 | 21 | 8 | 17 | 42 | 59 |  |
| Statistika | köhnə | 20 | 0 | 0 | 0 | — | — | — | ✅ |
|  | yeni | 20 | 0 | 0 | 0 | — | 0 | 0 |  |
| Azərbaycan tarixi | köhnə | 0 | 0 | 21 | 8 | 16 | — | — | ✅ |
|  | yeni | 0 | 0 | 21 | 8 | 16 | 21 | 37 |  |
| Mikroiqtisadiyyat | köhnə | 20 | 0 | 0 | 0 | — | — | — | ✅ |
|  | yeni | 20 | 0 | 0 | 0 | — | 0 | 0 |  |
| Müəssisənin (firmanın) iqtisadiyyatı | köhnə | 0 | 0 | 21 | 7 | 0 | — | — | ✅ |
|  | yeni | 0 | 0 | 21 | 7 | 0 | 21 | 21 |  |
| Azərbaycan iqtisadiyyatı | köhnə | 0 | 13 | 18 | 7 | 14 | — | — | ✅ |
|  | yeni | 0 | 13 | 18 | 7 | 14 | 31 | 45 |  |
| İqtisadiyyata giriş | köhnə | 0 | 8 | 19 | 8 | — | — | — | ✅ |
|  | yeni | 0 | 8 | 19 | 8 | — | 27 | 27 |  |
| Sosiologiya | köhnə | 5 | 0 | 0 | 0 | — | — | — | ✅ |
|  | yeni | 5 | 0 | 0 | 0 | — | 0 | 0 |  |
| Azərbaycan dilində işgüzar və akademik kommunikasiya | köhnə | 1 | 0 | 20 | 7 | 15 | — | — | ✅ |
|  | yeni | 1 | 0 | 20 | 7 | 15 | 20 | 35 |  |
| Azərbaycanın iqtisadi inkişafının perspektivləri | köhnə | 4 | 0 | 0 | 0 | — | — | — | ✅ |
|  | yeni | 4 | 0 | 0 | 0 | — | 0 | 0 |  |
| Xarici dildə işgüzar və akademik kommunikasiya-1 | köhnə | 0 | 19 | 21 | 8 | 34 | — | — | ✅ |
|  | yeni | 0 | 19 | 21 | 8 | 34 | 40 | 74 |  |

### Nümunə 08

| Yoxlama | Nəticə |
|---|---|
| Ad/soyad uyğunluğu | ✅ uyğun |
| Qrup uyğunluğu | ✅ uyğun |
| İxtisas/proqram uyğunluğu | ✅ uyğun |
| Hədəf statusu | enrolled (aktiv üzvlük) |

| Fənn | Tərəf | Qayıb | Seminar bal | Kollokvium | Sərbəst iş | İmtahan | Giriş balı | Yekun | ⚑ |
|---|---|---|---|---|---|---|---|---|---|
| Kibertəhlükəsizliyin təmin edilməsi yolları | köhnə | 0 | 0 | 23 | 7 | 50 | — | — | ✅ |
|  | yeni | 0 | 0 | 23 | 7 | 50 | 23 | 73 |  |
| Diferensial tənliklər | köhnə | 0 | 9 | 27 | 10 | 17 | — | — | ✅ |
|  | yeni | 0 | 9 | 27 | 10 | 17 | 36 | 53 |  |
| Mülki müdafiə | köhnə | 1 | 13 | 14 | 7 | 17 | — | — | 🔴 |
|  | yeni | 1 | 13 | 14 | 7 | 24 | 27 | 51 |  |
| Fizika | köhnə | 1 | 23 | 21 | 9 | 4 | — | — | 🔴 |
|  | yeni | 1 | 23 | 21 | 9 | 17 | 44 | 61 |  |
| Kompüter arxitekturası | köhnə | 2 | 7 | 23 | 10 | 17 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Xarici dildə işgüzar və akademik kommunikasiya | köhnə | 3 | 93 | 23 | 9 | — | — | — | 🔴 |
|  | yeni | 2 | 93 | 23 | 9 | — | 50 | 50 |  |
| Sxemotexnikanın əsasları | köhnə | 3 | 10 | 28 | 9 | 19 | — | — | ✅ |
|  | yeni | 3 | 10 | 28 | 9 | 19 | 38 | 57 |  |
| Verilənlərin strukturu və alqoritmlər | köhnə | 0 | 8 | 24 | 8 | — | — | — | ✅ |
|  | yeni | 0 | 8 | 24 | 8 | — | 32 | 32 |  |
| Ehtimal nəzəriyyəsi və riyazi statistika | köhnə | 0 | 14 | 22 | 5 | 3 | — | — | ✅ |
|  | yeni | 0 | 14 | 22 | 5 | 3 | 36 | 39 |  |
| Azərbaycan tarixi | köhnə | 1 | 17 | 30 | 10 | 30 | — | — | ✅ |
|  | yeni | 1 | 17 | 30 | 10 | 30 | 47 | 77 |  |
| Etika və estetika | köhnə | 2 | 8 | 11 | 8 | 21 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Əməliyyat sistemləri | köhnə | 4 | 36 | 28 | 10 | 32 | — | — | ✅ |
|  | yeni | 4 | 36 | 28 | 10 | 32 | 50 | 82 |  |
| Xarici dildə işgüzar akademik kommunikasiya-2(pre-intermediate) | köhnə | 3 | 19 | 21 | 10 | — | — | — | ✅ |
|  | yeni | 3 | 19 | 21 | 10 | — | 40 | 40 |  |
| Proqramlaşdırmanın əsasları | köhnə | 6 | 21 | 21 | 8 | 22 | — | — | ✅ |
|  | yeni | 6 | 21 | 21 | 8 | 22 | 42 | 64 |  |
| Riyazi analiz | köhnə | 0 | 0 | 0 | 6 | — | — | — | ↔ birləşmə |
|  | yeni | 1 | 16 | 23 | 6 | 1 | 39 | 40 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Azərbaycan dilində işgüzar və akademik kommunikasiya | köhnə | 0 | 27 | 18 | 8 | 35 | — | — | ✅ |
|  | yeni | 0 | 27 | 18 | 8 | 35 | 45 | 80 |  |
| Riyazi analiz | köhnə | 0 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 1 | 16 | 23 | 6 | 1 | 39 | 40 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Xətti cəbr və analitik həndəsə | köhnə | 0 | 15 | 23 | 8 | 29 | — | — | ✅ |
|  | yeni | 0 | 15 | 23 | 8 | 29 | 38 | 67 |  |
| Proqramlaşdırma texnologiyaları | köhnə | 1 | 19 | 20 | 10 | 23 | — | — | ✅ |
|  | yeni | 1 | 19 | 20 | 10 | 23 | 39 | 62 |  |
| Riyazi analiz | köhnə | 1 | 16 | 23 | 0 | 1 | — | — | ↔ birləşmə |
|  | yeni | 1 | 16 | 23 | 6 | 1 | 39 | 40 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Kompüter mühəndisliyinin əsasları | köhnə | 0 | 24 | 23 | 8 | 17 | — | — | ✅ |
|  | yeni | 0 | 24 | 23 | 8 | 17 | 47 | 64 |  |
| Kompüter diaqnostikası | köhnə | 2 | 16 | 27 | 10 | 24 | — | — | ✅ |
|  | yeni | 2 | 16 | 27 | 10 | 24 | 43 | 67 |  |
| Alqoritmləşdirmə və proqramlaşdırma | köhnə | 0 | 20 | 30 | 10 | 34 | — | — | ✅ |
|  | yeni | 0 | 20 | 30 | 10 | 34 | 50 | 84 |  |
| Diskret riyaziyyat | köhnə | 0 | 17 | 29 | 10 | 33 | — | — | ✅ |
|  | yeni | 0 | 17 | 29 | 10 | 33 | 46 | 79 |  |

### Nümunə 09

| Yoxlama | Nəticə |
|---|---|
| Ad/soyad uyğunluğu | ✅ uyğun |
| Qrup uyğunluğu | ✅ uyğun |
| İxtisas/proqram uyğunluğu | ✅ uyğun |
| Hədəf statusu | enrolled (aktiv üzvlük) |

| Fənn | Tərəf | Qayıb | Seminar bal | Kollokvium | Sərbəst iş | İmtahan | Giriş balı | Yekun | ⚑ |
|---|---|---|---|---|---|---|---|---|---|
| Dünyanın müasir təbii elmi mənzərəsinin paradiqması | köhnə | 8 | 0 | 21 | 7 | 18 | — | — | ↔ birləşmə |
|  | yeni | 8 | 0 | 21 | 7 | 18 | 21 | 39 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Antik fəlsəfə | köhnə | 1 | 6 | 10 | 9 | 0 | 30 | 30 | 🔴 |
|  | yeni | 1 | 6 | 10 | 9 | 9 | 16 | 25 |  |
| Müasir İKT və informasiya təhlükəsizliyi | köhnə | 3 | 0 | 19 | 7 | 12 | — | — | ↔ birləşmə |
|  | yeni | 4 | 0 | 19 | 7 | 12 | 19 | 31 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Müasir fəlsəfə | köhnə | 13 | 0 | 13 | 7 | 19 | — | — | ✅ |
|  | yeni | 13 | 0 | 13 | 7 | 19 | 13 | 32 |  |
| Siyasətin fəlsəfəsi | köhnə | 2 | 0 | 17 | 6 | 8 | — | — | ✅ |
|  | yeni | 2 | 0 | 17 | 6 | 8 | 17 | 25 |  |
| Müasir fəlsəfə | köhnə | 1 | 0 | 5 | 8 | 3 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Qədim Şərq fəlsəfəsi | köhnə | 2 | 0 | 14 | 8 | 17 | — | — | ✅ |
|  | yeni | 2 | 0 | 14 | 8 | 17 | 14 | 31 |  |
| Türk xalqlarının fəlsəfi fikri tarixi | köhnə | 3 | 8 | 11 | 7 | 6 | — | — | ↔ birləşmə |
|  | yeni | 3 | 8 | 11 | 7 | 6 | 19 | 25 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Etika və estetika | köhnə | 2 | 6 | 16 | 7 | 9 | 32 | 41 | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Məntiq-2 | köhnə | 0 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Siyasət nəzəriyyəsi | köhnə | 1 | 6 | 20 | 8 | 23 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| İnsan hüquqları | köhnə | 1 | 8 | 24 | 8 | 8 | — | — | ✅ |
|  | yeni | 1 | 8 | 24 | 8 | 8 | 32 | 40 |  |
| Elmin fəlsəfəsi | köhnə | 15 | 0 | 20 | 7 | 21 | — | — | ✅ |
|  | yeni | 15 | 0 | 20 | 7 | 21 | 20 | 41 |  |
| Elinistik və orta əsr Avropa fəlsəfəsi | köhnə | 4 | 8 | 16 | 7 | 5 | — | — | ✅ |
|  | yeni | 4 | 8 | 16 | 7 | 5 | 24 | 29 |  |
| Tarixin fəlsəfəsi | köhnə | 8 | 6 | 16 | 6 | 21 | — | — | ✅ |
|  | yeni | 8 | 6 | 16 | 6 | 21 | 22 | 43 |  |
| Elinistik və orta əsr Avropa fəlsəfəsi | köhnə | 1 | 0 | 8 | 6 | 9 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Azərbaycan fəlsəfə tarixi | köhnə | 3 | 7 | 14 | 8 | 5 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Sosial fəlsəfə -2 | köhnə | 3 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Elinistik və orta əsr Avropa fəlsəfəsi | köhnə | 4 | 0 | 14 | 7 | 0 | — | — | ✅ |
|  | yeni | 4 | 0 | 14 | 7 | 0 | 14 | 14 |  |
| Avropa fəlsəfəsi | köhnə | 26 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 26 | 0 | 0 | 0 | — | 0 | 0 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Müasir fəlsəfi komparativistika | köhnə | 3 | 7 | 21 | 8 | 30 | — | — | ✅ |
|  | yeni | 3 | 7 | 21 | 8 | 30 | 28 | 58 |  |
| Hüquq fəlsəfəsi | köhnə | 1 | 0 | 6 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Antik fəlsəfə | köhnə | 2 | 14 | 14 | 8 | 3 | — | — | ✅ |
|  | yeni | 2 | 14 | 14 | 8 | 3 | 28 | 31 |  |
| Ontologiya və idrak nəzəriyyəsi -3( Epistemologiya ) | köhnə | 3 | 0 | 6 | 4 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Sosial fəlsəfə -1 | köhnə | 2 | 7 | 19 | 7 | 22 | — | — | ✅ |
|  | yeni | 2 | 7 | 19 | 7 | 22 | 26 | 48 |  |
| Strateji idarəetmə | köhnə | 5 | 0 | 16 | 8 | — | — | — | ✅ |
|  | yeni | 5 | 0 | 16 | 8 | — | 16 | 16 |  |
| Müasir fəlsəfə | köhnə | 0 | 14 | 17 | 8 | 17 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Müasir təbiətşünaslıq konsepsiyası | köhnə | 5 | 7 | 21 | 7 | 0 | — | — | ✅ |
|  | yeni | 5 | 7 | 21 | 7 | 0 | 28 | 28 |  |
| Din fəlsəfəsi | köhnə | 3 | 14 | 21 | 7 | 18 | 37 | 55 | 🔴 |
|  | yeni | 3 | 14 | 21 | 7 | 18 | 35 | 53 |  |
| Şəxsiyyətin azadlığı və məsuliyyəti | köhnə | 1 | 15 | 13 | 10 | 12 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Genderin fəlsəfi problemləri | köhnə | 1 | 7 | 20 | 8 | 18 | — | — | ✅ |
|  | yeni | 1 | 7 | 20 | 8 | 18 | 27 | 45 |  |
| Fəlsəfi antropologiya | köhnə | 23 | 0 | 0 | 0 | — | — | — | ✅ |
|  | yeni | 23 | 0 | 0 | 0 | — | 0 | 0 |  |
| Mülki müdafiə | köhnə | 2 | 5 | 15 | 4 | 6 | 28 | 34 | ↔ birləşmə |
|  | yeni | 2 | 5 | 15 | 4 | 20 | 20 | 40 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Politologiya | köhnə | 3 | 8 | 19 | 8 | — | — | — | ✅ |
|  | yeni | 3 | 8 | 19 | 8 | — | 27 | 27 |  |
| Siyasət nəzəriyyəsi | köhnə | 1 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 3 | 0 | 12 | 8 | 7 | 12 | 19 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| İslam fəlsəfəsi | köhnə | 6 | 2 | 15 | 7 | 6 | — | — | ✅ |
|  | yeni | 6 | 2 | 15 | 7 | 6 | 17 | 23 |  |
| Xarici dildə işgüzar və akademik kommunikasiya | köhnə | 5 | 0 | 18 | 6 | — | — | — | ✅ |
|  | yeni | 5 | 0 | 18 | 6 | — | 18 | 18 |  |
| Xarici dildə işgüzar və akademik kommunikasiya | köhnə | 4 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Türk xalqlarının fəlsəfi fikri tarixi | köhnə | 0 | 0 | 5 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 3 | 8 | 11 | 7 | 6 | 19 | 25 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Süni intellektin fəlsəfi aspektləri | köhnə | 4 | 0 | 18 | 7 | 19 | — | — | ✅ |
|  | yeni | 4 | 0 | 18 | 7 | 19 | 18 | 37 |  |
| Alman klassik fəlsəfəsi | köhnə | 8 | 0 | 18 | 7 | 21 | — | — | ✅ |
|  | yeni | 8 | 0 | 18 | 7 | 21 | 18 | 39 |  |
| Sosial pedaqogika | köhnə | 3 | 0 | 19 | 7 | — | — | — | ✅ |
|  | yeni | 3 | 0 | 19 | 7 | — | 19 | 19 |  |
| Sosial fəlsəfə -2 | köhnə | 0 | 5 | 18 | 8 | 25 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Məntiq-1 | köhnə | 0 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Şəxsiyyətin azadlığı və məsuliyyəti | köhnə | 4 | 0 | 18 | 6 | 11 | — | — | ✅ |
|  | yeni | 4 | 0 | 18 | 6 | 11 | 18 | 29 |  |
| Məntiq-1 | köhnə | 1 | 3 | 5 | 9 | 1 | 25 | 26 | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Siyasət nəzəriyyəsi | köhnə | 2 | 0 | 12 | 8 | 7 | — | — | ↔ birləşmə |
|  | yeni | 3 | 0 | 12 | 8 | 7 | 12 | 19 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Mifologiya | köhnə | 1 | 7 | 19 | 10 | 7 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Xarici dildə işgüzar və akademik kommunikasiya | köhnə | 6 | 10 | 8 | 6 | 26 | 17 | 43 | 🔴 |
|  | yeni | 6 | 10 | 8 | 6 | 26 | 18 | 44 |  |
| Avropa fəlsəfəsi | köhnə | 0 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 26 | 0 | 0 | 0 | — | 0 | 0 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Avropa fəlsəfəsi | köhnə | 0 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 26 | 0 | 0 | 0 | — | 0 | 0 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Ontologiya və idrak nəzəriyyəsi -2 ( qnoseologiya) | köhnə | 0 | 12 | 17 | 7 | 23 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Etika və estetika | köhnə | 2 | 9 | 6 | 9 | 6 | — | — | ✅ |
|  | yeni | 2 | 9 | 6 | 9 | 6 | 15 | 21 |  |
| Məntiq-2 | köhnə | 2 | 6 | 16 | 7 | 21 | — | — | ✅ |
|  | yeni | 2 | 6 | 16 | 7 | 21 | 22 | 43 |  |
| Fəlsəfi antropologiya | köhnə | 0 | 13 | 16 | 7 | 23 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Dünyanın müasir təbii elmi mənzərəsinin paradiqması | köhnə | 0 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 8 | 0 | 21 | 7 | 18 | 21 | 39 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Müasir İKT və informasiya təhlükəsizliyi | köhnə | 6 | 6 | 20 | 6 | 26 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Müasir İKT və informasiya təhlükəsizliyi | köhnə | 1 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 4 | 0 | 19 | 7 | 12 | 19 | 31 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Qədim yazılar (Yunan, latın ) | köhnə | 1 | 0 | 20 | 8 | 14 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Humanitar fənlərin fəlsəfi problemləri | köhnə | 0 | 0 | 0 | 0 | — | — | — | ✅ |
|  | yeni | 0 | 0 | 0 | 0 | — | 0 | 0 |  |
| Mifologiya | köhnə | 3 | 0 | 18 | 6 | 0 | — | — | ✅ |
|  | yeni | 3 | 0 | 18 | 6 | 0 | 18 | 18 |  |
| Mülki müdafiə | köhnə | 0 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 2 | 5 | 15 | 4 | 20 | 20 | 40 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Latın dili | köhnə | 8 | 4 | 3 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Etika və estetika | köhnə | 0 | 8 | 13 | 7 | 22 | — | — | ✅ |
|  | yeni | 0 | 8 | 13 | 7 | 22 | 21 | 43 |  |
| Hüquq fəlsəfəsi | köhnə | 6 | 0 | 14 | 7 | 17 | — | — | ✅ |
|  | yeni | 6 | 0 | 14 | 7 | 17 | 14 | 31 |  |
| Azərbaycan Respublikasının konstitusiyası və hüququn əsasları | köhnə | 0 | 0 | 21 | 8 | 17 | — | — | ✅ |
|  | yeni | 0 | 0 | 21 | 8 | 17 | 21 | 38 |  |
| İqtisadiyyatın əsasları | köhnə | 0 | 8 | 22 | 8 | 17 | — | — | ✅ |
|  | yeni | 0 | 8 | 22 | 8 | 17 | 30 | 47 |  |
| Sosial fəlsəfə -1 | köhnə | 12 | 0 | 4 | 7 | — | — | — | ✅ |
|  | yeni | 12 | 0 | 4 | 7 | — | 4 | 4 |  |
| Siyasət nəzəriyyəsi | köhnə | 3 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Arqumentasiya nəzəriyyəsi | köhnə | 2 | 7 | 21 | 8 | 21 | — | — | ✅ |
|  | yeni | 2 | 7 | 21 | 8 | 21 | 28 | 49 |  |
| Azərbaycan fəlsəfə tarixi | köhnə | 6 | 8 | 5 | 4 | 1 | — | — | ✅ |
|  | yeni | 6 | 8 | 5 | 4 | 1 | 13 | 14 |  |
| Ontologiya və idrak nəzəriyyəsi -3( Epistemologiya ) | köhnə | 5 | 7 | 19 | 6 | 18 | — | — | ✅ |
|  | yeni | 5 | 7 | 19 | 6 | 18 | 26 | 44 |  |

### Nümunə 10

| Yoxlama | Nəticə |
|---|---|
| Ad/soyad uyğunluğu | ✅ uyğun |
| Qrup uyğunluğu | ✅ uyğun |
| İxtisas/proqram uyğunluğu | ✅ uyğun |
| Hədəf statusu | enrolled (aktiv üzvlük) |

> Bu tələbə üçün jurnal xanası tapılmadı.

### Nümunə 11

| Yoxlama | Nəticə |
|---|---|
| Ad/soyad uyğunluğu | ✅ uyğun |
| Qrup uyğunluğu | ✅ uyğun |
| İxtisas/proqram uyğunluğu | ✅ uyğun |
| Hədəf statusu | enrolled (aktiv üzvlük) |

| Fənn | Tərəf | Qayıb | Seminar bal | Kollokvium | Sərbəst iş | İmtahan | Giriş balı | Yekun | ⚑ |
|---|---|---|---|---|---|---|---|---|---|
| Qonaqpərvərlik sənayesində marketinq | köhnə | 5 | 16 | 17 | 10 | 44 | — | — | ✅ |
|  | yeni | 5 | 16 | 17 | 10 | 44 | 33 | 77 |  |
| Turizm coğrafiyası | köhnə | 1 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Turizmə giriş | köhnə | 0 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Biznes riyaziyyatı | köhnə | 6 | 22 | 15 | 9 | 2 | — | — | ✅ |
|  | yeni | 6 | 22 | 15 | 9 | 2 | 37 | 39 |  |
| Xarici dildə işgüzar akademik kommunikasiya-2(elementary) | köhnə | 8 | 14 | 17 | 8 | — | — | — | ✅ |
|  | yeni | 8 | 14 | 17 | 8 | — | 31 | 31 |  |
| Azərbaycan dilində işgüzar və akademik kommunikasiya | köhnə | 3 | 7 | 14 | 10 | 23 | — | — | ✅ |
|  | yeni | 3 | 7 | 14 | 10 | 23 | 21 | 44 |  |
| Restoran menecmenti | köhnə | 3 | 17 | 17 | 6 | 40 | — | — | ↔ birləşmə |
|  | yeni | 4 | 17 | 17 | 6 | 40 | 34 | 74 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Turizm coğrafiyası | köhnə | 0 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Biznes statikası | köhnə | 5 | 21 | 10 | 10 | 36 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Mühasibat uçotu | köhnə | 4 | 10 | 18 | 8 | 7 | — | — | ✅ |
|  | yeni | 4 | 10 | 18 | 8 | 7 | 28 | 35 |  |
| Azərbaycanda turizmin inkişaf problemləri | köhnə | 2 | 0 | 25 | 9 | 17 | — | — | ✅ |
|  | yeni | 2 | 0 | 25 | 9 | 17 | 25 | 42 |  |
| Xarici dildə işgüzar və akademik kommunikasiya | köhnə | 5 | 26 | 21 | 7 | — | — | — | ✅ |
|  | yeni | 5 | 26 | 21 | 7 | — | 47 | 47 |  |
| Azərbaycan tarixi | köhnə | 0 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Turizm coğrafiyası | köhnə | 1 | 13 | 20 | 6 | 49 | — | — | ✅ |
|  | yeni | 1 | 13 | 20 | 6 | 49 | 33 | 82 |  |
| Menecmentin əsasları | köhnə | 3 | 0 | 18 | 6 | 19 | — | — | ✅ |
|  | yeni | 3 | 0 | 18 | 6 | 19 | 18 | 37 |  |
| Makroiqtisadiyyat | köhnə | 4 | 16 | 29 | 7 | 20 | — | — | ✅ |
|  | yeni | 4 | 16 | 29 | 7 | 20 | 45 | 65 |  |
| Turizmin iqtisadiyyatı | köhnə | 4 | 45 | 23 | 10 | 32 | — | — | ✅ |
|  | yeni | 4 | 45 | 23 | 10 | 32 | 50 | 82 |  |
| Azərbaycanın iqtisadi inkişafının perspektivləri | köhnə | 1 | 22 | 23 | 8 | 26 | — | — | ✅ |
|  | yeni | 1 | 22 | 23 | 8 | 26 | 45 | 71 |  |
| Qış turizminin təşkilinin xüsusiyyətləri | köhnə | 1 | 10 | 18 | 8 | — | — | — | ✅ |
|  | yeni | 1 | 10 | 18 | 8 | — | 28 | 28 |  |
| Turizm sahəsində reklamlar | köhnə | 2 | 39 | 16 | 9 | 36 | — | — | ✅ |
|  | yeni | 2 | 39 | 16 | 9 | 36 | 50 | 86 |  |
| Turizmə giriş | köhnə | 1 | 7 | 23 | 9 | 42 | — | — | ↔ birləşmə |
|  | yeni | 1 | 7 | 23 | 9 | 42 | 30 | 72 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Restoran menecmenti | köhnə | 1 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 4 | 17 | 17 | 6 | 40 | 34 | 74 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Mikroiqtisadiyyat | köhnə | 0 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Azərbaycan tarixi | köhnə | 0 | 5 | 17 | 8 | 29 | — | — | ↔ birləşmə |
|  | yeni | 0 | 5 | 17 | 8 | 29 | 22 | 51 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Turizm hüququ | köhnə | 4 | 5 | 20 | 7 | 30 | — | — | ✅ |
|  | yeni | 4 | 5 | 20 | 7 | 30 | 25 | 55 |  |
| Turizmə giriş | köhnə | 0 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 1 | 7 | 23 | 9 | 42 | 30 | 72 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Azərbaycan tarixi | köhnə | 0 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 0 | 5 | 17 | 8 | 29 | 22 | 51 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| İdarəetmə uçotu və korporativ qərarların verilməsi | köhnə | 5 | 7 | 17 | 8 | 21 | — | — | ✅ |
|  | yeni | 5 | 7 | 17 | 8 | 21 | 24 | 45 |  |
| Turizmdə təhlükəsizlik | köhnə | 3 | 21 | 16 | 9 | 38 | — | — | ✅ |
|  | yeni | 3 | 21 | 16 | 9 | 38 | 37 | 75 |  |
| Multikulturalizmə giriş | köhnə | 1 | 7 | 22 | 7 | 12 | — | — | ✅ |
|  | yeni | 1 | 7 | 22 | 7 | 12 | 29 | 41 |  |
| Mikroiqtisadiyyat | köhnə | 0 | 8 | 25 | 9 | 6 | — | — | 🔴 |
|  | yeni | 0 | 8 | 25 | 9 | 17 | 33 | 50 |  |
| Turizmdə servis xidmətinin təşkili | köhnə | 5 | 18 | 20 | 10 | 20 | — | — | ✅ |
|  | yeni | 5 | 18 | 20 | 10 | 20 | 38 | 58 |  |

### Nümunə 12

| Yoxlama | Nəticə |
|---|---|
| Ad/soyad uyğunluğu | ✅ uyğun |
| Qrup uyğunluğu | ✅ uyğun |
| İxtisas/proqram uyğunluğu | ✅ uyğun |
| Hədəf statusu | enrolled (aktiv üzvlük) |

> Bu tələbə üçün jurnal xanası tapılmadı.

### Nümunə 13

| Yoxlama | Nəticə |
|---|---|
| Ad/soyad uyğunluğu | ✅ uyğun |
| Qrup uyğunluğu | ✅ uyğun |
| İxtisas/proqram uyğunluğu | ✅ uyğun |
| Hədəf statusu | enrolled (aktiv üzvlük) |

> Bu tələbə üçün jurnal xanası tapılmadı.

### Nümunə 14

| Yoxlama | Nəticə |
|---|---|
| Ad/soyad uyğunluğu | ✅ uyğun |
| Qrup uyğunluğu | ✅ uyğun |
| İxtisas/proqram uyğunluğu | ✅ uyğun |
| Hədəf statusu | enrolled (aktiv üzvlük) |

> Bu tələbə üçün jurnal xanası tapılmadı.

### Nümunə 15

| Yoxlama | Nəticə |
|---|---|
| Ad/soyad uyğunluğu | ✅ uyğun |
| Qrup uyğunluğu | ✅ uyğun |
| İxtisas/proqram uyğunluğu | ✅ uyğun |
| Hədəf statusu | enrolled (aktiv üzvlük) |

> Bu tələbə üçün jurnal xanası tapılmadı.

### Nümunə 16

| Yoxlama | Nəticə |
|---|---|
| Ad/soyad uyğunluğu | ✅ uyğun |
| Qrup uyğunluğu | ✅ uyğun |
| İxtisas/proqram uyğunluğu | ✅ uyğun |
| Hədəf statusu | enrolled (aktiv üzvlük) |

| Fənn | Tərəf | Qayıb | Seminar bal | Kollokvium | Sərbəst iş | İmtahan | Giriş balı | Yekun | ⚑ |
|---|---|---|---|---|---|---|---|---|---|
| Ümumi psixologiya-4(təfəkkur və nitq) | köhnə | 1 | 10 | 30 | 10 | 47 | — | — | ✅ |
|  | yeni | 1 | 10 | 30 | 10 | 47 | 40 | 87 |  |
| Mülki müdafiə | köhnə | 0 | 8 | 6 | 0 | 41 | 21 | 62 | ↔ birləşmə |
|  | yeni | 0 | 8 | 17 | 8 | 41 | 25 | 66 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Yeniyetmələrdə hüquqa zidd davranışın psixologiyası | köhnə | 0 | 10 | 27 | 10 | 39 | — | — | ✅ |
|  | yeni | 0 | 10 | 27 | 10 | 39 | 37 | 76 |  |
| Eksperimental psixologiya | köhnə | 0 | 0 | 30 | 10 | 39 | — | — | ✅ |
|  | yeni | 0 | 0 | 30 | 10 | 39 | 30 | 69 |  |
| Psixofiziologiya | köhnə | 1 | 8 | 30 | 10 | 45 | — | — | ✅ |
|  | yeni | 1 | 8 | 30 | 10 | 45 | 38 | 83 |  |
| Ümumi psixologiya-3 (diqqət və hafizə ) | köhnə | 1 | 8 | 25 | 10 | 41 | 44 | 85 | 🔴 |
|  | yeni | 1 | 8 | 25 | 10 | 41 | 33 | 74 |  |
| Ümumpsixoloji praktikum-1 | köhnə | 0 | 19 | 28 | 10 | — | — | — | ✅ |
|  | yeni | 0 | 19 | 28 | 10 | — | 47 | 47 |  |
| Ümumi psixologiya-5 (emosiya və motivasiya ) | köhnə | 0 | 9 | 28 | 10 | 31 | — | — | ✅ |
|  | yeni | 0 | 9 | 28 | 10 | 31 | 37 | 68 |  |
| Xüsusi psixologiya | köhnə | 1 | 9 | 29 | 10 | 34 | 48 | 82 | 🔴 |
|  | yeni | 1 | 9 | 29 | 10 | 34 | 38 | 72 |  |
| Mülki müdafiə | köhnə | 0 | 0 | 11 | 8 | 41 | 29 | 70 | ↔ birləşmə |
|  | yeni | 0 | 8 | 17 | 8 | 41 | 25 | 66 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Pedaqoji psixologiya | köhnə | 0 | 0 | 26 | 10 | 34 | — | — | ✅ |
|  | yeni | 0 | 0 | 26 | 10 | 34 | 26 | 60 |  |
| Mülki müdafiə | köhnə | 0 | 0 | 0 | 0 | 41 | 10 | 51 | ↔ birləşmə |
|  | yeni | 0 | 8 | 17 | 8 | 41 | 25 | 66 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Psixoterapiyanın əsasları | köhnə | 0 | 10 | 30 | 10 | 33 | — | — | ✅ |
|  | yeni | 0 | 10 | 30 | 10 | 33 | 40 | 73 |  |
| Hüqüq psixologiyası | köhnə | 4 | 10 | 29 | 10 | 49 | — | — | ✅ |
|  | yeni | 4 | 10 | 29 | 10 | 49 | 39 | 88 |  |
| Təhsil psixologiyası | köhnə | 1 | 0 | 26 | 10 | 29 | — | — | ✅ |
|  | yeni | 1 | 0 | 26 | 10 | 29 | 26 | 55 |  |
| İnformasiya texnologiyaları (ixtisas üzrə) | köhnə | 0 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 0 | 9 | 24 | 10 | 44 | 33 | 77 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Siyasi psixologiya | köhnə | 0 | 9 | 28 | 9 | 48 | — | — | ✅ |
|  | yeni | 0 | 9 | 28 | 9 | 48 | 37 | 85 |  |
| Ailə psixologiyası | köhnə | 0 | 10 | 28 | 10 | 39 | — | — | ✅ |
|  | yeni | 0 | 10 | 28 | 10 | 39 | 38 | 77 |  |
| Psixi sağlamlıq | köhnə | 1 | 0 | 30 | 9 | 47 | — | — | ✅ |
|  | yeni | 1 | 0 | 30 | 9 | 47 | 30 | 77 |  |
| Patopsixologiya | köhnə | 1 | 19 | 26 | 10 | 35 | — | — | ✅ |
|  | yeni | 1 | 19 | 26 | 10 | 35 | 45 | 80 |  |
| Ümumi psixologiya-6 (fərdiyyət və şəxsiyyət ) | köhnə | 0 | 10 | 30 | 10 | 43 | — | — | ✅ |
|  | yeni | 0 | 10 | 30 | 10 | 43 | 40 | 83 |  |
| Ümumpsixoloji praktikum-2 | köhnə | 1 | 18 | 29 | 10 | 40 | 47 | 87 | ✅ |
|  | yeni | 1 | 18 | 29 | 10 | 40 | 47 | 87 |  |
| Pedaqogika | köhnə | 0 | 0 | 27 | 10 | 45 | — | — | ✅ |
|  | yeni | 0 | 0 | 27 | 10 | 45 | 27 | 72 |  |
| Psixoloji yardımın hüquqi əsasları | köhnə | 0 | 30 | 29 | 10 | 40 | — | — | ✅ |
|  | yeni | 0 | 30 | 29 | 10 | 40 | 50 | 90 |  |
| Multikulturalizmə giriş | köhnə | 0 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 0 | 9 | 28 | 10 | 22 | 37 | 59 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| İnformasiya texnologiyaları (ixtisas üzrə) | köhnə | 0 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 0 | 9 | 24 | 10 | 44 | 33 | 77 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| ASF və sensor sistemin fiziologiyası | köhnə | 0 | 19 | 25 | 10 | — | — | — | ✅ |
|  | yeni | 0 | 19 | 25 | 10 | — | 44 | 44 |  |
| Psixodiaqnostika | köhnə | 0 | 9 | 28 | 10 | 49 | — | — | ✅ |
|  | yeni | 0 | 9 | 28 | 10 | 49 | 37 | 86 |  |
| Etnopsixologiya | köhnə | 0 | 9 | 28 | 10 | 36 | 48 | 84 | 🔴 |
|  | yeni | 0 | 9 | 28 | 10 | 36 | 37 | 73 |  |
| Ümumi psixologiya-2 (duygu və qavrayış ) | köhnə | 0 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 1 | 20 | 25 | 10 | — | 45 | 45 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| İnformasiya texnologiyaları (ixtisas üzrə) | köhnə | 0 | 9 | 24 | 10 | 44 | — | — | ↔ birləşmə |
|  | yeni | 0 | 9 | 24 | 10 | 44 | 33 | 77 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Ümumi psixologiya-2 (duygu və qavrayış ) | köhnə | 1 | 30 | 25 | 10 | — | — | — | ↔ birləşmə |
|  | yeni | 1 | 20 | 25 | 10 | — | 45 | 45 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Fəlsəfə | köhnə | 0 | 9 | 14 | 9 | — | — | — | ↔ birləşmə |
|  | yeni | 0 | 9 | 14 | 9 | — | 23 | 23 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Klinik psixologiya | köhnə | 0 | 10 | 28 | 10 | 32 | — | — | ✅ |
|  | yeni | 0 | 10 | 28 | 10 | 32 | 38 | 70 |  |
| Fəlsəfə | köhnə | 0 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 0 | 9 | 14 | 9 | — | 23 | 23 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Menecment psixologiyası | köhnə | 1 | 10 | 29 | 10 | 41 | — | — | ✅ |
|  | yeni | 1 | 10 | 29 | 10 | 41 | 39 | 80 |  |
| Sosial psixologiya | köhnə | 0 | 0 | 30 | 10 | 39 | — | — | ✅ |
|  | yeni | 0 | 0 | 30 | 10 | 39 | 30 | 69 |  |
| Müqayisəli psixologiya və zoopsixologiya | köhnə | 0 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 0 | 9 | 28 | 10 | 45 | 37 | 82 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Xarici dildə işgüzar və akademik kommunikasiya | köhnə | 0 | 21 | 18 | 9 | 50 | 26 | 76 | 🔴 |
|  | yeni | 0 | 21 | 18 | 9 | 50 | 39 | 89 |  |
| Biznes psixologiyası və sahibkarlıq | köhnə | 0 | 10 | 30 | 8 | 50 | — | — | ✅ |
|  | yeni | 0 | 10 | 30 | 8 | 50 | 40 | 90 |  |
| İnkişaf və yaş psixologiyası | köhnə | 1 | 9 | 30 | 10 | 39 | — | — | ✅ |
|  | yeni | 1 | 9 | 30 | 10 | 39 | 39 | 78 |  |
| Multikulturalizmə giriş | köhnə | 0 | 9 | 28 | 10 | 22 | — | — | ↔ birləşmə |
|  | yeni | 0 | 9 | 28 | 10 | 22 | 37 | 59 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Mülki müdafiə | köhnə | 0 | 0 | 0 | 0 | 41 | 21 | 62 | ↔ birləşmə |
|  | yeni | 0 | 8 | 17 | 8 | 41 | 25 | 66 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Müqayisəli psixologiya və zoopsixologiya | köhnə | 0 | 9 | 28 | 10 | 45 | — | — | ↔ birləşmə |
|  | yeni | 0 | 9 | 28 | 10 | 45 | 37 | 82 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Psixologiyada riyazi və statistik metodlar | köhnə | 0 | 9 | 27 | 10 | 40 | — | — | ✅ |
|  | yeni | 0 | 9 | 27 | 10 | 40 | 36 | 76 |  |

### Nümunə 17

| Yoxlama | Nəticə |
|---|---|
| Ad/soyad uyğunluğu | ✅ uyğun |
| Qrup uyğunluğu | ✅ uyğun |
| İxtisas/proqram uyğunluğu | ✅ uyğun |
| Hədəf statusu | enrolled (aktiv üzvlük) |

> Bu tələbə üçün jurnal xanası tapılmadı.

### Nümunə 18

| Yoxlama | Nəticə |
|---|---|
| Ad/soyad uyğunluğu | ✅ uyğun |
| Qrup uyğunluğu | ✅ uyğun |
| İxtisas/proqram uyğunluğu | ✅ uyğun |
| Hədəf statusu | enrolled (aktiv üzvlük) |

> Bu tələbə üçün jurnal xanası tapılmadı.

### Nümunə 19

| Yoxlama | Nəticə |
|---|---|
| Ad/soyad uyğunluğu | ✅ uyğun |
| Qrup uyğunluğu | ✅ uyğun |
| İxtisas/proqram uyğunluğu | ✅ uyğun |
| Hədəf statusu | enrolled (aktiv üzvlük) |

> Bu tələbə üçün jurnal xanası tapılmadı.

### Nümunə 20

| Yoxlama | Nəticə |
|---|---|
| Ad/soyad uyğunluğu | ✅ uyğun |
| Qrup uyğunluğu | ✅ uyğun |
| İxtisas/proqram uyğunluğu | ✅ uyğun |
| Hədəf statusu | enrolled (aktiv üzvlük) |

| Fənn | Tərəf | Qayıb | Seminar bal | Kollokvium | Sərbəst iş | İmtahan | Giriş balı | Yekun | ⚑ |
|---|---|---|---|---|---|---|---|---|---|
| Psixologiyanın əsasları | köhnə | 6 | 25 | 27 | 10 | 43 | — | — | ✅ |
|  | yeni | 6 | 25 | 27 | 10 | 43 | 50 | 93 |  |
| Təhsildə psixoloji xidmət və psixoloji praktikum | köhnə | 1 | 17 | 24 | 10 | 36 | — | — | ↔ birləşmə |
|  | yeni | 4 | 17 | 24 | 10 | 36 | 41 | 77 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Uşaq psixologiyası | köhnə | 4 | 17 | 26 | 10 | 36 | — | — | ↔ birləşmə |
|  | yeni | 5 | 17 | 26 | 10 | 36 | 43 | 79 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Xarici dildə işgüzar akademik kommunikasiya-2(intermediate) | köhnə | 6 | 17 | 23 | 10 | — | — | — | ✅ |
|  | yeni | 6 | 17 | 23 | 10 | — | 40 | 40 |  |
| Uşaq anatomiyası, fiziologiyası və gigiyenası | köhnə | 1 | 8 | 17 | 8 | 33 | — | — | ↔ birləşmə |
|  | yeni | 4 | 8 | 17 | 8 | 33 | 25 | 58 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Psixologiyanın əsasları | köhnə | 0 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Uşaq anatomiyası, fiziologiyası və gigiyenası | köhnə | 3 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 4 | 8 | 17 | 8 | 33 | 25 | 58 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Təhsildə İKT | köhnə | 6 | 26 | 20 | 10 | 32 | — | — | ✅ |
|  | yeni | 6 | 26 | 20 | 10 | 32 | 46 | 78 |  |
| Təhsildə psixoloji xidmət və psixoloji praktikum | köhnə | 3 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 4 | 17 | 24 | 10 | 36 | 41 | 77 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Azərbaycan dilində işgüzar və akademik kommunikasiya | köhnə | 5 | 24 | 17 | 10 | 43 | — | — | ✅ |
|  | yeni | 5 | 24 | 17 | 10 | 43 | 41 | 84 |  |
| Uşaq psixologiyası | köhnə | 1 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 5 | 17 | 26 | 10 | 36 | 43 | 79 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Azərbaycan tarixi | köhnə | 4 | 9 | 27 | 10 | 48 | — | — | ↔ birləşmə |
|  | yeni | 7 | 9 | 27 | 10 | 48 | 36 | 84 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Azərbaycan tarixi | köhnə | 3 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 7 | 9 | 27 | 10 | 48 | 36 | 84 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Pedaqogika | köhnə | 7 | 48 | 25 | 10 | 35 | — | — | ✅ |
|  | yeni | 7 | 48 | 25 | 10 | 35 | 50 | 85 |  |
| Xarici dildə işgüzar və akademik kommunikasiya-1(pre-intermadiate) | köhnə | 10 | 63 | 16 | 10 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |

> **Qeyd:** «Giriş balı» sütunundakı fərqi XƏTA saymayın — düstur hazırda
> yenilənir (bax §4.2).

## 4. Bal bütövlüyü

### 4.1 `yekun` cədvəli ↔ hədəfin hesabladığı yekun

| Göstərici | Say |
|---|---|
| Mənbədəki `yekun` sətri | 17,194 |
| Hədəfdəki yazılışa bağlanan sətir | 15,681 |
| …bunlardan birləşən jurnal səbəbindən eyni yazılışa düşən | 1,013 |
| …yəni fərqli yazılış sayı | 14,668 |
| Bağlana bilməyən (yazılış köçürülməyib) | 1,513 |
| Bağlandı, amma registrar-da tapılmadı | 0 |
| Müqayisə edilən yekun bal | 14,668 |
| *J8 fazasının öz rəqəmi:* bağlana bilməyən | 1,513 |
| *J8 fazasının öz rəqəmi:* kənarlaşan yekun | 15,112 |

> Son iki sətir ledger-dən gəlir (`legacy_journal_reconcile_*`) və bu hesabatın
> MÜSTƏQİL hesabladığı rəqəmlərlə üzləşdirilir — iki sübut mənbəyi bir-birini
> yoxlayır.

**Yekun balı fərqinin paylanması** (hədəfin hesabladığı − legacy `yekun`):

| Fərq | Say | Pay |
|---|---|---|
| 0 | 532 | 3.6 % |
| ±1 | 947 | 6.5 % |
| ±2 | 990 | 6.7 % |
| ±3–5 | 2,783 | 19.0 % |
| >5 | 9,416 | 64.2 % |

> ⚠️ Bu paylanmadakı böyük fərqlərin əsas mənbəyi **giriş balı düsturudur**
> (§4.2) — yekun = giriş + imtahan olduğu üçün giriş kənarlaşması birbaşa
> yekuna keçir.  Düsturdan asılı olmayan hissəni aşağıdakı iki cədvəldə görün.

**İmtahan balı fərqinin paylanması** (`im`/`im2` ↔ `FinalGrade`/`ResitRecord`):

| Fərq | Say | Pay |
|---|---|---|
| 0 | 13,801 | 94.1 % |
| ±1 | 24 | 0.2 % |
| ±2 | 18 | 0.1 % |
| ±3–5 | 105 | 0.7 % |
| >5 | 720 | 4.9 % |

**`yekun − giriş` fərqinin paylanması** — giriş düsturundan ASILI OLMAYAN hissə:

| Fərq | Say | Pay |
|---|---|---|
| 0 | 13,723 | 93.6 % |
| ±1 | 38 | 0.3 % |
| ±2 | 25 | 0.2 % |
| ±3–5 | 122 | 0.8 % |
| >5 | 760 | 5.2 % |

### 4.2 ⏳ Giriş balı — DÜSTUR GÖZLƏYİR

> Giriş balının hesablanma düsturu **hazırda yenilənir**.  Aşağıdakı paylanma
> `entry = min(seminar + kollokvium, entry_score_max)` cari güzgüsü ilə
> hesablanıb və **XƏTA SAYILMIR** — düstur dəqiqləşəndə bu bölmə yenidən
> işlədilməlidir.

| Fərq | Say | Pay |
|---|---|---|
| 0 | 533 | 3.6 % |
| ±1 | 954 | 6.5 % |
| ±2 | 990 | 6.7 % |
| ±3–5 | 2,804 | 19.1 % |
| >5 | 9,387 | 64.0 % |

### 4.3 Xana dəyərlərinin paylanması

`ie` = «iştirak edib» — bu **davamiyyətdir, bal deyil**; hədəfdə
`LessonMark.status = present` (bal sütunu boş) kimi oturur.

| Domen / hədəf sətri | Dəyər forması | Say |
|---|---|---|
| Təqvim xanaları (davamiyyət + gündəlik bal) | boş | 7,355 |
| Təqvim xanaları (davamiyyət + gündəlik bal) | ie (davamiyyət: iştirak edib) | 3,523,724 |
| Təqvim xanaları (davamiyyət + gündəlik bal) | qb (davamiyyət: qayıb) | 633,794 |
| Təqvim xanaları (davamiyyət + gündəlik bal) | rəqəm (bal) | 251,552 |
| Komponent xanaları (kollokvium + sərbəst iş) | boş | 630 |
| Komponent xanaları (kollokvium + sərbəst iş) | ie (davamiyyət: iştirak edib) | 4 |
| Komponent xanaları (kollokvium + sərbəst iş) | qb (davamiyyət: qayıb) | 257 |
| Komponent xanaları (kollokvium + sərbəst iş) | rəqəm (bal) | 600,483 |
| İmtahan xanaları (im / im2) | boş | 634 |
| İmtahan xanaları (im / im2) | digər (oxunmayan) | 493 |
| İmtahan xanaları (im / im2) | rəqəm (bal) | 131,102 |
| → hədəf: `LessonMark.status = present` | davamiyyət | 3,381,803 |
| → hədəf: `LessonMark.status = absent` | davamiyyət | 534,323 |
| → hədəf: `LessonMark.status = excused` | üzrlü davamiyyət | 5,178 |
| → hədəf: `LessonMark.score` dolu | bal | 231,677 |
| → hədəf: `ComponentScore` (kollokvium) | bal | 410,109 |
| → hədəf: `ComponentScore` (sərbəst iş) | bal | 135,938 |

## 4A. Legacy qiymət faktlarının itkisizlik sübutu

> Bu yoxlama ad/FİN/e-poçt çıxarmır və fərdi açarları hesabatda göstərmir.
> Hər `(mənbə cədvəli, PK)` üçün giriş, imtahan, yekun, təkrar və xüsusi
> kod payload-u sətir-səviyyəsində tutuşdurulur; nəticə yalnız aqreqatdır.

| Invariant | Say |
|---|---|
| Mənbə qiymət faktı | 171,080 |
| Immutable hədəf faktı | 171,080 |
| Mənbədə təkrarlanan `(cədvəl, PK)` | 0 |
| Hədəfdə təkrarlanan `(cədvəl, PK)` | 0 |
| Hədəfdə çatışmayan mənbə açarı | 0 |
| Mənbədə qarşılığı olmayan artıq hədəf açarı | 0 |
| Bal payload-u fərqli olan ortaq açar | 0 |
| Mənbədən müstəqil yenidən hesablanan hash uyğunsuzluğu | 0 |
| Ledger / tenant / hash / review guard pozuntusu | 0 |

**Nəticə: ✅ TAM TUTUR.**

### Mənbə cədvəli üzrə

| Cədvəl | Mənbə | Hədəf | Fərq |
|---|---|---|---|
| `imthngrscxsblr` | 12,544 | 12,544 | 0 |
| `journals_dates_points` | 138,737 | 138,737 | 0 |
| `journals_dates_points_archive` | 2,605 | 2,605 | 0 |
| `yekun` | 17,194 | 17,194 | 0 |

### Qiymət kodu üzrə

| Kod | Mənbə | Hədəf | Fərq |
|---|---|---|---|
| `01` | 11 | 11 | 0 |
| `02` | 192 | 192 | 0 |
| `03` | 103 | 103 | 0 |
| `04` | 198 | 198 | 0 |
| `05` | 91 | 91 | 0 |
| `07` | 2 | 2 | 0 |
| `09` | 400 | 400 | 0 |
| `10` | 336 | 336 | 0 |
| `11` | 145 | 145 | 0 |
| `12` | 81 | 81 | 0 |
| `exam_entry_exit` | 12,544 | 12,544 | 0 |
| `ga` | 25 | 25 | 0 |
| `im` | 129,047 | 129,047 | 0 |
| `im2` | 5,787 | 5,787 | 0 |
| `k1` | 139 | 139 | 0 |
| `k2` | 53 | 53 | 0 |
| `k3` | 34 | 34 | 0 |
| `ll` | 366 | 366 | 0 |
| `pa` | 1,761 | 1,761 | 0 |
| `rr` | 113 | 113 | 0 |
| `si` | 64 | 64 | 0 |
| `ss` | 721 | 721 | 0 |
| `wr` | 1,164 | 1,164 | 0 |
| `ww` | 509 | 509 | 0 |
| `yekun` | 17,194 | 17,194 | 0 |

### Mapping statusu üzrə (sübut saxlanır, kanonik bağ ayrıca qiymətləndirilir)

| Status | Say |
|---|---|
| `conflict` | 2,279 |
| `discarded_source` | 7,728 |
| `group_mismatch` | 1,964 |
| `linked` | 151,228 |
| `unresolved` | 7,881 |

## 4B. Çap olunmuş bal-vərəqi arxivinin itkisizlik sübutu

> Xam HTML və fərdi məlumat hesabatda göstərilmir. Hər export-un source PK-si,
> UTF-8 SHA-256-si, açılmamış ölçüsü və zlib-dən geri açılan baytları yoxlanır.

| Invariant | Say |
|---|---|
| Mənbə export sətri | 52,386 |
| Immutable hədəf artifact-ı | 52,386 |
| Mənbə payload baytı | 979,137,679 |
| Hədəfdə möhürlənmiş açılmamış bayt | 979,137,679 |
| Çatışmayan mənbə açarı | 0 |
| Artıq hədəf açarı | 0 |
| Metadata uyğunsuzluğu | 0 |
| Müstəqil source hash uyğunsuzluğu | 0 |
| Sıxılma / ledger / tenant / digest pozuntusu | 0 |

**Nəticə: ✅ TAM TUTUR.**

## 5. Keyfiyyət yoxlamaları

### 5.1 Mənbədə (MyEdu) — köçürmədən ƏVVƏLKİ vəziyyət

Buradakı rəqəmlər köçürmənin qüsuru deyil, **mənbənin öz vəziyyətidir**.

| Yoxlama | Say | Qiymət |
|---|---|---|
| Adı və ya soyadı boş olan tələbə | 0 | ✅ təmiz |
| Qrupu olmayan tələbə | 1 | ⚠️ baxılmalıdır |
| Mövcud olmayan qrupa istinad edən tələbə (orfan) | 16 | ⚠️ baxılmalıdır |
| Təkrarlanan FİN (dublikat namizədi) | 2 | ⚠️ baxılmalıdır |
| Eyni ad+soyad+ata adı (dublikat namizədi) | 70 | ⚠️ baxılmalıdır |
| Adı və ya soyadı boş olan işçi | 0 | ✅ təmiz |
| Müəllimi olmayan jurnal | 0 | ✅ təmiz |
| Mövcud olmayan müəllimə istinad edən jurnal (orfan) | 1,531 | ⚠️ baxılmalıdır |
| Mövcud olmayan fənnə istinad edən jurnal (orfan) | 0 | ✅ təmiz |
| Təkrarlanan jurnal `uniqid` | 0 | ✅ təmiz |
| Mövcud olmayan ixtisasa istinad edən qrup (orfan) | 0 | ✅ təmiz |
| Mövcud olmayan jurnala istinad edən `yekun` sətri | 0 | ✅ təmiz |
| Mövcud olmayan tələbəyə istinad edən `yekun` sətri | 58 | ⚠️ baxılmalıdır |

### 5.2 Hədəfdə (EMS Arena) — köçürmədən SONRAKI vəziyyət

| Yoxlama | Say | Qiymət |
|---|---|---|
| Adı və ya soyadı boş olan hesab | 0 | ✅ təmiz |
| Akademik qeydi (SAR) olmayan tələbə | 17 | ⚠️ baxılmalıdır |
| Qrupsuz akademik qeyd | 0 | ✅ təmiz |
| Müəllimsiz açılış | 1,172 | ⚠️ baxılmalıdır |
| Açılışsız dərs | 0 | ✅ təmiz |
| Yazılışı olmayan bal xanası (orfan) | 0 | ✅ təmiz |
| Dərsi olmayan bal xanası (orfan) | 0 | ✅ təmiz |
| Komponenti olmayan komponent balı (orfan) | 0 | ✅ təmiz |
| Təkrarlanan yazılış (açılış + tələbə) | 0 | ✅ təmiz |
| Eyni tələbənin iki aktiv akademik qeydi | 0 | ✅ təmiz |
| Eyni adlı fənn (dublikat namizədi) | 9 | ⚠️ baxılmalıdır |
| Eyni fənn+qrup+dövr üçün iki açılış | 0 | ✅ təmiz |
| Eyni yazılış+dərs üçün iki bal xanası | 0 | ✅ təmiz |

## 6. Ledger problem kodları (ilk 30)

Bunlar səssiz itki DEYİL: hər biri qeydə alınmış, səbəbi adlandırılmış hadisədir.

| Mənbə cədvəli | Kod | Ciddilik | Say |
|---|---|---|---|
| `journals_dates_added_by_teacher` | `legacy_journal_lesson_duplicate` | info | 85,673 |
| `journals_dates_added_by_teacher` | `legacy_journal_lesson_orphan` | info | 61,319 |
| `journals_dates_rooms` | `legacy_lesson_meta_fake` | info | 26,303 |
| `journals_dates_rooms` | `legacy_lesson_meta_orphan` | info | 23,391 |
| `journals_dates_added_by_teacher` | `legacy_journal_lesson_kind_absent` | info | 16,786 |
| `yekun` | `legacy_journal_reconcile_final_deviation` | info | 15,112 |
| `journals` | `legacy_journal_lock_applied` | info | 13,987 |
| `yekun` | `legacy_entry_score_derived` | info | 13,206 |
| `journals_dates_points` | `legacy_lesson_synthesised` | info | 12,292 |
| `journals_dates_rooms` | `legacy_lesson_meta_ambiguous` | warning | 11,921 |
| `journals_dates_points` | `legacy_lesson_synth_hours_unresolved` | info | 11,722 |
| `journals` | `legacy_journal_enrollment_orphan` | info | 10,836 |
| `students` | `legacy_account_email_untrusted` | info | 7,816 |
| `journals_dates_points` | `legacy_grade_fact_discarded_source` | warning | 6,622 |
| `sillabus` | `legacy_syllabus_blank_row_dropped` | info | 6,405 |
| `imthngrscxsblr` | `legacy_grade_fact_unresolved` | warning | 6,250 |
| `sillabus` | `legacy_syllabus_assessment_note_unsurfaced` | info | 5,092 |
| `journals_dates_rooms` | `legacy_lesson_meta_hours_fractional` | warning | 4,306 |
| `journals_dates_points` | `legacy_journal_archive_overlap` | info | 4,245 |
| `sillabus` | `legacy_syllabus_welcome_unsurfaced` | info | 4,079 |
| `journals` | `legacy_journal_student_group_mismatch` | warning | 3,871 |
| `journals_dates_points` | `legacy_journal_mark_recovered_enrollment_unresolved` | warning | 3,806 |
| `journals_dates_points` | `legacy_journal_mark_enrollment_unresolved` | warning | 3,806 |
| `journals` | `legacy_journal_multi_group` | info | 3,580 |
| `curricula_plan` | `legacy_plan_hours_not_modelled` | info | 3,422 |
| `students` | `legacy_sar_curriculum_substituted` | warning | 3,244 |
| `journals_dates_rooms` | `legacy_lesson_meta_topic_missing` | info | 3,139 |
| `allowed_qb` | `legacy_excuse_document_absent` | info | 2,964 |
| `journals` | `legacy_journal_offering_merged` | info | 2,872 |
| `sillabus_serbest_is` | `legacy_selfwork_topics_truncated` | info | 2,813 |

## Əlavə: sorğu vaxtları

Ümumi sorğu vaxtı: **12 dəq 59 s** (43 sorğu, hamısı yalnız-oxu).

| Sorğu | Müddət | Qaytarılan sətir |
|---|---|---|
| hədəf · immutable bal-vərəqi artifact-ləri | 10 dəq 5 s | 52,386 |
| mənbə · dedup edilmiş xana açarları | 1 dəq 26 s | 5,134,834 |
| mənbə · xana seçki açarları | 19.6 s | 5,150,028 |
| mənbə · xana təsnifatı | 7.7 s | 17 |
| hədəf · keyfiyyət | 7.7 s | 13 |
| mənbə · dəyər paylanması | 7.7 s | 18 |
| hədəf · immutable legacy qiymət faktları | 6.7 s | 171,080 |
| hədəf · nümunə yazılışlar | 5.9 s | 219 |
| mənbə · bal-vərəqi artifact metadata | 4.5 s | 52,386 |
| mənbə · xam yazıla bilən | 4.5 s | 3 |
| hədəf · varlıq sayları | 4.3 s | 29 |
| hədəf · ledger | 3.1 s | 55 |
| mənbə · legacy qiymət faktları | 2.5 s | 169,231 |
| mənbə · journals_dates_points xam source hash | 2.2 s | 136,888 |
| hədəf · yekun güzgüsü | 2.1 s | 14,668 |
| mənbə · mənbə dərs slotları | 1.7 s | 309,551 |
| hədəf · offering körpüsü | 731 ms | 13,987 |
| mənbə · cədvəl sayları | 692 ms | 15 |
| hədəf · bərpa dərslərindəki xanalar | 628 ms | 1 |
| hədəf · enrollment körpüsü | 549 ms | 183,771 |
