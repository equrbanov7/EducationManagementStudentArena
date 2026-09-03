# Claude Design — v3 promptu (Tədris Şöbəsi + Tələbə Mərkəzi kabinetləri)

> Bu faylın «────» xəttindən sonrakı hissəsini olduğu kimi Claude Design-a ver.
> Kontekst: v1-də 6 ekran (Dekanlıq/Koordinator/Kafedra/Tədris/Müəllim/Rektor),
> v2-də tədris planı + illik işçi plan hazırlandı. V3 iki YENİ kabinet açır.
> Mənbə qərarlar: `docs/architecture/AKADEMIK_OS_ANALIZI.md`.

────────────────────────────────────────────────────────────────────────

Sən EMSArena universitet sisteminin dizaynını **v3-ə** çıxarırsan. Bu dəfə iki yeni
kabinet var: **Tədris Şöbəsi** və **Tələbə Mərkəzi**. Hər ikisi mövcud dərs yükü
ekranları ilə eyni dizayn dilini davam etdirir.

## 0. Qabıq və dizayn sistemi — v2 qaydaları tam qüvvədədir

**Topbar və sol sidebar-ı ÇƏKMƏ.** Yalnız məzmun sahəsi:

```html
<div style="max-width:1180px; padding:24px 28px 40px">
  <!-- başlıq bloku, filtrlər, kartlar, cədvəllər, modallar -->
</div>
```

Rəngləri token kimi elan et və hər yerdə `var(--ems-*)` işlət:

```css
:root{
  --ems-primary-50:#eff6ff;  --ems-primary-100:#dbeafe; --ems-primary-200:#bfdbfe;
  --ems-primary-600:#2563eb; --ems-primary-700:#1d4ed8; --ems-primary-800:#1e40af;
  --ems-neutral-0:#ffffff; --ems-neutral-50:#f8fafc; --ems-neutral-100:#f1f5f9;
  --ems-neutral-200:#e2e8f0; --ems-neutral-300:#cbd5e1; --ems-neutral-400:#94a3b8;
  --ems-neutral-500:#64748b; --ems-neutral-700:#334155; --ems-neutral-900:#0f172a;
  --ems-success:#16a34a; --ems-success-bg:#dcfce7;
  --ems-danger:#dc2626;  --ems-danger-bg:#fee2e2;
  --ems-warning:#f59e0b; --ems-warning-bg:#fef3c7;
}
```

Dəyişməz qaydalar:

- **Tətbiq yalnız işıqlıdır** — `prefers-color-scheme: dark` işlətmə, tünd fonlu kart yoxdur,
  palitradan kənar rəng yoxdur.
- **Cədvəl:** başlıq `--ems-primary-50` fon + `--ems-primary-800` uppercase mətn; zebra sətir;
  hover `--ems-primary-50`; geniş cədvəldə ilk sütun sticky; konteyner daxilində üfüqi scroll.
- **Stat kart:** ağ fon, 4px rəngli sol border, böyük qalın rəqəm, kiçik UPPERCASE boz etiket.
- **Filtrlər:** «Bax»/«Tətbiq et» düyməsi YOXDUR — dəyişiklik 300ms debounce ilə dərhal tətbiq
  olunur. Açılanlar axtarış sahəli xüsusi komponentdir (native `<select>` yox), çoxlu element
  olanda lazy + səhifələnmiş. Bütün input-ların hündürlüyü eynidir.
- **Hər siyahı üçün 3 vəziyyət:** skeleton (shimmer), boş vəziyyət (ikon + izah + «filtrləri
  sıfırla»), xəta («Məlumat yüklənmədi · Yenidən cəhd et»).
- **Bütün göstəricilər nümunə datadan hesablanır** — markup-a hərfi rəqəm yazma; filtr dəyişəndə
  stat kartlar da dəyişməlidir.
