"""Sistem faktları (toplu, sətir sayından asılı olmayan sorğular): üzvlüklər, dərs yükü, cari jurnallar.

Hamısı ``bypass_rls`` altında (əmr) çağırılır; heç nə yazmır.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from django.apps import apps as django_apps

from ..people.constants import TEACHER_ROLE_NAMES

#: Dərs yükü sənədinin ləğv statusu (``workload.constants.TaskStatus.CANCELLED``) — import kənarı yaranmasın.
CANCELLED_TASK = "cancelled"


@dataclass
class Facts:
    memberships: dict = field(default_factory=lambda: defaultdict(list))  # user → [üzvlük sətri]
    load_chairs: dict = field(default_factory=lambda: defaultdict(lambda: defaultdict(int)))  # user → kafedra → saat
    journal_chairs: dict = field(default_factory=lambda: defaultdict(set))  # user → {kafedra | None}
    journal_count: dict = field(default_factory=lambda: defaultdict(int))
    unit_names: dict = field(default_factory=dict)
    unit_types: dict = field(default_factory=dict)
    inactive_units: set = field(default_factory=set)
    task_chairs: set = field(default_factory=set)  # tədris ilində tapşırığı olan kafedralar
    offering_chairs: dict = field(default_factory=lambda: defaultdict(int))  # kafedra → cari açılış sayı

    def has_load(self, user_id) -> bool:
        return bool(self.load_chairs.get(user_id))

    def has_journal(self, user_id) -> bool:
        return bool(self.journal_count.get(user_id))

    def teaching_now(self, user_id) -> bool:
        return self.has_load(user_id) or self.has_journal(user_id)


def _model(app_label, name):
    return django_apps.get_model(app_label, name)


def current_period_ids(organization) -> list:
    """Cari semestr(lər) — ``AcademicPeriod.is_current``."""
    return list(
        _model("organizations", "AcademicPeriod")
        .objects.filter(organization=organization, is_current=True)
        .values_list("pk", flat=True)
    )


def teaching_user_ids(organization, academic_year: str, period_ids) -> set:
    """Tədris ilində dərs yükü bölgüsü (``TeacherAssignment``) və ya cari semestrdə aktiv jurnalı olan istifadəçilər."""
    loaded = set(
        _model("workload", "TeacherAssignment")
        .objects.filter(
            organization=organization,
            teacher_id__isnull=False,
            row__task__academic_year=academic_year,
        )
        .exclude(row__task__status=CANCELLED_TASK)
        .values_list("teacher_id", flat=True)
        .distinct()
    )
    journals = set(
        _model("registrar", "CourseOffering")
        .objects.filter(organization=organization, is_active=True, period_id__in=list(period_ids or []))
        .exclude(instructor_id=None)
        .values_list("instructor_id", flat=True)
        .distinct()
    )
    return loaded | journals


def collect(organization, user_ids, *, academic_year: str, period_ids) -> Facts:
    facts = Facts()
    for unit_id, name, unit_type, active in (
        _model("organizations", "OrgUnit")
        .objects.filter(organization=organization)
        .values_list("id", "name", "unit_type", "is_active")
    ):
        facts.unit_names[str(unit_id)] = name
        facts.unit_types[str(unit_id)] = unit_type
        if not active:
            facts.inactive_units.add(str(unit_id))
    ids = [pk for pk in set(user_ids) if pk]
    for row in (
        _model("organizations", "Membership")
        .objects.filter(organization=organization, user_id__in=ids, is_active=True, role__is_active=True)
        .values(
            "id",
            "user_id",
            "role__name",
            "role__level",
            "scope_unit_id",
            "scope_unit__unit_type",
            "is_primary",
            "created_at",
        )
        .order_by()
    ):
        row["scope_unit_id"] = str(row["scope_unit_id"]) if row["scope_unit_id"] else None
        facts.memberships[row["user_id"]].append(row)
    for teacher_id, chair_id, hours in (
        _model("workload", "TeacherAssignment")
        .objects.filter(organization=organization, teacher_id__in=ids, row__task__academic_year=academic_year)
        .exclude(row__task__status=CANCELLED_TASK)
        .values_list("teacher_id", "row__task__chair_id", "hours")
    ):
        facts.load_chairs[teacher_id][str(chair_id)] += int(hours or 0)
    facts.task_chairs = {
        str(pk)
        for pk in _model("workload", "TeachingTask")
        .objects.filter(organization=organization, academic_year=academic_year)
        .exclude(status=CANCELLED_TASK)
        .values_list("chair_id", flat=True)
    }
    offerings = _model("registrar", "CourseOffering").objects.filter(
        organization=organization, is_active=True, period_id__in=list(period_ids or [])
    )
    for instructor_id, chair_id in offerings.filter(instructor_id__in=ids).values_list(
        "instructor_id", "subject__chair_unit_id"
    ):
        facts.journal_chairs[instructor_id].add(str(chair_id) if chair_id else None)
        facts.journal_count[instructor_id] += 1
    for chair_id in offerings.exclude(subject__chair_unit_id=None).values_list("subject__chair_unit_id", flat=True):
        facts.offering_chairs[str(chair_id)] += 1
    return facts


def role_user_ids(organization, role_names) -> set:
    """Bu rollardan birini (aktiv) daşıyan istifadəçilər — «köhnəlmiş rol» yoxlaması üçün."""
    return set(
        _model("organizations", "Membership")
        .objects.filter(organization=organization, is_active=True, role__name__in=list(role_names))
        .values_list("user_id", flat=True)
        .distinct()
    )


def teacher_role_user_ids(organization) -> set:
    """Təşkilatda aktiv müəllim-rollu üzvlüyü olan istifadəçilər (bloklu hesablar daxil)."""
    return set(
        _model("organizations", "Membership")
        .objects.filter(
            organization=organization, is_active=True, role__is_active=True, role__name__in=TEACHER_ROLE_NAMES
        )
        .values_list("user_id", flat=True)
        .distinct()
    )


__all__ = ["Facts", "collect", "current_period_ids", "role_user_ids", "teacher_role_user_ids", "teaching_user_ids"]
