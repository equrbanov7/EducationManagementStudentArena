"""«Kadr analitikası» — müəllim başına BİR sətir (toplu sorğularla, N+1 YOX).

Mənbələr (hamısı mövcud data — yeni sahə yoxdur):

* heyət: aktiv akademik üzvlük (``ACADEMIC_ROLE_NAMES``) VƏ YA seçilmiş ilin yük profili
  (``workload.TeacherWorkloadProfile``) olan hər istifadəçi (superadmin çıxılır);
* fakültə / kafedra: seçilmiş üzvlüyün ``scope_unit``-i və onun ``path`` əcdadları;
* elmi ad / dərəcə / cins / doğum tarixi: ``UserProfile``; elmi ad boşdursa yük profilinin vəzifəsi;
* ştat vahidi: ``TeacherWorkloadProfile.staff_fraction`` + ``is_external`` (Forma 7 idxalı buraya yazır);
* plan saat / norma / doluluq: ``apps.workload.public.chair_staff_load`` (modul daxilinə girmədən);
* tədris fəaliyyəti: ``apps.registrar.public.instructor_activity`` (jurnal + keçirilmiş dərs);
* inzibati vəzifə (sahib 2026-10-11): akademik roldan BAŞQA aktiv üzvlüklər (dekan, kafedra müdiri,
  prorektor, HR …) + profilin sərbəst «Vəzifə» mətni — bir sorğu, bütün namizədlər üçün;
* ştat tarixçəsi (``profile_history``): müəllimin BÜTÜN illərin yük profilləri — yalnız açıq səhifənin
  sətirləri üçün (1 sorğu / səhifə), siyahıda «Tarixçə» xülasəsi kimi göstərilir.

Sorğu büdcəsi SABİTDİR (sətir sayından asılı deyil): üzvlüklər 1, inzibati üzvlüklər 1, yük profilləri
1, istifadəçilər 1, struktur 1, illər 2, yük aqreqatı 3 (fasad), jurnallar 1, dərslər 1 — cəmi ~12.
Filtr / aqreqat / səhifələmə bundan sonra Python-da gedir (heyət ~10³ sətirdir).
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import date

from django.contrib.auth import get_user_model
from django.db.models import Q

from core.constants import OrgUnitType

from . import constants as C

User = get_user_model()

_FACULTY_TYPES = (OrgUnitType.FACULTY, OrgUnitType.DEANERY)
_CHAIR_TYPES = (OrgUnitType.CHAIR, OrgUnitType.DEPARTMENT)
_TEACHER_ROLES = frozenset(C.ACADEMIC_ROLE_NAMES)
#: İnzibati vəzifə sayılmayan rollar — sırf dərs deyən rollar (kafedra müdiri inzibatidir).
_PLAIN_TEACHER_ROLES = frozenset(C.ACADEMIC_ROLE_NAMES) - frozenset(C.ADMIN_ROLE_NAMES_ALSO)


# ── Tədris ili ──────────────────────────────────────────────────────────────


def year_options(organization) -> tuple[list[str], str]:
    """(illər — yenidən köhnəyə, default il). Default: cari dövrün ili, yoxdursa ən sonuncu."""
    from apps.organizations.models import AcademicPeriod
    from apps.workload.models import TeacherWorkloadProfile

    periods = list(
        AcademicPeriod.objects.filter(organization=organization)
        .exclude(academic_year="")
        .values_list("academic_year", "is_current")
        .distinct()
    )
    years = {year for year, _current in periods}
    years |= set(
        TeacherWorkloadProfile.objects.filter(organization=organization)
        .values_list("academic_year", flat=True)
        .distinct()
    )
    ordered = sorted((year for year in years if year), reverse=True)
    current = next((year for year, is_current in periods if is_current), "")
    return ordered, current or (ordered[0] if ordered else "")


def year_bounds(academic_year: str) -> tuple[date | None, date | None]:
    """«2026/2027» → (2026-09-01, 2027-09-01); tanınmırsa (None, None)."""
    match = re.match(r"^\s*(\d{4})", academic_year or "")
    if not match:
        return None, None
    start = int(match.group(1))
    return date(start, 9, 1), date(start + 1, 9, 1)


# ── Struktur ────────────────────────────────────────────────────────────────


def _structure(organization) -> dict:
    """Fakültə / kafedra vahidləri — {id: (ad, tip, path)} (1 sorğu, struktur ölçüsü qədər)."""
    from apps.organizations.models import OrgUnit

    rows = OrgUnit.objects.filter(organization=organization, unit_type__in=(*_FACULTY_TYPES, *_CHAIR_TYPES))
    return {
        str(pk): (name, unit_type, path)
        for pk, name, unit_type, path in rows.values_list("pk", "name", "unit_type", "path")
    }


def _placement(unit_id, unit_path: str, unit_type: str, units: dict) -> tuple[str, str, str, str]:
    """(faculty_id, faculty_name, chair_id, chair_name) — vahidin özü + path əcdadları."""
    faculty_id = faculty = chair_id = chair = ""
    segments = [segment for segment in (unit_path or "").split("/") if segment.strip()]
    if unit_id and str(unit_id) not in segments:
        segments.append(str(unit_id))
    for segment in segments:
        info = units.get(segment)
        if info is None:
            continue
        name, kind, _path = info
        if kind in _FACULTY_TYPES and not faculty_id:
            faculty_id, faculty = segment, name
        elif kind in _CHAIR_TYPES and not chair_id:
            chair_id, chair = segment, name
    return faculty_id, faculty, chair_id, chair


def _pick_membership(rows: list[dict]) -> dict | None:
    """Müəllimin «əsas» üzvlüyü: akademik rol → kafedra vahidi → əsas → yüksək səviyyə → köhnə."""
    if not rows:
        return None

    def rank(row):
        return (
            row["role__name"] not in _TEACHER_ROLES,
            row["scope_unit__unit_type"] not in _CHAIR_TYPES,
            not row["is_primary"],
            -(row["role__level"] or 0),
            row["created_at"],
        )

    return sorted(rows, key=rank)[0]


# ── Sətir qurucusu ─────────────────────────────────────────────────────────


def _status(values: dict) -> str:
    if values["profile__is_deleted"]:
        return C.STATUS_DELETED
    if values["profile__access_state"] == "archived":
        return C.STATUS_ARCHIVED
    if not values["is_active"]:
        return C.STATUS_BLOCKED
    return C.STATUS_ACTIVE


def _age(birth: date | None, today: date) -> int | None:
    if not birth:
        return None
    return today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))


def staff_type(profile: dict | None) -> str:
    """Ştat növü: profil yoxdur → none; kənar və ya 0 pay → saathesabı; ≥1 → tam; 0,5 → yarım."""
    if profile is None:
        return C.STAFF_NONE
    fraction = float(profile["staff_fraction"] or 0)
    if profile["is_external"] or fraction <= 0:
        return C.STAFF_HOURLY
    if fraction >= 1:
        return C.STAFF_FULL
    if abs(fraction - 0.5) < 1e-9:
        return C.STAFF_HALF
    return C.STAFF_PARTIAL


def _name_key(values: dict) -> str:
    parts = (values["last_name"], values["first_name"], values["profile__patronymic"])
    return " ".join(" ".join((part or "").split()).casefold() for part in parts).strip()


def _population(organization, academic_year: str):
    """(üzvlük sətirləri user→[..], yük profilləri user→{..}) — 2 sorğu."""
    from apps.organizations.models import Membership
    from apps.workload.models import TeacherWorkloadProfile

    profiles = {
        row["teacher_id"]: row
        for row in TeacherWorkloadProfile.objects.filter(organization=organization, academic_year=academic_year).values(
            "teacher_id", "position", "staff_fraction", "is_external"
        )
    }
    profile_teachers = TeacherWorkloadProfile.objects.filter(
        organization=organization, academic_year=academic_year
    ).values("teacher_id")
    memberships = defaultdict(list)
    rows = (
        Membership.objects.filter(organization=organization, is_active=True, role__organization=organization)
        .filter(Q(role__is_active=True, role__name__in=C.ACADEMIC_ROLE_NAMES) | Q(user_id__in=profile_teachers))
        .values(
            "user_id",
            "role__name",
            "role__display_name",
            "role__level",
            "is_primary",
            "created_at",
            "title",
            "scope_unit_id",
            "scope_unit__path",
            "scope_unit__unit_type",
        )
        .order_by()
    )
    for row in rows:
        memberships[row["user_id"]].append(row)
    return memberships, profiles


def _admin_memberships(organization, user_ids) -> dict:
    """İnzibati vəzifələr: user → [{role, label, unit, unit_id, title, since}] (1 sorğu, rol səviyyəsinə görə)."""
    from apps.organizations.models import Membership
    from core.staff_position import visible_role_label

    out = defaultdict(list)
    rows = (
        Membership.objects.filter(
            organization=organization, is_active=True, role__organization=organization, role__is_active=True
        )
        .filter(user_id__in=user_ids)
        .exclude(role__name__in=_PLAIN_TEACHER_ROLES)
        .exclude(role__name__in=("student", "alumni", "member", "lead_student"))
        .values(
            "user_id",
            "role__name",
            "role__display_name",
            "role__level",
            "scope_unit_id",
            "scope_unit__name",
            "title",
            "created_at",
        )
        .order_by("-role__level", "created_at")
    )
    for row in rows:
        out[row["user_id"]].append(
            {
                "role": row["role__name"],
                # Seed-dən ingiliscə qalmış ad («Dean») → AZ etiket («Dekan»); admin dəyişdiyi ada toxunulmur.
                "label": visible_role_label(row["role__name"], row["role__display_name"]) or row["role__name"],
                "unit_id": str(row["scope_unit_id"] or ""),
                "unit": row["scope_unit__name"] or "",
                "title": row["title"] or "",
                "since": row["created_at"].date() if row["created_at"] else None,
            }
        )
    return out


_USER_FIELDS = (
    "pk",
    "username",
    "first_name",
    "last_name",
    "is_active",
    "is_superuser",
    "last_login",
    "date_joined",
    "profile__patronymic",
    "profile__academic_title",
    "profile__academic_degree",
    "profile__gender",
    "profile__birth_date",
    "profile__password_change_required",
    "profile__is_deleted",
    "profile__access_state",
    "profile__staff_position",
)


def build_rows(actor, academic_year: str, *, today: date | None = None) -> list[dict]:
    """Aktorun əhatəsindəki hər müəllim üçün bir sətir (sabit sorğu sayı)."""
    from apps.registrar.public import instructor_activity
    from apps.workload.public import chair_staff_load

    organization = actor.organization
    if organization is None or not actor.has_access:
        return []
    today = today or date.today()
    memberships, profiles = _population(organization, academic_year)
    candidate_ids = set(memberships) | set(profiles)
    if not candidate_ids:
        return []
    units = _structure(organization)
    admin = _admin_memberships(organization, candidate_ids)
    users = list(User.objects.filter(pk__in=candidate_ids, is_superuser=False).values(*_USER_FIELDS))
    year_start, year_end = year_bounds(academic_year)

    rows = []
    for values in users:
        picked = _pick_membership(memberships.get(values["pk"], []))
        unit_id = picked["scope_unit_id"] if picked else None
        unit_path = (picked or {}).get("scope_unit__path") or ""
        if not actor.unit_visible(unit_id, unit_path):
            continue
        faculty_id, faculty, chair_id, chair = _placement(
            unit_id, unit_path, (picked or {}).get("scope_unit__unit_type") or "", units
        )
        profile = profiles.get(values["pk"])
        title = values["profile__academic_title"] or C.POSITION_TO_TITLE.get((profile or {}).get("position") or "", "")
        joined = values["date_joined"].date() if values["date_joined"] else None
        admin_roles = admin.get(values["pk"], [])
        staff_position = " ".join((values["profile__staff_position"] or "").split())
        rows.append(
            {
                "id": values["pk"],
                "username": values["username"],
                "name": " ".join(
                    part for part in (values["last_name"], values["first_name"], values["profile__patronymic"]) if part
                ).strip()
                or values["username"],
                "name_key": _name_key(values),
                "faculty_id": faculty_id,
                "faculty": faculty,
                "chair_id": chair_id,
                "chair": chair,
                "role": (picked or {}).get("role__name") or "",
                "has_membership": picked is not None,
                "title": title or C.TITLE_NONE,
                "title_from_position": bool(title and not values["profile__academic_title"]),
                "degree": values["profile__academic_degree"] or C.DEGREE_NONE,
                "gender": values["profile__gender"] or "unspecified",
                "age": _age(values["profile__birth_date"], today),
                "status": _status(values),
                "never_logged_in": values["last_login"] is None,
                "not_activated": bool(values["profile__password_change_required"]),
                "joined": joined,
                "is_new": bool(joined and year_start and year_start <= joined < year_end),
                "staff_type": staff_type(profile),
                "staff_fraction": float(profile["staff_fraction"] or 0) if profile else None,
                "is_external": bool(profile and profile["is_external"]),
                "position": (profile or {}).get("position") or "",
                "admin_roles": admin_roles,
                "admin_role_names": [item["role"] for item in admin_roles],
                "staff_position": staff_position,
                "admin_label": _admin_label(admin_roles, staff_position),
            }
        )
    _attach_load(rows, organization, academic_year, chair_staff_load)
    _attach_activity(
        rows,
        instructor_activity(
            organization=organization, academic_year=academic_year, teacher_ids=[row["id"] for row in rows]
        ),
    )
    _attach_issues(rows)
    return rows


def _admin_label(admin_roles, staff_position: str) -> str:
    """Siyahı xanası / sıralama / ixrac üçün tək sətir: «Dekan · Mühəndislik; Kafedra müdiri · İnformatika»."""
    parts = []
    for item in admin_roles:
        parts.append(f"{item['label']} · {item['unit']}" if item["unit"] else item["label"])
    if not parts and staff_position:
        parts.append(staff_position)
    return "; ".join(parts)


def _attach_load(rows, organization, academic_year, chair_staff_load) -> None:
    load = chair_staff_load(
        organization=organization, teacher_ids=[row["id"] for row in rows], academic_year=academic_year
    )["by_teacher"]
    for row in rows:
        summary = load.get(row["id"]) or {}
        hours = int(summary.get("total_hours") or 0)
        row["planned_load"] = hours
        row["norm_hours"] = int(summary.get("norm_hours") or 0)
        row["hourly_paid_hours"] = int(summary.get("hourly_paid_hours") or 0)
        row["fill_percent"] = int(summary.get("fill_percent") or 0)
        row["load_band"] = summary.get("load_band", "free") if hours else "none"


def _attach_activity(rows, activity) -> None:
    for row in rows:
        item = activity.get(row["id"]) or {}
        row["journals"] = item.get("journals", 0)
        row["lessons"] = item.get("lessons", 0)
        row["held_hours"] = item.get("held_hours", 0)
        row["planned_hours"] = item.get("planned_hours", 0)


def _attach_issues(rows) -> None:
    names = Counter(row["name_key"] for row in rows if row["name_key"])
    for row in rows:
        issues = []
        if row["title"] == C.TITLE_NONE:
            issues.append(C.ISSUE_NO_TITLE)
        if row["degree"] == C.DEGREE_NONE:
            issues.append(C.ISSUE_NO_DEGREE)
        if row["staff_type"] == C.STAFF_NONE:
            issues.append(C.ISSUE_NO_STAFF)
        if not row["chair_id"]:
            issues.append(C.ISSUE_NO_CHAIR)
        if row["name_key"] and names[row["name_key"]] > 1:
            issues.append(C.ISSUE_DUPLICATE)
        if not row["has_membership"]:
            issues.append(C.ISSUE_NO_MEMBERSHIP)
        if row["never_logged_in"]:
            issues.append(C.ISSUE_NEVER_LOGGED)
        row["issues"] = issues


def profile_history(organization, teacher_ids) -> dict:
    """Ştat tarixçəsi: teacher → [{year, position, staff_type, staff_fraction, is_external, norm, confirmed,
    changed}] — yenidən köhnəyə; ``changed`` əvvəlki ilə (xronoloji) nisbətən ştat/vəzifə fərqidir.

    Yalnız açıq səhifənin sətirləri üçün çağırılır (1 sorğu); ``academic_year`` boş olan profil atılır."""
    from apps.workload.models import TeacherWorkloadProfile

    ids = [pk for pk in teacher_ids if pk]
    if not ids:
        return {}
    by_teacher = defaultdict(list)
    rows = (
        TeacherWorkloadProfile.objects.filter(organization=organization, teacher_id__in=ids)
        .exclude(academic_year="")
        .values(
            "teacher_id",
            "academic_year",
            "position",
            "staff_fraction",
            "is_external",
            "load_confirmed_at",
        )
        .order_by("academic_year")
    )
    for row in rows:
        by_teacher[row["teacher_id"]].append(row)
    # Norma — «Sistem tənzimləmələri» qaydası (ştat payı + inzibati vəzifə), saxlanmış sahə deyil.
    from apps.workload.public import admin_teacher_ids, current_rule

    rule = current_rule()
    # Üzvlük sorğusu yalnız inzibati norma fərq yaradanda (defoltda 1 ştatdan fərqli paylar) — sorğu büdcəsi.
    admins = admin_teacher_ids(
        organization,
        [tid for tid, items in by_teacher.items() if any(rule.base(i["staff_fraction"]) != rule.admin for i in items)],
    )
    out = {}
    for teacher_id, items in by_teacher.items():
        timeline = []
        previous = None
        for item in items:
            kind = staff_type(item)
            entry = {
                "year": item["academic_year"],
                "position": item["position"] or "",
                "staff_type": kind,
                "staff_fraction": float(item["staff_fraction"] or 0),
                "is_external": bool(item["is_external"]),
                "norm": rule.norm(item["staff_fraction"], is_admin=teacher_id in admins),
                "confirmed": item["load_confirmed_at"] is not None,
                "changed": bool(
                    previous
                    and (
                        previous["staff_type"] != kind
                        or previous["staff_fraction"] != float(item["staff_fraction"] or 0)
                        or previous["position"] != (item["position"] or "")
                    )
                ),
            }
            timeline.append(entry)
            previous = entry
        timeline.reverse()
        out[teacher_id] = timeline
    return out


def structure_options(organization, actor) -> tuple[list[dict], list[dict]]:
    """Filtr üçün (fakültələr, kafedralar) — əhatə daxilində, ada görə (1 sorğu)."""
    units = _structure(organization)
    faculties, chairs = [], []
    for unit_id, (name, kind, path) in units.items():
        if not actor.unit_visible(unit_id, path) and not actor.scope.is_org_wide:
            continue
        if kind in _FACULTY_TYPES:
            faculties.append({"value": unit_id, "label": name})
        elif kind in _CHAIR_TYPES:
            faculty_id, faculty, _cid, _chair = _placement(unit_id, path, kind, units)
            chairs.append({"value": unit_id, "label": name, "faculty_id": faculty_id, "faculty": faculty})
    faculties.sort(key=lambda item: item["label"].casefold())
    chairs.sort(key=lambda item: item["label"].casefold())
    return faculties, chairs


__all__ = ["build_rows", "profile_history", "staff_type", "structure_options", "year_bounds", "year_options"]