- **Əlçatanlıq:** modallarda `role="dialog"` + `aria-modal="true"` + Escape + focus-trap;
  `<label for>`; klik olunan sətirdə `tabindex="0"` + `role="button"`; ikon düymələrində `aria-label`.
- **Responsivlik:** `repeat(auto-fit, minmax(...))`; ~900px-də 2 sütun, ~640px-də 1 sütun.
- Azərbaycan dilində, self-contained HTML, xarici CDN yox, ikonlar inline SVG.

---

## 1. Bu v3-ün həll etdiyi problem

Hazırda akademik kataloq **tək düz səhifədir**: ixtisaslar, fənlər, tədris planları, fənn
açılışları, tələbə təyinatları — hamısı bir-birinin altına yığılmış panellərdir. İxtisasa
kliklədikdə **redaktə formu** açılır; ixtisasın *içini* (hansı fənlər, hansı plan versiyaları,
hansı qruplar) görmək üçün ayrıca tədris planına girmək lazımdır. Yəni:

> **İndi yalnız «içərisinə baxmaq» var — gəzmək, seçmək, müqayisə etmək yoxdur.**

V3 bunu **iyerarxik master-detail** modelinə çevirir və Tədris Şöbəsinə öz kabinetini verir.

---

## 2. Domen qaydaları — bu ekranların məntiq qatı

Bunlar dizayn tərcihi deyil, sistemin qanunudur. Hər ekranda tətbiq olunur.

### 2.1 ⭐ Fənn kataloqunda KREDİT və SAAT YOXDUR

Bu, v3-ün ən vacib qaydasıdır və hazırkı formda səhvdir (düzəldilir).

**Fənn** — kataloq qeydidir: kod, ad, təsvir, tədris edən kafedra. Vəssalam.
**Kredit və saat** fənnin yox, **tədris planı sətrinin** atributudur, çünki **hər ixtisasda
dəyişir**:

| Fənn | İxtisas | Kredit |
|---|---|---|
| Proqramlaşdırmanın əsasları | Kompüter mühəndisliyi | **8** |
| Proqramlaşdırmanın əsasları | İnformasiya təhlükəsizliyi | **6** |
| Proqramlaşdırmanın əsasları | Mexatronika | **7** |

Nəticələr:

- «Yeni fənn» modalında **kredit sahəsi olmamalıdır** (indi «ECTS krediti» var — çıxarılır).
- Fənn kataloqu cədvəlində **kredit/saat sütunu olmamalıdır**.
- Kredit yalnız **plan sətrində** yazılır və oradan oxunur.
- Fənn kataloqunda kreditin *görünə biləcəyi* yeganə yer: sətri açanda çıxan
  **«İxtisaslar üzrə kredit»** oxunaq alt-cədvəli (aşağıda, §4.3).

### 2.2 Fənn ≠ fənn açılışı ≠ müəllim təyinatı ≠ yük

Dörd ayrı obyektdir, dörd ayrı ekran sütunu:

- **Fənn** (kataloq) — universitetdə bir dəfə var.
- **Tədris planı sətri** — fənn + ixtisas + semestr + kredit + saat bölgüsü.
- **Fənn açılışı** — fənn × semestr × qrup; **elektron jurnal məhz budur**.
- **Müəllim təyinatı** — kimin tədris etdiyi; illik, dəyişə bilər.

«Yeni jurnal yarat» düyməsi **heç bir ekranda olmamalıdır** — jurnal müəllim təyinatından
avtomatik doğur.

### 2.3 Kredit necə cəmlənir

Kredit **fənnin yox, plan sətrinin** atributudur; eyni fənn 2 qrupa tədris olunanda saat 2 dəfə,
kredit 1 dəfə sayılır. Aqreqatda həmişə **«Cəmi kredit (təkrarsız fənn)»** yaz.

### 2.4 Saat düsturu

