# Boş jurnal xanaları — kök səbəblər və həll (2026-11-10)

Sahibin istəyi: «Jurnallarda çoxlu boş xana var — səbəbini araşdır, düzgün yolla doldur.» Ekran görüntüsü səviyyə
qrupu jurnalıdır: **E-26 · elementary** (`ff4bbf31-8719-4ac6-93a8-3dc6f90800cb`), dərs tarixləri tam üst-üstə düşür.
Qayda: heç bir qiymət və ya davamiyyət uydurulmur. Xana yalnız köhnə sistemdən (myedu) və ya tələbənin başqa
jurnalındakı EYNİ dərsdən doldurulur. Kollec jurnalları xaricdir.

## 1. Məlumat və metod (yalnız oxu)
- Prod core snapshot 2026-11-10 08:23 UTC (head `177fec85`), şəxsi qovluq:
  `Secret/reaudit-20261109/claude-core-capture-6/current.json`.
- Köhnə sistem: `legacy-source.json` (226 517 nöqtə, 14-cü semestr, 21.10 dump-ı) + `ems-legacy-delta-src` adları.
- Analizator: şəxsi `Secret/empty-cells-20261110/analyze.py`, `classification.json`, `cat_summary.json`.
- Əhatə: Payız 2026/2027-nin aktiv, Kollec olmayan 1 659 açılışı. 2026-11-10-dan əvvəlki hər dərs × ona aid olan
  (lab / seminar alt qrup qaydası) hər qeydiyyatlı tələbə. İlk uyğun kateqoriya qalib gəlir.
- **313 301 aid xana, 20 420 boş (6,5 %), 670 jurnalda.**

## 2. Kateqoriyalar

### A. Etibarlı mənbədən doldurula bilən: 358 xana (+ dedupe ilə aradan qalxan 319)
| Kod | Xana | Jurnal | Mənası | Həll |
|---|---:|---:|---|---|
| B2 eyni fənndə ikinci (boş) aktiv qeydiyyat | 319 | 6 | Tələbənin xanaları legacy «alt qrupdan əlavə» sətrindədir, öz qrup jurnalında isə boş əkiz qeydiyyat da var. 536 MU2 `fa776e7c` (160), `de94fc77` (120) ↔ 536 MU1 `04f5c205` / `7a62f438`. | `dedupe` əməliyyatı (57 qeydiyyat buraxılır). Kod səhvi düzəldilib (§3). |
| F1 eyni dərs tələbənin başqa jurnalında | 116 | 7 | Eyni tələbə, fənn (və ya səviyyə ailəsi), tarix, saat, növ, müəllim; xana aktiv olmayan qeydiyyatdadır. E-39 `a0fe62be` 50, E-25 `650ac066` 48, P-9 `d8c55cae` 7. | `sibling` əməliyyatı (köçürmə). |
| F2 köhnə sistemdə eyni fənn və slotda dəyər | 111 | 24 | 510/6BİEO `2e218a02` 20, 233 İT ing `52bb2904` 13, 135 Sİ ing `d1e7cd77` 11. 11-i köhnə sistemdə boş sətirdir. | `fill_legacy_cells_20261108` planı (100) + sahib qərarı ilə «iştirak» planı (11). |
| F3 köhnə sistemdə fənn adının variantı | 131 | 3 | «Kompüter diaqnostikası» → «Kompüterlərin diaqnostikası» (235 İT ing `740322bb` 129); «Verilənlərin bazası sistemləri» → «Verilənlər bazası sistemləri» (2). | Eyni plan (131); yalnız bu iki ad cütü. |

Planlar (şəxsi, yalnız id): `legacy-fill.json` 231 xana (sha256 `4376c41d…`), `legacy-blank-owner-present.json` 11 xana.

### B. Sahibin baxışı lazımdır: 2 581 xana
- R1 eyni slotda köhnə sistemdə BAŞQA fənn: 1 660 / 113 jurnal (536 T Mikroiqtisadiyyat `378373bb` 206,
  536 T «Turizmə giriş» `6954a200` 166, 135Si-2 `e5c613e4` 132). EMS-dəki dərs saatı/fənni və ya fənn xəritəsi səhvdir.
- R2 eyni fənn, başqa saat: 815 / 59 (535 TB 2 `0b81fc5f` 120).
- R3 eyni gün başqa slotda / başqa müəllimdə xana: 106 / 15 (S-1, E-46, İ-5 səviyyə qrupları).

