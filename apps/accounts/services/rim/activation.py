"""Profil aktivləşdirmə — RİM-ə bildiriş + say (sahib 2026-10-23).

Sahib: «kim yeni profili aktivləşdiribsə RİM-ə bildiriş gəlsin; neçə nəfərin aktivləşdirdiyini konkret sayla
görüm». İki hissə:

* **Bildiriş** — ``profile.email_verified`` False → True olanda (ilk giriş OTP-si və ya parol bərpası OTP-si;
  bax ``views/auth/first_login._finish`` və ``forms/otp.mark_self_service_password_set``) təşkilatın bütün RİM
  üzvlərinə (``ikt_rehber`` / ``rim_staff`` — «Bildiriş göndər»dəki «RİM mərkəzi» hədəfi ilə eyni rollar)
  in-app bildiriş gedir: kim, hansı növ, və yekun say. Açar: ``login.notify_rim_on_activation``.
* **Say** — RİM mərkəzinin KPI sırası (:func:`activation_counts`). «Aktivləşdirib» = e-poçtu təsdiqli VƏ ilkin
  parolda deyil — tələbə reyestrinin «Hesab aktivləşdirmə» görünüşü ilə eyni qayda
  (``services/people/study_state.py``). Baza: təşkilatda AKTİV üzvlüyü olan, bloklanmamış, silinməmiş, arxivdə
  olmayan hesablar. Növlər ``rim/search.apply_kind_filter`` ilə eynidir (həm müəllim, həm heyət olan iki növdə
  sayılır; «Cəmi» unikal şəxsdir).

Çatdırılma COMMIT-dən SONRA və BEST-EFFORT-dur — bildiriş xətası aktivləşdirməni geri qaytarmır.
Parol bərpası anonim sorğudadır (tenant konteksti yoxdur), ona görə alıcıların ``user_id``-ləri və bildiriş
yazısı ``bypass_rls()`` altındadır — kateqoriya A: alıcı siyahısı sabit rol adları + aktivləşdirənin ÖZ
təşkilatı ilə məhdudlaşır, çağırana sətir qaytarılmır (``docs/audits/RLS_BYPASS_AUDIT.md``).
"""

from __future__ import annotations

import logging
from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.db import transaction
from django.urls import reverse
from django.utils.translation import pgettext

from core import runtime_settings
from core.rls import bypass_rls

from ...models import UserProfile
from .search import STUDENT_ROLE_NAMES, TEACHING_ROLE_NAMES

logger = logging.getLogger(__name__)

_CTX = "accounts.rim_activation"

#: «Sistem tənzimləmələri» açarı (``core/runtime_settings_rim_activation.py``).
KEY_NOTIFY = "login.notify_rim_on_activation"
#: RİM mərkəzinin rolları — ``notification_scopes.ROLE_TARGETS["rim"]`` ilə eyni.
RIM_ROLE_NAMES = ("ikt_rehber", "rim_staff")
#: Bildirişdən RİM mərkəzinə keçid: axtarış sahəsi bu parametrlə doldurulur (``views/rim/section.py``).
QUERY_PARAM = "rim_q"

KINDS = ("student", "teacher", "staff")


_STUDENT = frozenset(STUDENT_ROLE_NAMES)
_TEACHING = frozenset(TEACHING_ROLE_NAMES)


def _kind_of_role(role_name) -> str | None:
    """``rim/search.apply_kind_filter`` ilə eyni bölgü; ``member`` və rolsuz üzvlük heç bir növə düşmür."""
    if role_name in _STUDENT:
        return "student"
    if role_name in _TEACHING:
        return "teacher"
    if role_name and role_name != "member":
        return "staff"
    return None


def _pct(done: int, total: int) -> float:
    return round(done * 100 / total, 1) if total else 0.0


def activation_counts(organization) -> dict:
    """``{"total": {done, total, pct}, "student": {...}, "teacher": {...}, "staff": {...}}``.

    TƏK sorğu — təşkilatın aktiv üzvlük sətirləri (``user_id``, rol, iki profil bayrağı); növlər Python-da
    yığılır. İstifadəçi başına EXISTS alt-sorğulu aqreqat 9 400 hesablıq klonda ~470 ms çəkirdi (RİM səhifəsinin
    hər açılışı + hər aktivləşdirmə), bu forma bir indeksli JOIN-dir.
    """
    from apps.organizations.models import Membership

    buckets = {key: {"done": 0, "total": 0} for key in ("total", *KINDS)}
    if organization is not None:
        rows = (
            Membership.objects.filter(
                organization=organization, is_active=True, user__is_active=True, user__is_superuser=False
            )
            .exclude(user__profile__is_deleted=True)
            .exclude(user__profile__access_state=UserProfile.AccessState.ARCHIVED)
            .values_list(
                "user_id", "role__name", "user__profile__email_verified", "user__profile__password_change_required"
            )
        )
        users: dict = {}
        for user_id, role_name, verified, initial in rows.iterator(chunk_size=5000):
            entry = users.setdefault(user_id, [bool(verified) and not initial, set()])
            kind = _kind_of_role(role_name)
            if kind:
                entry[1].add(kind)
        for activated, kinds in users.values():
            for key in ("total", *kinds):
                buckets[key]["total"] += 1
                buckets[key]["done"] += int(activated)
    return {key: {**row, "pct": _pct(row["done"], row["total"])} for key, row in buckets.items()}