```
ümumi saat     = kredit × 30            (NK 348)
auditoriya     = ümumi − sərbəst iş
həftəlik       = auditoriya ÷ 15        (semestr 15 tədris həftəsidir)
mühazirə cəmi  = mühazirə plan × BİRLƏŞMƏ sayı
seminar cəmi   = seminar plan  × YARIMQRUP sayı
```

«Qrup sayı» ifadəsini işlətmə. Çarpanı görünən et: `15 × 3 = 45`.

### 2.5 Tədris planı versiyalıdır, qəbul ilinə bağlıdır

Bir ixtisasın eyni anda bir neçə qüvvədə planı olur — 2024, 2025, 2026 qəbulu ayrı-ayrı.
Plan dəyişəndə köhnə tələbənin planı **pozulmur**: yeni versiya yaranır. Ona görə ixtisas
ekranında plan həmişə **qəbul ili × versiya** cütü ilə göstərilir və status çipi daşıyır
(Qaralama · Kafedra baxışı · Fakültə şurası · Tədris şöbəsi · Təsdiqlənib · Arxiv).

### 2.6 Struktur iyerarxikdir

`Universitet → Fakültə → Kafedra → İxtisas → Qrup`. Hər istifadəçi yalnız öz qovşağının
alt-ağacını görür (dekan öz fakültəsini, kafedra müdiri öz kafedrasını). Tədris Şöbəsi
**bütün ağacı** görür — bu, onun rolunun mahiyyətidir.

### 2.7 Fənn ilə kafedra əlaqəsi

Hər fənnin **tədris edən kafedrası** var (xidməti fənlərdə bu, ixtisasın kafedrasından fərqlidir
— məsələn «Müasir İKT» fənnini İT kafedrası filologiya qruplarına tədris edir). Yükün hansı
kafedraya gedəcəyi məhz bu sahədən müəyyən olunur, ona görə **boş qala bilməz**.

---

## 3. EKRAN A — Tədris Şöbəsi: «İxtisaslar» (iyerarxik gəzinti)

Bu, v3-ün əsas ekranıdır. Məqsəd: Tədris Şöbəsi işçisi bütün universitetin akademik
strukturunu **gəzə**, ixtisasa girib içini görə bilsin.

### 3.1 Tərtibat — üç sütunlu master-detail

```
┌────────────────┬──────────────────────┬─────────────────────────────┐
│ STRUKTUR RAIL  │  İXTİSAS SİYAHISI    │  İXTİSAS DETALI             │
│ (240px)        │  (seçilmiş qovşağın) │  (qalan sahə)               │
│                │                      │                             │
│ 🔍 axtarış     │  kart / sətir siyahı │  breadcrumb                 │
│ ▾ Mühəndislik  │  ┌────────────────┐  │  H2 ixtisas adı + çiplər    │
│    Proqram...  │  │ Kompüter müh.  │  │  ─────────────────────────  │
│    İnform.təh. │  │ 050632 · Bak.  │  │  [Ümumi][Planlar][Fənnlər]  │
│ ▸ İqtisadiyyat │  │ 4 qrup · 128 t │  │  [Qruplar][Açılışlar]       │
│ ▸ Filologiya   │  └────────────────┘  │                             │
└────────────────┴──────────────────────┴─────────────────────────────┘
```

- **Sol rail** — fakültə → kafedra ağacı. Axtarış sahəsi ağacı filtrləyir. Hər qovşaqda
  ixtisas sayı rozetkası. Qovşaq seçiləndə orta sütun dəyişir.
- **Orta sütun** — seçilmiş qovşağın ixtisasları. **Klik → sağda detal açılır**, redaktə formu
  YOX. Redaktə ayrıca «✎» düyməsidir.
- **Sağ sütun** — ixtisas detalı, tablı.
- ~1100px-dən aşağıda: rail açılan panelə, üç sütun ardıcıl iki mərhələyə çevrilir
  (siyahı → detal, «‹ Geri» düyməsi ilə).
