"""Qorunan media — 25% qəbzləri və alt qrup qərar sənədləri (``core.media_policies`` runtime reyestri).

Default DENY. Faylı görür: müraciətin SAHİBİ (tələbə) və müraciəti struktur əhatəsində görən heyət
(qəbz: ``retake.payment_verify`` / ``retake.manage`` / ``student.records_view``; qərar sənədi: mühasibsiz). Fayl adı təsadüfidir — orijinal
ad yalnız Mühasibatlıq növbəsində göstərilir.

``retake_documents/`` prefiksi ALTINDA üç sənəd sahəsi var (review 2026-10-19, B1): alt qrup qərarı
(``decision_document``), ödənişdən sonra bağlanış qərarı (``closure_document``) və «Ödənişin qaytarılması qərarı»
(``refund_document``). Hamısı eyni iz açarları ilə (``TRAIL_KEYS``) açılır; qaytarılma qərarını əlavə olaraq
Mühasibatlıq (``retake.payment_verify``) görür — «Qaytarılacaq ödənişlər» növbəsində icra üçün lazımdır.

``exam_chance_documents/`` (2026-10-24) — «Yenidən imtahan cəhdi»nin məcburi əsas sənədi (``ExamChanceGrant``).
Görür: qeydin tələbəsi, superadmin, həmin təşkilatın İmtahan Mərkəzi və 25% izini görən heyət (müraciətə bağlı
qeyddə müraciətin əhatəsi, əks halda təşkilat-geniş iz açarı).
"""

from __future__ import annotations

from django.db.models import Q

from . import retake_access
from .models import ExamChanceGrant, RetakeApplication, RetakeReceipt


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


def _document_keys(application, path: str) -> tuple:
    if application.refund_document and application.refund_document.name == path:
        return retake_access.RECEIPT_KEYS  # iz açarları + Mühasibatlıq
    return retake_access.TRAIL_KEYS


def check_document_access(user, path: str) -> bool:
    if not path:
        return False
    match = Q(decision_document=path) | Q(closure_document=path) | Q(refund_document=path)
    try:
        application = RetakeApplication.objects.select_related("organization").get(match)
    except (RetakeApplication.DoesNotExist, RetakeApplication.MultipleObjectsReturned):
        return False
    return _allowed(user, application, _document_keys(application, path))


def _exam_center_member(user, organization) -> bool:
    from core.media_policies import EXAM_CENTER_ROLE_NAMES, user_has_org_membership

    if getattr(user, "is_exam_center", False) and user_has_org_membership(user, organization):
        return True
    return user.memberships.filter(
        organization=organization, is_active=True, role__name__in=EXAM_CENTER_ROLE_NAMES
    ).exists()


def check_chance_document_access(user, path: str) -> bool:
    if not path or not getattr(user, "is_authenticated", False):
        return False
    grants = list(
        ExamChanceGrant.objects.filter(document=path).select_related("organization", "application__organization")[:50]
    )
    if not grants:
        return False
    organization = grants[0].organization
    if any(grant.organization_id != organization.pk for grant in grants):
        return False  # eyni yol iki təşkilatda — heç vaxt olmamalıdır; default DENY
    if any(grant.student_id == user.pk for grant in grants):
        return True
    if user.is_superuser or getattr(user, "is_superadmin", False):
        return True
    if _exam_center_member(user, organization):
        return True
    for grant in grants:
        if grant.application is not None and retake_access.application_in_scope(
            user, grant.application, retake_access.TRAIL_KEYS
        ):
            return True
    return any(retake_access.has_org_wide_key(user, organization, key) for key in retake_access.TRAIL_KEYS)


__all__ = ["check_chance_document_access", "check_document_access", "check_receipt_access"]
