import io
import logging
import os
import re
from collections import defaultdict

from django.conf import settings
from django.utils.translation import pgettext

from apps.exams.constants import ANSWERLINE_RE, LABELS, OPTION_RE, QUESTION_RE
from apps.exams.services.utils import _norm

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

# PyMuPDF (fitz) — PDF highlight (annotation) oxuması üçün. Opsionaldır:
# quraşdırılmayıbsa, mətn yenə çıxarılır, sadəcə PDF-də highlight→düz cavab işləməz.
try:
    import fitz
except ImportError:
    fitz = None

logger = logging.getLogger(__name__)

# ---- Fayl yükləmə təhlükəsizliyi -----------------------------------------------
# settings.EXAM_UPLOAD_MAX_BYTES ilə konfiqurasiya edilə bilər; default 45MB.
MAX_UPLOAD_BYTES = getattr(settings, "EXAM_UPLOAD_MAX_BYTES", 45 * 1024 * 1024)

# Magic bytes (real signature) — uzantıya görə yox, faktiki məzmuna görə yoxlayırıq.
FILE_SIGNATURES = {
    "pdf": [b"%PDF-"],
    "png": [b"\x89PNG\r\n\x1a\n"],
    "jpg": [b"\xff\xd8\xff"],
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def _ensure_within_size_limit(uploaded_file, limit: int) -> None:
    if uploaded_file.size and uploaded_file.size > limit:
        raise ValueError(pgettext("exams.service.parsing.error", "file_too_large"))


def _peek_magic_bytes(uploaded_file, length: int = 8) -> bytes:
    """Faylın əvvəlindən magic bytes oxu, sonra cursor-u geri qaytar."""
    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    head = uploaded_file.read(length) or b""
    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    return head


def _verify_magic_bytes(head: bytes, expected_key: str) -> bool:
    signatures = FILE_SIGNATURES.get(expected_key, [])
    return any(head.startswith(sig) for sig in signatures)


def _pdf_safety_check(uploaded_file) -> None:
    """
    PDF-də OpenAction/JavaScript/embedded file kimi aktiv kontentin olub-olmadığını yoxlayırıq.
    Tam sanitize etmirik — sadəcə şübhəli pattern olarsa rədd edirik.
    """
    try:
        uploaded_file.seek(0)
    except Exception:
        pass
    # PDF-in ilk hissəsindən şübhəli açar sözləri axtarırıq (tam fayla baxmaq baha olardı).
    sample = uploaded_file.read(256 * 1024) or b""
    try:
        uploaded_file.seek(0)
    except Exception:
        pass

    suspicious_markers = (
        b"/JS",
        b"/JavaScript",
        b"/Launch",
        b"/EmbeddedFile",
        b"/OpenAction",
        b"/AA",  # additional actions
    )
    if any(marker in sample for marker in suspicious_markers):
        raise ValueError(pgettext("exams.service.parsing.error", "file_pdf_active_content"))


END_QUESTION_RE = re.compile(r"^\s*END_QUESTION\s*$", re.IGNORECASE)
# Bitişik variant sərhədi: kiçik hərf → böyük hərf keçidi (az/en/tr/ru əlifbaları)
JOINED_OPTION_BOUNDARY_RE = re.compile(r"(?<=[a-zəöüğışçа-яё])(?=[A-ZƏÖÜĞİŞÇА-ЯЁ])")

# ---- Bullet (•) / işarə (√) formatlı sənədlər ------------------------------------
# Bəzi PDF/Word ixracları variantları A–E etiketi ilə yox, bullet işarəsi ilə,
# düz cavabı isə √ / ✓ işarəsi ilə verir (məs. universitet yekun test sənədləri):
#   1. Sual mətni?
#    • Yanlış variant
#    √ Düz variant
# Aşağıdakı çevirici belə sətrləri mövcud parserin tanıdığı "A) ..." / "*B) ..."
# formasına salır — parser məntiqinə toxunulmur.
_BULLET_CHARS = "•◦▪‣●○·"
_CHECK_CHARS = "√✓✔☑✅"
_BULLET_OPTION_LINE_RE = re.compile(rf"^\s*[{_BULLET_CHARS}]\s*(.+)$")
_CHECK_OPTION_LINE_RE = re.compile(rf"^\s*[{_CHECK_CHARS}]\s*(.+)$")

# ---- Kiril variant etiketləri (rus dilinə tərcümə olunmuş sənədlər) --------------
# Tərcümə zamanı "A)" çox vaxt görünüşcə eyni olan kiril hərfinə çevrilir.
# İki sxem mövcuddur:
#   1) Ardıcıl rus əlifbası: А Б В Г Д  → A B C D E
#   2) Latın oxşarı (lookalike): А В С Д Е → A B C D E
# Sənəddə Б və ya Г varsa ardıcıl sxem, əks halda lookalike qəbul edilir.
_CYRILLIC_SEQ_MAP = {"А": "A", "Б": "B", "В": "C", "Г": "D", "Д": "E"}
_CYRILLIC_LOOKALIKE_MAP = {"А": "A", "В": "B", "С": "C", "Д": "D", "Е": "E"}
_CYR_OPTION_LABEL_RE = re.compile(r"^(\s*\*?\s*)([АБВГДСЕабвгдсе])(\s*[\)\.])", re.MULTILINE)
_CYR_ANSWERLINE_RE = re.compile(
    r"^(\s*(?:cavab|duz\s*cavab|düz\s*cavab|correct|answer|ответ|правильный\s*ответ|cevap|doğru\s*cevap)\s*[:\-]\s*)"
    r"([АБВГДСЕабвгдсе](?:\s*[,;/]\s*[АБВГДСЕабвгдсе])*)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


def _normalize_cyrillic_option_labels(text: str) -> str:
    """Kiril variant etiketlərini (А Б В …) latın A–E etiketlərinə çevirir."""
    if not text:
        return text

    used = {m.group(2).upper() for m in _CYR_OPTION_LABEL_RE.finditer(text)}
    if not used:
        return text

    mapping = _CYRILLIC_SEQ_MAP if used & {"Б", "Г"} else _CYRILLIC_LOOKALIKE_MAP

    def _label_repl(match):
        latin = mapping.get(match.group(2).upper())
        if latin is None:
            return match.group(0)
        return match.group(1) + latin + match.group(3)

    def _answer_repl(match):
        translated = "".join(mapping.get(ch.upper(), ch) if ch.upper() in mapping else ch for ch in match.group(2))
        return match.group(1) + translated

    text = _CYR_OPTION_LABEL_RE.sub(_label_repl, text)
    return _CYR_ANSWERLINE_RE.sub(_answer_repl, text)


# Tək qalmış sual nömrəsi sətri ("350." / "350)") — uzun suallarda PDF extraction
# nömrəni ayrıca sətirdə saxlayır, mətn növbəti sətirdən başlayır.
_BARE_QNO_RE = re.compile(r"^\s*(\d{1,4})\s*([\.\)])\s*$")


def _merge_bare_question_numbers(text: str) -> str:
    """
    Tək sual nömrəsi sətrini növbəti mətn sətri ilə birləşdirir ki, QUESTION_RE
    onu sual başlanğıcı kimi tanısın. Növbəti sətir variant/işarə sətridirsə
    (sual mətni tamam yoxdursa) toxunulmur.
    """
    if not text:
        return text

    lines = text.splitlines()
    out_lines: list[str] = []
    i = 0
    while i < len(lines):
        m = _BARE_QNO_RE.match(lines[i])
        if m:
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if (
                j < len(lines)
                and not OPTION_RE.match(lines[j])
                and not _BARE_QNO_RE.match(lines[j])
                and not _BULLET_OPTION_LINE_RE.match(lines[j])
                and not _CHECK_OPTION_LINE_RE.match(lines[j])
            ):
                out_lines.append(f"{m.group(1)}{m.group(2)} {lines[j].strip()}")
                i = j + 1
                continue
        out_lines.append(lines[i])
        i += 1
    return "\n".join(out_lines)


def _convert_marker_options(text: str) -> str:
    """
    Bullet (•) variantlarını "A) ..." formasına, √-li sətrləri isə "*X) ..."
    (düz cavab) formasına çevirir. Etiket sayğacı hər sual sətrində sıfırlanır.
    Mövcud A–E etiketli sətrlərə toxunulmur; marker yoxdursa mətn olduğu kimi qalır.
    """
    if not text or not any(ch in text for ch in _BULLET_CHARS + _CHECK_CHARS):
        return text

    out_lines = []
    label_idx = 0
    for line in text.splitlines():
        if QUESTION_RE.match(line):
            label_idx = 0
            out_lines.append(line)
            continue

        m_check = _CHECK_OPTION_LINE_RE.match(line)
        m_bullet = None if m_check else _BULLET_OPTION_LINE_RE.match(line)
        match = m_check or m_bullet
        if match and label_idx < len(LABELS):
            label = LABELS[label_idx]
            label_idx += 1
            prefix = "*" if m_check else ""
            out_lines.append(f"{prefix}{label}) {match.group(1).strip()}")
        else:
            out_lines.append(line)

    return "\n".join(out_lines)


# PDF-dən çıxan mətni parser üçün uyğun formaya salır:


def normalize_pdf_extracted_text(text: str) -> str:
    """
    PDF-dən çıxan mətni parser üçün uyğun formaya salır:
    - sual nömrələrinin qabağına boş sətir əlavə edir (… \n\n12) …)
    - A–E variantlarının qabağına newline əlavə edir (… \nA) …)
    - "Cavab:" sətrini yeni sətrə keçirir
    - '*' işarəsi ilə variant arasında boşluğu düzəldir (*A) kimi)
    - bullet (•) və işarə (√) markerlərini yeni sətirdən başladır
    """
    if not text:
        return ""

    t = text.replace("\r", "\n")

    # çoxlu boşluqları normallaşdır
    t = re.sub(r"[ \t]+", " ", t)

    # "Cavab:" həmişə yeni sətirdən başlasın (az/en/ru/tr açar sözləri)
    t = re.sub(r"(?i)\s+((?:cavab|correct|answer|ответ|cevap)\s*:)", r"\n\1", t)

    # "* A)" kimi çıxırsa "*A)" et
    t = re.sub(r"\*\s+([A-E])", r"*\1", t, flags=re.IGNORECASE)

    # Sual nömrələri: " 12)" və ya " 12." -> yeni blok kimi başlasın
    # (Variant daxilində 1) 2) olsa belə parser artıq IN_OPT-də bunu sual saymır, problem olmur.)
    t = re.sub(r"(?<!\n)\s+(\d{1,4})\s*(\)|\.(?!\d))", r"\n\n\1\2", t)

    # Variantlar: " A)" / " *A)" / " B." və s -> yeni sətirdən başlasın
    t = re.sub(r"(?<!\n)\s+(\*?[A-E])\s*([\)\.])", r"\n\1\2", t, flags=re.IGNORECASE)

    # Bullet/işarə markerləri (• variant, √ düz cavab) yeni sətirdən başlasın
    t = re.sub(rf"(?<!\n)\s+([{_BULLET_CHARS}{_CHECK_CHARS}])\s*", r"\n\1 ", t)

    # 3+ boş sətiri 2-yə sal
    t = re.sub(r"\n{3,}", "\n\n", t)

    return t.strip()


# ---- Highlight (mark) → düz cavab ----------------------------------------------
# İdeya: DOCX-də sarı/rəngli işarələnmiş, PDF-də highlight annotation ilə qeyd
# edilmiş variant "düz cavab" sayılır. Parser-i dəyişmirik — sadəcə extraction
# mərhələsində belə variant sətrinin əvvəlinə artıq mövcud olan "*" markerini
# əlavə edirik (OPTION_RE onsuz da "*A)" formatını düz cavab kimi tanıyır).
# Bu yanaşma heç bir mövcud parser məntiqini və ya testini pozmur.

# az/en/tr/ru hərfləri saxlanılır — rus mətnlərində highlight uyğunlaşması işləsin
_HIGHLIGHT_CORE_RE = re.compile(r"[^0-9a-zəğıöüçşıа-яё]+")


def _highlight_core(text: str) -> str:
    """Müqayisə üçün variant mətnini sadələşdir (kiçik hərf, yalnız söz simvolları)."""
    return _HIGHLIGHT_CORE_RE.sub(" ", (text or "").lower()).strip()


def _frag_label_and_core(fragment: str) -> tuple[str | None, str]:
    """Highlight fraqmentindən (varsa) A–E etiketini və sadələşmiş mətn nüvəsini al."""
    m = OPTION_RE.match((fragment or "").strip())
    if m:
        return m.group(2).upper(), _highlight_core(m.group(3))
    return None, _highlight_core(fragment)


def _fragment_matches_option(frag_label, frag_core, opt_label, opt_core) -> bool:
    """
    Bir highlight fraqmentinin konkret variant sətrinə aid olub-olmadığını qərarlaşdır.
    - Fraqmentdə etiket varsa (məs. "D) ..."), yalnız etiketə görə uyğunlaşdırırıq (ən etibarlı).
    - Etiket yoxdursa, mətnə görə: ya tam bərabər, ya da variant nüvəsi fraqment
      nüvəsinin tam içindədir (yarımçıq highlight səbəbli yanlış uyğunluqdan qaçmaq üçün).
    """
    if frag_label:
        return frag_label == opt_label
    if not frag_core or not opt_core:
        return False
    return opt_core == frag_core or (len(opt_core) >= 3 and opt_core in frag_core)


def _mark_correct_option_lines(text: str, highlight_fragments: list[str]) -> str:
    """
    highlight_fragments ilə uyğun gələn variant sətrlərinin əvvəlinə "*" əlavə edir.
    Yalnız OPTION_RE-yə uyğun (A–E) sətrlərə toxunur; sual mətninə toxunmur.
    Fraqment yoxdursa mətn olduğu kimi qaytarılır (davranış dəyişmir).
    """
    if not highlight_fragments:
        return text

    parsed = [_frag_label_and_core(f) for f in highlight_fragments]
    out_lines = []
    for line in text.splitlines():
        m = OPTION_RE.match(line)
        if m and not m.group(1):  # variant sətridir və hələ "*" ilə işarələnməyib
            opt_label = m.group(2).upper()
            opt_core = _highlight_core(m.group(3))
            if any(_fragment_matches_option(fl, fc, opt_label, opt_core) for fl, fc in parsed):
                line = re.sub(r"^(\s*)", r"\1*", line, count=1)
        out_lines.append(line)
    return "\n".join(out_lines)


def _extract_pdf_highlights(uploaded_file) -> list[str]:
    """
    PDF-dəki highlight annotation-larının altındakı mətni çıxarır (PyMuPDF ilə).
    Tam müdafiəlidir: fitz yoxdursa və ya hər hansı xəta olarsa boş siyahı qaytarır,
    beləliklə yükləmə heç vaxt highlight oxuması səbəbindən sınmır.
    """
    if fitz is None:
        return []

    try:
        uploaded_file.seek(0)
        data = uploaded_file.read()
        uploaded_file.seek(0)
    except Exception:
        return []

    fragments: list[str] = []
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            for page in doc:
                annot = page.first_annot
                while annot is not None:
                    try:
                        # 8 == PDF_ANNOT_HIGHLIGHT
                        if annot.type and annot.type[0] == 8:
                            verts = annot.vertices or []
                            parts = []
                            # vertices hər highlight üçün 4 nöqtəlik (quad) qruplarla gəlir
                            for i in range(0, len(verts) - 3, 4):
                                rect = fitz.Quad(verts[i : i + 4]).rect
                                chunk = page.get_textbox(rect)
                                if chunk and chunk.strip():
                                    parts.append(chunk.strip())
                            frag = " ".join(parts).strip()
                            if frag:
                                fragments.append(frag)
                    except Exception:
                        pass
                    annot = annot.next
    except Exception as exc:
        logger.warning("PDF highlight extraction failed: %s", exc)
        return []

    return fragments


# ---- Skan edilmiş (şəkil əsaslı) PDF üçün OCR ----------------------------------
# Bəzi PDF-lər tamamilə şəkildən ibarətdir (mətn qatı yoxdur). Belə fayllarda
# pypdf/PyMuPDF mətn çıxara bilmir. Bu halda PyMuPDF-in daxili Tesseract OCR-ı ilə
# mətni şəkildən tanıyırıq. OCR yalnız mətn qatı OLMAYANDA işə düşür (performans).
# Server-də `tesseract-ocr` + `tesseract-ocr-aze` quraşdırılmalıdır.


def _pdf_has_text_layer(uploaded_file) -> bool | None:
    """
    PyMuPDF ilə sürətli yoxlama: PDF-də çıxarıla bilən mətn qatı varmı?

    Returns:
        True  — ən azı bir səhifədə mətn var.
        False — heç bir səhifədə mətn yoxdur (skan edilmiş PDF).
        None  — müəyyən edilə bilmədi (fitz yoxdur və ya fayl açılmadı) →
                çağıran tərəf köhnə pypdf yolu ilə davam etməlidir.
    """
    if fitz is None:
        return None
    try:
        uploaded_file.seek(0)
        data = uploaded_file.read()
        uploaded_file.seek(0)
    except Exception:
        return None
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            for page in doc:
                if (page.get_text("text") or "").strip():
                    return True
            return False
    except Exception:
        return None


def _build_yellow_mask(pil_image):
    """
    RGB şəkildən sarı highlight maskası qurur (mode "L", 0/255). Yalnız PIL —
    numpy asılılığı yoxdur. Sarı = yüksək R, yüksək G, aşağı B (R-B və G-B fərqi
    kifayət qədər böyük). Skan edilmiş PDF-də düz cavabın sarı işarələnməsini
    aşkar etmək üçün istifadə olunur.
    """
    from PIL import ImageChops

    r, g, b = pil_image.split()

    def at_least(channel, threshold):
        return channel.point(lambda v, t=threshold: 255 if v >= t else 0)

    r_high = at_least(r, 150)
    g_high = at_least(g, 150)
    b_low = b.point(lambda v: 255 if v < 150 else 0)
    # ImageChops.subtract 0-da kəsir, ona görə R-B / G-B fərqi üçün uyğundur.
    rb_gap = at_least(ImageChops.subtract(r, b), 40)
    gb_gap = at_least(ImageChops.subtract(g, b), 40)

    mask = r_high
    for layer in (g_high, b_low, rb_gap, gb_gap):
        mask = ImageChops.multiply(mask, layer)  # 0/255 maskalar üçün məntiqi AND
    return mask


def _line_yellow_ratio(mask, bbox) -> float:
    """Verilmiş düzbucaqlıda sarı piksellərin nisbəti (0..1)."""
    x0, y0, x1, y1 = bbox
    if x1 <= x0 or y1 <= y0:
        return 0.0
    crop = mask.crop((x0, y0, x1, y1))
    total = crop.size[0] * crop.size[1]
    if not total:
        return 0.0
    histogram = crop.histogram()
    yellow_pixels = histogram[255] if len(histogram) >= 256 else 0
    return yellow_pixels / total


def _word_bbox(word, zoom: float, mask_w: int, mask_h: int) -> tuple[int, int, int, int]:
    return (
        max(0, int(word[0] * zoom)),
        max(0, int(word[1] * zoom)),
        min(mask_w, int(word[2] * zoom)),
        min(mask_h, int(word[3] * zoom)),
    )


def _line_words_have_yellow(mask, line_words, zoom: float, min_ratio: float, mask_w: int, mask_h: int) -> bool:
    """
    OCR söz qutularını sarı highlight maskası ilə müqayisə edir.
    Həm bütün sətrə, həm də ayrıca söz qutularına baxırıq: skan PDF-lərdə müəllim
    bəzən yalnız cavab sözünü boyayır, sətrin tam eni isə ağ qalır.
    """
    if mask is None or not line_words:
        return False

    line_bbox = (
        max(0, int(min(w[0] for w in line_words) * zoom)),
        max(0, int(min(w[1] for w in line_words) * zoom)),
        min(mask_w, int(max(w[2] for w in line_words) * zoom)),
        min(mask_h, int(max(w[3] for w in line_words) * zoom)),
    )
    if _line_yellow_ratio(mask, line_bbox) >= min_ratio:
        return True

    return any(_line_yellow_ratio(mask, _word_bbox(word, zoom, mask_w, mask_h)) >= min_ratio for word in line_words)


def _ensure_tessdata_prefix() -> None:
    """
    PyMuPDF OCR requires TESSDATA_PREFIX even when the tesseract CLI can find
    languages by itself. Debian/Ubuntu packages keep traineddata here.
    """
    if os.getenv("TESSDATA_PREFIX"):
        return

    candidates = (
        "/usr/share/tesseract-ocr/5/tessdata",
        "/usr/share/tesseract-ocr/4.00/tessdata",
        "/usr/share/tessdata",
    )
    for path in candidates:
        if os.path.exists(os.path.join(path, "eng.traineddata")):
            os.environ["TESSDATA_PREFIX"] = path
            return


def _ocr_pdf_text(uploaded_file) -> str:
    """
    Skan edilmiş PDF-dən OCR ilə mətn çıxarır (PyMuPDF daxili Tesseract) və
    şəkilə "baked" sarı highlight ilə işarələnmiş düz cavabı aşkar edib mövcud
    "*" markerini həmin variant sətrinə əlavə edir. Beləliklə skan PDF-də belə
    highlight→düz cavab işləyir (annotation olmasa da).

    Konfiqurasiya (settings):
      - EXAM_PDF_OCR_ENABLED            (default True)
      - EXAM_PDF_OCR_LANG               (default "aze") — Tesseract dili; işləməsə "eng"
      - EXAM_PDF_OCR_DPI                (default 160)
      - EXAM_PDF_OCR_MAX_PAGES          (default 40) — request timeout-dan qoruyan limit
      - EXAM_PDF_OCR_HIGHLIGHT          (default True) — sarı→düz cavab aşkarı
      - EXAM_PDF_OCR_HIGHLIGHT_MIN_RATIO(default 0.10) — sətrin sarı örtük həddi

    Tam müdafiəlidir: fitz/Tesseract yoxdursa və ya xəta olarsa boş sətir qaytarır.
    """
    if fitz is None or not getattr(settings, "EXAM_PDF_OCR_ENABLED", True):
        return ""

    _ensure_tessdata_prefix()

    lang = getattr(settings, "EXAM_PDF_OCR_LANG", "aze")
    detect_highlight = getattr(settings, "EXAM_PDF_OCR_HIGHLIGHT", True)
    try:
        dpi = int(getattr(settings, "EXAM_PDF_OCR_DPI", 160))
        max_pages = int(getattr(settings, "EXAM_PDF_OCR_MAX_PAGES", 40))
        min_ratio = float(getattr(settings, "EXAM_PDF_OCR_HIGHLIGHT_MIN_RATIO", 0.10))
    except (TypeError, ValueError):
        dpi, max_pages, min_ratio = 160, 40, 0.10

    try:
        uploaded_file.seek(0)
        data = uploaded_file.read()
        uploaded_file.seek(0)
    except Exception:
        return ""

    # Konfiqurasiya olunmuş dil, sonra "eng" fallback. İlk işləyən dili "kilidləyirik".
    languages_to_try = [lang] + (["eng"] if lang != "eng" else [])
    active_lang = None
    zoom = dpi / 72.0
    parts: list[str] = []
    try:
        from PIL import Image
    except Exception:
        Image = None
        detect_highlight = False

    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            for index, page in enumerate(doc):
                if index >= max_pages:
                    logger.info("PDF OCR truncated at %d pages (doc has %d).", max_pages, doc.page_count)
                    break

                # OCR textpage (mətn + söz qutuları). İlk işləyən dili tap.
                textpage = None
                for candidate in ([active_lang] if active_lang else languages_to_try):
                    try:
                        textpage = page.get_textpage_ocr(full=True, language=candidate, dpi=dpi)
                        active_lang = candidate
                        break
                    except Exception:
                        continue
                if textpage is None:
                    continue

                page_text = _ocr_page_text_with_highlights(
                    page, textpage, zoom, detect_highlight, min_ratio, Image, dpi
                )
                if page_text.strip():
                    parts.append(page_text.strip())
    except Exception as exc:
        logger.warning("PDF OCR failed: %s", exc)
        return ""

    return normalize_pdf_extracted_text("\n\n".join(parts))


def _ocr_image_text(uploaded_file) -> str:
    """
    PNG/JPG faylını OCR üçün tək səhifəlik image-only PDF kimi emal edir.
    Bu, ayrıca Tesseract wrapper-i əlavə etmədən skan-PDF üçün yazılmış
    highlight→düz cavab məntiqindən birbaşa şəkil fayllarında da istifadə edir.
    """
    if fitz is None or not getattr(settings, "EXAM_PDF_OCR_ENABLED", True):
        return ""

    try:
        from PIL import Image
    except Exception:
        return ""

    try:
        uploaded_file.seek(0)
        image = Image.open(uploaded_file)
        image.load()
        uploaded_file.seek(0)
    except Exception as exc:
        logger.warning("Image OCR open failed for upload %s: %s", getattr(uploaded_file, "name", ""), exc)
        return ""

    try:
        dpi = max(72, int(getattr(settings, "EXAM_PDF_OCR_DPI", 160)))
    except (TypeError, ValueError):
        dpi = 160

    image = image.convert("RGB")
    width, height = image.size
    if width <= 0 or height <= 0:
        return ""

    png_buffer = io.BytesIO()
    image.save(png_buffer, format="PNG")
    page_width = max(1, width * 72 / dpi)
    page_height = max(1, height * 72 / dpi)

    doc = fitz.open()
    try:
        page = doc.new_page(width=page_width, height=page_height)
        page.insert_image(page.rect, stream=png_buffer.getvalue())
        pdf_buffer = io.BytesIO(doc.tobytes())
    finally:
        doc.close()

    return _ocr_pdf_text(pdf_buffer)


def _ocr_page_text_with_highlights(page, textpage, zoom, detect_highlight, min_ratio, Image, dpi) -> str:
    """
    Bir səhifə üçün OCR mətnini sətir-sətir qurur. Sarı highlight aşkarı aktivdirsə,
    variant sətrinin söz-qutusu sarı ilə örtülübsə əvvəlinə "*" əlavə edir.
    """
    words = page.get_text("words", textpage=textpage) or []
    if not words:
        # Fallback: highlight aşkarı mümkün deyilsə düz mətn.
        return page.get_text(textpage=textpage) or ""

    mask = None
    if detect_highlight and Image is not None:
        try:
            pix = page.get_pixmap(dpi=dpi)
            rgb = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            mask = _build_yellow_mask(rgb)
        except Exception:
            mask = None

    mask_w, mask_h = mask.size if mask is not None else (0, 0)

    # Sözləri oxu sırasına görə (block, line) sətrlərə qrupla.
    from collections import OrderedDict

    grouped: "OrderedDict[tuple, list]" = OrderedDict()
    for word in words:
        # word = (x0, y0, x1, y1, text, block_no, line_no, word_no)
        grouped.setdefault((word[5], word[6]), []).append(word)

    lines_out: list[str] = []
    current_option_index = None
    for line_words in grouped.values():
        text = " ".join(w[4] for w in line_words).strip()
        if not text:
            continue

        line_has_yellow = _line_words_have_yellow(mask, line_words, zoom, min_ratio, mask_w, mask_h)
        match = OPTION_RE.match(text)

        if mask is not None:
            if match and not match.group(1):  # variant sətri, hələ ulduzsuz
                if line_has_yellow:
                    text = "*" + text
            elif line_has_yellow and current_option_index is not None:
                existing = lines_out[current_option_index]
                if OPTION_RE.match(existing) and not existing.lstrip().startswith("*"):
                    lines_out[current_option_index] = re.sub(r"^(\s*)", r"\1*", existing, count=1)

        if match:
            current_option_index = len(lines_out)
        elif QUESTION_RE.match(text):
            current_option_index = None

        lines_out.append(text)

    return "\n".join(lines_out)


# Yüklənmiş fayldan mətn çıxarır. Dəstəklənən formatlar: .txt, .pdf, .png, .jpg


def extract_text_from_upload(uploaded_file) -> str:
    """
    Yüklənmiş fayldan mətn çıxarır. Dəstəklənən formatlar: .txt, .pdf, .png, .jpg.
    DOCX/DOC qəsdən dəstəklənmir — makro/embed riski və qeyri-stabil parse
    nəticələri səbəbindən sual importu üçün bağlıdır (ayrıca error mesajı verilir).
    Çoxsaylı təhlükəsizlik yoxlamaları ilə birlikdə:
      - Ölçü limiti (default 45MB, settings.EXAM_UPLOAD_MAX_BYTES)
      - Faktiki magic bytes (uzantı saxtalaşdırıla bilər)
      - PDF: aktiv kontent (JS/OpenAction/EmbeddedFile) yoxlanışı
    """
    name = (uploaded_file.name or "").lower()
    ext = os.path.splitext(name)[1]

    # 1) Ölçü limiti
    _ensure_within_size_limit(uploaded_file, MAX_UPLOAD_BYTES)

    # 2) Word sənədləri artıq qəbul edilmir — istifadəçiyə aydın mesaj.
    if ext in (".docx", ".doc", ".docm", ".dotm", ".dotx", ".rtf"):
        raise ValueError(pgettext("exams.service.parsing.error", "file_docx_not_allowed"))

    # 3) Digər təhlükəli uzantıları ilkin olaraq rədd edirik
    blocked_extensions = (".xlsm", ".pptm", ".bin", ".exe", ".scr", ".js", ".html", ".htm", ".zip")
    if ext in blocked_extensions:
        raise ValueError(pgettext("exams.service.parsing.error", "file_has_macros"))

    if ext == ".txt":
        # TXT üçün magic bytes yoxdur — sadəcə oxuyuruq, lakin UTF-8 səhvini ignoryalayırıq
        return uploaded_file.read().decode("utf-8", errors="ignore")

    if ext in IMAGE_EXTENSIONS:
        signature_key = "png" if ext == ".png" else "jpg"
        head = _peek_magic_bytes(uploaded_file, 12)
        if not _verify_magic_bytes(head, signature_key):
            raise ValueError(pgettext("exams.service.parsing.error", "file_signature_mismatch"))

        normalized = _ocr_image_text(uploaded_file)
        if not normalized.strip():
            raise ValueError(pgettext("exams.service.parsing.error", "pdf_no_text_layer"))
        return normalized

    if ext == ".pdf":
        if PdfReader is None:
            raise ValueError(pgettext("exams.service.parsing.error", "pdf_dependency_missing"))

        head = _peek_magic_bytes(uploaded_file, 8)
        if not _verify_magic_bytes(head, "pdf"):
            raise ValueError(pgettext("exams.service.parsing.error", "file_signature_mismatch"))

        # PDF aktiv kontent yoxlaması
        _pdf_safety_check(uploaded_file)

        try:
            uploaded_file.seek(0)
        except Exception:
            pass

        # Skan edilmiş (mətn qatı olmayan) PDF-də pypdf 0 nəticə üçün uzun müddət
        # (saniyələrlə) sərf edir. Əvvəlcə sürətli yoxlama: mətn qatı varmı?
        # Yoxdursa (False) birbaşa OCR-a keçirik və pypdf israfını ötürürük.
        has_text_layer = _pdf_has_text_layer(uploaded_file)

        normalized = ""
        if has_text_layer is not False:
            # True və ya naməlum (köhnə/test yolu) — mövcud pypdf çıxarışı işləyir.
            try:
                reader = PdfReader(uploaded_file)
            except Exception as exc:
                logger.warning("PDF parse failed for upload %s: %s", name, exc)
                raise ValueError(pgettext("exams.service.parsing.error", "file_corrupt"))

            # Şifrli PDF-i rədd edirik — content extraction işləməz, lakin pis niyyət üçün də səbəb olar
            if getattr(reader, "is_encrypted", False):
                raise ValueError(pgettext("exams.service.parsing.error", "file_pdf_encrypted"))

            parts = []
            for page in reader.pages:
                try:
                    txt = page.extract_text() or ""
                except Exception:
                    continue
                txt = txt.strip()
                if txt:
                    parts.append(txt)

            normalized = normalize_pdf_extracted_text("\n\n".join(parts))

        # Mətn qatı tapılmadısa (skan edilmiş PDF) — OCR fallback.
        if not normalized.strip():
            normalized = _ocr_pdf_text(uploaded_file)
            if not normalized.strip():
                # OCR da nəticə vermədi (Tesseract yoxdur / şəkil keyfiyyəti aşağı /
                # OCR deaktivdir) — istifadəçiyə aydın səbəb göstəririk.
                raise ValueError(pgettext("exams.service.parsing.error", "pdf_no_text_layer"))

        # PDF highlight annotation-ları ilə mark olunmuş variantı "*" ilə işarələ
        highlight_fragments = _extract_pdf_highlights(uploaded_file)
        return _mark_correct_option_lines(normalized, highlight_fragments)

    raise ValueError(pgettext("exams.service.parsing.error", "unsupported_file_type"))


def _new_question(q_no: str, text: str) -> dict:
    return {
        "q_no": q_no,
        "text": text.strip(),
        "options": {},
        "correct": [],
        "answer_mode": "single",
        "warnings": [],
    }


def _strip_question_number(line: str, fallback_no: int) -> tuple[str, str]:
    m_q = QUESTION_RE.match(line)
    if m_q:
        return m_q.group(1), m_q.group(2).strip()
    return str(fallback_no), line.strip()


def _finish_question(current: dict | None) -> dict | None:
    if not current:
        return None

    if not current["correct"] and current.get("_answerline_correct"):
        current["correct"] = current["_answerline_correct"]

    if not current["correct"]:
        current["correct"] = ["A"]

    current["answer_mode"] = "multiple" if len(current["correct"]) > 1 else "single"
    current.pop("_answerline_correct", None)
    return current


def _is_option_continuation(line: str) -> bool:
    if not line:
        return False
    return line[0].islower() or line[0] in ",;:-)]}"


def _coerce_unlabeled_options(option_lines: list[str]) -> list[str]:
    cleaned = [line.strip() for line in option_lines if line.strip()]
    if len(option_lines) <= len(LABELS):
        while len(cleaned) < len(LABELS):
            for idx in range(len(cleaned) - 1, -1, -1):
                parts = JOINED_OPTION_BOUNDARY_RE.split(cleaned[idx], maxsplit=1)
                if len(parts) == 2 and all(len(part.strip()) > 2 for part in parts):
                    cleaned[idx : idx + 1] = [parts[0].strip(), parts[1].strip()]
                    break
            else:
                break
        return cleaned

    options: list[str] = []
    total = len(option_lines)

    for idx, line in enumerate(option_lines):
        text = line.strip()
        if not text:
            continue

        remaining_lines = total - idx
        remaining_slots_after_new_option = len(LABELS) - len(options) - 1
        can_start_new_option = len(options) < len(LABELS) and remaining_lines - 1 >= remaining_slots_after_new_option

        if options and _is_option_continuation(text):
            options[-1] += " " + text
        elif can_start_new_option:
            options.append(text)
        elif options:
            options[-1] += " " + text

    return options[: len(LABELS)]


def _question_line_index(lines: list[str]) -> int:
    last_possible_question_index = max(0, len(lines) - len(LABELS))
    for idx in range(last_possible_question_index, -1, -1):
        line = lines[idx]
        if QUESTION_RE.match(line) or "?" in line:
            return idx
    if len(lines) > len(LABELS):
        return len(lines) - len(LABELS) - 1
    return 0


def _looks_like_question_prompt(line: str) -> bool:
    text = (line or "").strip()
    if not text:
        return False

    lower = text.lower()
    question_markers = (
        "?",
        ":",
        # az
        "hansı",
        "hansıdır",
        "hansidir",
        "nədir",
        "nedir",
        "nəyi",
        "neyi",
        "kimdir",
        "harada",
        "necə",
        "nece",
        "aiddir",
        "aid edilir",
        "istifadə",
        "istifade",
        "aşağıdakı",
        "asagidaki",
        # en
        "which",
        "what",
        "following",
        # ru
        "какой",
        "какая",
        "какое",
        "которы",
        "что такое",
        "является",
        "следующ",
        # tr
        "hangisi",
        "aşağıdaki",
        "nelerdir",
    )
    return any(marker in lower for marker in question_markers)


def _split_unlabeled_question_and_options(lines: list[str], q_idx: int) -> tuple[list[str], list[str]]:
    question_lines = [lines[q_idx]]
    option_start = q_idx + 1

    while option_start < len(lines) and len(lines) - option_start > len(LABELS):
        candidate = lines[option_start]
        if not _looks_like_question_prompt(candidate):
            break
        question_lines.append(candidate)
        option_start += 1

    return question_lines, lines[option_start:]


def _parse_unlabeled_end_question_block(lines: list[str], fallback_no: int) -> dict | None:
    if len(lines) < 2:
        return None

    q_idx = _question_line_index(lines)
    question_lines, option_lines = _split_unlabeled_question_and_options(lines, q_idx)
    q_no, q_text = _strip_question_number(" ".join(question_lines), fallback_no)

    if len(option_lines) < 2:
        return None

    options = _coerce_unlabeled_options(option_lines)
    current = _new_question(q_no, q_text)
    for label, option_text in zip(LABELS, options, strict=False):
        current["options"][label] = option_text

    return _finish_question(current)


def _parse_labeled_end_question_block(lines: list[str], fallback_no: int) -> dict | None:
    question_lines: list[str] = []
    current = None
    current_opt_label = None

    for line in lines:
        m_ans = ANSWERLINE_RE.match(line)
        if m_ans and current:
            labels = re.split(r"\s*[,;/]\s*", m_ans.group(2).upper())
            seen = set()
            current["_answerline_correct"] = [
                label for label in labels if label in LABELS and not (label in seen or seen.add(label))
            ]
            continue

        m_opt = OPTION_RE.match(line)
        if m_opt:
            if current is None:
                question_text = " ".join(question_lines).strip()
                if not question_text:
                    return None
                q_no, q_text = _strip_question_number(question_text, fallback_no)
                current = _new_question(q_no, q_text)

            star = bool(m_opt.group(1))
            label = m_opt.group(2).upper()
            text = m_opt.group(3).strip()
            current["options"][label] = text
            current_opt_label = label
            if star and label not in current["correct"]:
                current["correct"].append(label)
            continue

        if current is not None and current_opt_label:
            current["options"][current_opt_label] += " " + line.strip()
        elif current is not None:
            current["text"] += " " + line.strip()
        else:
            question_lines.append(line.strip())

    return _finish_question(current)


def _parse_end_question_blocks(raw_text: str) -> list[dict]:
    questions = []
    block: list[str] = []

    def flush_block() -> None:
        nonlocal block
        if not block:
            return

        fallback_no = len(questions) + 1
        parser = (
            _parse_labeled_end_question_block
            if any(OPTION_RE.match(line) for line in block)
            else _parse_unlabeled_end_question_block
        )
        parsed = parser(block, fallback_no)
        if parsed:
            questions.append(parsed)
        block = []

    for raw in raw_text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if END_QUESTION_RE.match(line):
            flush_block()
            continue
        block.append(line)

    flush_block()
    return questions


# Severity səviyyələri — UI-da rəngləməni və "blok edirmi?" qərarını bunlara görə veririk
SEVERITY_ERROR = "error"  # qırmızı — saxlanışı blok etməyə bilər, amma diqqət vacibdir
SEVERITY_WARNING = "warning"  # sarı — informativ xəbərdarlıq
SEVERITY_INFO = "info"  # mavi — sadəcə yumşaq qeyd


def _add_warning(q: dict, w_type: str, msg: str, severity: str = SEVERITY_WARNING, **extra) -> None:
    payload = {"type": w_type, "msg": msg, "severity": severity}
    payload.update(extra)
    q["warnings"].append(payload)


def _validate_questions(questions: list[dict]) -> None:
    for q in questions:
        opts = q.get("options", {}) or {}

        # missing A-D — bunlar minimum tələbdir, ERROR
        for must in ["A", "B", "C", "D"]:
            if must not in opts:
                _add_warning(
                    q,
                    "missing_option",
                    pgettext("exams.service.parsing.warning", "missing_option").format(option=must),
                    severity=SEVERITY_ERROR,
                )

        # Variant sayı: standart 5 (A-E). 4 olarsa — sarı warning, 3 və daha az — minimum_option warning-i artıq qoyulub.
        present_labels = [lab for lab in ["A", "B", "C", "D", "E"] if lab in opts]
        option_count = len(present_labels)
        if option_count == 4 and "E" not in opts:
            _add_warning(
                q,
                "option_count_recommend_5",
                pgettext("exams.service.parsing.warning", "option_count_recommend_5").format(count=option_count),
                severity=SEVERITY_WARNING,
            )
        elif option_count < 4:
            # missing A/B/C/D artıq error verdi — bunu info səviyyəsində əlavə eləyirik
            _add_warning(
                q,
                "option_count_too_low",
                pgettext("exams.service.parsing.warning", "option_count_too_low").format(count=option_count),
                severity=SEVERITY_ERROR,
            )

        # duplicate options text warning
        norm_map = defaultdict(list)
        for lab, txt in opts.items():
            norm_map[_norm(txt)].append(lab)

        dup_groups = [labs for norm_txt, labs in norm_map.items() if norm_txt and len(labs) > 1]
        for labs in dup_groups:
            _add_warning(
                q,
                "duplicate_option_text",
                pgettext("exams.service.parsing.warning", "duplicate_option_text").format(labels=", ".join(labs)),
                severity=SEVERITY_WARNING,
            )

        # correct label exists?
        for c in q.get("correct", []):
            if c not in opts:
                _add_warning(
                    q,
                    "correct_missing",
                    pgettext("exams.service.parsing.warning", "correct_missing").format(option=c),
                    severity=SEVERITY_ERROR,
                )

        # boş və ya çox qısa variant mətnləri (UX faydası: spam/yanlış parse halı)
        for lab in present_labels:
            txt = (opts.get(lab) or "").strip()
            if not txt:
                _add_warning(
                    q,
                    "empty_option_text",
                    pgettext("exams.service.parsing.warning", "empty_option_text").format(option=lab),
                    severity=SEVERITY_ERROR,
                )

        # uzunluq/balans xəbərdarlığı — yalnız doğru cavabı çox uzun/qısa olduqda
        correct_labels = [c for c in q.get("correct", []) if c in opts]
        wrong_labels = [lab for lab in present_labels if lab not in correct_labels]
        if correct_labels and wrong_labels:
            correct_lengths = [len((opts.get(c) or "").strip()) for c in correct_labels]
            wrong_lengths = [len((opts.get(w) or "").strip()) for w in wrong_labels]
            if correct_lengths and wrong_lengths:
                max_correct = max(correct_lengths)
                max_wrong = max(wrong_lengths)
                avg_wrong = sum(wrong_lengths) / max(1, len(wrong_lengths))
                # yalnız doğru cavab çox uzundursa (≥1.8x ortalama yanlışdan və ≥15 simvol)
                if max_correct >= 15 and avg_wrong > 0 and max_correct >= avg_wrong * 1.8:
                    _add_warning(
                        q,
                        "correct_too_long",
                        pgettext("exams.service.parsing.warning", "correct_too_long"),
                        severity=SEVERITY_INFO,
                    )
                # və ya yalnız doğru cavab çox qısadır (≤0.4x və yanlışlar uzundur)
                elif max_wrong >= 15 and max_correct > 0 and max_correct <= avg_wrong * 0.4:
                    _add_warning(
                        q,
                        "correct_too_short",
                        pgettext("exams.service.parsing.warning", "correct_too_short"),
                        severity=SEVERITY_INFO,
                    )


# PDF-dən çıxan və ya digər mənbədən alınan raw mətni parser üçün strukturlaşdırılmış sual formatına çevirir


def parse_bulk_mcq(raw_text: str):
    """
    Output:
      questions: list[
        {
          "q_no": "12" (mətn içindəki nömrə),
          "text": "...",
          "options": {"A": "...", ..., "E": "..."},
          "correct": ["A"] or ["A","C"],
          "answer_mode": "single"|"multiple",
          "warnings": [ {type, msg, ref?}, ... ]
        }
      ]
    """
    # Ön-emal: kiril etiketləri (rus tərcümələri), tək qalmış sual nömrələri
    # və bullet/√ markerləri parserin tanıdığı "A) / *B)" formasına salınır.
    raw_text = _normalize_cyrillic_option_labels(raw_text or "")
    raw_text = _merge_bare_question_numbers(raw_text)
    raw_text = _convert_marker_options(raw_text)

    if any(END_QUESTION_RE.match(line) for line in raw_text.splitlines()):
        questions = _parse_end_question_blocks(raw_text)
        if questions:
            _validate_questions(questions)
            return questions

    lines = raw_text.splitlines()
    OUTSIDE, IN_Q, IN_OPT = 0, 1, 2

    state = OUTSIDE
    current = None
    current_opt_label = None

    def close_option():
        nonlocal current_opt_label
        current_opt_label = None

    def close_question():
        nonlocal current, current_opt_label, state
        if not current:
            return
        close_option()

        finished = _finish_question(current)
        if finished:
            questions.append(finished)

        current = None
        current_opt_label = None
        state = OUTSIDE

    questions = []

    for raw in lines:
        line = raw.rstrip("\n")
        if not line.strip():
            continue

        # Answer line (istənilən yerdə ola bilər)
        m_ans = ANSWERLINE_RE.match(line)
        if m_ans and current:
            labels = re.split(r"\s*[,;/]\s*", m_ans.group(2).upper())
            labels = [x for x in labels if x in list("ABCDE")]
            # uniq preserve order
            seen = set()
            uniq = []
            for x in labels:
                if x not in seen:
                    uniq.append(x)
                    seen.add(x)
            current["_answerline_correct"] = uniq
            continue

        # OPTION?
        m_opt = OPTION_RE.match(line)
        if m_opt and current:
            star = bool(m_opt.group(1))
            label = m_opt.group(2).upper()
            text = m_opt.group(3).strip()

            current["options"][label] = text
            current_opt_label = label
            state = IN_OPT
            if star and label not in current["correct"]:
                current["correct"].append(label)
            continue

        # QUESTION START?
        m_q = QUESTION_RE.match(line)

        if state == OUTSIDE and m_q:
            # yeni sual
            current = _new_question(m_q.group(1), m_q.group(2).strip())
            state = IN_Q
            continue

        # Əgər artıq sualın içindəyiksə:
        if current:
            # Əgər option bitib və yeni sual başlayırsa
            if state == IN_OPT and m_q and len(current["options"]) >= 4:
                # əvvəlki sualı bağla, yenisini başlat
                close_question()
                current = _new_question(m_q.group(1), m_q.group(2).strip())
                state = IN_Q
                continue
            # IN_Q vəziyyətində və yeni sual gəlirsə
            elif state == IN_Q and m_q and current["options"]:
                close_question()
                current = _new_question(m_q.group(1), m_q.group(2).strip())
                state = IN_Q
                continue

            # Əks halda bu sətir ya sualın davamıdır, ya da variantın davamıdır
            if state == IN_OPT and current_opt_label:
                current["options"][current_opt_label] += " " + line.strip()
            else:
                current["text"] += " " + line.strip()
        else:
            # OUTSIDE ikən sual formatına düşməyən mətn → ignore
            pass

    # axırı bağla
    if current:
        close_question()

    _validate_questions(questions)

    return questions
