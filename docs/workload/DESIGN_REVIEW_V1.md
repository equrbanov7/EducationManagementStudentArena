# Dərs yükü dizaynı — v1 təhlili (Claude Design, 6 səhifə)

> **Mənbə:** `Dərs yükü mərkəzi dizayn` layihəsi — 6 `.dc.html` səhifə (01 Tədris şöbəsi,
> 02 Koordinator, 03 Kafedra müdiri, 04 Dekanlıq, 05 Müəllim, 06 Rektor).
> **Metod:** hər səhifənin həm markup-u, həm DCLogic məntiqi və nümunə datası oxunub;
> rəqəmlər əl ilə yenidən hesablanıb. Əlavə olaraq real «Tapşırıq» Excel-inin 855 sətri
> üzərində saat düsturları yoxlanılıb.
> **Yekun:** 66 qayda pozuntusu, 91 funksional boşluq, 91 domen/hesablama problemi, 68 ölü kod nöqtəsi.

---

## 1. Ümumi qiymət

**Vizual dil ~90% bizimdir.** Palitra (#2563eb, #eff6ff, #e2e8f0, slate mətnlər), kart
radiusları, çip/badge dili, modal quruluşu — hamısı `--ems-*` tokenlərinə demək olar ki
birbaşa oturur. Rəng seçimi mübahisə mövzusu deyil, yalnız **tokenləşdirmə** işi qalır.

**İnformasiya memarlığı güclüdür.** 22 sütunlu tapşırıq cədvəli, iki səviyyəli başlıq,
üç qatlı sticky, canlı yekun zolağı, göndərmədən əvvəl yoxlama modalı — bunlar Excel-ə
alışmış istifadəçini itirmədən elektron formaya keçirən düzgün həllərdir.

**Zəiflik məntiqdədir, görünüşdə deyil.** Demək olar hər ekranda göstəricilər datadan
hesablanmır — markup-a hərfi yazılıb; nəticədə eyni səhifənin iki yerində iki fərqli
həqiqət görünür. Bir neçə yerdə isə domen qaydası özü səhv tətbiq olunub (aşağıda §4).

**Bir cümlə ilə:** dizaynı əsas kimi götürmək olar, amma **hesablama qatını sıfırdan
yazmaq lazımdır** — mockup-dakı rəqəmlərin heç birinə güvənmək olmaz.

---

## 2. Saxlanmalı güclü tərəflər

| # | Nə | Harada |
|---|---|---|
| 1 | **Kredit çipi** — mavi konturlu, qalın rəqəm + kiçik «kr». Cədvəldə, kafedra kartında, kataloq açılanında, import cədvəlində, dilim siyahısında — hər yerdə eyni | 01 (7 yerdə), 02, 03, 04 |
| 2 | **İki səviyyəli cədvəl başlığı** — Mühazirə/Seminar/Lab üçün `colspan=2`, altında «plan \| cəmi»; plan boz, cəmi qara-qalın | 01 |
| 3 | **Üç qatlı sticky** — sticky başlıq (2 sətir) + sticky ilk sütun + tbody sonunda «səhifə cəmi» + kartın dibində sənəd yekunu | 01 |
| 4 | **Modalda canlı sətir cəmi** — istifadəçi saatı yazarkən nəticəni dərhal görür | 01 |
| 5 | **plan → cəmi avto-hesablama, əl ilə override imkanı ilə** | 01 |
| 6 | **Kataloq-öncəlikli fənn seçici + «Kataloqda yoxdur» qaçış yolu** (sarı xəbərdarlıqla) | 01 |
| 7 | **Göndərmədən əvvəl yoxlama modalı** — xəbərdarlıqlar + hansı fakültəyə nə qədər saat/kredit/sətir gedəcək. Rəqəmlər tam bağlanır: 6 120+1 845+1 000 = 8 965 | 01 |
| 8 | **Import sehrbazının dürüstlüyü** — uyğunlaşmayan sətirləri gizlətmir, «mətn kimi qalacaq» statusu verir və 3-cü addımda təkrar xatırladır | 01 |
| 9 | **Qaytarılan sətrin 3 yerdə görünməsi** — sətir fonu, fənn altında qırmızı qeyd, ayrıca panel + dekan sitatı + «Redaktora keç» | 01 |
| 10 | **Passiv düymə vəziyyətləri** — səbəb yazılmayınca «İrad göndər»/«Qaytar» aktivləşmir | 02, 04 |
| 11 | **Zəncir timeline-ı** — TŞ → koordinator → dekanlıq → kafedra → müəllim; «mən haradayam» sualına cavab verir | 04, 05, 06 |
| 12 | **Müəllim etiraz axını** — modal → validasiya → siyahının başına «Baxılır» kartı → bildirişə keçid → toast | 05 |
| 13 | **Çəki ilə faiz hesablanması** — `Σ(saat×faiz)/Σsaat`, faizlərin sadə ortalaması yox. Metodoloji cəhətdən düzgündür, backend-ə eyni formada köçürülməlidir | 06 |
| 14 | **Vahid status/rəng lüğəti** — `stOf()`/`barOf()` bütün cədvəl və modallara eyni astanaları verir | 06 |
| 15 | **Kontekstli naviqasiya** — risk kartından kafedra görünüşünə keçəndə fakültə filtri öncədən qurulur | 06 |
| 16 | **Arxiv rejimi konsepti** — keçmiş il seçiləndə sarı banner + sidebar rəng dəyişimi | 01, 02, 03, 04 |

---

## 3. Sistematik qayda pozuntuları (6 səhifənin HAMISINDA təkrarlanır)

Bunlar bir dəfə düzəldilib ortaq layout-a çıxarılmalıdır:

| # | Pozuntu | Düzəliş |
|---|---|---|
| 1 | **Sidebar 300px** | 248px; nav padding-lərini uyğun azalt |
| 2 | **«Menyunu yığ» düyməsi** (heç bir state-ə bağlı deyil, ölü) | Tamamilə sil — sidebar daim görünür |
| 3 | **Aktiv nav = dolu mavi (#3b82f6) + ağ mətn + kölgə** | `background:#eff6ff; color:#1d4ed8; box-shadow:inset 3px 0 0 #2563eb`, kölgəni sil |
| 4 | **Filtrlər «Bax»/«Göstər» düyməsi tələb edir + native `<select>`** | Debounce-lu ani filtr + `EMSSearchableSelect` (axtarışlı, lazy, kaskad) |
| 5 | **Skeleton / yüklənmə / xəta vəziyyəti heç bir yerdə yoxdur** | Hər cədvələ 3 vəziyyət: skeleton, boş (ikon + «filtri sıfırla»), xəta («yenidən cəhd et») |
| 6 | **Sıfır CSS custom property** — tək 01-də ~600 inline `style` atributu | `:root{--ems-*}` + xarici CSS (CSP onsuz da inline-a icazə vermir) |

Səhifə-səhifə əlavələr:

- **Cədvəl başlığı** `#f8fafc` + boz mətn verilib (03, 05, 06) — bizdə `#eff6ff` + `#1e40af`.
- **Sticky ilk sütun yoxdur** geniş cədvəllərdə (02, 03, 05, 06) — yalnız 01-də var.
- **Sətir hover yoxdur** (02, 03, 06).
- **Palitradan kənar rənglər:** `#3b82f6` (aktiv nav, fokus), `#10b981` (badge), `#0f172a`
  kart fonu (06), hesabat ikonlarında bənövşəyi/narıncı palitra (06).
- **Tünd kart fonu** (06 — «Ümumi tədris yükü» kartı və hesabat banneri) — tətbiq yalnız işıqlıdır.
- **Media query yoxdur** — bütün grid-lər sabit 3-4 sütun, ~1200px-dən aşağıda dağılır.
- **Əlçatanlıq:** modallarda `role="dialog"`/`aria-modal`/focus-trap yoxdur; `<label>`-lər
  `for/id` ilə bağlanmayıb; klik olunan `<tr>`-lər klaviatura ilə əlçatan deyil.
- **Orfoqrafiya:** «Şəxsi yükum» → «Şəxsi yüküm» (05).

---

## 4. Domen və hesablama səhvləri (ən vacib bölmə)

### 4.1 ⚠️ Kreditlərin cəmlənməsi — kök səhv

Sən kreditlərin vacibliyini xüsusi vurğulamışdın; dizayn krediti **göstərməkdə** əla, amma
**cəmləməkdə** səhvdir:

- **01-də** sətir kreditləri sadəcə toplanır: 5+4+6+4+4+3+5+4 = 35. Amma «Veb texnologiyalar»
  (4 kr) iki ayrı sətirdə (235 İT və 236 İ) tədris olunduğu üçün krediti **iki dəfə** sayılıb.
  Təkrarsız düzgün rəqəm **31**-dir. Eyni səhv «CƏMİ KREDİT 142» və dilim üzrə 98/28/16
  rəqəmlərində də var.
- **03-də** kredit çipi hər **fəaliyyət** sətrində təkrarlanır — R. Həsənov üçün «Veb
  texnologiyalar 4 kr» üç dəfə görünür; cəm əlavə edilsə 12 kr çıxacaq.
- **05-də** eyni tələ hazır vəziyyətdədir (2 qrupu bir sətirdə saxlayan sətirlər).
- **06-da** kredit ümumiyyətlə yoxdur.

**Qayda:** kredit tədris sətrinin yox, **fənn-tələbə cütünün** atributudur. Aqreqat ya
«təkrarsız fənn krediti», ya da açıq adlandırılmış ayrı metrik olmalıdır («kredit-qrup»).
Semestr üzrə ~30 AKTS yoxlaması yalnız təkrarsız hesabla mənalıdır.

**Əlavə kəşf (Excel-dən):** eyni fənnin krediti **ixtisasa görə dəyişir** — 421 unikal fənn
adından **35-i** fərqli ixtisaslarda fərqli kredit daşıyır (məs. «Proqramlaşdırmanın
əsasları»: Komp.müh 8 kr, İnform.təh 6 kr, Mexatronika 7 kr; «Ümumi ekologiya»: Ekolog.müh
7 kr, Ekologiya 5 kr). Deməli **kredit `Subject.ects`-də deyil, tədris planı sətrində
(`CurriculumSubject`) saxlanmalıdır** — bu, mövcud modelin düzəliş tələb edən yeridir.

### 4.2 ⚠️ «Cəmi = plan × qrup sayı» izahı yanlışdır

Real Excel-in **855 sətri** üzərində yoxladım — düstur belədir:

| Fəaliyyət | Düstur | Uyğunluq |
|---|---|---|
| Mühazirə cəmi | plan × **birləşmə sayı** (axın) | **770/770 = 100%** |
| Seminar cəmi | plan × **qrup/yarımqrup sayı** | 724/730 = 99.2% |
| Laboratoriya cəmi | plan × qrup/yarımqrup sayı | 74/75 = 98.7% |
| Sətir CƏMİ | bütün «cəmi» sütunlarının cəmi | **855/855 = 100%** |

Yəni **qrup sayı heç bir düsturda birbaşa iştirak etmir** — mühazirə axın sayına, seminar/lab
yarımqrup sayına vurulur. Dizaynın öz kodu bunu düzgün edir, amma **izah mətni səhvdir**:
modalda və yoxlama modalında «plan × qrup sayına görə hesablanır» yazılıb (01). Terminologiya
düzəldilməlidir.

Daha ciddisi — **02, 03 və 05-də çarpan ümumiyyətlə tətbiq olunmayıb**:
- 05-də CS-3021 (2 qrup) üçün seminar/lab 2×30=60 olmalı ikən 30 yazılıb; CS-3110 və
  CS-2208-də lab 120 olmalı ikən 60. **Düzəldilsə illik yük 780 yox, 960 saat olur** — və
  səhifədəki bütün 700 saat norma / 80 saat saathesabı / 1 000 ₼ hekayəsi dağılır.
- Bu səhv datanın içində «sənədləşib» də: 05-in etiraz nümunəsi məhz «laboratoriya saatı
  ikiqat artmadı» deyir və statusu «Cavablandırıldı»dır — yəni mockup öz məntiq səhvini
  həll olunmuş problem kimi təqdim edir.

**Bonus:** 855 sətirdə cəmi **7 uyğunsuzluq** tapdım (məs. «Ümumi kimya»: G=2, plan=15,
amma cəmi 45 yazılıb). Bunlar real Excel-dəki insan səhvləridir — sistem onları **avtomatik
tutacaq**. Bu, modulun konkret və ölçülə bilən faydasıdır.

### 4.3 Rəhbərlik saatları fənn sətrinə yapışdırılıb

01 və 02-də «Şəbəkələrin təhlükəsizliyi» sətri buraxılış (40) və doktorant (30) rəhbərliyi
saatlarını daşıyır və bu 70 saat fənnin 165 saatlıq cəmisinə daxildir, krediti də 5 görünür.
Rəhbərlik yükü **müəllim-tələbə cütünə** aiddir, fənn-təklifinə yox — kafedra bölgüsündə
ikiqat sayılma riski yaradır. Üstəlik həmin sətir **magistr**dir: magistrdə «buraxılış işi»
deyil, **dissertasiya** olur. Rəhbərlik ayrıca sətir tipi olmalıdır (fənnsiz, kreditsiz,
tələbə sayına bağlı).

### 4.4 Göstəricilər datadan hesablanmır

Demək olar hər stat kart hərfi rəqəmdir:

- **01:** kartlar «12 kafedra / 4 göndərilmiş / 3 təsdiqlənmiş / 1 qaytarılmış» deyir,
  data massivində isə 8 kafedra var (3 qaralama, 2 göndərilib, 2 təsdiqlənib, 1 qaytarılıb).
  Eyni panelin iki yerində iki fərqli həqiqət.
- **01:** «SƏHİFƏ CƏMİ» sətri 1 073 yazır, 8 sətrin faktiki cəmi 1 051-dir.
- **02:** progress məxrəci sabit 28-dir və `17 + reviewedCount` sehrli offset-i ilə hesablanır,
  cədvəldə isə 7 sətir var — «Nəticə: 7 sətir» ilə «28 sətirdən 20-i baxılıb» yan-yana durur.
- **05:** semestr kartı (402/378 və 51.5%/48.5%) markup-da sabitdir — «Yaz» filtri seçiləndə
  belə 402 payız göstərir. Fərdi plan başlığındakı 1 160 / 607 / 52% də sabitdir.
- **06:** «5 fakültə · 16 kafedra · 252 müəllim», tfoot-dakı «16» və «252», sidebar «5»
  nişanı — hamısı hərfi, halbuki hamısı `DEPS`-dən hesablana bilər.

### 4.5 Vəziyyət maşını ziddiyyətləri

- **01:** sənəd eyni anda həm «QARALAMA» çipi daşıyır və «Dekanlıqlara göndər» düyməsi
  göstərir, həm də İzləmə tabında «04.08.2026-da göndərilib» yazır və dekan qərarları görünür.
- **02 (ən təhlükəli):** «Hamısına viza ver» **aktiv filtrə məhəl qoymur** — istifadəçi
  «236 KE ing» filtrləyib 2 sətir görəndə düyməyə basırsa, **görmədiyi bütün 28 sətrə** viza
  verilir. Təsdiq dialoqu və geri-alma yoxdur.
- **02:** irad bildirmək progress-i **azaldır** (irad viza bayrağını silir), halbuki irad da
  tamamlanmış qərardır. «Gözləyir» sayğacı **mənfi** ola bilir (−1). Eyni sətir eyni anda həm
  «Vizalı» düyməsi, həm sarı «İradlı» fonu göstərə bilir.
- **03:** «Bölgünü TƏSDİQLƏ» **heç vaxt aktivləşə bilmir** — qapı `bölünmüş ≥ 8 965` tələb
  edir, mövcud 7 830 + görünən bütün qalıq (260) = 8 090. Təsdiq modalı və ona bağlı
  «Hesabatlar» görünüşü prototipdə əlçatmazdır.
- **03:** vakant saatlar **eyni anda həm «bölünüb», həm «vakant»** sayılır; üstəlik vakant
  cəminə izahsız `+120` sabiti əlavə olunub — istifadəçi bu 120 saatı heç bir ekranda tapa bilmir.

### 4.6 Qrup filtri substring müqayisəsi edir

01 və 02-də `groups.indexOf(filter) >= 0` işlədilir → **«236 KE» filtri «236 KE ing» qrupunu
da tutur**. AZ/EN sektor ayrımı olan bütün qruplarda sistematik səhvdir. Səbəb: qruplar
massiv yox, birləşdirilmiş mətn kimi saxlanılır («036 / 336 F»). Dil sektoru da qrup **adına
yedirilib**, halbuki bizdə qrup ayrıca OrgUnit-dir.

### 4.7 Rektor səhifəsinin aqreqasiya problemləri (06)

- **Bölünmüş saat faizdən törədilir** (`dist = hours × pct/100`) — domen axını tərsinədir və
  kəsr saatlar yaradır (31 028,8 saat). Nəticədə sütun cəmi 102 359, tfoot isə 102 358 göstərir.
- **«Vakant» ilə «bölünməmiş» qarışdırılıb:** ümumi 114 900, bölünmüş 102 358 → qalıq 12 542,
  amma vakant kimi yalnız 2 750 göstərilir. **9 792 saat adsız qalır.**
- **Funnel mətni data ilə ziddiyyətdədir:** «11 kafedra tamamlayıb» yazır, `DEPS`-də isə
  yalnız 3 kafedra 100%-dədir.
- **«Tamamlandı» statusu norma aşımını gizlədir:** 100% bölünmüş, amma 410 saat norma üstü
  olan kafedra yaşıl görünür.
- **Siyasi ziddiyyət bağlanmır:** eyni ekranda 34 müəllim normadan az yüklüdür, 3 630 saat
  norma üstü verilib və 14 yeni ştat təklif olunur. Rektorun ilk sualı — «niyə 34 az yüklü
  müəllim varkən ştat açırıq?» — cavabsız qalır.
- **«14 vakant ştat»** əslində ştat deyil: 2 750/14 = 196 saat/ştat, yəni saathesabı əvəzləmədir.

### 4.8 Norma nərdivanı məntiqsizdir (03)

Dosent 500, baş müəllim 550, müəllim 600, **assistent 0.5 ştat → 250 (tam ştatda 500)** —
yəni assistentin tam norması dosentlə eynidir və müəllimdən aşağıdır. Real praktikada aşağı
vəzifədə tədris norması **daha yüksək** olur. Rəqəmlər hər halda universitet-konfiqurasiyalı
olmalıdır (rəsmi differensiasiya dövlət səviyyəsində yoxdur — bax spec §8).

### 4.9 ⚠️ Koordinatorun əsas işi ekranda mümkün deyil (02)

Bu, ən çox məlumat verən tapıntıdır. Koordinatorun nümunə iradı belədir:

> «Laboratoriya saatı **ixtisas planındakı 30 saatdan** çoxdur»

Amma ekranda **tədris planının norması göstərilən sütun yoxdur** — koordinator müqayisə edə
bilmədiyi bir şeyə istinad edir. Üstəlik nümunə data iddianı təkzib edir (həmin sətirdə lab
cəmi tam 30-dur, çox deyil).

Eyni problem 02-nin başqa tapıntılarında da görünür: kredit ↔ saat nisbəti sətirdən sətrə
uyğunsuzdur (5 kr → 60 saat, 4 kr → 75 saat, 6 kr → 75 saat), çarpan (birləşmə/yarımqrup)
UI-da izah olunmur, semestr üzrə kredit yekunu yoxdur.

**Nəticə:** koordinator/dekan ekranı **tədris planı ilə yan-yana müqayisə** olmadan mənasızdır.
Bu, birbaşa növbəti bölməyə aparır.

---

## 5. Ölü kod = unudulmuş ekran hissələri

DCLogic-də hesablanıb markup-da işlədilməyən 68 dəyər tapıldı. Bunların çoxu «dizaynerin
nəzərdə tutub çəkmədiyi» ekranlardır — icra zamanı ya tamamlanmalı, ya silinməlidir:

- **06:** `depList`/`risky` indeks saxlayır, amma kafedra sətrinin heç bir drill-down-u yoxdur;
  `DEPS[].over` (3 630 saat norma üstü) heç bir aqreqata düşmür; `decisions` massivi render
  olunur, «Bax» düyməsinin handler-i yoxdur; `s.modal` çoxmodallı dizayn edilib, ikinci modal
  yazılmayıb.
- **05:** etiraz modalında «səbəb» sahəsi yığılır, obyektə yazılmır; `sum()` funksiyası var,
  amma kartlar hardcoded; bildirişlərdə per-item `read` sahəsi yoxdur.
- **01:** «əl ilə dəyişdirilib» xəbərdarlığı üçün `manualOverride` bayrağı modeldə yoxdur —
  yəni xəbərdarlıq texniki olaraq mümkün deyil.
- **02/03/06:** tədris ili və semestr filtrləri **inert**dir — state dəyişir, heç bir
  hesablamaya təsir etmir; il dəyişəndə səhifə köhnə datanı «arxiv» bayrağı altında göstərir.
- **Bütün səhifələr:** «Menyunu yığ» və ikinci «Çıxış» düymələri handler-sizdir.

---

## 6. Çatışmayan funksionallıq (icra planına düşməli)

**Hər səhifədə:** səhifələmə, sütun üzrə sıralama, axtarış, deadline/son tarix göstəricisi,
xəta vəziyyəti, toplu əməliyyat, audit tarixçəsi (kim/nə vaxt/nə), geri-alma.

**Səhifəyə xas:**
- **01:** kafedra kartına klik kontekst ötürmür (həmişə eyni statik sənəd açılır); arxiv
  rejimi yalnız bannerdir — bütün düymələr aktiv qalır; import nəticəsi mövcud sənədlə
  uzlaşdırılmır (əlavə/əvəz/birləşdir seçimi yoxdur); xəbərdarlıqlardan aid sətirlərə keçid yoxdur.
- **02:** təqdimdən sonra növbə kilidlənmir; «Baxdım» təsdiqsiz geri-toggle edir (audit izi yox).
- **03:** fəaliyyət taksonomiyası yarımçıqdır — yalnız mühazirə/seminar/lab bölünə bilir;
  məsləhət, imtahan, buraxılış, doktorant, təcrübə saatları bu ekranda **ümumiyyətlə
  bölünmür**; kəsr saat `parseInt` ilə səssizcə kəsilir; dublikat bölgü yoxlaması yoxdur.
- **04:** növbə siyahısı yoxdur — birbaşa bir kafedranın diliminə düşürsən, hansı dilimlərin
  gözlədiyi görünmür (sidebar-da «3» nişanı var, siyahısı yox).
- **05:** «Dəyişdirilib» statusu var, amma **nəyin** dəyişdiyini göstərən diff yoxdur — müəllimin
  əsas sualı cavabsızdır; şəxsi yükün Excel/PDF ixracı yoxdur (yalnız fərdi planda var);
  təsdiq geri qaytarıla bilmir və son tarix göstərilmir.
- **06:** rektorun **təsdiq əməliyyatı yoxdur** — funnel «Rektor təsdiqi — GÖZLƏYİR» yazır,
  düymə yoxdur; bütün ixrac düymələri ölüdür; illər arası müqayisə yoxdur.

---

## 7. Nə etməli — prioritetli düzəliş siyahısı

**P0 — icradan əvvəl həll olunmalı (domen):**
1. Kredit aqreqasiyası qaydası: təkrarsız fənn krediti + kredit `CurriculumSubject`-ə keçir.
2. Saat düsturunun terminologiyası: mühazirə = plan × **birləşmə**, seminar/lab = plan ×
   **yarımqrup**; UI-da çarpan görünsün.
3. Rəhbərlik saatları ayrıca sətir tipinə çıxsın (fənnsiz, kreditsiz).
4. «Vakant» ≠ «bölünməmiş» — iki ayrı göstərici.
5. Bütün göstəricilər datadan hesablansın; markup-da hərfi rəqəm qalmasın.
6. Qruplar massiv kimi saxlanılsın (substring filtri aradan qalxsın), dil sektoru ayrıca ölçü olsun.

**P1 — ortaq layout işi (bir dəfə):**
7. Sidebar 248px + collapse silinsin + aktiv bənd primary-50 & 3px zolaq.
8. Filtrlər ani + axtarışlı select-lərə keçsin.
9. Skeleton/boş/xəta vəziyyətləri əlavə olunsun.
10. Tokenləşdirmə + xarici CSS/JS (CSP).
11. Modal a11y (role/aria/focus-trap) + label bağlantıları + klaviatura ilə əlçatan sətirlər.

**P2 — funksional tamamlama:**
12. Səhifələmə, sıralama, axtarış, deadline, audit tarixçəsi — hər ekranda.
13. 03-də bütün fəaliyyət növləri bölünə bilsin; təsdiq qapısı vakantla keçidə icazə versin.
14. 04-ə dilim növbəsi siyahısı; 06-ya rektor təsdiqi; 05-ə diff və ixrac.
15. Ölü kod nöqtələri ya tamamlansın, ya silinsin.

**P3 — yeni mərhələ:**
16. **Tədris planı modulu** — koordinator/dekan ekranının müqayisə bazası (aşağıda).
