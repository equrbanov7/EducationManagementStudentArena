# Legacy → EMS Arena köçürmə uzlaşdırma hesabatı

> Bu «testlər keçdi» hesabatı DEYİL.  Bu, **hər mənbə xanasına nə olduğunun**
> mühasibatıdır.  Tutmayan hər rəqəm aşağıda **İZAH OLUNMAMIŞ FƏRQ** kimi
> açıq göstərilir — gizlədilmir.

**Rejim:** hər iki bazaya YALNIZ OXU (`SET TRANSACTION READ ONLY`).  Heç bir
`INSERT` / `UPDATE` / `DELETE` icra olunmur.

| Sahə | Dəyər |
|---|---|
| Hesabat vaxtı | 2026-08-27 06:56:53 |
| Mənbə (MariaDB) | `emsarena-legacy-source-rehearsal:myedudb` |
| Hədəf (PostgreSQL) | `127.0.0.1:55433/emsarena_rehearsal_b90d8e9fc8ef` |
| Repetisiya rejimi / statusu | `rehearsal` / `succeeded` |
| Snapshot SHA-256 | `177ef2269027395f…` |
| Ledger-in gördüyü mənbə sətri | 15,496 |
| Başlama → bitmə | 2026-08-27 00:08:01.285418+00:00 → 2026-08-27 02:38:52.809212+00:00 |

## 0. Bir baxışda

| Göstərici | Say | Mənbənin %-i |
|---|---|---|
| Mənbə jurnal xanası (canlı + arxiv, xam) | 5,911,322 | 100 % |
| Hədəfdə yaradılan sətir | 4,368,694 | 73.9 % |
| İzah olunmuş fərq (boş / oxunmayan / orphan / dublikat / həll olunmayan) | 1,349,112 | 22.8 % |
| **İZAH OLUNMAMIŞ FƏRQ** | **+193,516** | 3.3 % |

**Nəticə:** 🔴 193,516 sətir izahsızdır.

### Ən diqqətçəkən rəqəmlər

1. **18,253** jurnal-yazılışı ötürülüb (9.2 %) — əsas səbəb `legacy_journal_student_inactive` (5 hadisə). Həmin tələbələrin bal xanaları da hədəfə düşmür.
2. **2,042** legacy jurnal açılışa çevrilməyib; onlara bağlı bütün xanalar nərdivanda «orphan jurnal» pilləsindədir.
3. **13** tələbə arxiv üzvlüyü ilə köçüb (aktiv: 5,214) — heç bir hesab silinməyib.
4. **507,734** qayıb və **3,198,284** iştirak xanası davamiyyət kimi oturub; bal daşıyan xana isə **216,453**.
5. `yekun` cədvəlinin **1,979** sətri hədəfdəki yazılışa bağlana bilməyib (yazılış köçürülmədiyi üçün).
6. **4,659** xana heç bir domenə düşmür (naməlum `month_id`) — import-un say balansı onları görmür, bu hesabat görür (§1.3).

## 1. Sətir mühasibatı

### 1.1 Mənbə cədvəllərinin xam sayları

| Mənbə cədvəli | Sətir sayı |
|---|---|
| `curricula` | 126 |
| `curricula_plan` | 3,424 |
| `departments` | 31 |
| `groups` | 766 |
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
| `journal_components` | — | 11,238 | 9,426 | 1,811 | 1 | — (törəmə varlıq) |
| `journal_enrollment` | — | 199,454 | 181,094 | 18,253 | 107 | — (törəmə varlıq) |
| `journal_entry_scores` | — | 13,987 | 13,759 | 228 | 0 | — (törəmə varlıq) |
| `journal_finals` | — | 10,081 | 8,366 | 1,658 | 57 | — (törəmə varlıq) |
| `journal_lock` | — | 13,987 | 13,976 | 11 | 0 | — (törəmə varlıq) |
| `journal_marks` | — | 12,184 | 10,090 | 2,094 | 0 | — (törəmə varlıq) |
| `journal_reconcile` | `yekun` = 17,194 | 17,199 | 0 | 553 | 16,646 | 🔴 +1 |
| `journal_selfwork` | — | 11,861 | 10,156 | 1,705 | 0 | — (törəmə varlıq) |
| `lesson` | `journals_dates_added_by_teacher` = 379,215 | 440,124 | 293,070 | 146,992 | 62 | 🔴 +60,909 |
| `lesson_subject` | `lessons` = 2,521 | 2,521 | 2,521 | 0 | 0 | ✅ tutur |
| `speciality_program` | — | 101 | 101 | 0 | 0 | — (törəmə varlıq) |
| `speciality_unit` | `speciality` = 83 | 83 | 83 | 0 | 0 | ✅ tutur |
| `student` | `students` = 7,816 | 7,816 | 7,716 | 84 | 16 | ✅ tutur |
| `student_placement` | — | 7,716 | 0 | 7,703 | 13 | — (törəmə varlıq) |
| `student_record` | — | 7,716 | 7,703 | 13 | 0 | — (törəmə varlıq) |
| `worker` | `workers` = 729 | 729 | 715 | 2 | 12 | ✅ tutur |
| `worker_materialisation` | — | 715 | 715 | 0 | 0 | — (törəmə varlıq) |

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
| − dublikat xana (J-V4 uduzanları) | −3,532 | 4,405,538 |
| − orphan jurnal (açılış yaradılmayıb) | −261,523 | 4,144,015 |
| − həll olunmayan yazılış (tələbə jurnalda aktiv deyil) | −242,195 | 3,901,820 |
| **= Gözlənilən hədəf sətri** |  | **3,901,820** |
| **Hədəfdə FAKTİKİ** |  | **3,711,153** |
| 🔴 **İZAH OLUNMAMIŞ FƏRQ** |  | **+190,667** |

#### Komponent xanaları (kollokvium + sərbəst iş)

| Pillə | Dəyişiklik | Qalıq |
|---|---|---|
| Mənbə sətri (xam) | 701,005 |  |
| − boş xana (mənbədə dəyər yoxdur) | −630 | 700,375 |
| − oxunmayan xana (karantin) | −469 | 699,906 |
| − arxiv örtüşməsi (J-V7 kəsimindən sonra) | −99,423 | 600,483 |
| − dublikat xana (J-V4 uduzanları) | −1,977 | 598,506 |
| − orphan jurnal (açılış yaradılmayıb) | −34,861 | 563,645 |
| − həll olunmayan yazılış (tələbə jurnalda aktiv deyil) | −22,896 | 540,749 |
| **= Gözlənilən hədəf sətri** |  | **540,749** |
| **Hədəfdə FAKTİKİ** |  | **538,457** |
| 🔴 **İZAH OLUNMAMIŞ FƏRQ** |  | **+2,292** |

#### İmtahan xanaları (im / im2)

| Pillə | Dəyişiklik | Qalıq |
|---|---|---|
| Mənbə sətri (xam) | 134,834 |  |
| − boş xana (mənbədə dəyər yoxdur) | −634 | 134,200 |
| − oxunmayan xana (karantin) | −507 | 133,693 |
| − arxiv örtüşməsi (J-V7 kəsimindən sonra) | −2,591 | 131,102 |
| − dublikat xana (J-V4 uduzanları) | −874 | 130,228 |
| − orphan jurnal (açılış yaradılmayıb) | −7,437 | 122,791 |
| − həll olunmayan yazılış (tələbə jurnalda aktiv deyil) | −3,150 | 119,641 |
| **= Gözlənilən hədəf sətri** |  | **119,641** |
| **Hədəfdə FAKTİKİ** |  | **119,084** |
| 🔴 **İZAH OLUNMAMIŞ FƏRQ** |  | **+557** |

#### Qalan izahsız fərq haqqında

Qalıq **+193,516** sətirdir (mənbənin 3.3 %-i).
Bu hesabat onu **fərziyyə ilə bağlamır** — açıq qalıq kimi saxlayır.  Ən ehtimallı
mənbələr (yoxlanılmalıdır, sübut deyil):

1. **Dərs slotu tapılmayan bal xanası** — bir `LessonMark` yalnız mövcud `Lesson`-a
   bağlana bilər; xananın (ay, gün, saat) slotu üçün `journals_dates_added_by_teacher`
   sətri yoxdursa xana yazılmır.  Ledger-də bunun izi: `legacy_journal_lesson_orphan` = 61,319.
2. **Hədəf toqquşması** — eyni (yazılış, dərs) cütü üçün ikinci xana yazıla bilmir (`legacy_journal_mark_target_conflict` = 261).
3. **Üzrlü qayıb çevrilməsi** — `excusable` bayrağı olan xanalar `excused` statusuna düşür (`legacy_journal_mark_excused` = 1,375).

Növbəti addım: bu üç ehtimalı ayrıca sorğu ilə ölçüb nərdivana yeni pillə kimi əlavə etmək.

#### ⚠️ Heç bir domenə düşməyən xanalar

Mənbədə **4,659** xananın `month_id` kodu nə təqvim ayı, nə
`k1/k2/k3/si`, nə də `im/im2`-dir.  İmport-un say balansı bu sətirləri
tamamilə kənarda saxlayır — bu hesabat onları GÖRÜNƏN edir.

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
| Tələbə (auth.user) | 7,816 | 8,443 | +627 | Hədəfə müəllim/işçi hesabları da daxildir — aşağıdakı rol cədvəlinə bax. |
| Müəllim / işçi | 729 | — | — | Rol cədvəlində ayrıca görünür. |
| Jurnal → açılış (CourseOffering) | 13,875 | 11,115 | -2,760 | ⚠️ Gözləntinin ƏKSİ: eyni fənn+qrup+dövr üçün bir neçə legacy jurnal BİR açılışa BİRLƏŞİR (`legacy_journal_offering_merged`) → hədəfdə AZ olur, çox yox. |
| Dərs (Lesson) | 379,215 | 293,070 | -86,145 | Eyni slot üçün bir neçə müəllim sətri bir dərsə düşür (`legacy_journal_lesson_duplicate`) → hədəfdə az olur. |
| Yekun cədvəli (`yekun`) | 17,194 | 114,021 | +96,827 | Hədəfdə FinalGrade jurnalın `im` xanasından da doğur — `yekun` cədvəli yeganə mənbə deyil. |
| Təqvim xanaları (davamiyyət + gündəlik bal) | 5,070,824 | 3,711,153 | -1,359,671 | Nərdivan üçün §1.3-ə bax. |
| Komponent xanaları (kollokvium + sərbəst iş) | 701,005 | 538,457 | -162,548 | Nərdivan üçün §1.3-ə bax. |
| İmtahan xanaları (im / im2) | 134,834 | 119,084 | -15,750 | Nərdivan üçün §1.3-ə bax. |

### Hədəf tərəfdə rol üzrə üzvlüklər

Məzun / qeyri-aktiv tələbələr **arxiv üzvlüyü** kimi köçür — hesabdan silinmir,
sadəcə `is_active = false` olur.

| Rol | Aktiv üzvlük | Arxiv (qeyri-aktiv) |
|---|---|---|
| `student` | 5,214 | 13 |
| `alumni` | 2,490 | 0 |
| `teacher` | 716 | 0 |
| `rector` | 1 | 0 |
| `ikt_rehber` | 1 | 0 |
| `program_coordinator` | 1 | 0 |
| `dean` | 1 | 0 |
| `exam_center` | 1 | 0 |
| `chair_head` | 1 | 0 |

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

