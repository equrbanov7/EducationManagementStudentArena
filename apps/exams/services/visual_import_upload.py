"""Workbench upload-ları üçün vahid visual-first hazırlıq axını."""

from __future__ import annotations

from apps.exams.services.import_media import (
    clear_stash,
    get_stashed_import_text,
    stash_math_images,
)
from apps.exams.services.parsing import extract_text_from_upload

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
        new_token = stash_math_images(
            uploaded_file,
            owner_id=owner_id,
            organization_id=organization_id,
        )
        if not new_token:
            raise ValueError("Vizual faylın layout-u etibarlı çıxarıla bilmədi")
        try:
            canonical_text = get_stashed_import_text(
                new_token,
                owner_id=owner_id,
                organization_id=organization_id,
            )
        except Exception:
            clear_stash(new_token)
            raise
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

    extracted_text = extract_text_from_upload(uploaded_file)
    if previous_token:
        _clear_scoped_stash(
            previous_token,
            owner_id=owner_id,
            organization_id=organization_id,
        )
    return extracted_text, ""


__all__ = ["prepare_question_upload"]
