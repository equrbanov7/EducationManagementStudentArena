# Dizayn v2 — «Tədris planı redaktoru» ekranının təhlili

> **Fayl:** `Tədris planı redaktoru.dc.html` (1 096 sətir), Claude Design v2 promptuna cavab.
> **Metod:** iki müstəqil agent — biri struktur/qayda uyğunluğu, digəri domen riyaziyyatı.
> Nümunə datanın **hər rəqəmi əl ilə yenidən hesablanıb**.
> **Vəziyyət:** 2-ci ekran («İllik işçi tədris planı») hələ hazırlanır.

---

## 1. Yekun qiymət

**V1-dən köklü irəliləyiş.** Prompt demək olar hərfən icra olunub: qabıq çəkilməyib, 13 sütunlu
iki səviyyəli cədvəl, sticky balans paneli, 5 modal, tədris qrafiki tabı, üç cədvəl vəziyyəti
və — ən vacibi — **bütün rəqəmlər datadan hesablanır**. V1-in əsas xəstəliyi (markup-a hərfi
yazılmış göstəricilər) burada demək olar tamamilə aradan qalxıb.

**Riyaziyyat qüsursuza yaxındır.** 12 sətrin 10-unda `kredit × 30 = ümumi saat`,
12-sinin hamısında `auditoriya = ümumi − sərbəst iş` və `mühazirə + seminar + lab = auditoriya`,
12-sinin hamısında `həftəlik = auditoriya ÷ 15` **dəqiq tutur**. Qalan 2 sətir **qəsdən əkilmiş
xətadır** və UI onları düzgün tutur («180 olmalı», «90 olmalı») — hətta biri audit tarixçəsində
«180 → 185 dəyişdirildi» sətri ilə izah olunur. Blok aqreqatları və yekun sətri əl hesabımla tam
üst-üstə düşür: **58 kredit · 1 750 · 1 090 · 660 = 285 + 285 + 90**.

**İki P0 problem var** və hər ikisi göndərmə qapısını keçir — yəni səhv plan Elmi Şuraya gedə bilər.

---

## 2. Promptun icrası — bənd-bənd

