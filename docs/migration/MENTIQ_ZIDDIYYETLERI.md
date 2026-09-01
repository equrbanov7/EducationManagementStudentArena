# Məntiq ziddiyyətləri — köhnə MyEdu datasının yoxlanışı

**Tarix:** 2026-08-31 · **Versiya:** v2 (düzəldilmiş) · **Rejim:** yalnız-oxu (SELECT) ·
**Repetisiya bazası:** `emsarena_rehearsal_52ea0301808c` · **run_id:** `7c3e8d46-0464-4f52-bbe7-7afd852b5bf3`

---

# ⚠️ DÜZƏLİŞ QEYDİ (v1 → v2)

Sizə göndərilmiş **v1** siyahısı düşmən baxışından keçdi. Baxış **arifmetikada və
data zəncirində bir dənə də səhv tapmadı** — onlarla sətir uçdan-uca izlənib,
hamısı bazayla üst-üstə düşdü, köçürmə sadiqliyi də təsdiqləndi. Tapılanların
hamısı **interpretasiya və təqdimat** qüsurları idi. Aşağıda hər biri və nə
edildiyi.

## 1. 🔴 ŞƏXSİYYƏT AÇARI TOQQUŞMASI — ən vacib düzəliş

**Nə səhv idi.** «Tələbə ID» adlı sütun iki fərqli vərəqdə **iki fərqli açar
fəzasını** göstərirdi:

* **B vərəqi** → köhnə MyEdu `students.id`
* **C vərəqi** → yeni sistemin `auth_user.id`

Eyni sütun adı, eyni görkəmli rəqəmlər — amma başqa-başqa nömrələmə.
C-dəki **3 118 tələbənin 100 %-inin** nömrəsi köhnə nömrədən fərqlidir və
**1 964-ü (63 %) köhnə bazada BAŞQA REAL TƏLƏBƏYƏ aiddir.**

> **Sübut.** C-də `telebe_id = 5918` → doğru şəxs **Abdullayev Eldar**
> (`myedu.student.8171`, qrup 235 EM).
> Köhnə bazada isə `students.id = 5918` = **İsmayılova Mələkxanım Güloğlanovna**,
> qrup 2532 Bİ — **tamam başqa adam**.
>
> Dekanlıq bu nömrə ilə tələbə axtarsaydı, **səhv adamın üzərinə rəsmi qərar**
> çıxa bilərdi.

**Nə edildi.** Hər vərəqdə indi **hər iki açar ayrıca sütundur**, açarın hansı
sistemə aid olduğu **sütun adında açıq yazılıb**:

| sütun | nədir |
|---|---|
| **Köhnə sistem ID (MyEdu students.id)** | köhnə MyEdu bazasında axtarış üçün (sarı fon) |
| **Yeni sistem ID (auth_user.id)** | yeni EMS Arena bazasında axtarış üçün (mavi fon) |
| **İstifadəçi adı (login)** | **birmənalı açar** — `myedu.student.<köhnə id>` |
| Ad, soyad · Qrup | insan gözü ilə yoxlama üçün |

Əlavə olaraq yeni **«🔑 Şəxsiyyət körpüsü»** vərəqi var: siyahılarda adı keçən
**5 166 tələbənin** hər üç açarı bir yerdə, üstəlik **hansı vərəqlərdə göründüyü**
(`A` / `B` / `C` və kombinasiyaları) — B ilə C arasında **çarpaz istinad** məhz
oradan aparılır. Nömrəsi köhnə bazada başqa tələbəyə düşən **3 575 sətirdə**
açıq xəbərdarlıq mətni var.

> **Praktik qayda:** rəsmi qərar çıxarmazdan əvvəl **istifadəçi adı (login)** ilə
> yoxlayın. Yalnız o, iki sistemdə də birmənalıdır.

## 2. İstifadəçi adı defislə yazılmışdı

**Nə səhv idi.** A vərəqi `myedu-student-1090` yazırdı. Həqiqi login **nöqtə**
ilədir: `myedu.student.1090`. Yəni **17 107 sətrin hamısının** nömrəsi axtarışda
heç nə tapmayacaqdı.

**Nə edildi.** Bütün istifadəçi adları həqiqi login formatına çevrildi; köhnə
`students.id` ayrıca sütuna çıxarıldı, yeni `auth_user.id` isə körpüdən əlavə edildi.

## 3. A vərəqinin başlığı miqyası ~17× şişirdirdi

**Nə səhv idi.** Başlıq «**Yekun ≠ Giriş + Çıxış — 17 107 sətir**» deyirdi.
Bu tərifə uyğun **cəmi 1 sətir** var. Qalanı tamamilə başqa siniflərdir.

**Nə edildi.** Vərəq **«A — Yekun, giriş, çıxış»** adlandırıldı; hər sətrə
**«Sinif»** və **«Ziddiyyətdir?»** sütunları əlavə edildi; xülasə alt siniflər
üzrə ayrıldı.

