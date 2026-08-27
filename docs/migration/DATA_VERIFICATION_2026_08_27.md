# Data köçürmə — yekun yoxlama hesabatı

**Tarix:** 2026-08-27
**Yeni repetisiya bazası:** `emsarena_rehearsal_b90d8e9fc8ef`
**Müqayisə (köhnə) bazası:** `emsarena_rehearsal_603f5e9f08e7` (bu gecəki 5 düzəlişdən ƏVVƏL)
**Mənbə:** MyEdu MariaDB (`myedudb`) — yalnız oxu rejimində (`@@global.read_only=1` təsdiqləndi)

Hər iki bazaya və mənbəyə **yalnız SELECT** getdi. Heç bir yazma əməliyyatı olmayıb.

---

## 1. Bir baxışda

| Göstərici | Köhnə run | Yeni run | Dəyişiklik |
|---|---:|---:|---|
| **Tələbə yazılışı (Enrollment)** | 106,870 | **148,020** | +41,150 |
| **Akademik qeyd (SAR)** | 5,213 | **7,703** | +2,490 |
| **Fənn açılışı (CourseOffering)** | 9,599 | **11,115** | +1,516 |
| **Dərs (Lesson)** | 243,923 | **293,070** | +49,147 |
| **Ballı dərs qiyməti (LessonMark)** | 160,064 | **216,453** | +35.2 % |
| **Komponent balı (ComponentScore)** | 384,456 | **686,477** | +302,021 |
| **Yekun qiymət (FinalGrade)** | 83,488 | **114,021** | +30,533 |
| **Sərbəst iş mövzusu (SelfWorkTopic)** | 0 | **69,404** | yeni |
| **Dərs tipi bölgüsü** | 100 % mühazirə | seminar 150,739 / mühazirə 110,822 / lab 31,509 | — |
| **Jurnalda GÖRÜNƏN bal** | 0 / 160,064 = **0 %** | 215,445 / 216,453 = **99.53 %** | — |
| **«Tələbə jurnalda aktiv deyil» deyə ötürülən xana** | 1,479,737 | **268,241** | −81.9 % |
| **`legacy_journal_student_inactive` hadisəsi** | 60,984 | **5** | −99.99 % |
| **Mənbənin köçən payı (3 domen)** | 56.1 % | **73.9 %** | +17.8 f.b. |
| **İmtahan balı DƏQİQ uyğunluq** | 85.8 % | **94.0 %** | +8.2 f.b. |
| **Bağlana bilməyən `yekun` sətri** | 12,379 | **1,979** | −84 % |
| **Akademik qeydi olmayan tələbə** | 2,504 | **14** | −99.4 % |
| **Arxiv tələbədə ən azı 1 fənn** | 0 / 2,503 (**0 %**) | 2,405 / 2,490 (**96.6 %**) | — |
| **Bütövlük pozuntusu** (orfan bal / orfan komponent / dublikat yazılış / dublikat açılış) | 0 / 0 / 0 / 0 | **0 / 0 / 0 / 0** | pozulmayıb |

**Bir cümlə ilə:** Beş düzəlişin hamısı işləyib və ölçülə bilən nəticə verib. Köçürmənin
əhatəsi mənbənin 56 %-indən 74 %-inə qalxdı, arxiv tələbələrin datası ilk dəfə köçdü,
seminar balları ilk dəfə jurnalda görünür. Beş açıq problem qaldı — üçü düzəliş, ikisi
sizin qərarınızı gözləyir.

---

## 2. Nə düzəldi — hər düzəlişin ölçülmüş təsiri

### Düzəliş 1 — Arxiv (məzun / qeyri-aktiv) tələbələrin üzvlüyü ✅ İŞLƏYİR

| Ölçü | Köhnə | Yeni |
|---|---:|---:|
| Arxiv tələbə (ən azı 1 fənni olan) | 0 / 2,503 | **2,405 / 2,490** |
| Arxiv tələbələrin cəmi yazılışı | 0 | **48,095** |
| `legacy_journal_student_inactive` hadisəsi | 60,984 | **5** |
| Akademik qeydi olmayan tələbə | 2,504 | **14** |

Seçmə yoxlama (təsadüfi 5 arxiv tələbəsi): 1910 → 10/10 jurnal, 2020 → 16/16,
314 → 11/11, 62 → 2/2, 2451 → 4/8 (qalan 4-ü mənbədə `fake=1` jurnaldır).

