# ChatGPT-yə veriləcək yoxlama promptu

> **Qeyd:** Bu maşında ChatGPT/Codex CLI quraşdırılmayıb və Chrome uzantısı qoşulu deyil —
> ona görə mən özüm göndərə bilmirəm. Aşağıdakı «────» xəttindən sonrakı hissəni kopyalayıb
> ChatGPT-yə ver, cavabı mənə qaytar — mən onu bizim tapıntılarla tutuşdurub fərqləri hesabat
> edəcəyəm.
>
> **Faylları da əlavə et:** `docs/workload/TEDRIS_PROSESI_TAM_AXIN.md`,
> `docs/workload/TEDRIS_PLANI_SPEC.md`, `docs/workload/DERS_YUKU_SPEC.md`.

────────────────────────────────────────────────────────────────────────

Sən Azərbaycan ali təhsil sisteminin tədris prosesi və universitet ERP arxitekturası üzrə
ekspert-auditorsan. Sənə bir universitet idarəetmə sistemi (EMSArena) üçün hazırlanmış üç sənəd
verilir: (1) Azərbaycan universitetlərində tədris prosesinin tam illik axını, (2) tədris planı
modulunun spesifikasiyası, (3) dərs yükü modulunun spesifikasiyası.

Bu sənədlər Azərbaycan normativ aktları (NK №75, №117, №215, №242, №348; ETN Kollegiya qərarları
KQ-02/2024 və KQ-12/2024; TN №59, №113, №401) və real universitet sənədləri əsasında hazırlanıb.

## Tapşırığın

**1. NORMATİV DOĞRULUQ AUDİTİ.** Sənəddəki hər normativ iddianı yoxla. Xüsusilə bunları:
- 1 AKTS krediti = 30 saat; həftəlik ümumi yük 45 saat = 1,5 kredit (NK 348 b. 3.2.2)
- Semestr 20 həftə (5-i imtahan sessiyası) → nəzəri təlim 15 həftə; qiyabi 16 həftə
- Əyani semestr 30 kredit, qiyabi 24, maksimum 40, yay semestri ≤10
- Bakalavriat 240–300 kredit, magistratura 120
- Seçmə fənlər ümumi saatın 25–30%-i; humanitar fənlər 15–20% (NK 117 b. 2.23–2.24)
- Auditoriya/sərbəst iş nisbətinin qanunla sabitlənmədiyi; köhnə 1:1 qaydasının ləğv edildiyi
- Sərbəst işin ≥40%-inin müəllim rəhbərliyi ilə (MRTSİ) olması
- Tədris qruplarında 15–30 nəfər; 30-dan az olduqda bölünmə aparılmaması (NK 75 §8.8)
- Mühazirədə qrupların birləşdirilməsi şərtləri: eyni kredit + eyni məzmun
- KQ-12: «1 akademik saat üçün 1 qrupa (qrup birləşməsinə) 1 saat»
- 1 ştat illik yük ≥500 saat, auditoriya payı ≥60% (NK 215); ≤1,5 ştat; ≤250 saat saathesabı
- Kənardan cəlb olunanların payı ≤ ümumi yükün 20%-i (istisna 30%)
- Fərdi tədris planı: 5–15 iyul təqdim, 10 sentyabra qədər düzəliş, sonra qadağan (NK 348 b. 3.3.1–3.3.2)
- Fənnə yetərli tələbə yığılmazsa illik işçi tədris planına daxil edilməməsi (b. 3.3.3)
- Tədris ilinin 15 sentyabrda başlaması (NK 117 b. 2.9)
- «Təkrar kursda saxlanılma» institutunun KQ-02 (2024) ilə ləğv edilməsi
- Bərpada semestr paritetliyi (payızda xaric → yalnız növbəti payızda bərpa)

Hər biri üçün de: **TƏSDİQ / SƏHV / DƏYİŞİB / TAPMADIM** + düzgün variant + mənbə.
Qüvvədən düşmüş və ya sonradan dəyişdirilmiş bəndləri xüsusi qeyd et.

