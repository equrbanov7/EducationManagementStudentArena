# Köhnə sistemin (MyEdu) **giriş balı** düsturu — datadan geri-mühəndislik

**Tarix:** 2026-08-27 · **Mənbə:** `emsarena-legacy-source-rehearsal` / `myedudb` (yalnız `SELECT`)
**Status:** müstəqil analiz. Sahibin rəsmi düsturu ilə çarpaz-yoxlama üçün nəzərdə tutulub.

İstifadə olunan artefaktlar (hamısı scratchpad-dədir):

| fayl | nədir |
|---|---|
| `legacy_girish_reference.py` | təmiz Python referans implementasiyası (asılılıqsız) |
| `verify_girish.py` | bütün 17 194 `yekun` sətrinə qarşı işlədən yoxlama skripti |
| `parse_bal.py` → `bal_rows.tsv` | `balvereqi_logs`-dan çıxarılmış **903 943** komponent sətri |
| `dav_study.py`, `sem_study3.py`, `bal_dav.py`, `bal_sem.py` | alt-düsturların izolyasiya testləri |

---

## 1. Qısa cavab

```
giriş = ROUND( davamiyyət + sərbəst_iş + seminar )        , maksimum 50

davamiyyət = 10 × (N − Q) / N                    0 … 10
sərbəst_iş = "si" xanasının dəyəri               0 … 10
seminar    = 3 × ORTA(bütün rəqəmli qiymətlər)   0 … 30
```

* `N` — jurnaldakı **dərs xanalarının (gün × saat) ümumi sayı** (`journals_dates.dates`
  massivinin uzunluğunun cəmi; bir gündə iki saat varsa gün iki dəfə sadalanır).
* `Q` — həmin tələbənin `point = 'qb'` olan xanalarının sayı.
* «bütün rəqəmli qiymətlər» = `k1`, `k2`, `k3` kollokviumları **və** gündəlik
  seminar/məşğələ/lab qiymətləri — hamısı 0…10 şkalasında və **bərabər çəkili**.
  Jurnalda keçirilmiş, lakin tələbənin iştirak etmədiyi kollokvium **0** kimi sayılır.
* `ROUND` = PHP-nin `round()`-u: 0.5 yuxarı (39.5 → 40).

10 + 10 + 30 = **50** — Azərbaycan «çoxballı qiymətləndirmə» normativi ilə tam üst-üstə düşür.
İmtahan qalan 50 baldır və `yekun = giriş + imtahan` (17 194 sətrin 16 844-ündə, 97.96 %).

**Nə üçün ballar tam ədəddir:** `sərbəst_iş` onsuz da tam ədəddir, `seminar` isə
üç kollokvium olduqda `3 × (k1+k2+k3)/3 = k1+k2+k3` — yəni tam ədəd. Deməli
yuvarlaqlaşdırma praktikada **yalnız davamiyyət hissəsinə** toxunur və nəticə
həmişə tam ədəd olur. Sahibin «ballar tam ədəddir» ipucusu bununla izah olunur.

---

## 2. Sübutlar

### 2.1 «Bal vərəqi» ixracları — düsturun dörd komponenti açıq görünür

`balvereqi_logs.data` sütunu **iki dəfə HTML-escape olunmuş** cədvəldir
(«Tələbələrin biliyinin çoxballı sistemlə qiymətləndirilməsi cədvəli»).
Sütunları: *Davamiyyət · Sərbəst iş · Sem.-prak./məş./lab. · Giriş bal · İmtahan ·
Güzəşt Giriş/imtahan · Yekun bal*. Nümunə (log id = 2):

| Davamiyyət | Sərbəst iş | Sem — lab | Giriş | yoxlama |
|---|---|---|---|---|
| 8.93 bal | 8 | 23 — 0 | **40** | 8.93+8+23 = 39.93 → 40 ✔ |
| 9.47 bal | 9 | 27.75 — 0 | **46** | 9.47+9+27.75 = 46.22 → 46 ✔ |
| 9.73 bal | 10 | 30 — 0 | **50** | 49.73 → 50 ✔ |
| 0.27 bal **(Kəsr)** | — | 0 — 0 | **0** | kəsr → 0 ✔ |

