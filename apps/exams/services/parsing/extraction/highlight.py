"""extraction paketi — highlight."""

import re

from apps.exams.constants import OPTION_RE, QUESTION_RE
from apps.exams.services.pdf_math import Q_SEQUENCE_GAP as _Q_SEQ_GAP

from ._deps import fitz
from .constants import (
    _HIGHLIGHT_CORE_RE,
    logger,
)


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
