"""«Elan statistikası» (sahib 2026-11-18): hədəf auditoriyadan kim popup-u görüb, kim oxuyub, kim görməyib —
fakültə / kafedra / ixtisas / qrup / rol üzrə bölgü + axtarışlı, səhifəli şəxs siyahısı.

Performans (sahibin sərt şərti — sayt yavaşımamalıdır):

* Hər şey SQL-də aqreqat olunur: ``recipients.targeted_users`` (EXISTS semi-join-lər, JOIN yoxdur) üzərinə
  istifadəçinin ailəsi (rol), bölməsi (tələbə — aktiv akademik qeydin qrupu, digərləri — üzvlüyün
  ``scope_unit``-i) və qəbz vaxtları (``ann_receipt_once`` unikal indeksi ilə nöqtə axtarışı) korrelyasiyalı
  alt-sorğu kimi əlavə olunur, sonra ``GROUP BY (ailə, bölmə)`` — Python-a yüzlərlə sətir gəlir, minlərlə yox.
* Ölçü üzrə «yuxarı bölmə» (fakültə, ixtisas …) bölmə yolundan Python-da tapılır (``stats_units``) —
  sabit ≤ 2 əlavə sorğu.
* Sorğu sayı istifadəçi sayından asılı deyil: bölgü = rollar + aqreqat + 2 bölmə; siyahı = rollar + COUNT +
  səhifə + 2 bölmə (testlər bunu ölçür). Səhifə ayrıca, tənbəl (AJAX) yüklənir — mövcud səhifələrə yük yoxdur.
"""

from __future__ import annotations

import math
from contextlib import contextmanager

from django.apps import apps as django_apps
from django.db import connection, transaction
from django.db.models import Case, CharField, Exists, OuterRef, Q, Subquery, UUIDField, Value, When

from core.search_text import tolerant_q

from ..constants import STATS_DIMENSIONS, STATS_PAGE_SIZE, STATS_STATUSES, Audience
from ..models import AnnouncementReceipt
from . import stats_units as su
from .recipients import _path_q, family_roles, targeted_users

_STUDENTS, _TEACHERS, _STAFF = Audience.STUDENTS.value, Audience.TEACHERS.value, Audience.STAFF.value
_SEARCH_FIELDS = ("first_name", "last_name", "username")


def _receipts(announcement):
    """Bu elanın istifadəçi qəbzi (``ann_receipt_once`` unikal indeksi ilə nöqtə axtarışı)."""
    return AnnouncementReceipt.objects.filter(
        organization_id=announcement.organization_id, announcement_id=announcement.pk, user_id=OuterRef("pk")
    )


@contextmanager
def no_jit():
    """Analitik sorğu üçün JIT-siz kursor. Xərc qiyməti ``jit_above_cost``-u keçəndə PostgreSQL JIT kompilyasiyasına
    0,1–1 s sərf edir, sorğunun özü isə ~50 ms-dir. ``SET LOCAL`` yalnız bu tranzaksiyaya aiddir (PgBouncer-ə təhlükəsiz).
    """
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET LOCAL jit = off")
        yield cursor


_GROUPED_SQL = """
WITH people AS MATERIALIZED ({inner})
SELECT ann_family, ann_unit,
       COUNT(*),
       COUNT(*) FILTER (WHERE ann_seen IS NOT NULL),
       COUNT(*) FILTER (WHERE ann_read IS NOT NULL),
       COUNT(*) FILTER (WHERE ann_seen IS NOT NULL OR ann_read IS NOT NULL),
       COUNT(*) FILTER (WHERE ann_ack IS NOT NULL)
FROM people
GROUP BY ann_family, ann_unit
"""
_GROUPED_FIELDS = ("ann_family", "ann_unit", "total", "seen", "read", "reached", "acked")


def _grouped(queryset) -> list:
    """``GROUP BY (ailə, bölmə)`` SQL-də; hər istifadəçinin alt-sorğuları BİR dəfə hesablanır (``MATERIALIZED`` CTE).

    ORM-in ``values().annotate(Count(filter=…))`` forması korrelyasiyalı alt-sorğuları SELECT-də, GROUP BY-da və
    hər FILTER-də təkrarlayırdı (6 000 nəfərdə ~0,45 s). SQL və parametrlər ORM-in özündəndir
    (``sql_with_params``) — sorğuya istifadəçi mətni qoşulmur.
    """
    if queryset.query.is_empty():  # auditoriyaya uyğun rol yoxdur (``none()``) — SQL qurulmur
        return []
    fields = ("pk", "ann_family", "ann_unit", "ann_seen", "ann_read", "ann_ack")
    inner, params = queryset.values(*fields).order_by().query.sql_with_params()
    with no_jit() as cursor:
        cursor.execute(_GROUPED_SQL.format(inner=inner), params)
        return [dict(zip(_GROUPED_FIELDS, row)) for row in cursor.fetchall()]