52 386 ixracdan çıxarılmış **903 943** tələbə sətri üzərində:

| ixrac ili | sətir | `giriş = round(dav+si+sem+lab)` dəqiq | ±1 |
|---|---|---|---|
| 2023 | 17 508 | 99.95 % | **100.00 %** |
| 2024 | 165 570 | 96.90 % | **100.00 %** |
| 2025 | 340 537 | 97.16 % | **100.00 %** |
| 2026 | 376 137 | 97.34 % | **100.00 %** |
| **cəmi** | **899 752** | **97.24 %** | **100.00 %** |

±1 fərq HTML-də komponentlərin **2 onluq rəqəmə yuvarlaqlaşdırılmış** çap
olunmasından gəlir (məs. 8.6666… → «8.67»), düsturdan yox. Yəni **kompozisiya
qaydası 2023–2026 arası dəyişməyib**.

### 2.2 Davamiyyət alt-düsturu

**(a) Bal vərəqlərindən.** Hər vərəqdə bütün tələbələr eyni `N`-i paylaşır.
5-dən çox tələbəsi olan **55 096 vərəqin 55 096-sı (100.00 %)** üçün elə tam `N`
tapılır ki, hər tələbənin `10 − davamiyyət` dəyəri `10·q/N` (q tam) şəklindədir.
Ən çox rast gəlinən `N`-lər: 30, 15, 61, 22, 43, 24, 45 — yəni jurnal xanası sayı.

**(b) `yekun`-dan.** Digər komponentləri sırf tam ədəd olan (tək jurnal,
`si` var, düz 3 kollokvium, gündəlik qiymət yox) **2 499** sətirdə
`davamiyyət_faktiki = girish − si − Σk` hesablandı:

| yuvarlaqlaşdırma | uyğunluq |
|---|---|
| **round(10·(N−Q)/N)** | **92.52 %** |
| ceil | 68.27 % |
| floor | 61.46 % |

Bütün `(Q, N)` cütlərində **moda dəyəri round-un verdiyi ədədlə eynidir** —
bir dənə də istisna yoxdur. Nümunələr:

| Q | N | 10·(N−Q)/N | round | faktiki paylanma |
|---|---|---|---|---|
| 1 | 15 | 9.333 | 9 | 9:135, 10:4 |
| 1 | 23 | 9.565 | **10** | 10:152 (100 %) |
| 2 | 23 | 9.130 | 9 | 9:134, 10:4 |
| 3 | 15 | 8.000 | 8 | 8:30, 9:6 |
| 4 | 23 | 8.261 | 8 | 8:61, 9:6 |
| 4 | 30 | 8.667 | **9** | 9:62, 8:1 |
| 5 | 30 | 8.333 | 8 | 8:63, 9:1 |

Diqqət: `Q=1, N=23` → 10, amma `Q=1, N=15` → 9. Yəni cərimə **sayla deyil,
faizlə** işləyir — bu, sahibin «öz cədvəli var» ipucusunun mahiyyətidir.

**Üzrlü qayıb (`excusable`) davamiyyət balına TƏSİR ETMİR.** Üzrlü qayıbları
saymamaq variantı uyğunluğu **heç dəyişmir** (13 112 → 13 112). `why` sahəsi
sırf qeyddir.

### 2.3 Seminar alt-düsturu

**(a) Bal vərəqlərindən.** «Sem.» sütununun 1 080 fərqli dəyərinin hamısı
(903 943 sətrin 903 739-u = **99.989 %**) `3 × (tam qiymətlərin ortası)` formasına
uyğundur: 21, 24, 27, 30, 22.5 (=3·7.5), 21.75 (=3·29/4), 28.2 (=3·47/5),
14.6 (=3·73/15) …

**(b) `yekun`-dan.** Davamiyyəti 10 olan (Q = 0) və tək `si` xanası olan
**4 075** sətirdə `seminar_faktiki = girish − 10 − si` hesablandı:

| namizəd | uyğunluq |
|---|---|
| **3 × orta(k + gündəlik qiymətlər)** | **79.09 %** |
| 3 × orta(yalnız k) | 50.21 % |
| Σk (kollokviumların cəmi) | 47.41 % |
| 3 × ceil(orta) | 38.63 % |
| 3 × round(orta) | 37.60 % |
| 3 × max(qiymətlər) | 29.82 % |

Gündəlik qiymətləri olan sətirlərdə fərq daha kəskindir: `3 × orta(hamısı)`
**83.29 %**, `Σk` isə cəmi 40.84 %.

---

## 3. Qayıb cəriməsi cədvəli

Cərimə **faizlə pilləlidir** (`davamiyyət = 10 − round(10 × qayıb_faizi)`):

| buraxılmış saatın payı | davamiyyət balı | itirilən bal |
|---|---|---|
| 0 % – **5 %** (daxil) | **10** | 0 |
| 5 % – **15 %** (daxil) | **9** | 1 |
| 15 % – **25 %** (daxil) | **8** | 2 |
| 25 % – **35 %** (daxil) | **7** | 3 (25 %-dən yuxarı → **kəsr**) |
| 35 % – **45 %** (daxil) | **6** | 4 |
| 45 % – **55 %** (daxil) | **5** | 5 |
| 55 % – **65 %** (daxil) | **4** | 6 |
| 65 % – **75 %** (daxil) | **3** | 7 |
| 75 % – **85 %** (daxil) | **2** | 8 |
| 85 % – **95 %** (daxil) | **1** | 9 |
| 95 %-dən yuxarı | **0** | 10 |

> Sərhəd **yuxarı ucda daxildir**, çünki `round()` 0.5-i yuxarı aparır: tam 5 %
> qayıbda hələ 10 bal, tam 25 % qayıbda hələ 8 bal verilir (və hələ kəsr deyil).
> Bu cədvəl `legacy_girish_reference.QAYIB_CEDVELI`-dədir və `N ≤ 200` üçün
> `round(10·(N−Q)/N)` ilə **bir dənə də fərqi yoxdur**.

Eyni cədvəl mütləq qayıb sayı ilə (sətir = qayıb sayı, sütun = jurnalın xana sayı `N`):

| qb | N=8 | N=10 | N=15 | N=23 | N=30 | N=45 | N=60 | N=75 |
|---|---|---|---|---|---|---|---|---|
| 0 | 10 | 10 | 10 | 10 | 10 | 10 | 10 | 10 |
| 1 | 9 | 9 | 9 | 10 | 10 | 10 | 10 | 10 |
| 2 | 8 | 8 | 9 | 9 | 9 | 10 | 10 | 10 |
| 3 | 6 | 7 | 8 | 9 | 9 | 9 | 10 | 10 |
| 4 | 5 | 6 | 7 | 8 | 9 | 9 | 9 | 9 |
| 5 | 4 | 5 | 7 | 8 | 8 | 9 | 9 | 9 |
| 6 | 3 | 4 | 6 | 7 | 8 | 9 | 9 | 9 |
| 7 | 1 | 3 | 5 | 7 | 8 | 8 | 9 | 9 |
| 8 | 0 | 2 | 5 | 7 | 7 | 8 | 9 | 9 |
| 9 | – | 1 | 4 | 6 | 7 | 8 | 9 | 9 |
| 10 | – | 0 | 3 | 6 | 7 | 8 | 8 | 9 |
| 12 | – | – | 2 | 5 | 6 | 7 | 8 | 8 |
| 15 | – | – | 0 | 3 | 5 | 7 | 8 | 8 |
| 20 | – | – | – | 1 | 3 | 6 | 7 | 7 |
| 25 | – | – | – | – | 2 | 4 | 6 | 7 |

Pillə sərhədləri (davamiyyət balının dəyişdiyi qayıb sayı):

