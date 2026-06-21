# Sual idxalında düstur & şəkil dəstəyi — inteqrasiya təlimatı

## Problemin kökü
Mathcad/MathType ilə hazırlanmış PDF-lərdə düsturlar Unicode mətn deyil — **Symbol
font + PUA glyph**-ləri ilə qurulur (PUA kodu `U+F028`=`(`, `U+F03D`=`=`, `U+F0E6`=matris
mötərizəsi). `pypdf` bunları ya zibilə çevirir, ya da çoxsətirli matrisi qarışdırır.

Həll iki qatlıdır (LMS best practice):
1. **Glyph remap** — sətirli (1D) düsturlar üçün: Symbol glyph → əsl Unicode.
2. **Region → PNG** — 2D düsturlar (matris/kəsr/kök) üçün: region kəsilib şəkil kimi bağlanır.

Real 52 səhifəlik imtahan PDF-də doğrulanıb: Symbol zibili **2771 → 1**, 36 sualda
2D düstur aşkarlandı (29 stem + 60 variant şəkli).

---

## ✅ Artıq tətbiq edilib (canlıdır, miqrasiya tələb edir)

| Fayl | Dəyişiklik |
|---|---|
| `apps/exams/services/pdf_math.py` | **YENİ** — `remap_symbol_pua()` + `extract_math_images()` + `extract_correct_labels()` (mövqe əsaslı highlight) + Adobe Symbol cədvəli |
| `apps/exams/services/parsing.py` | `normalize_pdf_extracted_text()` → `remap_symbol_pua()`; highlight artıq MÖVQE əsaslı (`extract_correct_labels` + `_mark_correct_options_by_position`) — köhnə "hər sualda A" buguğu həll olundu |
| `apps/exams/domain/question_bank.py` | `ExamQuestionOption.image` + `BankQuestionOption.image` + `option_media_path`/`bank_option_media_path` |
| `apps/exams/domain/__init__.py`, `apps/exams/models.py` | yeni path funksiyaları re-export |
| `apps/exams/migrations/0023_option_image.py` | **YENİ** — variant `image` sahələri |
| `apps/exams/services/import_media.py` | **YENİ** — preview→save axınında şəkil daşıma servisi |

**İlk addım:**
```bash
python manage.py migrate exams
```
> `remap` təkbaşına “qatıb qarışdırma” probleminin böyük hissəsini həll edir və heç
> bir əlavə wiring tələb etmir — yalnız migrasiya.

---

## 🟢 Düzgün cavab (sarı highlight) buguğu — HƏLL OLUNDU (canlı, migration-suz)
Köhnə kod highlight-ı **yalnız etiketə görə qlobal** uyğunlaşdırırdı: sənəddə bir
yerdə "A)" düzgün olduğu üçün HƏR sualın bütün variantları işarələnirdi → parser
default **A**-ya düşürdü (sizin gördüyünüz "həmişə A" problemi).

İndi highlight **mövqe əsaslıdır**: hər sarı işarə fiziki olaraq yerləşdiyi sual +
variantа bağlanır (`extract_correct_labels`), sual nömrəsi məhdud-aralıqlı monoton
izlənir (düstur rəqəmlərinin saxta anker yaratması bloklanır). Sizin 300 suallıq
PDF-də doğrulandı: cavab paylanması balanslıdır (A≈69, B≈63, C≈61, E≈57, D≈45) və
yoxlanan suallar highlight ilə üst-üstə düşür (Q1→E, Q2→C, Q3→D, Q4→B, Q5→D...).
Reqressiya testi əlavə olundu (`test_highlight_is_scoped_per_question_no_cross_contamination`).
> Bu düzəliş **dərhal işləyir** — yalnız kod, əlavə migration/wiring lazım deyil.

---

## ✅ Şəkil wiring — TAMAMLANDI (migration tələb edir)
Aşağıdakılar artıq kodda tətbiq olundu (yalnız `migrate exams` lazımdır):

| Fayl | Dəyişiklik |
|---|---|
| `views/teacher/question_library.py` | bank bulk: preview-da `stash_math_images`, save-də `attach_math_images` + `clear_stash`, `math_token` kontekst |
| `views/teacher/question_bank.py` | imtahan bulk: eyni axın (`test_question_bank`) |
| `partials/_bulk_question_workbench.html` | hər iki forma `math_token` gizli sahəsi |
| `services/randomizer.py` | `build_shuffled_options` artıq variant `image` URL-ni qaytarır |
| `templates/exams/student/take_exam.html` | variant şəkli (`opt.image`) həm tək, həm çox cavablı rejimdə göstərilir |

**İş axını:** müəllim PDF yükləyir → preview-da düstur regionları PNG kimi yığılır
(token) → "yadda saxla"-da hər sual/variantın şəkli modelə bağlanır → tələbə imtahan
həllində düsturu şəkil kimi görür.