| sinif | sətir | ziddiyyətdir? | nədir |
|---|---:|---|---|
| **A1** | **1** | **bəli** | yekun cəmdən böyükdür (>±1) — *yeganə həqiqi arifmetik uyğunsuzluq* |
| **A2** | **0** | bəli | yekun cəmdən kiçikdir (>±1) — **heç bir sətir yoxdur** |
| **A5** | **1 068** | **bəli** | bal diapazondan kənar (yekun>100, çıxış>50, mənfi giriş) |
| **A3** | **250** | **bəli** | giriş və/və ya çıxış yoxdur, yekun var |
| A5L | 573 | xeyr | Xarici dil / «Level» kursu — ayrı sxem, məlumat üçün |
| A2r | 64 | xeyr | ±1 yuvarlaqlaşdırma zolağı |
| A4 | 12 431 | xeyr | **yekun qeydi ÜMUMİYYƏTLƏ yoxdur** — köçürmə tapşırığı |
| A4z | 2 720 | xeyr | eyni, çıxış balı 0 |

**Həqiqi ziddiyyət: 1 319 sətir** (A1+A2+A3+A5), 716 unikal tələbə.
Qalan **15 788 sətir** ya köçürmə tapşırığıdır (yekun yazılmayıb — 15 151),
ya yuvarlaqlaşdırmadır, ya da ayrı bal sxemli kursdur.

> ✅ **Yaxşı xəbər gizlədilmir.** Arifmetika demək olar qüsursuzdur:
> `yekun = round(giriş + çıxış)` qaydası saxlanmış `yekun` cədvəlində
> **99.994 %** (17 193/17 194), çap olunmuş bal vərəqlərində **99.950 %**
> (127 113/127 177) doğrudur. Rədd edilən namizədlər: `floor(giriş)+çıxış` → 55.98 %,
> çəkili variantlar və `(a+b)/2` → təsadüf səviyyəsi.

## 4. C-nin plan-əsaslı cütləri şübhəli idi

**Nə səhv idi.** `curricula_plan.lesson_before_id` sahəsinin **«ön şərt»** yoxsa
sadəcə **«plan sırası»** olduğu təsdiqlənməyib, amma v1 hər iki mənbədən gələn
cütləri **eyni kefiyyətdə** göstərirdi.

Ölçdük: `lesson_before_id` dolu olan **446 plan sətrinin 37-si** və onlardan
çıxan **235 fərqli cütün 50-si daxilən yararsızdır**:

| qüsur | plan sətri | fərqli cüt |
|---|---:|---:|
| ön şərt fənnin **ÖZÜNƏ** istinad edir | 18 | 23 |
| ön şərt həmin tədris planında **ümumiyyətlə yoxdur** | 18 | 26 |
| ön şərt **eyni semestrə** qoyulub | 1 | 1 |

**Nə edildi — üç iş.**

**(a) Ad-əsaslı və plan-əsaslı cütlər AYRILDI.** Hər C sətrində indi
«Cüt mənbəyi» sütunu var:

| cüt mənbəyi | sətir | etibar |
|---|---:|---|
| **ad ardıcıllığı + tədris planı** (ikiqat təsdiq) | 1 339 | **ƏN GÜCLÜ** — hər iki mənbə eyni şeyi deyir |
| **ad ardıcıllığı** | 71 | **SAĞLAM** — nəzarətdə bir dənə də yanlış cüt tapılmadı |
| **YALNIZ tədris planı ⚠** | 3 042 | **EHTİYATLA** — sahənin mənası təsdiqlənməyib |

**(b) Daxilən yararsız cütlərin sətirləri ÇIXARILDI** — **455 sətir**.
Onlar ayrıca **«C — çıxarılan sətirlər»** vərəqində, çıxarılma səbəbi ilə
saxlanılır. **Hamısı C3 idi** (orta/aşağı şiddət) — **kritik C1/C2/C4-dən heç
bir sətir çıxarılmadı**.

**(c) Şübhəli plan cütlərinə sətir səviyyəsində xəbərdarlıq yapışdırıldı**
(**877 sətir**):

| şübhə siqnalı | nümunə |
|---|---|
| **fan-out** — bir fənn planda 3+ fərqli fənnə ön şərt göstərilib | «Ümumi psixologiya-1 (psixologiyaya giriş)» → **6 fərqli fənn**, cəmi **779 pozuntu** |
| **nömrə atlanır** | «Tələffüz və şifahi nitq vərdişləri **-1** → **-3**» (‑2 atlanır), 38 pozuntu |
| **paralel hissələr** | «İnformasiyanın mühafizəsi… **(təşkilati və hüquq)** → **(proqram texniki)**» — ardıcıllıq deyil, bölmə |

Digər şübhəli cütlər (hamısı «YALNIZ tədris planı ⚠» qrupundadır və cüt
kataloqundan atıla bilər): «Rəsm‑4 → Xüsusi resm» (43), «Rəsm‑4 → Xüsusi
qrafika» (3), «Qrafik dizaynda layihələndirilməsi əsasları → Kompozisiya /
Layihələndirmə».

