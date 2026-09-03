# İxtisas şifrləri — nə dəyişdi, nə qaldı

> **Sahibin tələbi:** «İxtisasın yanında ixtisas kodları olsun gərək, bunu **hər
> kəs görə bilməlidi**; indiki ixtisas kodları uydurmadı deyəsən.» →
> «Burda **yeni və köhnə** kodlar var, **bunları da əlavə et**.»

Bu sənəd nəyin dəyişdiyini, hansı proqramın hansı şifri aldığını və **sənin
qərarını gözləyən 15 sətri** göstərir.

---

## 1. Problem nə idi

Bazadakı 101 proqramın şifr vəziyyəti köçürmədən sonra belə idi:

| Vəziyyət | Say |
|---|---:|
| Uydurma `MYEDU-NN` kodu (köçürmənin daxili açarı) | **73** |
| Rəqəmli görünən kod | 28 |
| …onlardan **tamam başqa ixtisası göstərən** | **25** |
| …doğru olan | **3** |

Yəni ekranda göstərilən şifrlərin demək olar hamısı yanlış idi. Bir neçə nümunə:

| Bizdə yazılmışdı | Həmin şifr rəsmi təsnifatda əslində |
|---|---|
| `050501` Biologiya | **Riyaziyyat** |
| `050504` Ekologiya | **Kimya** |
| `050620` Kompüter Mühəndisliyi | **Dəniz naviqasiyası mühəndisliyi** |
| `050615` İnformasiya Təhlükəsizliyi | **Hava nəqliyyatının hərəkətinin idarə olunması mühəndisliyi** |
| `050118` Təhsildə sosial-psixoloji xidmət | **İbtidai sinif müəllimliyi** |
| `050604` Cihaz Mühəndisliyi | **Geofizika mühəndisliyi** |

Magistratura proqramları `050XXX-M` daşıyırdı — rəsmi magistratura təsnifatı
`060XXX`-dir, yəni o şifrlər **ümumiyyətlə mövcud deyildi**.

Doğru çıxan 3 şifr: `050624` Cihazqayırma, `050629` Mexatronika, `060411`
Kommersiya.

---

## 2. Nə dəyişdi

### 2.1 Model — İKİ şifr sütunu

Azərbaycanda ixtisas təsnifatı **2024-cü ildə tam dəyişib**, ona görə bir sütun
kifayət etmir:

| Sütun | Nə saxlayır | Format |
|---|---|---|
| `official_code` | **CARİ** təsnifat — NK 503 (02.12.2024), NK 109 (17.04.2026) düzəlişi ilə | `6XXXXXX` bakalavr · `7XXXXXX` magistr |
| `legacy_official_code` | **ƏVVƏLKİ** nəsil — köhnə tələbələrin **diplomundakı** şifr | `050XXX` bakalavr · `060XXX` magistr |

**Niyə hər ikisi saxlanılır** (bir sütuna yığmaq məlumat itirir):

* ixtisas **ləğv olunub** → köhnə şifr var, yenisi yoxdur (`050401` «Dünya
  iqtisadiyyatı», `060411` «Kommersiya»);
* ixtisas **yenidir** → yeni şifr var, köhnəsi yoxdur (`6006017` «İnformasiya
  təhlükəsizliyi»);
* ixtisas **bölünüb** (`050810` «Turizm və otelçilik» → `6008007` + `6008008`);
* ixtisasın **adı dəyişib** (`050624` «Cihazqayırma mühəndisliyi» → `6006004`
  «Cihaz mühəndisliyi»).

Üstəlik hazırda oxuyan tələbələrin diplom və arayışlarında məhz köhnə şifr
yazılıb — onu silmək sənədlə bazanı ziddiyyətə salardı.

> **Daxili `code` (`MYEDU-*`) toxunulmadı.** O, köçürmə xəttinin indeks açarıdır
> və istifadəçiyə heç vaxt göstərilmir.

### 2.2 Göstərmə qaydası

| Etiket | Nəticə | Harada |
|---|---|---|
| `display_label` | `Ad · 6006004` | siyahı, açılan menyu, cədvəl |
| `display_label_full` | `Ad · 6006004 · köhnə 050624` | transkript, profil kartı |
| `official_code_pair` | `6006004 · köhnə 050624` | şifr nişanı |

Cari şifri olmayan (ləğv olunmuş) ixtisas **şifrsiz qalmır** — etiket köhnə
şifrə geri çəkilir. Şifr ümumiyyətlə yoxdursa ayırıcı da yazılmır (asılı qalmış
«Ad · » quyruğu olmur).

---

## 3. Rəqəmlər

| | Say |
|---|---:|
| Bazadakı proqram | 101 |
| **Şifr yazıldı** | **86** |
| …hər iki nəslin şifri ilə | 76 |
| …yalnız köhnə şifr (yeni təsnifatda ləğv) | 6 |
| …yalnız cari şifr (köhnə təsnifatda yox idi) | 4 |
| **Boş qaldı — sənin qərarın** | **7** |
| **Boş qaldı — ixtisas deyil** | **8** |
| Yazılan şifr dəyəri (cəmi) | 162 |
| Düzəldilən səhv şifr | 26 |

