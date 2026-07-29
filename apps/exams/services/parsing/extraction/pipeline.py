"""extraction paketi — pipeline."""

import os

from django.utils.translation import pgettext

from apps.exams.services.pdf_math import extract_correct_labels

from .constants import (
    IMAGE_EXTENSIONS,
    MAX_UPLOAD_BYTES,
    logger,
)
from .highlight import (
    _mark_correct_options_by_position,
    _pdf_has_text_layer,
)
from .normalize import (
    normalize_pdf_extracted_text,
)
from .ocr import (
    _ocr_pdf_text,
)
from .safety import (
    _ensure_within_size_limit,
    _pdf_safety_check,
    _peek_magic_bytes,
    _verify_magic_bytes,
)


def _geometry_mcq_text(uploaded_file) -> str:
    """Etibarlı MCQ layout-u varsa vizual manifestin canonical mətnini qaytar."""

    try:
        uploaded_file.seek(0)
        data = uploaded_file.read()
    except Exception:
        return ""
    finally:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass

    try:
        from apps.exams.services.pdf_layout import LayoutConfidenceError, extract_pdf_layout

        return extract_pdf_layout(data, fail_closed=True).canonical_text
    except LayoutConfidenceError:
        # Sənəd MCQ olmaya bilər (məsələn, AI üçün yüklənən mühazirə PDF-i).
        # Bu halda mövcud ümumi mətn çıxarışı işləməyə davam edir.
        return ""
    except Exception as exc:
        logger.warning("PDF geometry extraction failed: %s", exc)
        return ""


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

            # Etibarlı test layout-u tapıldıqda canonical mətn də eyni
            # geometriya manifestindən gəlir. Beləliklə düstur içindəki rəqəm və
            # A–E simvolları saxta sual/variant sərhədi yaratmır.
            normalized = _geometry_mcq_text(uploaded_file)
            if not normalized:
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