### Nümunənin bir baxışda mənzərəsi

| Tələbə | Legacy ID | Qrup | Üzvlük | Fənn (köçən/cəmi) | Nəticə |
|---|---|---|---|---|---|
| Rəcəbli Mehriban | `#1006` | 330 T2 | aktiv | 13/27 | ⚠️ 13/27 fənn köçüb |
| MƏMMƏDOVA MEHRİBAN | `#222` | 531 İ | aktiv | 28/29 | ⚠️ 28/29 fənn köçüb |
| Kərimli Murad | `#2373` | 803/1 BT | aktiv | 0/0 | — jurnal xanası yoxdur |
| NOVRUZİ LƏMAN | `#2962` | 2232 M | aktiv | 46/47 | ⚠️ 46/47 fənn köçüb |
| BAYRAMOV TOĞRUL | `#5992` | 233 İT az | aktiv | 37/39 | ⚠️ 37/39 fənn köçüb |
| Madərov Faiq | `#6838` | 234 İ az | aktiv | 15/20 | ⚠️ 15/20 fənn köçüb |
| Hüseynzadə Fatimə | `#6973` | 234 SBİO İNG | aktiv | 26/31 | ⚠️ 26/31 fənn köçüb |
| ABASOVA JALƏ | `#7292` | 803/4BT | aktiv | 20/22 | ⚠️ 20/22 fənn köçüb |
| ADIGÖZƏLZADƏ GULƏR | `#7399` | 409/4MBA(ing) | aktiv | 0/0 | — jurnal xanası yoxdur |
| Ağazadə Yusif | `#7688` | 3/334F2 | aktiv | 31/31 | ✅ bütün fənlər köçüb |
| dadasev azer | `#7944` | Level 2025-2026 | aktiv | 0/0 | — jurnal xanası yoxdur |
| VƏLİYEV CAMAL | `#7971` | Level 2025-2026 | aktiv | 0/0 | — jurnal xanası yoxdur |
| CƏFƏROVA FATİMƏ | `#7999` | Level 2025-2026 | aktiv | 0/0 | — jurnal xanası yoxdur |
| MİRZƏYEVA FİRUZA | `#8022` | Level 2025-2026 | aktiv | 0/0 | — jurnal xanası yoxdur |
| QASIMOVA LƏMAN | `#8070` | Level 2025-2026 | aktiv | 0/0 | — jurnal xanası yoxdur |
| HÜSEYNOVA NƏRMİN | `#8137` | Level 2025-2026 | aktiv | 0/0 | — jurnal xanası yoxdur |
| əliyev kənan | `#8165` | Level 2025-2026 | aktiv | 0/0 | — jurnal xanası yoxdur |
| Əliyev Yavər | `#8255` | 235 EKO | aktiv | 14/14 | ✅ bütün fənlər köçüb |
| Yusifov Kamal | `#9042` | 635 2 | aktiv | 13/14 | ⚠️ 13/14 fənn köçüb |
| Cəfərli Rüqəyya | `#9313` | 235 CM | aktiv | 0/6 | 🔴 heç bir fənn köçməyib |

### Rəcəbli Mehriban — legacy `#1006` → `auth.user #952`

| Sahə | Köhnə (MyEdu) | Yeni (EMS Arena) |
|---|---|---|
| Ad, soyad | Rəcəbli Mehriban | Rəcəbli Mehriban |
| Qrup | 330 T2 | 330 T2 |
| İxtisas / proqram | Tərcümə | Tərcümə |
| Statusu | — | enrolled (aktiv üzvlük) |

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
| Peşəkar tərcümənin əsasları | köhnə | 0 | 24 | 24 | 10 | — | — | — | 🔴 |
|  | yeni | 0 | 7 | 24 | 10 | — | 31 | 31 |  |
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
| İnsan haqları hüququ | köhnə | 1 | 18 | 25 | 10 | — | — | — | 🔴 |
|  | yeni | 0 | 0 | 25 | 10 | — | 25 | 25 |  |
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

### MƏMMƏDOVA MEHRİBAN — legacy `#222` → `auth.user #207`

| Sahə | Köhnə (MyEdu) | Yeni (EMS Arena) |
|---|---|---|
| Ad, soyad | MƏMMƏDOVA MEHRİBAN | MƏMMƏDOVA MEHRİBAN |
| Qrup | 531 İ | 531 İ |
| İxtisas / proqram | İqtisadiyyat | İqtisadiyyat |
| Statusu | — | enrolled (aktiv üzvlük) |

| Fənn | Tərəf | Qayıb | Seminar bal | Kollokvium | Sərbəst iş | İmtahan | Giriş balı | Yekun | ⚑ |
|---|---|---|---|---|---|---|---|---|---|
| Əməyin iqtisadiyyatı | köhnə | 2 | 16 | 25 | 9 | 32 | — | — | ✅ |
|  | yeni | 2 | 16 | 25 | 9 | 32 | 41 | 73 |  |
| Beynelxalq iqtisadi təşkilatlar | köhnə | 0 | 23 | 24 | 9 | 16 | — | — | 🔴 |
|  | yeni | 0 | 23 | 24 | 9 | 24 | 47 | 71 |  |
| Fəlsəfə | köhnə | 1 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 1 | 8 | 22 | 8 | 31 | 30 | 61 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Rəqəmsal iqtisadiyyat (sahə iqtisadiyyatı) | köhnə | 1 | 24 | 25 | 9 | 28 | — | — | ✅ |
|  | yeni | 1 | 24 | 25 | 9 | 28 | 49 | 77 |  |
| Fəlsəfə | köhnə | 1 | 8 | 22 | 8 | 31 | — | — | ↔ birləşmə |
|  | yeni | 1 | 8 | 22 | 8 | 31 | 30 | 61 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Menecment | köhnə | 0 | 23 | 25 | 8 | 14 | — | — | ✅ |
|  | yeni | 0 | 23 | 25 | 8 | 14 | 48 | 62 |  |
| İqtisadi fikir tarixi | köhnə | 1 | 24 | 13 | 9 | 17 | 37 | 54 | ✅ |
|  | yeni | 1 | 24 | 13 | 9 | 17 | 37 | 54 |  |
| Mülki müdafiə | köhnə | 0 | 7 | 18 | 7 | 41 | 36 | 77 | 🔴 |
|  | yeni | 0 | 7 | 18 | 7 | 41 | 25 | 66 |  |
| Mikroiqtisadiyyat | köhnə | 2 | 21 | 20 | 7 | 35 | 37 | 72 | 🔴 |
|  | yeni | 2 | 21 | 20 | 7 | 35 | 41 | 76 |  |
| İKT-baza komputer bilikləri | köhnə | 4 | 11 | 17 | 8 | — | — | — | 🔴 |
|  | yeni | 0 | 6 | 17 | 8 | — | 23 | 23 |  |
| Sığorta və sığortanın təşkili | köhnə | 11 | 27 | 26 | 10 | 42 | — | — | ✅ |
|  | yeni | 11 | 27 | 26 | 10 | 42 | 50 | 92 |  |
| Müəssisənin iqtisadiyyatı | köhnə | 4 | 27 | 22 | 9 | 31 | — | — | ✅ |
|  | yeni | 4 | 27 | 22 | 9 | 31 | 49 | 80 |  |
| Sosial sahələrin iqtisadiyyatı | köhnə | 2 | 26 | 28 | 10 | 28 | — | — | ✅ |
|  | yeni | 2 | 26 | 28 | 10 | 28 | 50 | 78 |  |
| Biznes etikası | köhnə | 3 | 26 | 23 | 9 | 34 | — | — | ✅ |
|  | yeni | 3 | 26 | 23 | 9 | 34 | 49 | 83 |  |
| Makroiqtisadiyyat | köhnə | 1 | 18 | 20 | 7 | 43 | — | — | ↔ birləşmə |
|  | yeni | 1 | 18 | 20 | 7 | 43 | 38 | 81 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Statistika | köhnə | 3 | 29 | 17 | 8 | 19 | 35 | 54 | 🔴 |
|  | yeni | 3 | 29 | 17 | 8 | 19 | 46 | 65 |  |
| Makroiqtisadiyyat | köhnə | 0 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 1 | 18 | 20 | 7 | 43 | 38 | 81 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| İqtisadiyyatın tənzimlənməsi | köhnə | 7 | 15 | 23 | 6 | 23 | — | — | ✅ |
|  | yeni | 7 | 15 | 23 | 6 | 23 | 38 | 61 |  |
| Azad iqtisadi zonaların milli iqtisadiyyata təsiri | köhnə | 4 | 26 | 27 | 10 | 44 | — | — | ✅ |
|  | yeni | 4 | 26 | 27 | 10 | 44 | 50 | 94 |  |
| Şirkətlərin korporative məsuliyyəti | köhnə | 3 | 14 | 24 | 9 | 34 | — | — | ✅ |
|  | yeni | 3 | 14 | 24 | 9 | 34 | 38 | 72 |  |
| İnkişaf iqtisadiyyatı | köhnə | 7 | 25 | 25 | 8 | 19 | — | — | ✅ |
|  | yeni | 7 | 25 | 25 | 8 | 19 | 50 | 69 |  |
| Menecment | köhnə | 1 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Ekonometrika | köhnə | 1 | 26 | 18 | 8 | 6 | — | — | 🔴 |
|  | yeni | 1 | 26 | 18 | 8 | 17 | 44 | 61 |  |
| Beynəlxalq iqtisadiyyat | köhnə | 1 | 27 | 25 | 8 | 20 | — | — | ✅ |
|  | yeni | 1 | 27 | 25 | 8 | 20 | 50 | 70 |  |
| İnformasiya texnologiyaları (ixtisas üzrə) | köhnə | 14 | 0 | 0 | 0 | — | — | — | ✅ |
|  | yeni | 14 | 0 | 0 | 0 | — | 0 | 0 |  |
| Ətraf mühitin iqtisadiyyati | köhnə | 4 | 27 | 28 | 10 | 26 | — | — | ✅ |
|  | yeni | 4 | 27 | 28 | 10 | 26 | 50 | 76 |  |
| Marketinq | köhnə | 2 | 24 | 24 | 9 | 46 | — | — | ✅ |
|  | yeni | 2 | 24 | 24 | 9 | 46 | 48 | 94 |  |
| Xarici dildə işgüzar və akademik kommunikasiya | köhnə | 1 | 7 | 15 | 8 | 37 | 23 | 60 | 🔴 |
|  | yeni | 1 | 7 | 15 | 8 | 37 | 22 | 59 |  |
| Transmilli korporasiyalar | köhnə | 4 | 24 | 24 | 8 | 19 | — | — | ✅ |
|  | yeni | 4 | 24 | 24 | 8 | 19 | 48 | 67 |  |

### Kərimli Murad — legacy `#2373` → `auth.user #2223`