---

## 4. SƏNİN QƏRARINI GÖZLƏYƏN 7 İXTİSAS

Bunlara şifr **yazılmayıb**, çünki bir neçə real namizəd var və seçim
məzmun qərarıdır, texniki qərar deyil.

| Daxili kod | İxtisas | Pillə | Cari şifr (NK 503) | Köhnə şifr |
|---|---|---|---|---|
| `MYEDU-25` | Azərbaycan dili və ədəbiyyatı | bakalavr | 6002006 | 050201 |
| `MYEDU-77` | Maliyyə nəzarəti və auidit | bakalavr | — | 050403 |
| `MYEDU-45` | Turizm və otelçilik | bakalavr | — | 050810 |
| `MYEDU-84` | İqtisadiyyatın tənzimlənməsi (ingilis) | bakalavr | — | 050404 |
| `MYEDU-89-M` | Akvabioresurslar | magistr | 7005013 | 060709 |
| `MYEDU-72-M` | Məhkəmə psixologiyası | magistr | 7002013 | 060209 |
| `MYEDU-73-M` | Ümumi idarəetmə | magistr | — | — |

### MYEDU-25 — «Azərbaycan dili və ədəbiyyatı» (bakalavr)

Ad 'müəllimliyi'siz — Filologiya kimi oxunur. ALTERNATİV: 050101/6001001 (Az. dili və ədəbiyyatı müəllimliyi). SAHİB SEÇSİN.

### MYEDU-45 — «Turizm və otelçilik» (bakalavr)

Yeni təsnifatda BÖLÜNÜB: 6008007 Turizm bələdçiliyi / 6008008 Turizm işinin təşkili. Bakalavrda 'Turizm və otelçilik' YOXDUR. SAHİB SEÇSİN.

### MYEDU-72-M — «Məhkəmə psixologiyası» (magistr)

'Məhkəmə psixologiyası' rəsmi ixtisaslaşma adı deyil. NAMİZƏDLƏR: 060209 Psixologiya ('Hüquq psixologiyası') / 060212 Hüquqşünaslıq. SAHİB SEÇSİN.

### MYEDU-73-M — «Ümumi idarəetmə» (magistr)

'Ümumi idarəetmə' rəsmi adda yoxdur. NAMİZƏDLƏR: 060407 Menecment ('Strateji idarəetmə') / 060409 Biznesin idarə edilməsi / 060410 Dövlət və bələdiyyə idarəetməsi. SAHİB SEÇSİN.

### MYEDU-77 — «Maliyyə nəzarəti və auidit» (bakalavr)

Bu, magistratura İXTİSASLAŞMASININ adıdır (060403 Maliyyə → 'Maliyyə nəzarəti və audit'). Bakalavrda qarşılığı yoxdur. NAMİZƏDLƏR: 050403 Maliyyə / 050402 Mühasibat uçotu və audit. SAHİB SEÇSİN.

### MYEDU-84 — «İqtisadiyyatın tənzimlənməsi (ingilis)» (bakalavr)

Bu, magistratura İXTİSASLAŞMASININ adıdır (060404 → 'İqtisadiyyatın tənzimlənməsi'). Bakalavrda qarşılığı yoxdur. SAHİB TƏSDİQLƏSİN.

### MYEDU-89-M — «Akvabioresurslar» (magistr)

'Akvabioresurslar' rəsmi adda yoxdur; 060709 'Su bioehtiyatları' ixtisaslaşmasına uyğun gəlir. ALTERNATİV: 060707 Balıqçılıq. SAHİB SEÇSİN.


**MYEDU-77 və MYEDU-84 struktur problemidir:** hər ikisi **magistratura
ixtisaslaşmasının** adıdır, amma bazada **bakalavr** kimi qeyd olunub.
Şifr seçməzdən əvvəl pillənin özü düzəldilməlidir.

---

## 5. Şifr VERİLMƏYƏN 8 sətir — ixtisas deyil

Bunlar struktur/test qeydləridir. Şifr verilmir; silinmir də.

| Daxili kod | İxtisas | Pillə | Cari şifr (NK 503) | Köhnə şifr |
|---|---|---|---|---|
| `MYEDU-66` | Dizayn Məktəbi | bakalavr | — | — |
| `MYEDU-92` | Kollec | bakalavr | — | — |
| `MYEDU-101` | Kollec 2 | bakalavr | — | — |
| `MYEDU-61` | Level | bakalavr | — | — |
| `MYEDU-91` | Lifelong | bakalavr | — | — |
| `MYEDU-65` | aaa | bakalavr | — | — |
| `MYEDU-91-M` | Lifelong | magistr | — | — |
| `MYEDU-36-M` | Magistratura və doktorantura | magistr | — | — |