**Kritik hissə üçün konkret rəqəm:** C1+C2-nin **783 sətrinin 463-ü (59 %)**
yalnız plan sahəsinə söykənir. Bu 463 sətir **cəmi 10 cütdən** gəlir və
**heç birində şübhə siqnalı yoxdur** — cütlər məzmunca da inandırıcıdır
(«Xətti cəbr → Ehtimal nəzəriyyəsi» 198, «Ehtimal nəzəriyyəsi → Ekonometrika» 127,
«İqtisadiyyata giriş → Mikroiqtisadiyyat» 47, «Ümumi kimya → Biokimya» 35,
«Mikroiqtisadiyyat → Makroiqtisadiyyat» 25 və s.). Yenə də **təsdiq tədris
şöbəsindən keçməlidir**.

> ✅ **Sahibin öz nümunəsi qorunub** — indi hər iki açarla:
> **Abdullayev Eldar Əli** · köhnə ID **8171** · yeni ID **5918** ·
> `myedu.student.8171` · qrup **235 EM** ·
> `Riyaziyyat -1` (2025/2026 Payız) **kəsilib** giriş 32 + çıxış 18 = **50** →
> `Riyaziyyat -2` (2025/2026 Yaz) **keçib** giriş 35 + çıxış 24 = **59**.
> Cüt mənbəyi: **ad + plan (ikiqat təsdiq)**.

## 5. B-nin «Yekun bal» sütunu qarışıq idi

**Nə səhv idi.** Sütun bəzən **müəllimin çap etdiyi** dəyəri, bəzən isə
**jurnaldan bərpa edilmiş hesablamanı** göstərirdi — sütun adı bunu demirdi.

**Nə edildi.** Hər sətir üçün mənbə çap vərəqləri ilə üzləşdirildi və iki yeni
sütun əlavə edildi: **«Yekun balın MƏNBƏYİ»** və **«Yekun balın mənbəyi — izah»**
(izahda konkret log nömrəsi və ixrac tarixi var).

| mənbə | sətir |
|---|---:|
| **çap vərəqindən** (müəllimin imzaladığı vərəqdə həmin rəqəm var) | **2 248** |
| **hesablanıb (rekonstruksiya)** — çap vərəqi yoxdur və ya yekunu fərqlidir | **125** |
| yekun balı ümumiyyətlə yoxdur | 389 |

## 6. A-nın «Mənbə açarı (PK)» sətri müəyyən etmirdi

**Nə səhv idi.** `balvereqi_logs` mənbəli **3 681 sətirdə** PK yalnız **LOG
blokunun** nömrəsidir. Bir log 40+ tələbənin bütöv cədvəlini saxlayır — o
nömrə ilə konkret sətri tapmaq mümkün deyildi.

**Nə edildi.** **«Sətir açarı (sətri tapmaq üçün)»** sütunu əlavə edildi:

```
log 30813 · cədvəl 24 · sətir: MƏMMƏDOVA XEYRANSA RASİM QIZI
          · Atmosferin ekologiyası, müasir çirkləndiricilər
          · giriş=48 imtahan=86 yekun=134
```

3 681 log sətrinin **3 508-i** üçün log daxilindəki **dəqiq cədvəl nömrəsi** də
bərpa edildi. Digər mənbələrdə (`yekun`, `imthngrscxsblr`, hədəf `registrar_finalgrade`)
PK onsuz da sətri birbaşa müəyyən edir və sütun bunu açıq yazır.

## 7. Hədd təqdimatı düzəldildi

**Nə səhv idi.** `dav < 7.50` həddi «**datadan geri mühəndislik**» kimi təqdim
olunurdu. Bu, dəqiq deyil — **empirik optimum bu deyil**:

| hədd | çap bayrağı ilə uyğunluq |
|---|---:|
| 7.44 (**sırf empirik argmax**) | **99.5698 %** |
| **7.50 (istifadə etdiyimiz)** | **99.4458 %** |
| 7.36 | 98.9976 % |
| 7.54 | 99.2042 % |

**Nə edildi.** Hədd indi olduğu kimi təqdim olunur:

> **`dav < 7.50` universitetin 25 % normativindən gəlir**
> (üzrsüz buraxılmış saat > fənnin ümumi saatının 25 %-i), **sonra data ilə
> YOXLANILIB** — 899 956 çap sətrində **99.4458 %** uyğunluq.
> Sırf empirik optimum **7.44** olardı (99.5698 %) — fərq **0.124 faiz bəndi,
> ≈1 116 sətir**. Onu **qəsdən seçmədik**, çünki hədd **müdafiə oluna bilən**
> olmalıdır: normativ rəqəm izah edilə bilir, əyri uydurulmuş rəqəm yox.
> Sərhəd **ciddidir**: `dav == 7.50` olan 485 sətrin cəmi 9-u bayraqlıdır —
> **tam 25 % buraxan hələ buraxılır**.

---

## Fayllar

