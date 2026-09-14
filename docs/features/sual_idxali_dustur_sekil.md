# Sual idxalı: düstur (LaTeX) və şəkil dəstəyi

Sual bankı → «Toplu əlavə et» (`exams:question_bank_bulk_add`) və imtahan sualları
səhifəsindəki eyni iş masası («workbench»). Sənəd 2026-09-14 vəziyyətini təsvir edir
(commit-lər `576821c5` W3 `w3import`, `36b32754` W4 `w4superv`, `931dff3e`); qaydalar koddan
və testlərdən oxunub — mənbələr §9.

Sahibin istəyi: *«şəkil və düstur olanda problem yaranmasın — dünya praktikası nədirsə
onu düşünərək et.»* Seçilən yanaşma Moodle / Canvas / QTI ilə eynidir: düstur **mətn
olaraq LaTeX** kimi saxlanır (axtarıla və redaktə edilə bilir, HTML deyil, XSS səthi yoxdur),
brauzerdə **KaTeX** render edir; şəkil sənəddən çıxarılır, yoxlanır, normallaşdırılır və
sual / varianta bağlanır.

---

## 1. Qısa iş axını

1. Bankı açın → «Toplu əlavə et».
2. Mənbə seçin: **mətn yapışdırın** (textarea) **və ya fayl yükləyin** (`.pdf .docx .txt
   .png .jpg .jpeg`; PNG/JPG vizual sənəd kimi PDF-ə çevrilib eyni yoldan keçir).
3. «Önizləmə» → hər sual kart kimi görünür: nişanlar (düstur / şəkil / dublikat /
   xəta / xəbərdarlıq), süzgəc çipləri, düzgün cavab, bal.
4. Lazım olanı düzəldin (mətn kartda redaktə olunur) → «Yadda saxla» → suallar banka
   (`BankQuestion` + `BankQuestionOption`) yazılır; şəkillər `image` sahələrinə bağlanır,
   müvəqqəti stash silinir.

Yükləmə serverdə saxlanmır — çıxarılan şəkillər müvəqqəti **stash**-də (manifest ilə)
dayanır, sahibinə bağlıdır (başqa müəllim tokenlə də ala bilməz — test) və 48 saatdan sonra
təmizlənir (`import_retention`).

---

## 2. Yapışdırılan mətnin formatı

| Element | Tanınan yazılış |
|---|---|
| Sual | `1. Sual mətni` və ya `1) Sual mətni` (nömrə + nöqtə/mötərizə) |
| Variant | `A) mətn`, `A. mətn` (A–E; kiril A/В/С/Д/Е də normallaşdırılır) |
| Düzgün cavab | `*B) mətn` **və ya** `B) mətn*` (sonluq `*`; bir neçə → çoxcavablı), ya da ayrıca sətir `Cavab: B` / `Answer: B` / `Ответ: B` / `Cevap: B` |
| Sual sərhədi | boş sətirdən sonra gələn `N.` sətri ≥ 2 variantlı sualı bağlayır; `END_QUESTION` markeri də tanınır |
| Düstur | `$…$`, `$$…$$`, `\(…\)`, `\[…\]` — sual və variant mətnində |

Valyuta qoruması: `$5 və $10` kimi «`$` + rəqəm» düstur sayılmır (server regex-i
`$`-dan əvvəl hərf/rəqəm olmamasını tələb edir; brauzerdə həmin konteynerdə tək-`$`
ayırıcısı söndürülür).

---

## 3. Düstur boru xətti

### 3.1 Saxlanma və kanonik forma

- Etibarlı düstur bazada **`\(…\)`** (sətir içi) və **`\[…\]`** (ayrıca sətir) formasına
  salınır; `$…$` / `$$…$$` yazılışı idxalda çevrilir. Düstur içindəki sətir keçidləri boşluğa
  çevrilir (`linebreaks` filtri düsturu `<br>` ilə bölməsin).
- Mətn HTML kimi **qaçırılmış** qalır; KaTeX mətn düyünündən render edir.

### 3.2 Təhlükəsizlik limitləri (server, `parsing/math_text.py`)

| Qayda | Nəticə |
|---|---|
| Düstur gövdəsi > **2 000 simvol** | ayırıcılar qırılır, mətn kimi qalır; xəbərdarlıq «Düstur çox uzundur (limit 2000 simvol) — mətn kimi saxlanıldı: «…»» |
| Qadağan əmr: `\href \url \includegraphics \def \gdef \edef \xdef \let \futurelet \newcommand \renewcommand \providecommand \input \include \write \csname \catcode \htmlClass \htmlId \htmlStyle \htmlData` | ayırıcılar qırılır, tərs slaşlar çıxarılır (mətn oxunaqlı qalır); xəbərdarlıq «Düsturda icazə verilməyən əmr var (\href) — düstur mətn kimi saxlanıldı: «…»» |