---

## 6. Yeni təsnifatda LƏĞV edilən ixtisaslar

Köhnə şifr yazıldı, cari şifr **qəsdən boş**. Hər biri kataloqda açar sözlə
yoxlanıldı.

| Daxili kod | İxtisas | Pillə | Cari şifr (NK 503) | Köhnə şifr |
|---|---|---|---|---|
| `MYEDU-41` | Dünya iqtisadiyyatı | bakalavr | — | 050401 |
| `MYEDU-12` | Meşə materiallarının və ağac emalının texnologiyası mühəndisliyi | bakalavr | — | 050639 |
| `MYEDU-13` | Poliqrafiya mühəndisliyi | bakalavr | — | 050645 |
| `MYEDU-52` | Sənayenin təşkili və idarə edilməsi | bakalavr | — | 050405 |
| `MYEDU-51` | İstehlak mallarının ekspertizası və marketinqi | bakalavr | — | 050644 |
| `060411-M` | Elektron kommersiya | magistr | — | 060411 |

## 7. Köhnə təsnifatda OLMAYAN (yeni) ixtisaslar

| Daxili kod | İxtisas | Pillə | Cari şifr (NK 503) | Köhnə şifr |
|---|---|---|---|---|
| `MYEDU-53` | Beynəlxalq ticarət və logistika | bakalavr | 6004001 | — |
| `050809` | Turizm bələdçiliyi | bakalavr | 6008007 | — |
| `MYEDU-49` | Turizm işinin təşkili | bakalavr | 6008008 | — |
| `050615` | İnformasiya Təhlükəsizliyi | bakalavr | 6006017 | — |

## 8. Adı rəsmən DƏYİŞƏN ixtisaslar

Ekranda artıq **yeni** ad deyil, bazadakı ad göstərilir — amma şifr yeni
təsnifatın şifridir. Adları da yeniləmək istəsən, ayrıca qərardır.

| Daxili kod | İxtisas | Pillə | Cari şifr (NK 503) | Köhnə şifr |
|---|---|---|---|---|
| `050604` | Cihaz Mühəndisliyi | bakalavr | 6006004 | 050624 |
| `050403` | Davamlı inkişafın idarə edilməsi | bakalavr | 6002002 | 050412 |
| `MYEDU-67` | Davamlı inkişafın idarə edilməsi | bakalavr | 6002002 | 050412 |
| `MYEDU-48` | Mühasibat | bakalavr | 6004008 | 050402 |
| `MYEDU-68` | Qida mühəndisliyi | bakalavr | 6006023 | 050642 |
| `050708` | Su Bioehtiyyatları və Akvakultura | bakalavr | 6005013 | 050709 |
| `MYEDU-52` | Sənayenin təşkili və idarə edilməsi | bakalavr | — | 050405 |
| `MYEDU-30` | İngilis dili və ədəbiyyatı müəllimliyi | bakalavr | 6001007 | 050103 |
| `MYEDU-87-M` | Beynəlxalq turizm | magistr | 7008004 | 060803 |
| `050708-M` | Su Bioehtiyyatları və Akvakultura | magistr | 7005013 | 060709 |
| `MYEDU-49-M` | Turizm işinin təşkili | magistr | 7008004 | 060803 |
| `MYEDU-69-M` | Turizm və hotelçiliyin idarə edilməsi | magistr | 7008004 | 060803 |
| `MYEDU-85-M` | İdarəetmədə informasiya sistemləri və şəbəkələri | magistr | 7006016 | 060632 |
| `050616-M` | İnformasiya Texnologiyaları | magistr | 7006016 | 060632 |

---

## 9. Şifri DÜZƏLDİLƏN 26 proqram

Bunlarda əvvəllər tamam başqa ixtisasın şifri yazılmışdı.