| fayl | nədir |
|---|---|
| `MENTIQ_ZIDDIYYETLERI.xlsx` | **8 vərəqli** iş kitabı (v1-də 5 idi) |
| `MENTIQ_ZIDDIYYETLERI.csv` | birləşmiş, sadələşdirilmiş versiya (UTF-8 BOM, `;` ayırıcı), 24 321 sətir |
| `mentiq_ziddiyyetleri/SEXSIYYET_KORPUSU.tsv` | 🔑 **YENİ** — köhnə ID ↔ yeni ID ↔ login körpüsü (5 166 tələbə) |
| `mentiq_ziddiyyetleri/A_arifmetik.tsv` | A növü, **27 sütun** (v1: 20) |
| `mentiq_ziddiyyetleri/B_kesilib_neticesi_var.tsv` | B növü, **35 sütun** (v1: 31) |
| `mentiq_ziddiyyetleri/C_ardicil_fenn.tsv` | C növü, **27 sütun** (v1: 23), 4 452 sətir |
| `mentiq_ziddiyyetleri/C_cutler.tsv` | 208 cüt + mənbə, xəbərdarlıq və şübhə siqnalı |
| `mentiq_ziddiyyetleri/C_cixarilan_setirler.tsv` | **YENİ** — çıxarılan 455 sətir, səbəbi ilə |
| `mentiq_ziddiyyetleri/_v1_arxiv/` | v1-in dəyişdirilməmiş nüsxəsi (müqayisə üçün) |

Excel vərəqləri: **⚠ DÜZƏLİŞ QEYDİ** · **Xülasə** · **🔑 Şəxsiyyət körpüsü** ·
**A — Yekun, giriş, çıxış** · **B — Kəsilib, nəticəsi var** · **C — Ardıcıl fənn** ·
**Ardıcıl fənn cütləri** · **C — çıxarılan sətirlər**.
Hər data vərəqində başlıq dondurulub, avtofiltr qoşulub, şiddət rənglənib,
tarixlər həqiqi tarix kimi saxlanılıb. **Köhnə ID sütunu sarı, yeni ID sütunu
mavi fondadır.**

---

> ## ⚠️ ƏN ÖNƏMLİ QEYD — KÖHNƏ DATA DƏYİŞDİRİLMİR
>
> Bu sənəd və ona bağlı cədvəllər **heç bir balı, statusu və ya qeydi düzəltmir**.
> Bütün analiz `SELECT`-lə aparılıb; nə mənbə MariaDB-yə, nə də hədəf PostgreSQL-ə
> **bir dənə də yazma əməliyyatı** getməyib.
>
> Siyahının məqsədi tək şeydir: **əl ilə baxış**. Hansı sətrin həqiqətən səhv
> olduğuna, hansının isə köhnə sistemin qanuni (amma qəribə) davranışı olduğuna
> **yalnız insan** qərar verə bilər. Avtomatik «düzəliş» qəsdən **yoxdur**.

---

## Bir baxışda

| növ | siyahıdakı sətir | bundan **ziddiyyət** | unikal tələbə |
|---|---:|---:|---:|
| **A** — Yekun, giriş, çıxış bloku | 17 107 | **1 319** | 3 492 |
| **B** — Kəsilib, amma nəticəsi var | 2 762 | **2 712** | 1 284 |
| **C** — Ardıcıl fənndə sıra pozuntusu | **4 452** | **844** (C1+C2+C4) | 3 068 |
| **CƏMİ** | **24 321** | **4 875** | (növlər arasında təkrarlana bilər) |

> v1-də **CƏMİ 24 776** yazılırdı və hamısı «ziddiyyət» kimi oxunurdu.
> Düzgün oxunuş: **24 321 sətir siyahıya düşüb**, bunlardan **4 875-i həqiqi
> ziddiyyətdir**; qalanı köçürmə tapşırığı (yekun yazılmayıb), yuvarlaqlaşdırma,
> ayrı bal sxemi və ya «fənn 1 heç götürülməyib» halıdır.

---

## ⚖️ «Bu köhnə sistemdən gəlir» vs «köçürmə yaradıb» — KRİTİK AYRIM

**Köçürmə bu ziddiyyətlərin heç birini yaratmayıb.** Sübut qatı sətir-sətir
müqayisə edilib:

| mənbə cədvəli | mənbə | hədəf | fərq |
|---|---:|---:|---:|
| `yekun` → `registrar_legacygradefact` | 17 194 | 17 194 | **0** |
| `imthngrscxsblr` → `registrar_legacygradefact` | 12 544 | 12 544 | **0** |
| `balvereqi_logs` → `registrar_legacygradeartifact` | 52 386 sətir / 979 137 679 bayt | 52 386 / 979 137 679 | **0** |

Ona görə A vərəqindəki `Mənbədə də var idi` sütunu **hər sətirdə «bəli»**-dir.

**Nəticə:** bütün ziddiyyətlər **köhnə MyEdu sistemində artıq mövcud idi**.
Köçürmə onları sadıqcasına daşıyıb — sahibin qaydasına uyğun olaraq
(«biz köhnə datanı dəyişmirik, sadəcə yeni sistemə köçürürük»).

