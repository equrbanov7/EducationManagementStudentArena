"""Sillabus iş axını keçidlərinin bildiriş yaratdığını yoxlayır.

Bildirişlər ``transaction.on_commit`` ilə göndərilir (bax
``apps/syllabus/services/notifications.py``); pytest-django-ın
``django_capture_on_commit_callbacks`` fixture-i olmadan bu callback-lər
heç vaxt işə düşməz (test tranzaksiyası əsl commit etmir).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model

import pytest

from apps.notifications.models import InAppNotification, NotificationType
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
from core.constants import RoleScopeType

User = get_user_model()

TEACHER_PERMS = ["syllabus.view", "syllabus.edit", "syllabus.submit", "grade.input"]
CHAIR_PERMS = ["syllabus.view", "syllabus.review", "syllabus.approve", "syllabus.revise", "syllabus.reject"]
DEAN_PERMS = ["syllabus.view", "syllabus.review", "syllabus.approve", "syllabus.revise", "syllabus.reject"]

pytestmark = pytest.mark.django_db


@pytest.fixture()
def world():
    org = make_org("syl-notify-org")
    teacher = User.objects.create_user("syl_notify_teacher", "syl_notify_teacher@x.test", "pw")
    chair = User.objects.create_user("syl_notify_chair", "syl_notify_chair@x.test", "pw")
    stack = make_academic_stack(org)
    activate_member(org, teacher, "teacher", permissions=TEACHER_PERMS)
    activate_member(
        org,
        chair,
        "chair_head",
        permissions=CHAIR_PERMS,
        scope_unit=stack["chair"],
        level=70,
        scope_type=RoleScopeType.UNIT,
    )
    offering = make_offering(org, stack, teacher)
    return {"org": org, "teacher": teacher, "chair": chair, "stack": stack, "offering": offering}


def _actor(user, org):
    return services.resolve_actor(user, org)


def _fill(version, actor):
    for section_id, data in complete_section_data().items():
        if section_id in {SectionKey.PREV.value, SectionKey.SEND.value}:
            continue
        services.save_section(version=version, section_id=section_id, data=data, actor=actor)
    version.refresh_from_db()
    return version


@pytest.fixture()
def draft(world):
    actor = _actor(world["teacher"], world["org"])
    syllabus, version = services.create_draft(
        organization=world["org"],
        subject=world["stack"]["subject"],
        period=world["stack"]["period"],
        actor=actor,
        offering=world["offering"],
        program=world["stack"]["program"],
        chair_unit=world["stack"]["chair"],
        plan_hours=PLAN_HOURS,
    )
    return syllabus, version, actor


def _notifications_for(user, event=None):
    qs = InAppNotification.objects.filter(recipient=user)
    if event:
        qs = qs.filter(metadata__event=event)
    return qs


def test_submit_notifies_chair_head(django_capture_on_commit_callbacks, draft, world):
    _syllabus, version, actor = draft
    _fill(version, actor)
    with django_capture_on_commit_callbacks(execute=True):
        services.submit(version=version, actor=actor)

    notes = _notifications_for(world["chair"], "syllabus_submit")
    assert notes.count() == 1
    note = notes.first()
    assert "təsdiqə göndərildi" in note.title
    assert note.notification_type == NotificationType.APPROVAL


def test_submit_falls_back_to_dean_when_no_chair_head(django_capture_on_commit_callbacks, world):
    # Ayrıca dosye: kafedra müdiri YOXDUR, sadəcə dekan var.
    org = world["org"]
    dean = User.objects.create_user("syl_notify_dean", "syl_notify_dean@x.test", "pw")
    stack2 = make_academic_stack(org, code="DEAN301")
    activate_member(
        org,
        dean,
        "dean",
        permissions=DEAN_PERMS,
        scope_unit=stack2["chair"],
        level=80,
        scope_type=RoleScopeType.UNIT,
    )
    teacher2 = User.objects.create_user("syl_notify_teacher2", "syl_notify_teacher2@x.test", "pw")
    activate_member(org, teacher2, "teacher", permissions=TEACHER_PERMS)
    offering2 = make_offering(org, stack2, teacher2)
    actor2 = _actor(teacher2, org)
    _syllabus2, version2 = services.create_draft(
        organization=org,
        subject=stack2["subject"],
        period=stack2["period"],
        actor=actor2,
        offering=offering2,
        program=stack2["program"],
        chair_unit=stack2["chair"],
        plan_hours=PLAN_HOURS,
    )
    _fill(version2, actor2)

    with django_capture_on_commit_callbacks(execute=True):
        services.submit(version=version2, actor=actor2)

    assert _notifications_for(dean, "syllabus_submit").count() == 1


def test_start_review_notifies_author(django_capture_on_commit_callbacks, draft, world):
    _syllabus, version, actor = draft
    _fill(version, actor)
    with django_capture_on_commit_callbacks(execute=True):
        version = services.submit(version=version, actor=actor)
    chair_actor = _actor(world["chair"], world["org"])
    with django_capture_on_commit_callbacks(execute=True):
        services.start_review(version=version, actor=chair_actor)

    notes = _notifications_for(world["teacher"], "syllabus_start_review")
    assert notes.count() == 1
    assert "baxışa götürüldü" in notes.first().title


def test_approve_notifies_author(django_capture_on_commit_callbacks, draft, world):
    _syllabus, version, actor = draft
    _fill(version, actor)
    with django_capture_on_commit_callbacks(execute=True):
        version = services.submit(version=version, actor=actor)
    chair_actor = _actor(world["chair"], world["org"])
    with django_capture_on_commit_callbacks(execute=True):
        services.approve(version=version, actor=chair_actor)

    notes = _notifications_for(world["teacher"], "syllabus_approve")
    assert notes.count() == 1
    assert "təsdiqləndi" in notes.first().title


def test_request_revision_notifies_author_with_reason(django_capture_on_commit_callbacks, draft, world):
    _syllabus, version, actor = draft
    _fill(version, actor)
    with django_capture_on_commit_callbacks(execute=True):
        version = services.submit(version=version, actor=actor)
    chair_actor = _actor(world["chair"], world["org"])
    reason = "Ədəbiyyat siyahısı yenilənməlidir."
    with django_capture_on_commit_callbacks(execute=True):
        services.request_revision(version=version, actor=chair_actor, reason=reason)

    notes = _notifications_for(world["teacher"], "syllabus_request_revision")
    assert notes.count() == 1
    assert reason in notes.first().title


def test_reject_notifies_author_with_reason(django_capture_on_commit_callbacks, draft, world):
    _syllabus, version, actor = draft
    _fill(version, actor)
    with django_capture_on_commit_callbacks(execute=True):
        version = services.submit(version=version, actor=actor)
    chair_actor = _actor(world["chair"], world["org"])
    reason = "Fənn planına uyğun deyil."
    with django_capture_on_commit_callbacks(execute=True):
        services.reject(version=version, actor=chair_actor, reason=reason)

    notes = _notifications_for(world["teacher"], "syllabus_reject")
    assert notes.count() == 1
    assert reason in notes.first().title


def test_withdraw_notifies_the_reviewer_who_opened_it(django_capture_on_commit_callbacks, draft, world):
    _syllabus, version, actor = draft
    _fill(version, actor)
    with django_capture_on_commit_callbacks(execute=True):
        version = services.submit(version=version, actor=actor)
    chair_actor = _actor(world["chair"], world["org"])
    with django_capture_on_commit_callbacks(execute=True):
        version = services.start_review(version=version, actor=chair_actor)

    with django_capture_on_commit_callbacks(execute=True):
        services.withdraw(version=version, actor=actor, reason="Səhv fayl əlavə etmişəm")

    notes = _notifications_for(world["chair"], "syllabus_withdraw")
    assert notes.count() == 1


def test_withdraw_from_submitted_sends_nothing_no_reviewer_yet(django_capture_on_commit_callbacks, draft, world):
    """SUBMITTED-dən (heç kim baxışa götürməmiş) geri çağırmada rəyçi yoxdur."""
    _syllabus, version, actor = draft
    _fill(version, actor)
    with django_capture_on_commit_callbacks(execute=True):
        version = services.submit(version=version, actor=actor)

    with django_capture_on_commit_callbacks(execute=True):
        services.withdraw(version=version, actor=actor, reason="Səhv fayl əlavə etmişəm")

    assert InAppNotification.objects.filter(metadata__event="syllabus_withdraw").count() == 0