| Daxili kod | İxtisas | Pillə | Cari şifr (NK 503) | Köhnə şifr |
|---|---|---|---|---|
| `050501` | Biologiya | bakalavr | 6005001 | 050505 |
| `050604` | Cihaz Mühəndisliyi | bakalavr | 6006004 | 050624 |
| `050403` | Davamlı inkişafın idarə edilməsi | bakalavr | 6002002 | 050412 |
| `050504` | Ekologiya | bakalavr | 6005004 | 050510 |
| `050501-63` | Ekologiya Mühəndisliyi | bakalavr | 6006007 | 050649 |
| `050204` | Fəlsəfə | bakalavr | 6002005 | 050202 |
| `050620` | Kompüter Mühəndisliyi | bakalavr | 6006022 | 050631 |
| `050628` | Mexanika mühəndisliyi | bakalavr | 6006028 | 050630 |
| `MYEDU-12` | Meşə materiallarının və ağac emalının texnologiyası mühəndisliyi | bakalavr | — | 050639 |
| `050706` | Meşəçilik | bakalavr | 6007007 | 050708 |
| `050211` | Psixologiya | bakalavr | 6002013 | 050209 |
| `050212` | Regionşünaslıq | bakalavr | 6002014 | 050211 |
| `050807` | Sosial Iş | bakalavr | 6008006 | 050813 |
| `050708` | Su Bioehtiyyatları və Akvakultura | bakalavr | 6005013 | 050709 |
| `050214` | Tarix | bakalavr | 6002016 | 050206 |
| `050809` | Turizm bələdçiliyi | bakalavr | 6008007 | — |
| `050118` | Təhsildə sosial psixoloji xidmət | bakalavr | 6001021 | 050121 |
| `050616` | İnformasiya Texnologiyaları | bakalavr | 6006016 | 050655 |
| `050615` | İnformasiya Təhlükəsizliyi | bakalavr | 6006017 | — |
| `050501-M` | Biologiya | magistr | 7005001 | 060505 |
| `050504-M` | Ekologiya | magistr | 7005004 | 060510 |
| `050620-M` | Kompüter Mühəndisliyi | magistr | 7006022 | 060631 |
| `050211-M` | Psixologiya | magistr | 7002013 | 060209 |
| `050708-M` | Su Bioehtiyyatları və Akvakultura | magistr | 7005013 | 060709 |
| `050214-M` | Tarix | magistr | 7002016 | 060206 |
| `050616-M` | İnformasiya Texnologiyaları | magistr | 7006016 | 060632 |

---

## 10. Tam siyahı — yazılan 86 şifr

