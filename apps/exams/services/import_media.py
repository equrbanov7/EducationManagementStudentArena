"""
Sual idxalında düstur şəkillərini iki addımlı (preview → save) axında daşımaq.

Problem: "preview" addımında fayl yüklənir və şəkillər çıxarılır, lakin "save"
addımında yalnız mətn (raw_text) gizli form sahəsi ilə geri gəlir — fayl təkrar
yüklənmir. Ona görə şəkilləri preview zamanı müvəqqəti yığırıq (token altında),
save zamanı isə sual nömrəsinə görə tapıb modelin ``image`` sahəsinə bağlayırıq.

İstifadə (view-da):

    # preview addımında, fayl oxunandan sonra:
    token = stash_math_images(uploaded) or ""
    # token-i gizli sahə kimi şablona ötür (context["math_token"] = token)

    # save addımında, hər sual/variant yaradılandan sonra:
    attach_math_images(token, q_no, question)   # question.options artıq mövcud olmalıdır
    # bütün suallar saxlanandan sonra:
    clear_stash(token)
"""

from __future__ import annotations

import logging
import re
import shutil
import uuid
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile

from apps.exams.services.pdf_math import extract_math_images

logger = logging.getLogger(__name__)

# MEDIA_ROOT altında müvəqqəti idxal qovluğu.
_IMPORT_SUBDIR = "question_imports"
# Token formatı: yalnız hex — yol manipulyasiyasına (path traversal) qarşı.
_TOKEN_RE = re.compile(r"^[0-9a-f]{32}$")


def _stash_root() -> Path:
    return Path(settings.MEDIA_ROOT) / _IMPORT_SUBDIR


def _safe_dir(token: str) -> Path | None:
    if not token or not _TOKEN_RE.match(token):
        return None
    return _stash_root() / token


def _png_name(q_no: str, label: str | None) -> str:
    """Fayl adı: '12__stem.png' və ya '12__opt_B.png'."""
    suffix = "stem" if label is None else f"opt_{label}"
    return f"{q_no}__{suffix}.png"


def stash_math_images(uploaded_file) -> str | None:
    """
    Yüklənmiş PDF-dən 2D düstur şəkillərini çıxarıb müvəqqəti qovluğa yazır.
    Şəkil yoxdursa və ya xəta olarsa ``None`` qaytarır (idxal pozulmur).
    Qaytarılan token gizli form sahəsi kimi save addımına ötürülməlidir.
    """
    try:
        images = extract_math_images(uploaded_file)
    except Exception as exc:  # pragma: no cover
        logger.warning("stash_math_images extract failed: %s", exc)
        return None
    if not images:
        return None

    token = uuid.uuid4().hex
    target = _stash_root() / token
    try:
        target.mkdir(parents=True, exist_ok=True)
        for q_no, bucket in images.items():
            if bucket.get("stem"):
                (target / _png_name(q_no, None)).write_bytes(bucket["stem"])
            for label, png in (bucket.get("options") or {}).items():
                (target / _png_name(q_no, label)).write_bytes(png)
    except OSError as exc:  # pragma: no cover
        logger.warning("stash_math_images write failed: %s", exc)
        return None
    return token


def attach_math_images(token: str, q_no: str, question) -> None:
    """
    Token altında saxlanan şəkilləri verilmiş suala və onun variantlarına bağlayır.

    ``question`` — yenicə yaradılmış ExamQuestion/BankQuestion (``options`` related
    manager-i mövcud olmalıdır). Yalnız hələ şəkli olmayan obyektlərə yazır
    (mövcud şəkli üstələmir). Şəkil tapılmazsa səssiz keçir.
    """
    directory = _safe_dir(token)
    if directory is None or not directory.is_dir():
        return

    q_no = str(q_no)

    # Sual stem-i
    stem_path = directory / _png_name(q_no, None)
    if stem_path.is_file() and not getattr(question, "image", None):
        _assign_image(question, stem_path)

    # Variantlar (label-ə görə)
    for option in question.options.all():
        if not option.label or getattr(option, "image", None):
            continue
        opt_path = directory / _png_name(q_no, option.label.upper())
        if opt_path.is_file():
            _assign_image(option, opt_path)


def _assign_image(instance, path: Path) -> None:
    """PNG-ni modelin ``image`` sahəsinə yazır (storage backend-dən asılı olaraq)."""
    try:
        instance.image.save(path.name, ContentFile(path.read_bytes()), save=True)
    except Exception as exc:  # pragma: no cover
        logger.warning("attach image failed (%s): %s", path.name, exc)


def clear_stash(token: str) -> None:
    """İdxal bitəndən sonra müvəqqəti qovluğu təmizləyir."""
    directory = _safe_dir(token)
    if directory is not None and directory.is_dir():
        shutil.rmtree(directory, ignore_errors=True)
