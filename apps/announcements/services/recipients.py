"""Hədəf auditoriya SQL-də: say (forma xülasəsi, KPI) və məcburi elanın alıcı siyahısı.

``audience.visible_q`` «bu elan bu istifadəçiyə aiddirmi?» sualını ELAN tərəfdən süzür; burada
əks istiqamət lazımdır — «bu auditoriyaya kimlər düşür?». Qayda eynidir (``family_of`` rol adına
görə; daraltma: tələbə — aktiv akademik qeydinin QRUPU, digərləri — üzvlüyün ``scope_unit``-i
seçilmiş bölmənin özü və ya alt-ağacıdır), lakin bütün üzvlükləri Python-a yükləmək əvəzinə
sabit sayda sorğu qurulur:

1. təşkilatın rolları (kiçik cədvəl) → ailə üzrə rol id-ləri — 1 sorğu;
2. ``User`` üzərində ``id IN (hədəf rollu aktiv üzvlər)`` (təşkilatla məhdud semi-join) VƏ ailə
   şərtləri ``EXISTS`` alt-sorğuları ilə — say üçün 1 ``COUNT``, siyahı üçün ``COUNT`` + səhifə.

``OrgUnit.path`` = ``"<kök-id>/…/<öz-id>"`` (UUID seqmentləri, ``/`` UUID-də yoxdur) — ona görə
``path LIKE '%<bölmə-id>%'`` dəqiq seqment uyğunluğudur (bölmənin özü və ya alt-ağacı).

Tenant: hər alt-sorğu ``organization_id``-ni açıq süzür; RLS siyasəti də eyni təşkilatı tətbiq edir.
"""

from __future__ import annotations

import math

from django.apps import apps as django_apps
from django.contrib.auth import get_user_model
from django.db.models import Count, Exists, OuterRef, Q, Subquery
from django.utils.translation import npgettext, pgettext

from core.search_text import tolerant_q

from ..constants import RECIPIENT_STATUSES, RECIPIENTS_PAGE_SIZE, SUMMARY_UNIT_NAMES, Audience
from ..models import AnnouncementReceipt
from .audience import family_of

_CTX = "announcements.manage"
_STUDENTS = Audience.STUDENTS.value
_SEARCH_FIELDS = ("first_name", "last_name", "username", "email")


def _org_id(organization):
    return getattr(organization, "pk", organization)


def _family_roles(org_id) -> dict:
    """``{ailə: [rol id-ləri]}`` — təşkilatın rol cədvəlindən (``family_of`` ilə EYNİ qayda)."""
    Role = django_apps.get_model("organizations", "Role")
    result: dict = {}
    for pk, name in Role.objects.filter(organization_id=org_id).values_list("pk", "name"):
        family = family_of(name)
        if family:
            result.setdefault(family, []).append(pk)
    return result


def _path_q(field: str, units) -> Q:
    query = Q()
    for unit in units:
        query |= Q(**{f"{field}__contains": unit})
    return query


def targeted_users(organization, families, units):
    """Auditoriyaya düşən AKTİV istifadəçilərin ``QuerySet``-i (təkrarsız — JOIN yoxdur)."""
    User = get_user_model()
    org_id = _org_id(organization)
    families = {str(family) for family in families or ()}
    units = sorted({str(unit) for unit in units or ()})
    roles = _family_roles(org_id) if families else {}
    student_roles = roles.get(_STUDENTS, []) if _STUDENTS in families else []
    other_roles = [pk for family in sorted(families - {_STUDENTS}) for pk in roles.get(family, [])]
    if not student_roles and not other_roles:
        return User.objects.none()
    Membership = django_apps.get_model("organizations", "Membership")
    active = Membership.objects.filter(organization_id=org_id, is_active=True)
    where = Q()
    if other_roles:
        staff = active.filter(user_id=OuterRef("pk"), role_id__in=other_roles)
        if units:
            staff = staff.filter(_path_q("scope_unit__path", units))
        where |= Q(Exists(staff))
    if student_roles:
        student = Q(Exists(active.filter(user_id=OuterRef("pk"), role_id__in=student_roles)))
        if units:
            Record = django_apps.get_model("registrar", "StudentAcademicRecord")
            records = Record.objects.filter(organization_id=org_id, is_active=True, student_id=OuterRef("pk")).filter(
                _path_q("group__path", units)
            )
            student &= Q(Exists(records))
        where |= student
    members = active.filter(role_id__in=student_roles + other_roles).values("user_id")
    return User.objects.filter(is_active=True, pk__in=members).filter(where)


