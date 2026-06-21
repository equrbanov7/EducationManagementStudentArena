"""
Riyazi məzmunlu PDF-lərdən sual idxalı üçün köməkçi servis.

Problem
-------
Word/Mathcad/MathType ilə hazırlanmış imtahan PDF-lərində düsturlar əsl Unicode
mətn KİMİ saxlanmır. Onlar "Symbol" fontunun Private-Use-Area (PUA) glyph-ləri
ilə qurulur (məs. ``\\uf028`` = ``(``, ``\\uf03d`` = ``=``, ``\\uf0e6`` = matris
mötərizəsinin yuxarı küncü). ``pypdf.extract_text()`` bu glyph-ləri ya zibilə
çevirir, ya da iki sətirli matris/kəsr strukturlarını bir-birinə qarışdırır.

Həll — best practice (LMS/Moodle/Canvas idxal axınları ilə eyni prinsip):

1. **Glyph remapping** — sətirli (1D) riyaziyyat üçün: Symbol PUA glyph-lərini
   standart Adobe Symbol kodlaşmasına görə əsl Unicode-a çeviririk. Bu, mötərizə,
   bərabərlik, operator, yunan hərfləri və funksiya çağırışlarını ``rows(m)``,
   ``plot("y","z")`` kimi təmiz bərpa edir. Mətn axtarıla/redaktə edilə bilən qalır.

2. **Region → şəkil** — sətirə sığmayan (2D) riyaziyyat üçün (matris, kəsr, kök,
   sütun-vektor): həmin PDF sahəsini yüksək DPI PNG kimi kəsib sualın/variantın
   ``image`` sahəsinə bağlayırıq. Düstur orijinaldakı kimi dəqiq görünür.

Modul tam müdafiəlidir: ``PyMuPDF (fitz)`` quraşdırılmayıbsa və ya hər hansı
xəta olarsa, remap mətni olduğu kimi qaytarır, şəkil çıxarışı isə boş ``{}``
qaytarır — mövcud mətn idxalı heç vaxt sınmır.
"""

from __future__ import annotations

import logging

from apps.exams.constants import OPTION_RE, QUESTION_RE

try:
    import fitz  # PyMuPDF — opsionaldır
except ImportError:  # pragma: no cover - mühitdən asılıdır
    fitz = None
