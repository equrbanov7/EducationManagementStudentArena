"""Owner report 2026-11-04: «yükü səhvən başqa müəllimə verdim, «Bərpa et» işləmir».

The exact flow: teacher A taught the journal, the operator moved BOTH load kinds to teacher B through the normal
«Yük bölgüsü» service (offering sync hands the journal to B). Restoring must give the load and the journal back to
A — from the owner's own admin list (``/jurnal/?teacher=A``) and from view-as FULL as A — with the real operator
in the audit trail, while a plain teacher gains nothing.

Root causes covered here: the admin «MÜƏLLİM» filter listed only owner/share journals, so A's moved journal had no
row (and no button) in the owner's own session; the front-end half (dead button on the full page) is in
``tests/js/journal_history_restore.test.js``.
"""

import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.registrar.models import CourseOffering, Lesson
from apps.registrar.teacher_journal_list import own_visible_queryset
from core.rls import bypass_rls

from ..constants import AmendmentReason, TaskStatus
from ..models import TeacherAssignment, TeachingTaskRow
from ..services.row_edit import assign_amended
from ..services.scoping import resolve_actor
from .factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task

REASON = "Yük səhvən başqa müəllimə verilmişdi, geri qaytarılır."


class MovedLoadRestoreTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.org = make_org("history-moved-load")
            cls.admin = cls.org.owner
            cls.admin.first_name, cls.admin.last_name, cls.admin.is_superuser = "Rim", "Rəhbəri", True
            cls.admin.save(update_fields=["first_name", "last_name", "is_superuser"])
            cls.stack = make_structure(cls.org, code="ML")
            User = get_user_model()
            cls.teacher = User.objects.create_user("ml_teacher", first_name="Aynur", last_name="Əvvəlki")
            cls.other = User.objects.create_user("ml_other", first_name="Bəhruz", last_name="Səhvən")
            for user in (cls.teacher, cls.other):
                activate_member(cls.org, user, "teacher", permissions=TEACHER_PERMS, scope_unit=cls.stack["chair"])
            cls.task = make_task(cls.org, cls.stack["chair"], status=TaskStatus.DISTRIBUTED)
            cls.row = make_row(cls.task, cls.stack, lecture_total=30, seminar_total=30)
            for kind in ("lecture", "seminar"):
                TeacherAssignment.objects.create(
                    organization=cls.org, row=cls.row, activity=kind, hours=30, teacher=cls.teacher
                )
            cls.offering = CourseOffering.objects.create(
                organization=cls.org,
                subject=cls.stack["subject"],
                period=cls.stack["period"],
                group=cls.stack["group"],
                instructor=cls.teacher,
                lesson_hours=60,
            )
            for kind in ("lecture", "seminar"):
                Lesson.objects.create(
                    organization=cls.org,
                    offering=cls.offering,
                    date=timezone.localdate(),
                    kind=kind,
                    hours=2,
                    instructor=cls.teacher,
                    created_by=cls.teacher,
                )

    def setUp(self):
        # The mistake, through the official distribution service (as «Yük bölgüsü» does it).
        with bypass_rls():
            actor = resolve_actor(self.admin, self.org)
            for prior in TeacherAssignment.objects.filter(row=self.row):
                assign_amended(
                    row=TeachingTaskRow.objects.select_related("task").get(pk=self.row.pk),
                    actor=actor,
                    activity=prior.activity,
                    teacher_id=self.other.pk,
                    hours=prior.hours,
                    assignment=prior,
                    amend={"reason": AmendmentReason.CORRECTION, "note": "Səhvən başqasına verildi"},
                )
            self.assertEqual(CourseOffering.objects.get(pk=self.offering.pk).instructor_id, self.other.pk)
            self.assertFalse(self.course().journal_is_current_load)

    # ── helpers ──────────────────────────────────────────────────────────────

    def course(self):
        queryset = CourseOffering.objects.filter(pk=self.offering.pk).select_related(
            "period", "subject", "group", "instructor"
        )
        return own_visible_queryset(queryset, self.teacher, self.org).get()

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()

    def post(self, *, teacher=None, reason=REASON):
        body = {"reason": reason}
        if teacher is not None:
            body["teacher"] = teacher.pk
        return self.client.post(
            reverse("workload:history_teacher_restore", args=[self.offering.pk]),
            data=json.dumps(body),
            content_type="application/json",
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            HTTP_ACCEPT="application/json",
        )

    def assert_restored(self):
        with bypass_rls():
            self.assertEqual(
                sorted(TeacherAssignment.objects.filter(row=self.row).values_list("activity", "teacher_id")),
                [("lecture", self.teacher.pk), ("seminar", self.teacher.pk)],
            )
            self.assertEqual(
                set(TeacherAssignment.objects.filter(row=self.row).values_list("assigned_by_id", flat=True)),
                {self.admin.pk},
            )
            self.assertEqual(CourseOffering.objects.get(pk=self.offering.pk).instructor_id, self.teacher.pk)
            self.assertTrue(self.course().journal_is_current_load)
            audit = AuditLog.objects.get(resource_type="workload.HistoryTeacherRestore")
            self.assertEqual((audit.user_id, audit.reason), (self.admin.pk, REASON))
            self.assertEqual(audit.new_values["teacher_id"], self.teacher.pk)

    def assert_untouched(self):
        with bypass_rls():
            self.assertEqual(
                set(TeacherAssignment.objects.filter(row=self.row).values_list("teacher_id", flat=True)),
                {self.other.pk},
            )
            self.assertEqual(CourseOffering.objects.get(pk=self.offering.pk).instructor_id, self.other.pk)
            self.assertFalse(AuditLog.objects.filter(resource_type="workload.HistoryTeacherRestore").exists())

    def assert_restore_ui(self, page):
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "data-jl-hrestore-open")
        self.assertContains(page, reverse("workload:history_teacher_restore", args=[self.offering.pk]))
        self.assertContains(page, "Bəhruz Səhvən → Aynur Əvvəlki (30 saat)")
        self.assertContains(page, "data-jl-hrestore-modal")
        self.assertContains(page, "registrar/js/journal_history_restore.js")

    # ── tests ────────────────────────────────────────────────────────────────

    def test_owner_own_session_teacher_filter_lists_the_moved_journal_and_restores_it(self):
        self.login(self.admin)
        # Müəllim filtri müəllimin öz siyahısını güzgüləyir (PR #199): köçürülmüş jurnal «Əvvəlki jurnal qeydləri»ndədir.
        page = self.client.get(reverse("registrar:journal_list") + "?teaching=history&teacher=" + str(self.teacher.pk))
        self.assertTrue(page.context["journal_is_broad"])
        self.assertIn(self.offering.pk, [offering.pk for offering in page.context["offerings"]])
        self.assert_restore_ui(page)
        self.assertContains(page, 'data-teacher-id="%s"' % self.teacher.pk)

        response = self.post(teacher=self.teacher)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(response.json()["status"], "restored")
        self.assert_restored()
        # Now current for her: the row no longer offers a restore.
        page = self.client.get(reverse("registrar:journal_list") + "?teacher=" + str(self.teacher.pk))
        self.assertNotContains(page, "data-jl-hrestore-open")

    def test_view_as_full_restores_with_the_real_operator_as_actor(self):
        self.login(self.admin)
        started = self.client.post(reverse("accounts:view_as_start"), {"user_id": self.teacher.pk, "org": self.org.pk})
        self.assertEqual(started.status_code, 302)
        page = self.client.get(reverse("registrar:journal_list") + "?teaching=history")
        self.assertEqual(page.context["request"].view_as_mode, "full")
        self.assert_restore_ui(page)

        response = self.post()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "restored")
        self.assert_restored()
        with bypass_rls():
            self.assertTrue(
                AuditLog.objects.filter(
                    user=self.admin, reason="view_as_action", changes__url_name="workload:history_teacher_restore"
                ).exists()
            )

    def test_plain_teachers_get_no_button_and_a_json_403(self):
        for user, teacher in ((self.teacher, None), (self.other, self.teacher)):
            self.login(user)
            page = self.client.get(reverse("registrar:journal_list") + "?teaching=history")
            self.assertEqual(page.status_code, 200)
            self.assertNotContains(page, "data-jl-hrestore-open")
            response = self.post(teacher=teacher)
            self.assertEqual(response.status_code, 403, response.content)
            self.assertEqual(response["Content-Type"], "application/json")
            self.assertFalse(response.json()["ok"])
        self.assert_untouched()
