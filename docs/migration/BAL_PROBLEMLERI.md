# Ballarda problemli tələbələr — sahib üçün iş siyahısı

**Buraxılış 5 (düzəldilmiş)** · **Tarix:** 2026-09-01 · **Şaxə:** `Develop` @ `7cdc3376`
**Sübut bazası:** `emsarena_rehearsal_52ea0301808c` (repetisiya nüsxəsi),
run `7c3e8d46-0464-4f52-bbe7-7afd852b5bf3` · **mənbə:** köhnə `myedu` MariaDB bazası
**Bu analiz yalnız-oxu idi** — heç bir bazaya yazılmadı, heç bir kod dəyişmədi.

---

## 0. DÜZƏLİŞ QEYDİ — nə səhv idi, nə düzəldildi

Bu, sənədin **beşinci** nüsxəsidir. §0.000 **5-ci nüsxənin** düzəlişidir
(4-cü nüsxənin blokeri); §0.00 **4-cü nüsxənin** düzəlişidir (3-cü nüsxənin
blokeri); §0.0 **3-cü nüsxənin** düzəlişidir (2-ci nüsxənin blokeri);
§0.1–0.6 **2-ci nüsxənin** düzəlişləridir (1-ci nüsxəyə görə).

---

### 0.00.a ⚠ NAXIŞ — dörd dövrdə EYNİ SİNİF SƏHV təkrarlandı

Oxuyan bunu bilməlidir: bu sənəd dörd dəfə düzəldilib və **hər dəfə eyni sinif
səhv bir qat aşağıda** üzə çıxıb.

| Nüsxə | Səhv | Kök |
|---|---|---|
| 1 → 2 | K13-ün hamısı «yeni sistemdə heç nə» yazırdı — **506 sətirdə dəyər VAR idi** | hədəf ümumiyyətlə yoxlanmırdı; boşluq fərziyyə ilə doldurulurdu |
| 2 → 3 | jurnal açarı iki formada gəlirdi, fənn həll olunmurdu — **4 525 sətirdə qəti hökm yanlış idi** | açar tutmayanda «naməlum» yox, **qəti hökm** yazılırdı |
| 3 → 4 | fənn **ad konvensiyasından** qurulurdu — **152 sətirdə qəti hökm YALAN, 12 380 sətirdə fənn kodu yanlış** | fənn **avtoritetli xəritədən** deyil, `MYEDU-L{dərs id}` **konvensiyasından** həll olunurdu |
| 4 → 5 | tələbənin həmin fənndə bir neçə yazılışı olanda proqram **İXTİYARİ birini** götürüb qəti cümlə yazırdı — **171 sətirdə «xana boşdur» YALAN idi** | hökm namizədlərin **hamısına** deyil, siyahının **birinci** üzvünə baxırdı |

**Kök səbəb hər dörd dəfə eynidir:**

1. **Açar tutmayanda proqram «müəyyən edilə bilmədi» yox, QƏTİ HÖKM yazırdı.**
   Bilməmək faktı hökmə çevrilirdi.
2. **Kimlik ad/nömrə konvensiyasından qurulurdu, avtoritetli xəritədən yox.**
   Konvensiya 99 %-də düz işləyir və məhz buna görə təhlükəlidir: qalan 1 %-də
   səssizcə yalan danışır.
3. **Çoxluqdan İXTİYARİ bir üzv seçilib onun haqqında qəti cümlə yazılırdı.**
   Namizəd bir dənə olanda bu görünmür; iki olanda hökm sikkə atmağa çevrilir.
   Beşinci dövrün blokeri məhz budur (§0.000).

4-cü nüsxədə hər ikisi qaydaya salındı: fənn **yalnız**
`legacy_import_legacyentitymap(entity_type='lesson_subject')` avtoritetli
xəritəsi ilə həll olunur, çap edilən hər fənn kodunun hədəfdə mövcudluğu
`registrar_subject` ilə **proqramla təsdiqlənir**, və namizəd yazılışın
vəziyyəti oxuna bilməyəndə hökm **«müəyyən edilə bilmədi»** olur.
---

### 0.000 ⚠ BLOKER — «xana boşdur» hökmü İXTİYARİ seçimdən doğurdu (171 sətir)

**4-cü nüsxə belə işləyirdi.** Tələbənin həmin fənndəki namizəd yazılışları
tapılırdı, sonra:

```python
pick = next(e for e in cands if e in E)   # ← siyahının BİRİNCİ üzvü
s = E.get(cands[0])
empty = not s.get("exam")                 # ← yalnız BU yazılışa baxır
```

Tələbənin həmin fənndə **bir neçə yazılışı** olanda (təkrar oxuma, qrup
dəyişməsi, iki açılış) proqram **ixtiyari birini** götürüb hədəf haqqında
**qəti cümlə** yazırdı: «yazılış var, dəyərin xanası boşdur». Seçilən yazılışın
xanası boş, **qonşusununku dolu** ola bilərdi — və hökm bunu heç yerdə demirdi.

**Canlı bazadan təsdiqlənmiş nümunələr:**

| Köhnə tələbə | Köhnə dərs | Mənbə | 4-cü nüsxənin hökmü | **HƏQİQƏT** |
|---:|---:|---|---|---|
| 1574 | 1146 | imtahan 9 | «yazılış var, xana boşdur» 🟠 | **İKİ yazılış** — biri boş, digərində **imtahan 19.00**; proqram BOŞ olanı seçmişdi |
| 851 | 2089 | imtahan 19 | «yazılış var, xana boşdur» 🔴 | eyni fənndə başqa açılışda **imtahan 8.00** var |
| 3507 | 42 | imtahan 7 | «yazılış var, xana boşdur» 🟠 | **ÜÇ yazılış** — birində **imtahan 3.00** |

**Alt-qüsur — exam/resit asimmetriyası (1 sətir).** Uyğunluq axtarışı dəyəri
həm `exam`, həm `resit` xanasında qəbul edirdi, «boşdur» testi isə **yalnız**
`exam`-a baxırdı. Nəticədə imtahan xanası boş, **təkrar imtahan xanası DOLU**
olan yazılış «xana boşdur» kimi göstərilirdi (köhnə tələbə 3336 · dərs 2148 ·
**təkrar imtahan 29.00** + 5 komponent).

**Düzəliş — namizədlərin HAMISINA baxılır, seçim yoxdur.**

| Vəziyyət | Hökm |
|---|---|
| namizədlərin **hər hansı birində** dəyər var | **«Hədəfdə VAR — dəyər fərqli»** (neçə yazılış, neçəsində dəyər — cümlədə yazılır) |
| namizədlərin **hamısı** boş | «xana boşdur» *(cümlə doğrudur)* |
| namizəd var, amma vəziyyəti oxunmur | **«müəyyən edilə bilmədi»** |

«Boşdur» testi indi uyğunluq axtarışı ilə **eyni xanalara** baxır (imtahan
**və** təkrar imtahan; komponent hadisəsində — komponentlər), yəni simmetriya
bərpa olundu.

**Açar dəqiq olan 4 sətirdə** («direct» / «same_off») cümlə seçilmiş yazılış
üçün **doğrudur** — ona görə hökm dəyişmədi, amma artıq **gizlətmir**: sətrə
`DİQQƏT — eyni fənndə başqa açılışda dəyəri OLAN N yazılış var` əlavə olunur və
həmin yazılışın tam vəziyyəti «Yeni sistemdə» sütununda `‖` işarəsindən sonra
çap edilir.

**Nəticə — 171 sətrin yeni bölgüsü:**

| Köhnə hökm (4-cü nüsxə) | Sətir | **5-ci nüsxədə** |
|---|---:|---|
| «eyni fənndə yazılış var (başqa açılış), xana boşdur» 🟠 | 167 | **«Hədəfdə VAR — dəyər fərqli»** 🟠 |
| «yazılış VAR, amma xana boşdur» 🔴 (açar dəqiq) | 4 | hökm eyni qalır 🔴 + **DİQQƏT açıqlaması** |

Bundan başqa **442 sətirdə** (439 K13 + 3 dublikat faylında) hökmün **mətni**
dəqiqləşdi, hökm sinfi dəyişmədi:
çox namizədli hallarda artıq «N yazılış var, **HAMISININ** xanası boşdur» /
«N yazılışdan K-sında dəyər VAR» yazılır — yəni cümlə neçə yazılışa baxıldığını
açıq deyir.

**K13-ün hökm bölgüsünə təsiri** (sətir sayı **dəyişmir**, 10 815):

| Hökm | 4-cü nüsxə | **5-ci nüsxə** |
|---|---:|---:|
| Hədəfdə **YOXDUR** | 10 467 | **10 300** |
| Hədəfdə **VAR — dəyər fərqli** | 121 | **288** |
| **Müəyyən edilə bilmədi** | 227 | 227 |

Şiddət bölgüsü dəyişmir (🔴 7 757 / 🟠 2 831 / 🟡 227) — şiddət açarın
dəqiqliyindən asılıdır, hökmün özündən yox.

**Öz-özünə süpürgə — qalan ixtiyari seçim varmı.** Düzəlişdən sonra sual
yenidən verildi və **bir qalıq tapıldı**: 10 sətirdə **birdən çox** namizədin
xanası dolu idi, proqram isə «Yeni sistemdə» sütununda onlardan **birini**
göstərib «Fərq» rəqəmini də ondan hesablayırdı. Hökm doğru idi (hansı dolu
yazılışı seçsən, «dəyər fərqlidir» doğrudur), amma **rəqəm ixtiyari** idi.
Bu da bağlandı:

