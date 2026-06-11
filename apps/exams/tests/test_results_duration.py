from datetime import timedelta

from django.contrib.auth import get_user_model
from django.utils import timezone

import pytest

from apps.exams.models import Exam, ExamAttempt
from apps.exams.views.teacher.results import (
    _attempt_effective_duration,
    _attempt_effective_finish,
    _expire_overdue_attempts,
)
from apps.organizations.models import Organization, OrganizationType

User = get_user_model()


@pytest.mark.django_db
def test_expire_overdue_and_duration_clamp():
    teacher = User.objects.create_user(username="exp-t1", email="exp-t1@example.com", password="x")
    student = User.objects.create_user(username="exp-s1", email="exp-s1@example.com", password="x")
    org = Organization.objects.create(
        name="Expire Org", org_type=OrganizationType.SCHOOL, owner=teacher, status="active", is_active=True
    )
    teacher.profile.organization = org
    teacher.profile.organization_type = org.org_type
    teacher.profile.save(update_fields=["organization", "organization_type", "updated_at"])
    exam = Exam.objects.create(author=teacher, title="E", exam_type="test", is_active=True, total_duration_minutes=60)

    a = ExamAttempt.objects.create(user=student, exam=exam, status="in_progress")
    ExamAttempt.objects.filter(pk=a.pk).update(started_at=timezone.now() - timedelta(hours=31))
    a.refresh_from_db()

    # lazy bulk expire
    assert _expire_overdue_attempts(exam) == 1
    a.refresh_from_db()
    assert a.status == "expired"
    assert a.duration_seconds == 3600
    assert a.finished_at == a.started_at + timedelta(minutes=60)

    # köhnə yanlış sətir (30+ saat) display-də clamp olunur
    b = ExamAttempt.objects.create(user=student, exam=exam, status="expired", attempt_number=2)
    ExamAttempt.objects.filter(pk=b.pk).update(
        started_at=timezone.now() - timedelta(hours=31),
        finished_at=timezone.now(),
        duration_seconds=int(timedelta(hours=31).total_seconds()),
    )
    b.refresh_from_db()
    finish, inferred = _attempt_effective_finish(b)
    assert inferred is True
    assert finish == b.started_at + timedelta(minutes=60)
    assert _attempt_effective_duration(b, finish) == 3600

    # mark_finished gecikəndə deadline-a clamp edir
    c = ExamAttempt.objects.create(user=student, exam=exam, status="in_progress", attempt_number=3)
    ExamAttempt.objects.filter(pk=c.pk).update(started_at=timezone.now() - timedelta(hours=5))
    c.refresh_from_db()
    c.mark_finished(status="expired")
    assert c.duration_seconds == 3600