```
N= 15 : 0→10, 1→9, 3→8, 4→7, 6→6, 7→5, 9→4, 10→3, 12→2, 13→1, 15→0
N= 23 : 0→10, 2→9, 4→8, 6→7, 9→6, 11→5, 13→4, 15→3, 18→2, 20→1, 22→0
N= 30 : 0→10, 2→9, 5→8, 8→7, 11→6, 14→5, 17→4, 20→3, 23→2, 26→1, 29→0
N= 45 : 0→10, 3→9, 7→8, 12→7, 16→6, 21→5, 25→4, 30→3, 34→2, 39→1, 43→0
N= 60 : 0→10, 4→9, 10→8, 16→7, 22→6, 28→5, 34→4, 40→3, 46→2, 52→1, 58→0
N= 75 : 0→10, 4→9, 12→8, 19→7, 27→6, 34→5, 42→4, 49→3, 57→2, 64→1, 72→0
```

### Kəsr

`kəsr ⟺ Q / N > 0.25` (ekvivalent: `davamiyyət < 7.5`) — `yekun.kesr` bayrağını
**13 878 / 15 942 = 87.05 %** dəqiqliklə təkrarlayır. Uyğunsuzluqların əsas
səbəbi: kəsr köhnə sistemdə **hər jurnal üzrə ayrıca** hesablanıb (mühazirə
jurnalında 25 %-i keçib, birləşmiş hesabla keçməyib). Müasir bal vərəqlərində
kəsr alan tələbənin **giriş balı 0 yazılır**; `yekun` dövründə isə belə deyil
(aşağıda «kəsr klasteri»).

---

## 4. Uyğunluq faizi (17 194 `yekun` sətri)

> `information_schema` 17 252 göstərir — bu, InnoDB-nin təxminidir; cədvəldə
> faktiki **17 194** sətir var.

| çoxluq | sətir | **dəqiq** | ±1 | ±2 |
|---|---|---|---|---|
| **normal fənlər** (`level = 0`) | 15 942 | **13 141 (82.43 %)** | 14 783 (92.73 %) | ≈15 220 (95.5 %) |
| «Level» ingilis dili kursları (`level = 1`) | 1 252 | 59 (4.71 %) | 112 (8.95 %) | 158 (12.62 %) |
| **cəmi** | 17 194 | **13 200 (76.77 %)** | 14 895 (86.63 %) | ≈15 378 (89.4 %) |

(rəqəmlər `python3 verify_girish.py` çıxışıdır)

Məlumatı **tam** olan alt-çoxluqda (bir jurnal, `si` var, 3 kollokvium var —
12 490 sətir, normal sətirlərin 78 %-i):

> **dəqiq 10 905 (87.31 %) · ±1 11 978 (95.90 %)**

Fərq histoqramı (normal sətirlər, ±9-da kəsilib):

```
-9:  39   -4:  31   -3:  95   -2: 303   -1: 1062
 0: 13141
+1: 580   +2: 135   +3:  61   +4:  27   +9: 408
```
(`-9` və `+9` sütunları ±9 və daha böyük fərqlərin cəmidir)

### Uyğunsuzluqların anatomiyası (2 801 sətir)

| səbəb | sətir | şərh |
|---|---|---|
| `|fərq| = 1` | 1 640 (58.5 %) | sərhəd yuvarlaqlaşdırması / `N`-in bir-iki xana fərqi |
| `|fərq| = 2` | 438 | eyni, daha güclü |
| «kəsr → yalnız davamiyyət» klasteri | 300 (232-si `kesr=1`) | `girish ≤ 15` olduğu halda komponentlər 25–47 verir |
| çox-jurnallı sətirlər | 1 104 / 3 182 (**34.7 %** xəta) | tək jurnallı sətirlərdə xəta cəmi 13.2 % |
| `si` xanası ümumiyyətlə yoxdur | 38 | |
| heç bir qiymət xanası yoxdur | 22 | |