else:
    # Bu cür sənədlərdə (qüsurlu çəkim axınları) fitz stderr-ə minlərlə
    # zərərsiz "syntax error" yazır. Mətn/şəkil çıxarışına təsir etmir,
    # ona görə logu çirkləndirməsin deyə söndürürük.
    try:
        fitz.TOOLS.mupdf_display_errors(False)
    except Exception:  # pragma: no cover
        pass

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 1) Symbol font → Unicode (Adobe "Symbol" standart kodlaşması)
# ---------------------------------------------------------------------------
# Açar = Symbol fontunun simvol kodu (0x20–0xFE). PDF mətnində bu glyph-lər
# PUA-da, yəni ``0xF000 + kod`` kimi görünür (məs. "(" → 0xF028).
SYMBOL_TO_UNICODE: dict[int, str] = {
    # ASCII ilə üst-üstə düşən durğu/operatorlar
    0x20: " ",
    0x21: "!",
    0x22: "∀",
    0x23: "#",
    0x24: "∃",
    0x25: "%",
    0x26: "&",
    0x27: "∋",
    0x28: "(",
    0x29: ")",
    0x2A: "∗",
    0x2B: "+",
    0x2C: ",",
    0x2D: "−",
    0x2E: ".",
    0x2F: "/",
    0x3A: ":",
    0x3B: ";",
    0x3C: "<",
    0x3D: "=",
    0x3E: ">",
    0x3F: "?",
    0x40: "≅",
    0x5B: "[",
    0x5C: "∴",
    0x5D: "]",
    0x5E: "⊥",
    0x5F: "_",
    0x60: "‾",
    0x7B: "{",
    0x7C: "|",
    0x7D: "}",
    0x7E: "~",
    # Yunan böyük hərflər
    0x41: "Α",
    0x42: "Β",
    0x43: "Χ",
    0x44: "Δ",
    0x45: "Ε",
    0x46: "Φ",
    0x47: "Γ",
    0x48: "Η",
    0x49: "Ι",
    0x4A: "ϑ",
    0x4B: "Κ",
    0x4C: "Λ",
    0x4D: "Μ",
    0x4E: "Ν",
    0x4F: "Ο",
    0x50: "Π",
    0x51: "Θ",
    0x52: "Ρ",
    0x53: "Σ",
    0x54: "Τ",
    0x55: "Υ",
    0x56: "ς",
    0x57: "Ω",
    0x58: "Ξ",
    0x59: "Ψ",
    0x5A: "Ζ",
    # Yunan kiçik hərflər
    0x61: "α",
    0x62: "β",
    0x63: "χ",
    0x64: "δ",
    0x65: "ε",
    0x66: "φ",
    0x67: "γ",
    0x68: "η",
    0x69: "ι",
    0x6A: "ϕ",
    0x6B: "κ",
    0x6C: "λ",
    0x6D: "μ",
    0x6E: "ν",
    0x6F: "ο",
    0x70: "π",
    0x71: "θ",
    0x72: "ρ",
    0x73: "σ",
    0x74: "τ",
    0x75: "υ",
    0x76: "ϖ",
    0x77: "ω",
    0x78: "ξ",
    0x79: "ψ",
    0x7A: "ζ",
    # Riyazi operatorlar (yuxarı diapazon)
    0xA3: "≤",
    0xA5: "∞",
    0xB0: "°",
    0xB1: "±",
    0xB2: "″",
    0xB3: "≥",
    0xB4: "×",
    0xB5: "∝",
    0xB6: "∂",
    0xB7: "•",
    0xB8: "÷",
    0xB9: "≠",
    0xBA: "≡",
    0xBB: "≈",
    0xBC: "…",
    0xC5: "⊕",
    0xD6: "√",
    0xD7: "⋅",
    0xE5: "∑",
    0xF2: "∫",
    # Böyük (çoxsətirli) sərhəd glyph-ləri — matris/kəsr/vektor strukturları
    0xE6: "⎛",
    0xE7: "⎜",
    0xE8: "⎝",
    0xF6: "⎞",
    0xF7: "⎟",
    0xF8: "⎠",
    0xE9: "⎡",
    0xEA: "⎢",
    0xEB: "⎣",
    0xF9: "⎤",
    0xFA: "⎥",
    0xFB: "⎦",
    0xEC: "⎧",
    0xED: "⎨",
    0xEE: "⎩",
    0xFC: "⎫",
    0xFD: "⎬",
    0xFE: "⎭",
}

# PUA diapazonu: Symbol glyph-ləri bu aralıqda görünür.
_PUA_LOW, _PUA_HIGH = 0xF000, 0xF0FF

# 2D struktur glyph-ləri (Symbol kodları) — bunlar varsa düstur sətirə sığmır,
# deməli region-şəkil lazımdır: böyük mötərizələr + kök + inteqral + cəm.
STRUCTURAL_SYMBOL_CODES: frozenset[int] = frozenset(
    {
        0xE6,
        0xE7,
        0xE8,
        0xE9,
        0xEA,
        0xEB,
        0xEC,
        0xED,
        0xEE,
        0xF6,
        0xF7,
        0xF8,
        0xF9,
        0xFA,
        0xFB,
        0xFC,
        0xFD,
        0xFE,
        0xD6,
        0xF2,
        0xE5,
    }
)


def remap_symbol_pua(text: str) -> str:
    """
    Symbol fontunun PUA glyph-lərini əsl Unicode simvollarına çevirir.

    PUA-da olmayan və ya cədvəldə tapılmayan simvollar dəyişmədən qalır,
    ona görə adi mətnə heç bir təsir etmir (idempotent və təhlükəsizdir).
    """
    if not text:
        return text

    def _translate(ch: str) -> str:
        code = ord(ch)
        if _PUA_LOW <= code <= _PUA_HIGH:
            return SYMBOL_TO_UNICODE.get(code - 0xF000, ch)
        return ch

    # Sürətli yol: PUA glyph yoxdursa toxunmuruq.
    if not any(_PUA_LOW <= ord(c) <= _PUA_HIGH for c in text):
        return text

    return "".join(_translate(c) for c in text)


