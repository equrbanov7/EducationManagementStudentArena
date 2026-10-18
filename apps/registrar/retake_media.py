"""Qorunan media — 25% qəbzləri və alt qrup qərar sənədləri (``core.media_policies`` runtime reyestri).

Default DENY. Faylı görür: müraciətin SAHİBİ (tələbə) və müraciəti struktur əhatəsində görən heyət
(qəbz: ``retake.payment_verify`` / ``retake.manage`` / ``student.records_view``; qərar sənədi: mühasibsiz). Fayl adı təsadüfidir — orijinal
ad yalnız Mühasibatlıq növbəsində göstərilir.
"""

from __future__ import annotations

from . import retake_access
from .models import RetakeApplication, RetakeReceipt


def _single(queryset, **lookup):
    try:
        return queryset.get(**lookup)
    except (queryset.model.DoesNotExist, queryset.model.MultipleObjectsReturned):
        return None


def _allowed(user, application, keys) -> bool:
    if application is None or not getattr(user, "is_authenticated", False):
        return False
    if application.student_id == user.pk:
        return True
    return retake_access.application_in_scope(user, application, keys)


def check_receipt_access(user, path: str) -> bool:
    receipt = _single(RetakeReceipt.objects.select_related("application__organization"), file=path)
    return receipt is not None and _allowed(user, receipt.application, retake_access.RECEIPT_KEYS)


def check_document_access(user, path: str) -> bool:
    application = _single(RetakeApplication.objects.select_related("organization"), decision_document=path)
    return _allowed(user, application, retake_access.TRAIL_KEYS)


__all__ = ["check_document_access", "check_receipt_access"]