> Qeyd: preview SİYAHISINDA hələ mətn göstərilir (düstur şəkli yox) — şəkil yadda
> saxlamadan sonra sual səhifəsində görünür. Preview-da da şəkil göstərmək istəsəniz
> `parsed` dict-lərinə `math_token`-dan şəkil URL-i inject etmək lazımdır (kiçik əlavə).

### Hələ əlavə oluna bilər (opsional, ikincili)
- Nəticə/yoxlama səhifələri (`exam_result.html`, `teacher_check_attempt.html`,
  `partials/_question_form.html`): bunlar model instance işlədir, ona görə sadəcə
  `{% if opt.image %}<img src="{{ opt.image.url }}">{% endif %}` əlavə etmək kifayətdir.
- Tək sual əl ilə yaratma formasında variant şəkli yükləmə (`create_options`).

## 🔧 (Köhnə qeyd) Manual wiring nümunəsi — artıq tətbiq olunub

### 1) Bank toplu-yükləmə view — `apps/exams/views/teacher/question_library.py`

**a. Preview addımında token yığ** (`extract_text_from_upload`-dan sonra, ~457-ci sətir):
```python
from apps.exams.services.import_media import stash_math_images, attach_math_images, clear_stash

math_token = (request.POST.get("math_token") or "").strip()
if uploaded:
    try:
        raw_text = extract_text_from_upload(uploaded)
        math_token = stash_math_images(uploaded) or ""   # ƏLAVƏ
    except Exception as exc:
        ...
```
**b.** `context`-ə əlavə et: `"math_token": math_token,`
**c.** `_save_bank_questions(...)` çağırışına `math_token=math_token` ötür; bitəndən
sonra `clear_stash(math_token)`.

**d. `_save_bank_questions` — q_no izlə və şəkilləri bağla:**
```python
def _save_bank_questions(*, bank, parsed, selected, language, q_format,
                         points_payload, created_by, math_token=""):
    rows, option_payloads, q_numbers = [], [], []     # q_numbers ƏLAVƏ
    for index, question in enumerate(parsed, start=1):
        ...
        rows.append(BankQuestion(...))
        option_payloads.append((options, set(...)))
        q_numbers.append(str(question.get("q_no") or index))   # ƏLAVƏ
    ...
    with transaction.atomic():
        created = BankQuestion.objects.bulk_create(rows, batch_size=100)
        # ... mövcud option bulk_create ...
        if option_rows:
            BankQuestionOption.objects.bulk_create(option_rows, batch_size=500)

        # ŞƏKİL BAĞLA — variantlar yaradılandan SONRA:
        if math_token:
            for bank_question, q_no in zip(created, q_numbers):
                attach_math_images(math_token, q_no, bank_question)
    return len(created)
```

### 2) İmtahan toplu-yükləmə view — `apps/exams/views/teacher/question_bank.py`
Eyni pattern: preview-da `stash_math_images`, save-də hər `ExamQuestion` üçün
`attach_math_images(token, q_no, question)`. ~280 və ~1179-cu sətirlərdəki axınlar.

### 3) Şablon — gizli sahə
Toplu-yükləmə formalarına (`question_bank_bulk_add.html`,
`_bulk_question_workbench.html`) `raw_text` gizli sahəsinin yanına:
```html
<input type="hidden" name="math_token" value="{{ math_token }}">
```

### 4) Frontend — variant şəklini göstər
`question.image` artıq göstərilir; variant üçün eyni pattern. Hər `opt.text`-dən sonra
(məs. `take_exam.html` ~221, 236; `exam_result.html`, `teacher_check_attempt.html`,
`partials/_question_form.html`):
```html
<span class="opt-text">{{ opt.text }}</span>
{% if opt.image %}
  <img src="{{ opt.image.url }}" class="opt-image" alt="{% trans 'alt_option_image' context 'exams.template' %}">
{% endif %}
```
CSS (mövcud exam CSS-ə): `.opt-image{max-width:100%;height:auto;vertical-align:middle}`

---

## ➕ Opsional — yazılan LaTeX üçün KaTeX (gələcək AI/əl ilə düstur)
Şəkillər problemi həll etdiyi üçün məcburi deyil. İstəsəniz `take_exam.html`-ə:
```html
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex/dist/contrib/auto-render.min.js"
        onload="renderMathInElement(document.body)"></script>
```
> Asset izolyasiya qaydanıza görə bunu yalnız imtahan/sual səhifələrinə include edin, `base.html`-ə yox.

---

## Tenant/təhlükəsizlik qeydləri
- Şəkillər mövcud `MEDIA` axını ilə saxlanır (`option_media_path` → `question_media/exam_<id>/...`),
  yəni tenant izolyasiyası dəyişmir. Private media prefix qaydanız buna da şamil olunur.
- `import_media` token yalnız 32-hex (path-traversal müdafiəsi); idxal bitəndə qovluq silinir.
- `extract_math_images` tam müdafiəlidir: `fitz` yoxdursa/xəta olsa `{}` qaytarır — mətn idxalı sınmır.
- Render limiti: maksimum 60 səhifə (`_MAX_PAGES`), ~216 DPI (`_RENDER_ZOOM`).