def base_queryset(announcement, *, family="", unit=""):
    """Hədəf auditoriya + ``ann_family`` / ``ann_unit`` / ``ann_seen`` / ``ann_read`` / ``ann_ack`` annotasiyaları."""
    org_id = announcement.organization_id
    families = {str(value) for value in announcement.audience_families or ()}
    roles = family_roles(org_id) if families else {}
    users = targeted_users(org_id, families, announcement.audience_units, roles=roles)
    Membership = django_apps.get_model("organizations", "Membership")
    active = Membership.objects.filter(organization_id=org_id, is_active=True, user_id=OuterRef("pk"))
    whens = []
    for name in (_STUDENTS, _TEACHERS):
        if name in families and roles.get(name):
            whens.append(When(Exists(active.filter(role_id__in=roles[name])), then=Value(name)))
    default_family = _STAFF if _STAFF in families else (_TEACHERS if _TEACHERS in families else _STUDENTS)
    family_expr = Case(*whens, default=Value(default_family), output_field=CharField())
    other_roles = [pk for name in sorted(families - {_STUDENTS}) for pk in roles.get(name, [])]
    target_units = sorted({str(value) for value in announcement.audience_units or ()})
    unit_whens, unit_default = [], Value(None, output_field=UUIDField())
    if _STUDENTS in families and roles.get(_STUDENTS):
        Record = django_apps.get_model("registrar", "StudentAcademicRecord")
        records = Record.objects.filter(
            organization_id=org_id, is_active=True, student_id=OuterRef("pk"), group__isnull=False
        ).order_by("-admission_year", "pk")
        if target_units:  # daraldılmış elanda — hədəf bölmədəki qrup (targeted_users ilə eyni şərt)
            records = records.filter(_path_q("group__path", target_units))
        unit_whens.append(When(ann_family=_STUDENTS, then=Subquery(records.values("group_id")[:1])))
    if other_roles:
        posts = active.filter(role_id__in=other_roles, scope_unit__isnull=False).order_by("-is_primary", "pk")
        if target_units:  # başqa kafedrada da üzvü olan — hədəf bölmədəki üzvlüyü sayılır
            posts = posts.filter(_path_q("scope_unit__path", target_units))
        unit_default = Subquery(posts.values("scope_unit_id")[:1])
    receipts = _receipts(announcement)
    queryset = users.annotate(ann_family=family_expr).annotate(
        ann_unit=Case(*unit_whens, default=unit_default, output_field=UUIDField()),
        ann_seen=Subquery(receipts.values("popup_seen_at")[:1]),
        ann_read=Subquery(receipts.values("read_at")[:1]),
        ann_ack=Subquery(receipts.values("acknowledged_at")[:1]),
    )
    if family in (_STUDENTS, _TEACHERS, _STAFF):
        queryset = queryset.filter(ann_family=family)
    if unit:
        OrgUnit = django_apps.get_model("organizations", "OrgUnit")
        subtree = OrgUnit.objects.filter(organization_id=org_id, path__contains=str(unit)).values("pk")
        queryset = queryset.filter(ann_unit__in=Subquery(subtree))
    return queryset


def _pct(part, whole) -> int:
    return int(round(100 * part / whole)) if whole else 0


def _finish(bucket: dict) -> dict:
    total = bucket["total"]
    bucket["unseen"] = max(total - bucket["reached"], 0)
    bucket["seen_pct"] = _pct(bucket["seen"], total)
    bucket["read_pct"] = _pct(bucket["read"], total)
    bucket["reached_pct"] = _pct(bucket["reached"], total)
    bucket["unseen_pct"] = _pct(bucket["unseen"], total)
    return bucket


def _empty(key, label) -> dict:
    return {"key": key, "label": label, "total": 0, "seen": 0, "read": 0, "reached": 0, "acked": 0}