Ən böyük struktur problemi **jurnal cütləşdirməsidir**: `yekun.journal_id`
çox vaxt yalnız *mühazirə* jurnalını göstərir, kollokvium/sərbəst iş isə eyni
`lesson_id`-li *seminar* jurnalındadır. Model komponentləri eyni `lesson_id` və
`semestr = 3` olan bütün jurnallardan yığır (bu, dəqiqliyi 79.3 % → 82.4 %
qaldırdı), amma bir tələbə eyni fənnin iki müxtəlif jurnalında (məs. təkrar
qrup) olanda həddindən artıq yığım baş verir — `+9` klasterinin (408 sətir)
əsas hissəsi budur.

---

## 5. Uyğunsuzluq nümunələri (konkret id-lərlə)

Format: `student_id / journal_id / lesson_id · faktiki girish · modelin verdiyi`

| # | student | journal | lesson | girish | model | fərq | dav (Q/N) | si | seminar | kollokvium | gündəlik | qeyd |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1500 | 2964 | 5 | 34 | 35 | +1 | 9.231 (2/26) | 8 | 18.00 | 4,6,6,7,7 | — | 4 jurnal birləşib |
| 2 | 3554 | 2837 | 1042 | 42 | 40 | −2 | 10.000 (0/8) | 8 | 22.00 | 6,8,8 | — | seminar 24 lazımdır (=3·8) |
| 3 | 3319 | 2774 | 5 | 37 | 41 | +4 | 10.000 (0/22) | 8 | 23.25 | 6,8,8 | 9 | 6 jurnal — həddən artıq yığım |
| 4 | 1318 | 2722 | 110 | 46 | 45 | −1 | 10.000 (0/15) | 9 | 25.50 | 8,8,9 | 9 | sərhəd |
| 5 | 3154 | 2651 | 5 | 37 | 34 | −3 | 10.000 (0/5) | 6 | 18.00 | 5,6,7 | — | |
| 6 | 1273 | 2506 | 119 | 48 | 49 | +1 | 9.268 (3/41) | 10 | 29.25 | 9,10,10 | 10 | sərhəd |
| 7 | 2669 | 2251 | 1230 | 45 | 43 | −2 | 9.667 (1/30) | 10 | 23.79 | 7,8,10 | 7,7,7,7,8,8,8,8 | |
| 8 | 811 | 2145 | 85 | 47 | 48 | +1 | 9.737 (1/38) | 10 | 28.20 | 9,10,10 | 8,10 | sərhəd |
| 9 | 1485 | 2013 | 5 | 29 | 30 | +1 | 8.750 (3/24) | 5 | 15.75 | 4,5,7 | 5 | 3 jurnal |
| 10 | 1060 | 1758 | 105 | 43 | 40 | −3 | 9.474 (2/38) | 10 | 20.57 | 7,8,9 | 1,7,7,9 | «1» qiyməti sonradan yazılmış ola bilər |
| 11 | 1718 | 1463 | 413 | 44 | 43 | −1 | 8.696 (3/23) | 10 | 24.60 | 8,9,10 | 6,8 | sərhəd |
| 12 | 1800 | 1188 | 1795 | 36 | 37 | +1 | 7.812 (7/32) | 8 | 21.00 | 6,7,7 | 6,8,8 | sərhəd |
| 13 | 919 | 2962 | 834 | **9** | 47 | +38 | 8.750 (2/16) | 10 | 27.86 | 9,9,9 | 9,10,10,10 | «kəsr» klasteri |
| 14 | 918 | 2962 | 834 | **10** | 40 | +30 | 9.375 (1/16) | 10 | 20.57 | 7,7,7 | 5,7,7,7 | «kəsr» klasteri |
| 15 | 3461 | 2957 | — | **13** | 40 | +27 | 6.667 (10/30) | 9 | 24.00 | 8,8,8 | — | «kəsr» klasteri |

**Xüsusi diqqət — 2962 nömrəli jurnal.** «Dil Tarixi (mühazirə)», 175 və 176
qruplarını əhatə edir. 176 qrupunun tələbələrində (908–919) `girish` 8–10-dur,
halbuki komponentlər 25–47 verir. Onların `girish` dəyəri **təxminən yalnız
davamiyyət balına** bərabərdir (st 919 → dav 8.75 → 9 = girish; st 909 → dav
10 = girish). Yəni köhnə sistem bu tələbələr üçün kəsr səbəbindən seminar və
sərbəst iş hissələrini sıfırlayıb — amma bu davranış bütün `kesr = 1`
sətirlərində təkrarlanmır (1 486 kəsr sətrinin əksəriyyəti normal düsturla
hesablanıb), ona görə qayda kimi modelə salınmayıb.