- dolu yazılışların **hamısı** çap olunur (`‖` ilə ayrılır) — 14 sətirdə;
- **«Fərq» yalnız birmənalı olanda yazılır**; dolu yazılışların imtahan balı
  öz aralarında fərqlidirsə xana **boş qalır** və səbəb cümlədə deyilir
  (3 sətir). Beləliklə sənəddə **ixtiyari seçimdən doğan tək rəqəm də qalmadı**.

**Müstəqil təsdiq.** `adv2/sweep2.py` pipeline fayllarına güvənmədən, canlı
bazadan **12 464 hökmün hamısını** yenidən qurur və iki sual verir:
(a) qəti hökm yalandırmı, (b) hökm namizədlər arasında **fikir ayrılığı**
olanda bunu gizlədirmi. Nəticə:

```
SƏHV QƏTİ HÖKM              : 0
İXTİYARİ SEÇİMDƏN DOĞAN HÖKM: 0
```

Yoxlanan qəti hökmlər: 5 496 «yazılış yoxdur» · 3 116 «hesab köçməyib» ·
2 691 «xana boşdur» (ondan **4**-ü DİQQƏT açıqlaması ilə, 2 687-də həmin
fənndə həqiqətən heç bir dəyər yoxdur) · 934 «hədəfdə var»; qalan 227 sətir
onsuz da qəti hökm daşımır.

### 0.000.b Baş siyahının açarı **AD**dan **KOD**a keçirildi

`BAS_SIYAHI_telebe_fenn.tsv` sətirləri belə birləşdirilirdi:

```python
k = (kohne_id, fenn ADI, tedris_ili, semestr)   # ← ad
```

Bu, sənədin özünün pislədiyi naxışdır — **kimlik addan qurulur**. Üstəlik
sahibin əsl oxuduğu vərəqdədir. Hədəfdə **eyni ADlı, fərqli KODlu 7 cüt fənn**
var (`Tədqiqat metodları`, `Əski əlifba`, `İmmunologiya`, `Hüquq və siyasət`,
`Gömrük-tarif tənzimlənməsi`, `Meşə-park təsərrüfatları`,
`Ölkəşünaslıq və mədəniyyətlərarası ünsiyyət`) — ad açarı onları **bir sətirdə
birləşdirə** bilərdi.

Açar `fenn_kodu`-ya keçirildi (kodu olmayan yeganə kateqoriya K8-dir; orada
açıq `ad:` nişanı ilə ada geri düşülür). **Bu dataset-də ölçülmüş zərər = 0** —
hər iki açar eyni **50 188** sətir verir; dəyişiklik yalnız gələcəyi qoruyur.

**Baş siyahının bir məhdudiyyəti qalır (qəsdən).** Konsolidasiya səbəbindən
**23 sətir** iki fərqli **köhnə dərs id**-sini bir sətirdə birləşdirir (məsələn
köhnə 562 və 1582 → `MYEDU-L562`), amma «Köhnə sistemdə dərs id» sütununda
onlardan yalnız **biri** görünür. Birləşmə **doğrudur** — hədəfdə həqiqətən tək
fənndir; sadəcə sütun tam tarixçəni göstərmir. Tam bölgü kateqoriya
fayllarındadır (`bal_problemleri/K*.tsv`), orada hər sətir öz köhnə dərs
id-sini saxlayır.

### 0.000.c Açıqlanmamış dəyişiklik — 3-cü nüsxənin baş siyahısı **KÖHNƏ** idi

Sənəd «sətir sayı dəyişmir (70 255)» deyirdi, amma baş siyahı səssizcə
dəyişmişdi:

| Fayl | 3-cü nüsxə | **4/5-ci nüsxə** | Fərq |
|---|---:|---:|---:|
| `BAS_SIYAHI_telebe_fenn.tsv` sətir | 50 992 | **50 188** | −804 |
| … hadisə cəmi | 269 480 | **269 257** | −223 |

**Yeni rəqəm DOĞRUdur.** Kateqoriya fayllarının **xam** hadisə cəmi tam
**269 257**-dir və 4/5-ci nüsxənin baş siyahısı ona **hərfən** bərabərdir.
Səbəb ölçüldü: 3-cü nüsxənin baş siyahısı **köhnə qalmışdı** — onda hələ də
fənni həll olunmamış **809 sətir** (fənn sütununda `#lesson `, kod boş,
**4 525 hadisə**) vardı; həmin sətirlər K13 yenidən qurulanda aradan qalxmış,
amma baş siyahı **yenidən yaradılmamışdı**. Yəni 3-cü nüsxə **223 hadisəni
ARTIQ sayırdı**. Bu, 4-cü nüsxənin səssizcə düzəltdiyi əlavə səhvdir və indi
qeydə alınır.

---

### 0.00 ⚠ BLOKER — fənn KONVENSİYA ilə həll olunurdu → yalan hökm + fantom kod

**3-cü nüsxə fənni belə tapırdı:** köhnə dərs id-sinə `MYEDU-L` prefiksi
əlavə edirdi (`MYEDU-L{lesson_id}`) və namizəd açılışları `map_offering`-dən
qurulan köməkçi xəritə ilə süzürdü. Bu, **konvensiyadır** — avtoritetli
mənbə deyil.

**Köçürmə isə konsolidasiya edir.** Köhnə `lessons` cədvəlində təkrarlanan
dərslər hədəfdə **TƏK** bir `registrar_subject`-ə birləşdirilib. Avtoritetli
xəritədə (`legacy_import_legacyentitymap`, `entity_type='lesson_subject'`)
**2 521 köhnə dərs → 2 501 fənn**; **20 köhnə dərs** üçün kod konvensiyadan
FƏRQLİDİR:

| Köhnə dərs | Konvensiyanın uydurduğu kod | **Hədəfdəki HƏQİQİ kod** | Fənn |
|---:|---|---|---|
| 1918 | ~~MYEDU-L1918~~ | **MYEDU-L145** | Azərbaycan tarixi |
| 1582 | ~~MYEDU-L1582~~ | **MYEDU-L562** | Kargüzarlığın təşkili və yazı texnikası |
| 2249 | ~~MYEDU-L2249~~ | **MYEDU-L1509** | Aqrokimya və ətraf mühitin mühafizəsi |
| 1624 | ~~MYEDU-L1624~~ | **MYEDU-L944** | Qiymət və qiymətləndirmə |
| 2421 | ~~MYEDU-L2421~~ | **MYEDU-L563** | İşgüzar yazışmalar |
| … | | | *(cəmi 20 dərs · 19 fənn)* |

**Nəticə — iki ayrı zərər:**

**(a) 152 sətirdə QƏTİ HÖKM YALAN idi.** K13-də «tələbənin bu fənnə yeni
sistemdə **HEÇ BİR** yazılışı yoxdur 🔴» yazılırdı. Faktda tələbənin yazılışı
**VAR** — sadəcə konsolidasiya olunmuş kod altında. 11 sətirdə köhnə dəyər
hədəfdə **artıq durur**.

Uçdan-uca təsdiqlənmiş nümunələr (mənbə: `imthngrscxsblr`, köhnə dərs 1918 →
hədəf `MYEDU-L145`, açılış «531 Ting · Yaz»):

| Mənbə sətri | Köhnə tələbə | Köhnə dəyər | Yeni sistemdə |
|---:|---:|---|---|
| id 159 | 425 | imtahan 5 | **imtahan 5.00** |
| id 162 | 423 | imtahan 11 | **imtahan 11.00** |
| id 164 | 419 | imtahan 6 | **imtahan 6.00** |
| id 166 | 420 | imtahan 17 | **imtahan 17.00** |
| id 167 | 426 | imtahan 22 | **imtahan 22.00** |
| id 243 | 2249 | imtahan 5 | **imtahan 5.00** *(dərs 1582 → `MYEDU-L562`)* |

**(b) 354 sətirdə çap olunan «Fənn kodu» hədəfdə MÖVCUD DEYİLDİ** — universitet
o kodu yeni sistemdə axtarsaydı heç nə tapmayacaqdı (`MYEDU-L1918` ×327,
`MYEDU-L2249` ×12, `MYEDU-L1624` ×10, `MYEDU-L1582` ×4, `MYEDU-L2421` ×1).

**Düzəliş.** Fənn həlli **bütün kateqoriyalarda** avtoritetli xəritəyə keçirildi;
uyğunluq tapılmayanda hökm **«müəyyən edilə bilmədi»** olur.

| Ölçü | 3-cü nüsxə | **4-cü nüsxə** |
|---|---:|---:|
| Ləğv olunan **yalan qəti hökm** («bu fənndə yazılış YOXDUR») | — | **152** |
| — «əslində eyni fənndə yazılış VAR, xana boş» (🔴→🟠) | — | 141 |
| — «əslində köhnə dəyər hədəfdə TAPILIR» (🔴→🟡) | — | 11 |
| Düzəldilən **fənn kodu** | — | **12 380** |
| — K13/K0/DUB-dakı **fantom** kod (hədəfdə mövcud deyildi) | 354 | **0** |
| — K4/K5/K6-dakı **köhnə sistem** kodu (`L{dərs id}`) | 12 026 | **0** |
| Çap edilən kodun hədəfdə mövcudluğu | yoxlanmırdı | **120 118 / 120 118 = 100 %** |
| **FANTOM KOD** | 354 | **0** |