| Daxili kod | İxtisas | Pillə | Cari şifr (NK 503) | Köhnə şifr |
|---|---|---|---|---|
| `MYEDU-29` | Azərbaycan dili və ədəbiyyatı müəllimliyi | bakalavr | 6001001 | 050101 |
| `MYEDU-17` | Beynəlxalq Münasibətlər (Tədris Ingilis Dilində) | bakalavr | 6002001 | 050213 |
| `MYEDU-18` | Beynəlxalq münasibətlər | bakalavr | 6002001 | 050213 |
| `MYEDU-53` | Beynəlxalq ticarət və logistika | bakalavr | 6004001 | — |
| `050501` | Biologiya | bakalavr | 6005001 | 050505 |
| `MYEDU-42` | Biznesin idarə edilməsi | bakalavr | 6004002 | 050409 |
| `050604` | Cihaz Mühəndisliyi | bakalavr | 6006004 | 050624 |
| `050624` | Cihazqayırma mühəndisliyi | bakalavr | 6006004 | 050624 |
| `050403` | Davamlı inkişafın idarə edilməsi | bakalavr | 6002002 | 050412 |
| `MYEDU-67` | Davamlı inkişafın idarə edilməsi | bakalavr | 6002002 | 050412 |
| `MYEDU-56` | Dizayn (Qrafik) | bakalavr | 6003005 | 050321 |
| `MYEDU-35` | Dizayn (İnteryer) | bakalavr | 6003005 | 050321 |
| `MYEDU-50` | Dövlət və bələdiyyə idarəetməsi | bakalavr | 6004003 | 050410 |
| `MYEDU-41` | Dünya iqtisadiyyatı | bakalavr | — | 050401 |
| `050504` | Ekologiya | bakalavr | 6005004 | 050510 |
| `050501-63` | Ekologiya Mühəndisliyi | bakalavr | 6006007 | 050649 |
| `MYEDU-26` | Filologiya (İngilis dili və ədəbiyyatı) | bakalavr | 6002006 | 050201 |
| `050204` | Fəlsəfə | bakalavr | 6002005 | 050202 |
| `050620` | Kompüter Mühəndisliyi | bakalavr | 6006022 | 050631 |
| `MYEDU-62` | Kompüter elmləri | bakalavr | 6005009 | 050509 |
| `MYEDU-43` | Maliyyə | bakalavr | 6004005 | 050403 |
| `MYEDU-47` | Marketinq | bakalavr | 6004006 | 050408 |
| `MYEDU-44` | Menecment | bakalavr | 6004007 | 050407 |
| `050628` | Mexanika mühəndisliyi | bakalavr | 6006028 | 050630 |
| `050629` | Mexatronika və robototexnika mühəndisliyi | bakalavr | 6006029 | 050629 |
| `MYEDU-12` | Meşə materiallarının və ağac emalının texnologiyası mühəndisliyi | bakalavr | — | 050639 |
| `050706` | Meşəçilik | bakalavr | 6007007 | 050708 |
| `MYEDU-48` | Mühasibat | bakalavr | 6004008 | 050402 |
| `MYEDU-46` | Mühasibat uçotu və audit | bakalavr | 6004008 | 050402 |
| `MYEDU-13` | Poliqrafiya mühəndisliyi | bakalavr | — | 050645 |
| `MYEDU-14` | Politologiya | bakalavr | 6002012 | 050208 |
| `MYEDU-15` | Politologiya (Tədris Ingilis Dilində) | bakalavr | 6002012 | 050208 |
| `050211` | Psixologiya | bakalavr | 6002013 | 050209 |
| `MYEDU-68` | Qida mühəndisliyi | bakalavr | 6006023 | 050642 |
| `050212` | Regionşünaslıq | bakalavr | 6002014 | 050211 |
| `050807` | Sosial Iş | bakalavr | 6008006 | 050813 |
| `050708` | Su Bioehtiyyatları və Akvakultura | bakalavr | 6005013 | 050709 |
| `MYEDU-52` | Sənayenin təşkili və idarə edilməsi | bakalavr | — | 050405 |
| `050214` | Tarix | bakalavr | 6002016 | 050206 |
| `MYEDU-20` | Tarix (Tədris Ingilis Dilində) | bakalavr | 6002016 | 050206 |
| `MYEDU-24` | Tarix müəllimliyi | bakalavr | 6001018 | 050113 |
| `050809` | Turizm bələdçiliyi | bakalavr | 6008007 | — |
| `MYEDU-49` | Turizm işinin təşkili | bakalavr | 6008008 | — |
| `050118` | Təhsildə sosial psixoloji xidmət | bakalavr | 6001021 | 050121 |
| `MYEDU-27` | Tərcümə | bakalavr | 6002017 | 050203 |
| `MYEDU-28` | Tərcümə (Dillər üzrə) | bakalavr | 6002017 | 050203 |
| `050616` | İnformasiya Texnologiyaları | bakalavr | 6006016 | 050655 |
| `050615` | İnformasiya Təhlükəsizliyi | bakalavr | 6006017 | — |
| `MYEDU-30` | İngilis dili və ədəbiyyatı müəllimliyi | bakalavr | 6001007 | 050103 |
| `MYEDU-40` | İqtisadiyyat | bakalavr | 6004004 | 050404 |
| `MYEDU-51` | İstehlak mallarının ekspertizası və marketinqi | bakalavr | — | 050644 |
| `MYEDU-17-M` | Beynəlxalq Münasibətlər (Tədris Ingilis Dilində) | magistr | 7002001 | 060213 |
| `MYEDU-18-M` | Beynəlxalq münasibətlər | magistr | 7002001 | 060213 |
| `MYEDU-88-M` | Beynəlxalq münasibətlər və diplomatiya | magistr | 7002001 | 060213 |
| `MYEDU-87-M` | Beynəlxalq turizm | magistr | 7008004 | 060803 |
| `050501-M` | Biologiya | magistr | 7005001 | 060505 |
| `MYEDU-42-M` | Biznesin idarə edilməsi | magistr | 7004002 | 060409 |
| `MYEDU-56-M` | Dizayn (Qrafik) | magistr | 7003005 | 060321 |
| `MYEDU-35-M` | Dizayn (İnteryer) | magistr | 7003005 | 060321 |
| `050504-M` | Ekologiya | magistr | 7005004 | 060510 |
| `060411-M` | Elektron kommersiya | magistr | — | 060411 |
| `MYEDU-86-M` | Genetika | magistr | 7005001 | 060505 |
| `MYEDU-81-M` | Klinik psixologiya | magistr | 7002013 | 060209 |
| `MYEDU-82-M` | Klinik psixologiya (ing) | magistr | 7002013 | 060209 |
| `MYEDU-79-M` | Komputer sistemləri və şəbəkələri | magistr | 7006022 | 060631 |
| `MYEDU-80-M` | Komputer sistemləri və şəbəkələri (ing) | magistr | 7006022 | 060631 |
| `050620-M` | Kompüter Mühəndisliyi | magistr | 7006022 | 060631 |
| `MYEDU-76-M` | Malekulyar biologiya | magistr | 7005001 | 060505 |
| `MYEDU-43-M` | Maliyyə | magistr | 7004006 | 060403 |
| `MYEDU-77-M` | Maliyyə nəzarəti və auidit | magistr | 7004006 | 060403 |
| `MYEDU-78-M` | Maliyyə nəzarəti və auidit (ingilis) | magistr | 7004006 | 060403 |
| `MYEDU-44-M` | Menecment | magistr | 7004008 | 060407 |
| `MYEDU-71-M` | Orta əsrər tarixi | magistr | 7002016 | 060206 |
| `050211-M` | Psixologiya | magistr | 7002013 | 060209 |
| `MYEDU-75-M` | Qafqaz xalqlarının tarixi | magistr | 7002016 | 060206 |
| `MYEDU-74-M` | Sosial psixologiya | magistr | 7002013 | 060209 |
| `050708-M` | Su Bioehtiyyatları və Akvakultura | magistr | 7005013 | 060709 |
| `050214-M` | Tarix | magistr | 7002016 | 060206 |
| `MYEDU-70-M` | Turizm işi | magistr | 7008004 | 060803 |
| `MYEDU-49-M` | Turizm işinin təşkili | magistr | 7008004 | 060803 |
| `MYEDU-69-M` | Turizm və hotelçiliyin idarə edilməsi | magistr | 7008004 | 060803 |
| `MYEDU-85-M` | İdarəetmədə informasiya sistemləri və şəbəkələri | magistr | 7006016 | 060632 |
| `050616-M` | İnformasiya Texnologiyaları | magistr | 7006016 | 060632 |
| `MYEDU-40-M` | İqtisadiyyat | magistr | 7004005 | 060404 |
| `MYEDU-83-M` | İqtisadiyyatın tənzimlənməsi | magistr | 7004005 | 060404 |
| `MYEDU-90-M` | Ətraf mühitin mühafizə və bərpa metodları | magistr | 7005004 | 060510 |

