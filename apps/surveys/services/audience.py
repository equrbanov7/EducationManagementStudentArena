"""Sorğu auditoriyası — kim doldurmalıdır (FAIL-CLOSED).

Ailələr (rol adına görə, ``ProfileRole.normalize_membership_role_name``):

* ``students`` — ``student`` / ``lead_student``;
* ``teachers`` — tədris rolları (``teacher``, ``instructor``, ``assistant`` …);
* ``staff`` — qalan hər rol (rektorluq, dekanlıq, kafedra müdiri, RİM, tədris şöbəsi …);
* neytral rollar (``member``, ``alumni``, ``parent`` …) heç bir ailəyə düşmür.

``everyone`` = üç ailənin birləşməsi. Superuser / view-as heç vaxt auditoriya deyil (qapı və
inbox onları ayrıca kənarlaşdırır).

Daraltma (``Survey.audience_filter``), mövcud struktur əhatəsi qaydası ilə (``OrgUnit.path``
alt-ağacı, ``organizations.scoping.UnitScope.unit_subtree_q`` ilə eyni məntiq):

* ``units`` — fakültə / kafedra / ixtisas / qrup: tələbə aktiv akademik qeydinin QRUPU ilə,
  müəllim/heyət isə üzvlüyünün ``scope_unit``-i ilə alt-ağaca düşməlidir;
* ``programs`` / ``course_years`` — YALNIZ tələbə atributlarıdır: seçiləndə auditoriyada yalnız
  uyğun tələbələr qalır (müəllim/heyət düşür).

Sorğu büdcəsi: istifadəçi yoxlaması (:func:`user_in_audience`) daraltma yoxdursa SIFIR sorğu
(üzvlüklər middleware-dən), varsa 1–2 sorğu; iştirak hesabı (:func:`audience_user_ids`) 2–3 sorğu.
"""

from __future__ import annotations

import uuid

from django.apps import apps as django_apps
from django.db.models import Q

from core.roles import ProfileRole

from .. import registrar_bridge as bridge
from ..constants import MAX_FILTER_ITEMS, STUDENT_ROLE_NAMES, Audience

FAMILY_STUDENTS = Audience.STUDENTS.value
FAMILY_TEACHERS = Audience.TEACHERS.value
FAMILY_STAFF = Audience.STAFF.value
ALL_FAMILIES = frozenset({FAMILY_STUDENTS, FAMILY_TEACHERS, FAMILY_STAFF})

TEACHER_ROLE_NAMES = frozenset(
    {
        "teacher",
        "assistant_teacher",
        "instructor",
        "professor",
        "associate_professor",
        "senior_instructor",
        "assistant",
        "lab_assistant",
    }
)
NEUTRAL_ROLE_NAMES = frozenset({"member", "alumni", "parent", "trustee", "collaborator", "owner", ""})
#: DB-də saxlanan (normallaşdırılmamış) adlar da daxil — sorğu filtri üçün.
_STUDENT_DB_NAMES = tuple(sorted(STUDENT_ROLE_NAMES))
_TEACHER_DB_NAMES = tuple(sorted(TEACHER_ROLE_NAMES))
_NON_STAFF_DB_NAMES = tuple(sorted(STUDENT_ROLE_NAMES | TEACHER_ROLE_NAMES | NEUTRAL_ROLE_NAMES))


def family_of(role_name) -> str | None:
    name = ProfileRole.normalize_membership_role_name(role_name or "")
    if name in STUDENT_ROLE_NAMES:
        return FAMILY_STUDENTS
    if name in TEACHER_ROLE_NAMES:
        return FAMILY_TEACHERS
    if name in NEUTRAL_ROLE_NAMES:
        return None
    return FAMILY_STAFF


def role_families(memberships) -> set:
    """Aktiv üzvlüklərin ailələri (sıfır sorğu — rol ``select_related`` ilə gəlir)."""
    families = set()
    for membership in memberships or ():
        role = getattr(membership, "role", None)
        if role is None or not getattr(membership, "is_active", True):
            continue
        family = family_of(getattr(role, "name", ""))
        if family:
            families.add(family)
    return families


def audience_families(audience) -> frozenset:
    if audience == Audience.EVERYONE:
        return ALL_FAMILIES
    return frozenset({audience}) if audience in ALL_FAMILIES else frozenset()


