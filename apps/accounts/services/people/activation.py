"""Hesab aktivləşdirmə hesabatı — qruplar üzrə (sahib 2026-10-03).

Problem: prod-da 6285 aktiv tələbədən cəmi ~56-sı öz parolunu qurub e-poçtunu təsdiqləyib; bal
xəbərdarlığı, sorğu, bildiriş — hamısı tələbənin girişindən asılıdır. Dekanlığa hansı qrupun geri
qaldığını və kimin hələ girmədiyini göstərən siyahı + çap vərəqi lazımdır.

Mənbə reyestrin ÖZÜDÜR (``registry.filtered_state_records``): eyni əhatə (dekan → öz fakültəsi),
eyni filtrlər, eyni ``account_state`` tərifi. Oxumayanlar (arxiv / xaric / məzun) sayılmır — onlardan
aktivləşdirmə gözlənilmir. Parol və ya e-poçt heç yerdə göstərilmir.
"""

from __future__ import annotations

from django.db.models import Count, Q

from .registry import filtered_state_records
from .rows import full_name_of, resolve_unit_ancestors

#: Aktivləşdirmə gözlənilməyən vəziyyətlər (bax ``study_state.STUDY_STATES``).
EXCLUDED_STATES = ("archived", "expelled", "graduated")


def _pct(part: int, total: int) -> int:
    return round(100 * part / total) if total else 0


def activation_report(*, actor, request=None, values=None) -> dict:
    """``{"rows": [...qrup...], "faculties": [...], "totals": {...}}`` — ən geri qalan qrup birinci."""
    empty = {"rows": [], "faculties": [], "totals": {"total": 0, "activated": 0, "initial": 0, "never": 0, "pct": 0}}
    if not actor.can_view_registry or actor.organization is None:
        return empty

    records = filtered_state_records(actor=actor, request=request, values=values).exclude(
        study_state__in=EXCLUDED_STATES
    )
    grouped = list(
        records.order_by()
        .values("group_id", "group__name")
        .annotate(
            total=Count("id"),
            activated=Count("id", filter=Q(account_state="activated")),
            initial=Count("id", filter=Q(account_state="initial")),
            never=Count("id", filter=Q(student__last_login__isnull=True)),
        )
    )
    if not grouped:
        return empty

    from apps.organizations.models import OrgUnit

    units = list(
        OrgUnit.objects.filter(
            organization=actor.organization, pk__in=[row["group_id"] for row in grouped if row["group_id"]]
        ).only("id", "name", "path", "unit_type")
    )
    ancestors = {
        str(key): value for key, value in resolve_unit_ancestors(units, organization=actor.organization).items()
    }

    rows = []
    for row in grouped:
        group_id = str(row["group_id"]) if row["group_id"] else ""
        rows.append(
            {
                "group_id": group_id,
                "group_name": row["group__name"] or "",
                "faculty": (ancestors.get(group_id) or {}).get("faculty", ""),
                "total": row["total"],
                "activated": row["activated"],
                "initial": row["initial"],
                "never": row["never"],
                "pct": _pct(row["activated"], row["total"]),
            }
        )
    rows.sort(key=lambda item: (item["pct"], -item["initial"], item["group_name"]))

    faculties: dict[str, dict] = {}
    for row in rows:
        bucket = faculties.setdefault(
            row["faculty"], {"faculty": row["faculty"], "groups": 0, "total": 0, "activated": 0, "initial": 0}
        )
        bucket["groups"] += 1
        for key in ("total", "activated", "initial"):
            bucket[key] += row[key]
    faculty_rows = sorted(
        ({**item, "pct": _pct(item["activated"], item["total"])} for item in faculties.values()),
        key=lambda item: (item["pct"], item["faculty"]),
    )

    totals = {key: sum(row[key] for row in rows) for key in ("total", "activated", "initial", "never")}
    totals["pct"] = _pct(totals["activated"], totals["total"])
    return {"rows": rows, "faculties": faculty_rows, "totals": totals}


def activation_sheet(*, actor, group_id: str, request=None) -> dict | None:
    """Bir qrupun çap vərəqi: hələ aktivləşdirməyən tələbələr (ad + istifadəçi adı, PAROLSUZ).

    Qrup aktorun əhatəsində deyilsə (və ya mövcud deyilsə) ``None`` — görünüş 404 qaytarır.
    """
    if not actor.can_view_registry or actor.organization is None or not group_id:
        return None
    records = (
        filtered_state_records(actor=actor, request=request, values={"group": group_id})
        .exclude(study_state__in=EXCLUDED_STATES)
        .select_related("student", "group")
        .order_by("student__last_name", "student__first_name")
    )
    students = list(records)
    if not students:
        return None
    group = students[0].group
    ancestors = resolve_unit_ancestors([group], organization=actor.organization).get(group.pk) or {}
    pending = [
        {
            "name": full_name_of(record.student),
            "username": record.student.username,
            "never_logged_in": record.student.last_login is None,
        }
        for record in students
        if record.account_state != "activated"
    ]
    return {
        "group_name": group.name,
        "faculty": ancestors.get("faculty", ""),
        "total": len(students),
        "activated": len(students) - len(pending),
        "pending": pending,
    }


__all__ = ["EXCLUDED_STATES", "activation_report", "activation_sheet"]