---

## 11. Mənbə sənədlər

| Sənəd | Nə verir | Say |
|---|---|---:|
| **NK 503**, 02.12.2024 (e-qanun 58365) | cari təsnifat | 329 |
| **NK 109**, 17.04.2026 (e-qanun 61684) | NK 503-ə düzəliş | +1 |
| e-qanun **16051** | köhnə bakalavr `050XXX` | 169 |
| e-qanun **21781** | köhnə magistratura `060XXX` | 202 |

NK 503 bölgüsü: bakalavr 154 · baza ali tibb 3 · magistratura 129 ·
rezidentura 43 = **329**.

**NK 109 yoxlanıldı:** yalnız bir ixtisas əlavə edir — `6006046` «Daşınmaz
əmlakın idarə olunması» — və o, artıq kataloqdadır (konsolidə mətn). Heç bir
WCU proqramı ona uyğun gəlmir.

Kataloqlar repoya köçürülüb: `apps/registrar/data/ixtisas/` (bax oradakı
`README.md`).

---

## 12. Uydurma şifr necə qarşısı alınır

Bu datanın **əvvəlki, əl ilə yığılmış** variantında 5 şifrdən **2-si səhv idi**:

| | Yazılmışdı | Həmin şifr əslində |
|---|---|---|
| `MYEDU-40` «İqtisadiyyat» | `050405` | «Sənayenin təşkili və idarə olunması» |
| `MYEDU-43` «Maliyyə» | `050406` | «Statistika» |

Hər ikisi «iki müstəqil mənbə ilə təsdiqlənib» qeydi daşıyırdı. Dərs budur:
**şifri təsnifatın ÖZÜ ilə tutuşdurmadan heç bir mənbə kifayət deyil.**

İndi əl ilə şifr yazmaq mümkün deyil. Komanda hər icrada emissiya olunan hər
şifr üçün tələb edir:

1. şifr rəsmi kataloqda **mövcuddur**;
2. kataloqdakı **adı** fayldakı adla eynidir;
3. şifrin **pilləsi** uyğundur (`05`↔bakalavr, `06`↔magistr; `6`↔bakalavr,
   `7`↔magistr).

Pozuntu olarsa komanda **heç nə yazmadan** dayanır.

---

## 13. Komanda

`Program.code`-a **toxunmur**, yalnız iki rəsmi şifr sütununa yazır.
**İdempotentdir** — repetisiya bazası yenidən qurulanda təkrar işlədilə bilər.

```bash
python manage.py set_program_official_codes                  # dry-run (DEFOLT)
python manage.py set_program_official_codes --holds          # yazılmayanlar
python manage.py set_program_official_codes --table          # hər proqramın cari vəziyyəti
python manage.py set_program_official_codes --apply          # yazır
python manage.py set_program_official_codes --apply --organization <uuid>
```

Təhlükəsizlik: defolt dry-run · idempotent · fail-closed (ad/pillə uyuşmasa və
ya sətirdə fərqli şifr olsa **heç nə** yazılmır) · hər yazı audit izinə düşür.

Sən 4-cü bölmədəki 7 ixtisasa qərar verdikdən sonra şifrləri
`apps/registrar/data/ixtisas/program_codes.tsv` faylına yazmaq və `eminlik`
sütununu `dəqiq` etmək kifayətdir — komanda qalanını edir.

---

## 14. Harada görünür

| Səth | Nə göstərir |
|---|---|
| Tələbə profili — akademik struktur kartı | hər iki şifr (`official_code_pair`) |
| Tələbə profili — transkript bölməsi | `Ad · cari · köhnə` |
| Transkript **PDF** (rəsmi sənəd) | `Ad · cari · köhnə` |
| Akademik qeydlər cədvəli | `Ad · şifr` + tooltip-də hər ikisi |
| İnsanlar kataloqu (sətir + filtr) | `Ad · şifr` |
| İnsanlar analitikası (ixtisas səbəti) | `Ad · şifr` |
| Registrar konsolu — ixtisas siyahısı | hər iki şifr nişanda |
| Registrar konsolu — ixtisas forması | iki ayrıca sahə |
| Tədris planı (siyahı + detal) | `Ad · şifr` |
| Sillabus (siyahı, baxış, ön baxış, PDF) | `Ad · şifr` |
| Sillabus **redaktoru** — başlıq + kilidli «Təhsil proqramı» sətri | `Ad · şifr` |
| Sillabus təsdiqi — **«Əhatə» tabı** (cədvəl + vahid filtri) | ad + şifr nişanı |
| İmtahan mərkəzi — XLSX hesabatı | `Ad · şifr` |
| Axtarış nəticələri | `Ad · şifr` |
| Django admin (siyahı + axtarış) | hər iki sütun |

