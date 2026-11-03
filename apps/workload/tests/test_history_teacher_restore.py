"""«Bu müəllimə bərpa et» — the history list always shows a restore state to privileged operators (owner 2026-11-03).

Root case: a seminar teacher's journal is owned by the lecturer and the seminar load moved to someone else;
the old button was silently hidden (``instructor != teacher``). Now: a ready button (view-as included) that
moves the load/ownership through existing services, or a disabled button with the concrete reason.
"""

import json

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditLog
from apps.registrar.models import CourseOffering, Lesson, TeachingHandover
from apps.registrar.public import handover_actions
from apps.registrar.teacher_journal_list import own_visible_queryset
from core.rls import bypass_rls

from ..constants import TaskStatus
from ..models import TeacherAssignment
from ..services import history_teacher_restore as service
from .factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task

REASON = "Seminar jurnalı müəllimin özünə qaytarılır."


class HistoryTeacherRestoreTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        with bypass_rls():
            cls.org = make_org("history-teacher-restore")
            cls.admin = cls.org.owner
            cls.admin.first_name, cls.admin.last_name, cls.admin.is_superuser = "Rim", "Rəhbəri", True
            cls.admin.save(update_fields=["first_name", "last_name", "is_superuser"])
            cls.stack = make_structure(cls.org, code="HT")
            cls.teacher = get_user_model().objects.create_user("ht_teacher", first_name="Çiçək", last_name="Seminarçı")
            cls.lecturer = get_user_model().objects.create_user(
                "ht_lecturer", first_name="Vahab", last_name="Mühazirəçi"
            )
            for user in (cls.teacher, cls.lecturer):
                activate_member(cls.org, user, "teacher", permissions=TEACHER_PERMS, scope_unit=cls.stack["chair"])
            cls.task = make_task(cls.org, cls.stack["chair"], status=TaskStatus.DISTRIBUTED)
            cls.offering = CourseOffering.objects.create(
                organization=cls.org,
                subject=cls.stack["subject"],
                period=cls.stack["period"],
                group=cls.stack["group"],
                instructor=cls.lecturer,
                lesson_hours=30,
            )
            Lesson.objects.create(
                organization=cls.org,
                offering=cls.offering,
                date=timezone.localdate(),
                kind="seminar",
                hours=2,
                instructor=cls.teacher,
            )

    def request(self, *, view_as=True, mode="full"):
        request = RequestFactory().post("/")
        request.user, request.organization = self.teacher, self.org
        request.real_user, request.is_view_as = (self.admin, True) if view_as else (self.teacher, False)
        request.view_as_mode = mode if view_as else None
        return request

    def course(self):
        queryset = CourseOffering.objects.filter(pk=self.offering.pk).select_related(
            "period", "subject", "group", "instructor"
        )
        return own_visible_queryset(queryset, self.teacher, self.org).get()

    def decorated(self, **kwargs):
        course = self.course()
        self.assertFalse(course.journal_is_current_load)
        service.attach(self.request(**kwargs), [course])
        return course

    def seminar_row(self, teacher):
        row = make_row(self.task, self.stack, lecture_total=0, seminar_total=30)
        TeacherAssignment.objects.create(organization=self.org, row=row, activity="seminar", hours=30, teacher=teacher)
        return row

    def view_as_client(self):
        self.client.force_login(self.admin)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()
        started = self.client.post(reverse("accounts:view_as_start"), {"user_id": self.teacher.pk, "org": self.org.pk})
        self.assertEqual(started.status_code, 302)

    def post(self, reason=REASON):
        url = reverse("workload:history_teacher_restore", args=[self.offering.pk])
        return self.client.post(url, data=json.dumps({"reason": reason}), content_type="application/json")

    def test_view_as_list_shows_button_and_restore_moves_the_seminar_load_to_this_teacher(self):
        with bypass_rls():
            row = self.seminar_row(self.lecturer)
        self.view_as_client()
        page = self.client.get(reverse("registrar:journal_list") + "?teaching=history")
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "data-jl-hrestore-open")
        self.assertContains(page, reverse("workload:history_teacher_restore", args=[self.offering.pk]))
        self.assertContains(page, "Vahab Mühazirəçi → Çiçək Seminarçı (30 saat)")
        self.assertContains(page, "data-jl-hrestore-modal")
        self.assertContains(page, "registrar/js/journal_history_restore.js")

        response = self.post()
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], "restored")
        with bypass_rls():
            assignment = TeacherAssignment.objects.get(row=row, activity="seminar")
            self.assertEqual((assignment.teacher_id, assignment.hours), (self.teacher.pk, 30))
            self.assertEqual(assignment.assigned_by_id, self.admin.pk)
            self.assertTrue(self.course().journal_is_current_load)
            audit = AuditLog.objects.get(resource_type="workload.HistoryTeacherRestore")
            self.assertEqual((audit.user_id, audit.reason), (self.admin.pk, REASON))

    def test_handed_over_journal_is_reverted_to_this_teacher(self):
        with bypass_rls():
            self.seminar_row(self.teacher)
            CourseOffering.objects.filter(pk=self.offering.pk).update(instructor=self.teacher)
            handover_actions.reassign(
                actor=self.admin,
                organization=self.org,
                offering_id=self.offering.pk,
                new_instructor_id=self.lecturer.pk,
                reason="Səhvən başqasına verildi",
            )
            record = TeachingHandover.objects.get(offering=self.offering)
            listed = self.decorated().history_teacher_restore
            self.assertEqual(listed["state"], service.READY)
            self.assertIn("Fənn təhvili geri qaytarılır", " ".join(listed["steps"]))
            result = service.restore_for_teacher(request=self.request(), offering_id=self.offering.pk, reason=REASON)
            self.assertEqual(result["status"], "restored")
            record.refresh_from_db()
            self.assertIsNotNone(record.reverted_at)
            self.assertEqual(record.reverted_by_id, self.admin.pk)
            self.assertEqual(CourseOffering.objects.get(pk=self.offering.pk).instructor_id, self.teacher.pk)
            self.assertTrue(self.course().journal_is_current_load)

    def test_journal_without_load_row_is_handed_over_to_this_teacher(self):
        with bypass_rls():
            listed = self.decorated().history_teacher_restore
            self.assertEqual(listed["state"], service.READY)
            self.assertIn("Jurnalın sahibi: Vahab Mühazirəçi → Çiçək Seminarçı", listed["steps"])
            service.restore_for_teacher(request=self.request(), offering_id=self.offering.pk, reason=REASON)
            record = TeachingHandover.objects.get(offering=self.offering, reverted_at__isnull=True)
            self.assertEqual((record.from_instructor_id, record.to_instructor_id), (self.lecturer.pk, self.teacher.pk))
            self.assertEqual(record.reason, REASON)
            self.assertTrue(self.course().journal_is_current_load)

    def test_patok_row_shows_disabled_button_with_reason_and_distribution_link(self):
        with bypass_rls():
            row = self.seminar_row(self.lecturer)
            row.groups.add(
                self.stack["group"].__class__.objects.create(
                    organization=self.org,
                    name="HT-237",
                    slug="ht-237",
                    unit_type="group",
                    parent=self.stack["specialty"],
                )
            )
        self.view_as_client()
        page = self.client.get(reverse("registrar:journal_list") + "?teaching=history")
        self.assertContains(page, 'disabled aria-disabled="true"')
        self.assertContains(page, "HT-237")
        self.assertContains(page, "row=" + str(row.pk))
        self.assertNotContains(page, "data-jl-hrestore-open")
        response = self.post()
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "workload.history_teacher_restore_patok")
        with bypass_rls():
            self.assertEqual(TeacherAssignment.objects.get(row=row).teacher_id, self.lecturer.pk)

    def test_plain_teacher_sees_nothing_and_cannot_restore(self):
        with bypass_rls():
            self.seminar_row(self.lecturer)
            course = self.decorated(view_as=False)
            self.assertFalse(hasattr(course, "history_teacher_restore"))
        self.client.force_login(self.teacher)
        session = self.client.session
        session["active_organization"] = self.org.slug
        session.save()
        page = self.client.get(reverse("registrar:journal_list") + "?teaching=history")
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, "jl-hrestore")
        response = self.post()
        self.assertEqual(response.status_code, 403)
        with bypass_rls():
            self.assertEqual(TeacherAssignment.objects.get().teacher_id, self.lecturer.pk)

    def test_readonly_view_as_shows_the_reason_instead_of_hiding_the_button(self):
        with bypass_rls():
            self.seminar_row(self.lecturer)
            listed = self.decorated(mode="readonly").history_teacher_restore
        self.assertEqual(listed["state"], service.BLOCKED)
        self.assertIn("tam baxış", listed["reason"])

    def test_short_reason_and_failed_final_check_write_nothing(self):
        with bypass_rls():
            row = self.seminar_row(self.lecturer)
            with self.assertRaises(service.Denied) as short:
                service.restore_for_teacher(request=self.request(), offering_id=self.offering.pk, reason="qısa")
            self.assertEqual(short.exception.status, 400)
            original = service._current

            def never_current(teacher, organization, offering_id):
                course = original(teacher, organization, offering_id)
                if course is not None:
                    course.journal_is_current_load = False
                return course

            service._current = never_current
            try:
                with self.assertRaises(service.Denied) as stale:
                    service.restore_for_teacher(request=self.request(), offering_id=self.offering.pk, reason=REASON)
            finally:
                service._current = original
            self.assertEqual(stale.exception.code, "workload.history_teacher_restore_not_current")
            self.assertEqual(TeacherAssignment.objects.get(row=row).teacher_id, self.lecturer.pk)
            self.assertEqual(CourseOffering.objects.get(pk=self.offering.pk).instructor_id, self.lecturer.pk)