# ---------------------------------------------------------------------------
# 2) 2D riyazi region → PNG
# ---------------------------------------------------------------------------
# Render keyfiyyəti və təhlükəsizlik limitləri (settings ilə dəyişdirilə bilər).
_RENDER_ZOOM = 3.0  # ~216 DPI — ekran üçün kifayət qədər iti
_REGION_PAD = 4.0  # region ətrafına kiçik boşluq (px)
_MAX_PAGES = 60  # DoS-a qarşı: maksimum səhifə sayı


def _iter_pages(doc):
    """
    Sənədin səhifələrini (maksimum _MAX_PAGES) versiya-dayanıqlı şəkildə gəzir.
    ``doc[:n]`` dilimləməsi bəzi köhnə PyMuPDF versiyalarında dəstəklənmir —
    ona görə indekslə gedirik.
    """
    try:
        total = doc.page_count
    except Exception:  # pragma: no cover
        total = len(doc)
    for i in range(min(total, _MAX_PAGES)):
        yield doc[i]


def _has_structural_glyph(text: str) -> bool:
    return any(_PUA_LOW <= ord(c) <= _PUA_HIGH and (ord(c) - 0xF000) in STRUCTURAL_SYMBOL_CODES for c in text)


def _iter_text_lines(page):
    """Səhifədəki mətn sətirlərini (bbox, text) cütləri kimi qaytarır."""
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        if block.get("type") != 0:  # 0 = mətn bloku
            continue
        for line in block.get("lines", []):
            txt = "".join(span.get("text", "") for span in line.get("spans", []))
            yield line["bbox"], txt


def _build_anchors(lines):
    """
    Sətirlərdən sual və variant ankerlərini qurur.

    Qaytarır: list[(y_top, q_no, option_label_or_None)] — y-ə görə sıralı.
    """
    anchors = []
    current_q = None
    for bbox, txt in lines:
        y_top = float(bbox[1])
        # Parserlə eyni regex-lər: anker təyini ilə sual parse-ı sinxron qalır.
        q_match = QUESTION_RE.match(txt)
        if q_match:
            current_q = q_match.group(1)
            anchors.append((y_top, current_q, None))
            continue
        opt_match = OPTION_RE.match(txt)
        if opt_match and current_q is not None:
            anchors.append((y_top, current_q, opt_match.group(2).upper()))
    anchors.sort(key=lambda a: a[0])
    return anchors


def _owner_for_y(center_y: float, anchors):
    """
    Verilmiş şaquli mövqeyi əhatə edən ən yaxın yuxarı ankeri tapır.
    Qaytarır: (q_no, option_label_or_None) və ya None.
    """
    owner = None
    for y_top, q_no, label in anchors:
        if y_top <= center_y:
            owner = (q_no, label)
        else:
            break
    return owner


def _regions_by_owner(lines, anchors):
    """
    Struktur (2D) glyph-i olan sətirləri ƏVVƏLCƏ sahibinə (sual stem-i və ya
    konkret variant) görə qruplaşdırır, sonra hər sahib üçün onları tək region
    kimi birləşdirir. Bu yanaşma qonşu variant matrislərinin bir-birinə
    "axmasının" qarşısını alır — hər variant öz şəklini alır.

    Qaytarır: dict[(q_no, label)] -> fitz.Rect
    """
    grouped: dict[tuple, "fitz.Rect"] = {}
    for bbox, txt in lines:
        if not _has_structural_glyph(txt):
            continue
        rect = fitz.Rect(bbox)
        owner = _owner_for_y((rect.y0 + rect.y1) / 2, anchors)
        if owner is None:
            continue
        if owner in grouped:
            grouped[owner] |= rect  # union
        else:
            grouped[owner] = rect
    return grouped