Praktik təsiri: B növündəki 2 762 sətrin **2 599-unda** həmin imtahan balı yeni
sistemdə (`registrar_finalgrade.exam_score`) artıq görünür.

---

## A — Yekun, giriş, çıxış bloku

### Sadə dildə

Bir fənndə üç rəqəm var: **giriş balı** (semestr ərzində toplanan), **çıxış balı**
(imtahan) və **yekun**. Yekun sadəcə bu ikisinin **cəmidir** — çəki yoxdur,
ortalama yoxdur:

```
yekun = round(giriş + çıxış)
```

Qayda iki müstəqil populyasiyada yoxlanıb: saxlanmış `yekun` cədvəlində
**99.994 %** (17 194 sətir), çap olunmuş bal vərəqlərində **99.950 %**
(127 177 sətir). Qaydada şübhə **yoxdur**.

İki incəlik — hər ikisi **ziddiyyət deyil**:

1. **Təkrar imtahan (`timt`) çıxış balını əvəz edir** (14 230 sətir).
   Nəzərə almasan 12 277 saxta «yekun artıqdır» həyəcanı çıxır.
2. **Çap edilən giriş balı ayrıca yuvarlaqlaşdırılır**, yekun isə xam cəmdən
   hesablanır — vərəqdəki `giriş + çıxış` bəzən yekundan **1 fərqlənir**
   (64 sətir, A2r).

### Siniflər — bax §3 (Düzəliş qeydi)

**A5-in tərkibi** (kateqoriyalar üst-üstə düşə bilər):

| pozuntu | A5 sətri | unikal tələbə |
|---|---:|---:|
| `yekun > 100` (ən yüksək **135**) | 59 | 53 |
| `çıxış > 50` (maksimum 50-dir) | 476 | 319 |
| `giriş > 50` (maksimum 50-dir) | 158 | — |
| **mənfi giriş balı** (ən aşağı **−26**) | 577 | 246 |

A5L (Xarici dil / «Level») sətirləri də əlavə edilsə: mənfi giriş **601 sətir /
263 tələbə**, `çıxış > 50` **882 sətir / 328 tələbə**, `yekun > 100` **83 sətir / 72 tələbə**.

Mənfi giriş balı köhnə davamiyyət düsturunun nəticəsidir: qayıba görə cərimə
0-a sıxılmır, mənfiyə keçir (bax `DAVAMIYYET_DUSTUR_YOXLAMASI.md` §4).

### Konkret nümunə

> **A1 — yeganə həqiqi arifmetik uyğunsuzluq**
> **İmanova Naibə Fikrət** · köhnə ID **1090** · yeni ID **1025** ·
> `myedu.student.1090` · qrup 129 T ·
> «Qədim yazılar (Yunan, latın)», 2022/2023 Payız:
> **giriş 22 + çıxış 24 = 46**, amma saxlanmış yekun **48**.
> Fərq +2 — mənbədə `guzest_artim = 2` (güzəşt artımı) yazılıb.
> *Sətir açarı:* `yekun.id = 8342`.

> **A5 — ən kəskin diapazon pozuntusu**
> **Məmmədova Xeyransa Rasim qızı** · köhnə ID **276** · yeni ID **261** ·
> `myedu.student.276` · qrup 231 EKO ·
> «Atmosferin ekologiyası, müasir çirkləndiricilər»:
> **çıxış balı 86** (maksimum 50-dir) → **yekun 135**. Naxış 2023/2024 və
> 2025/2026-da təkrarlanır.
> *Sətir açarı:* `log 3205 · cədvəl 24 · sətir: MƏMMƏDOVA XEYRANSA RASİM QIZI ·
> Atmosferin ekologiyası… · giriş=49 imtahan=86 yekun=135`.

> **A4 — ən kütləvi hal (ziddiyyət deyil, köçürmə tapşırığı)**
> **Həsənova Jalə Abbas** · köhnə ID **1276** · yeni ID **1193** · `myedu.student.1276` ·
> qrup 029 ing · «Psixologiyada riyazi metodlar», 2022/2023 Payız:
> `imthngrscxsblr`-də **giriş 50 + çıxış 47 = 97** yazılıb, amma bu tələbə üçün
> `yekun` cədvəlində **heç bir sətir yoxdur**. 12 505 imtahan sətrinin
> **12 431-i** belədir.

### Giriş balı düsturu haqqında — bu bug DEYİL

Köhnə PHP kodu **hovuz (pool) düsturunu** icra edib
(`3 × ORTA(bütün rəqəmli qiymətlər bir hovuzda)`), universitetin rəsmi normativ
düsturunu (`((cari_iş_ort + kollokvium_ort)/2) × 3`) **yox**.
İki düsturun fərqləndiyi 43 036 sətirdə: **hovuz 99.37 %**, **rəsmi 0.04 %**.

