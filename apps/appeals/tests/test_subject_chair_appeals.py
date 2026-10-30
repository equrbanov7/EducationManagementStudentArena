"""Subject ownership, scoped readonly chair/lab access and teacher-only IM invitation."""

from importlib import import_module
from types import SimpleNamespace
from urllib.parse import unquote

from django.apps import apps
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.appeals.models import Appeal
from apps.appeals.services.notify import notify_appeal_filed_teachers
from apps.appeals.services.permissions import can_decide_appeal, can_view_appeal
from apps.appeals.services.student_identity import student_group_map
from apps.appeals.services.subject_scope import PERMISSION, appeal_chair_map, scoped_queryset
from apps.appeals.services.teaching_scope import scoped_appeals, teaching_section_visible
from apps.appeals.tests.test_review_teacher_document_2026_10_21 import _ReviewSetup
from apps.notifications.models import InAppNotification
from apps.organizations.models import Membership, OrgUnit
from apps.registrar.models import Curriculum, StudentAcademicRecord
from apps.workload.models import TeachingTask, TeachingTaskRow
from apps.workload.tests.factories import make_org, make_structure
from core.rls import bypass_rls

User = get_user_model()


class SubjectChairAppealTests(_ReviewSetup):
    def setUp(self):
        super().setUp()
        with bypass_rls():
            self.owner_chair = OrgUnit.objects.create(
                organization=self.org, name="Subject owner", slug="appeal-owner", unit_type="chair"
            )
            self.other_chair = OrgUnit.objects.create(
                organization=self.org, name="Other chair", slug="appeal-other", unit_type="chair"
            )
            self.subject.chair_unit = self.owner_chair
            self.subject.save(update_fields=["chair_unit"])
            self.appeal.exam.subject = self.subject
            self.student.first_name, self.student.last_name = "Fatimə", "Əliyeva"
            self.student.save(update_fields=["first_name", "last_name"])
            self.student.profile.patronymic = "Rövşən"
            self.student.profile.save(update_fields=["patronymic"])
            self.chair_manager = self.member("appeal-chair", "chair_head", self.owner_chair)
            self.laborant = self.member("appeal-lab", "lab_assistant", self.owner_chair)
            self.other_manager = self.member("appeal-other-chair", "chair_head", self.other_chair)
            self.other_laborant = self.member("appeal-other-lab", "lab_assistant", self.other_chair)
            self.unitless = self.member("appeal-unitless", "lab_assistant", None)

    def member(self, username, role, unit):
        user = User.objects.create_user(username)
        Membership.objects.create(
            organization=self.org, user=user, role=self.org.roles.get(name=role), scope_unit=unit, is_active=True
        )
        return user

    def visible(self, user):
        with bypass_rls():
            return scoped_appeals(user, self.org)[0].filter(pk=self.appeal.pk).exists()

    def clean_notices(self):
        InAppNotification.objects.filter(metadata__appeal_id=self.appeal.pk).delete()

    def notice(self, user):
        return InAppNotification.objects.filter(recipient=user, metadata__appeal_id=self.appeal.pk)

    def test_default_grants_are_explicit_read_only_and_unit_scoped(self):
        for name in ("chair_head", "lab_assistant"):
            role = self.org.roles.get(name=name)
            self.assertIn(PERMISSION, role.permissions)
            self.assertNotIn("appeal.respond", role.permissions)
            self.assertNotIn("appeal.decide", role.permissions)
            self.assertEqual(role.scope_type, "unit")

    def test_owner_manager_and_laborant_see_course_appeal_but_other_chair_does_not(self):
        for user in (self.chair_manager, self.laborant):
            self.assertTrue(self.visible(user))
            self.assertTrue(teaching_section_visible(user, self.org))
        for user in (self.other_manager, self.other_laborant, self.unitless):
            self.assertFalse(self.visible(user))

    def test_subject_staff_get_readonly_drawer_with_full_identity_and_group(self):
        for user in (self.chair_manager, self.laborant):
            client = self._client(user)
            response = client.get(
                reverse("appeals:teaching_appeal_detail", args=[self.appeal.pk]),
                HTTP_X_REQUESTED_WITH="XMLHttpRequest",
            )
            self.assertEqual(response.status_code, 200)
            html = response.json()["html"]
            self.assertIn("Fatimə Əliyeva Rövşən", html)
            self.assertIn(self.student.username, html)
            self.assertIn(self.subject.name, html)
            self.assertNotIn("data-appeals-review-form", html)
            response = client.post(reverse("appeals:review_appeal", args=[self.appeal.pk]), {"decision": "accept"})
            self.assertIn(response.status_code, (403, 404))

    def test_canonical_read_permission_matches_subject_scope_without_decision_authority(self):
        for user, allowed in ((self.chair_manager, True), (self.laborant, True), (self.other_manager, False)):
            request = RequestFactory().get("/appeals/")
            request.user, request.organization = user, self.org
            self.assertEqual(can_view_appeal(request, self.appeal), allowed)
            self.assertFalse(can_decide_appeal(request, self.appeal))

    def test_published_exact_workload_overrides_subject_metadata_and_draft_does_not(self):
        with bypass_rls():
            task = TeachingTask.objects.create(
                organization=self.org,
                chair=self.other_chair,
                academic_year=self.offering.period.academic_year,
                status="draft",
            )
            row = TeachingTaskRow.objects.create(
                organization=self.org,
                task=task,
                subject=self.subject,
                period=self.offering.period,
                lecture_total=30,
                lecture_plan=30,
                total_hours=30,
            )
            row.groups.add(self.offering.group)
            self.assertTrue(self.visible(self.chair_manager))
            self.assertFalse(self.visible(self.other_manager))
            task.status = "distributed"
            task.save(update_fields=["status"])
            self.assertFalse(self.visible(self.chair_manager))
            self.assertTrue(self.visible(self.other_manager))

    def test_missing_authoritative_chair_does_not_infer_teacher_employment_or_group(self):
        self.subject.chair_unit = None
        self.subject.save(update_fields=["chair_unit"])
        Membership.objects.create(
            organization=self.org,
            user=self.subject_teacher,
            role=self.org.roles.get(name="teacher"),
            scope_unit=self.owner_chair,
        )
        self.assertFalse(self.visible(self.chair_manager))
        self.assertFalse(self.visible(self.laborant))

    def test_notification_invites_actual_teacher_and_informs_only_owning_chair_staff(self):
        with bypass_rls():
            self.clean_notices()
            notify_appeal_filed_teachers(self.appeal, item_count=1)
            teacher_note = self.notice(self.subject_teacher).get()
            self.assertIn("İmtahan Mərkəzinə yaxınlaşın", teacher_note.message)
            for text in (
                "Fatimə Əliyeva Rövşən",
                self.subject_teacher.first_name,
                self.subject.name,
                self.student.username,
            ):
                self.assertIn(text, teacher_note.message)
            for user in (self.chair_manager, self.laborant):
                note = self.notice(user).get()
                self.assertIn("Müəllim apellyasiya", note.message)
                self.assertIn("Fatimə Əliyeva Rövşən", note.message)
                self.assertIn(self.subject_teacher.first_name, note.message)
                self.assertIn(f"/organizations/switch/{self.org.slug}/", note.link)
                self.assertIn(f"ta_open={self.appeal.pk}", unquote(note.link))
            for user in (self.student, self.other_manager, self.other_laborant, self.unitless):
                self.assertFalse(self.notice(user).exists())

    def test_inactive_membership_or_role_revokes_read_and_new_notification(self):
        Membership.objects.filter(user=self.laborant, organization=self.org).update(is_active=False)
        self.assertFalse(self.visible(self.laborant))
        with bypass_rls():
            self.clean_notices()
            notify_appeal_filed_teachers(self.appeal, item_count=1)
            self.assertFalse(self.notice(self.laborant).exists())
        self.org.roles.filter(name="chair_head").update(is_active=False)
        self.assertFalse(self.visible(self.chair_manager))

    def test_teacher_with_revoked_grading_membership_is_not_invited(self):
        Membership.objects.filter(user=self.subject_teacher, organization=self.org).update(is_active=False)
        with bypass_rls():
            self.clean_notices()
            notify_appeal_filed_teachers(self.appeal, item_count=1)
            self.assertFalse(self.notice(self.subject_teacher).exists())

    def test_additional_unrelated_membership_cannot_lend_subject_scope(self):
        Membership.objects.create(
            organization=self.org,
            user=self.other_laborant,
            role=self.org.roles.get(name="teacher"),
            scope_unit=self.owner_chair,
        )
        self.assertFalse(self.visible(self.other_laborant))

    def test_same_user_foreign_org_record_does_not_replace_displayed_group(self):
        with bypass_rls():
            original = student_group_map(Appeal.objects.filter(pk=self.appeal.pk))[self.student.pk]
            foreign_org = make_org("appeal-foreign-student")
            stack = make_structure(foreign_org, code="APF")
            Membership.objects.create(
                organization=foreign_org, user=self.student, role=foreign_org.roles.get(name="student")
            )
            curriculum = Curriculum.objects.create(
                organization=foreign_org, program=stack["program"], admission_year=2025
            )
            StudentAcademicRecord.objects.create(
                organization=foreign_org,
                student=self.student,
                program=stack["program"],
                curriculum=curriculum,
                group=stack["group"],
                admission_year=2025,
            )
            self.assertEqual(student_group_map(Appeal.objects.filter(pk=self.appeal.pk))[self.student.pk], original)
            self.assertFalse(scoped_queryset(self.chair_manager, foreign_org).exists())

    def test_explicit_exam_teacher_notice_link_opens_even_without_current_enrollment(self):
        self.exam.journal_teacher = self.other_teacher
        self.exam.save(update_fields=["journal_teacher"])
        self.appeal.exam = self.exam
        self.assertTrue(self.visible(self.other_teacher))
        with bypass_rls():
            self.clean_notices()
            notify_appeal_filed_teachers(self.appeal, item_count=1)
            self.assertEqual(self.notice(self.other_teacher).count(), 1)

    def test_chair_map_does_not_cross_tenant(self):
        other_org = make_org("appeal-foreign-map")
        self.assertEqual(appeal_chair_map(Appeal.objects.filter(pk=self.appeal.pk), other_org), {})

    def test_current_student_gets_no_new_onsite_call_even_when_they_have_staff_role(self):
        Membership.objects.create(
            organization=self.org,
            user=self.student,
            role=self.org.roles.get(name="lab_assistant"),
            scope_unit=self.owner_chair,
        )
        with bypass_rls():
            self.clean_notices()
            notify_appeal_filed_teachers(self.appeal, item_count=1)
            self.assertFalse(self.notice(self.student).exists())

    def test_another_period_workload_never_infers_subject_owner(self):
        with bypass_rls():
            self.subject.chair_unit = None
            self.subject.save(update_fields=["chair_unit"])
            another = make_structure(self.org, code="AP-OTHER")
            task = TeachingTask.objects.create(
                organization=self.org, chair=self.other_chair, academic_year="2026/2027", status="distributed"
            )
            row = TeachingTaskRow.objects.create(
                organization=self.org,
                task=task,
                subject=self.subject,
                period=another["period"],
                lecture_plan=30,
                lecture_total=30,
                total_hours=30,
            )
            row.groups.add(self.offering.group)
            self.assertFalse(self.visible(self.chair_manager))
            self.assertFalse(self.visible(self.other_manager))

    def test_subject_scope_query_count_is_constant_for_more_appeals(self):
        scoped_queryset(self.chair_manager, self.org).count()
        with CaptureQueriesContext(connection) as small:
            scoped_queryset(self.chair_manager, self.org).count()
        for _index in range(6):
            Appeal.objects.create(organization=self.org, exam=self.exam, student=self.student, attempt=self.attempt)
        with CaptureQueriesContext(connection) as large:
            self.assertGreater(scoped_queryset(self.chair_manager, self.org).count(), 1)
        self.assertEqual(len(small), len(large))

    def test_existing_role_data_migration_is_idempotent_and_reversible(self):
        migration = import_module("apps.organizations.migrations.0079_subject_appeal_read_access")
        roles = list(self.org.roles.filter(name__in=("chair_head", "lab_assistant")))
        original = {}
        for role in roles:
            role.permissions = [key for key in role.permissions if key != PERMISSION]
            role.save(update_fields=["permissions"])
            original[role.pk] = list(role.permissions)

        def execute(sql):
            with connection.cursor() as cursor:
                cursor.execute(sql)

        editor = SimpleNamespace(connection=connection, execute=execute)
        migration.forward(apps, editor)
        migration.forward(apps, editor)
        for role in roles:
            role.refresh_from_db()
            self.assertEqual(role.permissions.count(PERMISSION), 1)
        migration.backward(apps, editor)
        for role in roles:
            role.refresh_from_db()
            self.assertNotIn(PERMISSION, role.permissions)
            self.assertEqual(role.permissions, original[role.pk])
