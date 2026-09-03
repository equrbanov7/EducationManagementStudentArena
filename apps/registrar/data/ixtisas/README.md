# Rəsmi ixtisas şifri kataloqları

Bu qovluq **rəsmi dövlət mənbələrindən** çıxarılmış ixtisas təsnifatlarını və
WCU proqramlarının onlara uyğunlaşdırılmasını saxlayır. Fayllar
`python manage.py set_program_official_codes` komandasının yeganə data mənbəyidir
— komanda scratchpad-dan və ya internetdən **asılı deyil**, ona görə repetisiya
bazası yenidən qurulanda təkrar işlədilə bilir.

## Fayllar

| Fayl | Mənbə sənəd | Sətir |
|---|---|---:|
| `catalog_2024.tsv` | **NK 503**, 02.12.2024 — «Təhsil pillələri üzrə ixtisasların (proqramların) təsnifatı». NK **109**, 17.04.2026 düzəlişi daxildir (e-qanun 58365, 61684) | 329 |
| `catalog_legacy_bachelor.tsv` | e-qanun **16051** — əvvəlki nəsil bakalavr təsnifatı (`050XXX`) | 169 |
| `catalog_legacy_master.tsv` | e-qanun **21781** — əvvəlki nəsil magistratura təsnifatı (`060XXX`) | 202 |
| `program_codes.tsv` | WCU-nun 101 proqramının hər iki nəslə uyğunlaşdırılması | 101 |

`catalog_2024.tsv` bölgüsü: bakalavr 154 · baza ali tibb 3 · magistratura 129 ·
rezidentura 43 = **329**. NK 109 (17.04.2026) yalnız bir ixtisas əlavə edir —
`6006046` «Daşınmaz əmlakın idarə olunması» — və o, artıq kataloqdadır
(e-qanun konsolidə mətni).

## Şifr formatları

| Nəsil | Bakalavr | Magistratura |
|---|---|---|
| CARİ (NK 503/2024) | `6XXXXXX` (7 rəqəm) | `7XXXXXX` (7 rəqəm) |
| ƏVVƏLKİ | `050XXX` | `060XXX` |

İki nəslin şifr fəzaları kəsişmir, ona görə şifrə baxıb hansı təsnifata aid
olduğunu birmənalı demək olur.

## `program_codes.tsv` sütunları

| Sütun | Məna |
|---|---|
| `daxili_kod` | `Program.code` — sətri tapmaq üçün DAXİLİ açar, dəyişdirilmir |
| `ad` | `Program.name` — kor-koranə UPDATE-in qarşısını alan yoxlama |
| `seviyye` | `bachelor` / `master` |
| `kohne_kod` · `kohne_ad` | əvvəlki nəsil şifr; ixtisas yalnız 2024-də varsa boş |
| `cari_kod` · `cari_ad` | NK 503 şifri; ixtisas ləğv olunubsa boş |
| `eminlik` | `dəqiq` · `yüksək` · `şübhəli` · `tapılmadı` |
| `qeyd` | əsaslandırma / namizədlər |

**Əminlik** dərəcələri:

* `dəqiq` (72) — ad kataloqda hərfi var. Yazılır.
* `yüksək` (14) — ixtisas eynidir, amma **adı rəsmən dəyişib**
  (`050624` «Cihazqayırma mühəndisliyi` → `6006004` «Cihaz mühəndisliyi»). Yazılır.
* `şübhəli` (7) — bir neçə real namizəd var, seçim **sahibindir**. Yazılmır.
* `tapılmadı` (8) — sətir ixtisas DEYİL («Level», «aaa», «Kollec» …). Yazılmır.

## Dəyişiklik qaydası

Bu fayllara əl ilə şifr **əlavə edilə bilməz**: `_program_official_codes.validate()`
hər icrada emissiya olunan hər şifrin (1) kataloqda mövcud olduğunu,
(2) kataloqdakı adının fayldakı adla eyni olduğunu, (3) pilləyə uyğun
prefiks daşıdığını tələb edir. Pozuntu olarsa komanda **heç nə yazmadan**
dayanır. Kataloqda olmayan şifr yazmaq istəyirsinizsə, əvvəlcə kataloq faylını
rəsmi sənədə əsasən yeniləyin.

Yoxlamanı `apps/registrar/tests/test_program_official_codes.py` kilidləyir.

## Nə üçün bu qədər ciddiyyət

Bu datanın əvvəlki, **əl ilə yığılmış** variantında 5 şifrdən 2-si səhv idi
(`MYEDU-40` «İqtisadiyyat» → `050405`, əslində «Sənayenin təşkili»;
`MYEDU-43` «Maliyyə» → `050406`, əslində «Statistika») — hər ikisi «iki
müstəqil mənbə ilə təsdiqlənib» qeydi ilə. Şifri təsnifatın ÖZÜ ilə
tutuşdurmadan heç bir mənbə kifayət deyil.