### C. Düzgün olaraq boş: 5 692 xana
- B1 paralel paylaşılan dərslər (iki müəllim, hər biri öz tələbələrinə): 369 (434 R `dee9eb13`).
- L1 tələbənin öz səviyyə dərsi deyil: 595 / 17.
- L2 sütun ayrılmış tələbələrə aiddir: 868 / 16.
- L3 tələbə dərsdən SONRA əlavə/köçürülüb: 2 877 / 241.
- L4 köhnə sistemdə həmin gün tələbə üçün dərs yox idi: 879 / 45.
- L5 mənbə jurnalı olmayan səviyyə tələbəsi: 104 / 4.

### D. Müəllim yazmayıb, mənbə yoxdur: 11 470 xana
- T1 köhnə dövr dərsi, heç bir qeyd yoxdur: 418 / 16.
- T2 köhnə sistemdə bu fənn üzrə jurnal yoxdur: 2 841 / 185.
- T3 köhnə sistemdə də boşdur: 2 842 / 226 (190-ı yalnız q/b yazılmış sütunlarda).
- T4 yeni sistemdə dərs açılıb, heç yazılmayıb: 1 134 / 40 (51 dərs).
- T5 yeni sistemdə yalnız q/b yazılmış sütun: 696 / 32.
- T6 yeni sistemdə müəllim tələbəni ötürüb: 2 211 / 244.
- T7 səviyyə qrupunun mənbə jurnalında dərs var, xana boş: 1 328 / 23 (115-i yalnız q/b sütunlarında).

**E-26 (ekran görüntüsü):** 129 T7, 32 L1, 1 R1. Müəllim 28.09–16.10 və 26–27.10 tarixlərində yalnız qayıbları
qeyd edib, qalanları boş qoyub; 29–30.10-da TB tələbələri hələ başqa sinifdə idi (rəsmi səviyyə siyahısı 06.11).
Yalnız q/b yazılmış sütunlar cəmi 1 001 xanadır — «boş = iştirak etdi» qaydası sahibin qərarı olmadan tətbiq edilmir.

## 3. Düzəldilmiş kod səhvi
`Importer._confirm_and_enroll` (`apps/workload/services/task_workbook_import.py`) hər yük faylı / Forma 1 / cədvəl
təyinatında qrupun hər tələbəsini qrupun öz jurnalına yazırdı — tələbənin həmin fənni başqa jurnalda keçdiyini
yoxlamadan. 24.10-da təmizlənmiş boş əkizlər bu yolla yenidən yaranırdı (31.10 17:00 — 13, 09.11 21:00 — 21,
23:00 — 23). Yeni `apps/workload/services/enroll_guard.active_elsewhere` `_enroll_own_students` ilə eyni qaydanı
tətbiq edir (sayğac `enrollment_elsewhere_skipped`); `test_load_upload_2026_10_23.py`-dakı reqressiya testi
düzəlişsiz uğursuz olur.

## 4. `fill_empty_cells_20261110` əmri (prod-da işlədilməyib)
`--org qku --actor <superadmin> [--only dedupe|sibling] [--apply] [--undo --batch emptycells-…]`;
prod-data-ops: `command=fill_empty_cells_20261110`, `batch` boş / `dedupe` / `sibling` / `emptycells-…` (undo).
- Defolt dry-run; əhatə: cari semestr, aktiv, bağlı olmayan, Kollec xaric; hər yazı xananın hələ boş olduğunu yoxlayır.
- `dedupe`: məlumatsız yeganə öz-qrup sətrini buraxır (silmir), şərt — xanaları olan tam bir qonaq sətri var.
- `sibling`: yalnız eyni tələbənin aktiv olmayan qeydiyyatından, fənn/ailə + tarix + saat + növ + müəllim uyğun və
  bütün mənbələr razıdırsa köçürür; qayıblar yenidən hesablanır.
- Paket audit sətri; undo yalnız həmin paketin dəyişməmiş xanalarına və buraxılmış sətirlərinə toxunur.
- 03.11 prod nüsxəsində dry-run: 8 s, 449 köçürmə. Testlər: `apps/registrar/tests/test_empty_cells_fill_2026_11_10.py`.

## 5. Prod ardıcıllığı
1. Kod düzəlişini deploy et (növbəti yük faylından əvvəl — əks halda əkizlər yenidən yaranır).
2. `fill_empty_cells_20261110` dry-run (~57 buraxma, ~116 köçürmə), sonra apply.
3. Şifrəli köhnə sistem planı `fill_legacy_cells_20261108` ilə (231 xana; istəyə görə 11 boş sətir).
4. Sahib qərarları: R1/R2 siyahısı və «yalnız q/b sütunlarında boş = iştirak» qaydası.
5. T4–T6 (4 041 yeni sistem xanası) müəllimlərə bildiriş.

Nəticə: ~677 xana etibarlı mənbədən həll olunur, ~5 700 xana düzgün olaraq boşdur, ~14 000 xana sahibin qərarını
və ya müəllimin yazmasını tələb edir.