Hər səth `display_label` / `display_label_full` / `official_code_pair`
etiketlərindən birini işlədir — heç bir səthdə sahələr əl ilə birləşdirilmir.

**Qayda harada yaşayır.** Formatlaşdırmanın TƏK mənbəyi `core/program_codes.py`-dır
(saf funksiyalar: `program_display_label`, `program_display_label_full`,
`program_official_code_pair`, `program_display_code`). `registrar.Program`-ın
etiket property-ləri ona **deleqasiya** edir. Niyə `core`: `apps.syllabus`
`apps.registrar`-ı idxal EDƏ BİLMƏZ (`registrar → syllabus` tili artıq var,
tərs istiqamət `scripts/module_deps.py`-da dövr olardı), amma «Əhatə» tabının
breakdown-u eyni etiketi qurmalıdır. `values()`/`annotate()` ilə işləyən
səthlər (`people/lookups.py`, `people/students.py`,
`people/analytics_students.py`, `syllabus/services/coverage.py`) model instansı
almadan məhz bu saf funksiyaları çağırır.

---

## 15. Axtarış invariantı

> **Ekranda şifr GÖSTƏRƏN hər səth, həmin şifrlə axtarışı da dəstəkləməlidir.**

### Tərif niyə məhz belədir

Əvvəlki redaksiyada bu bölmə «şifr üzrə axtaran səthlər»i sadalayırdı. Bu,
invariantı **tərsinə** oxumaqdır və məhz o, növbəti blokeri gizlətdi: siyahı
artıq şifr axtaran iki səthdən ibarət idi, ona görə «tam» görünürdü — halbuki
şifri GÖSTƏRƏN, amma axtarmayan səthlər siyahıya heç düşmürdü.

Doğru istiqamət **göstərmədən axtarışa** doğrudur:

1. Səth ekranda şifr çap edirmi? (`display_label`, `display_label_full`,
   `official_code_pair`, `display_code` və ya `program_*` köməkçiləri)
2. Həmin səthin axtarış qutusu varmı?
3. Varsa — o qutu şifri axtarırmı?

**2 = bəli və 3 = xeyr** olan hər sətir BLOKERDİR: istifadəçi eyni qutuda
GÖRDÜYÜ dəyəri yazır və **sıfır** nəticə alır.

`display_code` cari şifr yoxdursa **köhnə** şifrə geri çəkildiyi üçün yalnız
`official_code` üzrə süzmək də kifayət etmir. Ona görə hər şifr axtarışı
`core.program_codes.program_code_search_q()` işlədir — sahə siyahısı
(`PROGRAM_CODE_SEARCH_FIELDS`) etiket qaydası ilə **eyni faylda** saxlanılır ki,
biri dəyişəndə o biri unudulmasın.

### A. Şifr GÖSTƏRƏN + axtarış qutusu OLAN səthlər

Bunların hamısı şifri axtarmalıdır — invariantın faktiki əhatəsi budur.

| Səth | Etiketi quran | Süzgəci quran | Vəziyyət |
|---|---|---|---|
| ⌘K qlobal axtarış — tələbə nəticələri (`base.html`, HƏR səhifədə) | `views/search.py:_student_group` | eyni funksiya | ✅ ad + hər iki şifr |
| İnsanlar kataloqu — «Tələbələr» cədvəli | `services/people/students.py` | `services/people/filters.py:search_q` + `students.py:_program_search_matcher` | ✅ ad + hər iki şifr |
| Akademik qeydlər — ixtisas seçicisi (`records_program_search`) | `views/academic_records.py` | eyni funksiya | ✅ ad + hər iki şifr |
| Sillabus siyahısı (kart + cədvəl) | `views/syllabus/rows.py` | `syllabus/services/queries.py:syllabus_queryset` | ✅ ad + hər iki şifr |
| Sillabus təsdiq növbəsi | `views/syllabus/review_rows.py` | `syllabus/services/queries.py:review_queue` | ✅ ad + hər iki şifr |
| Django admin — `Program`, `Curriculum`, `StudentAcademicRecord` | admin `list_display` | `search_fields` | ✅ ad + hər iki şifr |
| İnsanlar kataloqu — «İxtisas» açılışı | `services/people/lookups.py:_program_options` | brauzerin `<select>` typeahead-i | ✅ süzgəc GÖSTƏRİLƏN mətnin özü üzərindədir (şifr mətnin içindədir) |