Köçürmə köhnə davranışı **eynilə** kopyalayır — **sahib qərarıdır**, bug deyil.
Detallar: `docs/migration/LEGACY_GIRISH_FORMULA.md`.

---

## B — Kəsilib, amma nəticəsi var

### Sadə dildə

Üzrsüz qayıbı çox olan tələbə imtahana buraxılmamalıdır. Bu siyahıda
buraxılmamalı olan, amma **imtahan balı yazılmış** (bəzən hətta fənni
**keçmiş**) tələbələr var.

### Hədd necə tapıldı

**Mənbədə «imtahana buraxılmır» adlı açıq sütun YOXDUR.** Bütün sxem
`information_schema` üzrə tarandı. `yekun.kesr` yeganə namizəd idi, amma o,
buraxılış bayrağı **deyil**: `kesr=1` olan 2 385 sətrin **2 111-i (88.5 %)
imtahana girib**. Yəni `kesr` = «kəsr/keçməyib», davamiyyət kəsilməsi yox.

Yeganə açıq status **müəllimin çap etdiyi bal vərəqindəki `(Kəsr)` bayrağıdır**:

| davamiyyət balı | sətir | bayraqlı | pay |
|---|---:|---:|---:|
| < 7.36 | 66 195 | 65 202 | **98.50 %** |
| 7.36 … 7.54 (render zolağı) | 10 729 | — | keçid |
| > 7.54 | 823 032 | 1 183 | **0.14 %** |

**HƏDD: üzrsüz buraxılmış saat > fənnin ümumi saatının 25 %-i (ciddi bərabərsizlik)
⟺ davamiyyət balı < 7.50** — mənbəyi və müdafiəsi üçün bax §7 (Düzəliş qeydi).

**Keçid həddi:** `yekun ≥ 51` **və** `imtahan balı ≥ 17`.
(`kesr=0` olan 14 809 sətrin 14 806-sı `yekun≥51`.)

### Alt növlər

| alt növ | sətir | unikal tələbə | nə deməkdir |
|---|---:|---:|---|
| **B1** | 2 145 | 1 054 | çap olunmuş `(Kəsr)` + `dav<7.5` + imtahan balı |
| **B3** | 1 700 | 995 | kəsilib + `yekun ≥ 51` — fənni **keçib** görünür |
| **B2b** | 292 | 248 | çap vərəqi yox; 4 fərqli məxrəcin **hamısı** `m>0.25N` deyir |
| B1x | 206 | 185 | `(Kəsr)` var, amma `dav≥7.5` — köhnə sistemin **daxili** ziddiyyəti |
| **B2a** | 119 | 108 | `dav<7.5` (hədd aşılıb), bayraq qoyulmayıb, imtahan balı var |
| B4 | 50 | 42 | kəsilib, amma **üzrlü qayıb sənədi var** — *ziddiyyət deyil, izahdır* |
| **CƏMİ (sətir)** | **2 762** | **1 284** | (bir sətir bir neçə alt növə düşə bilər) |

**Şiddət bölgüsü:** kritik 1 212 (22-si rekonstruksiya ilə ikiqat təsdiqli) ·
yüksək 633 (20 ikiqat) · rekonstruksiya-əsaslı 243 · orta 243 ·
aşağı / yalançı-müsbət ehtimalı 381 · üzrlü sənədlə izah olunan 50.

**«Yekun bal» sütununun mənbəyi:** bax §5 (Düzəliş qeydi) — indi hər sətirdə
açıq göstərilir.

### Konkret nümunə

> **B1+B3 — kritik, ikiqat təsdiqli**
> **Qulamova Günəş Ceyhun** · köhnə ID **3283** · yeni ID **3078** ·
> `myedu.student.3283` · qrup 132 SI · «Sosial statistika», 2023/2024 Payız.
> Davamiyyət balı **0.76** (hədd 7.50), 46 saatın **14-ü üzrsüz qayıb**
> (nisbət 0.304 > 0.25). Çap vərəqində `(Kəsr)` yazılıb.
> Buna baxmayaraq 2024-02-27-də imtahan verib, **18 bal** alıb, **yekunu 51**-dir
> — fənni **keçib** görünür. *Yekun balın mənbəyi: çap vərəqindən.*
> Müstəqil jurnal rekonstruksiyası da təsdiqləyir.
>
> ⚠️ **Diqqət:** yeni sistemdə `auth_user.id = 3283` **başqa tələbədir**
> (Memmedov Arif Saleh, 529 IMEM). Axtarışı `myedu.student.3283` ilə aparın.

> **B4 — ziddiyyət deyil, izahdır**
> **İsgəndərova Arzu Sənan** · köhnə ID **5924** · yeni ID **3791** · `myedu.student.5924` ·
> «Su bitkilərinin fiziologiyası»: `dav=7.13` və `(Kəsr)` var, amma
> 2024-02-26 tarixi üçün **üzrlü qayıb sənədi** mövcuddur.

---

## C — Ardıcıl fənndə sıra pozuntusu

### Sadə dildə