Yoxlama proqramla aparılır (`fix3/verify_codes.py`): hər faylın hər sətrinin
`fenn_kodu` dəyəri canlı `registrar_subject` kod universi (2 501 kod) ilə
tutuşdurulur. Nəticə: **fantom kod 0**. Kod xanası boş qalan yeganə kateqoriya
**K8-dir** — o, tələbə səviyyəsindədir, fənnə aid deyil. Boş xanaların **tam
sayı 1 974-dür**: K8-in **987** sətri + baş siyahıda onların **987** güzgüsü
(`BAS_SIYAHI_telebe_fenn.tsv`). 4-cü nüsxə yalnız birincisini deyirdi.

### 0.00.b «Fənn kodu» sütununda iki konvensiya qarışmışdı — vahidləşdirildi

3-cü nüsxədə eyni sütun iki fərqli şey daşıyırdı: K13/K0 **hədəf** kodunu,
K4 (10 849) · K5 (1 110) · K6 (67) — cəmi **12 026 sətir** isə köhnə sistemin
`lessons.lesson_code` / `L{dərs id}` dəyərini. Sahib bu sütuna görə süzgəc
qura bilmirdi.

İndi **üç ayrı sütun** var:

| Sütun | Nədir |
|---|---|
| **Fənn kodu (yeni sistem)** | EMS Arena-dakı **həqiqi** `registrar_subject.code` — mövcudluğu yoxlanılıb. **Süzgəc üçün bu sütun.** |
| **Köhnə sistemdə dərs id** | myedu `lessons.id`. 20 dərs tək fənnə birləşdirilib, ona görə bu id-dən yeni kodu **uydurmaq olmaz**. |
| **Köhnə sistemdə fənn kodu** | myedu `lessons.lesson_code`, olduğu kimi. Köhnə bazada çox vaxt mənasızdır («37» 1 984 dərsdə, «01» 186 dərsdə) — yalnız arayış üçün. |

### 0.00.c Süpürgə — eyni səhv başqa kateqoriyalarda varmı

Bütün 18 fayl və hər sətir yoxlandı:

| Yoxlama | Nəticə |
|---|---|
| Fənn kodu **konvensiyadan** qurulan kateqoriya | yalnız **K13 / K0 / DUB** — düzəldildi |
| Fənn kodu **köhnə sistem** dəyəri olan kateqoriya | **K4 · K5 · K6** (12 026 sətir) — düzəldildi |
| Fənn kodu hədəfdəki açılış FK-sından gələn kateqoriya | K1 · K2 · K3 · K7 · K9 · K10 · K10b · K11 · K12 — **artıq düzgün idi** (0 uyğunsuzluq) |
| **Hökmü** fənn həllindən asılı olan kateqoriya | yalnız **K13** — digərləri açar-əsaslıdır, yalan hökm riski yoxdur |
| Konsolidasiya olunmuş dərsə toxunan sətir (bütün fayllar) | **1 068** — kodu düzəldildi; yalnız K13-ün 328-i əvvəl yanlış idi |
| Köhnə dərs → hədəf fənn örtüyü (avtoritetli xəritə) | **2 521 / 2 521 = 100 %** |

**Kateqoriya fayllarında sətir sayı dəyişmir (70 255).** Dəyişən **hökm** və
**fənn kodudur**. Ümumi şiddət bölgüsü: 🔴 26 346 → **26 194** ·
🟠 33 665 → **33 806** · 🟡 10 244 → **10 255**.

> ⚠️ **Baş siyahı isə dəyişdi** — 4-cü nüsxə bunu açıqlamırdı.
> `BAS_SIYAHI_telebe_fenn.tsv` 50 992 → **50 188** sətir (−804), hadisə
> 269 480 → **269 257** (−223). Səbəb və hansı rəqəmin doğru olduğu **§0.000.c**-də.

---

### 0.0 ⚠ BLOKER — K13-də fənn həll olunmurdu, buna görə **hökm səhv idi**

**Kök səbəb bir cümlədir: proqram bilmədiyini «yoxdur» kimi çap edirdi.**

2-ci nüsxədə K13-ün hədəf yoxlaması tək açardan asılı idi — «köhnə jurnal
`uniqid` + köhnə tələbə id → `registrar_enrollment`». Açar tutmayanda düzgün
cavab **«müəyyən edilə bilmədi»** olmalı idi; proqram isə **qəti «yazılış
yoxdur»** yazırdı. Yəni **bilməmək faktı hökmə çevrilirdi.**

Açar niyə tutmurdu: `source_journal_ref` mənbədə **iki fərqli formada** gəlir —
`yekun` cədvəlində **nömrəli** `journals.id`, `journals_dates_points(_archive)`
cədvəlində isə **mətn** `journals.uniqid`. 2-ci nüsxə yalnız nömrəli formanı
tanıyırdı. Nəticədə **4 525 sətirdə** «Fənn» sütunu boş (`#lesson …`), «Fənn
kodu» boş qalırdı — və fənn bilinmədiyi üçün hədəfə baxmaq **ümumiyyətlə
mümkün olmurdu**.

Bu, sadəcə boş sütun deyildi: sənəd universitetə **artıq düzgün köçürülmüş
balları** «yeni sistemdə görünmür» deyə axtartdırırdı.

**Düzəliş.** Jurnal hər iki formada tanınır və fənn
`journals_dates_points.journal_uniqid → journals.lesson_id → lessons`
zənciri ilə bərpa olunur:

| Fənnin mənbəyi | Sətir |
|---|---:|
| Qiymət faktının öz `source_lesson_ref` sütunundan | 7 939 |
| **`journals.lesson_id`-dən bərpa olundu** | **4 525** |
| Bərpa olunmadı | **0** |
| **Örtük — köhnə DƏRS id-si** | **12 464 / 12 464 = 100 %** |

> ⚠ **Bu 100 % yalnız köhnə DƏRS id-sinə aiddir — FƏNN KODUNA yox.**
> 3-cü nüsxə fənn kodunu həmin id-dən `MYEDU-L{id}` konvensiyası ilə
> uydururdu, ona görə **354 sətirdə çap olunan kod hədəfdə mövcud deyildi**.
> Bu fərq 3-cü nüsxədə heç yerdə deyilmirdi. Düzgün ayrılmış örtük:
>
> | Örtük növü | 3-cü nüsxə | **4-cü nüsxə** |
> |---|---:|---:|
> | Köhnə **dərs id-si** həll olunur | 12 464 / 12 464 = **100 %** | 12 464 / 12 464 = **100 %** |
> | Hədəfdə **MÖVCUD fənn kodu** çap olunur | 12 110 / 12 464 = **97,16 %** | **12 464 / 12 464 = 100 %** |
>
> Səbəb §0.00-dədir: fənn indi avtoritetli `lesson_subject` xəritəsi ilə həll
> olunur, konvensiya ilə yox.

**Hökm indi dörd ayrı haldır və heç biri fərziyyə deyil:**

| Hökm | Sətir | Hara getdi |
|---|---:|---|
| **Hədəfdə VAR — eyni dəyər** | **636** | K0 vərəqi (591) + dublikat fayllar (45) |
| Hədəfdə VAR — dəyər fərqli | 130 | K13-də qalır (120) |
| Hədəfdə YOXDUR | 11 482 | K13-də qalır (10 479) |
| **Müəyyən edilə bilmədi** | **216** → 4-cü nüsxədə **227** | K13-də 🟡 kimi qalır — **«yoxdur» DEMƏK DEYİL** |

Son sətir ən vacibidir. Bu sətirlərdə köhnə dəyər **eyni fənndə tapılır**, amma
**başqa tədris ili/semestrdə**; hansı açılışa aid olduğu **mənbədən bilinmir**.
Cavab bilinmədiyi üçün **hökm verilmir** — «İtki növü» sütununda açıq şəkildə
«MÜƏYYƏN EDİLƏ BİLMƏDİ — hökm verilmir» yazılır.

> ⚠ **SƏBƏB 26 sətirdə yanlış izah olunmuşdu.** 3-cü nüsxə bütün 216 sətir üçün
> «mənbə cədvəlində (`imthngrscxsblr`) nə jurnal, nə semestr sütunu var» yazırdı.
> Bu, yalnız bir hissəsi üçün doğrudur. Faktiki bölgü (4-cü nüsxə, 227 sətir):
>
> | Mənbə | Sətir | Səbəb — dəqiq ifadə |
> |---|---:|---|
> | `imthngrscxsblr` | **201** | cədvəldə **jurnal da, semestr də sütun kimi yoxdur** — sətir hansı açılışa aid olduğunu göstərmir |
> | `journals_dates_points` | **26** | **jurnal VAR** (`journal_uniqid` doludur); dəyər eyni fənndə tapılır, amma **jurnalın semestri ilə hədəf açılışın semestri uyuşmur** |
>
> Yəni 26 sətirdə **hökm doğru, SƏBƏB yanlış** idi. İndi hər sətrin öz səbəbi
> «İstiqamət / yoxlama nəticəsi» sütununda yazılır.

**Nəticə: 85 sətir yalançı müsbət çıxdı** və K0-a köçürüldü. Uçdan-uca
təsdiqlənmiş dörd nümunə — hamısı 2-ci nüsxədə 🔴 «yeni sistemdə görünmür»
yazırdı, faktiki vəziyyət isə budur:

| Tələbə | Fənn | Köhnə | Yeni sistemdə |
|---|---|---:|---:|
| 1330 Novruzlu Rauf | Pedaqoji psixologiya | 29 | **imtahan 29.00** |
| 2291 Kərimov Pərviz | Multikulturalizmə giriş | 29 | **imtahan 29.00** |
| 904 Fileydanov Sərxan | Dil tarixi | 19 | **imtahan 19.00** |
| 805 MUSAYEV MƏHƏMMƏD | Mülki müdafiə | 25 | **imtahan 25.00** |

