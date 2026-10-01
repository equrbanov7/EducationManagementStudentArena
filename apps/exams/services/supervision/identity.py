"""Tələbə KİMLİYİ — İM nəzarətçisinin monitorda üz-üzə yoxlaması üçün.

Sahib 2026-10-01: «imtahan verən tələbənin şəkli görünə bilsin … ad, soyad,
qrup şəkildə olsun ki İM nəzarətçisi imtahan zamanı baxa bilsin».

* Şəkil — ``UserProfile.avatar`` (yoxdursa baş hərflər). URL HEÇ VAXT xam media
  yolu deyil: ``exams:proctor_student_photo`` marşrutundan keçir və orada
  ``can_view_student_photo`` yoxlanır (tələbə yalnız ÖZ şəklini, nəzarətçi yalnız
  nəzarət etdiyi zal/oturumdakı tələbəni, imtahan mərkəzi öz təşkilatını görür).
* Qrup — akademik qeyddən (aktiv/ən yeni qeyd), TƏK sorğu ilə.
* Tələbə nömrəsi — təsdiqlənmiş ``institutional_identifier`` (varsa).
"""

from __future__ import annotations

from datetime import timedelta

from django.apps import apps as django_apps
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

#: Bitmiş cəhdin şəkli nəzarətçiyə bu qədər müddət açıq qalır (hesabat/izah üçün).
_FINISHED_PHOTO_WINDOW = timedelta(hours=12)
_RECORD_ORDER = ("student_id", "-is_active", "-admission_year", "created_at")


def initials_for(user) -> str:
    first = (getattr(user, "first_name", "") or getattr(user, "username", "") or "")[:1]
    last = (getattr(user, "last_name", "") or "")[:1]
    return (first + last).upper() or "?"


def photo_url(user_id: int, version) -> str:
    url = reverse("exams:proctor_student_photo", args=[user_id])
    if version:
        url += f"?v={int(version)}"
    return url


def _group_names(organization, student_ids) -> dict:
    """{student_id: qrup adı} — akademik reyestrdən (jurnal modeli DEYİL).

    ``registrar.models``-i statik import etmirik (mikroservis sərhədi,
    ``scripts/context_map.py``): model app reyestrindən oxunur, yalnız ad sütunu.
    """
    if organization is None or not student_ids:
        return {}
    try:
        record_model = django_apps.get_model("registrar", "StudentAcademicRecord")
    except LookupError:
        return {}
    rows = (
        record_model.objects.filter(organization=organization, student_id__in=student_ids)
        .order_by(*_RECORD_ORDER)
        .values_list("student_id", "group__name")
    )
    groups = {}
    for student_id, group_name in rows:
        if student_id not in groups and group_name:
            groups[student_id] = group_name
    return groups


def student_identities(organization, users) -> dict:
    """{user_id: {"name","username","group","student_number","photo_url","initials"}}.

    İki sorğu (profil + qrup) — monitor snapshot-u üçün N+1 yoxdur.
    """
    users = [user for user in users if user is not None]
    if not users:
        return {}
    user_ids = sorted({user.pk for user in users})
    profile_model = django_apps.get_model("accounts", "UserProfile")
    profiles = {
        row["user_id"]: row
        for row in profile_model.objects.filter(user_id__in=user_ids).values(
            "user_id", "avatar", "updated_at", "institutional_identifier"
        )
    }
    groups = _group_names(organization, user_ids)
    result = {}
    for user in users:
        profile = profiles.get(user.pk) or {}
        has_avatar = bool(profile.get("avatar"))
        updated_at = profile.get("updated_at")
        result[user.pk] = {
            "name": user.get_full_name() or user.username,
            "username": user.username,
            "group": groups.get(user.pk, ""),
            "student_number": profile.get("institutional_identifier") or "",
            "photo_url": photo_url(user.pk, updated_at.timestamp() if updated_at else None) if has_avatar else "",
            "initials": initials_for(user),
        }
    return result


def student_identity(organization, user) -> dict:
    return student_identities(organization, [user]).get(user.pk, {})


def attach_identity(rows, organization, users_by_id) -> list:
    """Monitor sətirlərinə kimlik sahələrini əlavə edir (``student_id`` üzrə)."""
    identities = student_identities(organization, list(users_by_id.values()))
    for row in rows:
        identity = identities.get(row.get("student_id")) or {}
        row["photo_url"] = identity.get("photo_url", "")
        row["initials"] = identity.get("initials", "")
        row["group"] = identity.get("group", "")
        row["student_number"] = identity.get("student_number", "")
    return rows


def can_view_student_photo(user, organization, student_id: int) -> bool:
    """Şəkil marşrutunun icazə qaydası (deny-by-default).

    * tələbənin özü → bəli;
    * imtahan mərkəzi → yalnız aktiv təşkilatın üzvü olan tələbə;
    * zal/oturum nəzarətçisi → yalnız nəzarət etdiyi zalda/oturumda bu tələbənin
      CANLI (və ya son 12 saatda bitmiş) cəhdi/bileti varsa;
    * qalan hamı (digər tələbələr daxil) → xeyr.
    """
    if not getattr(user, "is_authenticated", False):
        return False
    if user.pk == student_id:
        return True
    if organization is None:
        return False

    from apps.exams.services.final_center import can_manage_final_center, user_is_org_member

    if not user_is_org_member(user, organization.pk):
        return False
    if can_manage_final_center(user):
        membership_model = django_apps.get_model("organizations", "Membership")
        return membership_model.objects.filter(user_id=student_id, organization=organization, is_active=True).exists()

    attempt_model = django_apps.get_model("exams", "ExamAttempt")
    since = timezone.now() - _FINISHED_PHOTO_WINDOW
    live_or_recent = Q(status="in_progress") | Q(finished_at__gte=since)
    if (
        attempt_model.objects.filter(user_id=student_id, exam__organization=organization, room__invigilators=user)
        .filter(live_or_recent)
        .exists()
    ):
        return True
    ticket_model = django_apps.get_model("exams", "FinalExamTicket")
    supervised = Q(session__room__invigilators=user) | Q(session__invigilator=user) | Q(session__staff=user)
    return (
        ticket_model.objects.filter(student_id=student_id, organization=organization)
        .filter(supervised)
        .filter(session__state__in=("entry_open", "active"))
        .exists()
    )


__all__ = [
    "attach_identity",
    "can_view_student_photo",
    "initials_for",
    "photo_url",
    "student_identities",
    "student_identity",
]