| Sahə | Köhnə (MyEdu) | Yeni (EMS Arena) |
|---|---|---|
| Ad, soyad | Kərimli Murad | Kərimli Murad |
| Qrup | 803/1 BT | 803/1 BT |
| İxtisas / proqram | Magistratura və doktorantura | Magistratura və doktorantura |
| Statusu | — | enrolled (aktiv üzvlük) |

> Bu tələbə üçün jurnal xanası tapılmadı.

### NOVRUZİ LƏMAN — legacy `#2962` → `auth.user #2783`

| Sahə | Köhnə (MyEdu) | Yeni (EMS Arena) |
|---|---|---|
| Ad, soyad | NOVRUZİ LƏMAN | NOVRUZİ LƏMAN |
| Qrup | 2232 M | 2232 M |
| İxtisas / proqram | Meşəçilik | Meşəçilik |
| Statusu | — | enrolled (aktiv üzvlük) |

| Fənn | Tərəf | Qayıb | Seminar bal | Kollokvium | Sərbəst iş | İmtahan | Giriş balı | Yekun | ⚑ |
|---|---|---|---|---|---|---|---|---|---|
| İnformatika | köhnə | 0 | 0 | 23 | 10 | 23 | — | — | ↔ birləşmə |
|  | yeni | 0 | 0 | 23 | 10 | 23 | 23 | 46 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Xarici dildə işgüzar və akademik kommunikasiya -3 | köhnə | 0 | 30 | 24 | 10 | 58 | — | — | ✅ |
|  | yeni | 0 | 30 | 24 | 10 | 58 | 50 | 100 |  |
| Botanika | köhnə | 0 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 0 | 0 | 21 | 7 | 11 | 21 | 32 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Azərbaycan dilində işgüzar və akademik kommunikasiya | köhnə | 0 | 5 | 17 | 8 | 18 | — | — | ✅ |
|  | yeni | 0 | 5 | 17 | 8 | 18 | 22 | 40 |  |
| Fitopatologiya | köhnə | 0 | 7 | 21 | 7 | 10 | — | — | ✅ |
|  | yeni | 0 | 7 | 21 | 7 | 10 | 28 | 38 |  |
| Politologiya | köhnə | 1 | 8 | 24 | 10 | 25 | — | — | ✅ |
|  | yeni | 1 | 8 | 24 | 10 | 25 | 32 | 57 |  |
| Qafqazın ekologiyası | köhnə | 0 | 8 | 22 | 8 | 17 | — | — | ✅ |
|  | yeni | 0 | 8 | 22 | 8 | 17 | 30 | 47 |  |
| Oduncaqşünaslıq və meşə əmtəəşünaslığı | köhnə | 0 | 0 | 24 | 8 | 25 | — | — | ✅ |
|  | yeni | 0 | 0 | 24 | 8 | 25 | 24 | 49 |  |
| Azərbaycan tarixi | köhnə | 0 | 0 | 0 | 7 | — | — | — | ↔ birləşmə |
|  | yeni | 0 | 6 | 19 | 7 | 6 | 25 | 31 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Xarici dildə işgüzar və akademik kommunikasiya-2 | köhnə | 1 | 30 | 25 | 10 | 61 | — | — | ✅ |
|  | yeni | 1 | 30 | 25 | 10 | 61 | 50 | 100 |  |
| Fizika | köhnə | 0 | 0 | 24 | 8 | 6 | — | — | ✅ |
|  | yeni | 0 | 0 | 24 | 8 | 6 | 24 | 30 |  |
| Meşələrin ekoloji faydalıqları | köhnə | 0 | 8 | 18 | 5 | 23 | — | — | ✅ |
|  | yeni | 0 | 8 | 18 | 5 | 23 | 26 | 49 |  |
| İnformatika | köhnə | 0 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 0 | 0 | 23 | 10 | 23 | 23 | 46 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Meşəçilik | köhnə | 1 | 0 | 21 | 5 | 20 | — | — | ✅ |
|  | yeni | 1 | 0 | 21 | 5 | 20 | 21 | 41 |  |
| Meşə qanunvericiliyi və idarəçiliyi | köhnə | 3 | 7 | 21 | 7 | — | — | — | ✅ |
|  | yeni | 3 | 7 | 21 | 7 | — | 28 | 28 |  |
| Torpaqşünaslıq | köhnə | 0 | 8 | 21 | 5 | 19 | — | — | ✅ |
|  | yeni | 0 | 8 | 21 | 5 | 19 | 29 | 48 |  |
| Meşə genetikası və seleksiyası | köhnə | 0 | 9 | 27 | 8 | 18 | — | — | ✅ |
|  | yeni | 0 | 9 | 27 | 8 | 18 | 36 | 54 |  |
| Riyaziyyat | köhnə | 0 | 8 | 24 | 10 | 15 | 44 | 62 | 🔴 |
|  | yeni | 0 | 8 | 24 | 10 | 18 | 32 | 50 |  |
| Riyazi statiska | köhnə | 0 | 7 | 20 | 6 | 6 | — | — | ✅ |
|  | yeni | 0 | 7 | 20 | 6 | 6 | 27 | 33 |  |
| Oduncaq xammalının kompleks istifadəsi | köhnə | 1 | 7 | 24 | 7 | 6 | — | — | ✅ |
|  | yeni | 1 | 7 | 24 | 7 | 6 | 31 | 37 |  |
| Botanika | köhnə | 0 | 0 | 21 | 7 | 11 | — | — | ↔ birləşmə |
|  | yeni | 0 | 0 | 21 | 7 | 11 | 21 | 32 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Xarici dildə işgüzar və akademik kommunikasiya | köhnə | 0 | 30 | 26 | 10 | 67 | 49 | 116 | 🔴 |
|  | yeni | 0 | 30 | 26 | 10 | 67 | 50 | 100 |  |
| Meşə maşın və traktorları | köhnə | 0 | 6 | 15 | 6 | 17 | — | — | ✅ |
|  | yeni | 0 | 6 | 15 | 6 | 17 | 21 | 38 |  |
| Meşə təsərrüfatının iqtisadiyyatı, təşkili və idarə olunması | köhnə | 0 | 0 | 21 | 3 | 39 | — | — | ✅ |
|  | yeni | 0 | 0 | 21 | 3 | 39 | 21 | 60 |  |
| Xarici dildə işgüzar və akademik kommunikasiya | köhnə | 36 | 0 | 0 | 0 | 0 | 0 | 0 | 🔴 |
|  | yeni | 36 | 0 | 0 | 0 | — | 0 | 0 |  |
| Meşə entomologiyası | köhnə | 1 | 8 | 21 | 9 | 17 | — | — | ✅ |
|  | yeni | 1 | 8 | 21 | 9 | 17 | 29 | 46 |  |
| Əmək mühafizəsi | köhnə | 1 | 0 | 15 | 6 | 22 | — | — | ✅ |
|  | yeni | 1 | 0 | 15 | 6 | 22 | 15 | 37 |  |
| Meşə taksasiyası | köhnə | 0 | 7 | 18 | 8 | 21 | — | — | ✅ |
|  | yeni | 0 | 7 | 18 | 8 | 21 | 25 | 46 |  |
| Meşə meliorasiyası və qoruyucu meşəsalma | köhnə | 1 | 8 | 24 | 9 | 7 | — | — | ✅ |
|  | yeni | 1 | 8 | 24 | 9 | 7 | 32 | 39 |  |
| Azərbaycan tarixi | köhnə | 0 | 6 | 19 | 0 | 6 | — | — | ↔ birləşmə |
|  | yeni | 0 | 6 | 19 | 7 | 6 | 25 | 31 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Bəzək bağçılığı və peyzaj dizaynı | köhnə | 0 | 5 | 21 | 6 | 18 | — | — | ✅ |
|  | yeni | 0 | 5 | 21 | 6 | 18 | 26 | 44 |  |
| Geodeziya | köhnə | 0 | 9 | 24 | 9 | 23 | — | — | ✅ |
|  | yeni | 0 | 9 | 24 | 9 | 23 | 33 | 56 |  |
| Meteorologiya və iqlimşünaslıq | köhnə | 0 | 8 | 25 | 8 | 12 | 44 | 61 | 🔴 |
|  | yeni | 0 | 8 | 25 | 8 | 17 | 33 | 50 |  |
| Rekreasiya meşəçiliyi | köhnə | 1 | 9 | 27 | 8 | 19 | — | — | ✅ |
|  | yeni | 1 | 9 | 27 | 8 | 19 | 36 | 55 |  |
| Ekologiya | köhnə | 0 | 9 | 24 | 8 | 17 | 44 | 61 | 🔴 |
|  | yeni | 0 | 9 | 24 | 8 | 17 | 33 | 50 |  |
| Ali bitkilərin sistematikası | köhnə | 1 | 6 | 18 | 6 | 17 | — | — | ✅ |
|  | yeni | 1 | 6 | 18 | 6 | 17 | 24 | 41 |  |
| Multikulturalizmə giriş | köhnə | 0 | 9 | 30 | 8 | 24 | — | — | ✅ |
|  | yeni | 0 | 9 | 30 | 8 | 24 | 39 | 63 |  |
| Tingçilik təsərrüfatı | köhnə | 3 | 7 | 24 | 10 | — | — | — | ✅ |
|  | yeni | 3 | 7 | 24 | 10 | — | 31 | 31 |  |
| Meşəbərpa işləri | köhnə | 2 | 0 | 21 | 7 | 18 | — | — | ✅ |
|  | yeni | 2 | 0 | 21 | 7 | 18 | 21 | 39 |  |
| Dendrologiya | köhnə | 0 | 23 | 23 | 8 | 21 | — | — | ✅ |
|  | yeni | 0 | 23 | 23 | 8 | 21 | 46 | 67 |  |
| Ümumi kimya | köhnə | 1 | 9 | 24 | 8 | 11 | — | — | ✅ |
|  | yeni | 1 | 9 | 24 | 8 | 11 | 33 | 44 |  |
| Əməyin mühafizəsi | köhnə | 0 | 0 | 0 | 0 | — | — | — | ✅ |
|  | yeni | 0 | 0 | 0 | 0 | — | 0 | 0 |  |
| Xarici dildə işgüzar və akademik kommunikasiya | köhnə | 7 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Meşə yanğınları | köhnə | 1 | 0 | 24 | 8 | 24 | — | — | ✅ |
|  | yeni | 1 | 0 | 24 | 8 | 24 | 24 | 48 |  |
| Ümumi əkinçilik | köhnə | 0 | 9 | 21 | 9 | 17 | — | — | ✅ |
|  | yeni | 0 | 9 | 21 | 9 | 17 | 30 | 47 |  |
| Təsərrüfatların intensiv idarə edilməsi | köhnə | 0 | 0 | 21 | 7 | 19 | — | — | ✅ |
|  | yeni | 0 | 0 | 21 | 7 | 19 | 21 | 40 |  |
| Meşə əkinləri | köhnə | 2 | 13 | 19 | 7 | 7 | — | — | ✅ |
|  | yeni | 2 | 13 | 19 | 7 | 7 | 32 | 39 |  |

### BAYRAMOV TOĞRUL — legacy `#5992` → `auth.user #3859`