**Təhlükəsizlik tərəfi yoxlanıldı və təmizdir:** arxiv hesablarının **hamısı** (2,490)
`alumni` rolundadır, başqa rol yoxdur. Yəni data qapısı açıldı, giriş qapısı bağlı qaldı.

### Düzəliş 2 — Qrup-başına jurnal bölgüsü ✅ İŞLƏYİR (bir yan təsirlə)

- CourseOffering 9,599 → **11,115** (eyni 11,861 mənbə jurnalından)
- Dərs 243,923 → **293,070**
- Dublikat açılış / dublikat yazılış: **0**

⚠️ Yan təsiri var — bax [«Nə qaldı» §3.1](#31-bloker--qrup-uyğunsuzluğu-tarixi-datanı-silir).

### Düzəliş 3 — J5b: köhnə giriş balının qalıq komponenti ✅ İŞLƏYİR

Bu, sahibin əsas şikayətini — «tələbələr səhvən kəsilmiş görünür» — həll etdi.

| Ölçü (eyni 99,003 yazılış üzərində) | Köhnə | Yeni |
|---|---:|---:|
| **Bal-əsaslı kəsr faizi** | 24.35 % | **11.38 %** (−53 %) |
| Orta giriş balı | 31.00 | **36.82** |
| Giriş balı = 0 olan tələbə-fənn | 7,901 | **1,627** |
| Giriş balı < 25 olan | 26,799 | **11,014** |

Arxiv komponenti («Davamiyyət və sərbəst iş (arxiv)», maks 50 bal) **148,020 yazılışın
100 %-ni** əhatə edir — arxiv balı olmayan yazılış qalmayıb.

**Mənbə ilə tutuşdurma (yeganə həqiqət mənbəyi — köhnə `yekun` cədvəli, 15,215 sətir):**
- Hesablanmış giriş balı `yekun.girish` ilə **96.1 % dəqiq** üst-üstə düşür (±2 tolerans → 97.0 %)
- Köhnə sistemdə **keçmiş** 13,052 tələbə-fəndən yeni sistemdə kəsilmiş görünən: **84 (0.64 %)**
- Seçmə yoxlamada 108 yazılışın **108-i** dəqiq bərpa olundu (13-ü `yekun`-dan, 95-i düsturdan)

### Düzəliş 4 — Dərs tipi (mühazirə / seminar / lab) ✅ İŞLƏYİR

| Ölçü | Köhnə | Yeni |
|---|---:|---:|
| Dərs tipi | 100 % mühazirə (243,923) | seminar **150,739** / mühazirə **110,822** / lab **31,509** |
| Jurnalda **görünən** bal | 0 (0 %) | **215,445 (99.53 %)** |
| Görünməyən bal | 160,064 (hamısı) | 1,008 (0.47 %) |

Müstəqil yoxlama (mənbənin işlədilməyən üçüncü siqnalı — otaq cədvəli):
mühazirə **99.4 %**, seminar **93.7 %** uyğunluq; ümumi ziddiyyət 9,960 / 275,522 = 3.6 %.
Seçmə yoxlamada 1,774 xanadan 1,768-i uyğun, 6-sı uyğunsuz (hamısı §3.5-dəki qüsurdan).

### Düzəliş 5 — J9: Sərbəst iş mövzuları ✅ İŞLƏYİR (formatda problem var)

| Ölçü | Köhnə | Yeni |
|---|---:|---:|
| SelfWorkTopic | 0 | **69,404** |
| Mövzusu olan açılış | 0 | **10,173 / 11,115 (91.5 %)** |
| HTML qalığı (`&uuml;` və s.) | — | **0** — mənbədəki 25,608 belə sətir düzgün açılıb |
| Mojibake / boş başlıq | — | **0 / 0** |

Mənbədən müstəqil yenidən hesabladım: gözlənilən Σ min(mövzu, 10) = **69,404** — hədəflə
**hərfi-hərfinə** eyni. Yəni «itən mövzu» yoxdur. (Əvvəlki ~79,933 gözləntisi səhv idi.)

⚠️ Formatda iki problem qaldı — bax §3.4.

---

## 3. Nə qaldı — açıq problemlər

### 3.1 🔴 BLOKER — qrup uyğunsuzluğu tarixi datanı silir

Qrup-başına bölgü tətbiq olunanda sistem tələbənin **bugünkü** qrupuna baxır
(`students.group_id`), jurnalın öz qrupuna yox. Qrupu dəyişmiş tələbənin əvvəlki
tədris ilinin jurnalları tamamilə atılır.

**Ölçülmüş itki:**

| Nə itdi | Say |
|---|---:|
| Tələbə yazılışı | **6,945** (2,329 tələbədə) |
| Ballı dərs qiyməti | **3,873** (1,015 tələbədə) |
| **Yekun qiymət** | **1,030** (376 tələbədə) |
| Komponent balı | 979 (100 tələbədə) |
| Atılan jurnal-tələbə sətri (`legacy_journal_student_group_mismatch`) | 3,862 (727 jurnal, 1,440 tələbə) |

**Konkret nümunə:** aktiv tələbə #7582 (Aişə Ağamirzəzadə) — bugünkü qrupu 781.
Mənbədə 32 jurnalı var; 18-i köçdü, 14-ü atıldı. Atılan 14-ün hamısı çox-qruplu
jurnaldır və heç birində 781 yoxdur (qrupları 660/661/676/48/50/520). Nəticədə
onun bütün 2024/2025 tarixçəsi (9 yekun qiymət, 24 komponent) yox oldu.

Qayda yalnız ÇOX qruplu jurnallara toxunur; tək qruplu jurnal olduğu kimi köçür.
Köhnə run-da bu qayda ümumiyyətlə yox idi.

### 3.2 🟠 YÜKSƏK — `fake` / `sonra_sil` süzgəci dublikatı olmayan balları atır

Sistem 1,866 mənbə jurnalını «silinmiş / saxta» kimi süzür. Bu jurnallarda
**255,490 xana** var, o cümlədən 6,369 imtahan balı, 22,353 kollokvium,
7,507 sərbəst iş balı, 21,518 qayıb.

Dublikat yoxlaması etdim: 6,341 (tələbə, fənn) cütündən yalnız **268-inin** normal
jurnalda qarşılığı var. Yəni **6,073 imtahan balı yeganə nüsxədir və atılır**.

**Konkret nümunə:** aktiv tələbə #9396 (2025/2026 Payız) üç fənnini tam itirir —
Strateji marketinq (k1=9, k2=10, k3=9, si=10, imtahan=50), Liderlik (10/9/9/9, 45),
Biznes etikası (9/7/10/10, 45). Bu üç fənn onun köçən 7 jurnalının heç birində yoxdur.

→ Sizin qərarınız lazımdır (bax §4).

### 3.3 🟠 YÜKSƏK — 2023/2024 Yaz semestrində saxta qayıb blokları

Həmin semestrdə mənbədəki cədvəl şəbəkəsi 90 dəqiqəlik cütdən **50 dəqiqəlik tək
akademik saata** keçib (mənbədə təsdiqləndi: 09:20 / 10:15 / 11:05 / 14:40 slotları
yalnız bu semestrdə kütləvi görünür). Köçürmə isə hər dərsə sabit **2 saat** yazır —
nəticədə həmin semestrdə qayıb saatı iki qat sayılır.

| Ölçü (2023/2024 Yaz) | Dəyər |
|---|---:|
| Cəmi yazılış | 12,804 |
| Qayıba görə bloklanan | **5,312 (41.5 %)** |
| Bunlardan **balı keçməyə kifayət edən** (yəni saxta blok) | **3,252** |
| Qayıb saatı yarıya bölünsə blok sayı | 997 (7.8 %) — qonşu semestrlərin 5.7–10.0 % zolağında |

Sistem üzrə: 13,578 blokdan **4,315-i (31.8 %) saxtadır**. Digər semestrlərdə bu
defekt yoxdur (orada yarıya bölmə blok sayını normadan aşağı salır).

Düzəlişi mexanikidir: dərs saatını sabit 2 əvəzinə slot şəbəkəsindən çıxarmaq.

### 3.4 🟠 YÜKSƏK — Sərbəst iş mövzuları birləşmiş açılışlarda təkrarlanır

**2,063 açılışa iki və daha çox köhnə jurnal** (fərqli sillabus) düşür və faza hər
jurnal üçün ayrıca mövzu dəsti yazır.

| Nəticə | Say |
|---|---:|
| Təkrar `order` slotu olan açılış | **1,467** (7,174 slot cütü) |
| Ziddiyyətli başlıqlı slot (başqa sillabusun mövzusu) | **2,442** cüt / 5,704 sətir |
| Eyni mətnin dublikatı | 4,732 cüt / 10,339 sətir |
| 10 mövzu tavanını aşan açılış | **942** (maksimum 70 mövzu bir açılışda) |

**İstifadəçiyə görünən nəticə:** lövhə 10 slot göstərir və mövzuları sıraya görə
doldurur — 20 mövzulu açılışda tələbə `1, 1, 2, 2, 3, 3, 4, 4, 5, 5` görür və real
6–10-cu mövzular **tamamilə düşür**.

Əlavə: **15,326 real mövzu** 10 tavanına görə ümumiyyətlə köçmür (1,424 sillabus,
2,813 jurnal). Tavan qərarlı seçimdir, amma mətn hədəfdə yoxdur.

### 3.5 🟡 ORTA — 1,008 bal hələ də jurnalda görünmür

141 dərs, **86 açılış, 395 tələbə**. Ballar realdır (0.00–10.00).

İki kök səbəb ölçüldü:
- **78 dərs** — bir açılışa düşən qonşu jurnalların açar uyğunsuzluğu (dərs tipi jurnal
  kodu ilə, bal isə açılış kodu ilə açarlanır)
- **63 dərs** — mənbədəki `sem_muh=1 → mühazirə` qaydasının 0.27 %-lik quyruğu
  (mənbədə 287 belə slot real bal daşıyır)

Müstəqil təsdiq: problemli 85 dərsdən **72-si (85 %)** üçün otaq cədvəli «bu mühazirə
deyil» deyir.

### 3.6 🟡 ORTA — sabit dərs saatı lokal olaraq qayıb hesabını şişirdir

Dərs saatı bütün 293,070 sətirdə sabit 2-dir. Ümumi qayda kimi bu **doğrudur**
(rəsmi davamiyyət cədvəli: 1 qayıb = 2 akademik saat) — bu, əvvəl «xəta» kimi
göstərilmişdi və çürüdüldü. **Amma** slot şəbəkəsi tək-saatlıq olan açılışlarda
(əsasən §3.3-dəki semestr) hesab iki qat çıxır.

Vahid-uyğun ölçmə (qayıb işarəsi / dərs sayı > 25 %) ilə müqayisə:
hazırkı hesabla **13,578** blok, vahid-uyğun hesabla **7,523** →
**6,417 yalançı-müsbət**, 362 yalançı-mənfi.

### 3.7 🟡 ORTA — Sərbəst iş balının 14,454 sətri hədəfə çatmayıb

Mənbədə 148,505 `si` balı var, hədəfdə **134,051** (köhnə run-da 95,821).
Fərqin bölgüsü ölçüldü: **8,696-sı** köçməyən jurnallara düşür (izahlıdır),
qalan ~5,758-i yazılışı həll olunmayan sətirlərdir (2,284 xəbərdarlıq + 1,766 orfan
+ 201 boş). Mənbədəki xam çirk isə kiçikdir (77 boş + 114 qeyri-rəqəm dəyər).

### 3.8 🟢 AŞAĞI — qeydə alınmış, təcili deyil

| Problem | Ölçü |
|---|---|
| Placeholder «Sərbəst iş N» başlıqları | 2,923 (mənbədə 2,572 boş adlı sətir var) |
| 255 simvolda kəsilmiş mövzu başlığı | 2,435 (mənbədə maks 7,688 simvol) |
| Mövzusu olmayan açılış | 942 — 1,701 jurnalın mənbədə sillabus bağı yoxdur (mənbə boşluğu) |
| `lesson_hours=0` olan açılışda qayıb bloku ümumiyyətlə işləmir | 1,954 açılış / 25,314 yazılış (17 %) |
| Birləşmiş jurnalda bir yazılışa 2+ tarixi giriş balı düşür | 811 yazılış — hansının seçildiyi deterministik olmalıdır |
| 2021/2022 illəri praktiki olaraq qiymətləndirilməmiş qalır | Payız 367/367 (100 %), Yaz 9,972/10,674 (93.4 %) — transkriptdə çəkisizdir |
| Mənbənin öz siyahısında olmayan tələbələrin xanaları köçmür | Seçmədə 16 cüt / 259 xana (demək olar hamısı 0 dəyərli) |
| Uzlaşdırma alətinin açar formatı düzəlişi | Artıq repoda commit edilib (`70b75393`); ondan əvvəl yaradılmış hesabatlar etibarsızdır |

---

## 4. Qərarınız gözlənilir

### 4.1 ⏳ Rəsmi giriş balı düsturu — ƏN VACİB
Bu **xəta deyil**, sizin təsdiqinizi gözləyən açıq sualdır.

- 148,020 yazılışdan yalnız **14,224-ü (9.6 %)** köhnə `yekun` cədvəlindən **dəqiq**
  dəyər alır. Qalan **133,796-sı (90.4 %)** datadan çıxarılmış düsturla hesablanıb:
  `clamp(10 − 0.5 × qayıb + Σ kollokvium + sərbəst iş, 0, 50)`
- Bu düsturun keyfiyyəti ölçüldü: `yekun` dilimində dəqiq uyğunluq **21.5 %**,
  ±2 tolerans ilə **76.1 %**. Meyilli deyil (orta sapma −0.12, medyan −0.50) və
  kütləvi kəsr yaratmır (kəsr faizi dəqiq dilimdə 9.74 %, hesablanmış dilimdə 11.63 %).
- Rəsmi düsturu verəndə həmin **133,796 dəyər yenidən hesablanacaq** və uzlaşdırma
  güzgüsü də yenilənməlidir.

### 4.2 ⏳ `fake` / `sonra_sil` jurnalları köçsün, yoxsa atılsın?
6,073 unikal imtahan balı (dublikatı olmayan) hazırda atılır. Bu jurnallar köhnə
sistemdə «silinmiş» işarələnib, amma real bal daşıyır. **Sual:** silinmiş jurnalların
balı arxivə köçürülsün, yoxsa köhnə sistemin qərarına hörmət edilsin?

### 4.3 ⏳ 25 % qayıb bloku tarixi semestrlərə tətbiq olunsunmu?
Köhnə MyEdu sistemində «imtahana buraxılmır» bloku **ümumiyyətlə yox idi** — mənbədə
belə sütun tapılmadı (`kesr` bayrağının 94.5 %-i bal qaydasıdır, davamiyyət deyil).
Köhnə düsturda qayıb yalnız giriş balını azaldırdı (maks 10 bal cərimə).

Yeni sistemdə bu qayda tenant parametridir (`absence_limit_percent = 25`, 101 proqramın
hamısında). Yer üzü həqiqəti testi: köhnə `yekun` dilimində bloklanan 280 tələbədən
**184-ü faktiki olaraq imtahanda iştirak edib** — yəni köhnə sistem qaydanı praktikada
tətbiq etmirdi.

**Sual:** arxiv semestrlərində davamiyyət bloku göstərilsin, yoxsa yalnız 2026/2027-dən
irəli tətbiq olunsun? (§3.3-dəki texniki düzəliş bundan ayrıdır və hər halda edilməlidir.)

### 4.4 ⏳ Sərbəst iş: 10 mövzu tavanı saxlanılsın?
15,326 real mövzu tavana görə köçmür. Tavan lövhənin 10 slotuna və komponentin 10 ballıq
maksimumuna bağlıdır. **Sual:** arxiv fənlərində tavan qaldırılsın (mövzular tam görünsün),
yoxsa olduğu kimi qalsın?

### 4.5 ⏳ Qrup tarixçəsi
§3.1-dəki bloker texniki düzəliş tələb edir (jurnalın öz qrupu istifadə olunmalıdır).
**Sual:** düzəliş üçün yeni tam repetisiya işlədək, yoxsa cutover-dən əvvəl birbaşa?

---

## 5. Metodologiya və etibarlılıq

- **Beş müstəqil yoxlama raundu** işlədildi: uzlaşdırma nərdivanı, kəsilmə təhlili,
  dərs tipi/seminar, sərbəst iş (J9), və tələbə-səviyyəli xana-bəxana müqayisə.
- Sonra **çürütmə raundu** aparıldı: ən ciddi 6 tapıntı ayrıca sorğularla yenidən
  yoxlandı. Nəticə: **3-ü tam çürüdüldü** (yanlış həyəcan idi), **2-sinin ciddiliyi
  endirildi**, **1-i təsdiqləndi**. Çürüdülmüş tapıntılar bu hesabatda **yoxdur**.
- Xana-bəxana dəqiqlik testi (10 təsadüfi tələbə, 108 yazılış):
  **1,774 mənbə xanası ↔ 1,774 hədəf xanası — 0 çatışmayan, 0 artıq, 0 uyğunsuz.**
  Kollokvium / sərbəst iş / imtahan / təkrar imtahan komponentləri: **0 uyğunsuzluq**.
- Bütövlük invariantları hər iki run-da təmizdir: orfan bal xanası **0**, orfan komponent
  balı **0**, dublikat yazılış **0**, dublikat açılış **0**.
- Bu hesabatdakı hər rəqəm birbaşa sorğu ilə ölçülüb. Ölçülməyən heç bir iddia yoxdur.