«Riyaziyyat 1» keçilmədən «Riyaziyyat 2» götürülə bilməz. Bu siyahıda birinci
fənndən **kəsilmiş**, ikinci fənndə isə **imtahan nəticəsi olan** (bəzən hətta
**keçmiş**) tələbələr var.

### Alt növlər (yararsız plan cütləri çıxarıldıqdan sonra)

| alt növ | şiddət | sətir | unikal tələbə | nə deməkdir |
|---|---|---:|---:|---|
| **C2** | kritik | 416 | 354 | 1-dən kəsilib (heç vaxt keçməyib) + 2-dən **KEÇİB** |
| **C1** | yüksək | 367 | 310 | 1-dən kəsilib + 2-də **imtahan nəticəsi var** (keçməyib) |
| **C4** | orta | 61 | 61 | 2-ni 1-dən **əvvəlki** semestrdə götürüb (sıra tərsinə) |
| C3 | orta / aşağı | 3 608 | 2 596 | 1-i **heç götürməyib** + 2-də nəticə var |
| **CƏMİ** | | **4 452** | **3 068** | (v1: 4 907 — 455 sətir çıxarıldı) |

C1+C2 üzrə unikal tələbə **572**, C1+C2+C4 üzrə **626**.

* **«Sonra keçib» (qanuni) 19 hal siyahıdan ÇIXARILIB** — tələbə 1-i sonrakı
  semestrdə təkrar götürüb keçib.
* **Eyni semestrdə götürülən 39 hal** pozuntu sayılmayıb.
* **Müstəqil təsdiq:** C1+C2-nin fənn-1 sətirlərindən 99-unun köhnə `yekun`
  cədvəlində öz sətri var → **99/99-u (100 %) təsdiqləndi** (`yekun < 51` və ya
  `kesr = 1`). Sıfır ziddiyyət.

### Ən çox pozuntulu cütlər

| fənn 1 → fənn 2 | cüt mənbəyi | pozuntu |
|---|---|---:|
| Xətti cəbr və riyazi analiz → Ehtimal nəzəriyyəsi və riyazi statistika | **yalnız plan ⚠** | 682 |
| İqtisadiyyata giriş → Mikroiqtisadiyyat | **yalnız plan ⚠** | 373 |
| Xarici dildə işgüzar və akademik kommunikasiya 1 → 2 | ad + plan | 247 |
| Ümumi psixologiya-1 → Sosial psixologiya | **yalnız plan ⚠ (fan-out)** | 218 |
| Ümumi kimya → Biokimya | **yalnız plan ⚠** | 208 |
| Ehtimal nəzəriyyəsi və riyazi statistika → Ekonometrika | **yalnız plan ⚠** | 185 |

### Metod

Keçdi/kəsildi qərarı **sistemin öz kodu ilə** yenidən quruldu
(`apps/registrar/finals.py::compute_final_result` + `gradebook_components.entry_score_for`):
`giriş = round(min(GENERIC və ya LessonMark cəmi + KOLLOKVIUM, 50))`;
`yekun = round(giriş + çıxış + bonus)`; `keçib = yekun ≥ 51 AND çıxış ≥ 17`.
Bərpanın doğruluğu: köhnə `yekun` ilə üst-üstə düşən 14 224 yazılışda
giriş balı **98.07 %**, imtahan balı **92.25 %** eyni çıxdı.

Ön şərt **iki müstəqil mənbədən** götürüldü — və indi **ayrı-ayrı işarələnir**
(bax §4):
1. **Ad ardıcıllığı** — kiçik hərf, kirill-latın homoqlif əvəzləmə, tire
   birləşdirmə, `I/II/III/IV → 1/2/3/4`, sonra **kök tam eyni + nömrə ardıcıl**.
   Kök tam eyni olduğuna görə «Kimya» vs «Kimya sənayesi» kimi yalançı cütlər
   **yaranmır**. **Nəzarətdə bir dənə də yanlış cüt tapılmadı.**
2. **Tədris planı ön şərti** — `curricula_plan.lesson_before_id`.
   **Sahənin mənası təsdiqlənməyib** — bu mənbədən gələn cütlər ⚠ ilə işarələnib.

---

## ⚠️ Aşkarlamanın hüdudları (dürüstlük qeydi)

1. **C — plan-əsaslı cütlər.** `curricula_plan.lesson_before_id` sahəsinin
   «ön şərt» yoxsa «plan sırası» olduğu **təsdiqlənməyib**. Daxilən yararsız
   cütləri çıxardıq (455 sətir), şübhəlilərə xəbərdarlıq yapışdırdıq (877 sətir),
   qalanları «YALNIZ tədris planı ⚠» kimi işarələdik — **qərar sizindir**.

2. **C — ad-əsaslı cütlər sağlamdır.** Kök tam eyni + nömrə ardıcıl qaydası
   yalançı cüt yaratmır; nəzarətdə atılası tapılmadı.