def _kind_label(user, organization) -> str:
    from apps.organizations.models import Membership

    names = set(
        Membership.objects.filter(user=user, organization=organization, is_active=True).values_list(
            "role__name", flat=True
        )
    )
    if names & set(STUDENT_ROLE_NAMES):
        return pgettext(_CTX, "Tələbə")
    if names & set(TEACHING_ROLE_NAMES):
        return pgettext(_CTX, "Müəllim")
    if names - {"member"}:
        return pgettext(_CTX, "Əməkdaş")
    return ""


def _number(value: float) -> str:
    return f"{value:g}".replace(".", ",")


def _message(user, organization, kind_label: str) -> str:
    counts = activation_counts(organization)
    total = counts["total"]
    head = " · ".join(part for part in (kind_label, f"@{user.username}") if part)
    summary = pgettext(_CTX, "Cəmi aktivləşdirən: %(done)d / %(total)d (%(pct)s%%)") % {
        "done": total["done"],
        "total": total["total"],
        "pct": _number(total["pct"]),
    }
    kinds = pgettext(_CTX, "tələbə %(s)d / %(st)d, müəllim %(t)d / %(tt)d, əməkdaş %(e)d / %(et)d") % {
        "s": counts["student"]["done"],
        "st": counts["student"]["total"],
        "t": counts["teacher"]["done"],
        "tt": counts["teacher"]["total"],
        "e": counts["staff"]["done"],
        "et": counts["staff"]["total"],
    }
    return f"{head}. {summary} — {kinds}."


def _organization_of(user):
    """``profile.organization``; boşdursa əsas (sonra ən köhnə) AKTİV üzvlüyün təşkilatı.

    ``profile.organization`` hər hesabda doldurulmayıb (idxal/köçürmə) — yalnız ona baxsaq bildiriş səssizcə
    itərdi. Çağırış ``bypass_rls()`` daxilindədir (anonim parol bərpası), nəticə aktivləşdirənin ÖZ üzvlüyüdür.
    """
    from apps.organizations.models import Membership

    profile = getattr(user, "profile", None)
    organization = getattr(profile, "organization", None)
    if organization is not None:
        return organization
    membership = (
        Membership.objects.filter(user=user, is_active=True)
        .select_related("organization")
        .order_by("-is_primary", "pk")
        .first()
    )
    return membership.organization if membership else None


def notify_rim_of_activation(user) -> None:
    """Aktivləşdirmə anında çağırılır (tranzaksiya daxilində); çatdırılma ``on_commit``-dədir."""
    try:
        if not runtime_settings.get_bool(KEY_NOTIFY):
            return
    except Exception:  # noqa: BLE001 — tənzimləmə oxunmasa defolt (yandırılı)
        logger.warning("RİM activation notify switch unreadable; using default.", exc_info=True)
    transaction.on_commit(lambda: _deliver(user))


def _deliver(user) -> None:
    try:
        from apps.notifications.public import create_notification_for_users
        from apps.organizations.models import Membership

        name = (user.get_full_name() or "").strip() or user.username
        link = f"{reverse('accounts:profile')}?{urlencode({'section': 'rim-center', QUERY_PARAM: user.username})}"
        with bypass_rls():
            organization = _organization_of(user)
            if organization is None:
                return
            recipient_ids = set(
                Membership.objects.filter(
                    organization=organization, is_active=True, role__is_active=True, role__name__in=RIM_ROLE_NAMES
                ).values_list("user_id", flat=True)
            )
            recipient_ids.discard(user.pk)
            if not recipient_ids:
                return
            create_notification_for_users(
                recipients=get_user_model().objects.filter(pk__in=recipient_ids, is_active=True),
                title=(pgettext(_CTX, "Profilini aktivləşdirdi: %(name)s") % {"name": name})[:255],
                message=_message(user, organization, _kind_label(user, organization))[:2000],
                link=link,
                notification_type="system",
                metadata={
                    "kind": "profile_activated",
                    "user_id": user.pk,
                    "organization_id": organization.pk,
                    "link_label": pgettext(_CTX, "RİM mərkəzində aç"),
                },
                organization=organization,
            )
    except Exception:  # noqa: BLE001 — bildiriş heç vaxt aktivləşdirməni sındırmır
        logger.warning("RİM activation notification failed.", exc_info=True)


__all__ = ["KEY_NOTIFY", "QUERY_PARAM", "RIM_ROLE_NAMES", "activation_counts", "notify_rim_of_activation"]