# ── Daraltma filtri ─────────────────────────────────────────────────────────


def _uuid_list(raw) -> list:
    result = []
    for item in raw if isinstance(raw, (list, tuple)) else []:
        try:
            value = str(uuid.UUID(str(item)))
        except (TypeError, ValueError, AttributeError):
            continue
        if value not in result:
            result.append(value)
    return result[:MAX_FILTER_ITEMS]


def normalize_filter(raw) -> dict:
    """Etibarlı, təkrarsız, sıralı filtr (yanlış dəyərlər atılır)."""
    raw = raw if isinstance(raw, dict) else {}
    years = []
    for item in raw.get("course_years") or []:
        try:
            year = int(item)
        except (TypeError, ValueError):
            continue
        if 1 <= year <= 10 and year not in years:
            years.append(year)
    return {
        "units": _uuid_list(raw.get("units")),
        "programs": _uuid_list(raw.get("programs")),
        "course_years": sorted(years),
    }


def is_narrowed(audience_filter) -> bool:
    flt = normalize_filter(audience_filter)
    return bool(flt["units"] or flt["programs"] or flt["course_years"])


def student_only(audience_filter) -> bool:
    flt = normalize_filter(audience_filter)
    return bool(flt["programs"] or flt["course_years"])


def _unit_paths(organization, unit_ids) -> dict:
    if not unit_ids:
        return {}
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    return {
        str(pk): path or ""
        for pk, path in OrgUnit.objects.filter(organization=organization, pk__in=unit_ids).values_list("pk", "path")
    }


def _in_subtree(unit_id, path, roots: dict) -> bool:
    """``roots = {id: path}`` — vahid özü və ya alt-ağacı (``path`` materiallaşmış yoldur)."""
    if not roots:
        return False
    if unit_id is not None and str(unit_id) in roots:
        return True
    path = path or ""
    return any(root_path and path.startswith(f"{root_path}/") for root_path in roots.values())


def _student_row_matches(row, flt, roots) -> bool:
    if flt["units"] and not _in_subtree(row["group_id"], row["group_path"], roots):
        return False
    if flt["programs"] and str(row["program_id"]) not in flt["programs"]:
        return False
    if flt["course_years"] and row["course_year"] not in flt["course_years"]:
        return False
    return True


# ── Tək istifadəçi (qapı / inbox) ───────────────────────────────────────────