- Hər səviyyə **dərin-link olunmalıdır** (breadcrumb-dan geri qayıtmaq işləməlidir).

### 3.2 İxtisas kartı (orta sütun)

Ad · kod · pillə çipi (Bakalavr/Magistr) · təhsil forması (Əyani/Qiyabi) · qrup sayı ·
tələbə sayı · aktiv plan versiyası çipi. Planı olmayan ixtisas **sarı ⚠ «Plan yoxdur»** çipi
daşıyır — bu, Tədris Şöbəsinin ən vacib siqnalıdır.

Yuxarıda: axtarış + pillə filtri + forma filtri + «yalnız plansızlar» keçidi + sıralama.

### 3.3 İxtisas detalı — 5 tab

**Tab 1 · Ümumi.** Kod, tam ad, pillə, təhsil forması, tabe olduğu kafedra/fakültə, məzuniyyət
üçün ECTS (240/120), qayıb limiti %, aktiv/arxiv. Sağda kiçik stat sütunu: qrup sayı, tələbə
sayı, cari semestrdə açılmış fənn sayı, təyin olunmamış fənn sayı (qırmızı).

**Tab 2 · Tədris planları.** Qəbul ili üzrə sətirlər: `2026 · v2 · Təsdiqlənib · 240 kr · 62 sətir`.
Hər sətirdə status çipi, təsdiq tarixi, Elmi Şura protokolu, «Aç» / «Klonla» / «Versiya çıxar».
Eyni ildə birdən çox versiya varsa **qüvvədə olan** işarələnir, qalanları solğun.

**Tab 3 · Fənnlər** ← *bu, «içərisinə baxmaq» tələbinin əsl cavabıdır.*
Bu ixtisasda tədris olunan **bütün** fənlərin semestr üzrə qruplaşdırılmış siyahısı:

| Semestr | Şifr | Fənn | Blok | **Kredit** | Ümumi saat | Auditoriya | Müh/Sem/Lab | Tədris edən kafedra | Prerekvizit |
|---|---|---|---|---|---|---|---|---|---|

- Semestr başlıq sətri **aqreqat** göstərir (cəmi kredit / saat) və açıq mavi fondadır.
- Kredit burada **bu ixtisasa aid dəyərdir** — başqa ixtisasda başqa ola bilər (§2.1).
- Sətrə klik → yan panel: fənnin kataloq qeydi + digər ixtisaslarda krediti + açılışları.
- Filtr: semestr, blok (məcburi/ixtisas/seçmə/ümumi), tədris edən kafedra.

**Tab 4 · Qruplar.** Qəbul ili × qrup cədvəli: ad, dil sektoru (AZ/EN), tələbə sayı, kurs,
doluluq (15–30 normasına görə rəngli), «Jurnalları gör». 30-u aşan qrup ⚠ işarələnir.

**Tab 5 · Fənn açılışları (cari semestr).** Fənn · qrup · müəllim · jurnal statusu ·
dərs sayı · giriş balı orta. **Müəllimi olmayan açılış qırmızı** — «Kafedraya göndər» linki.

### 3.4 İcazələr bu ekranda

- Görmə: Tədris Şöbəsi (bütün ağac), Dekanlıq (öz fakültəsi), Kafedra müdiri (öz kafedrası).
- İxtisas yaratma/redaktə: Tədris Şöbəsi. Digərləri üçün «✎» düyməsi **görünmür** (passiv yox — yoxdur).
- Arxivə salma: təsdiq modalı + səbəb; planı olan ixtisas silinmir, yalnız arxivləşir.

---

## 4. EKRAN B — Tədris Şöbəsi: «Fənnlər» (qlobal kataloq)

Universitetdəki **bütün** fənlər burada görünür və yeni fənn buradan əlavə olunur.

### 4.1 Başlıq bloku

H1 «Fənn kataloqu» + alt mətn «Universitetdə tədris olunan bütün fənlər. Kredit və saat
fənnin deyil, tədris planının atributudur.» + sağda «＋ Yeni fənn».

