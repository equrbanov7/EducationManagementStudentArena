# Claude Design üçün prompt — Dərs Yükü modulu (EMSArena)

> Bu faylın məzmununu olduğu kimi Claude-a ver. Nəticə HTML mockup-lar şəklində
> qayıdacaq; onları geri gətir, istehsal koduna (external CSS/JS, CSP-uyğun) mən çevirəcəyəm.

---

Sən peşəkar UI/UX dizaynersən. «EMSArena» adlı universitet idarəetmə sisteminin yeni
**«Dərs yükü» (tədris tapşırığı)** modulunun ekranlarını dizayn edəcəksən. Nəticəni
**tam işlək, self-contained HTML səhifələr** kimi ver (bir faylda `<style>` və az miqdarda
`<script>` — modalları açıb-bağlamaq, tabları dəyişmək üçün; heç bir xarici CDN/framework
işlətmə). Bütün mətnlər **Azərbaycan dilində** olsun.

**İş qaydası:** əvvəlcə yalnız 1-ci səhifəni (Tədris şöbəsi) hazırla. Mən baxıb
təsdiqləyəndən / düzəliş deyəndən sonra növbəti səhifəyə keç. Beləcə 5 səhifəni
bir-bir tamamlayacağıq.

## 1. Dizayn sistemi (mövcud sistemə uyğunluq MƏCBURİDİR)

Sistem ağ + mavi, yalnız işıqlı (light) temadır. Dark mode YOXDUR. Bu CSS
dəyişənlərini kökdə elan et və hər yerdə yalnız bunlardan istifadə et:

- Əsas mavi: `--ems-primary-600: #2563eb` (brend rəngi), `--ems-primary-700: #1d4ed8`,
  `--ems-primary-800: #1e40af`, açıq çalarlar: `--ems-primary-50: #eff6ff`,
  `--ems-primary-100: #dbeafe`, `--ems-primary-200: #bfdbfe`
- Neytrallar (slate): `--ems-neutral-0: #ffffff`, `50: #f8fafc`, `100: #f1f5f9`,
  `200: #e2e8f0` (standart border), `300: #cbd5e1`, `400: #94a3b8`, `500: #64748b`
  (köməkçi mətn), `700: #334155`, `900: #0f172a` (əsas mətn)
- Semantik: uğur `#16a34a` (açıq fon `#dcfce7`), xəta/qaytarma `#dc2626` (açıq fon
  `#fee2e2`), xəbərdarlıq `#f59e0b` (açıq fon `#fef3c7`)
- Şrift: system-ui yığını (`-apple-system, "Segoe UI", Roboto, sans-serif`)
- Kartlar: ağ fon, 12–14px radius, 1px `#e2e8f0` border, çox yüngül kölgə.
  **Stat-kartlar:** 4px rəngli SOL border + böyük qalın rəqəm (1.6–1.8rem) + altında
  kiçik UPPERCASE boz etiket
- Cədvəllər: başlıq sətri `--ems-primary-50` fonlu, kiçik UPPERCASE hərflər; zebra
  sətirlər (cüt sətir `#f8fafc`); hover-də `--ems-primary-50`; geniş cədvəllərdə ilk
  sütun sticky; cədvəl konteyneri öz daxilində üfüqi scroll edir
- Düymələr: əsas — mavi dolu; ikinci — ağ fon + boz border; təhlükəli — qırmızı.
  8–10px radius
- Modallar: yarı-şəffaf tünd backdrop + ağ kart (16px radius), başlıq + sağda bağla
  (×), altda «Ləğv et / Təsdiq» düymələri
- Select-lər: axtarış xanalı açılan siyahılar; çoxseçimlidə seçilənlər mavi chip kimi

**Status rəng kodları (hər yerdə eyni):** Qaralama — boz chip; Göndərilib — mavi;
Qaytarılıb — qırmızı; Təsdiqlənib — yaşıl; Bölgüdə — narıncı (amber); Bölünüb — tünd
yaşıl dolu; Vakant — qırmızı konturlu.

**KREDİT VURĞUSU (çox vacib):** fənnin krediti heç vaxt adi mətn kimi itməsin. Hər
fənn sətrində kredit ayrıca **chip/badge** kimi görünsün (mavi kontur, qalın rəqəm,
kiçik «kr» etiketi, məs. `5 kr`). Yekun panellərdə cəmi saatla yanaşı **cəmi kredit**
də göstərilsin. Fənn seçiləndə kredit avtomatik dolur, amma redaktə oluna bilir.

