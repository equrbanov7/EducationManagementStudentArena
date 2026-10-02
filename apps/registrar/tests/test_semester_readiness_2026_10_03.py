"""«Semestr hazırlığı» (sahib 2026-10-03): kafedra üzrə müəllimsiz / sillabussuz / cədvəlsiz / jurnalı
yazılmayan fənlər, «SİLLABUSSUZ» KPI-nın düzəlişi və «Xatırlat» bildirişləri.

Kilidlənən qaydalar:

* sillabus qaydası JURNALLA EYNİDİR — yalnız ``approved_version`` sayılır (qaralama sayılmır);
* jurnal yoxlaması semestrin ilk həftəsindən sonra başlayır, 14 gün dərs yoxdursa «yazılmır»;
* KPI əvvəl mövcud olmayan ``Syllabus.status`` sahəsi ilə süzülürdü və həmişə «—» idi;
* «Xatırlat»: müəllimə öz fənləri (sillabus / jurnal), kafedra rəhbərinə xülasə; 12 saatda bir dəfə;
  yalnız ``semester.open`` olan rol göndərə bilir.
"""

from __future__ import annotations

from datetime import date, time

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, override_settings
from django.urls import reverse

import pytest

from apps.notifications.models import InAppNotification
from apps.organizations.models import OrgUnit
from apps.registrar import semester_readiness
from apps.registrar.models import CourseOffering, Lesson, ScheduleSlot, Subject
from apps.registrar.semester_open import coverage
from apps.registrar.semester_reminders import build_messages
from apps.syllabus import services
from apps.syllabus.constants import SectionKey
from apps.syllabus.tests.factories import (
    PLAN_HOURS,
    activate_member,
    complete_section_data,
    make_academic_stack,
    make_offering,
    make_org,
)
from core.constants import OrgUnitType, RoleScopeType

User = get_user_model()

pytestmark = pytest.mark.django_db

TEACHER_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]
CHAIR_PERMS = ["syllabus.view", "syllabus.review", "syllabus.approve", "syllabus.revise", "syllabus.reject"]
#: Semestr 2025-09-01 – 2026-01-31; «bu gün» ilk həftədən sonra.
TODAY = date(2025, 10, 15)

LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache", "LOCATION": "readiness"}}


def _approve(org, stack, offering, teacher, chair_user):
    actor = services.resolve_actor(teacher, org)
    _syllabus, version = services.create_draft(
        organization=org,
        subject=offering.subject,
        period=stack["period"],
        actor=actor,
        offering=offering,
        program=stack["program"],
        chair_unit=stack["chair"],
        plan_hours=dict(PLAN_HOURS),
    )
    for section_id, data in complete_section_data().items():
        if section_id in {SectionKey.PREV.value, SectionKey.SEND.value}:
            continue
        services.save_section(version=version, section_id=section_id, data=data, actor=actor)
    version.refresh_from_db()
    version = services.submit(version=version, actor=actor)
    return services.approve(version=version, actor=services.resolve_actor(chair_user, org))


@pytest.fixture()
def world():
    org = make_org("sem-ready")
    teacher = User.objects.create_user("rd_teacher", "rd_teacher@x.test", "pw")
    chair_user = User.objects.create_user("rd_chair", "rd_chair@x.test", "pw")
    office = User.objects.create_user("rd_office", "rd_office@x.test", "pw")
    dean = User.objects.create_user("rd_dean", "rd_dean@x.test", "pw")
    stack = make_academic_stack(org, code="RDY101")
    stack["period"].refresh_from_db()  # fabrik tarixləri mətn kimi verir; DB-dən `date` gəlir
    activate_member(org, teacher, "teacher", permissions=TEACHER_PERMS)
    activate_member(
        org,
        chair_user,
        "chair_head",
        permissions=CHAIR_PERMS,
        scope_unit=stack["chair"],
        level=70,
        scope_type=RoleScopeType.UNIT,
    )
    activate_member(org, office, "teaching_office_head", permissions=["semester.view", "semester.open"], level=80)
    activate_member(org, dean, "dean", permissions=["semester.view"], level=75)
    stack["chair"].head = chair_user
    stack["chair"].save(update_fields=["head"])
    stack["subject"].chair_unit = stack["chair"]
    stack["subject"].save(update_fields=["chair_unit"])
    other_subject = Subject.objects.create(organization=org, code="RDY102", name="Fənn 2", chair_unit=stack["chair"])
    other_group = OrgUnit.objects.create(
        organization=org, name="RDY-qrup-2", slug="sem-ready-rdy-group-2", unit_type=OrgUnitType.GROUP
    )

    ready = make_offering(org, stack, teacher)  # hər şey qaydasında
    _approve(org, stack, ready, teacher, chair_user)
    ScheduleSlot.objects.create(
        organization=org, offering=ready, weekday=2, start_time=time(9, 0), end_time=time(10, 30)
    )
    Lesson.objects.create(organization=org, offering=ready, date=date(2025, 10, 10))

    stale = CourseOffering.objects.create(  # müəllim var, sillabus yox, slot var, son dərs 20 gün əvvəl
        organization=org, subject=other_subject, period=stack["period"], group=stack["group"], instructor=teacher
    )
    ScheduleSlot.objects.create(
        organization=org, offering=stale, weekday=3, start_time=time(9, 0), end_time=time(10, 30)
    )
    Lesson.objects.create(organization=org, offering=stale, date=date(2025, 9, 25))

    bare = CourseOffering.objects.create(  # heç nə yoxdur
        organization=org, subject=other_subject, period=stack["period"], group=other_group
    )
    return {
        "org": org,
        "stack": stack,
        "period": stack["period"],
        "teacher": teacher,
        "chair_user": chair_user,
        "office": office,
        "dean": dean,
        "ready": ready,
        "stale": stale,
        "bare": bare,
    }


