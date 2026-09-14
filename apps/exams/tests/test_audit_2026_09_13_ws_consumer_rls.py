"""Audit 2026-09-13 infra P1-1 — final-mərkəz WS consumer-ləri NOBYPASSRLS rolu altında.

WS scope-da tenant GUC yoxdur; `FinalExamRoomConsumer`/`FinalExamWaitConsumer`
sorğuları `bypass_rls()`-siz idi → NOSUPERUSER NOBYPASSRLS tətbiq rolu (Codex
P0-01 rollout-u) altında FORCE RLS 0 sətir qaytarır və hər nəzarətçi monitoru /
tələbə gözləmə soketi 4403 alırdı. `ExamSupervisionConsumer` (bypass ilə) nəzarət
nöqtəsidir. Rol: `organizations.0003_rls_policies`-in yaratdığı `rls_app_role`
(`SET LOCAL ROLE` — test tranzaksiyası ilə geri qayıdır).
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.db import connection
from django.utils import timezone

import pytest

from apps.accounts.models import ProfileRole
from apps.exams.consumers import ExamSupervisionConsumer, FinalExamRoomConsumer, FinalExamWaitConsumer
from apps.exams.domain.final_center import TICKET_STATUS_WAITING
from apps.exams.models import Exam, ExamAttempt, ExamRoom, ExamRoomSession, FinalExamTicket
from apps.exams.services.final_center import open_entry
from apps.exams.tests.test_exam_center_policy import PASSWORD, _assign_user_to_org
from apps.organizations.models import Organization
from core.constants import OrganizationType

User = get_user_model()


def _sync(consumer_cls, name):
    """`database_sync_to_async` sarğısının altındakı sinxron funksiyanı qaytar."""
    return consumer_cls.__dict__[name].func


def _set(name, value):
    with connection.cursor() as cur:
        cur.execute("SELECT set_config(%s, %s, true)", [name, value])


@pytest.fixture
def final_center(db):
    owner = User.objects.create_user("aw_owner", "aw_owner@test.az", PASSWORD)
    org = Organization.objects.create(
        name="AW Univ", org_type=OrganizationType.UNIVERSITY, owner=owner, status="active", is_active=True
    )
    center = User.objects.create_user("aw_center", "aw_center@test.az", PASSWORD)
    _assign_user_to_org(center, org, ProfileRole.MEMBER, "exam_center_head")
    student = User.objects.create_user("aw_student", "aw_student@test.az", PASSWORD)
    _assign_user_to_org(student, org, ProfileRole.STUDENT, "student")
    exam = Exam.objects.create(
        title="AW Final", author=center, organization=org, exam_type="test", exam_type_extended="final", is_active=True
    )
    room = ExamRoom.objects.create(organization=org, name="Zal", code="ZAW", capacity=10)
    now = timezone.now()
    session = ExamRoomSession.objects.create(
        organization=org,
        room=room,
        invigilator=center,
        scheduled_start=now + timedelta(minutes=5),
        scheduled_end=now + timedelta(hours=2),
    )
    open_entry(session, center)
    ticket = FinalExamTicket.objects.create(
        organization=org, session=session, exam=exam, student=student, status=TICKET_STATUS_WAITING
    )
    attempt = ExamAttempt.objects.create(exam=exam, user=student, status="in_progress")
    return {"center": center, "student": student, "session": session, "ticket": ticket, "attempt": attempt}


@pytest.mark.postgres
@pytest.mark.django_db
def test_final_center_consumers_authorize_under_nobypassrls_role(final_center):
    if connection.vendor != "postgresql":
        pytest.skip("RLS yalnız PostgreSQL")
    center, student = final_center["center"], final_center["student"]
    session, ticket, attempt = final_center["session"], final_center["ticket"], final_center["attempt"]
    room_c, wait_c, sup_c = FinalExamRoomConsumer(), FinalExamWaitConsumer(), ExamSupervisionConsumer()

    # Superuser bağlantısı (RLS tətbiq olunmur) — hamısı keçir.
    assert _sync(FinalExamRoomConsumer, "_can_supervise")(room_c, center, session.id) is True
    assert _sync(FinalExamWaitConsumer, "_authorize")(wait_c, student, ticket.id, None, None) is not None

    # İstehsal rolu: NOBYPASSRLS, WS scope-da tenant GUC yoxdur.
    _set("app.bypass_rls", "off")
    _set("app.current_org_id", "")
    with connection.cursor() as cur:
        cur.execute("SET LOCAL ROLE rls_app_role")
        cur.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        assert cur.fetchone() == (False, False)

    assert _sync(ExamSupervisionConsumer, "_can_observe_attempt")(sup_c, student, attempt.id) is True
    assert _sync(FinalExamRoomConsumer, "_can_supervise")(room_c, center, session.id) is True
    auth = _sync(FinalExamWaitConsumer, "_authorize")(wait_c, student, ticket.id, None, None)
    assert auth is not None and auth["session_id"] == session.id

    # Presence yazıları da 0 sətrə düşməməlidir.
    wait_c.session_id, wait_c.ticket_id = session.id, ticket.id
    wait_c.entry_ticket_id, wait_c.entry_version = None, None
    _sync(FinalExamWaitConsumer, "_mark_connected_db")(wait_c, False)
    assert _sync(FinalExamWaitConsumer, "_heartbeat")(wait_c) is True
    with connection.cursor() as cur:
        cur.execute("RESET ROLE")
    ticket.refresh_from_db()
    assert ticket.last_seen_at is not None