**Ümumi UX prinsipi:** aydınlıq > sıxlıq. Qarışıq, yüklü interfeys OLMASIN — hər
ekranda bir əsas iş; ikinci dərəcəli məlumat drill-down/modala keçsin. Boş vəziyyətlər
üçün (heç nə yoxdursa) sadə empty-state dizaynı (ikon + izah + əsas düymə).

## 2. Layout skeleti (BÜTÜN səhifələrdə eyni)

- Yuxarıda nazik top bar: solda «EMS Arena» loqo yazısı (mavi), sağda universitet adı +
  istifadəçi adı/rol + çıxış ikonu.
- **Solda DAİM GÖRÜNƏN sidebar** (240–260px, ağ fon, sağ border): rola uyğun menyu
  bəndləri, aktiv bənd `--ems-primary-50` fon + mavi mətn + solda 3px mavi zolaq.
  Sidebar heç vaxt gizlənmir/yığılmır.
- Məzmun sahəsi: yuxarıda səhifə başlığı + breadcrumb + kontekst düymələri, altında
  məzmun. Maksimum en ~1400px, desktop-first.

## 3. Modulun konteksti (qısa)

Universitetdə illik «tədris-pedaqoji tapşırıq» (dərs yükü) dövriyyəsi:
**Tədris şöbəsi** hər kafedra üçün tapşırıq hazırlayır (fənn, qruplar, saatlar,
kreditlər) → **Dekanlıq** (dekan + hər ixtisasın proqram koordinatoru) təsdiqləyir və
ya qaytarır → **Kafedra müdiri** təsdiqlənmiş yükü öz müəllimlərinə bölür (bölündükcə
qalıq saat azalır) → **Müəllim** öz yükünü kabinetində görür və yükləyir.

Saat strukturu (rəsmi sənəddən): mühazirə (plan üzrə / cəmi), təcrübi-seminar
(plan/cəmi), laboratoriya (plan/cəmi), məsləhət, imtahan, buraxılış işinə rəhbərlik,
doktorantlara rəhbərlik, təcrübələr; sətir CƏMİ-si və KREDİT. «Cəmi» = plan × qrup
sayı (mühazirədə birləşmə sayı, seminarda qrup/yarımqrup sayı).

## 4. Səhifələr (bir-bir hazırla)

### Səhifə 1 — Tədris şöbəsi: «Dərs yükü mərkəzi»

Sidebar bəndləri: İdarə paneli, Tapşırıqlar, Excel import, Hesabatlar, Parametrlər.
Bu səhifə 3 görünüşü əhatə etsin (tab və ya ayrı bölmə kimi):

**a) İl paneli (İdarə paneli):** yuxarıda tədris ili seçici (2026/2027) + «Yeni
tapşırıq» düyməsi. Stat-kartlar: cəmi kafedra, göndərilmiş, təsdiqlənmiş, qaytarılmış.
Altında kafedra kartları grid-i — hər kartda: kafedra adı, status chip-i, yekun saat
(böyük rəqəm), Payız/Yaz mini bölgüsü, cəmi kredit, son hərəkət tarixi, «Aç» düyməsi.

**b) Tapşırıq redaktoru** (bir kafedranın sənədi açılıb): Excel-ə bənzər böyük cədvəl.
Sütunlar: Semestr (PAYIZ/YAZ), Qruplar, Fənn, İxtisas, Forma (əyani/qiyabi/intensiv),
Səviyyə (bakalavr/magistr), Tələbə sayı, Birləşmə, Yarımqrup, Mühazirə plan/cəmi,
Seminar plan/cəmi, Lab plan/cəmi, Məsləhət, İmtahan, Buraxılış, Doktorant, Təcrübə,
CƏMİ (qalın), **Kredit (chip)**, əməliyyatlar (redaktə/kopyala/sil ikonları).
Üst toolbar: «Sətir əlavə et», filtrlər (semestr, ixtisas, forma), axtarış.
Alt yekun zolağı (sticky): Payız cəmi | Yaz cəmi | ÜMUMİ saat | Cəmi kredit +
«Dekanlıqlara göndər» düyməsi.
**CRUD tam görünsün:**
- «Sətir əlavə et» MODALI: fənn axtarışlı seçimi (kataloqdan; seçiləndə kredit
  avto-dolur — kredit sahəsi vurğulu), «kataloqda yoxdur» keçidi ilə sərbəst ad,
  xüsusi sətir növü (Adi dərs / Təcrübə / Buraxılış işi), ixtisas seçimi → ona bağlı
  qruplar çoxseçimi (chip-lər), semestr, forma, səviyyə, tələbə sayı, birləşmə/yarımqrup
  sayları, saat xanaları (plan yazılanda cəmi avtomatik hesablanır, redaktə olunandır),
  canlı sətir CƏMİ önizləməsi.