Stat kartlar: cəmi fənn · aktiv · heç bir planda istifadə olunmayan (sarı) · kafedrası
təyin olunmamış (qırmızı) · xidməti fənn sayı.

### 4.2 Kataloq cədvəli — **kredit/saat sütunu YOXDUR**

| Kod | Fənn adı | Tədris edən kafedra | İstifadə | Semestrlər | Status |
|---|---|---|---|---|---|
| MİF-B04.01 | Proqramlaşdırmanın əsasları | Proqramlaşdırma və İT | **3 ixtisas** | 1, 2 | Aktiv |
| MİF-B02.07 | Müasir İKT | Proqramlaşdırma və İT | 7 ixtisas · xidməti | 1 | Aktiv |
| MİF-B09.12 | Kriptoqrafiya | İnformasiya təhlükəsizliyi | — | — | Aktiv ⚠ istifadəsiz |

Filtrlər: axtarış (kod + ad), tədris edən kafedra, «yalnız istifadəsizlər», «yalnız kafedrasızlar»,
status. Sütun üzrə sıralama, səhifələmə.

### 4.3 ⭐ Sətir açılışı — «İxtisaslar üzrə kredit»

Sətrə klikləyəndə **oxunaq (read-only)** alt-panel açılır — fənnin hər ixtisasda hansı kreditlə
getdiyini göstərir. Bu, §2.1 qaydasını istifadəçiyə *öyrədən* yerdir:

| İxtisas | Plan (qəbul ili · versiya) | Semestr | Kredit | Ümumi saat | Müh/Sem/Lab | → |
|---|---|---|---|---|---|---|
| Kompüter mühəndisliyi | 2026 · v2 | 1 | **8** | 240 | 30/30/— | Plan sətrini aç |
| İnformasiya təhlükəsizliyi | 2026 · v1 | 1 | **6** | 180 | 30/15/15 | Plan sətrini aç |
| Mexatronika | 2025 · v3 | 2 | **7** | 210 | 30/15/30 | Plan sətrini aç |

Panelin başında kiçik izah zolağı:
> «Kredit bu cədvəldə redaktə olunmur — o, tədris planı sətrinin atributudur. Dəyişmək üçün
> müvafiq planı açın.»

Altda: «Bu fənn üzrə cari semestr açılışları (4)» — qısa siyahı.

### 4.4 «Yeni fənn» modalı — sahələr dəqiq bunlardır

| Sahə | Tip | Qeyd |
|---|---|---|
| Fənn kodu | mətn, unikal | `MİF-B04.01`; unikallıq canlı yoxlanır |
| Fənnin adı | mətn | |
| Tədris edən kafedra | axtarışlı açılan | **məcburidir** — yük bu sahədən kafedraya gedir |
| Təsvir | textarea | opsional |
| Aktiv | keçid | default açıq |

**Modalda OLMAYACAQ sahələr — və bunu istifadəçiyə de:** kredit, ECTS, ümumi saat, dərs saatı,
mühazirə/seminar/laboratoriya bölgüsü, semestr, məcburi/seçmə. Modalın altında sabit izah bloku:

> ℹ️ **Kredit və saat burada yazılmır.** Eyni fənn müxtəlif ixtisaslarda fərqli kreditlə keçilir
> (məs. 8 / 6 / 7). Bu dəyərlər fənn ixtisasın tədris planına əlavə olunanda təyin edilir.

Modalda ikinci addım opsionaldır: «İndi bir tədris planına əlavə edim?» — ixtisas + plan versiyası
+ semestr + kredit seçimi ilə. Seçilsə, kredit **məhz orada** soruşulur.

### 4.5 Silinmə qaydası

Planda istifadə olunan fənn **silinmir** (`PROTECT`). Silmə düyməsi belə davranır: istifadə varsa
düymə «Arxivləşdir»ə çevrilir və izah verir — «3 tədris planında istifadə olunur, silinə bilməz».
İstifadəsiz fənn silinə bilər, təsdiq modalı ilə.

