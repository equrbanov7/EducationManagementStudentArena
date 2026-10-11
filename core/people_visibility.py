"""Şəxs səthlərinin görünürlüyü — ictimai profil və profil şəkli (URL auditi B1/B5, 2026-10-10).

Qayda üç səth üçün EYNİDİR: baxan — hədəfin özü, superadmin, ya da hədəflə ən azı
BİR təşkilatda hər ikisinin AKTİV üzvlüyü olan istifadəçi. Qalan hamıya 404:
«yoxdur» və «icazə yoxdur» eyni cavabdır (ardıcıl id və ``ad.soyad`` istifadəçi
adları ilə mövcudluq orakulu olmasın).

* ``accounts/users/<username>/`` — ictimai profil;
* ``accounts/profile-avatar/<user_id>/`` — profil şəkli;
* ``/media/avatars/…`` — ``core.media_views._check_avatar_access``.

``exams/supervision/photo/<user_id>/`` ayrıca, daha dar qaydadır — toxunulmur.

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