- Silmə təsdiq modalı (qırmızı vurğulu).
- «Göndər» klikində VALİDASİYA XÜLASƏSİ modalı: xəbərdarlıqlar siyahısı (məs. «3 sətirdə
  cəmi düsturla uyğun gəlmir», «2 fənn kataloqla uyğunlaşmayıb») + hansı fakültələrə
  təsdiq diliminin düşəcəyi + «Təsdiq et, göndər».

**c) İzləmə görünüşü** (göndərilmiş sənəd): fakültə dilimləri cədvəli — fakültə adı,
status chip, koordinator vizası (3/5 kimi progress), dekan qərarı, tarix, şərh.
Qaytarılan sətirlər əsas cədvəldə qırmızı fonla + dekan şərhi tooltip/sətiraltı.

**d) Excel import sehrbazı:** 3 addımlı stepper (1. Fayl yüklə → 2. Uyğunlaşdırma —
tapılan fənn/qrupların kataloqla eşləşmə cədvəli, tapılmayanlar sarı «mətn kimi
qalacaq» işarəsi ilə → 3. Nəticə xülasəsi: neçə sətir, cəmi saat/kredit).

### Səhifə 2 — Dekanlıq: «Yük təsdiqi»

Sidebar: Təsdiq növbəsi, Tarixçə. Yuxarıda iki tab: **Koordinator baxışı** və
**Dekan baxışı**.

- **Koordinator baxışı:** başlıqda ixtisas adı + progress («28 sətirdən 21-i baxılıb»).
  Cədvəl: yalnız öz ixtisasının sətirləri (fənn + kredit chip, qruplar, semestr, saat
  yekunu). Hər sətirdə iki düymə: «✓ Baxdım» (yaşıl) və «İrad» (sarı) — İrad klikində
  modal: şərh (məcburi) + göndər. Baxılmış sətirlər solğun yaşıl fon.
- **Dekan baxışı:** stat-kartlar (dilimin cəmi saatı, cəmi kredit, ixtisas sayı,
  iradlı sətir sayı — qırmızı kart). Cədvəl: sətirlər + «Koordinator vizası» sütunu
  (✓ / irad ikonu + şərhi hover-də) + hər sətirdə checkbox. Alt zolaq: «Seçilmişləri
  qaytar» (modal: qaytarma səbəbi məcburi textarea) və «Dilimi TƏSDİQLƏ» (yaşıl,
  confirm modalı: «X sətir, Y saat, Z kredit təsdiqlənəcək»). Tarixçə tabında
  hərəkət jurnalı (kim, nə vaxt, nə etdi) timeline kimi.

### Səhifə 3 — Kafedra müdiri: «Yük bölgüsü» (modulun vitrin səhifəsi)

Sidebar: Yük bölgüsü, Müəllim yükləri, Hesabatlar. İki panelli layout:

- **Sol panel — tapşırıq sətirləri** (~60% en): filtr zolağı (semestr, fənn, ixtisas,
  forma, «yalnız bölünməmişlər»). Hər sətir kart/sıra kimi: fənn adı + **kredit chip**,
  qruplar, semestr, ixtisas; altında fəaliyyət-fəaliyyət **qalıq progress barları**:
  «Mühazirə 30/30 ✓» (yaşıl, dolu), «Seminar 15/45» (narıncı, 1/3 dolu), «Lab 0/30»
  (boş, boz). Sətirdə «Bölgü et» düyməsi. Tam bölünmüş sətirdə yaşıl «Tam» nişanı.
- **Bölgü MODALI** («Bölgü et» klikində): yuxarıda sətir xülasəsi (fənn, kredit,
  qruplar, qalıqlar); fəaliyyət növü seçimi (yalnız qalığı olanlar aktiv); müəllim
  axtarışlı siyahısı — **hər müəllimin adının yanında cari yükü / norması mini progress
  bar** (məs. «Dos. A.Məmmədov — 420/500 s.»); saat input (maks = qalıq, aşanda qırmızı
  xəta); qrup/yarımqrup qeydi (mətn); «saathesabı» checkbox; **«Vakant saxla»** seçimi
  (müəllimsiz — qırmızı konturlu). «Əlavə et» → modal içində əlavə olunan bölgülər
  siyahısı görünür, qalıq canlı azalır.