**Şiddət də düzəldi.** Fənn həll olunandan sonra K13-ün bir çox sətri «heç bir
yazılış yoxdur 🔴» halından «eyni fənndə yazılış var, başqa açılış 🟠» halına
keçdi: K13-ün şiddət bölgüsü **🔴 9 286 / 🟠 1 562 / 🟡 190** → **🔴 7 909 /
🟠 2 690 / 🟡 216** → (4-cü nüsxə, §0.00) **🔴 7 757 / 🟠 2 831 / 🟡 227**.

---

### 0.0b Canlı ↔ arxiv dublikatı — 138 sətir

`journals_dates_points_archive` cədvəlinin **138 sətri** canlı
`journals_dates_points` cədvəlinin **eyni sətridir** — eyni `id`, eyni tələbə,
eyni jurnal, eyni bal. K13-də hər ikisi ayrıca problem kimi sayılırdı.
Mənbədə birbaşa yoxlanıldı (`id=241786`: hər iki cədvəldə hərfən eyni sətir);
K13-ə düşən **138 arxiv sətrinin 138-i də** canlı əkizinə tam bərabərdir.
Hamısı çıxarıldı → `DUB_K13_ARXIV_EYNI.tsv`.

**Eyni naxış başqa yerdə varmı — yoxlandı.** Mənbədəki **bütün** arxiv/köhnə
cədvəllər süzüldü:

| Cədvəl | Sətir | Nəticə |
|---|---:|---|
| `journals_dates_points_archive` | 776 033 | yeganə dolu arxiv — 138-i K13-ə düşürdü |
| `yekun_old` | **0** | boşdur |
| `yekun_24_02_2023` | **0** | boşdur |

**Gündəlik xana kateqoriyalarında (K3 · K6 · K10 · K10b) bu naxış YOXDUR:**
orada canlı + arxiv axını açar səviyyəsində birləşdirilib —
**5 134 272 sətir = 5 134 272 unikal açar** (sıfır dublikat açar), və həmin
kateqoriyaların heç birində tam eyni sətir təkrarlanmır (0 dublikat).
Yəni dublikat riski yalnız K13-in oxuduğu sübut cədvəlində vardı.

---

### 0.1–0.6 · 2-ci nüsxənin düzəlişləri (1-ci nüsxəyə görə)

Sizə göndərdiyim **birinci nüsxədə dörd yerdə interpretasiya səhvi vardı**.
Rəqəmlərin özü və data zənciri düzgün idi (bütün onlarla sətir uçdan-uca
mənbə ↔ hədəf tutuşdurulub, köçürmə sadiqliyi də təsdiqlənib:
`yekun` 17 194→17 194 · `imthngrscxsblr` 12 544→12 544 · `balvereqi_logs`
52 386→52 386), amma **sətirlərin oxunuşu** yanlış idi. Dördü də düzəldildi.

### 0.1 «Yeni sistemdə heç nə» — 506 yalançı müsbət

Birinci nüsxədə K13-ün **bütün 12 464 sətri** istisnasız «(yeni sistemdə heç nə)»
yazırdı. Bu, ölçülmüş fakt deyil, **fərziyyə** idi: sətir yazılışa bağlanmadığına
görə hədəfin boş olduğu güman edilmişdi.

İndi **hər K13 sətri üçün hədəf baza həqiqətən yoxlandı** (yazılış açarı: köhnə
jurnal `uniqid` + köhnə tələbə id → `registrar_enrollment`, sonra
`registrar_finalgrade` və təkrar imtahan qeydi). Nəticə:

| K13-ün ziddiyyətli (`legacy_grade_fact_conflict`) 506 sətri | Say |
|---|---:|
| Yazılış yeni sistemdə **VAR** | **506 / 506** |
| `registrar_finalgrade` sətri **VAR** | **506 / 506** |
| Köhnə imtahan balı yeni sistemdə **imtahan balı kimi** durur | **494** |
| Köhnə imtahan balı yeni sistemdə **təkrar imtahan balı kimi** durur | **12** |
| **Yeni sistemdə tapılmayan dəyər** | **0** |

> **Nümunə — məhz birinci nüsxədə K13-ün əsas nümunəsi kimi verdiyim sətir.**
> Abbasova Şəfiqə, 330 F2, «Dil tarixi», 2022/2023 Payız.
> Birinci nüsxə: «Köhnə: giriş 9 · imtahan 12 · yekun 21 … **Yeni sistemdə heç nə
> görünmür**».
> Faktiki hədəf vəziyyəti: **imtahan 12.00 · komponent cəmi 45.00 (5 xana) ·
> 15 dərs xanası**, açılış 330 F2 / 2022/2023 / Payız. Yəni bal yerindədir.

> **Nümunə (12-lik qrup).** HƏSƏNZADƏ DƏNİZ, 531 M, «Ekonometrika», 2022/2023 Payız.
> Köhnə `yekun`: giriş 36 · **imtahan 17** · yekun 53.
> Yeni sistem: imtahan balı **8.00**, amma **təkrar imtahan 17.00** — yəni köhnə 17
> yerindədir, sadəcə təkrar imtahan xanasındadır. 8.00 ilə 17.0 arasındakı fərq
> **köhnə sistemin öz daxili ziddiyyətidir** və artıq **K11 və K12-də sayılır**;
> K13-də üçüncü dəfə saymaq düzgün deyil.

Bu 506 sətir siyahıdan silinmədi — **«K0 · Yoxlanıldı» adlı ayrıca vərəqə**
çıxarıldı (154 tələbə); orada həm köhnə, həm yeni dəyər yan-yana görünür.
Universitetdə yoxlamağa ehtiyac yoxdur.

**Eyni yoxlama K13-ün qalan 11 038 sətrinə də tətbiq olundu** və «Yeni sistemdə»
sütunu artıq faktiki vəziyyəti yazırdı:

| Yeni sistemdəki faktiki vəziyyət (2-ci nüsxə) | Sətir |
|---|---:|
| Yazılış yoxdur (və ya tələbə hesabı köçməyib) — dəyər həqiqətən görünmür | 8 339 |
| Eyni fənndə yazılış var (başqa açılış), imtahan balı boşdur | 2 488 |
| Eyni fənndə yazılış var (başqa açılış), bal fərqlidir | 21 |
| Ehtimal olunan uyğunluq — mənbə cədvəlində semestr sütunu yoxdur (🟡) | 190 |

⚠️ **Bu cədvəl 2-ci nüsxənin vəziyyətidir və artıq etibarlı deyil.** Birinci
sətrin (8 339) böyük hissəsi **ölçülməmiş fərziyyə** idi: həmin sətirlərdə fənn
ümumiyyətlə həll olunmamışdı, ona görə hədəfə baxmaq mümkün deyildi.
Düzəldilmiş bölgü üçün **§0.0-a** baxın.

*Qeyd:* son sətir üçün dəqiq cavab **mənbədə yoxdur** — köhnə `imthngrscxsblr`
(imtahan buraxılış) cədvəlində nə jurnal, nə semestr sütunu var, yalnız
tələbə + fənn + tarix. Ona görə bu 190 sətir «təsdiqlənmiş» yox, **«ehtimal»**
kimi işarələnib və 🟡-ə endirilib.

### 0.2 Toqquşmanın istiqaməti — «itki» sözü 128 sətirdə tərsinə idi

Birinci nüsxə K1/K2/K3-ün **hamısını** «bal itdi» adlandırırdı. Toqquşmada
atılan dəyər hədəfdə qalandan **aşağı** da ola bilər — o zaman tələbə heç nə
itirmir. Hər sətirdə istiqamət indi hesablandı və **ayrıca sütuna** yazıldı
(«İstiqamət / yoxlama nəticəsi»):

| Kateqoriya | Sətir | Tələbə **İTİRİB** | Tələbə **QAZANIB** | Bərabər |
|---|---:|---:|---:|---:|
| K1 · imtahan balı | 20 | **8** | **12** | 0 |
| K2 · kollokvium / sərbəst iş | 285 | **170** | **115** | 0 |
| K3 · gündəlik xana (rəqəmli) | 315 | **314** | **1** | 0 |

> **Nümunə.** «Qafqaz xalqları tarixi» (206/2QX, 2022/2023 Payız) jurnalında
> K1-in 7 sətri var. Onların **6-sında** hədəfdə qalan imtahan balı atılandan
> **yüksəkdir** (+2 … +10): Quluzadə Elvin 32 → **42**, Orucova Jalə 27 → **33**.
> Yalnız bir sətirdə (Cəfərov Samir 35 → 34) tələbə 1 bal itirir.
> Bu, atılan jurnalın **daha erkən / qaralama** nüsxə olduğunu göstərir.

⚠️ **Bu, imtahan protokolu üçün vacibdir.** Rəsmi düzəliş sənədi yalnız
**«Tələbə İTİRİB»** sətirləri üzərinə yazılmalıdır — cəmi **492 sətir**
(K1 8 · K2 170 · K3 314). «QAZANIB» sətirlərində tələbənin balı aşağı
düşməyib; onlara sənəd qaldırmaq lazım deyil.

### 0.3 K3-ün 🔴 etiketi 256 sətirdə əsassız idi (45 % şişirtmə)

Birinci nüsxə K3-ün **571 sətrini** «rəqəmli bal itib 🔴» sayırdı. Faktiki bölgü:

| K3-ün 1 289 sətrinin daxili bölgüsü | Sətir | Doğru şiddət |
|---|---:|---|
| Mənbə rəqəmli → hədəfdə rəqəm yoxdur (iştirak/qayıb) | 309 | 🔴 **rəqəmli bal itdi** |
| Hər iki tərəf rəqəmli, dəyər fərqli | 6 | 🔴 (5 itki) / 🟠 (1 qazanc) |
| **Mənbə «iştirak/qayıb» → hədəfdə rəqəmli bal VAR** | **256** | 🟠 **bal yerindədir**, yalnız davamiyyət işarəsi itib |
| İştirak ↔ qayıb ziddiyyəti (heç bir tərəfdə rəqəm yoxdur) | 718 | 🟠 |

Real rəqəmli itki **315 sətirdir, 571 deyil**. 571 rəqəmi 256 sətri —
**balın saxlanıldığı** halları — səhvən itki sayırdı (45 % şişirtmə).

> **Nümunə — birinci nüsxədə K3-ün nümunəsi kimi verdiyim sətir.**
> ZİNATOV ELDAR, 132 P ing, «Fəlsəfə», 2023-10-13. Bir jurnalda **iştirak**,
> digərində **9 bal**; yeni sistemdə **9.00 qaldı**. Yəni **bal itməyib** —
> itən yalnız «iştirak» işarəsidir. Bu sətir 🔴 yox, 🟠 olmalıdır.

### 0.4 K5 və K13 eyni köhnə sətirləri iki dəfə sayırdı — 920 dublikat

Köhnə `yekun` cədvəlinin bağlanmamış sətirləri həm **K5**-də, həm **K13**-də
görünürdü. Kəsişmə **təxmini deyil, dəqiq ölçüldü**: hər iki tərəfdə köhnə
`yekun.id` (hədəfdə `registrar_legacygradefact.source_pk`) var.

| | Sətir |
|---|---:|
| K5 — `yekun`-un bağlanmamış bütün sətirləri (1 059 atılmış mənbə + 344 qrup uyğunsuzluğu + 576 həll olunmayan) | 1 979 |
| K13-ün `yekun` mənbəli sətirləri (344 + 576 + 506 ziddiyyətli) | 1 426 |
| **Kəsişmə (dəqiq açar: köhnə `yekun.id`)** | **920** |

920 dublikat **K13-dən çıxarıldı**; **K5 kanonik siyahıdır**. Çıxarılan
sətirlər `DUB_K13_K5_ile_eyni.tsv` faylında izlənilə bilər.

**Nəticə:** K13-ün `yekun` mənbəli **1 426 sətrinin hamısı** ya K5 dublikatı
(920), ya yalançı müsbət (506) çıxdı — bu mənbədən **bir dənə də yeni problem
yoxdur**. (2-ci nüsxədə K13-də qalan 11 038 sətir yalnız iki mənbədən idi:
imtahan buraxılış cədvəli `imthngrscxsblr` 6 513 · gündəlik jurnal xanası
4 525. 3-cü nüsxədə bu 4 525 sətrin fənni bərpa olundu və 138-i arxiv
dublikatı çıxdı — bax §0.0 və §0.0b.)

*Ölçmə qeydi:* düşmən baxışı bu kəsişməni **866** ölçmüşdü — o rəqəm
`(köhnə id, fənn, tədris ili, semestr, mənbə dəyəri)` təxmini açarının
**unikal açar** sayıdır; həmin açar bəzi fərqli mənbə sətirlərini birləşdirir.
Sətir səviyyəsində eyni açar 937 verir. Mənbə sətir id-si ilə dəqiq cavab
**920-dir** və dedup bununla aparıldı.

### 0.5 Digər düzəlişlər

- **«Toqquşmada itən fərqli dəyər» = 1 594** (1 653 deyil). 1 653 köhnə
  RUN2 sıra seçimindən gəlirdi. Sıradan asılı olmayan ölçü:
  təqvim 1 289 · komponent 285 · imtahan 20.
- **Yazılış ötürülmə səbəbi.** RUN3 hesabatının «əsas səbəb
  `legacy_journal_student_inactive` (5 hadisə)» cümləsi **yanlışdır** —
  5 hadisə heç cür «əsas səbəb» ola bilməz. Doğru bölgü (18 360 ötürülmüş
  yazılış):

  | Səbəb kodu | Say | Hansı kateqoriyada |
  |---|---:|---|
  | `legacy_journal_enrollment_orphan` (sahibsiz jurnal) | 10 836 | K4 |
  | `legacy_journal_student_group_mismatch` (qrup uyğunsuzluğu) | 3 862 | **K9** |
  | `legacy_journal_student_unresolved` (tələbə hesabı köçməyib) | 3 550 | K4 |
  | `legacy_journals_students_invalid` (siyahı pozuq — karantin) | 107 | K4 |
  | `legacy_journal_student_inactive` (jurnalda aktiv deyil) | **5** | K4 |

  Birinci nüsxənin K4 bölməsi qrup uyğunsuzluğunu da K4-ün içində sayırdı;
  əslində o, ayrıca **K9** kateqoriyasıdır (K4 = 14 498, K9 = 3 862).

### 0.6 Rəqəmlərin dəyişməsi — bir baxışda

| Göstərici | 1-ci | 2-ci | 3-cü | 4-cü | **Bu nüsxə (5-ci)** |
|---|---:|---:|---:|---:|---:|
| Cəmi problemli sətir | 71 904 | 70 478 | 70 255 | 70 255 | **70 255** |
| — yalançı müsbət (dəyər hədəfdə var) çıxarıldı | — | −506 | −591 | −591 | −591 |
| — K5 ilə dublikat çıxarıldı | — | −920 | −920 | −920 | −920 |
| — **canlı ↔ arxiv dublikatı** çıxarıldı | — | — | −138 | −138 | −138 |
| 🔴 Yüksək | 29 379 | 27 723 | 26 346 | 26 194 | **26 194** |
| 🟠 Orta | 32 497 | 32 537 | 33 665 | 33 806 | **33 806** |
| 🟡 Baxılmalı | 10 028 | 10 218 | 10 244 | 10 255 | **10 255** |
| Universitetdə əl ilə yoxlanmalı | 40 754 | 38 944 | 38 721 | 38 721 | **38 721** |
| Toqquşmada **həqiqi** bal itkisi (K1+K2+K3 🔴) | 876 | 492 | 492 | 492 | 492 |
| K13 sətri | 12 464 | 11 038 | 10 815 | 10 815 | **10 815** |
| **K13-də fənni həll olunmayan sətir** | 12 464 | 4 525 | 0 | 0 | **0** |
| **Ləğv olunan yalan qəti hökm** | — | 506 | 4 525 | 152 | **171** |
| **«Müəyyən edilə bilmədi» kimi işarələnən** | 0 | 190 | 216 | 227 | **227** |
| **Fantom fənn kodu (hədəfdə mövcud deyil)** | — | — | 354 | 0 | **0** |
| **Köhnə sistem kodu «Fənn kodu» sütununda** | — | — | 12 026 | 0 | **0** |
| **K13 «Hədəfdə VAR — dəyər fərqli»** | — | 21 | 121 | 121 | **288** |
| **İxtiyari seçimdən doğan qəti hökm** | — | — | — | 171 | **0** |
| **İxtiyari seçimdən doğan «Fərq» rəqəmi** | — | — | — | 3 | **0** |
| **Baş siyahı sətri** (`telebe_fenn`) | — | — | 50 992 | 50 188 | **50 188** |
| — baş siyahının hadisə cəmi | — | — | 269 480 | 269 257 | **269 257** |
| Tarixi bərpa olunan sətir | — | 64 957 (92,2 %) | 69 259 (98,6 %) | 69 259 (98,6 %) | **69 259 (98,6 %)** |
| Toxunulan unikal tələbə | 6 146 | 6 146 | 6 146 | 6 146 | 6 146 |

**Heç bir real problem siyahıdan silinmədi** — yalnız yalançı müsbətlər və
dublikatlar ayrıldı, hər ikisi ayrıca faylda/vərəqdə saxlanıldı.

---

## Fayllar

| Fayl | Nədir |
|---|---|
| `BAL_PROBLEMLERI.xlsx` | **Əsas təhvil.** 6 vərəq: Xülasə · Yüksək prioritet · Orta · Baxılmalı · **K0 · Yoxlanıldı** · Tələbə üzrə |
| `BAL_PROBLEMLERI.csv` | Eyni 70 255 sətir, UTF-8 BOM ilə (Excel düzgün açır) |
| `bal_problemleri/BAS_SIYAHI_telebe_fenn.tsv` | Tələbə + fənn üzrə yığcam siyahı — **50 188 sətir · 269 257 hadisə** (açar: köhnə tələbə id + **fənn KODU** + tədris ili + semestr, §0.000.b) |
| `bal_problemleri/K*.tsv` | Kateqoriya üzrə xam fayllar + `00_INDEKS.tsv` |
| `bal_problemleri/K0_yoxlanildi_problem_deyil.tsv` | **Yoxlanıldı, problem deyil** — 591 sətir, cəmə daxil deyil |
| `bal_problemleri/DUB_K13_K5_ile_eyni.tsv` | K5 ilə dublikat 920 sətir, cəmə daxil deyil |
| `bal_problemleri/DUB_K13_ARXIV_EYNI.tsv` | **Canlı ↔ arxiv dublikatı** 138 sətir, cəmə daxil deyil |

