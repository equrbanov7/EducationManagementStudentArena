"""Workbench upload-ları üçün vahid visual-first hazırlıq axını."""

from __future__ import annotations

import logging

from django.core.exceptions import PermissionDenied

from apps.exams.services.import_media import (
    clear_stash,
    get_stashed_import_text,
    stash_math_images,
)
from apps.exams.services.parsing import extract_text_from_upload

logger = logging.getLogger(__name__)

_VISUAL_EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg")


def _clear_scoped_stash(token, *, owner_id, organization_id):
    """Hidden POST token-i yalnız sahib/tenant scope-u təsdiqlənəndən sonra sil."""

    if not token:
        return
    get_stashed_import_text(
        token,
        owner_id=owner_id,
        organization_id=organization_id,
    )
    clear_stash(token)


def _rewind(uploaded_file) -> None:
    try:
        uploaded_file.seek(0)
    except Exception:  # noqa: BLE001 — seek dəstəkləməyən stream-lər üçün
        pass


def try_visual_import(uploaded_file, *, owner_id, organization_id):
    """Vizual bundle qurmağa cəhd et; mümkün deyilsə ``None`` qaytar.

    Layout-u ardıcıl anchor-lara oturmayan real bank PDF-ləri (nömrə boşluğu,
    təkrarlanan nömrə və s.) idxalı TAM dayandırmamalıdır — belə fayl sadəcə
    "vizual deyil" sayılır və çağıran adi mətn çıxarışına düşür. Yalnız
    ``PermissionDenied`` (scope pozuntusu) yuxarı qaldırılır; faylın özü
    qəbuledilməzdirsə (aktiv kontent, yanlış imza) mətn çıxarışı onsuz da
    öz lokallaşdırılmış xətasını verəcək.
    """

    _rewind(uploaded_file)
    try:
        new_token = stash_math_images(
            uploaded_file,
            owner_id=owner_id,
            organization_id=organization_id,
        )
    except PermissionDenied:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.info("prepare_question_upload: vizual idxal alınmadı, mətnə keçilir (%s)", exc)
        return None

    if not new_token:
        return None

    try:
        canonical_text = get_stashed_import_text(
            new_token,
            owner_id=owner_id,
            organization_id=organization_id,
        )
    except PermissionDenied:
        clear_stash(new_token)
        raise
    except Exception as exc:  # noqa: BLE001
        clear_stash(new_token)
        logger.info("prepare_question_upload: manifest mətni oxunmadı, mətnə keçilir (%s)", exc)
        return None

    return canonical_text, new_token


def prepare_question_upload(
    uploaded_file,
    *,
    previous_token="",
    owner_id=None,
    organization_id=None,
    preserve_visual=True,
):
    """
    Upload-dan canonical mətn və private manifest token-i qaytar.

    Vizual formatlarda preview mətni ilə son media binding-i eyni manifestdən
    gəlir. Yeni bundle tam hazır olmadan köhnə token silinmir.
    """

    filename = str(getattr(uploaded_file, "name", "") or "").lower()
    if preserve_visual and filename.endswith(_VISUAL_EXTENSIONS):
        visual = try_visual_import(
            uploaded_file,
            owner_id=owner_id,
            organization_id=organization_id,
        )
        if visual is not None:
            canonical_text, new_token = visual
            if previous_token and previous_token != new_token:
                try:
                    _clear_scoped_stash(
                        previous_token,
                        owner_id=owner_id,
                        organization_id=organization_id,
                    )
                except Exception:
                    clear_stash(new_token)
                    raise
            return canonical_text, new_token
        # Vizual axın alınmadı — aşağıdakı adi mətn çıxarışına düşürük.

    _rewind(uploaded_file)
    extracted_text = extract_text_from_upload(uploaded_file)
    if previous_token:
        _clear_scoped_stash(
            previous_token,
            owner_id=owner_id,
            organization_id=organization_id,
        )
    return extracted_text, ""


__all__ = ["prepare_question_upload", "try_visual_import"]