def _render_region(page, region: "fitz.Rect") -> bytes:
    """Region-ı tam səhifə eni boyunca yüksək DPI PNG kimi render edir."""
    # Düsturun bütün enini tutmaq üçün clip-i səhifə eninə genişləndiririk,
    # şaquli olaraq isə yalnız region + kiçik boşluq.
    clip = fitz.Rect(
        page.rect.x0 + 2,
        max(page.rect.y0, region.y0 - _REGION_PAD),
        page.rect.x1 - 2,
        min(page.rect.y1, region.y1 + _REGION_PAD),
    )
    pix = page.get_pixmap(matrix=fitz.Matrix(_RENDER_ZOOM, _RENDER_ZOOM), clip=clip)
    return pix.tobytes("png")


def extract_math_images(file_or_bytes) -> dict[str, dict]:
    """
    PDF-dəki 2D riyazi regionları (matris, kəsr, kök, sütun-vektor) aşkar edib
    PNG bytes kimi qaytarır, sual nömrəsi və variant etiketinə görə açarlanır.

    Nəticə formatı::

        {
          "3": {"stem": b"...png...", "options": {}},
          "6": {"stem": None, "options": {"B": b"...", "C": b"..."}},
        }

    "stem" — sualın özünün (variantlardan əvvəlki) düstur şəkli.
    "options" — hər variantın (A–E) öz düstur şəkli.

    fitz yoxdursa və ya hər hansı xəta olarsa boş dict qaytarır (mətn idxalı
    yenə işləyər, sadəcə şəkil bağlanmaz).
    """
    if fitz is None:
        return {}

    data = _read_bytes(file_or_bytes)
    if not data:
        return {}

    result: dict[str, dict] = {}
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            for page in _iter_pages(doc):
                lines = list(_iter_text_lines(page))
                if not lines:
                    continue
                anchors = _build_anchors(lines)
                if not anchors:
                    continue
                for (q_no, label), region in _regions_by_owner(lines, anchors).items():
                    try:
                        png = _render_region(page, region)
                    except Exception as exc:  # pragma: no cover
                        logger.warning("Math region render failed (q=%s): %s", q_no, exc)
                        continue
                    bucket = result.setdefault(q_no, {"stem": None, "options": {}})
                    if label is None:
                        bucket["stem"] = png
                    else:
                        bucket["options"][label] = png
    except Exception as exc:  # pragma: no cover - korlanmış PDF və s.
        logger.warning("extract_math_images failed: %s", exc)
        return {}

    return result


# ---------------------------------------------------------------------------
# 3) Highlight (sarı işarələmə) → düzgün cavab — MÖVQE əsaslı
# ---------------------------------------------------------------------------
# Köhnə yanaşma highlight mətnini YALNIZ etiketə görə (qlobal) uyğunlaşdırırdı:
# sənəddə harasa "A)", "B)" ... düzgün cavab kimi işarələndiyi üçün HƏR sualın
# bütün variantları "düzgün" sayılırdı və parser default "A"-ya düşürdü.
#
# Düzgün həll: highlight-ı onun fiziki yerləşdiyi suala + variantа bağlamaq.
# Hər highlight düzbucaqlısı yalnız ən çox üst-üstə düşdüyü TƏK variantа aid edilir.

# Highlight üçün minimum şaquli üst-üstə düşmə (px) — təsadüfi toxunmanı kəsir.
_MIN_HL_OVERLAP = 4.0

# Sual nömrəsi izləməsi üçün maksimum sıçrayış. Real imtahanda nömrələr ardıcıl
# artır; düstur mətnindəki iri rəqəmlər (məs. "...0 0 81") saxta anker yaratdıqda
# bu məhdudiyyət onları rədd edir. parsing.py eyni sabiti import edir.
Q_SEQUENCE_GAP = 3


def _is_yellow_fill(fill) -> bool:
    """RGB fill rəngi sarıdırmı (yüksək R+G, aşağı B)? — annotation-suz PDF-lər üçün."""
    return bool(fill) and len(fill) >= 3 and fill[0] > 0.85 and fill[1] > 0.8 and fill[2] < 0.6


