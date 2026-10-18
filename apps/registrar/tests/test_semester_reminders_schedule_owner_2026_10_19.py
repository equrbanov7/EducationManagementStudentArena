"""«Semestr hazırlığı» → «Xatırlat»: «Cədvəl yoxdur» cədvəli QURANA gedir (2026-10-19 düzəlişi).

Cədvəli Tədris şöbəsi yox, ``schedule.manage`` açarlı dekanlıq / koordinator (bölmə səviyyəli) qurur: onlara
fənn · qrup siyahısı ilə bildiriş gedir; mərkəzi (təşkilat səviyyəli) açar sahibinə və müəllimə — yox.
Kafedra xülasəsi cədvəli kimin qurduğunu yazır.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import override_settings

import pytest

from apps.notifications.models import InAppNotification
from apps.organizations.models import AcademicPeriod, OrgUnit
from apps.registrar.models import CourseOffering, Subject
from apps.registrar.semester_reminders import build_messages, schedule_owner_messages, send_reminders
from apps.syllabus.tests.factories import activate_member, make_org
from core.constants import AcademicPeriodType, OrgUnitType, RoleScopeType

User = get_user_model()

pytestmark = pytest.mark.django_db

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "sched-owner"}}


@pytest.fixture()
def world():
    org = make_org("sched-owner")
    faculty = OrgUnit.objects.create(organization=org, name="Fak", slug="so-fak", unit_type=OrgUnitType.FACULTY)
    other_faculty = OrgUnit.objects.create(
        organization=org, name="Başqa fak", slug="so-fak2", unit_type=OrgUnitType.FACULTY
    )
    chair = OrgUnit.objects.create(
        organization=org, name="Kafedra", slug="so-kaf", unit_type=OrgUnitType.CHAIR, parent=faculty
    )
    group = OrgUnit.objects.create(
        organization=org, name="SO-251", slug="so-251", unit_type=OrgUnitType.GROUP, parent=faculty
    )
    period = AcademicPeriod.objects.create(
        organization=org,
        name="Payız",
        period_type=AcademicPeriodType.SEMESTER,
        academic_year="2026/2027",
        start_date="2026-09-15",
        end_date="2027-01-31",
    )
    period.refresh_from_db()
    subject = Subject.objects.create(organization=org, code="SO101", name="Slotsuz fənn", chair_unit=chair)
    teacher = User.objects.create_user("so_teacher", "so_teacher@x.test", "pw")
    activate_member(org, teacher, "teacher", permissions=["syllabus.view", "grade.input"])
    CourseOffering.objects.create(organization=org, subject=subject, period=period, group=group, instructor=teacher)
    users = {name: User.objects.create_user(f"so_{name}", f"so_{name}@x.test", "pw") for name in ("dean", "far", "rim")}
    activate_member(
        org,
        users["dean"],
        "dean_office",
        permissions=["schedule.manage"],
        scope_unit=faculty,
        scope_type=RoleScopeType.UNIT,
    )
    activate_member(
        org,
        users["far"],
        "coordinator",
        permissions=["schedule.manage"],
        scope_unit=other_faculty,
        scope_type=RoleScopeType.UNIT,
    )
    activate_member(org, users["rim"], "rim_staff", permissions=["schedule.manage"], level=80)
    return {"org": org, "period": period, "chair": chair, "teacher": teacher, **users}


def test_schedule_owner_messages_target_unit_scoped_schedule_managers(world):
    messages = schedule_owner_messages(world["org"], world["period"], str(world["chair"].pk))
    assert set(messages) == {world["dean"].pk}
    _user, text = messages[world["dean"].pk]
    assert "Slotsuz fənn · SO-251" in text


def test_chair_summary_names_who_builds_the_schedule(world):
    chair_text = build_messages(world["org"], world["period"], str(world["chair"].pk))["chair"]
    assert "1 fənn — dərs cədvəli yoxdur (cədvəli dekanlıq / koordinator qurur)" in chair_text


@override_settings(CACHES=LOCMEM)
def test_send_reminders_notifies_schedule_owner_once(world):
    cache.clear()
    result = send_reminders(world["org"], world["period"], world["chair"], actor=world["rim"])
    assert result["schedule_owners"] == 1
    notes = InAppNotification.objects.filter(
        metadata__event="semester_readiness_reminder", metadata__audience="schedule_owner"
    )
    assert list(notes.values_list("recipient__username", flat=True)) == ["so_dean"]
    assert "section%3Dschedule-manage" in notes.get().link  # təşkilat keçidi ilə sarılır
    teacher_notes = InAppNotification.objects.filter(recipient=world["teacher"]).values_list("message", flat=True)
    assert teacher_notes and all("cədvəl" not in message.lower() for message in teacher_notes)
    assert send_reminders(world["org"], world["period"], world["chair"], actor=world["rim"])["throttled"] is True


@override_settings(CACHES=LOCMEM)
def test_dean_covering_two_chairs_gets_one_merged_notice(world):
    """Rəy 2026-10-19: «Xatırlat» kafedra üzrədir — dekanlıq ikinci kafedradan təkrar bildiriş almır, ilk
    bildiriş isə əhatəsindəki BÜTÜN cədvəlsiz fənləri sadalayır."""
    cache.clear()
    org, period = world["org"], world["period"]
    faculty = world["chair"].parent
    second_chair = OrgUnit.objects.create(
        organization=org, name="Kafedra 2", slug="so-kaf2", unit_type=OrgUnitType.CHAIR, parent=faculty
    )
    group = OrgUnit.objects.get(organization=org, slug="so-251")
    subject = Subject.objects.create(
        organization=org, code="SO201", name="İkinci slotsuz fənn", chair_unit=second_chair
    )
    CourseOffering.objects.create(organization=org, subject=subject, period=period, group=group)

    first = send_reminders(org, period, world["chair"], actor=world["rim"])
    second = send_reminders(org, period, second_chair, actor=world["rim"])
    assert (first["schedule_owners"], second["schedule_owners"], second["schedule_owners_recent"]) == (1, 0, 1)
    notes = InAppNotification.objects.filter(recipient=world["dean"], metadata__audience="schedule_owner")
    assert notes.count() == 1
    message = notes.get().message
    assert "Slotsuz fənn · SO-251" in message and "İkinci slotsuz fənn · SO-251" in message
