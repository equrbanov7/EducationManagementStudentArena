# Claude Design — v2 promptu (düzəlişlər + tədris planı ekranları)

> Bu faylın «────» xəttindən sonrakı hissəsini olduğu kimi Claude-a ver.

────────────────────────────────────────────────────────────────────────

Sən EMSArena universitet sisteminin «Dərs yükü» modulunun dizaynını **v2-yə** çıxarırsan.
V1-də 6 səhifə hazırlanıb; indi həm düzəlişlər var, həm də 2 yeni ekran.

## 0. ƏN VACİB DƏYİŞİKLİK — qabığı çəkmə

**Topbar və sol sidebar-ı ÇƏKMƏ.** Tətbiqdə onlar artıq var və öz qaydaları ilə işləyir —
v1-də çəkdiyin qabıq bizim mövcud strukturumuzdan kənara çıxdı, ona görə onu atırıq.

Hər faylda **yalnız məzmun sahəsini** ver — istifadəçi sol menyudakı bəndə klikləyəndə sağda
açılan hissəni. Səhifəni belə qur:

```html
<div style="max-width:1180px; padding:24px 28px 40px">
  <!-- yalnız məzmun: başlıq bloku, filtrlər, kartlar, cədvəllər, modallar -->
</div>
```

- Ölçü fərziyyəsi: sol menyu ~248px yer tutur, sənin sahən **~1180px**-dir (ümumi 1440px).
- Modallar `position:fixed; inset:0` ilə tam ekranı örtə bilər — bu istisnadır, normaldır.
- Səhifə başlığı bloku (breadcrumb + H1 + alt mətn + sağ tərəfdə düymələr) **sənin sahəndədir**,
  onu çək.
- Naviqasiya bəndlərini, loqonu, istifadəçi menyusunu, «çıxış» düyməsini çəkmə.

## 1. Dizayn sistemi — dəyişməz qalır, amma tokenlə

Rəngləri **CSS dəyişəni kimi** elan et və hər yerdə `var(--ems-*)` işlət (v1-də hamısı xam
hex idi, tokenləşdirmə tam əl işi oldu):

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

**Palitradan kənar rəng işlətmə.** V1-də `#3b82f6`, `#10b981`, tünd `#0f172a` kart fonu və
hesabat ikonlarında bənövşəyi/narıncı palitra vardı — hamısı çıxarılır. Tünd fonlu kart yoxdur,
tətbiq yalnız işıqlıdır.

**Cədvəl:** başlıq `--ems-primary-50` fon + `--ems-primary-800` mətn + uppercase; zebra sətirlər;
**hover `--ems-primary-50`**; geniş cədvəldə **ilk sütun sticky**; konteyner daxilində üfüqi scroll.

**Stat kart:** ağ fon, **4px rəngli sol border**, böyük qalın rəqəm, kiçik UPPERCASE boz etiket.

**Filtrlər:** «Bax»/«Göstər»/«Tətbiq et» düyməsi **YOXDUR** — dəyişiklik dərhal tətbiq olunur
(300ms debounce). Açılanları axtarış sahəsi olan xüsusi komponent kimi çək (native `<select>` yox).

**Hər cədvəl üçün 3 vəziyyət göstər** (v1-də heç biri yox idi): skeleton (shimmer sətirlər),
boş vəziyyət (ikon + izah + «filtrləri sıfırla»), xəta («Məlumat yüklənmədi · Yenidən cəhd et»).

**Əlçatanlıq:** modallarda `role="dialog"` + `aria-modal="true"`, `<label for>` bağlantıları,
klik olunan sətirlərdə `tabindex="0"` + `role="button"`, ikon düymələrində `aria-label`.

**Responsivlik:** grid-lər `repeat(auto-fit, minmax(...))` olsun; ~900px-də 2 sütuna, ~640px-də
1 sütuna düşsün.

## 2. Domen qaydaları — v1-də səhv idi, düzəlt

Bunlar dizaynın məntiq qatıdır, hər ekranda tətbiq olunur:

### 2.1 Kredit necə cəmlənir
Kredit **tədris sətrinin yox, fənnin** atributudur. Eyni fənn 2 qrupa tədris olunanda saat
2 dəfə sayılır, **kredit 1 dəfə**. Ona görə:
- Sətirdə kredit çipi qalır (yaxşı işlənib, saxla).
- Aqreqatda **«Cəmi kredit (təkrarsız fənn)»** yazılır — sadəcə «Cəmi kredit» yox.
- Müəllim ekranında fəaliyyət sətirlərində kredit çipi **təkrarlanmır** — yalnız fənn başlığında.

### 2.2 Saat düsturu və terminologiya
```
mühazirə cəmi   = mühazirə plan × BİRLƏŞMƏ sayı (mühazirə axını)
seminar cəmi    = seminar plan  × YARIMQRUP sayı
laboratoriya    = lab plan      × YARIMQRUP sayı
sətir CƏMİ      = bütün «cəmi» sütunlarının cəmi
```
**«Qrup sayı» ifadəsini işlətmə** — v1-də izah mətnləri «plan × qrup sayı» deyirdi, bu yanlışdır.
Cədvəldə çarpanı **görünən et**: `15 × 3 = 45` kimi, ya da xananın altında kiçik boz `×3`.

### 2.3 Rəhbərlik saatları ayrı sətirdir
Buraxılış işi / dissertasiya / doktorant rəhbərliyi fənn sətrinə **yapışdırılmır** — ayrıca
sətir növüdür (fənnsiz, kreditsiz, tələbə sayına bağlı). Magistrdə «buraxılış işi» deyil,
**dissertasiya** yazılır.

### 2.4 «Vakant» ≠ «bölünməmiş»
İki ayrı göstərici: **bölünməmiş** (hələ heç kimə verilməyib) və **vakant** (müəllim yoxdur,
saathesabı/ştat tələb edir). V1-də qarışdırılmışdı və 9 792 saat adsız qalmışdı.

### 2.5 Bütün göstəricilər datadan hesablanır
V1-də demək olar hər stat kart markup-a hərfi yazılmışdı və filtrə reaksiya vermirdi. Nümunə
datanı massiv kimi saxla, **bütün kartları, yekun sətirlərini və faizləri ondan hesabla**.
Filtr dəyişəndə kartlar da dəyişməlidir.

### 2.6 Qruplar massivdir
`"036 / 336 F"` kimi birləşdirilmiş mətn yox, qrup obyektləri massivi (ad, tələbə sayı, dil
sektoru). Filtr dəqiq bərabərliklə işləməlidir — v1-də `indexOf` işlədilirdi və «236 KE» filtri
«236 KE ing» qrupunu da tuturdu.

## 3. Yeni ekran A — «Tədris planı redaktoru»

Universitetdə dərs yükü tədris planından törəyir. Bu ekran kafedra/dekanlıq üçündür.

**Kontekst zolağı:** ixtisas adı + qəbul ili + pillə (bakalavr/magistr) + status çipi
(Qaralama / Kafedra baxışı / Fakültə şurası / Tədris şöbəsi / Təsdiqlənib) + Elmi Şura protokolu.

**Əsas cədvəl — iki səviyyəli (blok → fənn), rəsmi 13 sütun:**

| Sütun | Qeyd |
|---|---|
| Şifr | `MİF-B04.01` |
| Fənnin adı | seçmə blokda alt-siyahı (nömrələnmiş alternativlər) |
| **Kredit** | çip |
| Ümumi saat | = kredit × 30, avto |
| Sərbəst iş | auditoriyadan kənar |
| Auditoriya | = ümumi − sərbəst |
| Mühazirə / Seminar / Laboratoriya | auditoriyanın bölgüsü |
| Prerekvizit | şifr çipləri |
| Semestr | `1-payız`, `2-yaz` |
| Həftəlik | = auditoriya ÷ 15 |
| Tədris edən kafedra | xidməti fənlər üçün vacib |

Blok başlığı sətri **aqreqat** göstərir (blokun cəmi kredit/saat) və vizual olaraq fərqlənir
(açıq mavi fon, qalın).

**Sağda canlı balans paneli** — bu ekranın əsl dəyəri, sticky:

