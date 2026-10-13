"""Şəxs səthlərinin görünürlüyü — ictimai profil və profil şəkli (URL auditi B1/B5, 2026-10-10).

Qayda üç səth üçün EYNİDİR: baxan — hədəfin özü, superadmin, ya da hədəflə ən azı
BİR təşkilatda hər ikisinin AKTİV üzvlüyü olan istifadəçi. Qalan hamıya 404:
«yoxdur» və «icazə yoxdur» eyni cavabdır (ardıcıl id və ``ad.soyad`` istifadəçi
adları ilə mövcudluq orakulu olmasın).

* ``accounts/users/<username>/`` — ictimai profil;
* ``accounts/profile-avatar/<user_id>/`` — profil şəkli;
* ``/media/avatars/…`` — ``core.media_views._check_avatar_access``.

``exams/supervision/photo/<user_id>/`` ayrıca, daha dar qaydadır — toxunulmur.

2026-10-14 (sahib: «profil şəkli marşrutu bağlansın»): profil ŞƏKLİ üçün ``can_view_avatar`` daha dardır —
ortaq təşkilat kifayət deyil. TƏLƏBƏ (yalnız tələbə/starosta/məzun üzvlüyü olan) başqa TƏLƏBƏNİN şəklini
yalnız qrup yoldaşıdırsa və ya eyni fənn açılışında (seçmə / birləşmiş dərs) birlikdədirsə görür;
müəllim/heyət şəklini ortaq təşkilatda görür. Heyət (müəllim daxil) ortaq təşkilatda hamını görür.
Əvvəl hər tələbə ardıcıl id ilə bütün universitetin tələbə şəkillərini yığa bilirdi.

``organizations_membership`` RLS altındadır: tenant konteksti olan sorğuda yoxlama
faktiki olaraq baxanın aktiv təşkilatı ilə məhdudlaşır (daha sərt tərəf).
core → apps importu yoxdur (modul-sərhəd gate-i): model ``django_apps`` ilə alınır.
"""

from __future__ import annotations

from django.apps import apps as django_apps

from core.permissions import is_superadmin_user


def can_view_person(viewer, target_user_id) -> bool:
    """``viewer`` ``target_user_id`` şəxsinin profil səthlərini görə bilərmi?"""
    if viewer is None or not getattr(viewer, "is_authenticated", False) or not target_user_id:
        return False
    if viewer.pk == target_user_id:
        return True
    if is_superadmin_user(viewer):
        return True
    membership_model = django_apps.get_model("organizations", "Membership")
    target_orgs = membership_model.objects.filter(user_id=target_user_id, is_active=True).values("organization_id")
    return membership_model.objects.filter(
        user_id=viewer.pk,
        is_active=True,
        organization_id__in=target_orgs,
    ).exists()


#: Tələbə ailəsi — bu rollardan BAŞQA aktiv üzvlüyü olmayan hesab «tələbə baxan» sayılır.
_STUDENT_ROLE_NAMES = frozenset({"student", "lead_student", "alumni"})


def _is_student_only(user_id) -> bool:
    membership_model = django_apps.get_model("organizations", "Membership")
    names = set(membership_model.objects.filter(user_id=user_id, is_active=True).values_list("role__name", flat=True))
    return bool(names) and names <= _STUDENT_ROLE_NAMES


def _share_class(viewer_id, target_id) -> bool:
    """Qrup yoldaşı (aktiv akademik qeyd, eyni qrup) və ya eyni fənn açılışında birlikdə."""
    record_model = django_apps.get_model("registrar", "StudentAcademicRecord")
    viewer_groups = record_model.objects.filter(student_id=viewer_id, is_active=True, group__isnull=False).values(
        "group_id"
    )
    if record_model.objects.filter(student_id=target_id, is_active=True, group_id__in=viewer_groups).exists():
        return True
    enrollment_model = django_apps.get_model("registrar", "Enrollment")
    viewer_offerings = (
        enrollment_model.objects.filter(student_id=viewer_id).exclude(status="dropped").values("offering_id")
    )
    return (
        enrollment_model.objects.filter(student_id=target_id, offering_id__in=viewer_offerings)
        .exclude(status="dropped")
        .exists()
    )


def can_view_avatar(viewer, target_user_id) -> bool:
    """Profil ŞƏKLİ — ``can_view_person``-dan dar (bax modul sənədi, 2026-10-14)."""
    if not can_view_person(viewer, target_user_id):
        return False
    if viewer.pk == target_user_id or is_superadmin_user(viewer):
        return True
    if not _is_student_only(viewer.pk):
        return True  # müəllim / heyət — ortaq təşkilat kifayətdir
    if not _is_student_only(target_user_id):
        return True  # tələbə müəllimin / heyətin şəklini görür
    return _share_class(viewer.pk, target_user_id)
