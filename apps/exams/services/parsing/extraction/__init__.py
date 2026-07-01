"""extraction — parsing paketinin geriyə-uyğun alt-fasadı.
Bütün simvollar (PdfReader, fitz daxil) re-export olunur ki, parsing/__init__
və facade-patch (`patch.object(parsing, ...)`) işləsin."""

from ._deps import PdfReader, fitz  # noqa: F401
from .constants import (  # noqa: F401
    _BARE_QNO_RE,
    _BULLET_CHARS,
    _BULLET_OPTION_LINE_RE,
    _CHECK_CHARS,
    _CHECK_OPTION_LINE_RE,
    _CYR_ANSWERLINE_RE,
    _CYR_OPTION_LABEL_RE,
    _CYRILLIC_LOOKALIKE_MAP,
    _CYRILLIC_SEQ_MAP,
    _HIGHLIGHT_CORE_RE,
    END_QUESTION_RE,
    FILE_SIGNATURES,
    IMAGE_EXTENSIONS,
    JOINED_OPTION_BOUNDARY_RE,
    MAX_UPLOAD_BYTES,
    logger,
)
from .highlight import (  # noqa: F401
    _build_yellow_mask,
    _extract_pdf_highlights,
    _frag_label_and_core,
    _fragment_matches_option,
    _highlight_core,
    _line_words_have_yellow,
    _line_yellow_ratio,
    _mark_correct_option_lines,
    _mark_correct_options_by_position,
    _pdf_has_text_layer,
    _word_bbox,
)
from .normalize import (  # noqa: F401
    _convert_marker_options,
    _merge_bare_question_numbers,
    _normalize_cyrillic_option_labels,
    normalize_pdf_extracted_text,
)
from .ocr import (  # noqa: F401
    _ensure_tessdata_prefix,
    _ocr_image_text,
    _ocr_page_text_with_highlights,
    _ocr_pdf_text,
)
from .pipeline import (  # noqa: F401
    extract_text_from_upload,
)
from .safety import (  # noqa: F401
    _ensure_within_size_limit,
    _pdf_safety_check,
    _peek_magic_bytes,
    _verify_magic_bytes,
)
