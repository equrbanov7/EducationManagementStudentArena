"""İmtahan ↔ jurnal açıq bağlantısı + müəllim → fənn seçimi + fənn dəyişəndə yenidən sinxron (sahib 2026-10-24).

Prod halı «JS Loop»: midterm əvvəl YANLIŞ fənnə bağlanıb, tələbələr verəndən SONRA fənn dəyişdirilib —
nəticələr jurnalın «Midterm» sütununa düşməyib. Bax ``apps/exams/services/exam_journal_link.py``.
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.db import connection
from django.test import Client
from django.urls import reverse
from django.utils import timezone

import pytest

from apps.audit.models import AuditLog
from apps.exams.forms import ExamForm
from apps.exams.models import Exam, ExamAttempt
from apps.exams.services import exam_journal_link, midterm_journal_sync
from apps.exams.tests.test_exam_center_policy import _assign_user_to_org
from apps.exams.tests.test_midterm_journal_sync_2026_10_21 import _MidtermSetup
from apps.organizations.models import OrgUnit
from apps.registrar import interim_components
from apps.registrar.models import ComponentScore, CourseOffering, Enrollment, Subject
from core.constants import OrgUnitType
from core.rls import bypass_rls
from core.roles import ProfileRole

_AUDIT_TYPE = "registrar.grade.midterm-auto"


def _login(user, organization):
    client = Client()
    client.force_login(user)
    session = client.session
    session["active_organization"] = organization.slug
    session.save()
    return client


class _LinkSetup(_MidtermSetup):
    """Midterm quraşdırması + YANLIŞ fənn (başqa müəllim, eyni qrup) + başqa qrup + imtahan mərkəzi."""

    def setUp(self):
        super().setUp()
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.teacher2 = User.objects.create_user("jl_teacher2", "jl_teacher2@qku.edu.az", "pw")
        self.center = User.objects.create_user("jl_center", "jl_center@qku.edu.az", "pw")
        with bypass_rls():
            _assign_user_to_org(self.teacher, self.org, ProfileRole.TEACHER, "teacher")
            _assign_user_to_org(self.teacher2, self.org, ProfileRole.TEACHER, "teacher")
            _assign_user_to_org(self.center, self.org, ProfileRole.MEMBER, "exam_center_head")
            self.wrong_subject = Subject.objects.create(organization=self.org, code="WR200", name="Yanlış fənn")
            self.wrong_offering = CourseOffering.objects.create(
                organization=self.org,
                subject=self.wrong_subject,
                period=self.period,
                group=self.group,
                instructor=self.teacher2,
                lesson_hours=30,
            )
            self.wrong_enrollment = Enrollment.objects.create(
                organization=self.org, student=self.student, offering=self.wrong_offering
            )
            self.other_group = OrgUnit.objects.create(
                organization=self.org, name="JBG2", slug="jb-g2", unit_type=OrgUnitType.GROUP
            )

    def _midterm_of(self, offering):
        with bypass_rls():
            return interim_components.ensure_kollokviums(offering)[0]

    def _score_in(self, offering, enrollment):
        with bypass_rls():
            return ComponentScore.objects.filter(component=self._midterm_of(offering), enrollment=enrollment).first()

    def _payload(self, **extra):
        start = timezone.localtime() + datetime.timedelta(days=1)
        payload = {
            "modal": "1",
            "title": "JS Loop",
            "description": "",
            "exam_type": "test",
            "exam_type_extended": "midterm",
            "subject": str(self.subject.pk),
            "random_question_count": "3",
            "start_datetime": start.strftime("%Y-%m-%dT%H:%M"),
            "end_datetime": (start + datetime.timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M"),
            "total_duration_minutes": "60",
            "max_attempts_per_user": "1",
            "allowed_units": [str(self.group.pk)],
        }
        payload.update(extra)
        return payload


class TeacherSubjectsEndpointTests(_LinkSetup):
    url = reverse("exams:journal_teacher_subjects")

    def _get(self, **params):
        response = _login(self.teacher, self.org).get(self.url, params, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_teacher_sees_only_own_current_period_subjects(self):
        data = self._get(teacher=self.teacher.pk)
        self.assertEqual([row["id"] for row in data["results"]], [str(self.subject.pk)])
        data = self._get(teacher=self.teacher2.pk)
        self.assertEqual([row["id"] for row in data["results"]], [str(self.wrong_subject.pk)])

    def test_selected_ok_flags_whether_current_subject_belongs_to_teacher(self):
        self.assertTrue(self._get(teacher=self.teacher.pk, selected=str(self.subject.pk))["selected_ok"])
        self.assertFalse(self._get(teacher=self.teacher2.pk, selected=str(self.subject.pk))["selected_ok"])

    def test_units_filter_limits_to_offerings_of_the_exam_groups(self):
        self.assertEqual(self._get(teacher=self.teacher.pk, units=str(self.other_group.pk))["results"], [])
        data = self._get(teacher=self.teacher.pk, units=str(self.group.pk))
        self.assertEqual([row["id"] for row in data["results"]], [str(self.subject.pk)])

    def test_non_teacher_or_garbage_teacher_returns_nothing(self):
        self.assertEqual(self._get(teacher=self.student.pk)["results"], [])
        self.assertEqual(self._get(teacher="abc")["results"], [])
        self.assertEqual(self._get()["results"], [])

    def test_search_query_filters_teacher_subjects(self):
        self.assertEqual(self._get(teacher=self.teacher.pk, q="Yanlış")["results"], [])
        self.assertEqual(len(self._get(teacher=self.teacher.pk, q="Proqram")["results"]), 1)

    def test_student_is_denied(self):
        response = _login(self.student, self.org).get(self.url, {"teacher": self.teacher.pk})
        self.assertEqual(response.status_code, 403)


class ExamFormTeacherValidationTests(_LinkSetup):
    def _form(self, **overrides):
        data = self._payload(**overrides)
        data.pop("allowed_units")
        return ExamForm(data, user=self.center, organization=self.org)

    def test_subject_not_taught_by_selected_teacher_is_rejected(self):
        with bypass_rls():
            form = self._form(journal_teacher=str(self.teacher2.pk))
            self.assertFalse(form.is_valid())
        self.assertIn("subject", form.errors)

    def test_teacher_with_own_subject_is_valid_and_empty_teacher_keeps_all_subjects(self):
        with bypass_rls():
            self.assertNotIn("subject", self._form(journal_teacher=str(self.teacher.pk)).errors)
            self.assertNotIn("subject", self._form(subject=str(self.wrong_subject.pk)).errors)

    def test_student_cannot_be_journal_teacher(self):
        with bypass_rls():
            form = self._form(journal_teacher=str(self.student.pk))
            self.assertFalse(form.is_valid())
        self.assertIn("journal_teacher", form.errors)


class AutoLinkOnCreateTests(_LinkSetup):
    def _create(self, **extra):
        client = _login(self.center, self.org)
        with self.captureOnCommitCallbacks(execute=True):
            response = client.post(
                reverse("exams:create_exam") + "?modal=1",
                self._payload(**extra),
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
        self.assertEqual(response.status_code, 200, response.content[:400])
        with bypass_rls():
            return Exam.objects.get(title="JS Loop")

    def test_create_links_each_group_offering_and_stores_teacher(self):
        exam = self._create(journal_teacher=str(self.teacher.pk))
        with bypass_rls():
            self.assertEqual(exam.journal_teacher_id, self.teacher.pk)
            self.assertEqual(list(exam.journal_offerings.all()), [self.offering])

    def test_teacher_without_groups_links_teacher_offerings(self):
        exam = self._create(journal_teacher=str(self.teacher.pk), allowed_units=[])
        with bypass_rls():
            self.assertEqual(list(exam.journal_offerings.all()), [self.offering])

    def test_subgroup_offering_is_linked_when_parent_group_is_assigned(self):
        with bypass_rls():
            faculty = OrgUnit.objects.create(organization=self.org, name="Fak", slug="jl-fak", unit_type="faculty")
            OrgUnit.objects.filter(pk=self.group.pk).update(parent=faculty, name="234 K az")
            sub = OrgUnit.objects.create(
                organization=self.org, name="234 K-1", slug="jl-sub", unit_type=OrgUnitType.GROUP, parent=faculty
            )
            sub_offering = CourseOffering.objects.create(
                organization=self.org, subject=self.subject, period=self.period, group=sub, instructor=self.teacher
            )
        exam = self._create()
        with bypass_rls():
            self.assertEqual(set(exam.journal_offerings.all()), {self.offering, sub_offering})


class LinkedSyncTests(_LinkSetup):
    def _linked_exam(self, **fields):
        exam, options = self._exam(title="JS Loop", **fields)
        with bypass_rls():
            exam.allowed_units.add(self.group)
            exam_journal_link.refresh_links(exam)
        return exam, options

    def test_submission_writes_to_linked_offering_scaled_to_30(self):
        exam, options = self._linked_exam()
        with bypass_rls():
            self.assertEqual(list(exam.journal_offerings.all()), [self.offering])
        attempt = self._finish(exam, options, correct=2)
        row = self._score_in(self.offering, self.enrollment)
        self.assertEqual(row.score, Decimal("20"))
        self.assertEqual(row.exam_source["attempt_id"], attempt.pk)
        self.assertEqual(row.exam_source["exam_id"], exam.pk)

    def test_linked_offering_wins_over_other_enrollment_of_same_subject(self):
        """Tələbə eyni fənn üzrə iki jurnalda (məs. alt qrup) — bal BAĞLI jurnala yazılır."""
        with bypass_rls():
            guest = OrgUnit.objects.create(organization=self.org, name="G-X", slug="jl-gx", unit_type="group")
            guest_offering = CourseOffering.objects.create(
                organization=self.org, subject=self.subject, period=self.period, group=guest
            )
            guest_enrollment = Enrollment.objects.create(
                organization=self.org, student=self.student, offering=guest_offering
            )
        exam, options = self._exam(title="JS Loop")
        with bypass_rls():
            exam.allowed_units.add(guest)
            exam_journal_link.refresh_links(exam)
        self._finish(exam, options, correct=3)
        self.assertEqual(self._score_in(guest_offering, guest_enrollment).score, Decimal("30"))
        self.assertIsNone(self._score_in(self.offering, self.enrollment))


class ResyncOnSubjectChangeTests(_LinkSetup):
    """İstifadəçinin dəqiq halı: yanlış fənn → tələbələr verir → fənn düzəldilir → jurnal düzəlir."""

    def _taken_with_wrong_subject(self):
        exam, options = self._exam(title="JS Loop")
        with bypass_rls():
            Exam.objects.filter(pk=exam.pk).update(subject=self.wrong_subject, author=self.center)
            exam.refresh_from_db()
            exam.allowed_units.add(self.group)
            exam_journal_link.refresh_links(exam)
        self._finish(exam, options, correct=2)  # 66.7% → yanlış fənnin jurnalına 20
        self.assertEqual(self._score_in(self.wrong_offering, self.wrong_enrollment).score, Decimal("20"))
        self.assertIsNone(self._score_in(self.offering, self.enrollment))
        return exam

    def _edit(self, exam, **extra):
        client = _login(self.center, self.org)
        with self.captureOnCommitCallbacks(execute=True):
            response = client.post(
                reverse("exams:edit_exam", kwargs={"slug": exam.slug}) + "?modal=1",
                self._payload(**extra),
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
        self.assertEqual(response.status_code, 200, response.content[:400])

    def test_changing_subject_after_attempts_moves_scores_to_new_journal(self):
        exam = self._taken_with_wrong_subject()
        self._edit(exam, subject=str(self.subject.pk), journal_teacher=str(self.teacher.pk))
        self.assertEqual(self._score_in(self.offering, self.enrollment).score, Decimal("20"))
        self.assertIsNone(self._score_in(self.wrong_offering, self.wrong_enrollment))  # köhnə xana silindi
        with bypass_rls():
            self.assertEqual(list(exam.journal_offerings.all()), [self.offering])
            cleared = AuditLog.objects.filter(resource_type=_AUDIT_TYPE, resource_id=str(self.wrong_offering.pk))
            self.assertTrue(any("silindi" in (c.get("note") or "") for log in cleared for c in log.changes))

    def test_manual_score_in_old_journal_is_not_touched(self):
        exam = self._taken_with_wrong_subject()
        with bypass_rls():
            other = ComponentScore.objects.get(enrollment=self.wrong_enrollment)
            ComponentScore.objects.filter(pk=other.pk).update(exam_source=None)  # «əl ilə yazılmış» xana
        self._edit(exam, subject=str(self.subject.pk))
        with bypass_rls():
            self.assertTrue(ComponentScore.objects.filter(pk=other.pk).exists())
        self.assertEqual(self._score_in(self.offering, self.enrollment).score, Decimal("20"))

    def test_resync_is_idempotent(self):
        exam = self._taken_with_wrong_subject()
        self._edit(exam, subject=str(self.subject.pk))
        with bypass_rls():
            exam.refresh_from_db()
            counts = exam_journal_link.resync_exam_journal(exam, notify=False)
            audits = AuditLog.objects.filter(resource_type=_AUDIT_TYPE).count()
            again = exam_journal_link.resync_exam_journal(exam, notify=False)
            self.assertEqual(AuditLog.objects.filter(resource_type=_AUDIT_TYPE).count(), audits)
        self.assertEqual(counts.get("unchanged"), 1)
        self.assertEqual(again.get("cleared", 0), 0)

    def test_unchanged_edit_schedules_no_resync(self):
        exam = self._taken_with_wrong_subject()
        with bypass_rls(), mock.patch.object(exam_journal_link, "resync_exam_journal") as resync:
            with self.captureOnCommitCallbacks(execute=True):
                scheduled = exam_journal_link.after_exam_saved(
                    exam,
                    previous_subject_id=exam.subject_id,
                    previous_link_ids=exam_journal_link.linked_offering_ids(exam),
                )
        self.assertFalse(scheduled)
        resync.assert_not_called()


class BackfillCommandTests(_LinkSetup):
    def _run(self, *args):
        out = StringIO()
        call_command("sync_midterm_scores", *args, stdout=out)
        return out.getvalue()

    def _legacy_js_loop(self):
        """Prod halı: cəhd yanlış fənnlə bitib, fənn SONRA birbaşa (köhnə kod, resync yox) düzəldilib."""
        exam, options = self._exam(title="JS Loop")
        with bypass_rls():
            Exam.objects.filter(pk=exam.pk).update(subject=self.wrong_subject)
            exam.refresh_from_db()
            exam.allowed_units.add(self.group)
        self._finish(exam, options, correct=3)
        with bypass_rls():
            Exam.objects.filter(pk=exam.pk).update(subject=self.subject)
        self.assertEqual(self._score_in(self.wrong_offering, self.wrong_enrollment).score, Decimal("30"))
        self.assertIsNone(self._score_in(self.offering, self.enrollment))
        return exam

    def test_dry_run_then_apply_fixes_js_loop(self):
        exam = self._legacy_js_loop()
        out = self._run("--org", self.org.slug, "--exam", exam.slug, "--dry-run")
        self.assertIn("DRY-RUN", out)
        self.assertIn("written 1", out)
        self.assertIn("cleared 1", out)
        self.assertIsNone(self._score_in(self.offering, self.enrollment))  # dry-run heç nə yazmır
        with bypass_rls():
            self.assertFalse(Exam.objects.get(pk=exam.pk).journal_offerings.exists())
        out = self._run("--org", self.org.slug, "--exam", str(exam.pk), "--apply")
        self.assertIn("YAZILDI", out)
        self.assertEqual(self._score_in(self.offering, self.enrollment).score, Decimal("30"))
        self.assertIsNone(self._score_in(self.wrong_offering, self.wrong_enrollment))
        with bypass_rls():
            self.assertEqual(list(Exam.objects.get(pk=exam.pk).journal_offerings.all()), [self.offering])
        again = self._run("--org", self.org.slug, "--exam", exam.slug, "--apply")
        self.assertIn("unchanged 1", again)
        self.assertIn("köhnə jurnal xanaları: —", again)

    def test_unknown_exam_is_an_error(self):
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            self._run("--exam", "no-such-exam")

    def test_hidden_results_are_not_written_but_wrong_journal_is_cleaned(self):
        exam = self._legacy_js_loop()
        with bypass_rls():
            Exam.objects.filter(pk=exam.pk).update(results_hidden_from_students=True)
        out = self._run("--exam", exam.slug, "--apply")
        self.assertIn("results_hidden 1", out)
        self.assertIsNone(self._score_in(self.offering, self.enrollment))
        self.assertIsNone(self._score_in(self.wrong_offering, self.wrong_enrollment))

    def test_attempt_is_official_only_once_per_student(self):
        exam = self._legacy_js_loop()
        with bypass_rls():
            attempts = ExamAttempt.objects.filter(exam=exam)
            self.assertEqual(len(list(midterm_journal_sync.official_attempts(attempts))), 1)


@pytest.mark.postgres
class RelinkRestrictedRoleTests(_LinkSetup):
    """İstehsal ssenarisi: NOBYPASSRLS rolu + tenant konteksti — bağlantı M2M-i (yeni RLS siyasəti), yeni
    jurnala yazı və köhnə jurnaldan silinmə RLS altında işləyir."""

    def test_relink_and_resync_under_rls_app_role(self):
        exam, options = self._exam(title="JS Loop")
        with bypass_rls():
            Exam.objects.filter(pk=exam.pk).update(subject=self.wrong_subject)
            exam.refresh_from_db()
            exam.allowed_units.add(self.group)
            exam_journal_link.refresh_links(exam)
        self._finish(exam, options, correct=2)
        with bypass_rls():
            Exam.objects.filter(pk=exam.pk).update(subject=self.subject)
        with connection.cursor() as cursor:
            cursor.execute("SELECT set_config('app.bypass_rls', 'off', true)")
            cursor.execute("SELECT set_config('app.current_org_id', %s, true)", [str(self.org.pk)])
            cursor.execute("SET LOCAL ROLE rls_app_role")
        try:
            fresh = Exam.objects.select_related("organization").get(pk=exam.pk)
            _old, new_ids = exam_journal_link.refresh_links(fresh)
            counts = exam_journal_link.resync_exam_journal(fresh, notify=False)
        finally:
            with connection.cursor() as cursor:
                cursor.execute("RESET ROLE")
                cursor.execute("SELECT set_config('app.bypass_rls', 'on', true)")
        self.assertEqual(new_ids, {self.offering.pk})
        self.assertEqual(counts.get("written"), 1)
        self.assertEqual(counts.get("cleared"), 1)
        self.assertEqual(self._score_in(self.offering, self.enrollment).score, Decimal("20"))
        self.assertIsNone(self._score_in(self.wrong_offering, self.wrong_enrollment))