| Sahə | Köhnə (MyEdu) | Yeni (EMS Arena) |
|---|---|---|
| Ad, soyad | BAYRAMOV TOĞRUL | BAYRAMOV TOĞRUL |
| Qrup | 233 İT az | 233 İT az |
| İxtisas / proqram | İnformasiya Texnologiyaları | İnformasiya Texnologiyaları |
| Statusu | — | enrolled (aktiv üzvlük) |

| Fənn | Tərəf | Qayıb | Seminar bal | Kollokvium | Sərbəst iş | İmtahan | Giriş balı | Yekun | ⚑ |
|---|---|---|---|---|---|---|---|---|---|
| İnformasiya texnologiyalarının əsasları | köhnə | 0 | 38 | 25 | 10 | 17 | — | — | ✅ |
|  | yeni | 0 | 38 | 25 | 10 | 17 | 50 | 67 |  |
| Diferensial tənliklər | köhnə | 1 | 7 | 15 | 10 | 22 | — | — | ✅ |
|  | yeni | 1 | 7 | 15 | 10 | 22 | 22 | 44 |  |
| Xətti cəbr və analitik həndəsə | köhnə | 0 | 6 | 11 | 7 | 27 | — | — | ✅ |
|  | yeni | 0 | 6 | 11 | 7 | 27 | 17 | 44 |  |
| Azərbaycan Respublikasının konstitusiyası və hüququn əsasları | köhnə | 0 | 8 | 22 | 10 | 24 | — | — | ✅ |
|  | yeni | 0 | 8 | 22 | 10 | 24 | 30 | 54 |  |
| Mülki müdafiə | köhnə | 1 | 5 | 16 | 6 | 34 | — | — | ✅ |
|  | yeni | 1 | 5 | 16 | 6 | 34 | 21 | 55 |  |
| Kompüter şəbəkələri | köhnə | 6 | 31 | 14 | 8 | — | — | — | ↔ birləşmə |
|  | yeni | 5 | 40 | 23 | 8 | 39 | 50 | 89 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Veb proqramlaşdırma | köhnə | 0 | 0 | 25 | 9 | 43 | — | — | ✅ |
|  | yeni | 0 | 0 | 25 | 9 | 43 | 25 | 68 |  |
| Verilənlərin strukturu və alqoritmlər | köhnə | 9 | 0 | 22 | 6 | 31 | — | — | ✅ |
|  | yeni | 9 | 0 | 22 | 6 | 31 | 22 | 53 |  |
| Insan komputer interfeysi | köhnə | 4 | 15 | 24 | 8 | 49 | — | — | ✅ |
|  | yeni | 4 | 15 | 24 | 8 | 49 | 39 | 88 |  |
| Azərbaycan tarixi | köhnə | 5 | 10 | 20 | 8 | 28 | — | — | ✅ |
|  | yeni | 5 | 10 | 20 | 8 | 28 | 30 | 58 |  |
| Ehtimal nəzəriyyəsi və riyazi statistika | köhnə | 1 | 8 | 22 | 8 | 7 | — | — | 🔴 |
|  | yeni | 1 | 8 | 22 | 8 | 24 | 30 | 54 |  |
| İT layihələrin idarəedilməsi | köhnə | 1 | 8 | 25 | 8 | 36 | — | — | ✅ |
|  | yeni | 1 | 8 | 25 | 8 | 36 | 33 | 69 |  |
| Riyazi analiz | köhnə | 10 | 6 | 20 | 7 | 16 | — | — | ✅ |
|  | yeni | 10 | 6 | 20 | 7 | 16 | 26 | 42 |  |
| Fizika | köhnə | 0 | 6 | 0 | 0 | 18 | — | — | ↔ birləşmə |
|  | yeni | 0 | 6 | 18 | 8 | 18 | 24 | 42 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Proqramlaşdırmanın əsasları | köhnə | 3 | 20 | 21 | 8 | 33 | — | — | ✅ |
|  | yeni | 3 | 20 | 21 | 8 | 33 | 41 | 74 |  |
| Diskret riyaziyyat | köhnə | 3 | 7 | 18 | 7 | 34 | — | — | ✅ |
|  | yeni | 3 | 7 | 18 | 7 | 34 | 25 | 59 |  |
| Verilənlərin bazası sistemləri | köhnə | 7 | 17 | 22 | 7 | 48 | — | — | 🔴 |
|  | yeni | 4 | 17 | 22 | 7 | 48 | 39 | 87 |  |
| Bulud texnologiyaları | köhnə | 0 | 6 | 19 | 9 | 37 | — | — | ↔ birləşmə |
|  | yeni | 0 | 6 | 19 | 9 | 37 | 25 | 62 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Sxemotexnikanın əsasları | köhnə | 7 | 8 | 22 | 10 | 20 | — | — | ✅ |
|  | yeni | 7 | 8 | 22 | 10 | 20 | 30 | 50 |  |
| Kompüter şəbəkələri | köhnə | 0 | 9 | 9 | 0 | 39 | — | — | ↔ birləşmə |
|  | yeni | 5 | 40 | 23 | 8 | 39 | 50 | 89 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Veb sistemləri və texnologiyaları | köhnə | 2 | 0 | 17 | 9 | 46 | — | — | ↔ birləşmə |
|  | yeni | 4 | 0 | 26 | 9 | 46 | 26 | 72 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Veb sistemləri və texnologiyaları | köhnə | 2 | 0 | 9 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 4 | 0 | 26 | 9 | 46 | 26 | 72 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Alqoritmləşdirmə və proqramlaşdırma | köhnə | 2 | 15 | 24 | 9 | 18 | — | — | ✅ |
|  | yeni | 2 | 15 | 24 | 9 | 18 | 39 | 57 |  |
| Kompüterlərin diaqnostikası | köhnə | 0 | 5 | 22 | 8 | 30 | — | — | ↔ birləşmə |
|  | yeni | 0 | 5 | 22 | 8 | 30 | 27 | 57 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Xarici dildə işgüzar və akademik kommunikasiya | köhnə | 22 | 18 | 23 | 8 | — | — | — | ✅ |
|  | yeni | 22 | 18 | 23 | 8 | — | 41 | 41 |  |
| Bulud texnologiyaları | köhnə | 0 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 0 | 6 | 19 | 9 | 37 | 25 | 62 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Kompüter arxitekturası | köhnə | 13 | 15 | 22 | 8 | 17 | — | — | ✅ |
|  | yeni | 13 | 15 | 22 | 8 | 17 | 37 | 54 |  |
| Fizika | köhnə | 0 | 0 | 18 | 8 | 18 | — | — | ↔ birləşmə |
|  | yeni | 0 | 6 | 18 | 8 | 18 | 24 | 42 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Azərbaycan dilində işgüzar və akademik kommunikasiya | köhnə | 1 | 14 | 20 | 10 | 31 | — | — | ✅ |
|  | yeni | 1 | 14 | 20 | 10 | 31 | 34 | 65 |  |
| Kibertəhlükəsizliyin təmin edilməsi yolları | köhnə | 0 | 9 | 25 | 8 | 45 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Proqramlaşdırma texnologiyaları | köhnə | 4 | 7 | 23 | 6 | 43 | — | — | ✅ |
|  | yeni | 4 | 7 | 23 | 6 | 43 | 30 | 73 |  |
| Xarici dildə işgüzar və akademik kommunikasiya | köhnə | 5 | 35 | 26 | 10 | — | — | — | ✅ |
|  | yeni | 5 | 35 | 26 | 10 | — | 50 | 50 |  |
| İnformasiya təhlükəsizliyi | köhnə | 3 | 8 | 24 | 9 | 50 | — | — | ✅ |
|  | yeni | 3 | 8 | 24 | 9 | 50 | 32 | 82 |  |
| Azərbaycan Respublikasının konstitusiyası və hüququn əsasları | köhnə | 0 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Kompüterlərin diaqnostikası | köhnə | 0 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 0 | 5 | 22 | 8 | 30 | 27 | 57 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Lazer və onun istifadəsi | köhnə | 5 | 0 | 22 | 10 | 44 | — | — | ✅ |
|  | yeni | 5 | 0 | 22 | 10 | 44 | 22 | 66 |  |
| Multimedia texnologiyaları | köhnə | 2 | 8 | 24 | 10 | 27 | — | — | ✅ |
|  | yeni | 2 | 8 | 24 | 10 | 27 | 32 | 59 |  |
| Qərarqəbuletmənin intellektual texnologiyaları | köhnə | 2 | 9 | 25 | 10 | 36 | — | — | ✅ |
|  | yeni | 2 | 9 | 25 | 10 | 36 | 34 | 70 |  |
| Əməliyyat sistemləri | köhnə | 7 | 23 | 24 | 8 | 36 | — | — | ✅ |
|  | yeni | 7 | 23 | 24 | 8 | 36 | 47 | 83 |  |

### Madərov Faiq — legacy `#6838` → `auth.user #4598`

| Sahə | Köhnə (MyEdu) | Yeni (EMS Arena) |
|---|---|---|
| Ad, soyad | Madərov Faiq | Madərov Faiq |
| Qrup | 234 İ az | 234 İ az |
| İxtisas / proqram | İnformasiya Təhlükəsizliyi | İnformasiya Təhlükəsizliyi |
| Statusu | — | enrolled (aktiv üzvlük) |