**2837 nömrəli jurnal** (nümunə #2) ayrıca maraqlıdır: 8 tələbənin **hamısında**
`seminar_faktiki = 3 × (floor(orta) + 1)`, yəni orta yuxarı pilləyə yuvarlanıb.
Bu davranış cəmi bir neçə jurnalda müşahidə olunur (yalnız kollokvium olan
1 088 sətrin ~30 %-i) — ya köhnə sistemdə ikinci bir rejim olub, ya da həmin
xanalar `yekun` hesablandıqdan sonra redaktə edilib.

---

## 6. Güzəşt sahələri

| sahə | sıfırdan fərqli sətir | rolu |
|---|---|---|
| `guzest_girish` | 20 (dəyərlər 2, 4, 10) | **giriş balına ƏLAVƏ OLUNMUR** |
| `guzest_artim` | 614 (dəyərlər 1, 2, 3, 5, 6, 7, 9, 10) | **giriş balına ƏLAVƏ OLUNMUR** |

Ölçmə (yalnız güzəşti olan sətirlər):

| variant | `guzest_artim ≠ 0` (536 sətir) | `guzest_girish ≠ 0` (8 sətir) |
|---|---|---|
| düstur olduğu kimi | **424 dəqiq** | **7 dəqiq** |
| düstur + `guzest_artim` | 15 | 7 |
| düstur + `guzest_girish` | 424 | 0 |

Yəni güzəşti əlavə etmək dəqiqliyi **28 dəfə pisləşdirir**. Həmçinin:

* `yekun = girish + imtahanda` güzəştli sətirlərin **613 / 614**-ündə də doğrudur
  (güzəşt yekuna da əlavə olunmur);
* `im` xanası ilə `yekun.imtahanda` güzəştli sətirlərin 520 / 592-sində
  **eynidir** (güzəşt imtahan balına da sonradan əlavə olunmayıb).

**Nəticə:** `guzest_girish` / `guzest_artim` sırf **qeyddir** — hansı güzəştin
verildiyini saxlayır (bal vərəqində «Güzəşt Giriş/imtahan» sütunu kimi çap olunur),
lakin `girish` sütununun hesablanmasına daxil deyil. Ehtimal ki, hərfi qiymətə
(A–F) çevirmə mərhələsində istifadə olunub.

---

## 7. İllər üzrə fərq

`yekun` cədvəli **tək bir semestrin** snapshot-udur: bütün 17 194 sətir
`journals.semestr = 3` jurnallarına aiddir (2022-09-14 … 2023-02-22, yəni
**2022/2023 payız** semestri). `yekun_old` və `yekun_24_02_2023` cədvəlləri boşdur.
Deməli `yekun` daxilində il-il müqayisə mümkün deyil.

İllər arası sabitlik bal vərəqləri ilə ölçüldü (§2.1 cədvəli): kompozisiya
qaydası **2023-08 … 2026-08 arası 100 % ±1 sabitdir**. Tək fərq **təqdimatda**:
2023-dən sonrakı vərəqlərdə seminar sütunu «sem — lab» şəklində iki hissəyə
bölünür (laboratoriyası olan fənlər üçün ayrıca orta). Balın özündə hər iki hissə
sadəcə toplanır.

| dövr | düstur |
|---|---|
| 2022/2023 payız (`yekun`, semestr 3) | `round(dav + si + 3·orta(k + gündəlik))`, maks 50 |
| 2023-08 … 2026-08 (bal vərəqləri) | eyni; seminar «sem» + «lab» kimi iki ortaya bölünə bilər |

---

## 8. Jurnal xanalarının lüğəti (əlavə tapıntılar)

`journals_dates_points`:

* `point`: `ie` = iştirak edib (3.5 M), `qb` = qayıb (632 K), `0…10` = gündəlik
  qiymət, `17…50` = «Level» kurslarının bacarıq balları, boş = yazılmamış,
  `l` (493 sətir, mənası aydınlaşmadı).
* `month_id` / `day_number` xüsusi dəyərləri:
  `k1`, `k2`, `k3` = kollokvium 1/2/3 (0…10) · `si` = sərbəst iş (0…10) ·
  `im` = imtahan · `im2` = təkrar imtahan ·
  `ss`, `ww`, `ll`, `rr` = **yalnız «Level» kurslarında** speaking / writing /
  listening / reading (hər biri 0…25) · `pa`, `wr` = həmin kurslarda əlavə
  komponentlər (0…10) · `ga` (25 sətir, mənası aydınlaşmadı).
* `excusable` / `why` — giriş balına **təsir etmir** (§2.2).
* `sem_muh` (0/1/2/3) və `lab` (0/1) — semestr 3 jurnallarında `lab` xanaların
  demək olar hamısında 1-dir, yəni həmin dövrdə bu bayraq başqa məna daşıyıb;
  giriş balının hesablanmasında ayırıcı rol oynamır.
* `journals_dates_points` ↔ `journals` bağlantısı: **`journal_uniqid = journals.uniqid`**
  (yeganə etibarlı açar). `j_id` sütunu 5.1 M sətrin 4.38 M-ində **NULL**-dur;
  dolu olduqda `uniqid` ilə heç vaxt ziddiyyət təşkil etmir (0 uyğunsuzluq).
* `journals_dates_points_archive` (772 K) — 2022-12-31-də dayanmış snapshot.
  Onunla hesablama `yekun`-a **daha pis** uyğun gəlir (81.07 % vs 82.43 %), yəni
  canlı cədvəl istifadə edilməlidir.

### «Level» ingilis dili kursları (`yekun.level = 1`, 1 252 sətir)

Bu 1 252 sətir başqa sxemdədir və giriş balı **50-ni aşa bilir** (maksimum 59;
`level = 0` sətirlərində heç vaxt 50-ni keçmir). Onların **imtahan** tərəfi tam
həll olundu:

```
imtahan = 0.4 × (ss + ww + ll + rr)        # dörd bacarıq, hər biri 0…25
```

(nümunə: ss 18 + ww 20 + ll 14 + rr 17 = 69 → 27.6 = `yekun.imtahanda` ✔).
Giriş tərəfi həll olunmadı — `pa`, `wr` komponentlərinin çəkisi və davamiyyətin
şkalası (10 yoxsa 20?) datadan birmənalı çıxmadı.

---

## 9. Əminlik səviyyəsi

| komponent | əminlik | əsas |
|---|---|---|
| `giriş = round(davamiyyət + sərbəst_iş + seminar)`, maks 50 | **çox yüksək (≈99 %)** | 899 752 bal vərəqi sətrində 100 % ±1, 97.24 % dəqiq; sütun adları düsturu birbaşa göstərir |
| `davamiyyət = 10·(N−Q)/N` | **çox yüksək** | 55 096 / 55 096 vərəq formaya uyğun; izolyasiya testində 92.52 % (ceil/floor 61–68 %) |
| Yuvarlaqlaşdırma = `round()` (0.5 yuxarı), sonda bir dəfə | **yüksək** | floor/ceil variantları 46–60 %-ə düşür |
| `sərbəst_iş` = `si` xanası, 0…10 | **çox yüksək** | bal vərəqində ayrıca sütun; `yekun`-da birbaşa uyğunluq |
| `seminar = 3 × orta(k1,k2,k3 + gündəlik qiymətlər)` | **yüksək (≈85 %)** | 99.989 % bal vərəqi dəyəri bu formaya uyğun; alternativlərdən 29 f.b. üstün |
| Kollokvium və gündəlik qiymətlərin **bərabər çəkili** olması | **orta** | ortalama üstündür, amma yalnız kollokvium olan sətirlərdə 67.6 %-də qalır |
| İştirak edilməyən kollokviumun 0 sayılması | **orta** | +0.2 f.b. yaxşılaşma (82.25 % → 82.43 %) |
| `N` = `journals_dates`-dəki gün×saat xanalarının sayı | **orta-yüksək** | `max(N, tələbənin xana sayı)` variantı bir qədər yaxşıdır |
| Kollokvium/sərbəst işin qardaş jurnaldan yığılması | **orta** | 79.3 % → 82.4 %; həddən artıq yığım `+9` klasterini yaradır |
| `kəsr ⟺ qayıb > 25 %` | **orta-yüksək (87 %)** | jurnal-səviyyəsində hesablandığı üçün fərqlər var |
| Güzəşt sahələrinin girişə daxil OLMAMASI | **çox yüksək** | əlavə etmək dəqiqliyi 424 → 15 endirir |
| Üzrlü qayıbın təsirsizliyi | **çox yüksək** | fərq sıfırdır |
| «Level» kurslarının imtahan düsturu (`0.4 × Σ4 bacarıq`) | **yüksək** | yoxlanılan nümunələrin hamısında dəqiq |
| «Level» kurslarının **giriş** düsturu | **əminlik yoxdur** | həll olunmadı |
| `kesr = 1` üçün girişin sıfırlanması | **aşağı** | 300 sətirdə müşahidə olunur, qalan 1 186 kəsr sətrində yox |

### Nədən əmin deyiləm / sahibə soruşulmalı

1. **Seminar hissəsinin dəqiq tərifi.** «3 × orta(bütün qiymətlər)» ən yaxşı
   uyğunlaşandır, amma bir neçə jurnalda (məs. 2837, 2863) ortanın **yuxarı
   pilləyə** yuvarlandığı görünür. Köhnə sistemdə iki rejim vardımı?
2. **`N`-in mənbəyi.** `journals_dates` xana sayı, yoxsa `journals.fenn_saati`
   (11 210 sətirdə 0-dır, ona görə istifadə edilə bilmədi), yoxsa sillabusdakı
   `ders_saati`?
3. **Kollokvium ilə gündəlik qiymətin çəkisi.** Doğrudanmı bərabərdir, yoxsa
   kollokvium 3 dəfə ağırdır?
4. **Mühazirə + seminar jurnallarının birləşdirilmə qaydası.** Hansı jurnallar
   bir «fənn qeydiyyatı» sayılırdı — `lesson_id` + qrup, yoxsa `parent_id`?
5. **Kəsr alan tələbənin giriş balı.** Müasir vərəqlərdə 0 yazılır; `yekun`
   dövründə niyə bəzən «yalnız davamiyyət», bəzən tam düsturdur?
6. **«Level» kurslarının giriş düsturu** (`pa`, `wr`, `ss/ww/ll/rr` çəkiləri).

---

## 10. Təkrar icra

```bash
cd <scratchpad>
python3 legacy_girish_reference.py     # kiçik self-test
python3 verify_girish.py --examples 20 # 17 194 sətrin hamısına qarşı hesabat
```

`verify_girish.py` lazım olan cədvəlləri `docker exec … mariadb -e "SELECT …"`
ilə özü çıxarır (yalnız oxuma) və `vg_*.tsv` kimi keşləyir; `--refresh` ilə
yenidən çəkir.

Bal vərəqi analizini təkrarlamaq üçün (xam ixrac ~1 GB olduğu üçün silinib,
`bal_rows.tsv` isə saxlanılıb):

```bash
docker exec emsarena-legacy-source-rehearsal sh -c \
  'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" myedudb -N -e \
   "SELECT id,owner_id,uniqid,export_time,data FROM balvereqi_logs ORDER BY id;"' \
  > balvereqi.tsv
python3 parse_bal.py      # -> bal_rows.tsv (903 943 sətir)
python3 bal_dav.py        # davamiyyət formasının yoxlanışı
python3 bal_sem.py        # seminar formasının yoxlanışı
python3 bal_by_year.py    # illər üzrə sabitlik
```