Heç nə **səssiz silinmir** — hər neytrallaşdırma önizləmədə xəbərdarlıq kimi görünür.
Brauzer qatı ikinci müdafiədir: KaTeX `trust:false`, `throwOnError:false`,
`strict:"ignore"`.

### 3.3 DOCX: Word düsturu (OMML) → LaTeX

Word düsturları sənəddə Office MathML kimi saxlanır; `parsing/omml.py` onları LaTeX-ə
çevirir: kəsr (`m:f`), alt/üst indeks (`m:sSub` / `m:sSup` / `m:sSubSup` / `m:sPre`), kök
(`m:rad`, dərəcəli və dərəcəsiz), n-ar operator — cəm / inteqral / hasil, limitlərlə
(`m:nary`), ayırıcı mötərizələr (`m:d`), matris (`m:m`), funksiya (`m:func`), limit
(`m:limLow` / `m:limUpp`), vurğu (`m:acc`), üst xətt (`m:bar`), qrup mötərizəsi
(`m:groupChr`), çərçivə (`m:borderBox`), tənlik massivi (`m:eqArr`), qutu / fantom;
yunan hərfləri və operatorlar Unicode → makro (`α` → `\alpha`, `≤` → `\leq` …).

- `m:oMath` → `\(…\)`; `m:oMathPara` (ayrıca sətir) → `\[…\]`.
- **Naməlum qovşaq** atılmır: mətni `\text{…}` kimi qalır və sual «Düstur tam çevrilmədi
  ({nodes}) — mətn kimi saxlanıldı» xəbərdarlığı + «Bu sualdakı düstur Word-dən tam
  çevrilmədi — render nəticəsini yoxlayın.» nişanı alır.

### 3.4 Render (KaTeX)

- Vendor: `static/vendor/katex/0.16.47/` (`katex.min.js`, `katex.min.css`,
  `contrib/auto-render.min.js`, `fonts/*.woff2`); CDN yoxdur, CSP-yə uyğundur
  (`core/tests/test_w3_katex_assets.py` mövcudluğu və CSP-ni yoxlayır).
- Başladıcı `static/js/ems_math.js` (AJAX-safe, `EMSReady`) yalnız **`[data-ems-math]`**
  konteynerlərində işləyir və bölmə dəyişəndə yenidən çalışır; `script / pre / code /
  textarea / input / select` içinə girmir.
- Yüklənən səhifələr (`partials/ems_ui/_math_assets.html`): tələbə imtahanı
  (`take_exam`), nəticə (`exam_result`), müəllimin cəhd baxışı / yoxlaması, imtahan detalı
  və sual idarəetməsi (bank detalı daxil), sual göndərişi önizləməsi, toplu əlavə
  iş masası.

---

## 4. Şəkil boru xətti

### 4.1 DOCX (`parsing/docx_reader.py`)

| Qayda | Detal |
|---|---|
| Fayl növü | yalnız makro-suz **`.docx`**; `.doc / .docm / .dotm / .dotx / .rtf` rədd |
| İmza | `PK\x03\x04` ilə başlamalıdır — «Faylın uzantısı və faktiki məzmunu uyğun gəlmir.» |
| Zip qoruması | `validate_zip_archive` (zip-bomb: fayl sayı / açılmış ölçü); `word/document.xml` + `[Content_Types].xml` olmalıdır — əks halda «Word (.docx) faylı oxunmadı — zip strukturu pozuqdur və ya sənəd deyil.» |
| Makro | `word/vbaProject*` varsa rədd («Bu fayl növü təhlükəsizlik səbəbi ilə qəbul edilmir…») |
| Ölçü | ≤ 45 MB (`EXAM_UPLOAD_MAX_BYTES`, PDF ilə eyni) — oxunmadan əvvəl yoxlanır |
| Xarici şəkil | `TargetMode="External"` əlaqələr **heç vaxt yüklənmir** → «{count} şəkil xarici linkdir — təhlükəsizlik səbəbi ilə yüklənmədi.» |
| Şəkil formatı | raster (PNG / JPEG / GIF / BMP / TIFF / WebP) Pillow ilə tanınır; EMF / WMF / SVG atılır → «{count} şəkil dəstəklənmir və ya limitdən böyükdür — atıldı» |
| Şəkil limitləri | ≤ 12 MB, ≤ 50 MP, ən çox 200 şəkil; > 2 000 px tərəf **kiçildilir**, **EXIF silinir**; çıxış PNG (qrafika/alfa) və ya JPEG (foto) |
| Lövbər | paraqraf mətninə `[[img:N]]` markeri yazılır — sualın gövdəsində olan şəkil suala, variant sətrində olan şəkil **həmin varianta** bağlanır; cədvəl xanaları ayrı sətir olur, `w:br` sətir keçidi, `w:sym` Unicode |
| Naməlum marker | `[[img:N]]` sənəddə olmayan nömrəyə istinad edirsə → «Şəkil istinadı tapılmadı: [[img:{refs}]] …» (idxal dayanmır) |