def user_in_audience(survey, user, memberships) -> bool:
    """İstifadəçi bu sorğunun auditoriyasındadırmı (FAIL-CLOSED)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    families = role_families(memberships) & audience_families(survey.audience)
    if not families:
        return False
    flt = normalize_filter(survey.audience_filter)
    if not (flt["units"] or flt["programs"] or flt["course_years"]):
        return True
    roots = _unit_paths(survey.organization_id, flt["units"])
    if flt["units"] and not roots:
        return False  # seçilmiş vahidlər silinib — heç kim (fail-closed)
    if FAMILY_STUDENTS in families:
        for row in bridge.active_student_rows(survey.organization_id, [user.pk]):
            if _student_row_matches(row, flt, roots):
                return True
    if families - {FAMILY_STUDENTS} and flt["units"] and not (flt["programs"] or flt["course_years"]):
        for membership in memberships or ():
            role = getattr(membership, "role", None)
            if role is None or family_of(role.name) in (None, FAMILY_STUDENTS):
                continue
            unit = getattr(membership, "scope_unit", None)
            if unit is not None and _in_subtree(unit.pk, unit.path, roots):
                return True
    return False


# ── Bütün auditoriya (iştirak faizi, bildiriş) ──────────────────────────────


def _family_q(families) -> Q:
    q = Q(pk__in=[])
    if FAMILY_STUDENTS in families:
        q |= Q(role__name__in=_STUDENT_DB_NAMES)
    if FAMILY_TEACHERS in families:
        q |= Q(role__name__in=_TEACHER_DB_NAMES)
    if FAMILY_STAFF in families:
        q |= ~Q(role__name__in=_NON_STAFF_DB_NAMES)
    return q


def _memberships(organization):
    Membership = django_apps.get_model("organizations", "Membership")
    return Membership.objects.filter(organization=organization, is_active=True, user__is_active=True)


def audience_user_ids(survey) -> set:
    """Auditoriyanın bütün istifadəçi id-ləri (superuser-lər də üzvdürsə daxildir)."""
    families = audience_families(survey.audience)
    if not families:
        return set()
    organization = survey.organization_id
    base = _memberships(organization)
    flt = normalize_filter(survey.audience_filter)
    if not (flt["units"] or flt["programs"] or flt["course_years"]):
        return set(base.filter(_family_q(families)).values_list("user_id", flat=True))
    roots = _unit_paths(organization, flt["units"])
    if flt["units"] and not roots:
        return set()
    result = set()
    if FAMILY_STUDENTS in families:
        students = {
            row["student_id"]
            for row in bridge.active_student_rows(organization)
            if _student_row_matches(row, flt, roots)
        }
        if students:
            result |= set(
                base.filter(_family_q({FAMILY_STUDENTS}), user_id__in=students).values_list("user_id", flat=True)
            )
    others = families - {FAMILY_STUDENTS}
    if others and flt["units"] and not (flt["programs"] or flt["course_years"]):
        unit_q = Q(pk__in=[])
        for root_id, root_path in roots.items():
            unit_q |= Q(scope_unit_id=root_id) | Q(scope_unit__path__startswith=f"{root_path}/")
        result |= set(base.filter(_family_q(others)).filter(unit_q).values_list("user_id", flat=True))
    return result


def user_locations(organization, user_ids) -> dict:
    """``{user_id: [(unit_id, path), …]}`` — tələbə qrupu + heyət üzvlüyünün vahidi (2 sorğu)."""
    wanted = set(user_ids)
    located: dict = {}
    if not wanted:
        return located
    # Böyük auditoriyada nəhəng ``IN (…)`` əvəzinə təşkilat üzrə oxunur və Python-da süzülür.
    narrow = list(wanted) if len(wanted) <= 500 else None
    for row in bridge.active_student_rows(organization, narrow):
        if row["group_id"] and row["student_id"] in wanted:
            located.setdefault(row["student_id"], []).append((row["group_id"], row["group_path"]))
    memberships = _memberships(organization).filter(scope_unit__isnull=False)
    if narrow is not None:
        memberships = memberships.filter(user_id__in=narrow)
    for user_id, unit_id, path in memberships.values_list("user_id", "scope_unit_id", "scope_unit__path"):
        if user_id in wanted:
            located.setdefault(user_id, []).append((unit_id, path))
    return located


def unit_rows(organization, unit_ids=None) -> list:
    """İştirak cədvəlinin sətirləri: seçilmiş vahidlər, yoxdursa təşkilatın fakültələri."""
    from core.constants import OrgUnitType

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    queryset = OrgUnit.objects.filter(organization=organization)
    if unit_ids:
        queryset = queryset.filter(pk__in=unit_ids)
    else:
        queryset = queryset.filter(unit_type=OrgUnitType.FACULTY)
    return [
        {"id": pk, "name": name, "path": path or ""}
        for pk, name, path in queryset.order_by("path", "name").values_list("pk", "name", "path")[:60]
    ]


def unit_choices(organization) -> list:
    """Qurucunun daraltma siyahısı: fakültə → kafedra/şöbə → ixtisas → qrup (ağac sırası ilə)."""
    from core.constants import OrgUnitType

    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    wanted = [
        OrgUnitType.FACULTY,
        OrgUnitType.CHAIR,
        OrgUnitType.DEPARTMENT,
        OrgUnitType.SPECIALTY,
        OrgUnitType.GROUP,
    ]
    rows = (
        OrgUnit.objects.filter(organization=organization, unit_type__in=wanted)
        .order_by("path")
        .values_list("pk", "name", "unit_type", "level")[:1500]
    )
    return [
        {"id": str(pk), "label": name, "type": unit_type, "level": level or 0} for pk, name, unit_type, level in rows
    ]


def unit_labels(organization, unit_ids) -> dict:
    if not unit_ids:
        return {}
    OrgUnit = django_apps.get_model("organizations", "OrgUnit")
    return {
        str(pk): name
        for pk, name in OrgUnit.objects.filter(organization=organization, pk__in=unit_ids).values_list("pk", "name")
    }