| Fənn | Tərəf | Qayıb | Seminar bal | Kollokvium | Sərbəst iş | İmtahan | Giriş balı | Yekun | ⚑ |
|---|---|---|---|---|---|---|---|---|---|
| İnformasiya təhlükəsizliyinin əsasları | köhnə | 3 | 20 | 28 | 10 | 49 | — | — | ✅ |
|  | yeni | 3 | 20 | 28 | 10 | 49 | 48 | 97 |  |
| Ehtimal nəzəriyyəsi | köhnə | 3 | 17 | 18 | 9 | 20 | — | — | ✅ |
|  | yeni | 3 | 17 | 18 | 9 | 20 | 35 | 55 |  |
| Kiber risklərin idarə olunması | köhnə | 5 | 10 | 28 | 10 | 44 | — | — | ✅ |
|  | yeni | 5 | 10 | 28 | 10 | 44 | 38 | 82 |  |
| informasiya təhlükəsizliyi və kibertəhlükəsizliyin hüquqi aspektləri | köhnə | 4 | 10 | 30 | 10 | 41 | — | — | ✅ |
|  | yeni | 4 | 10 | 30 | 10 | 41 | 40 | 81 |  |
| şəbəkələrin təhlükəsizliyi | köhnə | 2 | 28 | 27 | 10 | 36 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Xətti cəbr | köhnə | 7 | 6 | 19 | 7 | 22 | — | — | ✅ |
|  | yeni | 7 | 6 | 19 | 7 | 22 | 25 | 47 |  |
| Proqramlaşdırmanın əsasları | köhnə | 4 | 0 | 20 | 7 | 43 | — | — | ✅ |
|  | yeni | 4 | 0 | 20 | 7 | 43 | 20 | 63 |  |
| Xarici dildə işgüzar akademik kommunikasiya-2(pre-intermediate) | köhnə | 14 | 18 | 23 | 9 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Kibertəhlükəsizliyin əsasları | köhnə | 5 | 10 | 29 | 10 | 49 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Azərbaycan tarixi | köhnə | 5 | 18 | 30 | 10 | 35 | — | — | ✅ |
|  | yeni | 5 | 18 | 30 | 10 | 35 | 48 | 83 |  |
| Diskret riyaziyyat | köhnə | 3 | 8 | 24 | 7 | 42 | — | — | ✅ |
|  | yeni | 3 | 8 | 24 | 7 | 42 | 32 | 74 |  |
| Əməliyyat sistemləri | köhnə | 2 | 8 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Xarici dildə işgüzar və akademik kommunikasiya | köhnə | 9 | 22 | 16 | 7 | — | — | — | ✅ |
|  | yeni | 9 | 22 | 16 | 7 | — | 38 | 38 |  |
| Sosial mühəndislik | köhnə | 3 | 0 | 23 | 10 | 36 | — | — | ✅ |
|  | yeni | 3 | 0 | 23 | 10 | 36 | 23 | 59 |  |
| Azərbaycan dilində işgüzar və akademik kommunikasiya | köhnə | 0 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Sistem dizaynı | köhnə | 4 | 0 | 27 | 10 | 44 | — | — | ✅ |
|  | yeni | 4 | 0 | 27 | 10 | 44 | 27 | 71 |  |
| Veb təhlükəsizliyi | köhnə | 3 | 9 | 27 | 10 | 37 | — | — | ✅ |
|  | yeni | 3 | 9 | 27 | 10 | 37 | 36 | 73 |  |
| Zərərverici proqram vasitələrinin təhlili | köhnə | 4 | 25 | 30 | 10 | 48 | — | — | ✅ |
|  | yeni | 4 | 25 | 30 | 10 | 48 | 50 | 98 |  |
| Riyazi analiz | köhnə | 5 | 3 | 16 | 9 | 14 | — | — | ✅ |
|  | yeni | 5 | 3 | 16 | 9 | 14 | 19 | 33 |  |
| C proqramlaşdırma dili | köhnə | 3 | 49 | 28 | 7 | 26 | — | — | 🔴 |
|  | yeni | 3 | 39 | 28 | 7 | 26 | 50 | 76 |  |

### Hüseynzadə Fatimə — legacy `#6973` → `auth.user #4731`

| Sahə | Köhnə (MyEdu) | Yeni (EMS Arena) |
|---|---|---|
| Ad, soyad | Hüseynzadə Fatimə | Hüseynzadə Fatimə |
| Qrup | 234 SBİO İNG | 234 SBİO İNG |
| İxtisas / proqram | Su Bioehtiyyatları və Akvakultura | Su Bioehtiyyatları və Akvakultura |
| Statusu | — | enrolled (aktiv üzvlük) |

| Fənn | Tərəf | Qayıb | Seminar bal | Kollokvium | Sərbəst iş | İmtahan | Giriş balı | Yekun | ⚑ |
|---|---|---|---|---|---|---|---|---|---|
| Xüsusi xarici dil | köhnə | 0 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Su bitkilərinin fiziologiyası | köhnə | 0 | 24 | 22 | 9 | 18 | — | — | ↔ birləşmə |
|  | yeni | 1 | 24 | 22 | 9 | 18 | 46 | 64 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Su bitkilərinin fiziologiyası | köhnə | 1 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 1 | 24 | 22 | 9 | 18 | 46 | 64 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| İnformatika | köhnə | 3 | 8 | 26 | 8 | 41 | — | — | ↔ birləşmə |
|  | yeni | 3 | 8 | 26 | 8 | 41 | 34 | 75 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Zoologiya | köhnə | 0 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Xarici dildə işgüzar və akademik kommunikasiya | köhnə | 9 | 0 | 6 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Xarici dildə işgüzar akademik kommunikasiya-2(pre-intermediate) | köhnə | 7 | 43 | 20 | 10 | — | — | — | ✅ |
|  | yeni | 7 | 43 | 20 | 10 | — | 50 | 50 |  |
| Botanika | köhnə | 3 | 23 | 26 | 9 | 33 | — | — | ✅ |
|  | yeni | 3 | 23 | 26 | 9 | 33 | 49 | 82 |  |
| Mülki müdafiə | köhnə | 2 | 16 | 12 | 8 | 21 | — | — | ✅ |
|  | yeni | 2 | 16 | 12 | 8 | 21 | 28 | 49 |  |
| Planktonologiya | köhnə | 5 | 50 | 24 | 10 | 31 | — | — | ✅ |
|  | yeni | 5 | 50 | 24 | 10 | 31 | 50 | 81 |  |
| Təbiətdən səmərəli istifadə | köhnə | 4 | 8 | 24 | 10 | 29 | — | — | ✅ |
|  | yeni | 4 | 8 | 24 | 10 | 29 | 32 | 61 |  |
| Ekologiya | köhnə | 2 | 15 | 22 | 8 | 32 | — | — | ✅ |
|  | yeni | 2 | 15 | 22 | 8 | 32 | 37 | 69 |  |
| Riyaziyyat | köhnə | 3 | 25 | 17 | 10 | 23 | — | — | ✅ |
|  | yeni | 3 | 25 | 17 | 10 | 23 | 42 | 65 |  |
| Azərbaycan tarixi | köhnə | 1 | 19 | 25 | 10 | 26 | — | — | ✅ |
|  | yeni | 1 | 19 | 25 | 10 | 26 | 44 | 70 |  |
| İnformatika | köhnə | 0 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 3 | 8 | 26 | 8 | 41 | 34 | 75 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Su çirklənməsi və ona nəzarət | köhnə | 6 | 29 | 30 | 10 | 45 | — | — | ✅ |
|  | yeni | 6 | 29 | 30 | 10 | 45 | 50 | 95 |  |
| Su toksikologiyası | köhnə | 0 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Zoologiya | köhnə | 7 | 25 | 16 | 10 | 33 | — | — | ✅ |
|  | yeni | 7 | 25 | 16 | 10 | 33 | 41 | 74 |  |
| İxtisasa giriş və ixtisasın inkişaf tarixi | köhnə | 0 | 27 | 23 | 9 | 19 | — | — | ✅ |
|  | yeni | 0 | 27 | 23 | 9 | 19 | 50 | 69 |  |
| Su toksikologiyası | köhnə | 6 | 26 | 22 | 9 | 23 | — | — | ✅ |
|  | yeni | 6 | 26 | 22 | 9 | 23 | 48 | 71 |  |
| Xüsusi xarici dil | köhnə | 3 | 0 | 10 | 10 | 25 | — | — | ↔ birləşmə |
|  | yeni | 4 | 27 | 23 | 10 | 25 | 50 | 75 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Ümumi kimya | köhnə | 1 | 14 | 13 | 5 | 8 | — | — | 🔴 |
|  | yeni | 1 | 14 | 13 | 5 | 38 | 27 | 65 |  |
| Xüsusi xarici dil | köhnə | 1 | 27 | 13 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 4 | 27 | 23 | 10 | 25 | 50 | 75 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Fizika | köhnə | 0 | 16 | 24 | 8 | 26 | — | — | ✅ |
|  | yeni | 0 | 16 | 24 | 8 | 26 | 40 | 66 |  |
| Ümumi biologiya | köhnə | 1 | 37 | 22 | 9 | 19 | — | — | ✅ |
|  | yeni | 1 | 37 | 22 | 9 | 19 | 50 | 69 |  |
| Xarici dildə işgüzar və akademik kommunikasiya | köhnə | 1 | 27 | 24 | 10 | — | — | — | ✅ |
|  | yeni | 1 | 27 | 24 | 10 | — | 50 | 50 |  |
| Biokimya | köhnə | 4 | 6 | 19 | 9 | 18 | — | — | ✅ |
|  | yeni | 4 | 6 | 19 | 9 | 18 | 25 | 43 |  |
| Azərbaycan dilində işgüzar və akademik kommunikasiya | köhnə | 0 | 17 | 25 | 9 | 29 | — | — | ✅ |
|  | yeni | 0 | 17 | 25 | 9 | 29 | 42 | 71 |  |
| Əmək mühafizəsi | köhnə | 4 | 29 | 17 | 9 | 28 | — | — | ✅ |
|  | yeni | 4 | 29 | 17 | 9 | 28 | 46 | 74 |  |
| Azərbaycan Respublikasının konstitusiyası və hüququn əsasları | köhnə | 3 | 10 | 27 | 10 | 34 | — | — | ✅ |
|  | yeni | 3 | 10 | 27 | 10 | 34 | 37 | 71 |  |
| Ekologiya | köhnə | 0 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |

### ABASOVA JALƏ — legacy `#7292` → `auth.user #5046`

| Sahə | Köhnə (MyEdu) | Yeni (EMS Arena) |
|---|---|---|
| Ad, soyad | ABASOVA JALƏ | ABASOVA JALƏ |
| Qrup | 803/4BT | 803/4BT |
| İxtisas / proqram | Turizm işinin təşkili | Turizm işinin təşkili |
| Statusu | — | enrolled (aktiv üzvlük) |