---

## 5. EKRAN C — Tədris Şöbəsi: giriş paneli (kabinetin ana səhifəsi)

Kabinetə girəndə görünən ilk ekran. Məqsəd: «bu gün nə etməliyəm».

**Sətir 1 — stat kartlar:** fakültə · ixtisas · fənn · aktiv tədris planı · cari semestrdə
açılmış fənn · təyinatsız açılış (qırmızı).

**Sətir 2 — «Gözləyən işlər» siyahısı** (bu, kabinetin əsl dəyəridir):

| Növ | Nə | Kim gözləyir | Son tarix | → |
|---|---|---|---|---|
| Tədris planı | İnformasiya təhlükəsizliyi 2026 · v1 | Tədris şöbəsi təsdiqi | 10 sent · **3 gün** | Aç |
| Dərs yükü | Mexatronika kafedrası tapşırığı | Tədris şöbəsi baxışı | 10 sent · **3 gün** | Aç |
| Struktur | 4 fənnin tədris edən kafedrası boşdur | — | — | Düzəlt |
| Açılış | 7 fənn açılışında müəllim yoxdur | Kafedra | 12 sent | Bax |

Son tarixlər **akademik təqvimdən** gəlir; 3 gündən az qalanda qırmızı geri sayım.

**Sətir 3 — akademik təqvim zolağı:** cari semestrin mərhələləri (qeydiyyat pəncərəsi, dərs
başlanğıcı, kollokvium pəncərəsi, sessiya) üfüqi zaman xətti üzərində, bugünkü mövqe işarəli.

**Sətir 4 — sürətli keçidlər:** İxtisaslar · Fənnlər · Tədris planları · İllik işçi plan ·
Dərs yükü · Fənn açılışları · Akademik təqvim.

---

## 6. EKRAN D — Tələbə Mərkəzi kabineti

Yeni qəbul olunan tələbənin sənədi bu kabinetdən keçir. Hazırda sistemdə belə bir kabinet yoxdur —
sıfırdan dizayn edirsən.

### 6.1 Başlıq + stat kartlar

Cari qəbul kampaniyası çipi («2026/2027 qəbulu · açıq»). Kartlar: ATİS-dən gələn · sənəd
gözləyən · yoxlanışda · çatışmazlıq (sarı) · təsdiqlənmiş · qeydiyyata salınmış · imtina.

### 6.2 Əsas cədvəl — qəbul növbəsi

| FİN | Ad Soyad | İxtisas | Pillə/Forma | Qəbul balı | Sənəd statusu | Çatışmazlıq | Mənbə | → |
|---|---|---|---|---|---|---|---|---|

Status çipləri **state machine-dir**, sırası sabitdir:

```
Qəbul edildi → Yoxlanılır → ┬→ Təsdiqləndi → Qeydiyyata salındı
                            ├→ Çatışmazlıq var ⟳ (Yoxlanılır-a qayıdır)
                            └→ İmtina edildi (səbəb məcburi)
```

Hər keçid **səbəb + əmr rekviziti** tələb edir və audit izi buraxır (kim, nə vaxt, nə üçün).

Filtrlər: status, ixtisas, pillə, forma, mənbə (ATİS / fayl idxalı / əl ilə), tarix aralığı.
Toplu əməliyyat: seçilmiş sətirlər üçün «Yoxlanışa götür», «Təsdiqlə», «Sənəd tələbi göndər».

### 6.3 Tələbə detal panelı

Sağdan açılan geniş panel, üç bölmə:

1. **Şəxsi məlumat** — ATİS-dən gələn (oxunaq, boz fon, «ATİS mənbəyi» nişanı) + daxili sahələr
   (redaktə oluna bilən). ATİS sahəsini dəyişmək qadağandır — dəyişiklik tələbi ayrıca axındır.