```
Semestr 1    30 / 30 kredit   ✓
Semestr 2    28 / 30 kredit   ⚠ 2 kredit çatmır
...
ÜMUMİ       240 / 240         ✓
Seçmə payı   28,9%   (25–30%)  ✓
Humanitar    17,0%   (15–20%)  ✓
Kredit↔saat  2 sətirdə pozulub ⚠
Prerekvizit  dövr yoxdur       ✓
Kafedra      3 sətir boş       ⚠
```
Xəbərdarlıqlara klik → cədvəldə həmin sətirlərə filtr.

**Modallar:** sətir əlavə/redaktə (fənn kataloqu axtarışlı, kredit yazılanda ümumi saat və
həftəlik avto-hesablanır, canlı yoxlama mesajları), blok əlavə, **«Keçən ildən klonla»**
(mənbə plan seçimi + önizləmə + nə dəyişəcək), prerekvizit seçimi (yalnız əvvəlki semestrlərin
fənləri), «Fakültə şurasına göndər» (balans xülasəsi + xəbərdarlıqlar).

**İkinci tab — «Tədris qrafiki»:** sentyabr→avqust həftəlik toru; xanalar: nəzəri təlim (boş),
imtahan sessiyası, təcrübə, yekun attestasiya, tətil. Rəngli leqenda ilə.

## 4. Yeni ekran B — «İllik işçi tədris planı»

Tədris planı statikdir (qəbul ilinə bağlı); bu isə **hər il** yaranır və tələbə saylarını daşıyır.
Dekanlıq təsdiqləyib tədris şöbəsinə göndərir — dərs yükü məhz bundan generasiya olunur.

**Yuxarıda generasiya zolağı:** «2026/2027 üçün plan generasiya edildi — 5 ixtisas, 128 sətir,
1 240 tələbə» + «Yenidən generasiya et» düyməsi (xəbərdarlıq modalı ilə).

**Stat kartlar:** sətir sayı, **cəmi kredit (təkrarsız fənn)**, tələbə sayı, istisna edilən sətir
(qırmızı), tədris edən kafedra sayı.

**Cədvəl:** Fənn + kredit çipi · Kurs · Semestr · Qruplar (çip, hər çipdə tələbə sayı) ·
Cəmi tələbə · Tədris edən kafedra (redaktə oluna bilən açılan) · «Daxil edilsin?» keçidi.

Keçid söndürüləndə sətir solğunlaşır və səbəb tələb olunur («yetərli tələbə yoxdur» və s.) —
bu, normativ tələbdir (fənnə az tələbə yığılarsa illik plana daxil edilmir).

**Sətir detalı modalı:** plandan gələn norma saatları (mühazirə/seminar/lab), qrup-qrup tələbə
bölgüsü, dil sektoru, prerekvizitin ödənib-ödənmədiyi.

**Alt sticky zolaq:** yekunlar + «Tədris şöbəsinə göndər».

## 5. Mövcud 6 səhifəyə əlavələr

### 5.1 Koordinator və Dekanlıq — «PLAN ↔ TAPŞIRIQ» müqayisə sütunları
Bu, v1-in ən böyük boşluğudur: koordinatorun nümunə iradı «ixtisas planındakı 30 saatdan
çoxdur» deyir, amma **plan norması ekranda yoxdur** — müqayisə edə bilmədiyi şeyə istinad edir.

Cədvələ iki sütun əlavə et:

| PLAN (norma) | TAPŞIRIQ | FƏRQ |
|---|---|---|
| 30 / 15 / 15 | 30 / 45 / 15 | `seminar ×3 (3 yarımqrup)` — yaşıl, izah var |
| 30 / 15 / 30 | 30 / 15 / 45 | `lab +15 · izahsız` — sarı ⚠ |

Fərq sətirləri sarı fonla; «yalnız fərqli sətirlər» filtri; iradı birbaşa fərqə bağlayan düymə.

### 5.2 Digər düzəlişlər (v1 təhlilindən)
- **Tədris şöbəsi:** kafedra kartına klik həmin kafedranın sənədini açsın (v1-də həmişə eyni
  statik sənəd açılırdı); arxiv rejimində bütün redaktə düymələri **passiv** olsun; xəbərdarlıqdan
  aid sətirlərə keçid; import nəticəsi üçün «əlavə et / əvəz et / birləşdir» seçimi.