3. **B — naməlum məxrəc.** Fənnin ümumi saat sayı (`N`) mənbədə açıq yazılmayıb;
   4 fərqli məxrəclə bərpa edilib. `H_real` məxrəci çap bayrağı ilə **96.96 %**
   üst-üstə düşür; 4 məxrəcin **hamısı** razı olduqda dəqiqlik **95.6 %**,
   əhatə **60.5 %**. **381 sətir «aşağı (yalançı müsbət ola bilər)»** kimi
   işarələnib. 632 029 `qb` xanasının 23 219-u (3.7 %) heç bir dərs slotuna
   bağlanmadı.

4. **A — yuvarlaqlaşdırma.** Çap edilən giriş balı müstəqil yuvarlaqlaşdırılır;
   ±1 fərq **A2r** kimi ayrıca işarələnib və ziddiyyət sayılmayıb (64 sətir).

5. **Çap vərəqləri anlıq şəkildir.** `balvereqi_logs` ixrac anının vəziyyətini
   saxlayır — ixracdan sonrakı jurnal redaktələri orada görünmür.

6. **Kəsilmə statusu heç vaxt açıq saxlanmayıb.** Köhnə sistem onu hər dəfə
   yenidən hesablayıb. Bizim hədd normativdən gəlir və data ilə **99.4458 %**
   uyğunlaşır — amma **100 % deyil**.

---

## Nə etmək lazımdır

Təklif olunan ardıcıllıq — **hər addım əl ilə baxışdır, avtomatik düzəliş yox**:

0. **Əvvəlcə açar məsələsini komandaya çatdırın.** Tələbə axtarılanda
   **`İstifadəçi adı (login)`** işlədilsin; nömrə ilə axtarış zəruridirsə,
   **hansı sistemdə** axtarıldığı aydın olsun. «🔑 Şəxsiyyət körpüsü» vərəqi
   bunun üçündür.

1. **Kiçik və kəskin olanlar.** `A1` (1 sətir) və `A5`-in `yekun > 100` hissəsi
   (59 sətir) — açıq-aşkar səhvdir və sayı azdır. Fakültələrlə yoxlanıb,
   lazım gələrsə **yeni sistemdə audited correction** (İKT rəhbəri axını,
   PDF sənədli) ilə düzəldilə bilər — köhnə data yenə toxunulmaz qalır.

2. **`A5` — mənfi giriş balı (637 sətir, 263 tələbə).** Köhnə davamiyyət
   düsturunun sistematik nəticəsidir. Birdəfəlik **siyasi qərar**: ya olduğu
   kimi saxlanılır, ya da yeni sistemdə giriş balı 0-a sıxılır.
   **Fərdi sətir-sətir baxış lazım deyil.**

3. **`B3` (1 700 sətir, 995 tələbə) — ən həssas blok.** Bu tələbələr davamiyyətə
   görə buraxılmamalı ikən fənni **keçmiş** görünürlər. Arxivdəki üzrlü sənəd və
   ya dekanlıq qərarı axtarılmalıdır. `B4`-dəki 50 hal artıq sənədlə izah olunur.
   **Sətirə baxarkən «Yekun balın MƏNBƏYİ» sütununu oxuyun** — çap vərəqindən
   gələn 2 248 sətir daha ağır sübutdur.

4. **`C2` (416 sətir, kritik).** Ön şərt pozuntusu ilə diplom verilmiş ola bilər.
   **Əvvəlcə cüt kataloqunu təsdiqləyin** — xüsusən «YALNIZ tədris planı ⚠»
   qrupundakı 10 cütü (463 sətir); sonra qalan sətirləri tədris şöbəsi ilə keçin.

5. **`A4`/`A4z` (15 151 sətir) — köçürmə tapşırığı, ziddiyyət yox.** İmtahan
   nəticəsi olub yekunu yazılmamış sətirlərdir. Qərar: yeni sistemdə
   `yekun = giriş + çıxış` kimi **hesablanaraq göstərilsin**, yoxsa boş qalsın.

6. **`C3` (3 608 sətir) ən sonda.** Böyük hissəsi köhnə sistemin natamam
   yazılış qeydlərindəndir — həqiqi pozuntu nisbəti burada ən aşağıdır.
   **877-sində şübhə siqnalı var** — onları ya axıra saxlayın, ya da cütü
   ləğv edib toplu şəkildə çıxarın.

> **Təkrar edirik:** yuxarıdakı heç bir addım bu analiz tərəfindən icra
> edilməyib. Köhnə data olduğu kimi qalır; bu sənəd yalnız **nəyə baxmaq
> lazım olduğunu** göstərir.

---

## Əlaqəli sənədlər

* `docs/migration/LEGACY_GIRISH_FORMULA.md` — giriş balı düsturu (hovuz vs rəsmi)
* `docs/migration/UZRLU_QAYIB_SENEDLERI.md` — üzrlü qayıb sənədləri
* `docs/migration/DATA_VERIFICATION_2026_08_27.md` — ümumi köçürmə yoxlaması
* `apps/registrar/exam_eligibility.py` — yeni sistemin imtahana buraxılış qapısı