Hər sətir = **bir tələbə + bir fənn + bir hadisə**. Sətirdə ad, ata adı, köhnə ID,
qeydiyyat qrupu, ixtisas, jurnal qrupu, **fənn kodu (yeni sistem)**, fənn,
**köhnə sistemdə dərs id**, **köhnə sistemdə fənn kodu**, müəllim, tədris ili,
semestr, **tarix**, köhnə sistemdəki dəyər, **yeni sistemdəki faktiki dəyər**,
fərq, **istiqamət / yoxlama nəticəsi** və izah var.

> **5-ci nüsxədə məzmun dəyişikliyi.** `.xlsx` və `.csv` yenidən quruldu —
> 171 sətirdə «xana boşdur» hökmü düzəldi (§0.000). Sətir sayı və şiddət
> bölgüsü dəyişmədi; dəyişən yalnız **hökm mətnidir**. Əvvəlki nüsxəni
> saxlamısınızsa, «İstiqamət / yoxlama nəticəsi» sütununu yeniləyin.
>
> **4-cü nüsxədə sütun dəyişikliyi.** «Fənn kodu» sütunu ikiyə bölündü:
> **«Fənn kodu (yeni sistem)»** — EMS Arena-dakı həqiqi kod (hamısının
> mövcudluğu yoxlanılıb, **fantom 0**) — süzgəc üçün bu sütunu işlədin; və
> **«Köhnə sistemdə dərs id» / «Köhnə sistemdə fənn kodu»** — köhnə myedu
> identifikatorları. Əvvəlki nüsxələrdə bu iki konvensiya **eyni sütunda
> qarışmışdı** (§0.00.b).

70 255 sətrin **69 259-unda (98,6 %) həqiqi tarix var** və Excel-də süzülür.
(2-ci nüsxədə 92,2 % idi — fənn/jurnal açarı bərpa olunanda 4 525 sətrin semestr
pəncərəsi də bərpa olundu.)

---

## 1. Ümumi mənzərə

| Göstərici | Say |
|---|---:|
| Köhnə sistemdən yeni sistemə **uğurla köçən bal xanası** | **4 368 694** |
| Bu xanaların **dəyər səviyyəsində yoxlanması** | hamısı yoxlandı |
| Yeni sistemdə **səhv dəyər** tapılan xana | **0** |
| Səbəbi adlandırıla bilməyən («izahsız») fərq | **0** |
| Hazır bərpa ilə **avtomatik geri qaytarılan** xana | **161 775** |
| Bu siyahıdakı problemli sətir | **70 255** |
| Ayrıca: yoxlanıldı, problem deyil | 591 |
| Ayrıca: K5 ilə dublikat | 920 |
| Ayrıca: canlı ↔ arxiv dublikatı | 138 |
| Toxunulan **unikal tələbə** | **6 146** |

İki nəticəni ayrıca vurğulayıram:

1. **Yeni sistemdə duran hər bal mənbənin real balıdır.** Bütün 4,3 milyon xana
   bir-bir tutuşduruldu — heç bir yerdə «uydurulmuş» və ya sürüşmüş dəyər yoxdur.
2. **Problem «bal səhvdir» yox, «bal çatışmır» şəklindədir** — köçmə zamanı bəzi
   xanalar bağlanacaq yer tapmayıb və görünmür.

---

## 2. Nə etmək lazımdır — 70 255 sətrin beş səbəti

Excel-də **«Həll yolu»** sütununa görə süzün:

| Həll yolu | Sətir | Nə deməkdir |
|---|---:|---|
| **Hazır bərpa ilə avtomatik bağlanır** | **10 769** | Düzəldici artıq yazılıb və ölçülüb (K10 + K10b) |
| **Sistem qərarı — düzəliş tələb etmir** | **13 206** | Giriş balı düsturunun fərqi; qərar sənədləşib |
| **Köhnə sistemdə də yoxdur — universitet qərarı** | **7 175** | Köçürmə qüsuru deyil (K7 + K8) |
| **Tələbəyə zərəri yoxdur — yalnız qeyd** | **384** | Toqquşmada atılan dəyər hədəfdə qalandan **aşağı** idi, ya da rəqəmli bal yerində qalıb |
| **UNİVERSİTETDƏ ƏL İLƏ YOXLANMALI** | **38 721** | **Əsl iş siyahısı budur** |

Ayrıca vərəqdə: **591 sətir yoxlanıldı və problem olmadığı təsdiqləndi.**
Ayrıca fayllarda: **920 + 138 dublikat** (cəmə daxil deyil).

### 2.1 Avtomatik bağlanan hissə (10 769 sətir)

Köhnə sistemdə bal yazılıb, amma həmin gün üçün **dərs cədvəli sətri yox idi**,
ona görə balın bağlanacağı dərs yaranmayıb. Düzəldici (J12 bərpası) balın öz
`(ay, gün, saat)` açarından dərsi özü yaradır. Bu bərpa **ayrıca nüsxədə işə
salınıb və ölçülüb**: `registrar_lesson` +11 607 sətir, **`registrar_lessonmark`
+161 775 xana**, ondan sonra bu kateqoriya sıfıra düşür.

Yalnız **173 xanada** bərpa hədəfdə duran **fərqli** dəyərin üstünə düşür — insan
qərarı yalnız bu 173-ə lazımdır. (Digər 2 712 toqquşmada dəyər eynidir.)

### 2.2 Ən ağır nöqtələr — ilk baxılası yer

1. **ƏLİZADƏ RƏSUL** (köhnə id 3256, qrup 132 SI, «Mülki müdafiə», 2022/2023 Payız).
   Müəllim **2023-03-28 07:26:36**-da imtahan balını 1-dən **39**-a düzəldib.
   Yeni sistemdə **1.00** durur. Fərq **−38** — siyahıdakı ən böyük tək itki.
2. **Toqquşmada tələbənin İTİRDİYİ 492 sətir** (K1 8 · K2 170 · K3 314).
   Rəsmi düzəliş sənədi yalnız bunlara lazımdır.
3. **K13-ün 288 sətri** — tələbənin eyni fənndə yazılışı var, amma hədəfdəki
   bal köhnə dəyərdən fərqlidir. Bu rəqəm hər dövrdə böyüdü, çünki hər dəfə
   proqramın **gizlətdiyi** bir dəstə üzə çıxdı: 2-ci nüsxədə 21 → 4-cü
   nüsxədə 121 → **5-ci nüsxədə 288** (ixtiyari seçim aradan qalxdı, §0.000).

---

## 3. Kateqoriyalar — nə baş verib və bir nümunə

### K0 · Yoxlanıldı — problem DEYİL (591 sətir · 197 tələbə · ayrıca vərəq)
Köhnə qiymət faktı yazılışa bağlanmayıb, amma **dəyərin özü yeni sistemdə
eyni rəqəmlə durur** — **573**-ü imtahan balı, **13**-ü təkrar imtahan balı,
**5**-i komponent balı kimi. `registrar_finalgrade` / təkrar imtahan / komponent
xanaları bir-bir yoxlanıb. Bunların **85-i 3-cü nüsxədə əlavə olundu** — fənn
açarı bərpa olunandan sonra ortaya çıxdı (§0.0).
**Cəmi sətir sayına daxil deyil.**

### K1 · Toqquşma — imtahan balı (20 sətir · 20 tələbə · 🔴 8 / 🟠 12)
Köhnə sistemdə eyni fənnin **iki ayrı jurnalı** var idi; yeni sistemdə onlar bir
dərs açılışına birləşdi. Eyni tələbənin imtahan balı iki jurnalda **fərqli** idi —
yeni sistemə yalnız biri düşdü, digəri heç yerdə saxlanmadı.
**8 sətirdə tələbə itirib; 12 sətirdə hədəfdə qalan bal atılandan yüksəkdir.**

> **Nümunə (itki).** ƏLİZADƏ RƏSUL — yuxarıda.
> **Nümunə (qazanc).** Quluzadə Elvin, 206/2QX, «Qafqaz xalqları tarixi».
> Atılan jurnalda 32, hədəfdə qalan **42**. Tələbə heç nə itirməyib.

### K2 · Toqquşma — kollokvium / sərbəst iş (285 sətir · 181 tələbə · 🔴 170 / 🟠 115)
Eyni birləşmə mexanizmi; dəyər kollokvium və ya sərbəst iş balıdır.

> **Nümunə.** Fərədova Ayan, 534 T ing, «Turizm coğrafiyası», 2024/2025 Payız,
> 2024-11-18. Kollokvium 1 — jurnal `Ek7Al3GXKU` → 8, jurnal `1ZuJJrydja` → 9.
> Yeni sistemdə **9.00**. Tələbə **itirməyib** (atılan dəyər 1 bal aşağı idi).

### K3 · Toqquşma — gündəlik xana (1 289 sətir · 835 tələbə · 🔴 314 / 🟠 975)
Eyni mexanizm, gündəlik dərs xanası üzərində. **Yalnız 314 sətirdə rəqəmli bal
itib.** 256 sətirdə rəqəmli bal hədəfdə saxlanılıb (yalnız iştirak/qayıb işarəsi
itib), 718 sətir isə iştirak↔qayıb ziddiyyətidir, 1 sətirdə tələbə qazanıb.

> **Nümunə.** ZİNATOV ELDAR, 132 P ing, «Fəlsəfə», 2023-10-13.
> Bir jurnalda iştirak, digərində 9 bal; yeni sistemdə **9.00 qaldı** —
> **bal itməyib**, itən yalnız iştirak işarəsidir (🟠).