2. **Sənəd çeklisti** — hər sənəd üçün sətir: attestat/diplom, şəxsiyyət vəsiqəsi surəti,
   tibbi arayış, hərbi bilet, foto, ərizə. Hər birində: qəbul edildi ✓ / çatışmır ✗ / əsli
   gətirilmədi ⚠, qəbul tarixi, qəbul edən şəxs, qeyd. **Bütün məcburi sənədlər ✓ olmadan
   «Təsdiqlə» düyməsi passivdir** və üstünə gələndə səbəbi göstərir.
3. **Tarixçə** — status keçidləri zaman xətti (kim, nə vaxt, səbəb, əmr №).

### 6.4 ⭐ Duplikat növbəsi (ayrıca tab)

Sistemin ən kritik qorunmasıdır: **eyni tələbə iki dəfə yaradıla bilməz.** FİN kod üzrə
uyğunluq aşkarlananda sətir bura düşür və **səssiz birləşdirmə qadağandır**:

```
⚠ FİN 5AB1C2D3 — 2 qeyd
  ┌ ATİS 2026 idxalı · Aygün Məmmədova · Kompüter mühəndisliyi
  └ Mövcud qeyd    · Aygün Məmmədova · İqtisadiyyat · 2024 qəbulu · xaric edilib

  [Bu, eyni şəxsdir → bərpa axını]  [Fərqli şəxsdir → izah tələb olunur]  [Sonraya saxla]
```

### 6.5 ATİS idxalı (ayrıca tab)

- Üç mənbə eyni boru xəttindən keçir: **API** · **fayl idxalı (Excel/CSV)** · **əl ilə daxiletmə**.
- İdxal addımları: fayl seç → sütun uyğunlaşdırma (önizləmə cədvəli ilə) → validasiya nəticəsi
  (neçə sətir keçdi / xəbərdarlıq / xəta, sətir-sətir) → təsdiq → nəticə hesabatı.
- Təkrar idxal **idempotentdir**: «142 sətirdən 138-i dəyişməyib, 3-ü yeniləndi, 1-i duplikat
  növbəsinə düşdü» kimi nəticə göstərilməlidir.
- Uğursuz sətirlər ayrıca cədvəldə qalır və yenidən cəhd oluna bilər.

### 6.6 Qeydiyyat (provisioning)

Təsdiqlənmiş tələbələr üçün son addım: qrupa təyinat + hesab yaradılması. Cədvəldə seçim →
«Qrupa təyin et» → ixtisas + qəbul ili üzrə qrup təklifi (sistem `ceil(N/30)` ilə qrup sayı
təklif edir, 15–30 normasını yoxlayır) → əmr № + tarix → təsdiq.

Nəticə zolağı: «128 tələbə 5 qrupa təyin olundu · hesablar yaradıldı · ilk giriş məktubu göndərildi».

---

## 7. İcazə qatı — hər ekranda görünməlidir

İki yeni rol yaradılır (sistemdə hazırda yoxdur):

| Rol | Səviyyə | Görür | Edir |
|---|---|---|---|
| **Tədris Şöbəsi müdiri** | 85 | bütün ağac, bütün planlar, bütün yük | plan/yük təsdiqi, ixtisas + fənn idarəetməsi, akademik təqvim |
| **Tədris Şöbəsi əməkdaşı** | 65 | eyni | fənn əlavə, plan hazırlığı — **təsdiq YOX** |
| **Tələbə Mərkəzi əməkdaşı** | 65 | qəbul növbəsi, öz kampaniyası | sənəd yoxlaması, status keçidi, idxal — akademik nəticələri **görmür** |

Dizaynda qayda: **icazəsi olmayan əməliyyat düyməsi passiv göstərilmir — ümumiyyətlə çəkilmir.**
Yalnız kilidli vəziyyət (məs. təsdiqlənmiş plan) passiv düymə + izah tooltip-i ilə göstərilir.

