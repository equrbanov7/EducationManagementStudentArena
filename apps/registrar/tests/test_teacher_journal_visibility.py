"""Authoritative positive workload and narrow real-author history without new writes."""

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import connection
from django.http import Http404
from django.template.loader import render_to_string
from django.test import RequestFactory, TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.organizations.models import Membership, OrgUnit
from apps.registrar.journal_access import can_edit_journal, is_direct_editor
from apps.registrar.journal_list_scope import journal_list_base
from apps.registrar.journal_own_history import detail, eligible
from apps.registrar.models import CourseOffering, Enrollment, JournalShare, Lesson, LessonMark, TeachingHandover
from apps.registrar.page_contexts import journal_list_context
from apps.workload.constants import TaskStatus
from apps.workload.models import TeacherAssignment
from apps.workload.public import teacher_journal_assignments
from apps.workload.services.assignments import assign_teacher, unassign
from apps.workload.services.offering_sync import sync_task_offerings
from apps.workload.services.scoping import resolve_actor
from apps.workload.tests.factories import TEACHER_PERMS, activate_member, make_org, make_row, make_structure, make_task

User = get_user_model()


class TeacherJournalVisibilityTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.org = make_org("teacher-visible")
        cls.org.owner.is_superuser = True
        cls.org.owner.save(update_fields=["is_superuser"])
        cls.stack = make_structure(cls.org, code="TV")
        cls.task = make_task(cls.org, cls.stack["chair"], status=TaskStatus.AMENDED)
        cls.row = make_row(cls.task, cls.stack, lecture_total=30, seminar_total=30, lab_total=15)
        cls.teacher = User.objects.create_user("visible-teacher")
        cls.other = User.objects.create_user("visible-other")
        for teacher in (cls.teacher, cls.other):
            activate_member(cls.org, teacher, "teacher", permissions=TEACHER_PERMS)

    def request(self, user=None, **params):
        request = RequestFactory().get("/jurnal/", {"year": "", **params})
        request.user = user or self.teacher
        request.organization = self.org
        return request

    def offering(self, *, instructor=None, stack=None):
        stack = stack or self.stack
        return CourseOffering.objects.create(
            organization=self.org,
            subject=stack["subject"],
            group=stack["group"],
            period=stack["period"],
            instructor=instructor,
        )

    def context(self, **params):
        return journal_list_context(self.teacher, self.request(**params))

    def lesson(self, offering, **kwargs):
        return Lesson.objects.create(
            organization=self.org, offering=offering, date=timezone.localdate(), kind="seminar", **kwargs
        )

    def assignment(self, **kwargs):
        return TeacherAssignment.objects.create(
            organization=self.org, row=self.row, teacher=self.teacher, activity="seminar", hours=30, **kwargs
        )

    def test_confirmed_new_assignments_create_journal_and_all_types_immediately(self):
        actor = resolve_actor(self.org.owner, self.org)
        for kind, hours in (("lecture", 30), ("seminar", 30), ("lab", 15)):
            assign_teacher(row=self.row, actor=actor, activity=kind, teacher_id=self.teacher.pk, hours=hours)
        self.task.refresh_from_db()
        self.assertNotEqual(self.task.status, TaskStatus.DRAFT)
        offering = CourseOffering.objects.get(subject=self.stack["subject"], group=self.stack["group"])
        data = self.context()
        self.assertEqual([o.pk for o in data["offerings"]], [offering.pk])
        self.assertEqual(data["offerings"][0].slot_kinds, ["lecture", "seminar", "lab"])
        for kind in ("lecture", "seminar", "lab"):
            self.assertEqual([o.pk for o in self.context(kind=kind)["offerings"]], [offering.pk])

    def test_stale_empty_owner_and_manual_legacy_share_supply_no_current_load(self):
        own = self.offering(instructor=self.teacher)
        shared_stack = make_structure(self.org, code="TVS")
        shared = self.offering(instructor=self.other, stack=shared_stack)
        JournalShare.objects.create(organization=self.org, offering=shared, teacher=self.teacher, source="legacy")
        self.assertEqual(self.context()["offerings"], [])
        self.assertEqual(self.context(teaching="history")["offerings"], [])
        self.assertTrue(CourseOffering.objects.filter(pk=own.pk).exists())
        self.assertTrue(JournalShare.objects.filter(offering=shared, is_active=True).exists())

    def test_unassign_hides_empty_owner_without_deleting_journal(self):
        assignment = self.assignment()
        sync_task_offerings(self.task)
        offering = CourseOffering.objects.get(subject=self.stack["subject"])
        self.assertEqual(len(self.context()["offerings"]), 1)
        unassign(assignment=assignment, actor=resolve_actor(self.org.owner, self.org))
        self.assertEqual(self.context()["offerings"], [])
        self.assertEqual(self.context(teaching="history")["offerings"], [])
        self.assertTrue(CourseOffering.objects.filter(pk=offering.pk).exists())

    def test_unassigned_real_teacher_retains_only_history_and_no_write_access(self):
        assignment = self.assignment()
        sync_task_offerings(self.task)
        offering = CourseOffering.objects.get(subject=self.stack["subject"])
        self.lesson(offering, instructor=self.teacher, hours=3)
        unassign(assignment=assignment, actor=resolve_actor(self.org.owner, self.org))
        offering.refresh_from_db()
        self.assertIsNone(offering.instructor_id)
        self.assertFalse(can_edit_journal(self.teacher, offering))
        self.assertFalse(is_direct_editor(self.teacher, offering))
        self.assertEqual(self.context()["offerings"], [])
        data = self.context(teaching="history")
        row = data["offerings"][0]
        self.assertFalse(row.journal_is_current_load)
        self.assertEqual((row.journal_own_lessons, row.journal_own_hours), (1, 3))
        self.assertTrue(row.journal_own_history_link)
        self.assertEqual(detail(self.request(), offering).status_code, 200)
        html = render_to_string("registrar/partials/_journal_list_content.html", data, request=self.request())
        self.assertIn("?own_history=1", html)
        self.assertIn("Tarixçə: cari yük təyinatı yoxdur", html)

    def test_creator_and_mark_author_history_does_not_claim_other_teacher_hours(self):
        offering = self.offering(instructor=self.other)
        self.lesson(offering, instructor=self.other, created_by=self.teacher, hours=4)
        entered = self.lesson(offering, instructor=self.other, hours=2)
        foreign = self.lesson(offering, instructor=self.other, hours=7)
        for suffix in ("one", "two"):
            student = User.objects.create_user(f"visible-student-{suffix}")
            Membership.objects.create(organization=self.org, user=student, role=self.org.roles.get(name="student"))
            enrollment = Enrollment.objects.create(organization=self.org, offering=offering, student=student)
            LessonMark.objects.create(
                organization=self.org, lesson=entered, enrollment=enrollment, entered_by=self.teacher, score=8
            )
            LessonMark.objects.create(
                organization=self.org, lesson=foreign, enrollment=enrollment, entered_by=self.other, score=9
            )
        row = self.context(teaching="history")["offerings"][0]
        self.assertEqual((row.journal_own_lessons, row.journal_own_hours, row.journal_contributed_lessons), (0, 0, 2))
        response = detail(self.request(), offering)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "7 saat")
        self.assertContains(response, "8")
        self.assertNotContains(response, "save_finals")
        self.assertEqual(Lesson.objects.filter(offering=offering).count(), 3)

    def test_history_rejects_post_missing_evidence_inactive_membership_and_foreign_tenant(self):
        offering = self.offering(instructor=self.other)
        with self.assertRaises(Http404):
            detail(self.request(), offering)
        self.lesson(offering, instructor=self.teacher)
        request = RequestFactory().post("/jurnal/")
        request.user = self.teacher
        with self.assertRaises(Http404):
            detail(request, offering)
        Membership.objects.filter(organization=self.org, user=self.teacher).update(is_active=False)
        self.assertFalse(eligible(self.teacher, self.org))
        self.assertEqual(self.context(teaching="history")["offerings"], [])
        with self.assertRaises(Http404):
            detail(self.request(), offering)
        other_org = make_org("visible-foreign")
        self.assertFalse(eligible(self.teacher, other_org))

    def test_draft_cancelled_vacant_and_wrong_group_do_not_supply_current_visibility(self):
        self.assignment()
        offering = self.offering(instructor=self.teacher)
        for status in (TaskStatus.DRAFT, TaskStatus.CANCELLED):
            self.task.status = status
            self.task.save(update_fields=["status"])
            self.assertEqual(self.context()["offerings"], [])
        self.task.status = TaskStatus.DISTRIBUTED
        self.task.save(update_fields=["status"])
        other = make_structure(self.org, code="TVG")
        self.row.groups.set([other["group"]])
        self.assertEqual(self.context()["offerings"], [])
        self.row.groups.set([self.stack["group"]])
        TeacherAssignment.objects.filter(row=self.row).update(teacher=None)
        self.assertEqual(self.context()["offerings"], [])
        self.assertTrue(CourseOffering.objects.filter(pk=offering.pk).exists())

    def test_manual_kind_restriction_is_not_broadened_by_assignment(self):
        self.assignment()
        offering = self.offering(instructor=self.other)
        share = JournalShare.objects.create(
            organization=self.org, offering=offering, teacher=self.teacher, kinds=["lab"]
        )
        self.assertEqual(self.context()["offerings"], [])
        share.kinds = ["seminar"]
        share.save(update_fields=["kinds"])
        self.assertEqual(len(self.context(kind="seminar")["offerings"]), 1)
        self.assertEqual(self.context(kind="lab")["offerings"], [])

    def test_handover_observer_without_workload_remains_in_history(self):
        offering = self.offering(instructor=self.other)
        TeachingHandover.objects.create(
            organization=self.org,
            offering=offering,
            from_instructor=self.teacher,
            to_instructor=self.other,
            performed_by=self.org.owner,
        )
        self.assertEqual(self.context()["offerings"], [])
        history = self.context(teaching="history")["offerings"]
        self.assertEqual([o.pk for o in history], [offering.pk])
        self.assertFalse(history[0].journal_own_history_link)

    def test_broad_scope_keeps_empty_offerings_and_current_history_filter_does_not_apply(self):
        offering = self.offering(instructor=self.teacher)
        admin = User.objects.create_user("visible-admin", is_superuser=True)
        request = self.request(admin, teaching="history")
        data = journal_list_context(admin, request)
        self.assertTrue(data["journal_is_broad"])
        self.assertEqual([o.pk for o in data["offerings"]], [offering.pk])

    def test_verified_alias_is_resolved_both_directions_without_rebinding(self):
        target = make_structure(self.org, code="TVA")["group"]
        self.assignment()
        offering = self.offering(instructor=self.teacher)
        # Provider contract is already independently guarded by exact 233KE tests.
        alias = {self.stack["group"].pk: target}
        with (
            patch("apps.workload.services.journal_assignments.canonical_aliases", return_value=alias),
            patch("apps.registrar.teacher_journal_list.canonical_aliases", return_value=alias),
        ):
            keys = teacher_journal_assignments(organization=self.org, teacher_id=self.teacher.pk)
            self.assertIn((self.row.subject_id, self.row.period_id, target.pk), keys)
            self.assertEqual([o.pk for o in self.context()["offerings"]], [offering.pk])
        offering.refresh_from_db()
        self.assertEqual(offering.group_id, self.stack["group"].pk)

    def test_author_history_query_count_is_constant_with_mark_volume(self):
        offering = self.offering(instructor=self.other)
        self.lesson(offering, instructor=self.teacher)
        with CaptureQueriesContext(connection) as first:
            journal_list_base(self.teacher, self.request())[0].count()
        for _index in range(12):
            self.lesson(offering, instructor=self.teacher)
        with CaptureQueriesContext(connection) as second:
            journal_list_base(self.teacher, self.request())[0].count()
        self.assertEqual(len(first), len(second))

    def child(self, suffix, **settings):
        parent = self.stack["group"]
        return OrgUnit.objects.create(
            organization=self.org,
            name=f"TV-236-{suffix}",
            slug=f"tv-child-{suffix}",
            unit_type="group",
            parent=parent.parent,
            settings={**parent.settings, "parent_group": str(parent.pk), **settings},
        )

    def test_parent_positive_load_keeps_registered_child_journals_visible(self):
        self.assignment()
        one, two = self.child("1"), self.child("2")
        for child in (one, two):
            CourseOffering.objects.create(
                organization=self.org,
                subject=self.stack["subject"],
                period=self.stack["period"],
                group=child,
                instructor=self.teacher,
            )
        self.assertEqual({o.group_id for o in self.context()["offerings"]}, {one.pk, two.pk})
        # No duplicated payable-hours total is inferred from two child journals.
        self.assertTrue(all(o.journal_own_hours == 0 for o in self.context()["offerings"]))

    def test_child_specific_note_never_expands_to_parent_or_other_child_or_sector(self):
        self.stack["group"].settings = {"sector": "az"}
        self.stack["group"].save(update_fields=["settings"])
        one, two = self.child("1"), self.child("2")
        english = self.child("eng", sector="en")
        self.assignment(groups_note=one.name)
        keys = teacher_journal_assignments(organization=self.org, teacher_id=self.teacher.pk)
        self.assertEqual({key[2] for key in keys}, {one.pk})
        TeacherAssignment.objects.filter(row=self.row).update(groups_note="")
        keys = teacher_journal_assignments(organization=self.org, teacher_id=self.teacher.pk)
        self.assertEqual({key[2] for key in keys}, {self.stack["group"].pk, one.pk, two.pk})
        self.assertNotIn(english.pk, {key[2] for key in keys})

    def test_registered_children_with_unknown_metadata_remain_valid_but_other_parent_does_not(self):
        self.assignment()
        child = self.child("unknown", sector="az")
        foreign_parent = make_structure(self.org, code="TVP")["specialty"]
        unrelated = self.child("unrelated")
        unrelated.parent = foreign_parent
        unrelated.save(update_fields=["parent"])
        keys = teacher_journal_assignments(organization=self.org, teacher_id=self.teacher.pk)
        self.assertIn(child.pk, {key[2] for key in keys})
        self.assertNotIn(unrelated.pk, {key[2] for key in keys})

    def test_history_cannot_reveal_another_authors_lesson_or_cells(self):
        offering = self.offering(instructor=self.other)
        own = self.lesson(offering, instructor=self.teacher, topic="Own evidence")
        self.lesson(offering, instructor=self.other, topic="Other teacher private lesson")
        student = User.objects.create_user("visible-history-student", first_name="Private cell")
        Membership.objects.create(organization=self.org, user=student, role=self.org.roles.get(name="student"))
        enrollment = Enrollment.objects.create(organization=self.org, offering=offering, student=student)
        LessonMark.objects.create(
            organization=self.org, lesson=own, enrollment=enrollment, entered_by=self.other, score=10
        )
        response = detail(self.request(), offering)
        self.assertContains(response, "Own evidence")
        self.assertNotContains(response, "Other teacher private lesson")
        self.assertNotContains(response, "Private cell")

    def test_detail_fallback_after_unassignment_is_get_only_and_creates_no_scheme(self):
        from apps.registrar.models import AssessmentScheme
        from apps.registrar.views import journal_detail

        offering = self.offering(instructor=self.other)
        self.lesson(offering, instructor=self.teacher)
        request = self.request()
        # Canonical tenant-loader behavior is covered by its existing route tests.
        with patch("apps.registrar.journal_access.offering_or_404", return_value=offering):
            response = journal_detail(request, offering.pk)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AssessmentScheme.objects.filter(offering=offering).exists())
        request.method = "POST"
        request.POST = {}
        with patch("apps.registrar.journal_access.offering_or_404", return_value=offering), self.assertRaises(Http404):
            journal_detail(request, offering.pk)