def audience_count(organization, families, units) -> int:
    return targeted_users(organization, families, units).count()


def _receipts(announcement):
    return AnnouncementReceipt.objects.filter(
        organization_id=announcement.organization_id, announcement_id=announcement.pk, user_id=OuterRef("pk")
    )


def ack_summary(announcement) -> dict:
    """``{"targeted": Y, "acked": X}`` — X yalnız HAZIRKI hədəf auditoriyadan (bir aqreqat sorğu)."""
    queryset = targeted_users(
        announcement.organization_id, announcement.audience_families, announcement.audience_units
    ).annotate(is_acked=Exists(_receipts(announcement).filter(acknowledged_at__isnull=False)))
    totals = queryset.aggregate(targeted=Count("pk"), acked=Count("pk", filter=Q(is_acked=True)))
    targeted, acked = int(totals.get("targeted") or 0), int(totals.get("acked") or 0)
    return {"targeted": targeted, "acked": acked, "pending": max(targeted - acked, 0)}


def recipient_page(announcement, *, status="pending", q="", page=1, page_size=RECIPIENTS_PAGE_SIZE) -> dict:
    """Məcburi elanın alıcıları: ``pending`` (təsdiq gözləyir) / ``acked`` / ``all`` + axtarış + səhifə.

    Sorğular: rollar + ``COUNT`` + səhifə sətirləri = 3 (sətir sayından asılı deyil; N+1 yoxdur).
    """
    status = status if status in RECIPIENT_STATUSES else "pending"
    q = str(q or "").strip()[:100]
    receipts = _receipts(announcement)
    queryset = targeted_users(
        announcement.organization_id, announcement.audience_families, announcement.audience_units
    ).annotate(
        ack_at=Subquery(receipts.values("acknowledged_at")[:1]),
        read_at=Subquery(receipts.values("read_at")[:1]),
    )
    if status == "pending":
        queryset = queryset.filter(ack_at__isnull=True)
    elif status == "acked":
        queryset = queryset.filter(ack_at__isnull=False)
    search = tolerant_q(q, _SEARCH_FIELDS) if q else None
    if search is not None:
        queryset = queryset.filter(search)
    total = queryset.count()
    pages = max(1, math.ceil(total / page_size))
    page = max(1, min(int(page or 1), pages))
    order = ("-ack_at", "last_name", "first_name", "pk") if status == "acked" else ("last_name", "first_name", "pk")
    start = (page - 1) * page_size
    rows = (
        list(
            queryset.order_by(*order).values("pk", "username", "first_name", "last_name", "ack_at", "read_at")[
                start : start + page_size
            ]
        )
        if total
        else []
    )
    for row in rows:
        row["name"] = f"{row['first_name'] or ''} {row['last_name'] or ''}".strip() or row["username"]
        row["initials"] = "".join(part[:1] for part in row["name"].split()[:2]).upper() or "?"
    return {"items": rows, "total": total, "page": page, "pages": pages, "status": status, "q": q}


def summary_text(families, unit_names, count: int) -> str:
    """«Kim görəcək: Tələbələr · Fakültə F1 — təxminən N nəfər» (bölmə adları ən çox ``SUMMARY_UNIT_NAMES``)."""
    who = ", ".join(str(label) for value, label in Audience.choices if value in set(families or ()))
    names = list(unit_names or [])
    if not names:
        where = pgettext(_CTX, "bütün təşkilat")
    else:
        where = ", ".join(names[:SUMMARY_UNIT_NAMES])
        if len(names) > SUMMARY_UNIT_NAMES:
            where = f"{where} " + pgettext(_CTX, "və daha %(n)s") % {"n": len(names) - SUMMARY_UNIT_NAMES}
    return npgettext(
        _CTX,
        "Kim görəcək: %(who)s · %(where)s — təxminən %(n)s nəfər",
        "Kim görəcək: %(who)s · %(where)s — təxminən %(n)s nəfər",
        count,
    ) % {"who": who, "where": where, "n": count}


__all__ = ["ack_summary", "audience_count", "recipient_page", "summary_text", "targeted_users"]