def _highlight_rects(page) -> list:
    """
    Səhifədəki highlight sahələrini toplayır: həm Highlight annotation-ları
    (tip 8), həm də sarı dolğulu düzbucaqlılar (Word/PDF ixracı annotation
    yaratmadıqda). Eyni highlight iki dəfə düşsə belə nəticəyə təsir etmir —
    çünki hər biri ən yaxşı uyğun variantа bağlanır.
    """
    rects = []
    try:
        # page.annots() — bütün PyMuPDF versiyalarında stabil iterator
        # (köhnə `first_annot`/`.next` zənciri bəzi versiyalarda problemlidir).
        for annot in page.annots() or []:
            if annot.type and annot.type[0] == 8:  # PDF_ANNOT_HIGHLIGHT
                rects.append(fitz.Rect(annot.rect))
    except Exception:  # pragma: no cover
        pass
    try:
        for drawing in page.get_drawings():
            if _is_yellow_fill(drawing.get("fill")):
                rects.append(drawing["rect"])
    except Exception:  # pragma: no cover
        pass
    return rects


def _vertical_overlap(a, b) -> float:
    return max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))


def extract_correct_labels(file_or_bytes) -> dict[str, set]:
    """
    Highlight ilə işarələnmiş düzgün cavabları MÖVQEYƏ görə aşkar edir.

    Qaytarır: ``{q_no: {"D"}, ...}`` — hər sual nömrəsi üçün düzgün variant
    etiket(lər)i. Highlight tapılmazsa boş dict (parser öz default-una düşür).

    Sual nömrəsi izləməsi **monotondur** (yalnız artan nömrə real sual sayılır)
    — beləliklə variant mətnindəki təsadüfi rəqəmlər yanlış anker yaratmır.
    Eyni səbəbdən ``current_q`` səhifələr arası saxlanılır (sualın variantları
    növbəti səhifəyə keçə bilər).
    """
    if fitz is None:
        return {}
    data = _read_bytes(file_or_bytes)
    if not data:
        return {}

    result: dict[str, set] = {}
    current_q = None
    max_q = 0
    try:
        with fitz.open(stream=data, filetype="pdf") as doc:
            for page in _iter_pages(doc):
                rects = _highlight_rects(page)
                # Bu səhifədəki variant sətirlərini bbox ilə topla (highlight olsun-olmasın,
                # sual nömrəsi izləməsi davam etməlidir).
                options = []  # list[(q_no, label, fitz.Rect)]
                for bbox, txt in _iter_text_lines(page):
                    q_match = QUESTION_RE.match(txt)
                    if q_match:
                        n = int(q_match.group(1))
                        if max_q < n <= max_q + Q_SEQUENCE_GAP:
                            max_q = n
                            current_q = str(n)
                        continue
                    opt_match = OPTION_RE.match(txt)
                    if opt_match and current_q is not None:
                        options.append((current_q, opt_match.group(2).upper(), fitz.Rect(bbox)))

                # Hər highlight → ən çox üst-üstə düşən tək variant.
                for hl in rects:
                    best, best_overlap = None, 0.0
                    for q_no, label, rect in options:
                        overlap = _vertical_overlap(rect, hl)
                        if overlap > best_overlap:
                            best_overlap, best = overlap, (q_no, label)
                    if best is not None and best_overlap >= _MIN_HL_OVERLAP:
                        result.setdefault(best[0], set()).add(best[1])
    except Exception as exc:  # pragma: no cover
        logger.warning("extract_correct_labels failed: %s", exc)
        return {}

    return result


def _read_bytes(file_or_bytes) -> bytes:
    """UploadedFile, file-like və ya bytes-dan xam baytları təhlükəsiz oxuyur."""
    if isinstance(file_or_bytes, (bytes, bytearray)):
        return bytes(file_or_bytes)
    try:
        file_or_bytes.seek(0)
        data = file_or_bytes.read()
        file_or_bytes.seek(0)
        return data or b""
    except Exception:
        return b""