| Fənn | Tərəf | Qayıb | Seminar bal | Kollokvium | Sərbəst iş | İmtahan | Giriş balı | Yekun | ⚑ |
|---|---|---|---|---|---|---|---|---|---|
| Azərbaycan turizminin inkişaf perspektivləri | köhnə | 0 | 10 | 28 | 10 | 46 | — | — | ✅ |
|  | yeni | 0 | 10 | 28 | 10 | 46 | 38 | 84 |  |
| Psixologiya | köhnə | 1 | 0 | 26 | 10 | 23 | — | — | ✅ |
|  | yeni | 1 | 0 | 26 | 10 | 23 | 26 | 49 |  |
| Beynelxalq turizm şirkətlərinin fəaliyyət mexanizmi | köhnə | 2 | 7 | 29 | 10 | 37 | — | — | ✅ |
|  | yeni | 2 | 7 | 29 | 10 | 37 | 36 | 73 |  |
| Ali məktəb pedaqogikası | köhnə | 1 | 9 | 25 | 9 | 35 | — | — | ✅ |
|  | yeni | 1 | 9 | 25 | 9 | 35 | 34 | 69 |  |
| Beynəlxalq turizm sferasında risklər və sığortalanma | köhnə | 0 | 0 | 29 | 10 | 39 | — | — | ✅ |
|  | yeni | 0 | 0 | 29 | 10 | 39 | 29 | 68 |  |
| Vergi menecmenti | köhnə | 3 | 0 | 27 | 9 | 29 | — | — | ✅ |
|  | yeni | 3 | 0 | 27 | 9 | 29 | 27 | 56 |  |
| Rəqəmsal marketing | köhnə | 1 | 0 | 24 | 7 | 42 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Beynəlxalq maliyyə hesabat standartlarının tətbiqi | köhnə | 0 | 0 | 17 | 8 | 26 | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Xarici dil | köhnə | 5 | 7 | 21 | 8 | 20 | — | — | ✅ |
|  | yeni | 5 | 7 | 21 | 8 | 20 | 28 | 48 |  |
| Təşkilati davranış | köhnə | 0 | 0 | 18 | 8 | 18 | — | — | ✅ |
|  | yeni | 0 | 0 | 18 | 8 | 18 | 18 | 36 |  |
| Beynəlxalq turizm ehtiyatlarının qiymətləndirilməsi | köhnə | 2 | 8 | 29 | 10 | 38 | — | — | ✅ |
|  | yeni | 2 | 8 | 29 | 10 | 38 | 37 | 75 |  |
| Beynəlxalq və milli turizm tarixi | köhnə | 0 | 10 | 30 | 10 | 38 | — | — | ✅ |
|  | yeni | 0 | 10 | 30 | 10 | 38 | 40 | 78 |  |
| Turizm menecmenti | köhnə | 0 | 10 | 30 | 10 | 29 | — | — | ✅ |
|  | yeni | 0 | 10 | 30 | 10 | 29 | 40 | 69 |  |
| Turizmin, turizm sənayesinin tarixi və metodologiyası | köhnə | 0 | 0 | 30 | 10 | 31 | — | — | ✅ |
|  | yeni | 0 | 0 | 30 | 10 | 31 | 30 | 61 |  |
| Hüquq coğrafiyası | köhnə | 3 | 20 | 26 | 9 | 34 | — | — | ✅ |
|  | yeni | 3 | 20 | 26 | 9 | 34 | 46 | 80 |  |
| beynəlxalq turizm və ətraf mühitin mühafizəsi | köhnə | 2 | 10 | 30 | 10 | 46 | — | — | ✅ |
|  | yeni | 2 | 10 | 30 | 10 | 46 | 40 | 86 |  |
| Turizm ,mehmanxana və restoran biznesinin təşkili | köhnə | 2 | 9 | 26 | 10 | 42 | — | — | ✅ |
|  | yeni | 2 | 9 | 26 | 10 | 42 | 35 | 77 |  |
| İnsan resusrlarından istifadənin optimallaşdırılması | köhnə | 0 | 20 | 29 | 10 | 42 | — | — | ✅ |
|  | yeni | 0 | 20 | 29 | 10 | 42 | 49 | 91 |  |
| Beynəlxalq turizm fəaliyyətinin təşkili | köhnə | 0 | 0 | 30 | 9 | 32 | — | — | ✅ |
|  | yeni | 0 | 0 | 30 | 9 | 32 | 30 | 62 |  |
| Turizmdə marketinq konsepsiyası | köhnə | 1 | 9 | 29 | 10 | 37 | — | — | ✅ |
|  | yeni | 1 | 9 | 29 | 10 | 37 | 38 | 75 |  |
| Turizmin hüquqi əsasları | köhnə | 1 | 10 | 25 | 10 | 31 | — | — | ✅ |
|  | yeni | 1 | 10 | 25 | 10 | 31 | 35 | 66 |  |
| Turizmin ,turizm sənayesinin müasir problemləri | köhnə | 1 | 0 | 23 | 10 | 30 | — | — | ✅ |
|  | yeni | 1 | 0 | 23 | 10 | 30 | 23 | 53 |  |

### ADIGÖZƏLZADƏ GULƏR — legacy `#7399` → `auth.user #5153`

| Sahə | Köhnə (MyEdu) | Yeni (EMS Arena) |
|---|---|---|
| Ad, soyad | ADIGÖZƏLZADƏ GULƏR | ADIGÖZƏLZADƏ GULƏR |
| Qrup | 409/4MBA(ing) | 409/4MBA(ing) |
| İxtisas / proqram | Biznesin idarə edilməsi | Biznesin idarə edilməsi |
| Statusu | — | enrolled (aktiv üzvlük) |

> Bu tələbə üçün jurnal xanası tapılmadı.

### Ağazadə Yusif — legacy `#7688` → `auth.user #5440`

| Sahə | Köhnə (MyEdu) | Yeni (EMS Arena) |
|---|---|---|
| Ad, soyad | Ağazadə Yusif | Ağazadə Yusif |
| Qrup | 3/334F2 | 3/334F2 |
| İxtisas / proqram | Azərbaycan dili və ədəbiyyatı | Azərbaycan dili və ədəbiyyatı |
| Statusu | — | enrolled (aktiv üzvlük) |

| Fənn | Tərəf | Qayıb | Seminar bal | Kollokvium | Sərbəst iş | İmtahan | Giriş balı | Yekun | ⚑ |
|---|---|---|---|---|---|---|---|---|---|
| Dünya ədəbiyyatı - 2 (XVII-XIX əsr) | köhnə | 0 | 8 | 19 | 8 | 22 | — | — | ✅ |
|  | yeni | 0 | 8 | 19 | 8 | 22 | 27 | 49 |  |
| Şifahi xalq ədəbiyyatı(ixtisas ölkələri üzrə) | köhnə | 0 | 6 | 17 | 8 | 18 | — | — | ✅ |
|  | yeni | 0 | 6 | 17 | 8 | 18 | 23 | 41 |  |
| Mifologiya | köhnə | 0 | 13 | 19 | 8 | 17 | — | — | ✅ |
|  | yeni | 0 | 13 | 19 | 8 | 17 | 32 | 49 |  |
| Azərbaycan dialektologiyası | köhnə | 1 | 8 | 23 | 9 | 18 | — | — | ✅ |
|  | yeni | 1 | 8 | 23 | 9 | 18 | 31 | 49 |  |
| Xarici dildə işgüzar və akademik kommunikasiya-1 | köhnə | 0 | 75 | 28 | 10 | — | — | — | ✅ |
|  | yeni | 0 | 75 | 28 | 10 | — | 50 | 50 |  |
| Dil tarixi | köhnə | 0 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 0 | 15 | 21 | 10 | 17 | 36 | 53 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Dünya ədəbiyyatı - 1 (Qədim dövr) | köhnə | 0 | 20 | 22 | 10 | 35 | — | — | ✅ |
|  | yeni | 0 | 20 | 22 | 10 | 35 | 42 | 77 |  |
| Öyrənilən əsas dil-3 (Azərbaycan dilinin morfologiyası) | köhnə | 0 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 1 | 21 | 19 | 10 | 24 | 40 | 64 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Öyrənilən əsas dil-4 (Sintaksis-1) | köhnə | 0 | 9 | 17 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 0 | 17 | 25 | 7 | 22 | 42 | 64 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Azərbaycan tarixi | köhnə | 0 | 16 | 24 | 10 | 29 | — | — | ✅ |
|  | yeni | 0 | 16 | 24 | 10 | 29 | 40 | 69 |  |
| Mülki müdafiə | köhnə | 0 | 8 | 16 | 10 | 31 | — | — | ✅ |
|  | yeni | 0 | 8 | 16 | 10 | 31 | 24 | 55 |  |
| Dil tarixi | köhnə | 0 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 0 | 15 | 21 | 10 | 17 | 36 | 53 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Ölkə ədəbiyyatı tarixi - 2 (XIII-XVIII əsr Azərbaycan ədəbiyyatı) | köhnə | 0 | 7 | 19 | 9 | 20 | — | — | ↔ birləşmə |
|  | yeni | 0 | 7 | 19 | 9 | 20 | 26 | 46 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Dilçiliyə giriş | köhnə | 0 | 8 | 21 | 9 | 19 | — | — | ✅ |
|  | yeni | 0 | 8 | 21 | 9 | 19 | 29 | 48 |  |
| Ədəbiyyatşünaslığa giriş | köhnə | 0 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 0 | 4 | 16 | 8 | 21 | 20 | 41 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Müasir İKT və informasiya təhlükəsizliyi | köhnə | 0 | 8 | 22 | 8 | 34 | — | — | ✅ |
|  | yeni | 0 | 8 | 22 | 8 | 34 | 30 | 64 |  |
| Xarici dildə işgüzar akademik kommunikasiya-2(elementary) | köhnə | 0 | 44 | 19 | 10 | — | — | — | ✅ |
|  | yeni | 0 | 44 | 19 | 10 | — | 50 | 50 |  |
| Öyrənilən əsas dil-1 (Azərbaycan dilinin fonetikası) | köhnə | 0 | 0 | 0 | 0 | 19 | — | — | ↔ birləşmə |
|  | yeni | 0 | 20 | 15 | 9 | 19 | 35 | 54 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Ölkə ədəbiyyatı tarixi - 1 (XIII əsrə qədərki Azərbaycan ədəbiyyatı) | köhnə | 0 | 5 | 16 | 9 | 21 | — | — | ✅ |
|  | yeni | 0 | 5 | 16 | 9 | 21 | 21 | 42 |  |
| Psixologiya | köhnə | 0 | 11 | 14 | 7 | 17 | — | — | ✅ |
|  | yeni | 0 | 11 | 14 | 7 | 17 | 25 | 42 |  |
| Azərbaycan dilində işgüzar və akademik kommunikasiya | köhnə | 0 | 11 | 17 | 8 | 30 | — | — | ✅ |
|  | yeni | 0 | 11 | 17 | 8 | 30 | 28 | 58 |  |
| Öyrənilən əsas dil-3 (Azərbaycan dilinin morfologiyası) | köhnə | 1 | 21 | 19 | 10 | 24 | — | — | ↔ birləşmə |
|  | yeni | 1 | 21 | 19 | 10 | 24 | 40 | 64 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Ölkəşünaslıq | köhnə | 0 | 7 | 18 | 8 | 19 | — | — | 🔴 |
|  | yeni | 0 | 7 | 18 | 8 | 24 | 25 | 49 |  |
| Öyrənilən əsas dil-1 (Azərbaycan dilinin fonetikası) | köhnə | 0 | 20 | 15 | 9 | — | — | — | ↔ birləşmə |
|  | yeni | 0 | 20 | 15 | 9 | 19 | 35 | 54 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Ölkə ədəbiyyatı tarixi - 3 (XIX əsr Azərbaycan ədəbiyyatı) | köhnə | 1 | 12 | 19 | 7 | 23 | — | — | ✅ |
|  | yeni | 1 | 12 | 19 | 7 | 23 | 31 | 54 |  |
| Azərbaycan Respublikasının konstitusiyası və hüququn əsasları | köhnə | 0 | 17 | 28 | 9 | 34 | — | — | ✅ |
|  | yeni | 0 | 17 | 28 | 9 | 34 | 45 | 79 |  |
| Ədəbiyyatşünaslığa giriş | köhnə | 0 | 4 | 16 | 8 | 11 | — | — | ↔ birləşmə |
|  | yeni | 0 | 4 | 16 | 8 | 21 | 20 | 41 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Dil tarixi | köhnə | 0 | 15 | 21 | 10 | 17 | — | — | ↔ birləşmə |
|  | yeni | 0 | 15 | 21 | 10 | 17 | 36 | 53 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Öyrənilən əsas dil-2 (Azərbaycan dilinin leksikologiyası) | köhnə | 0 | 13 | 16 | 7 | 12 | — | — | 🔴 |
|  | yeni | 0 | 13 | 16 | 7 | 23 | 29 | 52 |  |
| Ölkə ədəbiyyatı tarixi - 2 (XIII-XVIII əsr Azərbaycan ədəbiyyatı) | köhnə | 0 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 0 | 7 | 19 | 9 | 20 | 26 | 46 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Öyrənilən əsas dil-4 (Sintaksis-1) | köhnə | 0 | 17 | 25 | 7 | 22 | — | — | ↔ birləşmə |
|  | yeni | 0 | 17 | 25 | 7 | 22 | 42 | 64 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |

### dadasev azer — legacy `#7944` → `auth.user #5691`

| Sahə | Köhnə (MyEdu) | Yeni (EMS Arena) |
|---|---|---|
| Ad, soyad | dadasev azer | dadasev azer |
| Qrup | Level 2025-2026 | Level 2025-2026 |
| İxtisas / proqram | Dizayn (Qrafik) | Dizayn (Qrafik) |
| Statusu | — | enrolled (aktiv üzvlük) |

> Bu tələbə üçün jurnal xanası tapılmadı.

### VƏLİYEV CAMAL — legacy `#7971` → `auth.user #5718`

| Sahə | Köhnə (MyEdu) | Yeni (EMS Arena) |
|---|---|---|
| Ad, soyad | VƏLİYEV CAMAL | VƏLİYEV CAMAL |
| Qrup | Level 2025-2026 | Level 2025-2026 |
| İxtisas / proqram | Dizayn (Qrafik) | Dizayn (Qrafik) |
| Statusu | — | enrolled (aktiv üzvlük) |

> Bu tələbə üçün jurnal xanası tapılmadı.

### CƏFƏROVA FATİMƏ — legacy `#7999` → `auth.user #5746`

| Sahə | Köhnə (MyEdu) | Yeni (EMS Arena) |
|---|---|---|
| Ad, soyad | CƏFƏROVA FATİMƏ | CƏFƏROVA FATİMƏ |
| Qrup | Level 2025-2026 | Level 2025-2026 |
| İxtisas / proqram | Dizayn (Qrafik) | Dizayn (Qrafik) |
| Statusu | — | enrolled (aktiv üzvlük) |

> Bu tələbə üçün jurnal xanası tapılmadı.

### MİRZƏYEVA FİRUZA — legacy `#8022` → `auth.user #5769`

| Sahə | Köhnə (MyEdu) | Yeni (EMS Arena) |
|---|---|---|
| Ad, soyad | MİRZƏYEVA FİRUZA | MİRZƏYEVA FİRUZA |
| Qrup | Level 2025-2026 | Level 2025-2026 |
| İxtisas / proqram | Dizayn (Qrafik) | Dizayn (Qrafik) |
| Statusu | — | enrolled (aktiv üzvlük) |

> Bu tələbə üçün jurnal xanası tapılmadı.

### QASIMOVA LƏMAN — legacy `#8070` → `auth.user #5817`

| Sahə | Köhnə (MyEdu) | Yeni (EMS Arena) |
|---|---|---|
| Ad, soyad | QASIMOVA LƏMAN | QASIMOVA LƏMAN |
| Qrup | Level 2025-2026 | Level 2025-2026 |
| İxtisas / proqram | Dizayn (Qrafik) | Dizayn (Qrafik) |
| Statusu | — | enrolled (aktiv üzvlük) |

> Bu tələbə üçün jurnal xanası tapılmadı.

### HÜSEYNOVA NƏRMİN — legacy `#8137` → `auth.user #5884`

| Sahə | Köhnə (MyEdu) | Yeni (EMS Arena) |
|---|---|---|
| Ad, soyad | HÜSEYNOVA NƏRMİN | HÜSEYNOVA NƏRMİN |
| Qrup | Level 2025-2026 | Level 2025-2026 |
| İxtisas / proqram | Dizayn (Qrafik) | Dizayn (Qrafik) |
| Statusu | — | enrolled (aktiv üzvlük) |

> Bu tələbə üçün jurnal xanası tapılmadı.

### əliyev kənan — legacy `#8165` → `auth.user #5912`

| Sahə | Köhnə (MyEdu) | Yeni (EMS Arena) |
|---|---|---|
| Ad, soyad | əliyev kənan | əliyev kənan |
| Qrup | Level 2025-2026 | Level 2025-2026 |
| İxtisas / proqram | Dizayn (Qrafik) | Dizayn (Qrafik) |
| Statusu | — | enrolled (aktiv üzvlük) |

> Bu tələbə üçün jurnal xanası tapılmadı.

### Əliyev Yavər — legacy `#8255` → `auth.user #6001`

| Sahə | Köhnə (MyEdu) | Yeni (EMS Arena) |
|---|---|---|
| Ad, soyad | Əliyev Yavər | Əliyev Yavər |
| Qrup | 235 EKO | 235 EKO |
| İxtisas / proqram | Ekologiya | Ekologiya |
| Statusu | — | enrolled (aktiv üzvlük) |

| Fənn | Tərəf | Qayıb | Seminar bal | Kollokvium | Sərbəst iş | İmtahan | Giriş balı | Yekun | ⚑ |
|---|---|---|---|---|---|---|---|---|---|
| Mülki müdafiə | köhnə | 0 | 20 | 17 | 8 | 25 | — | — | ✅ |
|  | yeni | 0 | 20 | 17 | 8 | 25 | 37 | 62 |  |
| Yer elmlərinin əsasları | köhnə | 1 | 6 | 8 | 6 | 12 | — | — | ✅ |
|  | yeni | 1 | 6 | 8 | 6 | 12 | 14 | 26 |  |
| Ümumi ekologiya | köhnə | 1 | 0 | 0 | 0 | 32 | — | — | ↔ birləşmə |
|  | yeni | 1 | 6 | 19 | 9 | 32 | 25 | 57 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Ali riyaziyyat | köhnə | 1 | 29 | 17 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 3 | 29 | 17 | 9 | 17 | 46 | 63 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Xarici dildə işgüzar akademik kommunikasiya-2(intermediate) | köhnə | 9 | 27 | 27 | 9 | — | — | — | ✅ |
|  | yeni | 9 | 27 | 27 | 9 | — | 50 | 50 |  |
| Kimya | köhnə | 1 | 16 | 8 | 10 | 23 | — | — | ✅ |
|  | yeni | 1 | 16 | 8 | 10 | 23 | 24 | 47 |  |
| Ümumi ekologiya | köhnə | 0 | 0 | 19 | 9 | — | — | — | ↔ birləşmə |
|  | yeni | 1 | 6 | 19 | 9 | 32 | 25 | 57 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Torpaqşünaslıq | köhnə | 1 | 6 | 11 | 8 | 17 | — | — | ✅ |
|  | yeni | 1 | 6 | 11 | 8 | 17 | 17 | 34 |  |
| Azərbaycan dilində işgüzar və akademik kommunikasiya | köhnə | 1 | 22 | 16 | 10 | 34 | — | — | ✅ |
|  | yeni | 1 | 22 | 16 | 10 | 34 | 38 | 72 |  |
| Xarici dildə işgüzar və akademik kommunikasiya-1(pre-intermadiate) | köhnə | 6 | 27 | 17 | 9 | — | — | — | ✅ |
|  | yeni | 6 | 27 | 17 | 9 | — | 44 | 44 |  |
| Biologiya | köhnə | 2 | 13 | 17 | 8 | 18 | — | — | ✅ |
|  | yeni | 2 | 13 | 17 | 8 | 18 | 30 | 48 |  |
| Ümumi ekologiya | köhnə | 0 | 6 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 1 | 6 | 19 | 9 | 32 | 25 | 57 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Ali riyaziyyat | köhnə | 2 | 0 | 0 | 9 | 6 | — | — | ↔ birləşmə |
|  | yeni | 3 | 29 | 17 | 9 | 17 | 46 | 63 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Fizika | köhnə | 1 | 6 | 15 | 7 | 8 | — | — | ✅ |
|  | yeni | 1 | 6 | 15 | 7 | 8 | 21 | 29 |  |

### Yusifov Kamal — legacy `#9042` → `auth.user #6787`

| Sahə | Köhnə (MyEdu) | Yeni (EMS Arena) |
|---|---|---|
| Ad, soyad | Yusifov Kamal | Yusifov Kamal |
| Qrup | 635 2 | 635 2 |
| İxtisas / proqram | Dizayn Məktəbi | Dizayn Məktəbi |
| Statusu | — | enrolled (aktiv üzvlük) |

| Fənn | Tərəf | Qayıb | Seminar bal | Kollokvium | Sərbəst iş | İmtahan | Giriş balı | Yekun | ⚑ |
|---|---|---|---|---|---|---|---|---|---|
| Rəsm -2 | köhnə | 8 | 0 | 21 | 0 | — | — | — | ✅ |
|  | yeni | 8 | 0 | 21 | 0 | — | 21 | 21 |  |
| Rəsm -1 | köhnə | 0 | 0 | 22 | 10 | 26 | — | — | ✅ |
|  | yeni | 0 | 0 | 22 | 10 | 26 | 22 | 48 |  |
| Kompüter qrafikası -2 | köhnə | 3 | 0 | 19 | 7 | 28 | — | — | ✅ |
|  | yeni | 3 | 0 | 19 | 7 | 28 | 19 | 47 |  |
| Layihə qrafikasının əsasları ,rəngli kompozisiya və şriftlər | köhnə | 2 | 0 | 16 | 4 | 23 | — | — | ✅ |
|  | yeni | 2 | 0 | 16 | 4 | 23 | 16 | 39 |  |
| Xarici dil | köhnə | 0 | 27 | 23 | 7 | — | — | — | ✅ |
|  | yeni | 0 | 27 | 23 | 7 | — | 50 | 50 |  |
| Kompüter qrafikası -1 | köhnə | 0 | 0 | 23 | 8 | 29 | — | — | ✅ |
|  | yeni | 0 | 0 | 23 | 8 | 29 | 23 | 52 |  |
| Xarici dildə işgüzar və akademik kommunikasiya-1(intermediate) | köhnə | 0 | 17 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Azərbaycanın tarixi | köhnə | 0 | 0 | 0 | 0 | — | — | — | ✅ |
|  | yeni | 0 | 0 | 0 | 0 | — | 0 | 0 |  |
| Azərbaycan tarixi | köhnə | 0 | 0 | 0 | 0 | — | — | — | ↔ birləşmə |
|  | yeni | 0 | 12 | 16 | 7 | 12 | 28 | 40 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Dizaynın əsasları-2 | köhnə | 5 | 0 | 0 | 0 | 17 | — | — | ✅ |
|  | yeni | 5 | 0 | 0 | 0 | 17 | 0 | 17 |  |
| Azərbaycan tarixi | köhnə | 0 | 12 | 16 | 7 | 12 | — | — | ↔ birləşmə |
|  | yeni | 0 | 12 | 16 | 7 | 12 | 28 | 40 | bir neçə legacy jurnal eyni açılışa birləşib — «yeni» sütunu birləşmiş nəticədir |
| Azərbaycan dilində işgüzar və akademik kommunikasiya | köhnə | 5 | 5 | 11 | 6 | 22 | — | — | ✅ |
|  | yeni | 5 | 5 | 11 | 6 | 22 | 16 | 38 |  |
| Multikulturalizmə giriş | köhnə | 0 | 8 | 21 | 8 | 7 | — | — | ✅ |
|  | yeni | 0 | 8 | 21 | 8 | 7 | 29 | 36 |  |
| Dizaynın əsasları-1 | köhnə | 0 | 0 | 17 | 10 | 29 | — | — | ✅ |
|  | yeni | 0 | 0 | 17 | 10 | 29 | 17 | 46 |  |