### 4.2 PDF

İki yol var (`visual_import_upload.try_visual_import`):

1. **Vizual-first** (layout inamlı olanda): sual / variant bölgəsi bütöv **şəkil kimi
   kəsilir** (`pdf_layout`), 2D riyaziyyat (matris, kəsr, kök) `pdf_math.extract_math_images`
   ilə yüksək DPI PNG olur; 1D riyaziyyat üçün Symbol-PUA glyph-ləri Unicode-a çevrilir
   (`remap_symbol_pua`) — mətn axtarıla bilən qalır.
2. **Mətn fallback** (layout inamsız, `LayoutConfidenceError`): 2026-09-14-ə qədər sənədin
   şəkilləri burada **itirdi**. İndi `parsing/pdf_images.py` PyMuPDF ilə səhifədəki raster
   yerləşimlərini tapır və bölgəyə görə bağlayır:
   - sual bölgəsi = `N.` lövbər sətrindən növbəti sual lövbərinə qədər (səhifə keçidi daxil);
     şəkilin mərkəzi hansı bölgəyə düşürsə o sualındır;
   - şəkilin **üstü** hansı `A)` variant sətrinin üstündən aşağıdadırsa həmin varianta,
     əks halda (variantlardan yuxarı) sualın gövdəsinə;
   - ilk sualdan əvvəlki (başlıq / loqo) və səhifənin ≥ 80 %-ni örtən (skan fonu) şəkillər
     atılır → «{count} şəkil heç bir suala bağlanmadı … — atıldı»; 8 pt-dən kiçik
     yerləşimlər (bullet, xətt) sayılmır; eyni obyekt (xref) iki yerdə → bir dəfə saxlanır;
   - şəkillər DOCX ilə **eyni** `normalize_image_bytes` qapısından keçir (12 MB / 50 MP /
     2 000 px / EXIF).
   Nəticə DOCX manifesti formatındadır (`origin="pdf"`), sonrası ortaqdır.

### 4.3 Yadda saxlanma

Önizləmədə şəkil müvəqqəti stash-dən thumbnail kimi göstərilir («Sənəddən çıxarılan
şəkil — yadda saxlayanda bağlanır: Sual / A / B …»). «Yadda saxla»da `attach_import_media`
şəkilləri `BankQuestion.image` / `BankQuestionOption.image` sahələrinə yazır; sorğu sayı
sual sayından asılı deyil (test: 1 sual = 3 sual = 22 sorğu). Uğursuz şəkil idxalı
xəbərdarlıq verir, heç vaxt 500 deyil.

---

## 5. Önizləmə nişanları və süzgəclər

Hər sual kartında (`_bulk_question_card.html`):

| Nişan | Mənası |
|---|---|
| `√ N` (yaşıl) | «LaTeX düstur tanındı» — N düstur sayı (sual + variantlar) |
| `√ !` (sarı) | «Düstur tam çevrilmədi — mətni yoxlayın» (OMML fallback, qadağan əmr, çox uzun) |
| «şəkil bağlı» | «Sənəddən şəkil bağlanacaq» |
| şəkil `?` | «Şəkil istinadı var, mənbə tapılmadı» |
| Xəta / Xəbərdarlıq / Qeyd sayğacları | ciddilik üzrə |
| Dublikat | idxal daxilində və ya bankda/imtahanda artıq var |
| Təmiz | xəbərdarlıq yoxdur |

Süzgəc çipləri: hamısı · xəta · xəbərdarlıq · dublikat · variant (struktur) · balans ·
**düstur** · **şəkil** · təmiz (sayğaclarla; boş kateqoriya söndürülür). Kartın «inam»
səviyyəsi: `text` → `formula_ok` → `formula_fallback` (şəkil ayrıca bayraqdır).

