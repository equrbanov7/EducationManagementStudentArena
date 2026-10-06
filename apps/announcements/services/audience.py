"""Auditoriya — «bu elan bu istifadəçiyə aiddirmi?» (FAIL-CLOSED).

Ailələr (``apps/surveys/services/audience.py`` ilə EYNİ qayda, rol adına görə):

* ``students`` — ``student`` / ``lead_student``;
* ``teachers`` — tədris rolları (``teacher``, ``instructor``, ``assistant`` …);
* ``staff`` — qalan hər rol (rektorluq, dekanlıq, kafedra, RİM, tədris şöbəsi …);
* neytral rollar (``member``, ``alumni``, ``parent`` …) heç bir ailəyə düşmür.

Struktur daraltması (``Announcement.audience_units``): boş → bütün təşkilat; doludursa
istifadəçinin bölməsi seçilmiş bölmələrdən birinin ÖZÜ və ya ALT-AĞACI olmalıdır.
Tələbənin bölməsi aktiv akademik qeydinin QRUPU, müəllim/heyətin isə üzvlüyünün
``scope_unit``-idir. ``OrgUnit.path`` = ``"<kök-id>/…/<öz-id>"`` olduğundan istifadəçinin
ƏCDAD id-ləri path seqmentləridir — DB-də ``audience_units ?| ancestors`` ilə süzülür.

Sorğu büdcəsi: ailələr üzvlüklərdən (middleware ``select_related`` ilə gətirir — SIFIR
sorğu); əcdadlar tələbə üçün BİR sorğu (akademik qeyd + qrup path-ı), nəticə istifadəçi
obyektində request-ömürlü saxlanılır.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from django.apps import apps as django_apps
from django.db.models import Q

from core.roles import ProfileRole

from ..constants import ALL_FAMILIES, Audience

STUDENT_ROLE_NAMES = frozenset({"student", "lead_student"})
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

_MEMO_ATTR = "_announcements_viewer"


def family_of(role_name) -> str | None:
    name = ProfileRole.normalize_membership_role_name(role_name or "")
    if name in STUDENT_ROLE_NAMES:
        return Audience.STUDENTS.value
    if name in TEACHER_ROLE_NAMES:
        return Audience.TEACHERS.value
    if name in NEUTRAL_ROLE_NAMES:
        return None
    return Audience.STAFF.value


@dataclass(frozen=True)
class Viewer:
    """İstifadəçinin auditoriya «izi»: ailələri + bölmə əcdadları (id sətirləri)."""

    families: frozenset = field(default_factory=frozenset)
    ancestors: frozenset = field(default_factory=frozenset)

    @property
    def is_empty(self) -> bool:
        return not self.families


EMPTY_VIEWER = Viewer()


def _memberships(user, organization, memberships=None):
    if memberships is not None:
        return [m for m in memberships if getattr(m, "organization_id", organization.pk) == organization.pk]
    Membership = django_apps.get_model("organizations", "Membership")
    return list(
        Membership.objects.filter(user=user, organization=organization, is_active=True).select_related(
            "role", "scope_unit"
        )
    )


def _path_ids(path, pk) -> set:
    segments = [segment for segment in (path or "").strip("/").split("/") if segment]
    return set(segments) if segments else ({str(pk)} if pk else set())


def _student_group_ancestors(user, organization) -> set:
    StudentAcademicRecord = django_apps.get_model("registrar", "StudentAcademicRecord")
    rows = StudentAcademicRecord.objects.filter(
        organization=organization, student=user, is_active=True, group__isnull=False
    ).values_list("group_id", "group__path")
    result = set()
    for group_id, path in rows:
        result |= _path_ids(path, group_id)
    return result


def viewer_for(user, organization, memberships=None) -> Viewer:
    """Ailələr + əcdadlar (request-ömürlü memo; superuser üzvlüksüzdürsə — boş)."""
    if user is None or organization is None or not getattr(user, "is_authenticated", False):
        return EMPTY_VIEWER
    memo = getattr(user, _MEMO_ATTR, None)
    if isinstance(memo, tuple) and memo[0] == organization.pk:
        return memo[1]
    families, ancestors = set(), set()
    for membership in _memberships(user, organization, memberships):
        role = getattr(membership, "role", None)
        if role is None or not getattr(membership, "is_active", True):
            continue
        family = family_of(getattr(role, "name", ""))
        if not family:
            continue
        families.add(family)
        unit = getattr(membership, "scope_unit", None)
        if family != Audience.STUDENTS.value and unit is not None:
            ancestors |= _path_ids(unit.path, unit.pk)
    if Audience.STUDENTS.value in families:
        ancestors |= _student_group_ancestors(user, organization)
    viewer = Viewer(families=frozenset(families), ancestors=frozenset(ancestors))
    try:
        setattr(user, _MEMO_ATTR, (organization.pk, viewer))
    except Exception:  # noqa: BLE001 — dəyişməz istifadəçi obyekti (nadir)
        pass
    return viewer


def families_only(memberships) -> frozenset:
    """Yalnız ailələr — SIFIR sorğu (popup/badge qısa yolu üçün)."""
    result = set()
    for membership in memberships or ():
        role = getattr(membership, "role", None)
        if role is None or not getattr(membership, "is_active", True):
            continue
        family = family_of(getattr(role, "name", ""))
        if family:
            result.add(family)
    return frozenset(result)


def visible_q(viewer: Viewer) -> Q:
    """Auditoriya filtri (PostgreSQL ``?|``): ailə kəsişməsi VƏ (daraltma yox VƏ YA əcdad kəsişməsi)."""
    if viewer.is_empty:
        return Q(pk__in=[])
    unit_q = Q(audience_units=[])
    if viewer.ancestors:
        unit_q |= Q(audience_units__has_any_keys=sorted(viewer.ancestors))
    return Q(audience_families__has_any_keys=sorted(viewer.families)) & unit_q


def matches(families, units, viewer: Viewer) -> bool:
    """Python tərəfli eyni qayda (xülasə sətirləri üçün)."""
    if viewer.is_empty or not set(families or ()) & viewer.families:
        return False
    units = {str(unit) for unit in units or ()}
    return not units or bool(units & viewer.ancestors)


def normalize_families(raw) -> list:
    values = raw if isinstance(raw, (list, tuple, set, frozenset)) else []
    return sorted({str(value) for value in values if str(value) in ALL_FAMILIES})


__all__ = [
    "EMPTY_VIEWER",
    "Viewer",
    "families_only",
    "family_of",
    "matches",
    "normalize_families",
    "viewer_for",
    "visible_q",
]