def summary(announcement, *, dimension="faculty", family="", unit="") -> dict:
    """KPI-lər + ölçü üzrə bölgü (hər sətir: say + hədəfə görə faiz)."""
    dimension = dimension if dimension in STATS_DIMENSIONS else "faculty"
    rows = _grouped(base_queryset(announcement, family=family, unit=unit))
    family_labels = dict(Audience.choices)
    units = {} if dimension == "role" else su.unit_map(announcement.organization_id, {r["ann_unit"] for r in rows})
    buckets: dict = {}
    totals = _empty("", "")
    for row in rows:
        if dimension == "role":
            key = row["ann_family"] or ""
            label = str(family_labels.get(key, su.missing_label()))
        else:
            key = su.nearest(units, row["ann_unit"], su.DIMENSION_TYPES[dimension])
            label = su.unit_label(units, key) or su.missing_label()
        bucket = buckets.setdefault(key, _empty(key, label))
        for field in ("total", "seen", "read", "reached", "acked"):
            bucket[field] += row[field]
            totals[field] += row[field]
    ordered = sorted(buckets.values(), key=lambda item: (item["key"] == "", -item["total"], item["label"].casefold()))
    return {
        "dimension": dimension,
        "rows": [_finish(bucket) for bucket in ordered],
        "totals": _finish(totals),
        "requires_ack": announcement.requires_ack,
    }


def _status_filter(queryset, announcement, status):
    """Vəziyyət süzgəci ``EXISTS`` / ``NOT EXISTS`` ilə (semi/anti-join) — WHERE-də korrelyasiyalı dəyər müqayisəsi yox."""
    receipts = _receipts(announcement)
    if status == "seen":
        return queryset.filter(Exists(receipts.filter(popup_seen_at__isnull=False)))
    if status == "read":
        return queryset.filter(Exists(receipts.filter(read_at__isnull=False)))
    if status == "unseen":
        return queryset.exclude(Exists(receipts.filter(Q(popup_seen_at__isnull=False) | Q(read_at__isnull=False))))
    return queryset


def _order(status):
    if status == "seen":
        return ("-ann_seen", "last_name", "first_name", "pk")
    if status == "read":
        return ("-ann_read", "last_name", "first_name", "pk")
    return ("last_name", "first_name", "pk")


def _decorate(rows, org_id) -> None:
    """Şəxs sətirlərinə ad, bölmə və fakültə adı (bölmə xəritəsi ≤ 2 sorğu)."""
    units = su.unit_map(org_id, {row["ann_unit"] for row in rows})
    family_labels = dict(Audience.choices)
    faculty_types = su.DIMENSION_TYPES["faculty"]
    for row in rows:
        row["name"] = f"{row['first_name'] or ''} {row['last_name'] or ''}".strip() or row["username"]
        row["initials"] = "".join(part[:1] for part in row["name"].split()[:2]).upper() or "?"
        row["unit_label"] = su.unit_label(units, row["ann_unit"])
        faculty = su.nearest(units, row["ann_unit"], faculty_types)
        row["faculty_label"] = su.unit_label(units, faculty) if faculty != str(row["ann_unit"] or "") else ""
        row["family_label"] = str(family_labels.get(row["ann_family"], ""))


_VALUES = ("pk", "username", "first_name", "last_name", "ann_family", "ann_unit", "ann_seen", "ann_read", "ann_ack")


def people_page(announcement, *, family="", unit="", status="all", q="", page=1, page_size=STATS_PAGE_SIZE) -> dict:
    """Axtarışlı, server tərəfdə səhifələnən şəxs siyahısı (``all`` / ``seen`` / ``read`` / ``unseen``)."""
    status = status if status in STATS_STATUSES else "all"
    q = str(q or "").strip()[:100]
    queryset = _status_filter(base_queryset(announcement, family=family, unit=unit), announcement, status)
    search = tolerant_q(q, _SEARCH_FIELDS) if q else None
    if search is not None:
        queryset = queryset.filter(search)
    with no_jit():
        total = queryset.count()
        pages = max(1, math.ceil(total / page_size))
        page = max(1, min(int(page or 1), pages))
        start = (page - 1) * page_size
        rows = list(queryset.order_by(*_order(status)).values(*_VALUES)[start : start + page_size]) if total else []
    _decorate(rows, announcement.organization_id)
    return {"items": rows, "total": total, "page": page, "pages": pages, "status": status, "q": q}


def export_rows(announcement, *, family="", unit="", status="all", q="", limit=None) -> list:
    """İxrac üçün bütün (süzülmüş) sətirlər — bir sorğu + bölmə xəritəsi."""
    status = status if status in STATS_STATUSES else "all"
    queryset = _status_filter(base_queryset(announcement, family=family, unit=unit), announcement, status)
    search = tolerant_q(str(q or "").strip()[:100], _SEARCH_FIELDS) if q else None
    if search is not None:
        queryset = queryset.filter(search)
    ordered = queryset.order_by(*_order(status)).values(*_VALUES)
    with no_jit():
        rows = list(ordered[:limit] if limit else ordered)
    _decorate(rows, announcement.organization_id)
    return rows


__all__ = ["base_queryset", "export_rows", "people_page", "summary"]