**Dublikat aşkarlanması** dəyişməyib: barmaq izi = normallaşdırılmış sual mətni + A…E
variant mətnləri; idxal daxilində təkrar → hər iki kartda «Dublikat» (ilk kartda neçə dəfə təkrarlandığı,
sonrakılarda hansı kartla eyni olduğu, «Aç #N» keçidi ilə) — ciddilik **xəta**; bankda /
imtahanda mövcud sualla eyni → «artıq var» xəbərdarlığı (mövcud sualın nömrəsi ilə).

---

## 6. Sual göndərişi (müəllim → kafedra) parseri

Eyni `parse_bulk_mcq` işlədir; 2026-09-14 (W4) düzəlişləri: boş sətirdən sonra gələn `N.`
sətri ≥ 2 variantlı sualı bağlayır (əvvəl ≥ 4 variant tələb edirdi → «C) üç» + «2. İkinci
sual» yapışırdı); sonluq `*` markeri (`B) iki*`, `B) iki *`) `*B)` ilə ekvivalentdir; tək
`*` mətni boşaltmır.

---

## 7. Məlum məhdudiyyətlər (2026-09-14)

- Pano (clipboard) ilə şəkil yapışdırma iş masasında **yoxdur** — yalnız fayl yükləmə. — **2026-09-14 dalğa 8-də əlavə edildi:** bank toplu əlavədə panodan (Ctrl/Cmd+V) və sürüklə-burax ilə şəkil yapışdırma `[[img:N]]` markeri ilə (eyni validasiya, ≤ 12 MB, ≤ 2000 px, EXIF silinir).
- PDF-də çox sütunlu səhifə fərz edilmir (bölgə qaydası tək sütunludur).
- OMML-dən LaTeX-ə çevirmə tam deyil — naməlum qovşaqlar mətn kimi qalır və nişanla
  göstərilir; müəllim yadda saxlamazdan əvvəl yoxlamalıdır.
- KaTeX-in dəstəkləmədiyi LaTeX (`throwOnError:false`) render olunmadan mətn kimi qalır —
  xəta atmır.

---

## 8. Yoxlama siyahısı (müəllim üçün)

1. Word-də düsturu **Equation** (Alt+=) ilə yazın — şəkil kimi yapışdırılmış düstur
   şəkil olaraq gəlir, mətn olaraq yox.
2. Şəkli sualın öz paraqrafına (və ya variant sətrinə) yerləşdirin — bağlanma paraqrafa
   görədir.
3. Faylı **`.docx`** kimi saxlayın (`.doc` / makrolu `.docm` rədd edilir).
4. Önizləmədə sarı düstur nişanı və «?» şəkil nişanı olan kartları açıb yoxlayın.
5. Yadda saxladıqdan sonra bank detalında düsturun render olduğunu, şəkilin göründüyünü
   yoxlayın (konsolda CSP xətası olmamalıdır).

---

## 9. Mənbələr

| Nə | Fayl |
|---|---|
| Düstur aşkarlama / sanitizasiya / kanonik forma | `apps/exams/services/parsing/math_text.py` |
| OMML → LaTeX | `apps/exams/services/parsing/omml.py` |
| DOCX oxuyucu (təhlükəsizlik, şəkillər, markerlər) | `apps/exams/services/parsing/docx_reader.py` |
| Marker → `media_refs`, parser nüvəsi, sonluq `*` | `apps/exams/services/parsing/media_markers.py`, `_core.py`, `option_markers.py` |
| PDF raster şəkillər (mətn fallback) | `apps/exams/services/parsing/pdf_images.py`, `import_media_pdf.py` |
| PDF glyph remap + 2D math bölgəsi | `apps/exams/services/pdf_math.py`, `pdf_layout/**` |
| Stash / manifest / bağlama | `apps/exams/services/import_media.py`, `import_media_docx.py`, `import_media_store.py`, `import_retention.py` |
| Önizləmə inam nişanları, dublikat | `apps/exams/services/bulk_confidence.py`, `bulk_workbench.py` |
| KaTeX vendor + başladıcı | `static/vendor/katex/0.16.47/**`, `static/js/ems_math.js`, `templates/partials/ems_ui/_math_assets.html` |
| Şablonlar | `apps/exams/templates/exams/teacher/partials/_bulk_question_workbench.html`, `_bulk_question_card.html` |
| Testlər | `apps/exams/tests/test_w3_import_omml.py` (19: OMML konstruksiyaları, sanitizasiya, valyuta, markerlər), `test_w3_import_docx.py` (18: oxuyucu, təhlükəsizlik, uçdan-uca önizləmə → yadda saxlama, stash əhatəsi, sorğu büdcəsi), `test_w4_pdf_images.py` (10: bölgə bağlama, loqo/fon, dublikat xref, səhifə keçidi, 2 600 → 2 000 px, uçdan-uca), `test_w4_parser_blocks.py` (9), `core/tests/test_w3_katex_assets.py` (6: aktivlər, CSP, node harness) |