### B. Şifr GÖSTƏRƏN, axtarış qutusu OLMAYAN səthlər

Burada invariantın tələbi yoxdur (axtarılacaq qutu yoxdur), amma siyahı
QƏSDƏN saxlanılır: bu səthlərdən birinə sonradan axtarış qutusu əlavə olunsa,
o, dərhal A cədvəlinə keçir və `program_code_search_q` tələb edir.

* Tələbə idarəetmə çekməcəsi — `services/people/academic.py`, `detail.py`
  (⚠️ ad ŞİFRSİZ + şifr AYRICA `program_code` nişanında — bax §15.1)
* Profil «Akademik struktur» kartları — `views/profile/context_builder/_helpers.py`
* Sillabus redaktoru — başlıq sətri + kilidli «Təhsil proqramı» (`views/syllabus/editor.py`)
* Sillabus önizləmə / detal / rəy paneli — `preview.py`, `detail_context.py`, `review_panel.py`
* Transkript PDF (`registrar/transcript_pdf.py`), sillabus PDF (`syllabus/document.py`)
* Tələbənin öz səhifələri — `_my_subjects.html`, `_my_transcript.html`, `_edit_profile.html`
* Dərs cədvəli başlığı — `registrar/partials/_schedule_content.html`
* Registrar konsolu və formaları — `console.html`, `program_form.html`, `curriculum_form.html`, `curriculum_detail.html`
* Analitika bölgüləri — `services/people/analytics_students.py`, `registrar/analytics.py`
* İmtahan mərkəzi XLSX ixracı — `exams/services/final_center/xlsx_report.py`
* Audit `resource_repr` — `registrar/transfer.py`, `status.py`, `set_program_official_codes.py`, `archive_non_program_rows.py`

### 15.1 Şifr İKİ DƏFƏ çap olunmasın

Səth həm birləşmiş etiketi (`display_label` = «Ad · şifr»), həm ayrıca şifr
nişanını (`official_code_pair`) verirsə və UI ikincisini birincinin **içinə**
qoyursa, cari şifr eyni sətirdə iki dəfə çıxır:

```
Kompüter mühəndisliyi · 6006022 [6006022 · köhnə 050631]   ← SINIQ
```

Doğru bölgü — **ad ŞİFRSİZ, şifr yalnız nişanda**
(`views/profile/context_builder/_helpers.py` naxışı):

```
Kompüter mühəndisliyi  [6006022 · köhnə 050631]            ← DOĞRU
```

Yəni: `program_label`/`program` + ayrıca `program_code` cütü verən hər səth
etiket üçün `display_label` YOX, `name` işlədir.

### Ayırıcı qaydası

Şifri (və ya digər parçanı) ayırıcı ilə birləşdirən şablon ayırıcını **öndən**
qoymalıdır, arxadan yox — əks halda boş parçada ayırıcı asılı qalır
(«Dünya iqtisadiyyatı · 050401 · ») və iki boş parçada İKİQAT olur («· ·»).
Bu, nadir hal deyil: köçürülmüş sillabusların əsas kütləsi `period=None` ilə
yaradılır (`syllabus/services/drafts.py:import_migrated_version`).

Python tərəfində əl ilə birləşdirmə ÜMUMİYYƏTLƏ yoxdur — `core.program_codes`
köməkçiləri boş parçada ayırıcı buraxmır.

### Testlər

| Fayl | Nəyi kilidləyir |
|---|---|
| `apps/accounts/tests/test_program_code_search_invariant.py` | İxtisas seçicisi + ⌘K qlobal axtarış: hər `display_label`-dən GÖSTƏRİLƏN şifr çıxarılıb sorğu kimi verilir; həmçinin N+1 büdcəsi və tək-JOIN yoxlaması |
| `apps/accounts/tests/test_people_directory.py` | Kataloq sətrinin etiketi ŞİFRLİ olmalıdır (mutasiya qapısı) + kataloq axtarışı şifri tapır |
| `apps/accounts/tests/test_people_academic.py` | Çekmə/detal: şifr İKİ DƏFƏ çap olunmur (§15.1) |
| `apps/accounts/tests/test_syllabus_editor_render.py` | Redaktor başlığında asılı/ikiqat ayırıcı yoxdur |

MUTASİYA SINAĞI (hamısı təsdiqlənib — düzəliş geri qaytarılanda testlər ÇÖKÜR):

* `PROGRAM_CODE_SEARCH_FIELDS`-dən `legacy_official_code` çıxarılsa;
* `students.py`-də `program_display_label(...)` → `program_name` edilsə;
* `academic.py`/`detail.py`-də `name` → `display_label` qaytarılsa;
* `_syllabus_editor.html`-də ayırıcı yenidən arxadan qoyulsa.