Hər ekranın yuxarısında kim kimi görür sualına cavab verən kiçik kontekst zolağı olsun:
`Tədris Şöbəsi · bütün fakültələr · 2026/2027 Payız`.

---

## 8. Nümunə data (real — bunlardan istifadə et)

**Universitet:** Qərbi Kaspi Universiteti, 2026/2027 tədris ili, Payız semestri.

**Fakültələr:** Mühəndislik və Tətbiqi Elmlər · İqtisadiyyat və İdarəetmə · Humanitar elmlər.

**Kafedralar (Mühəndislik):** Proqramlaşdırma və informasiya təhlükəsizliyi · Mexatronika və
robototexnika · Riyaziyyat.

**İxtisaslar:** Kompüter mühəndisliyi (050632, Bakalavr, Əyani, 240 ECTS, 4 qrup, 128 tələbə) ·
İnformasiya təhlükəsizliyi (050656, Bakalavr, 3 qrup, 89) · Mexatronika (050634, Bakalavr, 2 qrup, 47) ·
Kompüter elmləri (060509, Magistr, 1 qrup, 12) · Filologiya (050914, Bakalavr, plan YOXDUR ⚠).

**Fənlər (kredit ixtisasa görə dəyişir — bunu göstər):**
- Proqramlaşdırmanın əsasları: Komp.müh **8 kr**, İnform.təh **6 kr**, Mexatronika **7 kr**
- Proqramlaşdırmanın əsasları – 1: Komp.elm 5 kr · Veb texnologiyalar 4 kr
- İnformasiya təhlükəsizliyinin əsasları 6 kr · Şəbəkələrin təhlükəsizliyi 5 kr
- Müasir İKT və informasiya təhlükəsizliyi 3 kr (**xidməti** — psixologiya/filologiya qruplarına)
- Kriptoqrafiya — heç bir planda yoxdur (istifadəsiz nümunəsi)

**Qruplar:** 236 KE (40) · 236 KE ing (25, EN sektor) · 235 İT (40) · 235 K (25) · 236 İ (40) ·
036 (30) + 336 F (50) — sonuncular birləşmə nümunəsi.

**Plan sətri nümunəsi:**
`MİF-B04.04 · Proqramlaşdırma texnologiyaları · 8 kr · 240 ümumi · 180 sərbəst · 60 auditoriya ·
30 müh · 30 sem · — lab · prereq MİF-B04.01 · 2-yaz · həftəlik 4`

**Tələbə Mərkəzi nümunə sətirləri:** Aygün Məmmədova (FİN 5AB1C2D3, Komp.müh, 612 bal, Çatışmazlıq —
tibbi arayış) · Rəşad Quliyev (İnform.təh, 587, Təsdiqləndi) · Nurlan Əliyev (Mexatronika, 543,
Yoxlanılır) · Səbinə Hüseynova (Komp.elm magistr, 91, Qeydiyyata salındı).

---

## 9. İş qaydası

Bir-bir hazırla, **hər ekrandan sonra dayan**:

1. **Tədris Şöbəsi — İxtisaslar** (üç sütunlu master-detail, 5 tab) ← ən vacibi
2. **Tədris Şöbəsi — Fənnlər** (kataloq + «İxtisaslar üzrə kredit» paneli + yeni fənn modalı)
3. **Tədris Şöbəsi — giriş paneli**
4. **Tələbə Mərkəzi — qəbul növbəsi + detal paneli**
5. **Tələbə Mərkəzi — duplikat növbəsi + ATİS idxalı + qeydiyyat**

Hər ekranda: yalnız məzmun sahəsi, `var(--ems-*)` tokenləri, işıqlı tema, Azərbaycan dili,
self-contained HTML, inline SVG ikonlar, üç vəziyyət (skeleton/boş/xəta), datadan hesablanan
göstəricilər.

İndi 1-ci ekranı hazırla.