| Tələb | Vəziyyət | Qeyd |
|---|---|---|
| `:root --ems-*` tokenləri və istifadəsi | **qismən** | **521 dəfə** `var(--ems-*)` ✓, amma **32 xam hex** qalıb (#92400e ×15, #166534 ×7, #fde68a ×5…). Qadağan edilənlər (#3b82f6, #10b981, tünd kart) **tamamilə çıxarılıb** ✓ |
| Yalnız məzmun sahəsi (qabıq yox) | **tam** | `max-width:1180px;padding:24px 28px 40px` — promptdakı ilə eyni. Loqo/nav/çıxış yoxdur |
| Filtr apply düyməsi yox + debounce + native select yox | **tam** | Apply yoxdur; **dəqiq 300ms debounce**; `<select>` sıfır — 6 açılanın hamısı axtarışlı listbox |
| 3 vəziyyət (skeleton/boş/xəta) | **tam** | Skeleton `aria-busy`+`aria-live`, xəta `role="alert"`, boş vəziyyət «Filtrləri sıfırla»+«Sətir əlavə et». Real filtr nəticəsinə də bağlıdır |
| A11y | **qismən** | 5 modalda `role="dialog"`+`aria-modal`+`aria-labelledby` ✓, 12 `<label for>`, 21 `aria-label`, `scope="col"`, `aria-sort` ✓. **Yoxdur:** Escape, focus-trap, ilkin fokus; sıralanan `<th>` klaviatura ilə əlçatmaz |
| Responsivlik | **qismən** | `@media` **yoxdur**, amma `auto-fit minmax` + `flex-wrap` ilə ~940px-də alt-alta düşür. Cədvəl `min-width` + `overflow:auto` ✓ |
| Cədvəl üslubu | **qismən** | Başlıq primary-50 + primary-800 uppercase ✓, zebra ✓, sticky ilk sütun düzgün z-index qatları ilə ✓. **Hover ilk sütunda işləmir** — sticky td-nin öz fonu üstələyir |
| Stat kartlarda 4px sol border | **tam** | 5 + 3 kart, hamısı datadan, filtrə reaksiya verir |
| 13 sütun, iki səviyyəli | **tam** | 13 + əməliyyat; colspan hesabı düzgün (6+8=14, 9+5=14); seçmə blokda nömrələnmiş alternativlər |
| Canlı balans paneli | **qismən** | Sticky ✓, məzmun promptdakı nümunə ilə sətir-sətir üst-üstə düşür. **Auditoriya bölgüsü yoxlaması yoxdur**; 5 yoxlamadan yalnız 2-si klik olunur |
| 5 modal | **tam** | Sətir modalı ən güclü hissədir — canlı hesablama + 3 yoxlama + şərtli kilid |
| Tədris qrafiki tabı | **qismən** | Tor + leqenda var, amma **həftə hesabı normativlə ziddiyyətdədir** (aşağıda) |
| «Keçən ildən klonla» | **qismən** | Modal + diff cədvəli var, amma **diff statikdir** — mənbə dəyişəndə rəqəm dəyişmir |
| Kredit qaydası (təkrarsız fənn) | **tam** ⭐ | `uniqueCredit()` şifrə görə deduplikasiya edir; etiket birbaşa «Cəmi kredit (təkrarsız fənn)» yazılıb |

---

## 3. ⚠️ P0 — göndərmədən əvvəl mütləq düzəlməli

### 3.1 Prerekvizit yoxlaması heç nə hesablamır

Balans panelində və göndəriş modalında prerekvizit sətri **sabit `true`** yazılıb:
`chk('Prerekvizit', 'dövr yoxdur', true, …)`. Nə **dövr (cycle) aşkarlanması**, nə də
«prerekvizit sonrakı və ya eyni semestrdədir» yoxlaması var.

**Nəticə:** dövrü olan plan da «✓ dövr yoxdur» görünüb Elmi Şuraya göndərilə bilər — çünki
göndərmə şərti bu yoxlamanı ümumiyyətlə nəzərə almır.

**Düzəliş:** şifr → prerekvizit qrafını qur, DFS ilə dövr axtar, hər sətir üçün semestr sırasını
müqayisə et; balans sətrini «Prerekvizit — N sətirdə problem» kimi hesabla və göndərmə şərtinə daxil et.

### 3.2 Ümumi kredit hədəfi 240-a hardcode edilib

`totTarget = target × 8` (= 240) və kontekst zolağındakı «Bakalavr · 240 kredit» **markup-da
hərfi mətndir**. Spesifikasiya isə açıq deyir: **240 sabit deyil** — 4 illik 240, 5 illik 300,
magistr 120.

**Nəticə:** 5 illik bakalavr və ya magistr planı bu ekranda düzgün göstərilə bilməz. Qiyabi üçün
semestr hədəfini 24-ə qoysanız ümumi hədəf səssizcə 192 olur.

**Düzəliş:** `degreeYears` / `educationForm` / `semesterCount` prop-ları əlavə et
(4→8 sem/240, 5→10 sem/300, 2→4 sem/120); pillə çipini də həmin propdan yaz.

---

## 4. P1 — nəzərəçarpan qüsurlar

1. **Balans panelinin 8 semestrindən 6-sı sintetik massivdəndir** və həmişə `30/30 ✓` göstərir.
   Yekun 238 kreditin **180-i (76%)** heç bir plan sətrinə bağlı deyil, panel isə «canlı
   hesablanır» vəd edir. Həmin 6 sətir nə filtrə, nə redaktəyə reaksiya verir və heç vaxt ⚠ ola bilmir.

2. **«Auditoriya bölgüsü» yoxlaması balans panelində yoxdur** (yalnız modalda). Bu, əkilmiş
   xətaların **ikinci yarısını görünməz edir**: T02.01-də qaydaya görə auditoriya 70 olmalıdır,
   bölgü isə 45+30 = 75 (fərq +5); S06.02-də 40 olmalıdır, bölgü 45. Cədvəldə hər iki sətir
   «sağlam» görünür — pozuntu yalnız «Ümumi saat» xanasında işarələnir.

3. **Tədris qrafiki normativ həftə hesabı ilə ziddiyyətdədir.** Tor 12 ay × 5 həftə = **60 həftə**
   (tədris ili 52). Nəzəri təlim 19+19 = **38 həftə** (norma 15+15 = 30), imtahan sessiyası
   3+4 = **7** (norma 5+5 = 10). Eyni səhifədə həftəlik yük **÷15** ilə hesablanır — iki tab
   bir-birini təkzib edir.

4. **Qrafikdə 5 həftə təcrübə var, planda təcrübə sətri yoxdur.** NK 348 b. 3.2.2-yə görə
   1 həftə = 1,5 kredit, yəni 5 həftə = **7,5 kredit** plana daxil olmalıdır. Balans isə elə
   həmin semestrdə «2 kredit çatmır» deyir.

5. **Göndəriş modalındakı xəbərdarlıqlar statik massivdir.** Data tam təmiz olsa belə istifadəçi
   «⚠ 0 sətirdə kredit × 30 ≠ ümumi saat» görəcək. Üstəlik `Math.abs()` işlədildiyi üçün kredit
   **artıq** olanda da «çatmır» yazılır.

6. **Prerekvizit seçicisi ümumiləşmir:** semestrlər müqayisə edilmir, sadəcə `'1-payız'`
   literalı axtarılır. 8 semestrlik real planda 6-cı semestr sətrinə yalnız 1-ci semestr fənləri
   təklif olunacaq. Sətrin özü siyahıdan çıxarılmır (öz-özünə prerekvizit mümkündür).

7. **Sətir modalında BLOK seçimi və «Ümumi saat» override sahəsi yoxdur.** Yeni sətir heç bir
   bloka təyin edilə bilmir; əkilmiş 185 dəyəri redaktədə nə görünür, nə düzəldilir — modal onu
   səssizcə 180-ə çevirir.

8. **Klaviatura əlçatanlığı:** sıralanan `<th>`-lər yalnız siçanla; modallarda Escape,
   focus-trap və ilkin fokus yoxdur.

9. **Sıralama yalnız blok daxilində işləyir** — «Kredit ↓» seçəndə bloklar həmişə eyni sırada
   qalır, sıralama yalnız blok içindəki 2-4 sətrə təsir edir və bunu bildirən qeyd yoxdur.

---

## 5. P2 — kiçik, amma yığılan qüsurlar (seçilmiş)

- **Seçmə/humanitar payı KREDİTdən hesablanır**, NK 117 isə «ümumi saat miqdarının» faizi deyir.
  İki baza yalnız `kredit × 30` heç yerdə pozulmayanda üst-üstə düşür — burada pozulub.
  UI hansı bazanın işlədildiyini demir.
- **Faiz məxrəci 238-dir** (faktiki cəm), 240 deyil — natamam planda payı süni şişirdir.
- **«Ümumi saat» kartının alt yazısı öz rəqəmini təkzib edir**: «kredit × 30» yazır, dəyər 1 750,
  58 × 30 isə 1 740.
- **Sərbəst iş tək sahədir** — spesifikasiya MRTSİ/TSİ ayrılığını tələb edir (MRTSİ müəllim
  yükünə düşür, ≥40% normativdir). Bu, birbaşa dərs yükü modulunu qidalandıran sahədir.
- **Auditoriya/kredit əmsalı sətirdən-sətrə 25%–50% dəyişir** və heç bir yoxlaması yoxdur.
- **Klonlama diff-i statikdir**; **kontekst zolağı tamamilə statikdir** (protokol №, pillə,
  «12 gün qalıb» geri sayımı heç bir tarixdən hesablanmır).
- **Kurs filtri praktikada boş/dolu açarıdır** — 2/3/4-cü kurs seçiləndə cədvəl boşalır, balans
  paneli isə dəyişmir; qrafik tabında başlıqda «1-ci kurs» sabit yazılıb.
- **Kataloq və plan sətirləri fərqli kafedra lüğəti işlədir** — kataloqdan fənn seçəndə açılan
  öz siyahısında olmayan dəyər göstərir.
- **Mənfi dəyər yoxlaması yoxdur** — sərbəst iş ümumi saatdan böyük olanda auditoriya mənfi olur.
- **Peşə hazırlığı payı (80–85%) yoxlanmır** — data ilə 83,2% ✓, sadəcə göstərilmir.

---

## 6. Növbəti addım

**2-ci ekran** («İllik işçi tədris planı») hələ hazırlanır — hazır olanda eyni sərtliklə
yoxlayacağam.

Bu ekran üçün Claude Design-a veriləcək düzəliş siyahısı: **P0 iki bənd + P1-in 1, 2, 3, 5, 7
bəndləri**. Qalanları istehsalat koduna çevirərkən həll edilə bilər.

Ən vacib bir cümlə: **prerekvizit yoxlaması və kredit hədəfi düzəldilməsə, ekran səhv planı
təsdiqə buraxır** — qalan hər şey kosmetikadır.