def _client(user, org):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = org.slug
    session.save()
    return client


def test_offering_issues_follow_journal_rules(world):
    issues = semester_readiness.offering_issues(world["org"], world["period"], today=TODAY)
    assert issues[world["ready"].pk]["issues"] == []
    assert issues[world["stale"].pk]["issues"] == ["no_syllabus", "no_journal"]
    assert issues[world["bare"].pk]["issues"] == ["no_teacher", "no_syllabus", "no_schedule", "no_journal"]


def test_journal_is_not_checked_in_the_first_week_or_after_the_semester(world):
    first_week = semester_readiness.offering_issues(world["org"], world["period"], today=date(2025, 9, 5))
    after_end = semester_readiness.offering_issues(world["org"], world["period"], today=date(2026, 2, 10))
    for result in (first_week, after_end):
        assert all("no_journal" not in item["issues"] for item in result.values())


def test_draft_syllabus_is_not_counted_as_approved(world):
    actor = services.resolve_actor(world["teacher"], world["org"])
    services.create_draft(
        organization=world["org"],
        subject=world["stale"].subject,
        period=world["period"],
        actor=actor,
        offering=world["stale"],
        chair_unit=world["stack"]["chair"],
        plan_hours=dict(PLAN_HOURS),
    )
    issues = semester_readiness.offering_issues(world["org"], world["period"], today=TODAY)
    assert "no_syllabus" in issues[world["stale"].pk]["issues"]


def test_readiness_by_chair_counts_and_kpi_is_no_longer_blank(world):
    report = semester_readiness.readiness_by_chair(
        world["org"],
        world["period"],
        issues_map=semester_readiness.offering_issues(world["org"], world["period"], today=TODAY),
    )
    [row] = report["rows"]
    assert row["chair_id"] == str(world["stack"]["chair"].pk)
    assert (row["total"], row["ready"], row["pct"]) == (3, 1, 33)
    assert (row["no_teacher"], row["no_syllabus"], row["no_schedule"], row["no_journal"]) == (1, 2, 1, 2)
    assert coverage(world["org"], world["period"])["without_syllabus"] == 2


def test_reminder_messages_are_personal_and_skip_schedule_for_teachers(world):
    from unittest import mock

    with mock.patch("apps.registrar.semester_readiness.timezone.localdate", return_value=TODAY):
        messages = build_messages(world["org"], world["period"], str(world["stack"]["chair"].pk))
    teacher_text = messages["teachers"][world["teacher"].pk]
    assert "Sillabus təsdiqlənməyib: Fənn 2" in teacher_text
    assert "Jurnalda dərs yazılmır: Fənn 2" in teacher_text
    assert "cədvəl" not in teacher_text.lower()
    assert "1 fənn — müəllim təyin olunmayıb" in messages["chair"]
    assert "1 fənn — dərs cədvəli yoxdur" in messages["chair"]


@override_settings(CACHES=LOCMEM)
def test_remind_action_sends_once_per_cooldown_and_needs_open_permission(world):
    cache.clear()
    url = reverse("registrar:semester_action")
    payload = {
        "action": "remind_readiness",
        "period": str(world["period"].pk),
        "chair": str(world["stack"]["chair"].pk),
    }

    denied = _client(world["dean"], world["org"]).post(url, payload)
    assert denied.status_code == 403

    office = _client(world["office"], world["org"])
    first = office.post(url, payload)
    assert first.status_code == 200, first.content
    body = first.json()
    assert body["ok"] is True and body["teachers"] == 1 and body["chair_members"] >= 1
    assert "müəllimə" in body["message"]
    events = InAppNotification.objects.filter(metadata__event="semester_readiness_reminder")
    assert set(events.values_list("recipient__username", flat=True)) >= {"rd_teacher", "rd_chair"}

    again = office.post(url, payload)
    assert again.status_code == 429
    assert events.count() == len(set(events.values_list("recipient_id", flat=True)))

    bad = office.post(url, {**payload, "chair": "not-a-uuid"})
    assert bad.status_code == 404


def test_semester_section_renders_readiness_panel_and_issue_filter(world):
    client = _client(world["office"], world["org"])
    url = reverse("accounts:profile_section_fragment", kwargs={"section": "semester-opening"})
    response = client.get(url, {"sm_period": str(world["period"].pk), "sm_issue": "no_teacher"})
    assert response.status_code == 200
    section = response.context["semester_opening_section"]
    assert section["readiness"]["rows"][0]["total"] == 3
    assert [row["id"] for row in section["rows"]] == [str(world["bare"].pk)]
    assert any(field["name"] == "sm_issue" for field in section["filter_fields"])
    html = response.json()["html"]
    assert "Semestr hazırlığı" in html
    assert "remind_readiness" in html
