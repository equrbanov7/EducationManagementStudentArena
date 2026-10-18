"""25% / alt qrup müraciətləri — icazə və struktur ƏHATƏSİ (rol adı yox, AÇAR + əhatə).

Müqavilə (HTTP qatı bunu tətbiq edir):

* açar yoxdursa → **403** (``has_key`` yalan);
* açar var, amma müraciət / tələbə aktorun alt-ağacında deyil (və ya mövcud deyil) → **404**;
* tələbə YALNIZ öz müraciətlərini görür (``student_id == user.id``).

Əhatə ``journal_scope.permission_scope_for`` ilə (``OrgUnit.user_permission_scope`` → superadmin / sahib /
ORGANIZATION rolu = bütün təşkilat, UNIT rolu = ``scope_unit`` alt-ağacı). Müraciət əhatədədir, əgər
tələbənin müraciət anındakı qrupu VƏ YA kəsr açılışın qrupu alt-ağacdadır.
"""

from __future__ import annotations

from django.db.models import Q

from . import journal_scope, retake_rules

#: İz (trail) oxuyan açarlar — dekanlıq / tədris şöbəsi / RİM (``retake.manage``), koordinator və rəhbərlik
#: (``student.records_view``). ``retake.payment_verify`` QƏSDƏN YOXDUR (sahibin qaydası, 2026-10-18 mühasibat
#: icmalı): mühasib tələbənin ballarını və cəhd tarixçəsini görmür — yalnız «Ödəniş yoxlaması» növbəsini.
TRAIL_KEYS = (retake_rules.PERM_MANAGE, retake_rules.PERM_RECORDS_VIEW)
#: Qəbz faylını görənlər — iz açarları + Mühasibatlıq (qəbz ödəniş yoxlamasının özüdür).
RECEIPT_KEYS = (*TRAIL_KEYS, retake_rules.PERM_PAYMENT_VERIFY)


def _authenticated(user) -> bool:
    return bool(user is not None and getattr(user, "is_authenticated", False))


def scope(user, organization, key):
    return journal_scope.permission_scope_for(user, organization, key)


def has_key(user, organization, key) -> bool:
    if not _authenticated(user) or organization is None:
        return False
    return scope(user, organization, key).has_structure_access


def has_org_wide_key(user, organization, key) -> bool:
    """Açar BÜTÜN təşkilat əhatəsindədir (UNIT rolu yox) — təşkilat səviyyəli tənzimləmələr üçün (pəncərə, təhsil
    haqqı cədvəli). Kollokvium qapısı ``can_exam_center_decide`` ilə eyni ruh: alt-bölmə rolu bütün təşkilatın
    qaydasını dəyişmir (review 2026-10-19, LOW-7)."""
    if not _authenticated(user) or organization is None:
        return False
    unit_scope = scope(user, organization, key)
    return bool(unit_scope.has_structure_access and unit_scope.is_org_wide)


def can_verify_payments(user, organization) -> bool:
    return has_key(user, organization, retake_rules.PERM_PAYMENT_VERIFY)


def can_manage(user, organization) -> bool:
    return has_key(user, organization, retake_rules.PERM_MANAGE)


def can_record_result(user, organization) -> bool:
    return can_manage(user, organization) or has_key(user, organization, retake_rules.PERM_SCORE_ENTRY)


def can_view_trail(user, organization) -> bool:
    return any(has_key(user, organization, key) for key in TRAIL_KEYS)


def can_view_desk(user, organization) -> bool:
    """Növbə bölməsi görünür: iz açarları VƏ YA yalnız ödəniş yoxlaması (mühasib)."""
    return can_view_trail(user, organization) or can_verify_payments(user, organization)


def desk_keys(user, organization) -> dict:
    """Bölmə bayraqları — bir dəfə hesablanır (əhatə ``user``-də memoizasiya olunur)."""
    return {
        "verify": can_verify_payments(user, organization),
        "manage": can_manage(user, organization),
        "record": can_record_result(user, organization),
        "trail": can_view_trail(user, organization),
    }


def _subtree_q(unit_scope):
    if unit_scope.is_org_wide:
        return Q()
    return unit_scope.unit_subtree_q(path_field="student_group__path", id_field="student_group_id") | (
        unit_scope.unit_subtree_q(
            path_field="enrollment__offering__group__path", id_field="enrollment__offering__group_id"
        )
    )


def scope_q(user, organization, keys) -> Q | None:
    """Verilən açarlardan HƏR HANSI biri ilə görünən müraciətlərin filtri; heç biri yoxdursa ``None``."""
    combined = None
    for key in keys:
        unit_scope = scope(user, organization, key)
        if not unit_scope.has_structure_access:
            continue
        q = _subtree_q(unit_scope)
        if not q:  # təşkilat-geniş — filtr yoxdur
            return Q()
        combined = q if combined is None else combined | q
    return combined


def scoped_applications(queryset, user, organization, keys):
    q = scope_q(user, organization, keys)
    if q is None:
        return queryset.none()
    return queryset.filter(organization=organization).filter(q) if q else queryset.filter(organization=organization)


def application_in_scope(user, application, keys) -> bool:
    from .models import RetakeApplication

    qs = RetakeApplication.objects.filter(pk=application.pk)
    return scoped_applications(qs, user, application.organization, keys).exists()


def student_in_scope(user, organization, student_id, keys) -> bool:
    """Tələbə (aktiv akademik qeydinin qrupu) aktorun əhatəsindədirmi — iz görünüşü üçün."""
    from .models import RetakeApplication, StudentAcademicRecord

    q = scope_q(user, organization, keys)
    if q is None:
        return False
    # Rəy 2026-10-18 (LOW-5): tələbə BU təşkilatın tələbəsi olmalıdır (akademik qeyd və ya müraciət) —
    # təşkilat-geniş əhatə qlobal istifadəçi id-si ilə başqa təşkilatın adamının adını açmasın.
    belongs = (
        StudentAcademicRecord.objects.filter(organization=organization, student_id=student_id).exists()
        or RetakeApplication.objects.filter(organization=organization, student_id=student_id).exists()
    )
    if not belongs:
        return False
    if not q:
        return True
    if scoped_applications(RetakeApplication.objects.filter(student_id=student_id), user, organization, keys).exists():
        return True
    for key in keys:
        unit_scope = scope(user, organization, key)
        if not unit_scope.has_structure_access:
            continue
        group_q = unit_scope.unit_subtree_q(path_field="group__path", id_field="group_id")
        if (
            StudentAcademicRecord.objects.filter(organization=organization, student_id=student_id)
            .filter(group_q)
            .exists()
        ):
            return True
    return False


__all__ = [
    "RECEIPT_KEYS",
    "TRAIL_KEYS",
    "application_in_scope",
    "can_manage",
    "can_record_result",
    "can_verify_payments",
    "can_view_desk",
    "can_view_trail",
    "desk_keys",
    "has_key",
    "scope_q",
    "scoped_applications",
    "student_in_scope",
]