### Cəfərli Rüqəyya — legacy `#9313` → `auth.user #7057`

| Sahə | Köhnə (MyEdu) | Yeni (EMS Arena) |
|---|---|---|
| Ad, soyad | Cəfərli Rüqəyya | Cəfərli Rüqəyya |
| Qrup | 235 CM | 235 CM |
| İxtisas / proqram | Cihazqayırma mühəndisliyi | Cihazqayırma mühəndisliyi |
| Statusu | — | enrolled (aktiv üzvlük) |

| Fənn | Tərəf | Qayıb | Seminar bal | Kollokvium | Sərbəst iş | İmtahan | Giriş balı | Yekun | ⚑ |
|---|---|---|---|---|---|---|---|---|---|
| Mülki müdafiə | köhnə | 2 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Xətti cəbr və analitik həndəsə | köhnə | 2 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Cihaz texnologiyalarının əsasları | köhnə | 3 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Kompüter sistemlərinin aparat və proqram təminatının əsasları | köhnə | 0 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Azərbaycan dilində işgüzar və akademik kommunikasiya | köhnə | 2 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |
| Kompüter sistemlərinin aparat və proqram təminatının əsasları | köhnə | 3 | 0 | 0 | 0 | — | — | — | 🔴 |
|  | yeni | — | — | — | — | — | — | — | yazılış köçürülməyib (jurnal açılışı və ya tələbə həll olunmayıb) |

> **Qeyd:** «Giriş balı» sütunundakı fərqi XƏTA saymayın — düstur hazırda
> yenilənir (bax §4.2).

## 4. Bal bütövlüyü

### 4.1 `yekun` cədvəli ↔ hədəfin hesabladığı yekun

| Göstərici | Say |
|---|---|
| Mənbədəki `yekun` sətri | 17,194 |
| Hədəfdəki yazılışa bağlanan sətir | 15,215 |
| …bunlardan birləşən jurnal səbəbindən eyni yazılışa düşən | 991 |
| …yəni fərqli yazılış sayı | 14,224 |
| Bağlana bilməyən (yazılış köçürülməyib) | 1,979 |
| Bağlandı, amma registrar-da tapılmadı | 0 |
| Müqayisə edilən yekun bal | 14,224 |
| *J8 fazasının öz rəqəmi:* bağlana bilməyən | 1,979 |
| *J8 fazasının öz rəqəmi:* kənarlaşan yekun | 14,664 |

> Son iki sətir ledger-dən gəlir (`legacy_journal_reconcile_*`) və bu hesabatın
> MÜSTƏQİL hesabladığı rəqəmlərlə üzləşdirilir — iki sübut mənbəyi bir-birini
> yoxlayır.

**Yekun balı fərqinin paylanması** (hədəfin hesabladığı − legacy `yekun`):

| Fərq | Say | Pay |
|---|---|---|
| 0 | 514 | 3.6 % |
| ±1 | 916 | 6.4 % |
| ±2 | 955 | 6.7 % |
| ±3–5 | 2,700 | 19.0 % |
| >5 | 9,139 | 64.3 % |

> ⚠️ Bu paylanmadakı böyük fərqlərin əsas mənbəyi **giriş balı düsturudur**
> (§4.2) — yekun = giriş + imtahan olduğu üçün giriş kənarlaşması birbaşa
> yekuna keçir.  Düsturdan asılı olmayan hissəni aşağıdakı iki cədvəldə görün.

**İmtahan balı fərqinin paylanması** (`im`/`im2` ↔ `FinalGrade`/`ResitRecord`):

| Fərq | Say | Pay |
|---|---|---|
| 0 | 13,373 | 94.0 % |
| ±1 | 24 | 0.2 % |
| ±2 | 18 | 0.1 % |
| ±3–5 | 103 | 0.7 % |
| >5 | 706 | 5.0 % |

**`yekun − giriş` fərqinin paylanması** — giriş düsturundan ASILI OLMAYAN hissə:

| Fərq | Say | Pay |
|---|---|---|
| 0 | 13,295 | 93.5 % |
| ±1 | 38 | 0.3 % |
| ±2 | 25 | 0.2 % |
| ±3–5 | 120 | 0.8 % |
| >5 | 746 | 5.2 % |

### 4.2 ⏳ Giriş balı — DÜSTUR GÖZLƏYİR

> Giriş balının hesablanma düsturu **hazırda yenilənir**.  Aşağıdakı paylanma
> `entry = min(seminar + kollokvium, entry_score_max)` cari güzgüsü ilə
> hesablanıb və **XƏTA SAYILMIR** — düstur dəqiqləşəndə bu bölmə yenidən
> işlədilməlidir.

| Fərq | Say | Pay |
|---|---|---|
| 0 | 515 | 3.6 % |
| ±1 | 923 | 6.5 % |
| ±2 | 956 | 6.7 % |
| ±3–5 | 2,720 | 19.1 % |
| >5 | 9,110 | 64.0 % |

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
| → hədəf: `LessonMark.status = present` | davamiyyət | 3,198,284 |
| → hədəf: `LessonMark.status = absent` | davamiyyət | 507,734 |
| → hədəf: `LessonMark.status = excused` | üzrlü davamiyyət | 5,135 |
| → hədəf: `LessonMark.score` dolu | bal | 216,453 |
| → hədəf: `ComponentScore` (kollokvium) | bal | 404,406 |
| → hədəf: `ComponentScore` (sərbəst iş) | bal | 134,051 |

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
| Qrupsuz akademik qeyd | 0 | ✅ təmiz |
| Açılışsız dərs | 0 | ✅ təmiz |
| Müəllimsiz açılış | 1,206 | ⚠️ baxılmalıdır |
| Eyni adlı fənn (dublikat namizədi) | 9 | ⚠️ baxılmalıdır |
| Akademik qeydi (SAR) olmayan tələbə | 14 | ⚠️ baxılmalıdır |
| Adı və ya soyadı boş olan hesab | 4 | ⚠️ baxılmalıdır |
| Eyni tələbənin iki aktiv akademik qeydi | 0 | ✅ təmiz |
| Eyni fənn+qrup+dövr üçün iki açılış | 0 | ✅ təmiz |
| Təkrarlanan yazılış (açılış + tələbə) | 0 | ✅ təmiz |
| Komponenti olmayan komponent balı (orfan) | 0 | ✅ təmiz |
| Yazılışı olmayan bal xanası (orfan) | 0 | ✅ təmiz |
| Dərsi olmayan bal xanası (orfan) | 0 | ✅ təmiz |
| Eyni yazılış+dərs üçün iki bal xanası | 0 | ✅ təmiz |

## 6. Ledger problem kodları (ilk 30)

Bunlar səssiz itki DEYİL: hər biri qeydə alınmış, səbəbi adlandırılmış hadisədir.

| Mənbə cədvəli | Kod | Ciddilik | Say |
|---|---|---|---|
| `journals_dates_added_by_teacher` | `legacy_journal_lesson_duplicate` | info | 85,673 |
| `journals_dates_added_by_teacher` | `legacy_journal_lesson_orphan` | info | 61,319 |
| `journals_dates_added_by_teacher` | `legacy_journal_lesson_kind_absent` | info | 16,786 |
| `yekun` | `legacy_journal_reconcile_final_deviation` | info | 14,664 |
| `journals` | `legacy_journal_lock_applied` | info | 13,976 |
| `yekun` | `legacy_entry_score_derived` | info | 13,126 |
| `journals` | `legacy_journal_enrollment_orphan` | info | 10,836 |
| `students` | `legacy_account_email_untrusted` | info | 7,716 |
| `journals_dates_points` | `legacy_journal_mark_enrollment_unresolved` | warning | 4,365 |
| `journals` | `legacy_journal_student_group_mismatch` | warning | 3,862 |
| `journals` | `legacy_journal_multi_group` | info | 3,580 |
| `journals` | `legacy_journal_student_unresolved` | warning | 3,550 |
| `curricula_plan` | `legacy_plan_hours_not_modelled` | info | 3,422 |
| `students` | `legacy_sar_curriculum_substituted` | warning | 3,149 |
| `journals` | `legacy_journal_offering_merged` | info | 2,872 |
| `sillabus_serbest_is` | `legacy_selfwork_topics_truncated` | info | 2,813 |
| `journals` | `legacy_journal_lesson_hours_missing` | info | 2,753 |
| `students` | `legacy_sar_archived_student` | info | 2,490 |
| `yekun` | `legacy_entry_score_residual_clamped` | warning | 2,372 |
| `students` | `legacy_record_admission_year_missing` | info | 2,353 |
| `students` | `legacy_sar_admission_year_missing` | warning | 2,340 |
| `students` | `legacy_sar_admission_year_fallback` | warning | 2,340 |
| `students` | `legacy_sar_archived_no_admission_year` | info | 2,291 |
| `journals_dates_points` | `legacy_journal_component_enrollment_unresolved` | warning | 2,284 |
| `sillabus_serbest_is` | `legacy_selfwork_topic_placeholder` | info | 2,241 |
| `students` | `legacy_sar_curriculum_unmapped` | warning | 2,190 |
| `journals_dates_points` | `legacy_journal_archive_overlap` | info | 2,117 |
| `sillabus_serbest_is` | `legacy_selfwork_title_truncated` | info | 1,988 |
| `yekun` | `legacy_journal_reconcile_final_unresolved` | warning | 1,979 |
| `journals` | `legacy_journal_discarded_source` | info | 1,866 |

## Əlavə: sorğu vaxtları

Ümumi sorğu vaxtı: **2 d 49 s** (24 sorğu, hamısı yalnız-oxu).

| Sorğu | Müddət | Qaytarılan sətir |
|---|---|---|
| mənbə · xana → (jurnal, tələbə) | 2 d 7 s | 463,508 |
| mənbə · xana təsnifatı | 12.0 s | 17 |
| mənbə · dəyər paylanması | 10.5 s | 18 |
| mənbə · xam yazıla bilən | 7.3 s | 3 |
| hədəf · keyfiyyət | 4.1 s | 13 |
| hədəf · nümunə yazılışlar | 1.8 s | 228 |
| hədəf · varlıq sayları | 1.7 s | 29 |
| hədəf · yekun güzgüsü | 1.5 s | 14,224 |
| mənbə · cədvəl sayları | 719 ms | 13 |
| mənbə · nümunə xanaları | 322 ms | 7,537 |
| hədəf · enrollment körpüsü | 262 ms | 181,094 |
| mənbə · nümunə hovuzu | 228 ms | 7,816 |
| mənbə · keyfiyyət | 226 ms | 13 |
| mənbə · jurnal → fənn | 220 ms | 13,875 |
| mənbə · yekun sətirləri | 214 ms | 17,194 |
| hədəf · ledger | 206 ms | 46 |
| mənbə · nümunə yekun | 182 ms | 15 |
| hədəf · ledger problemləri | 85 ms | 99 |
| hədəf · offering körpüsü | 81 ms | 13,987 |
| hədəf · tələbə körpüsü | 61 ms | 7,716 |
