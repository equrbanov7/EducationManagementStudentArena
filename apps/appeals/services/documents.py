"""Apellyasiya qərarının əsaslandırıcı sənədi (sahib 2026-10-21).

Sahib: «Hələlik məcburi olmasa da sənəd yükləmə yeri olsun, sonra məcburi edəcəyik — onu da sistem tənzimləmədə
əlavə et». Saxlama nümunəsi 25% / alt qrup qərar sənədləri ilə eynidir (``registrar.retake_media``):

* PDF / JPG / PNG, ≤ 10 MB — ``core.upload_security`` (uzantı + MIME + imza + ölçü);
* yol ``appeal_documents/<org>/<təsadüfi ad>`` — orijinal ad yalnız ``document_name`` sahəsindədir;
* qorunan media prefiksi (``AppConfig.ready`` → ``core.media_policies.register_media_policy``): **default DENY**,
  endirə bilən — apellyasiya heyəti (imtahan mərkəzi: rəhbər/işçi/RİM, ``is_exam_center_user``) sənədin
  təşkilatında aktiv üzvlüklə, və superadmin. Tələbə, müəllim, başqa təşkilat — YOX.
* «Sistem tənzimləmələri» → ``exam.appeal_document_required`` yandırılıbsa sənədsiz qərar server tərəfindən rədd olunur.
"""

from __future__ import annotations

import posixpath
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.utils.translation import pgettext

from apps.appeals.models import APPEAL_DOCUMENT_EXTENSIONS, APPEAL_DOCUMENT_MAX_MB, AppealDecisionRecord

_CTX = "appeals.document"


def random_document_name(filename: str) -> str:
    extension = posixpath.splitext(str(filename or ""))[1].lower()
    if extension not in APPEAL_DOCUMENT_EXTENSIONS:
        extension = ""
    return f"{uuid4().hex}{extension}"


def document_required() -> bool:
    from core.runtime_settings_appeals import appeal_document_required

    return appeal_document_required()


def validate_decision_document(upload, *, required=None):
    """Yüklənmiş sənədi yoxla; ``None`` (sənəd yoxdur, məcburi deyil) və ya faylın özü. Xəta → ``ValidationError``."""
    required = document_required() if required is None else required
    if not upload:
        if required:
            raise ValidationError(pgettext(_CTX, "Qərar üçün əsaslandırıcı sənəd yükləmək məcburidir."))
        return None
    from core.upload_security import validate_uploaded_file

    validate_uploaded_file(upload, allowed_extensions=APPEAL_DOCUMENT_EXTENSIONS, max_size_mb=APPEAL_DOCUMENT_MAX_MB)
    return upload


def can_download_document(user, record) -> bool:
    if record is None or not getattr(user, "is_authenticated", False):
        return False
    from core.permissions import is_superadmin_user

    if is_superadmin_user(user):
        return True
    from apps.exams.public import is_exam_center_user
    from core.media_policies import user_has_org_membership

    return bool(is_exam_center_user(user) and user_has_org_membership(user, record.organization))


def check_document_access(user, path: str) -> bool:
    """``core.media_policies`` checker-i: ``(user, path) -> bool``, default DENY."""
    if not path:
        return False
    try:
        record = AppealDecisionRecord.objects.select_related("organization").get(document=path)
    except (AppealDecisionRecord.DoesNotExist, AppealDecisionRecord.MultipleObjectsReturned):
        return False
    return can_download_document(user, record)


__all__ = [
    "can_download_document",
    "check_document_access",
    "document_required",
    "random_document_name",
    "validate_decision_document",
]