- **Koordinator:** «Hamısına viza ver» **yalnız filtrlənmiş sətirlərə** təsir etsin + təsdiq
  modalı + geri-alma; irad vermək progress-i azaltmasın (irad da tamamlanmış qərardır); bir sətir
  eyni anda həm «vizalı» həm «iradlı» görünməsin.
- **Kafedra müdiri:** **bütün fəaliyyət növləri** bölünə bilsin (v1-də yalnız mühazirə/seminar/lab
  vardı — məsləhət, imtahan, buraxılış, doktorant, təcrübə yox idi); təsdiq qapısı vakantla
  keçidə icazə versin (xəbərdarlıq + əsaslandırma ilə); kəsr saat (15,5) dəstəklənsin; norma
  aşımı əlavə edilərkən xəbərdarlıq çıxsın və bar aşımı göstərsin.
- **Dekanlıq:** «Təsdiq növbəsi» əvvəlcə **gözləyən dilimlərin siyahısını** göstərsin, sonra
  detala keçsin (v1-də birbaşa bir sənədə düşürdün).
- **Müəllim:** «Dəyişdirilib» statusuna klik → **nə dəyişdi** diff-i (köhnə → yeni, səbəb, kim,
  nə vaxt); şəxsi yükün Excel/PDF ixracı; təsdiq üçün son tarix + geri sayım; təsdiqi geri çəkmə.
- **Rektor:** **təsdiq əməliyyatı** (funnel «Rektor təsdiqi — GÖZLƏYİR» deyir, amma düymə yoxdur);
  kafedra → müəllim → fənn drill-down-u; «norma üstü saat» stat kartı; «az yüklü müəllimlərlə
  örtülə bilən vakant saat» göstəricisi.
- **Hamısında:** səhifələmə, sütun üzrə sıralama, axtarış, **son tarix (deadline) göstəricisi**,
  audit tarixçəsi (kim/nə vaxt/nə etdi).

## 6. Nümunə data (real, bunlardan istifadə et)

Qərbi Kaspi Universiteti, 2026/2027. Kafedra: «Proqramlaşdırma və informasiya təhlükəsizliyi» —
8 965 saat (Payız 4 665 / Yaz 4 300).

**Fənlər (kredit ixtisasa görə dəyişir — bu vacibdir):**
- Proqramlaşdırmanın əsasları: Komp.müh **8 kr**, İnform.təh **6 kr**, Mexatronika **7 kr**
- Proqramlaşdırmanın əsasları – 1: Komp.elm 5 kr · Veb texnologiyalar: 4 kr
- İnformasiya təhlükəsizliyinin əsasları: 6 kr · Şəbəkələrin təhlükəsizliyi: 5 kr
- Müasir İKT və informasiya təhlükəsizliyi: 3 kr (xidməti — psixologiya/filologiya qruplarına)

**Qruplar:** 236 KE (40 tələbə), 236 KE ing (25), 235 İT (40), 235 K (25), 236 İ (40),
036 (30) + 336 F (50) — sonuncular birləşmə nümunəsi.

**Saat nümunələri:** müh 30/30 (birləşmə 1), sem 15/45 (3 yarımqrup), lab 30/60 (2 yarımqrup).

**Tədris planı nümunəsi (magistr, 13 sütun):**
`MİF-B04.04 | Proqramlaşdırma texnologiyaları | 8 kr | 240 ümumi | 180 sərbəst | 60 auditoriya |
30 müh | 30 sem | — lab | prereq MİF-B04.01 | 2-yaz | həftəlik 4`

**Müəllimlər:** dos. A. Məmmədov (norma 500), b/m N. Əliyeva (550), müəl. R. Həsənov (600),
assist. S. Quliyeva (0,5 ştat).

## 7. İş qaydası

Bir-bir hazırla, hər səhifədən sonra dayan:
1. **Tədris planı redaktoru** (yeni)
2. **İllik işçi tədris planı** (yeni)
3. Koordinator — plan↔tapşırıq müqayisə sütunları ilə yenilənmiş
4. Tədris şöbəsi — düzəlişlərlə
5. Kafedra müdiri — düzəlişlərlə
6. Dekanlıq, Müəllim, Rektor — düzəlişlərlə

Yalnız məzmun sahəsi, Azərbaycan dilində, self-contained HTML (xarici CDN yox, ikonlar inline SVG).
İndi 1-ci ekranı hazırla.
