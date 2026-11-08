"""Müəllim birləşdirməsinin QAPILARI — cüt yoxlanmadan heç nə yazılmır.

* mənbə ≠ hədəf, hər ikisi mövcud; hədəf AKTİVDİR;
* hər ikisi təşkilatda HEYƏTDİR (tələbə olmayan rol); heç biri tələbə deyil — mənbənin tələbə üzvlüyü, tələbə qeydi
  və ya qeydiyyatı varsa birləşdirmə YOXDUR;
* mənbə superuser / Django staff deyil, təşkilatın sahibi deyil;
* mənbənin köçəcək sətirləri yalnız BU təşkilatdadır;
* :data:`policy.POLICY` istifadəçiyə istinad edən HƏR sahəni təsnif edir.
"""

from __future__ import annotations

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model

from . import policy

STUDENT_ROLE = "student"
#: ``registrar_member_has_permission(..., 'grade.input')`` (DB qoruyucusu) ilə EYNİ dəst.
GRADE_INPUT = frozenset({"grade.input", "grading.input", "grade.*", "grading.*", "*"})


class MergeError(Exception):
    """Birləşdirmə dayandı — stabil kod (stdout-a yalnız kod çıxır, ad yox)."""


def _membership_model():
    return django_apps.get_model("organizations", "Membership")


def grants_grade_input(role) -> bool:
    return bool(set(role.permissions or []) & GRADE_INPUT)


def has_grade_input(organization, user) -> bool:
    """İstifadəçinin bu təşkilatda AKTİV ``grade.input`` üzvlüyü var (jurnal sahibi trigger-i bunu tələb edir)."""
    rows = _membership_model().objects.filter(
        organization=organization, user=user, is_active=True, role__is_active=True, role__organization=organization
    )
    return any(set(perms or []) & GRADE_INPUT for perms in rows.values_list("role__permissions", flat=True))


def _is_student(organization, user) -> bool:
    if _membership_model().objects.filter(organization=organization, user=user, role__name=STUDENT_ROLE).exists():
        return True
    registrar = django_apps.get_app_config("registrar")
    return (
        registrar.get_model("StudentAcademicRecord").objects.filter(student=user).exists()
        or registrar.get_model("Enrollment").objects.filter(student=user).exists()
    )


def _is_staff(organization, user, *, active_only: bool) -> bool:
    rows = _membership_model().objects.filter(organization=organization, user=user).exclude(role__name=STUDENT_ROLE)
    if active_only:
        rows = rows.filter(is_active=True)
    return rows.exists()


def _other_tenant(organization, source) -> bool:
    for relation in policy.relations():
        if policy.POLICY.get(relation.key) in policy.KEEP:
            continue
        if not any(field.name == "organization" for field in relation.model._meta.concrete_fields):
            continue
        rows = relation.model._base_manager.filter(**{relation.attname: source.pk})
        if rows.exclude(organization_id=organization.pk).exclude(organization__isnull=True).exists():
            return True
    return False


def load_pair(source_id: int, target_id: int) -> tuple:
    people = get_user_model().objects.select_related("profile").in_bulk([source_id, target_id])
    return people.get(source_id), people.get(target_id)


def check(organization, source, target) -> None:
    """Qapılar — pozulsa :class:`MergeError` (kod)."""
    if policy.unclassified():
        raise MergeError("unclassified_relation")
    if source is None or target is None:
        raise MergeError("user_missing")
    if source.pk == target.pk:
        raise MergeError("same_user")
    if not target.is_active:
        raise MergeError("target_inactive")
    if source.is_superuser or source.is_staff:
        raise MergeError("source_elevated")
    if _is_student(organization, source):
        raise MergeError("source_is_student")
    if _is_student(organization, target):
        raise MergeError("target_is_student")
    if not _is_staff(organization, source, active_only=False):
        raise MergeError("source_not_staff")
    if not _is_staff(organization, target, active_only=True):
        raise MergeError("target_not_staff")
    if django_apps.get_model("organizations", "Organization").objects.filter(owner=source).exists():
        raise MergeError("source_is_org_owner")
    if _other_tenant(organization, source):
        raise MergeError("source_other_tenant")


__all__ = ["GRADE_INPUT", "MergeError", "check", "grants_grade_input", "has_grade_input", "load_pair"]