**2. BOŞLUQ AUDİTİ.** Sənəddə əskik qalan nə var? Konkret olaraq:
- Tədris prosesinin hansı mərhələsi ümumiyyətlə əhatə olunmayıb?
- Hansı normativ tələb sistemə çıxarılmalı idi, amma çıxarılmayıb?
- Qiyabi, distant, ikinci ali təhsil, əlavə təhsil, hazırlıq kursları — bunların fərqləri
  düzgün nəzərə alınıbmı?
- Tibb təhsilinin xüsusi rejimi (NK 348-də ayrıca) nəzərə alınıbmı?
- Hərbi/xüsusi təyinatlı ali təhsil müəssisələrinin fərqləri?

**3. PROSES MƏNTİQİ AUDİTİ.** Təsvir olunan axını real universitet praktikası ilə tutuşdur:
```
Kafedra tədris planını yazır → Fakültə metodiki komissiyası → Fakültə Elmi Şurası
→ Tədris şöbəsi (uzlaşdırma + prorektor imzası) → Universitet Elmi Şurası → Rektor
→ İllik işçi tədris planı (tələbə sayları ilə) → Dekanlıq təsdiqi
→ Tədris şöbəsi kafedra tapşırıqlarını generasiya edir → Dekanlıq (dekan + koordinator) təsdiqi
→ Kafedra müdiri müəllimlərə bölür → Müəllim öz yükünü görür
```
- Bu ardıcıllıq düzgündürmü? Hansı addım əskikdir, hansı artıqdır, hansının yeri səhvdir?
- Real universitetlərdə bu proses nə qədər fərqlənir?
- Hansı addımda ən çox gecikmə/münaqişə yaranır?

**4. HESABLAMA DÜSTURU AUDİTİ.** Sənəddə iddia olunur ki:
```
mühazirə cəmi     = mühazirə plan × BİRLƏŞMƏ (mühazirə axını) sayı
seminar cəmi      = seminar plan  × YARIMQRUP sayı
laboratoriya cəmi = lab plan      × YARIMQRUP sayı
sətir CƏMİ        = bütün «cəmi» sütunlarının cəmi
```
Bu düstur real «Tapşırıq» sənədinin 855 sətrində yoxlanılıb (uyğunluq 100%/99,2%/98,7%/100%)
və KQ-12-nin «1 qrupa (qrup birləşməsinə) 1 saat» qaydası ilə uzlaşır.
- Düstur düzgündürmü? İstisna halları varmı (fərdi dərslər, incəsənət ixtisasları, tibb,
  klinik məşğələlər, xarici dil, idman)?
- Məsləhət, imtahan, buraxılış rəhbərliyi, doktorant rəhbərliyi, təcrübə saatları hansı
  düsturla hesablanır?

**5. ERP DİZAYN TƏNQİDİ.** Sənəddəki model qərarlarını qiymətləndir:
- Kreditin `Subject`-dən `CurriculumSubject`-ə köçürülməsi (eyni fənn ixtisasa görə fərqli
  kredit daşıyır) — düzgün qərardırmı?
- Aqreqatlarda kreditin «təkrarsız fənn üzrə» sayılması qaydası
- «Hesablama vahidi» anlayışı: `axın | qrup | yarımqrup | fərdi`
- Fakültə dilimləri ilə təsdiq (xidməti tədris səbəbindən)
- `AnnualWorkingPlan` (illik işçi tədris planı) ayrıca model kimi
- Nə əlavə etmək, nə sadələşdirmək lazımdır?

**6. RƏQABƏT VƏ RİSK.** Azərbaycanda UNEC EDUMAN, Unibook, ADA Banner, AzTU UİS mövcuddur.
İddia olunur ki, heç birində «kafedra tapşırığı → yük bölgüsü → fərdi iş planı → icra hesabatı»
zənciri yoxdur. Bu doğrudurmu? Bildiyin başqa sistem varmı? Bu modulun real bazar dəyəri nədir?

## Cavab formatı

Markdown. Hər bölmə üçün ayrıca başlıq. Səhv tapdığın hər yerdə: **iddia → düzgün variant →
mənbə**. Əmin olmadığın yerdə açıq «əmin deyiləm» yaz — uydurma mənbə vermə. Sonda **ən kritik
5 düzəliş** siyahısı ver.
