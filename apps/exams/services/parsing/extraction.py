"""PDF/şəkil yükləməsindən təmiz mətn çıxarışı: fayl təhlükəsizliyi,
normalizasiya, highlight aşkarlanması və OCR. parsing paketinin alt-moduludur.
(Avtomatik bölgü — köhnə parsing.py-nin 1-ci hissəsi, davranış dəyişməyib.)
"""

import io
import logging
import os
import re

from django.conf import settings
from django.utils.translation import pgettext

from apps.exams.constants import LABELS, OPTION_RE, QUESTION_RE
from apps.exams.services.pdf_math import Q_SEQUENCE_GAP as _Q_SEQ_GAP
from apps.exams.services.pdf_math import extract_correct_labels, remap_symbol_pua

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
    - Symbol fontunun PUA glyph-lərini əsl Unicode-a çevirir (düstur mətni)
    - sual nömrələrinin qabağına boş sətir əlavə edir (… \n\n12) …)
    - A–E variantlarının qabağına newline əlavə edir (… \nA) …)
    - "Cavab:" sətrini yeni sətrə keçirir
    - '*' işarəsi ilə variant arasında boşluğu düzəldir (*A) kimi)
    - bullet (•) və işarə (√) markerlərini yeni sətirdən başladır
    """
    if not text:
        return ""

    # Mathcad/MathType düsturlarının Symbol-font glyph-lərini bərpa et:
    # "rowsm" → "rows(m)". Adi mətnə təsir etmir.
    t = remap_symbol_pua(text).replace("\r", "\n")

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


def _mark_correct_options_by_position(text: str, correct_map: dict) -> str:
    """
    MÖVQE əsaslı highlight nəticəsini (``{q_no: {labels}}``) tətbiq edir:
    hər sualın yalnız işarələnmiş variant(lar)ının əvvəlinə "*" qoyur.

    Sual nömrəsini izləyir və açar (çap olunmuş sual nömrəsi) ilə correct_map-ı
    uyğunlaşdırır. İzləmə MƏHDUD-ARALIQLI monotondur: real sual nömrəsi ardıcıl
    artır (n = max_q+1), ona görə yalnız ``max_q < n <= max_q + _Q_SEQ_GAP``
    qəbul edilir. Bu, düstur mətnindəki iri rəqəmlərin (məs. "...81") saxta sual
    ankeri yaratmasının qarşısını alır — əks halda izləmə tullanıb ilişir və
    suallar işarələnmir. Map boşdursa mətn olduğu kimi qaytarılır.
    """
    if not correct_map:
        return text

    out_lines = []
    current_q = None
    max_q = 0
    for line in text.splitlines():
        q_match = QUESTION_RE.match(line)
        if q_match:
            n = int(q_match.group(1))
            if max_q < n <= max_q + _Q_SEQ_GAP:
                max_q = n
                current_q = str(n)
            out_lines.append(line)
            continue

        m = OPTION_RE.match(line)
        if m and not m.group(1) and current_q is not None:  # işarələnməmiş variant sətri
            label = m.group(2).upper()
            if label in correct_map.get(current_q, ()):  # type: ignore[arg-type]
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
    # `PdfReader` və `_ocr_image_text` testlərdə `patch.object(parsing, ...)` ilə
    # əvəz olunur. parsing artıq paketdir və patch fasad (__init__) namespace-inə
    # dəyər; ona görə bu iki asılılığı call-time fasaddan həll edirik ki, mock
    # təsirli olsun. (Digər köməkçilər lokal modul global-larından gəlir.)
    from apps.exams.services import parsing as _facade

    PdfReader = _facade.PdfReader
    _ocr_image_text = _facade._ocr_image_text

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

        # PDF highlight (sarı işarələmə) ilə mark olunmuş variantı "*" ilə işarələ.
        # MÖVQE əsaslı: hər highlight öz sualına+variantına bağlanır (köhnə qlobal
        # etiket uyğunluğu bütün variantları yanlış işarələyirdi).
        correct_map = extract_correct_labels(uploaded_file)
        return _mark_correct_options_by_position(normalized, correct_map)

    raise ValueError(pgettext("exams.service.parsing.error", "unsupported_file_type"))