### K4 · Jurnal-yazılışı ötürülüb (14 498 sətir · 76 754 xana · 2 961 tələbə · 🔴/🟠)
Tələbə köhnə jurnalda var, amma yeni sistemə **həmin fənnə yazılışı düşməyib** —
fənn onun transkriptində görünmür, deməli bütün bal xanaları da yoxdur.
Səbəb bölgüsü (**yalnız K4-ün öz sətirləri**): sahibsiz jurnal 10 836 ·
tələbə hesabı köçməyib 3 550 · jurnalın tələbə siyahısı pozuq (karantin) 107 ·
jurnalda aktiv deyil 5. *(Qrup uyğunsuzluğu ayrıca kateqoriyadır — K9, 3 862.)*

> **Nümunə.** Məmmədyarova Naima, 630-İ, «Mühit dizaynı-2», 2023/2024 Payız.
> Köhnə sistemdə **35 xana**, yeni sistemdə **0**.

### K5 · «Yekun» yazılışa bağlanmayıb (1 979 sətir · 888 tələbə · 🟠)
Köhnə sistemdə semestr yekun nəticəsi var, amma yeni sistemdə ona uyğun yazılış
tapılmadı (çünki yazılış özü köçməyib — K4/K9 ilə eyni kök).
**Bu kateqoriya `yekun` cədvəlinin bağlanmamış sətirləri üçün kanonikdir**;
K13-dən 920 dublikat məhz buna görə çıxarıldı.

> **Nümunə.** Cabbarlı Sona, 628.1, «Rəsm-4», 2022/2023 Payız.
> Köhnə: giriş 39 · imtahan 32 · **yekun 71**. Yeni sistemdə: yazılış yoxdur.

### K6 · Naməlum xana növü (3 826 sətir · 822 tələbə · 🟠)
Köhnə sistemin tanınmayan xana kodları — əsasən **xarici dil komponentləri**
(`pa`, `wr`, `sp` və s.). Dəyər itməyib: sübut cədvəlində saxlanılıb, amma
jurnal ekranında **görünmür**.

### K7 · Nə keçib, nə kəsilib (6 188 sətir · 1 198 tələbə · 🟡)
Tələbə dərslərə gəlib, amma **köhnə sistemdə** nə imtahan balı, nə nəticə var.
Köçürmə qüsuru deyil — köhnə bazanın öz boşluğudur.

### K8 · ÜOMG hesablana bilmir (987 tələbə · 🔴/🟡)
626 tələbənin heç bir fənndə imtahan balı yoxdur, **361 tələbənin isə
ümumiyyətlə heç bir yazılışı yoxdur**.

### K9 · Qrup uyğunsuzluğu (3 862 sətir · 116 633 xana · 1 440 tələbə · 🔴/🟡)
Tələbənin **qeydiyyat qrupu** ilə **jurnalın qrupu** üst-üstə düşmür, ona görə
yazılış (və bütün xanaları) ötürülüb. Adətən qrup dəyişikliyi olan tələbələrdir.

### K10 · İtən rəqəmli bal (5 147 sətir · 12 424 xana · 1 644 tələbə · 🔴)
Köhnə sistemdə bal var, amma **həmin gün üçün dərs cədvəli sətri yoxdur**.
**→ Hazır bərpa bunu avtomatik həll edir.**

### K10b · İtən qayıb (5 622 sətir · 19 108 xana · 1 748 tələbə · 🟠)
Eyni səbəb, itən dəyər **qayıbdır** — davamiyyət faizi olduğundan **daha yaxşı**
görünür. **→ Hazır bərpa həll edir.**

### K11 · İmtahan balı «yekun»-la uyğunsuz (1 073 sətir · 830 tələbə · 🔴/🟠)
840-ı köhnə sistemin **öz daxili ziddiyyətidir** (🟠) · **160-ı yalnız yekun-da
olub və tamamilə itib** · 29-da jurnal xanası var, hədəfə düşməyib ·
**44-ü nə yekun-a, nə xanaya bərabərdir** (🔴 — ən şübhəli qrup).

### K12 · Yekun bal kənarlaşması (14 664 sətir · 2 788 tələbə · 🔴/🟠/🟡)

| Səbəb | Sətir | Nə etməli |
|---|---:|---|
| **Giriş balı düsturunun fərqi** | 13 206 | Sistem qərarıdır — düzəliş tələb etmir |
| İmtahan balı fərqli | 876 | Yoxlanmalı |
| Təkrar imtahan hədəfdə sayılır, köhnə yekun-da yox | 350 | Yoxlanmalı |
| İmtahan balı hədəfə düşməyib | 189 | Yoxlanmalı |
| Köhnə yekun 100-dən böyük, yeni sistem 100-ə kəsir | 43 | Yeni davranış düzgündür |

### K13 · Bağlanmamış qiymət faktı (10 815 sətir · 2 510 tələbə · 🔴 7 757 / 🟠 2 831 / 🟡 227)
Köhnə sistemdə **real bal daşıyan** sətir heç bir yazılışa bağlana bilməyib.
12 464 namizəd sətrin **hamısında fənn həll olundu** (§0.0) və hədəf baza
bir-bir yoxlandı. Çıxarılanlar: **591** yalançı müsbət → K0, **920** K5
dublikatı, **138** canlı↔arxiv dublikatı.

Qalan 10 815 sətrin hökm bölgüsü:

| Hökm | Sətir | Şiddət |
|---|---:|---|
| Hədəfdə **YOXDUR** | 10 300 | 🔴 7 755 / 🟠 2 545 |
| Hədəfdə **VAR, dəyər fərqli** | 288 | 🟠 286 / 🔴 2 |
| **Müəyyən edilə bilmədi** | 227 | 🟡 227 |

Fənn bu kateqoriyada **avtoritetli** `lesson_subject` xəritəsi ilə həll olunur
(§0.00); 4-cü nüsxədə **152 yalan qəti hökm** ləğv edildi və **328 fantom fənn
kodu** həqiqi kodla əvəzləndi. 5-ci nüsxədə **171 «xana boşdur» hökmü**
ixtiyari seçimdən doğduğu üçün ləğv/açıqlandı (§0.000) — buna görə
«Hədəfdə VAR» 121-dən **288**-ə qalxdı.

**«Hədəfdə YOXDUR» 10 300 sətrin nə demək olduğu:**

| Alt-səbəb | Sətir | Nə lazımdır |
|---|---:|---|
| Tələbənin bu fənnə **heç bir yazılışı yoxdur** | 5 137 | yazılışı bərpa et, bal özü qayıdır |
| **Tələbə hesabı** yeni sistemə köçməyib | 2 482 | əvvəl hesab (aşağıya bax) |
| Yazılış var, **dəyərin xanası boşdur** | 2 681 | balı xanaya yaz |

⚠️ **«Hesab köçməyib» sətirləri bir ovuc hesabda toplanıb — ayrıca ölçü kimi
göstərilməlidir.** K13-ün 2 482 belə sətri **141 tələbədəndir**; ondan
**1 995 sətir (80,4 %) cəmi 90 tələbədəndir** — 83-ü köçürmədə `skipped`,
7-si `quarantined`. (Bu 90 hesab köçürmənin ümumi **84 skipped + 16
quarantined = 100** köçməmiş hesabının içindəndir.) Qalan 487 sətir
51 tələbədəndir və onlar avtoritetli xəritədə **ümumiyyətlə yoxdur** —
köhnə sistemdə silinmiş id.

**K13 + iki dublikat faylı + K0 birlikdə** (yəni yoxlanan 12 464 hökmün
hamısı) götürüləndə eyni ölçü: **3 116 sətir · 141 tələbə**, ondan
**2 568 sətir (82,4 %) həmin 90 tələbədən** (2 452 `skipped` + 116
`quarantined`), 548 sətir xəritədə olmayan 51 id-dən.

Yəni bu, minlərlə fərdi araşdırma deyil — **100 hesabın bərpası ilə həll
oluna bilən konsentrasiyadır**; hesablar qayıdanda 2 568 sətir öz-özünə
yenidən qiymətləndirilə bilər.

Mənbə bölgüsü: imtahan buraxılış cədvəli (`imthngrscxsblr`) **6 513**
(hamısının mənbədə real vaxtı var) · gündəlik jurnal xanası **4 302**.
**`yekun` mənbəli sətir qalmadı.**

⚠️ **227 sətir «yoxdur» demək deyil.** Orada köhnə dəyər eyni fənndə tapılır,
amma başqa tədris ili/semestrdə; sətir hansı açılışa aid olduğunu göstərmir.
Bunlara **hökm verilmir** — «İtki növü» sütununda «MÜƏYYƏN EDİLƏ BİLMƏDİ —
hökm verilmir» yazılır. Səbəb iki fərqlidir: **201** sətirdə (`imthngrscxsblr`)
mənbə cədvəlində nə jurnal, nə semestr sütunu var; **26** sətirdə
(`journals_dates_points`) **jurnal var**, amma jurnalın semestri hədəf açılışın
semestri ilə uyuşmur (§0.0).

> **Nümunə.** Köhnə `imthngrscxsblr` cədvəlində tələbənin imtahan giriş/çıxış
> balı var (məsələn giriş 43 · imtahan 41, 2022-10-05), amma həmin sətirdə
> **nə jurnal, nə semestr göstərilib** — ona görə heç bir yazılışa bağlanmayıb.
> Dəyər `registrar_legacygradefact` sübut cədvəlində durur, ekranlarda görünmür.

## 4. Tarix haqqında

69 259 sətirdə (98,6 %) həqiqi tarix var və Excel-də süzgəc işləyir. Tarixin
mənbəyi hər sətrin **«Tarixin mənbəyi»** sütununda yazılıb:

- **dərsin faktiki təqvim tarixi** — K3, K10, K10b
- **balın mənbədə yazılma vaxtı** (saat-dəqiqə ilə) — K1, K2, K6, K11 və K13-ün 6 513 sətri
- **itən xanaların ilk … son tarixi** (aralıq) — K4, K9
- **semestr pəncərəsi** — K5, K7, K12 və K13-ün qalanı (jurnal açarı bərpa
  olunandan sonra K13-ün 4 302 jurnal-xana sətri də bura düşdü — tarix örtüyü
  92,2 %-dən 98,6 %-ə qalxdı)

**Tarixi olmayan 5 521 sətir** üçün səbəb açıq yazılıb: köhnə sistemin `yekun`
cədvəlində **tarix sütunu ümumiyyətlə yoxdur**, K8 isə hadisə deyil, tələbə
səviyyəsində göstəricidir. Ayrıca **9 sətirdə mənbənin öz tarixi etibarsızdır**
(məsələn «fevralın 30-u») — orada xam mətn qeyd kimi saxlanılıb.

---

## 5. Dürüstlük qeydləri — ölçmə tarixçəsi

| İlkin qiymət | Ölçülmüş | İzah |
|---|---|---|
| K13-ün hamısı «yeni sistemdə heç nə» | **591 sətirdə dəyər hədəfdə VAR** | `registrar_finalgrade` / təkrar imtahan / komponent bir-bir yoxlandı (§0.1, §0.0) |
| K13-də 4 525 sətir «yazılış yoxdur» | **fənn həll olunmamışdı — hökm etibarsız idi** | Fənn 100 % bərpa olundu; 85 yalançı müsbət, 216 «müəyyən edilə bilmədi» (§0.0) |
| K13-də 171 sətir «yazılış var, dəyərin xanası boşdur» | **YALAN/GİZLİ — proqram bir neçə namizəd yazılışdan İXTİYARİ birini seçirdi** | 167-də başqa yazılışda dəyər VAR idi → «Hədəfdə VAR»; 4-də cümlə doğru idi, amma dəyərli qonşunu gizlədirdi → açıqlandı (§0.000) |
| «Xana boşdur» testi | **exam/resit ASİMMETRİK idi** | Uyğunluq axtarışı `exam` **və** `resit`-ə baxırdı, «boşdur» testi yalnız `exam`-a; təkrar imtahanı dolu 1 yazılış «boş» sayılırdı (§0.000) |
| Baş siyahının açarı | **fənn ADI idi** | Hədəfdə eyni ADlı fərqli KODlu 7 cüt fənn var; açar `fenn_kodu`-ya keçirildi, ölçülmüş zərər 0 (§0.000.b) |
| «Sətir sayı dəyişmir (70 255)» | **baş siyahı üçün DOĞRU deyildi** | 50 992 → 50 188 sətir, 269 480 → 269 257 hadisə; 3-cü nüsxənin baş siyahısı köhnə qalmışdı və 223 hadisəni artıq sayırdı (§0.000.c) |
| «Fərq» sütunu çox dolu namizəd olanda | **3 sətirdə rəqəm ixtiyari seçimdən gəlirdi** | İndi belə hallarda xana boş qalır və səbəb yazılır (§0.000) |
| Baş siyahının ad/müəllim/jurnal sütunları | **yığılan sətirlərdən birinin dəyəridir** | 16 981 sətir birdən çox mənbə sətrini yığır; sayılan göstəricilər (hadisə, şiddət, kateqoriya) hamısından hesablanır, **mətn sütunları isə nümayəndə sətirdəndir** — tam bölgü `bal_problemleri/K*.tsv`-dədir |
| «Boş qalan yeganə 987 sətir K8-dir» | **1 974** | K8-in 987 sətri + baş siyahıda 987 güzgüsü (§0.00) |
| K13-də 152 sətir «bu fənndə HEÇ BİR yazılış yoxdur 🔴» | **YALAN — yazılış konsolidasiya olunmuş fənn kodu altında VAR** | Fənn `MYEDU-L{dərs id}` konvensiyasından qurulurdu; 20 köhnə dərs hədəfdə tək fənnə birləşdirilib (§0.00) |
| «Fənn kodu» sütunundakı 12 380 dəyər | **354-ü hədəfdə mövcud DEYİLDİ, 12 026-sı köhnə sistemin kodu idi** | İndi hər kod `registrar_subject` ilə yoxlanılır — fantom 0 (§0.00.b) |
| «216 sətirdə mənbədə nə jurnal, nə semestr var» | **26 sətirdə SƏBƏB yanlış idi** | O 26 sətir `journals_dates_points`-dəndir və `journal_uniqid` VAR; hökm doğru, izah yanlış idi (§0.0) |
| K13-in arxiv sətirləri müstəqil problem | **138-i canlı sətrin eyni nüsxəsi** | Mənbədə `id` üzrə təsdiqləndi; bütün arxiv cədvəlləri süzüldü (§0.0b) |
| Toqquşmanın hamısı «bal itdi» | **492 itki · 128 qazanc · 974 bal itkisi olmayan** | İstiqamət hər sətirdə hesablandı (§0.2) |
| K3-də rəqəmli itki **571** | **315** | 256 sətirdə bal hədəfdə saxlanılıb (§0.3) |
| K5 + K13 cəmi | **920 dublikat çıxarıldı** | Dəqiq açar: köhnə `yekun.id` (§0.4) |
| Toqquşmada itən fərqli dəyər **1 653** | **1 594** | 1 653 əvvəlki RUN2 sıra seçimindən gəlirdi |
| ÜOMG hesablanmır: **231** tələbə | **987** | 626 (yazılışı var, qiyməti yox) + 361 (yazılışı yoxdur) |
| Qrup uyğunsuzluğu ~**1 190** tələbə | **1 440** | 3 862 yazılış · 1 440 fərqli tələbə |
| Bərpada toqquşan **2 972** xana | **2 885 toqquşma + 87 mənbə təqvim səhvi** | Ondan yalnız **173**-ü fərqli dəyərlə toqquşur |
| Yazılış ötürülmə səbəbi «əsasən aktiv deyil (5 hadisə)» | **yanlış idi** | Doğru bölgü §0.5-də |

**Sıra tələsi.** Toqquşmada «hansı dəyər qalır» sualında köçürmə axınının
modeli hədəfin **faktiki** qalibi ilə 621 təqvim · 103 komponent · 13 imtahan
sətrində üst-üstə düşmür. Ona görə bu siyahılar model proqnozundan yox,
**yeni bazadan oxunan faktiki dəyərdən** qurulub.

**Dördüncü kateqoriya axtarışı.** Yazılmış 4 368 694 xananın hamısı dəyər
səviyyəsində süpürüldü: **izahsız dəyər sürüşməsi = 0**.

**İxtiyari seçim axtarışı (5-ci nüsxə).** Sənədin **hər qəti hökmü** — 12 464
sətir, nümunə seçmədən — canlı bazadan yenidən quruldu və iki sual verildi:
hökm yalandırmı, və hökm namizədlər arasında fikir ayrılığı olanda bunu
gizlədirmi. Nəticə: **səhv qəti hökm = 0 · ixtiyari seçimdən doğan hökm = 0**
(`adv2/sweep2.py`).

**Nə HƏLƏ DƏ bilinmir.** 227 sətirdə hökm verilmir (§K13) və 548 sətirdə köhnə
tələbə id-si avtoritetli xəritədə ümumiyyətlə yoxdur — bunlar «problem yoxdur»
demək **deyil**, «bu data ilə cavab verilə bilməz» deməkdir və elə də
işarələnib.

---

## 6. Təklif olunan iş ardıcıllığı

1. **Toqquşmada tələbənin İTİRDİYİ 492 sətir** — «İstiqamət» sütununda
   «Tələbə İTİRİB» ilə süzün. Kağız imtahan protokolu ilə tutuşdurun.
   Ən yüksək təsirli və ən kiçik siyahıdır.
2. **K11-in 🔴 hissəsi (233 sətir)** və **K13-ün 288 sətri**
   (eyni fənndə yazılış var, bal fərqlidir — 5-ci nüsxədə 121-dən 288-ə qalxdı,
   §0.000).
3. **J12 bərpasını canlı bazaya tətbiq edin** — 10 769 sətir (K10 + K10b) əl işi
   olmadan bağlanır; sonra yalnız **173** toqquşmaya baxılır.
4. **K13-ün 6 513 imtahan-buraxılış sətri** — real bal daşıyır və heç bir ekranda
   görünmür; bağlanma qaydası texniki qərardır, universitet yoxlaması tələb etmir.
5. **K4 / K9-un bal daşıyan 6 219 sətri** (K4 2 787 + K9 3 432) — yazılışı bərpa
   edin, bal xanaları özü qayıdır.
6. **K7 (6 188) və K8 (987)** — köhnə sistemin boşluğudur; universitetin
   akademik qərarı lazımdır.
6b. **Köçməmiş 100 hesabın (84 `skipped` + 16 `quarantined`) bərpası** —
   tək bu addım K13-də **2 568 sətri** (82,4 % «hesab köçməyib» sətri)
   fərdi araşdırma olmadan yenidən qiymətləndirilə bilən hala gətirir.
7. **K12-nin 13 206 düstur sətri** — heç nə etmək lazım deyil
   (`GIRIS_DUSTUR_QERARI.md`).
8. **«Tələbəyə zərəri yoxdur» 384 sətir** — heç bir iş tələb etmir, yalnız
   arxiv qeydi üçün saxlanılıb.