- **Sağ panel — müəllim yük paneli** (~40%): hər müəllim üçün kompakt kart: ad +
  vəzifə (dosent və s.), **cəmi saat / norma progress bar** (norma aşımında qırmızı +
  xəbərdarlıq ikonu), Payız/Yaz bölgüsü, saathesabı hissə. Karta klik → MODAL:
  müəllimin tam bölgü cədvəli (fənn, kredit, fəaliyyət, saat, qruplar, semestr) +
  cəmi sətri + «Excel yüklə» düyməsi. Panelin başında «Vakant saatlar» qırmızı kartı.
- Səhifənin altında sticky yekun zolağı: «Bölünüb: 7 830 / 8 965 saat (87%)» progress +
  «Bölgünü TƏSDİQLƏ» düyməsi (yalnız 100%-də aktiv; vakant varsa sarı xəbərdarlıq
  modalı ilə keçir).

### Səhifə 4 — Müəllim: «Dərs yüküm»

Sidebar: Dərs yüküm, Arxiv. Məzmun:
- Stat-kartlar: İllik cəmi saat, Norma (və doluluq %-i progress ilə), Cəmi kredit,
  Saathesabı saat.
- Semestr tabları: Payız | Yaz | İllik yekun.
- Cədvəl: Fənn + **kredit chip**, Qrup(lar), Fəaliyyət növü (mühazirə/seminar/lab —
  rəngli mini-chip), Saat, Forma, Səviyyə. Altda yekun sətri.
- Sağ yuxarıda: «Excel yüklə» (öz yükü) və «Ümumi tapşırığa bax» (kafedranın təsdiqli
  sənədinə baxış modalı — sadə cədvəl önizləmə + yükləmə düyməsi).
- Arxiv: keçmiş illər seçici (yalnız oxunuş rejimi banneri ilə).

### Səhifə 5 — Rektorluq paneli (sonda, sadə)

Fakültə/kafedra üzrə yekun cədvəl (saat + kredit), status xəritəsi (hansı kafedra
hansı mərhələdədir — rəngli matris), «Vakant fond» kartı, norma kənarlaşmaları siyahısı.

## 5. Nümunə data (realdır, bunlardan istifadə et)

- Universitet: Qərbi Kaspi Universiteti; tədris ili 2026/2027.
- Kafedra: «Proqramlaşdırma və informasiya təhlükəsizliyi» — yekun 8 965 saat
  (Payız 4 665, Yaz 4 300).
- Fənlər (kreditlə): Proqramlaşdırmanın əsasları – 1 (5 kr), Proqramlaşdırmanın
  əsasları – 3 (4 kr), Veb texnologiyalar (4 kr), İnformasiya təhlükəsizliyinin
  əsasları (6 kr), Şəbəkələrin təhlükəsizliyi (5 kr), Müasir informasiya-kommunikasiya
  texnologiyaları və informasiya təhlükəsizliyi (3 kr).
- Qruplar: 236 KE, 236 KE ing, 235 İT, 235 K, 236 İ; birləşmə nümunəsi: «036 / 336 F»
  (tələbə: 30 / 50). Saat nümunələri: mühazirə 30/30, seminar 15/45, lab 30/60.
- Müəllimlər (nümunə): dos. A. Məmmədov (norma 500), b/m N. Əliyeva (norma 550),
  müəl. R. Həsənov (norma 600), assistent S. Quliyeva (0.5 ştat, norma 250).
- Fakültələr: Təbiət elmləri və İT fakültəsi; Humanitar fakültə (xidməti tədris
  nümunəsi üçün — psixologiya/filologiya qrupları).

## 6. Nə İSTƏMİRİK

- Dark mode, bənövşəyi/qradiyent «SaaS» estetikası, neon rənglər — YOX.
- Xarici font/ikon CDN-ləri — YOX (ikonlar sadə inline SVG olsun).
- Həddindən artıq sıx, Excel-dən betər qarışıq görünüş — YOX; aydınlıq əsasdır.
- Lorem ipsum — YOX; yalnız yuxarıdakı real Azərbaycan dilində data.

İndi Səhifə 1-i (Tədris şöbəsi) hazırla.
